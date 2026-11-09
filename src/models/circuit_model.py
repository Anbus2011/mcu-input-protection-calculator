"""
Pure math/physics engine for resistor divider with Zener clamp analysis.
No UI dependencies. All inputs are plain floats in dataclasses, all outputs
are result dataclasses.

Every input may be None (blank, unreadable or out of range). Each output is
computed only when every input it depends on is present; otherwise it is left
as None and the missing inputs are listed in ``CalculationResult.missing``
under that output's key. Nothing is ever substituted for a missing input.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from src.core.constants import ADC_SAMPLE_THRESHOLDS, ADC_SAMPLE_DEFAULT


# ── Data containers ──────────────────────────────────────────────────────────

@dataclass
class ZenerParams:
    vz_nom: Optional[float] = None
    vz_min: Optional[float] = None
    vz_max: Optional[float] = None
    izt_ma: Optional[float] = None
    izk_ma: Optional[float] = None
    zzt_typ: Optional[float] = None
    zzt_max: Optional[float] = None
    zzk_typ: Optional[float] = None
    zzk_max: Optional[float] = None
    ptot_mw: Optional[float] = None


@dataclass
class ResistorParams:
    r1_ohms: Optional[float] = None
    r2_ohms: Optional[float] = None
    # 0 means "no series resistor". None means it is needed but unusable
    # (for example a value > 0 with no unit).
    rs_ohms: Optional[float] = 0.0
    r1_tol_pct: Optional[float] = None
    r2_tol_pct: Optional[float] = None
    r1_rating_mw: Optional[float] = None
    r2_rating_mw: Optional[float] = None


@dataclass
class McuParams:
    vdd: Optional[float] = None
    v_recommended_max: Optional[float] = None
    v_absolute_max: Optional[float] = None
    safe_injection_ma: Optional[float] = None
    adc_bits: Optional[int] = None
    vil_factor: Optional[float] = None
    vih_factor: Optional[float] = None


@dataclass
class SystemParams:
    v_input_max: Optional[float] = None
    v_analog_fullscale: Optional[float] = None
    v_logic_high_min: Optional[float] = None
    v_logic_low_max: Optional[float] = None


# Status levels used by the view to pick a colour.
PASS, WARN, FAIL, INFO = "pass", "warn", "fail", "info"


@dataclass
class CalculationResult:
    # Divider network
    r_total_ohms: Optional[float] = None
    k_nominal: Optional[float] = None
    k_high: Optional[float] = None
    k_low: Optional[float] = None
    r_source_ohms: Optional[float] = None
    p_total_mw: Optional[float] = None

    # Component currents/power at max input (nominal resistors, typical Zener)
    i_r1_ma: Optional[float] = None
    i_r2_ma: Optional[float] = None
    i_z_ma: Optional[float] = None
    p_r1_mw: Optional[float] = None
    p_r2_mw: Optional[float] = None
    p_z_mw: Optional[float] = None

    # Clamp voltages at max input (nominal resistors)
    v_mcu_typ: Optional[float] = None
    v_mcu_worst_zener: Optional[float] = None

    # Safety margins (true worst case: tolerance + zener)
    v_mcu_worst: Optional[float] = None
    margin_rec_v: Optional[float] = None
    margin_abs_v: Optional[float] = None
    rec_status: Optional[tuple] = None        # (text, level)
    abs_status: Optional[tuple] = None
    i_injection_ma: Optional[float] = None
    inj_status: Optional[tuple] = None

    # ADC
    min_sample_cycles: Optional[float] = None
    resolution_mv_per_lsb: Optional[float] = None

    # MCU pin logic thresholds (factor x VDD)
    vil_v: Optional[float] = None
    vih_v: Optional[float] = None
    # Lowest solved pin voltage at the logic-high input (V_mcuL at Logic High)
    v_high_pin: Optional[float] = None

    # Operating points: list of dicts with keys
    # key, v_in, v_mcu_l, v_mcu_h, requirement, status, level
    operating_points: list = field(default_factory=list)

    # For plot generation. Keys present only when computable.
    plot_data: dict = field(default_factory=dict)

    # Power rating margins (percentage)
    r1_margin_pct: Optional[float] = None
    r2_margin_pct: Optional[float] = None
    z_margin_pct: Optional[float] = None
    r1_margin_status: Optional[tuple] = None
    r2_margin_status: Optional[tuple] = None
    z_margin_status: Optional[tuple] = None
    r1_rating_mw: Optional[float] = None
    r2_rating_mw: Optional[float] = None
    z_ptot_mw: Optional[float] = None

    # output key -> list of missing input names ("resistors.r1_ohms", ...)
    missing: dict = field(default_factory=dict)
    # Solver convergence warnings (text)
    warnings: list = field(default_factory=list)


# ── Zener voltage model ──────────────────────────────────────────────────────

def calculate_zener_voltage(iz_ma: float, zener: ZenerParams,
                            use_worst_case: bool = False) -> tuple:
    """
    Calculate Zener clamp voltage at a given current.
    Returns (v_clamp, r_differential). r_differential is None when the ZZK
    input it needs is blank.

    Three-region model:
      - Below IZK: soft breakdown, V ~ 0.97-1.0 x VZ_knee
      - IZK to IZT: linear interpolation VZ_knee -> VZ_nom
      - Above IZT: extrapolate with ZZT slope
    """
    if use_worst_case:
        vz_at_izt = zener.vz_max
        vz_at_izk = zener.vz_max * 0.97
        zzt = zener.zzt_max
        zzk = zener.zzk_max
    else:
        vz_at_izt = zener.vz_nom
        vz_at_izk = zener.vz_nom * 0.94
        zzt = zener.zzt_typ
        zzk = zener.zzk_typ

    izt = zener.izt_ma
    izk = zener.izk_ma

    if iz_ma <= 0:
        return vz_at_izk, zzk
    elif iz_ma <= izk:
        ratio = iz_ma / izk
        v_clamp = vz_at_izk * (0.97 + 0.03 * ratio)
        rdif = zzk
    elif iz_ma <= izt:
        ratio = (iz_ma - izk) / (izt - izk)
        v_clamp = vz_at_izk + (vz_at_izt - vz_at_izk) * ratio
        rdif = None if (zzk is None or zzt is None) else zzk + (zzt - zzk) * ratio
    else:
        v_clamp = vz_at_izt + (iz_ma - izt) * zzt / 1000
        rdif = zzt

    return v_clamp, rdif


# ── Iterative solver (the only copy) ─────────────────────────────────────────

SOLVER_ITERATIONS = 15
SOLVER_SETTLE_V = 1e-3   # last step must move the node by no more than 1 mV


@dataclass
class SolveResult:
    v_node: float
    settled: bool


def solve_node_voltage(vin: float, r1: float, r2: float,
                       zener: ZenerParams, use_worst_zener: bool) -> SolveResult:
    """Solve the MCU node voltage at *vin* (CLAUDE.md §4B).

    15 iterations of V = 0.3 V + 0.7 V_clamp, starting from VZ. If IZ falls
    below 0.5 mA the clamp is ineffective and the result is capped at VZ.

    ``settled`` is False when the iteration did not settle: the last step
    moved the node by more than 1 mV, or the unclamped iterate left the
    physical range [0, V_divider]. The returned voltage is then not reliable.
    """
    v_div = vin * r2 / (r1 + r2)
    vz_ref = zener.vz_max if use_worst_zener else zener.vz_nom
    vz_knee = vz_ref * (0.97 if use_worst_zener else 0.94)

    if v_div < vz_knee:
        return SolveResult(v_div, True)

    v_node = vz_ref
    final_iz = 0.0
    last_step = 0.0
    for i in range(SOLVER_ITERATIONS):
        i_r1 = (vin - v_node) / r1 * 1000
        i_r2 = v_node / r2 * 1000
        i_z = i_r1 - i_r2
        if i_z > 0:
            final_iz = i_z
            v_clamp, _ = calculate_zener_voltage(i_z, zener, use_worst_zener)
            new_v = v_node * 0.3 + v_clamp * 0.7
            last_step = new_v - v_node
            v_node = new_v
        else:
            # On the first pass this means the divider never reaches VZ (no
            # clamping). Later, it means the iterate overshot above V_divider.
            return SolveResult(v_div, i == 0)

    settled = abs(last_step) <= SOLVER_SETTLE_V and 0.0 <= v_node <= v_div

    if final_iz < 0.5:
        return SolveResult(min(v_div, vz_ref), settled)

    return SolveResult(max(vz_knee, min(v_div, v_node)), settled)


# ── ADC helper ───────────────────────────────────────────────────────────────

def get_min_sample_cycles(r_source_ohms: float) -> float:
    for threshold_ohms, cycles in ADC_SAMPLE_THRESHOLDS:
        if r_source_ohms <= threshold_ohms:
            return cycles
    return ADC_SAMPLE_DEFAULT


# ── Status helpers (verdict thresholds) ──────────────────────────────────────

def _margin_status(margin_pct: float) -> tuple:
    if margin_pct > 20:
        return f"✓ {margin_pct:.0f}%", PASS
    elif margin_pct > 0:
        return f"⚠ {margin_pct:.0f}%", WARN
    return f"✗ {margin_pct:.0f}%", FAIL


def _voltage_status(margin_v: float, pass_v: float) -> tuple:
    if margin_v >= pass_v:
        return "✓ PASS", PASS
    elif margin_v >= 0:
        return "⚠ TIGHT", WARN
    return "✗ FAIL", FAIL


def _injection_status(i_inj: float, limit: float) -> tuple:
    if i_inj <= limit * 0.5:
        return "✓ OK", PASS
    elif i_inj <= limit:
        return "⚠ MARGINAL", WARN
    return "✗ HIGH", FAIL


# ── Input cleaning (never crash on bad numbers passed in directly) ───────────

def _finite(x):
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _positive(x):
    x = _finite(x)
    return x if x is not None and x > 0 else None


def _non_negative(x):
    x = _finite(x)
    return x if x is not None and x >= 0 else None


def _tolerance(x):
    x = _finite(x)
    return x if x is not None and 0 <= x < 100 else None


def _fraction(x):
    x = _finite(x)
    return x if x is not None and 0 < x < 1 else None


def _clean_inputs(resistors, zener, mcu, system) -> dict:
    v = {
        "resistors.r1_ohms": _positive(resistors.r1_ohms),
        "resistors.r2_ohms": _positive(resistors.r2_ohms),
        "resistors.rs_ohms": _non_negative(resistors.rs_ohms),
        "resistors.r1_tol_pct": _tolerance(resistors.r1_tol_pct),
        "resistors.r2_tol_pct": _tolerance(resistors.r2_tol_pct),
        "resistors.r1_rating_mw": _positive(resistors.r1_rating_mw),
        "resistors.r2_rating_mw": _positive(resistors.r2_rating_mw),
        "zener.vz_nom": _positive(zener.vz_nom),
        "zener.vz_max": _positive(zener.vz_max),
        "zener.izt_ma": _positive(zener.izt_ma),
        "zener.izk_ma": _positive(zener.izk_ma),
        "zener.zzt_typ": _non_negative(zener.zzt_typ),
        "zener.zzt_max": _non_negative(zener.zzt_max),
        "zener.ptot_mw": _positive(zener.ptot_mw),
        "mcu.vdd": _positive(mcu.vdd),
        "mcu.v_recommended_max": _positive(mcu.v_recommended_max),
        "mcu.v_absolute_max": _positive(mcu.v_absolute_max),
        "mcu.safe_injection_ma": _positive(mcu.safe_injection_ma),
        "mcu.adc_bits": None,
        "mcu.vil_factor": _fraction(mcu.vil_factor),
        "mcu.vih_factor": _fraction(mcu.vih_factor),
        "system.v_input_max": _positive(system.v_input_max),
        "system.v_analog_fullscale": _non_negative(system.v_analog_fullscale),
        "system.v_logic_high_min": _non_negative(system.v_logic_high_min),
        "system.v_logic_low_max": _non_negative(system.v_logic_low_max),
    }
    bits = _finite(mcu.adc_bits)
    if bits is not None and bits.is_integer() and 1 <= bits <= 32:
        v["mcu.adc_bits"] = int(bits)
    # Model needs IZK < IZT (it divides by IZT - IZK)
    if v["zener.izk_ma"] is not None and v["zener.izt_ma"] is not None \
            and v["zener.izk_ma"] >= v["zener.izt_ma"]:
        v["zener.izk_ma"] = v["zener.izt_ma"] = None
    if v["mcu.vil_factor"] is not None and v["mcu.vih_factor"] is not None \
            and v["mcu.vil_factor"] >= v["mcu.vih_factor"]:
        v["mcu.vil_factor"] = v["mcu.vih_factor"] = None
    return v


# Input groups
R1, R2, RS = "resistors.r1_ohms", "resistors.r2_ohms", "resistors.rs_ohms"
T1, T2 = "resistors.r1_tol_pct", "resistors.r2_tol_pct"
Z_TYP = ("zener.vz_nom", "zener.izt_ma", "zener.izk_ma", "zener.zzt_typ")
Z_WC = ("zener.vz_max", "zener.izt_ma", "zener.izk_ma", "zener.zzt_max")
VDD = "mcu.vdd"
VIN = "system.v_input_max"

PLOT_POINTS = 200


# ── Main calculation entry point ─────────────────────────────────────────────

def calculate_all(resistors: ResistorParams, zener: ZenerParams,
                  mcu: McuParams, system: SystemParams) -> CalculationResult:
    """Run the full divider + Zener clamp analysis. Returns a CalculationResult."""
    res = CalculationResult()
    inp = _clean_inputs(resistors, zener, mcu, system)

    def need(key, *paths, deps=()):
        miss = []
        for d in deps:
            for p in res.missing.get(d, []):
                if p not in miss:
                    miss.append(p)
        for p in paths:
            if inp[p] is None and p not in miss:
                miss.append(p)
        if miss:
            res.missing[key] = miss
            return False
        return True

    # Zener with cleaned values (only fields the solver uses are read)
    z = ZenerParams(
        vz_nom=inp["zener.vz_nom"], vz_min=zener.vz_min, vz_max=inp["zener.vz_max"],
        izt_ma=inp["zener.izt_ma"], izk_ma=inp["zener.izk_ma"],
        zzt_typ=inp["zener.zzt_typ"], zzt_max=inp["zener.zzt_max"],
        zzk_typ=_finite(zener.zzk_typ), zzk_max=_finite(zener.zzk_max),
        ptot_mw=inp["zener.ptot_mw"],
    )

    r1, r2, rs = inp[R1], inp[R2], inp[RS]
    vin_max = inp[VIN]
    vdd = inp[VDD]
    v_rec_max = inp["mcu.v_recommended_max"]
    v_abs_max = inp["mcu.v_absolute_max"]

    unsettled = []

    def solve(vin, ra, rb, worst, where):
        sr = solve_node_voltage(vin, ra, rb, z, worst)
        if not sr.settled:
            unsettled.append(where)
        return sr.v_node

    # Divider network
    if need("divider", R1, R2):
        res.r_total_ohms = r1 + r2
        res.k_nominal = r2 / (r1 + r2)
    if need("r_source", R1, R2, RS):
        res.r_source_ohms = (r1 * r2) / (r1 + r2) + rs
        res.min_sample_cycles = get_min_sample_cycles(res.r_source_ohms)
    if need("tolerance", R1, R2, T1, T2):
        r1_tol = inp[T1] / 100
        r2_tol = inp[T2] / 100
        r1_min, r1_max = r1 * (1 - r1_tol), r1 * (1 + r1_tol)
        r2_min, r2_max = r2 * (1 - r2_tol), r2 * (1 + r2_tol)
        res.k_high = r2_max / (r1_min + r2_max)
        res.k_low = r2_min / (r1_max + r2_min)
    have_tol = res.k_high is not None

    def v_low(vin, where):
        """Lowest V_mcu: R1 max, R2 min, typical Zener (CLAUDE.md §4A)."""
        return solve(vin, r1_max, r2_min, False, where + " (V_mcuL)")

    def v_high(vin, where):
        """Highest V_mcu: R1 min, R2 max, worst-case Zener (CLAUDE.md §4A)."""
        return solve(vin, r1_min, r2_max, True, where + " (V_mcuH)")

    # Typical solve at max input, nominal resistors
    if need("typ_at_max", R1, R2, VIN, *Z_TYP):
        v_t = solve(vin_max, r1, r2, False, f"max input {vin_max:g} V (typical)")
        i_r1 = (vin_max - v_t) / r1 * 1000
        i_r2 = v_t / r2 * 1000
        i_z = max(0.0, i_r1 - i_r2)
        res.v_mcu_typ = v_t
        res.i_r1_ma, res.i_r2_ma, res.i_z_ma = i_r1, i_r2, i_z
        res.p_r1_mw = (i_r1 / 1000) ** 2 * r1 * 1000
        res.p_r2_mw = (i_r2 / 1000) ** 2 * r2 * 1000
        res.p_z_mw = v_t * i_z
        res.p_total_mw = res.p_r1_mw + res.p_r2_mw + res.p_z_mw

    if need("worst_zener_at_max", R1, R2, VIN, *Z_WC):
        res.v_mcu_worst_zener = solve(vin_max, r1, r2, True,
                                      f"max input {vin_max:g} V (worst Zener)")

    # Power rating margins
    res.r1_rating_mw = inp["resistors.r1_rating_mw"]
    res.r2_rating_mw = inp["resistors.r2_rating_mw"]
    res.z_ptot_mw = inp["zener.ptot_mw"]
    for name, rating, power in (
            ("r1", "resistors.r1_rating_mw", "p_r1_mw"),
            ("r2", "resistors.r2_rating_mw", "p_r2_mw"),
            ("z", "zener.ptot_mw", "p_z_mw")):
        p = getattr(res, power)
        if need(f"{name}_margin", rating, deps=("typ_at_max",)):
            pct = (inp[rating] - p) / inp[rating] * 100
            setattr(res, f"{name}_margin_pct", pct)
            setattr(res, f"{name}_margin_status", _margin_status(pct))
        elif p is not None:
            # Power is known; only the rating is blank. Show what is needed.
            setattr(res, f"{name}_margin_status",
                    (f"needs input (≥{p * 1.5:.0f} mW)", INFO))

    # True worst case at max input
    if need("v_mcu_worst", VIN, *Z_WC, deps=("tolerance",)):
        res.v_mcu_worst = v_high(vin_max, f"max input {vin_max:g} V")
    if need("margin_rec", "mcu.v_recommended_max", deps=("v_mcu_worst",)):
        res.margin_rec_v = v_rec_max - res.v_mcu_worst
        res.rec_status = _voltage_status(res.margin_rec_v, 0.05)
    if need("margin_abs", "mcu.v_absolute_max", deps=("v_mcu_worst",)):
        res.margin_abs_v = v_abs_max - res.v_mcu_worst
        res.abs_status = _voltage_status(res.margin_abs_v, 0.1)
    if need("injection", VDD, RS, deps=("v_mcu_worst",)):
        if res.v_mcu_worst > vdd:
            res.i_injection_ma = (res.v_mcu_worst - vdd) / (rs + 100) * 1000
        else:
            res.i_injection_ma = 0.0
    if need("inj_status", "mcu.safe_injection_ma", deps=("injection",)):
        res.inj_status = _injection_status(res.i_injection_ma,
                                           inp["mcu.safe_injection_ma"])

    # ADC resolution: VREF / 2^N referred to the divider input (VREF = VDD/VDDA)
    if need("resolution", VDD, "mcu.adc_bits", deps=("divider",)):
        res.resolution_mv_per_lsb = vdd / (2 ** inp["mcu.adc_bits"]) * 1000 / res.k_nominal

    # Logic thresholds at the MCU pin
    if need("vil", VDD, "mcu.vil_factor"):
        res.vil_v = inp["mcu.vil_factor"] * vdd
    if need("vih", VDD, "mcu.vih_factor"):
        res.vih_v = inp["mcu.vih_factor"] * vdd

    # Operating points
    def op_row(key, vin_path, label):
        row = {"key": key, "v_in": inp[vin_path], "v_mcu_l": None, "v_mcu_h": None,
               "requirement": None, "status": None, "level": None}
        if need(f"{key}.v_mcu_l", vin_path, *Z_TYP, deps=("tolerance",)):
            row["v_mcu_l"] = v_low(inp[vin_path], f"{label} {inp[vin_path]:g} V")
        if need(f"{key}.v_mcu_h", vin_path, *Z_WC, deps=("tolerance",)):
            row["v_mcu_h"] = v_high(inp[vin_path], f"{label} {inp[vin_path]:g} V")
        return row

    op_zero = {"key": "op_zero", "v_in": 0.0, "v_mcu_l": 0.0, "v_mcu_h": 0.0,
               "requirement": "--", "status": "Zero ref", "level": INFO}

    op_ll = op_row("op_ll", "system.v_logic_low_max", "Logic Low")
    if need("op_ll.requirement", deps=("vil",)):
        op_ll["requirement"] = f"< VIL {res.vil_v:.2f}V"
    if need("op_ll.status", deps=("vil", "op_ll.v_mcu_h")):
        ok = op_ll["v_mcu_h"] < res.vil_v
        op_ll["status"], op_ll["level"] = ("✓ PASS", PASS) if ok else ("✗ FAIL", FAIL)

    op_lh = op_row("op_lh", "system.v_logic_high_min", "Logic High")
    if need("op_lh.requirement", deps=("vih",)):
        op_lh["requirement"] = f"> VIH {res.vih_v:.2f}V"
    if need("op_lh.status", deps=("vih", "op_lh.v_mcu_l")):
        ok = op_lh["v_mcu_l"] > res.vih_v
        op_lh["status"], op_lh["level"] = ("✓ PASS", PASS) if ok else ("✗ FAIL", FAIL)
    res.v_high_pin = op_lh["v_mcu_l"]
    if "op_lh.v_mcu_l" in res.missing:
        res.missing["v_high_pin"] = list(res.missing["op_lh.v_mcu_l"])

    op_afs = op_row("op_afs", "system.v_analog_fullscale", "ADC Scale")
    if need("op_afs.requirement", VDD):
        op_afs["requirement"] = f"≤ VDD {vdd:.2f}V"
    if need("op_afs.status", VDD, "mcu.v_recommended_max", deps=("op_afs.v_mcu_h",)):
        vh = op_afs["v_mcu_h"]
        if vh <= vdd:
            op_afs["status"], op_afs["level"] = "✓ PASS", PASS
        elif vh <= v_rec_max:
            op_afs["status"], op_afs["level"] = "⚠ OVER", WARN
        else:
            op_afs["status"], op_afs["level"] = "✗ CLIP", FAIL

    op_max = op_row("op_max", VIN, "Max Input")
    if need("op_max.requirement", "mcu.v_absolute_max"):
        op_max["requirement"] = f"≤ {v_abs_max:.1f}V abs"
    if need("op_max.status", "mcu.v_absolute_max", deps=("op_max.v_mcu_h",)):
        ok = op_max["v_mcu_h"] <= v_abs_max
        op_max["status"], op_max["level"] = ("✓ PASS", PASS) if ok else ("✗ FAIL", FAIL)

    res.operating_points = [op_zero, op_ll, op_lh, op_afs, op_max]

    # Plot data: each curve is drawn when its own inputs are present.
    have_typ_curve = need("plot.typ", R1, R2, VIN, *Z_TYP)
    have_worst_curve = need("plot.worst", VIN, *Z_WC, deps=("tolerance",))
    if have_typ_curve or have_worst_curve:
        v_in_arr = np.linspace(0, vin_max, PLOT_POINTS)
        pd = {"v_in": v_in_arr, "vin_max": vin_max,
              "vdd": vdd, "v_rec_max": v_rec_max, "v_abs_max": v_abs_max}
        before = len(unsettled)
        if have_typ_curve:
            pd["v_mcu_typ"] = np.array(
                [solve(v, r1, r2, False, "plot") for v in v_in_arr])
        if have_worst_curve and have_tol:
            pd["v_mcu_worst"] = np.array(
                [v_high(v, "plot") for v in v_in_arr])
        n_plot_bad = len(unsettled) - before
        del unsettled[before:]
        if n_plot_bad:
            unsettled.append(f"{n_plot_bad} plot point(s)")
        res.plot_data = pd

    if unsettled:
        seen = []
        for w in unsettled:
            if w not in seen:
                seen.append(w)
        res.warnings.append(
            "Zener solver did not settle (last step > 1 mV or outside 0..V_divider) at: "
            + "; ".join(seen) + ". Those voltages are not reliable.")

    return res
