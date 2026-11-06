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
