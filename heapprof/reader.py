import math
from collections import defaultdict
from typing import Dict, List, Optional, Sequence, TextIO, Tuple, Union

from .lowlevel import HPC, HPD, HPM
from .types import HeapTrace, RawTrace, RawTraceLine, Snapshot
from .usage_graph import UsageGraph


class Reader(object):
    """Reader is the basic API for reading a heap profile."""

    def __init__(self, filebase: str) -> None:
        self.filebase = filebase

        # If you want access to the low-level API, you can use the hpm, hpd, and hpc variables. No
        # harm will come to you from doing so; Reader is just a simpler interface on top of them.
        self.hpm = HPM(filebase)
        self.hpd = HPD(filebase, self.hpm)
        self.hpc: Optional[HPC] = None

        self._openHPC()

    def hasDigest(self) -> bool:
        """Test if this Reader already has a digest (i.e. an .hpc file). If not, you can create one
        using makeDigest; this is a slow operation (O(minutes), usually) so isn't done on its own.
        """
        return self.hpc is not None

    def makeDigest(
        self, timeInterval: float = 60, precision: float = 0.01, verbose: bool = False
    ) -> None:
        """Parse the .hpm and .hpd files to form a digest. You need to do this before most of the
        methods will work.

        NB that this method deliberately does *not* check self.hasDigest(); you can use this to
        stomp an existing digest and create a new one.

        NB also that if this function is interrupted (say, with a ctrl-C) it should still yield a
        valid .hpc file; the file will just stop at whatever time makeDigest() has gotten up to by
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
        self.hpc = None
        try:
            HPC.make(self.filebase, timeInterval, precision, verbose)
        finally:
            # We do this in a "finally" block because if you control-C out of an HPC.make() call,
            # that stops the build early but we should still load the outcome, especially if we're
            # in some type of command-line interface where this isn't going to exit the entire
            # Python interpreter.
            self._openHPC()

    ###########################################################################################
    # Some core access functions
    def initialTime(self) -> float:
        """Return the time, in seconds since the epoch, when the program run started. This is useful
        if you want to compare this to logs data.
        """
        return self.hpm.initialTime

    def finalTime(self) -> float:
        """Return the time, in seconds since the epoch, of the last snapshot stored."""
        return self.initialTime() + self.elapsedTime()

    def elapsedTime(self) -> float:
        """Return the relative time between program start and the last snapshot."""
        assert self.hpc is not None
        return len(self.hpc) * self.hpc.timeInterval

    def samplingRate(self) -> Dict[int, float]:
        """Return the sampling rate parameters passed to the profiler."""
        return self.hpm.samplingRate

    def snapshotInterval(self) -> float:
        """Return the time interval, in seconds, between successive time snapshots in the digest.
        """
        assert self.hpc is not None
        return self.hpc.timeInterval

    def trace(self, traceindex: int) -> Optional[HeapTrace]:
        """Given a trace index (of a sort which you can get from various other functions), return a
        proper stack trace. A value of None means that we have no trace stored for this index.
        """
        return self.hpm.trace(traceindex)

    def rawTrace(self, traceindex: int) -> Optional[RawTrace]:
        """Like trace(), but the raw trace doesn't include the actual lines of code, so is cheaper
        to fetch.
        """
        return self.hpm.rawTrace(traceindex)

    def snapshots(self) -> Sequence[Snapshot]:
        """Return a sequence of all the time snapshots in the digest."""
        assert self.hpc is not None
        return self.hpc

    def snapshotAt(self, relativeTime: float) -> Snapshot:
        """Return the snapshot closest in time (rounding down) to the indicated relative time.
        """
        assert self.hpc is not None
        index = max(0, min(math.floor(relativeTime / self.hpc.timeInterval), len(self.hpc) - 1))
        return self.hpc[index]

    ###########################################################################################
    # Analysis tools
    # Note that while the below methods can produce the outputs needed to visualize the data in
    # various ways (memory flow graphs, flame graphs, time plots, etc), none of them do the
    # visualization themselves: those all require using separate tools (graphviz, matplotlib,
    # speedscope, etc) which are deliberately not included in this package, to minimize dependency
    # bloat. See the comments on each method for how to connect them to visualization tools, or use
    # the underlying data methods to roll your own or do your own data hunting!

    def usageGraph(self, snapshot: Snapshot) -> UsageGraph:
        """Compute a UsageGraph given a snapshot. See usage_graph.py for the details of what these
        are and how they can be used for analysis; these are one of your best ways to both
        visualize a snapshot or analyze time-dependence.

        Use this method if you want a graph visualization of your data.

        NB: The first call to usageGraph on a Reader may be a bit slow, because it has to load up
        all the stack traces from the .hpm file; once that cache is warm, future reads will be much
        faster.
        """
        nodeLocalUsage: Dict[RawTraceLine, int] = defaultdict(int)
        nodeCumulativeUsage: Dict[RawTraceLine, int] = defaultdict(int)
        edgeUsage: Dict[Tuple[RawTraceLine, RawTraceLine], int] = defaultdict(int)
        totalUsage = 0

        for traceindex, size in snapshot.usage.items():
            totalUsage += size

            # Grab the stack trace. If there is none, we only account for it in the total.
            rawTrace = self.hpm.rawTrace(traceindex)
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

        return UsageGraph(
            dict(nodeLocalUsage), dict(nodeCumulativeUsage), dict(edgeUsage), totalUsage
        )

    def usageGraphAt(self, relativeTime: float) -> UsageGraph:
        return self.usageGraph(self.snapshotAt(relativeTime))

    def asFlameGraph(self, snapshot: Snapshot, output: TextIO) -> None:
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

    def writeFlameGraph(self, when: Union[float, Snapshot], filename: str) -> None:
        """Convenience helper: Grab a snapshot at a particular relative time, and write it in
        collapsed stack format to filename.
        """
        if isinstance(when, float):
            when = self.snapshotAt(when)
        with open(filename, "w") as output:
            self.asCollapsedStack(when, output)

    def asTotalUsagePlot(self, scale: int = 1 << 20) -> Tuple[List[float], List[float]]:
        """Generate a curve of total usage over time. The result is a pair of parallel arrays (for
        ease of handing to matplotlib); the first lists seconds since program start, the second
        estimated total bytes used.

        Args:
            scale: A scaling factor to apply to the Y-axis. 1 << 20 would plot in MB, 1 << 30 in GB,
                etc.

        You can plot this (after pip install matplotlib) with

            import matplotlib.pyplot as plt
            _, ax = plt.subplots()
            ax.plot(*reader.asTotalUsagePlot(1 << 30))
            plt.show()
        """
        if not self.hpc:
            raise RuntimeError("You must make a digest before you can plot usage.")
        times: List[float] = []
        values: List[float] = []
        for snapshot in self.hpc:
            times.append(snapshot.relativeTime)
            values.append(snapshot.totalUsage())
        return (times, values)

    ###########################################################################################
    # Implementation details
    def _openHPC(self) -> None:
        """Try to open the .hpc file."""
        try:
            self.hpc = self.hpc or HPC(self.filebase, self.hpm)
        except (FileNotFoundError, ValueError):
            # These mean that either the file is absent or corrupt.
            pass
