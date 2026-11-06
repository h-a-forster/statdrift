# statdrift

Do p-values and estimates change when you upgrade SciPy or statsmodels, and do the release
notes say so? statdrift runs a frozen battery of 2,231 statistical calls under SciPy 1.9 to
1.18 and statsmodels 0.13.5 to 0.15.0 in pinned environments, and diffs adjacent releases.

| Primary steps, deterministic cells | SciPy (9 steps) | statsmodels (8 steps) |
|---|---:|---:|
| Cells changed | 420 of 53,232 (0.79%) | 42 of 13,073 (0.32%) |
| Function-releases changed | 41 of 585 | 5 of 136 |
| p-values crossing 0.05 or 0.01 | 2 of 14,439 | 0 of 4,553 |
| of which on ordinary inputs | 1 | 0 |
| p-values lost / gained (a number became NaN or an exception, or the reverse) | 15 / 6 | 0 / 6 |
| Material changes naming the function in the notes | 25 of 38 | 1 of 5 |
| Material changes the notes actually state (coded by reading) | 13 of 38 | 2 of 5 |
| Distinct upstream changes behind them that the notes state | 9 of 22 | 1 of 4 |

These rates describe this battery, a designed sample that leans on edge cases. They are not
the probability that your analysis changes. statdrift reports change, not correctness.

Of the two SciPy crossings, one is on ordinary data: `levene` with `center='trimmed'` on
normal samples, p 0.0366 to 0.0564 from 1.16.3 to 1.17.1, a bug fix the notes state. The
other is an input containing NaN, p 0.33 to 0.0, where neither value means anything.

Material changes cluster: one helper or one sweep moves several functions, so the 38 SciPy
function-releases come from 22 upstream changes. Silent means not stated under that
function's name: four functions that rank through `rankdata` count as silent although the
`rankdata` change itself is documented. A line can state a change without naming the function, so
the coded row can exceed the name row. Coding and grouping are one reader's judgement.

Two functions do not repeat at all within one release: `fisher_exact` on tables larger than
2x2 defaults to an unseeded Monte Carlo estimate, and `siegelslopes` with constant x returned
NaN in one run and a meaningless number in another. Those calls are left out of every count.

The tables are generated in [results/summary.md](results/summary.md). Design, estimands and
limits are in [docs/DESIGN.md](docs/DESIGN.md). Each changed cell is in
`results/changes.jsonl`, and each coded verdict with its evidence is in
`results/coding.csv`.

## Reproduce

You need [uv](https://docs.astral.sh/uv/) and a checkout: the battery, environments and notes
are not in the wheel, so statdrift refuses to run from an installed package. Results are for
Windows x86-64; the locks are universal, so other platforms can run the battery and get their
own numbers.

The second run of each environment is committed in `results/repeat/`, so `statdrift repeat` and
`statdrift diff` work without rerunning anything.

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
| `results/` | one JSONL per environment, the second run in `repeat/`, the summaries |
| `src/statdrift/` | builder, runner, differ, notes, report, CLI |

## Licence

MIT. Files under `notes/` are upstream's and keep their BSD-3-Clause licences.
