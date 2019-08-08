from typing import Dict, NamedTuple, TextIO, Tuple

from ._flow_graph import makeDotFile
from .types import RawTraceLine


class FlowGraph(NamedTuple):
    """A FlowGraph is one of the basic ways to analyze how memory was being used by a process at a
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
    allocated at the following stack traces, where letters denote lines of code::

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
    paths to a node; for example, in the diagram above, the A→C call path is much more significant
    than the B→C one!

    You can also compare FlowGraphs computed at two different times, and this can give critical
    insight into time dependencies. For example, say that your program has a natural flow of data
    where data is allocated (say, read in from disk) at point A, processed through stages B, C, and
    D, then written to a buffer at line E, and the output finally committed to disk and deallocated
    at line F. Say also that at some moment in time, overall memory usage for your program spikes.
    If the before and after of the spike were both during this processing flow (as opposed to, say,
    "before the flow vs during the flow," in which case the problem would be obvious), it can be
    very useful to compare the *fraction* of total memory allocated at A, B, C, D, E, and F, as well
    as total memory usage T, during the before and during snapshots.

    For example, if the fractions for A-F were all roughly the same both before and during the
    memory spike, this would tell you that during the spike, a lot more data is being read in, but
    the rest of the flow is proceeding as usual. If, on the other hand, the fractions for D, E, and
    F dropped during the spike, that would mean that less data (proportionally) was reaching them,
    which would imply that data was being held up at point C during the spike more than it was
    before -- a good hint as to where the problem might lie. Conversely, if fractional memory
    usage at D, E, and F was *higher* during the spike than before it, that might imply that D was
    generating more data than it was before, creating additional load on E and F. This
    interpretation would have to do with D being a processing stage; if memory usage at E alone were
    higher, that would imply that more memory was building up in the buffer during the spike, which
    might imply that the buffer's draining at F was not functioning -- perhaps the spike was caused
    by a problem in writing the data back out to disk?

    While there isn't a completely generic tool for doing this analysis, this kind of information
    can be invaluable in tracing down odd phenomena.
    """

    # The best way to create a FlowGraph is with Reader.usageGraph().
    nodeLocalUsage: Dict[RawTraceLine, int]
    nodeCumulativeUsage: Dict[RawTraceLine, int]
    edgeUsage: Dict[Tuple[RawTraceLine, RawTraceLine], int]
    totalUsage: int

    def asDotFile(
        self,
        dotFile: TextIO,
        minNodeFraction: float = 0.01,
        minEdgeFraction: float = 0.05,
        collapseNodes: bool = True,
        sizeNodesBasedOnLocalUsage: bool = True,
    ) -> None:
        """Write out a FlowGraph as a dot graph. The result can be visualized using graphviz, with
        a command like

        ::

            dot -T pdf -o foo.pdf foo.dot

        See www.graphviz.org for where you can get graphviz for your system.

        Args:
            dotFile: Where the data should be written.
            minNodeFraction: Nodes whose local size is less than this fraction of total usage
                are dropped for visual clarity.
            minEdgeFraction: Edges whose size is less than this fraction of their source node's
                cumulative usage are dropped for visual clarity.
            collapseNodes: If True, groups of trace lines that have no branching can get merged
                into each other.
            sizeNodesBasedOnLocalUsage: If True, the visual size of nodes in the graph will be
                increased for nodes that allocate memory themselves. This can draw the eye to
                useful information in some circumstances, and distract it in others, so YMMV.
        """
        return makeDotFile(
            dotFile,
            [self],
            minNodeFraction=minNodeFraction,
            minEdgeFraction=minEdgeFraction,
            collapseNodes=collapseNodes,
            sizeNodesBasedOnLocalUsage=sizeNodesBasedOnLocalUsage,
        )

    def writeDotFile(self, filename: str, **kwargs) -> None:
        """Convenience helper for interactive analysis."""
        with open(filename, 'w') as output:
            self.asDotFile(output, **kwargs)

    @classmethod
    def compare(
        cls,
        dotFileName: str,
        *usageGraphs: 'FlowGraph',
        minNodeFraction: float = 0.01,
        minEdgeFraction: float = 0.05,
        collapseNodes: bool = True,
        sizeNodesBasedOnLocalUsage: bool = True,
    ) -> None:
        """Create a dot graph comparing multiple FlowGraphs, which usually correspond to multiple
        time snapshots. In the resulting graph, boxes will look like this::

            |-------------------------------|
            |  filename:line number         |
            |  filename:line number         |
            |-------------------------------|
            | Loc/Cum  | Loc/Cum  | Loc/Cum |
            |-------------------------------|

        Here the sequence of filename:line numbers represents the segment of the stack trace
        represented by this node (multiple lines are fused together if basically nothing interesting
        happens between them), and for each "time stage" (parallel to the graphs we were passed) it
        shows the local and cumulative usage at that node. (Local usage == memory allocated at the
        final line of code in this stack trace; cumulative usage == memory allocated at or below the
        final line of code in this stack trace)

        This function is particularly useful for finding the causes of anomalous memory events. For
        example, imagine that your program is having an overall memory usage spike; you can see this
        on the time plot (which you made using Reader.asTotalUsagePlot), then pick three times --
        before, during, and after the spike -- make usage graphs for all three, and plot them::

            import heapprof
            r = heapprof.Reader('myfile')
            heapprof.FlowGraph.compare(
                'compare.dot',
                r.usageGraphAt(1000),  # A time before the spike
                r.usageGraphAt(2000),  # A time in the middle of the spike
                r.usageGraphAt(3000),  # A time after the spike
            )

        Then you view this with dot::

            dot -Tpdf -o compare.pdf compare.dot

        Each box on the graph will have three sizes in it, corresponding to the three timestamps;
        those boxes are color-coded from red to blue (corresponding to what fraction of total memory
        they take up at their respective timeslice), and the overall box is sized based on how much
        memory is being allocated directly by that box (as opposed to things that box calls).

        Starting from the top of the graph, there is a box marked "Program Root," whose cumulative
        usage numbers are total memory usage at those times; perhaps they're 800MB, 2GB, 800MB.
        Following the lines down, we see that in all cases, the majority of memory usage is along a
        particular route, but the *fraction* of cumulative memory usage used by various nodes during
        the spike is different from the fraction in the before or after, while the before and after
        tend to be pretty similar to each other.

        In the nodes where the "during" ≫ the "before" or "after," this is a sign that this is where
        additional memory is being used. In the nodes where the "during" fraction ≪ the "before" or
        "after," check the raw amounts rather than the ratios -- if the number hasn't changed, the
        fraction will go down, and that's a sign that this node hasn't moved.

        You now have an idea of where additional memory is being used during the spike.

        Args:
            dotFileName: The name of the file to which the output should be written.
            *usageGraphs: The sequence of graphs to compare.
            Other arguments: As for asDotGraph(), above.
        """
        with open(dotFileName, 'w') as output:
            makeDotFile(
                output,
                list(usageGraphs),
                minNodeFraction=minNodeFraction,
                minEdgeFraction=minEdgeFraction,
                collapseNodes=collapseNodes,
                sizeNodesBasedOnLocalUsage=sizeNodesBasedOnLocalUsage,
            )
