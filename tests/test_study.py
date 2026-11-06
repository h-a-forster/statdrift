"""Resume, and survival of a hung or crashing call, against a stand-in runner."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from statdrift import diff, study

FAKE = """
import argparse, json, sys, time
p = argparse.ArgumentParser()
for a in ("--battery", "--out", "--lib"):
    p.add_argument(a)
p.add_argument("--start", type=int)
a = p.parse_args()
calls = json.load(open(a.battery))["calls"]
with open(a.out, "a", newline="\\n") as out:
    if a.start == 0:
        out.write(json.dumps({"meta": {}}) + "\\n")
    for i in range(a.start, len(calls)):
        print(i, flush=True)
        if calls[i]["input"] == "hang":
            time.sleep(60)
        if calls[i]["input"] == "crash":
            sys.exit(3)
        row = dict(call=i, fn=calls[i]["fn"], variant="v", input=calls[i]["input"], field="p",
                   kind="p", group="grid", value=0.5, dtype="float64", warnings=[], exception=None)
        out.write(json.dumps(row) + "\\n")
        out.flush()
    out.write(json.dumps({"end": len(calls)}) + "\\n")
"""


def stand_in(tmp_path: Path, inputs: list[str]) -> Path:
    calls = [
        {"id": name, "lib": "scipy", "fn": "f", "variant": "v", "input": name, "group": "grid"}
        for name in inputs
    ]
    (tmp_path / "battery").mkdir()
    (tmp_path / "battery" / "battery.json").write_text(json.dumps({"calls": calls}))
    script = tmp_path / "fake.py"
    script.write_text(FAKE)
    return script


def test_hang_and_crash_become_rows_and_the_run_finishes(tmp_path, monkeypatch):
    monkeypatch.setattr(study, "RUNNER", stand_in(tmp_path, ["a", "hang", "b", "crash", "c"]))
    out = tmp_path / "results" / "x.jsonl"
    failures = study.run_battery(Path(sys.executable), "scipy", out, tmp_path, timeout=3.0)
    assert failures == {"timeouts": 1, "crashes": 1}
    _, calls = diff.load(out)
    assert calls[("f", "v", "hang")]["*"]["exception"] == "Timeout"
    assert calls[("f", "v", "crash")]["*"]["exception"].startswith("Crash")
    assert calls[("f", "v", "c")]["p"]["value"] == 0.5


def test_resume_drops_a_torn_tail_and_reruns_the_last_call(tmp_path):
    path = tmp_path / "r.jsonl"
    rows = [{"meta": {}}, {"call": 0}, {"call": 1}, {"call": 1}]
    path.write_bytes(b"".join(json.dumps(r).encode() + b"\n" for r in rows) + b'{"call": 2')
    assert study.resume_point(path) == 1
    assert len(path.read_bytes().splitlines()) == 2


def test_finished_file_is_skipped_and_absent_file_starts_at_zero(tmp_path):
    path = tmp_path / "r.jsonl"
    assert study.resume_point(path) == 0
    path.write_text('{"meta": {}}\n{"end": 0}\n')
    assert study.resume_point(path) is None


def test_a_second_concurrent_run_is_refused_and_a_finished_one_leaves_no_lock(tmp_path):
    with study.run_lock(tmp_path), pytest.raises(RuntimeError, match="another run"):
        study.run_lock(tmp_path).__enter__()
    with study.run_lock(tmp_path):
        pass


def test_a_header_with_the_wrong_version_is_refused(tmp_path):
    env = study.Env("scipy", "1.9.3", "t1", (("numpy", "1.25.2"), ("scipy", "1.9.3")), "3.11")
    path = tmp_path / "r.jsonl"
    meta = {"battery_sha256": "h", "versions": {"numpy": "1.25.2", "scipy": "1.10.0"}}
    path.write_text(json.dumps({"meta": meta}) + "\n")
    with pytest.raises(ValueError, match="not 1.9.3"):
        study.check_header(env, path, "h")
