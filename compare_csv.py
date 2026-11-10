"""Decide which changed CSVs differ from their committed copies only by floating-point noise.

A file passes when it has the same lines as the committed copy, each line identical once
its numbers are blanked, and every number within RTOL relative or ATOL absolute of the
committed one. Linux and macOS round the last bits of a double differently, so a pipeline
that reproduces exactly on the Mac that committed it moves the twelfth significant digit
on the runner; no published number is printed to anything like that precision.

Usage, from a paper repository's root:
  python3 compare_csv.py <file> [<file> ...]
Prints the files that are only noise, one per line, and explains the rest on stderr.
"""

import re
import subprocess
import sys

RTOL = 1e-6
ATOL = 1e-6
NUMBER = re.compile(r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def explain(path, reason):
    print(f"{path}: {reason}", file=sys.stderr)
    return False


def only_noise(path):
    committed = subprocess.run(["git", "show", f"HEAD:{path}"], capture_output=True, text=True)
    if committed.returncode != 0:
        return explain(path, "not in the committed tree")
    old_lines = committed.stdout.splitlines()
    with open(path) as f:
        new_lines = f.read().splitlines()
    if len(old_lines) != len(new_lines):
        return explain(path, f"{len(old_lines)} committed lines, {len(new_lines)} now")
    for i, (old, new) in enumerate(zip(old_lines, new_lines), start=1):
        if old == new:
            continue
        if NUMBER.sub("#", old) != NUMBER.sub("#", new):
            return explain(path, f"line {i} differs in more than its numbers")
        for a, b in zip(NUMBER.findall(old), NUMBER.findall(new)):
            a, b = float(a), float(b)
            if abs(a - b) > ATOL + RTOL * max(abs(a), abs(b)):
                return explain(path, f"line {i}: {a!r} is now {b!r}")
    return True


for path in sys.argv[1:]:
    if only_noise(path):
        print(path)
