import heapq
from typing import Dict, List, NamedTuple, Optional, Tuple

from .heap_profile import HeapProfile, HeapTrace
from .time_snapshot import TimeSnapshot


class TimeSlice(NamedTuple):
    # The absolute clock time, in seconds since the epoch.
    timestamp: float

    # The estimated total size of the heap, in bytes. This will *NOT INCLUDE* any allocations in
    # sizes whose sampling rate was zero; it will include estimates for allocations whose size was
    # sampled with nonzero probability; and it will be quasi-exact for allocations larger than the
    # biggest specified range, or those whose sampling rate is 1. The "quasi" in "quasi-exact" means
    # that when you call malloc(N), it actually may grab some larger number of bytes (e.g. to ensure
    # that the result is memory-aligned, but potentially for other implementation reasons as well)
    # and there's no robust way to find out what that actual number is across malloc
    # implementations. Sigh.
    estTotalSize: float

    # A dict from trace index -> estimated number of bytes used by the top N items in memory. This
    # always contains an entry with key 0 for "all other uses of memory," so that the values add up
    # to estTotalSize. (NB that 0 is not a valid trace index)
    #
    # TODO: This isn't the most useful thing right now, since often fixed allocations from program
    # start take up a lot of space in it, or multiple stack traces with a great deal in common are
    # combining to be a more interesting "top item" than any of the biggest individuals. The API for
    # this field should probably change to something more valuable.
    topItems: Dict[int, float]


class HeapHistory(NamedTuple):
    """HeapHistory is your main tool for looking at how a heap profile evolved over time. You build
    one with its make() method; its heart is then a sequence of TimeSlices at fixed intervals, each
    TimeSlice showing how much memory was used and what the top consumers were at that time.

    You can plot this (cf methods like asArrays, below) to get a nice graph of memory utilization
    over time; you can then grab TimeSnapshots at particular moments of interest to do a deeper dive
    into how memory was being used right then.
    """

    # The sampling rates that were used in this heap profile. This is provided as part of the
    # result, but is not needed in order to parse the history.
    samplingRate: Dict[int, float]

    # The history of the heap size.
    history: List[TimeSlice]

    # A dict from trace indices (which show up in the time slices) to actual stack traces. A value
    # of "None" means "unknown stack trace."
    traces: Dict[int, Optional[HeapTrace]]

    @classmethod
    def make(
        cls,
        profile: HeapProfile,
        timeGranularity: float = 1,
        topN: int = 10,
        startTime: Optional[float] = None,
        endTime: Optional[float] = None,
    ) -> 'HeapHistory':
        """Build a time-based representation of the life of a heap.
        Args:
            profile: A HeapProfile to analyze.
            timeGranularity: The time granularity, in seconds, in which the output should be
                generated.
            topN: At any given time slice, we should show the top N memory allocation traces.
            startTime, endTime: A time range (in seconds since the epoch) to probe.
        """
        # The outputs we're building. NB that trace index 0 always means "unknown."
        traces: Dict[int, Optional[HeapTrace]] = {0: None}
        history: List[TimeSlice] = []

        # The current state of the world
        nextSliceTime = profile.initialTime + timeGranularity
        maxTime = profile.initialTime
        snapshot = TimeSnapshot(profile)

        def prepTimeSlice() -> Dict[int, float]:
            # Prepare to generate a time slice: update self.traces and return everything we want to
            # write to it except the timestamp.
            topUsers = _findTopN(snapshot, topN)

            # Get the traces -- note how we only do this for traces we're actually going to output.
            for traceIndex in topUsers.keys():
                if traceIndex not in traces:
                    traces[traceIndex] = profile.trace(traceIndex)

            return topUsers

        def dumpEventsUntil(timestamp: float) -> None:
            nonlocal nextSliceTime

            topUsers = prepTimeSlice()

            # Write the events.
            while timestamp > nextSliceTime:
                history.append(TimeSlice(nextSliceTime, snapshot.totalSize, topUsers))
                nextSliceTime += timeGranularity

        for index, event in enumerate(profile.readEvents()):
            maxTime = max(maxTime, event.timestamp)
            if event.timestamp > nextSliceTime:
                dumpEventsUntil(event.timestamp)
            snapshot.add(event)
            if index % 10000 == 0:
                print(f'Processed {index} events spanning {maxTime - profile.initialTime} seconds')

        # Dump the final slice
        history.append(TimeSlice(maxTime, snapshot.totalSize, prepTimeSlice()))

        return cls(profile.samplingRate, history, traces)

    def asArrays(self, yscale: int = 1) -> Tuple[List[float], List[List[float]], List[int]]:
        """Convert a HeapHistory to a set of arrays suitable for feeding to pyplot.

        You can produce a nice graph of these with the commands:

            import matplotlib.pyplot as plt
            a = heapHistory.asArrays(1 << 30)
            plt.subplots().stackplot(a[0], *a[1])
            plt.show()

        Args:
            yscale: An amount by which to scale the outputs. You may want to pick 1 << 20 or
                1 << 30 to see values in megs or gigs.

        Returns:
            List[float]: The X-axis, given in seconds since run start.
            List[List[float]]: A list of Y-axes, one for each trace index which appears in the top
                N for at least one timestamp. Each array is parallel to the X-axis array; the
                values are the byte sizes at that time. If a given trace index isn't in the top N
                at that time, the value given is zero.
            List[int]: A list parallel to the previous list, giving the corresponding trace
                indices.

        The resulting stack traces are sorted in descending order by peak usage.
        """
        if not self.history:
            return [], [], []

        startTime = self.history[0].timestamp
        xAxis: List[float] = [e.timestamp - startTime for e in self.history]
        yAxes: Dict[int, List[float]] = {}
        for count, timeSlice in enumerate(self.history):
            for traceindex, size in timeSlice.topItems.items():
                if traceindex not in yAxes:
                    yAxes[traceindex] = [0] * len(xAxis)
                yAxes[traceindex][count] = size / yscale

        # A list of (max size, traceindex, data), sorted descending by max size.
        sortedYAxes = sorted(
            [(max(data), traceindex, data) for traceindex, data in yAxes.items()],
            key=lambda x: x[0],
            reverse=True,
        )

        return xAxis, [x[2] for x in sortedYAxes], [x[1] for x in sortedYAxes]


#################################################################################################
# Implementation details


class _HeapUser(NamedTuple):
    estSize: float
    traceIndex: int

    # NB reversed sense so that our heap pulls out the *biggest* users. NB also that mypy seems to
    # be confused about the type signatures of the standard data model methods for NamedTuple.
    def __lt__(self, other: '_HeapUser') -> bool:  # type: ignore
        return self.estSize > other.estSize


def _findTopN(snapshot: TimeSnapshot, topN: int) -> Dict[int, float]:
    heap = [_HeapUser(size, index) for index, size in snapshot.heapUsers.items() if index != 0]
    heapq.heapify(heap)
    result = {x.traceIndex: x.estSize for x in heap[:topN]}
    # mypy apparently doesn't understand sum().
    result[0] = snapshot.totalSize - sum(result.values())  # type: ignore
    return result
