#ifndef _HEAPPROF_UTIL_H__
#define _HEAPPROF_UTIL_H__

#include <assert.h>
#include <fcntl.h>
#include <string.h>
#include <string>
#include "Python.h"
#include "_heapprof/port.h"

//////////////////////////////////////////////////////////////////////////////////////////////////
// File I/O helpers

// A ScopedFile is a scoped file descriptor that closes (and optionally
// deletes!) on exit.
class ScopedFile {
 public:
  // Create a ScopedFile for either reading or writing, depending on the
  // parameter. After constructing it, if this is false, the file failed to open
  // and the exception has been set.
  ScopedFile(const char *filebase, const char *extension, bool write);
  ~ScopedFile();

  operator int() const { return fd_; }
  operator bool() const { return fd_ != -1; }
  const std::string &filename() const { return filename_; }

  // If delete-on-exit is set, this file will not just be closed on exit, it
  // will be deleted. You can use this to manage files that should only be
  // preserved if writing them works.
  void set_delete_on_exit(bool v) { delete_ = v; }

 private:
  const std::string filename_;
  const int fd_;
  bool delete_;
};

//////////////////////////////////////////////////////////////////////////////////////////////////
// Data writing helpers
// Because heap profiling is pretty performance-critical, we pick an output
// format that is as easy as possible to write. The helpers below help assemble
// the buffers that we'll dump to disk. NB that the methods whose name begins
// with "Unsafe" are exactly what they say: they DO NOT DO ANY BOUNDS CHECKING
// and expect their callers to have worked that out for them.

// A signed type has 8*sizeof(T) - 1 bits in its max value. This would encode to
// ceil((8*sizeof(T) - 1) / 7) bytes in varint coding, or (8*sizeof(T)-1+6)/7
// bytes.
#define MAX_SIGNED_VARINT_SIZE(signed_type) ((8 * sizeof(signed_type) + 5) / 7)
#define MAX_UNSIGNED_VARINT_SIZE(us_type) ((8 * sizeof(us_type) + 6) / 7)

// Write 'value' as a varint to the end of buffer, without doing any bounds
// checking. (It's assumed that the caller has already guaranteed this!) Returns
// a pointer immediately beyond that which was written. This code is based on
// the method used in protobuf.
inline uint8_t *UnsafeAppendVarint(uint8_t *buffer, int value) {
  assert(value >= 0);
  // Common case: small value, one byte.
  if (value < 0x80) {
    buffer[0] = static_cast<uint8_t>(value);
    return buffer + 1;
  }
  // Pretty common case: two byte value.
  buffer[0] = static_cast<uint8_t>(value | 0x80);
  value >>= 7;
  if (value < 0x80) {
    buffer[1] = static_cast<uint8_t>(value);
    return buffer + 2;
  }
  // Generic case: read lots of bytes.
  buffer++;
  do {
    *buffer = static_cast<uint8_t>(value | 0x80);
    value >>= 7;
    ++buffer;
  } while (PREDICT_FALSE(value >= 0x80));
  *buffer++ = static_cast<uint8_t>(value);
  return buffer;
}

// True if x is a UINT32-aligned pointer.
#define UINT32_ALIGNED(x) ((reinterpret_cast<intptr_t>(x) & 0x3) == 0)

// Append value, in network byte order, to the buffer, and return a pointer
// beyond where the write happened. No bounds checking is performed.
inline uint8_t *UnsafeAppendFixed32(uint8_t *buffer, uint32_t value) {
  if (PREDICT_TRUE(UINT32_ALIGNED(buffer))) {
    *reinterpret_cast<uint32_t *>(buffer) = absl::ghtonl(value);
  } else {
    const uint32_t norm = absl::ghtonl(value);
    memcpy(buffer, &norm, sizeof(uint32_t));
  }
  return buffer + sizeof(uint32_t);
}

// The read/write functions below are thread-hostile; they must only be called
// from a single thread at a time.
// All of these functions set the Python exception whenever they fail.

// Write single numbers to a file.
void WriteVarintToFile(int fd, uint64_t value);
void WriteFixed32ToFile(int fd, uint32_t value);
void WriteFixed64ToFile(int fd, uint64_t value);

// Read single numbers from a file. If they return false, they also set the
// Python exception.
bool ReadVarintFromFile(int fd, uint64_t *value);
bool ReadFixed32FromFile(int fd, uint32_t *value);
bool ReadFixed64FromFile(int fd, uint64_t *value);

// Write a string to a file as varint length + bytes. Fails (and sets the
// exception) only if the passed argument isn't a valid string.
bool WriteStringToFile(int fd, PyObject *value);
// Returns nullptr and sets the exception on failure; returns a reference owned
// by the caller on success.
PyObject *ReadStringFromFile(int fd);

// Set result = stop - start. result->tv_nsec is guaranteed to be in [0, 1B)
inline void DeltaTime(const struct timespec &start, const struct timespec &stop,
                      struct timespec *result) {
  result->tv_sec = stop.tv_sec - start.tv_sec;
  result->tv_nsec = stop.tv_nsec - start.tv_nsec;
  if (result->tv_nsec < 0) {
    result->tv_nsec += 1000000000L;
    result->tv_sec -= 1;
  }
}

#endif  // _HEAPPROF_UTIL_H__
