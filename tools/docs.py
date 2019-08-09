import copy
import logging
import os
import shutil
import subprocess
import sys
from typing import List

from _common import REPO_ROOT


def findCommand(commandName: str) -> bool:
    return subprocess.run(f'which {commandName}', shell=True).returncode == 0


def ensureRequirements() -> bool:
    # Ensure that everything required is installed.
    logging.info('Checking requirements')
    try:
        import sphinx  # noqa
        import recommonmark  # noqa
    except ImportError:
        reqsFile = os.path.abspath(os.path.join(REPO_ROOT, 'tools/requirements.txt'))
        relPath = os.path.relpath(os.getcwd(), reqsFile)
        logging.error(f'Required PIP packages are missing. Please run `pip install -r {relPath}')
        return False

    if not findCommand('make'):
        logging.error(
            'make is not installed on your machine! Please ensure you have a working '
            'development environment with all the standard tools.'
        )
        return False

    return True


def clearOldSite() -> None:
    logging.info('Clearing old site images')
    shutil.rmtree(os.path.join(REPO_ROOT, 'docs/build'), ignore_errors=True)
    shutil.rmtree(os.path.join(REPO_ROOT, '_site'), ignore_errors=True)


def rebuildSphinx() -> None:
    # Rebuilds docs/build from docs/. The master config for this is in docs/conf.py and
    # docs/Makefile.
    logging.info('Recompiling HTML from Sphinx')
    # Important trick: Make sure that even if the heapprof package is pip installed, we *don't* use
    # it: instead, 'import heapprof' should pull in REPO_ROOT/heapprof, so that you build from the
    # current client, not from the last time you ran 'python setup.py install' or the like.
    pythonPath: List[str] = []
    for pathEntry in sys.path:
        if 'site-packages/heapprof' not in pathEntry:
            pythonPath.append(pathEntry)
    pythonPath.append(REPO_ROOT)

    env = copy.copy(os.environ)
    env['PYTHONPATH'] = ':'.join(pythonPath)

    subprocess.run(
        'make html', cwd=os.path.join(REPO_ROOT, 'docs'), shell=True, check=True, env=env
    )


def main():
    logging.getLogger().addHandler(logging.StreamHandler())
    logging.getLogger().setLevel(logging.INFO)

    if not ensureRequirements():
        return

    clearOldSite()
    rebuildSphinx()


if __name__ == '__main__':
    main()
