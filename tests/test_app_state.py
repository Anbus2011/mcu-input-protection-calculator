"""
AppState tests: parsing, "needs input", range checks, the clamp-diode
tables, frequency inputs, save and load of .div format 2.0, and the plot
sweep.
Run with: python -m pytest tests/ -v
"""
import copy
import inspect
import json
import os

import pytest

from src.core import app_state as app_state_module
from src.core import constants, div_format
from src.core.app_state import AppState, LoadError, FIELDS, BANDWIDTH_KEYS, path_label
from src.core.constants import BANDWIDTH_STARTING_VALUES
from src.models.clamp_solver import FAIL, NEEDS_INPUT, PASS, pin_voltage, prepare, solve
from tests.designs import (
    KOHM, MOHM, OHM, V1_FILE, app_state, blank_design, change, schottky_gnd,
    schottky_rail, typed, zener_reference,
)

EXAMPLES = os.path.join(os.path.dirname(__file__), "..", "examples")
ZENER_DIV = os.path.join(EXAMPLES, "zener_gnd_bzb984_c3v3.div")
SCHOTTKY_DIV = os.path.join(EXAMPLES, "schottky_rail_bat54cv.div")


def ref_state():
    """The baseline, entered the way the user would type it."""
    return app_state()


def write_json(tmp_path, data, name="d.div"):
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


def saved(s, tmp_path, name="s.div"):
    path = str(tmp_path / name)
    assert s.save_to_file(path), s.last_save_error
    return json.loads(open(path, encoding="utf-8").read())


# ── Reference case through AppState ──────────────────────────────────────────

def test_reference_case_through_app_state():
    s = ref_state()
    d = s.details
    assert d["r_total_ohms"] == pytest.approx(28000)
    assert round(d["k_nominal"], 3) == 0.643
    assert round(d["v_pin_typ"], 2) == 3.02
    assert round(d["v_pin_high"], 2) == 3.24
    assert round(d["i_diode_ma"], 1) == 2.5
    assert s.report.lines() == []


def test_app_state_calls_the_one_solver():
    """AppState, divcheck and the tests all get their numbers from solve()."""
    s = ref_state()
    assert s.results == solve(s.design)
    assert s.results["details"]["v_pin_typ"] == solve(zener_reference())["details"]["v_pin_typ"]
    src = inspect.getsource(app_state_module)
    assert "solver.solve(self.design)" in src
    assert "math.log" not in src and "math.exp" not in src


# ── Frequency inputs: derivation, starting values, save/load ─────────────────

class TestFrequencyInputs:
    def test_tau_resistance_is_parallel_of_maximums_plus_rs_max(self):
        """Rewritten: tau now uses R1 max, R2 max and R_s max."""
        s = app_state(schottky_rail())
        r_par = 10100 * 18180 / 28280
        assert s.details["tau_ns"] == pytest.approx(r_par * 18 * 1e-3)
        s.set_fields({"rs.value": "100", "rs.rating": "250", "rs.tol": "5"})
        assert s.details["tau_ns"] == pytest.approx((r_par + 105) * 18 * 1e-3)

    def test_rs_zero_still_gives_limits(self):
        """The Schottky example has R_s = 0; the tab must not be blank."""
        s = AppState()
        s.open_file(SCHOTTKY_DIV)
        d = s.details
        assert d["tau_ns"] and d["tau_ns"] > 0
        assert d["f_may_work_hz"] is not None and d["f_reliable_hz"] is not None

    def test_vil_vih_are_factor_times_vdd_without_3v3_scaling(self):
        s = ref_state()
        s.set_fields({"mcu.vdd": "5.0", "mcu.v_recommended_max": "5.3",
                      "mcu.v_absolute_max": "5.5"})
        assert s.results["voltages"]["vil"] == pytest.approx(1.5)
        assert s.results["voltages"]["vih"] == pytest.approx(3.5)

    def test_high_level_is_lowest_pin_voltage_at_logic_high_input(self):
        s = app_state(schottky_rail())
        expected = pin_voltage(s.design, 3.8, "low")
        assert s.check("logic_high")["value"] == pytest.approx(expected)
        assert s.check("logic_high")["value"] != pytest.approx(3.3)   # not VDD

    def test_pin_never_reads_high_is_reported_not_replaced(self):
        s = ref_state()                                   # pin 1.83 V < VIH 2.31 V
        assert s.details["f_may_work_hz"] is None and s.details["f_reliable_hz"] is None
        assert "never reads high" in s.details["frequency_note"]
        assert s.details["tau_ns"] is not None

    def test_blank_derived_input_names_the_upstream_field(self):
        s = app_state(schottky_rail())
        s.set_field("mcu.vih_factor", "")
        assert "mcu.vih_factor" in s.missing_paths("f_limits")
        assert "VIH factor" in s.report.needs
        s.set_fields({"mcu.vih_factor": "0.7", "diode.capacitance_pf": ""})
        assert s.report.needs == ["C_diode"]
        assert s.details["f_may_work_hz"] is None and s.details["v_pin_typ"] is not None


class TestBandwidthStartingValues:
    def test_new_design_has_visible_starting_values(self):
        s = AppState()
        for name, v in BANDWIDTH_STARTING_VALUES.items():
            assert s.fields[f"bw.{name}"] == str(v)

    def test_margin_factor_starting_value(self):
        """Rewritten (was: C_diode starting value). The diode capacitance and
        the pin capacitance are part data now, not starting values. The margin
        factor starts at 1.5: owner's example, 1 MHz reliable, 1.5 MHz may work."""
        assert BANDWIDTH_STARTING_VALUES == {"c_stray_pf": 3, "margin_factor": 1.5}
        assert BANDWIDTH_KEYS == ["bw.c_stray_pf", "bw.margin_factor"]
        src = inspect.getsource(constants)
        assert "# owner's example, 2026-11-09: 1 MHz reliable, 1.5 MHz may work\n" \
               "    \"margin_factor\": 1.5," in src
        s = AppState()
        assert s.fields["diode.capacitance_pf"] == "" and s.fields["mcu.c_pin_pf"] == ""
        assert 1.5e6 / 1.5 == 1e6

    def test_save_and_load_bandwidth_key(self, tmp_path):
        s = ref_state()
        s.set_fields({"bw.c_stray_pf": "7", "bw.margin_factor": "2"})
        path = str(tmp_path / "bw.div")
        assert s.save_to_file(path)
        data = json.loads(open(path, encoding="utf-8").read())
        assert data["bandwidth"] == {"c_stray_pf": 7, "margin_factor": 2}
        s2 = AppState()
        s2.open_file(path)
        assert s2.fields["bw.c_stray_pf"] == "7"
        assert s2.fields["bw.margin_factor"] == "2"

    def test_blank_bandwidth_values_load_blank(self, tmp_path):
        """Rewritten: a file must have the bandwidth section; null values in
        it load blank (the starting values are not put back by themselves)."""
        s = AppState()
        data = zener_reference(bandwidth__c_stray_pf=None, bandwidth__margin_factor=None)
        warnings = s.open_file(write_json(tmp_path, data))
        for key in BANDWIDTH_KEYS:
            assert s.fields[key] == "", key
        assert "C_stray" in warnings[0]
        del data["bandwidth"]
        with pytest.raises(LoadError) as exc:
            s.open_file(write_json(tmp_path, data, "nobw.div"))
        assert str(exc.value).startswith("bandwidth: missing")

    def test_fill_only_blank_or_unreadable(self):
        s = AppState()
        s.set_fields({"bw.c_stray_pf": "abc", "bw.margin_factor": "2"})
        s.is_dirty = False
        filled = s.fill_bandwidth_starting_values()
        assert s.fields["bw.c_stray_pf"] == "3"
        assert s.fields["bw.margin_factor"] == "2"
        assert filled == ["C_stray"]
        assert s.is_dirty
        s.set_fields({"bw.c_stray_pf": "", "bw.margin_factor": ""})
        assert set(s.fill_bandwidth_starting_values()) == {"C_stray", "Margin factor"}
        assert s.fill_bandwidth_starting_values() == []


# ── Every field edit recalculates and marks unsaved ──────────────────────────

class TestEditsMarkDirty:
    def test_rating_edit_updates_margin_and_dirty(self):
        s = ref_state()
        s.is_dirty = False
        before = s.details["r1_margin_pct"]
        s.set_field("r1.rating", "75")
        assert s.is_dirty
        assert s.details["r1_margin_pct"] != before
        assert s.details["r1_margin_pct"] == pytest.approx((75 - s.details["p_r1_mw"]) / 75 * 100)

    @pytest.mark.parametrize("key", [k for k in FIELDS])
    def test_every_field_marks_dirty(self, key):
        s = AppState()
        kind = FIELDS[key].kind
        s.set_field(key, "1" if kind == "bool" else MOHM if kind == "unit"
                    else FIELDS[key].choices[0] if kind == "choice" else "7")
        assert s.is_dirty

    def test_same_text_is_not_a_change(self):
        s = AppState()
        s.set_field("r1.unit", s.fields["r1.unit"])
        s.set_field("diode.checked", "0")
        assert not s.is_dirty


# ── No hidden defaults ───────────────────────────────────────────────────────

class TestNoHiddenDefaults:
    def test_app_starts_blank(self):
        s = AppState()
        for key, spec in FIELDS.items():
            if key.startswith("bw.") or spec.kind == "unit":
                continue
            assert s.fields[key] == ("0" if spec.kind == "bool" else ""), key
        assert s.tables == {"forward": None, "reverse": None}      # blank, not "not modelled"
        assert s.table_state("forward") == s.table_state("reverse") == "blank"
        assert "Forward table" in s.report.needs and "Reverse table" in s.report.needs
        assert s.circuit.v["resistors.r1"] is None and s.design["mcu"]["vdd"] is None
        assert s.design["clamp_diode"]["anode"] is None
        assert s.design["system"]["v_input_max"] is None
        assert s.details["v_pin_typ"] is None
        assert s.results["verdict"] == NEEDS_INPUT

    def test_new_design_is_blank(self):
        s = ref_state()
        s.file_new()
        assert s.fields["r1.value"] == "" and s.fields["diode.part"] == ""
        assert s.tables == {"forward": None, "reverse": None}
        assert s.details["k_nominal"] is None and not s.is_dirty

    def test_blank_vdd_shows_needs_input_but_rest_computes(self):
        s = ref_state()
        s.set_field("mcu.vdd", "")
        d = s.details
        assert d["resolution_mv_per_lsb"] is None
        assert s.check("logic_high")["status"] == NEEDS_INPUT
        assert d["v_pin_typ"] is not None and d["margin_abs_v"] is not None
        assert s.report.needs == ["VDD/VDDA"]

    def test_labels_and_notes_block_nothing(self):
        """Rewritten (was: blank ZZK blocks nothing). The part names, the
        type, the pin type, sources, notes and the "checked" boxes are not
        used by any result."""
        s = ref_state()
        before = copy.deepcopy(s.results)
        s.set_fields({"diode.part": "", "diode.type": "", "diode.source": "",
                      "diode.note": "", "mcu.part": "", "mcu.pin_type": "",
                      "mcu.source": "", "mcu.note": "", "diode.checked": "1"})
        assert s.report.needs == []
        assert s.results == before

    def test_blank_minimum_cell_needed_only_for_worst_case(self):
        """Rewritten (was: blank VZ min needed only for worst-case power)."""
        s = ref_state()
        s.set_cell("reverse", 3, "v_min", "")
        assert s.report.needs == ["Reverse table row 4 V min"]
        assert s.details["p_r1_worst_mw"] is None and s.details["v_pin_high"] is None
        assert s.details["v_pin_typ"] is not None and s.details["p_r1_mw"] is not None
        assert s.details["v_pin_diode_max"] is not None

    def test_saved_blank_is_null(self, tmp_path):
        s = AppState()
        data = saved(s, tmp_path, "blank.div")
        assert data["resistors"]["r1"]["value"] is None
        assert data["mcu"]["vdd"] is None
        assert data["clamp_diode"]["type"] is None and data["clamp_diode"]["anode"] is None
        assert data["clamp_diode"]["forward"] is None and data["clamp_diode"]["reverse"] is None
        assert data["clamp_diode"]["checked"] is False
        assert data["system"]["v_touch"] is None
        assert div_format.validate(data) == []

    def test_no_presets(self):
        """Rewritten (was: the preset tests). Every diode and MCU value comes
        from the file or from the user: there is no preset table, drop-down
        or preset tracking."""
        assert not hasattr(constants, "ZENER_PRESETS")
        assert not hasattr(constants, "CUSTOM_PRESET")
        for name in ("select_zener_preset", "zener_preset_display", "zener_preset_base"):
            assert not hasattr(AppState(), name)
        data = AppState().get_data()
        assert "preset" not in data["clamp_diode"] and "zener" not in data


class TestRangeChecks:
    @pytest.mark.parametrize("key,text,msg", [
        ("r1.value", "-5", "greater than 0"),
        ("rs.value", "-1", "negative"),
        ("r1.tol", "150", "below 100"),
        ("r2.tol", "-1", "at least 0"),
        ("mcu.adc_bits", "0", "1 to 32"),
        ("mcu.vil_factor", "1.5", "between 0 and 1"),
    ])
    def test_single_field(self, key, text, msg):
        s = ref_state()
        s.set_field(key, text)
        problems = " ".join(s.report.problems)
        assert FIELDS[key].label in problems and msg in problems

    @pytest.mark.parametrize("key,text,msg", [
        ("mcu.v_pin_min", "0.3", "above 0"),
        ("bw.margin_factor", "0.9", "1 or more"),
        ("system.v_touch", "0", "greater than 0"),
        ("system.v_input_min", "40", "lowest input must be below"),
        ("system.f_required_hz", "-1", "greater than 0"),
    ])
    def test_new_fields(self, key, text, msg):
        s = ref_state()
        s.set_field(key, text)
        assert any(p.startswith(FIELDS[key].label + ":") and msg in p
                   for p in s.report.problems)
        assert s.details["v_pin_typ"] is not None

    def test_row_order_min_typ_max(self):
        """Rewritten (was: VZ min <= VZ nom <= VZ max)."""
        s = ref_state()
        s.set_cell("reverse", 11, "v_min", "3.4")      # above V typ 3.28
        assert any("Reverse table row 12 V min" in p and "v_min ≤ v_typ ≤ v_max" in p
                   for p in s.report.problems)
        assert s.details["v_pin_typ"] is None and s.details["v_pin_high"] is None

    def test_currents_ascend(self):
        """Rewritten (was: IZK must be below IZT)."""
        s = ref_state()
        s.set_cell("reverse", 11, "i_ma", "2")          # = the row above
        assert any(p.startswith("Reverse table row 12 current:") and "row above" in p
                   for p in s.report.problems)
        assert s.details["v_pin_typ"] is None and s.details["v_pin_high"] is None

    def test_vil_below_vih(self):
        s = ref_state()
        s.set_field("mcu.vil_factor", "0.8")
        assert any("VIL factor must be below VIH factor" in p for p in s.report.problems)

    def test_rules_are_the_solvers(self):
        """One set of rules for the app, the file and the solver."""
        src = inspect.getsource(app_state_module)
        assert "RANGE_RULES" not in src
        assert "solver.number_problem" in src and "solver.table_problems" in src


class TestSeriesResistorRules:
    @pytest.mark.parametrize("rs", ["", "0"])
    def test_no_series_resistor_needs_nothing(self, rs):
        s = ref_state()
        s.set_fields({"rs.value": rs, "rs.unit": "", "rs.rating": "", "rs.tol": ""})
        assert s.report.needs == []
        assert s.report.lines() == []
        assert s.circuit.v["resistors.r_series"] == 0.0
        assert s.details["has_rs"] is False and s.check("power_rs") is None
        assert s.details["r_source_ohms"] == pytest.approx(10000 * 18000 / 28000)

    def test_rs_needs_unit_when_positive(self):
        s = ref_state()
        s.set_fields({"rs.value": "100", "rs.unit": ""})
        assert "R_s unit" in s.report.needs
        assert s.details["r_source_ohms"] is None

    def test_rs_rating_and_tol_needed_when_positive(self):
        """R_s rating and tolerance are used (R_s power at R_s min, tau at
        R_s max), so they are listed as needed."""
        s = ref_state()
        s.set_field("rs.value", "100")
        assert s.report.needs == ["R_s power rating", "R_s tolerance"]
        assert not any("Also blank" in line for line in s.report.lines())
        assert s.details["p_rs_worst_mw"] is None
        assert s.check("power_rs")["status"] == NEEDS_INPUT
        s.set_fields({"rs.rating": "250", "rs.tol": "5"})
        assert s.report.needs == []
        assert s.details["p_rs_worst_mw"] is not None
        assert s.check("power_rs")["status"] == PASS

    def test_rs_power_uses_rs_low_tolerance(self):
        """Rewritten (owner, 2026-11-09; was: injection uses R_s min). Pin
        held at 0 V: P = V_node,max^2 / R_s,min, with no 100 ohm."""
        s = ref_state()
        s.set_fields({"rs.value": "1", "rs.unit": KOHM, "rs.rating": "250", "rs.tol": "5"})
        d = s.details
        assert d["p_rs_worst_mw"] == pytest.approx(d["v_pin_high"] ** 2 / 950 * 1000)
        assert d["p_rs_mw"] == pytest.approx(d["v_pin_typ"] ** 2 / 1000 * 1000)

    def test_unreadable_rs_is_not_no_resistor(self):
        s = ref_state()
        s.set_field("rs.value", "1k")
        assert s.details["has_rs"] is True and s.details["r_source_ohms"] is None
        assert any(p.startswith("R_s value:") for p in s.report.problems)


class TestPowerFollowUp:
    def test_blank_rating_needs_input_without_hint(self):
        s = ref_state()
        s.set_field("r1.rating", "")
        assert s.report.needs == ["R1 power rating"]
        assert s.details["r1_margin_pct"] is None
        assert s.check("power_r1")["status"] == NEEDS_INPUT

    def test_reference_typical_and_worst(self):
        s = ref_state()
        d = s.details
        for part in ("r1", "r2", "diode"):
            assert d[f"p_{part}_worst_mw"] >= d[f"p_{part}_mw"]
        assert "injection" not in [c["id"] for c in s.results["checks"]]
        assert "mcu.safe_injection_ma" not in FIELDS


class TestUnreadableBlocksSave:
    def test_save_refused_naming_field(self, tmp_path):
        s = ref_state()
        s.set_field("r2.tol", "1,5")
        path = str(tmp_path / "x.div")
        assert not s.save_to_file(path)
        assert "R2 tolerance" in s.last_save_error and "1,5" in s.last_save_error
        assert not os.path.exists(path)

    def test_cleared_field_allows_save(self, tmp_path):
        s = ref_state()
        s.set_field("r2.tol", "abc")
        s.set_field("r2.tol", "")
        assert s.save_to_file(str(tmp_path / "x.div"))

    def test_out_of_range_does_not_block_save(self, tmp_path):
        s = ref_state()
        s.set_field("r1.tol", "150")
        path = str(tmp_path / "x.div")
        assert s.save_to_file(path)
        # ... and the app opens its own file again, showing the problem
        s2 = AppState()
        warnings = s2.open_file(path)
        assert s2.fields["r1.tol"] == "150"
        assert any("resistors.r1.tolerance_pct: must be at least 0 and below 100 %" in w
                   for w in warnings)
        assert any(p.startswith("R1 tolerance:") for p in s2.report.problems)


# ── Zero ratings ─────────────────────────────────────────────────────────────

class TestZeroInvalid:
    @pytest.mark.parametrize("key,label", [("r1.rating", "R1 power rating"),
                                           ("r2.rating", "R2 power rating"),
                                           ("diode.ptot_mw", "Clamp diode Ptot")])
    def test_zero_is_invalid_not_a_crash(self, key, label):
        s = ref_state()
        s.set_field(key, "0")
        assert any(p.startswith(label + ":") and "greater than 0" in p
                   for p in s.report.problems)
        assert s.details["v_pin_typ"] is not None


# ── Atomic save ──────────────────────────────────────────────────────────────

class TestAtomicSave:
    def test_failed_write_keeps_existing_file(self, tmp_path, monkeypatch):
        path = tmp_path / "keep.div"
        path.write_text("ORIGINAL", encoding="utf-8")
        s = ref_state()

        def broken_dump(obj, f, **kw):
            f.write('{"partial": ')
            raise OSError("disk full")
        monkeypatch.setattr(div_format.json, "dump", broken_dump)
        assert not s.save_to_file(str(path))
        assert "disk full" in s.last_save_error
        assert path.read_text(encoding="utf-8") == "ORIGINAL"
        assert [p.name for p in tmp_path.iterdir()] == ["keep.div"]   # no temp left
        assert s.is_dirty

    def test_save_to_missing_folder_fails_cleanly(self, tmp_path):
        s = ref_state()
        assert not s.save_to_file(str(tmp_path / "nope" / "x.div"))
        assert s.last_save_error
        assert s.current_file is None


# ── Loading files ────────────────────────────────────────────────────────────

class TestLoading:
    def test_null_resistor_value_loads_blank(self, tmp_path):
        data = zener_reference(resistors__r1__value=None)
        s = AppState()
        warnings = s.open_file(write_json(tmp_path, data))
        assert s.fields["r1.value"] == ""
        assert s.circuit.v["resistors.r1"] is None
        assert "R1 value" in warnings[0]

    def test_one_warning_lists_all_blank_values_that_are_needed(self, tmp_path):
        """Rewritten: null values load blank and one warning lists those the
        results need. (Keys left out are format problems: next test.)"""
        data = zener_reference(mcu__vdd=None, mcu__vih_factor=None,
                               system__v_input_max=None, system__v_logic_low_max=None)
        data["clamp_diode"]["reverse"][2]["v_typ"] = None
        s = AppState()
        warnings = s.open_file(write_json(tmp_path, data))
        assert len(warnings) == 1 and "blank in the file" in warnings[0]
        for label in ("VDD/VDDA", "VIH factor", "Max Input", "Logic Low",
                      "Reverse table row 3 V typ"):
            assert label in warnings[0]
        # R_s = 0: its rating/tolerance (null in the file) aren't listed,
        # nor are the optional values that are blank
        for label in ("R_s power rating", "Min Input", "Touch voltage", "Required frequency"):
            assert label not in warnings[0]

    def test_every_format_problem_is_reported(self, tmp_path):
        data = zener_reference()
        del data["mcu"]["vdd"]
        del data["system"]
        data["clamp_diode"]["izt_ma"] = 5
        data["resistors"]["r1"]["unit"] = "kOhm"
        s = ref_state()
        with pytest.raises(LoadError) as exc:
            s.open_file(write_json(tmp_path, data))
        lines = str(exc.value).splitlines()
        assert [line.split(":")[0] for line in lines] == [
            "resistors.r1.unit", "clamp_diode.izt_ma", "mcu.vdd", "system"]
        assert s.fields["r1.value"] == "10"

    @pytest.mark.parametrize("mutate,where", [
        (lambda d: d["mcu"].__setitem__("vdd", "abc"), "mcu.vdd"),
        (lambda d: d["mcu"].__setitem__("vdd", True), "mcu.vdd"),
        (lambda d: d["resistors"]["r1"].__setitem__("unit", "kOhm"), "resistors.r1.unit"),
        (lambda d: d["resistors"]["r2"].__setitem__("unit", 5), "resistors.r2.unit"),
        (lambda d: d.__setitem__("resistors", []), "resistors"),
        (lambda d: d["resistors"].__setitem__("r_series", "x"), "resistors.r_series"),
        (lambda d: d["mcu"].__setitem__("adc_bits", 12.5), "mcu.adc_bits"),
        (lambda d: d["clamp_diode"].__setitem__("checked", "no"), "clamp_diode.checked"),
        (lambda d: d.__setitem__("notes", 12), "notes"),
        (lambda d: d["clamp_diode"].__setitem__("type", 3), "clamp_diode.type"),
        (lambda d: d["clamp_diode"].__setitem__("anode", "pin"), "clamp_diode.anode"),
        (lambda d: d["clamp_diode"]["reverse"][0].__setitem__("i_ma", "1u"),
         "clamp_diode.reverse[0].i_ma"),
    ])
    def test_malformed_rejected_and_state_untouched(self, tmp_path, mutate, where):
        s = ref_state()
        s.current_file = "previous.div"
        s.set_field("notes", "keep me")
        fields_before, tables_before = dict(s.fields), copy.deepcopy(s.tables)
        dirty_before = s.is_dirty
        data = zener_reference()
        mutate(data)
        with pytest.raises(LoadError) as exc:
            s.open_file(write_json(tmp_path, data))
        assert str(exc.value).startswith(where)
        assert s.fields == fields_before and s.tables == tables_before
        assert s.current_file == "previous.div"
        assert s.is_dirty == dirty_before
        assert s.details["v_pin_typ"] is not None

    def test_not_json_rejected(self, tmp_path):
        p = tmp_path / "bad.div"
        p.write_text("{not json", encoding="utf-8")
        s = AppState()
        with pytest.raises(LoadError):
            s.open_file(str(p))

    def test_ignore_changes_reset_after_failed_load(self, tmp_path):
        s = AppState()

        def boom():
            raise RuntimeError("UI sync failed")
        s.set_fields_callback(boom)
        with pytest.raises(RuntimeError):
            s.open_file(ZENER_DIV)
        assert s.ignore_changes is False
        s.set_fields_callback(None)
        s.is_dirty = False
        s.set_field("r1.value", "12")
        assert s.is_dirty

    def test_megaohm_accepted(self, tmp_path):
        data = zener_reference()
        data["resistors"]["r2"] = {"value": 1.5, "unit": MOHM, "rating_mw": 63, "tolerance_pct": 1}
        s = AppState()
        s.open_file(write_json(tmp_path, data))
        assert s.circuit.v["resistors.r2"] == pytest.approx(1.5e6)

    def test_format_1_file_is_refused(self, tmp_path):
        """Rewritten (was: results.div still loads). No converter: one clear
        message, and the design on screen is untouched."""
        s = ref_state()
        fields_before = dict(s.fields)
        with pytest.raises(LoadError) as exc:
            s.open_file(write_json(tmp_path, copy.deepcopy(V1_FILE)))
        assert "format 1.0" in str(exc.value) and "reads .div format 2.0" in str(exc.value)
        assert len(str(exc.value).splitlines()) == 1
        assert s.fields == fields_before
        assert not os.path.exists(os.path.join(EXAMPLES, "..", "results.div"))

    @pytest.mark.parametrize("path,verdict", [(ZENER_DIV, FAIL), (SCHOTTKY_DIV, FAIL)],
                             ids=["zener", "schottky"])
    def test_example_files_load(self, path, verdict):
        s = AppState()
        assert s.open_file(path) == []
        assert s.report.lines() == []
        assert s.results["verdict"] == verdict
        assert not s.is_dirty and s.title().endswith(os.path.basename(path))

    def test_stored_results_are_ignored_and_solved_again(self, tmp_path):
        data = dict(zener_reference(), results={"verdict": "PASS", "checks": "nonsense"})
        s = AppState()
        s.open_file(write_json(tmp_path, data))
        assert s.results["verdict"] == FAIL
        assert s.results == solve(zener_reference()) | {"details": s.results["details"]}

    def test_unusable_values_load_and_are_listed_to_fix(self, tmp_path):
        """A readable value that can't be used does not block opening."""
        data = zener_reference(mcu__vil_factor=0.8)
        data["clamp_diode"]["reverse"][5]["v_typ"] = 1.0
        s = AppState()
        warnings = s.open_file(write_json(tmp_path, data))
        assert len(warnings) == 1 and "can't be used" in warnings[0]
        for path in ("mcu.vil_factor", "mcu.vih_factor", "clamp_diode.reverse[5].v_typ"):
            assert path in warnings[0]
        assert s.fields["mcu.vil_factor"] == "0.8" and s.tables["reverse"][5]["v_typ"] == "1"
        fix = " ".join(s.report.problems)
        assert "VIL factor must be below VIH factor" in fix
        assert "Reverse table row 6 V typ: must be greater than in the row above" in fix

    @pytest.mark.parametrize("empty", [("forward",), ("reverse",), ("forward", "reverse")],
                             ids=["forward", "reverse", "both"])
    def test_empty_table_round_trips_as_empty(self, tmp_path, empty):
        """Open a file whose table is [], save without editing: still []
        ("not modelled"), and the other table is untouched."""
        data = zener_reference(**{f"clamp_diode__{t}": [] for t in empty})
        s = AppState()
        assert s.open_file(write_json(tmp_path, data)) == []
        assert not s.is_dirty
        for t in empty:
            assert s.tables[t] == []
        out = saved(s, tmp_path, "out.div")
        for t in ("forward", "reverse"):
            assert out["clamp_diode"][t] == data["clamp_diode"][t]
        assert out["clamp_diode"]["forward"] == [] and type(out["clamp_diode"]["forward"]) is list
        text = open(str(tmp_path / "out.div"), encoding="utf-8").read()
        for t in empty:
            assert f'    "{t}": []' in text          # written as [], not as rows or null

    @pytest.mark.parametrize("blank", [("forward",), ("reverse",), ("forward", "reverse")],
                             ids=["forward", "reverse", "both"])
    def test_null_table_round_trips_as_null(self, tmp_path, blank):
        """Open a file whose table is null, save without editing: still null
        ("not filled in"), not rows of null cells and not []. The table is
        needed, and the results that use it wait for it."""
        data = zener_reference(**{f"clamp_diode__{t}": None for t in blank})
        s = AppState()
        warnings = s.open_file(write_json(tmp_path, data))
        assert not s.is_dirty
        for t in blank:
            assert s.tables[t] is None and s.table_state(t) == "blank"
            label = "Forward table" if t == "forward" else "Reverse table"
            assert label in s.report.needs and label in warnings[0]
        assert s.details["v_pin_typ"] is None and s.details["k_nominal"] is not None
        out = saved(s, tmp_path, "out.div")
        for t in ("forward", "reverse"):
            assert out["clamp_diode"][t] == data["clamp_diode"][t]
        text = open(str(tmp_path / "out.div"), encoding="utf-8").read()
        for t in blank:
            assert out["clamp_diode"][t] is None and f'    "{t}": null' in text

    def test_null_and_empty_are_different_states(self, tmp_path):
        """null = not filled in yet (results keep asking); [] = not modelled."""
        s = AppState()
        s.open_file(write_json(tmp_path, zener_reference(clamp_diode__forward=None)))
        assert s.table_state("forward") == "blank" and s.details["v_pin_typ"] is None
        assert s.report.needs == ["Forward table"] and s.report.problems == []
        s.set_not_modelled("forward", True)
        assert s.tables["forward"] == [] and s.table_state("forward") == "not modelled"
        assert s.report.lines() == [] and s.details["v_pin_typ"] is not None
        assert s.is_dirty


# ── Clamp diode: tables, connection, type, "checked" ─────────────────────────

class TestClampDiode:
    def test_cell_edit_recalculates_and_marks_unsaved(self):
        s = ref_state()
        s.is_dirty = False
        before = s.details["v_pin_typ"]
        s.set_cell("reverse", 11, "v_typ", "3.30")
        assert s.is_dirty and s.details["v_pin_typ"] > before
        s.is_dirty = False
        s.set_cell("reverse", 11, "v_typ", "3.30")       # same text
        assert not s.is_dirty

    def test_add_and_delete_rows(self):
        s = ref_state()
        calls = []
        s.set_fields_callback(lambda: calls.append(1))
        s.is_dirty = False
        s.add_row("forward")
        assert s.tables["forward"] == [dict(i_ma="", v_min="", v_typ="", v_max="")]
        assert s.is_dirty and calls == [1]
        # one blank row: its cells are needed, and a table needs two rows
        assert "Forward table row 1 current" in s.report.needs
        assert any(p.startswith("Forward table: needs at least 2 rows") for p in s.report.problems)
        assert s.details["v_pin_typ"] is None
        # deleting the last row leaves the table blank (not filled in): needed
        s.delete_row("forward", 0)
        assert s.tables["forward"] is None and s.table_state("forward") == "blank"
        assert s.report.needs == ["Forward table"] and s.report.problems == []
        assert s.details["v_pin_typ"] is None and calls == [1, 1]
        # "Not modelled" switches a table with no rows between blank and []
        s.set_not_modelled("forward", True)
        assert s.tables["forward"] == [] and s.report.lines() == []
        assert s.details["v_pin_typ"] is not None and calls == [1, 1, 1]
        s.set_not_modelled("forward", False)
        assert s.tables["forward"] is None and s.report.needs == ["Forward table"]
        # "+ Add row" turns either state into rows
        s.add_row("forward")
        assert s.table_state("forward") == "rows" and len(s.tables["forward"]) == 1
        s.set_not_modelled("forward", True)            # no effect on a table with rows
        assert len(s.tables["forward"]) == 1
        s.delete_row("forward", 0)
        s.set_not_modelled("forward", True)
        s.add_row("forward")
        assert s.table_state("forward") == "rows"

    def test_empty_table_is_not_modelled_and_not_needed(self):
        s = ref_state()
        assert s.details["forward_modelled"] is False and s.details["reverse_modelled"] is True
        assert s.report.needs == []
        s.set_table("reverse", [])
        assert s.details["reverse_modelled"] is False
        assert s.details["v_pin_typ"] == pytest.approx(30 * 18 / 28)

    def test_unreadable_cell_blocks_save_and_names_the_cell(self, tmp_path):
        s = ref_state()
        s.set_cell("reverse", 0, "i_ma", "1u")
        assert s.unreadable_fields() == [("Reverse table row 1 current", "1u")]
        assert any(p == "Reverse table row 1 current: '1u' is not a number"
                   for p in s.report.problems)
        assert not s.save_to_file(str(tmp_path / "x.div"))
        assert "Reverse table row 1 current" in s.last_save_error
        assert s.details["v_pin_typ"] is None

    def test_tables_round_trip(self, tmp_path):
        s = app_state(schottky_rail())
        data = saved(s, tmp_path)
        assert data["clamp_diode"]["forward"] == schottky_rail()["clamp_diode"]["forward"]
        assert data["clamp_diode"]["reverse"] == schottky_rail()["clamp_diode"]["reverse"]
        s2 = AppState()
        s2.open_file(str(tmp_path / "s.div"))
        assert s2.tables == s.tables and s2.results == s.results

    def test_whole_design_round_trip(self, tmp_path):
        for make in (zener_reference, schottky_rail):
            data = saved(app_state(make()), tmp_path)
            assert div_format.validate(data) == []
            created = data.pop("created")
            assert created[:2] == "20"
            data.pop("results")
            expected = make()
            expected.pop("created")
            assert data == expected

    def test_saved_results_are_the_solvers(self, tmp_path):
        s = app_state(schottky_rail())
        data = saved(s, tmp_path)
        assert data["results"] == div_format.results_for_file(solve(schottky_rail()))
        assert list(data)[-1] == "results"

    @pytest.mark.parametrize("anode,cathode", [("node", "node"), ("gnd", "vdd")])
    def test_wiring_problem(self, anode, cathode):
        s = ref_state()
        s.set_fields({"diode.anode": anode, "diode.cathode": cathode})
        assert any(p.startswith("Anode connection: one of anode and cathode must be node")
                   for p in s.report.problems)
        assert s.details["v_pin_typ"] is None

    def test_connection_decides_not_the_type(self):
        s = ref_state()
        before = s.details["v_pin_typ"]
        s.set_field("diode.type", "schottky")
        assert s.details["v_pin_typ"] == before
        s = app_state(schottky_rail())
        assert s.details["v_pin_typ"] == pytest.approx(3.547, abs=0.001)
        assert s.info("rail_current")["value"] == pytest.approx(2.493, abs=0.001)
        s.set_fields({"diode.anode": "gnd", "diode.cathode": "node"})
        assert s.info("rail_current") is None
        assert s.details["v_pin_typ"] == pytest.approx(
            solve(schottky_gnd())["details"]["v_pin_typ"])

    def test_unknown_choice_text_is_a_problem(self):
        s = ref_state()
        s.fields["diode.anode"] = "pin"
        s.recalculate()
        assert any(p.startswith("Anode connection: unknown value 'pin'") for p in s.report.problems)
        assert s.unreadable_fields() == [("Anode connection", "pin")]

    def test_checked_and_text_round_trip(self, tmp_path):
        s = ref_state()
        s.set_fields({"diode.checked": "1", "mcu.note": "checked by DK", "mcu.pin_type": "FT"})
        data = saved(s, tmp_path)
        assert data["clamp_diode"]["checked"] is True and data["mcu"]["checked"] is False
        assert data["mcu"]["note"] == "checked by DK" and data["mcu"]["pin_type"] == "FT"
        s2 = AppState()
        s2.open_file(str(tmp_path / "s.div"))
        assert s2.fields["diode.checked"] == "1" and s2.fields["mcu.checked"] == "0"
        assert s2.fields["mcu.note"] == "checked by DK"


# ── Open + save without editing gives the inputs back exactly ────────────────

def input_text(path):
    """A saved file's text up to its "results" section."""
    text = open(path, encoding="utf-8").read()
    return text[:text.index('  "results": {')]


class TestExactRoundTrip:
    @pytest.mark.parametrize("path", [ZENER_DIV, SCHOTTKY_DIV], ids=["zener", "schottky"])
    def test_example_file_comes_back_identical(self, path, tmp_path):
        """Every input section exactly as written; the results too, since the
        solver has not changed."""
        s = AppState()
        s.open_file(path)
        out = str(tmp_path / "out.div")
        assert s.save_to_file(out)
        assert input_text(out) == input_text(path)
        assert open(out, encoding="utf-8").read() == open(path, encoding="utf-8").read()

    def test_whole_numbers_and_decimals_stay_as_written(self, tmp_path):
        """10 stays 10 and 10.0 stays 10.0; "created" and null text stay too."""
        data = zener_reference(created="2026-01-02T03:04:05", notes=None,
                               clamp_diode__source=None, mcu__checked=True)
        data["resistors"]["r1"]["value"] = 10.0
        data["resistors"]["r2"]["value"] = 18
        data["mcu"]["v_absolute_max"] = 4.0
        data["mcu"]["adc_bits"] = 12
        data["system"]["v_input_max"] = 30.0
        data["clamp_diode"]["reverse"][9] = dict(i_ma=1.0, v_min=2.51, v_typ=2.69, v_max=2.91)
        data["clamp_diode"]["reverse"][10]["i_ma"] = 2
        s = AppState()
        s.open_file(write_json(tmp_path, data))
        assert s.fields["r1.value"] == "10" and s.fields["r2.value"] == "18"   # shown the same
        out = saved(s, tmp_path, "out.div")
        out.pop("results")
        assert out == data
        for path, kind in ((("resistors", "r1", "value"), float),
                           (("resistors", "r2", "value"), int),
                           (("mcu", "v_absolute_max"), float), (("mcu", "adc_bits"), int),
                           (("system", "v_input_max"), float)):
            node = out
            for part in path:
                node = node[part]
            assert type(node) is kind, path
        assert type(out["clamp_diode"]["reverse"][9]["i_ma"]) is float
        assert type(out["clamp_diode"]["reverse"][10]["i_ma"]) is int
        assert out["created"] == "2026-01-02T03:04:05" and out["notes"] is None
        assert out["clamp_diode"]["source"] is None and out["mcu"]["checked"] is True
        text = open(str(tmp_path / "out.div"), encoding="utf-8").read()
        assert '"r1": {"value": 10.0, ' in text and '"r2": {"value": 18, ' in text

    def test_edited_value_is_written_as_entered(self, tmp_path):
        s = AppState()
        s.open_file(ZENER_DIV)
        s.set_fields({"r1.value": "12", "r2.value": "18.0", "mcu.vdd": "3.30",
                      "system.v_input_max": "2.4e1", "mcu.part": "STM32G431"})
        s.set_cell("reverse", 12, "v_typ", "3.6")
        s.set_cell("reverse", 12, "i_ma", "11")
        out = saved(s, tmp_path, "out.div")
        r1, r2 = out["resistors"]["r1"]["value"], out["resistors"]["r2"]["value"]
        assert (r1, type(r1)) == (12, int) and (r2, type(r2)) == (18.0, float)
        assert out["mcu"]["vdd"] == 3.3 and out["system"]["v_input_max"] == 24.0
        assert type(out["system"]["v_input_max"]) is float
        assert out["mcu"]["part"] == "STM32G431"
        row = out["clamp_diode"]["reverse"][12]
        assert row == dict(i_ma=11, v_min=3.37, v_typ=3.6, v_max=3.77)
        assert type(row["i_ma"]) is int
        # everything that was not edited is as it was in the file
        original = div_format.read_json(ZENER_DIV)
        assert out["resistors"]["r_series"] == original["resistors"]["r_series"]
        assert out["clamp_diode"]["reverse"][:12] == original["clamp_diode"]["reverse"][:12]
        assert out["created"] == original["created"]

    def test_typing_the_same_text_back_keeps_the_written_value(self, tmp_path):
        data = zener_reference()
        data["mcu"]["v_absolute_max"] = 4.0
        s = AppState()
        s.open_file(write_json(tmp_path, data))
        s.set_field("mcu.v_absolute_max", "4.5")
        s.set_field("mcu.v_absolute_max", "4")
        out = saved(s, tmp_path, "out.div")
        assert type(out["mcu"]["v_absolute_max"]) is float

    def test_created_is_set_once(self, tmp_path):
        s = ref_state()
        first = saved(s, tmp_path, "a.div")["created"]
        assert first[:2] == "20"
        s.set_field("r1.value", "11")
        assert saved(s, tmp_path, "b.div")["created"] == first
        s.file_new()
        assert s.design["created"] is None

    def test_results_are_unchanged_by_the_round_trip(self):
        for path in (ZENER_DIV, SCHOTTKY_DIV):
            s = AppState()
            s.open_file(path)
            stored = div_format.read_json(path)
            assert div_format.results_for_file(s.results) == stored["results"]
            assert div_format.results_for_file(solve(stored)) == stored["results"]


# ── "Checked against the data sheet" is unticked by an edit of a value ───────

class TestCheckedBox:
    def ticked(self, design=None):
        s = app_state(design)
        s.set_fields({"diode.checked": "1", "mcu.checked": "1"})
        s.is_dirty = False
        return s

    @pytest.mark.parametrize("key,text", [
        ("diode.type", "schottky"), ("diode.anode", "node"), ("diode.cathode", "vdd"),
        ("diode.capacitance_pf", "400"), ("diode.ptot_mw", "300")])
    def test_diode_value_unticks_the_diode_only(self, key, text):
        s = self.ticked()
        calls = []
        s.set_fields_callback(lambda: calls.append(1))
        s.set_field(key, text)
        assert s.fields["diode.checked"] == "0" and s.fields["mcu.checked"] == "1"
        assert calls == [1]                     # the UI is told to untick the box
        assert s.design["clamp_diode"]["checked"] is False

    @pytest.mark.parametrize("key", ["mcu.pin_type", "mcu.vdd", "mcu.v_recommended_max",
                                     "mcu.v_absolute_max", "mcu.v_pin_min", "mcu.adc_bits",
                                     "mcu.vil_factor", "mcu.vih_factor", "mcu.c_pin_pf",
                                     "mcu.t_pulse_min_ns"])
    def test_mcu_value_unticks_the_mcu_only(self, key):
        s = self.ticked()
        s.set_field(key, "0.5")
        assert s.fields["mcu.checked"] == "0" and s.fields["diode.checked"] == "1"

    @pytest.mark.parametrize("edit", [
        lambda s: s.set_cell("reverse", 3, "v_typ", "1.6"),
        lambda s: s.add_row("forward"),
        lambda s: s.delete_row("reverse", 12),
        lambda s: s.set_not_modelled("forward", False),
        lambda s: s.set_table("reverse", [])], ids=["cell", "add row", "delete row",
                                                    "not modelled", "set table"])
    def test_table_edit_unticks_the_diode(self, edit):
        s = self.ticked()
        edit(s)
        assert s.fields["diode.checked"] == "0" and s.fields["mcu.checked"] == "1"

    @pytest.mark.parametrize("key", ["diode.part", "diode.source", "diode.note",
                                     "mcu.part", "mcu.source", "mcu.note", "notes",
                                     "r1.value", "system.v_input_max", "bw.c_stray_pf"])
    def test_name_source_note_and_other_panels_leave_it_ticked(self, key):
        s = self.ticked()
        s.set_field(key, "7")
        assert s.fields["diode.checked"] == "1" and s.fields["mcu.checked"] == "1"
        assert s.is_dirty

    def test_same_text_is_not_an_edit(self):
        s = self.ticked()
        s.set_field("mcu.vdd", s.fields["mcu.vdd"])
        s.set_cell("reverse", 0, "i_ma", s.tables["reverse"][0]["i_ma"])
        assert s.fields["mcu.checked"] == "1" and s.fields["diode.checked"] == "1"
        assert not s.is_dirty

    def test_ticking_again_stays_until_the_next_edit(self, tmp_path):
        s = self.ticked()
        s.set_field("mcu.vdd", "3.0")
        s.set_field("mcu.checked", "1")
        assert saved(s, tmp_path)["mcu"]["checked"] is True
        s.set_field("mcu.c_pin_pf", "6")
        assert saved(s, tmp_path)["mcu"]["checked"] is False

    def test_opening_a_file_does_not_untick(self, tmp_path):
        data = zener_reference(clamp_diode__checked=True, mcu__checked=True)
        s = AppState()
        s.open_file(write_json(tmp_path, data))
        assert s.fields["diode.checked"] == "1" and s.fields["mcu.checked"] == "1"
        out = saved(s, tmp_path, "out.div")
        assert out["clamp_diode"]["checked"] is True and out["mcu"]["checked"] is True

    def test_setting_the_box_together_with_values_keeps_what_was_set(self):
        s = self.ticked()
        s.set_fields({"mcu.vdd": "3.0", "mcu.checked": "1", "diode.ptot_mw": "300"})
        assert s.fields["mcu.checked"] == "1" and s.fields["diode.checked"] == "0"


# ── New MCU and system values ────────────────────────────────────────────────

class TestNewValues:
    def test_lowest_input_check(self):
        s = app_state(schottky_gnd())
        assert s.check("pin_min") is None and s.level("min_input") is None
        s.set_field("system.v_input_min", "-5")
        assert s.check("pin_min")["status"] == PASS
        assert s.level("min_input")["low"] == pytest.approx(-0.293, abs=0.002)
        s.set_field("mcu.v_pin_min", "")
        assert s.check("pin_min")["status"] == NEEDS_INPUT and s.report.needs == ["Pin Min"]
        s.set_fields({"mcu.v_pin_min": "-0.3", "system.v_input_min": "0.5"})
        assert s.check("pin_min") is None and s.level("min_input")["v_in"] == 0.5

    def test_touch_voltage_rows(self):
        s = ref_state()
        assert s.info("touch_pin_high") is None
        verdict, checks = s.results["verdict"], copy.deepcopy(s.results["checks"])
        s.set_field("system.v_touch", "60")
        assert s.info("touch_pin_high")["value"] == pytest.approx(s.level("touch")["high"])
        assert s.info("touch_r1_power")["value"] > 200
        assert s.results["verdict"] == verdict and s.results["checks"] == checks

    def test_analog_error_status_needs_an_allowed_error(self):
        s = app_state(schottky_rail())
        assert s.check("analog_error")["status"] is None
        s.set_field("system.analog_error_allowed_pct", "0.5")
        assert s.check("analog_error")["status"] == PASS
        s.set_field("system.analog_error_allowed_pct", "0.05")
        assert s.check("analog_error")["status"] == FAIL
        s.set_field("system.v_analog_fullscale", "")
        assert s.check("analog_error") is None and s.check("analog_range") is None
        assert s.report.needs == []

    def test_required_frequency(self):
        s = app_state(schottky_rail())
        assert s.check("frequency") is None
        for text, status in (("800000", "PASS"), ("1000000", "TIGHT"), ("1400000", "FAIL")):
            s.set_field("system.f_required_hz", text)
            assert s.check("frequency")["status"] == status

    def test_new_values_round_trip(self, tmp_path):
        s = ref_state()
        values = {"system.v_input_min": "-24", "system.v_touch": "60",
                  "system.f_required_hz": "20000", "system.analog_error_allowed_pct": "1.5",
                  "mcu.v_pin_min": "-0.3", "mcu.c_pin_pf": "7", "mcu.t_pulse_min_ns": "20",
                  "mcu.pin_type": "FT"}
        s.set_fields(values)
        data = saved(s, tmp_path)
        assert data["system"]["v_input_min"] == -24 and data["system"]["v_touch"] == 60
        assert data["system"]["f_required_hz"] == 20000
        assert data["system"]["analog_error_allowed_pct"] == 1.5
        assert data["mcu"]["t_pulse_min_ns"] == 20 and data["mcu"]["pin_type"] == "FT"
        assert "safe_injection_ma" not in data["mcu"]
        s2 = AppState()
        s2.open_file(str(tmp_path / "s.div"))
        for key, text in values.items():
            assert s2.fields[key] == text, key

    def test_overall_verdict(self):
        s = ref_state()
        assert s.results["verdict"] == FAIL                  # logic_high
        s.set_field("system.v_logic_high_min", "24")
        assert s.results["verdict"] == PASS
        s.set_field("r1.rating", "")
        assert s.results["verdict"] == NEEDS_INPUT


# ── Plot: AppState sweeps the solver's pin-voltage function ──────────────────

class TestPlot:
    def test_plain_lists_of_200_points_from_0_to_max(self):
        s = ref_state()
        p = s.plot_data
        assert len(p["v_in"]) == len(p["v_mcu_typ"]) == len(p["v_mcu_worst"]) == 200
        assert p["v_in"][0] == 0.0 and p["v_in"][-1] == 30.0 and p["vin_min"] == 0.0
        assert (p["vdd"], p["v_rec_max"], p["v_abs_max"]) == (3.3, 3.6, 4.0)
        assert s.plot_message == ""

    def test_sweep_starts_at_a_negative_min_input(self):
        s = app_state(schottky_gnd(system__v_input_min=-5.0))
        p = s.plot_data
        assert p["v_in"][0] == -5.0 and p["vin_min"] == -5.0 and p["v_in"][-1] == 30.0
        assert p["v_mcu_typ"][0] == pytest.approx(s.level("min_input")["typ"])
        assert p["v_mcu_typ"] == sorted(p["v_mcu_typ"])

    def test_worst_curve_is_the_highest_of_the_corners(self):
        s = app_state(schottky_rail())
        c = prepare(s.design)
        for i in (0, 20, 199):
            vin = s.plot_data["v_in"][i]
            assert s.plot_data["v_mcu_worst"][i] == max(x["v"] for x in c.corners(vin))

    def test_lowest_curve_is_the_lowest_of_the_corners(self):
        """V_mcuL on the plot: the solver's pin-voltage function, "low" (the
        same eight corners as the tables)."""
        s = app_state(schottky_rail())
        c = prepare(s.design)
        p = s.plot_data
        assert type(p["v_mcu_low"]) is list and len(p["v_mcu_low"]) == 200
        assert all(type(x) is float for x in p["v_mcu_low"])
        for i in (0, 20, 199):
            vin = p["v_in"][i]
            assert p["v_mcu_low"][i] == c.pin_voltage(vin, "low")
            assert p["v_mcu_low"][i] == min(x["v"] for x in c.corners(vin))
        assert all(lo <= hi for lo, hi in zip(p["v_mcu_low"], p["v_mcu_worst"]))
        assert p["v_mcu_low"] == sorted(p["v_mcu_low"])     # never falls as the input rises

    @pytest.mark.parametrize("design", [zener_reference, schottky_rail, schottky_gnd])
    def test_band_ends_at_the_max_input_row_of_the_tables(self, design):
        s = app_state(design())
        row = s.level("max_input")
        assert s.plot_data["v_mcu_low"][-1] == row["low"]
        assert s.plot_data["v_mcu_worst"][-1] == row["high"]
        assert s.plot_data["v_mcu_typ"][-1] == row["typ"]

    @pytest.mark.parametrize("path", [ZENER_DIV, SCHOTTKY_DIV],
                             ids=["zener_gnd", "schottky_rail"])
    def test_low_and_high_curves_equal_the_pin_voltage_function(self, path):
        """The sweep takes the lowest and the highest from one corners() call
        per point. They are exactly (==, not approx) the solver's
        pin_voltage(x, "low") and pin_voltage(x, "high"): at 0 V, at the
        knee of each curve, at Max Input and at every other plot point."""
        s = AppState()
        s.open_file(path)
        p = s.plot_data
        v_in, last = p["v_in"], len(p["v_in"]) - 1
        c = prepare(s.design)          # not the Circuit that AppState swept

        def knee(curve):
            """Index of the plot point where *curve* bends most."""
            bend = [abs(curve[i - 1] - 2 * curve[i] + curve[i + 1])
                    for i in range(1, last)]
            return bend.index(max(bend)) + 1

        knees = sorted({knee(p[k]) for k in ("v_mcu_typ", "v_mcu_low", "v_mcu_worst")})
        assert v_in[0] == 0.0
        assert v_in[last] == 30.0 == s.level("max_input")["v_in"]
        for k in knees:                # a real knee: steeper before it than after it
            assert 0 < k < last
            for curve in (p["v_mcu_low"], p["v_mcu_worst"]):
                before = (curve[k] - curve[0]) / (v_in[k] - v_in[0])
                after = (curve[last] - curve[k]) / (v_in[last] - v_in[k])
                assert before > 2 * after

        named = [0, *knees, last]
        for i in named + [i for i in range(last + 1) if i not in named]:
            assert p["v_mcu_low"][i] == c.pin_voltage(v_in[i], "low"), v_in[i]
            assert p["v_mcu_worst"][i] == c.pin_voltage(v_in[i], "high"), v_in[i]
            assert p["v_mcu_low"][i] == pin_voltage(s.design, v_in[i], "low"), v_in[i]
            assert p["v_mcu_worst"][i] == pin_voltage(s.design, v_in[i], "high"), v_in[i]

    def test_sweep_solves_the_corners_once_per_point(self, monkeypatch):
        """Plot cost: one corners() call per plot point serves both the
        lowest and the highest curve (8 solves per point, not 16). Only the
        typical curve goes through pin_voltage."""
        from src.models.clamp_solver import Circuit
        s = app_state(schottky_rail())
        real_corners, real_pin_voltage = Circuit.corners, Circuit.pin_voltage
        swept, cases = [], []

        def corners(self, vin, where=""):
            if where == "sweep":
                swept.append(vin)
            return real_corners(self, vin, where)

        def pin_voltage_spy(self, v_in, case="typ"):
            cases.append(case)
            return real_pin_voltage(self, v_in, case)

        monkeypatch.setattr(Circuit, "corners", corners)
        monkeypatch.setattr(Circuit, "pin_voltage", pin_voltage_spy)
        s.recalculate()
        assert len(s.plot_data["v_in"]) == constants.PLOT_POINTS == 200
        assert swept == s.plot_data["v_in"]            # once per point, in order
        assert cases == ["typ"] * constants.PLOT_POINTS

    def test_lowest_curve_needs_the_worst_case_inputs(self):
        s = ref_state()
        s.set_field("r1.tol", "")
        assert "v_mcu_typ" in s.plot_data
        assert "v_mcu_low" not in s.plot_data and "v_mcu_worst" not in s.plot_data
        s.set_field("r1.tol", "1")
        s.set_cell("reverse", 0, "v_typ", "")
        assert "v_mcu_low" in s.plot_data and "v_mcu_typ" not in s.plot_data

    def test_logic_thresholds_are_handed_to_the_plot(self):
        """VIL and VIH for the plot are the solver's, not worked out again."""
        s = ref_state()
        p = s.plot_data
        assert p["vil"] == s.results["voltages"]["vil"] == pytest.approx(0.99)
        assert p["vih"] == s.results["voltages"]["vih"] == pytest.approx(2.31)
        s.set_field("mcu.vih_factor", "")
        assert s.plot_data["vih"] is None and s.plot_data["vil"] == pytest.approx(0.99)
        assert "v_mcu_typ" in s.plot_data            # the curves don't wait for it

    def test_each_curve_needs_its_own_inputs(self):
        s = ref_state()
        s.set_field("r1.tol", "")
        assert "v_mcu_typ" in s.plot_data and "v_mcu_worst" not in s.plot_data
        assert s.plot_message == "Worst-case curve needs input: R1 tolerance"
        s.set_cell("reverse", 0, "v_typ", "")
        assert s.plot_data == {}
        assert s.plot_message.startswith("Plot needs input: ")
        assert "Reverse table row 1 V typ" in s.plot_message
        s.set_fields({"r1.tol": "1"})
        assert "v_mcu_worst" in s.plot_data and "v_mcu_typ" not in s.plot_data
        assert s.plot_message == "Typical curve needs input: Reverse table row 1 V typ"

    def test_blank_max_input_clears_the_plot(self):
        s = ref_state()
        s.set_field("system.v_input_max", "")
        assert s.plot_data == {} and "Max Input" in s.plot_message

    def test_plot_is_not_numpy(self):
        from src.ui import plot_canvas
        assert "numpy" not in inspect.getsource(plot_canvas)
        assert "numpy" not in inspect.getsource(app_state_module)

    def test_unsettled_plot_points_are_reported(self, monkeypatch):
        from src.models import clamp_solver
        real = clamp_solver._solve_node
        monkeypatch.setattr(clamp_solver, "_solve_node",
                            lambda *a, **k: (real(*a, **k)[0], False))
        s = ref_state()
        assert any("did not settle at" in w and "plot point" in w for w in s.report.warnings)
        assert any("Max Input 30 V" in w for w in s.report.warnings)


def test_worst_status_of_several_checks():
    """The Max Input row of the Input Levels tab is judged on Safe Max and
    Absolute Max together: the worse of the two, in the verdict's order."""
    s = app_state(schottky_rail())
    assert s.check("pin_max_safe")["status"] == FAIL and s.check("pin_max_abs")["status"] == PASS
    assert s.worst_status("pin_max_safe", "pin_max_abs") == FAIL
    assert s.worst_status("pin_max_abs") == PASS
    s.set_field("mcu.v_recommended_max", "3.67")
    assert s.worst_status("pin_max_safe", "pin_max_abs") == "TIGHT"
    s.set_field("mcu.v_recommended_max", "")
    assert s.worst_status("pin_max_safe", "pin_max_abs") == NEEDS_INPUT
    s.set_field("mcu.v_absolute_max", "3.6")
    assert s.worst_status("pin_max_safe", "pin_max_abs") == FAIL    # FAIL outranks "needs input"
    assert s.worst_status("pin_min") is None                         # a check that is not made
    # the solver's own ordering, not a second one
    src = inspect.getsource(AppState.worst_status)
    assert "solver.worst_status" in src


def test_path_labels():
    assert path_label("mcu.vdd") == "VDD/VDDA"
    assert path_label("resistors.r_series.rating_mw") == "R_s power rating"
    assert path_label("clamp_diode.forward") == "Forward table"
    assert path_label("clamp_diode.reverse[3]") == "Reverse table row 4"
    assert path_label("clamp_diode.reverse[3].v_min") == "Reverse table row 4 V min"
    assert path_label("clamp_diode.anode") == "Anode connection"


def test_typed_design_matches_the_file_design():
    fields, tables = typed()
    assert fields["r1.value"] == "10" and fields["r1.unit"] == KOHM
    assert fields["rs.value"] == "0" and fields["rs.unit"] == OHM
    assert fields["diode.anode"] == "gnd" and fields["diode.checked"] == "0"
    assert tables["reverse"][11] == dict(i_ma="5", v_min="3.1", v_typ="3.28", v_max="3.5")
    assert app_state().design == change(zener_reference(), created=None)


# ── ADC bits and factors saved ───────────────────────────────────────────────

def test_adc_bits_and_factors_round_trip(tmp_path):
    s = ref_state()
    s.set_field("mcu.adc_bits", "16")
    path = str(tmp_path / "m.div")
    s.save_to_file(path)
    m = json.loads(open(path, encoding="utf-8").read())["mcu"]
    assert m["adc_bits"] == 16 and m["vil_factor"] == 0.3 and m["vih_factor"] == 0.7
    s2 = AppState()
    s2.open_file(path)
    assert s2.design["mcu"]["adc_bits"] == 16
    assert s2.details["resolution_mv_per_lsb"] == pytest.approx(3.3 / 65536 * 1000 / (18 / 28))
