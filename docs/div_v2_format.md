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

    {"i_ma": 1, "v_min": 2.51, "v_typ": 2.69, "v_max": 2.91}

A row says: at this current (mA), the voltage across the diode is between `v_min` and `v_max`, typically `v_typ`.

- Currents and voltages are above 0. Reverse voltages and currents are written as positive numbers.
- Rows are in ascending current, and each voltage column rises from row to row.
- In every row `v_min` ≤ `v_typ` ≤ `v_max`.
- A table has no rows (`[]`) or at least two. `[]` means that direction is not modelled: the solver takes its current as zero, and the app says so.
- A `null` cell is allowed; results that use that column then say "needs input". A table that is `null` is a blank too: not filled in yet, as opposed to `[]`, not modelled. The app shows the two differently, keeps each as it is on save, and starts a new design with both tables `null`.

How the solver reads a table: between two rows, ln(current) is linear in voltage. Below the first row and above the last, the nearest segment is extended. So give rows over the whole range of currents the design can reach, a few per decade where the curve bends.

`v_min` is the part that conducts most (lowest voltage at a given current) and `v_max` the part that conducts least. The solver uses the same column in both tables for one corner. Fold temperature into the two outer columns: the solver has no temperature input.

Leakage curves are nearly flat, so the three columns of a reverse table can be far apart in voltage at the same current (see the BAT54CV example and its `note`). If the leakiest part is already above a row's current at the lowest voltage the data sheet shows, the row can't be written from the data sheet alone; say in `note` what you did.

## `mcu`

| Key | Value |
|---|---|
| `part`, `source`, `checked`, `note` | as for the diode |
| `pin_type` | a label such as `"TT"` or `"FT"` |
| `vdd` | supply voltage, V. Also the ADC reference and the voltage of the `vdd` rail the diode may connect to |
| `v_recommended_max` | "Safe Max": highest pin voltage in normal operation, V. The `pin_max_safe` check against it is the guard against injection into the pin's protection diodes (on an STM32G4 TT pin, VDD + 0.3 V) |
| `v_absolute_max` | absolute maximum pin voltage, V |
| `v_pin_min` | lowest allowed pin voltage, V (0 or negative, for example -0.3) |
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

Written only by the solver (`divcheck.py` or the app's Save; both write the same `results` for the same design). Numbers are rounded to 7 significant digits and always written with a decimal point (`200.0`).

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

### Statuses

| `status` | Meaning |
|---|---|
| `"PASS"` | Inside the limit, with the margin the check asks for. |
| `"TIGHT"` | Not a failure, but not comfortable: inside the limit with less than the required margin. For `frequency` only, it means past `limit` ("reliable up to") and still inside an outer limit ("may work up to"). |
| `"FAIL"` | Past the limit (for `frequency`, past the outer one). |
| `"needs input"` | An input the check uses is blank or unusable; `needs_input` names it. |
| `null` | The check is information only (`analog_error` without an allowed error). |

`limit` in a check is the limit named below. Only `frequency` has a second, outer limit; in every other check a `value` past `limit` is FAIL.

| Check `id` | PASS | TIGHT | FAIL |
|---|---|---|---|
| `pin_max_safe` | at least 50 mV below `limit` | less than 50 mV below `limit`, down to exactly at it | above `limit` |
| `pin_max_abs` | at least 100 mV below `limit` | less than 100 mV below `limit`, down to exactly at it | above `limit` |
| `power_r1`, `power_r2`, `power_diode`, `power_rs` | below 80 % of `limit` (margin above 20 %) | from 80 % of `limit` to just below it | at or above `limit` |
| `frequency` | up to `limit` ("reliable up to") | above it, up to "may work up to" | above "may work up to", or the pin never reads high or low |
| `analog_range` | up to `limit` (VDD) | never | above `limit` |
| `pin_min` | at or above `limit` | never | below `limit` |
| `logic_high` | above `limit` (VIH) | never | at or below `limit` |
| `logic_low` | below `limit` (VIL) | never | at or above `limit` |
| `analog_error` | size of the error up to `limit` | never | above `limit` |

Example: in `examples/schottky_rail_bat54cv.div`, `analog_range` is FAIL with `value` 3.301258 V against `limit` 3.3 V. The 1.3 mV comes from resistor tolerance, not from the diode: at the 5.1 V full-scale input the divider alone, with R1 at −1 % and R2 at +1 %, gives 5.1 × 18.18 / 28.08 = 3.3019 V. That is above VDD, so the ADC reaches full scale just before the input does.

### The checks

| Check `id` | `value` | `limit` | Present |
|---|---|---|---|
| `pin_max_safe` | highest pin voltage at the maximum input | Safe Max | always |
| `pin_max_abs` | the same | absolute maximum | always |
| `pin_min` | lowest pin voltage at the lowest input | `v_pin_min` | lowest input given and negative |
| `logic_high` | lowest pin voltage at the Logic High input | VIH | always |
| `logic_low` | highest pin voltage at the Logic Low input | VIL | always |
| `power_r1`, `power_r2`, `power_diode` | worst-case power at the maximum input | rating | always |
| `power_rs` | worst-case power in R_series, with the pin held at 0 V | rating | R_series above 0 |
| `analog_range` | highest pin voltage at full scale | VDD | full scale given |
| `analog_error` | pin voltage with the diode minus without it, percent | allowed error | full scale given; status only with an allowed error |
| `frequency` | required frequency | "reliable up to" | required frequency given |

Information `id`s: `f_may_work` and `f_reliable` (Hz, always), `rail_current` (mA into VDD at the maximum input, diode connected to `vdd`), `touch_pin_high`, `touch_diode_current`, `touch_r1_power` (touch voltage given).

Level ids: `min_input`, `zero`, `logic_low`, `logic_high`, `analog_fullscale`, `max_input`, `touch`. Optional levels appear only when their input is given.

## How some of the results are calculated

Every pin voltage comes from one node solve: the current through R1 equals the current through R2 plus the diode current, found by bisection to 1 nV. "Lowest" and "highest" always mean the lowest and highest of the eight corners (R1 min/max × R2 min/max × diode column `v_min`/`v_max`). The solver does not choose a corner in advance; the table at the end of this section shows which corner it turned out to be in the two examples.

Resistor limits: R min = R × (1 − tolerance), R max = R × (1 + tolerance). With no series resistor, R_s max = 0.

### `power_rs` (mW)

    P = V_high² / R_s min

- V_high: the highest voltage at the junction of R1 and R2 at `v_input_max` (the `value` of `pin_max_safe`).
- R_s min: the series resistor at its low tolerance, which gives the most power.
- The pin is taken as held at 0 V, so the whole of V_high is across R_s. The drop in V_high that this load would cause is not taken into account, so P is an upper limit.

There is no estimate of the current into the pin: `pin_max_safe` covers that.

### `analog_error` (%)

At `v_analog_fullscale`, with R1 and R2 at their nominal values:

    V_ideal = v_analog_fullscale × R2 / (R1 + R2)        (pin voltage without the diode)
    error   = V_pin − V_ideal                            (V_pin: solved with the diode)
    value   = error / V_ideal × 100

The error is worked out twice, with the `v_min` column and with the `v_max` column, and the one of larger size is kept, with its sign. Negative means the diode pulls the reading down. No resistor tolerance is included: this check isolates what the diode does to the reading. The app also shows the same error in mV and in LSB (error ÷ (VDD / 2^`adc_bits`)).

### `f_may_work` and `f_reliable` (Hz)

    τ          = (R1 max ∥ R2 max + R_s max) × (C_diode + C_pin + C_stray)
    t_rise     = τ × ln( B_high / (B_high − VIH) )
    t_fall     = τ × ln( (A − B_low) / (VIL − B_low) )
    t_edge     = the larger of t_rise and t_fall
    f_may_work = 1 / (2 × (t_edge + t_pulse_min))
    f_reliable = f_may_work / margin_factor

- B_high: the lowest pin voltage at `v_logic_high_min`. The rising edge starts at 0 V and heads for B_high.
- A: the highest pin voltage at `v_input_max`. B_low: the highest pin voltage at `v_logic_low_max`. The falling edge starts at A and heads for B_low.
- VIL = `vil_factor` × VDD, VIH = `vih_factor` × VDD.
- τ always uses R1, R2 and R_s at their high tolerance, whichever corners A, B_high and B_low came from. The mix is deliberately on the slow side.
- If B_high is not above VIH, or B_low is not below VIL, there is no limit: both values are `null` and `notes` says the pin never reads high (or low).

Each edge is treated as a plain RC curve toward its final level. The frequency is at the pin, at 50 % duty.

### Corners in the two examples

| Quantity | Zener to GND | Schottky to rail |
|---|---|---|
| V_high and A (highest at `v_input_max`) | R1 min, R2 max, `v_max` | R1 min, R2 max, `v_max` |
| B_high (lowest at `v_logic_high_min`) | R1 max, R2 min, `v_min` | R1 max, R2 min, `v_max` |
| B_low (highest at `v_logic_low_max`) | R1 min, R2 max, `v_max` | R1 min, R2 max, `v_min` |
| `analog_error` column | `v_min` | `v_min` |

The Schottky column shows why all eight corners are solved: below VDD the rail diode leaks into the pin, so the leakiest column (`v_min`) gives the highest pin voltage there, and the least leaky (`v_max`) the lowest.

## The checker

    python divcheck.py in.div [out.div] [--json out.json]

It validates the file, solves it and prints a summary. With `out.div` it writes the file back with `results` filled in (`out.div` may be the same file as `in.div`). With `--json` it writes `results` alone.

Exit code 0: the file was valid and solved, whatever the statuses. 1: the file was invalid; every problem is listed as `key.path: message`. 2: a file could not be read or written.

The app writes a file back with every input exactly as it was read (`10` stays `10`, `10.0` stays `10.0`, `null` and `[]` stay), unless that input was edited in the app; only `results` is rewritten. An edited number is written as it was typed.

The checker rejects a file for any problem. The app is more lenient with one kind: a value that is readable but unusable (out of range, table rows out of order) still opens, and the app lists it under "Fix:".

It needs only a plain Python install (no numpy, matplotlib or customtkinter).

## Format 1.0 files

Format 1.0 described a Zener by five numbers (`zener` section). This version does not read it and there is no converter: the file is rejected with a message saying so.
