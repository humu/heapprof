from typing import Dict, Optional

import _heapprof

# Types exposed as part of the API -- check out their .py files to learn more!
from .flow_graph import FlowGraph  # noqa
from .reader import Reader
from .types import (HeapTrace, RawTrace, RawTraceLine, Snapshot,  # noqa
                    TraceLine)

# This default sampling rate was determined through some trial and error. However, it may or may not
# be the right one for any particular case.
DEFAULT_SAMPLING_RATE = {128: 1e-4, 8192: 0.1}


def start(filebase: str, samplingRate: Optional[Dict[int, float]] = None) -> None:
    """Start heapprof in profiling (normal) mode.

    Args:
        filebase: The outputs will be written to filebase.{hpm, hpd}, a pair of local files which
            can later be read using the HeapProfile class. NB that these must be local files for
            performance reasons.
        samplingRate: A dict from byte size to sampling probability. Each byte size is interpreted
            as the upper bound of the range, and the sampling probability for byte sizes larger than
            the largest range given is always 1; thus the default value means to profile allocations
            of 1-127 bytes at 1 in 10,000, to profile allocations of 128-8,191 bytes at 1 in 10, and
            to profile all allocations of 8,192 bytes or more.

    Raises:
        TypeError: If samplingRate is not a mapping of the appropriate type.
        ValueError: If samplingRate contains repeated entries.
        RuntimeError: If the profiler is already running.
    """
    _heapprof.startProfiler(
        filebase, samplingRate if samplingRate is not None else DEFAULT_SAMPLING_RATE
    )


def gatherStats() -> None:
    """Start heapprof in stats gathering mode.

    When the profiler is stopped, this will print out statistics on the size distribution of memory
    allocations. This can be useful for choosing sampling rates for profiling.
    """
    _heapprof.startStats()


def stop() -> None:
    """Stop the heap profiler.

    NB that if the program exits, this will be implicitly called.
    """
    _heapprof.stop()


def isProfiling() -> bool:
    """Test if the heap profiler is currently running."""
    return _heapprof.isProfiling()


def read(filebase: str, timeInterval: float = 60, precision: float = 0.01) -> Reader:
    """Open a reader, and create a digest for it if needed.

    Args:
        filebase: The name of the file to open; the same as the argument passed to start().

    Args which apply only if you're creating the digest (i.e., opening it for the first time):
        timeInterval: The time interval between successive snapshots to store in the digest,
            in seconds.
        precision: At each snapshot, stack traces totalling up to this fraction of total
            memory used at that frame may be dropped into the "other stack trace" bucket.
            This can greatly shrink the size of the digest at no real cost in usefulness.
            Must be in [0, 1); a value of zero means nothing is dropped.
    """
    r = Reader(filebase)
    if not r.hasDigest():
        r.makeDigest(timeInterval=timeInterval, precision=precision, verbose=True)
    return r
