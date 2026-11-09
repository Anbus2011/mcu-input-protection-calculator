"""
AppState tests for the bug-fix branch: parsing, "needs input", range checks,
bandwidth derivation, presets, save and load (bugs 1, 3, 5-10).
Run with: python -m pytest tests/ -v
"""
import json
import os

import pytest

from src.core import app_state as app_state_module
from src.core.app_state import AppState, LoadError, FIELDS, BANDWIDTH_KEYS
from src.core.constants import BANDWIDTH_STARTING_VALUES, ZENER_PRESETS
from src.models.circuit_model import solve_node_voltage

RESULTS_DIV = os.path.join(os.path.dirname(__file__), "..", "results.div")

OHM, KOHM, MOHM = "Ω", "kΩ", "MΩ"

# CLAUDE.md reference case, as the user would type it
REFERENCE = {
    "r1.value": "10", "r1.unit": KOHM, "r1.rating": "200", "r1.tol": "1",
    "r2.value": "18", "r2.unit": KOHM, "r2.rating": "100", "r2.tol": "1",
    "rs.value": "0", "rs.unit": OHM,
    "mcu.vdd": "3.3", "mcu.v_recommended_max": "3.6", "mcu.v_absolute_max": "4.0",
    "mcu.safe_injection_ma": "1.0", "mcu.adc_bits": "12",
    "mcu.vil_factor": "0.3", "mcu.vih_factor": "0.7",
    "system.v_input_max": "30", "system.v_analog_fullscale": "5.1",
    "system.v_logic_high_min": "3.8", "system.v_logic_low_max": "1.0",
}


def ref_state():
    s = AppState()
    s.set_fields(REFERENCE)
    s.select_zener_preset("BZB984-C3V3")
    return s


def write_json(tmp_path, data, name="d.div"):
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


def results_div_data():
    with open(RESULTS_DIV, encoding="utf-8") as f:
        return json.load(f)


# ── Reference case through AppState ──────────────────────────────────────────

def test_reference_case_through_app_state():
    s = ref_state()
    r = s.result
    assert r.r_total_ohms == pytest.approx(28000)
    assert round(r.k_nominal, 3) == 0.643
    assert round(r.v_mcu_typ, 2) == 3.18
    assert round(r.v_mcu_worst_zener, 2) == 3.43
    assert round(r.i_z_ma, 1) == 2.5
    assert s.report.lines() == []


# ── Bug 1: Signal Bandwidth derivation, starting values, save/load ───────────

class TestBandwidthDerivation:
    def test_tau_resistance_is_parallel_plus_rs(self):
        s = ref_state()
        assert s.bandwidth_params.r_tau_ohms == pytest.approx(10000 * 18000 / 28000)
        s.set_field("rs.value", "100")
        assert s.bandwidth_params.r_tau_ohms == pytest.approx(10000 * 18000 / 28000 + 100)
        c_total = 450 + 10 + 3
        assert s.bw_result.tau_ns == pytest.approx((10000 * 18000 / 28000 + 100) * c_total * 1e-3)

    def test_rs_zero_still_gives_bandwidth(self):
        """results.div has R_s = 0; tau used to be 0 and the tab blank."""
        s = AppState()
        s.open_file(RESULTS_DIV)
        s.fill_bandwidth_starting_values()
        s.set_fields({"mcu.vil_factor": "0.3", "mcu.vih_factor": "0.7"})
        b = s.bw_result
        assert b.tau_ns and b.tau_ns > 0
        assert b.f_max_effective_hz is not None
        assert b.limiting_factor

    def test_vil_vih_are_factor_times_vdd_without_3v3_scaling(self):
        s = ref_state()
        s.set_fields({"mcu.vdd": "5.0", "mcu.v_recommended_max": "5.3",
                      "mcu.v_absolute_max": "5.5"})
        assert s.bandwidth_params.vil_v == pytest.approx(1.5)
        assert s.bandwidth_params.vih_v == pytest.approx(3.5)

    def test_v_high_is_lowest_pin_voltage_at_logic_high_input(self):
        s = ref_state()
        expected = solve_node_voltage(3.8, 10100, 17820, s.zener, False).v_node
        assert s.bandwidth_params.v_high == pytest.approx(expected)
        assert s.bandwidth_params.v_high != pytest.approx(3.3)   # not VDD

    def test_never_reaches_vih_is_reported_not_replaced(self):
        s = ref_state()
        s.set_field("system.v_logic_high_min", "3.0")    # pin ~1.9 V < VIH 2.31 V
        b = s.bw_result
        assert b.f_max_effective_hz is None
        assert "never reaches VIH" in b.blocked["effective"]
        assert b.f_max_overflow_hz is not None

    def test_blank_derived_input_names_the_upstream_field(self):
        s = ref_state()
        s.set_field("mcu.vih_factor", "")
        assert "mcu.vih_factor" in s.bw_missing_keys("effective")
        assert "VIH factor" in s.report.needs


class TestBandwidthStartingValues:
    def test_new_design_has_visible_starting_values(self):
        s = AppState()
        for name, v in BANDWIDTH_STARTING_VALUES.items():
            expected = ("1" if v else "0") if isinstance(v, bool) else str(v)
            assert s.fields[f"bw.{name}"] == expected

    def test_c_diode_starting_value_is_datasheet_max(self):
        """Nexperia BZB984 Rev 3, Table 8: C3V3 Cd max 450 pF (f = 1 MHz, VR = 0 V)."""
        assert BANDWIDTH_STARTING_VALUES["c_diode_pf"] == 450

    def test_save_and_load_bandwidth_key(self, tmp_path):
        s = ref_state()
        s.set_fields({"bw.c_diode_pf": "300", "bw.counter_signed": "1", "bw.f_read_hz": "500"})
        path = str(tmp_path / "bw.div")
        assert s.save_to_file(path)
        data = json.loads(open(path, encoding="utf-8").read())
        assert data["bandwidth"]["c_diode_pf"] == 300
        assert data["bandwidth"]["counter_signed"] is True
        assert data["bandwidth"]["counter_bits"] == 16
        s2 = AppState()
        s2.open_file(path)
        assert s2.fields["bw.c_diode_pf"] == "300"
        assert s2.fields["bw.counter_signed"] == "1"
        assert s2.fields["bw.f_read_hz"] == "500"

    def test_file_without_bandwidth_key_loads_blank(self):
        s = AppState()
        warnings = s.open_file(RESULTS_DIV)
        for key in BANDWIDTH_KEYS:
            if FIELDS[key].kind != "bool":
                assert s.fields[key] == "", key
        assert "C_diode" in warnings[0]

    def test_fill_only_blank_or_unreadable(self):
        s = AppState()
        s.set_fields({"bw.c_diode_pf": "200", "bw.c_pin_pf": "abc", "bw.c_stray_pf": ""})
        s.is_dirty = False
        filled = s.fill_bandwidth_starting_values()
        assert s.fields["bw.c_diode_pf"] == "200"
        assert s.fields["bw.c_pin_pf"] == "10"
        assert s.fields["bw.c_stray_pf"] == "3"
        assert set(filled) == {"C_pin", "C_stray"}
        assert s.is_dirty


# ── Bug 3: every field edit recalculates and marks unsaved ───────────────────

class TestEditsMarkDirty:
    def test_rating_edit_updates_margin_and_dirty(self):
        s = ref_state()
        s.is_dirty = False
        before = s.result.r1_margin_pct
        s.set_field("r1.rating", "75")
        assert s.is_dirty
        assert s.result.r1_margin_pct != before
        assert s.result.r1_margin_pct == pytest.approx((75 - s.result.p_r1_mw) / 75 * 100)

    @pytest.mark.parametrize("key", [k for k in FIELDS])
    def test_every_field_marks_dirty(self, key):
        s = AppState()
        s.set_field(key, "1" if FIELDS[key].kind in ("bool",) else
                    (MOHM if FIELDS[key].kind == "unit" else "7"))
        assert s.is_dirty

    def test_same_text_is_not_a_change(self):
        s = AppState()
        s.set_field("r1.unit", s.fields["r1.unit"])
        assert not s.is_dirty


# ── Bug 5: no hidden defaults ────────────────────────────────────────────────

class TestNoHiddenDefaults:
    def test_app_starts_blank(self):
        s = AppState()
        for key, spec in FIELDS.items():
            if key.startswith("bw.") or spec.kind == "unit":
                continue
            assert s.fields[key] == "", key
        assert s.resistors.r1_ohms is None and s.mcu.vdd is None
        assert s.zener.vz_nom is None and s.system.v_input_max is None
        assert s.result.v_mcu_typ is None
        assert s.zener_preset_display() == ("", "")

    def test_new_design_is_blank(self):
        s = ref_state()
        s.file_new()
        assert s.fields["r1.value"] == "" and s.fields["zener.vz_nom"] == ""
        assert s.result.k_nominal is None and not s.is_dirty
        assert s.zener_preset_base is None

    def test_blank_vdd_shows_needs_input_but_rest_computes(self):
        s = ref_state()
        s.set_field("mcu.vdd", "")
        r = s.result
        assert r.resolution_mv_per_lsb is None and r.i_injection_ma is None
        assert r.v_mcu_typ is not None and r.margin_abs_v is not None
        assert s.report.needs == ["VDD/VDDA"]

    def test_unused_blank_fields_block_nothing(self):
        """Rewritten: only ZZK is unused now (VZ min feeds the worst-case power)."""
        s = ref_state()
        s.set_fields({"zener.zzk_typ": "", "zener.zzk_max": ""})
        assert s.report.needs == []
        assert s.result.v_mcu_worst is not None

    def test_blank_vz_min_needed_only_for_worst_power(self):
        s = ref_state()
        s.set_field("zener.vz_min", "")
        assert s.report.needs == ["VZ min"]
        assert s.result.p_r1_worst_mw is None
        assert s.result.v_mcu_worst is not None and s.result.p_r1_mw is not None

    def test_saved_blank_is_null(self, tmp_path):
        s = AppState()
        path = str(tmp_path / "blank.div")
        assert s.save_to_file(path)
        data = json.loads(open(path, encoding="utf-8").read())
        assert data["resistors"]["r1"]["value"] is None
        assert data["mcu"]["vdd"] is None
        assert data["zener"]["preset"] is None


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

    def test_vz_order(self):
        s = ref_state()
        s.set_field("zener.vz_min", "3.4")      # > VZ nom 3.3
        assert any("VZ min" in p and "VZ nom" in p for p in s.report.problems)
        assert s.result.v_mcu_typ is None

    def test_izk_below_izt(self):
        s = ref_state()
        s.set_field("zener.izk_ma", "5")         # = IZT
        assert any(p.startswith("IZK:") for p in s.report.problems)
        assert s.result.v_mcu_typ is None and s.result.v_mcu_worst is None

    def test_vil_below_vih(self):
        s = ref_state()
        s.set_field("mcu.vil_factor", "0.8")
        assert any("VIL factor must be below VIH factor" in p for p in s.report.problems)


class TestSeriesResistorRules:
    @pytest.mark.parametrize("rs", ["", "0"])
    def test_no_series_resistor_needs_nothing(self, rs):
        s = ref_state()
        s.set_fields({"rs.value": rs, "rs.unit": "", "rs.rating": "", "rs.tol": ""})
        assert s.report.needs == []
        assert s.report.lines() == []
        assert s.resistors.rs_ohms == 0.0
        assert s.result.has_rs is False and s.result.i_injection_ma == 0.0
        assert s.result.r_source_ohms == pytest.approx(10000 * 18000 / 28000)

    def test_rs_needs_unit_when_positive(self):
        s = ref_state()
        s.set_fields({"rs.value": "100", "rs.unit": ""})
        assert "R_s unit" in s.report.needs
        assert s.result.r_source_ohms is None

    def test_rs_rating_and_tol_needed_when_positive(self):
        """Rewritten: R_s rating and tolerance are now used (R_s power, and
        R_s min in the injection estimate), so they are listed as needed."""
        s = ref_state()
        s.set_field("rs.value", "100")
        assert s.report.needs == ["R_s power rating", "R_s tolerance"]
        assert not any("Also blank" in line for line in s.report.lines())
        assert s.result.i_injection_ma is None and s.result.p_rs_worst_mw is None
        assert s.result.rs_margin_status is None
        s.set_fields({"rs.rating": "250", "rs.tol": "5"})
        assert s.report.needs == []
        assert s.result.p_rs_worst_mw is not None
        assert s.result.rs_margin_worst_status is not None

    def test_injection_uses_rs_low_tolerance(self):
        s = ref_state()
        s.set_fields({"r1.value": "1", "rs.value": "1", "rs.unit": KOHM,
                      "rs.rating": "250", "rs.tol": "5"})
        r = s.result
        assert r.i_injection_ma == pytest.approx((r.v_mcu_worst - 3.6) / 1050 * 1000)


class TestPowerFollowUp:
    def test_blank_rating_needs_input_without_hint(self):
        s = ref_state()
        s.set_field("r1.rating", "")
        assert s.report.needs == ["R1 power rating"]
        assert s.result.r1_margin_status is None
        assert s.result.r1_margin_worst_status is None

    def test_reference_typical_and_worst(self):
        s = ref_state()
        r = s.result
        for part in ("r1", "r2", "z"):
            assert getattr(r, f"p_{part}_worst_mw") >= getattr(r, f"p_{part}_mw")
        assert r.i_injection_ma == 0.0


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
        assert s.save_to_file(str(tmp_path / "x.div"))


# ── Bug 6: zero ratings ──────────────────────────────────────────────────────

class TestZeroInvalid:
    @pytest.mark.parametrize("key,label", [("r1.rating", "R1 power rating"),
                                           ("r2.rating", "R2 power rating"),
                                           ("zener.ptot_mw", "Zener Ptot")])
    def test_zero_is_invalid_not_a_crash(self, key, label):
        s = ref_state()
        s.set_field(key, "0")
        assert any(p.startswith(label + ":") and "greater than 0" in p
                   for p in s.report.problems)
        assert s.result.v_mcu_typ is not None


# ── Bug 7: atomic save ───────────────────────────────────────────────────────

class TestAtomicSave:
    def test_failed_write_keeps_existing_file(self, tmp_path, monkeypatch):
        path = tmp_path / "keep.div"
        path.write_text("ORIGINAL", encoding="utf-8")
        s = ref_state()

        def broken_dump(obj, f, **kw):
            f.write('{"partial": ')
            raise OSError("disk full")
        monkeypatch.setattr(app_state_module.json, "dump", broken_dump)
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


# ── Bug 8: loading files ─────────────────────────────────────────────────────

class TestLoading:
    def test_null_resistor_value_loads_blank(self, tmp_path):
        data = results_div_data()
        data["resistors"]["r1"]["value"] = None
        s = AppState()
        warnings = s.open_file(write_json(tmp_path, data))
        assert s.fields["r1.value"] == ""
        assert s.resistors.r1_ohms is None
        assert "R1 value" in warnings[0]

    def test_one_warning_lists_all_missing(self, tmp_path):
        data = results_div_data()
        del data["mcu"]["vdd"]
        data["zener"]["izt_ma"] = None
        del data["system"]
        s = AppState()
        warnings = s.open_file(write_json(tmp_path, data))
        assert len([w for w in warnings if "missing" in w]) == 1
        for label in ("VDD/VDDA", "IZT", "Max Input", "Logic Low"):
            assert label in warnings[0]
        # R_s = 0: its rating/tolerance (null in results.div) aren't listed
        assert "R_s power rating" not in warnings[0]

    @pytest.mark.parametrize("mutate,where", [
        (lambda d: d["mcu"].__setitem__("vdd", "abc"), "mcu.vdd"),
        (lambda d: d["mcu"].__setitem__("vdd", True), "mcu.vdd"),
        (lambda d: d["resistors"]["r1"].__setitem__("unit", "kOhm"), "resistors.r1.unit"),
        (lambda d: d["resistors"]["r2"].__setitem__("unit", 5), "resistors.r2.unit"),
        (lambda d: d.__setitem__("resistors", []), "resistors"),
        (lambda d: d["resistors"].__setitem__("r_series", "x"), "resistors.r_series"),
        (lambda d: d.__setitem__("bandwidth", {"counter_bits": 16.5}), "bandwidth.counter_bits"),
        (lambda d: d.__setitem__("bandwidth", {"counter_signed": "no"}), "bandwidth.counter_signed"),
        (lambda d: d.__setitem__("notes", 12), "notes"),
        (lambda d: d["zener"].__setitem__("preset", 3), "zener.preset"),
    ])
    def test_malformed_rejected_and_state_untouched(self, tmp_path, mutate, where):
        s = ref_state()
        s.current_file = "previous.div"
        s.set_field("notes", "keep me")
        fields_before = dict(s.fields)
        dirty_before = s.is_dirty
        data = results_div_data()
        mutate(data)
        with pytest.raises(LoadError) as exc:
            s.open_file(write_json(tmp_path, data))
        assert str(exc.value).startswith(where)
        assert s.fields == fields_before
        assert s.current_file == "previous.div"
        assert s.is_dirty == dirty_before
        assert s.result.v_mcu_typ is not None

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
            s.open_file(RESULTS_DIV)
        assert s.ignore_changes is False
        s.set_fields_callback(None)
        s.is_dirty = False
        s.set_field("r1.value", "12")
        assert s.is_dirty

    def test_megaohm_accepted(self, tmp_path):
        data = results_div_data()
        data["resistors"]["r2"] = {"value": 1.5, "unit": MOHM, "rating_mw": 63, "tolerance_pct": 1}
        s = AppState()
        s.open_file(write_json(tmp_path, data))
        assert s.resistors.r2_ohms == pytest.approx(1.5e6)

    def test_results_div_still_loads(self):
        s = AppState()
        s.open_file(RESULTS_DIV)
        assert s.resistors.r1_ohms == 8200 and s.resistors.r2_ohms == 29000
        assert s.fields["mcu.adc_bits"] == "" and s.fields["mcu.vil_factor"] == ""
        assert s.zener_preset_display() == ("BZB984-C3V3", "")
        assert not s.is_dirty


# ── Bug 9: preset name after an edit ─────────────────────────────────────────

class TestPresetModified:
    def test_edit_shows_modified_and_saves_custom(self, tmp_path):
        s = ref_state()
        assert s.zener_preset_display() == ("BZB984-C3V3", "")
        s.set_field("zener.vz_max", "3.6")
        assert s.zener_preset_display() == ("Custom", "modified from BZB984-C3V3")
        path = str(tmp_path / "mod.div")
        assert s.save_to_file(path)
        z = json.loads(open(path, encoding="utf-8").read())["zener"]
        assert z["preset"] == "Custom" and z["preset_base"] == "BZB984-C3V3"
        s2 = AppState()
        s2.open_file(path)
        assert s2.zener_preset_display() == ("Custom", "modified from BZB984-C3V3")
        assert s2.fields["zener.vz_max"] == "3.6"

    def test_unmodified_saves_preset_name(self, tmp_path):
        s = ref_state()
        path = str(tmp_path / "p.div")
        s.save_to_file(path)
        z = json.loads(open(path, encoding="utf-8").read())["zener"]
        assert z["preset"] == "BZB984-C3V3" and z["preset_base"] is None

    def test_editing_back_restores_preset(self):
        s = ref_state()
        s.set_field("zener.ptot_mw", "300")
        s.set_field("zener.ptot_mw", "265")
        assert s.zener_preset_display() == ("BZB984-C3V3", "")

    def test_old_file_with_edited_values_shows_modified(self, tmp_path):
        data = results_div_data()
        data["zener"]["vz_max"] = 3.7
        s = AppState()
        s.open_file(write_json(tmp_path, data))
        assert s.zener_preset_display() == ("Custom", "modified from BZB984-C3V3")

    def test_preset_fills_visible_fields(self):
        s = AppState()
        s.select_zener_preset("BZB984-C5V1")
        assert s.fields["zener.vz_nom"] == "5.1"
        assert s.zener.vz_nom == ZENER_PRESETS["BZB984-C5V1"]["vz_nom"]
        assert s.is_dirty


# ── Bug 10: new MCU fields saved ─────────────────────────────────────────────

def test_adc_bits_and_factors_round_trip(tmp_path):
    s = ref_state()
    s.set_field("mcu.adc_bits", "16")
    path = str(tmp_path / "m.div")
    s.save_to_file(path)
    m = json.loads(open(path, encoding="utf-8").read())["mcu"]
    assert m["adc_bits"] == 16 and m["vil_factor"] == 0.3 and m["vih_factor"] == 0.7
    s2 = AppState()
    s2.open_file(path)
    assert s2.mcu.adc_bits == 16
    assert s2.result.resolution_mv_per_lsb == pytest.approx(3.3 / 65536 * 1000 / (18 / 28))
