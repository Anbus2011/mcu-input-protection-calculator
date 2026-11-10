"""
Test suite for the frequency limits (ported from the tests of the old
bandwidth_model.py to the clamp-diode solver).
Run with: python -m pytest tests/ -v
"""
import math

import pytest

from src.models.clamp_solver import solve
from tests.designs import schottky_rail


def design(**overrides):
    """Rail Schottky, resistors at 0 % so R max is the nominal value:
    R1 || R2 = 6428.57 ohm, C = 10 + 5 + 3 = 18 pF."""
    base = dict(resistors__r1__tolerance_pct=0, resistors__r2__tolerance_pct=0)
    base.update(overrides)
    return schottky_rail(**base)


R_TAU = 10000 * 18000 / 28000
TAU_NS = R_TAU * 18e-12 * 1e9


class TestRcFilterBasics:
    """Verify RC filter calculations against hand-computed values."""

    def setup_method(self):
        self.d = solve(design())["details"]

    def test_total_capacitance(self):
        assert abs(self.d["c_total_pf"] - 18.0) < 0.1

    def test_time_constant(self):
        # tau = 6428.57 * 18e-12 = 115.7 ns
        assert abs(self.d["tau_ns"] - 115.71) < 0.1
        assert self.d["tau_ns"] == pytest.approx(TAU_NS)


class TestEdgeTiming:
    """The rising and the falling edge time."""

    def setup_method(self):
        self.r = solve(design())
        self.d = self.r["details"]
        self.levels = self.r["voltages"]["levels"]

    def test_edge_times_positive(self):
        assert self.d["t_rise_ns"] > 0
        assert self.d["t_fall_ns"] > 0

    def test_rising_formula(self):
        """Rising edge: from 0 V towards the lowest pin voltage at Logic High,
        to VIH: tau * ln(B / (B - VIH))."""
        b = self.levels["logic_high"]["low"]
        expected = TAU_NS * math.log(b / (b - 2.31))
        assert abs(self.d["t_rise_ns"] - expected) < 0.01

    def test_falling_formula(self):
        """Falling edge: from the highest pin voltage at Max Input towards
        the highest at Logic Low, to VIL: tau * ln((A - B) / (VIL - B))."""
        a, b = self.levels["max_input"]["high"], self.levels["logic_low"]["high"]
        expected = TAU_NS * math.log((a - b) / (0.99 - b))
        assert abs(self.d["t_fall_ns"] - expected) < 0.01


class TestFrequencyLimits:
    def setup_method(self):
        self.d = solve(design())["details"]

    def test_both_limits_positive(self):
        """The two limits: "may work up to" and "reliable up to"."""
        assert self.d["f_may_work_hz"] > 0
        assert self.d["f_reliable_hz"] > 0

    def test_reliable_not_above_may_work(self):
        """The "reliable" limit is "may work" divided by the margin factor
        (1.5)."""
        assert self.d["f_reliable_hz"] < self.d["f_may_work_hz"]
        assert self.d["f_reliable_hz"] == pytest.approx(self.d["f_may_work_hz"] / 1.5)

    def test_edge_time_is_the_larger_of_the_two(self):
        """t_edge is the larger of the two edge times, and "may work up to"
        is 1 / (2 x (t_edge + minimum pulse width))."""
        d = self.d
        assert d["t_edge_ns"] == max(d["t_rise_ns"], d["t_fall_ns"])
        assert d["f_may_work_hz"] == pytest.approx(
            1 / (2 * (d["t_edge_ns"] + 17.65) * 1e-9))


class TestEdgeCases:
    def test_zero_resistance(self):
        """An unusable R1 leaves tau not computable, without division by zero."""
        r = solve(design(resistors__r1__value=0))
        assert r["details"]["tau_ns"] is None
        assert "resistors.r1.value" in r["missing"]["tau"]

    def test_zero_capacitance(self):
        r = solve(design(clamp_diode__capacitance_pf=0, mcu__c_pin_pf=0,
                         bandwidth__c_stray_pf=0))
        assert r["details"]["c_total_pf"] == 0

    def test_invalid_thresholds_no_crash(self):
        """VIH above the pin's high level should not crash."""
        r = solve(design(mcu__vih_factor=0.95))
        # Should still compute tau
        assert r["details"]["tau_ns"] > 0
        assert r["details"]["f_may_work_hz"] is None
