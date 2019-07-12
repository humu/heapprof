#include "_heapprof/stats_gatherer.h"
#include <stdio.h>
#include <algorithm>
#include <cstdio>
#include <string>
#include <vector>
#include "_heapprof/util.h"

StatsGatherer::StatsGatherer() {}

StatsGatherer::~StatsGatherer() {
  struct StatsString {
    std::string size;
    std::string num_allocs;
    std::string total_bytes;
  };

  // These initial values are the lengths of the titles for the columns.
  int size_len = 4;
  int allocs_len = 5;
  int total_len = 5;

  std::vector<StatsString> stats;
  int prev_size = 0;
  for (auto it = bins_.begin(); it != bins_.end(); ++it) {
    const int new_size = 1 << it->first;
    StatsString summary{
        std::to_string(prev_size + 1) + " - " + std::to_string(new_size),
        std::to_string(it->second.num_allocs),
        std::to_string(it->second.total_bytes)};
    size_len = std::max<int>(size_len, summary.size.size());
    allocs_len = std::max<int>(allocs_len, summary.num_allocs.size());
    total_len = std::max<int>(total_len, summary.total_bytes.size());
    stats.push_back(summary);

    prev_size = new_size;
  }

  fprintf(stderr, "-------------------------------------------\n");
  fprintf(stderr, "HEAP USAGE SUMMARY\n");
  fprintf(stderr, "%*s %*s %*s\n", size_len, "Size", allocs_len, "Count",
          total_len, "Bytes");
  for (auto it = stats.begin(); it != stats.end(); ++it) {
    fprintf(stderr, "%*s %*s %*s\n", size_len, it->size.c_str(), allocs_len,
            it->num_allocs.c_str(), total_len, it->total_bytes.c_str());
  }
}

void StatsGatherer::HandleMalloc(void* ptr, size_t size) {
  BinStats& stats = bins_[Log2RoundUp(size)];
  stats.num_allocs++;
  stats.total_bytes += size;
}
