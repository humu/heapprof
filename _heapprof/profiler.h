#ifndef _HEAPPROF_PROFILER_H__
#define _HEAPPROF_PROFILER_H__

#include <time.h>
#include <memory>
#include <unordered_map>
#include "Python.h"
#include "_heapprof/abstract_profiler.h"
#include "_heapprof/sampler.h"
#include "_heapprof/util.h"

// Profiler is the heart of heap profiling. When the profiler is on, a
// singleton Profiler exists, and is patched into the malloc calls using
// the standard hooks, by the logic in heapprof.cc; to end profiling, it is
// simply unpatched and deleted.
//
// All the real work happens in this file, as the patched calls trigger
// Profiler's Handle{Malloc, Realloc, Free} methods, which are the things
// that generate actual log entries and so on.

// This class is thread-compatible, but not thread-safe; callers are responsible
// for ensuring its methods are not called in parallel. (See _malloc_patch.cc
// for how this is done, and why we don't do the seemingly simple thing of
// making this class thread-safe instead)
class Profiler : public AbstractProfiler {
 public:
  // Takes ownership of the sampler.
  Profiler(const char *filebase, Sampler *sampler);
  virtual ~Profiler();

  // These each require that ptr (newptr) not be nullptr.
  virtual void HandleMalloc(void *ptr, size_t size);
  virtual void HandleFree(void *ptr);

  // Verifies validity of the profiler after construction. If false, the
  // exception is already set.
  bool ok() const { return ok_; }

 private:
  // The information we store for a live pointer.
  struct LivePointer {
    // The trace at which it was allocated.
    uint32_t traceindex;
    // The size of the memory allocated. (NB: This is the size as returned by
    // malloc, which alas is *not* the size as actually pulled by malloc; but
    // there's no API-agnostic way to find out what the particular malloc
    // implementation on this machine actually did.)
    size_t size;
  };

  std::unique_ptr<Sampler> sampler_;

  // File pointers to the two output files.
  ScopedFile metadata_file_;
  ScopedFile data_file_;

  // The time of the previous event.
  struct timespec last_clock_;

  // The next trace index we'll assign. Note that trace index 0 is defined to be
  // "the bogus trace index."
  uint32_t next_trace_index_ = 1;

  // A hash map from tracefp to trace index.
  std::unordered_map<uint32_t, uint32_t> trace_index_;

  // Data about currently live pointers.
  std::unordered_map<void *, LivePointer> live_set_;

  bool ok_ = false;

  // Get the current trace index.
  int GetTraceIndex();
};

#endif  // _HEAPPROF_PROFILER_H__
