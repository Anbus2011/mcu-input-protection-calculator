"""
Tests for the clamp-diode solver (src/models/clamp_solver.py).
Run with: python -m pytest tests/ -v
"""
import json
import math
import os
import subprocess
import sys

import pytest

from src.models import clamp_solver
from src.models.clamp_solver import (
    FAIL, NEEDS_INPUT, PASS, TIGHT, number_problem, pin_voltage, prepare, solve,
    table_problems, wiring_problems, worst_status,
)
from tests.designs import (
    C3V3_CURRENT_MA, C3V3_TYPICAL_V, KOHM, MOHM, OHM, change, schottky_gnd,
    schottky_rail, zener_reference,
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def results_design(v_in):
    """The design of the old results.div (8.2 kΩ / 29 kΩ) at one input level."""
    return zener_reference(resistors__r1__value=8.2, resistors__r2__value=29,
                           system__v_input_max=v_in)


def check(results, cid):
    hits = [c for c in results["checks"] if c["id"] == cid]
    assert len(hits) == 1, f"{cid}: {len(hits)} checks"
    return hits[0]


def info(results, iid):
    return next(i for i in results["info"] if i["id"] == iid)


def table_voltage(rows, column, amps):
    """Independent reading of a diode table: voltage at a current, with
    ln(current) linear in voltage between rows."""
    for a, b in zip(rows, rows[1:]):
        ia, ib = a["i_ma"] / 1000, b["i_ma"] / 1000
        if ia <= amps <= ib:
            frac = math.log(amps / ia) / math.log(ib / ia)
            return a[column] + (b[column] - a[column]) * frac
    raise AssertionError("current outside the table")


# ── Reference numbers (docs/session2_prompt.md) ──────────────────────────────

class TestReferenceNumbers:
    @pytest.mark.parametrize("design,typ,low,high", [
        (zener_reference(), 3.020, 2.840, 3.239),
        (results_design(3.0), 1.928, 1.803, 2.065),
        (results_design(4.1), 2.156, 2.007, 2.334),
        (results_design(30), 3.106, 2.926, 3.326),
    ])
    def test_table(self, design, typ, low, high):
        """The reference table (CLAUDE.md, Verification Baseline), with
        minimum = typical - 0.18 V and maximum = typical + 0.22 V in every
        row."""
        row = solve(design)["voltages"]["levels"]["max_input"]
        assert row["typ"] == pytest.approx(typ, abs=0.001)
        assert row["low"] == pytest.approx(low, abs=0.001)
        assert row["high"] == pytest.approx(high, abs=0.001)

    def test_values_as_measured(self):
        """The same rows to 1 mV, as this solver gives them."""
        got = [solve(d)["voltages"]["levels"]["max_input"] for d in
               (zener_reference(), results_design(3.0), results_design(4.1),
                results_design(30))]
        assert [(f"{r['typ']:.3f}", f"{r['low']:.3f}", f"{r['high']:.3f}") for r in got] == [
            ("3.020", "2.840", "3.239"), ("1.928", "1.803", "2.065"),
            ("2.156", "2.007", "2.334"), ("3.106", "2.926", "3.326")]

    def test_original_table_with_the_original_offsets(self):
        """With typical -/+ 0.2 V in every row the solver gives the table as
        docs/session2_prompt.md first had it, to the millivolt."""
        rows = [dict(r, v_min=round(r["v_typ"] - 0.2, 3), v_max=round(r["v_typ"] + 0.2, 3))
                for r in zener_reference()["clamp_diode"]["reverse"]]
        got = [solve(change(d, clamp_diode__reverse=rows))["voltages"]["levels"]["max_input"]
               for d in (zener_reference(), results_design(3.0), results_design(4.1),
                         results_design(30))]
        assert [(f"{r['typ']:.3f}", f"{r['low']:.3f}", f"{r['high']:.3f}") for r in got] == [
            ("3.020", "2.820", "3.219"), ("1.928", "1.789", "2.054"),
            ("2.156", "1.990", "2.318"), ("3.106", "2.906", "3.307")]

    def test_first_row_by_hand(self):
        """At 3.02 V the diode current is (30 - 3.02)/10k - 3.02/18k = 2.53 mA,
        between the 2 mA (2.93 V) and 5 mA (3.28 V) points; the solved voltage
        is the table voltage at that current."""
        r = solve(zener_reference())
        v = r["voltages"]["levels"]["max_input"]["typ"]
        amps = (30 - v) / 10000 - v / 18000
        assert amps * 1000 == pytest.approx(2.53, abs=0.005)
        assert r["details"]["i_diode_ma"] == pytest.approx(amps * 1000)
        assert 0.002 < amps < 0.005
        reverse = zener_reference()["clamp_diode"]["reverse"]
        assert v == pytest.approx(table_voltage(reverse, "v_typ", amps), abs=2e-6)

    def test_verification_baseline(self):
        d = solve(zener_reference())["details"]
        assert d["r_total_ohms"] == pytest.approx(28000)
        assert round(d["k_nominal"], 3) == 0.643
        assert f"{d['v_pin_typ']:.2f}" == "3.02"
        assert f"{d['v_pin_high']:.2f}" == "3.24"
        assert f"{d['i_diode_ma']:.2f}" == "2.53"

    def test_lowest_and_highest_corners(self):
        """For the Zener to GND: lowest is R1 +1 %, R2 -1 %, minimum column;
        highest is R1 -1 %, R2 +1 %, maximum column."""
        c = prepare(zener_reference())
        row = solve(zener_reference())["voltages"]["levels"]["max_input"]
        assert row["low"] == c.node(30, 10100, 17820, "min")
        assert row["high"] == c.node(30, 9900, 18180, "max")

    def test_results_div_design_never_reads_high(self):
        """The shipped results.div design: 3.0 V Logic High gave 2.328 V and
        PASS with the old model; the pin is really below VIH 2.31 V."""
        design = change(results_design(30), system__v_logic_high_min=3.0)
        r = solve(design)
        assert r["voltages"]["levels"]["logic_high"]["typ"] == pytest.approx(1.928, abs=0.01)
        assert check(r, "logic_high")["status"] == FAIL
        assert r["verdict"] == FAIL

    def test_c3v3_typical_column_is_the_data_sheet_curve(self):
        with open(os.path.join(ROOT, "docs", "bzb984_fig7_typical.json"), encoding="utf-8") as f:
            data = json.load(f)
        assert [i * 1000 for i in data["current_a"]] == pytest.approx(C3V3_CURRENT_MA)
        assert data["typical_v"]["BZB984-C3V3"] == C3V3_TYPICAL_V
        rows = zener_reference()["clamp_diode"]["reverse"]
        assert [r["v_typ"] for r in rows] == C3V3_TYPICAL_V
        for r in rows:
            assert r["v_min"] == pytest.approx(r["v_typ"] - 0.18)
            assert r["v_max"] == pytest.approx(r["v_typ"] + 0.22)
        # Table 8: VZ 3.10 to 3.50 V at IZ = 5 mA
        assert [(r["v_min"], r["v_typ"], r["v_max"]) for r in rows if r["i_ma"] == 5] == [
            (3.10, 3.28, 3.50)]
        note = zener_reference()["clamp_diode"]["note"]
        for text in ("v_typ - 0.18 V", "v_typ + 0.22 V", "in every row", "Table 8",
                     "3.10 V min and 3.50 V max"):
            assert text in note


class TestSchottkyToRail:
    def test_hand_check_maximum_column(self):
        """VDD 3.3 V, 10 kΩ / 18 kΩ, 30 V in, maximum column: about 2.43 mA,
        about 0.35 V across the diode, about 3.65 V at the pin."""
        d = solve(schottky_rail())["details"]
        v = d["v_pin_diode_max"]
        amps = (30 - v) / 10000 - v / 18000
        assert v == pytest.approx(3.65, abs=0.01)
        assert amps * 1000 == pytest.approx(2.432, abs=0.001)
        assert v - 3.3 == pytest.approx(0.35, abs=0.01)
        forward = schottky_rail()["clamp_diode"]["forward"]
        assert v - 3.3 == pytest.approx(table_voltage(forward, "v_max", amps), abs=2e-6)

    def test_bat54cv_table_7_maximums(self):
        forward = schottky_rail()["clamp_diode"]["forward"]
        assert [(r["i_ma"], r["v_max"]) for r in forward] == [
            (0.1, 0.24), (1, 0.32), (10, 0.40), (30, 0.50), (100, 0.80)]
        assert schottky_rail()["clamp_diode"]["capacitance_pf"] == 10

    def test_rail_follows_vdd(self):
        a = solve(schottky_rail())["details"]["v_pin_typ"]
        b = solve(schottky_rail(mcu__vdd=5.0, mcu__v_recommended_max=5.3,
                                mcu__v_absolute_max=5.5))["details"]["v_pin_typ"]
        assert b - a == pytest.approx(1.7, abs=0.02)

    def test_leakage_lifts_the_pin_at_zero_input(self):
        """With no input the reverse table still conducts from the rail."""
        row = solve(schottky_rail())["voltages"]["levels"]["zero"]
        assert 0 < row["low"] < row["typ"] < row["high"] < 0.01
        no_leak = solve(schottky_rail(clamp_diode__reverse=[]))
        assert no_leak["voltages"]["levels"]["zero"]["high"] == 0.0

    def test_rail_current_is_information_only(self):
        r = solve(schottky_rail())
        d = r["details"]
        assert info(r, "rail_current")["value"] == d["rail_current_worst_ma"]
        assert d["rail_current_ma"] == pytest.approx(d["i_diode_ma"])
        assert d["rail_current_worst_ma"] >= d["rail_current_ma"] > 2.4
        assert all(c["id"] != "rail_current" for c in r["checks"])
        grounded = solve(zener_reference())
        assert all(i["id"] != "rail_current" for i in grounded["info"])
        assert grounded["details"]["rail_current_ma"] is None


# ── Wirings ──────────────────────────────────────────────────────────────────

WIRINGS = {
    "zener to GND": zener_reference,
    "schottky to rail": schottky_rail,
    "schottky to GND": schottky_gnd,
}


class TestWirings:
    def test_zener_to_gnd_clamps_high_inputs(self):
        row = solve(zener_reference())["voltages"]["levels"]["max_input"]
        assert row["high"] < 3.3 < 30 * 18 / 28

    def test_schottky_to_gnd_clamps_negative_inputs(self):
        r = solve(schottky_gnd(system__v_input_min=-5.0))
        row = r["voltages"]["levels"]["min_input"]
        assert -5 * 18 / 28 < -3
        assert -0.30 < row["low"] < row["typ"] < row["high"] < -0.05
        # ... and leaves a positive input to the divider (plus leakage to GND)
        top = r["voltages"]["levels"]["max_input"]["typ"]
        assert top == pytest.approx(30 * 18 / 28, abs=0.05)

    def test_zener_forward_direction_needs_forward_data(self):
        """An empty forward table means conduction below GND is not modelled:
        the pin follows the plain divider at a negative input."""
        r = solve(zener_reference(system__v_input_min=-5.0))
        assert r["details"]["forward_modelled"] is False
        assert r["details"]["reverse_modelled"] is True
        assert r["voltages"]["levels"]["min_input"]["typ"] == pytest.approx(-5 * 18 / 28)

    def test_empty_reverse_table_means_no_clamping(self):
        r = solve(zener_reference(clamp_diode__reverse=[]))
        assert r["voltages"]["levels"]["max_input"]["typ"] == pytest.approx(30 * 18 / 28)
        assert r["needs_input"] == []

    @pytest.mark.parametrize("name", list(WIRINGS))
    @pytest.mark.parametrize("case", ["typ", "low", "high"])
    def test_pin_voltage_never_falls_as_input_rises(self, name, case):
        circuit = prepare(WIRINGS[name]())
        v_in = [-12 + 0.11 * i for i in range(600)]          # -12 V to 54 V
        v_pin = [circuit.pin_voltage(x, case) for x in v_in]
        assert circuit.unsettled == []
        for a, b in zip(v_pin, v_pin[1:]):
            assert b >= a - clamp_solver.SOLVER_TOLERANCE_V

    def test_fourth_wiring_also_solves(self):
        """Anode at VDD, cathode at the node: not a clamp, but the same math."""
        d = schottky_rail(clamp_diode__anode="vdd", clamp_diode__cathode="node")
        circuit = prepare(d)
        v = [circuit.pin_voltage(x, "typ") for x in (-5, 0, 1, 5, 30)]
        assert v == sorted(v) and circuit.unsettled == []
        assert v[1] > 3.0                   # pulled up to about VDD - VF

    @pytest.mark.parametrize("label", ["zener", "schottky", None, "anything"])
    @pytest.mark.parametrize("name", list(WIRINGS))
    def test_type_is_only_a_label(self, name, label):
        base = WIRINGS[name]()
        assert solve(change(base, clamp_diode__type=label)) == solve(base)

    def test_solver_source_never_reads_type(self):
        import inspect
        src = inspect.getsource(clamp_solver)
        assert '"type"' not in src and "'type'" not in src
        assert "clamp_diode.type" not in src

    @pytest.mark.parametrize("anode,cathode", [("node", "node"), ("gnd", "vdd"),
                                               ("vdd", "gnd"), ("gnd", "gnd")])
    def test_wiring_needs_exactly_one_terminal_at_the_node(self, anode, cathode):
        assert set(wiring_problems(anode, cathode)) == {"anode", "cathode"}
        r = solve(zener_reference(clamp_diode__anode=anode, clamp_diode__cathode=cathode))
        assert r["voltages"]["levels"]["max_input"]["typ"] is None
        assert {"clamp_diode.anode", "clamp_diode.cathode"} <= set(r["needs_input"])

    def test_wiring_rules(self):
        assert wiring_problems("gnd", "node") == {}
        assert wiring_problems("node", "vdd") == {}
        assert wiring_problems(None, None) == {}
        assert wiring_problems("ground", "node") == {"anode": "expected node, gnd or vdd"}


# ── Diode tables ─────────────────────────────────────────────────────────────

ROWS = [{"i_ma": 1, "v_min": 0.9, "v_typ": 1.0, "v_max": 1.1},
        {"i_ma": 10, "v_min": 1.9, "v_typ": 2.0, "v_max": 2.1},
        {"i_ma": 100, "v_min": 2.4, "v_typ": 2.5, "v_max": 2.6}]


def curve(rows, column="v_typ"):
    return [(r[column], math.log(r["i_ma"] / 1000)) for r in rows]


class TestDiodeTable:
    def test_table_points(self):
        for row in ROWS:
            assert clamp_solver._curve_current(curve(ROWS), row["v_typ"]) \
                == pytest.approx(row["i_ma"] / 1000)

    def test_ln_current_is_linear_in_voltage_between_rows(self):
        # halfway in voltage is the geometric mean in current
        assert clamp_solver._curve_current(curve(ROWS), 1.5) == pytest.approx(
            math.sqrt(0.001 * 0.010))
        assert clamp_solver._curve_current(curve(ROWS), 2.25) == pytest.approx(
            math.sqrt(0.010 * 0.100))

    def test_first_and_last_segments_are_extended(self):
        # one decade per volt below the table, one decade per 0.5 V above it
        assert clamp_solver._curve_current(curve(ROWS), 0.5) == pytest.approx(0.001 / 10 ** 0.5)
        assert clamp_solver._curve_current(curve(ROWS), 3.0) == pytest.approx(1.0)

    def test_no_current_at_or_below_zero_volts_or_without_a_table(self):
        assert clamp_solver._curve_current(curve(ROWS), 0) == 0.0
        assert clamp_solver._curve_current(curve(ROWS), -1) == 0.0
        assert clamp_solver._curve_current(None, 2.0) == 0.0

    def test_steep_segment_extended_far_does_not_overflow(self):
        steep = [(6.85, math.log(0.005)), (6.87, math.log(0.010))]
        assert math.isfinite(clamp_solver._curve_current(steep, 60.0))

    def test_columns_pick_the_corner(self):
        d = zener_reference(clamp_diode__reverse=ROWS)
        c = prepare(d)
        lo, typ, hi = (c.node(30, 10000, 18000, col) for col in ("min", "typ", "max"))
        assert lo < typ < hi
        assert hi - lo == pytest.approx(0.2, abs=0.01)

    def test_good_table_has_no_problems(self):
        assert table_problems(ROWS) == []
        assert table_problems([]) == []
        assert table_problems(zener_reference()["clamp_diode"]["reverse"]) == []
        assert table_problems(schottky_rail()["clamp_diode"]["forward"]) == []
        assert table_problems(schottky_rail()["clamp_diode"]["reverse"]) == []

    @pytest.mark.parametrize("mutate,where,text", [
        (lambda t: t[1].__setitem__("i_ma", 0.5), "[1].i_ma", "row above"),
        (lambda t: t[2].update(v_min=1.95, v_typ=2.0), "[2].v_typ", "row above"),
        (lambda t: t[0].__setitem__("v_min", 1.05), "[0].v_min", "v_min ≤ v_typ ≤ v_max"),
        (lambda t: t[0].__setitem__("v_max", -1), "[0].v_max", "greater than 0"),
        (lambda t: t[0].__setitem__("i_ma", 0), "[0].i_ma", "greater than 0"),
        (lambda t: t[1].__setitem__("v_typ", "2"), "[1].v_typ", "expected a number"),
        (lambda t: t[1].__setitem__("v_typ", True), "[1].v_typ", "expected a number"),
        (lambda t: t.__setitem__(1, [10, 1.9, 2.0, 2.1]), "[1]", "expected an object"),
        (lambda t: t.__delitem__(slice(1, 3)), "", "at least 2 rows"),
    ])
    def test_table_problems(self, mutate, where, text):
        rows = [dict(r) for r in ROWS]
        mutate(rows)
        problems = dict(table_problems(rows))
        assert text in problems[where]

    def test_not_a_list(self):
        assert table_problems(None)[0][0] == ""
        assert table_problems({"rows": []})[0][0] == ""

    def test_blank_cell_blocks_only_its_column(self):
        d = zener_reference()
        d["clamp_diode"]["reverse"][3]["v_min"] = None
        assert table_problems(d["clamp_diode"]["reverse"]) == []
        r = solve(d)
        row = r["voltages"]["levels"]["max_input"]
        assert row["typ"] == pytest.approx(3.020, abs=0.01)
        assert row["low"] is None and row["high"] is None
        assert r["needs_input"] == ["clamp_diode.reverse[3].v_min"]
        assert r["details"]["v_pin_diode_max"] is not None
        assert check(r, "pin_max_safe")["status"] == NEEDS_INPUT

    def test_bad_cell_makes_the_column_unusable(self):
        d = zener_reference()
        d["clamp_diode"]["reverse"][5]["v_typ"] = 1.0      # below the row above
        r = solve(d)
        assert r["voltages"]["levels"]["max_input"]["typ"] is None
        assert "clamp_diode.reverse[5].v_typ" in r["needs_input"]

    def test_one_row_table_is_unusable(self):
        d = zener_reference()
        d["clamp_diode"]["forward"] = [dict(ROWS[0])]
        r = solve(d)
        assert r["voltages"]["levels"]["max_input"]["typ"] is None
        assert r["needs_input"] == ["clamp_diode.forward"]


# ── Bisection ────────────────────────────────────────────────────────────────

class TestBisection:
    @pytest.mark.parametrize("name", list(WIRINGS))
    @pytest.mark.parametrize("vin", [-5.0, 0.5, 3.0, 30.0])
    def test_root_within_one_nanovolt(self, name, vin):
        """The residual of the node equation changes sign within 1 nV of the
        returned voltage."""
        c = prepare(WIRINGS[name]())
        curves = c.v[clamp_solver.CURVE["typ"]]
        v, settled = clamp_solver._solve_node(vin, 10000, 18000, c.sign, c.v_ref, curves)
        assert settled

        def residual(x):
            vd = c.sign * (x - c.v_ref)
            i = clamp_solver._curve_current(curves["forward"], vd) if vd > 0 else \
                -clamp_solver._curve_current(curves["reverse"], -vd) if vd < 0 else 0.0
            return (vin - x) / 10000 - x / 18000 - c.sign * i
        assert clamp_solver.SOLVER_TOLERANCE_V == 1e-9
        assert residual(v - 1e-9) > 0 > residual(v + 1e-9)

    def test_low_value_divider_converges(self):
        r = solve(zener_reference(resistors__r1__value=100, resistors__r1__unit=OHM,
                                  resistors__r2__value=100, resistors__r2__unit=OHM))
        assert r["warnings"] == []
        v = r["details"]["v_pin_typ"]
        # far above the table: on the extended last segment (5 mA to 10 mA)
        amps = (30 - v) / 100 - v / 100
        assert v == pytest.approx(3.28 + 0.27 * math.log(amps / 0.005) / math.log(2), abs=2e-6)

    def test_megaohm_divider_converges(self):
        r = solve(zener_reference(resistors__r1__unit=MOHM, resistors__r2__unit=MOHM))
        assert r["warnings"] == []
        assert 1.0 < r["details"]["v_pin_typ"] < 2.0     # µA range of the table

    def test_zero_input_is_exactly_zero_for_a_gnd_diode(self):
        row = solve(zener_reference())["voltages"]["levels"]["zero"]
        assert row == {"v_in": 0.0, "typ": 0.0, "low": 0.0, "high": 0.0}

    def test_unbracketed_solve_is_flagged(self):
        curves = {"forward": None, "reverse": None}
        v, settled = clamp_solver._solve_node(float("nan"), 10000, 18000, -1.0, 0.0, curves)
        assert settled is False
        v, settled = clamp_solver._solve_node(30, 10000, 18000, -1.0, 0.0, curves)
        assert settled is True and v == pytest.approx(30 * 18 / 28, abs=1e-6)

    def test_did_not_settle_warning(self, monkeypatch):
        real = clamp_solver._solve_node
        monkeypatch.setattr(clamp_solver, "_solve_node",
                            lambda *a, **k: (real(*a, **k)[0], False))
        r = solve(zener_reference())
        assert len(r["warnings"]) == 1 and "did not settle" in r["warnings"][0]
        assert "Max Input 30 V (typical)" in r["warnings"][0]

    def test_no_warning_normally(self):
        for make in WIRINGS.values():
            assert solve(make())["warnings"] == []

    def test_only_one_bisection_loop(self):
        import inspect
        src = inspect.getsource(clamp_solver)
        assert src.count("range(SOLVER_MAX_ITERATIONS)") == 1

    def test_pin_voltage_function_agrees_with_the_results(self):
        d = zener_reference()
        row = solve(d)["voltages"]["levels"]["max_input"]
        assert pin_voltage(d, 30, "typ") == row["typ"]
        assert pin_voltage(d, 30, "low") == row["low"]
        assert pin_voltage(d, 30, "high") == row["high"]
        assert pin_voltage(change(d, resistors__r1__value=None), 30) is None


# ── Missing inputs: "needs input", and the rest still computes ───────────────

class TestNeedsInput:
    def test_blank_design(self):
        r = solve({})
        assert r["verdict"] == NEEDS_INPUT
        assert r["voltages"]["levels"]["max_input"] == {
            "v_in": None, "typ": None, "low": None, "high": None}
        assert all(c["status"] == NEEDS_INPUT for c in r["checks"])
        for path in ("resistors.r1.value", "clamp_diode.anode", "mcu.vdd",
                     "system.v_input_max"):
            assert path in r["needs_input"]
        d = r["details"]
        assert d["k_nominal"] is None and d["v_pin_typ"] is None and d["tau_ns"] is None

    @pytest.mark.parametrize("junk", [None, 5, "text", [], {"resistors": 3},
                                      {"clamp_diode": {"reverse": "x"}}])
    def test_junk_never_crashes(self, junk):
        assert solve(junk)["verdict"] == NEEDS_INPUT

    @pytest.mark.parametrize("value", [None, "3.3", True, float("nan"), float("inf"), -1, 0])
    def test_unusable_value_is_needs_input(self, value):
        r = solve(zener_reference(resistors__r1__value=value))
        assert r["details"]["k_nominal"] is None
        assert r["voltages"]["levels"]["max_input"]["typ"] is None
        assert "resistors.r1.value" in r["needs_input"]
        assert r["voltages"]["vih"] == pytest.approx(2.31)       # still computed

    def test_blank_vdd_blocks_only_what_uses_it(self):
        r = solve(zener_reference(mcu__vdd=None))
        d = r["details"]
        assert d["resolution_mv_per_lsb"] is None and d["analog_error_lsb"] is None
        assert d["v_pin_typ"] is not None and d["margin_abs_v"] is not None
        assert check(r, "pin_max_abs")["status"] == PASS
        assert check(r, "analog_range")["status"] == NEEDS_INPUT
        assert check(r, "logic_high")["status"] == NEEDS_INPUT
        assert r["needs_input"] == ["mcu.vdd"]

    def test_rail_diode_needs_vdd_for_every_voltage(self):
        r = solve(schottky_rail(mcu__vdd=None))
        assert r["voltages"]["levels"]["max_input"]["typ"] is None
        assert r["missing"]["max_input.typ"] == ["mcu.vdd"]
        assert r["details"]["k_nominal"] is not None

    def test_blank_tolerance_blocks_worst_case_only(self):
        r = solve(zener_reference(resistors__r2__tolerance_pct=None))
        row = r["voltages"]["levels"]["max_input"]
        assert row["typ"] is not None and row["low"] is None and row["high"] is None
        assert r["details"]["p_r1_mw"] is not None and r["details"]["p_r1_worst_mw"] is None
        assert r["needs_input"] == ["resistors.r2.tolerance_pct"]

    def test_blank_adc_bits_blocks_only_resolution_and_lsb(self):
        r = solve(zener_reference(mcu__adc_bits=None))
        d = r["details"]
        assert d["resolution_mv_per_lsb"] is None and d["analog_error_lsb"] is None
        assert d["analog_error_mv"] is not None
        assert r["missing"]["resolution"] == ["mcu.adc_bits"]
        assert r["verdict"] == FAIL                # logic_high of the baseline

    @pytest.mark.parametrize("bits", [10, 12, 16])
    def test_resolution_vref_over_2n(self, bits):
        d = solve(zener_reference(mcu__adc_bits=bits))["details"]
        assert d["resolution_mv_per_lsb"] == pytest.approx(3.3 / 2 ** bits * 1000 / (18 / 28))

    def test_blank_rating_has_no_status(self):
        r = solve(zener_reference(resistors__r1__rating_mw=None))
        assert check(r, "power_r1")["status"] == NEEDS_INPUT
        assert r["details"]["r1_margin_pct"] is None
        assert r["details"]["p_r1_worst_mw"] is not None
        assert r["missing"]["r1_margin"] == ["resistors.r1.rating_mw"]

    def test_zero_rating_is_unusable_not_a_crash(self):
        r = solve(zener_reference(clamp_diode__ptot_mw=0))
        assert r["details"]["diode_margin_pct"] is None
        assert r["details"]["v_pin_typ"] is not None

    def test_optional_values_are_not_asked_for(self):
        r = solve(schottky_rail())
        ids = [c["id"] for c in r["checks"]]
        assert "pin_min" not in ids and "frequency" not in ids
        assert set(r["voltages"]["levels"]) == {
            "zero", "logic_low", "logic_high", "analog_fullscale", "max_input"}
        assert r["needs_input"] == []
        no_analog = solve(schottky_rail(system__v_analog_fullscale=None))
        assert "analog_fullscale" not in no_analog["voltages"]["levels"]
        assert not [c for c in no_analog["checks"] if c["id"].startswith("analog")]
        assert no_analog["needs_input"] == []

    def test_factor_rules(self):
        r = solve(zener_reference(mcu__vil_factor=0.8))       # above VIH factor
        assert r["voltages"]["vil"] is None and r["voltages"]["vih"] is None
        r = solve(zener_reference(mcu__vil_factor=0.25, mcu__vih_factor=0.75))
        assert r["voltages"]["vil"] == pytest.approx(0.825)
        assert r["voltages"]["vih"] == pytest.approx(2.475)

    def test_results_are_json(self):
        for make in WIRINGS.values():
            text = json.dumps(solve(make()), allow_nan=False)
            assert json.loads(text)["solver_version"] == clamp_solver.SOLVER_VERSION
        json.dumps(solve({}), allow_nan=False)

    def test_solver_version_is_a_constant(self):
        assert clamp_solver.SOLVER_VERSION == "2.0.0"


class TestRules:
    @pytest.mark.parametrize("path,value,text", [
        ("resistors.r1.value", -5, "greater than 0"),
        ("resistors.r_series.value", -1, "negative"),
        ("resistors.r1.tolerance_pct", 150, "below 100"),
        ("resistors.r2.tolerance_pct", -1, "at least 0"),
        ("mcu.adc_bits", 0, "1 to 32"),
        ("mcu.adc_bits", 12.5, "whole number"),
        ("mcu.vil_factor", 1.5, "between 0 and 1"),
        ("mcu.v_pin_min", 0.3, "above 0"),
        ("bandwidth.margin_factor", 0.5, "1 or more"),
        ("system.v_touch", 0, "greater than 0"),
        ("mcu.vdd", "3.3", "expected a number"),
        ("mcu.vdd", True, "expected a number"),
        ("mcu.vdd", float("inf"), "finite"),
    ])
    def test_number_problem(self, path, value, text):
        assert text in number_problem(path, value)

    def test_blank_and_good_values_are_not_problems(self):
        for path in clamp_solver.NUMBER_RULES:
            assert number_problem(path, None) is None
        assert number_problem("mcu.vdd", 3.3) is None
        assert number_problem("mcu.v_pin_min", -0.3) is None
        assert number_problem("system.v_input_min", -24) is None
        assert number_problem("mcu.adc_bits", 12.0) is None

    def test_lowest_input_must_be_below_the_maximum(self):
        r = solve(zener_reference(system__v_input_min=31))
        assert "min_input" not in r["voltages"]["levels"]
        assert r["voltages"]["levels"]["max_input"]["typ"] is not None


# ── Series resistor ──────────────────────────────────────────────────────────

class TestSeriesResistor:
    @pytest.mark.parametrize("value", [None, 0])
    def test_blank_or_zero_means_none(self, value):
        r = solve(zener_reference(resistors__r_series=dict(
            value=value, unit=None, rating_mw=None, tolerance_pct=None)))
        d = r["details"]
        assert d["has_rs"] is False and r["needs_input"] == []
        assert d["p_rs_mw"] is None and d["p_rs_worst_mw"] is None
        assert d["r_source_ohms"] == pytest.approx(10000 * 18000 / 28000)
        assert "power_rs" not in [c["id"] for c in r["checks"]]
        assert not any(k.startswith(("p_rs", "rs_margin")) for k in r["missing"])

    def test_positive_needs_unit_rating_and_tolerance(self):
        r = solve(zener_reference(resistors__r_series__value=100,
                                  resistors__r_series__unit=None))
        assert r["details"]["r_source_ohms"] is None
        assert "resistors.r_series.unit" in r["needs_input"]
        r = solve(zener_reference(resistors__r_series__value=100))
        assert r["needs_input"] == ["resistors.r_series.rating_mw",
                                    "resistors.r_series.tolerance_pct"]
        assert r["details"]["p_rs_worst_mw"] is None
        assert r["details"]["p_rs_mw"] is not None       # typical needs no tolerance
        assert check(r, "power_rs")["status"] == NEEDS_INPUT
        assert r["details"]["r_source_ohms"] == pytest.approx(10000 * 18000 / 28000 + 100)

    def test_unusable_value_is_not_treated_as_no_resistor(self):
        r = solve(zener_reference(resistors__r_series__value="abc"))
        assert r["details"]["has_rs"] is True
        assert r["details"]["r_source_ohms"] is None
        assert "resistors.r_series.value" in r["needs_input"]


# ── Check 1: highest input against Safe Max and Absolute Max ─────────────────

def hot(**overrides):
    """Rail Schottky with a 1 kΩ R1: the pin goes well above VDD + 0.3 V."""
    return schottky_rail(resistors__r1__value=1, resistors__r1__rating_mw=2000, **overrides)


class TestHighestInput:
    def test_margins(self):
        r = solve(zener_reference())
        d = r["details"]
        assert d["margin_rec_v"] == pytest.approx(3.6 - d["v_pin_high"])
        assert d["margin_abs_v"] == pytest.approx(4.0 - d["v_pin_high"])
        assert check(r, "pin_max_safe") == {"id": "pin_max_safe", "status": PASS,
                                            "value": d["v_pin_high"], "limit": 3.6, "unit": "V"}
        assert check(r, "pin_max_abs")["status"] == PASS

    def test_thresholds_kept(self):
        """Safe Max: PASS from 50 mV of margin, TIGHT down to 0, FAIL below.
        Absolute Max: PASS from 100 mV."""
        high = solve(zener_reference())["details"]["v_pin_high"]

        def statuses(rec_margin, abs_margin):
            r = solve(zener_reference(mcu__v_recommended_max=high + rec_margin,
                                      mcu__v_absolute_max=high + abs_margin))
            return check(r, "pin_max_safe")["status"], check(r, "pin_max_abs")["status"]
        assert statuses(0.06, 0.11) == (PASS, PASS)
        assert statuses(0.04, 0.09) == (TIGHT, TIGHT)
        assert statuses(-0.01, -0.01) == (FAIL, FAIL)

    def test_no_injection_estimate(self):
        """There is no injection check, no injection result, no
        injection-limit input and no assumed 100 Ω."""
        r = solve(hot())
        assert "injection" not in [c["id"] for c in r["checks"]]
        assert not [k for k in r["details"] if "inj" in k]
        assert not [p for p in clamp_solver.NUMBER_RULES if "injection" in p]
        assert not hasattr(clamp_solver, "injection_current_ma")
        assert not hasattr(clamp_solver, "ESD_INTERNAL_OHMS")

    def test_safe_max_is_the_guard(self):
        """A pin above Safe Max (VDD + 0.3 V here) fails pin_max_safe."""
        r = solve(hot())
        assert r["details"]["v_pin_high"] > 3.7 > 3.6
        assert check(r, "pin_max_safe")["status"] == FAIL
        assert r["verdict"] == FAIL
        assert check(solve(zener_reference()), "pin_max_safe")["status"] == PASS


# ── Check 2: lowest input ────────────────────────────────────────────────────

class TestLowestInput:
    def test_only_when_given_and_negative(self):
        assert "pin_min" not in [c["id"] for c in solve(schottky_gnd())["checks"]]
        r = solve(schottky_gnd(system__v_input_min=0.5))
        assert "pin_min" not in [c["id"] for c in r["checks"]]
        assert r["voltages"]["levels"]["min_input"]["v_in"] == 0.5

    def test_pass_and_fail(self):
        r = solve(schottky_gnd(system__v_input_min=-5.0))
        low = r["voltages"]["levels"]["min_input"]["low"]
        assert check(r, "pin_min") == {"id": "pin_min", "status": PASS, "value": low,
                                       "limit": -0.3, "unit": "V"}
        r = solve(schottky_gnd(system__v_input_min=-5.0, mcu__v_pin_min=low + 0.001))
        assert check(r, "pin_min")["status"] == FAIL and r["verdict"] == FAIL

    def test_unclamped_negative_input_fails(self):
        r = solve(zener_reference(system__v_input_min=-5.0))      # no forward data
        assert check(r, "pin_min")["status"] == FAIL

    def test_needs_the_pin_minimum(self):
        r = solve(schottky_gnd(system__v_input_min=-5.0, mcu__v_pin_min=None))
        assert check(r, "pin_min")["status"] == NEEDS_INPUT
        assert r["needs_input"] == ["mcu.v_pin_min"]


# ── Check 3: logic levels ────────────────────────────────────────────────────

class TestLogicLevels:
    def test_lowest_pin_at_logic_high_against_vih(self):
        r = solve(schottky_rail())
        row = r["voltages"]["levels"]["logic_high"]
        assert check(r, "logic_high") == {"id": "logic_high", "status": PASS,
                                          "value": row["low"],
                                          "limit": pytest.approx(2.31), "unit": "V"}
        r = solve(schottky_rail(mcu__vih_factor=0.75))            # VIH 2.475 V
        assert check(r, "logic_high")["status"] == FAIL

    def test_highest_pin_at_logic_low_against_vil(self):
        r = solve(schottky_rail())
        row = r["voltages"]["levels"]["logic_low"]
        assert check(r, "logic_low")["value"] == row["high"]
        assert check(r, "logic_low")["status"] == PASS
        r = solve(schottky_rail(system__v_logic_low_max=1.6))     # pin about 1.04 V
        assert check(r, "logic_low")["status"] == FAIL

    def test_blank_factors_block_only_the_logic_checks(self):
        r = solve(schottky_rail(mcu__vil_factor=None, mcu__vih_factor=None))
        assert check(r, "logic_high")["status"] == NEEDS_INPUT
        assert check(r, "logic_low")["status"] == NEEDS_INPUT
        assert r["voltages"]["levels"]["logic_low"]["high"] is not None
        assert check(r, "pin_max_abs")["status"] == PASS


# ── Check 4: power ───────────────────────────────────────────────────────────

class TestPower:
    def test_typical_point(self):
        d = solve(zener_reference())["details"]
        v = d["v_pin_typ"]
        assert d["i_r1_ma"] == pytest.approx((30 - v) / 10)
        assert d["i_r2_ma"] == pytest.approx(v / 18)
        assert d["i_r1_ma"] == pytest.approx(d["i_r2_ma"] + d["i_diode_ma"])
        assert d["p_r1_mw"] == pytest.approx((30 - v) ** 2 / 10)
        assert d["p_r2_mw"] == pytest.approx(v ** 2 / 18)
        assert d["p_diode_mw"] == pytest.approx(v * d["i_diode_ma"])
        assert d["p_total_mw"] == pytest.approx(d["p_r1_mw"] + d["p_r2_mw"] + d["p_diode_mw"])

    def test_rail_diode_power_uses_the_voltage_across_the_diode(self):
        d = solve(schottky_rail())["details"]
        assert d["p_diode_mw"] == pytest.approx((d["v_pin_typ"] - 3.3) * d["i_diode_ma"])

    @pytest.mark.parametrize("design", [
        zener_reference(), schottky_rail(), hot(),
        zener_reference(resistors__r1__value=4.7, system__v_input_max=24),
        zener_reference(system__v_input_max=60)])
    def test_worst_at_least_typical_for_each_part(self, design):
        d = solve(design)["details"]
        for part in ("r1", "r2", "diode"):
            assert d[f"p_{part}_worst_mw"] >= d[f"p_{part}_mw"], part

    def test_hand_checked_r1_corner(self):
        """Baseline: R1 dissipates most with R1 min 9.9 kΩ, R2 min 17.82 kΩ and
        the minimum column (lowest pin voltage, most current)."""
        r = solve(zener_reference())
        d = r["details"]
        v = prepare(zener_reference()).node(30, 9900, 17820, "min")
        amps = (30 - v) / 9900 - v / 17820
        reverse = zener_reference()["clamp_diode"]["reverse"]
        assert v == pytest.approx(table_voltage(reverse, "v_min", amps), abs=2e-6)
        assert d["p_r1_worst_mw"] == pytest.approx((30 - v) ** 2 / 9.9)
        assert d["p_r1_worst_mw"] == pytest.approx(74.47, abs=0.01)
        assert d["worst_power_corner"]["r1"] == "R1 min, R2 min, diode min"

    def test_series_resistor_power(self):
        """Pin held at 0 V: the whole node voltage is across R_s. Typical:
        V_typ^2 / R_s. Worst case: V_node,max^2 / R_s,min."""
        rs = dict(value=1, unit=KOHM, rating_mw=20, tolerance_pct=5)
        d = solve(hot(resistors__r_series=rs))["details"]
        assert d["i_rs_ma"] == pytest.approx(d["v_pin_typ"] / 1000 * 1000)
        assert d["p_rs_mw"] == pytest.approx(d["v_pin_typ"] ** 2 / 1000 * 1000)
        assert d["p_rs_worst_mw"] == pytest.approx(d["v_pin_high"] ** 2 / 950 * 1000)
        assert d["p_rs_worst_mw"] >= d["p_rs_mw"]
        assert d["rs_margin_worst_pct"] == pytest.approx((20 - d["p_rs_worst_mw"]) / 20 * 100)
        assert d["rs_margin_pct"] == pytest.approx((20 - d["p_rs_mw"]) / 20 * 100)
        assert "R_s min 950 Ω, pin at 0 V" in d["worst_power_corner"]["rs"]

    def test_series_resistor_power_on_the_baseline(self):
        """Baseline with R_s 100 Ω at 10 %: 3.239 V^2 / 90 Ω = 116.6 mW. No
        100 Ω term and no VDD in the formula."""
        rs = dict(value=100, unit=OHM, rating_mw=250, tolerance_pct=10)
        r = solve(zener_reference(resistors__r_series=rs))
        d = r["details"]
        assert d["p_rs_worst_mw"] == pytest.approx(d["v_pin_high"] ** 2 / 90 * 1000)
        assert d["p_rs_worst_mw"] == pytest.approx(116.6, abs=0.1)
        assert check(r, "power_rs") == {"id": "power_rs", "status": PASS,
                                        "value": d["p_rs_worst_mw"], "limit": 250,
                                        "unit": "mW"}
        no_vdd = solve(zener_reference(resistors__r_series=rs, mcu__vdd=None))
        assert no_vdd["details"]["p_rs_worst_mw"] == d["p_rs_worst_mw"]

    def test_margins_and_thresholds_kept(self):
        """PASS above 20 %, TIGHT from 0 to 20 %, FAIL at or below 0 %; the
        verdict comes from the worst-case margin."""
        d = solve(zener_reference())["details"]
        assert d["r1_margin_pct"] == pytest.approx((200 - d["p_r1_mw"]) / 200 * 100)
        assert d["r1_margin_worst_pct"] == pytest.approx((200 - d["p_r1_worst_mw"]) / 200 * 100)
        p = d["p_diode_worst_mw"]
        for rating, status in ((p / 0.79, PASS), (p / 0.9, TIGHT), (p, FAIL), (p * 0.9, FAIL)):
            r = solve(zener_reference(clamp_diode__ptot_mw=rating))
            assert check(r, "power_diode")["status"] == status
            assert r["details"]["power_verdict"] == status

    def test_typical_passes_worst_fails_gives_fail(self):
        wide = dict(resistors__r1__tolerance_pct=25, resistors__r2__tolerance_pct=25)
        p_typ = solve(zener_reference(**wide))["details"]["p_r1_mw"]
        r = solve(zener_reference(**wide, resistors__r1__rating_mw=1.3 * p_typ))
        d = r["details"]
        assert d["r1_margin_pct"] > 20 and d["r1_margin_worst_pct"] <= 0
        assert check(r, "power_r1")["status"] == FAIL
        assert d["power_verdict"] == FAIL

    def test_power_verdict(self):
        assert solve(schottky_rail())["details"]["power_verdict"] == PASS
        r = solve(schottky_rail(resistors__r2__rating_mw=None))
        assert r["details"]["power_verdict"] == NEEDS_INPUT

    def test_series_resistor_counts_in_verdict(self):
        rs = dict(value=1, unit=KOHM, rating_mw=1000, tolerance_pct=5)
        ok = solve(hot(resistors__r_series=rs))
        assert ok["details"]["power_verdict"] == PASS
        rs["rating_mw"] = ok["details"]["p_rs_worst_mw"] * 0.9
        r = solve(hot(resistors__r_series=rs))
        assert check(r, "power_rs")["status"] == FAIL
        assert r["details"]["power_verdict"] == FAIL


# ── Check 5: analog ──────────────────────────────────────────────────────────

class TestAnalog:
    def test_error_is_with_diode_minus_without(self):
        design = schottky_rail()
        r = solve(design)
        d = r["details"]
        ideal = 5.1 * 18 / 28
        c = prepare(design)
        errors = [c.node(5.1, 10000, 18000, col) - ideal for col in ("min", "max")]
        worst = max(errors, key=abs)
        assert d["analog_ideal_v"] == pytest.approx(ideal)
        assert d["analog_error_mv"] == pytest.approx(worst * 1000)
        assert d["analog_error_pct"] == pytest.approx(worst / ideal * 100)
        assert d["analog_error_lsb"] == pytest.approx(worst / (3.3 / 4096))
        assert d["analog_error_column"] == "min"          # the leakiest column
        assert d["analog_error_mv"] > 0                   # leakage lifts the pin

    def test_zener_pulls_the_reading_down(self):
        d = solve(zener_reference())["details"]
        assert d["analog_error_pct"] < -30                # 5.1 V full scale is clamped
        assert d["analog_error_column"] == "min"

    def test_information_only_without_an_allowed_error(self):
        r = solve(schottky_rail())
        c = check(r, "analog_error")
        assert c["status"] is None and c["limit"] is None and c["unit"] == "%"
        assert c["value"] == r["details"]["analog_error_pct"]

    def test_status_with_an_allowed_error(self):
        pct = solve(schottky_rail())["details"]["analog_error_pct"]
        r = solve(schottky_rail(system__analog_error_allowed_pct=pct * 1.01))
        assert check(r, "analog_error")["status"] == PASS
        r = solve(schottky_rail(system__analog_error_allowed_pct=pct * 0.99))
        assert check(r, "analog_error")["status"] == FAIL
        assert check(r, "analog_error")["limit"] == pytest.approx(pct * 0.99)

    def test_negative_error_compared_by_size(self):
        r = solve(zener_reference(system__analog_error_allowed_pct=1.0))
        assert check(r, "analog_error")["status"] == FAIL

    def test_range_against_vdd(self):
        """PASS up to VDD, FAIL above it: there is no TIGHT band."""
        r = solve(zener_reference())
        row = r["voltages"]["levels"]["analog_fullscale"]
        assert check(r, "analog_range") == {"id": "analog_range", "status": PASS,
                                            "value": row["high"], "limit": 3.3, "unit": "V"}
        r = solve(schottky_rail())               # 5.1 V: R1 -1 %, R2 +1 % gives 3.3013 V
        assert 3.3 < r["voltages"]["levels"]["analog_fullscale"]["high"] < 3.302
        assert check(r, "analog_range")["status"] == FAIL
        r = solve(schottky_rail(system__v_analog_fullscale=5.0))
        assert r["voltages"]["levels"]["analog_fullscale"]["high"] <= 3.3
        assert check(r, "analog_range")["status"] == PASS

    def test_range_does_not_use_safe_max(self):
        r = solve(schottky_rail(mcu__v_recommended_max=None))
        assert check(r, "analog_range")["status"] == FAIL
        for safe_max in (3.31, 5.0):
            r = solve(schottky_rail(mcu__v_recommended_max=safe_max))
            assert check(r, "analog_range")["status"] == FAIL


# ── Check 6: frequency ───────────────────────────────────────────────────────

class TestFrequency:
    def test_time_constant_uses_maximum_resistances(self):
        d = solve(schottky_rail())["details"]
        assert d["c_total_pf"] == 10 + 5 + 3
        r_tau = 10100 * 18180 / (10100 + 18180)
        assert d["tau_ns"] == pytest.approx(r_tau * 18e-12 * 1e9)
        rs = dict(value=100, unit=OHM, rating_mw=250, tolerance_pct=5)
        d = solve(schottky_rail(resistors__r_series=rs))["details"]
        assert d["tau_ns"] == pytest.approx((r_tau + 105) * 18e-12 * 1e9)

    def test_edge_times(self):
        """An edge from A towards B crosses T after tau x ln((B - A)/(B - T)).
        Rising: A = 0, B = lowest pin at Logic High, T = VIH. Falling: A =
        highest pin at the maximum input, B = highest pin at Logic Low, T = VIL."""
        r = solve(schottky_rail())
        d, lv = r["details"], r["voltages"]["levels"]
        tau = d["tau_ns"]
        b = lv["logic_high"]["low"]
        assert d["t_rise_ns"] == pytest.approx(tau * math.log((b - 0) / (b - 2.31)))
        a, b = lv["max_input"]["high"], lv["logic_low"]["high"]
        assert d["t_fall_ns"] == pytest.approx(tau * math.log((b - a) / (b - 0.99)))
        assert d["t_edge_ns"] == max(d["t_rise_ns"], d["t_fall_ns"])

    def test_limits(self):
        r = solve(schottky_rail())
        d = r["details"]
        shortest = d["t_edge_ns"] + 17.65
        assert d["t_pulse_shortest_ns"] == pytest.approx(shortest)
        assert d["f_may_work_hz"] == pytest.approx(1 / (2 * shortest * 1e-9))
        assert d["f_reliable_hz"] == pytest.approx(d["f_may_work_hz"] / 1.5)
        assert info(r, "f_may_work") == {"id": "f_may_work", "value": d["f_may_work_hz"],
                                         "unit": "Hz"}
        assert info(r, "f_reliable")["value"] == d["f_reliable_hz"]
        assert d["frequency_note"] is None
        assert f"{d['f_may_work_hz'] / 1e6:.3f}" == "1.347"       # as measured
        assert f"{d['f_reliable_hz'] / 1e6:.3f}" == "0.898"

    def test_margin_factor(self):
        a = solve(schottky_rail())["details"]
        b = solve(schottky_rail(bandwidth__margin_factor=2))["details"]
        assert b["f_may_work_hz"] == a["f_may_work_hz"]
        assert b["f_reliable_hz"] == pytest.approx(a["f_may_work_hz"] / 2)

    def test_required_frequency_statuses(self):
        d = solve(schottky_rail())["details"]
        reliable, may_work = d["f_reliable_hz"], d["f_may_work_hz"]
        for f, status in ((reliable * 0.99, PASS), (reliable, PASS),
                          ((reliable + may_work) / 2, TIGHT), (may_work, TIGHT),
                          (may_work * 1.01, FAIL)):
            r = solve(schottky_rail(system__f_required_hz=f))
            assert check(r, "frequency") == {"id": "frequency", "status": status, "value": f,
                                             "limit": reliable, "unit": "Hz"}

    def test_no_frequency_check_without_a_required_frequency(self):
        r = solve(schottky_rail())
        assert "frequency" not in [c["id"] for c in r["checks"]]

    def test_pin_never_reads_high(self):
        """The baseline: 3.8 V Logic High leaves the pin below VIH."""
        r = solve(zener_reference(system__f_required_hz=1000))
        d = r["details"]
        assert "never reads high" in d["frequency_note"]
        assert d["f_may_work_hz"] is None and d["f_reliable_hz"] is None
        assert d["t_rise_ns"] is None and d["t_edge_ns"] is None
        assert d["tau_ns"] is not None and d["c_total_pf"] == 458
        assert info(r, "f_may_work")["value"] is None
        assert check(r, "frequency")["status"] == FAIL
        assert "f_limits" not in r["missing"]

    def test_pin_never_reads_low(self):
        d = solve(schottky_rail(system__v_logic_low_max=1.6))["details"]
        assert "never reads low" in d["frequency_note"]
        assert d["f_may_work_hz"] is None

    def test_zener_design_that_reads_high(self):
        r = solve(zener_reference(system__v_logic_high_min=24))
        d = r["details"]
        assert check(r, "logic_high")["status"] == PASS
        r_tau = 10100 * 18180 / (10100 + 18180)
        assert d["tau_ns"] == pytest.approx(r_tau * 458e-12 * 1e9)
        assert d["f_may_work_hz"] == pytest.approx(
            1 / (2 * (d["t_edge_ns"] + 17.65) * 1e-9))

    @pytest.mark.parametrize("key,path", [
        ("clamp_diode__capacitance_pf", "clamp_diode.capacitance_pf"),
        ("mcu__c_pin_pf", "mcu.c_pin_pf"),
        ("bandwidth__c_stray_pf", "bandwidth.c_stray_pf"),
        ("mcu__t_pulse_min_ns", "mcu.t_pulse_min_ns"),
        ("bandwidth__margin_factor", "bandwidth.margin_factor"),
    ])
    def test_blank_input_blocks_the_limits(self, key, path):
        r = solve(schottky_rail(system__f_required_hz=1000, **{key: None}))
        assert r["details"]["f_may_work_hz"] is None
        assert r["details"]["frequency_note"] is None
        assert r["needs_input"] == [path]
        assert check(r, "frequency")["status"] == NEEDS_INPUT
        assert r["voltages"]["levels"]["max_input"]["typ"] is not None

    def test_zero_capacitance_and_zero_pulse_width(self):
        d = solve(schottky_rail(clamp_diode__capacitance_pf=0, mcu__c_pin_pf=0,
                                bandwidth__c_stray_pf=0, mcu__t_pulse_min_ns=0))["details"]
        assert d["f_may_work_hz"] is None and "both 0" in d["frequency_note"]

    def test_removed_limits_are_gone(self):
        d = solve(schottky_rail())["details"]
        for old in ("f_3db_hz", "t_rise_10_90_ns", "f_max_analog_hz", "f_max_practical_hz",
                    "f_max_overflow_hz", "limiting_factor", "min_sample_cycles"):
            assert old not in d


# ── Information rows and the overall verdict ─────────────────────────────────

class TestInfoAndVerdict:
    def test_touch_voltage(self):
        design = zener_reference(system__v_touch=60)
        r = solve(design)
        d = r["details"]
        c = prepare(design)
        corners = c.corners(60)
        assert d["touch_pin_high_v"] == max(x["v"] for x in corners)
        assert d["touch_pin_high_v"] == r["voltages"]["levels"]["touch"]["high"]
        points = [c.point(60, x["r1"], x["r2"], x["v"]) for x in corners]
        assert d["touch_diode_ma"] == pytest.approx(max(p["i_diode"] for p in points) * 1000)
        assert d["touch_r1_mw"] == pytest.approx(max(p["p_r1"] for p in points) * 1000)
        assert info(r, "touch_pin_high")["value"] == d["touch_pin_high_v"]
        assert info(r, "touch_diode_current")["unit"] == "mA"
        assert info(r, "touch_r1_power")["unit"] == "mW"
        assert d["touch_r1_mw"] > 200                    # above the 200 mW rating ...
        assert check(r, "power_r1")["status"] == PASS     # ... but not a check

    def test_touch_rows_do_not_change_the_verdict(self):
        base = solve(schottky_rail())
        touched = solve(schottky_rail(system__v_touch=60))
        assert touched["checks"] == base["checks"]
        assert touched["verdict"] == base["verdict"]
        assert not [i for i in base["info"] if i["id"].startswith("touch")]

    def test_worst_status_order(self):
        assert worst_status([PASS, PASS]) == PASS
        assert worst_status([PASS, TIGHT, None]) == TIGHT
        assert worst_status([TIGHT, NEEDS_INPUT]) == NEEDS_INPUT
        assert worst_status([NEEDS_INPUT, FAIL, PASS]) == FAIL
        assert worst_status([None]) is None

    def test_verdict_is_the_worst_check_status(self):
        for design in (zener_reference(), schottky_rail(), hot(),
                       schottky_rail(mcu__v_recommended_max=3.7),
                       schottky_rail(mcu__adc_bits=None, mcu__v_recommended_max=3.7)):
            r = solve(design)
            assert r["verdict"] == worst_status(c["status"] for c in r["checks"])

    def test_verdicts_of_the_two_reference_designs(self):
        z = solve(zener_reference())
        assert z["verdict"] == FAIL
        assert [c["id"] for c in z["checks"] if c["status"] == FAIL] == ["logic_high"]
        s = solve(schottky_rail())
        assert [c["id"] for c in s["checks"] if c["status"] == FAIL] == [
            "pin_max_safe", "analog_range"]
        passing = solve(schottky_rail(mcu__v_recommended_max=3.71, mcu__v_absolute_max=4.0,
                                      system__v_analog_fullscale=None))
        assert passing["verdict"] == PASS

    def test_check_ids(self):
        r = solve(schottky_gnd(system__v_input_min=-5, system__f_required_hz=1000,
                               resistors__r_series=dict(value=100, unit=OHM, rating_mw=100,
                                                        tolerance_pct=1)))
        assert [c["id"] for c in r["checks"]] == [
            "pin_max_safe", "pin_max_abs", "pin_min", "logic_high",
            "logic_low", "power_r1", "power_r2", "power_diode", "power_rs",
            "analog_range", "analog_error", "frequency"]
        for c in r["checks"]:
            assert set(c) == {"id", "status", "value", "limit", "unit"}


# ── Standard library only ────────────────────────────────────────────────────

def test_solver_runs_without_numpy_or_ui_packages():
    """The skill calls the solver under a plain Python install."""
    code = (
        "import sys\n"
        "for name in ('numpy', 'customtkinter', 'matplotlib', 'PIL', 'tkinter'):\n"
        "    sys.modules[name] = None\n"
        "from src.models import clamp_solver\n"
        "r = clamp_solver.solve({})\n"
        "assert r['verdict'] == 'needs input'\n"
        "print('ok')\n")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "ok"


def test_solver_imports_only_the_standard_library():
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(clamp_solver))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module.split(".")[0])
    assert imported == {"__future__", "math"}
