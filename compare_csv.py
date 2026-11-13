"""Decide which changed CSVs differ from their committed copies only by floating-point noise.

A file passes when it has the same lines as the committed copy, each line identical once
its numbers are blanked, and every number within RTOL relative or ATOL absolute of the
committed one. Linux and macOS round the last bits of a double differently, so a pipeline
that reproduces exactly on the Mac that committed it moves the twelfth significant digit
on the runner; no published number is printed to anything like that precision. RTOL is
1e-5 rather than 1e-6 because a delta-method SE built from a numerical Jacobian moves at
1e-6 between platforms (coppock_2021's margins() z statistic, 1.28e-6, 2026-11-13).

With --verdicts, a file passes when only its reproduced values have moved: same header,
same rows in the same order, and every column identical except value_script and
value_rewrite. That is for a ground-truth table whose reproduced values depend on
something the runner cannot hold fixed (coppock_2017a's bootstrap, whose converged draws
depend on LAPACK rounding), where the verdicts must still agree.

Usage, from a paper repository's root:
  python3 compare_csv.py [--verdicts] <file> [<file> ...]
Prints the files that pass, one per line, and explains the rest on stderr.
"""

import csv
import io
import re
import subprocess
import sys

RTOL = 1e-5
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


MAY_MOVE = {"value_script", "value_rewrite"}


def only_values_moved(path):
    committed = subprocess.run(["git", "show", f"HEAD:{path}"], capture_output=True, text=True)
    if committed.returncode != 0:
        return explain(path, "not in the committed tree")
    old_rows = list(csv.reader(io.StringIO(committed.stdout)))
    with open(path, newline="") as f:
        new_rows = list(csv.reader(f))
    if not old_rows or old_rows[0] != new_rows[0]:
        return explain(path, "header differs")
    header = old_rows[0]
    if not {"match", "match_rewrite"} & set(header):
        return explain(path, "has no verdict column to hold fixed")
    if len(old_rows) != len(new_rows):
        return explain(path, f"{len(old_rows)} committed rows, {len(new_rows)} now")
    fixed = [j for j, name in enumerate(header) if name not in MAY_MOVE]
    for i, (old, new) in enumerate(zip(old_rows, new_rows), start=1):
        if len(old) != len(new):
            return explain(path, f"line {i} has a different number of fields")
        for j in fixed:
            if old[j] != new[j]:
                return explain(path, f"line {i}: {header[j]} {old[j]!r} is now {new[j]!r}")
    return True


args = sys.argv[1:]
check = only_noise
if args and args[0] == "--verdicts":
    check, args = only_values_moved, args[1:]
for path in args:
    if check(path):
        print(path)
