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

You can read all the documentation [here](docs/README.md)
