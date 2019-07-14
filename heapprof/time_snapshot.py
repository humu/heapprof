from typing import Dict, Optional, TextIO

from .heap_profile import HeapEvent, HeapProfile


class TimeSnapshot(object):
    """A TimeSnapshot represents a summary of heap usage at a particular timestamp. It doesn't
    contain the actual traces, only the memory usage! For the traces, use the HeapProfile's
    trace() method.
    """

    def __init__(self, profile: HeapProfile) -> None:
        self.profile = profile
        # Time, in seconds since the Epoch.
        self.timestamp: float = 0
        # Estimated total heap size, in bytes.
        self.totalSize: int = 0
        # A map from trace index to active heap amounts, in bytes. The values should add up to
        # totalSize.
        self.heapUsers: Dict[int, int] = {}

    @classmethod
    def makeFromWindow(
        cls,
        profile: HeapProfile,
        startTime: Optional[float] = None,
        endTime: Optional[float] = None,
    ) -> 'TimeSnapshot':
        """Build a TimeSnapshot from all the data in a given window of time. "None" means "to
        infinity."
        """
        snapshot = cls(profile)
        for event in profile:
            if (startTime is not None and event.timestamp < startTime) or (
                endTime is not None and event.timestamp > endTime
            ):
                continue
            snapshot.add(event)
        return snapshot

    @classmethod
    def atTime(cls, profile: HeapProfile, atRelativeTime: float) -> 'TimeSnapshot':
        return cls.makeFromWindow(profile, endTime=profile.initialTime + atRelativeTime)

    def add(self, event: HeapEvent) -> None:
        """Add a single event to this snapshot."""
        self.timestamp = max(self.timestamp, event.timestamp)
        estSize = round(event.size * event.scaleFactor)
        if event.traceindex not in self.heapUsers:
            self.heapUsers[event.traceindex] = estSize
        else:
            self.heapUsers[event.traceindex] += estSize
            if not self.heapUsers[event.traceindex]:
                del self.heapUsers[event.traceindex]

    def asCollapsedStack(self, output: TextIO) -> None:
        """Output a time snapshot in Brendan Gregg's "collapsed stack" format. This can be
        visualized as a Flame graph with tools like speedscope.app. (Note that if you're using
        speedscope, only the "left heavy" and "sandwich" views make sense; the "time order" view
        is intended for CPU profiles over time, and would show random nonsense for heaps)
        """
        otherSize = 0
        for traceindex, size in self.heapUsers.items():
            trace = self.profile.trace(traceindex)
            if trace is None:
                otherSize += size
            else:
                traceArray = [f'{line.filename}:{line.lineno}' for line in trace]
                output.write(';'.join(traceArray))
                output.write(f' {size}\n')

        if otherSize > 0:
            output.write(f'OTHER {otherSize}\n')

    def writeCollapsedStack(self, outfile: str) -> None:
        """Write a "collapsed stack" to disk. This is provided as a useful helper when exploring
        heap profiles interactively.
        """
        with open(outfile, 'w') as output:
            self.asCollapsedStack(output)
