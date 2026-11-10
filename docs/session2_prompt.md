# Session prompt: clamp-diode solver, `.div` v2, simpler screens

> **SUPERSEDED in part.** This is the brief the `div-v2` work was done from, kept as a record. The project owner's later decisions (2026-11-09) overrode the lines listed below. **CLAUDE.md is the authority now**; where this file and CLAUDE.md disagree, CLAUDE.md wins.
>
> | Where in this file | What it says | What holds now (CLAUDE.md) |
> |---|---|---|
> | "The checks", item 1: "and the injection estimate. Rows and formula as today (§4D)." | Keep the injection estimate. | There is no injection estimate, no `injection` check and no `safe_injection_ma` key. `pin_max_safe` (Safe Max) is the guard. §4D item 1. |
> | "Out of scope": "(the injection estimate stays as it is)" | The same. | The same: the estimate is removed. |
> | "The checks", item 4: "Power. As §4B today, for R1, R2, the diode and R_s" | R_s power from the injection current, with the 100 Ω internal path. | R_s power takes the pin as held at 0 V: typical V_typ² / R_s, worst case V_node,max² / R_s,min. No 100 Ω anywhere. §4D item 4. R1, R2 and the diode are as written here. |
> | "The solver": "Solve by bisection to 1 µV" | 1 µV. | 1 nV (`SOLVER_TOLERANCE_V = 1e-9`). §4B. |
> | "Reference numbers": the C3V3 minimum and maximum columns, and the table | Originally typical − 0.2 V and typical + 0.2 V, giving lowest / highest 2.820 / 3.219, 1.789 / 2.054, 1.990 / 2.318 and 2.906 / 3.307 V, "within 0.01 V". | Typical − 0.18 V and typical + 0.22 V in every row (the Table 8 offsets at 5 mA). That paragraph and its table were edited in place to the new values on 2026-11-09. CLAUDE.md §5, Verification Baseline. |
>
> Added by a later decision and not in this file: the `analog_range` check (highest pin voltage at ADC Scale against VDD: PASS up to VDD, FAIL above). CLAUDE.md §4D item 5.

## What this session is for

The app's job is changing. A Claude skill (built later, not in this session) will read the MCU and diode datasheets, ask the user for the input requirements, and write a `.div` file. The app then opens that file so the user can review the result and adjust values. The skill, the app and a command-line checker must all get their numbers from the same solver.

This session does five things, in this order:

1. Replace the Zener-only model with a solver for one clamp diode of either kind: a Zener or a Schottky, connected to GND or to the VDD rail.
2. Put all part data in the `.div` file (format 2.0) and add a command-line checker.
3. Switch the app to the new solver and file format. Remove the diode drop-down and all presets.
4. Simplify the Signal Bandwidth tab to two numbers.
5. Update CLAUDE.md and the README to match.

The project owner approved these changes on 2026-11-09. They replace CLAUDE.md §4B and change parts of §4A, §4C, §4D and §5. Where this prompt and CLAUDE.md disagree, this prompt wins. Everything else in CLAUDE.md still applies: the Model / AppState / View split, the "no hidden defaults" rule, and running the tests after every change.

## Why the Zener model is replaced

The current model (`_zener_curve` and `solve_node_voltage` in `src/models/circuit_model.py`) assumes the Zener does not conduct below a knee at 0.94 × VZ. Real low-voltage Zeners conduct well below that. The BZB984 data sheet (Rev 3, Fig. 7) gives, for the C3V3 at 25 °C, typically 2.69 V at 1 mA and 2.03 V at 100 µA, where the model says 3.10 V.

The effect on the shipped `results.div` design (R1 8.2 kΩ, R2 29 kΩ, C3V3, VDD 3.3 V): at the 3.0 V Logic High input the app reports 2.328 V at the pin and PASS. With the data sheet curve the pin is at 1.93 V, below VIH (2.31 V), so the input never reads high. The protection side of the old model is safe (it reads about 0.2 V high); the logic-level and analog side is wrong.

A Schottky cannot be described by the five Zener fields at all. So the diode is now described by measured points from its data sheet, and the solver does not care which kind of diode it is.

## Decisions already made

Do not reopen these. If one turns out not to work, stop and ask instead of choosing a different design.

### The solver

- A new module in `src/models/`, Python standard library only (no numpy), no UI imports. It must run under a plain Python install, because the skill will call it.
- One entry point takes the design as a dict and returns the results as a dict. `AppState`, the command-line checker and the tests all call this one function. A value that is `None` gives "needs input" for every result that depends on it, and everything else still computes (the existing rule).
- The diode is a two-terminal part. `anode` and `cathode` are each `node`, `gnd` or `vdd`. Three wirings must work:
  - Zener: cathode at the node, anode at GND.
  - Schottky to the rail: anode at the node, cathode at VDD.
  - Schottky to GND: anode at GND, cathode at the node.
  `type` (`zener` or `schottky`) is a label for the screen. The math must not branch on it.
- The diode has two tables, `forward` and `reverse`. Each row is a current and the voltage across the diode at that current: minimum, typical and maximum. Rows are in ascending current and each voltage column must rise from row to row. Between rows, ln(current) is linear in voltage. Outside the table, extend the first or last segment. An empty table means that direction is not modelled, and the Clamp Diode panel says so (for example "no reverse data: leakage not included").
- Node equation: the current through R1 equals the current through R2 plus the diode current. The pin draws no current in this solve (as today). The VDD rail is treated as fixed at the MCU's VDD value. Solve by bisection to 1 µV on a bracket that covers every wiring (for example from min(V_in, 0) to max(V_in, VDD)). Keep the "did not settle" result and warning.
- Typical result: nominal R1 and R2, typical voltage column.
- Worst-case results: solve all eight corners, R1 {min, max} × R2 {min, max} × diode column {minimum, maximum}, and take the highest or the lowest as the check requires. Do not reason about which corner is worst; with leakage from a rail diode the answer is not always the obvious one. This changes §4A: the lowest pin voltage no longer uses the typical Zener.
- Removed: the three-region model, the 0.94 and 0.97 knee factors, the 0.5 mA rule and its step, ZZK, and the low-voltage Zener corner derived from VZ min.
- The solved pin voltage must never fall as the input voltage rises. Add a test for this for each wiring.

### The checks

Statuses are PASS, TIGHT, FAIL and "needs input". Keep the existing thresholds unless stated here.

1. **Highest input.** Highest pin voltage at the maximum input against Safe Max and Absolute Max, and the injection estimate. Rows and formula as today (§4D).
2. **Lowest input.** Only when a lowest input voltage is given and is negative. Lowest pin voltage against the MCU's pin minimum voltage (a new MCU field). FAIL below the limit, otherwise PASS.
3. **Logic levels.** At the Logic High input level the lowest pin voltage must be above VIH. At the Logic Low input level the highest pin voltage must be below VIL. One pair of levels per file: the skill reduces several signal sources to the lowest high and the highest low.
4. **Power.** As §4B today, for R1, R2, the diode and R_s, with the diode's minimum and maximum columns in place of the low and high Zener curves.
5. **Analog error.** Only when an analog full-scale input is given. The error is the pin voltage with the diode minus the pin voltage without it, at the full-scale input with nominal resistors; take the larger error of the two diode columns. Show it in mV, percent and LSB. It gets a status only when an allowed error (percent) is given; otherwise it is information.
6. **Frequency.** See the next section.

Information rows, with no status and no effect on the overall verdict:

- Touch voltage (for example 60 V), when given: highest pin voltage, diode current and R1 power at that input.
- Current into the VDD rail at the maximum input, when the diode is connected to VDD.

The overall verdict is the worst status among the checks that have one.

Remove `ADC_SAMPLE_THRESHOLDS` and the "Min Sample Cycles" row. The table does not match DS12983 Rev 5, Table 67 (for 6.4 kΩ the table gives 12.5 cycles, the data sheet needs 247.5). Keep the Source Impedance row.

### Frequency (Signal Bandwidth tab)

The question the tab answers: what input frequency can a pin with this divider and diode handle, for uses such as pulse input and encoders? It is the frequency at the pin (per channel for an encoder), at 50 % duty.

- Time constant: τ = (R1 max ∥ R2 max + R_s max) × (C_diode + C_pin + C_stray).
- An edge that starts at pin level A and heads for pin level B crosses threshold T after t = τ × ln((B − A) / (B − T)).
  - Rising edge: A = 0 V, B = lowest pin voltage at the Logic High level, T = VIH.
  - Falling edge: A = highest pin voltage at the maximum input, B = highest pin voltage at the Logic Low level, T = VIL.
  - If B does not get past T, the tab says the pin never reads high (or low) and shows no limits, as today.
- t_edge is the larger of the two edge times.
- **May work up to** = 1 / (2 × (t_edge + minimum pulse width)).
- **Reliable up to** = "may work up to" divided by the margin factor.
- **Required** (optional): PASS at or below "reliable", TIGHT between the two, FAIL above "may work".
- A Details control shows τ, total capacitance, the two edge times and the shortest usable pulse (t_edge + minimum pulse width).

Treating the edge as a plain RC curve toward the solved level errs on the safe side: the diode conducts less below the final level than at it, so the real edge is somewhat faster.

Fields:

- C_diode comes from the clamp diode data. C_pin and the minimum pulse width come from the MCU data. C_stray stays a board value.
- The margin factor is a visible field. Its starting value in `constants.py` is 1.5, with the source note "owner's example, 2026-11-09: 1 MHz reliable, 1.5 MHz may work".
- Remove N_samples, the peripheral clock, counter bits, signed and f_read, and with them the counter-overflow limit, the −3 dB bandwidth, the 10–90 % rise time, the two analog limits and the bottleneck name.

### The `.div` file, format 2.0

- Keep the v1 section and key names where a field already exists (`resistors`, `mcu`, `system`, and their keys). `clamp_diode` replaces `zener`.
- `mcu` and `clamp_diode` each carry `part`, `source` (one line: data sheet, revision, tables or figures), `checked` (true or false; the user ticks it in the app) and `note` (free text; the skill records there how the minimum and maximum columns were obtained, including temperature).
- `clamp_diode` also carries `type`, `anode`, `cathode`, `capacitance_pf`, the power rating, and the `forward` and `reverse` tables.
- New MCU values: pin type (a label such as TT or FT), pin minimum voltage, C_pin, minimum pulse width.
- New system values, all optional: lowest input voltage, touch voltage, required frequency, allowed analog error.
- `results` is written only by the solver: a solver version constant (not a git hash), the list of checks (id, status, value, limit, unit) and the key voltages. The app ignores stored results when it opens a file and solves again.
- The loader reports every problem in a file, each with its key path, not only the first.
- There is no v1 converter. A v1 file gets a clear message that this version reads format 2.0. Replace `results.div` with v2 example files: at least the Zener-to-GND reference design and one Schottky-to-rail design. Example files are test fixtures: set `checked` to false and say in `note` where each column came from.
- Write the format down in `docs/div_v2_format.md`, short enough to read in a few minutes. The skill will be written from it.

### The command-line checker

`python divcheck.py in.div [out.div] [--json out.json]`

It validates the file, solves it, and prints a short summary. With `out.div` it writes the file back with `results` filled in. With `--json` it writes the results alone. Exit code 0 means the file was valid and solved, whatever the statuses; 1 means the file was invalid, with every problem listed. It must not import customtkinter, matplotlib or numpy.

### The app

- The "Zener Diode" panel becomes "Clamp Diode": part name, type, connection, the two tables (cells editable), capacitance, power rating, source, note and the "checked" box. No drop-down. Remove `ZENER_PRESETS`, `select_zener_preset`, `zener_preset_display` and the preset tracking. Every diode and MCU value comes from the `.div` file or from the user typing it.
- The MCU and System panels gain the new fields listed above. The other input panels stay as they are.
- Rename "Zener" to "Clamp diode" in every label, result row and message.
- The Component Analysis tab stays as it is, apart from the renaming.
- The plot belongs to the app, not the solver. The solver returns no plot data. `AppState` sweeps the solver's pin-voltage function over the input range and hands plain lists to `plot_canvas.py`, so the curve and the tables cannot disagree.

### Tests

CLAUDE.md says not to delete tests. The approved exception: tests of removed features (presets, the three-region model, knee factors, the 0.5 mA rule, ZZK, the low-voltage corner, counter overflow, the old frequency limits, ADC sample cycles, reading `results.div` as v1) are deleted or rewritten for what replaces them. Every other test stays and passes. In your final message give the number of tests removed, rewritten and added, and put the new total in CLAUDE.md §5.

The UI tests need a desktop session.

## Reference numbers

`docs/bzb984_fig7_typical.json` holds the typical curve for each BZB984 type, read from Fig. 7 of the data sheet (accurate to about ±0.02 V). For the C3V3, use that row as the typical column, typical − 0.18 V as the minimum and typical + 0.22 V as the maximum (VZ is 3.10 to 3.50 V at 5 mA, Table 8, where Fig. 7 reads 3.28 V; the same two offsets are used in every row). With 1 % resistors the new solver gives (reset on 2026-11-09 from the typical ∓ 0.2 V values, which were 2.820 / 3.219, 1.789 / 2.054, 1.990 / 2.318 and 2.906 / 3.307 V):

| Design | Input | Typical | Lowest | Highest |
|---|---|---|---|---|
| R1 10 kΩ, R2 18 kΩ | 30 V | 3.020 V (diode 2.53 mA) | 2.840 V | 3.239 V |
| R1 8.2 kΩ, R2 29 kΩ | 3.0 V | 1.928 V | 1.803 V | 2.065 V |
| R1 8.2 kΩ, R2 29 kΩ | 4.1 V | 2.156 V | 2.007 V | 2.334 V |
| R1 8.2 kΩ, R2 29 kΩ | 30 V | 3.106 V | 2.926 V | 3.326 V |

Lowest is R1 +1 %, R2 −1 %, minimum column. Highest is R1 −1 %, R2 +1 %, maximum column. Check the first row by hand before trusting it: at 3.02 V the diode current is (30 − 3.02) / 10 kΩ − 3.02 / 18 kΩ = 2.53 mA, which lies between the 2 mA (2.93 V) and 5 mA (3.28 V) points. The first row replaces the Verification Baseline in CLAUDE.md.

For the Schottky example, BAT54CV Table 7 gives maximum forward voltages of 240 mV at 0.1 mA, 320 mV at 1 mA, 400 mV at 10 mA, 500 mV at 30 mA and 800 mV at 100 mA, a maximum reverse current of 2 µA at 25 V, and at most 10 pF. Confirm these against `datasheets/BAT54CV.pdf` (a local, untracked folder) before using them. Hand check for a rail Schottky with VDD 3.3 V, 10 kΩ / 18 kΩ and 30 V in, using the maximum column: about 2.44 mA, so about 0.35 V across the diode and about 3.65 V at the pin.

## Out of scope

Do not add any of these, even where they look easy:

- The skill itself.
- A verdict on current pushed into the rail, resistor voltage derating, VREF error, an ADC resolution check, an ADC sampling-time check, the board-unpowered case.
- A model of the MCU's internal protection diodes (the injection estimate stays as it is).
- Temperature handling in the solver. The skill folds hot and cold extremes into the minimum and maximum columns.
- More than one pin type, diode or pair of logic levels per file.
- Source and "checked" fields on individual values.
- A v1 converter.

## How to work

- Branch `div-v2` from `bug-fixes` (`bug-fixes` is not merged into `main`).
- Commit at the end of each of the five steps, with the tests passing. Steps 1 and 2 add code beside the old model, so the existing 401 tests still pass. Step 3 switches the app over and deletes the old model. At the end there is one solver.
- Do not merge and do not push.
- If git reports "dubious ownership", run it as `git -c safe.directory='*' ...`. Do not change the global git configuration.
- Final message: what changed per step, the test counts, the new reference numbers as you measured them, and anything in this prompt that you could not do as written.
