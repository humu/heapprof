#include "_heapprof/profiler.h"
#include <fcntl.h>
#include <stdio.h>
#include <string>
#include "Python.h"
#include "_heapprof/file_format.h"
#include "_heapprof/port.h"
#include "_heapprof/simple_hash.h"
#include "_heapprof/util.h"
#include "frameobject.h"

//////////////////////////////////////////////////////////////////////////////////////////////////
// Profiler

Profiler::Profiler(const char *filebase, Sampler *sampler)
    : sampler_(sampler),
      metadata_file_(filebase, ".hpm", true),
      data_file_(filebase, ".hpd", true) {
  if (!metadata_file_ || !data_file_) {
    return;
  }

  // Initialize our clock and write initial metadata.
  gettime(&last_clock_);
  WriteMetadata(metadata_file_, last_clock_, *sampler_);
  ok_ = true;
}

Profiler::~Profiler() {}

void Profiler::HandleMalloc(void *ptr, size_t size) {
  assert(ptr != nullptr);
  if (!sampler_->Sample(size)) {
    return;
  }
  struct timespec timestamp;
  gettime(&timestamp);
  const uint32_t traceindex = GetTraceIndex();
  live_set_[ptr] = {traceindex, size};
  WriteEvent(data_file_, &last_clock_, timestamp, traceindex, size, true);
}

void Profiler::HandleFree(void *ptr) {
  assert(ptr != nullptr);
  auto live_ptr = live_set_.find(ptr);
  // This means that this ptr wasn't sampled in HandleMalloc.
  if (live_ptr == live_set_.end()) {
    return;
  }
  struct timespec timestamp;
  gettime(&timestamp);
  WriteEvent(data_file_, &last_clock_, timestamp, live_ptr->second.traceindex,
             live_ptr->second.size, false);
  live_set_.erase(live_ptr);
}

// Get a unique fingerprint of the current Python stack trace. NB that this
// fingerprint will never be committed to disk, so it only needs to be unique
// within the scope of this program execution; that means we can safely hash
// just the code pointers.
static uint32_t GetTraceFP() {
  const PyThreadState *tstate = PyGILState_GetThisThreadState();
  if (tstate == nullptr) {
    // This is really weird and we should figure out what the appropriate error
    // handling is.
    return 0;
  }

  SimpleHash tracefp;
  for (PyFrameObject *pyframe = tstate->frame; pyframe != nullptr;
       pyframe = pyframe->f_back) {
    if (!SkipFrame(pyframe)) {
      tracefp.add(pyframe->f_code);
      tracefp.add(static_cast<uint32_t>(PyFrame_GetLineNumber(pyframe)));
    }
  }
  return tracefp.get();
}

int Profiler::GetTraceIndex() {
  const uint32_t tracefp = GetTraceFP();
  if (PREDICT_FALSE(tracefp == 0)) {
    return 0;
  }

  const auto it = trace_index_.find(tracefp);
  if (PREDICT_TRUE(it != trace_index_.end())) {
    return it->second;
  }

  // First time we've seen this tracefp! Write it out to the metadata file, add
  // its new index, and return that.
  uint32_t new_index = next_trace_index_++;
  // If we can't write a stack trace, or if the trace index overflowed, give
  // this tracefp the "invalid index" value.
  if (PREDICT_FALSE(!WriteRawTrace(metadata_file_) || new_index & kHighBits)) {
    new_index = 0;
  }
  trace_index_[tracefp] = new_index;
  return new_index;
}
