import os
import shutil
import subprocess

from _common import REPO_ROOT


"""Tool to rebuild docs/autodoc from scratch. Run this whenever you've changed any interfaces.
"""


def main():
    # Clean up the old stuff
    shutil.rmtree(os.path.join(REPO_ROOT, 'docs/autodoc/_build'), ignore_errors=True)
    try:
        os.remove(os.path.join(REPO_ROOT, 'docs/autodoc/heapprof.rst'))
    except FileNotFoundError:
        pass
    try:
        os.remove(os.path.join(REPO_ROOT, 'docs/autodoc/modules.rst'))
    except FileNotFoundError:
        pass

    if subprocess.run(
        'sphinx-apidoc -f -M -o docs/autodoc/ heapprof heapprof/tests', cwd=REPO_ROOT, shell=True
    ).returncode:
        print('sphinx-apidoc failed')
        return

    if subprocess.run(
        'make html', cwd=os.path.join(REPO_ROOT, 'docs/autodoc'), shell=True
    ).returncode:
        print('make sphinx output failed')
        return

    print('Docs rebuilt')


if __name__ == '__main__':
    main()
