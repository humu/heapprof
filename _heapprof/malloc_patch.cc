#include "_heapprof/malloc_patch.h"
#include <memory>
#include "Python.h"
#include "_heapprof/reentrant_scope.h"
#include "pythread.h"

// The logic of this file is heavily inspired by that of _tracemalloc.c, whose
// brave authors have fought their way through the morass of why the simple
// approach given in PEP445's example 3 doesn't actually work. There are two
// subtle bits:
//
// (1) The OBJ and MEM malloc Handlers are called with the GIL held, but the RAW
// Handler is called without it held, so we need our own locking in just that
// case. (See ProfilerLock, below) (2) Various allocators can and do call
// *other* allocators; e.g., the OBJ allocator may call the MEM allocator
// depending on how many bytes it's asked for. When this happens, we need to
// make sure that we only profile the topmost call, to avoid double-counting.
// This is Handled with ReentrantScope.

// Our global profiler state.
static std::unique_ptr<AbstractProfiler> g_profiler;

// The underlying allocators that we're going to wrap. This gets filled in with
// meaningful content during AttachProfiler.
static struct {
  PyMemAllocatorEx raw;
  PyMemAllocatorEx mem;
  PyMemAllocatorEx obj;
} g_base_allocators;

// The MEM and OBJ domain allocators are always called with the GIL held, so we
// have serialization guaranteed. But the RAW allocator is called with the GIL
// in an unknown state, and it would be Very Bad to try to grab it ourselves. So
// to ensure that we serialize all access to g_profiler, we use a separate
// mutex in that case. ProfilerLock is a simple scoped lock.
class ProfilerLock {
 public:
  explicit ProfilerLock(void *ctx) : is_raw_(ctx == &g_base_allocators.raw) {
    if (is_raw_) {
      PyThread_acquire_lock(lock_, 1);
    }
  }

  ~ProfilerLock() {
    if (is_raw_) {
      PyThread_release_lock(lock_);
    }
  }

  static void ModuleInit() { lock_ = PyThread_allocate_lock(); }

 private:
  static PyThread_type_lock lock_;
  const bool is_raw_;
};
PyThread_type_lock ProfilerLock::lock_ = nullptr;

// The wrapped methods with which we will replace the standard malloc, etc. In
// each case, ctx will be a pointer to the appropriate base allocator.

static void *WrappedMalloc(void *ctx, size_t size) {
  ReentrantScope scope;
  PyMemAllocatorEx *alloc = reinterpret_cast<PyMemAllocatorEx *>(ctx);
  void *ptr = alloc->malloc(alloc->ctx, size);
  if (ptr && scope.is_top_level()) {
    ProfilerLock l(ctx);
    g_profiler->HandleMalloc(ptr, size);
  }
  return ptr;
}

static void *WrappedCalloc(void *ctx, size_t nelem, size_t elsize) {
  ReentrantScope scope;
  PyMemAllocatorEx *alloc = reinterpret_cast<PyMemAllocatorEx *>(ctx);
  void *ptr = alloc->calloc(alloc->ctx, nelem, elsize);
  if (ptr && scope.is_top_level()) {
    ProfilerLock l(ctx);
    g_profiler->HandleMalloc(ptr, nelem * elsize);
  }
  return ptr;
}

static void *WrappedRealloc(void *ctx, void *ptr, size_t new_size) {
  ReentrantScope scope;
  PyMemAllocatorEx *alloc = reinterpret_cast<PyMemAllocatorEx *>(ctx);
  void *ptr2 = alloc->realloc(alloc->ctx, ptr, new_size);
  if (ptr2 && scope.is_top_level()) {
    ProfilerLock l(ctx);
    g_profiler->HandleRealloc(ptr, ptr2, new_size);
  }
  return ptr2;
}

static void WrappedFree(void *ctx, void *ptr) {
  ReentrantScope scope;
  PyMemAllocatorEx *alloc = reinterpret_cast<PyMemAllocatorEx *>(ctx);
  alloc->free(alloc->ctx, ptr);
  if (scope.is_top_level()) {
    ProfilerLock l(ctx);
    g_profiler->HandleFree(ptr);
  }
}

/* Our API */

void AttachProfiler(AbstractProfiler *profiler) {
  g_profiler.reset(profiler);

  PyMemAllocatorEx alloc;
  alloc.malloc = WrappedMalloc;
  alloc.calloc = WrappedCalloc;
  alloc.realloc = WrappedRealloc;
  alloc.free = WrappedFree;

  // Grab the base allocators
  PyMem_GetAllocator(PYMEM_DOMAIN_RAW, &g_base_allocators.raw);
  PyMem_GetAllocator(PYMEM_DOMAIN_MEM, &g_base_allocators.mem);
  PyMem_GetAllocator(PYMEM_DOMAIN_OBJ, &g_base_allocators.obj);

  // And repoint allocation at our wrapped methods!
  alloc.ctx = &g_base_allocators.raw;
  PyMem_SetAllocator(PYMEM_DOMAIN_RAW, &alloc);

  alloc.ctx = &g_base_allocators.mem;
  PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &alloc);

  alloc.ctx = &g_base_allocators.obj;
  PyMem_SetAllocator(PYMEM_DOMAIN_OBJ, &alloc);
}

void DetachProfiler() {
  if (IsProfilerAttached()) {
    PyMem_SetAllocator(PYMEM_DOMAIN_RAW, &g_base_allocators.raw);
    PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &g_base_allocators.mem);
    PyMem_SetAllocator(PYMEM_DOMAIN_OBJ, &g_base_allocators.obj);

    g_profiler.reset(nullptr);
  }
}

bool IsProfilerAttached() { return (g_profiler != nullptr); }

bool MallocPatchInit() {
  ProfilerLock::ModuleInit();
  return true;
}
