# Release instructions

This document is for heapprof maintainers only. It assumes that the release is being cut from an OS
X machine, since there's no good way to remotely build those wheels yet. To cut a new release:

1. Check in a changelist which increments the version number in setup.py and updates
   RELEASE_NOTES.md. The version number should follow the [semantic
   versioning](https://packaging.python.org/guides/distributing-packages-using-setuptools/#semantic-versioning-preferred)
   scheme.
1. Clean the local image by running `git clean -xfd`
1. Build the source wheel by running `python setup.py sdist`
1. Build the OS X wheel by running `python setup.py bdist_wheel`
1. Go to `https://circleci.com/gh/humu/heapprof/tree/master` and click on the links for the
   most recent `linux_x86_64` and `windows_64` jobs. For each of them, click on the "Artifacts" tab
   and download the corresponding wheels. Move them to your `dist` directory along with the wheels
   created in the previous step.
1. Run `twine upload dist/*` to push the new repository version.
1. Go to `https://pypi.org/project/heapprof/` and verify that the new version is live.
