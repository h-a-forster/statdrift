"""Resume, and survival of a hung or crashing call, against a stand-in runner."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from statdrift import cli, diff, report, study

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
        name = calls[i]["input"]
        print("\\nstatdrift-call", i, flush=True)
        if name == "hang":
            time.sleep(60)
        if name == "crash":
            sys.exit(3)
        while name == "chatty-hang":
            print("iteration", flush=True)
            time.sleep(0.05)
        if name == "noise":
            sys.stdout.buffer.write(b"\\x81 no newline")
            sys.stdout.flush()
        row = dict(call=i, fn=calls[i]["fn"], variant="v", input=name, field="p", kind="p",
                   group="grid", value=0.5, dtype="float64", warnings=[], exception=None)
        if name == "torn":
            out.write(json.dumps(row)[:20])
            out.flush()
            time.sleep(60)
        out.write(json.dumps(row) + "\\n")
        out.flush()
        if name == "finished-late":
            time.sleep(60)
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


def test_a_call_stopped_at_the_deadline_leaves_exactly_one_failed_row(tmp_path, monkeypatch):
    names = ["a", "finished-late", "torn", "chatty-hang", "noise", "b"]
    monkeypatch.setattr(study, "RUNNER", stand_in(tmp_path, names))
    out = tmp_path / "results" / "x.jsonl"
    failures = study.run_battery(Path(sys.executable), "scipy", out, tmp_path, timeout=2.0)
    assert failures == {"timeouts": 3, "crashes": 0}
    _, calls = diff.load(out)
    for name in ("finished-late", "torn", "chatty-hang"):
        assert set(calls[("f", "v", name)]) == {"*"}
    assert calls[("f", "v", "noise")]["p"]["value"] == 0.5
    assert calls[("f", "v", "b")]["p"]["value"] == 0.5


def test_a_runner_that_never_starts_is_an_error_not_a_row_per_call(tmp_path, monkeypatch):
    stand_in(tmp_path, ["a", "b"])
    broken = tmp_path / "broken.py"
    broken.write_text("import sys\nsys.exit(3)\n")
    monkeypatch.setattr(study, "RUNNER", broken)
    out = tmp_path / "results" / "x.jsonl"
    with pytest.raises(RuntimeError, match="before its first call"):
        study.run_battery(Path(sys.executable), "scipy", out, tmp_path, timeout=30.0)
    assert not out.exists()


def real_run(tmp_path: Path, name: str, *calls: tuple) -> dict:
    """Calls of (fn, args, kwargs, fields) through the real runner under this interpreter."""
    rows = [
        {"id": f"{name}{i}", "lib": "scipy", "fn": fn, "variant": f"v{i}", "input": "in"}
        | {"group": "grid", "args": args, "kwargs": kwargs, "fields": fields}
        for i, (fn, args, kwargs, fields) in enumerate(calls)
    ]
    data = {"inputs": {"in": {"x": [1.0, 2.0, 3.0, 4.0], "y": [2.0, 1.0, 4.0, 3.5]}}}
    (tmp_path / "battery").mkdir(exist_ok=True)
    (tmp_path / "battery" / "battery.json").write_text(json.dumps(data | {"calls": rows}))
    out = tmp_path / "results" / f"{name}.jsonl"
    study.run_battery(Path(sys.executable), "scipy", out, tmp_path, timeout=60.0)
    return diff.load(out)[1]


def test_a_library_writing_to_stdout_neither_stops_a_run_nor_shifts_the_blame(tmp_path):
    # No newline: the runner's next line must not merge with this one.
    chatter = ("builtins.print", ["chatter"], {"end": ""}, {"x": "[0]"})
    calls = real_run(tmp_path, "a", chatter, ("os._exit", [3], {}, {}))
    assert calls[("builtins.print", "v0", "in")]["x"]["exception"] == "TypeError"
    assert calls[("os._exit", "v1", "in")]["*"]["exception"] == "Crash:3"


def test_a_release_that_drops_every_field_is_a_status_change(tmp_path):
    fn = "scipy.stats.ttest_ind"
    old = real_run(tmp_path, "old", (fn, ["$x", "$y"], {}, {"pvalue": ".pvalue", "df": ".df"}))
    new = real_run(tmp_path, "new", (fn, ["$x", "$y"], {}, {"pvalue": ".renamed", "df": ".gone"}))
    tally, changes = diff.compare(old, new)
    assert tally["grid"][diff.STATUS] == 2
    assert all(c.material for c in changes)


def test_a_file_from_another_battery_is_refused(tmp_path, results):
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "study.toml").write_text(
        '[toolchains.t]\npython = "3.11"\nnumpy = "1"\n'
        '[[chains]]\nlib = "scipy"\ntoolchain = "t"\nversions = ["1.0.0", "1.1.0"]\n'
    )
    (tmp_path / "battery").mkdir()
    (tmp_path / "battery" / "battery.sha256").write_text("x\n")
    (tmp_path / "results").mkdir()
    stability = {name: {"unstable": []} for name in ("scipy-1.0.0-t", "scipy-1.1.0-t")}
    (tmp_path / "results" / "repeatability.json").write_text(json.dumps(stability))
    results("results/scipy-1.0.0-t.jsonl", [])
    other = results("results/scipy-1.1.0-t.jsonl", [])
    other.write_text(other.read_text().replace('"battery_sha256": "x"', '"battery_sha256": "y"'))
    with pytest.raises(ValueError, match="scipy-1.1.0-t: run against a different battery"):
        report.analyse(tmp_path)


def test_the_command_refuses_to_run_outside_a_checkout(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(study, "ROOT", tmp_path)
    with pytest.raises(SystemExit):
        cli.main(["battery"])
    assert "checkout" in capsys.readouterr().err
    assert not (tmp_path / "battery").exists()


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
