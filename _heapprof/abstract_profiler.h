#ifndef _HEAPPROF_ABSTRACT_PROFILER_H__
#define _HEAPPROF_ABSTRACT_PROFILER_H__

#include <assert.h>
#include <stddef.h>

// An AbstractProfiler is something that does actual profiling. For now, we
// don't have any fancy registration mechanism to refer to these by name;
// instead, each AbstractProfiler is used by a different exposed Python method
// defined in heapprof.cc.
//
// AbstractProfiler implementations should be thread-compatible, but need not be
// thread-safe.
class AbstractProfiler {
 public:
  // NB: The Python dynamic loader seems to get upset if any classes are purely
  // abstract; it wants _all_ the symbols to be loadable. ::shrug::
  virtual ~AbstractProfiler() {}

  // These may each assume that ptr is not null.
  virtual void HandleMalloc(void *ptr, size_t size) {}
  virtual void HandleFree(void *ptr) {}

  // The default implementation is good for most cases. We could be more clever
  // here, treating oldptr == nullptr as a malloc, oldptr == newptr as a malloc
  // of the delta size, and oldptr != newptr as a free + malloc, but this would
  // run into trouble if oldptr weren't selected by sampling. This is almost as
  // good and way easier. This method may assume that newptr != nullptr, but
  // oldptr may be null.
  virtual void HandleRealloc(void *oldptr, void *newptr, size_t size) {
    assert(newptr != nullptr);
    if (oldptr != nullptr) {
      HandleFree(oldptr);
    }
    HandleMalloc(newptr, size);
  }
};

#endif  // _HEAPPROF_ABSTRACT_PROFILER_H__
