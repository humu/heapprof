# Using heapprof

The basic flow of using heapprof is:

1. [Optional] Adjust parameters like the [sampling rate](sampling_rate.md).
1. Run your program with heapprof turned on. This generates .hpm (metadata) and .hpd (data) files.
1. Open the output files with `heapprof.read()` and create a .hpc (digest) file.
1. Analyze the resulting data with visualization tools, or do your own poking with the API.

The reason heapprof needs so many files is that it's doing everything it can to minimize overhead
while your program is running. By writing two files (one with things like stack traces, the other
with the individual events that happen) instead of one, it can minimize how much time is spent on
disk I/O; by deferring the work of combining individual events into easily-understood histories, it
both saves CPU and I/O during runtime, and gives the analysis tools more flexibility via access to
the raw data.

This means that at least the first time you open a set of .hpx files, you'll need to spend some time
processing it; this can range from seconds to minutes, depending on just how much data you've
accumulated.

> **Tip:** Partially-written .hpd and .hpm files are valid; this means you can start running
> analysis while your program is still going, and it shouldn't interfere with either your program or
> with further data collection! Partially-written digest files are also valid; this means that you
> can ctrl-C digest building partway through, and you'll get a perfectly valid digest up to the
> timestamp where you stopped it. You can always replace the digest by calling
> `heapprof.Reader.makeDigest()` again, with new options.

## Installation and system requirements

heapprof is designed to work with Python 3.7 or greater, using the CPython runtime. If you are using
an older version of Python or a less-common runtime, this package won't work, and you'll get strange
errors if you try.

To install heapprof, simply run `pip install heapprof`. Some of heapprof's data visualization
features require additional packages as well:

* For time plots, you will also need [matplotlib](https://matplotlib.org/). In most cases, you can
    install this by simply running `pip install matplotlib`.
* For flow graphs, you will also need [graphviz](https://www.graphviz.org/). graphviz is not a
    Python package; although there are Python packages with similar names that wrap it, all of them
    require that you install the underlying tool. See the graphviz site for how best to get it on
    your platform.
* For flame graphs, you can either use [speedscope.app](https://www.speedscope.app/) as a web
    application (and just send your flame data there), or you can install and run it locally with
    `npm install -g speedscope`. (See its [GitHub site](https://github.com/jlfwong/speedscope) for
    more installation details if you aren't familiar with running local JavaScript code)

## Running your code

heapprof can be invoked either programmatically or from the command line. Programmatically, you call

```
import heapprof

heapprof.start('/some/path/to/output')
... do something ...
heapprof.stop()
```

You don't need to do fancy exception-guarding; if the program exits before heapprof.stop() is
called, it will clean up automatically. The path you provide to `heapprof.start` is known as the
"filebase;" output will be written to filebase.hpd, filebase.hpm, and so on.

If you want to wrap an entire program execution in heapprof, it's even simpler:

```
python -m heapprof -o /output/file -- myprogram.py ...
```

You can pass arguments to your Python code just like you usually would.

## Making a digest

The files output by heapprof directly contain a sequence of events: timestamps and heap locations at
which memory was allocated or freed. Nearly all ways to analyze this rely on instead having a
picture of how memory looked as a function of time. A digest file is simply a precomputed time
history: when it's built, all the events are scanned, and at every given time interval, a `Snapshot`
is written. Each Snapshot is simply a map from stack traces at which memory was allocated, to the
number of live bytes in memory at that instant which were allocated from that location in code.

When you open the output, if a digest doesn't already exist, one is created for you:

```
import heapprof

r = heapprof.read('/output/file')
```

This function returns a `heapprof.Reader`, which is your main interface to all the data. XXX LINK

Once you have a reader and a digest, you can start [visualizing and interpreting the
results](visualizing_results.md).
