from os import path

from setuptools import Extension, find_packages, setup

with open(path.join(path.abspath(path.dirname(__file__)), 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

cppmodule = Extension(
    '_heapprof',
    sources=[
        '_heapprof/abstract_profiler.cc',
        '_heapprof/file_format.cc',
        '_heapprof/heapprof.cc',
        '_heapprof/malloc_patch.cc',
        '_heapprof/profiler.cc',
        '_heapprof/reentrant_scope.cc',
        '_heapprof/sampler.cc',
        '_heapprof/stats_gatherer.cc',
        '_heapprof/util.cc',
    ],
    include_dirs=['.'],
    define_macros=[('PY_SSIZE_T_CLEAN', None)],
    extra_compile_args=['-std=c++11'],
)

setup(
    # About this project
    name='heapprof',
    version='1.0.0a1',
    description='Logging heap profiler',
    long_description=long_description,
    keywords='development profiling memory',
    author='Yonatan Zunger',
    author_email='zunger@humu.com',
    license='MIT',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: MIT License',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: Implementation :: CPython',
    ],
    project_urls={
        'Source': 'https://github.com/humu-com/heapprof',
        'Tracker': 'https://github.com/humu-com/heapprof/issues',
    },

    # The actual contents
    ext_modules=[cppmodule],
    install_requires=[],
    packages=find_packages(exclude=['tests']),
    # NB: This has API requirements that only run on 3.7 and above. It's probably possible to make a
    # version of this run on 3.4 or above if anyone really wants to.
    python_requires='>=3.7',

    # Testing
    test_suite='nose.collector',
    tests_require=['nose', 'mypy'],
)
