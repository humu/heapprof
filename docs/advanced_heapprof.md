# Advanced heapprof

As you use heapprof more, you'll want to understand the corner cases of memory allocation better.
Here are some general advanced tips worth knowing:

* The performance overhead of heapprof hasn't yet been measured. From a rough eyeball estimate, it
    seems to be significant during the initial import of modules (because those generate so many
    distinct stack traces) but fairly low (similar to cProfile) during code execution. This will
    need to be measured and performance presumably tuned.
* The .hpx file format is optimized around minimizing overhead at runtime. The idea is that the
    profiler continuously writes to the two open file descriptors, and relies on the kernel's
    buffering in the file system implementation to minimize that impact; to use that buffering most
    effectively, it's important to minimize the size of data written, so that flushes are rare. This
    is why the wire encoding (cf file_format.*) tends towards things like varints, which use a bit
    more CPU but reduce bytes on the wire. This also helps keep the sizes of the generated files
    under control.
* The profiler very deliberately uses C++ native types, not Python data types, for its internal
    operations. This has two advantages: pure C++ types are faster and more compact, (because of
    the simpler memory management model), and they eliminate the risk of weird recursions if the
    heap profiler were to try to call any of the Python allocators. NB, however, that this means
    that the heap profiler does not include its own memory allocation in its output!
* More generally, the heap profiler only profiles calls to the Python memory allocators; C/C++
    modules which allocate memory separately from that are not counted. This can lead to
    discrepancies between the output of heapprof and total system usage.
* Furthermore, all real malloc() implementations generally allocate more bytes than requested under
    the hood (e.g., to guarantee memory alignment of the result; see e.g.
    [this function](https://github.com/gperftools/gperftools/blob/master/src/common.cc#L77) in
    tcmalloc). Unfortunately, there is no implementation-independent way to find out how many bytes
    were actually allocated, either from the underlying C/C++ allocators or from the higher-level
    Python allocators. This means that the heap measured by heapprof will be the "logical" heap
    size, which is strictly less than the heap size requested by the process from the kernel.
    However, it is that latter size which is monitored by external systems such as the out-of-memory
    (OOM) process killers in sandbox environments.

## Controlling Sampling

The sampling rate controls the probability with which heap events are written. Too high a sampling
rate, and the overhead of writing the data will stop your app, or the amount of data written will
overload your disk; too low a sampling rate, and you won't get a clear picture of events.

heapprof defines sampling rates as a `Dict[int, float]`, which maps the upper range of byte sizes to
sampling probabilities. For example, the default sampling rate is `{128: 1e-4, 8192: 0.1}`. This
means that allocations from 1-127 bytes get sampled at 1 in 10,000; allocations from 128-8191 bytes
get sampled at 1 in 10; and allocations of 8192 bytes or more are always written, without sampling.
These values have proven useful for some programs, but they probably aren't right for everything.

As heapprof is in its early days, its tools for picking sampling rates are somewhat manual. The best
way to do this is to run heapprof in "stats gathering" mode: you can do this either with

`python -m heapprof --mode stats -- mycommand.py args ...`

or programmatically by calling `heapprof.gatherStats()` instead of `heapprof.start(filename)`. In
this mode, rather than generating .hpx files, it will build up a distribution of allocation sizes,
and print it to stderr at profiling stop. The result will look something like this:

```
-------------------------------------------
HEAP USAGE SUMMARY
               Size    Count      Bytes
              1 - 1   138553       6646
              2 - 2    30462      60924
              3 - 4     3766      14076
              5 - 8   794441    5293169
             9 - 16  1553664   23614125
            17 - 32 17465509  509454895
            33 - 64 27282873 1445865086
           65 - 128  9489792  801787796
          129 - 256  3506871  567321439
          257 - 512   436393  143560935
         513 - 1024   347668  257207137
        1025 - 2048   410159  466041685
        2049 - 4096   135294  348213256
        4097 - 8192   194711 1026937305
       8193 - 16384    27027  278236057
      16385 - 32768     8910  183592671
      32769 - 65536     4409  200267665
     65537 - 131072     2699  228614855
    131073 - 262144     1478  277347497
    262145 - 524288     1093  306727390
   524289 - 1048576      104   75269351
  1048577 - 2097152       58   83804159
  2097153 - 4194304       37  106320012
  4194305 - 8388608        8   44335352
 8388609 - 16777216        6   69695438
16777217 - 33554432        3   55391152
```

This tells us that there was a huge number of allocations of 256 bytes or less, which means that we
can use a small sampling rate and still get good data, perhaps 1e-5. There seems to be a spike in
memory usage in the 4096-8192 byte range, and generally the 256-8192 byte range has a few hundred
thousand allocations, so we could sample it at a rate of 0.1 or 0.01. Beyond that, the counts drop
off radically, and so sampling would be a bad idea. This suggests a sampling rate of
`{256: 1e-5, 8192: 0.1}` for this program. You can set this by running

`python -m heapprof -o <filename> --sample '{256:1e-5, 8192:0.1} -- mycommand.py args...`

or

`heapprof.start('filename', {256: 1e-5, 8192: 0.1})`

Some tips for choosing a good sampling rate:

* The most expensive part of logging isn't writing the events, it's writing the stack traces.
    Generally, very small allocations happen at a huge variety of stack traces (nearly every time
    you instantiate a Python variable!), but larger ones are far less common. This means that it's
    usually very important to keep the sampling rate low for very small byte sizes -- say, no more
    than 1e-4 below 64 bytes, and preferably up to 128 bytes -- but much less important to keep it
    low for larger byte sizes.
* The only reason you want to keep the sampling rate low is for performance; if at any point you can
    get away with a bigger sampling rate, err on that side.
