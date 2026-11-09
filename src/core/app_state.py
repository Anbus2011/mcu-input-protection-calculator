"""
Controller / State Manager for the Divider Calculator.

AppState owns the raw text of every input field. The UI forwards what the
user types (set_field) and displays what AppState hands back; it never
parses or calculates.

On every change AppState:
  1. parses each field (blank or unreadable text -> None, range checks),
  2. builds the model parameter objects from the usable values only,
  3. runs the circuit and bandwidth models,
  4. builds an input report: which blank fields are needed, which fields
     have problems, and any solver warnings.

No hidden defaults: nothing is ever substituted for a blank field. The only
values the app fills in by itself are the visible bandwidth starting values
(constants.BANDWIDTH_STARTING_VALUES) and the fields of a Zener preset the
user picks.

Also handles File I/O (.div JSON format) and dirty-tracking.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from src.core.constants import (
    BANDWIDTH_STARTING_VALUES, CUSTOM_PRESET, FILE_FORMAT_VERSION,
    NEW_DESIGN_UNITS, RESISTOR_UNITS, ZENER_PRESETS,
)
from src.models.circuit_model import (
    CalculationResult, McuParams, ResistorParams, SystemParams, ZenerParams,
    calculate_all,
)
from src.models.bandwidth_model import (
    BandwidthParams, BandwidthResult, calculate_bandwidth,
)


# ── Field registry ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FieldSpec:
    key: str            # AppState / UI key
    label: str          # shown in messages
    kind: str           # "float", "int", "unit", "bool", "text"
    path: tuple         # location in the .div JSON


def _resistor_fields(prefix, name, json_name):
    return [
        FieldSpec(f"{prefix}.value", f"{name} value", "float", ("resistors", json_name, "value")),
        FieldSpec(f"{prefix}.unit", f"{name} unit", "unit", ("resistors", json_name, "unit")),
        FieldSpec(f"{prefix}.rating", f"{name} power rating", "float", ("resistors", json_name, "rating_mw")),
        FieldSpec(f"{prefix}.tol", f"{name} tolerance", "float", ("resistors", json_name, "tolerance_pct")),
    ]


ZENER_FIELD_NAMES = [
    ("vz_nom", "VZ nom"), ("vz_min", "VZ min"), ("vz_max", "VZ max"),
    ("izt_ma", "IZT"), ("zzt_typ", "ZZT typ"), ("zzt_max", "ZZT max"),
    ("izk_ma", "IZK"), ("zzk_typ", "ZZK typ"), ("zzk_max", "ZZK max"),
    ("ptot_mw", "Zener Ptot"),
]
MCU_FIELD_NAMES = [
    ("vdd", "VDD/VDDA", "float"), ("v_recommended_max", "Safe Max", "float"),
    ("v_absolute_max", "Abs. Max", "float"), ("safe_injection_ma", "Injection Limit", "float"),
    ("adc_bits", "ADC bits", "int"), ("vil_factor", "VIL factor", "float"),
    ("vih_factor", "VIH factor", "float"),
]
SYSTEM_FIELD_NAMES = [
    ("v_input_max", "Max Input"), ("v_analog_fullscale", "ADC Scale"),
    ("v_logic_high_min", "Logic High"), ("v_logic_low_max", "Logic Low"),
]
BANDWIDTH_FIELD_NAMES = [
    ("c_diode_pf", "C_diode", "float"), ("c_pin_pf", "C_pin", "float"),
    ("c_stray_pf", "C_stray", "float"), ("f_peripheral_mhz", "f_periph", "float"),
    ("n_samples", "N_samples", "int"), ("counter_bits", "Counter bits", "int"),
    ("counter_signed", "Counter signed", "bool"), ("f_read_hz", "f_read", "float"),
]

FIELD_SPECS: list = (
    _resistor_fields("r1", "R1", "r1")
    + _resistor_fields("r2", "R2", "r2")
    + _resistor_fields("rs", "R_s", "r_series")
    + [FieldSpec(f"zener.{n}", label, "float", ("zener", n)) for n, label in ZENER_FIELD_NAMES]
    + [FieldSpec(f"mcu.{n}", label, kind, ("mcu", n)) for n, label, kind in MCU_FIELD_NAMES]
    + [FieldSpec(f"system.{n}", label, "float", ("system", n)) for n, label in SYSTEM_FIELD_NAMES]
    + [FieldSpec(f"bw.{n}", label, kind, ("bandwidth", n)) for n, label, kind in BANDWIDTH_FIELD_NAMES]
    + [FieldSpec("notes", "Design notes", "text", ("notes",))]
)
FIELDS = {f.key: f for f in FIELD_SPECS}
FIELD_ORDER = {f.key: i for i, f in enumerate(FIELD_SPECS)}
ZENER_KEYS = [f"zener.{n}" for n, _ in ZENER_FIELD_NAMES]
BANDWIDTH_KEYS = [f"bw.{n}" for n, _, _ in BANDWIDTH_FIELD_NAMES]
RS_OPTIONAL_KEYS = ("rs.unit", "rs.rating", "rs.tol")

# Single-field range rules: key -> (test, message)
_GT0 = (lambda v: v > 0, "must be greater than 0")
_GE0 = (lambda v: v >= 0, "can't be negative")
_TOL = (lambda v: 0 <= v < 100, "must be at least 0 and below 100 %")
_FRACTION = (lambda v: 0 < v < 1, "must be a fraction of VDD between 0 and 1")
RANGE_RULES = {
    "r1.value": _GT0, "r2.value": _GT0, "rs.value": _GE0,
    "r1.rating": _GT0, "r2.rating": _GT0, "rs.rating": _GT0,
    "r1.tol": _TOL, "r2.tol": _TOL, "rs.tol": _TOL,
    "zener.vz_nom": _GT0, "zener.vz_min": _GT0, "zener.vz_max": _GT0,
    "zener.izt_ma": _GT0, "zener.izk_ma": _GT0,
    "zener.zzt_typ": _GE0, "zener.zzt_max": _GE0,
    "zener.zzk_typ": _GE0, "zener.zzk_max": _GE0,
    "zener.ptot_mw": _GT0,
    "mcu.vdd": _GT0, "mcu.v_recommended_max": _GT0, "mcu.v_absolute_max": _GT0,
    "mcu.safe_injection_ma": _GT0,
    "mcu.adc_bits": (lambda v: 1 <= v <= 32, "must be a whole number from 1 to 32"),
    "mcu.vil_factor": _FRACTION, "mcu.vih_factor": _FRACTION,
    "system.v_input_max": _GT0, "system.v_analog_fullscale": _GE0,
    "system.v_logic_high_min": _GE0, "system.v_logic_low_max": _GE0,
    "bw.c_diode_pf": _GE0, "bw.c_pin_pf": _GE0, "bw.c_stray_pf": _GE0,
    "bw.f_peripheral_mhz": _GT0, "bw.f_read_hz": _GT0,
    "bw.n_samples": (lambda v: v >= 1, "must be a whole number of at least 1"),
    "bw.counter_bits": (lambda v: 1 <= v <= 64, "must be a whole number from 1 to 64"),
}


class LoadError(Exception):
    """A .div file could not be loaded. The message names the field path."""


def format_number(v) -> str:
    """Text shown in a field for a number loaded from a file or preset."""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(v)
    v = float(v)
    if v.is_integer() and abs(v) < 1e15:
        return str(int(v))
    return repr(v)


@dataclass
class InputReport:
    needs: list = field(default_factory=list)        # labels of blank fields some result needs
    problems: list = field(default_factory=list)     # "label: message"
    unused_blank: list = field(default_factory=list) # blank, asked for, but no result uses them
    warnings: list = field(default_factory=list)     # solver warnings

    def lines(self) -> list:
        out = []
        if self.needs:
            out.append("Needs input: " + ", ".join(self.needs))
        if self.problems:
            out.append("Fix: " + "; ".join(self.problems))
        if self.unused_blank:
            out.append("Also blank (no result uses them yet): " + ", ".join(self.unused_blank))
        out.extend(self.warnings)
        return out


class AppState:
    """Central state manager that owns all input text, parsed values and results."""

    def __init__(self):
        self.current_file: Optional[str] = None
        self.is_dirty: bool = False
        self._ignore_changes: bool = False
        self.last_save_error: Optional[str] = None

        # Callbacks
        self._on_title_changed: Optional[Callable[[str], None]] = None
        self._on_results_changed: Optional[Callable[[CalculationResult], None]] = None
        self._on_bandwidth_changed: Optional[Callable[[BandwidthResult], None]] = None
        self._on_fields_changed: Optional[Callable[[], None]] = None

        # Raw text of every field, and the preset the Zener values came from
        self.fields: dict = {}
        self.zener_preset_base: Optional[str] = None
        self._reset_fields()

        # Parsed state (rebuilt by recalculate)
        self._numbers: dict = {}     # key -> number/bool/unit if readable, else None
        self._values: dict = {}      # key -> value if readable AND in range, else None
        self._problems: dict = {}    # key -> message
        self._unreadable: set = set()
        self._causes: dict = {}      # model input path -> [field keys making it None]
        self.resistors = ResistorParams()
        self.zener = ZenerParams()
        self.mcu = McuParams()
        self.system = SystemParams()
        self.bandwidth_params = BandwidthParams()
        self.result: Optional[CalculationResult] = None
        self.bw_result: Optional[BandwidthResult] = None
        self.report = InputReport()
        self.recalculate()

    # ── Callbacks ─────────────────────────────────────────────────────────

    def set_title_callback(self, cb: Callable[[str], None]):
        self._on_title_changed = cb

    def set_results_callback(self, cb: Callable[[CalculationResult], None]):
        self._on_results_changed = cb

    def set_bandwidth_callback(self, cb: Callable[[BandwidthResult], None]):
        self._on_bandwidth_changed = cb

    def set_fields_callback(self, cb: Callable[[], None]):
        """Called when AppState changed field text itself (load, new, preset, fill)."""
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
        """Store the text the user typed. Marks unsaved and recalculates if it changed."""
        if key not in FIELDS:
            raise KeyError(key)
        text = "" if text is None else str(text)
        if self.fields.get(key) == text:
            return
        self.fields[key] = text
        self.mark_dirty()
        if key != "notes":
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
        """Blank design: every field blank, except visible unit selectors and
        the visible bandwidth starting values."""
        self.fields = {spec.key: "" for spec in FIELD_SPECS}
        for name, unit in NEW_DESIGN_UNITS.items():
            self.fields[f"{name}.unit"] = unit
        for name, value in BANDWIDTH_STARTING_VALUES.items():
            self.fields[f"bw.{name}"] = format_number(value)
        self.zener_preset_base = None

    def select_zener_preset(self, name: str) -> None:
        """User picked a preset: fill its values visibly. "Custom" keeps the values."""
        before = (dict(self.fields), self.zener_preset_base)
        if name in ZENER_PRESETS:
            preset = ZENER_PRESETS[name]
            for n, _ in ZENER_FIELD_NAMES:
                self.fields[f"zener.{n}"] = format_number(preset[n])
            self.zener_preset_base = name
        elif name == CUSTOM_PRESET:
            self.zener_preset_base = None
        else:
            return
        if (dict(self.fields), self.zener_preset_base) != before:
            self.mark_dirty()
        self.recalculate()
        self._fire_fields()

    def fill_bandwidth_starting_values(self) -> list:
        """Fill blank or unreadable bandwidth fields from the starting values.
        Returns the labels of the fields filled."""
        filled = []
        for name, value in BANDWIDTH_STARTING_VALUES.items():
            key = f"bw.{name}"
            if FIELDS[key].kind == "bool":
                continue    # a checkbox is never blank
            if self.fields[key].strip() == "" or key in self._unreadable:
                self.fields[key] = format_number(value)
                filled.append(FIELDS[key].label)
        if filled:
            self.mark_dirty()
            self.recalculate()
            self._fire_fields()
        return filled

    # ── Zener preset state ────────────────────────────────────────────────

    def _zener_matches(self, name: str) -> bool:
        preset = ZENER_PRESETS[name]
        for n, _ in ZENER_FIELD_NAMES:
            v = self._numbers.get(f"zener.{n}")
            p = float(preset[n])
            if v is None or abs(v - p) > 1e-9 * max(1.0, abs(p)):
                return False
        return True

    def zener_preset_display(self) -> tuple:
        """(text for the preset selector, 'modified' note or '')."""
        base = self.zener_preset_base
        if base is not None:
            if self._zener_matches(base):
                return base, ""
            return CUSTOM_PRESET, f"modified from {base}"
        if any(self.fields[k].strip() for k in ZENER_KEYS):
            return CUSTOM_PRESET, ""
        return "", ""

    # ── Parsing ───────────────────────────────────────────────────────────

    def _parse_fields(self):
        numbers, problems, unreadable = {}, {}, set()
        for spec in FIELD_SPECS:
            text = self.fields.get(spec.key, "").strip()
            numbers[spec.key] = None
            if spec.kind == "text":
                continue
            if text == "":
                continue
            if spec.kind == "unit":
                if text in RESISTOR_UNITS:
                    numbers[spec.key] = text
                else:
                    problems[spec.key] = f"unknown unit '{text}' (use Ω, kΩ or MΩ)"
                    unreadable.add(spec.key)
                continue
            if spec.kind == "bool":
                if text in ("1", "0"):
                    numbers[spec.key] = text == "1"
                else:
                    problems[spec.key] = f"'{text}' is not on/off"
                    unreadable.add(spec.key)
                continue
            try:
                v = float(text)
                if not math.isfinite(v):
                    raise ValueError
            except ValueError:
                problems[spec.key] = f"'{text}' is not a number"
                unreadable.add(spec.key)
                continue
            if spec.kind == "int":
                if not v.is_integer():
                    problems[spec.key] = f"'{text}' is not a whole number"
                    unreadable.add(spec.key)
                    continue
                v = int(v)
            numbers[spec.key] = v

        values = dict(numbers)
        for key, (test, message) in RANGE_RULES.items():
            v = numbers.get(key)
            if v is not None and not test(v):
                problems[key] = message
                values[key] = None

        def cross(keys, ok, message):
            """Mark every field of a failed cross-field check as a problem."""
            if ok:
                return
            for k in keys:
                problems.setdefault(k, message)
                values[k] = None

        n = values.get
        vz = [("zener.vz_min", "zener.vz_nom"), ("zener.vz_nom", "zener.vz_max"),
              ("zener.vz_min", "zener.vz_max")]
        for lo, hi in vz:
            if numbers.get(lo) is not None and numbers.get(hi) is not None \
                    and lo not in problems and hi not in problems \
                    and numbers[lo] > numbers[hi]:
                cross((lo, hi), False, "VZ min ≤ VZ nom ≤ VZ max is not met")
        if n("zener.izk_ma") is not None and n("zener.izt_ma") is not None:
            cross(("zener.izk_ma", "zener.izt_ma"),
                  n("zener.izk_ma") < n("zener.izt_ma"), "IZK must be below IZT")
        if n("mcu.vil_factor") is not None and n("mcu.vih_factor") is not None:
            cross(("mcu.vil_factor", "mcu.vih_factor"),
                  n("mcu.vil_factor") < n("mcu.vih_factor"),
                  "VIL factor must be below VIH factor")

        self._numbers, self._values = numbers, values
        self._problems, self._unreadable = problems, unreadable

    def _build_params(self):
        v = self._values
        causes = {}

        def simple(path, key):
            causes[path] = [] if v[key] is not None else [key]
            return v[key]

        def resistance(path, prefix):
            val, unit = v[f"{prefix}.value"], v[f"{prefix}.unit"]
            if val is None:
                causes[path] = [f"{prefix}.value"]
                return None
            if unit is None:
                causes[path] = [f"{prefix}.unit"]
                return None
            causes[path] = []
            return val * RESISTOR_UNITS[unit]

        r1 = resistance("resistors.r1_ohms", "r1")
        r2 = resistance("resistors.r2_ohms", "r2")
        # R_s blank or 0 means there is no series resistor.
        if self.fields["rs.value"].strip() == "":
            rs = 0.0
            causes["resistors.rs_ohms"] = []
        elif v["rs.value"] == 0:
            rs = 0.0
            causes["resistors.rs_ohms"] = []
        else:
            rs = resistance("resistors.rs_ohms", "rs")

        self.resistors = ResistorParams(
            r1_ohms=r1, r2_ohms=r2, rs_ohms=rs,
            r1_tol_pct=simple("resistors.r1_tol_pct", "r1.tol"),
            r2_tol_pct=simple("resistors.r2_tol_pct", "r2.tol"),
            r1_rating_mw=simple("resistors.r1_rating_mw", "r1.rating"),
            r2_rating_mw=simple("resistors.r2_rating_mw", "r2.rating"),
        )
        self.zener = ZenerParams(**{
            n: simple(f"zener.{n}", f"zener.{n}") for n, _ in ZENER_FIELD_NAMES})
        self.mcu = McuParams(**{
            n: simple(f"mcu.{n}", f"mcu.{n}") for n, _, _ in MCU_FIELD_NAMES})
        self.system = SystemParams(**{
            n: simple(f"system.{n}", f"system.{n}") for n, _ in SYSTEM_FIELD_NAMES})
        self._bw_inputs = {
            n: simple(f"bandwidth.{n}", f"bw.{n}") for n, _, _ in BANDWIDTH_FIELD_NAMES}
        self._causes = causes

    @property
    def rs_present(self) -> bool:
        """True when a series resistor value greater than 0 is entered."""
        v = self._numbers.get("rs.value")
        return v is not None and v > 0

    # ── Recalculate ───────────────────────────────────────────────────────

    def recalculate(self):
        self._parse_fields()
        self._build_params()
        self.result = calculate_all(self.resistors, self.zener, self.mcu, self.system)

        # Bandwidth inputs derived from the DC analysis (CLAUDE.md §4C):
        #   tau resistance = R1||R2 + R_s, VIL/VIH = factor x VDD,
        #   V_high = lowest solved pin voltage at the Logic High input.
        r = self.result
        self.bandwidth_params = BandwidthParams(
            r_tau_ohms=r.r_source_ohms, vil_v=r.vil_v, vih_v=r.vih_v,
            v_high=r.v_high_pin, **self._bw_inputs)
        self.bw_result = calculate_bandwidth(self.bandwidth_params)
        self._build_report()

        if self._on_results_changed:
            self._on_results_changed(self.result)
        if self._on_bandwidth_changed:
            self._on_bandwidth_changed(self.bw_result)

    # ── Missing-input reporting ───────────────────────────────────────────

    _BW_DERIVED = {"r_tau_ohms": "r_source", "vil_v": "vil",
                   "vih_v": "vih", "v_high": "v_high_pin"}

    def _keys_for_paths(self, paths) -> list:
        keys = []
        for p in paths:
            for k in self._causes.get(p, []):
                if k not in keys:
                    keys.append(k)
        return sorted(keys, key=FIELD_ORDER.get)

    def missing_keys(self, output: str) -> list:
        """Field keys blocking a circuit output (key of CalculationResult.missing)."""
        return self._keys_for_paths(self.result.missing.get(output, []))

    def bw_missing_keys(self, output: str) -> list:
        """Field keys blocking a bandwidth output (key of BandwidthResult.missing)."""
        keys = []
        for name in self.bw_result.missing.get(output, []):
            if name in self._BW_DERIVED:
                ks = self.missing_keys(self._BW_DERIVED[name])
            else:
                ks = self._keys_for_paths([f"bandwidth.{name}"])
            for k in ks:
                if k not in keys:
                    keys.append(k)
        return sorted(keys, key=FIELD_ORDER.get)

    def describe_keys(self, keys) -> str:
        return ", ".join(FIELDS[k].label for k in sorted(set(keys), key=FIELD_ORDER.get))

    def _build_report(self):
        needed = []
        for out in self.result.missing:
            for k in self.missing_keys(out):
                if k not in needed:
                    needed.append(k)
        for out in self.bw_result.missing:
            for k in self.bw_missing_keys(out):
                if k not in needed:
                    needed.append(k)
        order = {spec.key: i for i, spec in enumerate(FIELD_SPECS)}
        needed.sort(key=order.get)
        rep = InputReport()
        rep.needs = [FIELDS[k].label for k in needed if k not in self._problems]
        rep.problems = [f"{FIELDS[k].label}: {msg}" for k, msg in
                        sorted(self._problems.items(), key=lambda kv: order[kv[0]])]
        if self.rs_present:
            rep.unused_blank = [FIELDS[k].label for k in ("rs.rating", "rs.tol")
                                if self.fields[k].strip() == ""]
        rep.warnings = list(self.result.warnings)
        self.report = rep

    def unreadable_fields(self) -> list:
        """[(label, text)] for every field whose text can't be read."""
        return [(FIELDS[s.key].label, self.fields[s.key]) for s in FIELD_SPECS
                if s.key in self._unreadable]

    # ── Serialisation (backwards-compatible .div JSON) ────────────────────

    def get_data(self) -> dict:
        """Serialize current state to a dict matching the .div JSON format.
        Blank fields are written as null. Raises ValueError on unreadable text."""
        bad = self.unreadable_fields()
        if bad:
            raise ValueError(self._unreadable_message(bad))
        num = self._numbers

        def res(prefix):
            return {
                "value": num[f"{prefix}.value"],
                "unit": num[f"{prefix}.unit"],
                "rating_mw": num[f"{prefix}.rating"],
                "tolerance_pct": num[f"{prefix}.tol"],
            }

        preset_text, modified = self.zener_preset_display()
        base = self.zener_preset_base
        zener = {
            "preset": preset_text or None,
            "preset_base": base if modified else None,
        }
        for n, _ in ZENER_FIELD_NAMES[:3]:
            zener[n] = num[f"zener.{n}"]
        zener["tolerance_pct"] = ZENER_PRESETS[base]["tolerance_pct"] if base else None
        for n, _ in ZENER_FIELD_NAMES[3:]:
            zener[n] = num[f"zener.{n}"]

        mcu = {"vdd": num["mcu.vdd"], "vdda": num["mcu.vdd"], "vref": num["mcu.vdd"]}
        for n, _, _ in MCU_FIELD_NAMES[1:]:
            mcu[n] = num[f"mcu.{n}"]

        return {
            "version": FILE_FORMAT_VERSION,
            "created": datetime.now().isoformat(),
            "notes": self.fields["notes"],
            "resistors": {"r1": res("r1"), "r2": res("r2"), "r_series": res("rs")},
            "zener": zener,
            "mcu": mcu,
            "system": {n: num[f"system.{n}"] for n, _ in SYSTEM_FIELD_NAMES},
            "bandwidth": {n: num[f"bw.{n}"] for n, _, _ in BANDWIDTH_FIELD_NAMES},
        }

    @staticmethod
    def _unreadable_message(bad) -> str:
        items = "\n".join(f"  • {label}: '{text}'" for label, text in bad)
        return ("These fields contain text that isn't a valid value. "
                "Fix or clear them before saving:\n" + items)

    @staticmethod
    def parse_file_data(data) -> tuple:
        """Validate a whole .div dict without touching any state.

        Returns (fields, preset_base, warnings). Raises LoadError naming the
        field path for malformed data (wrong type, non-numeric string, unknown
        unit, broken structure). Missing or null fields load blank.
        """
        if not isinstance(data, dict):
            raise LoadError("file: expected a JSON object at the top level")
        version = data.get("version")
        if version is not None and not isinstance(version, str):
            raise LoadError("version: expected text")

        def lookup(path):
            node = data
            for i, part in enumerate(path):
                if node is None:
                    return None
                if not isinstance(node, dict):
                    raise LoadError(f"{'.'.join(path[:i])}: expected an object")
                node = node.get(part)
            return node

        fields, missing = {}, []
        for spec in FIELD_SPECS:
            where = ".".join(spec.path)
            raw = lookup(spec.path)
            if spec.kind == "text":
                if raw is not None and not isinstance(raw, str):
                    raise LoadError(f"{where}: expected text")
                fields[spec.key] = raw or ""
                continue
            if raw is None:
                fields[spec.key] = ""
                missing.append(spec.key)
                continue
            if spec.kind == "unit":
                if not isinstance(raw, str):
                    raise LoadError(f"{where}: expected a unit (Ω, kΩ or MΩ)")
                if raw not in RESISTOR_UNITS:
                    raise LoadError(f"{where}: unknown unit '{raw}' (expected Ω, kΩ or MΩ)")
                fields[spec.key] = raw
                continue
            if spec.kind == "bool":
                if not isinstance(raw, bool):
                    raise LoadError(f"{where}: expected true or false")
                fields[spec.key] = "1" if raw else "0"
                continue
            if isinstance(raw, bool):
                raise LoadError(f"{where}: expected a number, got {str(raw).lower()}")
            if isinstance(raw, (int, float)):
                v = raw
            elif isinstance(raw, str):
                try:
                    v = float(raw)
                except ValueError:
                    raise LoadError(f"{where}: '{raw}' is not a number") from None
            else:
                raise LoadError(f"{where}: expected a number")
            if not math.isfinite(float(v)):
                raise LoadError(f"{where}: '{raw}' is not a finite number")
            if spec.kind == "int":
                if not float(v).is_integer():
                    raise LoadError(f"{where}: expected a whole number, got {raw}")
                v = int(float(v))
            fields[spec.key] = format_number(v)

        # Preset
        zener = data.get("zener")
        preset = zener.get("preset") if isinstance(zener, dict) else None
        preset_base = zener.get("preset_base") if isinstance(zener, dict) else None
        if preset is not None and not isinstance(preset, str):
            raise LoadError("zener.preset: expected text")
        if preset_base is not None and not isinstance(preset_base, str):
            raise LoadError("zener.preset_base: expected text")
        warnings = []
        base = None
        if preset in ZENER_PRESETS:
            base = preset
        elif preset == CUSTOM_PRESET:
            if preset_base in ZENER_PRESETS:
                base = preset_base
            elif preset_base:
                warnings.append(f"Unknown preset_base '{preset_base}'; the Zener loads as Custom.")
        elif preset:
            warnings.append(f"Unknown Zener preset '{preset}'; the Zener loads as Custom.")

        # R_s = 0 or blank: its unit, rating and tolerance aren't needed.
        rs_text = fields["rs.value"]
        if rs_text == "" or float(rs_text) == 0:
            missing = [k for k in missing if k not in RS_OPTIONAL_KEYS]

        if missing:
            labels = []
            for k in missing:
                if FIELDS[k].kind == "bool":
                    fields[k] = "0"
                    labels.append(f"{FIELDS[k].label} (shown unchecked)")
                else:
                    labels.append(FIELDS[k].label)
            warnings.insert(0, "These fields were missing or empty in the file and are "
                               "blank now:\n" + ", ".join(labels))
        return fields, base, warnings

    def load_data(self, data: dict) -> list:
        """Validate *data* fully, then replace the design with it.
        Returns load warnings. On LoadError nothing has changed."""
        fields, base, warnings = self.parse_file_data(data)
        with self.suspend_changes():
            self.fields = fields
            self.zener_preset_base = base
            self.recalculate()
            self._fire_fields()
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
        tmp = None
        try:
            folder = os.path.dirname(os.path.abspath(filepath))
            fd, tmp = tempfile.mkstemp(prefix=".~", suffix=".div.tmp", dir=folder)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            if os.name == "posix":
                mask = os.umask(0)
                os.umask(mask)
                os.chmod(tmp, 0o666 & ~mask)
            os.replace(tmp, filepath)
            tmp = None
        except Exception as e:
            self.last_save_error = f"Failed to save {filepath}:\n{e}"
            return False
        finally:
            if tmp is not None:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
        self.current_file = filepath
        self.is_dirty = False
        self._fire_title()
        return True

    def open_file(self, filepath: str) -> list:
        """Load a .div file. Returns load warnings.
        Raises LoadError; on error the current design, file name and unsaved
        flag are unchanged."""
        try:
            with open(filepath, "r", encoding="utf-8-sig") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError) as e:
            raise LoadError(f"Can't read {filepath}: {e}") from None
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise LoadError(f"file: not valid JSON ({e})") from None
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
