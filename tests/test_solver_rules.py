"""
Solver-level tests of the rules fixed on the bug-fix branch (ported from
the tests of the old circuit_model.py / bandwidth_model.py): one solver,
bisection, no results from missing inputs, no hidden defaults, thresholds,
worst-case power and the power verdict.
Run with: python -m pytest tests/ -v
"""
import inspect
import math
import re

import pytest

from src.models import clamp_solver
from src.models.clamp_solver import (
    FAIL, NEEDS_INPUT, PASS, TIGHT, pin_voltage, prepare, solve,
)
from tests.designs import KOHM, OHM, app_state, change, schottky_rail, zener_reference


def reference(**overrides):
    """Verification baseline: 10k/18k 1 %, R_s 0, 30 V, BZB984-C3V3 to GND,
    VDD 3.3 V."""
    return zener_reference(**overrides)


def check(results, cid):
    return next(c for c in results["checks"] if c["id"] == cid)


def rs(value, unit=KOHM, rating_mw=250, tolerance_pct=5):
    return dict(value=value, unit=unit, rating_mw=rating_mw, tolerance_pct=tolerance_pct)


# ── Reference case (must still hold) ─────────────────────────────────────────

class TestReferenceCase:
    def test_reference_values(self):
        r = solve(reference())
        d = r["details"]
        assert d["r_total_ohms"] == pytest.approx(28000)
        assert round(d["k_nominal"], 3) == 0.643
        assert round(d["v_pin_typ"], 2) == 3.02
        assert round(d["v_pin_high"], 2) == 3.24
        assert round(d["i_diode_ma"], 1) == 2.5
        assert r["warnings"] == []

    def test_reference_displayed_precision(self):
        """Values as displayed (3 decimals): typical 3.020, diode maximum with
        nominal R 3.235, highest of all corners 3.239."""
        d = solve(reference())["details"]
        assert f"{d['v_pin_typ']:.3f}" == "3.020"
        assert f"{d['v_pin_diode_max']:.3f}" == "3.235"
        assert f"{d['v_pin_high']:.3f}" == "3.239"
        assert f"{d['i_diode_ma']:.2f}" == "2.53"


# ── One solver everywhere ────────────────────────────────────────────────────

class TestSingleSolver:
    def test_5v_repro_worst_case_not_above_divider(self):
        """V_input max 5 V: the node can't exceed the divider voltage
        5 x 18/28 = 3.214 V."""
        d = solve(reference(system__v_input_max=5))["details"]
        v_div = 5 * 18000 / 28000
        assert d["v_pin_diode_max"] <= v_div + 1e-9
        assert d["v_pin_typ"] <= v_div + 1e-9

    def test_typical_and_worst_solved_independently(self):
        design = reference(system__v_input_max=5)
        d = solve(design)["details"]
        c = prepare(design)
        assert d["v_pin_typ"] == c.node(5, 10000, 18000, "typ")
        assert d["v_pin_diode_max"] == c.node(5, 10000, 18000, "max")
        assert d["v_pin_typ"] == pin_voltage(design, 5, "typ")

    def test_results_operating_points_and_plot_agree(self):
        """Results, input levels and plot all come from the same solver."""
        s = app_state()
        d = s.details
        # Plot's last point is V_in max
        assert s.plot_data["v_in"][-1] == pytest.approx(30)
        assert s.plot_data["v_mcu_typ"][-1] == pytest.approx(d["v_pin_typ"], abs=1e-12)
        assert s.plot_data["v_mcu_worst"][-1] == pytest.approx(d["v_pin_high"], abs=1e-12)
        assert s.level("max_input")["high"] == pytest.approx(d["v_pin_high"], abs=1e-12)

    def test_plot_typical_curve_matches_solver_at_every_point(self):
        s = app_state(reference(system__v_input_max=6))
        for vin, v in zip(s.plot_data["v_in"], s.plot_data["v_mcu_typ"]):
            assert v == pin_voltage(s.design, vin, "typ")
        for vin, v in zip(s.plot_data["v_in"], s.plot_data["v_mcu_worst"]):
            assert v == pin_voltage(s.design, vin, "high")

    def test_only_one_solver_loop_in_the_app(self):
        """One bisection loop, in clamp_solver.py; the old model is gone."""
        src = inspect.getsource(clamp_solver)
        assert src.count("range(SOLVER_MAX_ITERATIONS)") == 1
        with pytest.raises(ImportError):
            import src.models.circuit_model  # noqa: F401
        with pytest.raises(ImportError):
            import src.models.bandwidth_model  # noqa: F401


# ── Bisection; warning only when bracketing fails ────────────────────────────

class TestSolverSettling:
    def test_low_value_divider_converges(self):
        """R1 = R2 = 100 ohm. The node is far above the table, on the extended
        last segment (5 mA to 10 mA, 0.27 V per factor of 2)."""
        design = reference(resistors__r1__value=100, resistors__r1__unit=OHM,
                           resistors__r2__value=100, resistors__r2__unit=OHM)
        r = solve(design)
        assert r["warnings"] == []
        v = r["details"]["v_pin_typ"]
        amps = (30 - v) / 100 - v / 100
        assert v == pytest.approx(3.28 + 0.27 * math.log(amps / 0.005) / math.log(2), abs=1e-8)

    def test_unsettled_flag_from_solver(self):
        c = prepare(reference())
        curves = c.v[clamp_solver.CURVE["typ"]]
        for vin, r1, r2 in ((30, 100, 100), (30, 10000, 18000), (1, 10000, 18000)):
            assert clamp_solver._solve_node(vin, r1, r2, c.sign, c.v_ref, curves)[1] is True
        # A bracket with no sign change (an input that is not a number,
        # passed straight to the solver) is the case where bracketing fails
        v, settled = clamp_solver._solve_node(float("nan"), 1000, 18000, c.sign, c.v_ref, curves)
        assert settled is False

    def test_root_within_one_nanovolt(self):
        """The residual of the node equation changes sign within 1 nV of the
        returned voltage."""
        c = prepare(reference())
        curves = c.v[clamp_solver.CURVE["typ"]]
        r1, r2, vin = 10000, 18000, 30
        v, _ = clamp_solver._solve_node(vin, r1, r2, c.sign, c.v_ref, curves)

        def h(x):
            return (vin - x) / r1 - x / r2 - clamp_solver._curve_current(curves["reverse"], x)
        assert h(v - 1e-9) > 0 > h(v + 1e-9)

    def test_warning_kept_when_bracketing_fails(self, monkeypatch):
        real = clamp_solver._solve_node
        monkeypatch.setattr(clamp_solver, "_solve_node",
                            lambda *a, **k: (real(*a, **k)[0], False))
        r = solve(reference())
        assert r["warnings"] and "did not settle" in r["warnings"][0]

    def test_no_step_where_the_0_5_ma_rule_stepped(self):
        """Rewritten: the old model sat at 3.300 V just below 9.753 V in and
        dropped 0.2 V to its knee just above (the 0.5 mA rule). The table
        model has no such step: 2 mV of input moves the pin by 0.1 mV."""
        design = reference()
        below = pin_voltage(design, 9.752, "typ")
        above = pin_voltage(design, 9.754, "typ")
        assert 0 < above - below < 2e-4
        assert 2.4 < below < 2.7


# ── Nothing computable -> nothing shown ──────────────────────────────────────

class TestNoStaleOrFakeResults:
    def test_r1_zero_gives_no_results_not_zeros(self):
        s = app_state(reference(resistors__r1__value=0))
        r, d = s.results, s.details
        assert d["k_nominal"] is None and d["v_pin_typ"] is None and d["v_pin_high"] is None
        assert check(r, "pin_max_safe")["status"] == NEEDS_INPUT
        assert check(r, "pin_max_abs")["status"] == NEEDS_INPUT
        assert s.plot_data == {}
        for row in r["voltages"]["levels"].values():
            assert row["low"] is None and row["high"] is None
        for cid in ("logic_low", "logic_high", "analog_range"):
            assert check(r, cid)["status"] == NEEDS_INPUT

    def test_unrelated_outputs_still_computed(self):
        """A blank ADC bits field blocks only the resolution (and the analog
        error in LSB)."""
        s = app_state(reference(mcu__adc_bits=None))
        assert s.details["resolution_mv_per_lsb"] is None
        assert s.results["missing"]["resolution"] == ["mcu.adc_bits"]
        assert s.results["missing"]["analog_error_lsb"] == ["mcu.adc_bits"]
        assert sorted(k for k, v in s.results["missing"].items() if v) == [
            "analog_error_lsb", "resolution"]
        assert s.details["v_pin_typ"] is not None and s.plot_data


# ── No hidden defaults in the solver ─────────────────────────────────────────

class TestNoHiddenDefaults:
    def test_solver_has_no_fallback_values(self):
        """Rewritten (was: parameter dataclasses default to None). The solver
        takes a dict; it never reads a key with a fallback value."""
        src = inspect.getsource(clamp_solver)
        assert "dataclass" not in src
        assert not re.findall(r"\.get\([^()]*,", src)
        assert "setdefault" not in src

    def test_empty_inputs_compute_nothing(self):
        r = solve({})
        assert r["details"]["k_nominal"] is None and r["details"]["v_pin_typ"] is None
        from src.core.app_state import AppState
        assert AppState().plot_data == {}


# ── Zero ratings never crash ─────────────────────────────────────────────────

class TestZeroRatings:
    def test_zero_resistor_rating(self):
        d = solve(reference(resistors__r1__rating_mw=0))["details"]
        assert d["r1_margin_pct"] is None
        assert d["r2_margin_pct"] is not None

    def test_zero_ptot(self):
        d = solve(reference(clamp_diode__ptot_mw=0))["details"]
        assert d["diode_margin_pct"] is None
        assert d["v_pin_typ"] is not None


# ── ADC bits and logic threshold factors ─────────────────────────────────────

class TestAdcAndThresholds:
    @pytest.mark.parametrize("bits", [10, 12, 16])
    def test_resolution_vref_over_2n(self, bits):
        d = solve(reference(mcu__adc_bits=bits))["details"]
        assert d["resolution_mv_per_lsb"] == pytest.approx(3.3 / 2 ** bits * 1000 / (18 / 28))

    def test_threshold_factors_used(self):
        r = solve(reference(mcu__vil_factor=0.25, mcu__vih_factor=0.75))
        assert r["voltages"]["vil"] == pytest.approx(0.825)
        assert r["voltages"]["vih"] == pytest.approx(2.475)
        assert check(r, "logic_low")["limit"] == pytest.approx(0.25 * 3.3)
        assert check(r, "logic_high")["limit"] == pytest.approx(0.75 * 3.3)

    def test_blank_factors_block_only_logic_checks(self):
        r = solve(reference(mcu__vil_factor=None, mcu__vih_factor=None))
        assert check(r, "logic_low")["status"] == NEEDS_INPUT
        assert check(r, "logic_high")["status"] == NEEDS_INPUT
        assert r["voltages"]["levels"]["logic_low"]["high"] is not None
        assert check(r, "pin_max_abs")["status"] == PASS

    def test_high_level_is_lowest_pin_voltage_at_logic_high(self):
        """The level a high pulse settles to: the lowest of the 8 corners at
        the Logic High input (for this Zener: R1 max, R2 min, minimum column)."""
        design = reference()
        r = solve(design)
        c = prepare(design)
        corners = [x["v"] for x in c.corners(3.8)]
        assert check(r, "logic_high")["value"] == min(corners) \
            == r["voltages"]["levels"]["logic_high"]["low"]
        assert min(corners) == c.node(3.8, 10000 * 1.01, 18000 * 0.99, "min")


# ── Frequency limits (rewritten: was the four-limit bandwidth model) ─────────

class TestFrequencyRules:
    def test_pin_never_reads_high_blocks_limits_no_fallback(self):
        """If the pin never gets above VIH the result must say so and give no
        limit; nothing is substituted."""
        r = solve(reference())          # 3.8 V Logic High: pin 1.83 V < VIH 2.31 V
        d = r["details"]
        assert d["f_may_work_hz"] is None and d["f_reliable_hz"] is None
        assert "never reads high" in d["frequency_note"]
        assert r["notes"] == [d["frequency_note"]]
        assert d["tau_ns"] is not None

    def test_limits_need_every_input(self):
        r = solve(schottky_rail(mcu__t_pulse_min_ns=None))
        assert r["details"]["f_may_work_hz"] is None
        assert r["details"]["f_reliable_hz"] is None
        assert "mcu.t_pulse_min_ns" in r["missing"]["f_limits"]
        assert r["details"]["tau_ns"] is not None

    def test_tau_from_maximum_resistances(self):
        d = solve(schottky_rail())["details"]
        assert d["tau_ns"] == pytest.approx(10100 * 18180 / 28280 * 18e-12 * 1e9)

    def test_rising_formula(self):
        r = solve(schottky_rail())
        b = r["voltages"]["levels"]["logic_high"]["low"]
        expected = r["details"]["tau_ns"] * math.log(b / (b - 2.31))
        assert r["details"]["t_rise_ns"] == pytest.approx(expected)


# ── No injection estimate (owner, 2026-11-09) ────────────────────────────────

class TestNoInjectionEstimate:
    def test_safe_max_is_the_guard(self):
        """The estimate divided by an assumed 100 ohm that no data sheet
        gives; it is removed. Safe Max is the guard against injection."""
        r = solve(schottky_rail())
        assert "injection" not in [c["id"] for c in r["checks"]]
        assert not [k for k in r["details"] if "inj" in k]
        assert r["details"]["v_pin_high"] > 3.6
        assert check(r, "pin_max_safe")["status"] == FAIL
        src = inspect.getsource(clamp_solver)
        assert "ESD" not in src and "safe_injection" not in src and "+ 100" not in src


# ── Typical and worst-case power ─────────────────────────────────────────────

class TestWorstCasePower:
    HOT = dict(resistors__r1__value=1, resistors__r1__rating_mw=2000)
    CASES = [reference(),
             reference(**HOT, resistors__r_series=rs(1, rating_mw=250)),
             reference(resistors__r1__value=4.7, system__v_input_max=24),
             reference(system__v_input_max=60)]

    @pytest.mark.parametrize("design", CASES)
    def test_worst_at_least_typical_for_each_part(self, design):
        d = solve(design)["details"]
        for part in ("r1", "r2", "diode"):
            typ, worst = d[f"p_{part}_mw"], d[f"p_{part}_worst_mw"]
            assert worst is not None and worst >= typ, part
        if d["has_rs"]:
            assert d["p_rs_worst_mw"] >= d["p_rs_mw"]

    def test_hand_checked_r1_corner(self):
        """Reference case, corner R1 min 9.9 k, R2 min 17.82 k, minimum
        column: the diode current is between the 2 mA (2.75 V) and 5 mA
        (3.10 V) rows, so V = 2.75 + 0.35 x ln(I / 2 mA) / ln(2.5) with
        I = 30/9.9 - V (1/9.9 + 1/17.82) (mA, kohm)."""
        d = solve(reference())["details"]
        v = prepare(reference()).node(30, 9900, 17820, "min")
        i_ma = 30 / 9.9 - v * (1 / 9.9 + 1 / 17.82)
        assert 2 < i_ma < 5
        assert v == pytest.approx(2.75 + 0.35 * math.log(i_ma / 2) / math.log(2.5), abs=1e-8)
        assert v == pytest.approx(2.8477, abs=1e-4)
        p_r1 = (30 - v) ** 2 / 9.9          # mW (V^2 / kohm)
        assert d["p_r1_worst_mw"] == pytest.approx(p_r1, abs=1e-6)
        assert d["p_r1_worst_mw"] == pytest.approx(74.47, abs=0.01)
        assert d["worst_power_corner"]["r1"] == "R1 min, R2 min, diode min"

    def test_hand_checked_rs_worst(self):
        """Rewritten (owner, 2026-11-09): R_s 1 k at 5 %, pin held at 0 V:
        P = V_node,max^2 / R_s,min = V^2 / 950 ohm."""
        d = solve(reference(**self.HOT, resistors__r_series=rs(1)))["details"]
        assert d["p_rs_worst_mw"] == pytest.approx(d["v_pin_high"] ** 2 / 950 * 1000)
        assert d["p_rs_mw"] == pytest.approx(d["v_pin_typ"] ** 2 / 1000 * 1000)

    def test_blank_minimum_column_blocks_only_worst_case(self):
        """Rewritten (was: VZ min blocks only the worst-case power). A blank
        cell in the minimum column blocks the corners, not the typical."""
        design = reference()
        design["clamp_diode"]["reverse"][4]["v_min"] = None
        r = solve(design)
        d = r["details"]
        cell = "clamp_diode.reverse[4].v_min"
        assert d["p_r1_worst_mw"] is None and check(r, "power_r1")["status"] == NEEDS_INPUT
        assert cell in r["missing"]["p_r1_worst"]
        assert d["p_r1_mw"] is not None and d["r1_margin_pct"] is not None
        assert d["v_pin_typ"] is not None and d["v_pin_diode_max"] is not None
        assert r["needs_input"] == [cell]
        for key, miss in r["missing"].items():
            if cell in miss:
                assert "typ" not in key, key

    def test_no_series_resistor_has_no_rs_power(self):
        r = solve(reference())
        d = r["details"]
        assert d["has_rs"] is False
        assert d["p_rs_mw"] is None and d["p_rs_worst_mw"] is None
        assert not any(k.startswith(("p_rs", "rs_margin")) for k in r["missing"])

    def test_rs_margins_use_rs_rating(self):
        d = solve(reference(**self.HOT, resistors__r_series=rs(1, rating_mw=20)))["details"]
        assert d["rs_margin_worst_pct"] == pytest.approx((20 - d["p_rs_worst_mw"]) / 20 * 100)
        assert d["rs_margin_pct"] == pytest.approx((20 - d["p_rs_mw"]) / 20 * 100)


# ── A blank rating shows "needs input", no hint value ────────────────────────

class TestBlankRatingMargin:
    def test_blank_rating_has_no_status(self):
        r = solve(reference(resistors__r1__rating_mw=None))
        d = r["details"]
        assert d["r1_margin_pct"] is None and d["r1_margin_worst_pct"] is None
        assert check(r, "power_r1")["status"] == NEEDS_INPUT
        assert r["missing"]["r1_margin"] == ["resistors.r1.rating_mw"]
        assert d["p_r1_mw"] is not None
        src = inspect.getsource(clamp_solver)
        assert "* 1.5" not in src


# ── The worst-case margin is the power verdict ───────────────────────────────

class TestPowerVerdict:
    def test_reference_case_passes(self):
        r = solve(reference())
        assert r["details"]["power_verdict"] == PASS
        for part in ("r1", "r2", "diode"):
            assert check(r, f"power_{part}")["status"] == PASS
            # the typical margin is information only: a number, no status
            assert r["details"][f"{part}_margin_pct"] > 20

    def test_typical_passes_worst_fails_gives_fail(self):
        """R1/R2 at 25 %: R1 rating 1.3 x typical power gives a typical margin
        of 23 % (PASS by the > 20 % threshold) but the worst-case power is
        above the rating."""
        wide = dict(resistors__r1__tolerance_pct=25, resistors__r2__tolerance_pct=25)
        p_typ = solve(reference(**wide))["details"]["p_r1_mw"]
        r = solve(reference(**wide, resistors__r1__rating_mw=1.3 * p_typ))
        d = r["details"]
        assert d["r1_margin_pct"] > 20                      # typical would pass
        assert clamp_solver._margin_status(d["r1_margin_pct"]) == PASS
        assert d["r1_margin_worst_pct"] <= 0
        assert check(r, "power_r1")["status"] == FAIL
        assert d["power_verdict"] == FAIL

    def test_tight_worst_margin_gives_tight(self):
        p = solve(reference())["details"]["p_diode_worst_mw"]
        r = solve(reference(clamp_diode__ptot_mw=p / 0.9))   # 10 % worst-case margin
        assert r["details"]["power_verdict"] == TIGHT

    def test_blank_rating_blocks_verdict(self):
        r = solve(reference(resistors__r2__rating_mw=None))
        assert r["details"]["power_verdict"] == NEEDS_INPUT
        assert "resistors.r2.rating_mw" in r["missing"]["r2_margin_worst"]

    def test_series_resistor_counts_in_verdict(self):
        base = dict(resistors__r1__value=1, resistors__r1__rating_mw=2000,
                    clamp_diode__ptot_mw=5000)
        ok = solve(reference(**base, resistors__r_series=rs(1, rating_mw=1000)))
        assert ok["details"]["power_verdict"] == PASS
        p_rs = ok["details"]["p_rs_worst_mw"]
        r = solve(reference(**base, resistors__r_series=rs(1, rating_mw=p_rs * 0.9)))
        assert check(r, "power_rs")["status"] == FAIL
        assert r["details"]["power_verdict"] == FAIL
