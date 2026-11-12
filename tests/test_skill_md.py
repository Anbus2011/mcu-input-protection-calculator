"""
Tests for the skill: skill/SKILL.md (its versions, the names it uses, no
part named) and the package that skill/build_package.py builds from it.
Run with: python -m pytest tests/ -v
"""
import inspect
import json
import os
import re
import subprocess
import sys
import zipfile

import pytest

from skill import build_package, server
from src.core.div_format import DIODE_TYPES, FILE_RESULT_KEYS, RESULTS_KEY, SCHEMA
from src.models.clamp_solver import ROW_KEYS, SOLVER_VERSION, TERMINALS
from tests.test_solver_rules import PART_SPECIFIC_PATTERNS

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SKILL_DIR = os.path.join(ROOT, "skill")
SKILL_MD = os.path.join(SKILL_DIR, "SKILL.md")
BUILD_PY = os.path.join(SKILL_DIR, "build_package.py")
EXAMPLES_DIR = os.path.join(ROOT, "examples")
SKILL_EXAMPLES_DIR = os.path.join(SKILL_DIR, "examples")
TOOLS = ["solver_info", "solve_div", "plot_div"]
VERSION_FORM = r"\d+\.\d+\.\d+"
JSON_WORDS = {"null", "true", "false"}


def text_of(path):
    """A file's text, line ends as "\\n" whatever the platform wrote."""
    with open(path, encoding="utf-8") as f:
        return f.read()


def bytes_of(path):
    """A file's bytes, line ends as "\\n" (git may check out either)."""
    with open(path, "rb") as f:
        return f.read().replace(b"\r\n", b"\n")


def front_matter(text):
    """The front matter of SKILL.md as {key: value}."""
    block = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    assert block, "SKILL.md must start with front matter between --- lines"
    lines = block.group(1).split("\n")
    assert all(re.fullmatch(r"[a-z-]+: \S.*", line) for line in lines), lines
    return dict(line.split(": ", 1) for line in lines)


# ── The names SKILL.md may use ───────────────────────────────────────────────

def server_names():
    """Every name skill/server.py gives a client: the server's name, its
    tools, their arguments and the fields of their answers."""
    example = text_of(os.path.join(SKILL_EXAMPLES_DIR,
                                   sorted(os.listdir(SKILL_EXAMPLES_DIR))[0]))
    names = {server.SERVER_NAME}
    for tool in server.TOOLS:
        names.add(tool.__name__)
        names.update(inspect.signature(tool).parameters)
    names.update(server.solver_info())
    names.update(server.solve_div(example))
    names.update(server.plot_div(example).structuredContent)
    return names


def div_names():
    """Every key of a .div file (format 2.0) down to the table rows, the
    keys of "results", and the values a terminal or a diode type can have."""
    def keys(node):
        return set(node) | {k for child in node.values() if isinstance(child, dict)
                            for k in keys(child)}
    return (keys(SCHEMA) | set(ROW_KEYS) | {RESULTS_KEY} | set(FILE_RESULT_KEYS)
            | set(TERMINALS) | set(DIODE_TYPES))


def named(text):
    """The names a text gives in `backticks`: the server's name whole,
    otherwise each word of a span (`checked: false` gives checked and
    false)."""
    names = set()
    for span in re.findall(r"`([^`\n]+)`", text):
        if span == server.SERVER_NAME:
            names.add(span)
        else:
            names.update(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", span))
    return names


def not_the_servers(text):
    """The names of a text that are neither a .div key or value nor a name
    of the server."""
    return sorted(named(text) - div_names() - JSON_WORDS - server_names())


# ── SKILL.md ─────────────────────────────────────────────────────────────────

class TestSkillMd:
    def test_front_matter_is_a_name_and_a_one_line_description(self):
        front = front_matter(text_of(SKILL_MD))
        assert list(front) == ["name", "description"]
        assert re.fullmatch(build_package.NAME_FORM, front["name"])
        assert len(front["name"]) <= 64
        assert 0 < len(front["description"]) <= 200
        assert "Use " in front["description"]        # says when to use it
        assert build_package.skill_name(text_of(SKILL_MD)) == front["name"]

    def test_solver_version_is_the_solvers(self):
        """The SOLVER_VERSION the skill was written for is the solver's:
        after a bump, the skill is looked at again and this line changed."""
        stated = re.findall(r"^- Written and tested for SOLVER_VERSION: (.*)$",
                            text_of(SKILL_MD), re.MULTILINE)
        assert stated == [SOLVER_VERSION], \
            "SKILL.md must state clamp_solver.SOLVER_VERSION, once"
        assert server.solver_info()["solver_version"] == stated[0]

    def test_states_its_own_version(self):
        stated = re.findall(r"^- Skill version: (.*)$", text_of(SKILL_MD), re.MULTILINE)
        assert len(stated) == 1 and re.fullmatch(VERSION_FORM, stated[0])

    def test_every_tool_and_field_it_names_exists_in_the_server(self):
        """Every name in backticks is a tool of skill/server.py, an argument
        or an answer field of one, or a key (or a value) of the .div format."""
        text = text_of(SKILL_MD)
        assert not_the_servers(text) == []
        assert [t.__name__ for t in server.TOOLS] == TOOLS
        assert set(TOOLS) <= named(text)             # and it names all three
        # the fields the start of a session and the self-test read
        assert {"solver_version", "commit", "dirty", "valid", "problems", "div",
                "summary", server.SERVER_NAME} <= named(text) & server_names()

    def test_a_name_the_server_does_not_have_is_found(self):
        """The check above is not empty: made-up names are reported."""
        assert not_the_servers("Call `solve_file`; read `is_dirty` and `div`.") == \
            ["is_dirty", "solve_file"]
        assert not_the_servers("`dirty: true`, `checked: false`, `[]`, `v_min`") == []

    def test_start_of_session_rules_are_stated(self):
        text = text_of(SKILL_MD)
        start = text.split("## Start of every session")[1].split("\n## ")[0]
        assert start.index("`solver_info`") < start.index("`solve_div`")
        assert '"server dirty: true"' in start and "`commit`" in start
        assert "`commit_reason`" in start and "`dirty_reason`" in start
        # stops: a version mismatch, a self-test that differs, no examples
        assert start.count("stop") >= 3
        assert "examples/" in start and "with code" in start

    @pytest.mark.parametrize("wording", [
        ["which folder holds the board's data sheets", "once per board",
         "saved with the requirements", "the user's copy in that folder",
         "a file attached to the chat", "isn't there, stop", "download link",
         "document number and revision", "save it in that folder",
         "Never read a data sheet through the web"],
        ["from a project document instead of the data sheet",
         "don't use it on your own", "ask the user", "If they agree",
         "second-hand", "the document, and the data sheet it came from"],
        ["No estimates", "solving trial values through `solve_div`",
         "never from a hand or rough estimate"],
        ["A trial with placeholder values", "labeled as a what-if in the report",
         "names every placeholder", "never written into the .div"],
    ], ids=["data sheets", "values from other documents", "no estimates", "what-ifs"])
    def test_data_sheet_and_sourcing_rules_are_stated(self, wording):
        """The rules from the first live test, each in one bullet of Rules."""
        rules = text_of(SKILL_MD).split("\n## Rules\n")[1].split("\n## ")[0]
        bullets = [b for b in rules.split("\n- ") if wording[0] in b]
        assert len(bullets) == 1, wording[0]
        for phrase in wording:
            assert phrase in bullets[0], phrase

    def test_requirements_ask_for_the_data_sheet_folder_and_the_report_has_what_ifs(self):
        text = text_of(SKILL_MD)
        requirements = text.split("1. **Requirements.**")[1].split("\n2. **MCU.**")[0]
        assert "the folder that holds the board's data sheets" in requirements
        template = text.split("\n## Report template\n")[1]
        assert template.index("\n    What-ifs\n") < template.index("\n    Needs input\n")
        assert "WHAT-IF: " in template and "every placeholder" in template

    @pytest.mark.parametrize("wording", [
        ["**Threshold basis.**", "more than one pair of input thresholds",
         "guarantees by design for that pin", "`vil_factor` and `vih_factor`",
         "`mcu.note` says which pair was used, with its table and footnote",
         "tested in production, characterization, guaranteed by design",
         "solved as a what-if and shown in the report",
         "more than one pair and none is guaranteed by design, stop and ask the user "
         "which pair is the design basis",
         "With only one pair in the data sheet, use it and say so",
         "a threshold as a formula with an offset from VDD",
         "work out the voltage at the file's `vdd`, divide it by `vdd` to get the factor",
         "show that arithmetic in `mcu.note`"],
        ["**Leakage basis.**", "the most-leaky column (`v_min`)",
         "typical curve at the hot check temperature", "this is the design basis",
         "A worst case is a labeled what-if, never the design file",
         "the data sheet's maximum at temperature when it gives one",
         "the 25 C maximum scaled by the typical temperature rise",
         "`clamp_diode.note` says which basis each column uses"],
    ], ids=["thresholds", "leakage"])
    def test_design_basis_rules_are_stated(self, wording):
        basis = text_of(SKILL_MD).split("\n## Design basis\n")[1].split("\n## ")[0]
        bullets = [b for b in basis.split("\n- ") if wording[0] in b]
        assert len(bullets) == 1, wording[0]
        for phrase in wording:
            assert phrase in bullets[0], phrase

    def test_bench_check_measures_the_leakage_hot(self):
        text = text_of(SKILL_MD)
        bench = text.split("7. **Bench check.**")[1].split("\n## ")[0]
        assert "leakage is measured hot" in bench

    def test_encoder_section_is_stated(self):
        section = text_of(SKILL_MD).split(
            "\n## Quadrature encoder inputs\n")[1].split("\n## ")[0]
        for phrase in [
                "arithmetic is the skill's own and is shown in the report",
                "one pulse is one full cycle on one channel",
                "lines per revolution is pulses per revolution", "counts are 4 per pulse",
                "f_gap = 1 / (4 x (|t_rise - t_fall| + t_pulse_min_ns)), "
                "divided by `margin_factor`",
                "the lower of f_reliable and f_gap. Say which one set it",
                "counts per second (4 x frequency)",
                "max RPM = 60 x frequency / lines per revolution",
                "500, 1000, 1024, 2048, 2500, 4096 and 5000 lines per revolution",
                "solve a what-if copy with the input levels narrowed to that source",
                "next to the generic one",
                "not the encoder's own output limit or the cable's",
                "stop and say the server needs updating"]:
            assert phrase in section, phrase

    def test_a_specific_source_sets_three_levels_for_frequency_only(self):
        section = text_of(SKILL_MD).split(
            "\n## Quadrature encoder inputs\n")[1].split("\n## ")[0]
        source = section.split("- **A specific source.**")[1].split("\n- **")[0]
        for phrase in [
                "The copy sets three levels",
                "`v_logic_high_min` = the source's lowest high level (the slowest rise)",
                "`v_logic_low_max` = the source's highest low level "
                "(the slowest fall target)",
                "`v_input_max` = the source's highest high level "
                "(where the falling edge starts)",
                "This copy is for frequency only",
                "its power and highest-input checks describe the narrowed input, "
                "not the design, and are not reported",
                "never written into the .div that is handed over"]:
            assert phrase in source, phrase
        template = text_of(SKILL_MD).split("\n## Report template\n")[1]
        line = [l for l in template.split("\n") if "WHAT-IF source " in l]
        assert len(line) == 1
        for phrase in ["frequency only", "v_logic_high_min <its lowest high>",
                       "v_logic_low_max <its highest low>",
                       "v_input_max <its highest high>",
                       "power and highest-input checks describe the narrowed input "
                       "and are not reported"]:
            assert phrase in line[0], phrase

    def test_the_summary_rows_the_encoder_section_reads_are_the_summarys(self):
        """f_reliable, t_rise and t_fall are rows of the summary solve_div
        returns, under Information, when they have a value."""
        section = text_of(SKILL_MD).split(
            "\n## Quadrature encoder inputs\n")[1].split("\n## ")[0]
        rows = ["f_reliable", "t_rise", "t_fall"]
        assert "the f_reliable, t_rise and t_fall rows under Information" in section
        solved = [server.solve_div(text_of(os.path.join(SKILL_EXAMPLES_DIR, n)))["summary"]
                  for n in sorted(os.listdir(SKILL_EXAMPLES_DIR))]
        with_edges = [s for s in solved if "\n  t_rise " in s]
        assert with_edges, "an example with edge times"
        for summary in with_edges:
            information = summary.split("\nInformation\n")[1].split("\n\n")[0]
            for row in rows:
                assert re.search(rf"^  {row} +\d", information, re.MULTILINE), row

    def test_report_has_a_basis_line_and_the_basis_what_ifs(self):
        template = text_of(SKILL_MD).split("\n## Report template\n")[1]
        assert template.index("\n    Basis: thresholds ") < template.index("\n    Requirements\n")
        assert "; leakage " in template.split("\n    Basis: ")[1].split("\n")[0]
        what_ifs = template.split("\n    What-ifs\n")[1].split("\n    Needs input\n")[0]
        assert "WHAT-IF other threshold pair: " in what_ifs
        assert "WHAT-IF worst-case leakage: " in what_ifs
        assert "WHAT-IF source " in what_ifs
        assert template.index("\n    Encoder ") < template.index("\n    What-ifs\n")

    def test_names_no_part_vendor_or_data_sheet(self):
        """Part-agnostic, as the code is (the same patterns)."""
        found = [f"SKILL.md:{number}: {pattern} in {line.strip()!r}"
                 for number, line in enumerate(text_of(SKILL_MD).split("\n"), 1)
                 for pattern in PART_SPECIFIC_PATTERNS
                 if re.search(pattern, line, re.IGNORECASE)]
        assert not found, "\n".join(found)


# ── The package ──────────────────────────────────────────────────────────────

@pytest.fixture
def package(tmp_path):
    """(the package built into a temporary folder, the skill's name)."""
    path = build_package.build(str(tmp_path))
    return path, build_package.skill_name(text_of(SKILL_MD))


class TestPackage:
    def test_holds_skill_md_and_the_examples_and_nothing_else(self, package, tmp_path):
        path, name = package
        assert path == os.path.join(str(tmp_path), name + ".zip")
        assert os.listdir(str(tmp_path)) == [name + ".zip"]
        examples = sorted(os.listdir(SKILL_EXAMPLES_DIR))
        assert len(examples) == 2
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
            assert archive.namelist() == (
                [f"{name}/SKILL.md"] + [f"{name}/examples/{n}" for n in examples])
            assert archive.read(f"{name}/SKILL.md") == bytes_of(SKILL_MD)
            for n in examples:
                assert archive.read(f"{name}/examples/{n}") == \
                    bytes_of(os.path.join(SKILL_EXAMPLES_DIR, n)) == \
                    bytes_of(os.path.join(EXAMPLES_DIR, n))
            assert not any(n.endswith(".py") for n in archive.namelist())
            assert all(b"\r" not in archive.read(n) for n in archive.namelist())

    def test_self_test_passes_on_the_packaged_examples(self, package):
        """What the installed skill does with its examples/."""
        path, name = package
        with zipfile.ZipFile(path) as archive:
            examples = [n for n in archive.namelist() if n.endswith(".div")]
            assert len(examples) == 2
            for n in examples:
                text = archive.read(n).decode("utf-8")
                answer = server.solve_div(text, os.path.basename(n))
                assert answer["valid"] is True
                assert json.loads(answer["div"])["results"] == json.loads(text)["results"]
                assert answer["div"] == text
                assert answer["solver_version"] == SOLVER_VERSION

    def test_building_again_replaces_the_package(self, package, tmp_path):
        path, _name = package
        with zipfile.ZipFile(path) as archive:
            before = {n: archive.read(n) for n in archive.namelist()}
        assert build_package.build(str(tmp_path)) == path
        with zipfile.ZipFile(path) as archive:
            assert {n: archive.read(n) for n in archive.namelist()} == before

    def test_written_to_dist_which_git_ignores(self):
        assert build_package.DIST_DIR == os.path.join(ROOT, "dist")
        assert "dist/" in text_of(os.path.join(ROOT, ".gitignore")).split("\n")

    def test_command_line_writes_to_dist_and_says_where(self, monkeypatch, tmp_path, capsys):
        out = str(tmp_path / "dist")                 # stands in for dist/
        monkeypatch.setattr(build_package, "DIST_DIR", out)
        assert build_package.main([]) == 0
        name = build_package.skill_name(text_of(SKILL_MD))
        lines = capsys.readouterr().out.splitlines()
        assert lines[0] == f"Wrote {os.path.join(out, name + '.zip')}"
        assert lines[1] == f"  {name}/SKILL.md" and len(lines) == 4
        assert os.path.isfile(os.path.join(out, name + ".zip"))

    def test_runs_as_a_script_from_any_folder(self, tmp_path):
        out = tmp_path / "out"
        run = subprocess.run([sys.executable, BUILD_PY, str(out)], cwd=str(tmp_path),
                             capture_output=True, text=True)
        assert run.returncode == 0, run.stderr
        name = build_package.skill_name(text_of(SKILL_MD))
        assert run.stdout.splitlines()[0] == f"Wrote {out / (name + '.zip')}"
        assert [p.name for p in out.iterdir()] == [name + ".zip"]

    def test_builder_uses_the_standard_library_only(self):
        source = inspect.getsource(build_package)
        imports = re.findall(r"^(?:from|import) (\S+)", source, re.MULTILINE)
        assert sorted(imports) == ["__future__", "argparse", "os", "re", "sys",
                                   "typing", "zipfile"]

    @pytest.mark.parametrize("text, message", [
        ("# no front matter\n", "no front matter"),
        ("---\ndescription: x\n---\n", "no name"),
        ("---\nname: My Skill\n---\n", "must be lower-case"),
    ], ids=["no front matter", "no name", "bad name"])
    def test_a_skill_md_without_a_usable_name_is_refused(self, text, message):
        with pytest.raises(ValueError, match=message):
            build_package.skill_name(text)

    def test_a_failed_build_is_reported_with_exit_code_1(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(build_package, "SKILL_MD", "MISSING.md")
        assert build_package.main([str(tmp_path / "out")]) == 1
        assert "build_package.py: " in capsys.readouterr().err
        assert not (tmp_path / "out").exists()
