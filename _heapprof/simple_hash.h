#ifndef _HEAPPROF_SIMPLE_HASH_H__
#define _HEAPPROF_SIMPLE_HASH_H__

// This hash function is based on the hash used for tuples in
// Object/tupleobject.c.
class SimpleHash {
 public:
  SimpleHash() : acc_(kPrime5), count_(0) {}

  void add(uint32_t value) {
    acc_ += value * kPrime2;
    acc_ = ((acc_ << 13) | (acc_ >> 19));
    acc_ *= kPrime1;
    count_ += 1;
  }

  void add(void *ptr) {
    const intptr_t word = reinterpret_cast<intptr_t>(ptr);
    add(static_cast<uint32_t>(word));
    if (sizeof(intptr_t) == 8) {
      add(static_cast<uint32_t>(word >> 32));
    }
  }

  uint32_t get() const {
    const uint32_t value = acc_ + (count_ ^ (kPrime5 ^ 3527539UL));
    if (value == 0xffffffff) {
      return 1546275796;
    } else {
      return value;
    }
  }

 private:
  uint32_t acc_;
  uint32_t count_;

  static const uint32_t kPrime1 = 2654435761UL;
  static const uint32_t kPrime2 = 2246822519UL;
  static const uint32_t kPrime5 = 374761393UL;
};

#endif  // _HEAPPROF_SIMPLE_HASH_H__
