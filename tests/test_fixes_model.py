"""
Model-level tests for the bug-fix branch (bugs 1, 2, 4, 6, 10 and question c).
Run with: python -m pytest tests/ -v
"""
import inspect
import math

import pytest

from src.models import circuit_model
from src.models.circuit_model import (
    calculate_all, solve_node_voltage,
    McuParams, ResistorParams, SystemParams, ZenerParams,
)
from src.models.bandwidth_model import BandwidthParams, calculate_bandwidth

C3V3 = dict(vz_nom=3.3, vz_min=3.1, vz_max=3.5, izt_ma=5.0, izk_ma=1.0,
            zzt_typ=85.0, zzt_max=95.0, zzk_typ=350.0, zzk_max=600.0, ptot_mw=265.0)


def reference(**overrides):
    """CLAUDE.md verification baseline: 10k/18k 1 %, R_s 0, 30 V, BZB984-C3V3, VDD 3.3 V."""
    res = dict(r1_ohms=10000, r2_ohms=18000, rs_ohms=0, r1_tol_pct=1, r2_tol_pct=1,
               r1_rating_mw=200, r2_rating_mw=100, rs_tol_pct=None, rs_rating_mw=None)
    mcu = dict(vdd=3.3, v_recommended_max=3.6, v_absolute_max=4.0, safe_injection_ma=1.0,
               adc_bits=12, vil_factor=0.3, vih_factor=0.7)
    sysp = dict(v_input_max=30, v_analog_fullscale=5.1, v_logic_high_min=3.8,
                v_logic_low_max=1.0)
    zen = dict(C3V3)
    for k, v in overrides.items():
        hits = [d for d in (res, mcu, sysp, zen) if k in d]
        assert hits, f"unknown override {k}"
        for d in hits:
            d[k] = v
    return (ResistorParams(**res), ZenerParams(**zen), McuParams(**mcu), SystemParams(**sysp))


# ── Reference case (must still hold) ─────────────────────────────────────────

class TestReferenceCase:
    def test_reference_values(self):
        r = calculate_all(*reference())
        assert r.r_total_ohms == pytest.approx(28000)
        assert round(r.k_nominal, 3) == 0.643
        assert round(r.v_mcu_typ, 2) == 3.18
        assert round(r.v_mcu_worst_zener, 2) == 3.43
        assert round(r.i_z_ma, 1) == 2.5
        assert r.warnings == []

    def test_reference_displayed_precision_unchanged(self):
        """Values as displayed (3 decimals) at 453b460: typ 3.177, worst 3.433/3.434."""
        r = calculate_all(*reference())
        assert f"{r.v_mcu_typ:.3f}" == "3.177"
        assert f"{r.v_mcu_worst_zener:.3f}" == "3.433"
        assert f"{r.v_mcu_worst:.3f}" == "3.434"
        assert f"{r.i_z_ma:.2f}" == "2.51"


# ── Bug 2: one solver everywhere ─────────────────────────────────────────────

class TestSingleSolver:
    def test_5v_repro_worst_case_not_above_divider(self):
        """V_input max 5 V: the worst case was shown as 3.500 V; the node
        can't exceed the divider voltage 5 x 18/28 = 3.214 V."""
        r = calculate_all(*reference(v_input_max=5))
        v_div = 5 * 18000 / 28000
        assert r.v_mcu_worst_zener <= v_div + 1e-9
        assert r.v_mcu_worst_zener == pytest.approx(3.214, abs=5e-4)

    def test_typical_and_worst_solved_independently(self):
        r1, z, m, s = reference(v_input_max=5)
        r = calculate_all(r1, z, m, s)
        assert r.v_mcu_typ == solve_node_voltage(5, 10000, 18000, z, False).v_node
        assert r.v_mcu_worst_zener == solve_node_voltage(5, 10000, 18000, z, True).v_node

    def test_results_operating_points_and_plot_agree(self):
        """Results, operating points and plot all come from the same solver."""
        res, z, m, s = reference()
        r = calculate_all(res, z, m, s)
        # Plot's last point is V_in max
        assert r.plot_data["v_in"][-1] == pytest.approx(30)
        assert r.plot_data["v_mcu_typ"][-1] == pytest.approx(r.v_mcu_typ, abs=1e-12)
        assert r.plot_data["v_mcu_worst"][-1] == pytest.approx(r.v_mcu_worst, abs=1e-12)
        assert r.operating_points[4]["v_mcu_h"] == pytest.approx(r.v_mcu_worst, abs=1e-12)

    def test_plot_typical_curve_matches_solver_at_every_point(self):
        res, z, m, s = reference(v_input_max=6)
        r = calculate_all(res, z, m, s)
        for vin, v in zip(r.plot_data["v_in"], r.plot_data["v_mcu_typ"]):
            assert v == solve_node_voltage(vin, 10000, 18000, z, False).v_node

    def test_only_one_solver_loop_in_circuit_model(self):
        """Rewritten for the bisection solver (was: one 15-step iteration loop)."""
        src = inspect.getsource(circuit_model)
        assert src.count("range(SOLVER_MAX_ITERATIONS)") == 1
        assert "range(15)" not in src and "SOLVER_ITERATIONS =" not in src


# ── Question c: bisection solver; warning only when bracketing fails ─────────

class TestSolverSettling:
    def test_low_value_divider_now_converges(self):
        """R1 = R2 = 100 ohm used to overshoot (15-step iteration). Bisection
        converges; region 3 has a closed form:
        V = 3.3 + (I_Z - 5) x 0.085, I_Z = (30 - V)/0.1 - V/0.1 (mA, kohm)
        -> V = 28.375 / 2.7."""
        z = ZenerParams(**C3V3)
        sr = solve_node_voltage(30, 100, 100, z, False)
        assert sr.settled is True
        assert sr.v_node == pytest.approx(28.375 / 2.7, abs=2e-6)
        r = calculate_all(*reference(r1_ohms=100, r2_ohms=100))
        assert r.warnings == []
        assert r.v_mcu_typ == pytest.approx(28.375 / 2.7, abs=2e-6)

    def test_unsettled_flag_from_solver(self):
        """Rewritten: (30 V, 100, 100) now settles; a curve with no sign
        change over [0, V_divider] (negative ZZT, passed straight to the
        solver) is the case where bracketing fails."""
        z = ZenerParams(**C3V3)
        assert solve_node_voltage(30, 100, 100, z, False).settled is True
        assert solve_node_voltage(30, 10000, 18000, z, False).settled is True
        # Not clamping at all is settled
        assert solve_node_voltage(1, 10000, 18000, z, False).settled is True
        bad = ZenerParams(**dict(C3V3, zzt_typ=-1e6))   # matters above IZT
        sr = solve_node_voltage(30, 1000, 18000, bad, False)
        assert sr.settled is False
        assert sr.v_node == pytest.approx(30 * 18 / 19)

    def test_root_within_one_microvolt(self):
        """The returned node voltage is within 1 µV of where V = V_clamp(I_Z(V))."""
        z = ZenerParams(**C3V3)
        r1, r2, vin = 10000, 18000, 30
        v = solve_node_voltage(vin, r1, r2, z, False).v_node

        def h(x):
            iz = (vin - x) / r1 * 1000 - x / r2 * 1000
            return x - circuit_model.calculate_zener_voltage(iz, z, False)[0]
        assert h(v - 1e-6) < 0 < h(v + 1e-6)

    def test_warning_kept_when_bracketing_fails(self, monkeypatch):
        real = circuit_model.solve_node_voltage

        def failing(*a, **k):
            return circuit_model.SolveResult(real(*a, **k).v_node, False)
        monkeypatch.setattr(circuit_model, "solve_node_voltage", failing)
        r = calculate_all(*reference())
        assert r.warnings and "did not settle" in r.warnings[0]

    def test_cap_step_rule_unchanged(self):
        """CLAUDE.md §4B, I_Z < 0.5 mA -> cap at VZ, is kept: the typical curve
        (nominal 10k/18k) sits at VZ nom 3.3 V just below 9.753 V in, then
        drops about 0.2 V to the knee 0.94 x 3.3 = 3.102 V just above it."""
        z = ZenerParams(**C3V3)
        below = solve_node_voltage(9.752, 10000, 18000, z, False)
        above = solve_node_voltage(9.754, 10000, 18000, z, False)
        assert below.settled and above.settled
        assert below.v_node == pytest.approx(3.3)
        assert above.v_node == pytest.approx(0.94 * 3.3)


# ── Bug 4: nothing computable -> nothing shown ───────────────────────────────

class TestNoStaleOrFakeResults:
    def test_r1_zero_gives_no_results_not_zeros(self):
        r = calculate_all(*reference(r1_ohms=0))
        assert r.k_nominal is None and r.v_mcu_typ is None and r.v_mcu_worst is None
        assert r.rec_status is None and r.abs_status is None and r.inj_status is None
        assert r.i_injection_ma is None
        assert r.plot_data == {}
        for op in r.operating_points[1:]:
            assert op["v_mcu_l"] is None and op["v_mcu_h"] is None and op["status"] is None

    def test_unrelated_outputs_still_computed(self):
        """A blank ADC bits field blocks only the resolution."""
        r = calculate_all(*reference(adc_bits=None))
        assert r.resolution_mv_per_lsb is None
        assert r.missing["resolution"] == ["mcu.adc_bits"]
        assert r.v_mcu_typ is not None and r.plot_data


# ── Bug 5: no hidden defaults in the model ───────────────────────────────────

class TestNoDataclassDefaults:
    def test_params_default_to_none(self):
        for obj in (ZenerParams(), McuParams(), SystemParams()):
            assert all(v is None for v in vars(obj).values()), obj
        rp = ResistorParams()
        assert rp.r1_ohms is None and rp.r2_ohms is None
        assert rp.r1_tol_pct is None and rp.r1_rating_mw is None

    def test_empty_inputs_compute_nothing(self):
        r = calculate_all(ResistorParams(), ZenerParams(), McuParams(), SystemParams())
        assert r.k_nominal is None and r.v_mcu_typ is None and r.plot_data == {}

    def test_zzk_is_not_needed(self):
        """Rewritten: ZZK is reference only. (VZ min is now used by the
        worst-case power; see TestWorstCasePower.)"""
        r = calculate_all(*reference(zzk_typ=None, zzk_max=None))
        assert r.v_mcu_typ is not None and r.v_mcu_worst is not None
        assert r.p_z_worst_mw is not None
        for miss in r.missing.values():
            assert not any(p in miss for p in ("zener.zzk_typ", "zener.zzk_max"))

    def test_zzk_does_not_change_any_result(self):
        a = calculate_all(*reference())
        b = calculate_all(*reference(zzk_typ=1.0, zzk_max=99999.0))
        for name in ("v_mcu_typ", "v_mcu_worst", "v_mcu_worst_zener", "i_z_ma",
                     "p_r1_worst_mw", "p_z_worst_mw", "i_injection_ma"):
            assert getattr(a, name) == getattr(b, name), name


# ── Bug 6: zero ratings never crash ──────────────────────────────────────────

class TestZeroRatings:
    def test_zero_resistor_rating(self):
        r = calculate_all(*reference(r1_rating_mw=0))
        assert r.r1_margin_pct is None
        assert r.r2_margin_pct is not None

    def test_zero_ptot(self):
        r = calculate_all(*reference(ptot_mw=0))
        assert r.z_margin_pct is None
        assert r.v_mcu_typ is not None


# ── Bug 10: ADC bits and logic threshold factors ─────────────────────────────

class TestAdcAndThresholds:
    @pytest.mark.parametrize("bits", [10, 12, 16])
    def test_resolution_vref_over_2n(self, bits):
        r = calculate_all(*reference(adc_bits=bits))
        assert r.resolution_mv_per_lsb == pytest.approx(3.3 / 2 ** bits * 1000 / (18 / 28))

    def test_threshold_factors_used(self):
        r = calculate_all(*reference(vil_factor=0.25, vih_factor=0.75))
        assert r.vil_v == pytest.approx(0.825)
        assert r.vih_v == pytest.approx(2.475)
        assert r.operating_points[1]["requirement"] == f"< VIL {0.25 * 3.3:.2f}V"
        assert r.operating_points[2]["requirement"] == f"> VIH {0.75 * 3.3:.2f}V"

    def test_blank_factors_block_only_logic_checks(self):
        r = calculate_all(*reference(vil_factor=None, vih_factor=None))
        assert r.operating_points[1]["status"] is None
        assert r.operating_points[2]["status"] is None
        assert r.operating_points[1]["v_mcu_h"] is not None
        assert r.operating_points[4]["status"] is not None

    def test_v_high_pin_is_lowest_pin_voltage_at_logic_high(self):
        res, z, m, s = reference()
        r = calculate_all(res, z, m, s)
        expected = solve_node_voltage(3.8, 10000 * 1.01, 18000 * 0.99, z, False).v_node
        assert r.v_high_pin == expected == r.operating_points[2]["v_mcu_l"]


# ── Bug 1: bandwidth model ───────────────────────────────────────────────────

def bw(**kw):
    p = dict(r_tau_ohms=6428.57, c_diode_pf=450, c_pin_pf=10, c_stray_pf=3,
             vil_v=0.99, vih_v=2.31, v_high=2.45, f_peripheral_mhz=170, n_samples=3,
             counter_bits=16, counter_signed=False, f_read_hz=1000)
    p.update(kw)
    return calculate_bandwidth(BandwidthParams(**p))


class TestBandwidthModel:
    def test_v_high_below_vih_blocks_limits_no_fallback(self):
        """If V_high never reaches VIH the tab must say so; the effective
        limit must not silently fall back to the counter-overflow limit."""
        r = bw(v_high=2.2)
        assert r.f_max_overflow_hz == pytest.approx(65536000)
        assert r.f_max_effective_hz is None
        assert r.limiting_factor is None
        assert "never reaches VIH" in r.blocked["effective"]
        for k in ("practical", "digital", "t_undefined_rise"):
            assert "never reaches VIH" in r.blocked[k]

    def test_effective_needs_every_limit(self):
        r = bw(f_read_hz=None)
        assert r.f_max_overflow_hz is None
        assert r.f_max_effective_hz is None
        assert "f_read_hz" in r.missing["effective"]

    def test_effective_is_min_when_all_known(self):
        r = bw()
        limits = [r.f_max_analog_hz, r.f_max_practical_hz, r.f_max_digital_hz,
                  r.f_max_overflow_hz]
        assert r.f_max_effective_hz == min(limits)

    def test_tau_from_given_resistance(self):
        r = bw()
        assert r.tau_ns == pytest.approx(6428.57 * 463e-12 * 1e9)

    def test_rising_formula_with_v_high(self):
        r = bw()
        tau = 6428.57 * 463e-12
        expected = tau * math.log((2.45 - 0.99) / (2.45 - 2.31)) * 1e9
        assert r.t_undefined_rise_ns == pytest.approx(expected)


# ── Follow-up a: injection starts at VDD + 0.3 V, R_s at its low tolerance ───

def region3_worst_node(vin, r1_k, r2_k):
    """Closed-form node voltage on the worst-case curve above IZT (C3V3):
    V = 3.5 + (I_Z - 5) x 0.095 with I_Z = (vin - V)/R1 - V/R2 (mA, kohm)."""
    return (3.5 + 0.095 * (vin / r1_k - 5)) / (1 + 0.095 * (1 / r1_k + 1 / r2_k))


class TestInjectionEstimate:
    def test_reference_case_is_zero(self):
        """V_mcuH 3.434 V is below VDD + 0.3 = 3.6 V (it was 1.34 mA HIGH)."""
        r = calculate_all(*reference())
        assert r.i_injection_ma == 0.0
        assert r.inj_status[1] == circuit_model.PASS

    def test_node_above_onset_gives_expected_current(self):
        """R1 = 1 k (1 %), R_s = 1 k at 5 %: V_mcuH from the region-3 closed
        form, I = (V - 3.6) / (950 + 100)."""
        r = calculate_all(*reference(r1_ohms=1000, rs_ohms=1000, rs_tol_pct=5))
        v = region3_worst_node(30, 0.99, 18.18)
        assert r.v_mcu_worst == pytest.approx(v, abs=2e-6)
        assert r.i_injection_ma == pytest.approx((v - 3.6) / 1050 * 1000, abs=1e-5)
        assert r.i_injection_ma == pytest.approx(1.6774, abs=1e-4)

    def test_no_series_resistor_needs_no_tolerance(self):
        r = calculate_all(*reference(r1_ohms=1000, rs_ohms=0, rs_tol_pct=None))
        v = region3_worst_node(30, 0.99, 18.18)
        assert r.i_injection_ma == pytest.approx((v - 3.6) / 100 * 1000, abs=1e-4)

    def test_series_resistor_needs_its_tolerance(self):
        r = calculate_all(*reference(rs_ohms=1000, rs_tol_pct=None))
        assert r.i_injection_ma is None
        assert "resistors.rs_tol_pct" in r.missing["injection"]


# ── Follow-up b: typical and worst-case power ────────────────────────────────

class TestWorstCasePower:
    CASES = [dict(), dict(r1_ohms=1000, rs_ohms=1000, rs_tol_pct=5, rs_rating_mw=250),
             dict(r1_ohms=4700, v_input_max=24), dict(v_input_max=60)]

    @pytest.mark.parametrize("case", CASES)
    def test_worst_at_least_typical_for_each_part(self, case):
        r = calculate_all(*reference(**case))
        for part in ("r1", "r2", "z"):
            typ, worst = getattr(r, f"p_{part}_mw"), getattr(r, f"p_{part}_worst_mw")
            assert worst is not None and worst >= typ, part
        if r.has_rs:
            assert r.p_rs_worst_mw >= r.p_rs_mw

    def test_hand_checked_r1_corner(self):
        """Reference case, corner R1 min 9.9 k, R2 min 17.82 k, VZ min 3.1 V.
        I_Z is between IZK and IZT, so V = 2.914 + 0.186 x (I_Z - 1) / 4
        (knee 0.94 x 3.1 = 2.914) with I_Z = 30/9.9 - V (1/9.9 + 1/17.82)."""
        knee, slope = 0.94 * 3.1, (3.1 - 0.94 * 3.1) / 4
        g = 1 / 9.9 + 1 / 17.82
        v = (knee + slope * (30 / 9.9 - 1)) / (1 + slope * g)
        p_r1 = (30 - v) ** 2 / 9.9          # mW (V^2 / kohm)
        assert v == pytest.approx(2.98659, abs=1e-5)
        r = calculate_all(*reference())
        assert r.p_r1_worst_mw == pytest.approx(p_r1, abs=1e-5)
        assert r.p_r1_worst_mw == pytest.approx(73.71, abs=0.01)
        assert r.worst_power_corner["r1"] == "R1 min, R2 min, VZ min"

    def test_hand_checked_rs_worst(self):
        """R_s 1 k at 5 %: P = I^2 R with I = (V_mcuH - 3.6) / (R + 100);
        the maximum over 950..1050 ohm is at 950 ohm."""
        r = calculate_all(*reference(r1_ohms=1000, rs_ohms=1000, rs_tol_pct=5))
        v = region3_worst_node(30, 0.99, 18.18)
        i = (v - 3.6) / 1050
        assert r.p_rs_worst_mw == pytest.approx(i ** 2 * 950 * 1000, abs=1e-5)

    def test_rs_worst_peak_inside_tolerance_band(self):
        """P(R) peaks at R = 100 ohm; with R_s 100 ohm at 10 % the maximum is
        at 100 ohm, not at either end."""
        r = calculate_all(*reference(r1_ohms=1000, rs_ohms=100, rs_tol_pct=10))
        dv = r.v_mcu_worst - 3.6
        assert r.p_rs_worst_mw == pytest.approx((dv / 200) ** 2 * 100 * 1000, abs=1e-6)

    def test_vz_min_blocks_only_worst_power(self):
        r = calculate_all(*reference(vz_min=None))
        assert r.p_r1_worst_mw is None and r.r1_margin_worst_status is None
        assert "zener.vz_min" in r.missing["p_r1_worst"]
        assert r.p_r1_mw is not None and r.r1_margin_status is not None
        assert r.v_mcu_worst is not None and r.i_injection_ma is not None
        for key, miss in r.missing.items():
            if "zener.vz_min" in miss:
                assert "worst" in key or key in ("power_worst", "power_verdict"), key

    def test_no_series_resistor_has_no_rs_power(self):
        r = calculate_all(*reference())
        assert r.has_rs is False
        assert r.p_rs_mw is None and r.p_rs_worst_mw is None
        assert not any(k.startswith(("p_rs", "rs_margin")) for k in r.missing)

    def test_rs_margins_use_rs_rating(self):
        r = calculate_all(*reference(r1_ohms=1000, rs_ohms=1000, rs_tol_pct=5,
                                     rs_rating_mw=10))
        assert r.rs_margin_worst_pct == pytest.approx((10 - r.p_rs_worst_mw) / 10 * 100)
        assert r.rs_margin_pct == pytest.approx((10 - r.p_rs_mw) / 10 * 100)


# ── Follow-up: a blank rating shows "needs input", no hint value ─────────────

class TestBlankRatingMargin:
    def test_blank_rating_has_no_status(self):
        r = calculate_all(*reference(r1_rating_mw=None))
        assert r.r1_margin_status is None and r.r1_margin_worst_status is None
        assert r.missing["r1_margin"] == ["resistors.r1_rating_mw"]
        assert r.p_r1_mw is not None
        src = inspect.getsource(circuit_model)
        assert "* 1.5" not in src


# ── Follow-up 2: the worst-case margin is the power verdict ──────────────────

class TestPowerVerdict:
    def test_reference_case_passes(self):
        r = calculate_all(*reference())
        assert r.power_verdict == ("✓ PASS", circuit_model.PASS)
        for part in ("r1", "r2", "z"):
            assert getattr(r, f"{part}_margin_worst_status")[1] == circuit_model.PASS
            # typical margin is information only
            assert getattr(r, f"{part}_margin_status")[1] == circuit_model.INFO

    def test_typical_passes_worst_fails_gives_fail(self):
        """R1/R2 at 25 %: R1 rating 1.3 x typical power gives a typical margin
        of 23 % (PASS by the > 20 % threshold) but the worst-case power is
        above the rating."""
        p_typ = calculate_all(*reference(r1_tol_pct=25, r2_tol_pct=25)).p_r1_mw
        r = calculate_all(*reference(r1_tol_pct=25, r2_tol_pct=25,
                                     r1_rating_mw=1.3 * p_typ))
        assert r.r1_margin_pct > 20                      # typical would pass
        assert circuit_model._margin_status(r.r1_margin_pct)[1] == circuit_model.PASS
        assert r.r1_margin_worst_pct <= 0
        assert r.r1_margin_worst_status[1] == circuit_model.FAIL
        assert r.power_verdict == ("✗ FAIL", circuit_model.FAIL)

    def test_tight_worst_margin_gives_tight(self):
        p = calculate_all(*reference()).p_z_worst_mw
        r = calculate_all(*reference(ptot_mw=p / 0.9))   # 10 % worst-case margin
        assert r.power_verdict == ("⚠ TIGHT", circuit_model.WARN)

    def test_blank_rating_blocks_verdict(self):
        r = calculate_all(*reference(r2_rating_mw=None))
        assert r.power_verdict is None
        assert "resistors.r2_rating_mw" in r.missing["power_verdict"]

    def test_series_resistor_counts_in_verdict(self):
        base = dict(r1_ohms=1000, rs_ohms=1000, rs_tol_pct=5,
                    r1_rating_mw=2000, ptot_mw=5000)
        p_rs = calculate_all(*reference(**base, rs_rating_mw=1000)).p_rs_worst_mw
        assert calculate_all(*reference(**base, rs_rating_mw=1000)).power_verdict[1] \
            == circuit_model.PASS
        r = calculate_all(*reference(**base, rs_rating_mw=p_rs * 0.9))
        assert r.rs_margin_worst_status[1] == circuit_model.FAIL
        assert r.power_verdict[1] == circuit_model.FAIL
