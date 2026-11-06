"""The frozen battery is what the builder makes."""

from __future__ import annotations

from pathlib import Path

import pytest

from statdrift import battery

ROOT = Path(__file__).resolve().parents[1]


def test_frozen_battery_matches_its_hash_and_its_builder():
    raw = (ROOT / "battery" / "battery.json").read_bytes()
    pin = (ROOT / "battery" / "battery.sha256").read_text(encoding="ascii").strip()
    assert battery.sha256(raw) == pin
    assert battery.dumps(battery.build()) == raw


def test_write_refuses_to_replace_a_different_battery(tmp_path):
    (tmp_path / "battery.sha256").write_text("0" * 64, encoding="ascii")
    with pytest.raises(ValueError, match="frozen hash"):
        battery.write(tmp_path)


def test_controls_are_kept_out_of_the_grid():
    for call in battery.build()["calls"]:
        assert (call["group"] == "control") == call["input"].startswith("control/")
