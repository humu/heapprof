heapprof: A Logging Heap Profiler
=================================

.. image:: https://img.shields.io/badge/python-3.7-blue.svg
   :target: https://www.python.org/downloads/release/python-374/
.. image:: https://img.shields.io/badge/Contributor%20Covenant-v1.4%20adopted-ff69b4.svg
   :target: code_of_conduct.html
.. image:: https://img.shields.io/badge/License-MIT-yellow.svg
   :target: license.html
.. image:: https://circleci.com/gh/humu/heapprof/tree/master.svg?style=svg&circle-token=1557bfcabda0155d6505a45e3f00d4a71a005565
   :target: https://circleci.com/gh/humu/heapprof/tree/master

heapprof is a logging, sampling heap profiler for Python 3.7+.

* "Logging" means that as the program runs, it steadily generates a log of memory allocation and
  release events. This means that you can easily look at memory usage as a function of time.
* "Sampling" means that it can record only a statistically random sample of memory events. This
  improves performance dramatically while writing logs, and (with the right parameters) sacrifices
  almost no accuracy.

It comes with a suite of visualization and analysis tools (including time plots, flame graphs, and
flow graphs), as well as an API for doing your own analyses of the results.

heapprof is complementary to `tracemalloc <https://docs.python.org/3/library/tracemalloc.html>`_,
which is a snapshotting heap profiler. The difference is that tracemalloc keeps track of live memory
internally, and only writes snapshots when its snapshot() function is called; this means it has
slightly lower overhead, but you have to know the moments at which you'll want a snapshot before the
program starts. This makes it particularly useful for finding leaks (from the snapshot at program
exit), but not as good for understanding events like memory spikes.

**NOTE:** The 1.0.0 release of heapprof does not include compiled Windows binaries. You will need to
have a compiler and Python build environment installed in order to use this package. This will be
fixed in an upcoming maintenance release.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   quickstart
   using_heapprof
   visualizing_results
   advanced_heapprof
   api/index
   contributing
   license

.. toctree::
   :hidden:

   code_of_conduct
