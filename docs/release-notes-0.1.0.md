# statdrift 0.1.0

First study. Battery hash `a1fb32b0a4ea4a52f27d571788433b5acca13322038c692b76bc9d9599f75ba1`,
frozen in commit `601d189` before any release was diffed.

- 23 locked environments: SciPy 1.9.3 to 1.18.1 under two toolchains, statsmodels 0.13.5 to
  0.15.0 under one.
- Frozen battery of 2,231 calls over 153 inputs, with positive controls kept outside every
  estimand.
- Runner with a watchdog that turns a hang or an interpreter crash into a row, resume at call
  level, and a lock against concurrent runs.
- Standard-library differ: change rate, decision flips, documented share, magnitude.
- Release notes for 24 SciPy and 8 statsmodels releases, fetched once and hashed.
- Reading-based coding of all 43 material function-releases in `results/coding.csv`.

Corrections from the audit of 2026-11-06, none of which changes a measured cell:

- "p lost" now means a number that went away: SciPy 15 (was 42), statsmodels 0 (was 7). "p
  gained" is its own column: 6 and 6.
- `extreme` inputs count as ordinary, so the `levene` flip is on ordinary data: 1 of the 2.
- Material changes are grouped by upstream change (`upstream` in `results/coding.csv`).
- `results/repeat/` is committed, so the exclusion list can be rederived.
- The summary lists the flipped cells and names the failed calls; a test ties the README's
  headline table to it.
- Runner and watchdog: library output on stdout no longer aborts a run, a call with none of
  its fields stays in the diff, a call stopped at the deadline leaves one failure row, a runner
  that dies before its first call is an error. `statdrift notes` has a fetch timeout.
- `statdrift` refuses to run outside a checkout. Every file's battery hash is checked.
