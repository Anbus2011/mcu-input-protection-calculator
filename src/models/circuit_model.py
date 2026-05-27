"""
Pure math/physics engine for resistor divider with Zener clamp analysis.
No UI dependencies. All inputs are plain floats/dicts, all outputs are dicts.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from src.core.constants import (
    ADC_SAMPLE_THRESHOLDS,
    ADC_SAMPLE_DEFAULT,
    INTERNAL_ESD_VF,
    INTERNAL_ESD_R,
)
from src.models.clamps.zener import ZenerClamp
from src.models.clamps.base import ClampModel


# ── Data containers ──────────────────────────────────────────────────────────

@dataclass
class ZenerParams:
    vz_nom: float = 3.3
    vz_min: float = 3.1
    vz_max: float = 3.5
    izt_ma: float = 5.0
    izk_ma: float = 1.0
    zzt_typ: float = 85.0
    zzt_max: float = 95.0
    zzk_typ: float = 350.0
    zzk_max: float = 600.0
    ptot_mw: float = 265.0


@dataclass
class ResistorParams:
    r1_ohms: float = 10000.0
    r2_ohms: float = 18000.0
    rs_ohms: float = 0.0
    r1_tol_pct: float = 1.0
    r2_tol_pct: float = 1.0
    r1_rating_mw: Optional[float] = 200.0
    r2_rating_mw: Optional[float] = 100.0


@dataclass
class McuParams:
    vdd: float = 3.3
    v_recommended_max: float = 3.6
    v_absolute_max: float = 4.0
    safe_injection_ma: float = 1.0


@dataclass
class SystemParams:
    v_input_max: float = 30.0
    v_analog_fullscale: float = 5.1
    v_logic_high_min: float = 3.8
    v_logic_low_max: float = 1.0


@dataclass
class CalculationResult:
    # Divider network
    r_total_ohms: float = 0.0
    k_nominal: float = 0.0
    k_high: float = 0.0
    k_low: float = 0.0
    r_source_ohms: float = 0.0
    p_total_mw: float = 0.0

    # Component currents/power at max input
    i_r1_ma: float = 0.0
    i_r2_ma: float = 0.0
    i_z_ma: float = 0.0
    p_r1_mw: float = 0.0
    p_r2_mw: float = 0.0
    p_z_mw: float = 0.0

    # Clamp voltages (nominal resistors)
    v_mcu_typ: float = 0.0
    v_mcu_worst_zener: float = 0.0

    # Safety margins (true worst case: tolerance + zener)
    v_mcu_worst: float = 0.0
    margin_rec_v: float = 0.0
    margin_abs_v: float = 0.0
    i_injection_ma: float = 0.0

    # ADC
    min_sample_cycles: float = 0.0
    resolution_mv_per_lsb: float = 0.0

    # Operating points: list of dicts with keys
    # v_in, v_mcu_l, v_mcu_h, requirement, status, color
    operating_points: list = field(default_factory=list)

    # For plot generation
    plot_data: dict = field(default_factory=dict)

    # Power rating margins (percentage, None if no rating)
    r1_margin_pct: Optional[float] = None
    r2_margin_pct: Optional[float] = None
    z_margin_pct: Optional[float] = None
    r1_rating_mw: Optional[float] = None
    r2_rating_mw: Optional[float] = None
    z_ptot_mw: float = 265.0


# ── Zener voltage model (backward-compat shim) ───────────────────────────────

def calculate_zener_voltage(iz_ma: float, zener: ZenerParams,
                            use_worst_case: bool = False) -> tuple[float, float]:
    """
    Calculate Zener clamp voltage at a given current.
    Returns (v_clamp, r_differential).

    Thin shim: delegates to ZenerClamp.voltage_at_current() for backward
    compatibility with existing callers and tests.
    """
    clamp = ZenerClamp.from_params(zener)
    return clamp.voltage_at_current(iz_ma, use_worst_case=use_worst_case)


# ── Iterative solver ─────────────────────────────────────────────────────────

def _solve_clamped_voltage(vin: float, r1: float, r2: float, k: float,
                           zener: ZenerParams, use_worst_zener: bool) -> float:
    """Solve for MCU node voltage at a given Vin using dampened iteration.
    Zener-only shim — existing callers and tests continue to use this path.
    For non-Zener clamps use _solve_clamped_voltage_clamp().
    """
    clamp = ZenerClamp.from_params(zener)
    v_div = vin * k
    vz_ref = zener.vz_max if use_worst_zener else zener.vz_nom
    vz_knee = vz_ref * (0.97 if use_worst_zener else 0.94)

    if v_div < vz_knee:
        return v_div

    v_node = vz_ref
    final_iz = 0.0
    for _ in range(15):
        i_r1 = (vin - v_node) / r1 * 1000
        i_r2 = v_node / r2 * 1000
        i_z = i_r1 - i_r2
        if i_z > 0:
            final_iz = i_z
            v_clamp, _ = clamp.voltage_at_current(i_z, use_worst_case=use_worst_zener)
            v_node = v_node * 0.3 + v_clamp * 0.7
        else:
            return v_div

    if final_iz < 0.5:
        return min(v_div, vz_ref)

    return max(vz_knee, min(v_div, v_node))


def _solve_clamped_voltage_clamp(vin: float, r1: float, r2: float, k: float,
                                 clamp: ClampModel, use_worst_case: bool,
                                 vz_ref: float, vdd: float = 3.3) -> float:
    """Solve for MCU node voltage using any ClampModel strategy."""
    v_div = vin * k
    vz_knee = vz_ref * 0.94 if not use_worst_case else vz_ref * 0.97

    if v_div < vz_knee:
        return v_div

    v_node = vz_ref
    final_iz = 0.0
    for _ in range(15):
        i_r1 = (vin - v_node) / r1 * 1000
        i_r2 = v_node / r2 * 1000
        i_z = i_r1 - i_r2
        if i_z > 0:
            final_iz = i_z
            v_clamp, _ = clamp.voltage_at_current(i_z, use_worst_case=use_worst_case, vdd=vdd)
            v_node = v_node * 0.3 + v_clamp * 0.7
        else:
            return v_div

    if final_iz < 0.5:
        return min(v_div, vz_ref)

    return max(vz_knee, min(v_div, v_node))


# ── ADC helper ───────────────────────────────────────────────────────────────

def get_min_sample_cycles(r_source_ohms: float) -> float:
    for threshold_ohms, cycles in ADC_SAMPLE_THRESHOLDS:
        if r_source_ohms <= threshold_ohms:
            return cycles
    return ADC_SAMPLE_DEFAULT


# ── Internal calculation engine ───────────────────────────────────────────────

def _run_calculation(resistors: ResistorParams, clamp: ClampModel,
                     mcu: McuParams, system: SystemParams,
                     vz_nom: float, vz_max: float,
                     ptot_mw: float) -> CalculationResult:
    """
    Core calculation engine shared by calculate_all() and calculate_with_clamp().
    Takes a ClampModel directly so any clamp type can be used.
    """
    r1 = resistors.r1_ohms
    r2 = resistors.r2_ohms
    rs = resistors.rs_ohms

    if r1 <= 0 or r2 <= 0:
        return CalculationResult()

    # Tolerance-shifted values
    r1_tol = resistors.r1_tol_pct / 100
    r2_tol = resistors.r2_tol_pct / 100
    r1_min = r1 * (1 - r1_tol)
    r1_max = r1 * (1 + r1_tol)
    r2_min = r2 * (1 - r2_tol)
    r2_max = r2 * (1 + r2_tol)

    # Basic divider
    r_total = r1 + r2
    k = r2 / r_total
    k_high = r2_max / (r1_min + r2_max)
    k_low = r2_min / (r1_max + r2_min)
    r_source = (r1 * r2) / r_total + rs

    vin_max = system.v_input_max
    vdd = mcu.vdd

    # Iterative clamp at max input — typical
    v_node_typ = vz_nom
    v_node_worst = vz_max
    v_divider_max = vin_max * k

    for _ in range(15):
        # Typical
        i_r1_t = (vin_max - v_node_typ) / r1 * 1000
        i_r2_t = v_node_typ / r2 * 1000
        i_z_t = i_r1_t - i_r2_t
        if i_z_t > 0:
            vc_t, _ = clamp.voltage_at_current(i_z_t, use_worst_case=False, vdd=vdd)
            v_node_typ = v_node_typ * 0.3 + vc_t * 0.7
        else:
            v_node_typ = v_divider_max
            break

        # Worst-case Zener (nominal resistors)
        i_r1_w = (vin_max - v_node_worst) / r1 * 1000
        i_r2_w = v_node_worst / r2 * 1000
        i_z_w = i_r1_w - i_r2_w
        if i_z_w > 0:
            vc_w, _ = clamp.voltage_at_current(i_z_w, use_worst_case=True, vdd=vdd)
            v_node_worst = v_node_worst * 0.3 + vc_w * 0.7
        else:
            v_node_worst = v_divider_max
            break

    # Final currents at typical
    i_r1_max = (vin_max - v_node_typ) / r1 * 1000
    i_r2_max = v_node_typ / r2 * 1000
    i_z_max = max(0.0, i_r1_max - i_r2_max)

    # Power
    p_r1 = (i_r1_max / 1000) ** 2 * r1 * 1000
    p_r2 = (i_r2_max / 1000) ** 2 * r2 * 1000
    p_z = v_node_typ * i_z_max
    p_total = p_r1 + p_r2 + p_z

    # Tolerance helpers using generic ClampModel solver
    def calc_v_mcu_low(vin):
        return _solve_clamped_voltage_clamp(
            vin, r1_max, r2_min, k_low, clamp, False, vz_nom, vdd)

    def calc_v_mcu_high(vin):
        return _solve_clamped_voltage_clamp(
            vin, r1_min, r2_max, k_high, clamp, True, vz_max, vdd)

    # Operating points
    v_rec_max = mcu.v_recommended_max
    v_abs_max = mcu.v_absolute_max
    v_analog_fs = system.v_analog_fullscale
    v_logic_high = system.v_logic_high_min
    v_logic_low = system.v_logic_low_max

    vil_max = vdd * 0.3
    vih_min = vdd * 0.7

    v_at_ll_l = calc_v_mcu_low(v_logic_low)
    v_at_ll_h = calc_v_mcu_high(v_logic_low)
    v_at_lh_l = calc_v_mcu_low(v_logic_high)
    v_at_lh_h = calc_v_mcu_high(v_logic_high)
    v_at_afs_l = calc_v_mcu_low(v_analog_fs)
    v_at_afs_h = calc_v_mcu_high(v_analog_fs)
    v_at_max_l = calc_v_mcu_low(vin_max)
    v_at_max_h = calc_v_mcu_high(vin_max)

    v_mcu_worst = v_at_max_h
    margin_rec = v_rec_max - v_mcu_worst
    margin_abs = v_abs_max - v_mcu_worst

    # Internal ESD diode only conducts when V_mcu exceeds VDD by the silicon
    # forward voltage threshold (~0.6V). Below that, no current flows through
    # the internal ESD path regardless of which external clamp is active.
    v_inj_threshold = vdd + INTERNAL_ESD_VF
    if v_mcu_worst > v_inj_threshold:
        i_inj = (v_mcu_worst - v_inj_threshold) / (rs + INTERNAL_ESD_R) * 1000
    else:
        i_inj = 0.0

    # Operating points table data
    op_points = [
        {"v_in": 0, "v_mcu_l": 0, "v_mcu_h": 0,
         "requirement": "--", "status": "Zero ref", "color": "gray60"},
        {"v_in": v_logic_low, "v_mcu_l": v_at_ll_l, "v_mcu_h": v_at_ll_h,
         "requirement": f"< VIL {vil_max:.2f}V",
         "status": "\u2713 PASS" if v_at_ll_h < vil_max else "\u2717 FAIL",
         "color": "green" if v_at_ll_h < vil_max else "red"},
        {"v_in": v_logic_high, "v_mcu_l": v_at_lh_l, "v_mcu_h": v_at_lh_h,
         "requirement": f"> VIH {vih_min:.2f}V",
         "status": "\u2713 PASS" if v_at_lh_l > vih_min else "\u2717 FAIL",
         "color": "green" if v_at_lh_l > vih_min else "red"},
        {"v_in": v_analog_fs, "v_mcu_l": v_at_afs_l, "v_mcu_h": v_at_afs_h,
         "requirement": f"\u2264 VDD {vdd:.2f}V",
         "status": ("\u2713 PASS" if v_at_afs_h <= vdd
                    else ("\u26a0 OVER" if v_at_afs_h <= v_rec_max else "\u2717 CLIP")),
         "color": ("green" if v_at_afs_h <= vdd
                   else ("orange" if v_at_afs_h <= v_rec_max else "red"))},
        {"v_in": vin_max, "v_mcu_l": v_at_max_l, "v_mcu_h": v_at_max_h,
         "requirement": f"\u2264 {v_abs_max:.1f}V abs",
         "status": "\u2713 PASS" if v_at_max_h <= v_abs_max else "\u2717 FAIL",
         "color": "green" if v_at_max_h <= v_abs_max else "red"},
    ]

    # Plot data (voltage arrays)
    import numpy as np
    v_in_arr = np.linspace(0, vin_max, 200)
    v_mcu_typ_arr = []
    v_mcu_worst_arr = []

    for vin in v_in_arr:
        v_div = vin * k
        v_n = vz_nom
        for _ in range(15):
            ir1 = (vin - v_n) / r1 * 1000
            ir2 = v_n / r2 * 1000
            iz = ir1 - ir2
            if iz > 0:
                vc, _ = clamp.voltage_at_current(iz, use_worst_case=False, vdd=vdd)
                v_n = v_n * 0.3 + vc * 0.7
            else:
                v_n = v_div
                break
        v_mcu_typ_arr.append(min(v_n, v_div))
        v_mcu_worst_arr.append(calc_v_mcu_high(vin))

    # Power rating margins
    r1_margin = None
    if resistors.r1_rating_mw is not None:
        r1_margin = (resistors.r1_rating_mw - p_r1) / resistors.r1_rating_mw * 100

    r2_margin = None
    if resistors.r2_rating_mw is not None:
        r2_margin = (resistors.r2_rating_mw - p_r2) / resistors.r2_rating_mw * 100

    z_margin = (ptot_mw - p_z) / ptot_mw * 100

    return CalculationResult(
        r_total_ohms=r_total,
        k_nominal=k,
        k_high=k_high,
        k_low=k_low,
        r_source_ohms=r_source,
        p_total_mw=p_total,
        i_r1_ma=i_r1_max,
        i_r2_ma=i_r2_max,
        i_z_ma=i_z_max,
        p_r1_mw=p_r1,
        p_r2_mw=p_r2,
        p_z_mw=p_z,
        v_mcu_typ=v_node_typ,
        v_mcu_worst_zener=v_node_worst,
        v_mcu_worst=v_mcu_worst,
        margin_rec_v=margin_rec,
        margin_abs_v=margin_abs,
        i_injection_ma=i_inj,
        min_sample_cycles=get_min_sample_cycles(r_source),
        resolution_mv_per_lsb=vdd / 4095 * 1000 / k,
        operating_points=op_points,
        plot_data={
            "v_in": v_in_arr,
            "v_mcu_typ": np.array(v_mcu_typ_arr),
            "v_mcu_worst": np.array(v_mcu_worst_arr),
            "vdd": vdd,
            "v_rec_max": v_rec_max,
            "v_abs_max": v_abs_max,
            "vin_max": vin_max,
        },
        r1_margin_pct=r1_margin,
        r2_margin_pct=r2_margin,
        z_margin_pct=z_margin,
        r1_rating_mw=resistors.r1_rating_mw,
        r2_rating_mw=resistors.r2_rating_mw,
        z_ptot_mw=ptot_mw,
    )


# ── Main calculation entry points ─────────────────────────────────────────────

def calculate_all(resistors: ResistorParams, zener: ZenerParams,
                  mcu: McuParams, system: SystemParams) -> CalculationResult:
    """
    Run the full divider + Zener clamp analysis. Returns a CalculationResult.

    This is the ORIGINAL entry point kept unchanged for backward compatibility.
    All 32 existing Zener tests call this with a ZenerParams positional argument.
    New multi-clamp code uses calculate_with_clamp() instead.
    Approach (b) from T7 task spec: keep calculate_all() Zener-only, add new entry
    point for other clamp types.
    """
    clamp = ZenerClamp.from_params(zener)
    return _run_calculation(
        resistors, clamp, mcu, system,
        vz_nom=zener.vz_nom, vz_max=zener.vz_max, ptot_mw=zener.ptot_mw
    )


def calculate_with_clamp(resistors: ResistorParams, clamp: ClampModel,
                         mcu: McuParams, system: SystemParams,
                         clamp_type: str = "zener",
                         vclamp_nom: float = 3.3,
                         vclamp_max: float = 3.5,
                         ptot_mw: float = 265.0) -> CalculationResult:
    """
    Run full divider + clamp analysis for any ClampModel strategy.

    Added in T7 for multi-clamp AppState support. The existing calculate_all()
    entry point remains unchanged (Zener-only, backward compatible).

    Parameters
    ----------
    resistors : ResistorParams
    clamp : ClampModel
        Any ClampModel instance (ZenerClamp, SchottkyClamp, TVSClamp, etc.)
    mcu : McuParams
    system : SystemParams
    clamp_type : str
        "zener" | "tvs" | "schottky" -- informational, does not change math.
    vclamp_nom : float
        Nominal clamp voltage for iteration seed / operating point checks.
    vclamp_max : float
        Worst-case clamp voltage for iteration seed.
    ptot_mw : float
        Power dissipation rating for margin calculation.
    """
    return _run_calculation(
        resistors, clamp, mcu, system,
        vz_nom=vclamp_nom, vz_max=vclamp_max, ptot_mw=ptot_mw
    )
