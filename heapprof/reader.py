import math
from collections import defaultdict
from typing import (Dict, List, NamedTuple, Optional, Sequence, TextIO, Tuple,
                    Union)

from .flow_graph import FlowGraph
from .lowlevel import HPC, HPD, HPM
from .types import HeapTrace, RawTrace, RawTraceLine, Snapshot


class Reader(object):
    """Reader is the basic API for reading a heap profile."""

    def __init__(self, filebase: str) -> None:
        self.filebase = filebase

        # If you want access to the low-level API, you can use the hpm, hpd, and hpc variables. No
        # harm will come to you from doing so; Reader is just a simpler interface on top of them.
        self._hpm = HPM(filebase)
        self._hpd = HPD(filebase, self._hpm)
        self._hpc: Optional[HPC] = None

        self._openHPC()

    def hasDigest(self) -> bool:
        """Test if this Reader already has a digest (i.e. an ._hpc file). If not, you can create one
        using makeDigest; this is a slow operation (O(minutes), usually) so isn't done on its own.
        """
        return self._hpc is not None

    def makeDigest(
        self, timeInterval: float = 60, precision: float = 0.01, verbose: bool = False
    ) -> None:
        """Parse the ._hpm and ._hpd files to form a digest. You need to do this before most of the
        methods will work.

        NB that this method deliberately does *not* check self.hasDigest(); you can use this to
        stomp an existing digest and create a new one.

        NB also that if this function is interrupted (say, with a ctrl-C) it should still yield a
        valid ._hpc file; the file will just stop at whatever time makeDigest() has gotten up to by
        the time it was stopped. This doesn't apply if the function is interrupted in a way that
        kills the interpreter midway through, like kill -9'ing the process, though.

        Args:
            timeInterval: The time interval between successive snapshots to store in the digest,
                in seconds.
            precision: At each snapshot, stack traces totalling up to this fraction of total
                memory used at that frame may be dropped into the "other stack trace" bucket.
                This can greatly shrink the size of the digest at no real cost in usefulness.
                Must be in [0, 1); a value of zero means nothing is dropped.
            verbose: If true, prints status information to stderr as it runs.
        """
        self._hpc = None
        try:
            HPC.make(self.filebase, timeInterval, precision, verbose)
        finally:
            # We do this in a "finally" block because if you control-C out of an HPC.make() call,
            # that stops the build early but we should still load the outcome, especially if we're
            # in some type of command-line interface where this isn't going to exit the entire
            # Python interpreter.
            self._openHPC()

    def close(self) -> None:
        """Close the reader. After doing this, the reader is no longer usable."""
        self._hpm.close()
        if self._hpc:
            self._hpc.close()

    def __enter__(self) -> 'Reader':
        return self

    def __exit__(self, *args) -> bool:
        self.close()
        return False

    ###########################################################################################
    # High-level API access to the profile
    #
    # These functions are the "high-level API" to the profile, which speaks in terms of Snapshots --
    # the state of the heap as a function of time. If you want to do your own analysis, this is a
    # great place to start. If you want to drill down to the level of individual alloc and free
    # events, use the low-level API exposed by self._hpm and self._hpd.
    #
    # The analytics functions (after this section) provide even more high-level API, letting you
    # look at things like graphs of program nodes programmatically. Anything the visualization tools
    # let you display, they also let you analyze with code.

    def initialTime(self) -> float:
        """Return the time, in seconds since the epoch, when the program run started. This is useful
        if you want to compare this to logs data.
        """
        return self._hpm.initialTime

    def finalTime(self) -> float:
        """Return the time, in seconds since the epoch, of the last snapshot stored."""
        return self.initialTime() + self.elapsedTime()

    def elapsedTime(self) -> float:
        """Return the relative time between program start and the last snapshot."""
        assert self._hpc is not None
        return len(self._hpc) * self._hpc.timeInterval

    def samplingRate(self) -> Dict[int, float]:
        """Return the sampling rate parameters passed to the profiler."""
        return self._hpm.samplingRate

    def snapshotInterval(self) -> float:
        """Return the time interval, in seconds, between successive time snapshots in the digest.
        """
        assert self._hpc is not None
        return self._hpc.timeInterval

    def trace(self, traceindex: int) -> Optional[HeapTrace]:
        """Given a trace index (of a sort which you can get from various other functions), return a
        proper stack trace. A value of None means that we have no trace stored for this index.
        """
        return self._hpm.trace(traceindex)

    def rawTrace(self, traceindex: int) -> Optional[RawTrace]:
        """Like trace(), but the raw trace doesn't include the actual lines of code, so is cheaper
        to fetch.
        """
        return self._hpm.rawTrace(traceindex)

    def snapshots(self) -> Sequence[Snapshot]:
        """Return a sequence of all the time snapshots in the digest."""
        assert self._hpc is not None
        return self._hpc

    def snapshotAt(self, relativeTime: float) -> Snapshot:
        """Return the snapshot closest in time (rounding down) to the indicated relative time.
        """
        assert self._hpc is not None
        index = max(0, min(math.floor(relativeTime / self._hpc.timeInterval), len(self._hpc) - 1))
        return self._hpc[index]

    @property
    def hpm(self) -> HPM:
        """Access to the low-level HPM interface."""
        return self._hpm

    @property
    def hpd(self) -> HPD:
        """Access to the low-level HPD interface."""
        return self._hpd

    @property
    def hpc(self) -> HPC:
        """Access to the low-level HPC interface."""
        return self._hpc

    def fastGetUsage(
        self, snapshot: Snapshot, lines: Tuple[RawTraceLine, ...], cumulative: bool = True
    ) -> Tuple[Tuple[int, ...], int]:
        """This is a function to quickly fetch usage numbers without computing full usage graphs.
        Given a snapshot and a list of N raw trace lines, this will return an array with N+1
        elements. The first N elements are the cumulative (or local) usage at the indicated trace
        lines; the last element is the total usage for all trace lines.
        """
        data: Dict[RawTraceLine, int] = defaultdict(int)
        total = 0
        for traceindex, size in snapshot.usage.items():
            total += size
            rawTrace = self.rawTrace(traceindex)
            if rawTrace is None:
                continue
            if not cumulative:
                if rawTrace[-1] in lines:
                    data[rawTrace[-1]] += size
            else:
                for line in lines:
                    if line in rawTrace:
                        data[line] += size
        return (tuple(data[line] for line in lines), total)

    ###########################################################################################
    # Analytics Functions
    #
    # These functions expose three different views of the data. If you don't want to write code to
    # analyze your heap, and just want to pull out graphs, these are the way to go.
    #
    # If you don't know where to start, a good roadmap to analyzing your heap is:
    #  - Call self.timePlot().pyplot() to see overall memory usage as a function of time.
    #    You'll need to `pip install matplotlib` to view this.
    #  - If there are any individual points in time you want to examine in detail, call
    #    self.writeFlowGraph(time) or self.writeFlameGraph(time) to generate flow or flame
    #    visualizations. (Different people prefer different ones) You'll need to install
    #    graphviz (see graphviz.org) to view flow graphs, or use speedscope.app to view flame
    #    graphs.
    #  - If there are two or more points in time you'd like to compare, call
    #    self.compareFlowGraphs() to generate a flow graph that shows you how memory usage has
    #    shifted across the stack between times.
    #  - If any of the above tools showed you particular lines of code whose usage you'd like
    #    to see shift over time, call self.timePlot({...}).pyplot() to view that.
    #
    # All of these functions also let you access the data they display programmatically, which
    # is part of the high-level API.

    ###########################################################################################
    # Time plots: These allow you to view the time dependence of memory usage, both overall and for
    # individual lines of code.
    class TimePlot(NamedTuple):
        # The output of timePlot. All of the arrays below are parallel -- they have the same
        # number of entries.

        # A list of relative times, in seconds.
        times: List[float]

        # Total heap size at each time, in bytes.
        totalUsage: List[int]

        # For each line you requested, we return a list of values; the exact value returned depends
        # on the parameters selected.
        lines: List[List[int]]

        # A list parallel not to times, but to lines, of names for each line.
        labels: List[str]

        def pyplot(self, scale: int = 1 << 20) -> None:
            """Show this plot using pyplot. Note that this method will only work if you have
            separately pip installed matplotlib; we deliberately don't add this, as it would create
            a lot of dependency bloat!

            The scale is a scaling applied to byte quantities.
            """
            try:
                import matplotlib.pyplot as plt
            except ImportError:
                raise ImportError(
                    'This functionality requires matplotlib. You can install it '
                    'with `pip install matplotlib`.'
                )

            if self.lines:
                # With lines requested -- show three plots, one of total usage, one of raw usage per
                # line, one of the ratios.
                _, (total, raw, frac) = plt.subplots(3, 1, sharex=True)
                total.plot(self.times, [t / scale for t in self.totalUsage])

                rawLines: List[List[int]] = []
                for line in self.lines:
                    rawLines.append(self.times)
                    rawLines.append([v / scale for v in line])
                raw.plot(*rawLines)

                fracLines = []
                for line in self.lines:
                    fracLines.append(self.times)
                    fracLines.append([d / t for d, t in zip(line, self.totalUsage)])
                frac.plot(*fracLines)

                plt.legend(self.labels)

            else:
                # No lines -- just show the total usage.
                _, ax = plt.subplots()
                ax.plot(self.times, self.totalUsage)

            plt.show()

    def timePlot(
        self, lines: Optional[Dict[str, Union[str, RawTraceLine]]] = None
    ) -> 'Reader.TimePlot':
        """Sometimes, after you've looked at usage graphs and so on, you want to see how memory
        usage in certain parts of the program is varying over time. This function helps you with
        that.

        Args:
            lines: If given, this is a map from display label to lines of code whose usage you
                want to monitor. In this case, the output data will show memory usage at those
                lines, in addition to overall usage by the program.

                The lines may be specified either as RawTraceLine, or as "filename:lineno". This
                latter form is provided for convenience while debugging.
        """
        lines = lines or {}
        times: List[float] = []
        totalUsage: List[int] = []
        lineValues: List[List[int]] = [[] for i in range(len(lines))]

        labels = sorted(list(lines.keys()))
        traceLines = tuple(RawTraceLine.parse(lines[label]) for label in labels)
        for snapshot in self.snapshots():
            times.append(snapshot.relativeTime)
            data, total = self.fastGetUsage(snapshot, traceLines, cumulative=True)
            totalUsage.append(total)
            for lineValue, datum in zip(lineValues, data):
                lineValue.append(datum)

        return self.TimePlot(times, totalUsage, lineValues, labels)

    ###########################################################################################
    # Flow graphs
    #
    # A flow graph is a directed graph. Each node represents a line of code that shows up in a
    # stack trace. (Or sometimes, multiple lines of code that are grouped together because they
    # always show up in a single sequence in the stack trace; no reason to make graphs big)
    #
    # Each node has a local usage (how much memory was allocated by that line of code itself) and
    # a cumulative usage (how much memory was allocated by that line of code or by any functions it
    # called). Nodes are connected by edges that represent function calls; the weight of an edge is
    # the amount of memory used by calls that followed that edge.
    #
    # Each FlowGraph object represents the graph at a single snapshot. You can make a dot file
    # (which can be viewed with graphviz) out of a single flow graph, or you can compare multiple
    # flow graphs in a single visualization using compareFlowGraphs().
    #
    # flow_graph.py has very detailed comments if you'd like to learn more.
    def flowGraph(self, snapshot: Snapshot) -> FlowGraph:
        """Compute a FlowGraph given a snapshot. See flow_graph.py for the details of what these
        are and how they can be used for analysis; these are one of your best ways to both
        visualize a snapshot or analyze time-dependence.

        Use this method if you want a graph visualization of your data.

        NB: The first call to flowGraph on a Reader may be a bit slow, because it has to load up
        all the stack traces from the ._hpm file; once that cache is warm, future reads will be much
        faster.
        """
        nodeLocalUsage: Dict[RawTraceLine, int] = defaultdict(int)
        nodeCumulativeUsage: Dict[RawTraceLine, int] = defaultdict(int)
        edgeUsage: Dict[Tuple[RawTraceLine, RawTraceLine], int] = defaultdict(int)
        totalUsage = 0

        for traceindex, size in snapshot.usage.items():
            totalUsage += size

            # Grab the stack trace. If there is none, we only account for it in the total.
            rawTrace = self._hpm.rawTrace(traceindex)
            if rawTrace is None:
                continue

            traceLength = len(rawTrace)
            for i in range(traceLength):
                # nodeCumulativeUsage == total size of all stacks including this line.
                nodeCumulativeUsage[rawTrace[i]] += size
                # edgeUsage == total size of all edges containing (AB)
                if i < traceLength - 1:
                    edgeUsage[(rawTrace[i], rawTrace[i + 1])] += size
                else:
                    # nodeLocalUsage == total size of all stacks ending with this line.
                    nodeLocalUsage[rawTrace[i]] += size

        return FlowGraph(
            dict(nodeLocalUsage), dict(nodeCumulativeUsage), dict(edgeUsage), totalUsage
        )

    def flowGraphAt(self, relativeTime: float) -> FlowGraph:
        return self.flowGraph(self.snapshotAt(relativeTime))

    def compareFlowGraphs(self, dotFile: str, *relativeTimes: float, **kwargs) -> None:
        """Generate a graph view of the comparison of a bunch of different time slices, and save the
        result as a .dot file to the given name. See FlowGraph.compare() for the kwargs available.
        """
        graphs = tuple(self.flowGraphAt(t) for t in relativeTimes)
        FlowGraph.compare(dotFile, *graphs, **kwargs)

    ###########################################################################################
    # Flame graphs
    #
    # A flame graph visualizes memory usage as a sort of mountain range. Each vertical slice through
    # the mountain range represents a single stack trace; the width of the slice indicates the
    # amount of memory allocated by it. There are good interactive viewers for flame graphs, which
    # let you click around and explore where the memory goes. A major difference between flow and
    # flame graphs is that if a single line of code is called multiple times by different other
    # sources, it will be unified in the flow graph, while the flame graph will show each call site
    # as unrelated. This can be a pro or con, depending on the situation, so use both!

    def flameGraph(self, snapshot: Snapshot, output: TextIO) -> None:
        """Write a snapshot in Brendan Gregg's "collapsed stack" format. This format can be
        visualized as a Flame graph with tools like speedscope.app. (NB that if you're using
        speedscope, only the "left heavy" and "sandwich" views will make any sense; the "time
        order" view is intended to show CPU profiles over time, which would be nonsensical
        for this type of data)

        For speedscope, see https://github.com/jlfwong/speedscope, or use the hosted version at
        https://www.speedscope.app.
        """
        otherSize = 0
        for traceindex, size in snapshot.usage.items():
            trace = self.trace(traceindex)
            if trace is None:
                otherSize += size
            else:
                traceArray = [f"{line.filename}:{line.lineno}" for line in trace]
                output.write(";".join(traceArray))
                output.write(f" {size}\n")

        if otherSize > 0:
            output.write(f"OTHER {otherSize}\n")

    def flameGraphAt(self, relativeTime: float, output: TextIO) -> None:
        self.flameGraph(self.snapshotAt(relativeTime), output)

    def writeFlameGraph(self, filename: str, when: Union[float, Snapshot]) -> None:
        """Convenience helper: Grab a snapshot at a particular relative time, and write it in
        collapsed stack format to filename.
        """
        if not isinstance(when, Snapshot):
            when = self.snapshotAt(when)
        with open(filename, "w") as output:
            self.flameGraphAt(when, output)

    ###########################################################################################
    # Implementation details
    def _openHPC(self) -> None:
        """Try to open the .hpc file."""
        try:
            self._hpc = self._hpc or HPC(self.filebase, self._hpm)
        except (FileNotFoundError, ValueError):
            # These mean that either the file is absent or corrupt.
            pass
