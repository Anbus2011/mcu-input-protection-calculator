"""
Output panel classes — tabview components and result tables.
All display-only; updated via refresh(result) from AppState callbacks.
"""
from __future__ import annotations

import customtkinter as ctk
from typing import Optional

from src.models.circuit_model import CalculationResult
from src.models.bandwidth_model import BandwidthResult


# ── Table-row helpers ──────���──────────────────────────────────────────────────

def _table_header(parent, texts, widths):
    for i, (text, w) in enumerate(zip(texts, widths)):
        lbl = ctk.CTkLabel(parent, text=text, width=w, font=("", 12, "bold"),
                           anchor="w", fg_color=("gray80", "gray25"))
        lbl.grid(row=0, column=i, padx=1, pady=1, sticky="ew")


def _table_row(parent, label, unit, row_num, col_widths):
    bg = ("gray90", "gray20") if row_num % 2 == 1 else ("gray95", "gray17")
    ctk.CTkLabel(parent, text=label, width=col_widths[0], anchor="w",
                 fg_color=bg, font=("", 13)).grid(row=row_num, column=0, padx=1, pady=1, sticky="ew")
    val = ctk.CTkLabel(parent, text="--", width=col_widths[1], anchor="w",
                       font=("", 13, "bold"), fg_color=bg)
    val.grid(row=row_num, column=1, padx=1, pady=1, sticky="ew")
    ctk.CTkLabel(parent, text=unit, width=col_widths[2], anchor="w",
                 fg_color=bg, font=("", 13)).grid(row=row_num, column=2, padx=1, pady=1, sticky="ew")
    return val


def _component_row(parent, label, row_num, col_widths):
    bg = ("gray90", "gray20") if row_num % 2 == 1 else ("gray95", "gray17")
    ctk.CTkLabel(parent, text=label, width=col_widths[0], anchor="w",
                 fg_color=bg, font=("", 13)).grid(row=row_num, column=0, padx=1, pady=1, sticky="ew")
    cells = {}
    for i, key in enumerate(["current", "power", "rating", "margin"], start=1):
        c = ctk.CTkLabel(parent, text="--", width=col_widths[i], anchor="w",
                         font=("", 13, "bold") if key == "margin" else ("", 13), fg_color=bg)
        c.grid(row=row_num, column=i, padx=1, pady=1, sticky="ew")
        cells[key] = c
    return cells


def _safety_row(parent, label, row_num, col_widths):
    bg = ("gray90", "gray20") if row_num % 2 == 1 else ("gray95", "gray17")
    ctk.CTkLabel(parent, text=label, width=col_widths[0], anchor="w",
                 fg_color=bg, font=("", 13)).grid(row=row_num, column=0, padx=1, pady=1, sticky="ew")
    cells = {}
    for i, key in enumerate(["value", "limit", "margin", "status"], start=1):
        c = ctk.CTkLabel(parent, text="--", width=col_widths[i], anchor="w",
                         font=("", 13, "bold") if key == "status" else ("", 13), fg_color=bg)
        c.grid(row=row_num, column=i, padx=1, pady=1, sticky="ew")
        cells[key] = c
    return cells


def _inj_row(parent, label, row_num, col_widths):
    bg = ("gray90", "gray20") if row_num % 2 == 1 else ("gray95", "gray17")
    ctk.CTkLabel(parent, text=label, width=col_widths[0], anchor="w",
                 fg_color=bg, font=("", 13)).grid(row=row_num, column=0, padx=1, pady=1, sticky="ew")
    cells = {}
    for i, key in enumerate(["value", "limit", "status"], start=1):
        c = ctk.CTkLabel(parent, text="--", width=col_widths[i], anchor="w",
                         font=("", 13, "bold") if key == "status" else ("", 13), fg_color=bg)
        c.grid(row=row_num, column=i, padx=1, pady=1, sticky="ew")
        cells[key] = c
    return cells


def _margin_text(margin_pct: Optional[float], power_mw: float):
    """Return (text, color) for a power margin percentage."""
    if margin_pct is None:
        return f"need \u2265{power_mw * 1.5:.0f}", "gray60"
    if margin_pct > 20:
        return f"\u2713 {margin_pct:.0f}%", "green"
    elif margin_pct > 0:
        return f"\u26a0 {margin_pct:.0f}%", "orange"
    else:
        return f"\u2717 {margin_pct:.0f}%", "red"


# ── Component Analysis Tab ────────────────────────────────────────────────────

class ComponentsTab:
    def __init__(self, parent: ctk.CTkFrame):
        self._build(parent)

    def _build(self, parent):
        # Divider network
        ctk.CTkLabel(parent, text="Divider Network", font=("", 13, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        dt = ctk.CTkFrame(parent, fg_color="transparent"); dt.pack(fill="x", padx=10)
        cw = [200, 100, 60]
        _table_header(dt, ["Parameter", "Value", "Unit"], cw)
        self.r_total = _table_row(dt, "Input Impedance (R1+R2)", "k\u03a9", 1, cw)
        self.ratio = _table_row(dt, "Divider Ratio", "", 2, cw)
        self.r_source = _table_row(dt, "ADC Source Impedance (R1\u2225R2)", "k\u03a9", 3, cw)
        self.p_total = _table_row(dt, "Power Dissipation", "mW", 4, cw)

        # Component power
        ctk.CTkLabel(parent, text="Component Power (at Max Input)", font=("", 13, "bold")).pack(anchor="w", padx=10, pady=(15, 5))
        ct = ctk.CTkFrame(parent, fg_color="transparent"); ct.pack(fill="x", padx=10)
        ccw = [80, 90, 90, 100, 90]
        _table_header(ct, ["Component", "Current", "Power", "Power Rating", "Margin %"], ccw)
        self.r1_row = _component_row(ct, "R1", 1, ccw)
        self.r2_row = _component_row(ct, "R2", 2, ccw)
        self.z_row = _component_row(ct, "Zener", 3, ccw)

        # Clamp voltage
        ctk.CTkLabel(parent, text="Voltage at MCU Pin", font=("", 13, "bold")).pack(anchor="w", padx=10, pady=(15, 5))
        vt = ctk.CTkFrame(parent, fg_color="transparent"); vt.pack(fill="x", padx=10)
        vcw = [150, 100, 60]
        _table_header(vt, ["Condition", "V_mcu", "Unit"], vcw)
        self.vclamp_typ = _table_row(vt, "Typical", "V", 1, vcw)
        self.vclamp_worst = _table_row(vt, "Worst Case", "V", 2, vcw)

    def refresh(self, r: CalculationResult):
        self.r_total.configure(text=f"{r.r_total_ohms / 1000:.2f}")
        self.ratio.configure(text=f"{r.k_nominal:.4f}")
        self.r_source.configure(text=f"{r.r_source_ohms / 1000:.2f}")
        self.p_total.configure(text=f"{r.p_total_mw:.1f}")

        # R1
        self.r1_row["current"].configure(text=f"{r.i_r1_ma:.2f} mA")
        self.r1_row["power"].configure(text=f"{r.p_r1_mw:.1f} mW")
        self.r1_row["rating"].configure(text=f"{r.r1_rating_mw:.0f} mW" if r.r1_rating_mw else "--")
        txt, clr = _margin_text(r.r1_margin_pct, r.p_r1_mw)
        self.r1_row["margin"].configure(text=txt, text_color=clr)

        # R2
        self.r2_row["current"].configure(text=f"{r.i_r2_ma:.2f} mA")
        self.r2_row["power"].configure(text=f"{r.p_r2_mw:.1f} mW")
        self.r2_row["rating"].configure(text=f"{r.r2_rating_mw:.0f} mW" if r.r2_rating_mw else "--")
        txt, clr = _margin_text(r.r2_margin_pct, r.p_r2_mw)
        self.r2_row["margin"].configure(text=txt, text_color=clr)

        # Zener
        self.z_row["current"].configure(text=f"{r.i_z_ma:.2f} mA")
        self.z_row["power"].configure(text=f"{r.p_z_mw:.1f} mW")
        self.z_row["rating"].configure(text=f"{r.z_ptot_mw:.0f} mW")
        txt, clr = _margin_text(r.z_margin_pct, r.p_z_mw)
        self.z_row["margin"].configure(text=txt, text_color=clr)

        self.vclamp_typ.configure(text=f"{r.v_mcu_typ:.3f}")
        self.vclamp_worst.configure(text=f"{r.v_mcu_worst_zener:.3f}")


# ── MCU Input / Safety Tab ────────────────────────────────────────────────────

class SafetyTab:
    def __init__(self, parent: ctk.CTkFrame):
        self._build(parent)

    def _build(self, parent):
        # Voltage limits
        ctk.CTkLabel(parent, text="Voltage Limits (at Max Input)", font=("", 13, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        vt = ctk.CTkFrame(parent, fg_color="transparent"); vt.pack(fill="x", padx=10)
        vw = [150, 90, 90, 90, 80]
        _table_header(vt, ["Parameter", "V_mcu", "Limit", "Margin", "Status"], vw)
        self.rec_row = _safety_row(vt, "vs Safe Max", 1, vw)
        self.abs_row = _safety_row(vt, "vs Absolute Max", 2, vw)

        # Injection current
        ctk.CTkLabel(parent, text="Injection Current", font=("", 13, "bold")).pack(anchor="w", padx=10, pady=(15, 5))
        it = ctk.CTkFrame(parent, fg_color="transparent"); it.pack(fill="x", padx=10)
        iw = [150, 90, 90, 100]
        _table_header(it, ["Parameter", "Value", "Limit", "Status"], iw)
        self.inj_row = _inj_row(it, "Estimated", 1, iw)

        # ADC performance
        ctk.CTkLabel(parent, text="ADC Performance", font=("", 13, "bold")).pack(anchor="w", padx=10, pady=(15, 5))
        at = ctk.CTkFrame(parent, fg_color="transparent"); at.pack(fill="x", padx=10)
        aw = [150, 100, 80]
        _table_header(at, ["Parameter", "Value", "Unit"], aw)
        self.source_z = _table_row(at, "Source Impedance", "k\u03a9", 1, aw)
        self.sample_cyc = _table_row(at, "Min Sample Cycles", "cycles", 2, aw)
        self.resolution = _table_row(at, "Resolution", "mV/LSB", 3, aw)

    def refresh(self, r: CalculationResult, mcu_safe_inj: float):
        v_rec_max = r.plot_data.get("v_rec_max", 3.6)
        v_abs_max = r.plot_data.get("v_abs_max", 4.0)

        # Recommended
        self.rec_row["value"].configure(text=f"{r.v_mcu_worst:.3f} V")
        self.rec_row["limit"].configure(text=f"{v_rec_max:.2f} V")
        self.rec_row["margin"].configure(text=f"{r.margin_rec_v * 1000:+.0f} mV")
        if r.margin_rec_v >= 0.05:
            self.rec_row["status"].configure(text="\u2713 PASS", text_color="green")
        elif r.margin_rec_v >= 0:
            self.rec_row["status"].configure(text="\u26a0 TIGHT", text_color="orange")
        else:
            self.rec_row["status"].configure(text="\u2717 FAIL", text_color="red")

        # Absolute
        self.abs_row["value"].configure(text=f"{r.v_mcu_worst:.3f} V")
        self.abs_row["limit"].configure(text=f"{v_abs_max:.2f} V")
        self.abs_row["margin"].configure(text=f"{r.margin_abs_v * 1000:+.0f} mV")
        if r.margin_abs_v >= 0.1:
            self.abs_row["status"].configure(text="\u2713 PASS", text_color="green")
        elif r.margin_abs_v >= 0:
            self.abs_row["status"].configure(text="\u26a0 TIGHT", text_color="orange")
        else:
            self.abs_row["status"].configure(text="\u2717 FAIL", text_color="red")

        # Injection
        self.inj_row["value"].configure(text=f"{r.i_injection_ma:.2f} mA")
        self.inj_row["limit"].configure(text=f"{mcu_safe_inj:.1f} mA")
        if r.i_injection_ma <= mcu_safe_inj * 0.5:
            self.inj_row["status"].configure(text="\u2713 OK", text_color="green")
        elif r.i_injection_ma <= mcu_safe_inj:
            self.inj_row["status"].configure(text="\u26a0 MARGINAL", text_color="orange")
        else:
            self.inj_row["status"].configure(text="\u2717 HIGH", text_color="red")

        # ADC
        self.source_z.configure(text=f"{r.r_source_ohms / 1000:.2f}")
        self.sample_cyc.configure(text=f"{r.min_sample_cycles}")
        self.resolution.configure(text=f"{r.resolution_mv_per_lsb:.2f}")


# ── Operating Points Tab ─────��───────────────────────────────────────────────

class OperatingTab:
    def __init__(self, parent: ctk.CTkFrame):
        self._build(parent)

    def _build(self, parent):
        self.table = ctk.CTkFrame(parent, fg_color="transparent")
        self.table.pack(fill="x", padx=10, pady=10)

        headers = ["Level", "V_input", "V_mcuL", "V_mcuH", "Requirement", "Status"]
        widths = [90, 70, 75, 75, 130, 90]

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
                c = ctk.CTkLabel(self.table, text="--", width=w, anchor="w",
                                 font=("", 13, "bold") if bold else ("", 13), fg_color=bg)
                c.grid(row=rn, column=j, padx=1, pady=1, sticky="ew")
                cells[key] = c
            self.rows.append(cells)

    def refresh(self, r: CalculationResult):
        for i, op in enumerate(r.operating_points):
            self.rows[i]["v_in"].configure(text=f"{op['v_in']:.2f} V")
            self.rows[i]["v_mcu_l"].configure(text=f"{op['v_mcu_l']:.3f} V")
            self.rows[i]["v_mcu_h"].configure(text=f"{op['v_mcu_h']:.3f} V")
            self.rows[i]["thresh"].configure(text=op["requirement"])
            self.rows[i]["status"].configure(text=op["status"], text_color=op["color"])


# ── Bandwidth / PPS Results Tab ──────���────────────────────────────────────────

class BandwidthTab:
    """Displays the computed bandwidth / PPS analysis results."""

    def __init__(self, parent: ctk.CTkFrame):
        self._build(parent)

    def _build(self, parent):
        ctk.CTkLabel(parent, text="RC Filter Characteristics", font=("", 13, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        ft = ctk.CTkFrame(parent, fg_color="transparent"); ft.pack(fill="x", padx=10)
        cw = [200, 120, 80]
        _table_header(ft, ["Parameter", "Value", "Unit"], cw)
        self.c_total = _table_row(ft, "C_total", "pF", 1, cw)
        self.tau = _table_row(ft, "Time constant (\u03c4)", "ns", 2, cw)
        self.f_3db = _table_row(ft, "-3 dB bandwidth", "MHz", 3, cw)
        self.t_rise = _table_row(ft, "10\u201390% rise time", "ns", 4, cw)

        ctk.CTkLabel(parent, text="Threshold Timing", font=("", 13, "bold")).pack(anchor="w", padx=10, pady=(15, 5))
        tt = ctk.CTkFrame(parent, fg_color="transparent"); tt.pack(fill="x", padx=10)
        _table_header(tt, ["Parameter", "Value", "Unit"], cw)
        self.t_undef_rise = _table_row(tt, "Undefined zone (rise)", "ns", 1, cw)
        self.t_undef_fall = _table_row(tt, "Undefined zone (fall)", "ns", 2, cw)

        ctk.CTkLabel(parent, text="Maximum Frequency Limits", font=("", 13, "bold")).pack(anchor="w", padx=10, pady=(15, 5))
        lt = ctk.CTkFrame(parent, fg_color="transparent"); lt.pack(fill="x", padx=10)
        lw = [200, 120, 80]
        _table_header(lt, ["Limit", "Value", "Unit"], lw)
        self.f_analog = _table_row(lt, "Analog (conservative)", "kHz", 1, lw)
        self.f_practical = _table_row(lt, "Analog (practical)", "kHz", 2, lw)
        self.f_digital = _table_row(lt, "Digital sampling", "kHz", 3, lw)
        self.f_overflow = _table_row(lt, "Counter overflow", "kHz", 4, lw)

        ctk.CTkLabel(parent, text="Effective Limit", font=("", 13, "bold")).pack(anchor="w", padx=10, pady=(15, 5))
        et = ctk.CTkFrame(parent, fg_color="transparent"); et.pack(fill="x", padx=10)
        ew = [200, 120, 80]
        _table_header(et, ["Bottleneck", "Max PPS", "Unit"], ew)
        self.f_effective = _table_row(et, "--", "kHz", 1, ew)
        self._eff_label = et.grid_slaves(row=1, column=0)[0]

    def refresh(self, r: BandwidthResult):
        self.c_total.configure(text=f"{r.c_total_pf:.1f}")
        self.tau.configure(text=f"{r.tau_ns:.2f}")
        self.f_3db.configure(text=f"{r.f_3db_hz / 1e6:.3f}" if r.f_3db_hz else "--")
        self.t_rise.configure(text=f"{r.t_rise_ns:.2f}")

        self.t_undef_rise.configure(text=f"{r.t_undefined_rise_ns:.2f}" if r.t_undefined_rise_ns else "--")
        self.t_undef_fall.configure(text=f"{r.t_undefined_fall_ns:.2f}" if r.t_undefined_fall_ns else "--")

        def _fmt_khz(val):
            return f"{val / 1e3:.1f}" if val else "--"

        self.f_analog.configure(text=_fmt_khz(r.f_max_analog_hz))
        self.f_practical.configure(text=_fmt_khz(r.f_max_practical_hz))
        self.f_digital.configure(text=_fmt_khz(r.f_max_digital_hz))
        self.f_overflow.configure(text=_fmt_khz(r.f_max_overflow_hz))

        self.f_effective.configure(text=_fmt_khz(r.f_max_effective_hz))
        self._eff_label.configure(text=r.limiting_factor or "--")
