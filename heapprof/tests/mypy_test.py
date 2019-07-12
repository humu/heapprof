import os
import re
import sys
import unittest
from typing import Callable, Iterator, Optional, Set

import mypy.main

# TODO(zunger): There is probably a better way to run mypy as part of setuptools test, but I haven't
# yet figured it out.
# Here, we dynamically build a test case ("MyPyTest") which has one test in it per .py file in the
# repository, and each of those test cases runs mypy on that file. By doing this slightly complex
# thing, we get much cleaner errors if any file fails.

_REPOSITORY_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
_MYPY_CONFIG = os.path.join(_REPOSITORY_ROOT, 'mypy.ini')


def findPyFiles(
    rootdir: Optional[str] = None, seenPaths: Optional[Set[str]] = None
) -> Iterator[str]:
    rootdir = rootdir or _REPOSITORY_ROOT
    seenPaths = seenPaths or set()
    seenPaths.add(rootdir)

    for dirEntry in os.scandir(rootdir):
        if dirEntry.is_file() and dirEntry.name.endswith('.py'):
            yield dirEntry.path
        elif (
            dirEntry.is_dir()
            and not dirEntry.name.startswith('.')
            and dirEntry.path not in seenPaths
        ):
            yield from findPyFiles(dirEntry.path, seenPaths)


def toTestName(pathname: str) -> str:
    filename = os.path.relpath(pathname, _REPOSITORY_ROOT)[:-3]
    return 'testMyPy_' + re.sub('[^a-zA-Z0-9_]', '_', filename)


def makeTestMethod(pyFile: str) -> Callable:
    def test(self) -> None:
        try:
            mypy.main.main(
                None, sys.stdout, sys.stderr, args=[pyFile, '--config-file', _MYPY_CONFIG]
            )
        except SystemExit as e:
            self.assertEqual(0, e.code)

    return test


class MyPyTest(unittest.TestCase):
    # The only test functions are the ones we add dynamically
    pass


for pyFile in findPyFiles():
    setattr(MyPyTest, toTestName(pyFile), makeTestMethod(pyFile))


if __name__ == '__main__':
    unittest.main()
