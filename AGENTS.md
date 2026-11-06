# AGENTS.md

Guide for coding agents (and humans) working on statdrift. Read `docs/DESIGN.md` before
changing the battery, the differ or any estimand.

## What this is

A study and its instrument. A frozen battery of statistical calls runs under every minor
SciPy release from 1.9 to 1.18 and every statsmodels release from 0.13.5 to 0.15.0. A
standard-library differ compares adjacent releases and reports how much changed, how many
p-values crossed 0.05 or 0.01, and whether the release notes named the function. It reports
change, not correctness.

## Conventions

- uv + hatchling, `src/` layout, Python >= 3.11 (local dev 3.13 via `.python-version`),
  typed code, `ruff check` + `ruff format` (line length 100), pytest. `[tool.uv]
  exclude-newer` keeps the locks on releases at least two weeks old; move it deliberately
  (it also lives in `study.py` for the environment locks).
- The package has no runtime dependencies. numpy (dev) only builds the battery.
- `src/statdrift/runner.py` runs under the pinned interpreters: no statdrift imports, nothing
  newer than Python 3.9 syntax. `CALL_MARK` must match in `runner.py` and `study.py`; other
  stdout is a library's own and is ignored.
- Every diffed pair shares a toolchain. Do not add a release to a chain unless it fits that
  chain's Python and numpy; add a chain instead.
- The battery is frozen (`battery/battery.sha256`). Changing it voids every results file.
  Inputs taken from release notes are group `control` and stay outside every estimand.
- Long work: `statdrift run` appends each finished call, skips finished files and resumes a
  partial one. A call that hangs or kills the interpreter becomes a row (`Timeout`,
  `Crash:<code>`). The whole study takes about 15 minutes with both runs.
- Generated, never hand-edited: `results/summary.*`, `results/changes.jsonl`,
  `results/documented.csv`, `results/repeatability.json`. `results/repeat/` is committed: it
  is what `repeatability.json` is derived from. `results/coding.csv` is hand-written. The
  README's headline table and the tables in `REPORT.md`, once it is added (see `backlog.md`),
  are copied from `results/summary.md`; tests check both, and a `REPORT.md` row written by hand
  must contain the text `(by hand)`.
- No network in tests, `diff` or `repeat`. CI runs only on pull requests and manual dispatch
  (metered minutes, private repository). Do not dispatch it casually.
- Release hygiene: no personal names, local user paths or machine details in committed
  files. Scratch files go in `tmp/` (gitignored). No `.bak` copies; use git.
- Change notes go in `docs/release-notes-<version>.md`. Open work lives in `backlog.md`.
- Statistical honesty: the battery is a designed sample, so rates describe it and nothing
  else. Say so wherever a rate appears.

## Architecture map

| Path | Role |
|---|---|
| `configs/study.toml` | toolchains, chains, pinned commits for notes |
| `src/statdrift/battery.py` | builds inputs and calls; `battery/battery.json` is its frozen output |
| `src/statdrift/runner.py` | runs the battery in one environment, one JSONL row per cell |
| `src/statdrift/study.py` | writes, locks and syncs environments; runs with a hang and crash watchdog; resume |
| `src/statdrift/diff.py` | cell classes, tallies, magnitude, Clopper-Pearson (standard library only) |
| `src/statdrift/notes.py` | fetches and hashes notes, sections them, finds function names |
| `src/statdrift/report.py` | study pairs, repeatability, controls, all summaries |
| `src/statdrift/cli.py` | `battery / envs / run / repeat / notes / diff` |
| `envs/<env>/` | one uv project per environment, committed with its lock (`.venv` ignored) |
| `notes/` | release notes as fetched, `MANIFEST.json` with hashes |
| `results/<env>.jsonl` | one file per environment; `results/repeat/` holds the second run |
| `tests/fixtures/` | real `mannwhitneyu` rows from SciPy 1.6.3 and 1.7.3, the 1.7.0 notes |

## How to test and reproduce

```sh
uv sync --group dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run statdrift envs --check   # uv lock --check in each environment

uv run statdrift envs           # create 23 environments
uv run statdrift run            # results/<env>.jsonl (finished files are skipped)
uv run statdrift run --repeat   # results/repeat/
uv run statdrift repeat         # results/repeatability.json
uv run statdrift diff           # summaries
```

To rerun the study from scratch, delete `results/*.jsonl` first. Delete the `.venv`
directories afterwards with `statdrift envs --clean`.

## Status

See `backlog.md` for open work and `results/summary.md` for the findings.
