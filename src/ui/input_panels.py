"""
Input panel classes for the Divider Calculator.

Each panel owns its CTk widgets. Every input is bound to a Tk variable whose
write trace forwards the raw text to AppState.set_field, so typing, paste,
cut, delete, selection and programmatic changes are all seen. Panels never
parse or calculate; AppState does. sync_from_state() copies AppState's text
back into the widgets after AppState changed it (load, new, preset, fill).
"""
from __future__ import annotations

import customtkinter as ctk
from typing import TYPE_CHECKING

from src.core.constants import CUSTOM_PRESET, RESISTOR_UNITS, ZENER_PRESETS

if TYPE_CHECKING:
    from src.core.app_state import AppState


UNIT_CHOICES = list(RESISTOR_UNITS.keys())
NEEDS_INPUT = "needs input"
MUTED = "gray60"
ZZK_NOTE = "ZZK: reference only, not used in the calculation"
ZZK_TOOLTIP = ("ZZK (dynamic impedance at IZK) is reference only and is not "
               "used in the calculation. The Zener V-I model uses VZ, IZT, IZK "
               "and ZZT; you can leave ZZK blank.")


# ── Tooltip Helper ────────────────────────────────────────────────────────────

class _Tooltip:
    """Popup tooltip that appears near a widget on hover or click.
    Auto-dismisses after 4 seconds or when the mouse leaves."""

    def __init__(self, widget: ctk.CTkBaseClass, text: str):
        self.widget = widget
        self.text = text
        self._tw = None
        self._hide_id = None
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
        # Close tooltip if user clicks anywhere on it
        tw.bind("<Button-1>", lambda e: self._hide())
        frame = ctk.CTkFrame(tw, corner_radius=6, border_width=1,
                             border_color="gray50", fg_color=("gray90", "gray20"))
        frame.pack()
        ctk.CTkLabel(frame, text=self.text, wraplength=300, justify="left",
                     font=("", 12), padx=8, pady=6).pack()
        # Auto-dismiss after 4 seconds
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


# ── Base panel: field registration and syncing ────────────────────────────────

class _FieldPanel(ctk.CTkFrame):
    def __init__(self, parent, state: AppState, **kw):
        super().__init__(parent, **kw)
        self.app_state = state
        self.vars: dict = {}      # field key -> Tk variable
        self.widgets: dict = {}   # field key -> widget
        self._build()
        self.sync_from_state()

    def _build(self):
        raise NotImplementedError

    def _add_field(self, key, var, widget):
        self.vars[key] = var
        self.widgets[key] = widget
        var.trace_add("write", lambda *_: self.app_state.set_field(key, var.get()))

    def _entry(self, parent, key, width):
        var = ctk.StringVar(master=self, value="")
        e = ctk.CTkEntry(parent, width=width, textvariable=var)
        self._add_field(key, var, e)
        return e

    def _unit_combo(self, parent, key, width=70):
        var = ctk.StringVar(master=self, value="")
        c = ctk.CTkComboBox(parent, values=UNIT_CHOICES, width=width,
                            variable=var, state="readonly")
        self._add_field(key, var, c)
        return c

    def _checkbox(self, parent, key, width):
        var = ctk.StringVar(master=self, value="0")
        c = ctk.CTkCheckBox(parent, text="", width=width, variable=var,
                            onvalue="1", offvalue="0")
        self._add_field(key, var, c)
        return c

    def sync_from_state(self):
        """Copy AppState's field text into the widgets (no-op where equal)."""
        for key, var in self.vars.items():
            text = self.app_state.fields[key]
            if var.get() != text:
                var.set(text)


# ── Resistor Panel ────────────────────────────────────────────────────────────

class ResistorPanel(_FieldPanel):
    def _build(self):
        ctk.CTkLabel(self, text="Resistors", font=("", 14, "bold")).pack(anchor="w", padx=10, pady=5)
        for prefix, label in (("r1", "R1:"), ("r2", "R2:"), ("rs", "R_s:")):
            row = ctk.CTkFrame(self, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(row, text=label, width=40).pack(side="left")
            self._entry(row, f"{prefix}.value", 80).pack(side="left", padx=2)
            self._unit_combo(row, f"{prefix}.unit").pack(side="left", padx=2)
            ctk.CTkLabel(row, text="Rating:").pack(side="left", padx=(10, 2))
            self._entry(row, f"{prefix}.rating", 60).pack(side="left", padx=2)
            ctk.CTkLabel(row, text="mW").pack(side="left")
            ctk.CTkLabel(row, text="Tol:").pack(side="left", padx=(10, 2))
            self._entry(row, f"{prefix}.tol", 40).pack(side="left", padx=2)
            ctk.CTkLabel(row, text="%").pack(side="left")
        ctk.CTkLabel(self, text="R_s blank or 0 = no series resistor.",
                     text_color=MUTED, font=("", 11)).pack(anchor="w", padx=10)


# ── Zener Panel ───────────────────────────────────────────────────────────────

class ZenerPanel(_FieldPanel):
    def _build(self):
        LBL, ENT, UNT, LBL2 = 70, 60, 50, 40

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(header, text="Zener Diode", font=("", 14, "bold")).pack(side="left")
        self.preset = ctk.CTkComboBox(
            header, values=list(ZENER_PRESETS.keys()) + [CUSTOM_PRESET], width=150,
            state="readonly", command=self.app_state.select_zener_preset)
        self.preset.pack(side="right")
        ctk.CTkLabel(header, text="Preset:").pack(side="right", padx=5)
        self.modified_label = ctk.CTkLabel(self, text="", text_color="orange",
                                           font=("", 11))
        self.modified_label.pack(anchor="e", padx=10)

        params = ctk.CTkFrame(self, fg_color="transparent")
        params.pack(fill="x", padx=10, pady=5)

        def row():
            r = ctk.CTkFrame(params, fg_color="transparent")
            r.pack(fill="x", pady=2)
            return r

        r1 = row()
        ctk.CTkLabel(r1, text="VZ nom:", width=LBL).pack(side="left")
        self._entry(r1, "zener.vz_nom", ENT).pack(side="left", padx=2)
        ctk.CTkLabel(r1, text="V", width=LBL2).pack(side="left")
        ctk.CTkLabel(r1, text="min:", width=LBL2).pack(side="left")
        self._entry(r1, "zener.vz_min", ENT).pack(side="left", padx=2)
        ctk.CTkLabel(r1, text="V", width=LBL2).pack(side="left")
        ctk.CTkLabel(r1, text="max:", width=LBL2).pack(side="left")
        self._entry(r1, "zener.vz_max", ENT).pack(side="left", padx=2)
        ctk.CTkLabel(r1, text="V", width=LBL2).pack(side="left")

        r2 = row()
        ctk.CTkLabel(r2, text="@IZT:", width=LBL).pack(side="left")
        self._entry(r2, "zener.izt_ma", ENT).pack(side="left", padx=2)
        ctk.CTkLabel(r2, text="mA", width=LBL2).pack(side="left")
        ctk.CTkLabel(r2, text="ZZT:", width=LBL2).pack(side="left")
        self._entry(r2, "zener.zzt_typ", ENT).pack(side="left", padx=2)
        ctk.CTkLabel(r2, text="Ω typ", width=UNT).pack(side="left")
        self._entry(r2, "zener.zzt_max", ENT).pack(side="left", padx=2)
        ctk.CTkLabel(r2, text="Ω max", width=UNT).pack(side="left")

        r3 = row()
        ctk.CTkLabel(r3, text="@IZK:", width=LBL).pack(side="left")
        self._entry(r3, "zener.izk_ma", ENT).pack(side="left", padx=2)
        ctk.CTkLabel(r3, text="mA", width=LBL2).pack(side="left")
        ctk.CTkLabel(r3, text="ZZK:", width=LBL2).pack(side="left")
        self._entry(r3, "zener.zzk_typ", ENT).pack(side="left", padx=2)
        ctk.CTkLabel(r3, text="Ω typ", width=UNT).pack(side="left")
        self._entry(r3, "zener.zzk_max", ENT).pack(side="left", padx=2)
        ctk.CTkLabel(r3, text="Ω max", width=UNT).pack(side="left")

        r3n = row()
        ctk.CTkLabel(r3n, text="", width=LBL).pack(side="left")
        self.zzk_note = ctk.CTkLabel(r3n, text=ZZK_NOTE, text_color=MUTED, font=("", 11))
        self.zzk_note.pack(side="left")
        btn = ctk.CTkLabel(r3n, text="?", width=18, height=18,
                           fg_color=("gray75", "gray35"), corner_radius=9,
                           font=("", 11, "bold"), text_color=("gray30", "gray80"),
                           cursor="hand2")
        btn.pack(side="left", padx=(4, 0))
        self.zzk_tooltip = _Tooltip(btn, ZZK_TOOLTIP)

        r4 = row()
        ctk.CTkLabel(r4, text="Ptot:", width=LBL).pack(side="left")
        self._entry(r4, "zener.ptot_mw", ENT).pack(side="left", padx=2)
        ctk.CTkLabel(r4, text="mW", width=LBL2).pack(side="left")

    def refresh_preset(self):
        """Show the preset as AppState derives it (base, or Custom + 'modified')."""
        text, note = self.app_state.zener_preset_display()
        if self.preset.get() != text:
            self.preset.set(text)
        self.modified_label.configure(text=note)


# ── MCU Panel ─────────────────────────────────────────────────────────────────

class McuPanel(_FieldPanel):
    def _build(self):
        LBL, ENT, UNT = 110, 80, 35

        ctk.CTkLabel(self, text="MCU Pin Input Limits", font=("", 14, "bold")).pack(anchor="w", padx=10, pady=5)
        params = ctk.CTkFrame(self, fg_color="transparent")
        params.pack(fill="x", padx=10, pady=5)

        rows = [
            ("mcu.vdd", "VDD/VDDA:", "V", "Supply voltage. Also used as the ADC reference (VREF)."),
            ("mcu.v_recommended_max", "Safe Max:", "V", None),
            ("mcu.v_absolute_max", "Abs. Max:", "V", None),
            ("mcu.safe_injection_ma", "Injection Limit:", "mA", None),
            ("mcu.adc_bits", "ADC bits:", "bits",
             "ADC resolution N; resolution = VREF / 2^N.\n"
             "STM32G4: 12-bit ADCs (STM32G484 datasheet DS12983 Rev 5, "
             "Features: 5 x 12-bit ADCs)."),
            ("mcu.vil_factor", "VIL factor:", "×VDD",
             "Pin input-low threshold as a fraction of VDD (VIL = factor × VDD).\n"
             "STM32G4: 0.3 (STM32G484 datasheet DS12983 Rev 5, Table 54, "
             "all I/Os except FT_c)."),
            ("mcu.vih_factor", "VIH factor:", "×VDD",
             "Pin input-high threshold as a fraction of VDD (VIH = factor × VDD).\n"
             "STM32G4: 0.7 (STM32G484 datasheet DS12983 Rev 5, Table 54, "
             "all I/Os except FT_c)."),
        ]
        for key, label, unit, tip in rows:
            r = ctk.CTkFrame(params, fg_color="transparent")
            r.pack(fill="x", pady=2)
            ctk.CTkLabel(r, text=label, width=LBL).pack(side="left")
            self._entry(r, key, ENT).pack(side="left", padx=2)
            ctk.CTkLabel(r, text=unit, width=UNT).pack(side="left")
            if tip:
                _help_btn(r, tip)


# ── System Panel ──────────────────────────────────────────────────────────────

class SystemPanel(_FieldPanel):
    def _build(self):
        LBL, ENT, UNT = 110, 80, 45

        ctk.CTkLabel(self, text="System Requirements", font=("", 14, "bold")).pack(anchor="w", padx=10, pady=5)
        params = ctk.CTkFrame(self, fg_color="transparent")
        params.pack(fill="x", padx=10, pady=5)
        for key, label, unit in (
                ("system.v_input_max", "Max Input:", "V"),
                ("system.v_analog_fullscale", "ADC Scale:", "V"),
                ("system.v_logic_high_min", "Logic High:", "V min"),
                ("system.v_logic_low_max", "Logic Low:", "V max")):
            r = ctk.CTkFrame(params, fg_color="transparent")
            r.pack(fill="x", pady=2)
            ctk.CTkLabel(r, text=label, width=LBL).pack(side="left")
            self._entry(r, key, ENT).pack(side="left", padx=2)
            ctk.CTkLabel(r, text=unit, width=UNT).pack(side="left")


# ── Notes Panel ───────────────────────────────────────────────────────────────

class NotesPanel(ctk.CTkFrame):
    """Text widgets have no Tk variable, so edits are caught with <<Modified>>,
    which Tk raises for typing, paste, cut and delete alike."""

    def __init__(self, parent, state: AppState):
        super().__init__(parent)
        self.app_state = state
        ctk.CTkLabel(self, text="Design Notes", font=("", 14, "bold")).pack(anchor="w", padx=10, pady=5)
        self.textbox = ctk.CTkTextbox(self, height=80)
        self.textbox.pack(fill="x", padx=10, pady=5)
        self.textbox.bind("<<Modified>>", self._on_modified)
        self.sync_from_state()

    def _on_modified(self, event=None):
        if not self.textbox.edit_modified():
            return
        self.textbox.edit_modified(False)
        self.app_state.set_field("notes", self.textbox.get("1.0", "end-1c"))

    def sync_from_state(self):
        text = self.app_state.fields["notes"]
        if self.textbox.get("1.0", "end-1c") != text:
            self.textbox.delete("1.0", "end")
            self.textbox.insert("1.0", text)


# ── Bandwidth / PPS Input Panel ───────────────────────────────────────────────

class BandwidthInputPanel(_FieldPanel):
    """Input fields for the Signal Bandwidth / PPS analysis tab.

    The tau resistance, VIL, VIH and V_high are derived by AppState from the
    other panels and shown read-only here.
    """

    def __init__(self, parent, state: AppState):
        super().__init__(parent, state, fg_color="transparent")

    def _build(self):
        LBL_W, ENT_W, UNIT_W = 90, 80, 35

        ctk.CTkLabel(self, text="Derived from Other Panels", font=("", 13, "bold")).pack(anchor="w", padx=5, pady=(5, 2))
        auto = ctk.CTkFrame(self, fg_color="transparent")
        auto.pack(fill="x", padx=5)
        self.derived = {}
        for name, label, unit, tip in (
                ("r_tau_ohms", "τ resistance:", "Ω",
                 "R1∥R2 + R_s: the resistance that charges the pin capacitance."),
                ("vil_v", "VIL:", "V", "VIL factor × VDD (MCU panel)."),
                ("vih_v", "VIH:", "V", "VIH factor × VDD (MCU panel)."),
                ("v_high", "V_high:", "V",
                 "Lowest solved pin voltage at the Logic High input\n"
                 "(R1 max, R2 min, typical Zener): the level a high pulse settles to.")):
            r = ctk.CTkFrame(auto, fg_color="transparent")
            r.pack(fill="x", pady=1)
            ctk.CTkLabel(r, text=label, width=LBL_W, text_color=MUTED, anchor="w").pack(side="left")
            lbl = ctk.CTkLabel(r, text=NEEDS_INPUT, width=ENT_W, anchor="w", text_color=MUTED)
            lbl.pack(side="left", padx=2)
            ctk.CTkLabel(r, text=unit, width=UNIT_W, text_color=MUTED).pack(side="left")
            _help_btn(r, tip)
            self.derived[name] = lbl

        def section(title):
            ctk.CTkLabel(self, text=title, font=("", 13, "bold")).pack(anchor="w", padx=5, pady=(10, 2))
            f = ctk.CTkFrame(self, fg_color="transparent")
            f.pack(fill="x", padx=5)
            return f

        def entry_row(parent, key, label, unit, tip):
            r = ctk.CTkFrame(parent, fg_color="transparent")
            r.pack(fill="x", pady=2)
            ctk.CTkLabel(r, text=label, width=LBL_W).pack(side="left")
            self._entry(r, key, ENT_W).pack(side="left", padx=2)
            ctk.CTkLabel(r, text=unit, width=UNIT_W).pack(side="left")
            _help_btn(r, tip)

        cap = section("Capacitance")
        entry_row(cap, "bw.c_diode_pf", "C_diode:", "pF",
                  "Protection diode capacitance at 0 V reverse bias (worst case).\n"
                  "BZB984-C3V3: Cd max 450 pF (Nexperia BZB984 datasheet Rev 3, Table 8).")
        entry_row(cap, "bw.c_pin_pf", "C_pin:", "pF",
                  "MCU GPIO input capacitance.\n"
                  "STM32G4: CIO 5 pF typ (DS12983 Rev 5, Table 54).")
        entry_row(cap, "bw.c_stray_pf", "C_stray:", "pF",
                  "PCB parasitic/stray capacitance estimate.\nTypically 2-5 pF. Depends on trace length and layout.")

        dig = section("Digital Sampling")
        entry_row(dig, "bw.f_peripheral_mhz", "f_periph:", "MHz",
                  "Peripheral clock frequency that samples the input pin.\n"
                  "STM32G4: up to 170 MHz (DS12983 Rev 5, Table 17).")
        entry_row(dig, "bw.n_samples", "N_samples:", "",
                  "Minimum consecutive samples required for valid edge detection.\n"
                  "Find in the MCU reference manual under timer/input capture digital filter settings.")

        cnt = section("Counter Overflow")
        entry_row(cnt, "bw.counter_bits", "Bits:", "",
                  "Hardware counter width in bits (e.g. 16 or 32).\n"
                  "STM32G4: TIM3/TIM4 16-bit, TIM2/TIM5 32-bit (DS12983 Rev 5, Table 7).")
        r = ctk.CTkFrame(cnt, fg_color="transparent")
        r.pack(fill="x", pady=2)
        ctk.CTkLabel(r, text="Signed:", width=LBL_W).pack(side="left")
        self._checkbox(r, "bw.counter_signed", ENT_W).pack(side="left", padx=2)
        ctk.CTkLabel(r, text="", width=UNIT_W).pack(side="left")
        _help_btn(r, "Check if the counter counts +/- (signed).\n"
                     "Uses one bit for sign: 2^(N-1) counts instead of 2^N.")
        entry_row(cnt, "bw.f_read_hz", "f_read:", "Hz",
                  "How often firmware reads/resets the counter.\nTypically your PID loop rate or main polling frequency.")

        self.fill_button = ctk.CTkButton(
            self, text="Fill from starting values", height=28,
            command=self.app_state.fill_bandwidth_starting_values)
        self.fill_button.pack(anchor="w", padx=5, pady=(12, 2))
        ctk.CTkLabel(self, text="Fills only blank or unreadable fields above.",
                     text_color=MUTED, font=("", 11)).pack(anchor="w", padx=5)

    def refresh_derived(self):
        """Show the derived inputs AppState passed to the bandwidth model."""
        bp = self.app_state.bandwidth_params
        for name, lbl in self.derived.items():
            v = getattr(bp, name)
            if v is None:
                lbl.configure(text=NEEDS_INPUT, text_color=MUTED)
            else:
                text = f"{v:.0f}" if name == "r_tau_ohms" else f"{v:.3f}"
                lbl.configure(text=text, text_color=("gray10", "gray90"))
