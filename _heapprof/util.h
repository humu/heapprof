#ifndef _HEAPPROF_UTIL_H__
#define _HEAPPROF_UTIL_H__

#include <arpa/inet.h>
#include <assert.h>
#include <fcntl.h>
#include <string.h>
#include <time.h>
#include "Python.h"

// C++20 will have a standardized version of this. Until then, we use compiler-specific directives,
// which are notably missing in MSVC.
#if __clang__ || __GNUC__
#define PREDICT_FALSE(expr) __builtin_expect(static_cast<bool>(expr), 0)
#define PREDICT_TRUE(expr) __builtin_expect(static_cast<bool>(expr), 1)
#else
#define PREDICT_FALSE(expr) (expr)
#define PREDICT_TRUE(expr) (expr)
#endif

static inline int Log2RoundUp(uint64_t x) {
  // This special case is required because __builtin_clzll doesn't have defined
  // behavior for argument zero; NB that it does the right thing on any chip
  // that has the modern BSR instruction, but not necessarily on older impls
  // before this. "CLZ" stands for "count leading zeroes," btw.
  return x <= 1 ? 0 : 64 - __builtin_clzll(x - 1);
}

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
    *reinterpret_cast<uint32_t *>(buffer) = htonl(value);
  } else {
    const uint32_t norm = htonl(value);
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
