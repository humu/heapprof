#include "_heapprof/util.h"
#include <string>

#define VARINT_BUFFER_SIZE MAX_UNSIGNED_VARINT_SIZE(uint64_t)

static uint8_t g_varint_buffer[VARINT_BUFFER_SIZE];

void WriteVarintToFile(int fd, uint64_t value) {
  const uint8_t *end = UnsafeAppendVarint(g_varint_buffer, value);
  write(fd, g_varint_buffer, end - g_varint_buffer);
}

void WriteFixed32ToFile(int fd, uint32_t value) {
  const uint32_t data = absl::ghtonl(value);
  write(fd, &data, sizeof(uint32_t));
}

void WriteFixed64ToFile(int fd, uint64_t value) {
  const uint64_t data = absl::ghtonll(value);
  write(fd, &data, sizeof(uint64_t));
}

bool ReadFixed32FromFile(int fd, uint32_t *value) {
  const int bytes_read = read(fd, value, sizeof(uint32_t));
  if (bytes_read != sizeof(uint32_t)) {
    PyErr_SetString(PyExc_EOFError, "");
    return false;
  }
  *value = absl::gntohl(*value);
  return true;
}

bool ReadFixed64FromFile(int fd, uint64_t *value) {
  const int bytes_read = read(fd, value, sizeof(uint64_t));
  if (bytes_read != sizeof(uint64_t)) {
    PyErr_SetString(PyExc_EOFError, "");
    return false;
  }
  *value = absl::gntohll(*value);
  return true;
}

bool ReadVarintFromFile(int fd, uint64_t *value) {
  // Read the maximum number of bytes which could potentially be valid right
  // now; we'll put back the unused bytes later.
  const int bytes_read = read(fd, g_varint_buffer, VARINT_BUFFER_SIZE);
  *value = 0;
  int pos = 0;
  while (pos < bytes_read) {
    *value |= (g_varint_buffer[pos] & 0x7f) << (7 * pos);
    if (g_varint_buffer[pos] & 0x80) {
      pos++;
    } else {
      // Done! Put the remaining bytes back on the file.
      lseek(fd, -(bytes_read - pos - 1), SEEK_CUR);
      return true;
    }
  }
  // If we get here, the read failed!
  if (pos == bytes_read) {
    PyErr_SetString(PyExc_ValueError,
                    "Found a varint which could not decode into a uint64");
  } else {
    PyErr_SetString(PyExc_EOFError, "");
  }
  return false;
}

bool WriteStringToFile(int fd, PyObject *value) {
  Py_ssize_t len;
  const char *cstr = PyUnicode_AsUTF8AndSize(value, &len);
  if (cstr == nullptr) {
    // Exception already set.
    return false;
  }
  WriteVarintToFile(fd, len);
  write(fd, cstr, len);
  return true;
}

PyObject *ReadStringFromFile(int fd) {
  uint64_t len;
  if (!ReadVarintFromFile(fd, &len)) {
    // Exception already set.
    return nullptr;
  }
  const Py_ssize_t size = static_cast<Py_ssize_t>(len);

  char *buffer = reinterpret_cast<char *>(malloc(size));
  if (buffer == nullptr) {
    PyErr_Format(PyExc_MemoryError,
                 "Failed to allocate %zd bytes for string read", size);
    return nullptr;
  }
  const int bytes_read = read(fd, buffer, size);
  if (bytes_read < size) {
    free(buffer);
    PyErr_SetString(PyExc_EOFError, "");
    return nullptr;
  }

  // Succeed or fail, we'll return the result of this.
  PyObject *result = PyUnicode_DecodeUTF8(buffer, size, "strict");

  free(buffer);
  return result;
}

static inline int ScopedFileMode(bool write) {
  return write ? WRITE_MODE : READ_MODE;
}

ScopedFile::ScopedFile(const char *filebase, const char *suffix, bool write)
    : filename_(std::string(filebase) + suffix),
      fd_(open(filename_.c_str(), ScopedFileMode(write), 0600)),
      delete_(false) {
  if (fd_ == -1) {
    PyErr_SetFromErrnoWithFilenameObject(
        PyExc_OSError,
        PyUnicode_FromStringAndSize(filename_.c_str(), filename_.length()));
  }
}

ScopedFile::~ScopedFile() {
  if (fd_ != -1 && close(fd_) == -1) {
    PyErr_SetFromErrno(PyExc_OSError);
    return;
  }
  if (delete_ && unlink(filename_.c_str()) == -1) {
    PyErr_SetFromErrno(PyExc_OSError);
    return;
  }
}
