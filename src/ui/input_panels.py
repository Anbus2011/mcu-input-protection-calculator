"""
Input panel classes for the Divider Calculator.
Each panel owns its CTk widgets and pushes values into AppState on change.
"""
from __future__ import annotations

import customtkinter as ctk
from typing import TYPE_CHECKING

from src.core.constants import ZENER_PRESETS, TVS_PRESETS, SCHOTTKY_PRESETS
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
        _attach_tooltip(self.r1_value, "R1 \u2014 upper divider resistor. Current-limiting between V_input and the divider node.")
        self.r1_unit = ctk.CTkComboBox(r1f, values=["\u03a9", "k\u03a9"], width=70,
                                        command=self._on_change)
        self.r1_unit.pack(side="left", padx=2)
        self.r1_unit.set("k\u03a9")
        _attach_tooltip(self.r1_unit, "R1 unit: \u03a9 or k\u03a9.")
        ctk.CTkLabel(r1f, text="Rating:").pack(side="left", padx=(10, 2))
        self.r1_rating = ctk.CTkEntry(r1f, width=60)
        self.r1_rating.pack(side="left", padx=2)
        self.r1_rating.bind("<KeyRelease>", self._on_change)
        _attach_tooltip(self.r1_rating, "R1 power rating (mW). Datasheet Ptot; used for margin % vs actual dissipation.")
        ctk.CTkLabel(r1f, text="mW").pack(side="left")
        ctk.CTkLabel(r1f, text="Tol:").pack(side="left", padx=(10, 2))
        self.r1_tol = ctk.CTkEntry(r1f, width=40)
        self.r1_tol.pack(side="left", padx=2)
        self.r1_tol.bind("<KeyRelease>", self._on_change)
        _attach_tooltip(self.r1_tol, "R1 tolerance %. Worst-case stack-up uses R1 \u00d7 (1 \u00b1 tol).")
        ctk.CTkLabel(r1f, text="%").pack(side="left")

        # R2
        r2f = ctk.CTkFrame(self, fg_color="transparent")
        r2f.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(r2f, text="R2:", width=40).pack(side="left")
        self.r2_value = ctk.CTkEntry(r2f, width=80)
        self.r2_value.pack(side="left", padx=2)
        self.r2_value.bind("<KeyRelease>", self._on_change)
        _attach_tooltip(self.r2_value, "R2 \u2014 lower divider resistor to GND. Sets divider ratio R2/(R1+R2).")
        self.r2_unit = ctk.CTkComboBox(r2f, values=["\u03a9", "k\u03a9"], width=70,
                                        command=self._on_change)
        self.r2_unit.pack(side="left", padx=2)
        self.r2_unit.set("k\u03a9")
        _attach_tooltip(self.r2_unit, "R2 unit: \u03a9 or k\u03a9.")
        ctk.CTkLabel(r2f, text="Rating:").pack(side="left", padx=(10, 2))
        self.r2_rating = ctk.CTkEntry(r2f, width=60)
        self.r2_rating.pack(side="left", padx=2)
        self.r2_rating.bind("<KeyRelease>", self._on_change)
        _attach_tooltip(self.r2_rating, "R2 power rating (mW). Used for margin calculation.")
        ctk.CTkLabel(r2f, text="mW").pack(side="left")
        ctk.CTkLabel(r2f, text="Tol:").pack(side="left", padx=(10, 2))
        self.r2_tol = ctk.CTkEntry(r2f, width=40)
        self.r2_tol.pack(side="left", padx=2)
        self.r2_tol.bind("<KeyRelease>", self._on_change)
        _attach_tooltip(self.r2_tol, "R2 tolerance %. Worst-case uses opposite sign from R1 to find V_mcu extremes.")
        ctk.CTkLabel(r2f, text="%").pack(side="left")

        # R_series
        rsf = ctk.CTkFrame(self, fg_color="transparent")
        rsf.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(rsf, text="R_s:", width=40).pack(side="left")
        self.rs_value = ctk.CTkEntry(rsf, width=80)
        self.rs_value.pack(side="left", padx=2)
        self.rs_value.bind("<KeyRelease>", self._on_change)
        _attach_tooltip(self.rs_value, "R_series \u2014 optional resistor between divider node and MCU pin. Adds ESD-current limiting and forms the bandwidth-limiting R with C_total.")
        self.rs_unit = ctk.CTkComboBox(rsf, values=["\u03a9", "k\u03a9"], width=70,
                                        command=self._on_change)
        self.rs_unit.pack(side="left", padx=2)
        self.rs_unit.set("\u03a9")
        _attach_tooltip(self.rs_unit, "R_series unit: \u03a9 or k\u03a9.")
        ctk.CTkLabel(rsf, text="Rating:").pack(side="left", padx=(10, 2))
        self.rs_rating = ctk.CTkEntry(rsf, width=60)
        self.rs_rating.pack(side="left", padx=2)
        self.rs_rating.bind("<KeyRelease>", self._on_change)
        _attach_tooltip(self.rs_rating, "R_series power rating (mW). Leave blank if unused.")
        ctk.CTkLabel(rsf, text="mW").pack(side="left")
        ctk.CTkLabel(rsf, text="Tol:").pack(side="left", padx=(10, 2))
        self.rs_tol = ctk.CTkEntry(rsf, width=40)
        self.rs_tol.pack(side="left", padx=2)
        self.rs_tol.bind("<KeyRelease>", self._on_change)
        _attach_tooltip(self.rs_tol, "R_series tolerance %. Leave blank if unused.")
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


# ── Clamp Panel ───────────────────────────────────────────────────────────────

# Maps display name -> internal type string
_CLAMP_TYPE_MAP = {
    "Zener": "zener",
    "TVS": "tvs",
    "Schottky": "schottky",
}
_CLAMP_TYPE_DISPLAY = {v: k for k, v in _CLAMP_TYPE_MAP.items()}

_PRESET_MAP = {
    "zener": ZENER_PRESETS,
    "tvs": TVS_PRESETS,
    "schottky": SCHOTTKY_PRESETS,
}


class ClampPanel(ctk.CTkFrame):
    """Dynamic clamp-type panel with type dropdown, preset dropdown,
    TVS polarity selector, Schottky info label, and rebuilt parameter fields."""

    def __init__(self, parent, state: AppState):
        super().__init__(parent)
        self.app_state = state
        # Track polarity separately so TVS rebuilds preserve it
        self._polarity = "unidirectional"
        self._build()

    # ── Initial build ─────────────────────────────────────────────────────────

    def _build(self):
        # Header row: title + clamp type dropdown
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(header, text="Clamp Diode", font=("", 14, "bold")).pack(side="left")
        self.clamp_type_cb = ctk.CTkComboBox(
            header, values=["Zener", "TVS", "Schottky"], width=120,
            command=self._on_clamp_type_change
        )
        self.clamp_type_cb.pack(side="right")
        _attach_tooltip(self.clamp_type_cb, "Clamp topology: Zener (3-region V-I, bidirectional), TVS (lower Z_dyn, uni/bi), Schottky (clamps to VDD + V_F, upper-rail only).")
        ctk.CTkLabel(header, text="Type:").pack(side="right", padx=5)

        # Preset row
        preset_row = ctk.CTkFrame(self, fg_color="transparent")
        preset_row.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(preset_row, text="Preset:").pack(side="left")
        self.preset_cb = ctk.CTkComboBox(
            preset_row, values=list(ZENER_PRESETS.keys()), width=180,
            command=self._on_preset_change
        )
        self.preset_cb.pack(side="left", padx=5)
        _attach_tooltip(self.preset_cb, "Built-in datasheet preset for the selected clamp type. Choose 'Custom' to enter values manually.")

        # TVS polarity row (hidden by default)
        self.polarity_row = ctk.CTkFrame(self, fg_color="transparent")
        ctk.CTkLabel(self.polarity_row, text="Polarity:").pack(side="left")
        self.polarity_cb = ctk.CTkComboBox(
            self.polarity_row,
            values=["unidirectional", "bidirectional"],
            width=160,
            command=self._on_polarity_change
        )
        self.polarity_cb.pack(side="left", padx=5)
        self.polarity_cb.set("unidirectional")
        _attach_tooltip(self.polarity_cb, "TVS polarity. Unidirectional clamps positive transients only. Bidirectional (CA suffix) required for AC signals.")

        # Schottky info label (hidden by default)
        self.schottky_info_row = ctk.CTkFrame(self, fg_color="transparent")
        ctk.CTkLabel(
            self.schottky_info_row,
            text="4 channels, 2 common-cathode pairs (BAT54CV)",
            text_color="gray60", font=("", 11)
        ).pack(side="left", padx=5)

        # Dynamic parameter fields container
        self.params_container = ctk.CTkFrame(self, fg_color="transparent")
        self.params_container.pack(fill="x", padx=10, pady=5)
        self._field_widgets = {}

        # Initialize with current AppState clamp_type
        init_type = getattr(self.app_state, 'clamp_type', 'zener')
        display = _CLAMP_TYPE_DISPLAY.get(init_type, 'Zener')
        self.clamp_type_cb.set(display)
        self._refresh_preset_list(init_type)
        init_preset = getattr(self.app_state, 'clamp_preset_name', '')
        if init_preset and init_preset in _PRESET_MAP.get(init_type, {}):
            self.preset_cb.set(init_preset)
        else:
            presets = list(_PRESET_MAP.get(init_type, {}).keys())
            self.preset_cb.set(presets[0] if presets else '')
        self._rebuild_fields(init_type)
        self._update_conditional_rows(init_type)

    # ── Preset list management ────────────────────────────────────────────────

    def _refresh_preset_list(self, clamp_type: str):
        presets = list(_PRESET_MAP.get(clamp_type, {}).keys())
        self.preset_cb.configure(values=presets)

    # ── Conditional row visibility ─────────────────────────────────────────────

    def _update_conditional_rows(self, clamp_type: str):
        # TVS polarity row
        if clamp_type == "tvs":
            self.polarity_row.pack(fill="x", padx=10, pady=2)
        else:
            self.polarity_row.pack_forget()

        # Schottky info label (only for BAT54CV preset)
        if clamp_type == "schottky" and self.preset_cb.get() == "BAT54CV":
            self.schottky_info_row.pack(fill="x", padx=10, pady=2)
        else:
            self.schottky_info_row.pack_forget()

    # ── Dynamic field builders ────────────────────────────────────────────────

    def _destroy_params(self):
        for child in self.params_container.winfo_children():
            child.destroy()
        self._field_widgets = {}

    def _rebuild_fields(self, clamp_type: str):
        self._destroy_params()
        if clamp_type == "zener":
            self._build_zener_fields()
        elif clamp_type == "tvs":
            self._build_tvs_fields()
        elif clamp_type == "schottky":
            self._build_schottky_fields()
        # Load current preset values into fresh fields
        preset_name = self.preset_cb.get()
        preset_dict = _PRESET_MAP.get(clamp_type, {}).get(preset_name, {})
        if preset_dict:
            self._load_preset_into_fields(preset_dict)

    def _build_zener_fields(self):
        LBL = 70
        ENT = 60
        UNT = 50
        LBL2 = 40
        pc = self.params_container

        zener_tips = {
            "vz_nom": "Nominal Zener voltage at IZT. Datasheet 'VZ typical'.",
            "vz_min": "Minimum Zener voltage at IZT. Used for typical-case knee.",
            "vz_max": "Maximum Zener voltage at IZT. Worst-case knee = 0.97 \u00d7 VZ_max.",
            "izt_ma": "Test current (mA) where VZ is specified. Typically 5 mA.",
            "zzt_typ": "Dynamic impedance ZZT at IZT, typical (\u03a9). Slope above the knee.",
            "zzt_max": "Dynamic impedance ZZT at IZT, max (\u03a9). Worst-case slope.",
            "izk_ma": "Knee current IZK (mA) \u2014 onset of breakdown. Typically 1 mA.",
            "zzk_typ": "Dynamic impedance ZZK at IZK, typical (\u03a9). Soft-breakdown slope.",
            "zzk_max": "Dynamic impedance ZZK at IZK, max (\u03a9).",
            "ptot_mw": "Total power dissipation (mW) at 25\u00b0C. Used for clamp-power margin.",
        }

        # Row 1: VZ nom, min, max
        row1 = ctk.CTkFrame(pc, fg_color="transparent")
        row1.pack(fill="x", pady=2)
        ctk.CTkLabel(row1, text="VZ nom:", width=LBL).pack(side="left")
        self._field_widgets["vz_nom"] = ctk.CTkEntry(row1, width=ENT)
        self._field_widgets["vz_nom"].pack(side="left", padx=2)
        self._field_widgets["vz_nom"].bind("<KeyRelease>", self._on_field_change)
        _attach_tooltip(self._field_widgets["vz_nom"], zener_tips["vz_nom"])
        ctk.CTkLabel(row1, text="V", width=LBL2).pack(side="left")
        ctk.CTkLabel(row1, text="min:", width=LBL2).pack(side="left")
        self._field_widgets["vz_min"] = ctk.CTkEntry(row1, width=ENT)
        self._field_widgets["vz_min"].pack(side="left", padx=2)
        self._field_widgets["vz_min"].bind("<KeyRelease>", self._on_field_change)
        _attach_tooltip(self._field_widgets["vz_min"], zener_tips["vz_min"])
        ctk.CTkLabel(row1, text="V", width=LBL2).pack(side="left")
        ctk.CTkLabel(row1, text="max:", width=LBL2).pack(side="left")
        self._field_widgets["vz_max"] = ctk.CTkEntry(row1, width=ENT)
        self._field_widgets["vz_max"].pack(side="left", padx=2)
        self._field_widgets["vz_max"].bind("<KeyRelease>", self._on_field_change)
        _attach_tooltip(self._field_widgets["vz_max"], zener_tips["vz_max"])
        ctk.CTkLabel(row1, text="V", width=LBL2).pack(side="left")

        # Row 2: IZT, ZZT typ/max
        row2 = ctk.CTkFrame(pc, fg_color="transparent")
        row2.pack(fill="x", pady=2)
        ctk.CTkLabel(row2, text="@IZT:", width=LBL).pack(side="left")
        self._field_widgets["izt_ma"] = ctk.CTkEntry(row2, width=ENT)
        self._field_widgets["izt_ma"].pack(side="left", padx=2)
        self._field_widgets["izt_ma"].bind("<KeyRelease>", self._on_field_change)
        _attach_tooltip(self._field_widgets["izt_ma"], zener_tips["izt_ma"])
        ctk.CTkLabel(row2, text="mA", width=LBL2).pack(side="left")
        ctk.CTkLabel(row2, text="ZZT:", width=LBL2).pack(side="left")
        self._field_widgets["zzt_typ"] = ctk.CTkEntry(row2, width=ENT)
        self._field_widgets["zzt_typ"].pack(side="left", padx=2)
        self._field_widgets["zzt_typ"].bind("<KeyRelease>", self._on_field_change)
        _attach_tooltip(self._field_widgets["zzt_typ"], zener_tips["zzt_typ"])
        ctk.CTkLabel(row2, text="\u03a9 typ", width=UNT).pack(side="left")
        self._field_widgets["zzt_max"] = ctk.CTkEntry(row2, width=ENT)
        self._field_widgets["zzt_max"].pack(side="left", padx=2)
        self._field_widgets["zzt_max"].bind("<KeyRelease>", self._on_field_change)
        _attach_tooltip(self._field_widgets["zzt_max"], zener_tips["zzt_max"])
        ctk.CTkLabel(row2, text="\u03a9 max", width=UNT).pack(side="left")

        # Row 3: IZK, ZZK typ/max
        row3 = ctk.CTkFrame(pc, fg_color="transparent")
        row3.pack(fill="x", pady=2)
        ctk.CTkLabel(row3, text="@IZK:", width=LBL).pack(side="left")
        self._field_widgets["izk_ma"] = ctk.CTkEntry(row3, width=ENT)
        self._field_widgets["izk_ma"].pack(side="left", padx=2)
        self._field_widgets["izk_ma"].bind("<KeyRelease>", self._on_field_change)
        _attach_tooltip(self._field_widgets["izk_ma"], zener_tips["izk_ma"])
        ctk.CTkLabel(row3, text="mA", width=LBL2).pack(side="left")
        ctk.CTkLabel(row3, text="ZZK:", width=LBL2).pack(side="left")
        self._field_widgets["zzk_typ"] = ctk.CTkEntry(row3, width=ENT)
        self._field_widgets["zzk_typ"].pack(side="left", padx=2)
        self._field_widgets["zzk_typ"].bind("<KeyRelease>", self._on_field_change)
        _attach_tooltip(self._field_widgets["zzk_typ"], zener_tips["zzk_typ"])
        ctk.CTkLabel(row3, text="\u03a9 typ", width=UNT).pack(side="left")
        self._field_widgets["zzk_max"] = ctk.CTkEntry(row3, width=ENT)
        self._field_widgets["zzk_max"].pack(side="left", padx=2)
        self._field_widgets["zzk_max"].bind("<KeyRelease>", self._on_field_change)
        _attach_tooltip(self._field_widgets["zzk_max"], zener_tips["zzk_max"])
        ctk.CTkLabel(row3, text="\u03a9 max", width=UNT).pack(side="left")

        # Row 4: Ptot
        row4 = ctk.CTkFrame(pc, fg_color="transparent")
        row4.pack(fill="x", pady=2)
        ctk.CTkLabel(row4, text="Ptot:", width=LBL).pack(side="left")
        self._field_widgets["ptot_mw"] = ctk.CTkEntry(row4, width=ENT)
        self._field_widgets["ptot_mw"].pack(side="left", padx=2)
        self._field_widgets["ptot_mw"].bind("<KeyRelease>", self._on_field_change)
        _attach_tooltip(self._field_widgets["ptot_mw"], zener_tips["ptot_mw"])
        ctk.CTkLabel(row4, text="mW", width=LBL2).pack(side="left")

    def _build_tvs_fields(self):
        pc = self.params_container
        tvs_tips = {
            "v_rwm":    "Reverse Working Max (V). TVS is fully off below V_RWM.",
            "v_br_min": "Minimum breakdown voltage at I_T.",
            "v_br_max": "Maximum breakdown voltage at I_T. Worst-case V_mcuH uses this.",
            "v_c":      "Clamping voltage at peak pulse current I_PP.",
            "i_pp":     "Peak pulse current (A) at which V_C is specified.",
            "i_t":      "Test current (mA) at which V_BR is measured. Typically 1 mA.",
            "c_pf":     "TVS junction capacitance at 0V bias (pF). Affects RC bandwidth.",
            "p_ppm_w":  "Peak pulse power (W). Max transient power the TVS can dissipate.",
        }
        fields = [
            ("V_RWM:",    "v_rwm",    "V"),
            ("V_BR min:", "v_br_min", "V"),
            ("V_BR max:", "v_br_max", "V"),
            ("V_C:",      "v_c",      "V"),
            ("I_PP:",     "i_pp",     "A"),
            ("I_T:",      "i_t",      "mA"),
            ("C:",        "c_pf",     "pF"),
            ("P_PPM:",    "p_ppm_w",  "W"),
        ]
        for i in range(0, len(fields), 2):
            row = ctk.CTkFrame(pc, fg_color="transparent")
            row.pack(fill="x", pady=2)
            for label, key, unit in fields[i:i+2]:
                ctk.CTkLabel(row, text=label, width=80).pack(side="left")
                entry = ctk.CTkEntry(row, width=70)
                entry.pack(side="left", padx=2)
                entry.bind("<KeyRelease>", self._on_field_change)
                _attach_tooltip(entry, tvs_tips[key])
                ctk.CTkLabel(row, text=unit, width=35).pack(side="left")
                self._field_widgets[key] = entry

    def _build_schottky_fields(self):
        pc = self.params_container
        schottky_tips = {
            "vf_typ":     "Typical forward voltage VF (V) at I_F_test.",
            "vf_max":     "Maximum forward voltage VF (V) at I_F_test. Worst-case clamp uses this.",
            "if_test_ma": "Test current (mA) at which VF is tabulated. Typically 10 mA.",
            "r_dynamic":  "Dynamic resistance (\u03a9) \u2014 slope of VF-vs-IF curve.",
            "ir_ua":      "Reverse leakage current (\u03bcA). Off-state leakage.",
            "vr_max":     "Maximum reverse voltage rating (V).",
            "cd_pf":      "Junction capacitance at 0V reverse bias (pF).",
            "pd_mw":      "Power dissipation rating (mW).",
            "channels":   "Number of diode channels in package (e.g. BAT54CV: 4 channels, 2 CC pairs).",
        }
        fields = [
            ("VF typ:",   "vf_typ",     "V"),
            ("VF max:",   "vf_max",     "V"),
            ("IF test:",  "if_test_ma", "mA"),
            ("R_dyn:",    "r_dynamic",  "\u03a9"),
            ("IR:",       "ir_ua",      "\u03bcA"),
            ("VR max:",   "vr_max",     "V"),
            ("C_d:",      "cd_pf",      "pF"),
            ("Pd:",       "pd_mw",      "mW"),
            ("Channels:", "channels",   ""),
        ]
        for i in range(0, len(fields), 2):
            row = ctk.CTkFrame(pc, fg_color="transparent")
            row.pack(fill="x", pady=2)
            for label, key, unit in fields[i:i+2]:
                ctk.CTkLabel(row, text=label, width=80).pack(side="left")
                entry = ctk.CTkEntry(row, width=70)
                entry.pack(side="left", padx=2)
                entry.bind("<KeyRelease>", self._on_field_change)
                _attach_tooltip(entry, schottky_tips[key])
                if unit:
                    ctk.CTkLabel(row, text=unit, width=35).pack(side="left")
                self._field_widgets[key] = entry

    # ── Preset loading ─────────────────────────────────────────────────────────

    def _load_preset_into_fields(self, preset_dict: dict):
        """Fill field widgets from a preset dict."""
        for key, widget in self._field_widgets.items():
            if key in preset_dict and preset_dict[key] is not None:
                _set_entry(widget, preset_dict[key])

    def _get_current_params(self) -> dict:
        """Read all field widgets into a param dict."""
        params = {}
        for key, widget in self._field_widgets.items():
            try:
                val = widget.get().strip()
                params[key] = float(val) if val else 0.0
            except (ValueError, AttributeError):
                params[key] = 0.0
        return params

    # ── Event handlers ─────────────────────────────────────────────────────────

    def _on_clamp_type_change(self, choice: str):
        clamp_type = _CLAMP_TYPE_MAP.get(choice, "zener")
        presets = list(_PRESET_MAP.get(clamp_type, {}).keys())
        first_preset = presets[0] if presets else "Custom"
        preset_dict = _PRESET_MAP.get(clamp_type, {}).get(first_preset, {})

        # Update polarity from preset default if TVS
        if clamp_type == "tvs":
            self._polarity = preset_dict.get("polarity_default", "unidirectional")
            self.polarity_cb.set(self._polarity)

        self.app_state.set_clamp_type(clamp_type)
        self.app_state.set_clamp_preset(first_preset)

        self._refresh_preset_list(clamp_type)
        self.preset_cb.set(first_preset)
        self._rebuild_fields(clamp_type)
        self._update_conditional_rows(clamp_type)

        params = self._get_current_params()
        polarity = self._polarity if clamp_type == "tvs" else None
        self.app_state.update_clamp(clamp_type, params, polarity)
        self.app_state.mark_dirty()
        self.app_state.recalculate()

    def _on_preset_change(self, choice: str):
        clamp_type = _CLAMP_TYPE_MAP.get(self.clamp_type_cb.get(), "zener")
        preset_dict = _PRESET_MAP.get(clamp_type, {}).get(choice, {})

        if clamp_type == "tvs":
            pol = preset_dict.get("polarity_default", self._polarity)
            self._polarity = pol
            self.polarity_cb.set(pol)

        self.app_state.set_clamp_preset(choice)
        self._load_preset_into_fields(preset_dict)
        self._update_conditional_rows(clamp_type)

        params = self._get_current_params()
        polarity = self._polarity if clamp_type == "tvs" else None
        self.app_state.update_clamp(clamp_type, params, polarity)
        self.app_state.mark_dirty()
        self.app_state.recalculate()

    def _on_polarity_change(self, choice: str):
        self._polarity = choice
        clamp_type = _CLAMP_TYPE_MAP.get(self.clamp_type_cb.get(), "zener")
        params = self._get_current_params()
        self.app_state.update_clamp(clamp_type, params, choice)
        self.app_state.mark_dirty()
        self.app_state.recalculate()

    def _on_field_change(self, event=None):
        clamp_type = _CLAMP_TYPE_MAP.get(self.clamp_type_cb.get(), "zener")
        params = self._get_current_params()
        polarity = self._polarity if clamp_type == "tvs" else None
        self.app_state.update_clamp(clamp_type, params, polarity)
        self.app_state.mark_dirty()
        self.app_state.recalculate()

    # ── Public interface ───────────────────────────────────────────────────────

    def push_to_state(self):
        """Push current UI values into AppState."""
        clamp_type = _CLAMP_TYPE_MAP.get(self.clamp_type_cb.get(), "zener")
        params = self._get_current_params()
        polarity = self._polarity if clamp_type == "tvs" else None
        self.app_state.set_clamp_preset(self.preset_cb.get())
        self.app_state.update_clamp(clamp_type, params, polarity)

    def load_from_data(self, data: dict):
        """Load from a .div data dict (v2.0 clamp block or v1.0 zener block)."""
        clamp = data.get("clamp", {})
        if not clamp:
            z = data.get("zener", {})
            clamp = {
                "type": "zener",
                "preset": z.get("preset", "BZB984-C3V3"),
                "polarity": None,
                "params": {k: v for k, v in z.items() if k != "preset"},
            }

        clamp_type = clamp.get("type", "zener")
        preset_name = clamp.get("preset", "")
        polarity = clamp.get("polarity") or "unidirectional"
        params = clamp.get("params", {})

        display = _CLAMP_TYPE_DISPLAY.get(clamp_type, "Zener")
        self.clamp_type_cb.set(display)
        self._refresh_preset_list(clamp_type)

        presets = list(_PRESET_MAP.get(clamp_type, {}).keys())
        if preset_name not in presets:
            preset_name = presets[0] if presets else "Custom"
        self.preset_cb.set(preset_name)

        if clamp_type == "tvs":
            self._polarity = polarity
            self.polarity_cb.set(polarity)

        self._rebuild_fields(clamp_type)
        for key, widget in self._field_widgets.items():
            if key in params and params[key] is not None:
                _set_entry(widget, params[key])

        self._update_conditional_rows(clamp_type)

    def clear_fields(self):
        for widget in self._field_widgets.values():
            _set_entry(widget, "")
        clamp_type = _CLAMP_TYPE_MAP.get(self.clamp_type_cb.get(), "zener")
        self._update_conditional_rows(clamp_type)


# Backward-compat alias
ZenerPanel = ClampPanel


# ── MCU Panel ─────────────────────────────────────────────────────────────────

class McuPanel(ctk.CTkFrame):
    def __init__(self, parent, state: AppState):
        super().__init__(parent)
        self.app_state = state
        self._build()

    def _build(self):
        LBL = 110  # label width
        ENT = 80   # entry width
        UNT = 35   # unit width

        ctk.CTkLabel(self, text="MCU Pin Input Limits", font=("", 14, "bold")).pack(anchor="w", padx=10, pady=5)
        params = ctk.CTkFrame(self, fg_color="transparent")
        params.pack(fill="x", padx=10, pady=5)

        row1 = ctk.CTkFrame(params, fg_color="transparent")
        row1.pack(fill="x", pady=2)
        ctk.CTkLabel(row1, text="VDD/VDDA:", width=LBL).pack(side="left")
        self.vdd = ctk.CTkEntry(row1, width=ENT); self.vdd.pack(side="left", padx=2)
        self.vdd.bind("<KeyRelease>", self._on_change)
        _attach_tooltip(self.vdd, "MCU supply voltage VDD/VDDA (V). Schottky clamps to VDD + V_F.")
        ctk.CTkLabel(row1, text="V", width=UNT).pack(side="left")

        row2 = ctk.CTkFrame(params, fg_color="transparent")
        row2.pack(fill="x", pady=2)
        ctk.CTkLabel(row2, text="Safe Max:", width=LBL).pack(side="left")
        self.rec_max = ctk.CTkEntry(row2, width=ENT); self.rec_max.pack(side="left", padx=2)
        self.rec_max.bind("<KeyRelease>", self._on_change)
        _attach_tooltip(self.rec_max, "Recommended max pin voltage (V). Typically VDDA + 0.3V; above this begins to bias internal ESD diodes.")
        ctk.CTkLabel(row2, text="V", width=UNT).pack(side="left")

        row3 = ctk.CTkFrame(params, fg_color="transparent")
        row3.pack(fill="x", pady=2)
        ctk.CTkLabel(row3, text="Abs. Max:", width=LBL).pack(side="left")
        self.abs_max = ctk.CTkEntry(row3, width=ENT); self.abs_max.pack(side="left", padx=2)
        self.abs_max.bind("<KeyRelease>", self._on_change)
        _attach_tooltip(self.abs_max, "Absolute max pin voltage (V). Damage threshold — never exceed.")
        ctk.CTkLabel(row3, text="V", width=UNT).pack(side="left")

        row4 = ctk.CTkFrame(params, fg_color="transparent")
        row4.pack(fill="x", pady=2)
        ctk.CTkLabel(row4, text="Injection Limit:", width=LBL).pack(side="left")
        self.inj_safe = ctk.CTkEntry(row4, width=ENT); self.inj_safe.pack(side="left", padx=2)
        self.inj_safe.bind("<KeyRelease>", self._on_change)
        _attach_tooltip(self.inj_safe, "Maximum safe ESD injection current (mA) into a pin.")
        ctk.CTkLabel(row4, text="mA", width=UNT).pack(side="left")

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
        LBL = 110  # label width
        ENT = 80   # entry width
        UNT = 45   # unit width

        ctk.CTkLabel(self, text="System Requirements", font=("", 14, "bold")).pack(anchor="w", padx=10, pady=5)
        params = ctk.CTkFrame(self, fg_color="transparent")
        params.pack(fill="x", padx=10, pady=5)

        row1 = ctk.CTkFrame(params, fg_color="transparent")
        row1.pack(fill="x", pady=2)
        ctk.CTkLabel(row1, text="Max Input:", width=LBL).pack(side="left")
        self.vin_max = ctk.CTkEntry(row1, width=ENT); self.vin_max.pack(side="left", padx=2)
        self.vin_max.bind("<KeyRelease>", self._on_change)
        _attach_tooltip(self.vin_max, "Maximum expected signal voltage at divider input (V). Drives worst-case calcs.")
        ctk.CTkLabel(row1, text="V", width=UNT).pack(side="left")

        row2 = ctk.CTkFrame(params, fg_color="transparent")
        row2.pack(fill="x", pady=2)
        ctk.CTkLabel(row2, text="ADC Scale:", width=LBL).pack(side="left")
        self.analog_fs = ctk.CTkEntry(row2, width=ENT); self.analog_fs.pack(side="left", padx=2)
        self.analog_fs.bind("<KeyRelease>", self._on_change)
        _attach_tooltip(self.analog_fs, "Input voltage that maps to ADC full-scale (V). Used for mV/LSB resolution.")
        ctk.CTkLabel(row2, text="V", width=UNT).pack(side="left")

        row3 = ctk.CTkFrame(params, fg_color="transparent")
        row3.pack(fill="x", pady=2)
        ctk.CTkLabel(row3, text="Logic High:", width=LBL).pack(side="left")
        self.logic_high = ctk.CTkEntry(row3, width=ENT); self.logic_high.pack(side="left", padx=2)
        self.logic_high.bind("<KeyRelease>", self._on_change)
        _attach_tooltip(self.logic_high, "Minimum input voltage that must read as logic HIGH (V). VIH requirement at MCU.")
        ctk.CTkLabel(row3, text="V min", width=UNT).pack(side="left")

        row4 = ctk.CTkFrame(params, fg_color="transparent")
        row4.pack(fill="x", pady=2)
        ctk.CTkLabel(row4, text="Logic Low:", width=LBL).pack(side="left")
        self.logic_low = ctk.CTkEntry(row4, width=ENT); self.logic_low.pack(side="left", padx=2)
        self.logic_low.bind("<KeyRelease>", self._on_change)
        _attach_tooltip(self.logic_low, "Maximum input voltage that must read as logic LOW (V). VIL requirement at MCU.")
        ctk.CTkLabel(row4, text="V max", width=UNT).pack(side="left")

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
    """Popup tooltip that appears near a widget on hover or click.
    Click mode auto-dismisses after 4 seconds; hover-only mode dismisses on mouse-leave."""

    def __init__(self, widget: ctk.CTkBaseClass, text: str, hover_only: bool = False):
        self.widget = widget
        self.text = text
        self.hover_only = hover_only
        self._tw = None
        self._hide_id = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)
        if not hover_only:
            widget.bind("<Button-1>", self._toggle)

    def _show(self, event=None):
        if self._tw:
            return
        self._tw = tw = ctk.CTkToplevel()
        tw.wm_overrideredirect(True)
        tw.attributes("-topmost", True)
        tw.bind("<Button-1>", lambda e: self._hide())
        frame = ctk.CTkFrame(tw, corner_radius=6, border_width=1,
                             border_color="gray50", fg_color=("gray90", "gray20"))
        frame.pack()
        ctk.CTkLabel(frame, text=self.text, wraplength=300, justify="left",
                     font=("", 12), padx=8, pady=6).pack()

        # Place below or above the widget, whichever side has more screen room.
        tw.update_idletasks()
        tip_h = tw.winfo_reqheight()
        widget_x = self.widget.winfo_rootx()
        widget_y_top = self.widget.winfo_rooty()
        widget_y_bottom = widget_y_top + self.widget.winfo_height()
        screen_h = self.widget.winfo_screenheight()
        space_below = screen_h - widget_y_bottom
        space_above = widget_y_top
        if space_below >= space_above:
            y = widget_y_bottom + 4
        else:
            y = max(0, widget_y_top - tip_h - 4)
        tw.wm_geometry(f"+{widget_x}+{y}")

        if not self.hover_only:
            self._hide_id = self.widget.after(4000, self._hide)

    def _hide(self, event=None):
        if self._hide_id:
            try:
                self.widget.after_cancel(self._hide_id)
            except Exception:
                pass
            self._hide_id = None
        if self._tw:
            try:
                self._tw.destroy()
            except Exception:
                pass
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


def _attach_tooltip(widget, text: str):
    """Attach a hover-only tooltip directly to an editable widget."""
    _Tooltip(widget, text, hover_only=True)


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
        ctk.CTkLabel(a1, text="R_source:", width=90, text_color="gray60").pack(side="left")
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

        LBL_W = 90
        ENT_W = 80
        UNIT_W = 35

        ctk.CTkLabel(self, text="Capacitance", font=("", 13, "bold")).pack(anchor="w", padx=5, pady=(10, 2))
        cap = ctk.CTkFrame(self, fg_color="transparent"); cap.pack(fill="x", padx=5)

        c1 = ctk.CTkFrame(cap, fg_color="transparent"); c1.pack(fill="x", pady=2)
        ctk.CTkLabel(c1, text="C_diode:", width=LBL_W).pack(side="left")
        self.c_diode = ctk.CTkEntry(c1, width=ENT_W); self.c_diode.pack(side="left", padx=2)
        self.c_diode.bind("<KeyRelease>", self._on_change)
        _attach_tooltip(self.c_diode, "Protection diode junction capacitance at 0V reverse bias (pF). Datasheet 'Cj'.")
        ctk.CTkLabel(c1, text="pF", width=UNIT_W).pack(side="left")
        _help_btn(c1, "Protection diode junction capacitance at 0V reverse bias.\nFind in the diode datasheet under \"junction capacitance\" or \"Cj\".")

        c2 = ctk.CTkFrame(cap, fg_color="transparent"); c2.pack(fill="x", pady=2)
        ctk.CTkLabel(c2, text="C_pin:", width=LBL_W).pack(side="left")
        self.c_pin = ctk.CTkEntry(c2, width=ENT_W); self.c_pin.pack(side="left", padx=2)
        self.c_pin.bind("<KeyRelease>", self._on_change)
        _attach_tooltip(self.c_pin, "MCU GPIO input capacitance (pF). MCU datasheet GPIO electrical specs.")
        ctk.CTkLabel(c2, text="pF", width=UNIT_W).pack(side="left")
        _help_btn(c2, "MCU GPIO input capacitance.\nFind in the MCU datasheet under GPIO electrical specifications.")

        c3 = ctk.CTkFrame(cap, fg_color="transparent"); c3.pack(fill="x", pady=2)
        ctk.CTkLabel(c3, text="C_stray:", width=LBL_W).pack(side="left")
        self.c_stray = ctk.CTkEntry(c3, width=ENT_W); self.c_stray.pack(side="left", padx=2)
        self.c_stray.bind("<KeyRelease>", self._on_change)
        _attach_tooltip(self.c_stray, "PCB parasitic capacitance estimate (pF). Typically 2-5 pF.")
        ctk.CTkLabel(c3, text="pF", width=UNIT_W).pack(side="left")
        _help_btn(c3, "PCB parasitic/stray capacitance estimate.\nTypically 2-5 pF. Depends on trace length and layout.")

        ctk.CTkLabel(self, text="Digital Sampling", font=("", 13, "bold")).pack(anchor="w", padx=5, pady=(10, 2))
        dig = ctk.CTkFrame(self, fg_color="transparent"); dig.pack(fill="x", padx=5)

        d1 = ctk.CTkFrame(dig, fg_color="transparent"); d1.pack(fill="x", pady=2)
        ctk.CTkLabel(d1, text="f_periph:", width=LBL_W).pack(side="left")
        self.f_periph = ctk.CTkEntry(d1, width=ENT_W); self.f_periph.pack(side="left", padx=2)
        self.f_periph.bind("<KeyRelease>", self._on_change)
        _attach_tooltip(self.f_periph, "Peripheral clock frequency sampling the pin (MHz). MCU reference manual clock tree.")
        ctk.CTkLabel(d1, text="MHz", width=UNIT_W).pack(side="left")
        _help_btn(d1, "Peripheral clock frequency that samples the input pin.\nFind in the MCU reference manual clock tree diagram.")

        d2 = ctk.CTkFrame(dig, fg_color="transparent"); d2.pack(fill="x", pady=2)
        ctk.CTkLabel(d2, text="N_samples:", width=LBL_W).pack(side="left")
        self.n_samples = ctk.CTkEntry(d2, width=ENT_W); self.n_samples.pack(side="left", padx=2)
        self.n_samples.bind("<KeyRelease>", self._on_change)
        _attach_tooltip(self.n_samples, "Min consecutive samples required for valid edge detection (digital filter).")
        ctk.CTkLabel(d2, text="", width=UNIT_W).pack(side="left")
        _help_btn(d2, "Minimum consecutive samples required for valid edge detection.\nFind in the MCU reference manual under timer/input capture digital filter settings.")

        ctk.CTkLabel(self, text="Counter Overflow", font=("", 13, "bold")).pack(anchor="w", padx=5, pady=(10, 2))
        cnt = ctk.CTkFrame(self, fg_color="transparent"); cnt.pack(fill="x", padx=5)

        e1 = ctk.CTkFrame(cnt, fg_color="transparent"); e1.pack(fill="x", pady=2)
        ctk.CTkLabel(e1, text="Bits:", width=LBL_W).pack(side="left")
        self.counter_bits = ctk.CTkEntry(e1, width=ENT_W); self.counter_bits.pack(side="left", padx=2)
        self.counter_bits.bind("<KeyRelease>", self._on_change)
        _attach_tooltip(self.counter_bits, "Hardware counter width in bits (e.g. 16 or 32).")
        ctk.CTkLabel(e1, text="", width=UNIT_W).pack(side="left")
        _help_btn(e1, "Hardware counter width in bits (e.g. 16 or 32).\nFind in the MCU reference manual under timer/counter chapter.")

        e2 = ctk.CTkFrame(cnt, fg_color="transparent"); e2.pack(fill="x", pady=2)
        ctk.CTkLabel(e2, text="Signed:", width=LBL_W).pack(side="left")
        self.counter_signed = ctk.CTkCheckBox(e2, text="", width=ENT_W)
        self.counter_signed.pack(side="left", padx=2)
        self.counter_signed.configure(command=self._on_change)
        _attach_tooltip(self.counter_signed, "Check if counter is signed (+/-); signed halves max range.")
        ctk.CTkLabel(e2, text="", width=UNIT_W).pack(side="left")
        _help_btn(e2, "Check if the counter counts +/- (signed).\nUses one bit for sign, halving the max count range.")

        e3 = ctk.CTkFrame(cnt, fg_color="transparent"); e3.pack(fill="x", pady=2)
        ctk.CTkLabel(e3, text="f_read:", width=LBL_W).pack(side="left")
        self.f_read = ctk.CTkEntry(e3, width=ENT_W); self.f_read.pack(side="left", padx=2)
        self.f_read.bind("<KeyRelease>", self._on_change)
        _attach_tooltip(self.f_read, "Firmware counter read/reset rate (Hz). Typically your control loop rate.")
        ctk.CTkLabel(e3, text="Hz", width=UNIT_W).pack(side="left")
        _help_btn(e3, "How often firmware reads/resets the counter.\nTypically your PID loop rate or main polling frequency.")

    def _r_source_ohms(self) -> float:
        """Thévenin source impedance seen by C_total at the protection node.
        R_source = (R1 || R2) + R_series. Matches the Component Analysis tab."""
        r = self.app_state.resistors
        r1, r2, rs = r.r1_ohms, r.r2_ohms, r.rs_ohms
        r_par = (r1 * r2) / (r1 + r2) if (r1 + r2) > 0 else 0.0
        return r_par + rs

    def push_to_state(self):
        bp = self.app_state.bandwidth_params
        bp.r_series_ohms = self._r_source_ohms()
        vdd = self.app_state.mcu.vdd
        # MCU pin CMOS input thresholds (standard 0.3/0.7 × Vdd).
        # NOT the same as system.v_logic_high_min/low_max (those describe the
        # input source's logic-level spec, used by the Input Levels tab).
        bp.vil_v = 0.3 * vdd if vdd > 0 else 0
        bp.vih_v = 0.7 * vdd if vdd > 0 else 0
        bp.v_high = vdd
        bp.c_diode_pf = _safe_float(self.c_diode, 0)
        bp.c_pin_pf = _safe_float(self.c_pin, 0)
        bp.c_stray_pf = _safe_float(self.c_stray, 0)
        bp.f_peripheral_mhz = _safe_float(self.f_periph, 0)
        bp.n_samples = int(_safe_float(self.n_samples, 0))
        bp.counter_bits = int(_safe_float(self.counter_bits, 0))
        bp.counter_signed = bool(self.counter_signed.get())
        bp.f_read_hz = _safe_float(self.f_read, 0)

    def refresh_auto_values(self):
        """Update the read-only labels from AppState (called after main recalc).
        VIL/VIH shown here are the MCU PIN's CMOS input thresholds (0.3/0.7×Vdd),
        not the signal-source logic-level spec from SystemPanel."""
        r_source = self._r_source_ohms()
        vdd = self.app_state.mcu.vdd
        vil = 0.3 * vdd if vdd > 0 else 0
        vih = 0.7 * vdd if vdd > 0 else 0
        self.lbl_rs.configure(text=f"{r_source:.0f}" if r_source > 0 else "--")
        self.lbl_vil.configure(text=f"{vil:.2f}" if vdd > 0 else "--")
        self.lbl_vih.configure(text=f"{vih:.2f}" if vdd > 0 else "--")
        self.lbl_vhigh.configure(text=f"{vdd:.2f}" if vdd > 0 else "--")

    def _on_change(self, event=None):
        self.push_to_state()
        self.app_state.recalculate_bandwidth()
