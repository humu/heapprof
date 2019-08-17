import linecache
from typing import (Any, Dict, Iterable, Iterator, List, NamedTuple, Optional,
                    Sequence)

import _heapprof

from .types import HeapTrace, RawTrace, RawTraceLine, Snapshot, TraceLine


"""This file defines the low-level Python interface to reading .hpm, .hpd, and .hpc files. All the
other analysis tools are built on top of these, and these are mostly glue to underlying C++ code.
"""


class HPM(object):
    """HPM is the low-level interface to the .hpm file format."""

    def __init__(self, filebase: str) -> None:
        self._mdfile = open(filebase + ".hpm", "rb")

        # The raw stack traces that we've loaded so far. traceindices are 1-based indices into this
        # array.
        self._rawTraces: List[RawTrace] = []
        # The "clean" stack traces, including contents. We generate these separately because pulling
        # out the lines of code is expensive, so we only do it if someone asks for a given trace.
        self._traces: Dict[int, HeapTrace] = {}
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

    def rawTrace(self, traceindex: int) -> Optional[RawTrace]:
        """Given a traceindex (of the sort found in an HPDEvent), find the corresponding raw stack
        trace. Returns None if there is no known trace for this traceindex.
        """
        # traceindex 0 is reserved to mean "the bogus index."
        if not traceindex:
            return None

        # See if we need to read the raw trace from disk.
        while traceindex > len(self._rawTraces) and not self._allTracesRead:
            try:
                # Raw traces are stored on disk in reverse order, which makes them faster to write;
                # undo that here!
                self._rawTraces.append(
                    list(
                        RawTraceLine(*line)
                        for line in reversed(_heapprof.readRawTrace(self._mdfile.fileno()))
                    )
                )
            except EOFError:
                self._allTracesRead = True

        return self._rawTraces[traceindex - 1] if traceindex <= len(self._rawTraces) else None

    def trace(self, traceindex: int) -> Optional[HeapTrace]:
        """Given a traceindex (of the sort found in an HPDEvent), find the corresponding stack
        trace. Returns None if there is no known trace for this traceindex.
        """
        # traceindex 0 is reserved to mean "the bogus index."
        if not traceindex:
            return None
        # If we've already fetched it, return that.
        if traceindex in self._traces:
            return self._traces[traceindex]

        # Convert the raw trace to a full trace, with code fragments in it.
        self._traces[traceindex] = self._makeHeapTrace(self.rawTrace(traceindex))
        return self._traces[traceindex]

    def scaleFactor(self, eventSize: int) -> float:
        """Given an event size, find the appropriate scale factor for it."""
        absSize = abs(eventSize)
        for maxSize, scaleFactor in self._scaleFactors:
            if absSize < maxSize:
                return scaleFactor
        return 1

    def warmRawTraceCache(self) -> None:
        """rawTrace() can be slow, because it may need to fetch traces out of the HPM file. Calling
        this function forces that entire load to happen at once.
        """
        # This number is bigger than the biggest valid trace index.
        self.rawTrace(1 << 31)

    def close(self) -> None:
        if hasattr(self, "_mdfile"):
            self._mdfile.close()
            delattr(self, "_mdfile")

    ############################################################################################
    # Implementation details beyond this point.

    def __del__(self) -> None:
        self.close()

    def _makeHeapTrace(self, rawTrace: Optional[RawTrace]) -> Optional[HeapTrace]:
        if not rawTrace:
            return None
        return [
            TraceLine(
                filename=rawTraceLine.filename,
                lineno=rawTraceLine.lineno,
                fileline=linecache.getline(rawTraceLine.filename, rawTraceLine.lineno).strip(),
            )
            for rawTraceLine in rawTrace
        ]


class HPDEvent(NamedTuple):
    """A single event stored in a .hpd file."""

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


class HPD(Iterable[HPDEvent]):
    """HPD is the low-level interface to a .hpd file."""

    def __init__(self, filebase: str, hpm: Optional[HPM] = None) -> None:
        self.hpm = hpm or HPM(filebase)
        self._dataFileName = filebase + ".hpd"

    def __iter__(self) -> Iterator[HPDEvent]:
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
                    yield HPDEvent(newTime, traceindex, size, self.hpm.scaleFactor(size))
                    lastTime = newTime


class HPC(Sequence[Snapshot]):
    """HPC is the low-level interface to .hpc files."""

    def __init__(self, filebase: str, hpm: Optional[HPM] = None) -> None:
        self.hpm = hpm or HPM(filebase)
        self._file = open(filebase + ".hpc", "rb")
        self.initialTime, self.timeInterval, self.offsets = _heapprof.readDigestMetadata(
            self._file.fileno()
        )

    def __del__(self) -> None:
        self.close()

    def __len__(self) -> int:
        return len(self.offsets)

    def __getitem__(self, key: Any) -> Any:
        if not isinstance(key, int):
            raise NotImplementedError("HPC does not support slicing")
        return Snapshot(
            relativeTime=key * self.timeInterval,
            usage=_heapprof.readDigestEntry(self._file.fileno(), self.offsets[key]),
        )

    def __iter__(self) -> Iterator[Snapshot]:
        for i in range(len(self.offsets)):
            yield self[i]

    def __contains__(self, key: object) -> bool:
        return key in self.offsets

    def close(self) -> None:
        if hasattr(self, "_file"):
            self._file.close()
            delattr(self, "_file")

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
