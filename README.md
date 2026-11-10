# Active maintenance checks

Every repository in [active-maintenance-aec](https://github.com/active-maintenance-aec) carries a maintained rewrite of a published paper's code and a `run_all.R` that fetches the deposited data, verifies it, and rebuilds every number the paper prints. This repository reruns those pipelines on a schedule, on current R and current CRAN packages, so that a package release that breaks a pipeline or moves a published number is found within two months rather than whenever someone next opens the repository.

## How it works

- Each paper repository has a short `.github/workflows/maintenance.yml` that calls [`check.yml`](.github/workflows/check.yml) here, in its own weekly slot.
- Every week, a few seconds of work keep the repository's schedule enabled (GitHub disables a schedule after 60 days without repository activity, and these repositories are quiet by design).
- Once every eight weeks, in the repository's own week, the full check runs: install every package the code loads (`deps.R`), run `run_all.R`, and fail if the pipeline errors or if the run changes any committed file other than a figure. Figure files (PDF, PNG and the like) drawn on Linux never match the bytes of the copies drawn on the Mac that committed them, so they are listed but not judged; the numbers behind every figure are written out as CSVs, and those are. Nothing is pinned. A moved number is the finding.
- A manual dispatch from the repository's Actions tab runs the full check at once.

The run log and the installed package versions are attached to each run as an artifact.

## Schedule

`schedule.csv` lists each repository's week in the cycle, its weekday, and its next full check. Five repositories are checked each week, one a day, Monday to Friday at 06:47 UTC. `make_callers.py` writes the callers and the schedule; rerun it when a repository is added.
