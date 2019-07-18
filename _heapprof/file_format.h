#ifndef _HEAPPROF_FILE_FORMAT_H__
#define _HEAPPROF_FILE_FORMAT_H__

#include <time.h>
#include "Python.h"
#include "_heapprof/sampler.h"
#include "frameobject.h"

///////////////////////////////////////////////////////////////////////////////
// .hpm files: the metadata of a profile.
// This consists of a metadata header, followed by a sequence of "raw traces."
// Raw traces contain filenames and line numbers, and can be converted to nicer
// structures by the wrapping Python code.

// Write the metadata header to an .hpm file.
void WriteMetadata(int fd, const struct timespec &start_clock,
                   const Sampler &sampler);

// Read the metadata header from an .hpm file. This will either return a tuple
// (double initial_clock, Dict[int, double] sample_rate), or return nullptr and
// set the exception.
PyObject *ReadMetadata(int fd);

// Write the current Python stack trace as a raw trace to the indicated file
// descriptor. Returns false if there is no such trace!
bool WriteRawTrace(int fd);

// Read a single raw trace from the given file descriptor. Returns a
// List[Tuple[str, int]] on success, or nullptr + raises an EOFError.
PyObject *ReadRawTrace(int fd);

// Check if a certain stack frame should be ignored when building and analyzing
// stack traces.
bool SkipFrame(PyFrameObject *pyframe);

///////////////////////////////////////////////////////////////////////////////
// .hpd files: the raw log of events.
// This consists of a sequence of event entries, each of which encodes a
// timestamp, a trace index (which is a 1-based index into the list of traces in
// the .hpm file), a number of bytes, and whether it's an alloc or free.

// Bit constants for the index words in an event.
const uint32_t kDeltaIsNegative = 0x80000000;
const uint32_t kOperationIsFree = 0x40000000;
const uint32_t kHighBits = (kDeltaIsNegative | kOperationIsFree);

// Write a single heap event to the indicated file descriptor. last_clock is the
// clock value of the previous event written; it will be updated by this method.
// alloc is true for an allocation, or false for a free.
void WriteEvent(int fd, struct timespec *last_clock,
                const struct timespec &timestamp, uint32_t traceindex,
                size_t size, bool alloc);

// Read a single heap event from the given file descriptor, given a value for
// the timestamp of the previous event. Returns either a tuple (double
// delta-time, int traceindex, int size), or nullptr + raises an EOFError.
PyObject *ReadEvent(int fd);

///////////////////////////////////////////////////////////////////////////////
// .hpc files: a digested version of an .hpd file.
// This file is created after profiling is over; it combines the events in an
// .hpd file into a sequence of time snapshots, which can be random-accessed.

// Read filebase.hpd and create filebase.hpc.
bool MakeDigestFile(const char *filebase, int interval_msec, double precision,
                    bool verbose);

// Read the metadata and index from a .hpc file. Returns a
// Tuple[float, float, List[int]], giving the initial time, the time delta
// between frames, and a list of byte offsets for each frame in the file.
PyObject *ReadDigestMetadata(int fd);

// Read a single snapshot from a digest. The offset is one of the entries in the
// list given in the metadata. The result is a dict from trace index to number
// of live bytes at that instant.
PyObject *ReadDigestEntry(int fd, Py_ssize_t offset);

#endif  // _HEAPPROF_FILE_FORMAT_H__
