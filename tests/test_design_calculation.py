"""
Test suite for the design calculation (ported from the tests of the old
circuit_model.py to the clamp-diode solver).
Run with: python -m pytest tests/ -v
"""
import math

import pytest

from src.models import clamp_solver
from src.models.clamp_solver import solve
from tests.designs import KOHM, app_state, change, zener_reference


def curve(column="typ"):
    """The C3V3 reverse table as the solver holds it: [(volts, ln amps)]."""
    c = clamp_solver.prepare(zener_reference())
    return c.v[clamp_solver.CURVE[column]]["reverse"]


def current_ma(volts, column="typ"):
    return clamp_solver._curve_current(curve(column), volts) * 1000


# ── Diode table model (rewritten: was the three-region Zener model) ──────────

class TestDiodeCurve:
    """Verify the table model: ln(current) linear in voltage between rows,
    first and last segment extended."""

    def test_no_voltage_no_current(self):
        """Rewritten: the old model put the Zener at its knee voltage at zero
        current. The table model has no current at or below 0 V."""
        assert current_ma(0.0) == 0.0
        assert current_ma(-1.0) == 0.0

    def test_below_the_first_row(self):
        """Below 1 µA (1.14 V) the first segment is extended: the Zener
        conducts well below the old 0.94 x VZ knee."""
        slope = math.log(2) / (1.25 - 1.14)           # ln(2 µA / 1 µA) per volt
        assert current_ma(1.0) == pytest.approx(0.001 * math.exp(slope * (1.0 - 1.14)))
        assert 0 < current_ma(0.5) < current_ma(1.0) < 0.001

    def test_at_a_table_row(self):
        """At a table voltage the current is the row's current."""
        assert current_ma(2.69) == pytest.approx(1.0)
        assert current_ma(2.03) == pytest.approx(0.1)

    def test_between_rows(self):
        """Halfway in voltage between 2 mA (2.93 V) and 5 mA (3.28 V) the
        current is their geometric mean."""
        assert current_ma((2.93 + 3.28) / 2) == pytest.approx(math.sqrt(2 * 5))

    def test_at_5_ma(self):
        """At 5 mA: 3.28 V typical (Fig. 7), 3.10 to 3.50 V (Table 8)."""
        assert current_ma(3.28, "typ") == pytest.approx(5.0)
        assert current_ma(3.10, "min") == pytest.approx(5.0)
        assert current_ma(3.50, "max") == pytest.approx(5.0)

    def test_above_the_last_row(self):
        """Above 10 mA (3.55 V) the last segment (5 mA to 10 mA) is extended."""
        slope = math.log(2) / (3.55 - 3.28)
        assert current_ma(3.8) == pytest.approx(10 * math.exp(slope * (3.8 - 3.55)))

    def test_maximum_column_conducts_least(self):
        """At the same voltage the maximum column carries less current than
        the typical one, and the minimum column more."""
        for volts in [1.0, 2.0, 2.69, 3.28, 3.6]:
            assert current_ma(volts, "max") < current_ma(volts, "typ") < current_ma(volts, "min")


# ── Full calculation with known values ────────────────────────────────────────

class TestFullCalculation:
    """Solve the baseline (10k/18k, BZB984-C3V3 to GND) and verify results."""

    def setup_method(self):
        self.r = solve(zener_reference())
        self.d = self.r["details"]
        self.levels = self.r["voltages"]["levels"]

    def test_divider_ratio(self):
        # k = 18000 / (10000 + 18000) = 0.6429
        assert abs(self.d["k_nominal"] - 18000 / 28000) < 0.0001

    def test_input_impedance(self):
        assert abs(self.d["r_total_ohms"] - 28000) < 1

    def test_source_impedance(self):
        # R1||R2 + Rs = (10000*18000)/(10000+18000) + 0 = 6428.57
        expected = (10000 * 18000) / 28000
        assert abs(self.d["r_source_ohms"] - expected) < 1

    def test_tolerance_ratios(self):
        # k_high = R2_max / (R1_min + R2_max) > k_nominal
        # k_low  = R2_min / (R1_max + R2_min) < k_nominal
        assert self.d["k_high"] > self.d["k_nominal"]
        assert self.d["k_low"] < self.d["k_nominal"]

    def test_vmcu_typical_is_clamped(self):
        """At 30V input, the diode should clamp V_mcu well below divider voltage."""
        v_divider = 30 * self.d["k_nominal"]  # ~19.3V unclamped
        assert self.d["v_pin_typ"] < v_divider
        assert self.d["v_pin_typ"] < 4.0

    def test_vmcu_worst_greater_than_typical(self):
        assert self.d["v_pin_high"] >= self.d["v_pin_typ"]

    def test_vmcu_typical_near_zener(self):
        """Typical V_mcu should be close to VZ nom at max input."""
        assert abs(self.d["v_pin_typ"] - 3.3) < 0.3

    def test_safety_margins(self):
        # margin = limit - highest pin voltage
        assert abs(self.d["margin_rec_v"] - (3.6 - self.d["v_pin_high"])) < 0.001
        assert abs(self.d["margin_abs_v"] - (4.0 - self.d["v_pin_high"])) < 0.001

    def test_power_positive(self):
        assert self.d["p_r1_mw"] > 0
        assert self.d["p_r2_mw"] > 0
        assert self.d["p_diode_mw"] >= 0
        assert self.d["p_total_mw"] > 0

    def test_power_sum(self):
        """Total power should equal sum of component powers."""
        d = self.d
        assert abs(d["p_total_mw"] - (d["p_r1_mw"] + d["p_r2_mw"] + d["p_diode_mw"])) < 0.1

    def test_current_balance(self):
        """I_R1 = I_R2 + I_diode (Kirchhoff's current law at the node)."""
        d = self.d
        assert abs(d["i_r1_ma"] - (d["i_r2_ma"] + d["i_diode_ma"])) < 0.01

    def test_power_margins(self):
        # R1: 200 mW rating
        assert self.d["r1_margin_pct"] is not None
        assert self.d["r1_margin_pct"] == pytest.approx(
            (200 - self.d["p_r1_mw"]) / 200 * 100, abs=0.1)
        # R2: 100 mW rating
        assert self.d["r2_margin_pct"] is not None

    def test_operating_points_count(self):
        """0 V, Logic Low, Logic High, ADC Scale, Max Input."""
        assert list(self.levels) == ["zero", "logic_low", "logic_high",
                                     "analog_fullscale", "max_input"]

    def test_operating_point_zero(self):
        op0 = self.levels["zero"]
        assert op0["v_in"] == 0
        assert op0["low"] == 0
        assert op0["high"] == 0

    def test_operating_point_monotonic(self):
        """V_mcu should increase (or stay flat) as V_in increases."""
        prev_h = 0
        for op in self.levels.values():
            assert op["high"] >= prev_h - 0.001
            prev_h = op["high"]

    def test_plot_data_from_app_state_not_from_the_solver(self):
        """Rewritten: the solver returns no plot data. AppState sweeps the
        solver's pin-voltage function and holds plain lists."""
        assert not [k for k in self.r if "plot" in k]
        assert not [k for k in self.d if "plot" in k]
        plot = app_state().plot_data
        assert "v_in" in plot and "v_mcu_typ" in plot and "v_mcu_worst" in plot
        assert len(plot["v_in"]) == 200
        for key in ("v_in", "v_mcu_typ", "v_mcu_worst"):
            assert type(plot[key]) is list and all(type(x) is float for x in plot[key])

    def test_resolution(self):
        """Resolution is VREF / 2^N referred to the input, VREF = VDD."""
        expected = 3.3 / 4096 * 1000 / self.d["k_nominal"]
        assert abs(self.d["resolution_mv_per_lsb"] - expected) < 1e-9

    def test_min_sample_cycles_row_removed(self):
        """The ADC sampling-cycle table did not match DS12983 Table 67."""
        assert "min_sample_cycles" not in self.d
        assert not hasattr(clamp_solver, "get_min_sample_cycles")
        assert self.d["r_source_ohms"] is not None        # the impedance row stays


# ── The design of the old results.div ────────────────────────────────────────

class TestResultsDivDesign:
    """8.2k / 29k divider (the design the old results.div held)."""

    def setup_method(self):
        design = change(zener_reference(), resistors__r1__value=8.2,
                        resistors__r2__value=29, resistors__r2__rating_mw=63,
                        system__v_analog_fullscale=4.1, system__v_logic_high_min=3.0)
        self.r = solve(design)
        self.d = self.r["details"]

    def test_divider_ratio(self):
        expected = 29000 / (8200 + 29000)
        assert abs(self.d["k_nominal"] - expected) < 0.0001

    def test_vmcu_below_abs_max(self):
        """V_mcu worst case must stay below absolute max for a valid design."""
        assert self.d["v_pin_high"] < 4.0

    def test_vmcu_worst_near_zener_max(self):
        """With 30V input and 3.5V max Zener, worst case should be near 3.5V."""
        assert 3.0 < self.d["v_pin_high"] < 4.0

    def test_positive_margins(self):
        assert self.d["margin_abs_v"] > 0, f"Abs margin {self.d['margin_abs_v']} <= 0"


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_zero_resistors_returns_empty(self):
        """R1=0 or R2=0 should return an empty result without crashing."""
        r = solve(zener_reference(resistors__r1__value=0))
        assert r["details"]["k_nominal"] is None
        assert "resistors.r1.value" in r["missing"]["divider"]

    def test_no_clamping_at_low_voltage(self):
        """At 1V input, divider output is well below the Zener — no clamping."""
        design = zener_reference(resistors__r2__value=10, system__v_input_max=1.0)
        r = solve(design)
        # V_mcu should equal divider voltage (0.5V), not clamped
        assert abs(r["details"]["v_pin_typ"] - 0.5) < 0.05

    def test_high_series_resistance(self):
        """R_series should add to source impedance."""
        base = zener_reference(resistors__r2__value=10)
        with_rs = change(base, resistors__r_series=dict(value=1, unit=KOHM, rating_mw=None,
                                                        tolerance_pct=None))
        a, b = solve(base)["details"], solve(with_rs)["details"]
        assert abs(b["r_source_ohms"] - a["r_source_ohms"] - 1000) < 1
