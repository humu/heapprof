import argparse
import ast
import os
import sys
from typing import Dict, Optional, cast

import heapprof

parser = argparse.ArgumentParser("heapprof")
parser.add_argument(
    "-m",
    "--mode",
    choices=("profile", "stats"),
    help="Profiler mode selection",
    default="profile",
)
parser.add_argument("-o", "--output", help="Output file base", default="hprof")
parser.add_argument("--sample", help="Sampling rate dictionary")
parser.add_argument("command", nargs="+")
args = parser.parse_args()

sampleRate: Optional[Dict[int, float]] = None
if args.sample:
    parsed = ast.literal_eval(args.sample)
    assert isinstance(parsed, dict)
    sampleRate = cast(Dict[int, float], parsed)

progname = args.command[0]
sys.path.insert(0, os.path.dirname(progname))
sys.argv[:] = args.command
print(f'Heap profiler: Running {" ".join(sys.argv)}')
with open(progname, "rb") as fp:
    code = compile(fp.read(), progname, "exec")
globs = {
    "__file__": progname,
    "__name__": "__main__",
    "__package__": None,
    "__cached__": None,
}

if args.mode == "profile":
    heapprof.start(args.output, sampleRate)
elif args.mode == "stats":
    heapprof.gatherStats()
else:
    raise ValueError("Unknown mode [{args.mode}]")

try:
    exec(code, globs, None)
finally:
    heapprof.stop()
