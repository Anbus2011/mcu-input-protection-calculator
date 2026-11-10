"""
Controller / State Manager for the MCU Input Protection Calculator.

AppState owns the raw text of every input field and of every cell of the
two clamp-diode tables. The UI forwards what the user types (set_field,
set_cell) and displays what AppState hands back; it never parses or
calculates.

On every change AppState:
  1. parses each field (blank -> None, unreadable text and range problems
     are noted),
  2. builds the design dict (the layout of a .div file, format 2.0),
  3. calls the solver (src/models/clamp_solver.py) with it,
  4. sweeps the solver's pin-voltage function over the input range for the
     plot (plain lists),
  5. builds an input report: which blank fields are needed, which fields
     have problems, and any solver warnings.

No hidden defaults: nothing is ever substituted for a blank field. The only
values the app fills in by itself are the visible bandwidth starting values
(constants.BANDWIDTH_STARTING_VALUES). There are no part presets: every
clamp diode and MCU value comes from the .div file or from the user.

Also handles file I/O (.div format 2.0, src/core/div_format.py) and
dirty-tracking.
"""
from __future__ import annotations

import math
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from src.core import div_format
from src.core.constants import (
    BANDWIDTH_STARTING_VALUES, NEW_DESIGN_UNITS, PLOT_POINTS, RESISTOR_UNITS,
)
from src.core.div_format import DIODE_TYPES, DivError
from src.models import clamp_solver as solver
from src.models.clamp_solver import ROW_KEYS, TABLES, TERMINALS


# ── Field registry ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FieldSpec:
    key: str            # AppState / UI key
    label: str          # shown in messages
    kind: str           # "float", "int", "unit", "bool", "text", "choice"
    path: tuple         # location in the .div JSON
    choices: tuple = ()  # allowed values of a "choice" field

    @property
    def dotted(self) -> str:
        return ".".join(self.path)


def _resistor_fields(prefix, name, json_name):
    return [
        FieldSpec(f"{prefix}.value", f"{name} value", "float", ("resistors", json_name, "value")),
        FieldSpec(f"{prefix}.unit", f"{name} unit", "unit", ("resistors", json_name, "unit")),
        FieldSpec(f"{prefix}.rating", f"{name} power rating", "float", ("resistors", json_name, "rating_mw")),
        FieldSpec(f"{prefix}.tol", f"{name} tolerance", "float", ("resistors", json_name, "tolerance_pct")),
    ]


# name, label, kind
DIODE_FIELD_NAMES = [
    ("part", "Clamp diode part", "text"), ("type", "Clamp diode type", "choice"),
    ("anode", "Anode connection", "choice"), ("cathode", "Cathode connection", "choice"),
    ("capacitance_pf", "C_diode", "float"), ("ptot_mw", "Clamp diode Ptot", "float"),
    ("source", "Clamp diode source", "text"), ("note", "Clamp diode note", "text"),
    ("checked", "Clamp diode checked", "bool"),
]
MCU_FIELD_NAMES = [
    ("part", "MCU part", "text"), ("pin_type", "Pin type", "text"),
    ("vdd", "VDD/VDDA", "float"), ("v_recommended_max", "Safe Max", "float"),
    ("v_absolute_max", "Abs. Max", "float"), ("v_pin_min", "Pin Min", "float"),
    ("adc_bits", "ADC bits", "int"), ("vil_factor", "VIL factor", "float"),
    ("vih_factor", "VIH factor", "float"), ("c_pin_pf", "C_pin", "float"),
    ("t_pulse_min_ns", "Min pulse width", "float"),
    ("source", "MCU source", "text"), ("note", "MCU note", "text"),
    ("checked", "MCU checked", "bool"),
]
SYSTEM_FIELD_NAMES = [
    ("v_input_max", "Max Input"), ("v_input_min", "Min Input"),
    ("v_analog_fullscale", "ADC Scale"), ("analog_error_allowed_pct", "Allowed analog error"),
    ("v_logic_high_min", "Logic High"), ("v_logic_low_max", "Logic Low"),
    ("v_touch", "Touch voltage"), ("f_required_hz", "Required frequency"),
]
BANDWIDTH_FIELD_NAMES = [
    ("c_stray_pf", "C_stray", "float"), ("margin_factor", "Margin factor", "float"),
]
_CHOICES = {"type": DIODE_TYPES, "anode": TERMINALS, "cathode": TERMINALS}

FIELD_SPECS: list = (
    _resistor_fields("r1", "R1", "r1")
    + _resistor_fields("r2", "R2", "r2")
    + _resistor_fields("rs", "R_s", "r_series")
    + [FieldSpec(f"diode.{n}", label, kind, ("clamp_diode", n), _CHOICES.get(n, ()))
       for n, label, kind in DIODE_FIELD_NAMES]
    + [FieldSpec(f"mcu.{n}", label, kind, ("mcu", n)) for n, label, kind in MCU_FIELD_NAMES]
    + [FieldSpec(f"system.{n}", label, "float", ("system", n)) for n, label in SYSTEM_FIELD_NAMES]
    + [FieldSpec(f"bw.{n}", label, kind, ("bandwidth", n)) for n, label, kind in BANDWIDTH_FIELD_NAMES]
    + [FieldSpec("notes", "Design notes", "text", ("notes",))]
)
FIELDS = {f.key: f for f in FIELD_SPECS}
FIELD_ORDER = {f.key: i for i, f in enumerate(FIELD_SPECS)}
PATH_KEYS = {f.dotted: f.key for f in FIELD_SPECS}     # "mcu.vdd" -> "mcu.vdd", ...
BANDWIDTH_KEYS = [f"bw.{n}" for n, _, _ in BANDWIDTH_FIELD_NAMES]

TABLE_LABELS = {"forward": "Forward table", "reverse": "Reverse table"}
CELL_LABELS = {"i_ma": "current", "v_min": "V min", "v_typ": "V typ", "v_max": "V max"}
_TABLE_PATH = re.compile(r"clamp_diode\.(forward|reverse)(?:\[(\d+)\](?:\.(\w+))?)?$")


class LoadError(Exception):
    """A .div file could not be loaded. The message lists every problem,
    each starting with its key path."""


def format_number(v) -> str:
    """Text shown in a field for a number loaded from a file."""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(v)
    v = float(v)
    if v.is_integer() and abs(v) < 1e15:
        return str(int(v))
    return repr(v)


def path_label(path: str) -> str:
    """Screen label of a .div key path ("mcu.vdd" -> "VDD/VDDA")."""
    if path in PATH_KEYS:
        return FIELDS[PATH_KEYS[path]].label
    m = _TABLE_PATH.match(path)
    if m:
        table, row, cell = m.groups()
        label = TABLE_LABELS[table]
        if row is not None:
            label += f" row {int(row) + 1}"
        if cell is not None:
            label += f" {CELL_LABELS.get(cell, cell)}"
        return label
    return path


@dataclass
class InputReport:
    needs: list = field(default_factory=list)        # labels of blank fields some result needs
    problems: list = field(default_factory=list)     # "label: message"
    warnings: list = field(default_factory=list)     # solver warnings

    def lines(self) -> list:
        out = []
        if self.needs:
            out.append("Needs input: " + ", ".join(self.needs))
        if self.problems:
            out.append("Fix: " + "; ".join(self.problems))
        out.extend(self.warnings)
        return out


class AppState:
    """Central state manager that owns all input text, the design and the results."""

    def __init__(self):
        self.current_file: Optional[str] = None
        self.is_dirty: bool = False
        self._ignore_changes: bool = False
        self.last_save_error: Optional[str] = None

        # Callbacks
        self._on_title_changed: Optional[Callable[[str], None]] = None
        self._on_results_changed: Optional[Callable[[dict], None]] = None
        self._on_fields_changed: Optional[Callable[[], None]] = None

        # Raw text of every field and of every table cell
        self.fields: dict = {}
        self.tables: dict = {}       # "forward" / "reverse" -> [{row key: text}]
        self._reset_fields()

        # Parsed state (rebuilt by recalculate)
        self._values: dict = {}      # key -> parsed value if readable, else None
        self._problems: dict = {}    # key path -> message
        self._unreadable: set = set()        # field keys
        self._unreadable_cells: set = set()  # (table, row, cell key)
        self._cells: dict = {}       # table -> [{row key: number / None / nan}]
        self.design: dict = {}       # what the solver was given
        self.results: dict = {}      # what the solver returned
        self.circuit = None          # solver.Circuit of the design, for sweeps
        self.plot_data: dict = {}    # plain lists for the plot ({} = nothing to draw)
        self.plot_message: str = ""
        self.report = InputReport()
        self.recalculate()

    # ── Callbacks ─────────────────────────────────────────────────────────

    def set_title_callback(self, cb: Callable[[str], None]):
        self._on_title_changed = cb

    def set_results_callback(self, cb: Callable[[dict], None]):
        self._on_results_changed = cb

    def set_fields_callback(self, cb: Callable[[], None]):
        """Called when AppState changed field text itself (load, new, fill,
        table row added or deleted)."""
        self._on_fields_changed = cb

    def _fire_fields(self):
        if self._on_fields_changed:
            self._on_fields_changed()

    # ── Dirty tracking ────────────────────────────────────────────────────

    @property
    def ignore_changes(self) -> bool:
        return self._ignore_changes

    @ignore_changes.setter
    def ignore_changes(self, value: bool):
        self._ignore_changes = value

    @contextmanager
    def suspend_changes(self):
        """Suppress dirty-marking inside the block; always restored, even on error."""
        previous = self._ignore_changes
        self._ignore_changes = True
        try:
            yield
        finally:
            self._ignore_changes = previous

    def mark_dirty(self):
        if self._ignore_changes:
            return
        self.is_dirty = True
        self._fire_title()

    def _fire_title(self):
        if self._on_title_changed:
            self._on_title_changed(self.title())

    def title(self) -> str:
        name = os.path.basename(self.current_file) if self.current_file else "Untitled"
        dirty = " *" if self.is_dirty else ""
        return f"MCU Input Protection Calculator - {name}{dirty}"

    # ── Field editing (the only way inputs change) ────────────────────────

    @property
    def notes(self) -> str:
        return self.fields["notes"]

    @notes.setter
    def notes(self, text: str):
        self.fields["notes"] = text or ""

    def set_field(self, key: str, text) -> None:
        """Store the text the user typed. Marks unsaved and recalculates if
        it changed (free-text fields change no result)."""
        if key not in FIELDS:
            raise KeyError(key)
        text = "" if text is None else str(text)
        if self.fields.get(key) == text:
            return
        self.fields[key] = text
        self.mark_dirty()
        if FIELDS[key].kind != "text":
            self.recalculate()

    def set_fields(self, values: dict) -> None:
        """Set several fields at once (one recalculation). The UI is told to
        show the new text."""
        changed = False
        for key, text in values.items():
            if key not in FIELDS:
                raise KeyError(key)
            text = "" if text is None else str(text)
            if self.fields.get(key) != text:
                self.fields[key] = text
                changed = True
        if changed:
            self.mark_dirty()
            self.recalculate()
            self._fire_fields()

    def _reset_fields(self):
        """Blank design: every field blank and both diode tables empty,
        except visible unit selectors and the visible bandwidth starting
        values."""
        self.fields = {spec.key: ("0" if spec.kind == "bool" else "") for spec in FIELD_SPECS}
        for name, unit in NEW_DESIGN_UNITS.items():
            self.fields[f"{name}.unit"] = unit
        for name, value in BANDWIDTH_STARTING_VALUES.items():
            self.fields[f"bw.{name}"] = format_number(value)
        self.tables = {t: [] for t in TABLES}

    def fill_bandwidth_starting_values(self) -> list:
        """Fill blank or unreadable bandwidth fields from the starting values.
        Returns the labels of the fields filled."""
        filled = []
        for name, value in BANDWIDTH_STARTING_VALUES.items():
            key = f"bw.{name}"
            if self.fields[key].strip() == "" or key in self._unreadable:
                self.fields[key] = format_number(value)
                filled.append(FIELDS[key].label)
        if filled:
            self.mark_dirty()
            self.recalculate()
            self._fire_fields()
        return filled

    # ── Clamp diode tables ────────────────────────────────────────────────

    def set_cell(self, table: str, row: int, key: str, text) -> None:
        """Store the text typed into one table cell."""
        text = "" if text is None else str(text)
        if self.tables[table][row][key] == text:
            return
        self.tables[table][row][key] = text
        self.mark_dirty()
        self.recalculate()

    def add_row(self, table: str) -> None:
        """Append a blank row. Its cells are needed until filled in."""
        self.tables[table].append({key: "" for key in ROW_KEYS})
        self._tables_changed()

    def delete_row(self, table: str, row: int) -> None:
        del self.tables[table][row]
        self._tables_changed()

    def set_table(self, table: str, rows) -> None:
        """Replace a whole table. *rows* is a list of {i_ma, v_min, v_typ,
        v_max}; numbers or text."""
        new = [{key: ("" if row[key] is None else
                      row[key] if isinstance(row[key], str) else format_number(row[key]))
                for key in ROW_KEYS} for row in rows]
        if new != self.tables[table]:
            self.tables[table] = new
            self._tables_changed()

    def _tables_changed(self):
        self.mark_dirty()
        self.recalculate()
        self._fire_fields()

    # ── Parsing ───────────────────────────────────────────────────────────

    def _parse(self):
        values, problems, unreadable = {}, {}, set()
        for spec in FIELD_SPECS:
            raw = self.fields.get(spec.key, "")
            text = raw.strip()
            values[spec.key] = None
            if spec.kind == "text":
                values[spec.key] = raw
            elif text == "":
                pass
            elif spec.kind == "unit":
                if text in RESISTOR_UNITS:
                    values[spec.key] = text
                else:
                    problems[spec.dotted] = f"unknown unit '{text}' (use Ω, kΩ or MΩ)"
                    unreadable.add(spec.key)
            elif spec.kind == "choice":
                if text in spec.choices:
                    values[spec.key] = text
                else:
                    problems[spec.dotted] = (f"unknown value '{text}' (use "
                                             + ", ".join(spec.choices) + ")")
                    unreadable.add(spec.key)
            elif spec.kind == "bool":
                if text in ("1", "0"):
                    values[spec.key] = text == "1"
                else:
                    problems[spec.dotted] = f"'{text}' is not on/off"
                    unreadable.add(spec.key)
            else:
                try:
                    v = float(text)
                    if not math.isfinite(v):
                        raise ValueError
                except ValueError:
                    problems[spec.dotted] = f"'{text}' is not a number"
                    unreadable.add(spec.key)
                    continue
                if spec.kind == "int":
                    if not v.is_integer():
                        problems[spec.dotted] = f"'{text}' is not a whole number"
                        unreadable.add(spec.key)
                        continue
                    v = int(v)
                values[spec.key] = v
                # Range rules are the solver's (one set for app, file and solver)
                message = solver.number_problem(spec.dotted, v)
                if message is not None:
                    problems[spec.dotted] = message

        for paths, test, message, blame in solver.CROSS_RULES:
            numbers = [values[PATH_KEYS[p]] for p in paths]
            if None in numbers or any(p in problems for p in paths):
                continue
            if not test(*numbers):
                for p in blame:
                    problems[p] = message

        if not {"diode.anode", "diode.cathode"} & unreadable:
            for name, message in solver.wiring_problems(
                    values["diode.anode"], values["diode.cathode"]).items():
                problems[f"clamp_diode.{name}"] = message

        cells, unreadable_cells = {}, set()
        for table in TABLES:
            rows = []
            for i, row in enumerate(self.tables[table]):
                parsed = {}
                for key in ROW_KEYS:
                    text = row[key].strip()
                    parsed[key] = None
                    if text == "":
                        continue
                    try:
                        parsed[key] = float(text)
                        if not math.isfinite(parsed[key]):
                            raise ValueError
                    except ValueError:
                        parsed[key] = math.nan
                        problems[f"clamp_diode.{table}[{i}].{key}"] = f"'{text}' is not a number"
                        unreadable_cells.add((table, i, key))
                rows.append(parsed)
            cells[table] = rows
            for where, message in solver.table_problems(rows):
                problems.setdefault(f"clamp_diode.{table}{where}", message)

        self._values, self._problems = values, problems
        self._unreadable, self._unreadable_cells = unreadable, unreadable_cells
        self._cells = cells

    def _file_dict(self) -> dict:
        """The design in the layout of a .div file. Blank is None. Unreadable
        text becomes NaN (numbers) or the text itself (units, choices), which
        the solver treats as present but unusable."""
        v = self._values

        def leaf(kind, path):
            if path == "version":
                return div_format.FORMAT_VERSION
            if path == "created":
                return None
            if kind == div_format.TABLE:
                return [dict(row) for row in self._cells[path.rsplit(".", 1)[1]]]
            key = PATH_KEYS[path]
            if kind == div_format.TEXT:
                return self.fields[key]
            if kind == div_format.FLAG:
                return bool(v[key])
            if key in self._unreadable:
                return math.nan if kind == div_format.NUMBER else self.fields[key].strip()
            return v[key]

        def walk(schema, prefix):
            return {key: walk(kind, prefix + key + ".") if isinstance(kind, dict)
                    else leaf(kind, prefix + key) for key, kind in schema.items()}

        return walk(div_format.SCHEMA, "")

    # ── Recalculate ───────────────────────────────────────────────────────

    def recalculate(self):
        self._parse()
        self.design = self._file_dict()
        self.results = solver.solve(self.design)
        self.circuit = solver.prepare(self.design)
        self._sweep()
        self._build_report()
        if self._on_results_changed:
            self._on_results_changed(self.results)

    @property
    def details(self) -> dict:
        """Every number the screens show besides the checks and levels."""
        return self.results["details"]

    def check(self, check_id: str) -> Optional[dict]:
        """The solver's check with this id; None when the check is not made."""
        for c in self.results["checks"]:
            if c["id"] == check_id:
                return c
        return None

    def level(self, level_id: str) -> Optional[dict]:
        """{"v_in", "typ", "low", "high"} at an input level; None if not given."""
        return self.results["voltages"]["levels"].get(level_id)

    def info(self, info_id: str) -> Optional[dict]:
        for row in self.results["info"]:
            if row["id"] == info_id:
                return row
        return None

    # ── Plot: sweep of the solver's pin-voltage function ──────────────────

    def _sweep(self):
        """V_mcu against V_input as plain lists: the typical curve and the
        highest of the 8 corners. The plot and the tables come from the same
        function, so they cannot disagree."""
        c = self.circuit
        vin_max, vin_min = c.v[solver.VIN_MAX], c.v["system.v_input_min"]
        typ_block = c.blocked("typ") + [p for p in c.cause[solver.VIN_MAX]
                                        if p not in c.blocked("typ")]
        worst_block = c.blocked("worst") + [p for p in c.cause[solver.VIN_MAX]
                                            if p not in c.blocked("worst")]
        self.plot_data = {}
        if not typ_block or not worst_block:
            start = min(0.0, vin_min) if vin_min is not None else 0.0
            v_in = [start + (vin_max - start) * i / (PLOT_POINTS - 1)
                    for i in range(PLOT_POINTS)]
            v_in[-1] = vin_max
            data = {"v_in": v_in, "vin_min": start, "vin_max": vin_max,
                    "vdd": c.v[solver.VDD], "v_rec_max": c.v["mcu.v_recommended_max"],
                    "v_abs_max": c.v["mcu.v_absolute_max"]}
            if not typ_block:
                data["v_mcu_typ"] = [c.pin_voltage(x, "typ") for x in v_in]
            if not worst_block:
                data["v_mcu_worst"] = [c.pin_voltage(x, "high") for x in v_in]
            self.plot_data = data

        if typ_block and worst_block:
            both = typ_block + [p for p in worst_block if p not in typ_block]
            self.plot_message = "Plot needs input: " + self.describe_paths(both)
        elif typ_block:
            self.plot_message = "Typical curve needs input: " + self.describe_paths(typ_block)
        elif worst_block:
            self.plot_message = "Worst-case curve needs input: " + self.describe_paths(worst_block)
        else:
            self.plot_message = ""

    # ── Missing-input reporting ───────────────────────────────────────────

    @staticmethod
    def describe_paths(paths) -> str:
        labels = []
        for p in paths:
            label = path_label(p)
            if label not in labels:
                labels.append(label)
        return ", ".join(labels)

    def missing_paths(self, output: str) -> list:
        """Key paths of the inputs a solver result is waiting for."""
        return list(self.results["missing"].get(output, []))

    def _build_report(self):
        rep = InputReport()
        for p in self.results["needs_input"]:
            label = path_label(p)
            if p not in self._problems and label not in rep.needs:
                rep.needs.append(label)

        def order(path):
            if path in PATH_KEYS:
                return (0, FIELD_ORDER[PATH_KEYS[path]], 0, 0)
            m = _TABLE_PATH.match(path)
            table, row, cell = m.groups()
            return (1, TABLES.index(table), -1 if row is None else int(row),
                    ROW_KEYS.index(cell) if cell in ROW_KEYS else -1)
        rep.problems = [f"{path_label(p)}: {self._problems[p]}"
                        for p in sorted(self._problems, key=order)]
        rep.warnings = list(self.results["warnings"])
        bad_points = len(self.circuit.unsettled)
        if bad_points:
            rep.warnings.append(
                f"Clamp diode solver did not settle at {bad_points} plot point(s). "
                "The curve is not reliable there.")
        self.report = rep

    def unreadable_fields(self) -> list:
        """[(label, text)] for every field or table cell whose text can't be read."""
        out = [(FIELDS[s.key].label, self.fields[s.key]) for s in FIELD_SPECS
               if s.key in self._unreadable]
        for table, row, key in sorted(self._unreadable_cells,
                                      key=lambda c: (TABLES.index(c[0]), c[1],
                                                     ROW_KEYS.index(c[2]))):
            out.append((path_label(f"clamp_diode.{table}[{row}].{key}"),
                        self.tables[table][row][key]))
        return out

    # ── Serialisation (.div format 2.0) ───────────────────────────────────

    def get_data(self) -> dict:
        """The current design as a .div format 2.0 dict, with the solver's
        results. Blank fields are written as null. Raises ValueError on
        unreadable text."""
        bad = self.unreadable_fields()
        if bad:
            raise ValueError(self._unreadable_message(bad))
        data = self._file_dict()
        data["created"] = datetime.now().isoformat()
        return div_format.with_results(data, self.results)

    @staticmethod
    def _unreadable_message(bad) -> str:
        items = "\n".join(f"  • {label}: '{text}'" for label, text in bad)
        return ("These fields contain text that isn't a valid value. "
                "Fix or clear them before saving:\n" + items)

    @staticmethod
    def parse_file_data(data) -> tuple:
        """Validate a whole .div dict without touching any state.

        Returns (fields, tables, value_problems). Raises LoadError listing
        every format problem (wrong version, missing or unknown key, wrong
        type, unknown unit ...), each starting with its key path. Values
        that are readable but unusable (out of range, table rows out of
        order) load as they are and are returned as value_problems; null
        loads blank.
        """
        problems = div_format.validate(data)
        broken = [p for p in problems if p.kind == div_format.FORMAT]
        if broken:
            raise LoadError("\n".join(str(p) for p in broken))

        fields = {}
        for spec in FIELD_SPECS:
            raw = solver.lookup(data, spec.dotted)
            if spec.kind == "bool":
                fields[spec.key] = "1" if raw else "0"
            elif raw is None:
                fields[spec.key] = ""
            elif isinstance(raw, str):
                fields[spec.key] = raw
            else:
                fields[spec.key] = format_number(raw)
        tables = {}
        for table in TABLES:
            rows = data["clamp_diode"][table]
            if rows is None:
                # A null table is "not filled in yet", not "not modelled":
                # show two blank rows, which the results keep asking for.
                rows = [dict.fromkeys(ROW_KEYS)] * 2
            tables[table] = [{key: "" if row[key] is None else format_number(row[key])
                              for key in ROW_KEYS} for row in rows]
        return fields, tables, [p for p in problems if p.kind == div_format.VALUE]

    def load_data(self, data: dict) -> list:
        """Validate *data* fully, then replace the design with it. Stored
        results are ignored: the design is solved again. Returns load
        warnings. On LoadError nothing has changed."""
        fields, tables, value_problems = self.parse_file_data(data)
        with self.suspend_changes():
            self.fields, self.tables = fields, tables
            self.recalculate()
            self._fire_fields()
        warnings = []
        if self.report.needs:
            warnings.append("These values are blank in the file and results need them:\n"
                            + ", ".join(self.report.needs))
        if value_problems:
            warnings.append("These values in the file can't be used (they are listed "
                            "after \"Fix:\"):\n"
                            + "\n".join(f"  • {p}" for p in value_problems))
        return warnings

    # ── File operations ───────────────────────────────────────────────────

    def save_to_file(self, filepath: str) -> bool:
        """Save atomically (temp file + replace). On failure returns False and
        sets last_save_error; the existing file is untouched."""
        self.last_save_error = None
        try:
            data = self.get_data()
        except ValueError as e:
            self.last_save_error = str(e)
            return False
        try:
            div_format.write_json(filepath, data)
        except Exception as e:
            self.last_save_error = f"Failed to save {filepath}:\n{e}"
            return False
        self.current_file = filepath
        self.is_dirty = False
        self._fire_title()
        return True

    def open_file(self, filepath: str) -> list:
        """Load a .div file. Returns load warnings.
        Raises LoadError; on error the current design, file name and unsaved
        flag are unchanged."""
        try:
            data = div_format.read_json(filepath)
        except DivError as e:
            raise LoadError(str(e)) from None
        warnings = self.load_data(data)
        self.current_file = filepath
        self.is_dirty = False
        self._fire_title()
        return warnings

    def file_new(self):
        """Blank design (bandwidth fields get their visible starting values)."""
        with self.suspend_changes():
            self._reset_fields()
            self.current_file = None
            self.is_dirty = False
            self.recalculate()
            self._fire_fields()
        self._fire_title()
