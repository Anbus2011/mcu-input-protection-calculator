"""
The .div design file, format 2.0: structure, validation, reading and writing.

Standard library only (the command-line checker uses this module and must not
pull in customtkinter, matplotlib or numpy). The format is described in
docs/div_v2_format.md.

``validate`` reports every problem in a file, each with its key path. A
problem is one of two kinds:

* FORMAT: the file can't be read as a design (missing or unknown key, wrong
  type, unknown unit ...). The app refuses to open the file.
* VALUE: the value is readable but can't be used (out of range, table rows
  out of order ...). The app opens the file and shows the problem next to
  "Fix:"; the checker treats the file as invalid either way.

A null value is never a problem: it is a blank field, and the results that
need it say "needs input".
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from typing import NamedTuple

from src.models import clamp_solver as solver

FORMAT_VERSION = "2.0"
FORMAT, VALUE = "format", "value"
DIODE_TYPES = ("zener", "schottky")

# Leaf kinds
TEXT, FLAG, NUMBER, UNIT, TERMINAL, DIODE_TYPE, TABLE = (
    "text", "flag", "number", "unit", "terminal", "diode type", "table")

_RESISTOR = {"value": NUMBER, "unit": UNIT, "rating_mw": NUMBER, "tolerance_pct": NUMBER}

# Every key of a format 2.0 file except "results", in file order.
SCHEMA = {
    "version": TEXT,
    "created": TEXT,
    "notes": TEXT,
    "resistors": {"r1": _RESISTOR, "r2": _RESISTOR, "r_series": _RESISTOR},
    "clamp_diode": {
        "part": TEXT, "source": TEXT, "checked": FLAG, "note": TEXT,
        "type": DIODE_TYPE, "anode": TERMINAL, "cathode": TERMINAL,
        "capacitance_pf": NUMBER, "ptot_mw": NUMBER,
        "forward": TABLE, "reverse": TABLE,
    },
    "mcu": {
        "part": TEXT, "source": TEXT, "checked": FLAG, "note": TEXT,
        "pin_type": TEXT,
        "vdd": NUMBER, "v_recommended_max": NUMBER, "v_absolute_max": NUMBER,
        "v_pin_min": NUMBER, "safe_injection_ma": NUMBER, "adc_bits": NUMBER,
        "vil_factor": NUMBER, "vih_factor": NUMBER,
        "c_pin_pf": NUMBER, "t_pulse_min_ns": NUMBER,
    },
    "system": {
        "v_input_max": NUMBER, "v_input_min": NUMBER,
        "v_analog_fullscale": NUMBER, "analog_error_allowed_pct": NUMBER,
        "v_logic_high_min": NUMBER, "v_logic_low_max": NUMBER,
        "v_touch": NUMBER, "f_required_hz": NUMBER,
    },
    "bandwidth": {"c_stray_pf": NUMBER, "margin_factor": NUMBER},
}
RESULTS_KEY = "results"

# The part of the solver's results that is stored in a file.
FILE_RESULT_KEYS = ("solver_version", "verdict", "checks", "info", "voltages",
                    "needs_input", "notes", "warnings")
RESULT_DIGITS = 7       # significant digits of the numbers stored in "results"

V1_MESSAGE = (
    "this is a format 1.0 file (the Zener-only model). This version reads "
    ".div format 2.0 only and there is no converter: enter the design again, "
    "with the clamp diode's data-sheet tables (docs/div_v2_format.md).")


class Problem(NamedTuple):
    path: str
    message: str
    kind: str

    def __str__(self):
        return f"{self.path}: {self.message}"


class DivError(Exception):
    """A .div file can't be used. ``problems`` holds every problem found."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("\n".join(str(p) for p in self.problems))


# ── Validation ───────────────────────────────────────────────────────────────

def _is_number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _check_leaf(kind, path, raw, out):
    if raw is None and kind != FLAG:
        return                                      # blank
    if kind == TEXT:
        if not isinstance(raw, str):
            out.append(Problem(path, "expected text", FORMAT))
    elif kind == FLAG:
        if not isinstance(raw, bool):
            out.append(Problem(path, "expected true or false", FORMAT))
    elif kind == UNIT:
        if not isinstance(raw, str):
            out.append(Problem(path, "expected a unit (Ω, kΩ or MΩ)", FORMAT))
        elif raw not in solver.RESISTOR_UNITS:
            out.append(Problem(path, f"unknown unit '{raw}' (expected Ω, kΩ or MΩ)", FORMAT))
    elif kind == TERMINAL:
        if raw not in solver.TERMINALS:
            out.append(Problem(path, "expected \"node\", \"gnd\" or \"vdd\"", FORMAT))
    elif kind == DIODE_TYPE:
        if raw not in DIODE_TYPES:
            out.append(Problem(path, "expected \"zener\" or \"schottky\"", FORMAT))
    elif kind == NUMBER:
        message = solver.number_problem(path, raw)
        if message is not None:
            readable = _is_number(raw) and math.isfinite(raw) \
                and not message.startswith("expected")
            out.append(Problem(path, message, VALUE if readable else FORMAT))
    elif kind == TABLE:
        _check_table(path, raw, out)


def _check_table(path, rows, out):
    if not isinstance(rows, list):
        out.append(Problem(path, "expected a list of rows ([] when this direction "
                                 "is not modelled)", FORMAT))
        return
    for i, row in enumerate(rows):
        where = f"{path}[{i}]"
        if not isinstance(row, dict):
            out.append(Problem(where, "expected an object with i_ma, v_min, v_typ, v_max",
                               FORMAT))
            continue
        for key in solver.ROW_KEYS:
            if key not in row:
                out.append(Problem(f"{where}.{key}", "missing (use null for a blank value)",
                                   FORMAT))
            elif row[key] is not None and not (_is_number(row[key])
                                               and math.isfinite(row[key])):
                out.append(Problem(f"{where}.{key}", "expected a number", FORMAT))
        for key in row:
            if key not in solver.ROW_KEYS:
                out.append(Problem(f"{where}.{key}", "unknown key", FORMAT))
    already = {p.path for p in out}
    for where, message in solver.table_problems(rows):
        if path + where not in already:
            out.append(Problem(path + where, message, VALUE))


def _walk(node, schema, prefix, out):
    for key, kind in schema.items():
        path = prefix + key
        if key not in node:
            out.append(Problem(path, "missing (use null for a blank value)", FORMAT))
        elif isinstance(kind, dict):
            if isinstance(node[key], dict):
                _walk(node[key], kind, path + ".", out)
            else:
                out.append(Problem(path, "expected an object", FORMAT))
        else:
            _check_leaf(kind, path, node[key], out)
    for key in node:
        if key not in schema and not (prefix == "" and key == RESULTS_KEY):
            out.append(Problem(prefix + str(key), "unknown key", FORMAT))


def validate(data) -> list:
    """Every problem in a parsed .div file, as a list of Problem (path,
    message, kind). An empty list means the file is a valid format 2.0 design."""
    if not isinstance(data, dict):
        return [Problem("file", "expected a JSON object at the top level", FORMAT)]
    version = data.get("version")
    if version != FORMAT_VERSION:
        if version == "1.0" or "zener" in data:
            message = V1_MESSAGE
        elif version is None:
            message = f"missing: this version reads .div format {FORMAT_VERSION}"
        else:
            message = f"expected \"{FORMAT_VERSION}\", got {json.dumps(version)}"
        return [Problem("version", message, FORMAT)]

    out = []
    _walk(data, SCHEMA, "", out)
    if data.get(RESULTS_KEY) is not None and not isinstance(data[RESULTS_KEY], dict):
        out.append(Problem(RESULTS_KEY, "expected an object", FORMAT))

    bad = {p.path for p in out}
    diode = data.get("clamp_diode")
    if isinstance(diode, dict) and not bad & {"clamp_diode.anode", "clamp_diode.cathode"}:
        for name, message in solver.wiring_problems(diode.get("anode"),
                                                    diode.get("cathode")).items():
            out.append(Problem(f"clamp_diode.{name}", message, VALUE))
    for paths, test, message, blame in solver.CROSS_RULES:
        values = [solver.lookup(data, p) for p in paths]
        if None in values or bad & set(paths):
            continue
        if not test(*values):
            out.extend(Problem(p, message, VALUE) for p in blame)
    return out


def number_paths(schema=None, prefix="") -> list:
    """Key paths of every number in the format, in file order."""
    out = []
    for key, kind in (SCHEMA if schema is None else schema).items():
        if isinstance(kind, dict):
            out.extend(number_paths(kind, prefix + key + "."))
        elif kind == NUMBER:
            out.append(prefix + key)
    return out


# ── Results stored in a file ─────────────────────────────────────────────────

def _rounded(x):
    if isinstance(x, float):
        return float(f"{x:.{RESULT_DIGITS}g}") if math.isfinite(x) else None
    if isinstance(x, dict):
        return {k: _rounded(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_rounded(v) for v in x]
    return x


def results_for_file(results: dict) -> dict:
    """The stored part of the solver's results: version, verdict, checks,
    information rows, key voltages, inputs still needed, notes and warnings."""
    return _rounded({key: results[key] for key in FILE_RESULT_KEYS})


def with_results(data: dict, results: dict) -> dict:
    """A copy of the file data with "results" replaced by the solver's."""
    out = {key: value for key, value in data.items() if key != RESULTS_KEY}
    out[RESULTS_KEY] = results_for_file(results)
    return out


# ── Reading and writing ──────────────────────────────────────────────────────

def read_json(filepath: str):
    """Parse a .div file. Raises DivError when it can't be read or is not
    JSON. The data is not validated here: call ``validate``."""
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise DivError([Problem("file", f"can't read {filepath}: {e}", FORMAT)]) from None
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise DivError([Problem("file", f"not valid JSON ({e})", FORMAT)]) from None


ONE_LINE_KEYS = 5       # a small object of plain values is written on one line


def _scalar(x) -> bool:
    return not isinstance(x, (dict, list, tuple))


def _dumps(x, depth=0) -> str:
    """JSON text with 2-space indents, except that a list of plain values and
    an object of at most 5 plain values (a resistor, a table row, a check)
    stay on one line, so a diode table reads as a table."""
    pad = "  " * depth
    if isinstance(x, dict):
        if not x:
            return "{}"
        items = [(json.dumps(str(k)), v) for k, v in x.items()]
        if len(x) <= ONE_LINE_KEYS and all(_scalar(v) for v in x.values()):
            return "{" + ", ".join(f"{k}: {_dumps(v)}" for k, v in items) + "}"
        body = ",\n".join(f"{pad}  {k}: {_dumps(v, depth + 1)}" for k, v in items)
        return "{\n" + body + "\n" + pad + "}"
    if isinstance(x, (list, tuple)):
        if all(_scalar(v) for v in x):
            return "[" + ", ".join(_dumps(v) for v in x) + "]"
        body = ",\n".join(f"{pad}  {_dumps(v, depth + 1)}" for v in x)
        return "[\n" + body + "\n" + pad + "]"
    return json.dumps(x, allow_nan=False)


class _Encoder(json.JSONEncoder):
    def iterencode(self, o, _one_shot=False):
        yield _dumps(o)


def write_json(filepath: str, data) -> None:
    """Write atomically (temp file in the same folder, then replace). On any
    failure the existing file is untouched and no temp file is left."""
    tmp = None
    try:
        folder = os.path.dirname(os.path.abspath(filepath))
        fd, tmp = tempfile.mkstemp(prefix=".~", suffix=".div.tmp", dir=folder)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, cls=_Encoder)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        if os.name == "posix":
            mask = os.umask(0)
            os.umask(mask)
            os.chmod(tmp, 0o666 & ~mask)
        os.replace(tmp, filepath)
        tmp = None
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass
