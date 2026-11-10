"""Write every corpus repository's maintenance caller, and this repository's schedule.

Slots go in alphabetical order. Repository i checks in week i % 8 of the eight-week
cycle, on weekday i // 8 (Monday to Friday) at 06:47 UTC, so each week carries five full
checks, one a day, and every repository is checked once every 56 days. Minute 47 keeps
clear of the top of the hour, when GitHub delays scheduled runs most, and of the R
packages' :23 slots.

Usage, from this repository's root:
  python3 make_callers.py [corpus_dir]
"""

import csv
import datetime as dt
import os
import sys

CYCLE = 8
HOUR, MINUTE = 6, 47
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

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


def next_check(phase, weekday):
    """First date on or after today when this slot falls in its week of the cycle."""
    today = dt.datetime.now(dt.timezone.utc).date()
    for offset in range(7 * CYCLE):
        day = today + dt.timedelta(days=offset)
        fire = dt.datetime(day.year, day.month, day.day, HOUR, MINUTE, tzinfo=dt.timezone.utc)
        if day.weekday() == weekday and int(fire.timestamp()) // 604800 % CYCLE == phase:
            return day.isoformat()


corpus = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/git_projects/active_maintenance")
repos = sorted(d for d in os.listdir(corpus) if os.path.isdir(os.path.join(corpus, d, ".git")))
if len(repos) > CYCLE * len(WEEKDAYS):
    sys.exit(f"{len(repos)} repositories do not fit in {CYCLE * len(WEEKDAYS)} slots")

schedule = []
for i, repo in enumerate(repos):
    phase, weekday = i % CYCLE, i // CYCLE
    workflow_dir = os.path.join(corpus, repo, ".github", "workflows")
    os.makedirs(workflow_dir, exist_ok=True)
    with open(os.path.join(workflow_dir, "maintenance.yml"), "w") as f:
        f.write(CALLER.format(cycle=CYCLE, minute=MINUTE, hour=HOUR, cron_day=weekday + 1, phase=phase))
    schedule.append({
        "repo": repo,
        "phase": phase,
        "weekday": WEEKDAYS[weekday],
        "time_utc": f"{HOUR:02d}:{MINUTE:02d}",
        "next_full_check": next_check(phase, weekday),
    })

with open("schedule.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(schedule[0].keys()))
    writer.writeheader()
    writer.writerows(schedule)

print(f"wrote {len(schedule)} callers and schedule.csv")
