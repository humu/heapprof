#ifndef _HEAPPROF_SAMPLER_H__
#define _HEAPPROF_SAMPLER_H__

#include <cstdint>
#include <random>
#include <vector>
#include "Python.h"

// A Sampler maintains the map of sampling probabilities per allocation size.
// This will probably require some performance tuning.
class Sampler {
 public:
  // Construct a new Sampler. The argument must be a dict from int to double.
  explicit Sampler(PyObject* sampling_rate);
  ~Sampler() {}

  // Tests validity after construction. If this is false, the Python exception
  // has been set.
  bool ok() { return ok_; }

  // Decide if we should profile an allocation of the given size.
  bool Sample(int alloc_size);

  // Write the parameters of this sampler to a file.
  void WriteStateToFile(int fd) const;

 private:
  struct Range {
    Range(Py_ssize_t m, double p);
    Range& operator=(const Range& other) {
      max_bytes = other.max_bytes;
      probability = other.probability;
      return *this;
    }
    bool operator<(const Range& other) const {
      return max_bytes < other.max_bytes;
    }

    uint32_t probabilityAsUint32() const {
      if (probability == 0) {
        return 0;
      } else if (probability == UINT_FAST32_MAX) {
        return UINT32_MAX;
      } else {
        const double p = static_cast<double>(probability) / UINT_FAST32_MAX;
        return static_cast<uint32_t>(p * UINT32_MAX);
      }
    }

    Py_ssize_t max_bytes;
    uint_fast32_t probability;
  };

  // Sorted by max_bytes.
  std::vector<Range> ranges_;

  // Our RNG. minstd_rand uses Lehmer's generator, which is very fast and more
  // than good enough for our purposes.
  std::minstd_rand rng_ = std::minstd_rand();

  bool ok_ = false;
};

// Inline because this is called for every malloc.
inline bool Sampler::Sample(int alloc_size) {
  // ranges_ is small enough that a linear search is more efficient than a
  // binary one.
  for (auto it = ranges_.begin(); it != ranges_.end(); ++it) {
    if (it->max_bytes > alloc_size) {
      // Our sampling probability is it->probability
      if (it->probability == 0) {
        return false;
      } else if (it->probability == UINT_FAST32_MAX) {
        return true;
      } else {
        const bool result = rng_() < it->probability;
        return result;
      }
    }
  }

  // If it's bigger than all the ranges, we always interpret it as having
  // probability 1.
  return true;
}

#endif  // _HEAPPROF_SAMPLER_H__
