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

With --monte-carlo RTOL ATOL, a file passes when every number moved by no more than
ATOL + RTOL * max(|old|, |new|) plus one unit in the last place the coarser of the two
was printed to (two values rounded to 0.25 and 0.26 can come from draws 0.0001 apart).
That is for a Monte Carlo quantity (MCMC or bootstrap draws) that cannot agree across
platforms, sized per repository from measured moves (make_callers.py). In a ground-truth
table the verdict columns may flip, but only on rows whose reproduced values passed; and
when any did, ground_truth/float_coverage.csv passes too if each of its changed numbers
sits in a row named by a flipped claim's location and moved by no more than the number
of flips there.

Usage, from a paper repository's root:
  python3 compare_csv.py [--verdicts | --monte-carlo RTOL ATOL] <file> [<file> ...]
  python3 compare_csv.py --monte-carlo-spec "<entry> ..." RTOL ATOL
An entry is a git pathspec, or pathspec=RTOL:ATOL for a file on its own scale (blair's
ground truth holds text claims in points beside Table 4 cells in proportions); the spec
form judges each changed file the entries match. Prints the files that pass, one per
line, and explains the rest on stderr.
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


def last_place(token):
    """One unit in the last printed place of a number token (0.01 for "0.25")."""
    mantissa, _, exponent = token.lower().partition("e")
    decimals = len(mantissa.partition(".")[2])
    return 10.0 ** (-decimals + (int(exponent) if exponent else 0))


def within_band(a, b, rtol, atol):
    x, y = float(a), float(b)
    unit = max(last_place(a), last_place(b))
    return abs(x - y) <= atol + rtol * max(abs(x), abs(y)) + unit


def numbers_within_band(old, new, rtol, atol):
    if NUMBER.sub("#", old) != NUMBER.sub("#", new):
        return False
    return all(within_band(a, b, rtol, atol)
               for a, b in zip(NUMBER.findall(old), NUMBER.findall(new)))


# Columns that identify a ground-truth claim; they never move under Monte Carlo error.
IDENTITY = {"paper_id", "claim_id", "location", "claim_type", "claim", "value_paper", "digits"}
COVERAGE = "ground_truth/float_coverage.csv"


def committed_rows(path):
    committed = subprocess.run(["git", "show", f"HEAD:{path}"], capture_output=True, text=True)
    if committed.returncode != 0:
        return None
    return list(csv.reader(io.StringIO(committed.stdout)))


def monte_carlo_ground_truth(path, old_rows, new_rows, rtol, atol, flips):
    """Flips are added to `flips` only when the whole file passes."""
    header = old_rows[0]
    found = {}
    values = [j for j, name in enumerate(header) if name in MAY_MOVE]
    identity = [j for j, name in enumerate(header) if name in IDENTITY]
    location = header.index("location") if "location" in header else None
    for i, (old, new) in enumerate(zip(old_rows, new_rows), start=1):
        if old == new:
            continue
        if len(old) != len(new):
            return explain(path, f"line {i} has a different number of fields")
        for j in identity:
            if old[j] != new[j]:
                return explain(path, f"line {i}: {header[j]} {old[j]!r} is now {new[j]!r}")
        for j in values:
            if old[j] != new[j] and not numbers_within_band(old[j], new[j], rtol, atol):
                return explain(path, f"line {i}: {header[j]} {old[j]!r} is now {new[j]!r}, outside the Monte Carlo band")
        if any(old[j] != new[j] for j in range(len(header)) if j not in values):
            where = old[location] if location is not None else ""
            found[where] = found.get(where, 0) + 1
    for where, n in found.items():
        flips[where] = flips.get(where, 0) + n
    return True


def monte_carlo(path, rtol, atol, flips):
    old_rows = committed_rows(path)
    if old_rows is None:
        return explain(path, "not in the committed tree")
    with open(path, newline="") as f:
        new_rows = list(csv.reader(f))
    if not old_rows or old_rows[0] != new_rows[0]:
        return explain(path, "header differs")
    if len(old_rows) != len(new_rows):
        return explain(path, f"{len(old_rows)} committed rows, {len(new_rows)} now")
    if {"match", "match_rewrite"} & set(old_rows[0]):
        return monte_carlo_ground_truth(path, old_rows, new_rows, rtol, atol, flips)
    for i, (old, new) in enumerate(zip(old_rows, new_rows), start=1):
        if len(old) != len(new):
            return explain(path, f"line {i} has a different number of fields")
        for name, a, b in zip(old_rows[0], old, new):
            if a != b and not numbers_within_band(a, b, rtol, atol):
                return explain(path, f"line {i}: {name} {a!r} is now {b!r}, outside the Monte Carlo band")
    return True


def coverage_follows_flips(flips):
    old_rows = committed_rows(COVERAGE)
    if old_rows is None:
        return explain(COVERAGE, "not in the committed tree")
    with open(COVERAGE, newline="") as f:
        new_rows = list(csv.reader(f))
    if old_rows[0] != new_rows[0] or len(old_rows) != len(new_rows):
        return explain(COVERAGE, "shape differs")
    for i, (old, new) in enumerate(zip(old_rows, new_rows), start=1):
        if old == new:
            continue
        allowed = flips.get(old[0], 0)
        if len(old) != len(new) or old[0] != new[0] or not allowed:
            return explain(COVERAGE, f"line {i} ({old[0]}) changed with no tolerated flip there")
        for a, b in zip(old, new):
            if a == b:
                continue
            try:
                moved = abs(float(a) - float(b))
            except ValueError:
                return explain(COVERAGE, f"line {i}: {a!r} is now {b!r}")
            if moved > allowed:
                return explain(COVERAGE, f"line {i}: {a} is now {b}, more than the {allowed} flip(s) at {old[0]}")
    return True


def changed(pathspec):
    out = subprocess.run(["git", "diff", "--name-only", "--", pathspec],
                         capture_output=True, text=True).stdout
    return [line for line in out.splitlines() if line]


args = sys.argv[1:]
if args and args[0] in ("--monte-carlo", "--monte-carlo-spec"):
    if args[0] == "--monte-carlo":
        rtol, atol = float(args[1]), float(args[2])
        jobs = [(path, rtol, atol) for path in args[3:]]
    else:
        jobs = []
        for entry in args[1].split():
            pathspec, _, tols = entry.partition("=")
            rtol, atol = (float(x) for x in tols.split(":")) if tols else (float(args[2]), float(args[3]))
            jobs += [(path, rtol, atol) for path in changed(pathspec)]
    flips = {}
    for path, rtol, atol in jobs:
        if monte_carlo(path, rtol, atol, flips):
            print(path)
    if flips:
        print(f"Verdicts flipped inside the Monte Carlo band: {flips}", file=sys.stderr)
        if changed(COVERAGE) and coverage_follows_flips(flips):
            print(COVERAGE)
    sys.exit(0)
check = only_noise
if args and args[0] == "--verdicts":
    check, args = only_values_moved, args[1:]
for path in args:
    if check(path):
        print(path)
