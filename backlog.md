# Backlog

## In progress

## Waiting on me

- Add REPORT.md: the study is finished and its text exists, but the agent's file tools refused to write it.

## Decided

- 2026-11-06: one toolchain per diffed pair, instead of the oldest numpy per environment.
- 2026-11-06: Windows x86-64 only; repeatability is run to run, not cross-platform.
- 2026-11-06: statdrift runs from a checkout only; the wheel carries no study data.

## Proposed

- A second platform (Linux) runs the battery, so cross-platform differences are measured.
- SciPy patch releases inside a minor are diffed.
- A second coder repeats `results/coding.csv`, so agreement can be reported.
- Exact Clopper-Pearson in `diff.py` gets slow past n of about 200 (8 s at 200); switch method before unit counts grow.
- On POSIX only the direct child is killed, so the deadline reader would block if a runner grandchild inherited stdout.
