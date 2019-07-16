#ifndef _HEAPPROF_REENTRANT_SCOPE_H__
#define _HEAPPROF_REENTRANT_SCOPE_H__

#include "Python.h"
#include "pythread.h"

// Python separates its memory management into several "domains," each of which
// has their own malloc, realloc, calloc, and free functions. In _malloc_patch,
// we're going to instrument all of these domains with calls to the profiler --
// but there's one catch. Some of the handlers which we're about to instrument
// call *each other*; e.g., the OBJECT domain's malloc sometimes falls back to
// the MEMORY domain's malloc. When this happens, we want to make sure that
// we're only profiling at the topmost scope, so that we don't double-count
// memory.
//
// ReentrantScope is a simple solution to this problem; each malloc-type
// function keeps one of these in scope, and its is_top_level() method reveals
// whether we're at the top level of the malloc call (and so should profile) or
// not. Under the hood, this is done with a simple thread-local variable.
class ReentrantScope {
 public:
  ReentrantScope();
  ~ReentrantScope();

  bool is_top_level() const { return is_top_level_; }

 private:
  // This is a thread-local variable which indicates if we're already inside a
  // memory allocation call. It's set by an outermost call, and reset on its
  // exit, and we only do profiling at that outermost // level. As this is
  // PyObject-valued, we'll use for its two values IN_MALLOC and nullptr.
  static Py_tss_t in_malloc_;

  bool is_top_level_;
};

#endif  // _HEAPPROF_REENTRANT_SCOPE_H__
