"""
Input panel classes for the MCU Input Protection Calculator.

Each panel owns its CTk widgets. Every input is bound to a Tk variable whose
write trace forwards the raw text to AppState.set_field (or set_cell for the
clamp-diode tables), so typing, paste, cut, delete, selection and
programmatic changes are all seen. Panels never parse or calculate; AppState
does. sync_from_state() copies AppState's text back into the widgets after
AppState changed it (load, new, fill, table row added or deleted).
"""
from __future__ import annotations

import customtkinter as ctk
from typing import TYPE_CHECKING

from src.core.constants import RESISTOR_UNITS
from src.core.div_format import DIODE_TYPES
from src.models.clamp_solver import ROW_KEYS, TERMINALS

if TYPE_CHECKING:
    from src.core.app_state import AppState


UNIT_CHOICES = list(RESISTOR_UNITS.keys())
NEEDS_INPUT = "needs input"
MUTED = "gray60"

# Shown under a clamp-diode table that has no rows.
NOT_MODELLED = {
    "forward": "no forward data: forward conduction not included",
    "reverse": "no reverse data: leakage not included",
}
OTHER_PANELS_NOTE = (
    "The other inputs of this tab are on the left: the diode capacitance in "
    "the Clamp Diode panel, C_pin and the minimum pulse width in the MCU "
    "panel, the logic levels and the required frequency in the System panel.")
TABLE_TITLES = {
    "forward": "Forward (anode positive)",
    "reverse": "Reverse (cathode positive)",
}
TABLE_TIPS = {
    "forward": "The diode with its anode more positive than its cathode.\n"
               "Each row: a current and the voltage across the diode at that\n"
               "current (minimum, typical, maximum). Rows in ascending current.\n"
               "No rows = this direction is not modelled.",
    "reverse": "The diode with its cathode more positive than its anode: the\n"
               "working direction of a Zener, the leakage direction of a\n"
               "Schottky. Voltages and currents are entered as positive numbers.\n"
               "No rows = this direction is not modelled.",
}


# ── Tooltip Helper ────────────────────────────────────────────────────────────

class _Tooltip:
    """Popup tooltip that appears near a widget on hover or click.
    Auto-dismisses after 4 seconds or when the mouse leaves."""

    all_texts: list = []     # every tooltip text created (read by the UI tests)

    def __init__(self, widget: ctk.CTkBaseClass, text: str):
        self.widget = widget
        self.text = text
        _Tooltip.all_texts.append(text)
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
        self.textboxes: dict = {}  # field key -> CTkTextbox (no Tk variable)
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

    def _combo(self, parent, key, values, width=70):
        var = ctk.StringVar(master=self, value="")
        c = ctk.CTkComboBox(parent, values=list(values), width=width,
                            variable=var, state="readonly")
        self._add_field(key, var, c)
        return c

    def _unit_combo(self, parent, key, width=70):
        return self._combo(parent, key, UNIT_CHOICES, width)

    def _checkbox(self, parent, key, text="", width=24):
        var = ctk.StringVar(master=self, value="0")
        c = ctk.CTkCheckBox(parent, text=text, width=width, variable=var,
                            onvalue="1", offvalue="0")
        self._add_field(key, var, c)
        return c

    def _textbox(self, parent, key, height=60):
        """Free text over several lines. Text widgets have no Tk variable, so
        edits are caught with <<Modified>>, which Tk raises for typing, paste,
        cut and delete alike."""
        box = ctk.CTkTextbox(parent, height=height, wrap="word")

        def on_modified(event=None):
            if not box.edit_modified():
                return
            box.edit_modified(False)
            self.app_state.set_field(key, box.get("1.0", "end-1c"))
        box.bind("<<Modified>>", on_modified)
        self.textboxes[key] = box
        self.widgets[key] = box
        return box

    def _labelled(self, parent, label, key, unit="", tip=None, lbl_w=110, ent_w=80, unit_w=45):
        r = ctk.CTkFrame(parent, fg_color="transparent")
        r.pack(fill="x", pady=2)
        ctk.CTkLabel(r, text=label, width=lbl_w, anchor="w").pack(side="left")
        self._entry(r, key, ent_w).pack(side="left", padx=2)
        ctk.CTkLabel(r, text=unit, width=unit_w, anchor="w").pack(side="left")
        if tip:
            _help_btn(r, tip)
        return r

    def _part_rows(self, parent, prefix, lbl_w):
        """Source, note and the "checked" box that a diode or MCU carries."""
        r = ctk.CTkFrame(parent, fg_color="transparent")
        r.pack(fill="x", pady=2)
        ctk.CTkLabel(r, text="Source:", width=lbl_w, anchor="w").pack(side="left")
        self._entry(r, f"{prefix}.source", 290).pack(side="left", padx=2)
        _help_btn(r, "One line: data sheet, revision, tables or figures used.")
        r = ctk.CTkFrame(parent, fg_color="transparent")
        r.pack(fill="x", pady=2)
        ctk.CTkLabel(r, text="Note:", width=lbl_w, anchor="nw").pack(side="left", anchor="n")
        self._textbox(r, f"{prefix}.note").pack(side="left", fill="x", expand=True, padx=2)
        r = ctk.CTkFrame(parent, fg_color="transparent")
        r.pack(fill="x", pady=2)
        ctk.CTkLabel(r, text="", width=lbl_w).pack(side="left")
        self._checkbox(r, f"{prefix}.checked",
                       text="Checked against the data sheet").pack(side="left", padx=2)

    def sync_from_state(self):
        """Copy AppState's field text into the widgets (no-op where equal)."""
        for key, var in self.vars.items():
            text = self.app_state.fields[key]
            if var.get() != text:
                var.set(text)
        for key, box in self.textboxes.items():
            text = self.app_state.fields[key]
            if box.get("1.0", "end-1c") != text:
                box.delete("1.0", "end")
                box.insert("1.0", text)


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


# ── Clamp Diode Panel ─────────────────────────────────────────────────────────

class _DiodeTable(ctk.CTkFrame):
    """One editable clamp-diode table: a row is a current and the voltage
    across the diode at that current (minimum, typical, maximum)."""

    HEADERS = ("I (mA)", "V min", "V typ", "V max")
    CELL_W = 84

    def __init__(self, parent, state: AppState, table: str):
        super().__init__(parent, fg_color="transparent")
        self.app_state = state
        self.table = table
        self.cells: list = []     # per row: {row key: CTkEntry}
        self._vars: list = []     # per row: {row key: StringVar}
        self.delete_buttons: list = []

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x")
        ctk.CTkLabel(head, text=TABLE_TITLES[table], font=("", 12, "bold")).pack(side="left")
        _help_btn(head, TABLE_TIPS[table])
        self.add_button = ctk.CTkButton(head, text="+ Add row", width=80, height=24,
                                        command=lambda: state.add_row(table))
        self.add_button.pack(side="right")

        self.grid_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.grid_frame.pack(fill="x", pady=(2, 0))
        for col, text in enumerate(self.HEADERS):
            ctk.CTkLabel(self.grid_frame, text=text, width=self.CELL_W, anchor="w",
                         text_color=MUTED, font=("", 11)).grid(row=0, column=col, padx=1)
        self.note = ctk.CTkLabel(self, text="", text_color="orange", font=("", 11),
                                 anchor="w")
        self.note.pack(fill="x")
        self.sync_from_state()

    def _rebuild(self):
        for row in self.cells:
            for entry in row.values():
                entry.destroy()
        for button in self.delete_buttons:
            button.destroy()
        self.cells, self._vars, self.delete_buttons = [], [], []
        for i, texts in enumerate(self.app_state.tables[self.table]):
            entries, variables = {}, {}
            for col, key in enumerate(ROW_KEYS):
                var = ctk.StringVar(master=self, value=texts[key])
                var.trace_add("write", lambda *_, i=i, key=key, var=var:
                              self.app_state.set_cell(self.table, i, key, var.get()))
                entry = ctk.CTkEntry(self.grid_frame, width=self.CELL_W, textvariable=var)
                entry.grid(row=i + 1, column=col, padx=1, pady=1)
                entries[key], variables[key] = entry, var
            button = ctk.CTkButton(self.grid_frame, text="×", width=24, height=24,
                                   fg_color="gray40", hover_color="gray30",
                                   command=lambda i=i: self.app_state.delete_row(self.table, i))
            button.grid(row=i + 1, column=len(ROW_KEYS), padx=(4, 0))
            self.cells.append(entries)
            self._vars.append(variables)
            self.delete_buttons.append(button)

    def sync_from_state(self):
        rows = self.app_state.tables[self.table]
        if len(rows) != len(self.cells):
            self._rebuild()
        else:
            for variables, texts in zip(self._vars, rows):
                for key, var in variables.items():
                    if var.get() != texts[key]:
                        var.set(texts[key])
        self.note.configure(text="" if rows else NOT_MODELLED[self.table])


class ClampDiodePanel(_FieldPanel):
    """One clamp diode of either kind: part name, type, connection, the
    forward and reverse tables, capacitance, power rating, source, note and
    the "checked" box. No presets: values are typed or come from the file."""

    def _build(self):
        LBL = 90
        ctk.CTkLabel(self, text="Clamp Diode", font=("", 14, "bold")).pack(anchor="w", padx=10, pady=5)
        params = ctk.CTkFrame(self, fg_color="transparent")
        params.pack(fill="x", padx=10, pady=5)

        r = ctk.CTkFrame(params, fg_color="transparent")
        r.pack(fill="x", pady=2)
        ctk.CTkLabel(r, text="Part:", width=LBL, anchor="w").pack(side="left")
        self._entry(r, "diode.part", 150).pack(side="left", padx=2)
        ctk.CTkLabel(r, text="Type:").pack(side="left", padx=(10, 2))
        self._combo(r, "diode.type", DIODE_TYPES, 100).pack(side="left", padx=2)
        _help_btn(r, "Zener or Schottky. A label only: the calculation uses the\n"
                     "connection and the two tables, whatever the type.")

        r = ctk.CTkFrame(params, fg_color="transparent")
        r.pack(fill="x", pady=2)
        ctk.CTkLabel(r, text="Connection:", width=LBL, anchor="w").pack(side="left")
        ctk.CTkLabel(r, text="anode").pack(side="left", padx=(2, 2))
        self._combo(r, "diode.anode", TERMINALS, 80).pack(side="left", padx=2)
        ctk.CTkLabel(r, text="cathode").pack(side="left", padx=(10, 2))
        self._combo(r, "diode.cathode", TERMINALS, 80).pack(side="left", padx=2)
        _help_btn(r, "Where each terminal of the diode is connected. \"node\" is the\n"
                     "junction of R1 and R2; exactly one terminal is at the node.\n"
                     "Zener to GND: anode gnd, cathode node.\n"
                     "Schottky to the rail: anode node, cathode vdd.\n"
                     "Schottky to GND: anode gnd, cathode node.")

        r = ctk.CTkFrame(params, fg_color="transparent")
        r.pack(fill="x", pady=2)
        ctk.CTkLabel(r, text="Capacitance:", width=LBL, anchor="w").pack(side="left")
        self._entry(r, "diode.capacitance_pf", 60).pack(side="left", padx=2)
        ctk.CTkLabel(r, text="pF").pack(side="left")
        _help_btn(r, "Diode capacitance at 0 V bias, or the data-sheet maximum.\n"
                     "Used for the Signal Bandwidth time constant.")
        ctk.CTkLabel(r, text="Ptot:").pack(side="left", padx=(14, 2))
        self._entry(r, "diode.ptot_mw", 60).pack(side="left", padx=2)
        ctk.CTkLabel(r, text="mW").pack(side="left")

        self.tables = {}
        for table in ("forward", "reverse"):
            self.tables[table] = _DiodeTable(params, self.app_state, table)
            self.tables[table].pack(fill="x", pady=(8, 0))

        tail = ctk.CTkFrame(params, fg_color="transparent")
        tail.pack(fill="x", pady=(8, 0))
        self._part_rows(tail, "diode", LBL)

    def sync_from_state(self):
        super().sync_from_state()
        for table in getattr(self, "tables", {}).values():
            table.sync_from_state()


# ── MCU Panel ─────────────────────────────────────────────────────────────────

class McuPanel(_FieldPanel):
    def _build(self):
        LBL = 110

        ctk.CTkLabel(self, text="MCU Pin Input Limits", font=("", 14, "bold")).pack(anchor="w", padx=10, pady=5)
        params = ctk.CTkFrame(self, fg_color="transparent")
        params.pack(fill="x", padx=10, pady=5)

        r = ctk.CTkFrame(params, fg_color="transparent")
        r.pack(fill="x", pady=2)
        ctk.CTkLabel(r, text="Part:", width=LBL, anchor="w").pack(side="left")
        self._entry(r, "mcu.part", 150).pack(side="left", padx=2)
        ctk.CTkLabel(r, text="Pin type:").pack(side="left", padx=(10, 2))
        self._entry(r, "mcu.pin_type", 60).pack(side="left", padx=2)
        _help_btn(r, "A label for the kind of pin, such as TT or FT. The limits\n"
                     "below are the ones the data sheet gives for that pin type.")

        rows = [
            ("mcu.vdd", "VDD/VDDA:", "V",
             "Supply voltage. Also used as the ADC reference (VREF), and as the\n"
             "voltage of the rail when the clamp diode is connected to vdd."),
            ("mcu.v_recommended_max", "Safe Max:", "V",
             "Highest pin voltage in normal operation. The check against it is\n"
             "the guard against current into the pin's protection diodes.\n"
             "STM32G4 TT pins: VDD + 0.3 V (DS12983 Rev 5, Table 17)."),
            ("mcu.v_absolute_max", "Abs. Max:", "V", None),
            ("mcu.v_pin_min", "Pin Min:", "V",
             "Lowest allowed pin voltage (0 or negative). Checked only when a\n"
             "negative Min Input is given.\n"
             "STM32G4: VSS - 0.3 V (DS12983 Rev 5, Table 14)."),
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
            ("mcu.c_pin_pf", "C_pin:", "pF",
             "MCU pin input capacitance. Used for the Signal Bandwidth time\n"
             "constant. STM32G4: CIO 5 pF typ (DS12983 Rev 5, Table 54)."),
            ("mcu.t_pulse_min_ns", "Min pulse width:", "ns",
             "Shortest pulse the input peripheral accepts. Used for the Signal\n"
             "Bandwidth limits. STM32G4 timer inputs: 2 to 3 timer clock\n"
             "periods (DS12983 Rev 5, Table 84)."),
        ]
        for key, label, unit, tip in rows:
            self._labelled(params, label, key, unit, tip, lbl_w=LBL)
        self._part_rows(params, "mcu", LBL)


# ── System Panel ──────────────────────────────────────────────────────────────

class SystemPanel(_FieldPanel):
    def _build(self):
        LBL = 130

        ctk.CTkLabel(self, text="System Requirements", font=("", 14, "bold")).pack(anchor="w", padx=10, pady=5)
        params = ctk.CTkFrame(self, fg_color="transparent")
        params.pack(fill="x", padx=10, pady=5)
        for key, label, unit, tip in (
                ("system.v_input_max", "Max Input:", "V", None),
                ("system.v_input_min", "Min Input:", "V",
                 "Optional: the lowest input voltage. When it is negative, the\n"
                 "lowest pin voltage is checked against Pin Min."),
                ("system.v_analog_fullscale", "ADC Scale:", "V",
                 "Optional: the input voltage at ADC full scale. Gives the\n"
                 "analog range check and the analog error."),
                ("system.analog_error_allowed_pct", "Allowed error:", "%",
                 "Optional: allowed analog error at ADC Scale, in percent.\n"
                 "Without it the analog error is shown for information only."),
                ("system.v_logic_high_min", "Logic High:", "V min", None),
                ("system.v_logic_low_max", "Logic Low:", "V max", None),
                ("system.v_touch", "Touch voltage:", "V",
                 "Optional: a voltage the input may touch, for example 60 V.\n"
                 "Gives information rows only: it changes no verdict."),
                ("system.f_required_hz", "Required freq.:", "Hz",
                 "Optional: the input frequency the pin must handle (at the pin,\n"
                 "50 % duty). Compared with the Signal Bandwidth limits.")):
            self._labelled(params, label, key, unit, tip, lbl_w=LBL)
        ctk.CTkLabel(self, text="Optional values left blank leave their check out.",
                     text_color=MUTED, font=("", 11)).pack(anchor="w", padx=10)


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


# ── Signal Bandwidth Input Panel ──────────────────────────────────────────────

class BandwidthInputPanel(_FieldPanel):
    """Input fields of the Signal Bandwidth tab: the two board values. The
    diode capacitance comes from the Clamp Diode panel, the pin capacitance
    and the minimum pulse width from the MCU panel, and the required
    frequency from the System panel."""

    def __init__(self, parent, state: AppState):
        super().__init__(parent, state, fg_color="transparent")

    def _build(self):
        LBL_W, ENT_W, UNIT_W = 110, 80, 35

        ctk.CTkLabel(self, text="Board", font=("", 13, "bold")).pack(anchor="w", padx=5, pady=(5, 2))
        board = ctk.CTkFrame(self, fg_color="transparent")
        board.pack(fill="x", padx=5)
        self._labelled(board, "C_stray:", "bw.c_stray_pf", "pF",
                       "PCB parasitic/stray capacitance estimate.\n"
                       "Typically 2-5 pF. Depends on trace length and layout.",
                       lbl_w=LBL_W, ent_w=ENT_W, unit_w=UNIT_W)
        self._labelled(board, "Margin factor:", "bw.margin_factor", "",
                       "\"Reliable up to\" = \"may work up to\" ÷ this factor (1 or more).\n"
                       "Starting value 1.5: owner's example, 2026-11-09: 1 MHz\n"
                       "reliable, 1.5 MHz may work.",
                       lbl_w=LBL_W, ent_w=ENT_W, unit_w=UNIT_W)

        self.fill_button = ctk.CTkButton(
            self, text="Fill from starting values", height=28,
            command=self.app_state.fill_bandwidth_starting_values)
        self.fill_button.pack(anchor="w", padx=5, pady=(12, 2))
        ctk.CTkLabel(self, text="Fills only blank or unreadable fields above.",
                     text_color=MUTED, font=("", 11)).pack(anchor="w", padx=5)
        ctk.CTkLabel(self, text=OTHER_PANELS_NOTE, text_color=MUTED, font=("", 11),
                     justify="left", wraplength=340).pack(anchor="w", padx=5, pady=(12, 2))
