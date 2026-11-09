"""
Signal Bandwidth / Maximum PPS Analysis for protection networks.
Implements the RC low-pass filter model from the project documentation.

The protection network (Thevenin resistance R1||R2 + R_series driving the
Zener junction capacitance + MCU pin capacitance + stray capacitance) forms a
first-order low-pass filter that limits the maximum signal frequency the MCU
pin can reliably detect.

Every input may be None. An output is computed only when all of its inputs
are present; otherwise it stays None and its missing inputs are listed in
``BandwidthResult.missing``. When an output can't be computed for a reason
other than a missing input (for example the pin never reaches VIH), the
reason is in ``BandwidthResult.blocked``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BandwidthParams:
    # Resistance driving the pin capacitance: R1||R2 + R_series (ohms)
    r_tau_ohms: Optional[float] = None
    c_diode_pf: Optional[float] = None
    c_pin_pf: Optional[float] = None
    c_stray_pf: Optional[float] = None
    # Pin thresholds (V) and the settled high level at the pin (V)
    vil_v: Optional[float] = None
    vih_v: Optional[float] = None
    v_high: Optional[float] = None
    f_peripheral_mhz: Optional[float] = None
    n_samples: Optional[int] = None
    counter_bits: Optional[int] = None
    counter_signed: Optional[bool] = None
    f_read_hz: Optional[float] = None


@dataclass
class BandwidthResult:
    c_total_pf: Optional[float] = None
    tau_ns: Optional[float] = None
    f_3db_hz: Optional[float] = None
    t_rise_ns: Optional[float] = None
    t_undefined_rise_ns: Optional[float] = None
    t_undefined_fall_ns: Optional[float] = None
    f_max_analog_hz: Optional[float] = None
    f_max_practical_hz: Optional[float] = None
    f_max_digital_hz: Optional[float] = None
    f_max_overflow_hz: Optional[float] = None
    f_max_effective_hz: Optional[float] = None
    limiting_factor: Optional[str] = None
    # output key -> list of missing BandwidthParams field names
    missing: dict = field(default_factory=dict)
    # output key -> reason text (not a missing input)
    blocked: dict = field(default_factory=dict)


def _num(x):
    if x is None or isinstance(x, bool):
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def calculate_bandwidth(params: BandwidthParams) -> BandwidthResult:
    """Run the full bandwidth / PPS analysis."""
    res = BandwidthResult()
    p = {
        "r_tau_ohms": _num(params.r_tau_ohms),
        "c_diode_pf": _num(params.c_diode_pf),
        "c_pin_pf": _num(params.c_pin_pf),
        "c_stray_pf": _num(params.c_stray_pf),
        "vil_v": _num(params.vil_v),
        "vih_v": _num(params.vih_v),
        "v_high": _num(params.v_high),
        "f_peripheral_mhz": _num(params.f_peripheral_mhz),
        "n_samples": _num(params.n_samples),
        "counter_bits": _num(params.counter_bits),
        "counter_signed": params.counter_signed if isinstance(params.counter_signed, bool) else None,
        "f_read_hz": _num(params.f_read_hz),
    }
    # Range guards: anything unusable is treated as missing.
    for k in ("c_diode_pf", "c_pin_pf", "c_stray_pf", "n_samples"):
        if p[k] is not None and p[k] < 0:
            p[k] = None
    for k in ("r_tau_ohms", "f_peripheral_mhz", "f_read_hz", "counter_bits"):
        if p[k] is not None and p[k] <= 0:
            p[k] = None

    def need(key, *names, deps=()):
        miss = []
        for d in deps:
            for n in res.missing.get(d, []):
                if n not in miss:
                    miss.append(n)
        for n in names:
            if p[n] is None and n not in miss:
                miss.append(n)
        blocked = next((res.blocked[d] for d in deps if d in res.blocked), None)
        if miss:
            res.missing[key] = miss
            return False
        if blocked:
            res.blocked[key] = blocked
            return False
        return True

    # Total capacitance
    if need("c_total", "c_diode_pf", "c_pin_pf", "c_stray_pf"):
        res.c_total_pf = p["c_diode_pf"] + p["c_pin_pf"] + p["c_stray_pf"]
        if res.c_total_pf <= 0:
            res.blocked["c_total_ok"] = "C_total is 0"

    tau = None
    if need("tau", "r_tau_ohms", deps=("c_total", "c_total_ok")):
        tau = p["r_tau_ohms"] * res.c_total_pf * 1e-12
        res.tau_ns = tau * 1e9
        res.f_3db_hz = 1.0 / (2.0 * math.pi * tau)       # -3 dB bandwidth
        res.t_rise_ns = 2.197 * tau * 1e9                  # 10-90 % rise time
        res.f_max_analog_hz = 1.0 / (10.0 * tau)          # 99 % swing per half period
    for k in ("f_3db", "t_rise", "analog"):
        need(k, deps=("tau",))

    # Threshold crossing (rising edge from 0 V towards V_high)
    t_vih = None
    if need("thresholds", "vil_v", "vih_v", "v_high", deps=("tau",)):
        vil, vih, v_high = p["vil_v"], p["vih_v"], p["v_high"]
        if not (0 < vil < vih):
            res.blocked["thresholds"] = "VIL must be above 0 and below VIH"
        elif v_high <= vih:
            res.blocked["thresholds"] = (
                f"V_high {v_high:.3f} V never reaches VIH {vih:.3f} V")
        else:
            t_vil = -tau * math.log(1.0 - vil / v_high)
            t_vih = -tau * math.log(1.0 - vih / v_high)
            res.t_undefined_rise_ns = (t_vih - t_vil) * 1e9
            res.t_undefined_fall_ns = tau * math.log(vih / vil) * 1e9
            res.f_max_practical_hz = 1.0 / (2.0 * t_vih)
    for k in ("t_undefined_rise", "t_undefined_fall", "practical"):
        need(k, deps=("thresholds",))

    # Digital sampling limit
    if need("digital", "f_peripheral_mhz", "n_samples", deps=("thresholds",)):
        t_undefined = max(res.t_undefined_rise_ns, res.t_undefined_fall_ns) * 1e-9
        t_pulse_min = p["n_samples"] / (p["f_peripheral_mhz"] * 1e6)
        t_half_min = t_undefined + t_pulse_min
        if t_half_min > 0:
            res.f_max_digital_hz = 1.0 / (2.0 * t_half_min)
        else:
            res.blocked["digital"] = "undefined zone and N_samples are both 0"

    # Counter overflow limit: 2^N unsigned, 2^(N-1) signed
    if need("overflow", "counter_bits", "counter_signed", "f_read_hz"):
        bits = int(p["counter_bits"]) - (1 if p["counter_signed"] else 0)
        res.f_max_overflow_hz = (2 ** bits) * p["f_read_hz"]

    # Effective maximum: only when every limit is known
    if need("effective", deps=("analog", "practical", "digital", "overflow")):
        limits = [
            (res.f_max_analog_hz, "Analog bandwidth (conservative)"),
            (res.f_max_practical_hz, "Analog bandwidth (practical)"),
            (res.f_max_digital_hz, "Digital sampling"),
            (res.f_max_overflow_hz, "Counter overflow"),
        ]
        value, label = min(limits, key=lambda t: t[0])
        res.f_max_effective_hz = value
        res.limiting_factor = label

    return res
