# statdrift

Do p-values and estimates change when you upgrade SciPy or statsmodels, and do the release
notes say so? statdrift runs a frozen battery of 2,231 statistical calls under SciPy 1.9 to
1.18 and statsmodels 0.13.5 to 0.15.0 in pinned environments, and diffs adjacent releases.

| Primary steps, deterministic cells | SciPy (9 steps) | statsmodels (8 steps) |
|---|---:|---:|
| Cells changed | 420 of 53,232 (0.79%) | 42 of 13,073 (0.32%) |
| Function-releases changed | 41 of 585 | 5 of 136 |
| p-values crossing 0.05 or 0.01 | 2 of 14,439 | 0 of 4,553 |
| Material changes naming the function in the notes | 25 of 38 | 1 of 5 |
| Material changes the notes actually state (coded by reading) | 13 of 38 | 2 of 5 |

These rates describe this battery, a designed sample that leans on edge cases. They are not
the probability that your analysis changes. statdrift reports change, not correctness.

Two calls do not repeat at all within one release: `fisher_exact` on tables larger than 2x2
defaults to an unseeded Monte Carlo estimate, and `siegelslopes` with constant x returned NaN
in one run and a meaningless number in another.

The tables are generated in [results/summary.md](results/summary.md). Design, estimands and
limits are in [docs/DESIGN.md](docs/DESIGN.md). Each changed cell is in
`results/changes.jsonl`, and each coded verdict with its evidence is in
`results/coding.csv`.

## Reproduce

You need [uv](https://docs.astral.sh/uv/). Results are for Windows x86-64; the locks are
universal, so other platforms can run the battery and get their own numbers.

```sh
uv sync --group dev
uv run statdrift envs           # 23 locked environments
uv run statdrift run            # about 7 minutes; finished files are skipped
uv run statdrift run --repeat   # second run of each environment
uv run statdrift repeat         # results/repeatability.json
uv run statdrift diff           # results/summary.md and results/summary.json
```

Delete `results/*.jsonl` first for a run from scratch. `uv run statdrift envs --clean`
removes the virtual environments afterwards.

## Layout

| Path | Contents |
|---|---|
| `battery/` | the frozen battery and its hash |
| `configs/study.toml` | toolchains, release chains, pinned commits for notes |
| `envs/` | one locked uv project per environment |
| `notes/` | release notes as fetched, with hashes |
| `results/` | one JSONL per environment, plus the summaries |
| `src/statdrift/` | builder, runner, differ, notes, report, CLI |

## Licence

MIT. Files under `notes/` are upstream's and keep their BSD-3-Clause licences.
