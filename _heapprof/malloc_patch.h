#ifndef _HEAPPROF_MALLOC_PATCH_H__
#define _HEAPPROF_MALLOC_PATCH_H__

#include "_heapprof/abstract_profiler.h"

// These functions do the work of connecting and disconnecting a Profiler
// from the Python malloc hooks. In a normal world -- the world envisioned by
// PEP445 -- these functions would be too simple to require their own file, but
// as so often happens, the best-laid schemes of mice and API designers gang aft
// a-gley.

// Attach a profiler to the malloc hooks and start profiling. This function
// takes ownership of the profiler state; it will be deleted when it is
// detached.
void AttachProfiler(AbstractProfiler *profiler);

// Detach the profiler from the malloc hooks and stop profiling. It is not an
// error to call this if there is no active profiling.
void DetachProfiler();

// Test if profiling is active.
bool IsProfilerAttached();

// Called to initialize this subset of the module, after the module as a whole
// is created. Returns true on success; false is fatal.
bool MallocPatchInit();

#endif  // _HEAPPROF_MALLOC_PATCH_H__
