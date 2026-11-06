"""Turn result files into summary.json, summary.md, documented.csv and changes.jsonl."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from . import diff, notes, study

# Changes the SciPy 1.18.0 notes announce, as (function, variant) -> what must be seen in
# 1.17.1 -> 1.18.1. They are the instrument's positive controls, outside every estimand.
# None means no change: 1.18.1 reverted the binomtest attribute types (scipy#25509).
CONTROLS = {
    ("scipy.stats.rankdata", "min"): diff.DTYPE,
    ("scipy.stats.rankdata", "max"): diff.DTYPE,
    ("scipy.stats.rankdata", "dense"): diff.DTYPE,
    ("scipy.stats.rankdata", "ordinal"): diff.DTYPE,
    ("scipy.stats.binomtest", "attributes"): None,
    ("scipy.stats.multinomial.pmf", "unnormalised"): diff.STATUS,
    ("scipy.stats.spearmanr", "matrix"): diff.STATUS,
    ("scipy.stats.pmean", "tiny-p"): diff.NUMERIC,
}


# Input ids naming degenerate data: what a reader should discount before asking "does this
# touch my analysis?". Ties, small n and heavy tails are ordinary data and stay out.
DEGENERATE = (
    "nan",
    "constant",
    "all-zero",
    "exact-fit",
    "perfect",
    "separated",
    "collinear",
    "extreme",
    "zero-",
    "wrong-n",
    "impossible",
    "mostly-zero",
)


def is_degenerate(input_id: str) -> bool:
    return any(token in input_id for token in DEGENERATE)


def _pair(lib: str, tool_a: str, a: str, tool_b: str, b: str, scope: str) -> dict:
    return {
        "lib": lib,
        "scope": scope,
        "a": a,
        "b": b,
        "tool_a": tool_a,
        "tool_b": tool_b,
        "env_a": f"{lib}-{a}-{tool_a}",
        "env_b": f"{lib}-{b}-{tool_b}",
    }


def study_pairs(config: dict) -> list[dict]:
    """Every comparison the study makes, with the scope it belongs to."""
    out = []
    seen: dict[tuple[str, str], str] = {}
    for chain in config["chains"]:
        lib, tool, versions = chain["lib"], chain["toolchain"], chain["versions"]
        limit = chain.get("overlap_until")
        split = versions.index(limit) if limit else -1
        for i, (a, b) in enumerate(zip(versions, versions[1:], strict=False)):
            out.append(_pair(lib, tool, a, tool, b, "overlap" if i < split else "primary"))
        out.append(_pair(lib, tool, versions[0], tool, versions[-1], "span"))
        for version in versions:
            other = seen.get((lib, version))
            if other:
                out.append(_pair(lib, other, version, tool, version, "toolchain"))
            seen[(lib, version)] = tool
    return out


def repeatability(root: Path, config: dict) -> dict:
    """Compare each env's two runs. Cells that are not bitwise equal count as unstable."""
    out = {}
    for env in study.environments(config):
        first = root / "results" / f"{env.name}.jsonl"
        second = root / "results" / "repeat" / f"{env.name}.jsonl"
        one, two = first.read_bytes(), second.read_bytes()
        record: dict = {
            "sha256": hashlib.sha256(one).hexdigest(),
            "repeat_sha256": hashlib.sha256(two).hexdigest(),
            "identical": one == two,
            "unstable": [],
        }
        if one != two:
            _, a = diff.load(first)
            _, b = diff.load(second)
            for key in sorted(a):
                for field in sorted(a[key].keys() | b[key].keys()):
                    ra, rb = a[key].get(field), b[key].get(field)
                    same = ra and rb and diff.shown(ra) == diff.shown(rb)
                    if not (same and ra["dtype"] == rb["dtype"]):
                        record["unstable"].append([*key, field])
        out[env.name] = record
    path = root / "results" / "repeatability.json"
    path.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    return out


def _rate(tally: dict) -> dict:
    cells = tally.get("cells", 0)
    changed = tally.get(diff.NUMERIC, 0) + tally.get(diff.STATUS, 0)
    return {"changed": changed, "cells": cells, "rate": changed / cells if cells else 0.0}


def _documented(units: list[dict], tier: str, subset: str | None) -> dict:
    chosen = [u for u in units if subset is None or u[subset]]
    hits = sum(bool(u[tier]) for u in chosen)
    interval = diff.clopper_pearson(hits, len(chosen)) if chosen else (None, None)
    return {
        "hits": hits,
        "units": len(chosen),
        "share": hits / len(chosen) if chosen else None,
        "ci95": interval,
    }


def _load_coding(root: Path) -> dict[tuple[str, str], dict]:
    path = root / "results" / "coding.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        return {(row["step"], row["fn"]): row for row in csv.DictReader(handle)}


def _failures(loaded: dict[str, dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for env, calls in loaded.items():
        rows = (fields.get("*") for fields in calls.values())
        bad = sum(1 for r in rows if r and r["exception"].startswith(("Timeout", "Crash")))
        if bad:
            out[env] = bad
    return out


def _historical(root: Path) -> dict:
    """The mannwhitneyu rewrite, from real rows of SciPy 1.6.3 and 1.7.3."""
    fixtures = root / "tests" / "fixtures"
    _, old = diff.load(fixtures / "scipy-1.6.3-mannwhitneyu.jsonl")
    _, new = diff.load(fixtures / "scipy-1.7.3-mannwhitneyu.jsonl")
    tally, changes = diff.compare(old, new)
    default = [c for c in changes if c.variant == "default" and c.kind == "p"]
    grid = tally["grid"]
    return {
        "cells": grid["cells"],
        "changed": grid.get(diff.NUMERIC, 0) + grid.get(diff.STATUS, 0),
        "default_p_changed": len(default),
        "default_p_flipped": sum(1 for c in default if c.flips),
        "p_cells": grid["p_cells"],
        "p_flipped": grid.get("p_flipped", 0),
    }


def analyse(root: Path = study.ROOT) -> dict:
    config = study.load_config(root)
    stability = json.loads((root / "results" / "repeatability.json").read_text(encoding="utf-8"))
    loaded: dict[str, dict] = {}
    metas: dict[str, dict] = {}

    def calls(env: str) -> dict:
        if env not in loaded:
            metas[env], loaded[env] = diff.load(root / "results" / f"{env}.jsonl")
        return loaded[env]

    def unstable(*envs: str) -> set[tuple]:
        """A call with any field that did not repeat is not a measurement, in any field."""
        return {tuple(cell[:3]) for env in envs for cell in stability[env]["unstable"]}

    summary: dict = {"pairs": [], "documented": {}, "controls": {}, "inputs": {}}
    all_changes: list[dict] = []
    units: dict[str, list[dict]] = {"scipy": [], "statsmodels": []}
    changed_cells: dict[tuple, set] = {}
    coding = _load_coding(root)
    for pair in study_pairs(config):
        ea, eb = pair["env_a"], pair["env_b"]
        tally, changes = diff.compare(calls(ea), calls(eb), unstable(ea, eb))
        grid = [c for c in changes if c.group == "grid"]
        fns = diff.function_units(grid)
        record = pair | {
            "tally": tally,
            "stats": _rate(tally.get("grid", {})),
            "stochastic": _rate(tally.get("stochastic", {})),
            "functions_total": len(
                {k[0] for k, f in calls(eb).items() if next(iter(f.values()))["group"] == "grid"}
            ),
            "functions_changed": len(fns),
            "functions_material": sum(1 for u in fns.values() if u["material"]),
            "magnitude": diff.magnitude(grid),
        }
        summary["pairs"].append(record)
        step = f"{pair['a']} -> {pair['b']}"
        scope = pair["scope"]
        if scope in ("primary", "overlap"):
            changed_cells[(pair["lib"], pair["a"], pair["b"], pair["tool_b"])] = {
                (c.fn, c.variant, c.input, c.field) for c in grid if c.label != diff.DTYPE
            }
        if scope in ("primary", "overlap", "toolchain"):
            tag = f"{pair['lib']} {step} {pair['tool_a']}/{pair['tool_b']}"
            all_changes += [{"pair": tag, "scope": scope} | asdict(c) for c in changes]
        if scope == "primary":
            where = summary["inputs"].setdefault(pair["lib"], _new_input_tally())
            for c in grid:
                if c.label != diff.DTYPE:
                    row = where["degenerate" if is_degenerate(c.input) else "ordinary"]
                    row["changed"] += 1
                    row["numeric"] += c.label == diff.NUMERIC
                    row["material"] += c.material
                    row["flips"] += bool(c.flips)
                    row["functions"].add((step, c.fn))
        if scope == "primary":
            texts = notes.notes_for(pair["lib"], pair["b"], root)
            for fn, unit in sorted(fns.items()):
                named = notes.tiers_naming(fn, texts)
                row = {"lib": pair["lib"], "step": step, "fn": fn} | unit
                row |= {tier: len(lines) for tier, lines in named.items()}
                row["is_material"] = unit["material"] > 0
                row["is_flip"] = unit["flips"] > 0
                row["coded"] = coding.get((step, fn), {}).get("verdict", "")
                row["explained"] = row["coded"] == "explained"
                row["pointed"] = row["coded"] in ("explained", "pointer")
                units[pair["lib"]].append(row)
            if pair["b"] == "1.18.1":
                seen = {(c.fn, c.variant): c.label for c in changes if c.group == "control"}
                for key, label in CONTROLS.items():
                    summary["controls"]["/".join(key)] = {
                        "expected": label,
                        "seen": seen.get(key),
                        "found": seen.get(key) == label,
                    }

    for lib, rows in units.items():
        uncoded = [r["fn"] for r in rows if r["is_material"] and not r["coded"]]
        if coding and uncoded:
            raise ValueError(f"material units without a verdict in coding.csv: {uncoded}")
        coded_tiers = ("pointed", "explained") if coding else ()
        summary["documented"][lib] = {
            "all": {tier: _documented(rows, tier, None) for tier in notes.TIERS},
            **{
                subset: {
                    tier: _documented(rows, tier, subset) for tier in (*notes.TIERS, *coded_tiers)
                }
                for subset in ("is_material", "is_flip")
            },
            "units": rows,
        }
    for where in summary["inputs"].values():
        for row in where.values():
            row["functions"] = len(row["functions"])
    summary["overlap"] = []
    for (lib, a, b, tool), cells in changed_cells.items():
        twin = changed_cells.get((lib, a, b, "t1"))
        if tool == "t2" and twin is not None:
            summary["overlap"].append(
                {
                    "step": f"{a} -> {b}",
                    "t1": len(twin),
                    "t2": len(cells),
                    "both": len(twin & cells),
                }
            )
    summary["repeatability"] = {
        "envs": len(stability),
        "identical": sum(1 for r in stability.values() if r["identical"]),
        "unstable_cells": sum(len(r["unstable"]) for r in stability.values()),
    }
    summary["platforms"] = sorted({m["platform"] for m in metas.values()})
    summary["battery_sha256"] = next(iter(metas.values()))["battery_sha256"]
    summary["failures"] = _failures(loaded)
    summary["historical"] = _historical(root)
    return {"summary": summary, "changes": all_changes}


def _new_input_tally() -> dict:
    fields = {"changed": 0, "numeric": 0, "material": 0, "flips": 0}
    return {kind: fields | {"functions": set()} for kind in ("ordinary", "degenerate")}


def _input_table(inputs: dict) -> list[str]:
    lines = [
        "| Library | Inputs | Changed cells | Numeric | Material | p flips | Function-releases |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for lib, where in inputs.items():
        for kind, r in where.items():
            lines.append(
                f"| {lib} | {kind} | {r['changed']} | {r['numeric']} | {r['material']} | "
                f"{r['flips']} | {r['functions']} |"
            )
    return lines


def _percent(x: float | None, digits: int = 2) -> str:
    return "n/a" if x is None else f"{100 * x:.{digits}f}%"


def _step_table(pairs: list[dict]) -> list[str]:
    lines = [
        "| Step | Toolchain | Changed cells | of cells | Rate | of which status | Functions "
        "changed | material | p cells | flip 0.05 | flip 0.01 | p lost |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for p in pairs:
        t, s = p["tally"].get("grid", {}), p["stats"]
        tool = p["tool_b"] if p["tool_a"] == p["tool_b"] else f"{p['tool_a']}/{p['tool_b']}"
        lines.append(
            f"| {p['a']} -> {p['b']} | {tool} | {s['changed']} | {s['cells']} | "
            f"{_percent(s['rate'])} | {t.get(diff.STATUS, 0)} | "
            f"{p['functions_changed']}/{p['functions_total']} | {p['functions_material']} | "
            f"{t.get('p_cells', 0)} | {t.get('flip0.05', 0)} | {t.get('flip0.01', 0)} | "
            f"{t.get('p_lost', 0)} |"
        )
    return lines


def _totals_table(pairs: list[dict]) -> list[str]:
    lines = [
        "| Library | Steps | Changed cells | of cells | Rate | Function-releases changed | "
        "of | material | p cells | p flipped | p lost |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for lib in ("scipy", "statsmodels"):
        chosen = [p for p in pairs if p["lib"] == lib]
        tallies = [p["tally"].get("grid", {}) for p in chosen]
        changed = sum(p["stats"]["changed"] for p in chosen)
        cells = sum(p["stats"]["cells"] for p in chosen)
        lines.append(
            f"| {lib} | {len(chosen)} | {changed} | {cells} | {_percent(changed / cells)} | "
            f"{sum(p['functions_changed'] for p in chosen)} | "
            f"{sum(p['functions_total'] for p in chosen)} | "
            f"{sum(p['functions_material'] for p in chosen)} | "
            f"{sum(t.get('p_cells', 0) for t in tallies)} | "
            f"{sum(t.get('p_flipped', 0) for t in tallies)} | "
            f"{sum(t.get('p_lost', 0) for t in tallies)} |"
        )
    return lines


def _magnitude_table(pairs: list[dict]) -> list[str]:
    lines = [
        "| Step | Numeric p changes | Median abs(dp) | p90 | Max | <1e-12 | 1e-12..1e-6 | "
        "1e-6..1e-3 | >=1e-3 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for p in pairs:
        m = p["magnitude"]
        if m is None:
            lines.append(f"| {p['a']} -> {p['b']} | 0 | | | | | | | |")
            continue
        bins = " | ".join(str(v) for v in m["bins"].values())
        lines.append(
            f"| {p['a']} -> {p['b']} | {m['n']} | {m['median']:.2g} | {m['p90']:.2g} | "
            f"{m['max']:.2g} | {bins} |"
        )
    return lines


def _documented_table(documented: dict) -> list[str]:
    lines = [
        "| Library | Changed function-releases | Tier | Named | Share | 95% CP interval |",
        "|---|---|---|---:|---:|---|",
    ]
    subsets = (
        ("all", "all (> 1e-9)"),
        ("is_material", "material (> 1e-6 or status)"),
        ("is_flip", "flipped a p-value at 0.05 or 0.01"),
    )
    for lib, data in documented.items():
        for subset, label in subsets:
            for tier, d in data[subset].items():
                low, high = d["ci95"]
                interval = "n/a" if low is None else f"{low:.3f} to {high:.3f}"
                lines.append(
                    f"| {lib} | {label} | {tier} | {d['hits']}/{d['units']} | "
                    f"{_percent(d['share'], 1)} | {interval} |"
                )
    return lines


def _sensitivity_table(pairs: list[dict]) -> list[str]:
    head = " | ".join(f"rel > {t:g}" for t in diff.SENSITIVITY)
    lines = [f"| Library | Cells (all steps) | Bitwise equal | {head} |"]
    lines.append("|---|---:|---:|" + "---:|" * len(diff.SENSITIVITY))
    for lib in ("scipy", "statsmodels"):
        tallies = [p["tally"].get("grid", {}) for p in pairs if p["lib"] == lib]
        cells = sum(t.get("cells", 0) for t in tallies)
        same = sum(t.get("bitwise_same", 0) for t in tallies)
        counts = " | ".join(
            str(sum(t.get(f"rel>{tol:g}", 0) for t in tallies)) for tol in diff.SENSITIVITY
        )
        lines.append(f"| {lib} | {cells} | {same} | {counts} |")
    return lines


def _secondary_table(pairs: list[dict]) -> list[str]:
    lines = [
        "| Step | dtype only | warning only | API added | not applicable | fields added | "
        "fields removed | stochastic changed | of |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for p in pairs:
        t = p["tally"].get("grid", {})
        lines.append(
            f"| {p['a']} -> {p['b']} | {t.get(diff.DTYPE, 0)} | {t.get(diff.WARNING, 0)} | "
            f"{t.get(diff.API_ADDED, 0)} | {t.get(diff.NOT_APPLICABLE, 0)} | "
            f"{t.get('field_added', 0)} | {t.get('field_removed', 0)} | "
            f"{p['stochastic']['changed']} | {p['stochastic']['cells']} |"
        )
    return lines


def render(summary: dict) -> str:
    pairs = summary["pairs"]
    primary = [p for p in pairs if p["scope"] == "primary"]
    rep = summary["repeatability"]
    overlap_rows = [
        f"| {o['step']} | {o['t1']} | {o['t2']} | {o['both']} |" for o in summary["overlap"]
    ]
    control_rows = [
        f"| {name} | {c['expected']} | {c['seen']} | {'yes' if c['found'] else 'NO'} |"
        for name, c in summary["controls"].items()
    ]
    documented = {k: v for k, v in summary["documented"].items() if v["units"]}
    h = summary["historical"]
    out = [
        "# statdrift summary",
        "",
        "Generated by `statdrift diff` from `results/*.jsonl`. Do not edit.",
        "",
        f"Battery sha256 `{summary['battery_sha256']}`. "
        f"Platforms: {', '.join(summary['platforms'])}.",
        "",
        "## Totals over the primary steps (grid, deterministic cells)",
        "",
        *_totals_table(primary),
        "",
        "## Change and decision flips, SciPy (grid, deterministic cells)",
        "",
        *_step_table([p for p in primary if p["lib"] == "scipy"]),
        "",
        "## Change and decision flips, statsmodels (grid, deterministic cells)",
        "",
        *_step_table([p for p in primary if p["lib"] == "statsmodels"]),
        "",
        "## Magnitude of p-value changes",
        "",
        *_magnitude_table(primary),
        "",
        "## Documented share",
        "",
        "Unit: one function in one release step. Tiers: any = named anywhere in that "
        "release's notes except the author list; narrative = outside the issue and "
        "pull-request lists; compatibility = in a backwards-incompatible or deprecation "
        "section; pointed = a reader found a line about the implicated behaviour, whether "
        "or not it said results change; explained = a reader found a line that states this "
        "change (`results/coding.csv`).",
        "",
        *_documented_table(documented),
        "",
        "## Where changes fall (grid cells, primary steps)",
        "",
        "Degenerate means the input id names NaN, constant, all-zero, exact-fit, perfect, "
        "separated, collinear, extreme or similar data (`report.DEGENERATE`). This split "
        "was added after the results were seen.",
        "",
        *_input_table(summary["inputs"]),
        "",
        "## Sensitivity to the change threshold (numeric cells, primary steps)",
        "",
        *_sensitivity_table(primary),
        "",
        "## Secondary counts (grid cells unless stated, primary steps)",
        "",
        *_secondary_table(primary),
        "",
        "## Same steps under the second toolchain",
        "",
        "| Step | Changed cells t1 | Changed cells t2 | Changed in both |",
        "|---|---:|---:|---:|",
        *overlap_rows,
        "",
        *_step_table([p for p in pairs if p["scope"] == "overlap"]),
        "",
        "## Toolchain effect: same release, t1 (Python 3.11, numpy 1.25.2) vs t2 "
        "(Python 3.12, numpy 2.0.2)",
        "",
        *_step_table([p for p in pairs if p["scope"] == "toolchain"]),
        "",
        "## One jump across each chain",
        "",
        *_step_table([p for p in pairs if p["scope"] == "span"]),
        "",
        "## Repeatability on this machine",
        "",
        f"{rep['identical']} of {rep['envs']} environments reproduced their results file "
        f"byte for byte on a second run. {rep['unstable_cells']} cells differed; every field "
        "of those calls is excluded from every count above.",
        "",
        "## Positive controls (SciPy 1.17.1 -> 1.18.1, outside every estimand)",
        "",
        "| Control | Expected | Seen | Found |",
        "|---|---|---|---|",
        *control_rows,
        "",
        "## Historical control: mannwhitneyu, SciPy 1.6.3 -> 1.7.3",
        "",
        f"{h['changed']} of {h['cells']} cells changed. {h['p_flipped']} of {h['p_cells']} "
        f"p-value cells flipped at 0.05 or 0.01. With default arguments, "
        f"{h['default_p_changed']} p-values changed and {h['default_p_flipped']} flipped.",
        "",
        "## Calls that hung or crashed the interpreter",
        "",
        str(summary["failures"] or "None."),
        "",
    ]
    return "\n".join(out)


def write(root: Path = study.ROOT) -> dict:
    result = analyse(root)
    summary = result["summary"]
    out = root / "results"
    rows = [u for lib in ("scipy", "statsmodels") for u in summary["documented"][lib]["units"]]
    with (out / "documented.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = ["lib", "step", "fn", "cells", "material", "status", "flips", "max_delta_p"]
        fields += [*notes.TIERS, "coded"]
        writer = csv.DictWriter(handle, fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    with (out / "changes.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for row in result["changes"]:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    text = json.dumps(summary, indent=1, sort_keys=True) + "\n"
    (out / "summary.json").write_text(text, encoding="utf-8", newline="\n")
    (out / "summary.md").write_text(render(summary), encoding="utf-8", newline="\n")
    return summary
