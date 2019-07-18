import math
from typing import Dict, List, Optional, Sequence, TextIO, Tuple

from .lowlevel import HPC, HPD, HPM


class Reader(object):
    """Reader is the basic API for reading a heap profile."""

    def __init__(self, filebase: str) -> None:
        self.filebase = filebase
        self.hpm = HPM(filebase)
        self.hpd = HPD(filebase, self.hpm)
        # This may be None if you haven't made a digest yet.
        self.hpc: Optional[HPC] = None
        self._openHPC()

    def makeDigest(
        self, timeInterval: float = 60, precision: float = 0.01, verbose: bool = False
    ) -> None:
        """Parse the .hpm and .hpd files to form a digest. You need to do this before most of the
        methods will work.

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

    def trace(self, traceindex: int) -> Optional[HPM.HeapTrace]:
        """Given a trace index (of a sort which you can get from various other functions), return a
        proper stack trace. A value of None means that we have no trace stored for this index.
        """
        return self.hpm.trace(traceindex)

    def snapshots(self) -> Sequence[HPC.Snapshot]:
        """Return a sequence of all the time snapshots in the digest."""
        assert self.hpc is not None
        return self.hpc

    def snapshotAt(self, relativeTime: float) -> HPC.Snapshot:
        """Return the snapshot closest in time (rounding down) to the indicated relative time.
        """
        assert self.hpc is not None
        index = max(
            0, min(math.floor(relativeTime / self.hpc.timeInterval), len(self.hpc) - 1)
        )
        return self.hpc[index]

    ###########################################################################################
    # I/O helpers to interface with other analysis tools

    def plotTotalUsage(self, scale: int = 1 << 20) -> Tuple[List[float], List[float]]:
        """Generate a curve of total usage over time. The result is a pair of parallel arrays (for
        ease of handing to matplotlib); the first lists seconds since program start, the second
        estimated total bytes used.

        Args:
            scale: A scaling factor to apply to the Y-axis. 1 << 20 would plot in MB, 1 << 30 in GB,
                etc.

        You can plot this with

            import matplotlib.pyplot as plt
            _, ax = plt.subplots()
            ax.plot(*reader.plotTotalUsage(1 << 30))
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

    def asCollapsedStack(self, snapshot: HPC.Snapshot, output: TextIO) -> None:
        """Write a snapshot in Brendan Gregg's "collapsed stack" format. This format can be
        visualized as a Flame graph with tools like speedscope.app. (NB that if you're using
        speedscope, only the "left heavy" and "sandwich" views will make any sense; the "time
        order" view is intended to show CPU profiles over time, which would be nonsensical
        for this type of data)
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

    def writeCollapsedStack(self, relativeTime: float, filename: str) -> None:
        """Convenience helper: Grab a snapshot at a particular relative time, and write it in
        collapsed stack format to filename.
        """
        snapshot = self.snapshotAt(relativeTime)
        with open(filename, "w") as output:
            self.asCollapsedStack(snapshot, output)

    ###########################################################################################
    # Implementation details
    def _openHPC(self) -> None:
        """Try to open the .hpc file."""
        if self.hpc:
            return
        try:
            self.hpc = HPC(self.filebase, self.hpm)
        except (FileNotFoundError, ValueError):
            # These mean that either the file is absent or corrupt.
            pass
