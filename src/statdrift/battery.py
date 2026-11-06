"""Build the frozen battery: every input and every call, as one JSON file.

`battery/battery.json` was built once, committed before any release was diffed, and its
hash is pinned in `battery/battery.sha256`. Rebuilding must reproduce it byte for byte
under the locked numpy. The grid below comes from the study's function list and generic
edge cases, not from any release note; inputs taken from notes are group "control" and are
excluded from every estimand (docs/DESIGN.md section 4).
"""

from __future__ import annotations

import hashlib
import json
import zlib
from pathlib import Path

import numpy as np

SEED = 20261106
LARGE = 200  # input size above which only near-linear functions run


def _rng(input_id: str) -> np.random.Generator:
    return np.random.default_rng([SEED, zlib.crc32(input_id.encode())])


def _floats(array: np.ndarray) -> list:
    """Plain Python values with NaN as null."""
    return [None if np.isnan(v) else float(v) for v in array]


def _one_inputs() -> dict[str, dict]:
    out: dict[str, dict] = {}

    def add(name: str, draw) -> None:
        key = "one/" + name
        out[key] = {"x": _floats(np.asarray(draw(_rng(key))))}

    for n in (3, 4, 5, 6, 7, 8, 12, 30, 200, 10000):
        add(f"norm/n{n}", lambda r, n=n: r.normal(size=n))
    for n in (12, 30):
        add(f"shift0.6/n{n}", lambda r, n=n: r.normal(0.6, 1, n))
    add("lognormal/n30", lambda r: r.lognormal(size=30))
    add("t3/n30", lambda r: r.standard_t(3, 30))
    add("ties/n12", lambda r: np.round(r.normal(size=12)))
    add("ties/n30", lambda r: np.round(r.normal(size=30) * 2) / 2)
    add("zeros/n20", lambda r: r.normal(size=20) * r.integers(0, 2, 20))
    add("constant/n10", lambda r: np.full(10, 2.5))
    add("extreme/n30", lambda r: r.normal(50, 1, 30))
    add("nan/n20", lambda r: np.where(r.random(20) < 0.15, np.nan, r.normal(size=20)))
    return out


def _two_inputs() -> dict[str, dict]:
    out: dict[str, dict] = {}

    def add(name: str, draw) -> None:
        key = "two/" + name
        x, y = draw(_rng(key))
        out[key] = {"x": _floats(np.asarray(x)), "y": _floats(np.asarray(y))}

    sizes = [(3, 3), (3, 7), (4, 4), (5, 5), (6, 8), (8, 8), (9, 9), (20, 20), (21, 21)]
    sizes += [(30, 30), (54, 54), (55, 55), (200, 200), (10000, 10000), (10001, 10001)]
    for nx, ny in sizes:
        add(f"null/{nx}x{ny}", lambda r, nx=nx, ny=ny: (r.normal(size=nx), r.normal(size=ny)))
    add("hetero/30x60", lambda r: (r.normal(0, 1, 30), r.normal(0, 3, 60)))
    add("shift0.3/30x30", lambda r: (r.normal(0.3, 1, 30), r.normal(size=30)))
    add("shift0.6/30x30", lambda r: (r.normal(0.6, 1, 30), r.normal(size=30)))
    add("shift1/12x12", lambda r: (r.normal(1, 1, 12), r.normal(size=12)))
    add("extreme/30x30", lambda r: (r.normal(50, 1, 30), r.normal(size=30)))
    add("ties/4x5", lambda r: (np.round(r.normal(size=4)), np.round(r.normal(size=5))))
    add("ties/8x8", lambda r: (np.round(r.normal(size=8)), np.round(r.normal(size=8))))
    add("ties/30x30", lambda r: (np.round(r.normal(size=30)), np.round(r.normal(size=30))))
    add("constant-x/10x10", lambda r: (np.full(10, 1.5), r.normal(size=10)))
    add("constant-both/10x10", lambda r: (np.full(10, 1.5), np.full(10, 1.5)))
    add(
        "nan/20x20",
        lambda r: (
            np.where(r.random(20) < 0.15, np.nan, r.normal(size=20)),
            np.where(r.random(20) < 0.15, np.nan, r.normal(size=20)),
        ),
    )
    return out


def _paired_inputs() -> dict[str, dict]:
    out: dict[str, dict] = {}

    def add(name: str, draw) -> None:
        key = "paired/" + name
        x, y = draw(_rng(key))
        out[key] = {"x": _floats(np.asarray(x)), "y": _floats(np.asarray(y))}

    def noisy(r: np.random.Generator, n: int, shift: float = 0.0):
        x = r.normal(size=n)
        return x + shift + r.normal(0, 0.7, n), x

    for n in (3, 5, 6, 8, 12, 25, 26, 30, 50, 51, 200, 10000):
        add(f"null/n{n}", lambda r, n=n: noisy(r, n))
    add("shift0.4/n30", lambda r: noisy(r, 30, 0.4))
    add("extreme/n30", lambda r: noisy(r, 30, 50.0))

    def zeros(r: np.random.Generator):
        x, y = noisy(r, 20)
        x[:4] = y[:4]
        return x, y

    add("zeros/n20", zeros)
    add("ties/n20", lambda r: (lambda x: (x + np.round(r.normal(size=20)), x))(r.normal(size=20)))
    add("all-zero/n10", lambda r: (lambda x: (x, x.copy()))(r.normal(size=10)))

    def nans(r: np.random.Generator):
        x, y = noisy(r, 20)
        x[3] = np.nan
        y[11] = np.nan
        return x, y

    add("nan/n20", nans)
    return out


def _k_inputs() -> dict[str, dict]:
    out: dict[str, dict] = {}

    def add(name: str, draw) -> None:
        key = "k/" + name
        out[key] = {"groups": [_floats(np.asarray(g)) for g in draw(_rng(key))]}

    add("null/3x3", lambda r: [r.normal(size=3) for _ in range(3)])
    add("null/10x3", lambda r: [r.normal(size=10) for _ in range(3)])
    add("null/6x4", lambda r: [r.normal(size=6) for _ in range(4)])
    add("null/3000x3", lambda r: [r.normal(size=3000) for _ in range(3)])
    add("shift0.5/unequal", lambda r: [r.normal(s, 1, n) for s, n in ((0, 5), (0.5, 8), (1, 12))])
    add("shift0.3/30x3", lambda r: [r.normal(s, 1, 30) for s in (0, 0.3, 0.6)])
    add("extreme/30x3", lambda r: [r.normal(s, 1, 30) for s in (0, 50, 100)])
    add("ties/12x3", lambda r: [np.round(r.normal(size=12)) for _ in range(3)])
    add(
        "constant-group/10x3",
        lambda r: [np.full(10, 1.5), r.normal(size=10), r.normal(size=10)],
    )
    add("constant-all/10x3", lambda r: [np.full(10, 1.5) for _ in range(3)])
    add(
        "nan/10x3",
        lambda r: [np.where(r.random(10) < 0.2, np.nan, r.normal(size=10)) for _ in range(3)],
    )
    return out


def _bivariate_inputs() -> dict[str, dict]:
    out: dict[str, dict] = {}

    def add(name: str, draw) -> None:
        key = "biv/" + name
        x, y = draw(_rng(key))
        out[key] = {"x": _floats(np.asarray(x)), "y": _floats(np.asarray(y))}

    def correlated(r: np.random.Generator, n: int, rho: float):
        x = r.normal(size=n)
        return x, rho * x + np.sqrt(1 - rho**2) * r.normal(size=n)

    for n in (3, 4, 5, 6, 8, 30, 33, 34, 200, 10000):
        add(f"r0/n{n}", lambda r, n=n: correlated(r, n, 0.0))
    add("r0.3/n30", lambda r: correlated(r, 30, 0.3))
    add("r0.6/n30", lambda r: correlated(r, 30, 0.6))
    add("r0.95/n30", lambda r: correlated(r, 30, 0.95))
    add("perfect/n10", lambda r: (lambda x: (x, 2 * x + 1))(r.normal(size=10)))
    add("ties/n30", lambda r: (np.round(r.normal(size=30)), np.round(r.normal(size=30))))
    add("constant-x/n10", lambda r: (np.full(10, 1.5), r.normal(size=10)))

    def nans(r: np.random.Generator):
        x, y = correlated(r, 20, 0.3)
        x[3] = np.nan
        y[11] = np.nan
        return x, y

    add("nan/n20", nans)
    return out


def _regression_inputs() -> dict[str, dict]:
    out: dict[str, dict] = {}

    def design(r: np.random.Generator, n: int) -> np.ndarray:
        return np.column_stack([np.ones(n), r.normal(size=n), r.normal(size=n)])

    def add(key: str, y: np.ndarray, x: np.ndarray) -> None:
        out[key] = {"y": [float(v) for v in y], "X": [[float(v) for v in row] for row in x]}

    for n in (8, 50, 200):
        key = f"reg/n{n}"
        r = _rng(key)
        x = design(r, n)
        add(key, x @ [1.0, 0.5, -0.3] + r.normal(size=n), x)
    key = "reg/hetero/n100"
    r = _rng(key)
    x = design(r, 100)
    add(key, x @ [1.0, 0.5, 0.0] + r.normal(size=100) * (1 + np.abs(x[:, 1])), x)
    key = "reg/autocorrelated/n100"
    r = _rng(key)
    x = design(r, 100)
    e = np.zeros(100)
    for t in range(1, 100):
        e[t] = 0.6 * e[t - 1] + r.normal()
    add(key, x @ [1.0, 0.5, 0.0] + e, x)
    key = "reg/collinear/n50"
    r = _rng(key)
    x = design(r, 50)
    x[:, 2] = x[:, 1] + 1e-8 * r.normal(size=50)
    add(key, x @ [1.0, 0.5, 0.5] + r.normal(size=50), x)
    key = "reg/exact-fit/n20"
    r = _rng(key)
    x = design(r, 20)
    add(key, x @ [1.0, 2.0, -1.0], x)
    key = "reg/constant-y/n20"
    r = _rng(key)
    add(key, np.full(20, 3.0), design(r, 20))

    for n in (30, 100):
        key = f"bin/n{n}"
        r = _rng(key)
        x = design(r, n)
        p = 1 / (1 + np.exp(-(x @ [0.2, 1.0, -0.5])))
        add(key, (r.random(n) < p).astype(float), x)
    key = "bin/separated/n30"
    r = _rng(key)
    x = design(r, 30)
    add(key, (x[:, 1] > 0).astype(float), x)
    for n in (30, 100):
        key = f"cnt/n{n}"
        r = _rng(key)
        x = design(r, n)
        add(key, r.poisson(np.exp(x @ [0.5, 0.4, -0.2])).astype(float), x)
    key = "cnt/mostly-zero/n50"
    r = _rng(key)
    x = design(r, 50)
    add(key, r.poisson(0.05, 50).astype(float), x)
    return out


def _series_inputs() -> dict[str, dict]:
    out: dict[str, dict] = {}

    def ar(r: np.random.Generator, n: int, phi: float, theta: float = 0.0) -> np.ndarray:
        e = r.normal(size=n + 50)
        y = np.zeros(n + 50)
        for t in range(1, n + 50):
            y[t] = phi * y[t - 1] + e[t] + theta * e[t - 1]
        return y[50:]

    for key, draw in {
        "ts/ar0.6/n200": lambda r: ar(r, 200, 0.6),
        "ts/arma/n120": lambda r: ar(r, 120, 0.5, 0.4),
        "ts/white/n30": lambda r: r.normal(size=30),
        "ts/near-unit-root/n120": lambda r: ar(r, 120, 0.98),
        "ts/trend/n100": lambda r: 0.1 * np.arange(100) + r.normal(size=100),
    }.items():
        out[key] = {"x": [float(v) for v in draw(_rng(key))]}
    out["ts/constant/n30"] = {"x": [2.5] * 30}
    return out


def _table_inputs() -> dict[str, dict]:
    tables = {
        "small/a": [[1, 9], [11, 3]],
        "small/b": [[8, 2], [1, 5]],
        "small/c": [[3, 1], [1, 3]],
        "small/d": [[7, 12], [9, 4]],
        "small/e": [[12, 5], [29, 2]],
        "zero-diagonal": [[0, 5], [5, 0]],
        "zero-row": [[0, 0], [3, 4]],
        "balanced": [[5, 5], [5, 5]],
    }
    large = {"large/a": [[1000, 2000], [1500, 1800]], "large/b": [[122, 76], [98, 104]]}
    other = {
        "r2x3": [[3, 5, 2], [4, 1, 8]],
        "r3x3": [[10, 2, 3], [4, 9, 2], [1, 5, 12]],
        "r3x3-zeros": [[0, 2, 3], [4, 0, 2], [1, 5, 0]],
    }
    out = {"table/" + k: {"table": v, "small": True, "square": True} for k, v in tables.items()}
    out |= {"table/" + k: {"table": v, "small": False, "square": True} for k, v in large.items()}
    out |= {"table/" + k: {"table": v, "small": True, "square": False} for k, v in other.items()}
    return out


def _binom_inputs() -> dict[str, dict]:
    cases = [(7, 20, 0.5), (0, 10, 0.3), (10, 10, 0.3), (5, 10, 0.5), (682, 925, 0.75)]
    cases += [(1, 1000, 0.0001), (3, 15, 0.1), (42, 100, 0.5)]
    return {f"binom/k{k}n{n}p{p}": {"k": k, "n": n, "p": p} for k, n, p in cases}


def _multinomial_inputs() -> dict[str, dict]:
    cases = {
        "typical": ([3, 4, 3], 10, [0.2, 0.5, 0.3]),
        "zero-p": ([0, 4, 6], 10, [0.0, 0.5, 0.5]),
        "impossible": ([1, 4, 5], 10, [0.0, 0.5, 0.5]),
        "large": ([300, 450, 250], 1000, [0.3, 0.45, 0.25]),
        "wrong-n": ([3, 4, 3], 11, [0.2, 0.5, 0.3]),
    }
    return {"multinomial/" + k: {"x": x, "n": n, "p": p} for k, (x, n, p) in cases.items()}


def _pvalue_inputs() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for key, draw in {
        "plist/mixed": lambda r: np.concatenate([r.uniform(0, 0.01, 4), r.uniform(size=8)]),
        "plist/null": lambda r: r.uniform(size=12),
    }.items():
        out[key] = {"pvals": [float(v) for v in draw(_rng(key))]}
    out["plist/ties"] = {"pvals": [0.01, 0.01, 0.04, 0.04, 0.2, 0.2, 0.5, 1.0]}
    out["plist/edges"] = {"pvals": [0.0, 1e-300, 0.05, 0.05, 1.0]}
    return out


def _proportion_inputs() -> dict[str, dict]:
    cases = {
        "one/typical": (32, 80),
        "one/zero": (0, 25),
        "one/all": (25, 25),
        "one/large": (5120, 10000),
        "two/typical": ([30, 45], [100, 110]),
        "two/zero": ([0, 12], [40, 40]),
    }
    return {"prop/" + k: {"count": c, "nobs": n} for k, (c, n) in cases.items()}


def _control_inputs() -> dict[str, dict]:
    """Inputs taken from the SciPy 1.18.0 notes and their issues: positive controls only."""
    matrix = np.zeros((10, 4))
    matrix[:, 2] = np.arange(10)
    matrix[:, 3] = -np.arange(10)
    return {
        "control/rank-ints": {"x": [1, 2, 2, 3]},
        "control/binom": {"k": 7, "n": 20, "p": 0.5},
        "control/multinomial-unnormalised": {"x": [3, 7], "n": 10, "p": [0.4, 0.5]},
        "control/spearman-matrix": {"x": [[float(v) for v in row] for row in matrix]},
        "control/pmean": {"x": [50.0, 100.0, 300.0, 70.0, 25.0, 100.0, 2.0]},
    }


TWO = {"statistic": "[0]", "pvalue": "[1]"}
CI = {"ci.low": ".confidence_interval().low", "ci.high": ".confidence_interval().high"}
ATTR = {"statistic": ".statistic", "pvalue": ".pvalue"}

# nan_policy has spread through scipy.stats release by release. Functions listed here get
# the NaN input once per policy; a release without the keyword is "not applicable".
NAN_POLICY = {"propagate", "omit", "raise"}


def _variants(**named: dict) -> dict[str, dict]:
    return {"default": {}} | named


# (name, family, variants, fields, largest input, nan_policy variants?)
S = "scipy.stats."
M = "scipy.stats.mstats."
SCIPY: list[tuple] = [
    # two independent samples
    (
        S + "ttest_ind",
        "two",
        _variants(
            welch={"equal_var": False},
            trim10={"trim": 0.1},
            less={"alternative": "less"},
            permutations={"permutations": 999, "random_state": "$rng"},
        ),
        TWO | {"df": ".df"} | CI,
        10001,
        True,
    ),
    (
        S + "mannwhitneyu",
        "two",
        _variants(
            asymptotic={"method": "asymptotic"},
            no_continuity={"use_continuity": False},
            greater={"alternative": "greater"},
            exact={"method": "exact"},
        ),
        TWO,
        10001,
        True,
    ),
    (S + "ranksums", "two", _variants(less={"alternative": "less"}), TWO, 10001, True),
    (
        S + "ks_2samp",
        "two",
        _variants(
            exact={"method": "exact"},
            asymp={"method": "asymp"},
            greater={"alternative": "greater"},
        ),
        TWO,
        10001,
        True,
    ),
    (
        S + "brunnermunzel",
        "two",
        _variants(normal={"distribution": "normal"}),
        TWO,
        10001,
        True,
    ),
    (S + "ansari", "two", _variants(), TWO, 10001, True),
    (S + "mood", "two", _variants(), TWO, 10001, True),
    (S + "cramervonmises_2samp", "two", _variants(), ATTR, 10001, True),
    (S + "epps_singleton_2samp", "two", _variants(), TWO, 200, True),
    (S + "median_test", "two-star", _variants(), TWO | {"median": "[2]"}, 10001, False),
    (
        S + "permutation_test",
        "two-perm",
        _variants(),
        ATTR,
        200,
        False,
    ),
    # paired
    (
        S + "ttest_rel",
        "paired",
        _variants(less={"alternative": "less"}),
        TWO | {"df": ".df"} | CI,
        10000,
        True,
    ),
    (
        S + "wilcoxon",
        "paired",
        _variants(
            pratt={"zero_method": "pratt"},
            zsplit={"zero_method": "zsplit"},
            correction={"correction": True},
            less={"alternative": "less"},
        ),
        TWO,
        10000,
        True,
    ),
    # one sample
    (S + "ttest_1samp", "one-mean", _variants(), TWO | {"df": ".df"} | CI, 10000, True),
    (S + "wilcoxon", "one", _variants(), TWO, 10000, True),
    (S + "ks_1samp", "one-cdf", _variants(asymp={"method": "asymp"}), TWO, 10000, True),
    (S + "kstest", "one-norm", _variants(exact={"method": "exact"}), TWO, 10000, True),
    (
        S + "anderson",
        "one",
        _variants(),
        {"statistic": ".statistic", "critical_values": ".critical_values"},
        10000,
        False,
    ),
    (S + "shapiro", "one", _variants(), TWO, 10000, True),
    (S + "normaltest", "one", _variants(), TWO, 10000, True),
    (S + "skewtest", "one", _variants(), TWO, 10000, True),
    (S + "kurtosistest", "one", _variants(), TWO, 10000, True),
    (S + "jarque_bera", "one", _variants(), TWO, 10000, True),
    (S + "cramervonmises", "one-norm", _variants(), ATTR, 10000, True),
    (S + "skew", "one", _variants(unbiased={"bias": False}), {"value": ""}, 10000, True),
    (S + "kurtosis", "one", _variants(unbiased={"bias": False}), {"value": ""}, 10000, True),
    (S + "gmean", "one", _variants(), {"value": ""}, 10000, True),
    (S + "hmean", "one", _variants(), {"value": ""}, 10000, True),
    (S + "pmean", "one-p", _variants(), {"value": ""}, 10000, True),
    (
        S + "bootstrap",
        "one-boot",
        _variants(percentile={"method": "percentile"}, basic={"method": "basic"}),
        {
            "ci.low": ".confidence_interval.low",
            "ci.high": ".confidence_interval.high",
            "standard_error": ".standard_error",
        },
        200,
        False,
    ),
    (
        S + "rankdata",
        "one",
        _variants(
            min={"method": "min"},
            max={"method": "max"},
            dense={"method": "dense"},
            ordinal={"method": "ordinal"},
        ),
        {"ranks": ""},
        30,
        True,
    ),
    # bivariate
    (S + "pearsonr", "biv", _variants(), TWO | CI, 10000, True),
    (S + "spearmanr", "biv", _variants(), TWO, 10000, True),
    (
        S + "kendalltau",
        "biv",
        _variants(
            c={"variant": "c"},
            exact={"method": "exact"},
            asymptotic={"method": "asymptotic"},
        ),
        TWO,
        200,
        True,
    ),
    (S + "kendalltau", "biv-large", _variants(), TWO, 10000, False),
    (S + "weightedtau", "biv", _variants(), TWO, 10000, False),
    (
        S + "linregress",
        "biv",
        _variants(),
        {
            "slope": ".slope",
            "intercept": ".intercept",
            "rvalue": ".rvalue",
            "pvalue": ".pvalue",
            "stderr": ".stderr",
            "intercept_stderr": ".intercept_stderr",
        },
        10000,
        False,
    ),
    (
        S + "theilslopes",
        "biv-yx",
        _variants(),
        {"slope": "[0]", "intercept": "[1]", "low": "[2]", "high": "[3]"},
        200,
        False,
    ),
    (S + "siegelslopes", "biv-yx", _variants(), {"slope": "[0]", "intercept": "[1]"}, 200, False),
    # k samples
    (S + "kruskal", "k", _variants(), TWO, 3000, True),
    (S + "friedmanchisquare", "k-equal", _variants(), TWO, 3000, True),
    (S + "f_oneway", "k", _variants(), TWO, 3000, True),
    (
        S + "levene",
        "k",
        _variants(mean={"center": "mean"}, trimmed={"center": "trimmed"}),
        TWO,
        3000,
        True,
    ),
    (S + "bartlett", "k", _variants(), TWO, 3000, True),
    (S + "fligner", "k", _variants(), TWO, 3000, True),
    (S + "alexandergovern", "k", _variants(), ATTR, 3000, True),
    (S + "tukey_hsd", "k", _variants(), {"statistic": ".statistic", "pvalue": ".pvalue"}, 30, True),
    (
        S + "anderson_ksamp",
        "k-list",
        _variants(),
        {"statistic": ".statistic", "pvalue": ".significance_level"},
        3000,
        False,
    ),
    # contingency tables
    (
        S + "fisher_exact",
        "table-all",
        _variants(less={"alternative": "less"}),
        {"statistic": "[0]", "pvalue": "[1]"},
        0,
        False,
    ),
    (
        S + "chi2_contingency",
        "table-all",
        _variants(no_correction={"correction": False}, g_test={"lambda_": "log-likelihood"}),
        {"statistic": "[0]", "pvalue": "[1]", "dof": "[2]"},
        0,
        False,
    ),
    (S + "barnard_exact", "table-small", _variants(unpooled={"pooled": False}), ATTR, 0, False),
    (
        S + "boschloo_exact",
        "table-small",
        _variants(greater={"alternative": "greater"}),
        ATTR,
        0,
        False,
    ),
    (S + "somersd", "table-all", _variants(), ATTR, 0, False),
    # counts
    (
        S + "binomtest",
        "binom",
        _variants(less={"alternative": "less"}, greater={"alternative": "greater"}),
        {
            "statistic": ".statistic",
            "pvalue": ".pvalue",
            "proportion_estimate": ".proportion_estimate",
            "ci.low": ".proportion_ci().low",
            "ci.high": ".proportion_ci().high",
        },
        0,
        False,
    ),
    (S + "multinomial.pmf", "multinomial", _variants(), {"value": ""}, 0, False),
    (S + "multinomial.logpmf", "multinomial", _variants(), {"value": ""}, 0, False),
    # masked-array variants
    (M + "ttest_ind", "two", _variants(), TWO, 200, False),
    (M + "ttest_rel", "paired", _variants(), TWO, 200, False),
    (M + "mannwhitneyu", "two", _variants(), TWO, 200, False),
    (M + "ks_2samp", "two", _variants(), TWO, 200, False),
    (M + "kruskal", "k", _variants(), TWO, 30, False),
    (M + "f_oneway", "k", _variants(), TWO, 30, False),
    (M + "pearsonr", "biv", _variants(), TWO, 200, False),
    (M + "spearmanr", "biv", _variants(), TWO, 200, False),
    (M + "kendalltau", "biv", _variants(), TWO, 200, False),
    (
        M + "linregress",
        "biv",
        _variants(),
        {"slope": "[0]", "intercept": "[1]", "rvalue": "[2]", "pvalue": "[3]", "stderr": "[4]"},
        200,
        False,
    ),
    (
        M + "theilslopes",
        "biv-yx",
        _variants(),
        {"slope": "[0]", "intercept": "[1]", "low": "[2]", "high": "[3]"},
        200,
        False,
    ),
    (M + "normaltest", "one", _variants(), TWO, 200, False),
    (M + "skewtest", "one", _variants(), TWO, 200, False),
]

SHAPES: dict[str, tuple[str, list, dict]] = {
    # family: (input prefix, positional arguments, extra keyword arguments)
    "one": ("one/", ["$x"], {}),
    "one-mean": ("one/", ["$x"], {"popmean": 0.0}),
    "one-cdf": ("one/", ["$x", "$get:scipy.stats.norm.cdf"], {}),
    "one-norm": ("one/", ["$x", "norm"], {}),
    "one-p": ("one/", ["$x"], {"p": 0.5}),
    "one-boot": (
        "one/",
        [["$x"], "$stat:mean"],
        {"n_resamples": 999, "random_state": "$rng"},
    ),
    "two": ("two/", ["$x", "$y"], {}),
    "two-star": ("two/", ["$x", "$y"], {}),
    "two-perm": (
        "two/",
        [["$x", "$y"], "$stat:mean_diff"],
        {"vectorized": True, "n_resamples": 999, "random_state": "$rng"},
    ),
    "paired": ("paired/", ["$x", "$y"], {}),
    "biv": ("biv/", ["$x", "$y"], {}),
    "biv-large": ("biv/r0/n10000", ["$x", "$y"], {}),
    "biv-yx": ("biv/", ["$y", "$x"], {}),
    "k": ("k/", ["$*groups"], {}),
    "k-equal": ("k/", ["$*groups"], {}),
    "k-list": ("k/", ["$groups"], {}),
    "table-all": ("table/", ["$table"], {}),
    "table-small": ("table/", ["$table"], {}),
    "binom": ("binom/", ["$k"], {"n": "$n", "p": "$p"}),
    "multinomial": ("multinomial/", ["$x"], {"n": "$n", "p": "$p"}),
}


def _size(data: dict) -> int:
    if "groups" in data:
        return max(len(g) for g in data["groups"])
    return len(data.get("x", ()))


def _admits(fn: str, family: str, key: str, data: dict, largest: int, kwargs: dict) -> bool:
    """Exclude pairs that cannot run or would be unaffordable, by rule rather than by outcome."""
    if family == "biv-large":
        return True
    # n=10001 straddles the ks_2samp exact/asymptotic switch and exists only for it.
    if key.endswith("x10001") and not fn.endswith("ks_2samp"):
        return False
    if family == "k-equal" and len({len(g) for g in data["groups"]}) > 1:
        return False
    if family == "table-small" and not (data["small"] and data["square"]):
        return False
    if fn.endswith("somersd") and not data["square"]:
        return False
    limit = largest
    if "permutations" in kwargs or kwargs.get("method") == "exact":
        limit = min(largest or 200, 30 if fn.endswith("mannwhitneyu") else 200)
    return not largest or _size(data) <= limit


def _scipy_calls(inputs: dict[str, dict]) -> list[dict]:
    calls = []
    for fn, family, variants, fields, largest, nan_variants in SCIPY:
        prefix, args, extra = SHAPES[family]
        keys = [k for k in inputs if k.startswith(prefix)]
        for variant, kwargs in variants.items():
            for key in keys:
                if _admits(fn, family, key, inputs[key], largest, kwargs):
                    calls.append(_call("scipy", fn, variant, key, args, extra | kwargs, fields))
        if nan_variants:
            nan_keys = [k for k in keys if k.startswith(prefix + "nan/")]
            for policy in sorted(NAN_POLICY):
                for key in nan_keys:
                    kw = extra | {"nan_policy": policy}
                    calls.append(_call("scipy", fn, f"nan_{policy}", key, args, kw, fields))
    return calls


def _call(lib, fn, variant, key, args, kwargs, fields, then=(), group=None) -> dict:
    stochastic = any(v == "$rng" for v in kwargs.values())
    return {
        "id": f"{fn}|{variant}|{key}",
        "lib": lib,
        "fn": fn,
        "variant": variant,
        "input": key,
        "args": args,
        "kwargs": kwargs,
        "then": [list(step) for step in then],
        "fields": fields,
        "group": group or ("stochastic" if stochastic else "grid"),
    }


FIT = {"params": ".params", "bse": ".bse", "pvalues": ".pvalues", "llf": ".llf"}


def _statsmodels_calls(inputs: dict[str, dict]) -> list[dict]:
    calls: list[dict] = []

    def add(fn, variant, prefix, args, kwargs, fields, then=()) -> None:
        for key in inputs:
            if key.startswith(prefix):
                calls.append(_call("statsmodels", fn, variant, key, args, kwargs, fields, then))

    ols = "statsmodels.api.OLS"
    ols_fields = FIT | {
        "rsquared": ".rsquared",
        "fvalue": ".fvalue",
        "pvalue_f": ".f_pvalue",
    }
    add(ols, "nonrobust", "reg/", ["$y", "$X"], {}, ols_fields, [("fit", {})])
    for cov in ("HC0", "HC1", "HC2", "HC3"):
        add(ols, cov, "reg/", ["$y", "$X"], {}, ols_fields, [("fit", {"cov_type": cov})])
    hac = {"cov_type": "HAC", "cov_kwds": {"maxlags": 4}}
    add(ols, "HAC", "reg/", ["$y", "$X"], {}, ols_fields, [("fit", hac)])

    glm_fields = FIT | {"deviance": ".deviance", "pearson_chi2": ".pearson_chi2"}
    for family, prefix in (("Binomial", "bin/"), ("Poisson", "cnt/")):
        add(
            "statsmodels.api.GLM",
            family.lower(),
            prefix,
            ["$y", "$X"],
            {"family": f"$call:statsmodels.api.families.{family}"},
            glm_fields,
            [("fit", {})],
        )
    add("statsmodels.api.Logit", "default", "bin/", ["$y", "$X"], {}, FIT, [("fit", {"disp": 0})])

    z = "statsmodels.stats.proportion.proportions_ztest"
    add(z, "default", "prop/", ["$count", "$nobs"], {"value": 0.5}, TWO)
    add(z, "null_pooled", "prop/one/", ["$count", "$nobs"], {"value": 0.5, "prop_var": 0.5}, TWO)
    confint = "statsmodels.stats.proportion.proportion_confint"
    for method in ("normal", "agresti_coull", "beta", "wilson", "jeffreys", "binom_test"):
        add(
            confint,
            method,
            "prop/one/",
            ["$count", "$nobs"],
            {"method": method},
            {"low": "[0]", "high": "[1]"},
        )
    add(
        "statsmodels.stats.proportion.binom_test",
        "default",
        "prop/one/",
        ["$count", "$nobs"],
        {},
        {"pvalue": ""},
    )

    multi = "statsmodels.stats.multitest.multipletests"
    fields = {"reject": "[0]", "pvals_corrected": "[1]", "sidak": "[2]", "bonferroni": "[3]"}
    for method in ("fdr_bh", "fdr_by", "holm", "hommel", "bonferroni", "sidak"):
        add(multi, method, "plist/", ["$pvals"], {"method": method}, fields)

    dw = "statsmodels.stats.stattools.durbin_watson"
    add(dw, "default", "ts/", ["$x"], {}, {"value": ""})
    add(dw, "default", "one/ties/", ["$x"], {}, {"value": ""})
    lb = "statsmodels.stats.diagnostic.acorr_ljungbox"
    lb_fields = {"lb_stat": ".lb_stat", "lb_pvalue": ".lb_pvalue"}
    add(lb, "lags5", "ts/", ["$x"], {"lags": [5]}, lb_fields)
    add(
        lb,
        "box_pierce",
        "ts/",
        ["$x"],
        {"lags": [5], "boxpierce": True},
        lb_fields | {"bp_stat": ".bp_stat", "bp_pvalue": ".bp_pvalue"},
    )

    arima = "statsmodels.tsa.arima.model.ARIMA"
    arima_fields = FIT | {"aic": ".aic"}
    for name, order in (("101", [1, 0, 1]), ("200", [2, 0, 0]), ("111", [1, 1, 1])):
        add(arima, name, "ts/", ["$x"], {"order": order}, arima_fields, [("fit", {})])

    add("statsmodels.tsa.stattools.adfuller", "default", "ts/", ["$x"], {}, TWO)
    add("statsmodels.tsa.stattools.kpss", "default", "ts/", ["$x"], {"nlags": "auto"}, TWO)
    norm_inputs = ("one/norm/n30", "one/lognormal/n30", "one/ties/n30", "one/constant/n10")
    for key in norm_inputs:
        for fn in (
            "statsmodels.stats.diagnostic.lilliefors",
            "statsmodels.stats.stattools.jarque_bera",
        ):
            calls.append(_call("statsmodels", fn, "default", key, ["$x"], {}, TWO))
    for key in ("two/null/30x30", "two/shift0.6/30x30", "two/ties/8x8", "two/constant-both/10x10"):
        calls.append(
            _call(
                "statsmodels",
                "statsmodels.stats.weightstats.ttest_ind",
                "default",
                key,
                ["$x", "$y"],
                {},
                TWO | {"df": "[2]"},
            )
        )
        calls.append(
            _call(
                "statsmodels",
                "statsmodels.stats.weightstats.ztest",
                "default",
                key,
                ["$x", "$y"],
                {},
                TWO,
            )
        )
    for key in ("table/small/a", "table/small/d", "table/large/b", "table/zero-diagonal"):
        calls.append(
            _call(
                "statsmodels",
                "statsmodels.stats.contingency_tables.mcnemar",
                "default",
                key,
                ["$table"],
                {},
                ATTR,
            )
        )
    return calls


def _control_calls() -> list[dict]:
    rank = S + "rankdata"
    pmean = S + "pmean"
    calls = [
        _call("scipy", rank, m, "control/rank-ints", ["$x"], {"method": m}, {"ranks": ""})
        for m in ("average", "min", "max", "dense", "ordinal")
    ]
    calls.append(
        _call(
            "scipy",
            S + "binomtest",
            "attributes",
            "control/binom",
            ["$k"],
            {"n": "$n", "p": "$p"},
            {"k": ".k", "n": ".n"},
        )
    )
    calls.append(
        _call(
            "scipy",
            S + "multinomial.pmf",
            "unnormalised",
            "control/multinomial-unnormalised",
            ["$x"],
            {"n": "$n", "p": "$p"},
            {"value": ""},
        )
    )
    calls.append(
        _call(
            "scipy",
            S + "spearmanr",
            "matrix",
            "control/spearman-matrix",
            ["$x"],
            {},
            {"statistic": "[0]", "pvalue": "[1]"},
        )
    )
    calls.append(
        _call(
            "scipy",
            pmean,
            "tiny-p",
            "control/pmean",
            ["$x"],
            {"p": 1e-9},
            {"value": ""},
        )
    )
    for call in calls:
        call["group"] = "control"
    return calls


def build() -> dict:
    inputs: dict[str, dict] = {}
    for part in (
        _one_inputs,
        _two_inputs,
        _paired_inputs,
        _k_inputs,
        _bivariate_inputs,
        _regression_inputs,
        _series_inputs,
        _table_inputs,
        _binom_inputs,
        _multinomial_inputs,
        _pvalue_inputs,
        _proportion_inputs,
        _control_inputs,
    ):
        inputs |= part()
    calls = _scipy_calls(inputs) + _control_calls() + _statsmodels_calls(inputs)
    ids = [c["id"] for c in calls]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate call ids")
    missing = {c["input"] for c in calls} - set(inputs)
    if missing:
        raise ValueError(f"calls without inputs: {sorted(missing)}")
    used = {c["input"] for c in calls}
    return {"seed": SEED, "inputs": {k: v for k, v in inputs.items() if k in used}, "calls": calls}


def dumps(battery: dict) -> bytes:
    return json.dumps(battery, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write(directory: Path) -> str:
    """Write battery.json and its hash. Refuses to replace a different frozen battery."""
    raw = dumps(build())
    digest = sha256(raw)
    pin = directory / "battery.sha256"
    if pin.exists() and pin.read_text(encoding="ascii").strip() != digest:
        raise ValueError("rebuilt battery differs from the frozen hash; bump it deliberately")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "battery.json").write_bytes(raw)
    pin.write_text(digest + "\n", encoding="ascii")
    return digest
