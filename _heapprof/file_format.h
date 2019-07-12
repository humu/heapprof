#ifndef _HEAPPROF_FILE_FORMAT_H__
#define _HEAPPROF_FILE_FORMAT_H__

#include <time.h>
#include "Python.h"
#include "frameobject.h"
#include "_heapprof/sampler.h"

// Bit constants for the index words in an event.
const uint32_t kDeltaIsNegative = 0x80000000;
const uint32_t kOperationIsFree = 0x40000000;
const uint32_t kHighBits = (kDeltaIsNegative | kOperationIsFree);

// Write the metadata header to an .hpm file.
void WriteMetadata(int fd, const struct timespec &start_clock,
                   const Sampler &sampler);

// Read the metadata header from an .hpm file. This will either return a tuple
// (float initial_clock, Dict[int, float] sample_rate), or return nullptr and
// set the exception.
PyObject *ReadMetadata(int fd);

// Write a single heap event to the indicated file descriptor. last_clock is the
// clock value of the previous event written; it will be updated by this method.
// alloc is true for an allocation, or false for a free.
void WriteEvent(int fd, struct timespec *last_clock,
                const struct timespec &timestamp, uint32_t traceindex,
                size_t size, bool alloc);

// Read a single heap event from the given file descriptor, given a value for
// the timestamp of the previous event. Returns either a tuple (float timestamp,
// int traceindex, int size), or nullptr + raises an EOFError.
PyObject *ReadEvent(int fd, float last_time);

// Write the current Python stack trace as a raw trace to the indicated file
// descriptor. Returns false if there is no such trace!
bool WriteRawTrace(int fd);

// Read a single raw trace from the given file descriptor. Returns a
// List[Tuple[str, int]] on success, or nullptr + raises an EOFError.
PyObject *ReadRawTrace(int fd);

// Check if a certain stack frame should be ignored when building and analyzing
// stack traces.
bool SkipFrame(PyFrameObject *pyframe);

#endif  // _HEAPPROF_FILE_FORMAT_H__
