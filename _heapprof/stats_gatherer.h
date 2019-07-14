#ifndef _HEAPPROF_STATS_GATHERER_H__
#define _HEAPPROF_STATS_GATHERER_H__

#include <map>

#include "_heapprof/abstract_profiler.h"

// StatsGatherer is an AbstractProfiler which collects distribution statistics
// about the sizes of mallocs, and prints them out to stderr when the profiler
// is stopped. This is useful for figuring out the best choice of sampling rate
// parameters to pick for proper profiling.
class StatsGatherer : public AbstractProfiler {
 public:
  StatsGatherer();
  virtual ~StatsGatherer();

  void HandleMalloc(void *ptr, size_t size);

 private:
  struct BinStats {
    int num_allocs = 0;
    size_t total_bytes = 0;
  };

  // Keyed by ceil(log2(alloc size))
  std::map<int, BinStats> bins_;
};

#endif  // _HEAPPROF_STATS_GATHERER_H__
