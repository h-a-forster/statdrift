# Contributing

Read [docs/DESIGN.md](docs/DESIGN.md) first: it fixes the environments, the battery, the
estimands and what the study does not claim.

## Setup

You need [uv](https://docs.astral.sh/uv/) and git. From a clone:

```sh
uv sync --group dev
uv run statdrift --version
```

## Tests and lint

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run statdrift envs --check    # uv lock --check in every environment
```

CI runs lint and tests on pull requests only. Tests must run offline, write only under
pytest's `tmp_path`, and pass on Windows. A bug fix comes with a test that fails without it.

## Rules that keep the numbers honest

- The battery is frozen. Changing an input or a call changes `battery/battery.sha256`, voids
  every results file and starts a new study version: do that in its own pull request, and
  never after looking at a diff to chase a result. Inputs taken from release notes go in
  group `control`, never in the grid.
- `src/statdrift/runner.py` stays free of statdrift imports and of syntax newer than Python
  3.9. `diff.py` stays standard library only.
- Do not edit generated files: `results/summary.*`, `results/changes.jsonl`,
  `results/documented.csv`, `results/repeatability.json`. `results/coding.csv` is
  hand-written; each verdict quotes its evidence and groups the unit under an upstream change.
- The README's headline table and the tables in `REPORT.md`, once it is added, are copied
  from `results/summary.md`, and tests check that.
- Code style: Python 3.11+, typed, line length 100, ruff enforces the rest.

Security issues: see [SECURITY.md](SECURITY.md).
