"""Real changes the instrument must find: one historical, and the study's positive controls."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from statdrift import diff, notes, report

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def test_mannwhitneyu_rewrite_in_1_7_is_found_and_flips_verdicts():
    _, old = diff.load(FIXTURES / "scipy-1.6.3-mannwhitneyu.jsonl")
    _, new = diff.load(FIXTURES / "scipy-1.7.3-mannwhitneyu.jsonl")
    tally, changes = diff.compare(old, new)
    default = [c for c in changes if c.variant == "default" and c.kind == "p"]
    assert len(default) > 20  # the default went from one-sided to two-sided
    assert any(c.flips for c in default)
    assert diff.function_units(changes)["scipy.stats.mannwhitneyu"]["material"] > 0
    assert tally["grid"][diff.API_ADDED] > 0  # `method` is new in 1.7, which is not drift
    text = (FIXTURES / "scipy-1.7.0-notes.rst").read_text(encoding="utf-8")
    named = notes.tiers_naming("scipy.stats.mannwhitneyu", [text])
    assert named[notes.NARRATIVE]


def summary() -> dict:
    path = ROOT / "results" / "summary.json"
    if not path.exists():
        pytest.skip("no study results")
    return json.loads(path.read_text(encoding="utf-8"))


def test_every_positive_control_is_found():
    controls = summary()["controls"]
    assert set(controls) == {"/".join(key) for key in report.CONTROLS}
    missed = [name for name, control in controls.items() if not control["found"]]
    assert not missed


def test_every_environment_ran_the_frozen_battery():
    pin = (ROOT / "battery" / "battery.sha256").read_text(encoding="ascii").strip()
    assert summary()["battery_sha256"] == pin


def test_report_tables_are_copied_from_the_summary():
    report_path = ROOT / "REPORT.md"
    if not report_path.exists():
        pytest.skip("no report")
    source = (ROOT / "results" / "summary.md").read_text(encoding="utf-8")
    rows = [
        line
        for line in report_path.read_text(encoding="utf-8").splitlines()
        if line.startswith("| ") and "(by hand)" not in line
    ]
    assert rows
    missing = [line for line in rows if line not in source]
    assert not missing
