#!/usr/bin/env python3
"""
MCP server: a gateway from a Claude chat to the solver of this repository.

    python skill/server.py                             stdio
    python skill/server.py --http [--host H] [--port P]   streamable HTTP

Claude writes a .div (format 2.0, docs/div_v2_format.md), sends its text to
a tool and gets back the results and a plot.

The server has no math of its own, chooses no values and reads or writes no
design files. It takes the same path as divcheck.py (parse, validate, solve,
add "results", using the functions of src/core/div_format.py and
src/models/clamp_solver.py, and divcheck's own summary), so it returns what
divcheck.py prints and writes for the same file. The plot is the app's sweep
(AppState, which has no UI imports), drawn by skill/plot_png.py.

Every tool is read-only and takes the .div as JSON text, never a file path,
so the server can run on another machine. Every answer carries
SOLVER_VERSION, the commit the server is running and "dirty" (whether the
server's folder had uncommitted changes when it started).

Must not import customtkinter, directly or through another module.
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import subprocess
import sys
from typing import Any, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:        # run as a script: sys.path starts at skill/
    sys.path.insert(0, REPO)

from mcp.server.fastmcp import FastMCP, Image          # noqa: E402
from mcp.types import CallToolResult, TextContent, ToolAnnotations  # noqa: E402

import divcheck                                         # noqa: E402
from skill.plot_png import render_png                   # noqa: E402
from src.core.app_state import AppState                 # noqa: E402
from src.core.div_format import (                       # noqa: E402
    FORMAT_VERSION, DivError, parse_json, to_text, validate, with_results,
)
from src.models.clamp_solver import SOLVER_VERSION, solve  # noqa: E402

SERVER_NAME = "mcu-input-calculator"
HTTP_HOST = "127.0.0.1"         # --host when it is not given
HTTP_PORT = 8000                # --port when it is not given
SUMMARY_NAME = "design.div"     # first line of the summary when no name is given
GIT_TIMEOUT_S = 10
BYTE_ORDER_MARK = chr(0xFEFF)

INSTRUCTIONS = (
    "Solves a .div design file (format 2.0): one MCU input pin behind a "
    "resistor divider and one clamp diode. Send the whole file as JSON text. "
    "solve_div validates it, solves it and returns it with \"results\" filled "
    "in; plot_div draws pin voltage against input voltage; solver_info gives "
    "the solver version, the format version, the commit and whether the "
    "server's folder had uncommitted changes. The server does "
    "no math of its own, chooses no values and reads or writes no files.")

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                            idempotentHint=True, openWorldHint=False)


# ── The commit the server is running ─────────────────────────────────────────

def _git(*args) -> tuple:
    """(output, reason) of `git <args>` run in the repository folder. When
    git can't answer: (None, why). git never gets the server's stdin, which
    over stdio is the protocol."""
    try:
        run = subprocess.run(["git", *args], cwd=REPO,
                             stdin=subprocess.DEVNULL, capture_output=True,
                             text=True, timeout=GIT_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError) as e:
        return None, f"git could not be run: {e}"
    if run.returncode != 0:
        return None, (f"git {' '.join(args)} failed: "
                      + (run.stderr.strip() or f"exit code {run.returncode}"))
    return run.stdout, None


@functools.lru_cache(maxsize=1)
def _commit() -> tuple:
    """(commit, reason): `git rev-parse HEAD`, read once (main() reads it at
    start, so it is the commit of the code that was loaded). When git can't
    give it: (None, why)."""
    output, reason = _git("rev-parse", "HEAD")
    return (None if output is None else output.strip()), reason


@functools.lru_cache(maxsize=1)
def _dirty() -> tuple:
    """(dirty, reason): True when `git status --porcelain` lists anything (a
    changed, staged or untracked file), so the code that runs is not exactly
    the commit. Read once, at start, like the commit. When git can't say:
    (None, why)."""
    output, reason = _git("status", "--porcelain")
    return (None if output is None else bool(output.strip())), reason


def _stamp() -> dict:
    """What every answer carries: the solver version, the commit and whether
    the folder had uncommitted changes on top of it."""
    return {"solver_version": SOLVER_VERSION, "commit": _commit()[0],
            "dirty": _dirty()[0]}


# ── divcheck's path, on text instead of a file ───────────────────────────────

def _load(div_json: str) -> tuple:
    """(data, problems): parse and validate as divcheck.py does. problems is
    a list of "key.path: message", empty for a valid file; data is None when
    the text is not JSON. A byte order mark is dropped, as it is when
    divcheck.py reads a file."""
    try:
        data = parse_json(div_json.removeprefix(BYTE_ORDER_MARK))
        problems = validate(data)
    except DivError as e:
        data, problems = None, e.problems
    return data, [str(p) for p in problems]


def plot_sweep(data: dict) -> AppState:
    """The app's plot sweep of a valid design: an AppState that has loaded
    it. Its plot_data, plot_message and plot_unsettled_points are what the
    app's plot shows for the same file."""
    state = AppState()
    state.load_data(data)
    return state


# ── Tools ────────────────────────────────────────────────────────────────────

def solver_info() -> dict[str, Any]:
    """Versions of what this server runs. Read-only.

    Returns solver_version (the solver's SOLVER_VERSION), format_version
    (the .div format the server reads, "2.0"), commit (the git commit of
    the repository the server runs from) and dirty (true when that
    repository had changed, staged or untracked files when the server
    started, so the code that runs is not exactly the commit; false when it
    was clean). If git can't give the commit, commit is null and
    commit_reason says why; if it can't say whether the repository is
    clean, dirty is null and dirty_reason says why. Otherwise the two
    reasons are null.
    """
    commit, commit_reason = _commit()
    dirty, dirty_reason = _dirty()
    return {"solver_version": SOLVER_VERSION, "format_version": FORMAT_VERSION,
            "commit": commit, "dirty": dirty,
            "commit_reason": commit_reason, "dirty_reason": dirty_reason}


def solve_div(div_json: str, name: str = SUMMARY_NAME) -> dict[str, Any]:
    """Validate and solve a .div design file (format 2.0). Read-only.

    div_json: the whole .div file as JSON text (not a file path). Every key
    of the format must be present, null for a blank value; "results" may be
    left out and any stored results are ignored.
    name: optional file name, used only as the label on the first line of
    the summary.

    Returns:
    - valid: true when the file has no problems. An invalid file is a normal
      answer, not an error.
    - problems: every problem as "key.path: message" (empty when valid).
    - div: the file's text with "results" filled in by the solver, ready to
      save as it is (null when invalid). The inputs are returned as sent.
    - summary: a plain-text summary: verdict, checks, information rows (with
      the time constant tau and the edge times t_rise and t_fall, ns, when
      they have a value), pin voltages, inputs still needed (null when
      invalid).
    - solver_version, commit, dirty: what solved it. dirty is true when the
      server's folder had uncommitted changes when it started. commit and
      dirty are null when git can't give them; solver_info says why.

    A valid file is solved whatever its statuses: read the verdict and the
    checks in results. Blank inputs give "needs input", not a problem.
    """
    data, problems = _load(div_json)
    out = {"valid": not problems, "problems": problems, "div": None, "summary": None}
    if not problems:
        results = solve(data)
        out["div"] = to_text(with_results(data, results))
        out["summary"] = divcheck.summary(name, data, results)
    return {**out, **_stamp()}


def _plot(div_json: str) -> dict:
    """plot_div's answer as plain data, with the PNG as bytes under "png"
    (None when there is no image)."""
    data, problems = _load(div_json)
    out = {"valid": not problems, "problems": problems, "png": None,
           "message": None, "unsettled_points": None}
    if not problems:
        state = plot_sweep(data)
        out["message"] = state.plot_message
        out["unsettled_points"] = state.plot_unsettled_points
        if state.plot_data:
            out["png"] = render_png(state.plot_data, state.plot_message)
    return {**out, **_stamp()}


def plot_div(div_json: str) -> CallToolResult:
    """Plot pin voltage against input voltage for a .div design file. Read-only.

    div_json: the whole .div file as JSON text (not a file path), as for
    solve_div.

    Returns a PNG image and a JSON text. The image shows three curves over
    the input range (0 V, or a negative lowest input, up to the highest
    input): typical, and the lowest and the highest of the eight corners
    (R1 min/max x R2 min/max x diode column min/max), with the band between
    them shaded; VIL and VIH as thin lines; Abs. Max, Safe Max and VDD as
    dashed lines. It is the same sweep the app plots.

    The JSON text:
    - valid, problems: as for solve_div. An invalid file gives the problems
      and no image.
    - image: true when an image is returned.
    - message: which curve is missing and which inputs it needs ("" when
      all three are drawn; null when invalid). When no curve can be drawn
      there is no image.
    - unsettled_points: plot points where the solver did not settle; the
      curve is not reliable there (0 normally; null when invalid).
    - solver_version, commit, dirty: as for solve_div.
    """
    plot = _plot(div_json)
    png = plot.pop("png")
    info = {**plot, "image": png is not None}
    content = [] if png is None else [Image(data=png, format="png").to_image_content()]
    content.append(TextContent(type="text", text=json.dumps(info, indent=2)))
    return CallToolResult(content=content, structuredContent=info)


TOOLS = (solver_info, solve_div, plot_div)


# ── Server ───────────────────────────────────────────────────────────────────

def create_server(host: str = HTTP_HOST, port: int = HTTP_PORT) -> FastMCP:
    """The MCP server with its three tools. host and port are used by the
    streamable HTTP transport only. The server keeps nothing between calls,
    so HTTP is stateless and answers in plain JSON."""
    server = FastMCP(SERVER_NAME, instructions=INSTRUCTIONS, host=host, port=port,
                     stateless_http=True, json_response=True)
    for tool in TOOLS:
        server.add_tool(tool, annotations=READ_ONLY)
    return server


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="server.py",
        description="MCP server for .div design files (format 2.0): validates, "
                    "solves and plots a design sent as JSON text. stdio unless "
                    "--http is given.")
    parser.add_argument("--http", action="store_true",
                        help="serve streamable HTTP (at /mcp) instead of stdio")
    parser.add_argument("--host", default=HTTP_HOST,
                        help="with --http: address to listen on (default %(default)s)")
    parser.add_argument("--port", type=int, default=HTTP_PORT,
                        help="with --http: port to listen on (default %(default)s)")
    args = parser.parse_args(argv)
    _commit()       # read now: the commit of the code that has just been loaded,
    _dirty()        # and whether the folder had changes on top of it
    create_server(args.host, args.port).run(
        transport="streamable-http" if args.http else "stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
