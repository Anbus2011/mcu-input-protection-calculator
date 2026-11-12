"""
Tests for the command-line checker, divcheck.py.
Run with: python -m pytest tests/ -v
"""
import copy
import json
import os
import subprocess
import sys

import pytest

import divcheck
from src.core.div_format import read_json, results_for_file, write_json
from src.models.clamp_solver import solve
from tests.designs import V1_FILE, blank_design, schottky_rail, zener_reference

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ZENER = os.path.join(ROOT, "examples", "zener_gnd_bzb984_c3v3.div")
SCHOTTKY = os.path.join(ROOT, "examples", "schottky_rail_bat54cv.div")


def write(tmp_path, data, name="in.div"):
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


class TestSummary:
    @pytest.mark.parametrize("path", [ZENER, SCHOTTKY])
    def test_valid_file_exits_0_whatever_the_statuses(self, path, capsys):
        assert divcheck.main([path]) == 0
        out = capsys.readouterr().out
        assert "VERDICT: FAIL" in out            # both examples fail one check
        assert out.isascii()
        assert "format 2.0, solver 2.0.0" in out

    def test_zener_summary(self, capsys):
        divcheck.main([ZENER])
        out = capsys.readouterr().out
        lines = {line.split()[0]: line.split() for line in out.splitlines() if line.strip()}
        assert lines["pin_max_safe"][1:] == ["PASS", "3.239", "V", "limit", "3.600", "V"]
        assert "injection" not in lines
        assert lines["logic_high"][1:4] == ["FAIL", "1.831", "V"]
        assert lines["analog_error"][1] == "info"
        assert lines["f_may_work"][1] == "none"
        assert "The pin never reads high" in out
        # tau has a value; the edge times do not (the pin never reads high)
        assert "  tau                    2973.729 ns\n" in out
        assert "t_rise" not in out and "t_fall" not in out
        assert "Max Input         30.000    2.840    3.020    3.239" in out
        assert "No forward data: forward conduction is not modelled" in out
        assert "Not yet checked against the data sheet: clamp diode, MCU" in out
        assert "R1 10 kohm, R2 18 kohm, no R_s" in out
        assert "Needs input" not in out and "Warnings" not in out

    def test_schottky_summary(self, capsys):
        divcheck.main([SCHOTTKY])
        out = capsys.readouterr().out
        assert "Clamp diode: BAT54CV (schottky), anode node, cathode vdd" in out
        assert "f_may_work               1.347 MHz" in out
        assert "f_reliable             897.964 kHz" in out
        assert ("  rail_current              2.493 mA\n"
                "  tau                     116.871 ns\n"
                "  t_rise                  353.560 ns\n"
                "  t_fall                  255.192 ns\n\n") in out
        assert "No forward data" not in out and "No reverse data" not in out

    def test_edge_rows_are_the_solvers_details(self, capsys):
        """tau, t_rise and t_fall are the solver's details, in ns, printed
        under Information (they are not information rows of the file)."""
        divcheck.main([SCHOTTKY])
        out = capsys.readouterr().out
        details = solve(read_json(SCHOTTKY))["details"]
        rows = {line.split()[0]: line.split()[1:] for line in out.splitlines()
                if line.strip()}
        for label, key in divcheck.EDGE_ROWS:
            assert rows[label] == [f"{details[key]:.3f}", "ns"]
        assert "tau" not in {row["id"] for row in read_json(SCHOTTKY)["results"]["info"]}

    def test_edge_rows_without_a_value_are_left_out(self, tmp_path, capsys):
        assert divcheck.main([write(tmp_path, blank_design())]) == 0
        out = capsys.readouterr().out
        assert not any(line.split()[0] in ("tau", "t_rise", "t_fall")
                       for line in out.splitlines() if line.strip())

    def test_needs_input_is_listed_and_still_exits_0(self, tmp_path, capsys):
        data = zener_reference(mcu__vdd=None, resistors__r1__rating_mw=None)
        assert divcheck.main([write(tmp_path, data)]) == 0
        out = capsys.readouterr().out
        assert "Needs input:\n  resistors.r1.rating_mw\n  mcu.vdd" in out
        assert "needs input" in out

    def test_blank_design(self, tmp_path, capsys):
        assert divcheck.main([write(tmp_path, blank_design())]) == 0
        out = capsys.readouterr().out
        assert "VERDICT: needs input" in out
        # Both tables are null (not filled in), which is not the same as []
        # (not modelled: "No forward data" / "No reverse data").
        assert "  Forward table not filled in: needs input\n" in out
        assert "  Reverse table not filled in: needs input\n" in out
        assert "No forward data" not in out and "No reverse data" not in out

    @pytest.mark.parametrize("table", ["forward", "reverse"])
    def test_null_table_is_not_filled_in(self, tmp_path, capsys, table):
        """null: the table is still needed. It is not called "not modelled"."""
        other = "reverse" if table == "forward" else "forward"
        data = schottky_rail(**{f"clamp_diode__{table}": None})
        assert divcheck.main([write(tmp_path, data)]) == 0
        out = capsys.readouterr().out
        assert f"  {table.capitalize()} table not filled in: needs input\n" in out
        assert f"No {table} data" not in out and "is not modelled" not in out
        assert f"{other.capitalize()} table not filled in" not in out
        assert f"Needs input:\n  clamp_diode.{table}\n" in out
        assert out.isascii()

    @pytest.mark.parametrize("table", ["forward", "reverse"])
    def test_empty_table_is_not_modelled(self, tmp_path, capsys, table):
        """[]: the direction is not modelled, and nothing is asked for."""
        data = schottky_rail(**{f"clamp_diode__{table}": []})
        assert divcheck.main([write(tmp_path, data)]) == 0
        out = capsys.readouterr().out
        assert f"  No {table} data: {table} conduction is not modelled\n" in out
        assert "not filled in" not in out and "Needs input" not in out

    def test_one_table_null_and_the_other_empty(self, tmp_path, capsys):
        data = zener_reference(clamp_diode__reverse=None)       # forward is []
        assert divcheck.main([write(tmp_path, data)]) == 0
        out = capsys.readouterr().out
        assert ("  No forward data: forward conduction is not modelled\n"
                "  Reverse table not filled in: needs input\n") in out

    def test_checked_parts_are_not_listed(self, tmp_path, capsys):
        data = zener_reference(clamp_diode__checked=True)
        divcheck.main([write(tmp_path, data)])
        assert "Not yet checked against the data sheet: MCU\n" in capsys.readouterr().out


class TestOutputFiles:
    def test_out_div_has_results_filled_in(self, tmp_path, capsys):
        src = write(tmp_path, zener_reference())
        out = str(tmp_path / "out.div")
        assert divcheck.main([src, out]) == 0
        data = read_json(out)
        assert data["results"] == results_for_file(solve(zener_reference()))
        data.pop("results")
        assert data == zener_reference()
        assert json.loads(open(src, encoding="utf-8").read()) == zener_reference()

    def test_in_place(self, tmp_path, capsys):
        path = write(tmp_path, dict(schottky_rail(), results={"stale": True}))
        assert divcheck.main([path, path]) == 0
        data = read_json(path)
        assert "stale" not in data["results"]
        assert data["results"]["verdict"] == "FAIL"
        assert [p.name for p in tmp_path.iterdir()] == ["in.div"]

    def test_json_writes_the_results_alone(self, tmp_path, capsys):
        src = write(tmp_path, schottky_rail())
        out = str(tmp_path / "r.json")
        assert divcheck.main([src, "--json", out]) == 0
        assert read_json(out) == results_for_file(solve(schottky_rail()))
        assert sorted(p.name for p in tmp_path.iterdir()) == ["in.div", "r.json"]

    def test_both_outputs(self, tmp_path, capsys):
        src = write(tmp_path, schottky_rail())
        out, js = str(tmp_path / "o.div"), str(tmp_path / "r.json")
        assert divcheck.main([src, out, "--json", js]) == 0
        assert read_json(out)["results"] == read_json(js)

    def test_write_failure_exits_2(self, tmp_path, capsys):
        src = write(tmp_path, schottky_rail())
        assert divcheck.main([src, str(tmp_path / "missing" / "o.div")]) == 2
        assert "can't write" in capsys.readouterr().err


class TestSameResultsAsTheApp:
    """The app's Save and divcheck.py write identical "results" sections."""

    RS = dict(value=100, unit="Ω", rating_mw=250, tolerance_pct=5)
    DESIGNS = {
        "zener example": lambda: read_json(ZENER),
        "schottky example": lambda: read_json(SCHOTTKY),
        "with R_s": lambda: zener_reference(resistors__r_series=TestSameResultsAsTheApp.RS,
                                            system__v_touch=60, system__f_required_hz=20000,
                                            system__v_logic_high_min=24),
    }

    @staticmethod
    def results_text(path):
        text = open(path, encoding="utf-8").read()
        return text[text.index('  "results": {'):]

    @pytest.mark.parametrize("name", list(DESIGNS))
    def test_save_and_divcheck_write_identical_results(self, name, tmp_path, capsys):
        from src.core.app_state import AppState
        source = write(tmp_path, self.DESIGNS[name](), "source.div")
        by_app, by_checker = str(tmp_path / "app.div"), str(tmp_path / "checker.div")

        s = AppState()
        assert s.open_file(source) == []
        assert s.save_to_file(by_app)
        assert divcheck.main([source, by_checker]) == 0

        # the same text, character for character, and so the same values
        assert self.results_text(by_app) == self.results_text(by_checker)
        assert read_json(by_app)["results"] == read_json(by_checker)["results"]
        checks = {c["id"]: c for c in read_json(by_app)["results"]["checks"]}
        assert ("power_rs" in checks) == (name == "with R_s")
        if name == "with R_s":
            assert checks["power_rs"]["limit"] == 250 and checks["power_rs"]["status"] == "PASS"

    @pytest.mark.parametrize("path", [ZENER, SCHOTTKY])
    def test_example_files_hold_what_save_writes(self, path, tmp_path):
        from src.core.app_state import AppState
        s = AppState()
        s.open_file(path)
        out = str(tmp_path / "saved.div")
        assert s.save_to_file(out)
        assert self.results_text(out) == self.results_text(path)


class TestInvalidFiles:
    def test_every_problem_is_listed_and_exit_is_1(self, tmp_path, capsys):
        data = zener_reference()
        data["resistors"]["r1"]["unit"] = "kOhm"
        data["mcu"]["vdd"] = "3.3"
        data["clamp_diode"]["reverse"][5]["v_typ"] = 0.5
        del data["system"]["v_touch"]
        data["extra"] = 1
        out_path = tmp_path / "out.div"
        assert divcheck.main([write(tmp_path, data), str(out_path)]) == 1
        out = capsys.readouterr().out
        assert "in.div: invalid, 5 problems:" in out
        for path in ("resistors.r1.unit: ", "mcu.vdd: ", "clamp_diode.reverse[5].v_typ: ",
                     "system.v_touch: ", "extra: "):
            assert f"  {path}" in out
        assert "VERDICT" not in out
        assert not out_path.exists()             # nothing is written for a bad file

    def test_out_of_range_value_is_invalid(self, tmp_path, capsys):
        data = zener_reference(resistors__r1__tolerance_pct=150)
        assert divcheck.main([write(tmp_path, data)]) == 1
        assert "resistors.r1.tolerance_pct: must be at least 0 and below 100 %" in \
            capsys.readouterr().out

    def test_format_1_file(self, tmp_path, capsys):
        assert divcheck.main([write(tmp_path, copy.deepcopy(V1_FILE))]) == 1
        out = capsys.readouterr().out
        assert "invalid, 1 problem:" in out
        assert "format 1.0" in out and "reads .div format 2.0" in out

    def test_not_json(self, tmp_path, capsys):
        path = tmp_path / "bad.div"
        path.write_text("{not json", encoding="utf-8")
        assert divcheck.main([str(path)]) == 1
        assert "file: not valid JSON" in capsys.readouterr().out

    def test_missing_file_exits_2(self, tmp_path, capsys):
        assert divcheck.main([str(tmp_path / "nope.div")]) == 2
        assert "no such file" in capsys.readouterr().err


class TestCommandLine:
    def test_runs_as_a_script(self, tmp_path):
        out = str(tmp_path / "o.div")
        run = subprocess.run([sys.executable, "divcheck.py", ZENER, out], cwd=ROOT,
                             capture_output=True, text=True)
        assert run.returncode == 0, run.stderr
        assert "VERDICT: FAIL" in run.stdout
        assert read_json(out)["results"] == read_json(ZENER)["results"]

    def test_invalid_file_as_a_script(self, tmp_path):
        run = subprocess.run([sys.executable, "divcheck.py",
                              write(tmp_path, copy.deepcopy(V1_FILE))],
                             cwd=ROOT, capture_output=True, text=True)
        assert run.returncode == 1 and "format 1.0" in run.stdout

    def test_does_not_import_ui_or_numpy(self):
        """Blocks customtkinter, matplotlib, numpy, PIL and tkinter, then runs
        the checker: it must work under a plain Python install."""
        code = (
            "import sys\n"
            "for name in ('numpy', 'customtkinter', 'matplotlib', 'PIL', 'tkinter'):\n"
            "    sys.modules[name] = None\n"
            "import divcheck\n"
            f"code = divcheck.main([{SCHOTTKY!r}])\n"
            "loaded = [m for m in ('numpy', 'customtkinter', 'matplotlib')\n"
            "          if sys.modules.get(m) is not None]\n"
            "assert not loaded, loaded\n"
            "sys.exit(code)\n")
        run = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                             capture_output=True, text=True)
        assert run.returncode == 0, run.stderr
        assert "VERDICT: FAIL" in run.stdout

    def test_usage(self):
        run = subprocess.run([sys.executable, "divcheck.py"], cwd=ROOT,
                             capture_output=True, text=True)
        assert run.returncode == 2
        assert "usage: divcheck.py" in run.stderr and "--json" in run.stderr
