#include "_heapprof/file_format.h"
#include "_heapprof/scoped_object.h"
#include "_heapprof/util.h"

// Write out the initial metadata. The wire format of this metadata is:
//   fixed32: File format version (currently 1)
//   fixed64: Initial clock value.seconds
//   fixed64: Initial clock value.nsec
//   varint: Number of sampling ranges
//     fixed64: max size
//     fixed32: Probability scaled to UINT32_MAX
void WriteMetadata(int fd, const struct timespec &start_clock,
                   const Sampler &sampler) {
  WriteFixed32ToFile(fd, 1);
  WriteFixed64ToFile(fd, start_clock.tv_sec);
  WriteFixed64ToFile(fd, start_clock.tv_nsec);
  sampler.WriteStateToFile(fd);
}

PyObject *ReadMetadata(int fd) {
  uint32_t version;
  if (!ReadFixed32FromFile(fd, &version)) {
    PyErr_SetString(PyExc_EOFError, "Couldn't read version");
    return nullptr;
  }
  if (version != 1) {
    PyErr_Format(PyExc_ValueError, "Unknown metadata format %d", version);
    return nullptr;
  }

  uint64_t start_sec;
  uint64_t start_nsec;
  if (!ReadFixed64FromFile(fd, &start_sec) ||
      !ReadFixed64FromFile(fd, &start_nsec)) {
    PyErr_SetString(PyExc_EOFError, "Couldn't read start time");
    return nullptr;
  }
  const float start_time = start_sec + 1e-9 * start_nsec;

  ScopedObject sampling_rate(PyDict_New());
  uint64_t num_ranges;
  if (!ReadVarintFromFile(fd, &num_ranges)) {
    PyErr_SetString(PyExc_EOFError, "Couldn't read number of sampling ranges");
    return nullptr;
  }
  for (uint64_t i = 0; i < num_ranges; ++i) {
    uint64_t maxsize;
    uint32_t scaled_probability;
    if (!ReadFixed64FromFile(fd, &maxsize) ||
        !ReadFixed32FromFile(fd, &scaled_probability)) {
      return PyErr_Format(PyExc_EOFError,
                          "Couldn't read data for sampling range %d", i);
    }

    // Remember that PyDict_SetItem grabs its own reference, so we need to clean
    // up these objects ourselves. Sigh.
    ScopedObject py_max_size(PyLong_FromLongLong(maxsize));
    ScopedObject py_prob(PyFloat_FromDouble(
        static_cast<double>(scaled_probability) / UINT32_MAX));
    if (PyDict_SetItem(sampling_rate.get(), py_max_size.get(), py_prob.get()) ==
        -1) {
      return nullptr;
    }
  }

  return Py_BuildValue("fO", start_time, sampling_rate.release());
}

// Writing events out to the log. The wire format for an event is:
// 4 bytes, in network order:
//    1 bit: set if delta_t < 0
//    1 bit: set if this is a free, clear if it is an alloc
//    30 bits: traceindex
// varint: abs(delta_t), seconds part
// varint: abs(delta_t), usec (not nsec!!) part
// varint: size

// The largest possible event uses 4 bytes for the trace word, a varint-coded
// time_t for seconds, a varint up to 10^9-1 for nsecs, and a varint-coded
// size_t for the number of bytes. As 1B can be coded in 5 bytes as a varint
// (it's just under 2^30, which requires 5 septets), that gives the formula
// below.
#define MAX_EVENT_SIZE \
  9 + MAX_SIGNED_VARINT_SIZE(time_t) + MAX_SIGNED_VARINT_SIZE(size_t)

static uint8_t g_event_buffer[MAX_EVENT_SIZE];

void WriteEvent(int fd, struct timespec *last_clock,
                const struct timespec &timestamp, uint32_t traceindex,
                size_t size, bool alloc) {
  assert(!(traceindex & kHighBits));
  assert(size >= 0);

  struct timespec delta_t;
  DeltaTime(*last_clock, timestamp, &delta_t);
  assert(delta_t.tv_nsec >= 0);
  assert(delta_t.tv_nsec < 1000000000L);

  *last_clock = timestamp;

  uint32_t head_word = traceindex;
  if (delta_t.tv_sec < 0) {
    head_word |= kDeltaIsNegative;
    delta_t.tv_sec = -delta_t.tv_sec;
  }
  if (!alloc) {
    head_word |= kOperationIsFree;
  }

  uint8_t *end = UnsafeAppendFixed32(g_event_buffer, head_word);
  // NB: Time deltas are only given to usec granularity, as per POSIX. So
  // shaving off three zeroes improves storage a lot and loses nothing!
  end = UnsafeAppendVarint(end, delta_t.tv_sec);
  end = UnsafeAppendVarint(end, delta_t.tv_nsec / 1000);
  end = UnsafeAppendVarint(end, size);

  write(fd, g_event_buffer, end - g_event_buffer);
}

PyObject *ReadEvent(int fd, float last_time) {
  uint32_t indexword;
  uint64_t delta_seconds;
  uint64_t delta_usec;
  uint64_t size;
  if (!ReadFixed32FromFile(fd, &indexword) ||
      !ReadVarintFromFile(fd, &delta_seconds) ||
      !ReadVarintFromFile(fd, &delta_usec) || !ReadVarintFromFile(fd, &size)) {
    // Exception already set.
    return nullptr;
  }

  if (indexword & kDeltaIsNegative) {
    delta_seconds = -delta_seconds;
  }
  if (indexword & kOperationIsFree) {
    size = -size;
  }

  return Py_BuildValue("fii", last_time + delta_seconds + (1e-6 * delta_usec),
                       indexword & ~kHighBits, size);
}

bool SkipFrame(PyFrameObject *pyframe) {
  // If the filename begins with a <, this is an internal frame and we should
  // ignore it because these make the frames illegible.
  const Py_UCS4 first_char =
      PyUnicode_READ_CHAR(pyframe->f_code->co_filename, 0);
  return (first_char == 0x3c);
}

// Write a new stack trace to the metadata file. The wire format for a stack
// trace entry is a repeated group:
//    varint: line number + 1
//    varint: size of filename
//    bytes: filename
// terminated by a sentinel:
//    varint: 0
// Note, however, that the lines of this stack trace are in reverse order, going
// from the bottom *up*!
bool WriteRawTrace(int fd) {
  const PyThreadState *tstate = PyGILState_GetThisThreadState();
  if (tstate == nullptr) {
    return false;
  }

  // OK, we're going to need to write a sequence of tuples,
  // (pyframe->f_code->co_filename, line number)
  for (PyFrameObject *pyframe = tstate->frame; pyframe != nullptr;
       pyframe = pyframe->f_back) {
    if (!SkipFrame(pyframe)) {
      WriteVarintToFile(fd, PyFrame_GetLineNumber(pyframe) + 1);
      WriteStringToFile(fd, pyframe->f_code->co_filename);
    }
  }
  WriteVarintToFile(fd, 0);
  return true;
}

PyObject *ReadRawTrace(int fd) {
  ScopedObject list(PyList_New(0));
  if (!list) {
    PyErr_SetString(PyExc_RuntimeError, "Failed to allocate an empty list");
    return nullptr;
  }

  uint64_t lineno;
  while (1) {
    if (!ReadVarintFromFile(fd, &lineno)) {
      PyErr_SetString(PyExc_EOFError, "Unexpected EOF when expecting line number in stack trace");
      return nullptr;
    }

    if (lineno == 0) {
      // Sentinel -- we reached the end!
      return list.release();
    }

    lineno -= 1;
    PyObject *filename = ReadStringFromFile(fd);
    if (!filename) {
      PyErr_SetString(PyExc_EOFError, "Unexpected EOF when reading filename from stack trace");
      return nullptr;
    }

    ScopedObject tuple(Py_BuildValue("Ni", filename, lineno));
    if (!tuple) {
      PyErr_SetString(PyExc_RuntimeError, "Failed to build result tuple for raw stack trace");
      return nullptr;
    }
    // NB: PyList_Append grabs its own reference to the tuple, so we don't
    // release it; we indeed decrement its refcount at the end of this scope.
    if (PyList_Append(list.get(), tuple.get()) == -1) {
      PyErr_SetString(PyExc_RuntimeError, "Failed to append result tuple to list");
      return nullptr;
    }
  }
}
