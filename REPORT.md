# statdrift report: does upgrading SciPy or statsmodels change your p-values?

Results as released in 0.1.0: battery sha256 `a1fb32b0...`, Windows x86-64. Every number comes
from `results/summary.md` (written by `statdrift diff`), `results/coding.csv` or
`results/repeatability.json`. Table rows are copied from `results/summary.md`, and
`tests/test_controls.py` checks that. Design, estimands and limits: [docs/DESIGN.md](docs/DESIGN.md).

## Summary

- **Upgrades rarely move results here.** Over 9 adjacent SciPy steps (1.9 to 1.18), 420 of 53,232
  deterministic cells changed (0.79%). Over 8 statsmodels steps (0.13.5 to 0.15.0), 42 of 13,073
  changed (0.32%).
- **Verdicts almost never flip.** 2 of 14,439 SciPy p-values crossed 0.05 or 0.01. One was on
  ordinary data: `levene` with `center='trimmed'` on normal samples, p 0.03658 to 0.05643 from
  1.16.3 to 1.17.1, a bug fix the notes state. The other had NaN in its input. statsmodels: 0 of
  4,553.
- **The notes mostly do not say so.** Of 38 material SciPy changes, the notes name the function for
  25 but state the change for 13 (34.2%, 0.196 to 0.514). Those 38 come from 22 upstream changes, of
  which 9 are stated. statsmodels: 2 of 5.
- **The toolchain is not the cause.** Each release run under both toolchains (Python 3.11 with numpy
  1.25.2, and Python 3.12 with numpy 2.0.2) gave 0 changed cells, for all four releases.
- **Not every call repeats.** Only 10 of 23 environments reproduced their file byte for byte. The
  39 cells that differed come from `fisher_exact` on tables larger than 2x2 (an unseeded Monte Carlo
  default) and `siegelslopes` with constant x. They are left out of every count.

These rates describe a designed battery that leans on edge cases. They are not the probability that
your analysis changes. statdrift measures change, not correctness.

## Question

When you upgrade SciPy or statsmodels, how often do p-values and estimates move, how often does a
verdict flip, and how often did the release notes say so?

## Method

- **Battery.** 2,231 frozen calls. SciPy: 67 callables in `scipy.stats` and `scipy.stats.mstats`.
  65 are in the deterministic grid; `bootstrap` and `permutation_test` are stochastic only.
  statsmodels: 17 callables. Inputs are seeded draws at n from 3 upward, sizes near known method
  switches, ties, zeros, constants, extreme effects, NaN under each `nan_policy`, degenerate tables,
  near-collinear designs and perfect separation. Defaults come first, then named options.
- **Environments.** One locked uv project per release, the last patch of each minor. Each diffed
  pair shares one toolchain: t1 (Python 3.11, numpy 1.25.2) runs SciPy 1.9.3 to 1.16.3, t2 (Python
  3.12, numpy 2.0.2) runs 1.13.1 to 1.18.1, and sm runs every statsmodels release against SciPy
  1.11.4. Each run uses one BLAS thread, `PYTHONHASHSEED=0`, `python -I`, and seeds derived from
  each call's id.
- **Cells.** A cell is one (function, variant, input, field). A cell counts as changed if a number
  moves by more than 1e-9 relative (with a floor of 1e-12, or 1e-300 for p) or if its status
  changes: a number becomes NaN, infinite or an exception, or the reverse. A change is material
  above 1e-6 relative, or if it is a status change. Changes only in dtype or warnings, newly
  accepted keywords and added fields are counted apart.
- **Documented share.** The unit is one function in one step with a material change. Mechanical
  tiers: the name appears anywhere in the notes, in the narrative, or in a compatibility section.
  Two coded tiers come from reading every line that names the function: pointed and explained. One
  reader coded them after the results were known (`results/coding.csv`). Units are also grouped by
  the upstream change behind them.
- **Checks.** Every environment ran twice, and any call that differed between runs is excluded.
  Eight positive controls come from the SciPy 1.18.0 notes. A historical fixture covers the
  `mannwhitneyu` rewrite. The four releases run under both toolchains give an overlap check.

## Results

### Headline

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

### By step

| Step | Toolchain | Changed cells | of cells | Rate | of which status | Functions changed | material | p cells | flip 0.05 | flip 0.01 | p lost | p gained |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1.9.3 -> 1.10.1 | t1 | 114 | 5396 | 2.11% | 111 | 7/65 | 7 | 1571 | 1 | 1 | 4 | 0 |
| 1.10.1 -> 1.11.4 | t1 | 3 | 5647 | 0.05% | 2 | 2/65 | 2 | 1574 | 0 | 0 | 0 | 1 |
| 1.11.4 -> 1.12.0 | t1 | 50 | 5954 | 0.84% | 14 | 6/65 | 6 | 1575 | 0 | 0 | 7 | 0 |
| 1.12.0 -> 1.13.1 | t1 | 29 | 6004 | 0.48% | 3 | 6/65 | 3 | 1595 | 0 | 0 | 1 | 1 |
| 1.13.1 -> 1.14.1 | t1 | 38 | 6044 | 0.63% | 38 | 6/65 | 6 | 1621 | 0 | 0 | 0 | 0 |
| 1.14.1 -> 1.15.3 | t1 | 43 | 6045 | 0.71% | 42 | 3/65 | 3 | 1625 | 0 | 0 | 0 | 4 |
| 1.15.3 -> 1.16.3 | t1 | 6 | 6045 | 0.10% | 6 | 3/65 | 3 | 1625 | 0 | 0 | 0 | 0 |
| 1.16.3 -> 1.17.1 | t2 | 108 | 6046 | 1.79% | 2 | 3/65 | 3 | 1626 | 1 | 0 | 0 | 0 |
| 1.17.1 -> 1.18.1 | t2 | 29 | 6051 | 0.48% | 12 | 5/65 | 5 | 1627 | 0 | 0 | 3 | 0 |
| 0.13.5 -> 0.14.0 | sm | 32 | 1635 | 1.96% | 32 | 4/17 | 4 | 570 | 0 | 0 | 0 | 6 |
| 0.14.6 -> 0.15.0 | sm | 10 | 1634 | 0.61% | 0 | 1/17 | 1 | 569 | 0 | 0 | 0 | 0 |

The six statsmodels patch steps from 0.14.0 to 0.14.6 changed nothing. Most SciPy changes are
status changes. The large numeric steps are 1.16.3 to 1.17.1, where every `anderson` critical value
moved, and 1.11.4 to 1.12.0, where `shapiro` moved on 36 cells and by 0.012 in p at n = 10,000.

One jump across a whole chain changes more than any single step:

| Step | Toolchain | Changed cells | of cells | Rate | of which status | Functions changed | material | p cells | flip 0.05 | flip 0.01 | p lost | p gained |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1.9.3 -> 1.16.3 | t1 | 252 | 5419 | 4.65% | 212 | 23/65 | 23 | 1595 | 0 | 0 | 12 | 6 |
| 1.13.1 -> 1.18.1 | t2 | 222 | 6053 | 3.67% | 98 | 19/65 | 19 | 1628 | 1 | 0 | 3 | 5 |
| 0.13.5 -> 0.15.0 | sm | 32 | 1635 | 1.96% | 32 | 4/17 | 4 | 570 | 0 | 0 | 0 | 6 |

### Decision flips

| Step | Function | Variant | Input | Field | Before | After | Inputs |
|---|---|---|---|---|---:|---:|---|
| scipy 1.9.3 -> 1.10.1 | scipy.stats.cramervonmises_2samp | default | two/nan/20x20 | pvalue | 0.3255 | 0 | degenerate |
| scipy 1.16.3 -> 1.17.1 | scipy.stats.levene | trimmed | k/extreme/30x3 | pvalue | 0.03658 | 0.05643 | ordinary |

Among numeric p-value changes, the largest per step are 0.33 (1.9.3 to 1.10.1), 0.19 (1.14.1 to
1.15.3, `wilcoxon` with ties at n = 12) and 0.16 (1.16.3 to 1.17.1). Most other steps move p by
less than 1e-3.

### Where changes fall

| Library | Inputs | Changed cells | Numeric | Material | p flips | Function-releases |
|---|---|---:|---:|---:|---:|---:|
| scipy | ordinary | 240 | 174 | 179 | 1 | 18 |
| scipy | degenerate | 180 | 16 | 180 | 1 | 29 |
| statsmodels | ordinary | 8 | 0 | 8 | 0 | 1 |
| statsmodels | degenerate | 34 | 10 | 34 | 0 | 4 |

Degenerate means the input id names NaN, constant, all-zero, exact-fit, perfect, separated,
collinear or similar data. This split was chosen after the results were seen, so it is descriptive.

### Sensitivity to the change threshold

| Library | Cells (all steps) | Bitwise equal | rel > 1e-12 | rel > 1e-09 | rel > 1e-06 | rel > 0.001 |
|---|---:|---:|---:|---:|---:|---:|
| scipy | 53232 | 51666 | 332 | 190 | 129 | 116 |
| statsmodels | 13073 | 13019 | 10 | 10 | 10 | 7 |

Above 1e-9, most numeric changes are also above 1e-3. The headline does not rest on rounding.

### Documented share

| Library | Changed function-releases | Tier | Named | Share | 95% CP interval |
|---|---|---|---:|---:|---|
| scipy | material (> 1e-6 or status) | any | 25/38 | 65.8% | 0.486 to 0.804 |
| scipy | material (> 1e-6 or status) | narrative | 21/38 | 55.3% | 0.383 to 0.714 |
| scipy | material (> 1e-6 or status) | compatibility | 2/38 | 5.3% | 0.006 to 0.177 |
| scipy | material (> 1e-6 or status) | pointed | 27/38 | 71.1% | 0.541 to 0.846 |
| scipy | material (> 1e-6 or status) | explained | 13/38 | 34.2% | 0.196 to 0.514 |
| scipy | distinct upstream changes behind the material ones | pointed | 17/22 | 77.3% | 0.546 to 0.922 |
| scipy | distinct upstream changes behind the material ones | explained | 9/22 | 40.9% | 0.207 to 0.636 |
| statsmodels | material (> 1e-6 or status) | any | 1/5 | 20.0% | 0.005 to 0.716 |
| statsmodels | material (> 1e-6 or status) | pointed | 3/5 | 60.0% | 0.147 to 0.947 |
| statsmodels | material (> 1e-6 or status) | explained | 2/5 | 40.0% | 0.053 to 0.853 |

A name match is a weak signal: 25 named against 13 stated. Silent changes, with no line under the
function's name, include these (`results/coding.csv`):

- `shapiro`, 1.11.4 to 1.12.0: statistic and p moved on 36 cells, by 0.012 in p at n = 10,000.
- `mstats.linregress`, 1.17.1 to 1.18.1: on a perfect fit, p went from 4e-80 to 7e-64.
- `mannwhitneyu`, 1.17.1 to 1.18.1: on identical constant samples, p went from 1.0 to NaN.
- statsmodels `Logit` 0.15.0, under separation: the estimates moved.
- statsmodels `adfuller` 0.14.0, on a constant series: NaN became a ValueError.

`ansari`, `fligner`, `friedmanchisquare` and `mood` count as silent in 1.10, although the change
they inherit through `rankdata` is documented under that name.

### Checks

- **Toolchain:** the same release under t1 and t2 gave 0 changed cells for 1.13.1, 1.14.1, 1.15.3
  and 1.16.3. The three steps measured under both toolchains changed the same 38, 43 and 6 cells.
- **Positive controls:** all 8 controls from the SciPy 1.18.0 notes were found.
- **Historical control:** the `mannwhitneyu` rewrite from SciPy 1.6.3 to 1.7.3 changed 93 of 150
  cells and flipped 4 of 75 p-values.
- **Crashes:** `somersd` on a large table aborted the interpreter in 1.9.3 and 1.10.1 (exit code
  3221226505). 1.11 fixed it, and the notes say so.

## Limitations

- **Designed sample.** The battery is weighted towards edge cases, and its rates describe it.
  Most real analyses stay well inside the regions it stresses.
- **Change is not correctness.** No release is judged right or wrong.
- **SciPy alone.** Each step holds numpy and Python fixed. A real `pip install -U` also moves
  numpy, so it can show more change than a step here.
- **One platform, one machine.** Repeatability is run to run, not across platforms. Other BLAS
  builds and CPUs may differ.
- **SciPy patch releases inside a minor are not diffed.**
- **One reader.** The explained and pointed tiers, and the upstream grouping, are one reader's
  judgement after seeing the results. The ordinary/degenerate split is also post hoc.
- **Intervals.** Clopper-Pearson over function-releases that are not independent and not sampled
  from anything. They describe noise in a share over these units only.
- **The notes as a careful reader sees them.** A change explained only in a linked pull request
  does not count unless the PR title is in the notes.

## What would change the conclusion

- **A second coder.** The 13 of 38 explained rests on one reader. If a second reader codes many
  silent or pointed units as explained, the "notes rarely say so" finding weakens. The mechanical
  tiers (25 of 38 named) would not move.
- **A second platform.** If a Linux or other-BLAS run shows changes that this machine does not,
  the change rates here are a floor.
- **Moving numpy too.** Diffing upgrades that also move numpy, as users experience them, could
  raise the rates. The zero toolchain effect here holds only for the four releases checked.
- **A battery of ordinary analyses.** Weighting towards typical inputs would likely lower the
  rates. The one ordinary flip shows the rate is not zero.
- **Counting linked pull requests as documentation**, or diffing SciPy patch releases, would move
  the documented share and the per-step counts.

## Reproduce

```sh
uv sync --group dev
uv run statdrift envs           # 23 locked environments
uv run statdrift run            # about 7 minutes; finished files are skipped
uv run statdrift run --repeat   # second run of each environment
uv run statdrift repeat         # results/repeatability.json
uv run statdrift diff           # results/summary.md and results/summary.json
```
