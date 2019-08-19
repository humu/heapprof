#include "_heapprof/file_format.h"
#include <algorithm>
#include <map>
#include <utility>
#include <vector>
#include "_heapprof/scoped_object.h"
#include "_heapprof/util.h"

////////////////////////////////////////////////////////////////////////////////
// .hpm files

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

// The C++ representation of the .hpm header
struct RawMetadata {
  uint32_t version;
  uint64_t start_sec;
  uint64_t start_nsec;
  std::map<uint64_t, double> sampling_probability;

  inline double start_time() const { return start_sec + 1e-9 * start_nsec; }
};

// Read the metadata from a .hpm file in C++ form; return false and set the
// exception on failure.
static bool ReadRawMetadata(int fd, RawMetadata *md) {
  if (!ReadFixed32FromFile(fd, &md->version)) {
    PyErr_SetString(PyExc_EOFError, "Couldn't read version");
    return false;
  }
  if (md->version != 1) {
    PyErr_Format(PyExc_ValueError, "Unknown metadata format %d", md->version);
    return false;
  }

  if (!ReadFixed64FromFile(fd, &md->start_sec) ||
      !ReadFixed64FromFile(fd, &md->start_nsec)) {
    PyErr_SetString(PyExc_EOFError, "Couldn't read start time");
    return false;
  }

  uint64_t num_ranges;
  if (!ReadVarintFromFile(fd, &num_ranges)) {
    PyErr_SetString(PyExc_EOFError, "Couldn't read number of sampling ranges");
    return false;
  }
  for (uint64_t i = 0; i < num_ranges; ++i) {
    uint64_t maxsize;
    uint32_t scaled_probability;
    if (!ReadFixed64FromFile(fd, &maxsize) ||
        !ReadFixed32FromFile(fd, &scaled_probability)) {
      PyErr_Format(PyExc_EOFError, "Couldn't read data for sampling range %d",
                   i);
      return false;
    }
    md->sampling_probability[maxsize] =
        static_cast<double>(scaled_probability) / UINT32_MAX;
  }
  return true;
}

PyObject *ReadMetadata(int fd) {
  RawMetadata md;
  if (!ReadRawMetadata(fd, &md)) {
    return nullptr;
  }

  ScopedObject sampling_rate(PyDict_New());
  for (auto p : md.sampling_probability) {
    // Remember that PyDict_SetItem grabs its own reference, so we need to clean
    // up these objects ourselves. Sigh.
    ScopedObject py_max_size(PyLong_FromLongLong(p.first));
    ScopedObject py_prob(PyFloat_FromDouble(p.second));
    if (PyDict_SetItem(sampling_rate.get(), py_max_size.get(), py_prob.get()) ==
        -1) {
      return nullptr;
    }
  }

  return Py_BuildValue("fO", md.start_time(), sampling_rate.release());
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
      PyErr_SetString(
          PyExc_EOFError,
          "Unexpected EOF when expecting line number in stack trace");
      return nullptr;
    }

    if (lineno == 0) {
      // Sentinel -- we reached the end!
      return list.release();
    }

    lineno -= 1;
    PyObject *filename = ReadStringFromFile(fd);
    if (!filename) {
      PyErr_SetString(PyExc_EOFError,
                      "Unexpected EOF when reading filename from stack trace");
      return nullptr;
    }

    ScopedObject tuple(Py_BuildValue("Ni", filename, lineno));
    if (!tuple) {
      PyErr_SetString(PyExc_RuntimeError,
                      "Failed to build result tuple for raw stack trace");
      return nullptr;
    }
    // NB: PyList_Append grabs its own reference to the tuple, so we don't
    // release it; we indeed decrement its refcount at the end of this scope.
    if (PyList_Append(list.get(), tuple.get()) == -1) {
      PyErr_SetString(PyExc_RuntimeError,
                      "Failed to append result tuple to list");
      return nullptr;
    }
  }
}

////////////////////////////////////////////////////////////////////////////////
// .hpd files

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

struct RawEvent {
  uint32_t indexword;
  uint64_t delta_seconds;
  uint64_t delta_usec;
  uint64_t size;

  inline double delta_time() const {
    double result = delta_seconds + (1e-6 * delta_usec);
    if (indexword & kDeltaIsNegative) {
      result = -result;
    }
    return result;
  }

  inline int64_t byte_size() const {
    const int64_t result = static_cast<int64_t>(size);
    return is_free() ? -result : result;
  }

  inline bool is_free() const { return indexword & kOperationIsFree; }

  inline uint32_t traceindex() const { return indexword & ~kHighBits; }
};

// Read a single event and return it in C++ format. Returns false and sets
// the exception on problem.
static bool ReadRawEvent(int fd, RawEvent *raw_event) {
  return (ReadFixed32FromFile(fd, &raw_event->indexword) &&
          ReadVarintFromFile(fd, &raw_event->delta_seconds) &&
          ReadVarintFromFile(fd, &raw_event->delta_usec) &&
          ReadVarintFromFile(fd, &raw_event->size));
}

PyObject *ReadEvent(int fd) {
  RawEvent raw_event;
  if (!ReadRawEvent(fd, &raw_event)) {
    // Exception already set.
    return nullptr;
  }

  return Py_BuildValue("fii", raw_event.delta_time(), raw_event.traceindex(),
                       raw_event.byte_size());
}

////////////////////////////////////////////////////////////////////////////////
// .hpc files

// The format of a .hpc file is:
//   fixed32: version
//   fixed64: initial time seconds
//   fixed64: initial time nsec
//   varint: msec between snapshots
//   fixed64: byte offset to index
//
// Followed by a sequence of entries:
//   fixed32: magic number
//   varint: number of items
//     varint: traceindex
//     varint: size of item (for first item), or amount by which size is smaller
//             than the previous entry (for successive items).
//
// Followed by the index:
//   fixed32: index magic
//   varint: number of entries
//   varints: relative offset of entry N from entry N-1 or (for N=0) start of
//   file.

static const uint32_t kSnapshotMagic = 0x5379a0bd;
static const uint32_t kIndexMagic = 0xab935776;

struct HPMMetadata {
  double initial_time;
  // The int is the same as in a sampler; the float is the multiplicative
  // factor.
  std::map<uint64_t, float> scaling_factor;

  // Convert a raw size (unsigned, from a single event) to a scaled size
  // (accounting for sampling). We deliberately round this to an integer.
  inline int scaled_size(uint64_t raw_size) const {
    auto l_it = scaling_factor.upper_bound(raw_size);
    if (l_it == scaling_factor.end()) {
      return static_cast<int>(raw_size);
    } else {
      return static_cast<int>(raw_size * l_it->second);
    }
  }
};

// Read the metadata from a .hpm file and return it in C++ format. On error,
// returns false and sets the exception.
static bool GetHPMMetadata(const char *filebase, HPMMetadata *result) {
  ScopedFile hpm(filebase, ".hpm", false);
  if (!hpm) {
    return false;
  }

  RawMetadata md;
  if (!ReadRawMetadata(hpm, &md)) {
    return false;
  }

  result->initial_time = md.start_time();
  for (auto p : md.sampling_probability) {
    result->scaling_factor[p.first] = (p.second == 0 ? 0 : 1.0 / p.second);
  }

  return true;
}

// Sort function to put traces in descending order by size.
static bool SortPairs(const std::pair<uint32_t, int> &a,
                      const std::pair<uint32_t, int> &b) {
  return a.second > b.second;
}

static void WriteDigestEntry(int fd, const std::map<uint32_t, int> live_bytes,
                             double precision) {
  // Build up a map sorted in descending order by byte size.
  std::vector<std::pair<uint32_t, int> > sorted_bytes;
  sorted_bytes.reserve(live_bytes.size());
  int64_t total_size = 0;
  for (auto p : live_bytes) {
    sorted_bytes.push_back(p);
    total_size += p.second;
  }
  std::sort(sorted_bytes.begin(), sorted_bytes.end(), SortPairs);

  // If a finite precision was set, we're going to drop a bunch of stack traces
  // from the end, and instead aggregate their totals into a single "other"
  // category which is written with trace index zero. (Zero is the reserved "no
  // trace" index, so this makes good sense)
  if (precision > 0) {
    const int64_t slop_amount = static_cast<int64_t>(total_size * precision);
    int64_t other_bytes = 0;  // Bytes in the "OTHER" category.
    size_t last_index = sorted_bytes.size();
    for (; last_index >= 0 && other_bytes < slop_amount; --last_index) {
      other_bytes += sorted_bytes[last_index].second;
    }
    sorted_bytes.resize(last_index);

    if (other_bytes > 0) {
      const auto pair = std::make_pair(0, other_bytes);
      auto position = std::lower_bound(sorted_bytes.begin(), sorted_bytes.end(),
                                       pair, SortPairs);
      sorted_bytes.insert(position, pair);
    }
  }

  WriteFixed32ToFile(fd, kSnapshotMagic);
  WriteVarintToFile(fd, sorted_bytes.size());
  if (!sorted_bytes.empty()) {
    WriteVarintToFile(fd, sorted_bytes[0].first);
    WriteVarintToFile(fd, sorted_bytes[0].second);

    for (size_t i = 1; i < sorted_bytes.size(); ++i) {
      WriteVarintToFile(fd, sorted_bytes[i].first);
      // These are sorted in descending order, so we just write the differences.
      WriteVarintToFile(fd,
                        sorted_bytes[i - 1].second - sorted_bytes[i].second);
    }
  }
}

static void TimeToStderr(float seconds) {
  const int hours = static_cast<int>(seconds / 3600);
  seconds -= hours * 3600;
  const int minutes = static_cast<int>(seconds / 60);
  seconds -= minutes * 60;
  if (hours != 0) {
    fprintf(stderr, "%d:%02d:%02d", hours, minutes, static_cast<int>(seconds));
  } else {
    fprintf(stderr, "%02d:%02d", minutes, static_cast<int>(seconds));
  }
}

static void BytesToStderr(double bytes) {
  if (bytes < 1.2e9) {
    fprintf(stderr, "%0.1fMB", bytes / 1048576);
  } else {
    fprintf(stderr, "%0.1fGB", bytes / 1073741824);
  }
}

// TODO(zunger): This function is still way too slow; on my laptop it can digest
// about 50sec/sec. Some clever batch-reading and buffering of data, and maybe a
// smarter varint decoder, could probably speed this up by a *lot*.
bool MakeDigestFile(const char *filebase, int interval_msec, double precision,
                    bool verbose) {
  HPMMetadata hpm;
  if (!GetHPMMetadata(filebase, &hpm)) {
    return false;
  }

  ScopedFile hpd(filebase, ".hpd", false);
  if (!hpd) return false;

  ScopedFile hpc(filebase, ".hpc", true);
  if (!hpc) return false;
  hpc.set_delete_on_exit(true);

  // Write the header.
  WriteFixed32ToFile(hpc, 1);
  const uint64_t seconds = static_cast<uint64_t>(hpm.initial_time);
  WriteFixed64ToFile(hpc, seconds);
  const uint64_t nsec = static_cast<uint64_t>(1e9 * (hpm.initial_time - seconds));
  WriteFixed64ToFile(hpc, nsec);
  WriteVarintToFile(hpc, interval_msec);
  // This is where we're going to come back later and write the index location.
  const off_t index_offset_location = lseek(hpc, 0, SEEK_CUR);

  WriteFixed64ToFile(hpc, 0);

  // Now, let's write the entries.
  std::map<uint32_t, int> live_bytes;
  std::vector<off_t> snapshot_starts;

  const double interval = static_cast<double>(interval_msec) / 1000;
  double relative_time = 0;
  double next_snapshot = interval;
  int events_read = 0;
  int snapshots_written = 0;
  RawEvent event;

  struct timespec start_time;
  off_t total_bytes;
  if (verbose) {
    gettime(&start_time);
    total_bytes = lseek(hpd, 0, SEEK_END);
    lseek(hpd, 0, SEEK_SET);
    fprintf(stderr, "Digesting %s: ", filebase);
    BytesToStderr(total_bytes);
    fprintf(stderr, "\n");
  }

  while (ReadRawEvent(hpd, &event)) {
    // This is long-running, so check the signal handler. On interrupt, though,
    // we break, not fail: we'll dump out what we have so far.
    if (PyErr_CheckSignals() == -1) {
      break;
    }

    // Fetch the event data
    const uint32_t traceindex = event.traceindex();
    int scaled_size = hpm.scaled_size(event.size);
    if (event.is_free()) scaled_size = -scaled_size;

    // Update live_bytes and relative_time
    auto it = live_bytes.find(traceindex);
    if (it == live_bytes.end()) {
      live_bytes[traceindex] = scaled_size;
    } else {
      it->second += scaled_size;
      if (!it->second) {
        live_bytes.erase(it);
      }
    }

    const double delta_time = event.delta_time();
    if (delta_time > 0) {
      relative_time += delta_time;
    }
    for (; relative_time >= next_snapshot; next_snapshot += interval) {
      snapshot_starts.push_back(lseek(hpc, 0, SEEK_CUR));
      WriteDigestEntry(hpc, live_bytes, precision);
      ++snapshots_written;
    }

    ++events_read;

    if (verbose && !(events_read % 500000)) {
      struct timespec now;
      gettime(&now);
      struct timespec delta;
      DeltaTime(start_time, now, &delta);
      const double time_used = delta.tv_sec + 1e-9 * delta.tv_nsec;
      const off_t bytes = lseek(hpd, 0, SEEK_CUR);
      const double fraction = static_cast<double>(bytes) / total_bytes;
      const double eta = time_used * ((1.0 / fraction) - 1);

      // For those wanting to understand exactly what's being printed here: the
      // rate is given both in MBps (of data being read) and sec/sec, i.e.
      // seconds of profiling time per second of digestion time.
      fprintf(stderr, "Digested ");
      TimeToStderr(relative_time);
      fprintf(stderr, " of data (%0.1fM events, ", 1e-6 * events_read);
      BytesToStderr(bytes);
      fprintf(stderr, ") @ ");
      BytesToStderr(bytes / time_used);
      fprintf(stderr, "ps=%0.1fsec/sec; %0.1f%%; ETA ",
              relative_time / time_used, 100 * fraction);
      TimeToStderr(eta);
      fprintf(stderr, ")\n");
    }
  }

  // ReadRawEvent set an exception; ignore it. Other exceptions are legit.
  if (PyErr_ExceptionMatches(PyExc_EOFError) ||
      PyErr_ExceptionMatches(PyExc_ValueError)) {
    PyErr_Clear();
  }

  // Finally, write the index.
  if (verbose) {
    fprintf(stderr, "Writing index with %zd entries\n", snapshot_starts.size());
  }
  uint64_t index_offset = static_cast<uint64_t>(lseek(hpc, 0, SEEK_CUR));
  index_offset = absl::ghtonll(index_offset);
  pwrite(hpc, &index_offset, sizeof(index_offset), index_offset_location);

  WriteFixed32ToFile(hpc, kIndexMagic);
  WriteVarintToFile(hpc, snapshot_starts.size());
  if (!snapshot_starts.empty()) {
    WriteVarintToFile(hpc, snapshot_starts[0]);
    for (size_t i = 1; i < snapshot_starts.size(); ++i) {
      WriteVarintToFile(hpc, snapshot_starts[i] - snapshot_starts[i - 1]);
    }
  }

  hpc.set_delete_on_exit(false);
  return !PyErr_Occurred();
}

PyObject *ReadDigestMetadata(int fd) {
  uint32_t version = 0;
  if (!ReadFixed32FromFile(fd, &version) || version != 1) {
    PyErr_Format(PyExc_ValueError, "Unrecognized file version %d", version);
    return nullptr;
  }

  uint64_t initial_secs;
  uint64_t initial_nsec;
  uint64_t interval_msec;
  uint64_t index_offset;
  if (!ReadFixed64FromFile(fd, &initial_secs) ||
      !ReadFixed64FromFile(fd, &initial_nsec) ||
      !ReadVarintFromFile(fd, &interval_msec) ||
      !ReadFixed64FromFile(fd, &index_offset)) {
    return nullptr;
  }

  if (lseek(fd, index_offset, SEEK_SET) != static_cast<off_t>(index_offset)) {
    PyErr_Format(PyExc_ValueError, "Invalid index offset %llx in metadata",
                 index_offset);
    return nullptr;
  }
  uint32_t magic;
  if (!ReadFixed32FromFile(fd, &magic) || magic != kIndexMagic) {
    PyErr_Format(PyExc_ValueError, "Bad index magic number %08x", magic);
    return nullptr;
  }
  uint64_t num_entries;
  if (!ReadVarintFromFile(fd, &num_entries)) {
    PyErr_SetString(PyExc_ValueError, "Couldn't read index header");
    return nullptr;
  }

  ScopedObject offsets(PyList_New(num_entries));
  uint64_t offset = 0;
  for (uint64_t i = 0; i < num_entries; ++i) {
    uint64_t delta;
    if (!ReadVarintFromFile(fd, &delta)) {
      PyErr_SetString(PyExc_ValueError, "Broken index");
      return nullptr;
    }
    offset += delta;
    PyList_SET_ITEM(offsets.get(), i, PyLong_FromLongLong(offset));
  }

  const float initial_time = initial_secs + 1e-9 * initial_nsec;
  const float interval_time = 1e-3 * interval_msec;
  return Py_BuildValue("ffO", initial_time, interval_time, offsets.release());
}

PyObject *ReadDigestEntry(int fd, Py_ssize_t offset) {
  if (lseek(fd, offset, SEEK_SET) != offset) {
    PyErr_Format(PyExc_ValueError, "Invalid entry offset %d", offset);
    return nullptr;
  }

  uint32_t magic;
  if (!ReadFixed32FromFile(fd, &magic) || magic != kSnapshotMagic) {
    PyErr_Format(PyExc_ValueError, "Invalid magic number for entry at %d",
                 offset);
    return nullptr;
  }

  uint64_t num_items;
  if (!ReadVarintFromFile(fd, &num_items)) {
    return nullptr;
  }

  ScopedObject result(PyDict_New());
  if (!result) {
    return nullptr;
  }

  int64_t size = 0;
  for (uint64_t i = 0; i < num_items; ++i) {
    uint64_t traceindex;
    uint64_t delta_size;
    if (!ReadVarintFromFile(fd, &traceindex) ||
        !ReadVarintFromFile(fd, &delta_size)) {
      return nullptr;
    }

    if (i == 0) {
      size = delta_size;
    } else {
      size -= delta_size;
    }

    ScopedObject py_traceindex(PyLong_FromLongLong(traceindex));
    ScopedObject py_size(PyLong_FromLongLong(size));
    if (!py_traceindex || !py_size ||
        PyDict_SetItem(result.get(), py_traceindex.get(), py_size.get()) ==
            -1) {
      return nullptr;
    }
  }

  return result.release();
}
