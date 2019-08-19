#ifndef _HEAPPROF_PORT_H__
#define _HEAPPROF_PORT_H__

// System portability library, with various things so this can compile on a range of machines.

// All Windows platforms need this soonest.
#ifdef _WIN64
#include <windows.h>
#elif _WIN32
// TODO, maybe support this someday? It would require a lot more care with integer sizes in various
// places, but 32-bit machines are a dying breed.
#error heapprof does not currently support WIN32 builds.
#endif

////////////////////////////////////////////////////////////////////////////////////////////
// Time-related definitions

// Include this on all machines, but append things to it in some cases.
#include <time.h>

// Define clock_gettime etc for Windows boxen.
#ifdef _WIN64

inline void gettime(struct timespec *spec) {
  // This function returns the number of 100-nanosecond intervals (decashakes) since midnight
  // January 1st, 1601 UTC. This is a rather interesting combination of base and unit, being
  // roughly what you would need to describe nuclear chain reactions around the time of the
  // Protestant Reformation.
  uint64_t wintime;
  GetSystemTimeAsFileTime(reinterpret_cast<FILETIME*>(&wintime));

  // Convert to decashakes since the UNIX Epoch.
  const int64_t since_epoch = wintime - 116444736000000000LL;

  spec->tv_sec = since_epoch / 10000000LL;
  spec->tv_nsec = (since_epoch % 10000000LL) * 100;
}

#else

// POSIX systems just have a function for this.
inline void gettime(struct timespec *spec) {
  clock_gettime(CLOCK_REALTIME, spec);
}

#endif

////////////////////////////////////////////////////////////////////////////////////////////
// Bitwise operations, bytesex, and CPU branching.

// A note here: We need to achieve some portable operations which aren't yet
// available in the C++ standard, but the portable logic for them is
// depressingly long. So we include ABSL, which has extremely nice
// implementations of them. However, these are in the base/internal directory,
// because the ABSL team hasn't decided to make them formally part of the spec
// yet. At some point, these are definitely going to be moved out of internal,
// just Not Quite Yet. (Signed, the original author of endian.h and quite a bit
// of the other stuff in this directory; sigh. -- zunger@)
#include "absl/base/internal/bits.h"
// This file defines ghton[size] and gntoh[size].
#include "absl/base/internal/endian.h"

// C++20 will have a standardized version of this. Until then, we use
// compiler-specific directives, which are notably missing in MSVC.
#if __clang__ || __GNUC__
#define PREDICT_FALSE(expr) __builtin_expect(static_cast<bool>(expr), 0)
#define PREDICT_TRUE(expr) __builtin_expect(static_cast<bool>(expr), 1)
#else
#define PREDICT_FALSE(expr) (expr)
#define PREDICT_TRUE(expr) (expr)
#endif

// Return ceil(log2(x)).
inline int Log2RoundUp(uint64_t x) {
  return x ? 64 - absl::base_internal::CountLeadingZeros64(x - 1) : 0;
}

////////////////////////////////////////////////////////////////////////////////////////////
// File system access

#ifdef _WIN64
// Seriously, Microsoft? You don't have pwrite? Normal people implement write *on top of* pwrite.
inline ssize_t pwrite(int fd, const void *buf, size_t nbytes, off_t offset) {
  const off_t pos = lseek(fd, 0, SEEK_CUR);
  lseek(fd, offset, SEEK_SET);
  const ssize_t written = write(fd, buf, nbytes);
  lseek(fd, pos, SEEK_SET);
  return written;
}

// _O_BINARY has no POSIX equivalent, but if you don't set it, it will default to a text mode that
// will do "helpful" things like translate 0x0a to 0x0d0a when you write it.
#define WRITE_MODE _O_WRONLY | _O_CREAT | _O_TRUNC | _O_BINARY
#define READ_MODE _O_RDONLY | _O_BINARY

#else  // Non-Windows machines

// Defines write() etc on Unices.
#include <unistd.h>

#define WRITE_MODE O_WRONLY | O_CREAT | O_TRUNC
#define READ_MODE O_RDONLY

#endif  // Switch over platforms

#endif  // _HEAPPROF_PORT_H__
