# The `.div` file, format 2.0

A `.div` file describes one MCU input pin behind a resistor divider and one clamp diode. It is a JSON file in UTF-8. Whoever writes it (the app, or a script that read the data sheets) fills in the inputs; the solver fills in `results`.

    V_input ── R1 ──┬── R_series ──> MCU pin
                    ├── clamp diode ── GND or VDD
                    └── R2 ── GND

Two complete files are in `examples/`: a Zener to GND and a Schottky to the VDD rail.

## Rules for the whole file

- Every key listed below must be present. Write `null` for a value you don't have: it is a blank field, and the results that need it say "needs input". Nothing is filled in for you.
- Only `results` may be left out.
- An unknown key is an error, so a misspelt key is caught.
- Numbers are JSON numbers (`3.3`, not `"3.3"`), in the unit the key name ends with.
- Check a file with `python divcheck.py file.div`. It lists every problem with its key path.

## Top level

| Key | Value |
|---|---|
| `version` | `"2.0"` |
| `created` | text (a date), or `null` |
| `notes` | free text about the design |
| `resistors`, `clamp_diode`, `mcu`, `system`, `bandwidth` | the sections below |
| `results` | written by the solver; ignored when a file is opened |

## `resistors`

`r1`, `r2` and `r_series`, each `{"value", "unit", "rating_mw", "tolerance_pct"}`.

- `unit` is `"Ω"`, `"kΩ"` or `"MΩ"`. The Ω is U+03A9; in JSON you can write `"kΩ"`.
- `value` must be above 0 for `r1` and `r2`. For `r_series`, `null` or `0` means there is no series resistor, and its other three values are then not needed.
- `tolerance_pct` is 0 or more and below 100. `rating_mw` is above 0.

## `clamp_diode`

| Key | Value |
|---|---|
| `part` | part name |
| `source` | one line: data sheet, revision, tables or figures used |
| `checked` | `true` or `false`. Write `false`; the user ticks it in the app after comparing the values with the data sheet |
| `note` | free text: how each column of the tables was obtained, including temperature |
| `type` | `"zener"` or `"schottky"`. A label for the screen only; the solver never reads it |
| `anode`, `cathode` | `"node"`, `"gnd"` or `"vdd"`. Exactly one of the two is `"node"` (the junction of R1 and R2) |
| `capacitance_pf` | diode capacitance (use the value at 0 V bias, or the data-sheet maximum) |
| `ptot_mw` | power rating |
| `forward`, `reverse` | the two tables, see below |

The usual wirings:

| Clamp | `anode` | `cathode` |
|---|---|---|
| Zener to GND | `gnd` | `node` |
| Schottky to the VDD rail | `node` | `vdd` |
| Schottky to GND (negative inputs) | `gnd` | `node` |

### The diode tables

`forward` describes the diode with its anode more positive than its cathode; `reverse` describes it the other way round (the working direction of a Zener, the leakage direction of a Schottky). Each is a list of rows:

    {"i_ma": 1, "v_min": 2.49, "v_typ": 2.69, "v_max": 2.89}

A row says: at this current (mA), the voltage across the diode is between `v_min` and `v_max`, typically `v_typ`.

- Currents and voltages are above 0. Reverse voltages and currents are written as positive numbers.
- Rows are in ascending current, and each voltage column rises from row to row.
- In every row `v_min` ≤ `v_typ` ≤ `v_max`.
- A table has no rows (`[]`) or at least two. `[]` means that direction is not modelled: the solver takes its current as zero, and the app says so.
- A `null` cell is allowed; results that use that column then say "needs input". A table that is `null` is a blank too: not filled in yet, as opposed to `[]`, not modelled.

How the solver reads a table: between two rows, ln(current) is linear in voltage. Below the first row and above the last, the nearest segment is extended. So give rows over the whole range of currents the design can reach, a few per decade where the curve bends.

`v_min` is the part that conducts most (lowest voltage at a given current) and `v_max` the part that conducts least. The solver uses the same column in both tables for one corner. Fold temperature into the two outer columns: the solver has no temperature input.

Leakage curves are nearly flat, so the three columns of a reverse table can be far apart in voltage at the same current (see the BAT54CV example and its `note`). If the leakiest part is already above a row's current at the lowest voltage the data sheet shows, the row can't be written from the data sheet alone; say in `note` what you did.

## `mcu`

| Key | Value |
|---|---|
| `part`, `source`, `checked`, `note` | as for the diode |
| `pin_type` | a label such as `"TT"` or `"FT"` |
| `vdd` | supply voltage, V. Also the ADC reference and the voltage of the `vdd` rail the diode may connect to |
| `v_recommended_max` | "Safe Max": highest pin voltage in normal operation, V |
| `v_absolute_max` | absolute maximum pin voltage, V |
| `v_pin_min` | lowest allowed pin voltage, V (0 or negative, for example -0.3) |
| `safe_injection_ma` | injection current limit, mA |
| `adc_bits` | ADC resolution, whole number 1 to 32 |
| `vil_factor`, `vih_factor` | logic thresholds as a fraction of VDD (0.3 and 0.7); VIL below VIH |
| `c_pin_pf` | pin capacitance, pF |
| `t_pulse_min_ns` | shortest pulse the input peripheral accepts, ns |

## `system`

| Key | Value |
|---|---|
| `v_input_max` | highest input voltage, V (above 0) |
| `v_input_min` | optional: lowest input voltage, V. Checked against `v_pin_min` when negative |
| `v_analog_fullscale` | optional: input voltage at ADC full scale, V |
| `analog_error_allowed_pct` | optional: allowed analog error, percent |
| `v_logic_high_min` | lowest input voltage that must read high, V |
| `v_logic_low_max` | highest input voltage that must read low, V |
| `v_touch` | optional: a voltage the input may touch (for example 60 V); gives information rows only |
| `f_required_hz` | optional: required input frequency at the pin, Hz, 50 % duty |

One pair of logic levels per file: with several signal sources, give the lowest high and the highest low. An optional value that is `null` simply leaves its check out.

## `bandwidth`

| Key | Value |
|---|---|
| `c_stray_pf` | board stray capacitance, pF |
| `margin_factor` | "reliable up to" = "may work up to" ÷ this factor; 1 or more (the app starts at 1.5) |

## `results`

Written only by the solver (`divcheck.py` or the app's Save). Numbers are rounded to 7 significant digits.

| Key | Value |
|---|---|
| `solver_version` | version of the solver that wrote the results, for example `"2.0.0"` |
| `verdict` | the worst status among the checks: `"FAIL"`, else `"needs input"`, else `"TIGHT"`, else `"PASS"` |
| `checks` | list of `{"id", "status", "value", "limit", "unit"}` |
| `info` | list of `{"id", "value", "unit"}`: no status, no effect on the verdict |
| `voltages` | `vil`, `vih` and `levels`: for each input level `{"v_in", "typ", "low", "high"}` (pin voltage, V) |
| `needs_input` | key paths of blank or unusable inputs that some result is waiting for |
| `notes` | text: why a result has no value (for example "The pin never reads high") |
| `warnings` | text: solves that did not settle |

`typ` is nominal resistors with the typical column. `low` and `high` are the lowest and highest of the eight corners R1 min/max × R2 min/max × diode column min/max.

A check `status` is `"PASS"`, `"TIGHT"`, `"FAIL"`, `"needs input"`, or `null` for a check that is information only.

| Check `id` | `value` | `limit` | Present |
|---|---|---|---|
| `pin_max_safe` | highest pin voltage at the maximum input | Safe Max | always |
| `pin_max_abs` | the same | absolute maximum | always |
| `injection` | injection current estimate | injection limit | always |
| `pin_min` | lowest pin voltage at the lowest input | `v_pin_min` | lowest input given and negative |
| `logic_high` | lowest pin voltage at the Logic High input | VIH | always |
| `logic_low` | highest pin voltage at the Logic Low input | VIL | always |
| `power_r1`, `power_r2`, `power_diode` | worst-case power at the maximum input | rating | always |
| `power_rs` | the same for R_series | rating | R_series above 0 |
| `analog_range` | highest pin voltage at full scale | VDD | full scale given |
| `analog_error` | pin voltage with the diode minus without it, percent | allowed error | full scale given; status only with an allowed error |
| `frequency` | required frequency | "reliable up to" | required frequency given |

Information `id`s: `f_may_work` and `f_reliable` (Hz, always), `rail_current` (mA into VDD at the maximum input, diode connected to `vdd`), `touch_pin_high`, `touch_diode_current`, `touch_r1_power` (touch voltage given).

Level ids: `min_input`, `zero`, `logic_low`, `logic_high`, `analog_fullscale`, `max_input`, `touch`. Optional levels appear only when their input is given.

## The checker

    python divcheck.py in.div [out.div] [--json out.json]

It validates the file, solves it and prints a summary. With `out.div` it writes the file back with `results` filled in (`out.div` may be the same file as `in.div`). With `--json` it writes `results` alone.

Exit code 0: the file was valid and solved, whatever the statuses. 1: the file was invalid; every problem is listed as `key.path: message`. 2: a file could not be read or written.

The checker rejects a file for any problem. The app is more lenient with one kind: a value that is readable but unusable (out of range, table rows out of order) still opens, and the app lists it under "Fix:".

It needs only a plain Python install (no numpy, matplotlib or customtkinter).

## Format 1.0 files

Format 1.0 described a Zener by five numbers (`zener` section). This version does not read it and there is no converter: the file is rejected with a message saying so.
