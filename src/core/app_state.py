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
    DEFAULT_VALUES, FILE_FORMAT_VERSION, ZENER_PRESETS,
    SCHOTTKY_PRESETS, TVS_PRESETS,
)
from src.models.circuit_model import (
    CalculationResult, McuParams, ResistorParams, SystemParams, ZenerParams,
    calculate_all, calculate_with_clamp,
)
from src.models.clamps.base import ClampModel
from src.models.clamps.zener import ZenerClamp
from src.models.clamps.schottky import SchottkyClamp
from src.models.clamps.tvs import TVSClamp
from src.models.bandwidth_model import (
    BandwidthParams, BandwidthResult, calculate_bandwidth,
)


def _build_clamp(clamp_type, params, polarity=None):
    """Construct a ClampModel from a type string and param dict."""
    try:
        if clamp_type == "zener":
            return ZenerClamp(
                vz_nom=float(params.get("vz_nom", 3.3)),
                vz_min=float(params.get("vz_min", 3.1)),
                vz_max=float(params.get("vz_max", 3.5)),
                izt_ma=float(params.get("izt_ma", 5.0)),
                izk_ma=float(params.get("izk_ma", 1.0)),
                zzt_typ=float(params.get("zzt_typ", 85.0)),
                zzt_max=float(params.get("zzt_max", 95.0)),
                zzk_typ=float(params.get("zzk_typ", 350.0)),
                zzk_max=float(params.get("zzk_max", 600.0)),
                ptot_mw=float(params.get("ptot_mw", 265.0)),
            )
        elif clamp_type == "schottky":
            return SchottkyClamp(
                vf_typ=float(params.get("vf_typ", 0.32)),
                vf_max=float(params.get("vf_max", 0.40)),
                if_test_ma=float(params.get("if_test_ma", 10.0)),
                r_dynamic=float(params.get("r_dynamic", 4.0)),
                ir_ua=float(params.get("ir_ua", 2.0)),
                vr_max=float(params.get("vr_max", 30.0)),
                cd_pf=float(params.get("cd_pf", 10.0)),
                pd_mw=float(params.get("pd_mw", 200.0)),
                channels=int(params.get("channels", 4)),
            )
        elif clamp_type == "tvs":
            pol = polarity or params.get("polarity", "unidirectional")
            return TVSClamp(
                v_rwm=float(params.get("v_rwm", 60.0)),
                v_br_min=float(params.get("v_br_min", 66.7)),
                v_br_max=float(params.get("v_br_max", 73.7)),
                v_c=float(params.get("v_c", 96.8)),
                i_pp=float(params.get("i_pp", 6.2)),
                i_t=float(params.get("i_t", 1.0)),
                c_pf=float(params.get("c_pf", 380.0)),
                p_ppm_w=float(params.get("p_ppm_w", 600.0)),
                polarity=pol,
            )
        return None
    except Exception:
        return None


class AppState:
    """Central state manager that owns all parameter values and calculation results."""

    def __init__(self):
        self.current_file = None
        self.is_dirty = False
        self._ignore_changes = False

        # Callbacks
        self._on_title_changed = None
        self._on_results_changed = None
        self._on_bandwidth_changed = None

        # Current parameter objects (populated from UI or file)
        self.resistors = ResistorParams()
        self.zener = ZenerParams()   # kept for backward compat with existing UI (T8 updates this)
        self.mcu = McuParams()
        self.system = SystemParams()
        self.bandwidth_params = BandwidthParams()
        self.notes = ""

        # v2.0 multi-clamp fields
        self.clamp_type = "zener"          # "zener" | "tvs" | "schottky"
        self.clamp_preset_name = "BZB984-C3V3"
        self.clamp = None                  # active ClampModel instance
        self.clamp_params = {}             # type-specific param dict from .div

        # Display units/values for serialisation (matches .div format)
        self.r1_display_value = 10.0
        self.r1_display_unit = "k\u03a9"
        self.r2_display_value = 18.0
        self.r2_display_unit = "k\u03a9"
        self.rs_display_value = 0.0
        self.rs_display_unit = "\u03a9"
        self.rs_rating_mw = None
        self.rs_tol_pct = None

        # Last calculation result
        self.result = None
        self.bw_result = None

    # ── Callbacks ─────────────────────────────────────────────────────────

    def set_title_callback(self, cb):
        self._on_title_changed = cb

    def set_results_callback(self, cb):
        self._on_results_changed = cb

    def set_bandwidth_callback(self, cb):
        self._on_bandwidth_changed = cb

    # ── Dirty tracking ────────────────────────────────────────────────────

    @property
    def ignore_changes(self):
        return self._ignore_changes

    @ignore_changes.setter
    def ignore_changes(self, value):
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
            self._on_title_changed(f"MCU Input Protection Calculator - {name}{dirty}")

    # ── Recalculate ───────────────────────────────────────────────────────

    def recalculate(self):
        """Run calculation using the active clamp (any type)."""
        if self.clamp is not None and self.clamp_type != "zener":
            vclamp_nom, vclamp_max, ptot = self._clamp_voltage_refs()
            self.result = calculate_with_clamp(
                self.resistors, self.clamp, self.mcu, self.system,
                clamp_type=self.clamp_type,
                vclamp_nom=vclamp_nom, vclamp_max=vclamp_max, ptot_mw=ptot,
            )
        else:
            self.result = calculate_all(self.resistors, self.zener, self.mcu, self.system)
        if self._on_results_changed:
            self._on_results_changed(self.result)

    def _clamp_voltage_refs(self):
        """Return (vclamp_nom, vclamp_max, ptot_mw) for the active clamp."""
        if self.clamp_type == "schottky" and isinstance(self.clamp, SchottkyClamp):
            vdd = self.mcu.vdd
            return vdd + self.clamp.vf_typ, vdd + self.clamp.vf_max, self.clamp.pd_mw
        elif self.clamp_type == "tvs" and isinstance(self.clamp, TVSClamp):
            return self.clamp.v_br_min, self.clamp.v_br_max, self.clamp.p_ppm_w
        else:
            return self.zener.vz_nom, self.zener.vz_max, self.zener.ptot_mw

    def recalculate_bandwidth(self):
        self.bw_result = calculate_bandwidth(self.bandwidth_params)
        if self._on_bandwidth_changed:
            self._on_bandwidth_changed(self.bw_result)

    # ── Preset tracking ───────────────────────────────────────────────────

    _zener_preset_name = "BZB984-C3V3"

    def set_zener_preset(self, name):
        self._zener_preset_name = name
        self.clamp_preset_name = name

    def set_clamp_type(self, clamp_type: str):
        """Set the active clamp type field."""
        self.clamp_type = clamp_type

    def set_clamp_preset(self, preset_name: str):
        """Set the active preset name."""
        self.clamp_preset_name = preset_name
        if self.clamp_type == "zener":
            self._zener_preset_name = preset_name

    def update_clamp(self, clamp_type: str, params: dict, polarity: str = None):
        """Build a new ClampModel from type+params and store it. Also syncs zener legacy fields."""
        self.clamp_type = clamp_type
        self.clamp_params = dict(params)
        self.clamp = _build_clamp(clamp_type, params, polarity)
        if clamp_type == "zener":
            self.zener.vz_nom = float(params.get("vz_nom", 3.3))
            self.zener.vz_min = float(params.get("vz_min", 3.1))
            self.zener.vz_max = float(params.get("vz_max", 3.5))
            self.zener.izt_ma = float(params.get("izt_ma", 5))
            self.zener.zzt_typ = float(params.get("zzt_typ", 85))
            self.zener.zzt_max = float(params.get("zzt_max", 95))
            self.zener.zzk_typ = float(params.get("zzk_typ", 350))
            self.zener.zzk_max = float(params.get("zzk_max", 600))
            self.zener.izk_ma = float(params.get("izk_ma", 1))
            self.zener.ptot_mw = float(params.get("ptot_mw", 265))

    # ── Serialisation (v2.0 .div JSON) ────────────────────────────────────

    def get_data(self):
        """Serialize current state to a v2.0 .div JSON dict."""
        clamp_block = self._build_clamp_block()
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
            "clamp": clamp_block,
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

    def _build_clamp_block(self):
        """Build the 'clamp' dict for get_data()."""
        ct = self.clamp_type
        if ct == "zener":
            return {
                "type": "zener",
                "preset": self.clamp_preset_name or self._zener_preset_name,
                "polarity": None,
                "params": {
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
            }
        elif ct == "schottky" and isinstance(self.clamp, SchottkyClamp):
            return {
                "type": "schottky",
                "preset": self.clamp_preset_name,
                "polarity": None,
                "params": {
                    "vf_typ": self.clamp.vf_typ,
                    "vf_max": self.clamp.vf_max,
                    "if_test_ma": self.clamp.if_test_ma,
                    "r_dynamic": self.clamp.r_dynamic,
                    "ir_ua": self.clamp.ir_ua,
                    "vr_max": self.clamp.vr_max,
                    "cd_pf": self.clamp.cd_pf,
                    "pd_mw": self.clamp.pd_mw,
                    "channels": self.clamp.channels,
                },
            }
        elif ct == "tvs" and isinstance(self.clamp, TVSClamp):
            return {
                "type": "tvs",
                "preset": self.clamp_preset_name,
                "polarity": self.clamp.polarity,
                "params": {
                    "v_rwm": self.clamp.v_rwm,
                    "v_br_min": self.clamp.v_br_min,
                    "v_br_max": self.clamp.v_br_max,
                    "v_c": self.clamp.v_c,
                    "i_pp": self.clamp.i_pp,
                    "i_t": self.clamp.i_t,
                    "c_pf": self.clamp.c_pf,
                    "p_ppm_w": self.clamp.p_ppm_w,
                },
            }
        return {
            "type": ct,
            "preset": self.clamp_preset_name,
            "polarity": None,
            "params": dict(self.clamp_params),
        }

    def load_data(self, data):
        """Deserialize a .div JSON dict into state objects.

        Accepts both v1.0 (top-level 'zener' block) and v2.0 (top-level 'clamp' block).
        v1.0 files are auto-migrated. Unknown versions raise ValueError.
        """
        version = data.get("version")
        if version in (None, "1.0") or ("zener" in data and "clamp" not in data):
            data = self._migrate_v1_to_v2(data)
        elif version == "2.0":
            pass
        else:
            raise ValueError(f"Unsupported .div file version: {version!r}")

        self._ignore_changes = True
        try:
            self._load_v2(data)
        finally:
            self._ignore_changes = False

    def _migrate_v1_to_v2(self, data):
        """Translate a v1.0 dict into v2.0 shape."""
        z = data.get("zener", {})
        preset = z.get("preset", "Custom")
        params = {k: v for k, v in z.items() if k != "preset"}
        clamp_block = {
            "type": "zener",
            "preset": preset,
            "polarity": None,
            "params": params,
        }
        migrated = dict(data)
        migrated["version"] = "2.0"
        migrated["clamp"] = clamp_block
        return migrated

    def _load_v2(self, data):
        """Load v2.0 format data into state."""
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

        c = data.get("clamp", {})
        self.clamp_type = c.get("type", "zener")
        self.clamp_preset_name = c.get("preset", "Custom")
        polarity = c.get("polarity")
        params = c.get("params", {})
        self.clamp_params = dict(params)

        self.clamp = _build_clamp(self.clamp_type, params, polarity)

        if self.clamp_type == "zener":
            self._zener_preset_name = self.clamp_preset_name
            self.zener.vz_nom = float(params.get("vz_nom", 3.3))
            self.zener.vz_min = float(params.get("vz_min", 3.1))
            self.zener.vz_max = float(params.get("vz_max", 3.5))
            self.zener.izt_ma = float(params.get("izt_ma", 5))
            self.zener.zzt_typ = float(params.get("zzt_typ", 85))
            self.zener.zzt_max = float(params.get("zzt_max", 95))
            self.zener.zzk_typ = float(params.get("zzk_typ", 350))
            self.zener.zzk_max = float(params.get("zzk_max", 600))
            self.zener.izk_ma = float(params.get("izk_ma", 1))
            self.zener.ptot_mw = float(params.get("ptot_mw", 265))

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

    def reset_to_defaults(self):
        """Reset state to factory defaults."""
        defs = DEFAULT_VALUES
        self.load_data({
            "version": "1.0",
            "resistors": defs["resistors"],
            "zener": defs["zener"],
            "mcu": defs["mcu"],
            "system": defs["system"],
            "notes": "",
        })

    # ── File operations ───────────────────────────────────────────────────

    def save_to_file(self, filepath):
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

    def open_file(self, filepath):
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
