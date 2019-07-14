#include "_heapprof/reentrant_scope.h"

Py_tss_t ReentrantScope::in_malloc_ = Py_tss_NEEDS_INIT;

ReentrantScope::ReentrantScope() {
  PyThread_tss_create(&in_malloc_);
  const void *ptr = PyThread_tss_get(&in_malloc_);
  if (ptr == nullptr) {
    is_top_level_ = true;
    // Py_True is totally arbitrary; we just need any non-nullptr PyObject.
    PyThread_tss_set(&in_malloc_, Py_True);
  } else {
    assert(ptr == Py_True);
    is_top_level_ = false;
  }
}

ReentrantScope::~ReentrantScope() {
  if (is_top_level_) {
    PyThread_tss_set(&in_malloc_, nullptr);
  }
}
