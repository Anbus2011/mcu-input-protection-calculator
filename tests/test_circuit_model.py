"""
Test suite for the circuit calculation engine.
Run with: python -m pytest tests/ -v
"""
import math
import pytest

from src.models.circuit_model import (
    calculate_all, calculate_zener_voltage, get_min_sample_cycles,
    ResistorParams, ZenerParams, McuParams, SystemParams,
)


# ── Zener voltage model ──────────────────────────────────────────────────────

class TestZenerVoltage:
    """Verify the three-region Zener V-I model."""

    def setup_method(self):
        # BZB984-C3V3 parameters
        self.z = ZenerParams(
            vz_nom=3.3, vz_min=3.1, vz_max=3.5,
            izt_ma=5.0, izk_ma=1.0,
            zzt_typ=85.0, zzt_max=95.0,
            zzk_typ=350.0, zzk_max=600.0,
            ptot_mw=265.0,
        )

    def test_zero_current(self):
        """At zero current, voltage should be near knee voltage."""
        v, r = calculate_zener_voltage(0, self.z, False)
        # Typical knee = 0.94 * 3.3 = 3.102
        assert abs(v - 3.102) < 0.01
        assert r == self.z.zzk_typ

    def test_below_knee_current(self):
        """Below IZK, voltage rises gently from ~97% to 100% of knee."""
        v, r = calculate_zener_voltage(0.5, self.z, False)
        vz_knee = 3.3 * 0.94  # 3.102
        assert vz_knee * 0.97 < v < vz_knee * 1.01
        assert r == self.z.zzk_typ

    def test_at_knee_current(self):
        """At exactly IZK, voltage should equal knee voltage."""
        v, r = calculate_zener_voltage(1.0, self.z, False)
        vz_knee = 3.3 * 0.94
        assert abs(v - vz_knee) < 0.01

    def test_between_knee_and_test(self):
        """Between IZK and IZT, voltage interpolates linearly."""
        v, r = calculate_zener_voltage(3.0, self.z, False)
        # 3 mA is halfway between 1 and 5 mA -> halfway between knee and nom
        vz_knee = 3.3 * 0.94
        expected = vz_knee + (3.3 - vz_knee) * 0.5
        assert abs(v - expected) < 0.01

    def test_at_test_current(self):
        """At IZT, voltage should equal VZ_nom (typical) or VZ_max (worst)."""
        v_typ, _ = calculate_zener_voltage(5.0, self.z, False)
        v_wc, _ = calculate_zener_voltage(5.0, self.z, True)
        assert abs(v_typ - 3.3) < 0.01
        assert abs(v_wc - 3.5) < 0.01

    def test_above_test_current(self):
        """Above IZT, voltage extrapolates with ZZT slope."""
        v, r = calculate_zener_voltage(10.0, self.z, False)
        # v = 3.3 + (10 - 5) * 85 / 1000 = 3.3 + 0.425 = 3.725
        expected = 3.3 + 5.0 * 85.0 / 1000
        assert abs(v - expected) < 0.01
        assert r == self.z.zzt_typ

    def test_worst_case_higher_than_typical(self):
        """Worst-case voltage should always be >= typical at same current."""
        for i in [0.5, 1.0, 3.0, 5.0, 10.0]:
            v_typ, _ = calculate_zener_voltage(i, self.z, False)
            v_wc, _ = calculate_zener_voltage(i, self.z, True)
            assert v_wc >= v_typ, f"At {i} mA: worst {v_wc} < typical {v_typ}"


# ── ADC sample cycles ────────────────────────────────────────────────────────

class TestAdcSampleCycles:
    def test_low_impedance(self):
        assert get_min_sample_cycles(500) == 2.5

    def test_mid_impedance(self):
        assert get_min_sample_cycles(5000) == 6.5
        assert get_min_sample_cycles(10000) == 12.5

    def test_high_impedance(self):
        assert get_min_sample_cycles(50000) == 247.5

    def test_boundary_values(self):
        assert get_min_sample_cycles(1000) == 2.5
        assert get_min_sample_cycles(1001) == 6.5


# ── Full calculation with known values ────────────────────────────────────────

class TestFullCalculation:
    """Test calculate_all with known component values and verify results."""

    def setup_method(self):
        # Default 10k/18k divider, BZB984-C3V3
        self.resistors = ResistorParams(
            r1_ohms=10000, r2_ohms=18000, rs_ohms=0,
            r1_tol_pct=1.0, r2_tol_pct=1.0,
            r1_rating_mw=200, r2_rating_mw=100,
        )
        self.zener = ZenerParams(
            vz_nom=3.3, vz_min=3.1, vz_max=3.5,
            izt_ma=5.0, izk_ma=1.0,
            zzt_typ=85.0, zzt_max=95.0,
            zzk_typ=350.0, zzk_max=600.0,
            ptot_mw=265.0,
        )
        self.mcu = McuParams(vdd=3.3, v_recommended_max=3.6,
                             v_absolute_max=4.0, safe_injection_ma=1.0,
                             adc_bits=12, vil_factor=0.3, vih_factor=0.7)
        self.system = SystemParams(v_input_max=30, v_analog_fullscale=5.1,
                                   v_logic_high_min=3.8, v_logic_low_max=1.0)

    def test_divider_ratio(self):
        r = calculate_all(self.resistors, self.zener, self.mcu, self.system)
        # k = 18000 / (10000 + 18000) = 0.6429
        assert abs(r.k_nominal - 18000 / 28000) < 0.0001

    def test_input_impedance(self):
        r = calculate_all(self.resistors, self.zener, self.mcu, self.system)
        assert abs(r.r_total_ohms - 28000) < 1

    def test_source_impedance(self):
        r = calculate_all(self.resistors, self.zener, self.mcu, self.system)
        # R1||R2 + Rs = (10000*18000)/(10000+18000) + 0 = 6428.57
        expected = (10000 * 18000) / 28000
        assert abs(r.r_source_ohms - expected) < 1

    def test_tolerance_ratios(self):
        r = calculate_all(self.resistors, self.zener, self.mcu, self.system)
        # k_high = R2_max / (R1_min + R2_max) > k_nominal
        # k_low  = R2_min / (R1_max + R2_min) < k_nominal
        assert r.k_high > r.k_nominal
        assert r.k_low < r.k_nominal

    def test_vmcu_typical_is_clamped(self):
        """At 30V input, Zener should clamp V_mcu well below divider voltage."""
        r = calculate_all(self.resistors, self.zener, self.mcu, self.system)
        v_divider = 30 * r.k_nominal  # ~19.3V unclamped
        assert r.v_mcu_typ < v_divider
        assert r.v_mcu_typ < 4.0  # must be near Zener voltage

    def test_vmcu_worst_greater_than_typical(self):
        r = calculate_all(self.resistors, self.zener, self.mcu, self.system)
        assert r.v_mcu_worst >= r.v_mcu_typ

    def test_vmcu_typical_near_zener(self):
        """Typical V_mcu should be close to VZ_nom at max input."""
        r = calculate_all(self.resistors, self.zener, self.mcu, self.system)
        assert abs(r.v_mcu_typ - 3.3) < 0.3

    def test_safety_margins(self):
        r = calculate_all(self.resistors, self.zener, self.mcu, self.system)
        # margin = limit - v_mcu_worst
        assert abs(r.margin_rec_v - (3.6 - r.v_mcu_worst)) < 0.001
        assert abs(r.margin_abs_v - (4.0 - r.v_mcu_worst)) < 0.001

    def test_power_positive(self):
        r = calculate_all(self.resistors, self.zener, self.mcu, self.system)
        assert r.p_r1_mw > 0
        assert r.p_r2_mw > 0
        assert r.p_z_mw >= 0
        assert r.p_total_mw > 0

    def test_power_sum(self):
        """Total power should equal sum of component powers."""
        r = calculate_all(self.resistors, self.zener, self.mcu, self.system)
        assert abs(r.p_total_mw - (r.p_r1_mw + r.p_r2_mw + r.p_z_mw)) < 0.1

    def test_current_balance(self):
        """I_R1 = I_R2 + I_Z (Kirchhoff's current law at the node)."""
        r = calculate_all(self.resistors, self.zener, self.mcu, self.system)
        assert abs(r.i_r1_ma - (r.i_r2_ma + r.i_z_ma)) < 0.01

    def test_power_margins(self):
        r = calculate_all(self.resistors, self.zener, self.mcu, self.system)
        # R1: 200 mW rating
        assert r.r1_margin_pct is not None
        assert r.r1_margin_pct == pytest.approx(
            (200 - r.p_r1_mw) / 200 * 100, abs=0.1)
        # R2: 100 mW rating
        assert r.r2_margin_pct is not None

    def test_operating_points_count(self):
        r = calculate_all(self.resistors, self.zener, self.mcu, self.system)
        assert len(r.operating_points) == 5

    def test_operating_point_zero(self):
        r = calculate_all(self.resistors, self.zener, self.mcu, self.system)
        op0 = r.operating_points[0]
        assert op0["v_in"] == 0
        assert op0["v_mcu_l"] == 0
        assert op0["v_mcu_h"] == 0

    def test_operating_point_monotonic(self):
        """V_mcu should increase (or stay flat) as V_in increases."""
        r = calculate_all(self.resistors, self.zener, self.mcu, self.system)
        prev_h = 0
        for op in r.operating_points:
            assert op["v_mcu_h"] >= prev_h - 0.001
            prev_h = op["v_mcu_h"]

    def test_plot_data_present(self):
        r = calculate_all(self.resistors, self.zener, self.mcu, self.system)
        assert "v_in" in r.plot_data
        assert "v_mcu_typ" in r.plot_data
        assert "v_mcu_worst" in r.plot_data
        assert len(r.plot_data["v_in"]) == 200

    def test_resolution(self):
        """Rewritten for bug 10: resolution is VREF / 2^N (was VDD / 4095)."""
        r = calculate_all(self.resistors, self.zener, self.mcu, self.system)
        # resolution = VREF / 2^12 * 1000 / k, VREF = VDD
        expected = 3.3 / 4096 * 1000 / r.k_nominal
        assert abs(r.resolution_mv_per_lsb - expected) < 1e-9


# ── results.div cross-check ──────────────────────────────────────────────────

class TestResultsDivFile:
    """Verify calculations match expected values for the shipped results.div."""

    def setup_method(self):
        # 8.2k / 29k divider from results.div
        self.resistors = ResistorParams(
            r1_ohms=8200, r2_ohms=29000, rs_ohms=0,
            r1_tol_pct=1.0, r2_tol_pct=1.0,
            r1_rating_mw=200, r2_rating_mw=63,
        )
        self.zener = ZenerParams(
            vz_nom=3.3, vz_min=3.1, vz_max=3.5,
            izt_ma=5.0, izk_ma=1.0,
            zzt_typ=85.0, zzt_max=95.0,
            zzk_typ=350.0, zzk_max=600.0,
            ptot_mw=265.0,
        )
        self.mcu = McuParams(vdd=3.3, v_recommended_max=3.6,
                             v_absolute_max=4.0, safe_injection_ma=2.0)
        self.system = SystemParams(v_input_max=30, v_analog_fullscale=4.1,
                                   v_logic_high_min=3.0, v_logic_low_max=1.0)

    def test_divider_ratio(self):
        r = calculate_all(self.resistors, self.zener, self.mcu, self.system)
        expected = 29000 / (8200 + 29000)
        assert abs(r.k_nominal - expected) < 0.0001

    def test_vmcu_below_abs_max(self):
        """V_mcu worst case must stay below absolute max for a valid design."""
        r = calculate_all(self.resistors, self.zener, self.mcu, self.system)
        assert r.v_mcu_worst < self.mcu.v_absolute_max

    def test_vmcu_worst_near_zener_max(self):
        """With 30V input and 3.5V max Zener, worst case should be near 3.5V."""
        r = calculate_all(self.resistors, self.zener, self.mcu, self.system)
        assert 3.0 < r.v_mcu_worst < 4.0

    def test_positive_margins(self):
        """The shipped design should pass all safety checks."""
        r = calculate_all(self.resistors, self.zener, self.mcu, self.system)
        assert r.margin_abs_v > 0, f"Abs margin {r.margin_abs_v} <= 0"


# ── Edge cases ────────────────────────────────────────────────────────────────

C3V3 = dict(vz_nom=3.3, vz_min=3.1, vz_max=3.5, izt_ma=5.0, izk_ma=1.0,
            zzt_typ=85.0, zzt_max=95.0, zzk_typ=350.0, zzk_max=600.0, ptot_mw=265.0)


class TestEdgeCases:
    def test_zero_resistors_returns_empty(self):
        """R1=0 or R2=0 should return an empty result without crashing.
        (Rewritten for bug 4: results used to be zeros, which the screen
        showed as real values; they are now None = 'needs input'.)"""
        r = calculate_all(
            ResistorParams(r1_ohms=0, r2_ohms=18000),
            ZenerParams(), McuParams(), SystemParams(),
        )
        assert r.k_nominal is None
        assert "resistors.r1_ohms" in r.missing["divider"]

    def test_no_zener_clamping_at_low_voltage(self):
        """At 1V input, divider output is well below Zener — no clamping.
        (Rewritten for bug 5: the Zener used to get IZT/IZK/ZZT from hidden
        dataclass defaults; they are now given explicitly.)"""
        res = ResistorParams(r1_ohms=10000, r2_ohms=10000)
        z = ZenerParams(**C3V3)
        mcu = McuParams(vdd=3.3)
        sys = SystemParams(v_input_max=1.0)
        r = calculate_all(res, z, mcu, sys)
        # V_mcu should equal divider voltage (0.5V), not clamped
        assert abs(r.v_mcu_typ - 0.5) < 0.05

    def test_high_series_resistance(self):
        """R_series should add to source impedance."""
        r1 = calculate_all(
            ResistorParams(r1_ohms=10000, r2_ohms=10000, rs_ohms=0),
            ZenerParams(), McuParams(), SystemParams(),
        )
        r2 = calculate_all(
            ResistorParams(r1_ohms=10000, r2_ohms=10000, rs_ohms=1000),
            ZenerParams(), McuParams(), SystemParams(),
        )
        assert abs(r2.r_source_ohms - r1.r_source_ohms - 1000) < 1
