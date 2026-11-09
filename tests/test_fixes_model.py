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
               r1_rating_mw=200, r2_rating_mw=100)
    mcu = dict(vdd=3.3, v_recommended_max=3.6, v_absolute_max=4.0, safe_injection_ma=1.0,
               adc_bits=12, vil_factor=0.3, vih_factor=0.7)
    sysp = dict(v_input_max=30, v_analog_fullscale=5.1, v_logic_high_min=3.8,
                v_logic_low_max=1.0)
    zen = dict(C3V3)
    for k, v in overrides.items():
        for d in (res, mcu, sysp, zen):
            if k in d:
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

    def test_only_one_iteration_loop_in_circuit_model(self):
        src = inspect.getsource(circuit_model)
        assert src.count("range(SOLVER_ITERATIONS)") == 1
        assert "range(15)" not in src


# ── Question c: visible warning when the solver doesn't settle ───────────────

class TestSolverSettling:
    def test_low_value_divider_warns(self):
        """R1 = R2 = 100 ohm: the iteration overshoots; this must be visible."""
        r = calculate_all(*reference(r1_ohms=100, r2_ohms=100))
        assert r.warnings, "expected a 'did not settle' warning"
        assert "did not settle" in r.warnings[0]

    def test_unsettled_flag_from_solver(self):
        z = ZenerParams(**C3V3)
        assert solve_node_voltage(30, 100, 100, z, False).settled is False
        assert solve_node_voltage(30, 10000, 18000, z, False).settled is True
        # Not clamping at all is settled
        assert solve_node_voltage(1, 10000, 18000, z, False).settled is True


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

    def test_zzk_and_vz_min_are_not_needed(self):
        r = calculate_all(*reference(zzk_typ=None, zzk_max=None, vz_min=None))
        assert r.v_mcu_typ is not None and r.v_mcu_worst is not None
        for miss in r.missing.values():
            assert not any(p in miss for p in ("zener.zzk_typ", "zener.zzk_max", "zener.vz_min"))


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
