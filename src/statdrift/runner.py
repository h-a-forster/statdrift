"""Run the frozen battery in one pinned environment and append rows to a JSONL file.

This file runs under each study interpreter, on its own, with only numpy and the library
under study importable. Keep it free of statdrift imports and of syntax newer than
Python 3.9 (the regression fixture runs SciPy 1.6 on 3.9).

Each output row is one (function, variant, input, field) cell. A call that raises writes one
row with field "*" and the exception type. The parent process (`study.py`) reads CALL_MARK
lines on stdout, kills a call that hangs and restarts after one that crashes. Anything else
on stdout is a library's own output.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import math
import platform
import re
import warnings
import zlib

import numpy as np

CALL_MARK = "statdrift-call "  # study.py reads these lines
NO_FIELDS = "NoFields"  # the call returned, with none of its fields: a row keeps it in the diff
MAX_LEAVES = 64
PATH_TOKEN = re.compile(r"\.?([A-Za-z_]\w*)(\(\))?|\[(\d+)\]")


def mean_diff(x, y, axis=0):
    return np.mean(x, axis=axis) - np.mean(y, axis=axis)


def mean(x, axis=0):
    return np.mean(x, axis=axis)


STATISTICS = {"mean": mean, "mean_diff": mean_diff}


def resolve(dotted):
    """Import the longest module prefix of a dotted name, then walk attributes."""
    parts = dotted.split(".")
    for cut in range(len(parts), 0, -1):
        try:
            obj = importlib.import_module(".".join(parts[:cut]))
        except ImportError:
            continue
        for name in parts[cut:]:
            obj = getattr(obj, name)
        return obj
    raise ImportError(dotted)


def as_array(value):
    """A JSON list as an array: null is NaN, integers get numpy's default as for any user."""
    flat = np.asarray(value, dtype=object).ravel().tolist()
    if flat and all(isinstance(v, int) and not isinstance(v, bool) for v in flat):
        return np.asarray(value)
    return np.asarray(value, dtype=np.float64)


def bind(spec, data, seed):
    """Replace "$" references in a call's arguments with live objects."""
    if isinstance(spec, list):
        out = []
        for item in spec:
            if isinstance(item, str) and item.startswith("$*"):
                out.extend(bind("$" + item[2:], data, seed))
            else:
                out.append(bind(item, data, seed))
        return out
    if isinstance(spec, dict):
        return {key: bind(value, data, seed) for key, value in spec.items()}
    if not (isinstance(spec, str) and spec.startswith("$")):
        return spec
    name = spec[1:]
    if name == "rng":
        return np.random.default_rng(seed)
    if name.startswith("stat:"):
        return STATISTICS[name[5:]]
    if name.startswith("get:"):
        return resolve(name[4:])
    if name.startswith("call:"):
        return resolve(name[5:])()
    value = data[name]
    if name == "groups":
        return [as_array(group) for group in value]
    return as_array(value) if isinstance(value, list) else value


def walk(obj, path):
    """Follow a field path such as ``[1]`` or ``.confidence_interval().low``."""
    pos = 0
    while pos < len(path):
        match = PATH_TOKEN.match(path, pos)
        if match is None:
            raise ValueError("bad field path " + path)
        pos = match.end()
        if match.group(3) is not None:
            obj = obj[int(match.group(3))]
            continue
        obj = getattr(obj, match.group(1))
        if match.group(2):
            obj = obj()
    return obj


def encode(value):
    """A scalar as a JSON value and its type name. Non-finite floats become strings."""
    if value is np.ma.masked:
        return "masked", "masked"
    dtype = value.dtype.name if hasattr(value, "dtype") else type(value).__name__
    if value is None or isinstance(value, str):
        return value, dtype
    if isinstance(value, (bool, np.bool_)):
        return bool(value), dtype
    if isinstance(value, (int, np.integer)):
        return int(value), dtype
    if isinstance(value, (complex, np.complexfloating)):
        return repr(complex(value)), dtype
    number = float(value)
    if math.isnan(number):
        return "nan", dtype
    if math.isinf(number):
        return ("inf" if number > 0 else "-inf"), dtype
    return number, dtype


def leaves(field, value):
    """Flatten a value into (field, json value, type name) triples."""
    if isinstance(value, (list, tuple)) or hasattr(value, "__array__"):
        if not (hasattr(value, "ndim") and value.ndim == 0):
            if np.ma.isMaskedArray(value):
                array = value
            else:
                array = np.asarray(value)
            if array.size > MAX_LEAVES:
                raise ValueError("%s has %d leaves; limit %d" % (field, array.size, MAX_LEAVES))
            out = []
            for index in np.ndindex(array.shape):
                label = field + "[" + ",".join(str(i) for i in index) + "]"
                out.append((label,) + encode(array[index]))
            return out
        value = value[()]
    return [(field,) + encode(value)]


def exception_name(exc):
    """The exception type, marking a rejected keyword: that means the API lacks the option."""
    name = type(exc).__name__
    if isinstance(exc, TypeError) and "unexpected keyword" in str(exc):
        return "TypeError:unexpected-keyword"
    return name


def execute(call, data, seed):
    """Run one call. Returns rows of (field, value, type, exception) and warning names."""
    np.random.seed(seed)  # for code that draws from the legacy global stream
    rows = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            result = resolve(call["fn"])(
                *bind(call["args"], data, seed), **bind(call["kwargs"], data, seed)
            )
            for method, kwargs in call.get("then", []):
                result = getattr(result, method)(**bind(kwargs, data, seed))
        except Exception as exc:
            rows.append(("*", None, None, exception_name(exc)))
        else:
            for field, path in call["fields"].items():
                try:
                    value = walk(result, path)
                except AttributeError:
                    continue  # the field does not exist in this release
                except Exception as exc:
                    rows.append((field, None, None, exception_name(exc)))
                    continue
                rows.extend(triple + (None,) for triple in leaves(field, value))
            if not rows:
                rows.append(("*", None, None, NO_FIELDS))
    names = sorted({w.category.__name__ for w in caught})
    return rows, names


def row_lines(index, call, rows, names):
    lines = []
    for field, value, dtype, exc in rows:
        row = {
            "call": index,
            "fn": call["fn"],
            "variant": call["variant"],
            "input": call["input"],
            "field": field,
            "kind": "p" if field.startswith(("pvalue", "pvals", "lb_pvalue", "bp_pvalue")) else "x",
            "group": call["group"],
            "value": value,
            "dtype": dtype,
            "warnings": names,
            "exception": exc,
        }
        lines.append(json.dumps(row, allow_nan=False, sort_keys=True) + "\n")
    return lines


def header(battery_hash, lib):
    versions = {"python": platform.python_version(), "numpy": np.__version__}
    for name in ("scipy", "statsmodels", "pandas", "patsy"):
        if importlib.util.find_spec(name):
            versions[name] = importlib.import_module(name).__version__
    return {
        "battery_sha256": battery_hash,
        "lib": lib,
        "platform": platform.system() + "-" + platform.machine(),
        "versions": versions,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--battery", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--lib", required=True, choices=["scipy", "statsmodels"])
    parser.add_argument("--start", type=int, default=0, help="first call index to run")
    parser.add_argument("--only", default=None, help="regex on function names (fixtures)")
    args = parser.parse_args()

    with open(args.battery, "rb") as handle:
        raw = handle.read()
    battery = json.loads(raw)
    inputs = battery["inputs"]
    calls = [c for c in battery["calls"] if c["lib"] == args.lib]
    if args.only:
        calls = [c for c in calls if re.search(args.only, c["fn"])]

    with open(args.out, "a", encoding="utf-8", newline="\n") as out:
        if args.start == 0:
            meta = header(hashlib.sha256(raw).hexdigest(), args.lib)
            meta["calls"] = len(calls)
            out.write(json.dumps({"meta": meta}, sort_keys=True) + "\n")
            out.flush()
        for index in range(args.start, len(calls)):
            call = calls[index]
            # The leading newline ends any partial line a library left on stdout.
            print("\n" + CALL_MARK + str(index), flush=True)
            rows, names = execute(call, inputs[call["input"]], zlib.crc32(call["id"].encode()))
            out.write("".join(row_lines(index, call, rows, names)))
            out.flush()
        out.write(json.dumps({"end": len(calls)}) + "\n")


if __name__ == "__main__":
    main()
