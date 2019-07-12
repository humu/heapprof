#ifndef _HEAPPROF_SCOPED_OBJECT_H__
#define _HEAPPROF_SCOPED_OBJECT_H__

#include <utility>
#include "Python.h"

// This is a simple wrapper around a PyObject which owns a reference. It's a
// more C++ish (and less bug-prone) way to grab a scoped reference to an object.
// Its syntax deliberately mimics that of std::unique_ptr.
class ScopedObject {
 public:
  explicit ScopedObject(PyObject *o) : o_(o) {}
  ~ScopedObject() { Py_XDECREF(o_); }

  PyObject &operator*() { return *o_; }
  const PyObject &operator*() const { return *o_; }
  explicit operator bool() const noexcept { return o_ != nullptr; }
  PyObject *operator->() const noexcept { return o_; }

  PyObject *get() const noexcept { return o_; }
  PyObject *release() noexcept {
    PyObject *o = o_;
    o_ = nullptr;
    return o;
  }
  void reset(PyObject *o) noexcept {
    Py_XDECREF(o_);
    o_ = o;
  }
  void swap(ScopedObject &other) noexcept {
    PyObject *o = other.o_;
    other.o_ = o_;
    o_ = o;
  }

 private:
  PyObject *o_;
};

#endif  // _HEAPPROF_SCOPED_OBJECT_H__
