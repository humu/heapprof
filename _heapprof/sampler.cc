#include "_heapprof/sampler.h"
#include <algorithm>
#include "_heapprof/scoped_object.h"
#include "_heapprof/util.h"

Sampler::Range::Range(Py_ssize_t m, double p) : max_bytes(m) {
  if (p == 0) {
    probability = 0;
  } else if (p == 1) {
    probability = UINT_FAST32_MAX;
  } else {
    probability = static_cast<uint_fast32_t>(p * UINT_FAST32_MAX);
  }
}

Sampler::Sampler(PyObject *sampling_rate) {
  if (!PyMapping_Check(sampling_rate)) {
    PyErr_SetString(PyExc_TypeError, "samplingRate is not a Dict[int, float]");
    return;
  }

  {
    ScopedObject items(PyMapping_Items(sampling_rate));

    for (int i = 0, len = PyList_GET_SIZE(items.get()); i < len; ++i) {
      PyObject *item = PyList_GET_ITEM(items.get(), i);
      Py_ssize_t max_size;
      double probability;
      if (!PyArg_ParseTuple(item, "nd", &max_size, &probability)) {
        // Exception already set.
        return;
      }
      if (max_size < 0) {
        PyErr_Format(PyExc_ValueError,
                     "%zd is not a valid memory allocation size.", max_size);
        return;
      }
      if (probability < 0 || probability > 1) {
        PyErr_Format(
            PyExc_ValueError,
            "%f is not a valid probability; it must be in the range [0, 1].",
            probability);
        return;
      }
      ranges_.push_back(Range(max_size, probability));
    }
  }

  sort(ranges_.begin(), ranges_.end());

  // Safety check: Make sure there are no repeated entries.
  if (ranges_.size() > 1) {
    auto it = ranges_.begin();
    Py_ssize_t last_size = it->max_bytes;
    for (++it; it != ranges_.end(); ++it) {
      if (it->max_bytes == last_size) {
        PyErr_SetString(PyExc_ValueError,
                        "Repeated size entry in samplingRate");
        return;
      }
      last_size = it->max_bytes;
    }
  }

  ok_ = true;
}

void Sampler::WriteStateToFile(int fd) const {
  WriteVarintToFile(fd, ranges_.size());
  for (auto it = ranges_.begin(); it != ranges_.end(); ++it) {
    WriteFixed64ToFile(fd, it->max_bytes);
    WriteFixed32ToFile(fd, it->probabilityAsUint32());
  }
}
