"""
Output panel classes — tabview components and result tables.
All display-only; updated via refresh(app_state) after AppState solved the
design. Nothing is calculated here: every number and status comes from the
solver's results.

A value of None means the result can't be computed: the cell shows
"needs input" (the banner above the tabs names the inputs). A row whose
optional input is not given shows "--".
"""
from __future__ import annotations

import customtkinter as ctk
from typing import TYPE_CHECKING

from src.models.clamp_solver import FAIL, NEEDS_INPUT as STATUS_NEEDS_INPUT, PASS, TIGHT
from src.ui.input_panels import _Tooltip, NEEDS_INPUT, MUTED

if TYPE_CHECKING:
    from src.core.app_state import AppState

STATUS_COLORS = {PASS: "green", TIGHT: "orange", FAIL: "red"}
STATUS_MARKS = {PASS: "✓", TIGHT: "⚠", FAIL: "✗"}
NORMAL = ("gray10", "gray90")
BLOCKED = "n/a (see note)"
NO_RS = "no R_s"
NOT_GIVEN = "--"

# Check id -> name used in the overall verdict line
CHECK_LABELS = {
    "pin_max_safe": "Safe Max", "pin_max_abs": "Abs. Max", "pin_min": "Pin Min",
    "logic_high": "Logic High", "logic_low": "Logic Low",
    "power_r1": "R1 power", "power_r2": "R2 power", "power_diode": "Clamp diode power",
    "power_rs": "R_s power", "analog_range": "ADC range", "analog_error": "Analog error",
    "frequency": "Required frequency",
}


def _show(label, value, fmt: str = "{:.2f}", suffix: str = ""):
    """Display a number, or 'needs input' when it is None."""
    if value is None:
        label.configure(text=NEEDS_INPUT, text_color=MUTED)
    else:
        label.configure(text=fmt.format(value) + suffix, text_color=NORMAL)


def _show_text(label, text, color=NORMAL):
    label.configure(text=text, text_color=color)


def status_text(status, detail: str = "") -> tuple:
    """(text, colour) for a solver status. *detail* replaces the word, as in
    "✓ 63%" for a margin."""
    if status is None or status == STATUS_NEEDS_INPUT:
        return NEEDS_INPUT, MUTED
    return f"{STATUS_MARKS[status]} {detail or status}", STATUS_COLORS[status]


def _show_status(label, status, detail: str = ""):
    text, color = status_text(status, detail)
    label.configure(text=text, text_color=color)


def _not_given(cells):
    for label in cells.values():
        label.configure(text=NOT_GIVEN, text_color=MUTED)


# ── Table-row helpers ─────────────────────────────────────────────────────────

def _table_header(parent, texts, widths, tooltips=None):
    for i, (text, w) in enumerate(zip(texts, widths)):
        if tooltips and i < len(tooltips) and tooltips[i]:
            # Header cell with ? tooltip
            frame = ctk.CTkFrame(parent, fg_color=("gray80", "gray25"), corner_radius=0)
            frame.grid(row=0, column=i, padx=1, pady=1, sticky="ew")
            ctk.CTkLabel(frame, text=text, font=("", 12, "bold"), anchor="w",
                         fg_color="transparent").pack(side="left", padx=(4, 0))
            tip_btn = ctk.CTkLabel(frame, text="?", width=16, height=16,
                                   fg_color=("gray65", "gray45"), corner_radius=8,
                                   font=("", 10, "bold"), text_color=("gray20", "gray90"),
                                   cursor="hand2")
            tip_btn.pack(side="left", padx=(3, 2))
            _Tooltip(tip_btn, tooltips[i])
        else:
            lbl = ctk.CTkLabel(parent, text=text, width=w, font=("", 12, "bold"),
                               anchor="w", fg_color=("gray80", "gray25"))
            lbl.grid(row=0, column=i, padx=1, pady=1, sticky="ew")


def _table_row(parent, label, unit, row_num, col_widths):
    bg = ("gray90", "gray20") if row_num % 2 == 1 else ("gray95", "gray17")
    ctk.CTkLabel(parent, text=label, width=col_widths[0], anchor="w",
                 fg_color=bg, font=("", 13)).grid(row=row_num, column=0, padx=1, pady=1, sticky="ew")
    val = ctk.CTkLabel(parent, text=NEEDS_INPUT, width=col_widths[1], anchor="w",
                       font=("", 13, "bold"), fg_color=bg, text_color=MUTED)
    val.grid(row=row_num, column=1, padx=1, pady=1, sticky="ew")
    ctk.CTkLabel(parent, text=unit, width=col_widths[2], anchor="w",
                 fg_color=bg, font=("", 13)).grid(row=row_num, column=2, padx=1, pady=1, sticky="ew")
    return val


def _cells_row(parent, label, row_num, col_widths, keys, bold_keys):
    bg = ("gray90", "gray20") if row_num % 2 == 1 else ("gray95", "gray17")
    ctk.CTkLabel(parent, text=label, width=col_widths[0], anchor="w",
                 fg_color=bg, font=("", 13)).grid(row=row_num, column=0, padx=1, pady=1, sticky="ew")
    cells = {}
    for i, key in enumerate(keys, start=1):
        c = ctk.CTkLabel(parent, text=NEEDS_INPUT, width=col_widths[i], anchor="w",
                         font=("", 13, "bold") if key in bold_keys else ("", 13),
                         fg_color=bg, text_color=MUTED)
        c.grid(row=row_num, column=i, padx=1, pady=1, sticky="ew")
        cells[key] = c
    return cells


def _section(parent, title, first=False):
    ctk.CTkLabel(parent, text=title, font=("", 13, "bold")).pack(
        anchor="w", padx=10, pady=(10 if first else 15, 5))
    frame = ctk.CTkFrame(parent, fg_color="transparent")
    frame.pack(fill="x", padx=10)
    return frame


# ── Component Analysis Tab ────────────────────────────────────────────────────

class ComponentsTab:
    def __init__(self, parent: ctk.CTkFrame):
        self._build(parent)

    def _build(self, parent):
        dt = _section(parent, "Divider Network", first=True)
        cw = [250, 100, 60]
        _table_header(dt, ["Parameter", "Value", "Unit"], cw)
        self.r_total = _table_row(dt, "Input Impedance (R1+R2)", "kΩ", 1, cw)
        self.ratio = _table_row(dt, "Divider Ratio", "", 2, cw)
        self.r_source = _table_row(dt, "ADC Source Impedance (R1∥R2 + R_s)", "kΩ", 3, cw)
        self.p_total = _table_row(dt, "Power Dissipation (typical)", "mW", 4, cw)

        ct = _section(parent, "Component Power (at Max Input)")
        ccw = [90, 90, 85, 85, 85, 95, 95]
        tips = [
            None,
            "Typical current: nominal resistors, typical clamp diode column.\n"
            "Clamp diode: the current leaving the node through the diode.\n"
            "R_s: the typical node voltage across R_s, pin held at 0 V.",
            "Typical: nominal resistors, typical clamp diode column.",
            "Worst case: the highest power over the corners R1 min/max × "
            "R2 min/max × clamp diode minimum / maximum column, and the "
            "typical point.\n"
            "R_s: the highest node voltage across R_s at its low tolerance, "
            "pin held at 0 V (V² / R_s min).",
            None,
            "Rating margin against the typical power.\nFor information only; "
            "the verdict uses the worst-case margin.",
            "Rating margin against the worst-case power. This is the verdict:\n"
            "PASS > 20 %, TIGHT 0-20 %, FAIL ≤ 0 %.",
        ]
        _table_header(ct, ["Part", "Current", "Power typ", "Power worst", "Rating",
                           "Margin typ", "Margin worst"], ccw, tips)
        keys = ["current", "power", "power_worst", "rating", "margin", "margin_worst"]
        bold = {"margin_worst"}     # the verdict column
        self.r1_row = _cells_row(ct, "R1", 1, ccw, keys, bold)
        self.r2_row = _cells_row(ct, "R2", 2, ccw, keys, bold)
        self.diode_row = _cells_row(ct, "Clamp diode", 3, ccw, keys, bold)
        self.rs_row = _cells_row(ct, "R_s", 4, ccw, keys, bold)

        vf = ctk.CTkFrame(parent, fg_color="transparent"); vf.pack(anchor="w", padx=10, pady=(4, 0))
        ctk.CTkLabel(vf, text="Power verdict (worst case):", font=("", 13)).pack(side="left")
        self.power_verdict = ctk.CTkLabel(vf, text=NEEDS_INPUT, font=("", 13, "bold"),
                                          text_color=MUTED)
        self.power_verdict.pack(side="left", padx=(6, 0))

        vt = _section(parent, "Voltage at MCU Pin (nominal R1/R2)")
        vcw = [220, 100, 60]
        _table_header(vt, ["Condition", "V_mcu", "Unit"], vcw, [
            None,
            "Nominal R1 and R2 (no tolerance), at Max Input.\n"
            "Typical: the clamp diode's typical column.\n"
            "Worst clamp diode: its maximum column.\nThe full worst case (the "
            "highest of all corners) is V_mcuH on the MCU Input tab.",
            None])
        self.vclamp_typ = _table_row(vt, "Typical clamp diode", "V", 1, vcw)
        self.vclamp_worst = _table_row(vt, "Worst clamp diode (nominal R)", "V", 2, vcw)

    def refresh(self, s: AppState):
        d = s.details
        _show(self.r_total, None if d["r_total_ohms"] is None else d["r_total_ohms"] / 1000)
        _show(self.ratio, d["k_nominal"], "{:.4f}")
        _show(self.r_source, None if d["r_source_ohms"] is None else d["r_source_ohms"] / 1000)
        _show(self.p_total, d["p_total_mw"], "{:.1f}")

        rows = [(self.r1_row, "r1"), (self.r2_row, "r2"), (self.diode_row, "diode")]
        if d["has_rs"]:
            rows.append((self.rs_row, "rs"))
        else:
            for lbl in self.rs_row.values():
                lbl.configure(text=NO_RS, text_color=MUTED)
        for row, name in rows:
            _show(row["current"], d[f"i_{name}_ma"], "{:.2f}", " mA")
            _show(row["power"], d[f"p_{name}_mw"], "{:.1f}", " mW")
            _show(row["power_worst"], d[f"p_{name}_worst_mw"], "{:.1f}", " mW")
            _show(row["rating"], d[f"{name}_rating_mw"], "{:.0f}", " mW")
            # the typical margin is information: no tick
            _show(row["margin"], d[f"{name}_margin_pct"], "{:.0f}", "%")
            pct = d[f"{name}_margin_worst_pct"]
            _show_status(row["margin_worst"], s.check(f"power_{name}")["status"],
                         "" if pct is None else f"{pct:.0f}%")

        _show_status(self.power_verdict, d["power_verdict"])
        _show(self.vclamp_typ, d["v_pin_typ"], "{:.3f}")
        _show(self.vclamp_worst, d["v_pin_diode_max"], "{:.3f}")


# ── MCU Input / Safety Tab ────────────────────────────────────────────────────

class SafetyTab:
    def __init__(self, parent: ctk.CTkFrame):
        self._build(parent)

    def _build(self, parent):
        vt = _section(parent, "Voltage Limits", first=True)
        vw = [170, 90, 90, 90, 90]
        vt_tips = [
            None,
            "At Max Input: V_mcuH, the highest voltage at the MCU pin over all\n"
            "corners (R1 min/max, R2 min/max, clamp diode minimum/maximum\n"
            "column). Not the same as 'Worst clamp diode (nominal R)' on the\n"
            "Component Analysis tab.\n"
            "At Min Input: V_mcuL, the lowest pin voltage over the same corners.",
            "The MCU voltage threshold being compared against.\n"
            "Safe Max = highest pin voltage in normal operation. Its check is\n"
            "the guard against current into the pin's protection structures.\n"
            "Abs Max = damage threshold from datasheet.\n"
            "Pin Min = lowest allowed pin voltage.",
            "How much headroom remains to the limit.\nPositive = safe, negative = exceeded.",
            "PASS = safe margin (50 mV to Safe Max, 100 mV to Abs Max).\n"
            "TIGHT = within the limit but close.\nFAIL = limit exceeded.\n"
            "Pin Min: PASS or FAIL only.",
        ]
        _table_header(vt, ["Parameter", "V_mcu", "Limit", "Margin", "Status"], vw, vt_tips)
        keys = ["value", "limit", "margin", "status"]
        self.rec_row = _cells_row(vt, "Max Input vs Safe Max", 1, vw, keys, {"status"})
        self.abs_row = _cells_row(vt, "Max Input vs Absolute Max", 2, vw, keys, {"status"})
        self.min_row = _cells_row(vt, "Min Input vs Pin Min", 3, vw, keys, {"status"})

        at = _section(parent, "ADC Performance")
        aw = [170, 100, 80]
        _table_header(at, ["Parameter", "Value", "Unit"], aw)
        self.source_z = _table_row(at, "Source Impedance", "kΩ", 1, aw)
        self.resolution = _table_row(at, "Resolution", "mV/LSB", 2, aw)

        et = _section(parent, "Analog Error (at ADC Scale, nominal R1/R2)")
        ew = [170, 90, 90, 90, 90, 90]
        _table_header(et, ["Parameter", "Error", "Percent", "LSB", "Allowed", "Status"], ew, [
            None,
            "Pin voltage with the clamp diode minus the pin voltage without it,\n"
            "at the ADC Scale input with nominal R1 and R2. The larger error of\n"
            "the diode's minimum and maximum columns. Negative = the diode\n"
            "pulls the reading down.",
            "The error as a percentage of the pin voltage without the diode.",
            "The error in ADC steps (VDD / 2^N).",
            "Allowed analog error (System panel). Without it the error is\n"
            "shown for information only.",
            "PASS = the size of the error is within the allowed error.",
        ])
        self.error_row = _cells_row(et, "Clamp diode error", 1, ew,
                                    ["mv", "pct", "lsb", "allowed", "status"], {"status"})

        it = _section(parent, "Information (no verdict)")
        iw = [250, 100, 60]
        _table_header(it, ["Parameter", "Value", "Unit"], iw, [
            None,
            "Shown for information: these rows change no verdict.\n"
            "Touch rows: the highest of all corners at the Touch voltage.\n"
            "Rail current: the highest of all corners at Max Input, when the\n"
            "clamp diode is connected to VDD.",
            None])
        self.touch_pin = _table_row(it, "Touch: highest pin voltage", "V", 1, iw)
        self.touch_diode = _table_row(it, "Touch: clamp diode current", "mA", 2, iw)
        self.touch_r1 = _table_row(it, "Touch: R1 power", "mW", 3, iw)
        self.rail_current = _table_row(it, "Current into the VDD rail (Max Input)", "mA", 4, iw)

    def refresh(self, s: AppState):
        d = s.details
        for row, check_id, margin in ((self.rec_row, "pin_max_safe", d["margin_rec_v"]),
                                      (self.abs_row, "pin_max_abs", d["margin_abs_v"])):
            c = s.check(check_id)
            _show(row["value"], c["value"], "{:.3f}", " V")
            _show(row["limit"], c["limit"], "{:.2f}", " V")
            _show(row["margin"], None if margin is None else margin * 1000, "{:+.0f}", " mV")
            _show_status(row["status"], c["status"])

        c = s.check("pin_min")
        if c is None:           # no Min Input, or it is not negative
            _not_given(self.min_row)
        else:
            margin = None if c["value"] is None or c["limit"] is None \
                else (c["value"] - c["limit"]) * 1000
            _show(self.min_row["value"], c["value"], "{:.3f}", " V")
            _show(self.min_row["limit"], c["limit"], "{:.2f}", " V")
            _show(self.min_row["margin"], margin, "{:+.0f}", " mV")
            _show_status(self.min_row["status"], c["status"])

        _show(self.source_z, None if d["r_source_ohms"] is None else d["r_source_ohms"] / 1000)
        _show(self.resolution, d["resolution_mv_per_lsb"])

        c = s.check("analog_error")
        if c is None:           # no ADC Scale
            _not_given(self.error_row)
        else:
            _show(self.error_row["mv"], d["analog_error_mv"], "{:+.1f}", " mV")
            _show(self.error_row["pct"], d["analog_error_pct"], "{:+.2f}", " %")
            _show(self.error_row["lsb"], d["analog_error_lsb"], "{:+.1f}")
            if c["limit"] is None:
                _show_text(self.error_row["allowed"], NOT_GIVEN, MUTED)
                if c["value"] is None:
                    _show_status(self.error_row["status"], None)
                else:
                    _show_text(self.error_row["status"], "info", MUTED)
            else:
                _show(self.error_row["allowed"], c["limit"], "{:.2f}", " %")
                _show_status(self.error_row["status"], c["status"])

        for label, info_id, fmt in ((self.touch_pin, "touch_pin_high", "{:.3f}"),
                                    (self.touch_diode, "touch_diode_current", "{:.2f}"),
                                    (self.touch_r1, "touch_r1_power", "{:.1f}"),
                                    (self.rail_current, "rail_current", "{:.3f}")):
            row = s.info(info_id)
            if row is None:     # no Touch voltage / diode not connected to VDD
                _show_text(label, NOT_GIVEN, MUTED)
            else:
                _show(label, row["value"], fmt)


# ── Input Levels Tab ──────────────────────────────────────────────────────────

class OperatingTab:
    """Pin voltage at each input level, with the checks that level feeds.

    The value a row is judged on is in bold: V_mcuL where the pin must stay
    above a limit, V_mcuH where it must stay below one. A row with no check
    (0 V, Touch, a Min Input that is not negative) has nothing in bold."""

    # level id, row label, check ids, the cell the row is judged on
    ROWS = (("min_input", "Min Input", ("pin_min",), "v_mcu_l"),
            ("zero", "0V", (), None),
            ("logic_low", "Logic Low", ("logic_low",), "v_mcu_h"),
            ("logic_high", "Logic High", ("logic_high",), "v_mcu_l"),
            ("analog_fullscale", "ADC Scale", ("analog_range",), "v_mcu_h"),
            ("max_input", "Max Input", ("pin_max_safe", "pin_max_abs"), "v_mcu_h"),
            ("touch", "Touch", (), None))
    REQUIREMENTS = {"pin_min": "≥ {:.2f} V pin min", "logic_low": "< VIL {:.2f} V",
                    "logic_high": "> VIH {:.2f} V", "analog_range": "≤ VDD {:.2f} V",
                    "pin_max_safe": "≤ {:.2f} V safe", "pin_max_abs": "≤ {:.2f} V abs"}
    PLAIN, BOLD = ("", 13), ("", 13, "bold")
    CAPTION = ("V_mcuL / V_mcuH: the lowest / highest pin voltage over all corners "
               "(R1, R2 tolerance; clamp diode minimum and maximum columns). "
               "Bold: the value the row is judged on.")

    def __init__(self, parent: ctk.CTkFrame):
        self._build(parent)

    def _build(self, parent):
        self.table = ctk.CTkFrame(parent, fg_color="transparent")
        self.table.pack(fill="x", padx=10, pady=10)

        headers = ["Level", "V_input", "V_mcuL", "V_mcuH", "Requirement", "Status"]
        widths = [90, 85, 85, 85, 210, 100]

        for i, (text, w) in enumerate(zip(headers, widths)):
            ctk.CTkLabel(self.table, text=text, width=w, font=("", 12, "bold"),
                         anchor="w", fg_color=("gray80", "gray25")).grid(
                row=0, column=i, padx=1, pady=1, sticky="ew")

        self.rows = {}
        for i, (level, label, _checks, _judged) in enumerate(self.ROWS):
            rn = i + 1
            bg = ("gray90", "gray20") if i % 2 == 0 else ("gray95", "gray17")
            ctk.CTkLabel(self.table, text=label, width=widths[0], anchor="w",
                         font=self.PLAIN, fg_color=bg).grid(row=rn, column=0, padx=1, pady=1,
                                                            sticky="ew")
            cells = {}
            for j, (key, w) in enumerate(zip(["v_in", "v_mcu_l", "v_mcu_h", "thresh", "status"],
                                             widths[1:]), start=1):
                c = ctk.CTkLabel(self.table, text=NEEDS_INPUT, width=w, anchor="w",
                                 font=self.BOLD if key == "status" else self.PLAIN,
                                 fg_color=bg, text_color=MUTED)
                c.grid(row=rn, column=j, padx=1, pady=1, sticky="ew")
                cells[key] = c
            self.rows[level] = cells
        ctk.CTkLabel(parent, text=self.CAPTION, text_color=MUTED, font=("", 11),
                     wraplength=680, justify="left").pack(anchor="w", padx=10)

    def _requirement(self, checks) -> tuple:
        """(text, colour) of the Requirement cell: every limit the row is
        held to. A limit that is blank says so."""
        if all(c["limit"] is None for c in checks):
            return NEEDS_INPUT, MUTED
        parts = []
        for c in checks:
            if c["limit"] is None:
                parts.append(f"{CHECK_LABELS[c['id']]}: {NEEDS_INPUT}")
            else:
                parts.append(self.REQUIREMENTS[c["id"]].format(c["limit"]))
        return " / ".join(parts), NORMAL

    def refresh(self, s: AppState):
        for level, _label, check_ids, judged in self.ROWS:
            cells, row = self.rows[level], s.level(level)
            checks = [c for c in map(s.check, check_ids) if c is not None]
            for key in ("v_mcu_l", "v_mcu_h"):
                font = self.BOLD if row is not None and checks and key == judged else self.PLAIN
                if tuple(cells[key].cget("font")) != font:
                    cells[key].configure(font=font)
            if row is None:         # optional level, not given
                _not_given(cells)
                continue
            _show(cells["v_in"], row["v_in"], "{:.2f}", " V")
            _show(cells["v_mcu_l"], row["low"], "{:.3f}", " V")
            _show(cells["v_mcu_h"], row["high"], "{:.3f}", " V")
            if not checks:          # 0 V, Touch, or a Min Input that is not negative
                _show_text(cells["thresh"], NOT_GIVEN, MUTED)
                _show_text(cells["status"], "Zero ref" if level == "zero" else "info", MUTED)
            else:
                _show_text(cells["thresh"], *self._requirement(checks))
                # Max Input: the worse of Safe Max and Absolute Max
                _show_status(cells["status"], s.worst_status(*check_ids))


# ── Signal Bandwidth Results Tab ──────────────────────────────────────────────

def format_frequency(hz: float) -> str:
    """A frequency for the screen: "1.347 MHz", "898.0 kHz", "950 Hz"."""
    if hz >= 1e6:
        return f"{hz / 1e6:.3f} MHz"
    if hz >= 1e3:
        return f"{hz / 1e3:.1f} kHz"
    return f"{hz:.0f} Hz"


class BandwidthTab:
    """What input frequency can a pin with this divider and diode handle?
    Two numbers, "may work up to" and "reliable up to"; the required
    frequency with its status when one is given; and a Details control for
    the values behind them."""

    QUESTION = "Input frequency this pin can handle"
    CAPTION = ("For pulse inputs and encoders: the frequency at the pin (per channel "
               "for an encoder), at 50 % duty.")
    DETAILS_CLOSED, DETAILS_OPEN = "Details ▸", "Details ▾"

    def __init__(self, parent: ctk.CTkFrame):
        self._build(parent)

    def _build(self, parent):
        ctk.CTkLabel(parent, text=self.QUESTION, font=("", 13, "bold")).pack(
            anchor="w", padx=10, pady=(10, 0))
        ctk.CTkLabel(parent, text=self.CAPTION, text_color=MUTED, font=("", 11),
                     justify="left", wraplength=440).pack(anchor="w", padx=10, pady=(0, 6))

        grid = ctk.CTkFrame(parent, fg_color="transparent")
        grid.pack(fill="x", padx=10)

        def row(i, label, tip, big):
            name = ctk.CTkFrame(grid, fg_color="transparent")
            name.grid(row=i, column=0, sticky="w", pady=3)
            ctk.CTkLabel(name, text=label, font=("", 13), width=120, anchor="w").pack(side="left")
            tip_btn = ctk.CTkLabel(name, text="?", width=16, height=16,
                                   fg_color=("gray65", "gray45"), corner_radius=8,
                                   font=("", 10, "bold"), text_color=("gray20", "gray90"),
                                   cursor="hand2")
            tip_btn.pack(side="left", padx=(3, 8))
            _Tooltip(tip_btn, tip)
            value = ctk.CTkLabel(grid, text=NEEDS_INPUT, anchor="w", width=150,
                                 font=("", 20 if big else 13, "bold"), text_color=MUTED)
            value.grid(row=i, column=1, sticky="w", padx=(0, 10))
            return value

        self.f_may_work = row(
            0, "May work up to",
            "1 / (2 × (edge time + minimum pulse width)).\n"
            "The edge time is the longer of the rising edge (0 V to VIH) and the\n"
            "falling edge (from the Max Input level down to VIL), with the\n"
            "slowest resistors: R1, R2 and R_s at their high tolerance.", True)
        self.f_reliable = row(
            1, "Reliable up to",
            "\"May work up to\" divided by the margin factor (Board, on the left).", True)
        self.required_value = row(
            2, "Required",
            "The required frequency (System panel), if one is given.\n"
            "PASS: at or below \"reliable up to\".\n"
            "TIGHT: between \"reliable up to\" and \"may work up to\".\n"
            "FAIL: above \"may work up to\".", False)
        self.required_status = ctk.CTkLabel(grid, text=NOT_GIVEN, anchor="w",
                                            font=("", 13, "bold"), text_color=MUTED)
        self.required_status.grid(row=2, column=2, sticky="w")

        self.note = ctk.CTkLabel(parent, text="", text_color="red", justify="left",
                                 anchor="w", wraplength=440)
        self.note.pack(anchor="w", padx=10, pady=(6, 2))

        self.details_button = ctk.CTkButton(parent, text=self.DETAILS_CLOSED, width=90,
                                            height=24, fg_color="gray40",
                                            hover_color="gray30", command=self.toggle_details)
        self.details_button.pack(anchor="w", padx=10, pady=(4, 2))
        self.details_frame = ctk.CTkFrame(parent, fg_color="transparent")
        cw = [200, 120, 60]
        _table_header(self.details_frame, ["Parameter", "Value", "Unit"], cw)
        self.tau = _table_row(self.details_frame, "Time constant (τ)", "ns", 1, cw)
        self.c_total = _table_row(self.details_frame, "Total capacitance", "pF", 2, cw)
        self.t_rise = _table_row(self.details_frame, "Rising edge to VIH", "ns", 3, cw)
        self.t_fall = _table_row(self.details_frame, "Falling edge to VIL", "ns", 4, cw)
        self.t_shortest = _table_row(self.details_frame, "Shortest usable pulse", "ns", 5, cw)

    @property
    def details_shown(self) -> bool:
        return self.details_frame.winfo_manager() != ""

    def toggle_details(self):
        if self.details_shown:
            self.details_frame.pack_forget()
            self.details_button.configure(text=self.DETAILS_CLOSED)
        else:
            self.details_frame.pack(fill="x", padx=10, pady=(2, 8))
            self.details_button.configure(text=self.DETAILS_OPEN)

    def refresh(self, s: AppState):
        d = s.details
        note = d["frequency_note"]

        def cell(label, value, fmt="{:.2f}"):
            if value is None and note:      # no limit: the pin never reads high (or low)
                label.configure(text=BLOCKED, text_color="red")
            elif value is None:
                label.configure(text=NEEDS_INPUT, text_color=MUTED)
            else:
                label.configure(text=fmt(value) if callable(fmt) else fmt.format(value),
                                text_color=NORMAL)

        cell(self.f_may_work, d["f_may_work_hz"], format_frequency)
        cell(self.f_reliable, d["f_reliable_hz"], format_frequency)
        check = s.check("frequency")
        if check is None:                   # no required frequency given
            _show_text(self.required_value, NOT_GIVEN, MUTED)
            _show_text(self.required_status, "", MUTED)
        else:
            _show_text(self.required_value, format_frequency(check["value"]))
            _show_status(self.required_status, check["status"])
        self.note.configure(text=note or "")

        _show(self.tau, d["tau_ns"], "{:.2f}")
        _show(self.c_total, d["c_total_pf"], "{:.1f}")
        cell(self.t_rise, d["t_rise_ns"])
        cell(self.t_fall, d["t_fall_ns"])
        cell(self.t_shortest, d["t_pulse_shortest_ns"])
