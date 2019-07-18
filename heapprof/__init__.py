from typing import Dict, Optional

import _heapprof

from .reader import Reader  # noqa

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
            the largest range given is always 1; thus the default value means:
                Profile allocations of 1-127 bytes at 1 in 10,000
                Profile allocations of 128-8191 bytes at 1 in 10
                Profile all allocations of 8192 or more bytes

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
    """
    Stop the heap profiler.

    NB that if the program exits, this will be implicitly called.
    """
    _heapprof.stop()


def isProfiling() -> bool:
    """Test if the heap profiler is currently running."""
    return _heapprof.isProfiling()
