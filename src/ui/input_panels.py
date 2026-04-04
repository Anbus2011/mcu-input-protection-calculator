"""
Input panel classes for the Divider Calculator.
Each panel owns its CTk widgets and pushes values into AppState on change.
"""
from __future__ import annotations

import customtkinter as ctk
from typing import TYPE_CHECKING

from src.core.constants import ZENER_PRESETS
from src.models.bandwidth_model import BandwidthParams

if TYPE_CHECKING:
    from src.core.app_state import AppState


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_float(entry: ctk.CTkEntry, default):
    """Get float from entry, returning *default* on empty/invalid input."""
    try:
        val = entry.get().strip()
        if not val:
            return default
        return float(val)
    except (ValueError, TypeError):
        return default


def _set_entry(entry: ctk.CTkEntry, value):
    """Clear and set an entry's text."""
    entry.delete(0, "end")
    entry.insert(0, str(value) if value is not None else "")


# ── Resistor Panel ────────────────────────────────────────────────────────────

class ResistorPanel(ctk.CTkFrame):
    def __init__(self, parent, state: AppState):
        super().__init__(parent)
        self.app_state = state
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="Resistors", font=("", 14, "bold")).pack(anchor="w", padx=10, pady=5)

        # R1
        r1f = ctk.CTkFrame(self, fg_color="transparent")
        r1f.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(r1f, text="R1:", width=40).pack(side="left")
        self.r1_value = ctk.CTkEntry(r1f, width=80)
        self.r1_value.pack(side="left", padx=2)
        self.r1_value.bind("<KeyRelease>", self._on_change)
        self.r1_unit = ctk.CTkComboBox(r1f, values=["\u03a9", "k\u03a9"], width=70,
                                        command=self._on_change)
        self.r1_unit.pack(side="left", padx=2)
        self.r1_unit.set("k\u03a9")
        ctk.CTkLabel(r1f, text="Rating:").pack(side="left", padx=(10, 2))
        self.r1_rating = ctk.CTkEntry(r1f, width=60)
        self.r1_rating.pack(side="left", padx=2)
        ctk.CTkLabel(r1f, text="mW").pack(side="left")
        ctk.CTkLabel(r1f, text="Tol:").pack(side="left", padx=(10, 2))
        self.r1_tol = ctk.CTkEntry(r1f, width=40)
        self.r1_tol.pack(side="left", padx=2)
        self.r1_tol.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(r1f, text="%").pack(side="left")

        # R2
        r2f = ctk.CTkFrame(self, fg_color="transparent")
        r2f.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(r2f, text="R2:", width=40).pack(side="left")
        self.r2_value = ctk.CTkEntry(r2f, width=80)
        self.r2_value.pack(side="left", padx=2)
        self.r2_value.bind("<KeyRelease>", self._on_change)
        self.r2_unit = ctk.CTkComboBox(r2f, values=["\u03a9", "k\u03a9"], width=70,
                                        command=self._on_change)
        self.r2_unit.pack(side="left", padx=2)
        self.r2_unit.set("k\u03a9")
        ctk.CTkLabel(r2f, text="Rating:").pack(side="left", padx=(10, 2))
        self.r2_rating = ctk.CTkEntry(r2f, width=60)
        self.r2_rating.pack(side="left", padx=2)
        ctk.CTkLabel(r2f, text="mW").pack(side="left")
        ctk.CTkLabel(r2f, text="Tol:").pack(side="left", padx=(10, 2))
        self.r2_tol = ctk.CTkEntry(r2f, width=40)
        self.r2_tol.pack(side="left", padx=2)
        self.r2_tol.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(r2f, text="%").pack(side="left")

        # R_series
        rsf = ctk.CTkFrame(self, fg_color="transparent")
        rsf.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(rsf, text="R_s:", width=40).pack(side="left")
        self.rs_value = ctk.CTkEntry(rsf, width=80)
        self.rs_value.pack(side="left", padx=2)
        self.rs_value.bind("<KeyRelease>", self._on_change)
        self.rs_unit = ctk.CTkComboBox(rsf, values=["\u03a9", "k\u03a9"], width=70,
                                        command=self._on_change)
        self.rs_unit.pack(side="left", padx=2)
        self.rs_unit.set("\u03a9")
        ctk.CTkLabel(rsf, text="Rating:").pack(side="left", padx=(10, 2))
        self.rs_rating = ctk.CTkEntry(rsf, width=60)
        self.rs_rating.pack(side="left", padx=2)
        ctk.CTkLabel(rsf, text="mW").pack(side="left")
        ctk.CTkLabel(rsf, text="Tol:").pack(side="left", padx=(10, 2))
        self.rs_tol = ctk.CTkEntry(rsf, width=40)
        self.rs_tol.pack(side="left", padx=2)
        ctk.CTkLabel(rsf, text="%").pack(side="left")

    def _resistance_ohms(self, entry, combo):
        v = _safe_float(entry, 0)
        if combo.get() == "k\u03a9":
            v *= 1000
        return v

    def push_to_state(self):
        s = self.app_state
        s.resistors.r1_ohms = self._resistance_ohms(self.r1_value, self.r1_unit)
        s.resistors.r2_ohms = self._resistance_ohms(self.r2_value, self.r2_unit)
        s.resistors.rs_ohms = self._resistance_ohms(self.rs_value, self.rs_unit)
        s.resistors.r1_rating_mw = _safe_float(self.r1_rating, None)
        s.resistors.r2_rating_mw = _safe_float(self.r2_rating, None)
        s.resistors.r1_tol_pct = _safe_float(self.r1_tol, 1)
        s.resistors.r2_tol_pct = _safe_float(self.r2_tol, 1)
        # Display values for serialisation
        s.r1_display_value = _safe_float(self.r1_value, 10)
        s.r1_display_unit = self.r1_unit.get()
        s.r2_display_value = _safe_float(self.r2_value, 18)
        s.r2_display_unit = self.r2_unit.get()
        s.rs_display_value = _safe_float(self.rs_value, 0)
        s.rs_display_unit = self.rs_unit.get()
        s.rs_rating_mw = _safe_float(self.rs_rating, None)
        s.rs_tol_pct = _safe_float(self.rs_tol, None)

    def load_from_data(self, data: dict):
        r = data.get("resistors", {})
        r1 = r.get("r1", {})
        _set_entry(self.r1_value, r1.get("value", 10))
        self.r1_unit.set(r1.get("unit", "k\u03a9"))
        _set_entry(self.r1_rating, r1.get("rating_mw", "") or "")
        _set_entry(self.r1_tol, r1.get("tolerance_pct", 1))

        r2 = r.get("r2", {})
        _set_entry(self.r2_value, r2.get("value", 18))
        self.r2_unit.set(r2.get("unit", "k\u03a9"))
        _set_entry(self.r2_rating, r2.get("rating_mw", "") or "")
        _set_entry(self.r2_tol, r2.get("tolerance_pct", 1))

        rs = r.get("r_series", {})
        _set_entry(self.rs_value, rs.get("value", 0))
        self.rs_unit.set(rs.get("unit", "\u03a9"))
        _set_entry(self.rs_rating, rs.get("rating_mw", "") or "")
        _set_entry(self.rs_tol, rs.get("tolerance_pct", "") or "")

    def clear_fields(self):
        _set_entry(self.r1_value, "")
        self.r1_unit.set("k\u03a9")
        _set_entry(self.r1_rating, "")
        _set_entry(self.r1_tol, "")

        _set_entry(self.r2_value, "")
        self.r2_unit.set("k\u03a9")
        _set_entry(self.r2_rating, "")
        _set_entry(self.r2_tol, "")

        _set_entry(self.rs_value, "")
        self.rs_unit.set("\u03a9")
        _set_entry(self.rs_rating, "")
        _set_entry(self.rs_tol, "")

    def _on_change(self, event=None):
        self.push_to_state()
        self.app_state.mark_dirty()
        self.app_state.recalculate()


# ── Zener Panel ───────────────────────────────────────────────────────────────

class ZenerPanel(ctk.CTkFrame):
    def __init__(self, parent, state: AppState):
        super().__init__(parent)
        self.app_state = state
        self._build()

    def _build(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(header, text="Zener Diode", font=("", 14, "bold")).pack(side="left")

        self.preset = ctk.CTkComboBox(
            header, values=list(ZENER_PRESETS.keys()), width=150,
            command=self._on_preset_change
        )
        self.preset.pack(side="right")
        self.preset.set("")
        ctk.CTkLabel(header, text="Preset:").pack(side="right", padx=5)

        params = ctk.CTkFrame(self, fg_color="transparent")
        params.pack(fill="x", padx=10, pady=5)

        # Row 1: VZ nom, min, max
        row1 = ctk.CTkFrame(params, fg_color="transparent")
        row1.pack(fill="x", pady=2)
        ctk.CTkLabel(row1, text="VZ:", width=50).pack(side="left")
        self.vz_nom = ctk.CTkEntry(row1, width=60); self.vz_nom.pack(side="left", padx=2)
        self.vz_nom.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(row1, text="V (nom)").pack(side="left")
        self.vz_min = ctk.CTkEntry(row1, width=60); self.vz_min.pack(side="left", padx=(15, 2))
        self.vz_min.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(row1, text="V (min)").pack(side="left")
        self.vz_max = ctk.CTkEntry(row1, width=60); self.vz_max.pack(side="left", padx=(15, 2))
        self.vz_max.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(row1, text="V (max)").pack(side="left")

        # Row 2: IZT, ZZT typ/max
        row2 = ctk.CTkFrame(params, fg_color="transparent")
        row2.pack(fill="x", pady=2)
        ctk.CTkLabel(row2, text="@IZT:", width=50).pack(side="left")
        self.izt = ctk.CTkEntry(row2, width=60); self.izt.pack(side="left", padx=2)
        self.izt.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(row2, text="mA").pack(side="left")
        ctk.CTkLabel(row2, text="ZZT:").pack(side="left", padx=(15, 2))
        self.zzt_typ = ctk.CTkEntry(row2, width=50); self.zzt_typ.pack(side="left", padx=2)
        self.zzt_typ.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(row2, text="\u03a9 typ").pack(side="left")
        self.zzt_max = ctk.CTkEntry(row2, width=50); self.zzt_max.pack(side="left", padx=(10, 2))
        self.zzt_max.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(row2, text="\u03a9 max").pack(side="left")

        # Row 3: IZK, ZZK typ/max
        row3 = ctk.CTkFrame(params, fg_color="transparent")
        row3.pack(fill="x", pady=2)
        ctk.CTkLabel(row3, text="@IZK:", width=50).pack(side="left")
        self.izk = ctk.CTkEntry(row3, width=60); self.izk.pack(side="left", padx=2)
        self.izk.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(row3, text="mA").pack(side="left")
        ctk.CTkLabel(row3, text="ZZK:").pack(side="left", padx=(15, 2))
        self.zzk_typ = ctk.CTkEntry(row3, width=50); self.zzk_typ.pack(side="left", padx=2)
        self.zzk_typ.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(row3, text="\u03a9 typ").pack(side="left")
        self.zzk_max = ctk.CTkEntry(row3, width=50); self.zzk_max.pack(side="left", padx=(10, 2))
        self.zzk_max.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(row3, text="\u03a9 max").pack(side="left")

        # Row 4: Ptot
        row4 = ctk.CTkFrame(params, fg_color="transparent")
        row4.pack(fill="x", pady=2)
        ctk.CTkLabel(row4, text="Ptot:", width=50).pack(side="left")
        self.ptot = ctk.CTkEntry(row4, width=60); self.ptot.pack(side="left", padx=2)
        self.ptot.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(row4, text="mW").pack(side="left")

    def push_to_state(self):
        z = self.app_state.zener
        z.vz_nom = _safe_float(self.vz_nom, 3.3)
        z.vz_min = _safe_float(self.vz_min, 3.1)
        z.vz_max = _safe_float(self.vz_max, 3.5)
        z.izt_ma = _safe_float(self.izt, 5)
        z.zzt_typ = _safe_float(self.zzt_typ, 85)
        z.zzt_max = _safe_float(self.zzt_max, 95)
        z.zzk_typ = _safe_float(self.zzk_typ, 350)
        z.zzk_max = _safe_float(self.zzk_max, 600)
        z.izk_ma = _safe_float(self.izk, 1)
        z.ptot_mw = _safe_float(self.ptot, 265)
        self.app_state.set_zener_preset(self.preset.get())

    def _load_preset_values(self):
        name = self.preset.get()
        if name not in ZENER_PRESETS:
            return
        p = ZENER_PRESETS[name]
        _set_entry(self.vz_nom, p["vz_nom"])
        _set_entry(self.vz_min, p["vz_min"])
        _set_entry(self.vz_max, p["vz_max"])
        _set_entry(self.izt, p["izt_ma"])
        _set_entry(self.zzt_typ, p["zzt_typ"])
        _set_entry(self.zzt_max, p["zzt_max"])
        _set_entry(self.zzk_typ, p["zzk_typ"])
        _set_entry(self.zzk_max, p["zzk_max"])
        _set_entry(self.izk, p["izk_ma"])
        _set_entry(self.ptot, p["ptot_mw"])

    def load_from_data(self, data: dict):
        z = data.get("zener", {})
        self.preset.set(z.get("preset", "Custom"))
        _set_entry(self.vz_nom, z.get("vz_nom", 3.3))
        _set_entry(self.vz_min, z.get("vz_min", 3.1))
        _set_entry(self.vz_max, z.get("vz_max", 3.5))
        _set_entry(self.izt, z.get("izt_ma", 5))
        _set_entry(self.zzt_typ, z.get("zzt_typ", 85))
        _set_entry(self.zzt_max, z.get("zzt_max", 95))
        _set_entry(self.zzk_typ, z.get("zzk_typ", 350))
        _set_entry(self.zzk_max, z.get("zzk_max", 600))
        _set_entry(self.izk, z.get("izk_ma", 1))
        _set_entry(self.ptot, z.get("ptot_mw", 265))

    def clear_fields(self):
        self.preset.set("")
        _set_entry(self.vz_nom, "")
        _set_entry(self.vz_min, "")
        _set_entry(self.vz_max, "")
        _set_entry(self.izt, "")
        _set_entry(self.zzt_typ, "")
        _set_entry(self.zzt_max, "")
        _set_entry(self.zzk_typ, "")
        _set_entry(self.zzk_max, "")
        _set_entry(self.izk, "")
        _set_entry(self.ptot, "")

    def _on_preset_change(self, choice):
        self._load_preset_values()
        self.push_to_state()
        self.app_state.mark_dirty()
        self.app_state.recalculate()

    def _on_change(self, event=None):
        self.push_to_state()
        self.app_state.mark_dirty()
        self.app_state.recalculate()


# ── MCU Panel ─────────────────────────────────────────────────────────────────

class McuPanel(ctk.CTkFrame):
    def __init__(self, parent, state: AppState):
        super().__init__(parent)
        self.app_state = state
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="MCU Pin Input Limits", font=("", 14, "bold")).pack(anchor="w", padx=10, pady=5)
        params = ctk.CTkFrame(self, fg_color="transparent")
        params.pack(fill="x", padx=10, pady=5)

        row1 = ctk.CTkFrame(params, fg_color="transparent")
        row1.pack(fill="x", pady=2)
        ctk.CTkLabel(row1, text="VDD/VDDA:", width=90).pack(side="left")
        self.vdd = ctk.CTkEntry(row1, width=60); self.vdd.pack(side="left", padx=2)
        self.vdd.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(row1, text="V").pack(side="left")
        ctk.CTkLabel(row1, text="Safe Max:").pack(side="left", padx=(20, 2))
        self.rec_max = ctk.CTkEntry(row1, width=60); self.rec_max.pack(side="left", padx=2)
        self.rec_max.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(row1, text="V").pack(side="left")

        row2 = ctk.CTkFrame(params, fg_color="transparent")
        row2.pack(fill="x", pady=2)
        ctk.CTkLabel(row2, text="Abs. Max:", width=90).pack(side="left")
        self.abs_max = ctk.CTkEntry(row2, width=60); self.abs_max.pack(side="left", padx=2)
        self.abs_max.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(row2, text="V").pack(side="left")
        ctk.CTkLabel(row2, text="Injection Limit:").pack(side="left", padx=(20, 2))
        self.inj_safe = ctk.CTkEntry(row2, width=60); self.inj_safe.pack(side="left", padx=2)
        self.inj_safe.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(row2, text="mA").pack(side="left")

    def push_to_state(self):
        m = self.app_state.mcu
        m.vdd = _safe_float(self.vdd, 3.3)
        m.v_recommended_max = _safe_float(self.rec_max, 3.6)
        m.v_absolute_max = _safe_float(self.abs_max, 4.0)
        m.safe_injection_ma = _safe_float(self.inj_safe, 1.0)

    def load_from_data(self, data: dict):
        m = data.get("mcu", {})
        _set_entry(self.vdd, m.get("vdd", 3.3))
        _set_entry(self.rec_max, m.get("v_recommended_max", 3.6))
        _set_entry(self.abs_max, m.get("v_absolute_max", 4.0))
        _set_entry(self.inj_safe, m.get("safe_injection_ma", 1.0))

    def clear_fields(self):
        _set_entry(self.vdd, "")
        _set_entry(self.rec_max, "")
        _set_entry(self.abs_max, "")
        _set_entry(self.inj_safe, "")

    def _on_change(self, event=None):
        self.push_to_state()
        self.app_state.mark_dirty()
        self.app_state.recalculate()


# ── System Panel ──────────────────────────────────────────────────────────────

class SystemPanel(ctk.CTkFrame):
    def __init__(self, parent, state: AppState):
        super().__init__(parent)
        self.app_state = state
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="System Requirements", font=("", 14, "bold")).pack(anchor="w", padx=10, pady=5)
        params = ctk.CTkFrame(self, fg_color="transparent")
        params.pack(fill="x", padx=10, pady=5)

        row1 = ctk.CTkFrame(params, fg_color="transparent")
        row1.pack(fill="x", pady=2)
        ctk.CTkLabel(row1, text="Max Input:", width=90).pack(side="left")
        self.vin_max = ctk.CTkEntry(row1, width=60); self.vin_max.pack(side="left", padx=2)
        self.vin_max.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(row1, text="V").pack(side="left")
        ctk.CTkLabel(row1, text="ADC Scale:").pack(side="left", padx=(20, 2))
        self.analog_fs = ctk.CTkEntry(row1, width=60); self.analog_fs.pack(side="left", padx=2)
        self.analog_fs.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(row1, text="V").pack(side="left")

        row2 = ctk.CTkFrame(params, fg_color="transparent")
        row2.pack(fill="x", pady=2)
        ctk.CTkLabel(row2, text="Logic High:", width=90).pack(side="left")
        self.logic_high = ctk.CTkEntry(row2, width=60); self.logic_high.pack(side="left", padx=2)
        self.logic_high.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(row2, text="V min").pack(side="left")
        ctk.CTkLabel(row2, text="Logic Low:").pack(side="left", padx=(20, 2))
        self.logic_low = ctk.CTkEntry(row2, width=60); self.logic_low.pack(side="left", padx=2)
        self.logic_low.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(row2, text="V max").pack(side="left")

    def push_to_state(self):
        s = self.app_state.system
        s.v_input_max = _safe_float(self.vin_max, 30)
        s.v_analog_fullscale = _safe_float(self.analog_fs, 5.1)
        s.v_logic_high_min = _safe_float(self.logic_high, 3.8)
        s.v_logic_low_max = _safe_float(self.logic_low, 1.0)

    def load_from_data(self, data: dict):
        s = data.get("system", {})
        _set_entry(self.vin_max, s.get("v_input_max", 30))
        _set_entry(self.analog_fs, s.get("v_analog_fullscale", 5.1))
        _set_entry(self.logic_high, s.get("v_logic_high_min", 3.8))
        _set_entry(self.logic_low, s.get("v_logic_low_max", 1.0))

    def clear_fields(self):
        _set_entry(self.vin_max, "")
        _set_entry(self.analog_fs, "")
        _set_entry(self.logic_high, "")
        _set_entry(self.logic_low, "")

    def _on_change(self, event=None):
        self.push_to_state()
        self.app_state.mark_dirty()
        self.app_state.recalculate()


# ── Notes Panel ───────────────────────────────────────────────────────────────

class NotesPanel(ctk.CTkFrame):
    def __init__(self, parent, state: AppState):
        super().__init__(parent)
        self.app_state = state
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="Design Notes", font=("", 14, "bold")).pack(anchor="w", padx=10, pady=5)
        self.textbox = ctk.CTkTextbox(self, height=80)
        self.textbox.pack(fill="x", padx=10, pady=5)
        self.textbox.bind("<KeyRelease>", self._on_change)

    def push_to_state(self):
        self.app_state.notes = self.textbox.get("1.0", "end-1c")

    def load_from_data(self, data: dict):
        self.textbox.delete("1.0", "end")
        self.textbox.insert("1.0", data.get("notes", ""))

    def clear_fields(self):
        self.textbox.delete("1.0", "end")

    def _on_change(self, event=None):
        self.push_to_state()
        self.app_state.mark_dirty()


# ── Bandwidth / PPS Input Panel ───────────────────────────────────────────────

class BandwidthInputPanel(ctk.CTkFrame):
    """Input fields for the Signal Bandwidth / PPS analysis tab."""

    def __init__(self, parent, state: AppState):
        super().__init__(parent, fg_color="transparent")
        self.app_state = state
        self._build()

    def _build(self):
        # Protection network
        ctk.CTkLabel(self, text="Protection Network", font=("", 13, "bold")).pack(anchor="w", padx=5, pady=(5, 2))
        net = ctk.CTkFrame(self, fg_color="transparent"); net.pack(fill="x", padx=5)

        r1 = ctk.CTkFrame(net, fg_color="transparent"); r1.pack(fill="x", pady=1)
        ctk.CTkLabel(r1, text="R_series:", width=90).pack(side="left")
        self.r_series = ctk.CTkEntry(r1, width=70); self.r_series.pack(side="left", padx=2)
        self.r_series.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(r1, text="\u03a9").pack(side="left")

        r2 = ctk.CTkFrame(net, fg_color="transparent"); r2.pack(fill="x", pady=1)
        ctk.CTkLabel(r2, text="C_diode:", width=90).pack(side="left")
        self.c_diode = ctk.CTkEntry(r2, width=70); self.c_diode.pack(side="left", padx=2)
        self.c_diode.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(r2, text="pF").pack(side="left")
        ctk.CTkLabel(r2, text="C_pin:").pack(side="left", padx=(15, 2))
        self.c_pin = ctk.CTkEntry(r2, width=50); self.c_pin.pack(side="left", padx=2)
        self.c_pin.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(r2, text="pF").pack(side="left")
        ctk.CTkLabel(r2, text="C_stray:").pack(side="left", padx=(15, 2))
        self.c_stray = ctk.CTkEntry(r2, width=50); self.c_stray.pack(side="left", padx=2)
        self.c_stray.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(r2, text="pF").pack(side="left")

        # Thresholds
        ctk.CTkLabel(self, text="MCU Thresholds", font=("", 13, "bold")).pack(anchor="w", padx=5, pady=(10, 2))
        thr = ctk.CTkFrame(self, fg_color="transparent"); thr.pack(fill="x", padx=5)

        r3 = ctk.CTkFrame(thr, fg_color="transparent"); r3.pack(fill="x", pady=1)
        ctk.CTkLabel(r3, text="VIL:", width=90).pack(side="left")
        self.vil = ctk.CTkEntry(r3, width=70); self.vil.pack(side="left", padx=2)
        self.vil.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(r3, text="V").pack(side="left")
        ctk.CTkLabel(r3, text="VIH:").pack(side="left", padx=(15, 2))
        self.vih = ctk.CTkEntry(r3, width=70); self.vih.pack(side="left", padx=2)
        self.vih.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(r3, text="V").pack(side="left")
        ctk.CTkLabel(r3, text="V_high:").pack(side="left", padx=(15, 2))
        self.v_high = ctk.CTkEntry(r3, width=70); self.v_high.pack(side="left", padx=2)
        self.v_high.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(r3, text="V").pack(side="left")

        # Digital sampling
        ctk.CTkLabel(self, text="Digital Sampling", font=("", 13, "bold")).pack(anchor="w", padx=5, pady=(10, 2))
        dig = ctk.CTkFrame(self, fg_color="transparent"); dig.pack(fill="x", padx=5)

        r4 = ctk.CTkFrame(dig, fg_color="transparent"); r4.pack(fill="x", pady=1)
        ctk.CTkLabel(r4, text="f_periph:", width=90).pack(side="left")
        self.f_periph = ctk.CTkEntry(r4, width=70); self.f_periph.pack(side="left", padx=2)
        self.f_periph.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(r4, text="MHz").pack(side="left")
        ctk.CTkLabel(r4, text="N_samples:").pack(side="left", padx=(15, 2))
        self.n_samples = ctk.CTkEntry(r4, width=50); self.n_samples.pack(side="left", padx=2)
        self.n_samples.bind("<KeyRelease>", self._on_change)

        # Counter overflow
        ctk.CTkLabel(self, text="Counter Overflow", font=("", 13, "bold")).pack(anchor="w", padx=5, pady=(10, 2))
        cnt = ctk.CTkFrame(self, fg_color="transparent"); cnt.pack(fill="x", padx=5)

        r5 = ctk.CTkFrame(cnt, fg_color="transparent"); r5.pack(fill="x", pady=1)
        ctk.CTkLabel(r5, text="Bits:", width=90).pack(side="left")
        self.counter_bits = ctk.CTkEntry(r5, width=50); self.counter_bits.pack(side="left", padx=2)
        self.counter_bits.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(r5, text="Signed:").pack(side="left", padx=(15, 2))
        self.counter_signed = ctk.CTkCheckBox(r5, text="", width=30)
        self.counter_signed.pack(side="left", padx=2)
        self.counter_signed.configure(command=self._on_change)
        ctk.CTkLabel(r5, text="f_read:").pack(side="left", padx=(15, 2))
        self.f_read = ctk.CTkEntry(r5, width=70); self.f_read.pack(side="left", padx=2)
        self.f_read.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(r5, text="Hz").pack(side="left")

    def push_to_state(self):
        bp = self.app_state.bandwidth_params
        bp.r_series_ohms = _safe_float(self.r_series, 100)
        bp.c_diode_pf = _safe_float(self.c_diode, 95)
        bp.c_pin_pf = _safe_float(self.c_pin, 10)
        bp.c_stray_pf = _safe_float(self.c_stray, 3)
        bp.vil_v = _safe_float(self.vil, 0.99)
        bp.vih_v = _safe_float(self.vih, 2.31)
        bp.v_high = _safe_float(self.v_high, 3.3)
        bp.f_peripheral_mhz = _safe_float(self.f_periph, 170)
        bp.n_samples = int(_safe_float(self.n_samples, 3))
        bp.counter_bits = int(_safe_float(self.counter_bits, 16))
        bp.counter_signed = bool(self.counter_signed.get())
        bp.f_read_hz = _safe_float(self.f_read, 1000)

    def _on_change(self, event=None):
        self.push_to_state()
        self.app_state.recalculate_bandwidth()
