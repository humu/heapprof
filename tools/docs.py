import copy
import os
import shutil
import subprocess
import sys
from typing import List

from _common import REPO_ROOT

if __name__ == '__main__':
    shutil.rmtree(os.path.join(REPO_ROOT, 'docs/build'), ignore_errors=True)

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
