# statdrift design

This document fixes the question, the environments, the battery, the estimands and the
checks. It was committed with the frozen battery before any two releases were diffed.
Anything changed afterwards is listed in section 11.

## 1. Question

When you upgrade SciPy or statsmodels, how often do p-values and estimates move, how often
does a verdict flip, and how often did the release notes say so? statdrift reports change,
not correctness: it never says which release is right. Pure CDF and quantile accuracy
against certified values belongs to other work.

## 2. Corrections to the first plan

The study began from a plan with one environment per release, the oldest compatible numpy
in each, Python 3.11 up to SciPy 1.13 and 3.12/3.13 after that. These parts did not hold
up, and each change below is the fix.

| Weakness | Consequence | Fix |
|---|---|---|
| Oldest numpy per env, Python switching mid-chain | A diff between adjacent releases mixes SciPy, numpy, Python and the numpy RNG stream (NEP 19 does not promise stream stability between numpy versions) | Every diffed pair shares one toolchain; section 3 |
| A release is "the" minor | `1.18` is not installable | The last patch of each minor, which is what a user on that minor runs; a step's notes are all that minor's patch notes |
| Inputs built from known changes | Edge cases taken from release notes inflate the documented share, the headline estimand | The grid uses generic edge cases only; anything from notes is group `control`, outside every estimand |
| "Cross-platform repeatability by rerunning one env twice" | One machine run twice says nothing about platforms, and one env says nothing about the other 22 | Called repeatability, run for every env; a non-repeating cell is dropped from the diffs. Cross-platform is not measured |
| A 1e-9 relative rule alone | Rounding around zero (a t statistic of 1e-16 vs 3e-16) counts as a change; a changed result dtype or a new optional field needs a defined treatment | Absolute floor for non-p fields, sensitivity table over the threshold, explicit classes for dtype, warnings and added or removed fields |
| One share of cells as the result | A cell share is set by how many inputs and fields the battery gives each function, and one code change moves many cells | Report function-release units next to cells; the cell count is a description of this battery, never a population rate |
| Name in notes means documented | `kstest` appears in 1.18 under "array API support"; the name is present and nothing warned the reader | Three mechanical tiers and one coded tier; section 7 |
| Seeded resampling counted with deterministic cells | A changed resampling path moves a bootstrap interval with no numerical change in the method | Group `stochastic`, reported apart |
| Keyword missing in old releases | `nan_policy` spread through `scipy.stats` release by release, and a `TypeError` that becomes a number is a feature, not drift | `unexpected keyword` is recorded as such: not applicable or API added, outside the rate. A keyword that disappears counts as a status change |
| The process survives every call | A compiled extension can abort the interpreter, and an exact method can hang | A parent process turns a hang or a crash into a row and resumes at the next call |

## 3. Environments

One uv project per environment under `envs/`, with a committed `uv.lock` (hashes, Windows
wheels, checked with `uv lock --check`). `configs/study.toml` is the matrix.

| Toolchain | Python | numpy | Other pins | Releases |
|---|---|---|---|---|
| t1 | 3.11 | 1.25.2 | | SciPy 1.9.3, 1.10.1, 1.11.4, 1.12.0, 1.13.1, 1.14.1, 1.15.3, 1.16.3 |
| t2 | 3.12 | 2.0.2 | | SciPy 1.13.1, 1.14.1, 1.15.3, 1.16.3, 1.17.1, 1.18.1 |
| sm | 3.11 | 1.25.2 | SciPy 1.11.4, pandas 1.5.3, patsy 0.5.6 | statsmodels 0.13.5, 0.14.0 to 0.14.6, 0.15.0 |

Why these: numpy 1.25.2 is the only line inside both SciPy 1.9.3's cap (`<1.26`) and SciPy
1.16's floor (`>=1.25.2`) on Python 3.11, so t1 covers eight releases. SciPy 1.17 needs
numpy `>=1.26.4` and 1.18 needs Python `>=3.12` and numpy `>=2.0`, so the chain must change
toolchain once. t2 starts at 1.13.1, the first SciPy built against numpy 2.

Primary steps: t1 from 1.9.3 to 1.16.3, then t2 from 1.16.3 to 1.18.1. The four releases
run under both toolchains give two checks: the same SciPy step measured twice (overlap), and
the same release under two toolchains (the toolchain effect).

This measures SciPy alone. A real `pip install -U` also moves numpy, so a user's upgrade can
show more change than a step here. SciPy wheels bundle their own OpenBLAS, so a BLAS update
inside a SciPy release counts as part of that release, as it does for a user.

statsmodels runs against one fixed SciPy, numpy, pandas and patsy. Its patch releases are
measured because statsmodels shipped nothing but patches from 2023 to 2026.

Each run uses one BLAS thread, `PYTHONHASHSEED=0` and `python -I`. Each call seeds numpy's
legacy global stream and gets a fresh `Generator`, both from `crc32(call id)`.

Windows x86-64 only. Integer inputs use numpy's default integer, which is 32-bit on
Windows under numpy 1.x, because that is what a user's array gets.

## 4. Battery

`battery/battery.json` holds every input and every call; `battery/battery.sha256` pins it.
`statdrift battery` must rebuild it byte for byte under the locked numpy. Draws are seeded
by `(20261106, crc32(input id))` and stored as JSON, so no environment generates data.

SciPy: 67 callables in `scipy.stats` and `scipy.stats.mstats`, all present in SciPy 1.9.3.
statsmodels: 17 callables. Inputs: seeded draws, n = 3 to 8 and up, n near known method
switches (9, 20/21, 25/26, 33/34, 50/51, 54/55, 10000/10001), ties, zeros, constant arrays,
extreme effects, NaN under each `nan_policy`, degenerate tables, near-collinear designs,
perfect separation.

Inclusion rules, applied by size and by what can run, not by outcome: a function has a
largest input (`SCIPY` table in `battery.py`), exact methods stop at n = 30 (Mann-Whitney)
or 200, and n = 10001 exists only for `ks_2samp`. The grid uses defaults first, because a
changed default is exactly what a user hits, then named options.

Groups: `grid` (deterministic, primary), `stochastic` (a seeded `Generator` is an
argument), `control` (section 8).

Before freezing, the battery was run on the oldest and newest release of each library to
check field paths. Those runs looked at exception types only; no two releases were compared
and no output was kept.

## 5. Cells and classes

A row is one (function, variant, input, field) with value, dtype, warning categories and
exception type. A call that raises writes one row with field `*`.

For a pair of releases, each cell is exactly one of:

| Class | Rule | In the rate? |
|---|---|---|
| numeric | both numbers, `abs(a-b) > 1e-9 * max(abs(a), abs(b))` and `abs(a-b) > floor` | changed |
| status | number vs NaN/inf/masked/exception, or a different exception type, or a keyword that vanished | changed |
| dtype | equal within tolerance, type differs | in denominator, not changed |
| warning | equal, warning categories differ | in denominator, not changed |
| same | none of the above | in denominator |
| API added | the old release rejected the keyword | outside |
| not applicable | both rejected the keyword | outside |
| field added / removed | field exists on one side, call succeeded on both | outside, counted |
| unstable | differed between two runs of one environment | outside, counted |

The floor is 1e-12 for non-p fields, 1e-300 for p-values. Where one side raised, every field
of the other side is a status cell, so a raising call costs what it would cost a user.

## 6. Estimands

Each is computed by `diff.py` (standard library only) over the grid group, for each primary
step.

1. Change rate: (numeric + status) / cells. Also functions with at least one changed cell,
   over functions.
2. Decision-flip rate: p-value cells where `a < alpha` and `b < alpha` disagree, for alpha
   0.05 and 0.01, over p-value cells. A p-value that becomes NaN or an exception is "p lost",
   counted apart. The denominator depends on how many inputs sit near a threshold, which is
   a property of this battery.
3. Documented share: section 7.
4. Magnitude: the distribution of `abs(delta p)` over numeric p-value changes.

Material change: relative change above 1e-6, or any status change. This line separates
rounding from something a reader of a table could see; it is a reporting convention.

## 7. Documented share

Unit: one function in one primary step, with at least one changed grid cell. Notes are
fetched once from pinned commits, hashed in `notes/MANIFEST.json` and committed. A step's
notes are all patch notes of its target minor up to the target release. statsmodels has no
notes file for 0.14.5 and 0.14.6; their GitHub release bodies stand in.

Tiers, nested and mechanical (case-sensitive, whole word; `mstats.x` and `x` are distinct;
author lists excluded):

- any: the function name appears in the notes.
- narrative: it appears outside the issue and pull-request lists.
- compatibility: it appears in a backwards-incompatible or deprecation section.

A name match neither proves a warning nor rules one out: notes can name a function for an
unrelated reason, and a change in a shared helper (`scipy.special`, the axis/NaN decorator)
can be documented under the helper's name. So material changes are also coded by reading
every line naming the function, plus blanket statements, against the observed cells:

- explained: a line states this change.
- pointed: explained, or a line about the implicated behaviour that does not say results
  change (for example "gained `nan_policy` support").
- silent: neither.

`results/coding.csv` holds the verdict and the evidence for each unit, so every call can be
checked and overturned. This coding happens after the results are known and has one coder;
it is a judgement, not a measurement.

Interval: Clopper-Pearson with changed function-releases as units. They are neither a
random sample nor independent, so the interval describes noise in a share over these units,
not a population of functions.

## 8. Validity checks

- Null control: every environment runs twice. The files must match byte for byte, otherwise
  the differing cells are listed in `results/repeatability.json` and excluded.
- Positive controls: group `control` runs five inputs taken from the SciPy 1.18.0 notes
  (rankdata dtype, binomtest attribute dtype, multinomial with unnormalised p, spearmanr
  constant detection, pmean with tiny p). `report.CONTROLS` states what must be seen in
  1.17.1 to 1.18.1. A miss means a blind spot and fails `tests/test_controls.py`.
- Historical regression: `tests/fixtures/` holds real `mannwhitneyu` rows from SciPy 1.6.3
  and 1.7.3 (Python 3.9). The differ must report the change and the flips, and the 1.7.0
  notes must name the function.
- Overlap: the same step under t1 and t2 should change much the same cells.
- Differ tests on synthetic files with planted changes.

## 9. Limits

- The battery is a designed sample, weighted towards edge cases. Its rates describe it. They
  do not estimate the probability that your analysis changes. Most real analyses stay well
  inside the regions this battery stresses.
- A change is not a bug and no change is not correctness.
- Patch releases inside a minor are not diffed for SciPy.
- One platform, one machine. Other BLAS builds and CPUs can differ.
- The documented share reads notes the way a careful user would. A change explained only in
  a linked pull request does not count unless its title is in the notes (tier any).

## 10. Prior work

Only anecdotes and single-version checks were found.

- scikit-bio issue 1259: ANCOM tests failed when `mannwhitneyu` p-values changed between
  SciPy 0.16.1 and 0.17.0.
- PyTorch pull requests 64844 and 64922 pinned SciPy to 1.6.3, stating that
  `scipy.stats.poisson`, `geom` and `binom` return quite different results in 1.7+.
- SciPy 1.7.0 notes (the `mannwhitneyu` rewrite and new defaults) and 1.18.0 notes (rankdata,
  multinomial, binomtest, spearmanr, pmean).

No release-to-release measurement of drift in statistical software was found.

## 11. Changes after the freeze

The battery, the runner and the environments are unchanged since the freeze commit
(`601d189`). Everything below happened after results were visible, unless stated.

- First full run discarded before any diff. Two drivers ran at once and interleaved rows in
  the same files. `statdrift run` now takes a lock; only the clean rerun is committed.
- Differ, blind spot found by the spearmanr control: a scalar output that becomes an array was
  filed as a new field, outside the rate. A change of shape is now a status change. It moved
  no primary number: only the control cells had this shape change.
- Instability is now applied per call, not per cell. `siegelslopes` left one garbage field
  that matched by chance in two runs.
- The binomtest control expected a dtype change. SciPy 1.18.1 reverted it (scipy#25509), so at
  the last patch the control expects no change.
- Tier "pointed" and verdict "silent" were added to the coding when reading showed that
  "explained" alone hid lines that hint at a change without stating it.
- The split into ordinary and degenerate inputs (`report.DEGENERATE`) is post hoc and
  descriptive.
