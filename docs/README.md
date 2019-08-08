# heapprof: A Logging Heap Profiler

[![Python 3.7](https://img.shields.io/badge/python-3.7-blue.svg)](https://www.python.org/downloads/release/python-374/) 
[![CircleCI](https://circleci.com/gh/humu/heapprof/tree/master.svg?style=svg&circle-token=1557bfcabda0155d6505a45e3f00d4a71a005565)](https://circleci.com/gh/humu/heapprof/tree/master)
[![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-v1.4%20adopted-ff69b4.svg)](code-of-conduct.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

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

---

* [Quickstart](#heapprof-quickstart)
* [Using heapprof](using_heapprof.md)
  * [Installation and system requirements](using_heapprof.md#installation-and-system-requirements)
  * [Running your code](using_heapprof.md#running-your-code)
  * [Making a digest](using_heapprof.md#making-a-digest)
* [Visualizing and interpreting results](visualizing_results.md)
  * [Time plots](visualizing_results.md#time-plots)
  * [Flow graphs](visualizing_results.md#flow-graphs)
  * [Flame graphs](visualizing_results.md#flame-graphs)
  * [API access to data](visualizing_results.md#api-access-to-data)
* [Advanced heapprof](advanced_heapprof.md)
  * [Controlling sampling](advanced_heapprof.md#controlling-sampling)
* [API reference](autodoc/_build/html/index.html)
* [Contributing](contributing.md)
  * [The code of conduct](../CODE_OF_CONDUCT.md)
  * [The MIT license](../LICENSE)

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

You can analyze hpx files with the analysis and visualization tools built in to heapprof, or use its
APIs to dive deeper into your program's memory usage yourself. For example, you might do this with
the built-in visualization tools:

```
import heapprof
r = heapprof.read('filename')

# Generate a plot of total memory usage over time. This command requires that you first pip install
# matplotlib.
r.timePlot().pyplot()

# Looks like something interested happened 300 seconds in. You can look at the output as a Flame
# graph and view it in a tool like speedscope.app.
r.writeFlameGraph('flame-300.txt', 300)

# Or you can look at the output as a Flow graph and view it using graphviz. (See graphviz.org)
r.flowGraphAt(300).asDotFile('300.dot')

# Maybe you'd like to compare three times and see how memory changed. This produces a multi-time
# Flow graph.
r.compare('compare.dot', r.flowGraphAt(240), r.flowGraphAt(300), r.flowGraphAt(500))

# Or maybe you found some lines of code where memory use seemed to shift interestingly.
r.timePlot({
  'read_data': '/home/wombat/myproject/io.py:361',
  'write_buffer': '/home/wombat/myproject/io.py:582',
})
```

One thing you'll notice in the above is that visualization tools require you to install extra
packages -- that's a way to keep heapprof's dependencies down.

To learn more, continue on to [Using heapprof](using_heapprof.md)
