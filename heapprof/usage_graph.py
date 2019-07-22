import colorsys
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, NamedTuple, TextIO, Tuple

from ._si_prefix import bytesString
from .types import RawTraceLine, Snapshot


class UsageGraph(NamedTuple):
    """A UsageGraph is one of the basic ways to analyze how memory was being used by a process at a
    snapshot of time. If you've ever used a graph view of a CPU or memory profiler, this will be
    familiar. Essentially, you can imagine the state of the process as a moment as a directed graph,
    where each node represents a line of code at which either some memory was being allocated, or
    some other function was being called.

        * The "local usage" at a node is the amount of memory that has been allocated at that
          precise line of code. It is, of course, nonzero only for lines that actually allocate
          memory, and the sum of local usage over all nodes is the total memory usage. In terms of
          stack traces, it's the total allocation at all stack traces which *end* at this particular
          line of code.
        * The "cumulative usage" for a node is the amount of memory that is allocated by this node,
          and by all lines called from it. It is, therefore, going to be largest at the top of the
          graph, and if there's a single root line of code (which there is iff the program is
          single-threaded), the cumulative usage for the topmost node is equal to the total usage of
          the program. In terms of stack traces, it's the total allocation at all stack traces which
          *contain* this particular line of code.
        * The weight of an edge between two lines of code A and B is the total amount of memory
          allocated by operations that go from A directly to B in their stack trace -- that is, it's
          the total allocation of stack traces which contain the sequence "AB" with nothing in
          between.

    Why is this definition of an edge weight useful? Because it has the nice property that for any
    node, the sum of all incoming edge weights is equal to the local weight of the node plus the sum
    of all outgoing edge weights -- i.e., it shows how much memory usage "flows through" that edge.
    For example, say that at a given point in time, our memory usage showed that memory had been
    allocated at the following stack traces, where letters denote lines of code:

    AD=16                    0/73 A---- 57       10 ----B 0/10
    ACD=17                        |    ＼  24/67   /
    ACE=19    == Graph ==>     16 |     ---> C <---
    AC=21                         |         / ＼
    BC=3                          v     24 /   ＼19
    BCD=7                   40/40 D<-------     ------->E 19/19

    The ASCII graph shows for each node, "local / cumulative", and for each edge, the edge weight.
    This means, for example, that node A allocated no memory itself, but 73 bytes of allocation
    stream from it; those divide up into 16 via calls from A directly to D, and the other 57 in
    calls from A to C. Node C, on the other hand, directly allocates 24 bytes, and indirectly
    another 24 in calls to D and 19 in calls to E. Most of the immediate allocation of memory
    happens at D, which directly allocates 40 bytes.

    In the most useful visual representation, these are output as a graph, where the size of each
    node is proportional to its local size -- that lets you visually see exactly where most of the
    memory has been allocated at a glance, with line thicknesses (set by edge weight) showing you
    the primary flows of code which led there. That latter is important when there are multiple
    paths to a node; for example, in the diagram above, the A->C call path is much more significant
    than the B->C one!

    You can also compare UsageGraphs computed at two different times, and this can give critical
    insight into time dependencies. For example, say that your program has a natural flow of data
    where data is allocated (say, read in from disk) at point A, processed through stages B, C, and
    D, then written to a buffer at line E, and the output finally committed to disk and deallocated
    at line F. Say also that at some moment in time, overall memory usage for your program spikes.
    If the before and after of the spike were both during this processing flow (as opposed to, say,
    "before the flow vs during the flow," in which case the problem would be obvious), it can be
    very useful to compare the _fraction_ of total memory allocated at A, B, C, D, E, and F, as well
    as total memory usage T, during the before and during snapshots.

    For example, if the fractions for A-F were all roughly the same both before and during the
    memory spike, this would tell you that during the spike, a lot more data is being read in, but
    the rest of the flow is proceeding as usual. If, on the other hand, the fractions for D, E, and
    F dropped during the spike, that would mean that less data (proportionally) was reaching them,
    which would imply that data was being held up at point C during the spike more than it was
    before -- a good hint as to where the problem might lie. Conversely, if fractional memory
    usage at D, E, and F was _higher_ during the spike than before it, that might imply that D was
    generating more data than it was before, creating additional load on E and F. This
    interpretation would have to do with D being a processing stage; if memory usage at E alone were
    higher, that would imply that more memory was building up in the buffer during the spike, which
    might imply that the buffer's draining at F was not functioning -- perhaps the spike was caused
    by a problem in writing the data back out to disk?

    While there isn't a completely generic tool for doing this analysis, this kind of information
    can be invaluable in tracing down odd phenomena.
    """

    # The best way to create a UsageGraph is with Reader.usageGraph().
    nodeLocalUsage: Dict[RawTraceLine, int]
    nodeCumulativeUsage: Dict[RawTraceLine, int]
    edgeUsage: Dict[Tuple[RawTraceLine, RawTraceLine], int]
    totalUsage: int

    def asDotFile(
        self,
        dotFile: TextIO,
        minNodeFraction: float = 0.01,
        minEdgeFraction: float = 0.05,
        collapseLines: bool = True,
    ) -> None:
        """Write out a UsageGraph as a dot graph. The result can be visualized using graphviz, with
        a command like

            dot -T pdf -o foo.pdf foo.dot

        See www.graphviz.org for where you can get graphviz for your system.

        Args:
            dotFile: Where the data should be written.
            minNodeFraction: Nodes whose local size is less than this fraction of total usage
                are dropped for visual clarity.
            minEdgeFraction: Edges whose size is less than this fraction of their source node's
                cumulative usage are dropped for visual clarity.
            collapseLines: If True, groups of trace lines that have no branching can get merged
                into each other.
        """
        if minNodeFraction < 0 or minNodeFraction > 1:
            raise ValueError('minNodeFraction must be in [0, 1]')

        minNodeSize = int(self.totalUsage * minNodeFraction)

        if minEdgeFraction < 0 or minEdgeFraction > 1:
            raise ValueError('minEdgeFraction must be in [0, 1]')

        # Edges are colored by edge fraction; white is assigned to minEdgeFraction, black to
        # max(minEdgeFraction, 0.5), and we do a linear gradient between those two points.
        blackCutoff = max(minEdgeFraction, 0.5)
        scaleDenom = 255 / (blackCutoff - minEdgeFraction) if blackCutoff > minEdgeFraction else 0

        @dataclass
        class NodeInfo:
            cumSize: int
            localSize: int
            traceLines: List[RawTraceLine]

        # Build the list of graph nodes
        nodes: Dict[str, NodeInfo] = {}
        for node, cumSize in self.nodeCumulativeUsage.items():
            if cumSize < minNodeSize:
                continue
            nodes[self._nodeId(node)] = NodeInfo(cumSize, self.nodeLocalUsage.get(node, 0), [node])

        # Build the connection list, from src node ID to end node ID + size
        outgoingEdges: Dict[str, List[Tuple[str, int]]] = defaultdict(list)
        incomingEdges: Dict[str, List[Tuple[str, int]]] = defaultdict(list)
        for edge, edgeSize in self.edgeUsage.items():
            src, dst = edge

            srcId = self._nodeId(src)
            if srcId not in nodes:
                continue
            dstId = self._nodeId(dst)
            if dstId not in nodes:
                continue

            outgoingEdges[srcId].append((dstId, edgeSize))
            incomingEdges[dstId].append((srcId, edgeSize))

        # Next, collapse graph nodes. nodeMap will be a map from "old" (pre-collapse) to "new"
        # (post-collapse) node ID's; absence means the node is unchanged.
        nodeMap: Dict[str, str] = {}

        if collapseLines:
            for nodeId, nodeInfo in nodes.items():
                # If a node has essentially no local contribution and one outgoing edge,
                # and that child has only this as a parent, collapse those two nodes.
                if nodeInfo.localSize >= 0.01 * nodeInfo.cumSize:
                    continue
                outEdges = outgoingEdges.get(nodeId, [])
                if len(outEdges) != 1:
                    continue

                # We might want to collapse dstId into this node.
                dstId, _ = outEdges[0]
                dstId = nodeMap.get(dstId, dstId)

                childInEdges = incomingEdges.get(dstId, [])
                if len(childInEdges) != 1:
                    continue

                # If we get here, we want to collapse dstId into nodeId! Check if nodeId has already
                # been remapped, too.
                srcId = nodeMap.get(nodeId, nodeId)
                srcInfo = nodes[srcId]

                dstInfo = nodes[dstId]
                nodeMap[dstId] = srcId

                srcInfo.localSize += dstInfo.localSize
                srcInfo.traceLines.extend(dstInfo.traceLines)

        # Output
        dotFile.write('digraph {\n')
        dotFile.write('  node [shape="box" fontcolor="white" style="filled"];\n')
        for nodeId, nodeInfo in nodes.items():
            if nodeId in nodeMap:
                continue

            attrs: List[str] = []

            label = [f'{x.filename}:{x.lineno}' for x in nodeInfo.traceLines]
            label.append(f'{bytesString(nodeInfo.localSize)} / {bytesString(nodeInfo.cumSize)}')
            labelString = '\n'.join(label)
            attrs.append(f'label="{labelString}"')

            # The size of a node is a function of its local size
            attrs.append(f'fontsize={self._fontSize(nodeInfo.localSize)}')
            # The color of a node is a function of its cumulative size, from 200° (blue) at no size
            # to 360° (red) at max size.
            attrs.append(f'fillcolor="{self._color(nodeInfo.cumSize)}"')

            dotFile.write(f'  {nodeId} [{" ".join(attrs)}];\n')

        for srcId, dstIds in outgoingEdges.items():
            srcId = nodeMap.get(srcId, srcId)
            for dstId, edgeSize in dstIds:
                dstId = nodeMap.get(dstId, dstId)

                # Skip self-edges, which can happen when nodes are collapsed.
                if srcId == dstId:
                    continue

                fracWeight = edgeSize / nodes[srcId].cumSize
                if fracWeight < minEdgeFraction:
                    continue

                if fracWeight >= blackCutoff:
                    color = 0
                else:
                    color = int((blackCutoff - fracWeight) * scaleDenom)

                colorString = f'"#{color:02x}{color:02x}{color:02x}"'
                attrs = [f'color={colorString}', f'label="{bytesString(edgeSize)}"']

                dotFile.write(f'  {srcId} -> {dstId} [{" ".join(attrs)}];\n')

        dotFile.write('}\n')

    def writeDotFile(self, filename: str, **kwargs) -> None:
        """Convenience helper for interactive analysis."""
        with open(filename, 'w') as output:
            self.asDotFile(output, **kwargs)

    _MIN_FONT_SIZE = 15
    _MAX_FONT_SIZE = 200
    _SCALE_STARTS_AT = 0.01

    _FONT_SCALE_CONSTANT = (_MAX_FONT_SIZE - _MIN_FONT_SIZE) / (1 - _SCALE_STARTS_AT)

    _MIN_HUE = 200 / 360
    _MAX_HUE = 1
    # _SATURATION = 0.52
    _SATURATION = 0.7
    _VALUE = 0.95

    def _nodeId(self, node: RawTraceLine) -> str:
        return f'n{abs(hash(node)):016x}'

    def _fontSize(self, localSize: int) -> int:
        sizeFrac = localSize / self.totalUsage
        return int(
            self._MIN_FONT_SIZE
            + max(0, (sizeFrac - self._SCALE_STARTS_AT)) * self._FONT_SCALE_CONSTANT
        )

    def _color(self, cumSize: int) -> str:
        # The color of a node is a function of its cumulative size, from 170° (blue) at no size
        # to 360° (red) at max size.
        cumSizeFrac = cumSize / self.totalUsage
        hue = self._MIN_HUE + (self._MAX_HUE - self._MIN_HUE) * cumSizeFrac
        r, g, b = colorsys.hsv_to_rgb(hue, self._SATURATION, self._VALUE)
        return f'#{self._colorAsHex(r)}{self._colorAsHex(g)}{self._colorAsHex(b)}'

    def _colorAsHex(self, v: float) -> str:
        return f'{int(255 * v):02x}'


class UsageHistory(List[Tuple[Snapshot, UsageGraph]]):
    """UsageHistory shows the complete timeline of usage for a heap profile."""

    def __init__(self, *data: Tuple[Snapshot, UsageGraph]) -> None:
        super().__init__(data)
