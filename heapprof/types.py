from typing import Dict, List, NamedTuple, Union


class RawTraceLine(NamedTuple):
    """A RawTraceLine represents a single line of code."""

    filename: str
    lineno: int

    def __str__(self) -> str:
        if self.lineno:
            return f'{self.filename}:{self.lineno}'
        else:
            return self.filename

    @classmethod
    def parse(cls, value: Union['RawTraceLine', str]) -> 'RawTraceLine':
        if isinstance(value, RawTraceLine):
            return value
        filename, linestr = value.rsplit(':', 1)
        return cls(filename, int(linestr))


# A RawTrace is the simplest form of a raw stack trace.
RawTrace = List[RawTraceLine]


class TraceLine(NamedTuple):
    """A TraceLine is a RawTraceLine plus the actual line of code. These can be fetched from HPM
    files so long as the source code is also present; doing so is (for obvious reasons) more
    expensive than just working with RawTraces, but can make nicer stack traces.
    """

    # The filename
    filename: str
    # The line number
    lineno: int
    # The actual line of code
    fileline: str


HeapTrace = List[TraceLine]


class Snapshot(NamedTuple):
    """A Snapshot represents the state of the heap at a single moment in time. These are the basic
    elements of .hpc files.
    """

    # The timestamp of this snapshot, relative to program start, in seconds.
    relativeTime: float

    # Memory usage, as a map from the trace index at which memory was allocated (which can be
    # resolved into a proper raw or full stack trace using an HPM) to live bytes in memory at
    # this time.
    usage: Dict[int, int]

    def totalUsage(self) -> int:
        return sum(self.usage.values())
