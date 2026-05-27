"""
Signal Bandwidth / Maximum PPS Analysis for protection networks.
Implements the RC low-pass filter model from the project documentation.

The protection network (R_source + clamp junction capacitance + MCU pin
capacitance) forms a first-order low-pass filter that limits the maximum
signal frequency the MCU pin can reliably detect.

R_source is the Thévenin source impedance seen by C_total at the protection
node = (R1 || R2) + R_series. Callers populate r_series_ohms with this
Thévenin value, NOT just the optional R_s component. (The param name is
retained for backward compatibility with existing tests.)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class BandwidthParams:
    # Thévenin source impedance (Ω): (R1 || R2) + R_series_optional.
    # Param name kept as r_series_ohms for backward compatibility.
    r_series_ohms: float = 100.0
    c_diode_pf: float = 95.0
    c_pin_pf: float = 10.0
    c_stray_pf: float = 3.0
    vil_v: float = 0.99
    vih_v: float = 2.31
    f_peripheral_mhz: float = 170.0
    n_samples: int = 3
    counter_bits: int = 16
    counter_signed: bool = False
    f_read_hz: float = 1000.0
    v_high: float = 3.3


@dataclass
class BandwidthResult:
    c_total_pf: float = 0.0
    tau_ns: float = 0.0
    f_3db_hz: float = 0.0
    t_rise_ns: float = 0.0
    t_undefined_rise_ns: float = 0.0
    t_undefined_fall_ns: float = 0.0
    f_max_analog_hz: float = 0.0
    f_max_practical_hz: float = 0.0
    f_max_digital_hz: float = 0.0
    f_max_overflow_hz: float = 0.0
    f_max_effective_hz: float = 0.0
    limiting_factor: str = ""


def calculate_bandwidth(params: BandwidthParams) -> BandwidthResult:
    """Run the full bandwidth / PPS analysis."""
    result = BandwidthResult()

    # Total capacitance
    c_total_pf = params.c_diode_pf + params.c_pin_pf + params.c_stray_pf
    c_total_f = c_total_pf * 1e-12
    r = params.r_series_ohms

    result.c_total_pf = c_total_pf

    if r <= 0 or c_total_f <= 0:
        return result

    # Time constant
    tau = r * c_total_f
    result.tau_ns = tau * 1e9

    # -3 dB bandwidth
    result.f_3db_hz = 1.0 / (2.0 * math.pi * tau)

    # 10-90% rise time
    result.t_rise_ns = 2.197 * tau * 1e9

    # Threshold crossing times
    v_high = params.v_high
    vil = params.vil_v
    vih = params.vih_v

    if v_high > 0 and vil < v_high and vih < v_high and vih > vil:
        # Time to cross VIL on rising edge
        t_vil = -tau * math.log(1.0 - vil / v_high)
        # Time to cross VIH on rising edge
        t_vih = -tau * math.log(1.0 - vih / v_high)

        # Undefined zone duration (rising edge)
        result.t_undefined_rise_ns = (t_vih - t_vil) * 1e9

        # Falling edge undefined zone
        if vil > 0:
            result.t_undefined_fall_ns = tau * math.log(vih / vil) * 1e9

        # Analog ceiling (conservative: 5*tau per half-period)
        result.f_max_analog_hz = 1.0 / (10.0 * tau)

        # Practical analog ceiling (signal must reach VIH within half-period)
        if t_vih > 0:
            result.f_max_practical_hz = 1.0 / (2.0 * t_vih)

        # Digital sampling limit
        t_undefined = max(result.t_undefined_rise_ns, result.t_undefined_fall_ns) * 1e-9
        f_periph = params.f_peripheral_mhz * 1e6
        if f_periph > 0:
            t_pulse_min = params.n_samples / f_periph
            t_half_min = t_undefined + t_pulse_min
            if t_half_min > 0:
                result.f_max_digital_hz = 1.0 / (2.0 * t_half_min)

    # Counter overflow limit
    bits = params.counter_bits - (1 if params.counter_signed else 0)
    if params.f_read_hz > 0:
        result.f_max_overflow_hz = (2 ** bits) * params.f_read_hz

    # Effective maximum
    limits = []
    labels = []
    if result.f_max_analog_hz > 0:
        limits.append(result.f_max_analog_hz)
        labels.append("Analog bandwidth (conservative)")
    if result.f_max_practical_hz > 0:
        limits.append(result.f_max_practical_hz)
        labels.append("Analog bandwidth (practical)")
    if result.f_max_digital_hz > 0:
        limits.append(result.f_max_digital_hz)
        labels.append("Digital sampling")
    if result.f_max_overflow_hz > 0:
        limits.append(result.f_max_overflow_hz)
        labels.append("Counter overflow")

    if limits:
        idx = limits.index(min(limits))
        result.f_max_effective_hz = limits[idx]
        result.limiting_factor = labels[idx]

    return result
