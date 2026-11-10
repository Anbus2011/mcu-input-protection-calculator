"""
Tests for the .div file, format 2.0 (src/core/div_format.py) and the example
files in examples/.
Run with: python -m pytest tests/ -v
"""
import copy
import json
import os

import pytest

from src.core import div_format
from src.core.div_format import (
    FORMAT, VALUE, DivError, number_paths, parse_json, read_json, results_for_file,
    to_text, validate, with_results, write_json,
)
from src.models import clamp_solver
from src.models.clamp_solver import solve
from tests.designs import (
    KOHM, V1_FILE, blank_design, change, schottky_rail, zener_reference,
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EXAMPLES = {
    "zener_gnd_bzb984_c3v3.div": zener_reference,
    "schottky_rail_bat54cv.div": schottky_rail,
}


def example_path(name):
    return os.path.join(ROOT, "examples", name)


def paths(problems):
    return [p.path for p in problems]


def problem(problems, path):
    hits = [p for p in problems if p.path == path]
    assert len(hits) == 1, f"{path}: {[str(p) for p in problems]}"
    return hits[0]


# ── Example files ────────────────────────────────────────────────────────────

class TestExamples:
    @pytest.mark.parametrize("name", list(EXAMPLES))
    def test_valid(self, name):
        assert validate(read_json(example_path(name))) == []

    @pytest.mark.parametrize("name", list(EXAMPLES))
    def test_inputs_are_the_test_designs(self, name):
        data = read_json(example_path(name))
        data.pop("results")
        assert data == EXAMPLES[name]()

    @pytest.mark.parametrize("name", list(EXAMPLES))
    def test_stored_results_are_what_the_solver_gives(self, name):
        """Regenerate with: python divcheck.py examples/x.div examples/x.div"""
        data = read_json(example_path(name))
        assert data["results"] == results_for_file(solve(data))

    @pytest.mark.parametrize("name", list(EXAMPLES))
    def test_fixtures_are_not_marked_checked_and_say_where_columns_came_from(self, name):
        data = read_json(example_path(name))
        for section in ("clamp_diode", "mcu"):
            assert data[section]["checked"] is False
            assert data[section]["source"] and data[section]["note"]
        note = data["clamp_diode"]["note"]
        for column in ("v_min", "v_typ", "v_max"):
            assert column in note

    def test_one_of_each_kind(self):
        z = read_json(example_path("zener_gnd_bzb984_c3v3.div"))["clamp_diode"]
        s = read_json(example_path("schottky_rail_bat54cv.div"))["clamp_diode"]
        assert (z["type"], z["anode"], z["cathode"]) == ("zener", "gnd", "node")
        assert (s["type"], s["anode"], s["cathode"]) == ("schottky", "node", "vdd")

    def test_format_doc_quotes_the_stored_analog_range_value(self):
        """docs/div_v2_format.md explains this 1.3 mV FAIL."""
        data = read_json(example_path("schottky_rail_bat54cv.div"))
        check = next(c for c in data["results"]["checks"] if c["id"] == "analog_range")
        assert check == {"id": "analog_range", "status": "FAIL", "value": 3.301258,
                         "limit": 3.3, "unit": "V"}
        assert 3.3 < 5.1 * 18.18 / 28.08 < 3.302
        with open(os.path.join(ROOT, "docs", "div_v2_format.md"), encoding="utf-8") as f:
            doc = f.read()
        assert "`value` 3.301258 V against `limit` 3.3 V" in doc
        assert "injection" not in doc.replace("injection into", "")

    def test_results_div_is_gone_or_rejected(self):
        """No v1 converter: a v1 file gets one clear message."""
        problems = validate(copy.deepcopy(V1_FILE))
        assert len(problems) == 1
        assert problems[0].path == "version" and problems[0].kind == FORMAT
        assert "format 1.0" in problems[0].message
        assert "reads .div format 2.0" in problems[0].message
        assert "no converter" in problems[0].message


# ── Structure ────────────────────────────────────────────────────────────────

class TestStructure:
    def test_schema_numbers_are_the_solver_numbers(self):
        assert sorted(number_paths()) == sorted(clamp_solver.NUMBER_RULES)

    def test_schema_sections(self):
        assert list(div_format.SCHEMA) == ["version", "created", "notes", "resistors",
                                           "clamp_diode", "mcu", "system", "bandwidth"]
        for section in ("clamp_diode", "mcu"):
            assert list(div_format.SCHEMA[section])[:4] == ["part", "source", "checked", "note"]
        assert "zener" not in div_format.SCHEMA

    def test_v1_keys_kept(self):
        """Section and key names of format 1.0 are kept where the field exists."""
        s = div_format.SCHEMA
        assert set(s["resistors"]) == {"r1", "r2", "r_series"}
        assert set(s["resistors"]["r1"]) == {"value", "unit", "rating_mw", "tolerance_pct"}
        assert {"vdd", "v_recommended_max", "v_absolute_max",
                "adc_bits", "vil_factor", "vih_factor"} <= set(s["mcu"])
        assert {"v_input_max", "v_analog_fullscale", "v_logic_high_min",
                "v_logic_low_max"} <= set(s["system"])
        assert "ptot_mw" in s["clamp_diode"] and "c_stray_pf" in s["bandwidth"]

    def test_injection_limit_key_is_gone(self):
        """There is no injection-limit key: it is not in the schema, a file
        that has it gets a format problem, and the examples don't have it."""
        assert "safe_injection_ma" not in div_format.SCHEMA["mcu"]
        d = zener_reference()
        d["mcu"]["safe_injection_ma"] = 1.0
        problems = validate(d)
        assert paths(problems) == ["mcu.safe_injection_ma"]
        assert problems[0].message == "unknown key"
        for name in EXAMPLES:
            assert "injection" not in open(example_path(name), encoding="utf-8").read()

    def test_blank_design_is_valid(self):
        assert validate(blank_design()) == []

    def test_results_are_optional_and_not_read(self):
        d = zener_reference()
        assert validate(d) == []
        assert validate(dict(d, results=None)) == []
        assert validate(dict(d, results={"anything": [1, 2, 3]})) == []
        assert paths(validate(dict(d, results=[]))) == ["results"]

    @pytest.mark.parametrize("data", [None, [], "text", 5])
    def test_not_an_object(self, data):
        assert paths(validate(data)) == ["file"]

    @pytest.mark.parametrize("version,text", [
        (None, "missing"), ("3.0", "expected \"2.0\", got \"3.0\""),
        (2.0, "expected \"2.0\", got 2.0"), ("1.0", "format 1.0")])
    def test_version(self, version, text):
        d = zener_reference()
        if version is None:
            del d["version"]
        else:
            d["version"] = version
        problems = validate(d)
        assert paths(problems) == ["version"] and text in problems[0].message

    def test_missing_keys(self):
        d = zener_reference()
        del d["mcu"]["vdd"]
        del d["system"]
        del d["clamp_diode"]["reverse"][2]["v_typ"]
        del d["resistors"]["r2"]["unit"]
        problems = validate(d)
        assert set(paths(problems)) == {"mcu.vdd", "system", "resistors.r2.unit",
                                        "clamp_diode.reverse[2].v_typ"}
        assert all(p.kind == FORMAT and "missing" in p.message for p in problems)

    def test_unknown_keys(self):
        d = zener_reference()
        d["zener"] = {}
        d["mcu"]["vdda"] = 3.3
        d["clamp_diode"]["capacitance"] = 450
        d["clamp_diode"]["forward"] = [dict(i_ma=1, v_min=0.5, v_typ=0.6, v_max=0.7, temp=25),
                                       dict(i_ma=10, v_min=0.7, v_typ=0.8, v_max=0.9)]
        problems = validate(d)
        assert set(paths(problems)) == {"zener", "mcu.vdda", "clamp_diode.capacitance",
                                        "clamp_diode.forward[0].temp"}
        assert all(p.message == "unknown key" for p in problems)

    @pytest.mark.parametrize("mutate,where,text", [
        (lambda d: d["mcu"].__setitem__("vdd", "abc"), "mcu.vdd", "expected a number"),
        (lambda d: d["mcu"].__setitem__("vdd", "3.3"), "mcu.vdd", "expected a number"),
        (lambda d: d["mcu"].__setitem__("vdd", True), "mcu.vdd", "expected a number"),
        (lambda d: d["mcu"].__setitem__("vdd", float("nan")), "mcu.vdd", "finite"),
        (lambda d: d["mcu"].__setitem__("adc_bits", 12.5), "mcu.adc_bits", "whole number"),
        (lambda d: d["resistors"]["r1"].__setitem__("unit", "kOhm"), "resistors.r1.unit",
         "unknown unit 'kOhm'"),
        (lambda d: d["resistors"]["r2"].__setitem__("unit", 5), "resistors.r2.unit",
         "expected a unit"),
        (lambda d: d.__setitem__("resistors", []), "resistors", "expected an object"),
        (lambda d: d["resistors"].__setitem__("r_series", "x"), "resistors.r_series",
         "expected an object"),
        (lambda d: d.__setitem__("notes", 12), "notes", "expected text"),
        (lambda d: d["mcu"].__setitem__("pin_type", 5), "mcu.pin_type", "expected text"),
        (lambda d: d["clamp_diode"].__setitem__("checked", "yes"), "clamp_diode.checked",
         "true or false"),
        (lambda d: d["mcu"].__setitem__("checked", None), "mcu.checked", "true or false"),
        (lambda d: d["clamp_diode"].__setitem__("type", "tvs"), "clamp_diode.type", "zener"),
        (lambda d: d["clamp_diode"].__setitem__("anode", "ground"), "clamp_diode.anode",
         "node"),
        (lambda d: d["clamp_diode"].__setitem__("cathode", 0), "clamp_diode.cathode", "node"),
        (lambda d: d["clamp_diode"].__setitem__("reverse", {}), "clamp_diode.reverse",
         "expected a list"),
        (lambda d: d["clamp_diode"]["reverse"].__setitem__(1, [1, 2, 3, 4]),
         "clamp_diode.reverse[1]", "expected an object"),
        (lambda d: d["clamp_diode"]["reverse"][4].__setitem__("v_max", "1.9"),
         "clamp_diode.reverse[4].v_max", "expected a number"),
    ])
    def test_format_problems(self, mutate, where, text):
        d = zener_reference()
        mutate(d)
        problems = validate(d)
        p = problem(problems, where)
        assert text in p.message and p.kind == FORMAT
        assert str(p).startswith(where + ": ")
        assert len(problems) == 1

    @pytest.mark.parametrize("mutate,where,text", [
        (lambda d: d["resistors"]["r1"].__setitem__("value", -5), "resistors.r1.value",
         "greater than 0"),
        (lambda d: d["resistors"]["r1"].__setitem__("tolerance_pct", 150),
         "resistors.r1.tolerance_pct", "below 100"),
        (lambda d: d["mcu"].__setitem__("adc_bits", 0), "mcu.adc_bits", "1 to 32"),
        (lambda d: d["mcu"].__setitem__("v_pin_min", 0.3), "mcu.v_pin_min", "above 0"),
        (lambda d: d["bandwidth"].__setitem__("margin_factor", 0.9),
         "bandwidth.margin_factor", "1 or more"),
        (lambda d: d["clamp_diode"]["reverse"][3].__setitem__("i_ma", 0.004),
         "clamp_diode.reverse[3].i_ma", "row above"),
        (lambda d: d["clamp_diode"]["reverse"][0].__setitem__("v_max", 1.0),
         "clamp_diode.reverse[0].v_max", "v_min ≤ v_typ ≤ v_max"),
        (lambda d: d["clamp_diode"].__setitem__("forward", [
            dict(i_ma=1, v_min=0.5, v_typ=0.6, v_max=0.7)]), "clamp_diode.forward",
         "at least 2 rows"),
    ])
    def test_value_problems(self, mutate, where, text):
        d = zener_reference()
        mutate(d)
        p = problem(validate(d), where)
        assert text in p.message and p.kind == VALUE

    def test_cross_field_rules(self):
        problems = validate(zener_reference(mcu__vil_factor=0.8))
        assert set(paths(problems)) == {"mcu.vil_factor", "mcu.vih_factor"}
        assert all("VIL factor must be below VIH factor" in p.message and p.kind == VALUE
                   for p in problems)
        problems = validate(zener_reference(system__v_input_min=40))
        assert paths(problems) == ["system.v_input_min"]

    def test_wiring(self):
        problems = validate(zener_reference(clamp_diode__anode="node"))
        assert set(paths(problems)) == {"clamp_diode.anode", "clamp_diode.cathode"}
        assert all(p.kind == VALUE for p in problems)
        assert validate(zener_reference(clamp_diode__anode=None)) == []

    def test_every_problem_is_reported_not_only_the_first(self):
        d = zener_reference()
        d["resistors"]["r1"]["unit"] = "kOhm"
        d["resistors"]["r2"]["value"] = "18"
        d["clamp_diode"]["checked"] = 1
        d["clamp_diode"]["reverse"][2]["v_typ"] = 9.9
        d["clamp_diode"]["cathode"] = "pin"
        del d["mcu"]["vih_factor"]
        d["mcu"]["vdd"] = -3.3
        d["system"]["v_touch"] = "60"
        d["bandwidth"]["extra"] = 1
        d["created"] = 20261109
        problems = validate(d)
        expected = {
            "created", "resistors.r1.unit", "resistors.r2.value", "clamp_diode.checked",
            "clamp_diode.cathode", "clamp_diode.reverse[2].v_typ",
            "clamp_diode.reverse[3].v_typ", "mcu.vih_factor", "mcu.vdd", "system.v_touch",
            "bandwidth.extra"}
        assert expected <= set(paths(problems))
        for p in problems:
            assert str(p) == f"{p.path}: {p.message}" and p.message

    def test_null_table_is_blank_not_empty(self):
        """[] means "not modelled"; null means "not filled in yet"."""
        d = zener_reference(clamp_diode__forward=None)
        assert validate(d) == []
        r = solve(d)
        assert r["needs_input"] == ["clamp_diode.forward"]
        assert r["voltages"]["levels"]["max_input"]["typ"] is None

    def test_null_is_never_a_problem(self):
        d = zener_reference()
        for section in ("mcu", "system", "bandwidth"):
            for key, value in d[section].items():
                if not isinstance(value, bool):
                    d[section][key] = None
        d["clamp_diode"]["reverse"][0]["v_min"] = None
        d["resistors"]["r1"]["value"] = None
        d["created"] = None
        assert validate(d) == []


# ── Results stored in the file ───────────────────────────────────────────────

class TestStoredResults:
    def test_keys(self):
        stored = results_for_file(solve(zener_reference()))
        assert list(stored) == ["solver_version", "verdict", "checks", "info", "voltages",
                                "needs_input", "notes", "warnings"]
        assert stored["solver_version"] == clamp_solver.SOLVER_VERSION
        assert "details" not in stored and "missing" not in stored
        for c in stored["checks"]:
            assert list(c) == ["id", "status", "value", "limit", "unit"]

    def test_rounded_to_7_significant_digits(self):
        full = solve(schottky_rail())
        stored = results_for_file(full)
        a = stored["voltages"]["levels"]["max_input"]["typ"]
        b = full["voltages"]["levels"]["max_input"]["typ"]
        assert a == pytest.approx(b, abs=1e-6) and a == float(f"{b:.7g}")
        assert stored["voltages"]["vih"] == 2.31

    def test_whole_numbers_are_written_as_decimals(self):
        """A rating of 200 in a file and 200.0 typed in the app give the same
        text, so the app's Save and divcheck.py write identical results."""
        stored = results_for_file(solve(zener_reference()))
        limit = next(c for c in stored["checks"] if c["id"] == "power_r1")["limit"]
        v_in = stored["voltages"]["levels"]["max_input"]["v_in"]
        assert (limit, v_in) == (200.0, 30.0) and type(limit) is float and type(v_in) is float
        assert stored["voltages"]["levels"]["zero"]["v_in"] == 0.0

    def test_note_explains_a_missing_limit(self):
        stored = results_for_file(solve(zener_reference()))
        assert len(stored["notes"]) == 1 and "never reads high" in stored["notes"][0]
        assert results_for_file(solve(schottky_rail()))["notes"] == []

    def test_with_results_replaces_only_results(self):
        d = dict(zener_reference(), results={"stale": True})
        out = with_results(d, solve(d))
        assert list(out)[-1] == "results" and "stale" not in out["results"]
        out.pop("results")
        assert out == zener_reference()
        assert d["results"] == {"stale": True}         # the input is not changed

    def test_stored_results_do_not_change_the_solution(self):
        d = zener_reference()
        assert solve(dict(d, results={"verdict": "PASS"})) == solve(d)


# ── Reading and writing ──────────────────────────────────────────────────────

class TestReadWrite:
    def test_round_trip(self, tmp_path):
        path = str(tmp_path / "a.div")
        data = with_results(schottky_rail(), solve(schottky_rail()))
        write_json(path, data)
        assert read_json(path) == data
        assert validate(read_json(path)) == []

    def test_written_text(self, tmp_path):
        path = tmp_path / "a.div"
        write_json(str(path), zener_reference())
        text = path.read_text(encoding="utf-8")
        assert text.isascii() and text.endswith("}\n")
        assert '"unit": "k\\u03a9"' in text
        # a table row, a resistor and an empty table each take one line
        assert '      {"i_ma": 1, "v_min": 2.51, "v_typ": 2.69, "v_max": 2.91},\n' in text
        assert '    "r1": {"value": 10, "unit": "k\\u03a9", "rating_mw": 200, ' \
               '"tolerance_pct": 1},\n' in text
        assert '    "forward": [],\n' in text
        assert json.loads(text) == zener_reference()

    def test_nan_is_never_written(self, tmp_path):
        path = tmp_path / "a.div"
        with pytest.raises(ValueError):
            write_json(str(path), {"x": float("nan")})
        assert list(tmp_path.iterdir()) == []

    def test_failed_write_keeps_the_existing_file(self, tmp_path, monkeypatch):
        path = tmp_path / "keep.div"
        path.write_text("ORIGINAL", encoding="utf-8")

        def broken_dump(obj, f, **kw):
            f.write('{"partial": ')
            raise OSError("disk full")
        monkeypatch.setattr(div_format.json, "dump", broken_dump)
        with pytest.raises(OSError):
            write_json(str(path), zener_reference())
        assert path.read_text(encoding="utf-8") == "ORIGINAL"
        assert [p.name for p in tmp_path.iterdir()] == ["keep.div"]

    def test_missing_folder(self, tmp_path):
        with pytest.raises(OSError):
            write_json(str(tmp_path / "nope" / "a.div"), zener_reference())

    def test_read_errors(self, tmp_path):
        bad = tmp_path / "bad.div"
        bad.write_text("{not json", encoding="utf-8")
        with pytest.raises(DivError) as exc:
            read_json(str(bad))
        assert str(exc.value).startswith("file: not valid JSON")
        assert exc.value.problems[0].kind == FORMAT
        with pytest.raises(DivError) as exc:
            read_json(str(tmp_path / "missing.div"))
        assert "can't read" in str(exc.value)

    def test_byte_order_mark_and_plain_utf8_are_read(self, tmp_path):
        path = tmp_path / "bom.div"
        text = json.dumps(zener_reference(), ensure_ascii=False)
        assert KOHM in text
        path.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
        assert read_json(str(path)) == zener_reference()

    def test_parse_json_is_read_json_without_the_file(self, tmp_path):
        """read_json parses a file's text with parse_json: the same data and
        the same problem for the same text."""
        for name in EXAMPLES:
            with open(example_path(name), encoding="utf-8") as f:
                assert parse_json(f.read()) == read_json(example_path(name))
        assert parse_json(json.dumps(zener_reference())) == zener_reference()
        assert parse_json("[1, 2]") == [1, 2]           # not validated here
        bad = tmp_path / "bad.div"
        bad.write_text("{not json", encoding="utf-8")
        with pytest.raises(DivError) as from_file:
            read_json(str(bad))
        with pytest.raises(DivError) as from_text:
            parse_json("{not json")
        assert from_text.value.problems == from_file.value.problems
        assert str(from_text.value).startswith("file: not valid JSON")
        assert from_text.value.problems[0].kind == FORMAT

    @pytest.mark.parametrize("make", [zener_reference, schottky_rail, blank_design])
    def test_to_text_is_what_write_json_writes(self, make, tmp_path):
        data = with_results(make(), solve(make()))
        path = tmp_path / "a.div"
        write_json(str(path), data)
        with open(path, encoding="utf-8", newline="") as f:
            written = f.read()
        assert to_text(data) == written.replace("\r\n", "\n")   # line ends apart
        assert to_text(data).endswith("}\n") and to_text(data).isascii()
        assert json.loads(to_text(data)) == data

    @pytest.mark.parametrize("name", list(EXAMPLES))
    def test_to_text_of_an_example_is_the_example_file(self, name):
        with open(example_path(name), encoding="utf-8") as f:
            assert to_text(read_json(example_path(name))) == f.read()

    def test_to_text_never_writes_nan(self):
        with pytest.raises(ValueError):
            to_text({"x": float("nan")})

    def test_megaohm_unit(self):
        d = change(zener_reference(), resistors__r2__unit="MΩ")
        assert validate(d) == []
        assert solve(d)["details"]["r_total_ohms"] == pytest.approx(10e3 + 18e6)
