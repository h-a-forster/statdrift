"""Compare result files release by release. Standard library only.

A cell is (function, variant, input, field). Definitions are in docs/DESIGN.md section 5.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

TOL = 1e-9  # relative change that counts as a change
MATERIAL = 1e-6  # relative change beyond floating-point noise for any reader
ABS_FLOOR = 1e-12  # for non-p fields, so rounding around zero is not a change
P_FLOOR = 1e-300  # p-values keep their relative scale down to the subnormals
SENSITIVITY = (1e-12, 1e-9, 1e-6, 1e-3)
ALPHAS = (0.05, 0.01)
KEYWORD = "TypeError:unexpected-keyword"

SAME = "same"
NUMERIC = "numeric"
STATUS = "status"
DTYPE = "dtype"
WARNING = "warning"
API_ADDED = "api_added"
NOT_APPLICABLE = "not_applicable"

Key = tuple[str, str, str]  # fn, variant, input


def is_number(value: object) -> bool:
    return isinstance(value, bool | int | float)


def load(path: Path) -> tuple[dict, dict[Key, dict[str, dict]]]:
    """Read a results file. Fails on a file with no end marker: partial runs are not data."""
    meta: dict = {}
    calls: dict[Key, dict[str, dict]] = defaultdict(dict)
    complete = False
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if "meta" in row:
                meta = row["meta"]
            elif "end" in row:
                complete = True
            else:
                calls[(row["fn"], row["variant"], row["input"])][row["field"]] = row
    if not complete:
        raise ValueError(f"{path.name} has no end marker: the run did not finish")
    return meta, dict(calls)


def relative(a: float, b: float) -> float:
    if a == b:
        return 0.0
    return abs(a - b) / max(abs(a), abs(b))


def floor_for(kind: str) -> float:
    return P_FLOOR if kind == "p" else ABS_FLOOR


def differs(a: float, b: float, kind: str, tol: float) -> bool:
    return relative(a, b) > tol and abs(a - b) > floor_for(kind)


def classify(a: dict, b: dict) -> str:
    """Label one pair of rows, in order of what a user would notice first."""
    if a["field"] != b["field"] and "*" not in (a["field"], b["field"]):
        return STATUS  # the output changed shape, say from a scalar NaN to a matrix
    ea, eb = a["exception"], b["exception"]
    if ea == KEYWORD:
        return NOT_APPLICABLE if eb == KEYWORD else API_ADDED
    if ea or eb:
        return SAME if ea == eb else STATUS
    va, vb = a["value"], b["value"]
    if is_number(va) and is_number(vb):
        if differs(float(va), float(vb), b["kind"], TOL):
            return NUMERIC
    elif va != vb:
        return STATUS
    if a["dtype"] != b["dtype"]:
        return DTYPE
    return WARNING if a["warnings"] != b["warnings"] else SAME


def pairs_of(a: dict[str, dict], b: dict[str, dict]) -> list[tuple[str, dict | None, dict | None]]:
    """Match fields of one call. A call that raised on one side covers all the other's fields."""
    if "*" in a and "*" not in b:
        return [(f, a["*"], row) for f, row in sorted(b.items())] or [("*", a["*"], None)]
    if "*" in b and "*" not in a:
        return [(f, row, b["*"]) for f, row in sorted(a.items())] or [("*", None, b["*"])]
    out: list[tuple[str, dict | None, dict | None]] = []
    for stem in sorted({f.split("[")[0] for f in a.keys() | b.keys()}):
        left = {f: row for f, row in a.items() if f.split("[")[0] == stem}
        right = {f: row for f, row in b.items() if f.split("[")[0] == stem}
        if left and right and left.keys() != right.keys():
            # The output changed shape, say from a scalar NaN to a matrix: each leaf of the
            # larger side is one cell, set against the smaller side's matching or first leaf.
            if len(left) >= len(right):
                first = right[min(right)]
                out += [(f, row, right.get(f, first)) for f, row in sorted(left.items())]
            else:
                first = left[min(left)]
                out += [(f, left.get(f, first), row) for f, row in sorted(right.items())]
        else:
            out += [(f, left.get(f), right.get(f)) for f in sorted(left.keys() | right.keys())]
    return out


@dataclass
class Change:
    """One cell that differs between two releases."""

    fn: str
    variant: str
    input: str
    field: str
    kind: str
    group: str
    label: str
    a: object
    b: object
    rel: float | None
    delta_p: float | None
    flips: list[float]

    @property
    def material(self) -> bool:
        if self.label == STATUS:
            return True
        return self.label == NUMERIC and self.rel is not None and self.rel > MATERIAL


def shown(row: dict) -> object:
    return row["exception"] if row["exception"] else row["value"]


def compare(
    a: dict[Key, dict[str, dict]],
    b: dict[Key, dict[str, dict]],
    unstable: set[Key] = frozenset(),
) -> tuple[dict[str, dict[str, int]], list[Change]]:
    """Count cells by group and label, and list every changed cell."""
    if set(a) != set(b):
        raise ValueError("result files cover different calls: not the same battery")
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    changes: list[Change] = []
    for key in sorted(a):
        for field, ra, rb in pairs_of(a[key], b[key]):
            tally = counts[(ra or rb)["group"]]
            if key in unstable:
                tally["unstable"] += 1
            elif ra is None or rb is None:
                tally["field_added" if ra is None else "field_removed"] += 1
            else:
                label = classify(ra, rb)
                if label in (NOT_APPLICABLE, API_ADDED):
                    tally[label] += 1
                else:
                    change = _count_cell(key, field, ra, rb, label, tally)
                    if change is not None:
                        changes.append(change)
    return {group: dict(tally) for group, tally in counts.items()}, changes


def _count_cell(
    key: Key, field: str, ra: dict, rb: dict, label: str, tally: dict[str, int]
) -> Change | None:
    tally["cells"] += 1
    tally[label] += 1
    kind = "p" if "p" in (ra["kind"], rb["kind"]) else "x"
    rel = delta = None
    flips: list[float] = []
    plain = not ra["exception"] and not rb["exception"]
    numbers = plain and is_number(ra["value"]) and is_number(rb["value"])
    if numbers:
        x, y = float(ra["value"]), float(rb["value"])
        rel = relative(x, y)
        for tol in SENSITIVITY:
            if differs(x, y, kind, tol):
                tally[f"rel>{tol:g}"] += 1
        delta = abs(x - y)
    if shown(ra) == shown(rb):
        tally["bitwise_same"] += 1
    if kind == "p":
        tally["p_cells"] += 1
        if numbers:
            flips = [alpha for alpha in ALPHAS if (x < alpha) != (y < alpha)]
            for alpha in flips:
                tally[f"flip{alpha:g}"] += 1
            tally["p_flipped"] += bool(flips)
        elif label == STATUS:
            tally["p_lost"] += 1
    if label not in (NUMERIC, STATUS, DTYPE):
        return None
    if kind != "p":
        delta = None
    return Change(*key, field, kind, ra["group"], label, shown(ra), shown(rb), rel, delta, flips)


def quantile(sorted_values: list[float], q: float) -> float:
    """Empirical quantile (lower order statistic), so every printed value is a real cell."""
    return sorted_values[max(0, math.ceil(q * len(sorted_values)) - 1)]


def magnitude(changes: list[Change]) -> dict | None:
    """Distribution of |delta p| over p-value cells with a numeric change."""
    deltas = sorted(c.delta_p for c in changes if c.label == NUMERIC and c.kind == "p")
    if not deltas:
        return None
    bins = {"<1e-12": 0, "1e-12..1e-6": 0, "1e-6..1e-3": 0, ">=1e-3": 0}
    for value in deltas:
        if value < 1e-12:
            bins["<1e-12"] += 1
        elif value < 1e-6:
            bins["1e-12..1e-6"] += 1
        elif value < 1e-3:
            bins["1e-6..1e-3"] += 1
        else:
            bins[">=1e-3"] += 1
    return {
        "n": len(deltas),
        "median": quantile(deltas, 0.5),
        "p90": quantile(deltas, 0.9),
        "max": deltas[-1],
        "bins": bins,
    }


def function_units(changes: list[Change], group: str = "grid") -> dict[str, dict]:
    """Roll changed cells up to one record per function."""
    out: dict[str, dict] = {}
    for c in changes:
        if c.group != group or c.label == DTYPE:
            continue
        unit = out.setdefault(
            c.fn, {"cells": 0, "material": 0, "status": 0, "flips": 0, "max_delta_p": 0.0}
        )
        unit["cells"] += 1
        unit["material"] += c.material
        unit["status"] += c.label == STATUS
        unit["flips"] += bool(c.flips)
        unit["max_delta_p"] = max(unit["max_delta_p"], c.delta_p or 0.0)
    return out


def _tail_low(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p)."""
    total = 0.0
    for i in range(k + 1):
        log_term = math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1)
        total += math.exp(log_term + i * math.log(p) + (n - i) * math.log1p(-p))
    return min(total, 1.0)


def _bisect(condition) -> float:
    """The point in (0, 1) where `condition` turns from true to false."""
    low, high = 0.0, 1.0
    for _ in range(200):
        middle = (low + high) / 2
        if condition(middle):
            low = middle
        else:
            high = middle
    return (low + high) / 2


def clopper_pearson(k: int, n: int, level: float = 0.95) -> tuple[float, float]:
    """Exact two-sided binomial interval, by bisection on the binomial tails."""
    if not 0 <= k <= n or n == 0:
        raise ValueError(f"need 0 <= k <= n and n > 0, got k={k}, n={n}")
    alpha = (1 - level) / 2
    low = 0.0 if k == 0 else _bisect(lambda p: 1 - _tail_low(k - 1, n, p) < alpha)
    high = 1.0 if k == n else _bisect(lambda p: _tail_low(k, n, p) > alpha)
    return low, high
