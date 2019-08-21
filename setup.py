import distutils.spawn
import importlib
import os
import sys
from distutils.command.build_ext import build_ext as _build_ext  # type: ignore
from typing import Optional

from setuptools import Extension, find_packages, setup

with open(
    os.path.join(os.path.abspath(os.path.dirname(__file__)), "README.md"), encoding="utf-8"
) as f:
    long_description = f.read()

WINDOWS = sys.platform in ('win32', 'cygwin')
CMAKE = 'CMake' if WINDOWS else 'cmake'
EGGS_DIR = './.eggs'


def findEgg(prefix: str) -> str:
    """Find an egg whose name begins with the given string. Raises if this egg does not exist or is
    not unique.
    """
    found: Optional[str] = None
    for dirEntry in os.scandir(EGGS_DIR):
        if dirEntry.is_dir() and dirEntry.name.startswith(prefix):
            if found is not None:
                raise ValueError(
                    f'Found multiple eggs beginning with "{prefix}": {found} and '
                    f'{dirEntry.name}'
                )
            found = dirEntry.name
    if found is None:
        raise ValueError(f'Found no egg beginning with "{prefix}"')
    return os.path.join(EGGS_DIR, found)


def findCMake() -> str:
    # If cmake is already installed and available, we're good.
    if distutils.spawn.find_executable(CMAKE):
        return CMAKE

    # If cmake was only present because it's in setup_requires, that means that the egg is
    # downloaded, but the binary is hidden inside! Get its path.
    sys.path.append(findEgg('cmake-'))
    module = importlib.import_module('cmake')

    # The path of the cmake binary!
    cmake = os.path.join(module.CMAKE_BIN_DIR, CMAKE)
    # Ensure it's executable; this isn't always true in the wheel.
    os.chmod(cmake, 0o777)
    return cmake


# Our C++ library depends on ABSL. This insane monkey-patch is the simplest way I can figure out to
# actually make that dependency happen.
class BuildExtWithABSL(_build_ext):
    def run(self) -> None:
        if not os.path.exists("build/absl"):
            self.mkpath("build/absl")
            self.spawn(["git", "clone", "https://github.com/abseil/abseil-cpp.git", "build/absl"])

        cmake = findCMake()

        pwd = os.getcwd()
        os.chdir("build/absl")
        self.spawn([cmake, "."])
        self.spawn([cmake, "--build", ".", "--target", "base"])
        os.chdir(pwd)

        super().run()


cppmodule = Extension(
    "_heapprof",
    sources=[
        "_heapprof/abstract_profiler.cc",
        "_heapprof/file_format.cc",
        "_heapprof/heapprof.cc",
        "_heapprof/malloc_patch.cc",
        "_heapprof/profiler.cc",
        "_heapprof/reentrant_scope.cc",
        "_heapprof/sampler.cc",
        "_heapprof/stats_gatherer.cc",
        "_heapprof/util.cc",
    ],
    depends=[
        "_heapprof/abstract_profiler.h",
        "_heapprof/file_format.h",
        "_heapprof/malloc_patch.h",
        "_heapprof/port.h",
        "_heapprof/profiler.h",
        "_heapprof/reentrant_scope.h",
        "_heapprof/sampler.h",
        "_heapprof/scoped_object.h",
        "_heapprof/simple_hash.h",
        "_heapprof/stats_gatherer.h",
        "_heapprof/util.h",
    ],
    include_dirs=[os.getcwd(), "build/absl"],
    library_dirs=["build\\absl\\absl\\base\\Debug" if WINDOWS else "build/absl/absl/base"],
    libraries=["absl_base"],
    define_macros=[("PY_SSIZE_T_CLEAN", None)],
    extra_compile_args=["" if WINDOWS else "-std=c++11"],
)

setup(
    # About this project
    name="heapprof",
    version="1.0.1",
    description="Logging heap profiler",
    long_description=long_description,
    long_description_content_type="text/markdown",
    keywords="development profiling memory",
    author="Yonatan Zunger",
    author_email="zunger@humu.com",
    license="MIT",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "License :: OSI Approved :: MIT License",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: Implementation :: CPython",
    ],
    project_urls={
        "Documentation": "https://humu.github.io/heapprof",
        "Source": "https://github.com/humu/heapprof",
        "Tracker": "https://github.com/humu/heapprof/issues",
    },
    # I suppose I should be glad that distutils has a certain amount of monkey-patching ability
    # built-in?
    cmdclass={"build_ext": BuildExtWithABSL},
    # The actual contents
    # NB: This has API requirements that only run on 3.7 and above. It's probably possible to make a
    # version of this run on 3.4 or above if anyone really wants to.
    python_requires=">=3.7",
    ext_modules=[cppmodule],
    packages=find_packages(exclude=["tests", "tools", "docs", "docs_src"]),
    setup_requires=["cmake"],
    # Testing
    test_suite="nose.collector",
    tests_require=["nose"],
)
