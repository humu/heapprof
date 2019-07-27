import colorsys
import html
import io
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, NamedTuple, Set, TextIO, Tuple

from ._si_prefix import bytesString
from .types import RawTraceLine


"""The internal logic of rendering a collection of 'FlowGraph's as a dot file. The idea is that
we may receive multiple 'FlowGraph's, which represent different time slices of the same world,
and we want to build a unified visual representation showing all three. See the comment on
FlowGraph.compare() for an explanation of what the output will look like.

This logic is in a separate file simply for clarity for the reader, as it's hairy, nothing but
implementation details, and might otherwise obscure the very important FlowGraph class.
"""


def makeDotFile(
    output: TextIO,
    graphs: List['FlowGraph'],
    minNodeFraction: float = 0.01,
    minEdgeFraction: float = 0.05,
    collapseNodes: bool = True,
    sizeNodesBasedOnLocalUsage: bool = True,
) -> None:
    if minNodeFraction < 0 or minNodeFraction > 1:
        raise ValueError('minNodeFraction must be in [0, 1]')

    if minEdgeFraction < 0 or minEdgeFraction > 1:
        raise ValueError('minEdgeFraction must be in [0, 1]')

    nodes = _makeNodes(graphs, minNodeFraction)
    edges = _makeEdges(graphs, nodes, minEdgeFraction)
    _makeRootNode(graphs, nodes, edges)
    nodeMap: Dict[str, str] = {}
    if collapseNodes:
        _collapseNodes(graphs, nodes, edges, nodeMap)
    _render(output, graphs, nodes, edges, nodeMap, minEdgeFraction, sizeNodesBasedOnLocalUsage)


def _nodeId(line: RawTraceLine) -> str:
    """A node ID which can be easily used in dot files."""
    return f'n{abs(hash(line)):016x}'


###############################################################################################
# Visual computations


_MIN_FONT_SIZE = 15
_MAX_FONT_SIZE = 200
_SCALE_STARTS_AT = 0.01

_FONT_SCALE_CONSTANT = (_MAX_FONT_SIZE - _MIN_FONT_SIZE) / (1 - _SCALE_STARTS_AT)

# Warning before you mess with these parameters: They are chosen specifically so that this range is
# clearly distinguishable even with various types of color blindness. If you make any adjustments to
# this, make sure to run the output through the COBLIS simulator at color-blindness.com, at least to
# handle dichromatic views.
_MIN_HUE = 200 / 360
_MAX_HUE = 1
_SATURATION = 0.7
_VALUE = 0.95


def _fontSize(sizeFrac: float) -> int:
    return int(_MIN_FONT_SIZE + max(0, (sizeFrac - _SCALE_STARTS_AT)) * _FONT_SCALE_CONSTANT)


def _color(cumSizeFrac: float) -> str:
    # The color of a node is a function of its cumulative size, from 170° (blue) at no size
    # to 360° (red) at max size.
    hue = _MIN_HUE + (_MAX_HUE - _MIN_HUE) * cumSizeFrac
    r, g, b = colorsys.hsv_to_rgb(hue, _SATURATION, _VALUE)
    return f'#{_colorAsHex(r)}{_colorAsHex(g)}{_colorAsHex(b)}'


def _colorAsHex(v: float) -> str:
    return f'{int(255 * v):02x}'


###############################################################################################
# The data representation of nodes


@dataclass
class _NodeSize:
    cumSize: int = 0
    localSize: int = 0


class _NodeInfo(NamedTuple):
    # The trace lines represented by this node.
    traceLines: List[RawTraceLine]
    # A list, parallel to the input graphs, of (cumSize, localSize) pairs.
    sizes: List[_NodeSize]

    def add(self, other: '_NodeInfo') -> None:
        """Combine the data of other into self. "other" is always a descendant node of self."""
        assert len(other.sizes) == len(self.sizes)
        self.traceLines.extend(other.traceLines)
        for mySize, theirSize in zip(self.sizes, other.sizes):
            # NB that we don't add up cumulative sizes, because those are already sums!
            mySize.localSize += theirSize.localSize

    def fontSize(self, graphs: List['FlowGraph'], usageSizing: bool) -> int:
        if len(graphs) != len(self.sizes):
            raise AssertionError(f'Unexpected: {len(graphs)} graphs but this node is {self}')
        if not usageSizing:
            return _MIN_FONT_SIZE
        return _fontSize(
            max(size.localSize / graph.totalUsage for size, graph in zip(self.sizes, graphs))
        )

    def label(self, graphs: List['FlowGraph']) -> str:
        """Construct a dot HTML label, given an array of total memory sizes at each graph."""
        if len(graphs) != len(self.sizes):
            raise AssertionError(f'Unexpected: {len(graphs)} graphs but this node is {self}')

        if not self.traceLines:
            return ''

        result = io.StringIO()

        # NB: dot HTML syntax is a restricted subset of HTML, and the whole thing is wrapped in < >.
        # That is, what's below is not a typo, nor should you be using standard HTML-generating code
        # to make it.
        result.write(f'< <table border="1" cellborder="0" cellspacing="0">')

        # Trace lines live in horizontal spanning cells. NB that the filename is the only string in
        # this output that we don't directly synthesize, so we need to HTML-escape it for safety!
        for traceLine in self.traceLines:
            codeLine = html.escape(traceLine.filename)
            line = f'{codeLine}:{traceLine.lineno}' if traceLine.lineno else codeLine
            result.write(f'<tr><td colspan="{len(self.sizes)}" bgcolor="white">{line}</td></tr>')

        # Sizes live in vertically slices cells.
        result.write('<tr>')
        for index, (nodeSize, graph) in enumerate(zip(self.sizes, graphs)):
            fracUsage = nodeSize.cumSize / graph.totalUsage
            color = _color(fracUsage)
            result.write(
                f'<td color="white" bgcolor="{color}" cellspacing="4">'
                f'{bytesString(nodeSize.localSize)} / {bytesString(nodeSize.cumSize)} = '
                f'{int(100 * fracUsage):2d}%</td>'
            )
        result.write('</tr></table> >')

        return result.getvalue()


def _makeNodes(graphs: List['FlowGraph'], minNodeFraction: float) -> Dict[str, _NodeInfo]:
    """Build the initial set of nodes."""
    result: Dict[str, _NodeInfo] = {}
    for index, graph in enumerate(graphs):
        for node, cumSize in graph.nodeCumulativeUsage.items():
            nodeId = _nodeId(node)
            if nodeId not in result:
                result[nodeId] = _NodeInfo([node], [_NodeSize() for i in range(len(graphs))])

            result[nodeId].sizes[index].cumSize = cumSize
            result[nodeId].sizes[index].localSize = graph.nodeLocalUsage.get(node, 0)

    # Now prune tiny nodes -- but only do that now, once we know all their sizes.
    minNodeSize = [minNodeFraction * graph.totalUsage for graph in graphs]
    for nodeId, nodeInfo in list(result.items()):
        if all(size.cumSize < minSize for size, minSize in zip(nodeInfo.sizes, minNodeSize)):
            del result[nodeId]

    return result


###############################################################################################
# The data representation of edges

_EdgeList = Dict[str, Set[str]]


class _NodeEdges(NamedTuple):
    incomingEdges: _EdgeList  # dict dst -> srces
    outgoingEdges: _EdgeList  # dict src -> dsts

    # This is a dict from (srcId, dstId) to a list of sizes parallel to the set of graphs.
    edgeSizes: Dict[Tuple[str, str], List[int]]


def _makeEdges(
    graphs: List['FlowGraph'], nodes: Dict[str, _NodeInfo], minEdgeFraction: float
) -> _NodeEdges:
    """Build the initial set of edges. Returns a list of edge sets parallel to graphs.
    """
    edges = _NodeEdges(defaultdict(set), defaultdict(set), {})
    for index, graph in enumerate(graphs):
        for (src, dst), edgeSize in graph.edgeUsage.items():
            srcId = _nodeId(src)
            if srcId not in nodes:
                continue
            dstId = _nodeId(dst)
            if dstId not in nodes:
                continue

            srcCumSize = nodes[srcId].sizes[index].cumSize
            fracWeight = edgeSize / srcCumSize if srcCumSize else 1

            if fracWeight < minEdgeFraction:
                continue

            edges.incomingEdges[dstId].add(srcId)
            edges.outgoingEdges[srcId].add(dstId)

            sizeKey = (srcId, dstId)
            if sizeKey not in edges.edgeSizes:
                edges.edgeSizes[sizeKey] = [0] * len(graphs)
            edges.edgeSizes[sizeKey][index] = edgeSize

    return edges


###############################################################################################
# Node merging logic


def _makeRootNode(
    graphs: List['FlowGraph'], nodes: Dict[str, _NodeInfo], edges: _NodeEdges
) -> None:
    """If there isn't already a unique root node to the graph, create a synthetic one that has the
    overall program usage data in it.
    """
    rootNodes: Set[set] = set()
    for nodeId in nodes.keys():
        if nodeId not in edges.incomingEdges:
            rootNodes.add(nodeId)

    if len(rootNodes) < 2:
        return

    newRoot = _NodeInfo(
        [RawTraceLine('Program Root', '0')],
        [_NodeSize(cumSize=graph.totalUsage, localSize=0) for graph in graphs],
    )
    newRootId = 'root'

    nodes[newRootId] = newRoot
    for rootNode in rootNodes:
        edges.outgoingEdges[newRootId].add(rootNode)
        edges.incomingEdges[rootNode].add(newRootId)

        rootNodeInfo = nodes[rootNode]
        edges.edgeSizes[(newRootId, rootNode)] = [size.cumSize for size in rootNodeInfo.sizes]


def _collapseNodes(
    graphs: List['FlowGraph'],
    nodes: Dict[str, _NodeInfo],
    edges: _NodeEdges,
    nodeMap: Dict[str, str],
) -> None:
    """Collapse boring nodes. This will update nodeMap to be a dict from srcId -> dstId; if a node
    is present in this dict, its entry in nodes should henceforth be ignored. If a node is absent in
    this dict, that means the node still exists, and should be treated as real.
    """
    for nodeId, nodeInfo in nodes.items():
        # If the node has a nontrivial local contribution, we shouldn't collapse it.
        maxLocalFrac = max(
            size.localSize / size.cumSize if size.cumSize else 0 for size in nodeInfo.sizes
        )
        if maxLocalFrac >= 0.01:
            continue

        # If the node has outgoing edges to more than one other node, don't collapse it.
        targetNodes = edges.outgoingEdges.get(nodeId, set())  # type: ignore
        if len(targetNodes) != 1:
            continue

        # OK, there's another node with which we might consider collapsing this one!
        dstId = next(iter(targetNodes))
        if dstId == nodeId:
            continue

        # If that node has incoming edges from more than one node, though, we shouldn't do that.
        incomingNodes = edges.incomingEdges.get(dstId, set())  # type: ignore
        if len(incomingNodes) != 1:
            continue

        # If we get here, we indeed want to collapse dstId into nodeId!
        srcId = nodeMap.get(nodeId, nodeId)
        dstId = nodeMap.get(dstId, dstId)
        nodes[srcId].add(nodes[dstId])
        nodeMap[dstId] = srcId

    # Now update the edge size map.
    newSizes: Dict[Tuple[str, str], List[int]] = {}
    for (edgeSrc, edgeDst), sizes in edges.edgeSizes.items():
        mappedKey = (nodeMap.get(edgeSrc, edgeSrc), nodeMap.get(edgeDst, edgeDst))
        if mappedKey not in newSizes:
            newSizes[mappedKey] = sizes
        else:
            newSizes[mappedKey] = [
                max(oldSize, newSize) for oldSize, newSize in zip(newSizes[mappedKey], sizes)
            ]
    edges.edgeSizes.clear()
    edges.edgeSizes.update(newSizes)


###############################################################################################
# Rendering
def _render(
    output: TextIO,
    graphs: List['FlowGraph'],
    nodes: Dict[str, _NodeInfo],
    edges: _NodeEdges,
    nodeMap: Dict[str, str],
    minEdgeFraction: float,
    sizeNodesBasedOnLocalUsage: bool,
) -> None:
    output.write('digraph {\n')
    output.write('  node [shape=none margin=0]\n')

    for nodeId, nodeInfo in nodes.items():
        # If the node is mapped to something else, it's no longer a real node; ignore it.
        if nodeId in nodeMap:
            continue

        output.write(
            f'  {nodeId} [fontsize={nodeInfo.fontSize(graphs, sizeNodesBasedOnLocalUsage)} '
            f'label={nodeInfo.label(graphs)}]\n'
        )

    # Edges are colored by edge fraction; white is assigned to minEdgeFraction, black to
    # max(minEdgeFraction, 0.5), and we do a linear gradient between those two points.
    blackCutoff = max(minEdgeFraction, 0.5)
    scaleDenom = 180 / (blackCutoff - minEdgeFraction) if blackCutoff > minEdgeFraction else 0

    # Now we're going to render the edges. While we have N separate edge bundles for each of the N
    # graph stages, we're going to instead group these into single edges.
    for srcId, dsts in edges.outgoingEdges.items():
        srcId = nodeMap.get(srcId, srcId)
        for dstId in dsts:
            dstId = nodeMap.get(dstId, dstId)

            # Ignore self-edges, which happen a lot due to collapsing and are boring.
            if srcId == dstId:
                continue

            edgeKey = (srcId, dstId)
            assert edgeKey in edges.edgeSizes
            if edgeKey not in edges.edgeSizes:
                continue

            edgeSizes = edges.edgeSizes[edgeKey]
            fracWeights = [
                edgeSize / srcSize.cumSize if srcSize.cumSize else 0
                for edgeSize, srcSize in zip(edgeSizes, nodes[srcId].sizes)
            ]
            fracWeight = max(fracWeights)

            if fracWeight < minEdgeFraction:
                continue
            elif fracWeight >= blackCutoff:
                color = 0
            else:
                color = int((blackCutoff - fracWeight) * scaleDenom)
            colorString = f'#{color:02x}{color:02x}{color:02x}'

            label = f' / '.join(bytesString(edgeSize) for edgeSize in edgeSizes)

            output.write(f'  {srcId} -> {dstId} [color="{colorString}" label="{label}"];\n')

    output.write('}\n')
