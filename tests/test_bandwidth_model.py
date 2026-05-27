"""
Test suite for the bandwidth / PPS analysis engine.
Run with: python -m pytest tests/ -v
"""
import math
import pytest

from src.models.bandwidth_model import BandwidthParams, BandwidthResult, calculate_bandwidth


class TestRcFilterBasics:
    """Verify RC filter calculations against hand-computed values."""

    def setup_method(self):
        # 100 ohm, 108 pF total (95 + 10 + 3)
        self.params = BandwidthParams(
            r_series_ohms=100, c_diode_pf=95, c_pin_pf=10, c_stray_pf=3,
            vil_v=0.99, vih_v=2.31, v_high=3.3,
            f_peripheral_mhz=170, n_samples=3,
            counter_bits=16, counter_signed=False, f_read_hz=1000,
        )

    def test_total_capacitance(self):
        r = calculate_bandwidth(self.params)
        assert abs(r.c_total_pf - 108.0) < 0.1

    def test_time_constant(self):
        r = calculate_bandwidth(self.params)
        # tau = 100 * 108e-12 = 10.8e-9 = 10.8 ns
        assert abs(r.tau_ns - 10.8) < 0.1

    def test_3db_bandwidth(self):
        r = calculate_bandwidth(self.params)
        # f_3db = 1 / (2*pi*tau) = 1 / (2*pi*10.8e-9)
        expected = 1.0 / (2 * math.pi * 10.8e-9)
        assert abs(r.f_3db_hz - expected) / expected < 0.01

    def test_rise_time(self):
        r = calculate_bandwidth(self.params)
        # t_rise = 2.197 * tau = 2.197 * 10.8 = 23.73 ns
        expected = 2.197 * 10.8
        assert abs(r.t_rise_ns - expected) < 0.1

    def test_analog_conservative(self):
        r = calculate_bandwidth(self.params)
        # f_max = 1 / (10 * tau)
        tau = 100 * 108e-12
        expected = 1.0 / (10 * tau)
        assert abs(r.f_max_analog_hz - expected) / expected < 0.01


class TestThresholdTiming:
    def setup_method(self):
        self.params = BandwidthParams(
            r_series_ohms=100, c_diode_pf=95, c_pin_pf=10, c_stray_pf=3,
            vil_v=0.99, vih_v=2.31, v_high=3.3,
            f_peripheral_mhz=170, n_samples=3,
            counter_bits=16, counter_signed=False, f_read_hz=1000,
        )

    def test_undefined_zone_positive(self):
        """Undefined zone durations must be positive."""
        r = calculate_bandwidth(self.params)
        assert r.t_undefined_rise_ns > 0
        assert r.t_undefined_fall_ns > 0

    def test_rising_formula(self):
        """Verify rising edge undefined zone: tau * ln((Vh - VIL)/(Vh - VIH))."""
        r = calculate_bandwidth(self.params)
        tau = 100 * 108e-12
        expected = tau * math.log((3.3 - 0.99) / (3.3 - 2.31)) * 1e9
        assert abs(r.t_undefined_rise_ns - expected) < 0.01

    def test_falling_formula(self):
        """Verify falling edge undefined zone: tau * ln(VIH / VIL)."""
        r = calculate_bandwidth(self.params)
        tau = 100 * 108e-12
        expected = tau * math.log(2.31 / 0.99) * 1e9
        assert abs(r.t_undefined_fall_ns - expected) < 0.01


class TestFrequencyLimits:
    def setup_method(self):
        self.params = BandwidthParams(
            r_series_ohms=100, c_diode_pf=95, c_pin_pf=10, c_stray_pf=3,
            vil_v=0.99, vih_v=2.31, v_high=3.3,
            f_peripheral_mhz=170, n_samples=3,
            counter_bits=16, counter_signed=False, f_read_hz=1000,
        )

    def test_all_limits_positive(self):
        r = calculate_bandwidth(self.params)
        assert r.f_max_analog_hz > 0
        assert r.f_max_practical_hz > 0
        assert r.f_max_digital_hz > 0
        assert r.f_max_overflow_hz > 0

    def test_conservative_less_than_practical(self):
        """Conservative analog limit should be lower than practical."""
        r = calculate_bandwidth(self.params)
        assert r.f_max_analog_hz < r.f_max_practical_hz

    def test_effective_is_minimum(self):
        """Effective limit should equal the minimum of all limits."""
        r = calculate_bandwidth(self.params)
        all_limits = [r.f_max_analog_hz, r.f_max_practical_hz,
                      r.f_max_digital_hz, r.f_max_overflow_hz]
        assert abs(r.f_max_effective_hz - min(all_limits)) < 1

    def test_limiting_factor_identified(self):
        r = calculate_bandwidth(self.params)
        assert r.limiting_factor != ""

    def test_counter_overflow_unsigned(self):
        """Unsigned 16-bit at 1kHz read: 2^16 * 1000 = 65,536,000."""
        r = calculate_bandwidth(self.params)
        assert abs(r.f_max_overflow_hz - 65536000) < 1

    def test_counter_overflow_signed(self):
        """Signed 16-bit at 1kHz read: 2^15 * 1000 = 32,768,000."""
        p = BandwidthParams(
            r_series_ohms=100, c_diode_pf=95, c_pin_pf=10, c_stray_pf=3,
            vil_v=0.99, vih_v=2.31, v_high=3.3,
            f_peripheral_mhz=170, n_samples=3,
            counter_bits=16, counter_signed=True, f_read_hz=1000,
        )
        r = calculate_bandwidth(p)
        assert abs(r.f_max_overflow_hz - 32768000) < 1


class TestEdgeCases:
    def test_zero_resistance(self):
        """Zero resistance should return safely without division by zero."""
        p = BandwidthParams(r_series_ohms=0)
        r = calculate_bandwidth(p)
        assert r.tau_ns == 0

    def test_zero_capacitance(self):
        p = BandwidthParams(c_diode_pf=0, c_pin_pf=0, c_stray_pf=0)
        r = calculate_bandwidth(p)
        assert r.c_total_pf == 0

    def test_invalid_thresholds_no_crash(self):
        """VIH > V_high should not crash."""
        p = BandwidthParams(
            r_series_ohms=100, c_diode_pf=100, c_pin_pf=10, c_stray_pf=0,
            vil_v=1.0, vih_v=5.0, v_high=3.3,
        )
        r = calculate_bandwidth(p)
        # Should still compute tau and f_3db
        assert r.tau_ns > 0


class TestRSourceThevenin:
    """Regression: callers MUST pass Thévenin source impedance, not just R_s.

    With R1=10k, R2=18k, R_s=0 the protection-node Thévenin source impedance
    is (10k || 18k) + 0 = 6428.57 Ω — NOT 0. Passing 0 makes every output
    blank (the user-visible '--' bug)."""

    def test_user_default_topology_produces_nonempty_result(self):
        """R1=10k, R2=18k, R_s=0, BAT54CV caps → must produce real numbers."""
        r_thev = (10000 * 18000) / (10000 + 18000)  # ≈ 6428.57
        p = BandwidthParams(
            r_series_ohms=r_thev,
            c_diode_pf=10, c_pin_pf=5, c_stray_pf=3,   # BAT54CV + STM32G4
            vil_v=0.99, vih_v=2.31, v_high=3.3,
            f_peripheral_mhz=170, n_samples=4,
            counter_bits=16, counter_signed=False, f_read_hz=1000,
        )
        r = calculate_bandwidth(p)
        # tau = 6428 × 18e-12 ≈ 115.7 ns
        assert r.tau_ns == pytest.approx(115.7, abs=0.5)
        # f_3db = 1/(2π·τ) ≈ 1.376 MHz
        assert r.f_3db_hz == pytest.approx(1.376e6, rel=0.01)
        # all four limits must be > 0 (none blank)
        assert r.f_max_analog_hz > 0
        assert r.f_max_practical_hz > 0
        assert r.f_max_digital_hz > 0
        assert r.f_max_overflow_hz > 0
        assert r.f_max_effective_hz > 0
        assert r.limiting_factor != ""

    def test_passing_zero_r_returns_empty_result(self):
        """Passing only R_s=0 (the bug condition) must return empty — this
        documents WHY the UI must compute Thévenin before passing."""
        p = BandwidthParams(
            r_series_ohms=0,   # ← bug: caller forgot R1||R2
            c_diode_pf=10, c_pin_pf=5, c_stray_pf=3,
        )
        r = calculate_bandwidth(p)
        # Documented behavior — all bandwidth outputs blank.
        assert r.tau_ns == 0
        assert r.f_3db_hz == 0
        assert r.f_max_effective_hz == 0
