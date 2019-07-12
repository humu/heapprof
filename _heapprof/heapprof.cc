#define PY_SSIZE_T_CLEAN
#include <memory>
#include "Python.h"
#include "_heapprof/file_format.h"
#include "_heapprof/malloc_patch.h"
#include "_heapprof/profiler.h"
#include "_heapprof/sampler.h"
#include "_heapprof/stats_gatherer.h"

// This file defines the _heapprof Python module, which is the outer interface
// between the Python and C++ layers. _heapprof contains these functions:
//
// _heapprof.startProfiler(filebase: str, samplingRate: Dict[int, float]]) ->
// None
//    Starts heap profiling, writing the outputs to filebase.hpm and
//    filebase.hpd. It is an error to call this if heap profiling is already
//    running. Implemented in HeapProfStart().
//
//    Args:
//      filebase: The output will be written to filebase.{hpm, hpd}. These files
//      can be parsed using
//        the HeapProfile Python class.
//      samplingRate: Control the sampling rates for the heap profiler. This is
//      a dictionary from
//        allocation sizes (in bytes) to sampling rates (as probabilities), and
//        is interpreted as being sorted by byte size. For an allocation of X
//        bytes, the sampling rate applied is that given for the next byte size
//        > X (if one such exists), or 100% if it is greater than all keys in
//        the dictionary.
//
// _heapprof.startStats() -> None
//    Starts heap profiling in stats-gathering mode. This will print a
//    distribution of heap statistics to stderr on output. It is an error to
//    call this if heap profiling is already running. Implemented in
//    HeapProfStartStats().
//
// _heapprof.stop() -> None
//    Stops heap profiling.
//    Implemented in HeapProfStop().
//
// _heapprof.isProfiling() -> bool
//    Returns True iff profiling is currently running.
//    Implemented in HeapProfIsProfiling().
//
// _heapprof.readEvent(fd: int, lastTime: float) -> Optional[Tuple[float, int,
// int]]
//    Try to read a single event from an .hpd file open at the given file
//    descriptor. Either returns a tuple (timestamp, traceindex, signed size) or
//    None to mark EOF.
//
// _heapprof.readRawTrace(fd: int) -> List[Tuple[str, int]]
//    Try to read a single raw trace from an .hpm file open at the given file
//    descriptor. Returns a list of (filename, lineno) pairs in "normal" trace
//    order (i.e., top part of the trace first). May raise EOFError.
//
// _heapprof.readMetadata(fd: int) -> Tuple[float, Dict[int, float]]
//    Try to read the metadata header from a .hpm file. Returns (start time,
//    sampling rate map) on success; may raise EOFError.

static PyObject *HeapProfStart(PyObject *self, PyObject *args) {
  // NB: PyArg_ParseTuple raises a Py exception on error.
  const char *filebase;
  PyObject *sampling_rate;
  if (!PyArg_ParseTuple(args, "sO", &filebase, &sampling_rate)) {
    return nullptr;
  }

  if (IsProfilerAttached()) {
    PyErr_SetString(PyExc_RuntimeError, "The profiler is already running.");
    return nullptr;
  }

  std::unique_ptr<Sampler> sampler(new Sampler(sampling_rate));
  if (!sampler->ok()) {
    return nullptr;
  }

  std::unique_ptr<Profiler> profiler(new Profiler(filebase, sampler.release()));
  if (!profiler->ok()) {
    return nullptr;
  }

  AttachProfiler(profiler.release());

  Py_RETURN_NONE;
}

static PyObject *HeapProfStartStats(PyObject *self, PyObject *args) {
  if (IsProfilerAttached()) {
    PyErr_SetString(PyExc_RuntimeError, "The profiler is already running.");
    return nullptr;
  }

  AttachProfiler(new StatsGatherer());
  Py_RETURN_NONE;
}

static PyObject *HeapProfStop(PyObject *self, PyObject *args) {
  DetachProfiler();
  Py_RETURN_NONE;
}

static PyObject *HeapProfIsProfiling(PyObject *self, PyObject *args) {
  if (IsProfilerAttached()) {
    Py_RETURN_TRUE;
  } else {
    Py_RETURN_FALSE;
  }
}

// _heapprof.readEvent(fd: int, lastTime: float) -> Optional[Tuple[float, int,
// int]]
static PyObject *HeapProfReadEvent(PyObject *self, PyObject *args) {
  int fd;
  float last_time;
  if (!PyArg_ParseTuple(args, "if", &fd, &last_time)) {
    return nullptr;
  }
  return ReadEvent(fd, last_time);
}

// _heapprof.readRawTrace(fd: int) -> List[Tuple[str, int]]
static PyObject *HeapProfReadRawTrace(PyObject *self, PyObject *args) {
  int fd;
  if (!PyArg_ParseTuple(args, "i", &fd)) {
    return nullptr;
  }
  return ReadRawTrace(fd);
}

// _heapprof.readMetadata(fd: int) -> Tuple[float, Dict[int, float]]
static PyObject *HeapProfReadMetadata(PyObject *self, PyObject *args) {
  int fd;
  if (!PyArg_ParseTuple(args, "i", &fd)) {
    return nullptr;
  }
  return ReadMetadata(fd);
}

PyDoc_STRVAR(module_doc, "Logging heap profiler");

static PyMethodDef module_methods[] = {
    {"startProfiler", HeapProfStart, METH_VARARGS,
     "Start the heap profiler in profile mode"},
    {"startStats", HeapProfStartStats, METH_VARARGS,
     "Start the heap profiler in stats mode"},
    {"stop", HeapProfStop, METH_VARARGS, "Stop the heap profiler"},
    {"isProfiling", HeapProfIsProfiling, METH_VARARGS,
     "Test if we are currently profiling"},
    {"readEvent", HeapProfReadEvent, METH_VARARGS,
     "Read an event from an hpd file"},
    {"readRawTrace", HeapProfReadRawTrace, METH_VARARGS,
     "Read a raw stack trace from an hpm file"},
    {"readMetadata", HeapProfReadMetadata, METH_VARARGS,
     "Read the MD header from an hpm file"},
    {nullptr, nullptr, 0, nullptr}};

static struct PyModuleDef module_def = {
    PyModuleDef_HEAD_INIT,
    "_heapprof",
    module_doc,
    0, /* non-negative size to be able to unload the module */
    module_methods,
    nullptr,
};

// NB: The name of this function is magic, as it is the entrypoint to the Python
// linker.
extern "C" {

PyMODINIT_FUNC PyInit__heapprof(void) {
  PyObject *m = PyModule_Create(&module_def);
  if (m == nullptr) {
    return nullptr;
  }
  if (!MallocPatchInit()) {
    return nullptr;
  }
  return m;
}
};
