[![Python 3.7](https://img.shields.io/badge/python-3.7-blue.svg)](https://www.python.org/downloads/release/python-374/)
[![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-v1.4%20adopted-ff69b4.svg)](https://humu.github.io/heapprof/code_of_conduct.html)
[![MIT License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://humu.github.io/heapprof/license.html)
[![CircleCI](https://circleci.com/gh/humu/heapprof/tree/master.svg?style=svg&circle-token=1557bfcabda0155d6505a45e3f00d4a71a005565)](https://circleci.com/gh/humu/heapprof/tree/master)

# heapprof: A Logging Heap Profiler

heapprof is a logging, sampling heap profiler for Python 3.7+.

* "Logging" means that as the program runs, it steadily generates a log of memory allocation and
    release events. This means that you can easily look at memory usage as a function of time.
* "Sampling" means that it can record only a statistically random sample of memory events. This
    improves performance dramatically while writing logs, and (with the right parameters) sacrifices
    almost no accuracy.

It comes with a suite of visualization and analysis tools (including time plots, flame graphs, and
flow graphs), as well as an API for doing your own analyses of the results.

[![screenshot of split time plot](https://humu.github.io/heapprof/_images/split_time_plot.png)](https://humu.github.io/heapprof/visualizing_results.html)

heapprof is complementary to [tracemalloc](https://docs.python.org/3/library/tracemalloc.html),
which is a snapshotting heap profiler. The difference is that tracemalloc keeps track of live memory
internally, and only writes snapshots when its snapshot() function is called; this means it has
slightly lower overhead, but you have to know the moments at which you'll want a snapshot before the
program starts. This makes it particularly useful for finding leaks (from the snapshot at program
exit), but not as good for understanding events like memory spikes.

You can install heapprof with `pip install heapprof`. heapprof is released under the
[MIT License](https://humu.github.io/heapprof/license.html).

You can read all the documentation at [humu.github.io/heapprof](https://humu.github.io/heapprof).

## Navigating the Repository

If you're trying to find something in the GitHub repository, here's a brief directory (since, like
most Python packages, this is a maze of twisty subdirectories, all different):

* `heapprof` contains the Python package itself. (The API and visualization logic)
* `_heapprof` contains the C/C++ package. (The core profiling logic)
* `docs_src` contains the sources for the documentation, mostly as `.md` and `.rst` files.
* `docs` contains the compiled HTML version of `docs_src`, created with `tools/docs.py` and checked
    in.
* `tools` contains tools useful when modifying heapprof itself.
* And then there are the configuration files for all the tools:
    * `setup.py` is the master build configuration for the PIP package.
    * `.flake8` and `.pylintrc` are the configuration for Python linting.
    * `CPPLINT.cfg` is the configuration for C/C++ linting.
    * `mypy.ini` is the configuration for Python type checking.
    * `Gemfile` is for setting up Jekyll for documentation hosting.
    * `_config.yml` is the configuration for Jekyll serving.
    * `docs/Makefile` and `docs/conf.py` are the configuration for building the HTML docs image via
        Sphinx.
    * `.circleci` is the configuration for continuous integration testing.
    * `pyproject.toml` and the root `requirements.txt` make `setuptools` happy.
* Additional directories which are .gitignored but which show up during use:
    * `build` contains C/C++ dependencies and their compiled images; it's managed by `setup.py`.
    * `_site` contains the final Jekyll site which is served for documentation; it's created if you
        run `bundle exec jekyll serve` to run the docs web server locally.
