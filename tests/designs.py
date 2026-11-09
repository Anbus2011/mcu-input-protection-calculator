"""
Design dicts (.div format 2.0) shared by the tests.

``zener_reference()`` is the verification baseline: 10 kΩ / 18 kΩ at 1 %, no
R_s, 30 V in, BZB984-C3V3 from the node to GND, STM32G484 TT pin at 3.3 V.
``schottky_rail()`` is the same divider with a BAT54CV from the node to VDD.
The example files in examples/ hold the same inputs (checked by a test).
"""
import copy

OHM, KOHM, MOHM = "Ω", "kΩ", "MΩ"

# Nexperia BZB984 series Rev 3, Fig. 7 (typical, Tj = 25 °C), C3V3 row of
# docs/bzb984_fig7_typical.json: current (mA) and working voltage (V).
C3V3_CURRENT_MA = [0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10]
C3V3_TYPICAL_V = [1.14, 1.25, 1.41, 1.53, 1.67, 1.87, 2.03, 2.21, 2.47, 2.69, 2.93,
                  3.28, 3.55]

# Nexperia BAT54CV (27 December 2022). Forward: currents of Table 7.
BAT54_FORWARD_MA = [0.1, 1, 10, 30, 100]
BAT54_FORWARD_MAX_V = [0.24, 0.32, 0.40, 0.50, 0.80]        # Table 7, maximum
BAT54_FORWARD_TYP_V = [0.150, 0.213, 0.300, 0.361, 0.550]   # Fig. 1, curve (3), 25 °C


def table(currents_ma, v_min, v_typ, v_max):
    return [{"i_ma": i, "v_min": round(lo, 3), "v_typ": typ, "v_max": round(hi, 3)}
            for i, lo, typ, hi in zip(currents_ma, v_min, v_typ, v_max)]


def c3v3_reverse():
    """Typical column from Fig. 7; minimum = typical - 0.2 V, maximum =
    typical + 0.2 V (VZ is 3.1 to 3.5 V at 5 mA, Table 8)."""
    return table(C3V3_CURRENT_MA, [x - 0.2 for x in C3V3_TYPICAL_V], C3V3_TYPICAL_V,
                 [x + 0.2 for x in C3V3_TYPICAL_V])


def bat54_forward():
    """Maximum from Table 7, typical from Fig. 1; minimum = typical minus
    (maximum - typical)."""
    lows = [2 * t - m for t, m in zip(BAT54_FORWARD_TYP_V, BAT54_FORWARD_MAX_V)]
    return table(BAT54_FORWARD_MA, lows, BAT54_FORWARD_TYP_V, BAT54_FORWARD_MAX_V)


def bat54_reverse():
    """Leakage at 25 °C. Typical column: the voltage at which Fig. 2 curve (3)
    reaches 0.65 µA and 0.88 µA. Minimum column (leakiest part): the same
    curve with its current multiplied by 1.58, so that it passes through the
    Table 7 maximum, 2 µA at 25 V. Maximum column: current divided by 1.58."""
    return [{"i_ma": 0.00065, "v_min": 1.19, "v_typ": 7.31, "v_max": 18.3},
            {"i_ma": 0.00088, "v_min": 4.65, "v_typ": 14.1, "v_max": 28.6}]


ZENER_NOTE = (
    "reverse: v_typ is Fig. 7 (typical working voltage against current, Tj = 25 C), "
    "read from the graph to about +/-0.02 V. v_min = v_typ - 0.2 V and v_max = "
    "v_typ + 0.2 V: Table 8 gives VZ 3.1 to 3.5 V at 5 mA only, and the same "
    "+/-0.2 V is used at every current. 25 C only, no temperature spread. "
    "Table 8 IR max (5 uA at VR = 1 V) is leakier than v_min here (about "
    "1.5 uA at 1 V) and is not folded in. forward: empty, not modelled (Table 7 "
    "gives one point, VF max 0.9 V at 10 mA). capacitance: Cd max at VR = 0 V, "
    "1 MHz (Table 8). ptot: one diode loaded, Tamb <= 25 C (Table 5).")

SCHOTTKY_NOTE = (
    "forward: v_max is Table 7 (maximum VF, 25 C). v_typ is Fig. 1 curve (3), "
    "typical at 25 C, read from the graph. v_min = v_typ - (v_max - v_typ): the "
    "data sheet gives no minimum. reverse: v_typ is the voltage at which Fig. 2 "
    "curve (3) (typical, 25 C) reaches each current. v_min is the same curve with "
    "its current x 1.58, so that it passes through the Table 7 maximum (2 uA at "
    "25 V); v_max is the curve with its current / 1.58 (no data-sheet value). The "
    "two rows cover VR up to about 5 V on the leakiest column, enough for a 3.3 V "
    "rail; above that the extended segment over-estimates leakage. 25 C only: at "
    "85 C typical leakage is about 30 uA (Fig. 2 curve (2)). capacitance: Cd max "
    "at VR = 1 V, 1 MHz (Table 7). ptot: per device, one diode loaded, standard "
    "footprint (Table 5).")

MCU_NOTE = (
    "TT_xx pin. Safe Max = VDD + 0.3 V (Table 17, VIN). Abs. Max 4.0 V and pin "
    "minimum VSS - 0.3 V (Table 14). Injection limit: 1 mA is the project's "
    "working value, not a data-sheet one (Table 15 gives -5 / 0 mA: positive "
    "injection is not possible on TT and FT pins). VIL 0.3 x VDD, VIH 0.7 x VDD "
    "and CIO 5 pF typ (Table 54). Minimum pulse width: 3 x tTIMxCLK at 170 MHz "
    "(Table 84, tW(TI1,TI2), directional clock x1). ADC: 12 bit.")


def _resistor(value, unit, rating_mw, tolerance_pct):
    return {"value": value, "unit": unit, "rating_mw": rating_mw,
            "tolerance_pct": tolerance_pct}


def _mcu():
    return {
        "part": "STM32G484 (TT_xx pin)",
        "source": "ST DS12983 Rev 5: Tables 14, 15, 17, 54 and 84",
        "checked": False,
        "note": MCU_NOTE,
        "pin_type": "TT",
        "vdd": 3.3,
        "v_recommended_max": 3.6,
        "v_absolute_max": 4.0,
        "v_pin_min": -0.3,
        "safe_injection_ma": 1.0,
        "adc_bits": 12,
        "vil_factor": 0.3,
        "vih_factor": 0.7,
        "c_pin_pf": 5,
        "t_pulse_min_ns": 17.65,
    }


def _system():
    return {
        "v_input_max": 30,
        "v_input_min": None,
        "v_analog_fullscale": 5.1,
        "analog_error_allowed_pct": None,
        "v_logic_high_min": 3.8,
        "v_logic_low_max": 1.0,
        "v_touch": None,
        "f_required_hz": None,
    }


def zener_reference(**overrides):
    design = {
        "version": "2.0",
        "created": "2026-11-09",
        "notes": "Verification baseline: 10k / 18k divider, 30 V in, Zener to GND.",
        "resistors": {
            "r1": _resistor(10, KOHM, 200, 1),
            "r2": _resistor(18, KOHM, 100, 1),
            "r_series": _resistor(0, OHM, None, None),
        },
        "clamp_diode": {
            "part": "BZB984-C3V3",
            "source": "Nexperia BZB984 series Rev 3: Fig. 7, Tables 5, 7 and 8",
            "checked": False,
            "note": ZENER_NOTE,
            "type": "zener",
            "anode": "gnd",
            "cathode": "node",
            "capacitance_pf": 450,
            "ptot_mw": 265,
            "forward": [],
            "reverse": c3v3_reverse(),
        },
        "mcu": _mcu(),
        "system": _system(),
        "bandwidth": {"c_stray_pf": 3, "margin_factor": 1.5},
    }
    return change(design, **overrides)


def schottky_rail(**overrides):
    design = zener_reference()
    design["notes"] = "Same divider as the baseline with a Schottky from the pin to VDD."
    design["clamp_diode"] = {
        "part": "BAT54CV",
        "source": "Nexperia BAT54CV, 27 December 2022: Tables 5 and 7, Figs. 1 and 2",
        "checked": False,
        "note": SCHOTTKY_NOTE,
        "type": "schottky",
        "anode": "node",
        "cathode": "vdd",
        "capacitance_pf": 10,
        "ptot_mw": 350,
        "forward": bat54_forward(),
        "reverse": bat54_reverse(),
    }
    return change(design, **overrides)


def schottky_gnd(**overrides):
    """Schottky from GND to the node (clamps a negative input)."""
    design = schottky_rail()
    design["clamp_diode"].update(anode="gnd", cathode="node")
    return change(design, **overrides)


def change(design, **overrides):
    """A copy of *design* with values replaced. Keys are key paths with "__"
    for the dots: change(d, mcu__vdd=5.0, resistors__r1__value=8.2)."""
    design = copy.deepcopy(design)
    for key, value in overrides.items():
        *path, last = key.split("__")
        node = design
        for part in path:
            node = node[part]
        assert last in node, f"unknown key {key}"
        node[last] = value
    return design


def blank_design():
    """Every value blank (null), as the app saves a new design."""
    def blank(node):
        if isinstance(node, dict):
            return {k: blank(v) for k, v in node.items()}
        if isinstance(node, list):
            return []
        return False if isinstance(node, bool) else None
    design = blank(zener_reference())
    design["version"] = "2.0"
    return design


# A format 1.0 file (the old results.div), which this version does not read.
V1_FILE = {
    "version": "1.0",
    "created": "2026-04-04T14:58:19.601042",
    "notes": "",
    "resistors": {
        "r1": {"value": 8.2, "unit": KOHM, "rating_mw": 200.0, "tolerance_pct": 1.0},
        "r2": {"value": 29.0, "unit": KOHM, "rating_mw": 63.0, "tolerance_pct": 1.0},
        "r_series": {"value": 0.0, "unit": OHM, "rating_mw": None, "tolerance_pct": None},
    },
    "zener": {"preset": "BZB984-C3V3", "vz_nom": 3.3, "vz_min": 3.1, "vz_max": 3.5,
              "tolerance_pct": 5, "izt_ma": 5.0, "zzt_typ": 85.0, "zzt_max": 95.0,
              "zzk_typ": 350.0, "zzk_max": 600.0, "izk_ma": 1.0, "ptot_mw": 265.0},
    "mcu": {"vdd": 3.3, "vdda": 3.3, "vref": 3.3, "v_recommended_max": 3.6,
            "v_absolute_max": 4.0, "safe_injection_ma": 2.0},
    "system": {"v_input_max": 30.0, "v_analog_fullscale": 4.1, "v_logic_high_min": 3.0,
               "v_logic_low_max": 1.0},
}
