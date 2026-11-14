"""Write every corpus repository's maintenance caller, and this repository's schedule.

Slots go in alphabetical order. Repository i checks in week i % 8 of the eight-week
cycle, on weekday i // 8 (Monday to Saturday) at 06:47 UTC, so each week carries up to six full
checks, one a day, and every repository is checked once every 56 days. Minute 47 keeps
clear of the top of the hour, when GitHub delays scheduled runs most, and of the R
packages' :23 slots.

Usage, from this repository's root:
  python3 make_callers.py [corpus_dir]
"""

import csv
import datetime as dt
import os
import subprocess
import sys

CYCLE = 8
HOUR, MINUTE = 6, 47

# Repositories whose rerun of the deposited archive as a program does not fit on a GitHub
# runner: hewitt_etal_2024's takes hours, past the six-hour job limit, and two of
# aggarwal_etal_2023's deposited scripts peak at 12.3 and 10.3 GB against the runner's
# 16 GB. They skip those deposited scripts on GitHub; the local quarterly sweep still
# runs them.
ARCHIVE_SKIP_SLOW = {"aggarwal_etal_2023", "hewitt_etal_2024"}
# Outputs a repository's run cannot reproduce on the runner, restored rather than judged
# (check.yml's unjudged), and ground-truth tables judged on their verdicts alone
# (verdicts_only). coppock_2017a: the ictreg NLS bootstrap (seed 343, 2000 draws) fails on
# about half its resamples and which fail depends on LAPACK rounding (997 converged on the
# Mac, 990 on the runner), so adjusted SEs move in the third or fourth digit; Alex,
# 2026-11-13. Its verdicts agree in every row, and verdicts_only keeps that judged.
UNJUDGED = {
    "coppock_2017a": [
        "ground_truth/original_archive_*",
        "ground_truth/sampler_comparison.csv",
        "maintained/output/figure_1_*",
        "maintained/output/table_a1_subgroup_estimates.*",
        "maintained/output/text_descriptive_claims.csv",
    ],
}
VERDICTS_ONLY = {"coppock_2017a": ["ground_truth/coppock_2017a_ground_truth.csv"]}
# Monte Carlo quantities (check.yml's monte_carlo): (pathspecs, rtol, atol), each sized from
# measured cross-platform moves; Alex, 2026-11-13, "a more generous Monte Carlo tolerance".
# blair_coppock_moor_2020: the Stan meta-analysis; run 43523168023 moved figure 4 and
# Table 4 by at most 0.0056, and atol 0.026 is the widest of the claims gate's bands
# (3.42 x sqrt(2) x MCSE, maintained/mc_error.csv). coppock_2017a: the Table A1 bootstrap
# SEs; run 43523035915 moved them by at most 0.99% relative, so rtol 0.02.
MONTE_CARLO = {
    "blair_coppock_moor_2020": ([
        "maintained/output/figure_4_meta_estimates.csv",
        "maintained/output/table_4_meta_summary_cat.csv",
        "ground_truth/blair_coppock_moor_2020_ground_truth.csv",
    ], "0", "0.026"),
    "coppock_2017a": (["ground_truth/coppock_2017a_ground_truth.csv"], "0.02", "0"),
}
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

CALLER = """\
# Active maintenance check: reruns run_all.R on current R and CRAN packages every
# {cycle} weeks, in this repository's own slot. The shared logic, and the schedule for
# every repository, live in active-maintenance-aec/maintenance.
name: maintenance

on:
  schedule:
    - cron: "{minute} {hour} * * {cron_day}"
  workflow_dispatch:

permissions:
  actions: write
  contents: read

jobs:
  check:
    uses: active-maintenance-aec/maintenance/.github/workflows/check.yml@main
    with:
      phase: {phase}
"""

SKIP_SLOW_LINE = "      archive_skip_slow: true\n"


def next_check(phase, weekday):
    """First date on or after today when this slot falls in its week of the cycle."""
    today = dt.datetime.now(dt.timezone.utc).date()
    for offset in range(7 * CYCLE):
        day = today + dt.timedelta(days=offset)
        fire = dt.datetime(day.year, day.month, day.day, HOUR, MINUTE, tzinfo=dt.timezone.utc)
        if day.weekday() == weekday and int(fire.timestamp()) // 604800 % CYCLE == phase:
            return day.isoformat()


corpus = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/git_projects/active_maintenance")
# Only published repositories take a slot: a local repository with no origin has no
# GitHub workflow to run, and slotting it would move every repository after it.
def published(d):
    path = os.path.join(corpus, d)
    if not os.path.isdir(os.path.join(path, ".git")):
        return False
    remote = subprocess.run(["git", "-C", path, "remote", "get-url", "origin"], capture_output=True)
    return remote.returncode == 0


repos = sorted(d for d in os.listdir(corpus) if published(d))
if len(repos) > CYCLE * len(WEEKDAYS):
    sys.exit(f"{len(repos)} repositories do not fit in {CYCLE * len(WEEKDAYS)} slots")

schedule = []
for i, repo in enumerate(repos):
    phase, weekday = i % CYCLE, i // CYCLE
    workflow_dir = os.path.join(corpus, repo, ".github", "workflows")
    os.makedirs(workflow_dir, exist_ok=True)
    caller = CALLER.format(cycle=CYCLE, minute=MINUTE, hour=HOUR, cron_day=weekday + 1, phase=phase)
    if repo in ARCHIVE_SKIP_SLOW:
        caller += SKIP_SLOW_LINE
    if repo in UNJUDGED:
        caller += f'      unjudged: "{" ".join(UNJUDGED[repo])}"\n'
    if repo in VERDICTS_ONLY:
        caller += f'      verdicts_only: "{" ".join(VERDICTS_ONLY[repo])}"\n'
    if repo in MONTE_CARLO:
        paths, rtol, atol = MONTE_CARLO[repo]
        caller += f'      monte_carlo: "{" ".join(paths)}"\n'
        caller += f'      monte_carlo_rtol: "{rtol}"\n'
        caller += f'      monte_carlo_atol: "{atol}"\n'
    with open(os.path.join(workflow_dir, "maintenance.yml"), "w") as f:
        f.write(caller)
    schedule.append({
        "repo": repo,
        "phase": phase,
        "weekday": WEEKDAYS[weekday],
        "time_utc": f"{HOUR:02d}:{MINUTE:02d}",
        "next_full_check": next_check(phase, weekday),
        "archive_skip_slow": repo in ARCHIVE_SKIP_SLOW,
    })

with open("schedule.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(schedule[0].keys()))
    writer.writeheader()
    writer.writerows(schedule)

print(f"wrote {len(schedule)} callers and schedule.csv")
