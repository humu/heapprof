import linecache
from typing import Dict, Iterator, List, NamedTuple, Optional, Tuple

import _heapprof


class HeapEvent(NamedTuple):
    # The time at which this event happened, in seconds since the epoch.
    timestamp: float

    # The stack trace identifier at which this piece of memory was *allocated*. You can fetch the
    # actual stack trace for this identifier with HeapProfile.trace(index).
    traceindex: int

    # The number of bytes; this is positive for a memory allocation event, negative for a
    # deallocation.
    size: int

    # This is the amount by which you should multiply size to take sampling into account; for
    # example, if allocations of this size were sampled at a rate of 1e-4, this would be 10^4.
    scaleFactor: float


class TraceLine(NamedTuple):
    # The filename
    filename: str
    # The line number
    lineno: int
    # The actual line of code
    fileline: str


HeapTrace = List[TraceLine]


class HeapProfile(object):
    """HeapProfileis the API for reading .hpx files written by the heap profiler."""

    def __init__(self, filebase: str) -> None:
        self._mdfile = open(filebase + '.hpm', 'rb')
        self._dataFileName = filebase + '.hpd'

        # The raw stack traces that we've loaded so far. traceindices are 1-based indices into this
        # array.
        self._rawTraces: List[List[Tuple[str, int]]] = []
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

    def __iter__(self) -> Iterator[HeapEvent]:
        """Yield a sequence of heap events. Each event contains a timestamp, a stack trace index,
        and a number of bytes, which is positive for allocs and negative for frees. Note that these
        events are subject to sampling; that is, if the number of bytes is in a sampling range that
        has probability 0.1, there is a 0.1 probability that it shows up in these events; no attempt
        has been made here at "inverse scaling" that.
        """
        with open(self._dataFileName, 'rb') as datafile:
            lastTime = self._initialTime
            while True:
                try:
                    deltaTime, traceindex, size = _heapprof.readEvent(datafile.fileno())
                except EOFError:
                    break
                else:
                    newTime = lastTime + deltaTime
                    yield HeapEvent(newTime, traceindex, size, self.scaleFactor(size))
                    lastTime = newTime

    def trace(self, traceindex: int) -> Optional[HeapTrace]:
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
        self._mdfile.close()

    def _makeHeapTrace(self, rawTrace: List[Tuple[str, int]]) -> HeapTrace:
        return [
            TraceLine(
                filename=line[0],
                lineno=line[1],
                fileline=linecache.getline(line[0], line[1]).strip(),
            )
            # NB: Raw traces are in reverse order! That makes them faster to write.
            for line in reversed(rawTrace)
        ]
