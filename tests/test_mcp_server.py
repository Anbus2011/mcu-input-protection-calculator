"""
Tests for the MCP server, skill/server.py: a gateway to the solver that
returns what divcheck.py prints and writes, and the app's plot sweep as a PNG.
Run with: python -m pytest tests/ -v
"""
import asyncio
import base64
import builtins
import copy
import inspect
import io
import json
import os
import re
import socket
import subprocess
import sys
import time

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.memory import create_connected_server_and_client_session

import divcheck
from skill import plot_png, server
from src.core import constants
from src.core.app_state import AppState
from src.core.div_format import read_json, results_for_file
from src.models.clamp_solver import SOLVER_VERSION, solve
from tests.designs import (
    V1_FILE, blank_design, schottky_gnd, schottky_rail, zener_reference,
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_PY = os.path.join(ROOT, "skill", "server.py")
ZENER = os.path.join(ROOT, "examples", "zener_gnd_bzb984_c3v3.div")
SCHOTTKY = os.path.join(ROOT, "examples", "schottky_rail_bat54cv.div")
EXAMPLES_DIR = os.path.join(ROOT, "examples")
SKILL_EXAMPLES_DIR = os.path.join(ROOT, "skill", "examples")
EXAMPLES = pytest.mark.parametrize("path", [ZENER, SCHOTTKY],
                                   ids=["zener_gnd", "schottky_rail"])
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
STAMP_KEYS = {"solver_version", "commit", "dirty"}


def text_of(path):
    """A file's text, line ends as "\\n" whatever the platform wrote."""
    with open(path, encoding="utf-8") as f:
        return f.read()


def as_text(data):
    return json.dumps(data)


def write(tmp_path, data, name="in.div"):
    path = tmp_path / name
    path.write_text(as_text(data), encoding="utf-8")
    return str(path)


def invalid_design():
    """A missing key and a value out of range."""
    data = zener_reference(resistors__r1__tolerance_pct=150)
    del data["system"]["v_touch"]
    return data


def divcheck_problems(path, capsys):
    """The problems divcheck.py lists for a file, one per line."""
    capsys.readouterr()
    assert divcheck.main([path]) == 1
    header, *lines = capsys.readouterr().out.splitlines()
    assert ": invalid, " in header and all(line.startswith("  ") for line in lines)
    return [line[2:] for line in lines]


def git_head():
    try:
        run = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True)
    except OSError:
        return None
    return run.stdout.strip() if run.returncode == 0 else None


def git_dirty():
    try:
        run = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                             capture_output=True, text=True)
    except OSError:
        return None
    return bool(run.stdout.strip()) if run.returncode == 0 else None


@pytest.fixture
def fresh_commit():
    """The commit and "dirty" are read once and kept: forget them before
    and after."""
    server._commit.cache_clear()
    server._dirty.cache_clear()
    yield
    server._commit.cache_clear()
    server._dirty.cache_clear()


def fake_git(monkeypatch, head="abc123\n", status="", calls=None):
    """Replace git. *head* answers `git rev-parse HEAD` and *status*
    `git status --porcelain`: the output, an exception to raise, or
    (exit code, error text)."""
    def run(command, **kwargs):
        if calls is not None:
            calls.append((command, kwargs))
        answer = {"rev-parse": head, "status": status}[command[1]]
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, tuple):
            return subprocess.CompletedProcess(command, answer[0], "", answer[1])
        return subprocess.CompletedProcess(command, 0, answer, "")
    monkeypatch.setattr(server.subprocess, "run", run)


def png_of(result):
    """The PNG bytes of a plot_div answer (None when it has no image)."""
    images = [c for c in result.content if c.type == "image"]
    assert len(images) <= 1
    if not images:
        return None
    assert images[0].mimeType == "image/png"
    return base64.b64decode(images[0].data)


def info_of(result):
    """The JSON text of a plot_div answer."""
    texts = [c for c in result.content if c.type == "text"]
    assert len(texts) == 1 and result.content[-1] is texts[0]
    info = json.loads(texts[0].text)
    assert info == result.structuredContent
    return info


def png_size(png):
    assert png[:8] == PNG_SIGNATURE and png[12:16] == b"IHDR"
    return int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")


# ── solve_div ────────────────────────────────────────────────────────────────

class TestSolveDiv:
    @EXAMPLES
    def test_results_are_the_stored_results(self, path):
        answer = server.solve_div(text_of(path))
        assert answer["valid"] is True and answer["problems"] == []
        solved = json.loads(answer["div"])
        assert solved["results"] == read_json(path)["results"]
        assert solved["results"] == results_for_file(solve(read_json(path)))
        assert solved["results"]["verdict"] == "FAIL"       # solved whatever the statuses

    @EXAMPLES
    def test_results_are_divchecks_json_output(self, path, tmp_path, capsys):
        out = str(tmp_path / "r.json")
        assert divcheck.main([path, "--json", out]) == 0
        answer = server.solve_div(text_of(path))
        assert json.loads(answer["div"])["results"] == read_json(out)

    @EXAMPLES
    def test_div_is_the_file_divcheck_writes(self, path, tmp_path, capsys):
        """Character for character (line ends apart: the server returns
        "\\n", a file has the platform's)."""
        out = str(tmp_path / "out.div")
        assert divcheck.main([path, out]) == 0
        answer = server.solve_div(text_of(path))
        assert answer["div"] == text_of(out) == text_of(path)
        assert answer["div"].endswith("}\n") and "\r" not in answer["div"]

    @EXAMPLES
    def test_summary_is_what_divcheck_prints(self, path, capsys):
        capsys.readouterr()
        assert divcheck.main([path]) == 0
        printed = capsys.readouterr().out
        answer = server.solve_div(text_of(path), os.path.basename(path))
        assert answer["summary"] + "\n" == printed
        assert "VERDICT: FAIL" in answer["summary"]

    def test_name_is_only_the_label_of_the_summary(self):
        text = as_text(zener_reference())
        plain, named = server.solve_div(text), server.solve_div(text, "in3.div")
        assert plain["summary"].startswith("design.div  (format 2.0, solver ")
        assert named["summary"].startswith("in3.div  (format 2.0, solver ")
        assert plain["summary"].splitlines()[1:] == named["summary"].splitlines()[1:]
        assert plain["div"] == named["div"]

    def test_every_answer_carries_solver_version_commit_and_dirty(self, fresh_commit):
        for text in (as_text(zener_reference()), as_text(invalid_design()), "{not json"):
            answer = server.solve_div(text)
            assert set(answer) == {"valid", "problems", "div", "summary"} | STAMP_KEYS
            assert answer["solver_version"] == SOLVER_VERSION == "2.0.0"
            assert answer["commit"] == git_head()
            assert answer["dirty"] == git_dirty()

    def test_inputs_come_back_as_sent_and_stored_results_are_ignored(self):
        data = dict(schottky_rail(), results={"stale": True, "verdict": "PASS"})
        answer = server.solve_div(as_text(data))
        solved = json.loads(answer["div"])
        assert list(solved)[-1] == "results" and "stale" not in solved["results"]
        assert solved["results"] == results_for_file(solve(schottky_rail()))
        solved.pop("results")
        assert solved == schottky_rail()
        assert '"r1": {"value": 10, "unit": "k\\u03a9", "rating_mw": 200, ' \
               '"tolerance_pct": 1},\n' in answer["div"]     # 10 stays 10

    def test_blank_inputs_are_valid_and_need_input(self):
        answer = server.solve_div(as_text(blank_design()))
        assert answer["valid"] is True and answer["problems"] == []
        assert json.loads(answer["div"])["results"]["verdict"] == "needs input"
        assert "VERDICT: needs input" in answer["summary"]
        assert "Forward table not filled in: needs input" in answer["summary"]

    def test_invalid_file_is_a_normal_answer_with_divchecks_problems(self, tmp_path, capsys):
        data = invalid_design()
        answer = server.solve_div(as_text(data))
        assert answer["valid"] is False
        assert answer["div"] is None and answer["summary"] is None
        assert answer["problems"] == divcheck_problems(write(tmp_path, data), capsys)
        assert answer["problems"] == [
            "resistors.r1.tolerance_pct: must be at least 0 and below 100 %",
            "system.v_touch: missing (use null for a blank value)"]

    @pytest.mark.parametrize("make", [
        lambda: dict(zener_reference(), extra=1),
        lambda: zener_reference(mcu__vdd="3.3", resistors__r1__unit="kOhm"),
        lambda: zener_reference(clamp_diode__anode="node"),
        lambda: copy.deepcopy(V1_FILE),
        lambda: [1, 2],
    ], ids=["unknown key", "wrong types", "wiring", "format 1.0", "not an object"])
    def test_problems_are_divchecks_for_every_kind(self, make, tmp_path, capsys):
        data = make()
        answer = server.solve_div(as_text(data))
        assert answer["valid"] is False and answer["problems"]
        assert answer["problems"] == divcheck_problems(write(tmp_path, data), capsys)

    def test_text_that_is_not_json(self, tmp_path, capsys):
        path = tmp_path / "bad.div"
        path.write_text("{not json", encoding="utf-8")
        answer = server.solve_div("{not json")
        assert answer["valid"] is False and answer["div"] is None
        assert answer["problems"] == divcheck_problems(str(path), capsys)
        assert answer["problems"][0].startswith("file: not valid JSON")

    def test_byte_order_mark_is_dropped_as_divcheck_drops_it(self, tmp_path, capsys):
        text = "\ufeff" + as_text(zener_reference())
        path = tmp_path / "bom.div"
        path.write_text(text, encoding="utf-8")
        assert divcheck.main([str(path)]) == 0
        answer = server.solve_div(text)
        assert answer["valid"] is True
        assert answer["div"] == server.solve_div(as_text(zener_reference()))["div"]

    def test_solve_div_opens_no_file(self, monkeypatch):
        """The .div comes in as text and goes back as text."""
        def no_files(*args, **kwargs):
            raise AssertionError(f"a file was opened: {args}")
        text = text_of(ZENER)
        expected = server.solve_div(text, "x.div")
        monkeypatch.setattr(builtins, "open", no_files)
        monkeypatch.setattr(os, "replace", no_files)
        assert server.solve_div(text, "x.div") == expected
        assert server.solve_div(as_text(invalid_design()))["valid"] is False


# ── The skill's copies of the example files (its self-test) ──────────────────

class TestSkillExamples:
    """skill/examples/ holds copies of the files in examples/. Before
    designing, the skill solves both through solve_div and stops if the
    results differ from the stored ones."""

    NAMES = ["schottky_rail_bat54cv.div", "zener_gnd_bzb984_c3v3.div"]

    @staticmethod
    def content(folder, name):
        """A file's bytes, line ends as "\\n" (git may check out either)."""
        with open(os.path.join(folder, name), "rb") as f:
            return f.read().replace(b"\r\n", b"\n")

    def test_the_copies_are_the_files_in_examples(self):
        originals = sorted(n for n in os.listdir(EXAMPLES_DIR) if n.endswith(".div"))
        assert originals == self.NAMES
        assert sorted(os.listdir(SKILL_EXAMPLES_DIR)) == originals, \
            "skill/examples/ must hold exactly the .div files of examples/"
        for name in originals:
            assert self.content(SKILL_EXAMPLES_DIR, name) == self.content(EXAMPLES_DIR, name), \
                f"skill/examples/{name} differs from examples/{name}: copy it again"

    @pytest.mark.parametrize("name", NAMES)
    def test_self_test_passes_on_the_copies(self, name):
        """What the skill does: solve the copy through solve_div and compare
        with the results stored in it."""
        text = text_of(os.path.join(SKILL_EXAMPLES_DIR, name))
        stored = json.loads(text)["results"]
        answer = server.solve_div(text, name)
        assert answer["valid"] is True
        assert json.loads(answer["div"])["results"] == stored
        assert answer["div"] == text                # nothing at all changes
        assert stored["solver_version"] == answer["solver_version"] == SOLVER_VERSION

    def test_self_test_notices_a_changed_result(self):
        """A stored result that the solver no longer gives does not pass."""
        data = json.loads(text_of(os.path.join(SKILL_EXAMPLES_DIR, self.NAMES[1])))
        stored = copy.deepcopy(data["results"])
        data["resistors"]["r2"]["value"] = 18.2
        answer = server.solve_div(as_text(data))
        assert answer["valid"] is True
        assert json.loads(answer["div"])["results"] != stored


# ── solver_info ──────────────────────────────────────────────────────────────

class TestSolverInfo:
    def test_versions_and_commit(self, fresh_commit):
        info = server.solver_info()
        assert list(info) == ["solver_version", "format_version", "commit", "dirty",
                              "commit_reason", "dirty_reason"]
        assert info["solver_version"] == SOLVER_VERSION == "2.0.0"
        assert info["format_version"] == "2.0"
        assert info["commit"] == git_head()
        if info["commit"] is None:
            assert info["commit_reason"]
        else:
            assert re.fullmatch(r"[0-9a-f]{40}", info["commit"])
            assert info["commit_reason"] is None

    def test_dirty_is_what_git_status_says_of_this_folder(self, fresh_commit):
        info = server.solver_info()
        assert info["dirty"] == git_dirty()
        if info["dirty"] is None:
            assert info["dirty_reason"]
        else:
            assert type(info["dirty"]) is bool and info["dirty_reason"] is None

    @pytest.mark.parametrize("status, dirty", [
        ("", False),
        ("\n", False),
        (" M skill/server.py\n", True),         # changed
        ("M  README.md\n", True),               # staged
        ("?? notes.txt\n", True),               # untracked
        (" M a.py\n?? b.py\n", True),
    ], ids=["clean", "blank line", "changed", "staged", "untracked", "several"])
    def test_dirty_when_git_status_lists_anything(self, status, dirty,
                                                  fresh_commit, monkeypatch):
        fake_git(monkeypatch, status=status)
        info = server.solver_info()
        assert info["dirty"] is dirty and info["dirty_reason"] is None
        assert info["commit"] == "abc123" and info["commit_reason"] is None

    def test_git_is_run_once_in_the_repository_folder_without_the_servers_stdin(
            self, fresh_commit, monkeypatch):
        calls = []
        fake_git(monkeypatch, status=" M x.py\n", calls=calls)
        first = server.solver_info()
        assert (first["commit"], first["dirty"]) == ("abc123", True)
        answer = server.solve_div("{}")
        assert (answer["commit"], answer["dirty"]) == ("abc123", True)
        # read once, then kept: a later change does not alter the answer
        fake_git(monkeypatch, head="def456\n", status="", calls=calls)
        assert server.solver_info() == first
        assert server.solve_div("{}") == answer
        plot = info_of(server.plot_div("{}"))
        assert (plot["commit"], plot["dirty"]) == ("abc123", True)
        assert [command for command, _kwargs in calls] == [
            ["git", "rev-parse", "HEAD"], ["git", "status", "--porcelain"]]
        for _command, kwargs in calls:
            assert os.path.samefile(kwargs["cwd"], ROOT)
            # over stdio the server's stdin is the protocol: git must not get it
            assert kwargs["stdin"] == subprocess.DEVNULL

    def test_no_git_gives_nulls_with_a_reason(self, fresh_commit, monkeypatch):
        missing = FileNotFoundError("git is not installed")
        fake_git(monkeypatch, head=missing, status=missing)
        info = server.solver_info()
        assert info["commit"] is None and info["dirty"] is None
        assert info["commit_reason"] == info["dirty_reason"] == \
            "git could not be run: git is not installed"
        assert info["solver_version"] == SOLVER_VERSION
        # the other tools still answer
        answer = server.solve_div(text_of(ZENER))
        assert answer["valid"] is True
        assert answer["commit"] is None and answer["dirty"] is None
        plot = info_of(server.plot_div(text_of(ZENER)))
        assert plot["image"] is True
        assert plot["commit"] is None and plot["dirty"] is None

    def test_not_a_git_folder_gives_nulls_with_a_reason(self, fresh_commit, monkeypatch):
        not_git = (128, "fatal: not a git repository\n")
        fake_git(monkeypatch, head=not_git, status=not_git)
        info = server.solver_info()
        assert info["commit"] is None and info["dirty"] is None
        assert info["commit_reason"] == \
            "git rev-parse HEAD failed: fatal: not a git repository"
        assert info["dirty_reason"] == \
            "git status --porcelain failed: fatal: not a git repository"

    def test_git_that_hangs_gives_nulls_with_a_reason(self, fresh_commit, monkeypatch):
        hang = subprocess.TimeoutExpired(["git"], server.GIT_TIMEOUT_S)
        fake_git(monkeypatch, head=hang, status=hang)
        info = server.solver_info()
        assert info["commit"] is None and "timed out" in info["commit_reason"]
        assert info["dirty"] is None and "timed out" in info["dirty_reason"]

    def test_dirty_unknown_does_not_hide_the_commit(self, fresh_commit, monkeypatch):
        fake_git(monkeypatch, status=(1, ""))
        info = server.solver_info()
        assert info["commit"] == "abc123" and info["commit_reason"] is None
        assert info["dirty"] is None
        assert info["dirty_reason"] == "git status --porcelain failed: exit code 1"


# ── plot_div ─────────────────────────────────────────────────────────────────

class TestPlotDiv:
    @EXAMPLES
    def test_png_for_the_examples(self, path):
        result = server.plot_div(text_of(path))
        assert result.isError is False
        info = info_of(result)
        assert info == {"valid": True, "problems": [], "image": True, "message": "",
                        "unsettled_points": 0, "solver_version": SOLVER_VERSION,
                        "commit": git_head(), "dirty": git_dirty()}
        png = png_of(result)
        width, height = png_size(png)
        assert width > 600 and height > 300
        from PIL import Image
        with Image.open(io.BytesIO(png)) as image:
            assert image.format == "PNG" and image.size == (width, height)
            image.load()                                    # the whole image decodes
            assert len(image.convert("RGB").getcolors(1 << 24)) > 50    # not a blank page

    @EXAMPLES
    def test_curves_are_the_apps_plot_sweep_at_every_point(self, path, monkeypatch):
        """What is drawn is AppState's plot_data for the same file."""
        drawn = []
        real = server.render_png

        def spy(plot_data, message=""):
            drawn.append((plot_data, message))
            return real(plot_data, message)
        monkeypatch.setattr(server, "render_png", spy)
        result = server.plot_div(text_of(path))

        app = AppState()
        assert app.open_file(path) == []
        (plot_data, message), = drawn
        assert message == app.plot_message == ""
        assert set(plot_data) == set(app.plot_data) >= {
            "v_in", "v_mcu_typ", "v_mcu_low", "v_mcu_worst", "vil", "vih"}
        for key in ("v_in", "v_mcu_typ", "v_mcu_low", "v_mcu_worst"):
            assert len(plot_data[key]) == constants.PLOT_POINTS
            for i in range(constants.PLOT_POINTS):
                assert plot_data[key][i] == app.plot_data[key][i], (key, i)
        assert plot_data == app.plot_data
        assert (plot_data["vil"], plot_data["vih"]) == (
            app.results["voltages"]["vil"], app.results["voltages"]["vih"])
        assert plot_data["v_mcu_typ"][-1] == app.level("max_input")["typ"]
        assert png_of(result) == real(app.plot_data, app.plot_message)

    def test_plot_sweep_is_an_app_state_with_the_design_loaded(self):
        state = server.plot_sweep(schottky_gnd(system__v_input_min=-5.0))
        assert type(state) is AppState
        assert state.design == schottky_gnd(system__v_input_min=-5.0)
        assert state.plot_data["v_in"][0] == -5.0 and state.plot_data["v_in"][-1] == 30.0

    def test_invalid_file_gives_the_problems_and_no_image(self):
        text = as_text(invalid_design())
        result = server.plot_div(text)
        assert result.isError is False and png_of(result) is None
        info = info_of(result)
        assert info["valid"] is False and info["image"] is False
        assert info["problems"] == server.solve_div(text)["problems"] != []
        assert info["message"] is None and info["unsettled_points"] is None
        assert info["solver_version"] == SOLVER_VERSION
        assert info["commit"] == git_head() and info["dirty"] == git_dirty()

    def test_blank_design_is_valid_and_has_no_image(self):
        result = server.plot_div(as_text(blank_design()))
        info = info_of(result)
        assert png_of(result) is None
        assert info["valid"] is True and info["image"] is False
        assert info["message"].startswith("Plot needs input: ")
        assert info["unsettled_points"] == 0

    def test_a_curve_with_blank_inputs_is_left_out_and_named(self):
        text = as_text(zener_reference(resistors__r1__tolerance_pct=None))
        plot = server._plot(text)
        assert plot["message"] == "Worst-case curve needs input: R1 tolerance"
        assert png_size(plot["png"])[0] > 600
        full = server._plot(as_text(zener_reference()))
        assert plot["png"] != full["png"]

    def test_unsettled_plot_points_are_passed_on(self, monkeypatch):
        from src.models import clamp_solver
        real = clamp_solver._solve_node
        monkeypatch.setattr(clamp_solver, "_solve_node",
                            lambda *a, **k: (real(*a, **k)[0], False))
        info = info_of(server.plot_div(as_text(zener_reference())))
        assert info["unsettled_points"] == constants.PLOT_POINTS and info["image"] is True


class TestRenderer:
    def plot_data(self, design=None):
        return server.plot_sweep(design or zener_reference()).plot_data

    def test_png_bytes(self):
        png = plot_png.render_png(self.plot_data())
        assert png_size(png) == (round(plot_png.FIGURE_SIZE_IN[0] * plot_png.DPI),
                                 round(plot_png.FIGURE_SIZE_IN[1] * plot_png.DPI))

    def test_same_lists_give_the_same_picture(self):
        data = self.plot_data()
        assert plot_png.render_png(data) == plot_png.render_png(copy.deepcopy(data))

    def test_each_curve_and_line_is_drawn_only_when_present(self):
        data = self.plot_data()
        full = plot_png.render_png(data)
        for key in ("v_mcu_typ", "v_mcu_low", "v_mcu_worst"):
            less = {k: v for k, v in data.items() if k != key}
            assert plot_png.render_png(less) != full
        for key in ("vil", "vih", "vdd", "v_rec_max", "v_abs_max"):
            assert plot_png.render_png(dict(data, **{key: None})) != full
        assert plot_png.render_png(data, "Typical curve needs input: R1 value") != full

    def test_negative_input_range(self):
        data = self.plot_data(schottky_gnd(system__v_input_min=-5.0))
        assert min(data["v_mcu_low"]) < 0
        assert png_size(plot_png.render_png(data))[0] > 600

    def test_no_curve_is_an_error(self):
        with pytest.raises(ValueError):
            plot_png.render_png({})
        data = {k: v for k, v in self.plot_data().items() if not k.startswith("v_mcu_")}
        with pytest.raises(ValueError):
            plot_png.render_png(data)


# ── A gateway: no math, no customtkinter ─────────────────────────────────────

class TestGateway:
    def test_server_and_renderer_solve_nothing_themselves(self):
        """One solver: the server calls solve() and AppState; it has no sweep
        and no pin-voltage call of its own, and the renderer never sees the
        solver."""
        source = inspect.getsource(server)
        for name in ("pin_voltage", "corners(", "prepare(", "_solve_node", "import math"):
            assert name not in source, name
        assert source.count("solve(data)") == 1
        assert "src.ui" not in source
        renderer = inspect.getsource(plot_png)
        assert "from src" not in renderer and "import src" not in renderer
        assert "clamp_solver" not in renderer and "numpy" not in renderer
        assert "pyplot" not in renderer.replace("no pyplot", "")    # no global backend

    def test_import_chain_has_no_customtkinter(self):
        """Blocks customtkinter and tkinter, then solves and plots: the
        server works without them, and nothing of src/ui is loaded."""
        code = (
            "import sys\n"
            "for name in ('customtkinter', 'tkinter'):\n"
            "    sys.modules[name] = None\n"
            "from skill import server\n"
            f"text = open({ZENER!r}, encoding='utf-8').read()\n"
            "assert server.solve_div(text)['valid'] is True\n"
            "assert server._plot(text)['png'][:4] == b'\\x89PNG'\n"
            "loaded = [m for m in sys.modules if sys.modules[m] is not None and\n"
            "          (m.split('.')[0] in ('customtkinter', 'tkinter', '_tkinter')\n"
            "           or m.startswith('src.ui'))]\n"
            "assert not loaded, loaded\n"
            "print('ok')\n")
        run = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                             capture_output=True, text=True)
        assert run.returncode == 0, run.stderr
        assert run.stdout.strip() == "ok"


# ── The MCP protocol ─────────────────────────────────────────────────────────

def run_async(coroutine):
    return asyncio.run(coroutine)


async def describe(client):
    """What a client sees: the tools, and one answer from each."""
    tools = {t.name: t for t in (await client.list_tools()).tools}
    text = text_of(ZENER)
    info = await client.call_tool("solver_info", {})
    solved = await client.call_tool("solve_div", {"div_json": text, "name": "z.div"})
    plot = await client.call_tool("plot_div", {"div_json": text})
    bad = await client.call_tool("solve_div", {"div_json": as_text(invalid_design())})
    return tools, info, solved, plot, bad


class TestProtocol:
    def test_in_process_round_trip(self):
        async def go():
            async with create_connected_server_and_client_session(
                    server.create_server(), raise_exceptions=True) as client:
                return await describe(client)
        tools, info, solved, plot, bad = run_async(go())

        assert list(tools) == ["solver_info", "solve_div", "plot_div"]
        for tool in tools.values():
            hints = tool.annotations
            assert hints.readOnlyHint is True and hints.destructiveHint is False
            assert hints.idempotentHint is True and hints.openWorldHint is False
            assert "Read-only" in tool.description
        for name in ("solve_div", "plot_div"):
            schema = tools[name].inputSchema
            assert schema["properties"]["div_json"]["type"] == "string"
            assert schema["required"] == ["div_json"]
            assert "not a file path" in tools[name].description
        assert tools["solver_info"].inputSchema["properties"] == {}

        assert info.isError is False
        assert info.structuredContent == server.solver_info()
        assert solved.isError is False
        assert solved.structuredContent == server.solve_div(text_of(ZENER), "z.div")
        assert json.loads(solved.content[0].text) == solved.structuredContent
        assert json.loads(solved.structuredContent["div"])["results"] == \
            read_json(ZENER)["results"]
        assert bad.isError is False                 # an invalid file is a normal answer
        assert bad.structuredContent["valid"] is False
        assert bad.structuredContent["problems"] == \
            server.solve_div(as_text(invalid_design()))["problems"]
        assert plot.isError is False
        assert png_of(plot) == server._plot(text_of(ZENER))["png"]
        assert info_of(plot)["image"] is True

    def test_div_json_must_be_text(self):
        """A .div sent as an object, not as text, is refused by the tool's
        schema (nothing is guessed)."""
        async def go():
            async with create_connected_server_and_client_session(
                    server.create_server()) as client:
                return await client.call_tool("solve_div", {"div_json": zener_reference()})
        assert run_async(go()).isError is True

    def test_runs_over_stdio_as_a_script_from_any_folder(self, tmp_path):
        """The registered form: python <path>/skill/server.py, started from
        another folder."""
        async def go():
            parameters = StdioServerParameters(command=sys.executable,
                                               args=[SERVER_PY], cwd=str(tmp_path))
            with open(os.devnull, "w") as quiet:
                async with stdio_client(parameters, errlog=quiet) as (read, write_):
                    async with ClientSession(read, write_) as client:
                        started = await client.initialize()
                        return started, await describe(client)
        started, (tools, info, solved, plot, _bad) = run_async(go())
        assert started.serverInfo.name == "mcu-input-calculator"
        assert list(tools) == ["solver_info", "solve_div", "plot_div"]
        assert info.structuredContent == server.solver_info()
        assert solved.structuredContent == server.solve_div(text_of(ZENER), "z.div")
        assert png_of(plot)[:8] == PNG_SIGNATURE
        assert list(tmp_path.iterdir()) == []       # the server wrote no file

    def test_runs_over_streamable_http(self, tmp_path):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        process = subprocess.Popen(
            [sys.executable, SERVER_PY, "--http", "--port", str(port)],
            cwd=str(tmp_path), stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 30
            while True:
                assert process.poll() is None, "the server stopped"
                try:
                    socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                    break
                except OSError:
                    assert time.monotonic() < deadline, "the server did not come up"
                    time.sleep(0.1)

            async def go():
                url = f"http://127.0.0.1:{port}/mcp"
                async with streamable_http_client(url) as (read, write_, _session):
                    async with ClientSession(read, write_) as client:
                        await client.initialize()
                        return await describe(client)
            tools, info, solved, plot, _bad = run_async(go())
        finally:
            process.terminate()
            process.wait(timeout=30)
        assert list(tools) == ["solver_info", "solve_div", "plot_div"]
        assert info.structuredContent == server.solver_info()
        assert solved.structuredContent == server.solve_div(text_of(ZENER), "z.div")
        assert png_of(plot)[:8] == PNG_SIGNATURE


class TestCommandLine:
    @pytest.fixture
    def started(self, monkeypatch, fresh_commit):
        """Record how main() starts the server instead of serving."""
        runs = []
        monkeypatch.setattr(
            server.FastMCP, "run",
            lambda self, transport="stdio", mount_path=None: runs.append(
                (transport, self.settings.host, self.settings.port,
                 server._commit.cache_info().currsize
                 + server._dirty.cache_info().currsize)))
        return runs

    def test_stdio_by_default(self, started):
        assert server.main([]) == 0
        (transport, _host, _port, git_read), = started
        assert transport == "stdio"
        assert git_read == 2    # the commit and "dirty" are read before serving starts

    def test_http_option(self, started):
        assert server.main(["--http"]) == 0
        assert started[0][:3] == ("streamable-http", "127.0.0.1", 8000)

    def test_http_host_and_port(self, started):
        assert server.main(["--http", "--host", "0.0.0.0", "--port", "9123"]) == 0
        assert started[0][:3] == ("streamable-http", "0.0.0.0", 9123)

    def test_http_is_stateless_json(self):
        settings = server.create_server("127.0.0.1", 8123).settings
        assert settings.stateless_http is True and settings.json_response is True
        assert (settings.host, settings.port) == ("127.0.0.1", 8123)
        assert settings.streamable_http_path == "/mcp"

    def test_help_as_a_script(self, tmp_path):
        run = subprocess.run([sys.executable, SERVER_PY, "--help"], cwd=str(tmp_path),
                             capture_output=True, text=True)
        assert run.returncode == 0, run.stderr
        for option in ("--http", "--host", "--port", "stdio"):
            assert option in run.stdout

    def test_unknown_option(self):
        run = subprocess.run([sys.executable, SERVER_PY, "--file", "x.div"],
                             capture_output=True, text=True)
        assert run.returncode == 2 and "usage: server.py" in run.stderr
