"""Helpers to write synthetic result files in the runner's format."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def make_row(fn="scipy.stats.f", variant="default", input_="in", field="pvalue", value=0.5, **kw):
    row = {
        "call": 0,
        "fn": fn,
        "variant": variant,
        "input": input_,
        "field": field,
        "kind": "p" if field.startswith("pvalue") else "x",
        "group": "grid",
        "value": value,
        "dtype": "float64",
        "warnings": [],
        "exception": None,
    }
    return row | kw


def write_results(path: Path, rows: list[dict]) -> Path:
    lines = [json.dumps({"meta": {"platform": "test", "battery_sha256": "x"}})]
    lines += [json.dumps(row) for row in rows]
    lines.append(json.dumps({"end": len(rows)}))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def results(tmp_path):
    return lambda name, rows: write_results(tmp_path / name, rows)
