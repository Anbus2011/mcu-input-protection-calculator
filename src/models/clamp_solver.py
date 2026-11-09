"""
Solver for an MCU input protected by a resistor divider and one clamp diode.

    V_input ── R1 ──┬── R_series ──> MCU pin
                    │
                    ├── clamp diode ── GND or VDD
                    │
                    └── R2 ── GND

Python standard library only, no UI imports: the app, the command-line checker
(divcheck.py) and the tests all call ``solve(design)``.

``design`` is a dict in the layout of a ``.div`` file, format 2.0 (see
docs/div_v2_format.md). ``solve`` returns a dict of results. Any value may be
None (blank) or unusable (wrong type, out of range): every result that depends
on it is then None, its status is "needs input", and the key paths of the
inputs it is waiting for are listed in ``results["missing"]`` under that
result's name. Nothing is ever substituted for a missing input, and everything
that does not depend on it still computes.

The diode is a two-terminal part described by measured points, not by a diode
type: ``forward`` and ``reverse`` are tables of current against the voltage
across the diode (minimum, typical and maximum). Between rows ln(current) is
linear in voltage; outside the table the first or last segment is extended. An
empty table means that direction is not modelled (no current). ``type`` is a
label for the screen and is never read here.
"""
from __future__ import annotations

import math

SOLVER_VERSION = "2.0.0"

PASS, TIGHT, FAIL, NEEDS_INPUT = "PASS", "TIGHT", "FAIL", "needs input"

RESISTOR_UNITS = {"Ω": 1.0, "kΩ": 1e3, "MΩ": 1e6}
TERMINALS = ("node", "gnd", "vdd")
TABLES = ("forward", "reverse")
COLUMNS = ("min", "typ", "max")
ROW_KEYS = ("i_ma", "v_min", "v_typ", "v_max")

SOLVER_TOLERANCE_V = 1e-6     # bisection stops when the bracket is 1 µV wide
SOLVER_MAX_ITERATIONS = 200   # a guard only: 1 kV / 2^200 is far below 1 µV
_LN_CURRENT_MAX = 690.0       # exp() guard for a steep segment extended far

# Injection starts at VDD + 0.3 V; 100 ohm stands for the internal ESD path.
INJECTION_ONSET_ABOVE_VDD_V = 0.3
ESD_INTERNAL_OHMS = 100.0


# ── Input rules (shared with the file loader and AppState) ───────────────────

_GT0 = (lambda x: x > 0, "must be greater than 0")
_GE0 = (lambda x: x >= 0, "can't be negative")
_LE0 = (lambda x: x <= 0, "can't be above 0")
_TOL = (lambda x: 0 <= x < 100, "must be at least 0 and below 100 %")
_FRACTION = (lambda x: 0 < x < 1, "must be a fraction of VDD between 0 and 1")
_BITS = (lambda x: 1 <= x <= 32, "must be a whole number from 1 to 32")
_GE1 = (lambda x: x >= 1, "must be 1 or more")
_ANY = None

# Every number in a design, in file order: key path -> (test, message).
NUMBER_RULES = {
    "resistors.r1.value": _GT0,
    "resistors.r1.rating_mw": _GT0,
    "resistors.r1.tolerance_pct": _TOL,
    "resistors.r2.value": _GT0,
    "resistors.r2.rating_mw": _GT0,
    "resistors.r2.tolerance_pct": _TOL,
    "resistors.r_series.value": _GE0,
    "resistors.r_series.rating_mw": _GT0,
    "resistors.r_series.tolerance_pct": _TOL,
    "clamp_diode.capacitance_pf": _GE0,
    "clamp_diode.ptot_mw": _GT0,
    "mcu.vdd": _GT0,
    "mcu.v_recommended_max": _GT0,
    "mcu.v_absolute_max": _GT0,
    "mcu.v_pin_min": _LE0,
    "mcu.safe_injection_ma": _GT0,
    "mcu.adc_bits": _BITS,
    "mcu.vil_factor": _FRACTION,
    "mcu.vih_factor": _FRACTION,
    "mcu.c_pin_pf": _GE0,
    "mcu.t_pulse_min_ns": _GE0,
    "system.v_input_max": _GT0,
    "system.v_input_min": _ANY,
    "system.v_analog_fullscale": _GT0,
    "system.analog_error_allowed_pct": _GE0,
    "system.v_logic_high_min": _GE0,
    "system.v_logic_low_max": _GE0,
    "system.v_touch": _GT0,
    "system.f_required_hz": _GT0,
    "bandwidth.c_stray_pf": _GE0,
    "bandwidth.margin_factor": _GE1,
}
WHOLE_NUMBERS = ("mcu.adc_bits",)

# (paths compared, test, message, paths made unusable when the test fails)
CROSS_RULES = (
    (("mcu.vil_factor", "mcu.vih_factor"), lambda lo, hi: lo < hi,
     "VIL factor must be below VIH factor", ("mcu.vil_factor", "mcu.vih_factor")),
    (("system.v_input_min", "system.v_input_max"), lambda lo, hi: lo < hi,
     "the lowest input must be below the maximum input", ("system.v_input_min",)),
)

WIRING_MESSAGE = "one of anode and cathode must be node, the other gnd or vdd"


def number_problem(path: str, raw):
    """Why *raw* can't be used as the number at *path*. None when it can be,
    or when it is blank (None)."""
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return "expected a number"
    if not math.isfinite(raw):
        return "expected a finite number"
    if path in WHOLE_NUMBERS and not float(raw).is_integer():
        return "expected a whole number"
    rule = NUMBER_RULES[path]
    if rule is not None and not rule[0](raw):
        return rule[1]
    return None


def wiring_problems(anode, cathode) -> dict:
    """{"anode": message, "cathode": message} for unusable diode terminals.
    Blank (None) terminals are not problems."""
    out = {}
    for name, value in (("anode", anode), ("cathode", cathode)):
        if value is not None and value not in TERMINALS:
            out[name] = "expected node, gnd or vdd"
    if not out and anode is not None and cathode is not None \
            and (anode == "node") == (cathode == "node"):
        out = {"anode": WIRING_MESSAGE, "cathode": WIRING_MESSAGE}
    return out


def _cell_number(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) \
        and math.isfinite(x) else None


def table_problems(rows) -> list:
    """Problems in one diode table as [(where, message)]. *where* is "" for
    the table itself, "[2]" for a row or "[2].v_min" for a cell (rows count
    from 0). Blank cells (None) are not problems: they are inputs still needed.

    Rules: a list of rows, none (direction not modelled) or at least two;
    every current and voltage above 0; currents ascending; each voltage column
    rising from row to row; v_min <= v_typ <= v_max in every row.
    """
    if not isinstance(rows, list):
        return [("", "expected a list of rows ([] when this direction is not modelled)")]
    out = []
    if len(rows) == 1:
        out.append(("", "needs at least 2 rows, or none (direction not modelled)"))
    previous = {}
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            out.append((f"[{i}]", "expected an object with i_ma, v_min, v_typ, v_max"))
            continue
        cells = {}
        for key in ROW_KEYS:
            raw = row.get(key)
            if raw is None:
                continue
            x = _cell_number(raw)
            if x is None:
                out.append((f"[{i}].{key}", "expected a number"))
            elif x <= 0:
                out.append((f"[{i}].{key}", "must be greater than 0"))
            else:
                cells[key] = x
                if key in previous and x <= previous[key]:
                    out.append((f"[{i}].{key}", "must be greater than in the row above"))
                previous[key] = x
        bad = set()
        for lo, hi in (("v_min", "v_typ"), ("v_typ", "v_max"), ("v_min", "v_max")):
            if lo in cells and hi in cells and cells[lo] > cells[hi]:
                bad.update((lo, hi))
        for key in ROW_KEYS:
            if key in bad:
                out.append((f"[{i}].{key}", "v_min ≤ v_typ ≤ v_max is not met"))
    return out


# ── Logical inputs ───────────────────────────────────────────────────────────

R1, R2, RS = "resistors.r1", "resistors.r2", "resistors.r_series"
T1, T2, RST = (f"resistors.{n}.tolerance_pct" for n in ("r1", "r2", "r_series"))
R1_RATING, R2_RATING, RS_RATING = (
    f"resistors.{n}.rating_mw" for n in ("r1", "r2", "r_series"))
WIRING = "clamp_diode.wiring"
CURVE = {col: f"clamp_diode.curve.{col}" for col in COLUMNS}
C_DIODE, PTOT = "clamp_diode.capacitance_pf", "clamp_diode.ptot_mw"
VDD = "mcu.vdd"
VIN_MAX = "system.v_input_max"


def _lookup(design, path: str):
    node = design
    for part in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _clean(design) -> tuple:
    """(values, causes). values: logical input name -> usable value or None.
    causes: logical input name -> key paths that make it None ([] when usable)."""
    v, cause = {}, {}

    def put(name, value, paths):
        v[name] = value
        cause[name] = [] if value is not None else list(paths)

    raw = {p: _lookup(design, p) for p in NUMBER_RULES}
    num = {p: (x if x is not None and number_problem(p, x) is None else None)
           for p, x in raw.items()}
    for paths, test, _message, blame in CROSS_RULES:
        values = [num[p] for p in paths]
        if None not in values and not test(*values):
            for p in blame:
                num[p] = None

    def resistance(name):
        value, unit = num[f"resistors.{name}.value"], _lookup(design, f"resistors.{name}.unit")
        if value is None:
            return None, [f"resistors.{name}.value"]
        if not isinstance(unit, str) or unit not in RESISTOR_UNITS:
            return None, [f"resistors.{name}.unit"]
        return value * RESISTOR_UNITS[unit], []

    for name in ("r1", "r2", "r_series"):
        if name == "r_series" and (raw["resistors.r_series.value"] is None
                                   or num["resistors.r_series.value"] == 0):
            # R_s blank or 0 means there is no series resistor.
            ohms, paths = 0.0, []
        else:
            ohms, paths = resistance(name)
        put(f"resistors.{name}", ohms, paths)
        for key in ("rating_mw", "tolerance_pct"):
            p = f"resistors.{name}.{key}"
            put(p, num[p], [p])

    anode, cathode = _lookup(design, "clamp_diode.anode"), _lookup(design, "clamp_diode.cathode")
    bad = wiring_problems(anode, cathode)
    paths = [f"clamp_diode.{n}" for n, x in (("anode", anode), ("cathode", cathode))
             if x is None or n in bad]
    put(WIRING, None if paths else (anode, cathode), paths)

    tables = {t: _lookup(design, f"clamp_diode.{t}") for t in TABLES}
    problems = {t: table_problems(tables[t]) for t in TABLES}
    for col in COLUMNS:
        curves, paths = {}, []
        for t in TABLES:
            rows, used = tables[t], ("i_ma", f"v_{col}")
            for where, _message in problems[t]:
                if "." not in where or where.endswith(used):
                    paths.append(f"clamp_diode.{t}{where}")
            if isinstance(rows, list):
                for i, row in enumerate(rows):
                    if isinstance(row, dict):
                        paths.extend(f"clamp_diode.{t}[{i}].{k}" for k in used
                                     if row.get(k) is None)
            if not paths:
                curves[t] = [(row[f"v_{col}"], math.log(row["i_ma"] / 1000.0))
                             for row in rows] or None
        unique = [p for i, p in enumerate(paths) if p not in paths[:i]]
        put(CURVE[col], None if unique else curves, unique)

    for p in NUMBER_RULES:
        if not p.startswith("resistors."):
            put(p, int(num[p]) if p in WHOLE_NUMBERS and num[p] is not None else num[p], [p])
    return v, cause


# ── Diode curve and node equation ────────────────────────────────────────────

def _curve_current(curve, volts: float) -> float:
    """Current (A) through the diode at *volts* > 0 across it. *curve* is
    [(volts, ln amps)] with at least two points, or None (not modelled)."""
    if curve is None or volts <= 0:
        return 0.0
    if volts <= curve[1][0]:
        (v0, l0), (v1, l1) = curve[0], curve[1]
    elif volts >= curve[-2][0]:
        (v0, l0), (v1, l1) = curve[-2], curve[-1]
    else:
        lo, hi = 1, len(curve) - 2
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if curve[mid][0] <= volts:
                lo = mid
            else:
                hi = mid
        (v0, l0), (v1, l1) = curve[lo], curve[hi]
    return math.exp(min(l0 + (l1 - l0) * (volts - v0) / (v1 - v0), _LN_CURRENT_MAX))


def _solve_node(vin: float, r1: float, r2: float, sign: float, v_ref: float,
                curves: dict) -> tuple:
    """(node voltage, settled) where the current through R1 equals the
    current through R2 plus the diode current. The pin draws no current.

    *sign* is +1 with the anode at the node and -1 with the cathode at the
    node; *v_ref* is the voltage of the diode's other terminal (0 or VDD).

    f(V) = (vin - V)/R1 - V/R2 - I_diode_out(V) falls strictly as V rises, is
    not negative at the lowest of vin, 0 and v_ref and not positive at the
    highest, so bisection on that bracket finds the single root. It stops when
    the bracket is 1 µV wide. ``settled`` is False when the bracket has no
    sign change or does not narrow to 1 µV; the returned voltage (the plain
    divider voltage) is then not reliable.
    """
    forward, reverse = curves["forward"], curves["reverse"]

    def f(volts):
        vd = sign * (volts - v_ref)
        if vd > 0:
            i_diode = _curve_current(forward, vd)
        elif vd < 0:
            i_diode = -_curve_current(reverse, -vd)
        else:
            i_diode = 0.0
        return (vin - volts) / r1 - volts / r2 - sign * i_diode

    lo, hi = min(vin, 0.0, v_ref), max(vin, 0.0, v_ref)
    if lo == hi:
        return lo, True
    f_lo, f_hi = f(lo), f(hi)
    if not (f_lo >= 0 >= f_hi):         # also catches NaN
        return vin * r2 / (r1 + r2), False
    if f_lo == 0:
        return lo, True
    if f_hi == 0:
        return hi, True
    settled = False
    for _ in range(SOLVER_MAX_ITERATIONS):
        mid = 0.5 * (lo + hi)
        if f(mid) > 0:
            lo = mid
        else:
            hi = mid
        if hi - lo <= SOLVER_TOLERANCE_V:
            settled = True
            break
    return 0.5 * (lo + hi), settled


def injection_current_ma(v_pin: float, vdd: float, rs_ohms: float) -> float:
    """Estimated injection current (mA): max(0, V - (VDD + 0.3)) / (R_s + 100).
    Callers pass R_s at its low tolerance for the worst case."""
    over = v_pin - (vdd + INJECTION_ONSET_ABOVE_VDD_V)
    return max(0.0, over) / (rs_ohms + ESD_INTERNAL_OHMS) * 1000


class Circuit:
    """A design with its inputs cleaned, ready for node solves."""

    def __init__(self, design):
        self.v, self.cause = _clean(design)
        self.unsettled = []       # where a solve did not settle
        wiring = self.v[WIRING]
        self.rail = wiring is not None and "vdd" in wiring
        self.sign = 1.0 if wiring is not None and wiring[0] == "node" else -1.0

    def inputs(self, case: str) -> tuple:
        """Logical inputs a node solve needs. *case* is a diode column
        ("min", "typ", "max": nominal resistors) or "worst" (all 8 corners)."""
        names = [R1, R2, WIRING]
        if case == "worst":
            names += [T1, T2, CURVE["min"], CURVE["max"]]
        else:
            names.append(CURVE[case])
        if self.rail:
            names.append(VDD)
        return tuple(names)

    def blocked(self, case: str) -> list:
        """Key paths of the inputs a node solve is waiting for ([] if none)."""
        out = []
        for name in self.inputs(case):
            out.extend(p for p in self.cause[name] if p not in out)
        return out

    @property
    def v_ref(self) -> float:
        return self.v[VDD] if self.rail else 0.0

    def node(self, vin, r1, r2, col, where="") -> float:
        volts, settled = _solve_node(vin, r1, r2, self.sign, self.v_ref,
                                     self.v[CURVE[col]])
        if not settled:
            self.unsettled.append(where)
        return volts

    def resistor_band(self) -> tuple:
        r1, r2 = self.v[R1], self.v[R2]
        t1, t2 = self.v[T1] / 100, self.v[T2] / 100
        return r1 * (1 - t1), r1 * (1 + t1), r2 * (1 - t2), r2 * (1 + t2)

    def corners(self, vin, where="") -> list:
        """The 8 corners R1 {min, max} x R2 {min, max} x diode column
        {min, max} at *vin*: [{"name", "r1", "r2", "col", "v"}]."""
        r1_min, r1_max, r2_min, r2_max = self.resistor_band()
        out = []
        for r1_name, ra in (("R1 min", r1_min), ("R1 max", r1_max)):
            for r2_name, rb in (("R2 min", r2_min), ("R2 max", r2_max)):
                for col in ("min", "max"):
                    name = f"{r1_name}, {r2_name}, diode {col}"
                    out.append({"name": name, "r1": ra, "r2": rb, "col": col,
                                "v": self.node(vin, ra, rb, col, f"{where} ({name})")})
        return out

    def point(self, vin, r1, r2, volts) -> dict:
        """Currents (A) and powers (W) at a solved node voltage. i_diode is
        the current leaving the node through the diode (from Kirchhoff)."""
        i_r1, i_r2 = (vin - volts) / r1, volts / r2
        i_diode = i_r1 - i_r2
        return {"i_r1": i_r1, "i_r2": i_r2, "i_diode": i_diode,
                "p_r1": i_r1 ** 2 * r1, "p_r2": i_r2 ** 2 * r2,
                "p_diode": abs((volts - self.v_ref) * i_diode)}

    def pin_voltage(self, v_in: float, case: str = "typ"):
        """Solved pin voltage at *v_in*: "typ" (nominal resistors, typical
        column), or "low" / "high" (lowest / highest of the 8 corners).
        None while an input it needs is missing."""
        if case == "typ":
            if self.blocked("typ"):
                return None
            return self.node(v_in, self.v[R1], self.v[R2], "typ", "sweep")
        if self.blocked("worst"):
            return None
        volts = [c["v"] for c in self.corners(v_in, "sweep")]
        return min(volts) if case == "low" else max(volts)


def prepare(design) -> Circuit:
    """Clean a design once, for many ``pin_voltage`` calls (a plot sweep)."""
    return Circuit(design)


def pin_voltage(design, v_in: float, case: str = "typ"):
    """Solved pin voltage of *design* at *v_in* (see Circuit.pin_voltage)."""
    return Circuit(design).pin_voltage(v_in, case)


# ── Statuses ─────────────────────────────────────────────────────────────────

_RANK = {PASS: 0, TIGHT: 1, NEEDS_INPUT: 2, FAIL: 3}


def worst_status(statuses):
    """FAIL, else "needs input", else TIGHT, else PASS. None for no statuses."""
    statuses = [s for s in statuses if s is not None]
    return max(statuses, key=_RANK.get) if statuses else None


def _margin_status(margin_pct: float) -> str:
    if margin_pct > 20:
        return PASS
    return TIGHT if margin_pct > 0 else FAIL


def _voltage_status(margin_v: float, pass_v: float) -> str:
    if margin_v >= pass_v:
        return PASS
    return TIGHT if margin_v >= 0 else FAIL


def _injection_status(i_inj: float, limit: float) -> str:
    if i_inj <= limit * 0.5:
        return PASS
    return TIGHT if i_inj <= limit else FAIL


# ── Results ──────────────────────────────────────────────────────────────────

LEVELS = (          # id, input path (None = 0 V), optional
    ("min_input", "system.v_input_min", True),
    ("zero", None, False),
    ("logic_low", "system.v_logic_low_max", False),
    ("logic_high", "system.v_logic_high_min", False),
    ("analog_fullscale", "system.v_analog_fullscale", True),
    ("max_input", VIN_MAX, False),
    ("touch", "system.v_touch", True),
)
LEVEL_LABELS = {"min_input": "Min Input", "zero": "0 V", "logic_low": "Logic Low",
                "logic_high": "Logic High", "analog_fullscale": "ADC Scale",
                "max_input": "Max Input", "touch": "Touch"}

DETAIL_KEYS = (
    # divider
    "r_total_ohms", "k_nominal", "k_high", "k_low", "r_source_ohms",
    "resolution_mv_per_lsb",
    # at the maximum input
    "v_pin_typ", "v_pin_diode_max", "v_pin_high", "margin_rec_v", "margin_abs_v",
    "i_injection_ma",
    "i_r1_ma", "i_r2_ma", "i_diode_ma", "p_r1_mw", "p_r2_mw", "p_diode_mw", "p_total_mw",
    "has_rs", "i_rs_ma", "p_rs_mw",
    "p_r1_worst_mw", "p_r2_worst_mw", "p_diode_worst_mw", "p_rs_worst_mw",
    "worst_power_corner",
    "r1_rating_mw", "r2_rating_mw", "diode_rating_mw", "rs_rating_mw",
    "r1_margin_pct", "r2_margin_pct", "diode_margin_pct", "rs_margin_pct",
    "r1_margin_worst_pct", "r2_margin_worst_pct", "diode_margin_worst_pct",
    "rs_margin_worst_pct", "power_verdict",
    "rail_current_ma", "rail_current_worst_ma",
    # analog full scale
    "analog_ideal_v", "analog_error_mv", "analog_error_pct", "analog_error_lsb",
    "analog_error_column",
    # touch voltage
    "touch_pin_high_v", "touch_diode_ma", "touch_r1_mw",
    # frequency
    "c_total_pf", "tau_ns", "t_rise_ns", "t_fall_ns", "t_edge_ns",
    "t_pulse_shortest_ns", "f_may_work_hz", "f_reliable_hz", "frequency_note",
    # diode tables
    "forward_modelled", "reverse_modelled",
)


def solve(design) -> dict:
    """Solve a design. Returns::

        {"solver_version": "2.0.0",
         "verdict":  worst status among the checks that have one,
         "checks":   [{"id", "status", "value", "limit", "unit"}, ...],
         "info":     [{"id", "value", "unit"}, ...]      (no status),
         "voltages": {"vil", "vih", "levels": {id: {"v_in", "typ", "low", "high"}}},
         "needs_input": key paths of the blank or unusable inputs some result needs,
         "warnings": [text, ...],
         "details":  every other number the screens show (DETAIL_KEYS),
         "missing":  {result name: [key paths it is waiting for]}}

    A check status is PASS, TIGHT, FAIL, "needs input", or None for a check
    that is information only.
    """
    c = Circuit(design)
    v, missing = c.v, {}
    d = dict.fromkeys(DETAIL_KEYS)
    d["worst_power_corner"] = {}
    checks, info = [], []

    def need(key, *names, deps=()):
        miss = []
        for dep in deps:
            miss.extend(p for p in missing.get(dep, []) if p not in miss)
        for name in names:
            miss.extend(p for p in c.cause[name] if p not in miss)
        if miss:
            missing[key] = miss
            return False
        return True

    def check(cid, key, status, value, limit, unit):
        """Add a check. *key* names the result its status comes from: while
        that result is missing inputs the status is "needs input"."""
        if key in missing:
            status = NEEDS_INPUT
        checks.append({"id": cid, "status": status, "value": value,
                       "limit": limit, "unit": unit})

    r1, r2, rs, vdd = v[R1], v[R2], v[RS], v[VDD]
    vin_max = v[VIN_MAX]
    v_rec_max, v_abs_max = v["mcu.v_recommended_max"], v["mcu.v_absolute_max"]

    for t in TABLES:
        rows = _lookup(design, f"clamp_diode.{t}")
        d[f"{t}_modelled"] = bool(rows) if isinstance(rows, list) else None

    # ── Divider network ──────────────────────────────────────────────────
    if need("divider", R1, R2):
        d["r_total_ohms"] = r1 + r2
        d["k_nominal"] = r2 / (r1 + r2)
    if need("r_source", R1, R2, RS):
        d["r_source_ohms"] = r1 * r2 / (r1 + r2) + rs
    if need("tolerance", R1, R2, T1, T2):
        r1_min, r1_max, r2_min, r2_max = c.resistor_band()
        d["k_high"] = r2_max / (r1_min + r2_max)
        d["k_low"] = r2_min / (r1_max + r2_min)
    if need("resolution", VDD, "mcu.adc_bits", deps=("divider",)):
        d["resolution_mv_per_lsb"] = vdd / 2 ** v["mcu.adc_bits"] * 1000 / d["k_nominal"]

    # Logic thresholds at the pin
    vil = v["mcu.vil_factor"] * vdd if need("vil", VDD, "mcu.vil_factor") else None
    vih = v["mcu.vih_factor"] * vdd if need("vih", VDD, "mcu.vih_factor") else None

    # ── Pin voltage at every input level ─────────────────────────────────
    # typ: nominal resistors, typical column. low / high: the lowest / highest
    # of the 8 corners (no reasoning about which corner is the worst one).
    levels, corners = {}, {}
    for key, path, optional in LEVELS:
        vin = 0.0 if path is None else v[path]
        if optional and vin is None:
            continue
        names = () if path is None else (path,)
        where = f"{LEVEL_LABELS[key]} {vin:g} V" if vin is not None else ""
        row = {"v_in": vin, "typ": None, "low": None, "high": None}
        if need(f"{key}.typ", *names, *c.inputs("typ")):
            row["typ"] = c.node(vin, r1, r2, "typ", f"{where} (typical)")
        if need(f"{key}.worst", *names, *c.inputs("worst")):
            corners[key] = c.corners(vin, where)
            row["low"] = min(x["v"] for x in corners[key])
            row["high"] = max(x["v"] for x in corners[key])
        levels[key] = row

    # ── Maximum input: typical point ─────────────────────────────────────
    if need("typ_at_max", deps=("max_input.typ",)):
        v_typ = levels["max_input"]["typ"]
        pt = c.point(vin_max, r1, r2, v_typ)
        d["v_pin_typ"] = v_typ
        for name in ("r1", "r2", "diode"):
            d[f"i_{name}_ma"] = pt[f"i_{name}"] * 1000
            d[f"p_{name}_mw"] = pt[f"p_{name}"] * 1000
        d["p_total_mw"] = d["p_r1_mw"] + d["p_r2_mw"] + d["p_diode_mw"]
        if c.rail:
            d["rail_current_ma"] = pt["i_diode"] * 1000
    if need("diode_max_at_max", VIN_MAX, *c.inputs("max")):
        d["v_pin_diode_max"] = c.node(vin_max, r1, r2, "max",
                                      f"Max Input {vin_max:g} V (diode max, nominal R)")
    if need("v_pin_high", deps=("max_input.worst",)):
        d["v_pin_high"] = levels["max_input"]["high"]
    v_high = d["v_pin_high"]

    # ── Check 1: highest input ───────────────────────────────────────────
    if need("margin_rec", "mcu.v_recommended_max", deps=("v_pin_high",)):
        d["margin_rec_v"] = v_rec_max - v_high
    check("pin_max_safe", "margin_rec",
          None if d["margin_rec_v"] is None else _voltage_status(d["margin_rec_v"], 0.05),
          v_high, v_rec_max, "V")
    if need("margin_abs", "mcu.v_absolute_max", deps=("v_pin_high",)):
        d["margin_abs_v"] = v_abs_max - v_high
    check("pin_max_abs", "margin_abs",
          None if d["margin_abs_v"] is None else _voltage_status(d["margin_abs_v"], 0.1),
          v_high, v_abs_max, "V")

    # Series resistor. R_s = 0 means there is none and nothing is asked for.
    has_rs = d["has_rs"] = rs is None or rs > 0
    rs_names = (RS, RST) if has_rs else (RS,)
    rs_min = rs_max = None
    if not has_rs:
        rs_min = rs_max = 0.0
    elif rs is not None and v[RST] is not None:
        rs_min, rs_max = rs * (1 - v[RST] / 100), rs * (1 + v[RST] / 100)

    # Injection estimate: highest pin voltage, R_s at its low tolerance
    if need("injection", VDD, *rs_names, deps=("v_pin_high",)):
        d["i_injection_ma"] = injection_current_ma(v_high, vdd, rs_min)
    inj_limit = v["mcu.safe_injection_ma"]
    need("inj_status", "mcu.safe_injection_ma", deps=("injection",))
    check("injection", "inj_status",
          None if "inj_status" in missing
          else _injection_status(d["i_injection_ma"], inj_limit),
          d["i_injection_ma"], inj_limit, "mA")

    # ── Check 2: lowest input (only when it is negative) ─────────────────
    v_in_min = v["system.v_input_min"]
    if v_in_min is not None and v_in_min < 0:
        low = levels["min_input"]["low"]
        limit = v["mcu.v_pin_min"]
        need("pin_min", "mcu.v_pin_min", deps=("min_input.worst",))
        check("pin_min", "pin_min",
              None if "pin_min" in missing else (FAIL if low < limit else PASS),
              low, limit, "V")

    # ── Check 3: logic levels ────────────────────────────────────────────
    low_at_high = levels["logic_high"]["low"]
    need("logic_high", deps=("vih", "logic_high.worst"))
    check("logic_high", "logic_high",
          None if "logic_high" in missing else (PASS if low_at_high > vih else FAIL),
          low_at_high, vih, "V")
    high_at_low = levels["logic_low"]["high"]
    need("logic_low", deps=("vil", "logic_low.worst"))
    check("logic_low", "logic_low",
          None if "logic_low" in missing else (PASS if high_at_low < vil else FAIL),
          high_at_low, vil, "V")

    # ── Check 4: power at the maximum input ──────────────────────────────
    # Worst case per part: the highest power over the 8 corners and the
    # typical point (it lies inside the same range).
    if need("power_worst", deps=("max_input.worst", "typ_at_max")):
        best = {name: (d[f"p_{name}_mw"] / 1000, "typical") for name in ("r1", "r2", "diode")}
        rail_worst = d["rail_current_ma"]
        for corner in corners["max_input"]:
            pt = c.point(vin_max, corner["r1"], corner["r2"], corner["v"])
            for name in best:
                if pt[f"p_{name}"] > best[name][0]:
                    best[name] = (pt[f"p_{name}"], corner["name"])
            if c.rail:
                rail_worst = max(rail_worst, pt["i_diode"] * 1000)
        for name, (power, corner_name) in best.items():
            d[f"p_{name}_worst_mw"] = power * 1000
            d["worst_power_corner"][name] = corner_name
        d["rail_current_worst_ma"] = rail_worst
    for name in ("r1", "r2", "diode"):
        need(f"p_{name}_worst", deps=("power_worst",))

    if has_rs:
        if need("p_rs", RS, VDD, deps=("typ_at_max",)):
            d["i_rs_ma"] = injection_current_ma(d["v_pin_typ"], vdd, rs)
            d["p_rs_mw"] = (d["i_rs_ma"] / 1000) ** 2 * rs * 1000
        if need("p_rs_worst", RS, RST, VDD, deps=("v_pin_high",)):
            # P(R) = I(R)^2 R with I = dV / (R + 100) peaks at R = 100 ohm, so
            # the maximum over [R_s min, R_s max] is at an end or at 100 ohm.
            candidates = [rs_min, rs_max]
            if rs_min < ESD_INTERNAL_OHMS < rs_max:
                candidates.append(ESD_INTERNAL_OHMS)
            best_r = max(candidates,
                         key=lambda r: injection_current_ma(v_high, vdd, r) ** 2 * r)
            i_ma = injection_current_ma(v_high, vdd, best_r)
            d["p_rs_worst_mw"] = (i_ma / 1000) ** 2 * best_r * 1000
            d["worst_power_corner"]["rs"] = f"highest pin {v_high:.3f} V, R_s {best_r:g} Ω"

    # Margins: (rating - power) / rating. The worst-case margin is the
    # verdict for each part; the typical margin is information.
    parts = [("r1", R1_RATING, "typ_at_max", "p_r1_worst"),
             ("r2", R2_RATING, "typ_at_max", "p_r2_worst"),
             ("diode", PTOT, "typ_at_max", "p_diode_worst")]
    if has_rs:
        parts.append(("rs", RS_RATING, "p_rs", "p_rs_worst"))
    power_statuses = []
    for name, rating_name, typ_dep, worst_dep in parts:
        rating = d[f"{name}_rating_mw"] = v[rating_name]
        if need(f"{name}_margin", rating_name, deps=(typ_dep,)):
            d[f"{name}_margin_pct"] = (rating - d[f"p_{name}_mw"]) / rating * 100
        status = None
        if need(f"{name}_margin_worst", rating_name, deps=(worst_dep,)):
            pct = d[f"{name}_margin_worst_pct"] = \
                (rating - d[f"p_{name}_worst_mw"]) / rating * 100
            status = _margin_status(pct)
        check(f"power_{name}", f"{name}_margin_worst", status,
              d[f"p_{name}_worst_mw"], rating, "mW")
        power_statuses.append(checks[-1]["status"])
    d["power_verdict"] = worst_status(power_statuses)

    # ── Check 5: analog (only when a full-scale input is given) ──────────
    v_fs = v["system.v_analog_fullscale"]
    if v_fs is not None:
        fs_high = levels["analog_fullscale"]["high"]
        # Range: the highest pin voltage at full scale against VDD
        need("analog_range", VDD, "mcu.v_recommended_max",
             deps=("analog_fullscale.worst",))
        status = None
        if "analog_range" not in missing:
            status = PASS if fs_high <= vdd else TIGHT if fs_high <= v_rec_max else FAIL
        check("analog_range", "analog_range", status, fs_high, vdd, "V")

        # Error: pin voltage with the diode minus without it, nominal
        # resistors; the larger error of the two diode columns.
        if need("analog_error", "system.v_analog_fullscale", R1, R2,
                *c.inputs("min"), *c.inputs("max")):
            ideal = v_fs * r2 / (r1 + r2)
            errors = [(c.node(v_fs, r1, r2, col, f"ADC Scale {v_fs:g} V (diode {col}, nominal R)")
                       - ideal, col) for col in ("min", "max")]
            error, column = max(errors, key=lambda e: abs(e[0]))
            d["analog_ideal_v"] = ideal
            d["analog_error_mv"] = error * 1000
            d["analog_error_pct"] = error / ideal * 100
            d["analog_error_column"] = column
        if need("analog_error_lsb", VDD, "mcu.adc_bits", deps=("analog_error",)):
            d["analog_error_lsb"] = d["analog_error_mv"] / 1000 / (vdd / 2 ** v["mcu.adc_bits"])
        allowed = v["system.analog_error_allowed_pct"]
        status = None
        if allowed is not None and "analog_error" not in missing:
            status = PASS if abs(d["analog_error_pct"]) <= allowed else FAIL
        check("analog_error", "analog_error" if allowed is not None else None,
              status, d["analog_error_pct"], allowed, "%")

    # ── Check 6: frequency ───────────────────────────────────────────────
    # tau = (R1 max || R2 max + R_s max) x (C_diode + C_pin + C_stray). An
    # edge from pin level A towards B crosses threshold T after
    # tau x ln((B - A) / (B - T)).
    if need("c_total", C_DIODE, "mcu.c_pin_pf", "bandwidth.c_stray_pf"):
        d["c_total_pf"] = v[C_DIODE] + v["mcu.c_pin_pf"] + v["bandwidth.c_stray_pf"]
    tau = None
    if need("tau", *rs_names, deps=("tolerance", "c_total")):
        tau = (r1_max * r2_max / (r1_max + r2_max) + rs_max) * d["c_total_pf"] * 1e-12
        d["tau_ns"] = tau * 1e9
    note = None
    if need("edges", deps=("tau", "vil", "vih", "logic_high.worst", "logic_low.worst",
                           "max_input.worst")):
        if low_at_high <= vih:
            note = (f"The pin never reads high: its lowest voltage at the Logic High "
                    f"input, {low_at_high:.3f} V, does not get above VIH {vih:.3f} V.")
        elif high_at_low >= vil:
            note = (f"The pin never reads low: its highest voltage at the Logic Low "
                    f"input, {high_at_low:.3f} V, does not get below VIL {vil:.3f} V.")
        else:
            t_rise = tau * math.log(low_at_high / (low_at_high - vih))
            t_fall = tau * math.log((v_high - high_at_low) / (vil - high_at_low)) \
                if v_high > vil else 0.0
            d["t_rise_ns"], d["t_fall_ns"] = t_rise * 1e9, t_fall * 1e9
            d["t_edge_ns"] = max(t_rise, t_fall) * 1e9
    if need("f_limits", "mcu.t_pulse_min_ns", "bandwidth.margin_factor", deps=("edges",)) \
            and note is None:
        shortest_ns = d["t_edge_ns"] + v["mcu.t_pulse_min_ns"]
        if shortest_ns <= 0:
            note = "No frequency limit: the edge time and the minimum pulse width are both 0."
        else:
            d["t_pulse_shortest_ns"] = shortest_ns
            d["f_may_work_hz"] = 1.0 / (2.0 * shortest_ns * 1e-9)
            d["f_reliable_hz"] = d["f_may_work_hz"] / v["bandwidth.margin_factor"]
    d["frequency_note"] = note
    f_required = v["system.f_required_hz"]
    if f_required is not None:
        status = None
        if "f_limits" not in missing:
            if d["f_reliable_hz"] is None:
                status = FAIL
            elif f_required <= d["f_reliable_hz"]:
                status = PASS
            else:
                status = TIGHT if f_required <= d["f_may_work_hz"] else FAIL
        check("frequency", "f_limits", status, f_required, d["f_reliable_hz"], "Hz")

    # ── Information rows (no status, no effect on the verdict) ───────────
    info.append({"id": "f_may_work", "value": d["f_may_work_hz"], "unit": "Hz"})
    info.append({"id": "f_reliable", "value": d["f_reliable_hz"], "unit": "Hz"})
    if c.rail:
        info.append({"id": "rail_current", "value": d["rail_current_worst_ma"], "unit": "mA"})
    v_touch = v["system.v_touch"]
    if v_touch is not None:
        if need("touch", deps=("touch.typ", "touch.worst")):
            points = [c.point(v_touch, r1, r2, levels["touch"]["typ"])]
            points += [c.point(v_touch, x["r1"], x["r2"], x["v"]) for x in corners["touch"]]
            d["touch_pin_high_v"] = levels["touch"]["high"]
            d["touch_diode_ma"] = max(p["i_diode"] for p in points) * 1000
            d["touch_r1_mw"] = max(p["p_r1"] for p in points) * 1000
        info.append({"id": "touch_pin_high", "value": d["touch_pin_high_v"], "unit": "V"})
        info.append({"id": "touch_diode_current", "value": d["touch_diode_ma"], "unit": "mA"})
        info.append({"id": "touch_r1_power", "value": d["touch_r1_mw"], "unit": "mW"})

    warnings = []
    if c.unsettled:
        seen = [w for i, w in enumerate(c.unsettled) if w not in c.unsettled[:i]]
        warnings.append(
            "Clamp diode solver did not settle (bisection could not bracket the "
            "pin voltage) at: " + "; ".join(seen) + ". Those voltages are not reliable.")

    needed = [p for paths in missing.values() for p in paths]
    needs_input = [p for name in c.cause for p in c.cause[name] if p in needed]
    return {
        "solver_version": SOLVER_VERSION,
        "verdict": worst_status(x["status"] for x in checks),
        "checks": checks,
        "info": info,
        "voltages": {"vil": vil, "vih": vih, "levels": levels},
        "needs_input": [p for i, p in enumerate(needs_input) if p not in needs_input[:i]],
        "warnings": warnings,
        "details": d,
        "missing": missing,
    }
