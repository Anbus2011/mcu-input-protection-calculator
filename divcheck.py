#!/usr/bin/env python3
"""
Command-line checker for .div design files (format 2.0).

    python divcheck.py in.div [out.div] [--json out.json]

Validates the file, solves it with the same solver the app uses, and prints a
short summary. With out.div the file is written back with "results" filled
in (out.div may be in.div). With --json the results alone are written.

Exit code: 0 the file was valid and solved (whatever the statuses);
           1 the file was invalid, with every problem listed;
           2 a file could not be read or written.

Standard library only: no customtkinter, matplotlib or numpy.
"""
from __future__ import annotations

import argparse
import os
import sys

from src.core.div_format import (
    DivError, read_json, results_for_file, validate, with_results, write_json,
)
from src.models.clamp_solver import solve

LEVEL_NAMES = {"min_input": "Min Input", "zero": "0 V", "logic_low": "Logic Low",
               "logic_high": "Logic High", "analog_fullscale": "ADC Scale",
               "max_input": "Max Input", "touch": "Touch"}
# information row -> the solver result it comes from (results["missing"] key)
INFO_SOURCE = {"f_may_work": "f_limits", "f_reliable": "f_limits",
               "rail_current": "power_worst", "touch_pin_high": "touch",
               "touch_diode_current": "touch", "touch_r1_power": "touch"}
# Information rows taken from the solver's details (not stored in a file's
# results): label -> details key. Printed only when they have a value.
EDGE_ROWS = (("tau", "tau_ns"), ("t_rise", "t_rise_ns"), ("t_fall", "t_fall_ns"))


def _number(value, unit) -> str:
    if value is None:
        return "needs input"
    if unit == "Hz":
        for scale, name in ((1e6, "MHz"), (1e3, "kHz")):
            if abs(value) >= scale:
                return f"{value / scale:.3f} {name}"
        return f"{value:.1f} Hz"
    digits = {"V": 3, "mA": 3, "mW": 1, "%": 2}.get(unit, 3)
    return f"{value:.{digits}f} {unit}"


def _resistor(r) -> str:
    if r["value"] is None or r["unit"] is None:
        return "blank"
    unit = {"Ω": "ohm", "kΩ": "kohm", "MΩ": "Mohm"}[r["unit"]]
    return f"{r['value']:g} {unit}"


def summary(name: str, data: dict, results: dict) -> str:
    """Plain-ASCII summary of a solved design."""
    res, diode, mcu = data["resistors"], data["clamp_diode"], data["mcu"]
    rs = res["r_series"]
    no_rs = rs["value"] is None or rs["value"] == 0
    lines = [
        f"{name}  (format {data['version']}, solver {results['solver_version']})",
        f"  R1 {_resistor(res['r1'])}, R2 {_resistor(res['r2'])}, "
        + ("no R_s" if no_rs else f"R_s {_resistor(rs)}"),
        f"  Clamp diode: {diode['part'] or 'no part name'} ({diode['type'] or 'no type'}), "
        f"anode {diode['anode'] or 'blank'}, cathode {diode['cathode'] or 'blank'}",
        f"  MCU: {mcu['part'] or 'no part name'}, pin type {mcu['pin_type'] or 'blank'}, "
        f"VDD {_number(mcu['vdd'], 'V')}",
    ]
    for table, what in (("forward", "forward conduction"), ("reverse", "reverse conduction")):
        if diode[table] is None:        # null: not filled in yet, still needed
            lines.append(f"  {table.capitalize()} table not filled in: needs input")
        elif not diode[table]:          # []: this direction is not modelled
            lines.append(f"  No {table} data: {what} is not modelled")
    unchecked = [label for label, section in (("clamp diode", diode), ("MCU", mcu))
                 if not section["checked"]]
    if unchecked:
        lines.append("  Not yet checked against the data sheet: " + ", ".join(unchecked))

    lines += ["", f"VERDICT: {results['verdict']}", "", "Checks"]
    for c in results["checks"]:
        status = c["status"] or "info"
        limit = "" if c["limit"] is None else f"   limit {_number(c['limit'], c['unit'])}"
        lines.append(f"  {c['id']:<14} {status:<12} {_number(c['value'], c['unit']):>13}{limit}")
    lines += ["", "Information"]
    for row in results["info"]:
        text = _number(row["value"], row["unit"])
        if row["value"] is None and INFO_SOURCE[row["id"]] not in results["missing"]:
            text = "none"                # not waiting for an input: see the note
        lines.append(f"  {row['id']:<20} {text:>13}")
    for label, key in EDGE_ROWS:         # from details, only when they have a value
        value = results["details"][key]
        if value is not None:
            lines.append(f"  {label:<20} {_number(value, 'ns'):>13}")
    lines += [f"  {note}" for note in results["notes"]]

    lines += ["", f"Pin voltage (V)   {'input':>8} {'lowest':>8} {'typical':>8} {'highest':>8}"]
    for key, row in results["voltages"]["levels"].items():
        cells = " ".join(f"{'--' if row[k] is None else format(row[k], '.3f'):>8}"
                         for k in ("v_in", "low", "typ", "high"))
        lines.append(f"  {LEVEL_NAMES[key]:<15} {cells}")
    for key, label in (("vil", "VIL"), ("vih", "VIH")):
        value = results["voltages"][key]
        lines.append(f"  {label:<15} {'--' if value is None else format(value, '.3f'):>8}")

    if results["needs_input"]:
        lines += ["", "Needs input:"] + [f"  {p}" for p in results["needs_input"]]
    if results["warnings"]:
        lines += ["", "Warnings:"] + [f"  {w}" for w in results["warnings"]]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="divcheck.py",
        description="Validate and solve a .div design file (format 2.0).")
    parser.add_argument("infile", help="the .div file to check")
    parser.add_argument("outfile", nargs="?",
                        help="write the file back here with \"results\" filled in")
    parser.add_argument("--json", dest="json_out", metavar="out.json",
                        help="write the results alone to this file")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    name = os.path.basename(args.infile)
    if not os.path.isfile(args.infile):
        print(f"{name}: can't read {args.infile}: no such file", file=sys.stderr)
        return 2
    try:
        data = read_json(args.infile)
        problems = validate(data)
    except DivError as e:
        problems = e.problems
    if problems:
        print(f"{name}: invalid, {len(problems)} problem"
              f"{'' if len(problems) == 1 else 's'}:")
        for p in problems:
            print(f"  {p}")
        return 1

    results = solve(data)
    print(summary(name, data, results))
    try:
        if args.outfile:
            write_json(args.outfile, with_results(data, results))
        if args.json_out:
            write_json(args.json_out, results_for_file(results))
    except OSError as e:
        print(f"\ncan't write: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
