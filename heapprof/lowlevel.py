import linecache
from typing import (Any, Dict, Iterator, List, NamedTuple, Optional, Sequence,
                    Tuple)

import _heapprof


"""This file defines the low-level Python interface to reading .hpm, .hpd, and .hpc files. All the
other analysis tools are built on top of these, and these are mostly glue to underlying C++ code.
"""


class HPM(object):
    """HPM is the low-level interface to the .hpm file format."""

    class TraceLine(NamedTuple):
        # The filename
        filename: str
        # The line number
        lineno: int
        # The actual line of code
        fileline: str

    HeapTrace = List[TraceLine]

    def __init__(self, filebase: str) -> None:
        self._mdfile = open(filebase + ".hpm", "rb")

        # The raw stack traces that we've loaded so far. traceindices are 1-based indices into this
        # array.
        self._rawTraces: List[List[Tuple[str, int]]] = []
        # The "clean" stack traces, including contents. We generate these separately because pulling
        # out the lines of code is expensive, so we only do it if someone asks for a given trace.
        self._traces: Dict[int, HPM.HeapTrace] = {}
        # True if we've read to the end of self._mdfile
        self._allTracesRead = False

        # Read the metadata and compute our scale factors.
        self._initialTime, self._samplingRate = _heapprof.readMetadata(self._mdfile.fileno())
        self._scaleFactors = sorted(
            [
                (maxSize, 1 / probability if probability != 0 else 0)
                for maxSize, probability in self._samplingRate.items()
            ]
        )

    @property
    def initialTime(self) -> float:
        """Return the initial time of the profile."""
        return self._initialTime

    @property
    def samplingRate(self) -> Dict[int, float]:
        """Return the sampling rate used when generating this heap profile. This is a dict from
        number of bytes to sampling probability; for an allocation of size X, the sampling
        probability is given by the entry for the smallest number of bytes in this dict > X. (If
        there is no such entry, the sampling probability is always 1)
        """
        return self._samplingRate

    def trace(self, traceindex: int) -> Optional["HPM.HeapTrace"]:
        """Given a traceindex (of the sort found in a HeapEvent), find the corresponding stack
        trace. Returns None if there is no known trace for this traceindex.
        """
        # traceindex 0 is reserved to mean "the bogus index."
        if not traceindex:
            return None
        # If we've already fetched it, return that.
        if traceindex in self._traces:
            return self._traces[traceindex]

        # See if we need to read the raw trace from disk.
        while traceindex > len(self._rawTraces) and not self._allTracesRead:
            try:
                self._rawTraces.append(_heapprof.readRawTrace(self._mdfile.fileno()))
            except EOFError:
                self._allTracesRead = True

        if traceindex > len(self._rawTraces):
            # Huh; we genuinely don't know what this thing is.
            return None

        # Convert the raw trace to a full trace, with code fragments in it.
        self._traces[traceindex] = self._makeHeapTrace(self._rawTraces[traceindex - 1])
        return self._traces[traceindex]

    def scaleFactor(self, eventSize: int) -> float:
        """Given an event size, find the appropriate scale factor for it."""
        absSize = abs(eventSize)
        for maxSize, scaleFactor in self._scaleFactors:
            if absSize < maxSize:
                return scaleFactor
        return 1

    ############################################################################################
    # Implementation details beyond this point.

    def __del__(self) -> None:
        if hasattr(self, "_mdfile"):
            self._mdfile.close()

    def _makeHeapTrace(self, rawTrace: List[Tuple[str, int]]) -> "HPM.HeapTrace":
        return [
            self.TraceLine(
                filename=line[0],
                lineno=line[1],
                fileline=linecache.getline(line[0], line[1]).strip(),
            )
            # NB: Raw traces are in reverse order! That makes them faster to write.
            for line in reversed(rawTrace)
        ]


class HPD(object):
    """HPD is the low-level interface to a .hpd file."""

    class Event(NamedTuple):
        # The time at which this event happened, in seconds since the epoch.
        timestamp: float

        # The stack trace identifier at which this piece of memory was *allocated*. You can fetch
        # the actual stack trace for this identifier from the HPM.
        traceindex: int

        # The number of bytes; this is positive for a memory allocation event, negative for a
        # deallocation.
        size: int

        # This is the amount by which you should multiply size to take sampling into account; for
        # example, if allocations of this size were sampled at a rate of 1e-4, this would be 10^4.
        scaleFactor: float

    def __init__(self, filebase: str, hpm: Optional[HPM] = None) -> None:
        self.hpm = hpm or HPM(filebase)
        self._dataFileName = filebase + ".hpd"

    def __iter__(self) -> Iterator["HPD.Event"]:
        """Yield a sequence of heap events. Each event contains a timestamp, a stack trace index,
        and a number of bytes, which is positive for allocs and negative for frees. Note that these
        events are subject to sampling; that is, if the number of bytes is in a sampling range that
        has probability 0.1, there is a 0.1 probability that it shows up in these events; no attempt
        has been made here at "inverse scaling" that.
        """
        with open(self._dataFileName, "rb") as datafile:
            lastTime = self.hpm.initialTime
            while True:
                try:
                    deltaTime, traceindex, size = _heapprof.readEvent(datafile.fileno())
                except EOFError:
                    break
                else:
                    newTime = lastTime + deltaTime
                    yield self.Event(newTime, traceindex, size, self.hpm.scaleFactor(size))
                    lastTime = newTime


class HPC(Sequence["HPC.Snapshot"]):
    """HPC is the low-level interface to .hpc files."""

    class Snapshot(NamedTuple):
        # The timestamp of this snapshot, relative to program start, in seconds.
        relativeTime: float

        # Memory usage, as a map from the trace index at which memory was allocated (which can be
        # resolved into a proper stack trace using an HPM) to live bytes in memory at this time.
        usage: Dict[int, int]

        def totalUsage(self) -> int:
            return sum(self.usage.values())

    def __init__(self, filebase: str, hpm: Optional[HPM] = None) -> None:
        self.hpm = hpm or HPM(filebase)
        self._file = open(filebase + ".hpc", "rb")
        self.initialTime, self.timeInterval, self.offsets = _heapprof.readDigestMetadata(
            self._file.fileno()
        )

    def __del__(self) -> None:
        if hasattr(self, "_file"):
            self._file.close()

    def __len__(self) -> int:
        return len(self.offsets)

    def __getitem__(self, key: Any) -> Any:
        if not isinstance(key, int):
            raise NotImplementedError("HPC does not support slicing")
        return self.Snapshot(
            relativeTime=key * self.timeInterval,
            usage=_heapprof.readDigestEntry(self._file.fileno(), self.offsets[key]),
        )

    def __iter__(self) -> Iterator["HPC.Snapshot"]:
        for i in range(len(self.offsets)):
            yield self[i]

    def __contains__(self, key: object) -> bool:
        return key in self.offsets

    @classmethod
    def make(cls, filebase: str, timeInterval: float, precision: float, verbose: bool) -> None:
        """Build a .hpc file out of a .hpm and .hpd file.

        Args:
            filebase: The name of the hpx file to process.
            timeInterval: The gap between consecutive snapshots, in seconds.
            precision: The fraction of total bytes at any snapshot which can be stuffed into the
                "other" bin. Must be a number in [0, 1).
            verbose: If set, prints out a lot of state to stderr.
        """
        _heapprof.makeDigestFile(filebase, int(timeInterval * 1000), precision, verbose)
