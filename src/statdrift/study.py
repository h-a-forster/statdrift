"""Create the pinned environments and run the battery in each, resumably."""

from __future__ import annotations

import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = Path(__file__).with_name("runner.py")
EXCLUDE_NEWER = "2026-10-23T00:00:00Z"
CALL_TIMEOUT = 180.0  # seconds without a finished call before it counts as a hang
THREAD_LIMITS = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")


@dataclass(frozen=True)
class Env:
    lib: str
    version: str
    toolchain: str
    pins: tuple[tuple[str, str], ...]
    python: str

    @property
    def name(self) -> str:
        return f"{self.lib}-{self.version}-{self.toolchain}"


def load_config(root: Path = ROOT) -> dict:
    with (root / "configs" / "study.toml").open("rb") as handle:
        return tomllib.load(handle)


def environments(config: dict) -> list[Env]:
    out = []
    for chain in config["chains"]:
        tool = config["toolchains"][chain["toolchain"]]
        fixed = sorted((k, v) for k, v in tool.items() if k != "python")
        for version in chain["versions"]:
            pins = tuple(sorted({(chain["lib"], version), *fixed}))
            out.append(Env(chain["lib"], version, chain["toolchain"], pins, tool["python"]))
    return out


def select(envs: list[Env], only: str | None) -> list[Env]:
    if only is None:
        return envs
    chosen = [e for e in envs if only in e.name]
    if not chosen:
        raise ValueError(f"no environment matches {only!r}")
    return chosen


def pyproject_text(env: Env) -> str:
    deps = ", ".join(f'"{name}=={version}"' for name, version in env.pins)
    slug = env.name.replace(".", "-")
    return (
        f'[project]\nname = "statdrift-env-{slug}"\nversion = "0"\n'
        f'requires-python = "=={env.python}.*"\ndependencies = [{deps}]\n\n'
        f'[tool.uv]\npackage = false\nexclude-newer = "{EXCLUDE_NEWER}"\n'
    )


def _uv(*args: str, cwd: Path) -> None:
    subprocess.run(["uv", *args], cwd=cwd, check=True)


def create_env(env: Env, root: Path = ROOT, sync: bool = True) -> None:
    """Write the env's project, lock it if the lock is missing or stale, and sync it."""
    directory = root / "envs" / env.name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "pyproject.toml").write_text(pyproject_text(env), encoding="utf-8", newline="\n")
    _uv("lock", "--quiet", "--python", env.python, cwd=directory)
    if sync:
        _uv("sync", "--quiet", "--frozen", "--python", env.python, cwd=directory)


def check_lock(env: Env, root: Path = ROOT) -> None:
    _uv("lock", "--check", "--quiet", "--python", env.python, cwd=root / "envs" / env.name)


def python_of(env: Env, root: Path = ROOT) -> Path:
    venv = root / "envs" / env.name / ".venv"
    return venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def child_environ() -> dict[str, str]:
    """One thread and a fixed hash seed, so a run depends only on the pinned packages."""
    environ = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    environ |= dict.fromkeys(THREAD_LIMITS, "1")
    environ["PYTHONHASHSEED"] = "0"
    return environ


def resume_point(path: Path) -> int | None:
    """Trim a partial file to whole calls. Returns the next call index, None when complete."""
    if not path.exists():
        return 0
    lines = path.read_bytes().splitlines(keepends=True)
    parsed: list[dict] = []
    for line in lines:
        if not line.endswith(b"\n"):
            break
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError:
            break
    if parsed and "end" in parsed[-1]:
        return None
    last = max((row["call"] for row in parsed if "call" in row), default=None)
    if last is None:
        path.unlink()
        return 0
    # The last call's rows may be partial, so it reruns.
    keep = sum(1 for row in parsed if row.get("call", -1) != last)
    temporary = path.with_suffix(".trim")
    temporary.write_bytes(b"".join(lines[:keep]))
    temporary.replace(path)
    return last


def _failed_row(index: int, call: dict, reason: str) -> str:
    """The row runner.py would write for a call that raised."""
    keys = ("fn", "variant", "input", "group")
    row = {"call": index, "field": "*", "kind": "x", "value": None, "dtype": None}
    row |= {key: call[key] for key in keys} | {"warnings": [], "exception": reason}
    return json.dumps(row, sort_keys=True) + "\n"


def _pump(stream, sink: queue.Queue) -> None:
    for line in stream:
        sink.put(line)
    sink.put(None)


def run_battery(
    python: Path,
    lib: str,
    out: Path,
    root: Path = ROOT,
    timeout: float = CALL_TIMEOUT,
) -> dict[str, int]:
    """Run or resume one file. A call that hangs or kills the process becomes a row."""
    start = resume_point(out)
    if start is None:
        return {"timeouts": 0, "crashes": 0}
    out.parent.mkdir(parents=True, exist_ok=True)
    battery = root / "battery" / "battery.json"
    calls = [c for c in json.loads(battery.read_bytes())["calls"] if c["lib"] == lib]
    failures = {"timeouts": 0, "crashes": 0}
    while True:
        # -I keeps this directory off sys.path, so no local module can shadow a library's.
        command = [str(python), "-I", str(RUNNER), "--battery", str(battery)]
        command += ["--out", str(out), "--lib", lib, "--start", str(start)]
        proc = subprocess.Popen(
            command, stdout=subprocess.PIPE, text=True, env=child_environ(), cwd=out.parent
        )
        lines: queue.Queue = queue.Queue()
        threading.Thread(target=_pump, args=(proc.stdout, lines), daemon=True).start()
        current = start
        hung = False
        while True:
            try:
                line = lines.get(timeout=timeout)
            except queue.Empty:
                proc.kill()
                hung = True
                break
            if line is None:
                break
            current = int(line)
        code = proc.wait()
        if code == 0 and not hung:
            return failures
        reason = "Timeout" if hung else f"Crash:{code}"
        failures["timeouts" if hung else "crashes"] += 1
        print(f"{out.name}: call {current} {calls[current]['id']}: {reason}", flush=True)
        with out.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(_failed_row(current, calls[current], reason))
            start = current + 1
            if start == len(calls):
                handle.write(json.dumps({"end": len(calls)}) + "\n")
                return failures


def check_header(env: Env, path: Path, battery_hash: str) -> None:
    with path.open(encoding="utf-8") as handle:
        meta = json.loads(handle.readline())["meta"]
    if meta["battery_sha256"] != battery_hash:
        raise ValueError(f"{path.name}: run against a different battery")
    for name, version in env.pins:
        if meta["versions"].get(name) != version:
            raise ValueError(f"{path.name}: {name} is {meta['versions'].get(name)}, not {version}")


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_all(only: str | None, root: Path = ROOT, repeat: bool = False) -> None:
    pin = (root / "battery" / "battery.sha256").read_text(encoding="ascii").strip()
    if file_hash(root / "battery" / "battery.json") != pin:
        raise ValueError("battery.json does not match battery.sha256")
    for env in select(environments(load_config(root)), only):
        python = python_of(env, root)
        if not python.exists():
            raise FileNotFoundError(f"{env.name}: run `statdrift envs` first")
        out = root / "results" / ("repeat" if repeat else "") / f"{env.name}.jsonl"
        failures = run_battery(python, env.lib, out, root)
        check_header(env, out, pin)
        print(f"{env.name}: done {failures}", flush=True)


def clean_env(env: Env, root: Path = ROOT) -> None:
    shutil.rmtree(root / "envs" / env.name / ".venv", ignore_errors=True)
