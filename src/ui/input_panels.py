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


# ── Tooltip Helper ────────────────────────────────────────────────────────────

class _Tooltip:
    """Popup tooltip that appears near a widget on hover or click."""

    def __init__(self, widget: ctk.CTkBaseClass, text: str):
        self.widget = widget
        self.text = text
        self._tw = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)
        widget.bind("<Button-1>", self._toggle)

    def _show(self, event=None):
        if self._tw:
            return
        x = self.widget.winfo_rootx() + self.widget.winfo_width() + 5
        y = self.widget.winfo_rooty()
        self._tw = tw = ctk.CTkToplevel()
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.attributes("-topmost", True)
        frame = ctk.CTkFrame(tw, corner_radius=6, border_width=1,
                             border_color="gray50", fg_color=("gray90", "gray20"))
        frame.pack()
        ctk.CTkLabel(frame, text=self.text, wraplength=300, justify="left",
                     font=("", 12), padx=8, pady=6).pack()

    def _hide(self, event=None):
        if self._tw:
            self._tw.destroy()
            self._tw = None

    def _toggle(self, event=None):
        if self._tw:
            self._hide()
        else:
            self._show()


def _help_btn(parent, text: str):
    """Create a small '?' button with a tooltip."""
    btn = ctk.CTkLabel(parent, text="?", width=18, height=18,
                       fg_color=("gray75", "gray35"), corner_radius=9,
                       font=("", 11, "bold"), text_color=("gray30", "gray80"),
                       cursor="hand2")
    btn.pack(side="left", padx=(4, 0))
    _Tooltip(btn, text)
    return btn


# ── Bandwidth / PPS Input Panel ───────────────────────────────────────────────

class BandwidthInputPanel(ctk.CTkFrame):
    """Input fields for the Signal Bandwidth / PPS analysis tab.

    R_series, VIL, VIH, and V_high are auto-pulled from the other panels
    via AppState. Only bandwidth-specific inputs are shown here.
    """

    def __init__(self, parent, state: AppState):
        super().__init__(parent, fg_color="transparent")
        self.app_state = state
        self._build()

    def _build(self):
        # Auto-derived values (read-only display)
        ctk.CTkLabel(self, text="From Other Panels", font=("", 13, "bold")).pack(anchor="w", padx=5, pady=(5, 2))
        auto = ctk.CTkFrame(self, fg_color="transparent"); auto.pack(fill="x", padx=5)

        a1 = ctk.CTkFrame(auto, fg_color="transparent"); a1.pack(fill="x", pady=1)
        ctk.CTkLabel(a1, text="R_series:", width=90, text_color="gray60").pack(side="left")
        self.lbl_rs = ctk.CTkLabel(a1, text="--", width=70, anchor="w", text_color="gray60")
        self.lbl_rs.pack(side="left", padx=2)
        ctk.CTkLabel(a1, text="\u03a9", text_color="gray60").pack(side="left")
        ctk.CTkLabel(a1, text="VIL:", text_color="gray60").pack(side="left", padx=(15, 2))
        self.lbl_vil = ctk.CTkLabel(a1, text="--", width=50, anchor="w", text_color="gray60")
        self.lbl_vil.pack(side="left", padx=2)
        ctk.CTkLabel(a1, text="V", text_color="gray60").pack(side="left")
        ctk.CTkLabel(a1, text="VIH:", text_color="gray60").pack(side="left", padx=(15, 2))
        self.lbl_vih = ctk.CTkLabel(a1, text="--", width=50, anchor="w", text_color="gray60")
        self.lbl_vih.pack(side="left", padx=2)
        ctk.CTkLabel(a1, text="V", text_color="gray60").pack(side="left")
        ctk.CTkLabel(a1, text="V_high:", text_color="gray60").pack(side="left", padx=(15, 2))
        self.lbl_vhigh = ctk.CTkLabel(a1, text="--", width=50, anchor="w", text_color="gray60")
        self.lbl_vhigh.pack(side="left", padx=2)
        ctk.CTkLabel(a1, text="V", text_color="gray60").pack(side="left")

        # Uniform widths for all rows
        LBL_W = 90   # label width
        ENT_W = 80   # entry width
        UNIT_W = 35  # unit label width

        # Capacitance (bandwidth-specific)
        ctk.CTkLabel(self, text="Capacitance", font=("", 13, "bold")).pack(anchor="w", padx=5, pady=(10, 2))
        cap = ctk.CTkFrame(self, fg_color="transparent"); cap.pack(fill="x", padx=5)

        c1 = ctk.CTkFrame(cap, fg_color="transparent"); c1.pack(fill="x", pady=2)
        ctk.CTkLabel(c1, text="C_diode:", width=LBL_W).pack(side="left")
        self.c_diode = ctk.CTkEntry(c1, width=ENT_W); self.c_diode.pack(side="left", padx=2)
        self.c_diode.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(c1, text="pF", width=UNIT_W).pack(side="left")
        _help_btn(c1, "Protection diode junction capacitance at 0V reverse bias.\nFind in the diode datasheet under \"junction capacitance\" or \"Cj\".")

        c2 = ctk.CTkFrame(cap, fg_color="transparent"); c2.pack(fill="x", pady=2)
        ctk.CTkLabel(c2, text="C_pin:", width=LBL_W).pack(side="left")
        self.c_pin = ctk.CTkEntry(c2, width=ENT_W); self.c_pin.pack(side="left", padx=2)
        self.c_pin.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(c2, text="pF", width=UNIT_W).pack(side="left")
        _help_btn(c2, "MCU GPIO input capacitance.\nFind in the MCU datasheet under GPIO electrical specifications.")

        c3 = ctk.CTkFrame(cap, fg_color="transparent"); c3.pack(fill="x", pady=2)
        ctk.CTkLabel(c3, text="C_stray:", width=LBL_W).pack(side="left")
        self.c_stray = ctk.CTkEntry(c3, width=ENT_W); self.c_stray.pack(side="left", padx=2)
        self.c_stray.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(c3, text="pF", width=UNIT_W).pack(side="left")
        _help_btn(c3, "PCB parasitic/stray capacitance estimate.\nTypically 2-5 pF. Depends on trace length and layout.")

        # Digital sampling
        ctk.CTkLabel(self, text="Digital Sampling", font=("", 13, "bold")).pack(anchor="w", padx=5, pady=(10, 2))
        dig = ctk.CTkFrame(self, fg_color="transparent"); dig.pack(fill="x", padx=5)

        d1 = ctk.CTkFrame(dig, fg_color="transparent"); d1.pack(fill="x", pady=2)
        ctk.CTkLabel(d1, text="f_periph:", width=LBL_W).pack(side="left")
        self.f_periph = ctk.CTkEntry(d1, width=ENT_W); self.f_periph.pack(side="left", padx=2)
        self.f_periph.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(d1, text="MHz", width=UNIT_W).pack(side="left")
        _help_btn(d1, "Peripheral clock frequency that samples the input pin.\nFind in the MCU reference manual clock tree diagram.")

        d2 = ctk.CTkFrame(dig, fg_color="transparent"); d2.pack(fill="x", pady=2)
        ctk.CTkLabel(d2, text="N_samples:", width=LBL_W).pack(side="left")
        self.n_samples = ctk.CTkEntry(d2, width=ENT_W); self.n_samples.pack(side="left", padx=2)
        self.n_samples.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(d2, text="", width=UNIT_W).pack(side="left")
        _help_btn(d2, "Minimum consecutive samples required for valid edge detection.\nFind in the MCU reference manual under timer/input capture digital filter settings.")

        # Counter overflow
        ctk.CTkLabel(self, text="Counter Overflow", font=("", 13, "bold")).pack(anchor="w", padx=5, pady=(10, 2))
        cnt = ctk.CTkFrame(self, fg_color="transparent"); cnt.pack(fill="x", padx=5)

        e1 = ctk.CTkFrame(cnt, fg_color="transparent"); e1.pack(fill="x", pady=2)
        ctk.CTkLabel(e1, text="Bits:", width=LBL_W).pack(side="left")
        self.counter_bits = ctk.CTkEntry(e1, width=ENT_W); self.counter_bits.pack(side="left", padx=2)
        self.counter_bits.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(e1, text="", width=UNIT_W).pack(side="left")
        _help_btn(e1, "Hardware counter width in bits (e.g. 16 or 32).\nFind in the MCU reference manual under timer/counter chapter.")

        e2 = ctk.CTkFrame(cnt, fg_color="transparent"); e2.pack(fill="x", pady=2)
        ctk.CTkLabel(e2, text="Signed:", width=LBL_W).pack(side="left")
        self.counter_signed = ctk.CTkCheckBox(e2, text="", width=ENT_W)
        self.counter_signed.pack(side="left", padx=2)
        self.counter_signed.configure(command=self._on_change)
        ctk.CTkLabel(e2, text="", width=UNIT_W).pack(side="left")
        _help_btn(e2, "Check if the counter counts +/- (signed).\nUses one bit for sign, halving the max count range.")

        e3 = ctk.CTkFrame(cnt, fg_color="transparent"); e3.pack(fill="x", pady=2)
        ctk.CTkLabel(e3, text="f_read:", width=LBL_W).pack(side="left")
        self.f_read = ctk.CTkEntry(e3, width=ENT_W); self.f_read.pack(side="left", padx=2)
        self.f_read.bind("<KeyRelease>", self._on_change)
        ctk.CTkLabel(e3, text="Hz", width=UNIT_W).pack(side="left")
        _help_btn(e3, "How often firmware reads/resets the counter.\nTypically your PID loop rate or main polling frequency.")

    def push_to_state(self):
        bp = self.app_state.bandwidth_params
        # Auto-pull from other panels via AppState
        bp.r_series_ohms = self.app_state.resistors.rs_ohms
        vdd = self.app_state.mcu.vdd
        bp.vil_v = self.app_state.system.v_logic_low_max * (vdd / 3.3) if vdd > 0 else 0
        bp.vih_v = self.app_state.system.v_logic_high_min * (vdd / 3.3) if vdd > 0 else 0
        bp.v_high = vdd
        # Bandwidth-specific inputs
        bp.c_diode_pf = _safe_float(self.c_diode, 0)
        bp.c_pin_pf = _safe_float(self.c_pin, 0)
        bp.c_stray_pf = _safe_float(self.c_stray, 0)
        bp.f_peripheral_mhz = _safe_float(self.f_periph, 0)
        bp.n_samples = int(_safe_float(self.n_samples, 0))
        bp.counter_bits = int(_safe_float(self.counter_bits, 0))
        bp.counter_signed = bool(self.counter_signed.get())
        bp.f_read_hz = _safe_float(self.f_read, 0)

    def refresh_auto_values(self):
        """Update the read-only labels from AppState (called after main recalc)."""
        rs = self.app_state.resistors.rs_ohms
        vdd = self.app_state.mcu.vdd
        vil = self.app_state.system.v_logic_low_max * (vdd / 3.3) if vdd > 0 else 0
        vih = self.app_state.system.v_logic_high_min * (vdd / 3.3) if vdd > 0 else 0
        self.lbl_rs.configure(text=f"{rs:.0f}" if rs else "--")
        self.lbl_vil.configure(text=f"{vil:.2f}" if vdd > 0 else "--")
        self.lbl_vih.configure(text=f"{vih:.2f}" if vdd > 0 else "--")
        self.lbl_vhigh.configure(text=f"{vdd:.2f}" if vdd > 0 else "--")

    def _on_change(self, event=None):
        self.push_to_state()
        self.app_state.recalculate_bandwidth()
