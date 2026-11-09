"""
Output panel classes — tabview components and result tables.
All display-only; updated via refresh(...) from AppState callbacks.
A value of None means the result can't be computed: the cell shows
"needs input" (the banner above the tabs names the inputs).
"""
from __future__ import annotations

import customtkinter as ctk
from typing import Optional

from src.models.circuit_model import CalculationResult, McuParams, PASS, WARN, FAIL, INFO
from src.models.bandwidth_model import BandwidthResult
from src.ui.input_panels import _Tooltip, NEEDS_INPUT, MUTED

LEVEL_COLORS = {PASS: "green", WARN: "orange", FAIL: "red", INFO: MUTED}
NORMAL = ("gray10", "gray90")
BLOCKED = "n/a (see note)"


def _show(label, value, fmt: str = "{:.2f}", suffix: str = ""):
    """Display a number, or 'needs input' when it is None."""
    if value is None:
        label.configure(text=NEEDS_INPUT, text_color=MUTED)
    else:
        label.configure(text=fmt.format(value) + suffix, text_color=NORMAL)


def _show_status(label, status: Optional[tuple]):
    if status is None:
        label.configure(text=NEEDS_INPUT, text_color=MUTED)
    else:
        text, level = status
        label.configure(text=text, text_color=LEVEL_COLORS.get(level, NORMAL))


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


# ── Component Analysis Tab ────────────────────────────────────────────────────

class ComponentsTab:
    def __init__(self, parent: ctk.CTkFrame):
        self._build(parent)

    def _build(self, parent):
        ctk.CTkLabel(parent, text="Divider Network", font=("", 13, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        dt = ctk.CTkFrame(parent, fg_color="transparent"); dt.pack(fill="x", padx=10)
        cw = [250, 100, 60]
        _table_header(dt, ["Parameter", "Value", "Unit"], cw)
        self.r_total = _table_row(dt, "Input Impedance (R1+R2)", "kΩ", 1, cw)
        self.ratio = _table_row(dt, "Divider Ratio", "", 2, cw)
        self.r_source = _table_row(dt, "ADC Source Impedance (R1∥R2 + R_s)", "kΩ", 3, cw)
        self.p_total = _table_row(dt, "Power Dissipation", "mW", 4, cw)

        ctk.CTkLabel(parent, text="Component Power (at Max Input)", font=("", 13, "bold")).pack(anchor="w", padx=10, pady=(15, 5))
        ct = ctk.CTkFrame(parent, fg_color="transparent"); ct.pack(fill="x", padx=10)
        ccw = [80, 90, 90, 100, 150]
        _table_header(ct, ["Component", "Current", "Power", "Power Rating", "Margin %"], ccw)
        keys = ["current", "power", "rating", "margin"]
        self.r1_row = _cells_row(ct, "R1", 1, ccw, keys, {"margin"})
        self.r2_row = _cells_row(ct, "R2", 2, ccw, keys, {"margin"})
        self.z_row = _cells_row(ct, "Zener", 3, ccw, keys, {"margin"})

        ctk.CTkLabel(parent, text="Voltage at MCU Pin", font=("", 13, "bold")).pack(anchor="w", padx=10, pady=(15, 5))
        vt = ctk.CTkFrame(parent, fg_color="transparent"); vt.pack(fill="x", padx=10)
        vcw = [150, 100, 60]
        _table_header(vt, ["Condition", "V_mcu", "Unit"], vcw)
        self.vclamp_typ = _table_row(vt, "Typical", "V", 1, vcw)
        self.vclamp_worst = _table_row(vt, "Worst Case", "V", 2, vcw)

    def refresh(self, r: CalculationResult):
        _show(self.r_total, None if r.r_total_ohms is None else r.r_total_ohms / 1000)
        _show(self.ratio, r.k_nominal, "{:.4f}")
        _show(self.r_source, None if r.r_source_ohms is None else r.r_source_ohms / 1000)
        _show(self.p_total, r.p_total_mw, "{:.1f}")

        for row, i, p, rating, status in (
                (self.r1_row, r.i_r1_ma, r.p_r1_mw, r.r1_rating_mw, r.r1_margin_status),
                (self.r2_row, r.i_r2_ma, r.p_r2_mw, r.r2_rating_mw, r.r2_margin_status),
                (self.z_row, r.i_z_ma, r.p_z_mw, r.z_ptot_mw, r.z_margin_status)):
            _show(row["current"], i, "{:.2f}", " mA")
            _show(row["power"], p, "{:.1f}", " mW")
            _show(row["rating"], rating, "{:.0f}", " mW")
            _show_status(row["margin"], status)

        _show(self.vclamp_typ, r.v_mcu_typ, "{:.3f}")
        _show(self.vclamp_worst, r.v_mcu_worst_zener, "{:.3f}")


# ── MCU Input / Safety Tab ────────────────────────────────────────────────────

class SafetyTab:
    def __init__(self, parent: ctk.CTkFrame):
        self._build(parent)

    def _build(self, parent):
        ctk.CTkLabel(parent, text="Voltage Limits (at Max Input)", font=("", 13, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        vt = ctk.CTkFrame(parent, fg_color="transparent"); vt.pack(fill="x", padx=10)
        vw = [150, 90, 90, 90, 90]
        vt_tips = [
            None,
            "Worst-case voltage at the MCU pin.\nCalculated with tolerance-shifted resistors\nand worst-case Zener at maximum input voltage.",
            "The MCU voltage threshold being compared against.\nSafe Max = recommended operating limit.\nAbs Max = damage threshold from datasheet.",
            "How much headroom remains: Limit minus V_mcu.\nPositive = safe, negative = exceeded.",
            "PASS = safe margin.\nTIGHT = within spec but close.\nFAIL = limit exceeded.",
        ]
        _table_header(vt, ["Parameter", "V_mcu", "Limit", "Margin", "Status"], vw, vt_tips)
        keys = ["value", "limit", "margin", "status"]
        self.rec_row = _cells_row(vt, "vs Safe Max", 1, vw, keys, {"status"})
        self.abs_row = _cells_row(vt, "vs Absolute Max", 2, vw, keys, {"status"})

        ctk.CTkLabel(parent, text="Injection Current", font=("", 13, "bold")).pack(anchor="w", padx=10, pady=(15, 5))
        it = ctk.CTkFrame(parent, fg_color="transparent"); it.pack(fill="x", padx=10)
        iw = [150, 90, 90, 100]
        it_tips = [
            None,
            "Estimated current flowing into the MCU's\ninternal ESD clamp diode when V_mcu exceeds VDD.\nI_inj = (V_mcu - VDD) / (R_series + ~100Ω internal).",
            "Maximum safe injection current from the\nMCU datasheet (absolute max rating).",
            "OK = well within limit.\nMARGINAL = approaching limit.\nHIGH = exceeds safe injection current.",
        ]
        _table_header(it, ["Parameter", "Value", "Limit", "Status"], iw, it_tips)
        self.inj_row = _cells_row(it, "Estimated", 1, iw, ["value", "limit", "status"], {"status"})

        ctk.CTkLabel(parent, text="ADC Performance", font=("", 13, "bold")).pack(anchor="w", padx=10, pady=(15, 5))
        at = ctk.CTkFrame(parent, fg_color="transparent"); at.pack(fill="x", padx=10)
        aw = [150, 100, 80]
        _table_header(at, ["Parameter", "Value", "Unit"], aw)
        self.source_z = _table_row(at, "Source Impedance", "kΩ", 1, aw)
        self.sample_cyc = _table_row(at, "Min Sample Cycles", "cycles", 2, aw)
        self.resolution = _table_row(at, "Resolution", "mV/LSB", 3, aw)

    def refresh(self, r: CalculationResult, mcu: McuParams):
        for row, limit, margin, status in (
                (self.rec_row, mcu.v_recommended_max, r.margin_rec_v, r.rec_status),
                (self.abs_row, mcu.v_absolute_max, r.margin_abs_v, r.abs_status)):
            _show(row["value"], r.v_mcu_worst, "{:.3f}", " V")
            _show(row["limit"], limit, "{:.2f}", " V")
            _show(row["margin"], None if margin is None else margin * 1000, "{:+.0f}", " mV")
            _show_status(row["status"], status)

        _show(self.inj_row["value"], r.i_injection_ma, "{:.2f}", " mA")
        _show(self.inj_row["limit"], mcu.safe_injection_ma, "{:.1f}", " mA")
        _show_status(self.inj_row["status"], r.inj_status)

        _show(self.source_z, None if r.r_source_ohms is None else r.r_source_ohms / 1000)
        _show(self.sample_cyc, r.min_sample_cycles, "{}")
        _show(self.resolution, r.resolution_mv_per_lsb)


# ── Operating Points Tab ──────────────────────────────────────────────────────

class OperatingTab:
    def __init__(self, parent: ctk.CTkFrame):
        self._build(parent)

    def _build(self, parent):
        self.table = ctk.CTkFrame(parent, fg_color="transparent")
        self.table.pack(fill="x", padx=10, pady=10)

        headers = ["Level", "V_input", "V_mcuL", "V_mcuH", "Requirement", "Status"]
        widths = [90, 85, 85, 85, 130, 90]

        for i, (text, w) in enumerate(zip(headers, widths)):
            ctk.CTkLabel(self.table, text=text, width=w, font=("", 12, "bold"),
                         anchor="w", fg_color=("gray80", "gray25")).grid(
                row=0, column=i, padx=1, pady=1, sticky="ew")

        self.rows = []
        row_labels = ["0V", "Logic Low", "Logic High", "ADC Scale", "Max Input"]
        for i, label in enumerate(row_labels):
            rn = i + 1
            bg = ("gray90", "gray20") if i % 2 == 0 else ("gray95", "gray17")
            ctk.CTkLabel(self.table, text=label, width=widths[0], anchor="w",
                         font=("", 13), fg_color=bg).grid(row=rn, column=0, padx=1, pady=1, sticky="ew")
            cells = {}
            for j, (key, w) in enumerate(zip(["v_in", "v_mcu_l", "v_mcu_h", "thresh", "status"],
                                              widths[1:]), start=1):
                bold = key in ("v_mcu_h", "status")
                c = ctk.CTkLabel(self.table, text=NEEDS_INPUT, width=w, anchor="w",
                                 font=("", 13, "bold") if bold else ("", 13), fg_color=bg,
                                 text_color=MUTED)
                c.grid(row=rn, column=j, padx=1, pady=1, sticky="ew")
                cells[key] = c
            self.rows.append(cells)

    def refresh(self, r: CalculationResult):
        ops = r.operating_points or [{}] * len(self.rows)
        for cells, op in zip(self.rows, ops):
            _show(cells["v_in"], op.get("v_in"), "{:.2f}", " V")
            _show(cells["v_mcu_l"], op.get("v_mcu_l"), "{:.3f}", " V")
            _show(cells["v_mcu_h"], op.get("v_mcu_h"), "{:.3f}", " V")
            req = op.get("requirement")
            if req is None:
                cells["thresh"].configure(text=NEEDS_INPUT, text_color=MUTED)
            else:
                cells["thresh"].configure(text=req, text_color=NORMAL)
            st = op.get("status")
            _show_status(cells["status"], None if st is None else (st, op.get("level")))


# ── Bandwidth / PPS Results Tab ───────────────────────────────────────────────

class BandwidthTab:
    """Displays the computed bandwidth / PPS analysis results."""

    def __init__(self, parent: ctk.CTkFrame):
        self._build(parent)

    def _build(self, parent):
        cw = [200, 120, 80]
        ctk.CTkLabel(parent, text="RC Filter Characteristics", font=("", 13, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        ft = ctk.CTkFrame(parent, fg_color="transparent"); ft.pack(fill="x", padx=10)
        _table_header(ft, ["Parameter", "Value", "Unit"], cw)
        self.c_total = _table_row(ft, "C_total", "pF", 1, cw)
        self.tau = _table_row(ft, "Time constant (τ)", "ns", 2, cw)
        self.f_3db = _table_row(ft, "-3 dB bandwidth", "MHz", 3, cw)
        self.t_rise = _table_row(ft, "10–90% rise time", "ns", 4, cw)

        ctk.CTkLabel(parent, text="Threshold Timing", font=("", 13, "bold")).pack(anchor="w", padx=10, pady=(15, 5))
        tt = ctk.CTkFrame(parent, fg_color="transparent"); tt.pack(fill="x", padx=10)
        _table_header(tt, ["Parameter", "Value", "Unit"], cw)
        self.t_undef_rise = _table_row(tt, "Undefined zone (rise)", "ns", 1, cw)
        self.t_undef_fall = _table_row(tt, "Undefined zone (fall)", "ns", 2, cw)

        ctk.CTkLabel(parent, text="Maximum Frequency Limits", font=("", 13, "bold")).pack(anchor="w", padx=10, pady=(15, 5))
        lt = ctk.CTkFrame(parent, fg_color="transparent"); lt.pack(fill="x", padx=10)
        _table_header(lt, ["Limit", "Value", "Unit"], cw)
        self.f_analog = _table_row(lt, "Analog (conservative)", "kHz", 1, cw)
        self.f_practical = _table_row(lt, "Analog (practical)", "kHz", 2, cw)
        self.f_digital = _table_row(lt, "Digital sampling", "kHz", 3, cw)
        self.f_overflow = _table_row(lt, "Counter overflow", "kHz", 4, cw)

        ctk.CTkLabel(parent, text="Effective Limit", font=("", 13, "bold")).pack(anchor="w", padx=10, pady=(15, 5))
        et = ctk.CTkFrame(parent, fg_color="transparent"); et.pack(fill="x", padx=10)
        _table_header(et, ["Bottleneck", "Max PPS", "Unit"], cw)
        self.f_effective = _table_row(et, "--", "kHz", 1, cw)
        self._eff_label = et.grid_slaves(row=1, column=0)[0]

        self.note = ctk.CTkLabel(parent, text="", text_color="red", justify="left",
                                 anchor="w", wraplength=420)
        self.note.pack(anchor="w", padx=10, pady=(8, 5))

    def refresh(self, r: BandwidthResult):
        def cell(label, key, value, fmt):
            if value is None and key in r.blocked:
                label.configure(text=BLOCKED, text_color="red")
            else:
                _show(label, value, fmt)

        khz = lambda v: None if v is None else v / 1e3
        cell(self.c_total, "c_total", r.c_total_pf, "{:.1f}")
        cell(self.tau, "tau", r.tau_ns, "{:.2f}")
        cell(self.f_3db, "f_3db", None if r.f_3db_hz is None else r.f_3db_hz / 1e6, "{:.3f}")
        cell(self.t_rise, "t_rise", r.t_rise_ns, "{:.2f}")
        cell(self.t_undef_rise, "t_undefined_rise", r.t_undefined_rise_ns, "{:.2f}")
        cell(self.t_undef_fall, "t_undefined_fall", r.t_undefined_fall_ns, "{:.2f}")
        cell(self.f_analog, "analog", khz(r.f_max_analog_hz), "{:.1f}")
        cell(self.f_practical, "practical", khz(r.f_max_practical_hz), "{:.1f}")
        cell(self.f_digital, "digital", khz(r.f_max_digital_hz), "{:.1f}")
        cell(self.f_overflow, "overflow", khz(r.f_max_overflow_hz), "{:.1f}")
        cell(self.f_effective, "effective", khz(r.f_max_effective_hz), "{:.1f}")
        self._eff_label.configure(text=r.limiting_factor or "--")

        reasons = []
        for reason in r.blocked.values():
            if reason not in reasons:
                reasons.append(reason)
        self.note.configure(text="\n".join(reasons))
