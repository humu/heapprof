# The C++ Bit

This directory contains the `_heapprof` package, the C++ part of heapprof. The top level of this
module is heapprof.cc, which declares the API; profiler.* contains the "brains" of the heap
profiler, while malloc_patch.* contains the logic required to hook the profiler onto the PEP445
malloc hooks correctly. (A task, alas, more subtle than it at first seems!)
