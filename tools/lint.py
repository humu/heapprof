import argparse
import os
import subprocess
import sys
from typing import List, Optional, Set

from _common import REPO_ROOT

EXCLUDE_NAMES = {'build', 'dist'}


def addFileToList(filename: str, pyFiles: List[str], cppFiles: List[str]) -> None:
    parts = os.path.basename(filename).rsplit('.', 1)
    if len(parts) < 2:
        return

    suffix = parts[-1]
    if suffix == 'py':
        pyFiles.append(filename)
    elif suffix in ('c', 'cpp', 'cc', 'h', 'hpp'):
        cppFiles.append(filename)


def findFiles(
    rootDir: str,
    pyFiles: List[str],
    cppFiles: List[str],
    seenDirs: Optional[Set[str]] = None,
) -> None:
    """Find all Python and C++ files for us to lint."""
    seenDirs = seenDirs or set()
    rootDir = os.path.abspath(rootDir)
    seenDirs.add(rootDir)

    for dirEntry in os.scandir(rootDir):
        if dirEntry.name in EXCLUDE_NAMES or dirEntry.name.startswith('.'):
            continue

        if dirEntry.is_dir() and dirEntry.path not in seenDirs:
            findFiles(dirEntry.path, pyFiles, cppFiles, seenDirs)
        elif dirEntry.is_file():
            addFileToList(dirEntry.path, pyFiles, cppFiles)


def runCommand(*command: str) -> bool:
    pythonPath = ','.join(sys.path)
    try:
        subprocess.check_call([f'PYTHONPATH="{pythonPath}"', *command], cwd=REPO_ROOT, shell=True)
        return True
    except subprocess.CalledProcessError:
        return False


def lintPyFiles(files: List[str]) -> bool:
    if not files:
        return True

    ok = True
    if not runCommand('python', '-m', 'flake8', *files):
        ok = False
    if not runCommand('python', '-m', 'isort', '--atomic', '--check-only', *files):
        ok = False
    if not runCommand('python', '-m', 'black', '--check', *files):
        ok = False
    if not runCommand('python', '-m', 'mypy', *files):
        ok = False

    print(f'Lint of {len(files)} Python files {"successful" if ok else "failed"}!')
    return ok


def fixPyFiles(files: List[str]) -> None:
    if not files:
        return

    runCommand('python', '-m', 'isort', '--atomic', *files)
    runCommand('python', '-m', 'black', *files)


def lintCppFiles(files: List[str]) -> bool:
    if not files:
        return True

    ok = runCommand('python', '-m', 'cpplint', '--quiet', *files)
    print(f'Lint of {len(files)} C/C++ files {"successful" if ok else "failed"}!')
    return ok


def fixCppFiles(files: List[str]) -> None:
    if not files:
        return

    return runCommand('clang-format', '-i', '-style=Google', *files)


if __name__ == '__main__':
    parser = argparse.ArgumentParser('linter')
    parser.add_argument('--fix', action='store_true', help='Fix files in-place')
    parser.add_argument('files', nargs='*', help='Files to lint; default all')
    args = parser.parse_args()

    pyFiles: List[str] = []
    cppFiles: List[str] = []
    if args.files:
        for file in args.files:
            addFileToList(file, pyFiles, cppFiles)
    else:
        findFiles(REPO_ROOT, pyFiles, cppFiles)

    # If there was a fix request, run that first.
    if args.fix:
        fixPyFiles(pyFiles)
        fixCppFiles(cppFiles)

    ok = lintPyFiles(pyFiles)
    if not lintCppFiles(cppFiles):
        ok = False

    if not ok:
        sys.exit(1)
