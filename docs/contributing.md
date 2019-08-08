[![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-v1.4%20adopted-ff69b4.svg)](code_of_conduct.md)

# Contributing to heapprof

heapprof is an open source project distributed under the [MIT License](license.md). Discussions,
questions, and feature requests should be done via the
[GitHub issues page](https://github.com/humu-com/heapprof/issues).

Pull requests for bugfixes and features are welcome!

* Generally, you should discuss features or API changes on the tracking issue first, to make sure
  everyone is aligned on direction.
* Lint and style:
  - Python code should follow PEP8+[Black](https://github.com/python/black)
  formatting, and should pass mypy with strict type checking.
  - C/C++ code should follow the
    [Google C++ Style Guide](https://google.github.io/styleguide/cppguide.html).
  - You can check a client against the same lint checks run by the continuous integration test by
    running `python tools/lint.py`; if you add `--fix`, it will try to fix any errors it can
    in-place.
* Unittests are highly desired and should be invocable by `setup.py test`.
* Documentation: Any changes should be reflected in the documentation! Remember:
  - All Python modules should have clear docstrings for all public methods and variables. Classes
      should be organized with the interface first, and implementation details later.
  - If you're adding any new top-level modules, add corresponding .rst files in `docs/api` and link
      to them from `docs/api/index.rst`.
  - Any other changes should be reflected in the documentation in `docs`.
  - After changing the documentation, you can rebuild the HTML by running `python tools/docs.py`.
  - If you want to see how the documentation looks before pushing, install
      [Jekyll](https://jekyllrb.com/docs/installation/) locally, then from the root directory of
      this repository, run `bundle exec jekyll serve`. This will serve the same images that will be
      served in production on `localhost:4000`.

## Code of Conduct

Most importantly, heapprof is released with a [Contributor Code of Conduct](code_of_conduct.md). By
participating in this product, you agree to abide by its terms. This code also governs behavior on
the mailing list. We take this very seriously, and will enforce it gleefully.

## Desiderata

Some known future features that we'll probably want:

* Provide additional file formats of output to work with other kinds of visualization.
* Measure and tune system performance.
* Make the process of picking sampling rates less manual.
