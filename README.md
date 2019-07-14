[![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-v1.4%20adopted-ff69b4.svg)](code-of-conduct.md)

# heapprof: A Logging Heap Profiler

heapprof is a logging, sampling heap profiler for Python 3.7+.

* "Logging" means that as the program runs, it steadily generates a log of memory allocation and
    release events. This means that you can easily look at memory usage as a function of time.
* "Sampling" means that it can record only a statistically random sample of memory events. This
    improves performance dramatically while writing logs, and (with the right parameters) sacrifices
    almost no accuracy.

heapprof is complementary to [tracemalloc](https://docs.python.org/3/library/tracemalloc.html),
which is a snapshotting heap profiler. The difference is that tracemalloc keeps track of live memory
internally, and only writes snapshots when its snapshot() function is called; this means it has
slightly lower overhead, but you have to know the moments at which you'll want a snapshot before the
program starts. This makes it particularly useful for finding leaks (from the snapshot at program
exit), but not as good for understanding events like memory spikes.

## heapprof quickstart

You can install heapprof by running

`pip install heapprof`

The simplest way to get a heap profile for your program is to run

`python -m heapprof -o <filename> -- mycommand.py args...`

This will run your command and write the output to the files `<filename>.hpm` and `<filename>.hpd`.
(Collectively, the "hpx files") Alternatively, you can control heapprof programmatically:

```
import heapprof

heapprof.start('filename')
... do something ...
heapprof.stop()
```

Several tools are provided to read and analyze .hpx files.

* The `HeapProfile` class is the base .hpx reader; it lets you access the sequence of heap events
    and the corresponding stack traces.
* The `HeapHistory` class helps you look at the time-evolution of the heap. Its outputs can easily
    be visualized with libraries like matplotlib.
* The `TimeSnapshot` class lets you look at the detailed state of the world at any given time. Its
    outputs can be analyzed in depth with a range of visualization tools.

For example:

```
import heapprof

profile = heapprof.HeapProfile('filename')
# Get a history at 60-second resolution
hist = heapprof.HeapHistory.make(profile, timeGranularity=60)

# Plot this history. This logic isn't included as part of heapprof because including matplotlib
# would create a huge dependency bloat for little value.
a = hist.asArrays(1 << 30)  # 1GB scale on the y-axis
import matplotlib.pyplot as plt
plt.subplots().stackplot(a[0], *a[1])
plt.show()

# Now you look at the history and realize that something seems interesting at t=560 seconds.
# This command builds a snapshot at that time, and writes it in "collapsed stack" format to
# flame-560.txt. You can then explore it in detail using tools like speedscope.app.
heapprof.TimeSnapshot.atTime(profile, 560).writeCollapsedStack('flame-560.txt')
```

## Advanced options: managing the sampling rate

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

## Further technical notes

Of interest primarily if you need to understand the internals of heapprof or details of its
behavior:

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
* The profiler very deliberately does not use Python data types for its internal operations. This
    has two advantages: pure C++ types are faster and more compact, (because of the simpler memory
    management model), and they eliminate the risk of weird recursions if the heap profiler were to
    try to call any of the Python allocators. NB, however, that this means that the heap profiler
    does not include its own memory allocation in its output!
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

## Contributing to heapprof

heapprof is an open source project distributed under the [MIT License](LICENSE). Discussions,
questions, and feature requests should be done via the
[GitHub issues page](https://github.com/humu-com/heapprof/issues).

Pull requests for bugfixes and features are welcome! Generally, you should discuss features or API
changes on the tracking issue first, to make sure everyone is aligned on direction. Python code
should follow PEP8+[Black](https://github.com/python/black) formatting, while C/C++ code should
follow the [Google C++ Style Guide](https://google.github.io/styleguide/cppguide.html). Code should
be unittested and tests should be invoked by `setup.py test`.

Most importantly, heapprof is released with a [Contributor Code of Conduct](CODE_OF_CONDUCT.md). By
participating in this product, you agree to abide by its terms. This code also governs behavior on
the mailing list. We take this very seriously, and will enforce it gleefully.

### Desiderata

Some known future features that we'll probably want:

* Replace the "top N stack traces" feature of HeapHistory with something more informative.
* Provide additional file formats of output to work with other kinds of visualization, especially
    graph visualizations similar to those created by pprof.
* Provide a nicer user flow for analyzing data.
* Measure and tune system performance.
* Make the process of picking sampling rates less manual.
