"""
Controller / State Manager for the Divider Calculator.
Handles File I/O (JSON), dirty-tracking, and synchronization
between UI inputs and calculation models.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Callable, Optional

from src.core.constants import (
    DEFAULT_VALUES, FILE_FORMAT_VERSION, ZENER_PRESETS
)
from src.models.circuit_model import (
    CalculationResult, McuParams, ResistorParams, SystemParams, ZenerParams,
    calculate_all,
)
from src.models.bandwidth_model import (
    BandwidthParams, BandwidthResult, calculate_bandwidth,
)


class AppState:
    """Central state manager that owns all parameter values and calculation results."""

    def __init__(self):
        self.current_file: Optional[str] = None
        self.is_dirty: bool = False
        self._ignore_changes: bool = False

        # Callbacks
        self._on_title_changed: Optional[Callable[[str], None]] = None
        self._on_results_changed: Optional[Callable[[CalculationResult], None]] = None
        self._on_bandwidth_changed: Optional[Callable[[BandwidthResult], None]] = None

        # Current parameter objects (populated from UI or file)
        self.resistors = ResistorParams()
        self.zener = ZenerParams()
        self.mcu = McuParams()
        self.system = SystemParams()
        self.bandwidth_params = BandwidthParams()
        self.notes: str = ""

        # Display units/values for serialisation (matches .div format)
        self.r1_display_value: float = 10.0
        self.r1_display_unit: str = "k\u03a9"
        self.r2_display_value: float = 18.0
        self.r2_display_unit: str = "k\u03a9"
        self.rs_display_value: float = 0.0
        self.rs_display_unit: str = "\u03a9"
        self.rs_rating_mw: Optional[float] = None
        self.rs_tol_pct: Optional[float] = None

        # Last calculation result
        self.result: Optional[CalculationResult] = None
        self.bw_result: Optional[BandwidthResult] = None

    # ── Callbacks ─────────────────────────────────────────────────────────

    def set_title_callback(self, cb: Callable[[str], None]):
        self._on_title_changed = cb

    def set_results_callback(self, cb: Callable[[CalculationResult], None]):
        self._on_results_changed = cb

    def set_bandwidth_callback(self, cb: Callable[[BandwidthResult], None]):
        self._on_bandwidth_changed = cb

    # ── Dirty tracking ────────────────────────────────────────────────────

    @property
    def ignore_changes(self) -> bool:
        return self._ignore_changes

    @ignore_changes.setter
    def ignore_changes(self, value: bool):
        self._ignore_changes = value

    def mark_dirty(self):
        if self._ignore_changes:
            return
        self.is_dirty = True
        self._fire_title()

    def _fire_title(self):
        if self._on_title_changed:
            name = os.path.basename(self.current_file) if self.current_file else "Untitled"
            dirty = " *" if self.is_dirty else ""
            self._on_title_changed(f"Divider Calculator v1.1 - {name}{dirty}")

    # ── Recalculate ───────────────────────────────────────────────────────

    def recalculate(self):
        self.result = calculate_all(self.resistors, self.zener, self.mcu, self.system)
        if self._on_results_changed:
            self._on_results_changed(self.result)

    def recalculate_bandwidth(self):
        self.bw_result = calculate_bandwidth(self.bandwidth_params)
        if self._on_bandwidth_changed:
            self._on_bandwidth_changed(self.bw_result)

    # ── Serialisation (backwards-compatible .div JSON) ────────────────────

    def get_data(self) -> dict:
        """Serialize current state to a dict matching the .div JSON format."""
        data = {
            "version": FILE_FORMAT_VERSION,
            "created": datetime.now().isoformat(),
            "notes": self.notes,
            "resistors": {
                "r1": {
                    "value": self.r1_display_value,
                    "unit": self.r1_display_unit,
                    "rating_mw": self.resistors.r1_rating_mw,
                    "tolerance_pct": self.resistors.r1_tol_pct,
                },
                "r2": {
                    "value": self.r2_display_value,
                    "unit": self.r2_display_unit,
                    "rating_mw": self.resistors.r2_rating_mw,
                    "tolerance_pct": self.resistors.r2_tol_pct,
                },
                "r_series": {
                    "value": self.rs_display_value,
                    "unit": self.rs_display_unit,
                    "rating_mw": self.rs_rating_mw,
                    "tolerance_pct": self.rs_tol_pct,
                },
            },
            "zener": {
                "preset": self._zener_preset_name,
                "vz_nom": self.zener.vz_nom,
                "vz_min": self.zener.vz_min,
                "vz_max": self.zener.vz_max,
                "tolerance_pct": 5,
                "izt_ma": self.zener.izt_ma,
                "zzt_typ": self.zener.zzt_typ,
                "zzt_max": self.zener.zzt_max,
                "zzk_typ": self.zener.zzk_typ,
                "zzk_max": self.zener.zzk_max,
                "izk_ma": self.zener.izk_ma,
                "ptot_mw": self.zener.ptot_mw,
            },
            "mcu": {
                "vdd": self.mcu.vdd,
                "vdda": self.mcu.vdd,
                "vref": self.mcu.vdd,
                "v_recommended_max": self.mcu.v_recommended_max,
                "v_absolute_max": self.mcu.v_absolute_max,
                "safe_injection_ma": self.mcu.safe_injection_ma,
            },
            "system": {
                "v_input_max": self.system.v_input_max,
                "v_analog_fullscale": self.system.v_analog_fullscale,
                "v_logic_high_min": self.system.v_logic_high_min,
                "v_logic_low_max": self.system.v_logic_low_max,
            },
        }
        return data

    # Keep track of which preset was selected (for serialisation)
    _zener_preset_name: str = "BZB984-C3V3"

    def set_zener_preset(self, name: str):
        self._zener_preset_name = name

    def load_data(self, data: dict):
        """Deserialize a .div JSON dict into state objects."""
        self._ignore_changes = True
        try:
            r = data.get("resistors", {})
            r1 = r.get("r1", {})
            r2 = r.get("r2", {})
            rs = r.get("r_series", {})

            def _val_ohms(d, default_val, default_unit):
                v = d.get("value", default_val)
                u = d.get("unit", default_unit)
                if v is None:
                    v = 0
                return float(v) * (1000 if u == "k\u03a9" else 1)

            self.r1_display_value = float(r1.get("value", 10))
            self.r1_display_unit = r1.get("unit", "k\u03a9")
            self.resistors.r1_ohms = _val_ohms(r1, 10, "k\u03a9")
            self.resistors.r1_rating_mw = r1.get("rating_mw")
            self.resistors.r1_tol_pct = float(r1.get("tolerance_pct", 1))

            self.r2_display_value = float(r2.get("value", 18))
            self.r2_display_unit = r2.get("unit", "k\u03a9")
            self.resistors.r2_ohms = _val_ohms(r2, 18, "k\u03a9")
            self.resistors.r2_rating_mw = r2.get("rating_mw")
            self.resistors.r2_tol_pct = float(r2.get("tolerance_pct", 1))

            self.rs_display_value = float(rs.get("value", 0))
            self.rs_display_unit = rs.get("unit", "\u03a9")
            self.resistors.rs_ohms = _val_ohms(rs, 0, "\u03a9")
            self.rs_rating_mw = rs.get("rating_mw")
            self.rs_tol_pct = rs.get("tolerance_pct")

            z = data.get("zener", {})
            self._zener_preset_name = z.get("preset", "Custom")
            self.zener.vz_nom = float(z.get("vz_nom", 3.3))
            self.zener.vz_min = float(z.get("vz_min", 3.1))
            self.zener.vz_max = float(z.get("vz_max", 3.5))
            self.zener.izt_ma = float(z.get("izt_ma", 5))
            self.zener.zzt_typ = float(z.get("zzt_typ", 85))
            self.zener.zzt_max = float(z.get("zzt_max", 95))
            self.zener.zzk_typ = float(z.get("zzk_typ", 350))
            self.zener.zzk_max = float(z.get("zzk_max", 600))
            self.zener.izk_ma = float(z.get("izk_ma", 1))
            self.zener.ptot_mw = float(z.get("ptot_mw", 265))

            m = data.get("mcu", {})
            self.mcu.vdd = float(m.get("vdd", 3.3))
            self.mcu.v_recommended_max = float(m.get("v_recommended_max", 3.6))
            self.mcu.v_absolute_max = float(m.get("v_absolute_max", 4.0))
            self.mcu.safe_injection_ma = float(m.get("safe_injection_ma", 1.0))

            s = data.get("system", {})
            self.system.v_input_max = float(s.get("v_input_max", 30))
            self.system.v_analog_fullscale = float(s.get("v_analog_fullscale", 5.1))
            self.system.v_logic_high_min = float(s.get("v_logic_high_min", 3.8))
            self.system.v_logic_low_max = float(s.get("v_logic_low_max", 1.0))

            self.notes = data.get("notes", "")
        finally:
            self._ignore_changes = False

    def reset_to_defaults(self):
        """Reset state to factory defaults."""
        defs = DEFAULT_VALUES
        self.load_data({
            "resistors": defs["resistors"],
            "zener": defs["zener"],
            "mcu": defs["mcu"],
            "system": defs["system"],
            "notes": "",
        })

    # ── File operations ───────────────────────────────────────────────────

    def save_to_file(self, filepath: str) -> bool:
        try:
            data = self.get_data()
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)
            self.current_file = filepath
            self.is_dirty = False
            self._fire_title()
            return True
        except Exception:
            return False

    def open_file(self, filepath: str) -> dict:
        """Load file and return raw data dict (caller pushes to UI)."""
        with open(filepath, "r") as f:
            data = json.load(f)
        self.load_data(data)
        self.current_file = filepath
        self.is_dirty = False
        self._fire_title()
        return data

    def file_new(self):
        self.current_file = None
        self.is_dirty = False
        self.reset_to_defaults()
        self._fire_title()
