# MCU Input Protection Calculator - AI System Context

## 1. Project Purpose & Role
You are assisting with the "MCU Input Protection Calculator," a Python desktop application (CustomTkinter) used to analyze DC voltage levels and input frequency limits for microcontroller GPIO/ADC inputs protected by a resistor divider and one clamp diode: a Zener or a Schottky, connected to GND or to the VDD rail. Works with any MCU family (STM32, ESP32, PIC, AVR, etc.).

A design lives in a `.div` file (format 2.0, `docs/div_v2_format.md`). A Claude skill (not part of this repository) will read the MCU and diode data sheets and write that file; the app opens it so the user can review and adjust it. The skill, the app and the command-line checker `divcheck.py` all get their numbers from the same solver.

When writing or modifying code for this project, you must adhere strictly to the architectural rules and mathematical models defined in this document.

## 2. Architecture & State Management
This project uses a strict Controller/Model/View decoupled architecture.
* **`src/models/clamp_solver.py`**: The one solver. Python standard library only (no numpy), **no UI imports**: the skill calls it under a plain Python install. `solve(design)` takes the design as a dict (the layout of a `.div` file) and returns the results as a dict. `prepare(design).pin_voltage(v_in, case)` is the pin-voltage function for sweeps.
* **`src/core/div_format.py`**: The `.div` format 2.0: structure, `validate()` (every problem with its key path), atomic write, and the part of the results that is stored in a file. Standard library only.
* **`src/core/app_state.py`**: The central controller. Owns the text of every field and table cell, builds the design dict, calls `solve()`, sweeps the pin-voltage function for the plot, handles file I/O and dirty-tracking.
* **`src/ui/`**: CustomTkinter views. **NO math calculations.** Views capture input, send it to `AppState`, and display the solver's results.
* **`divcheck.py`**: Command-line checker. Must not import customtkinter, matplotlib or numpy.
* **Rule:** Never embed calculation logic inside a UI button click or input callback. Always route through `AppState`, which calls `solve()`. There is one solver: do not add a second calculation path.
* **Rule: one set of input rules.** Range and table rules live in `clamp_solver.py` (`NUMBER_RULES`, `CROSS_RULES`, `table_problems`, `wiring_problems`). The file validator and `AppState` use them; do not copy them.
* **Rule: no hidden defaults.** The UI forwards the raw text of every field to `AppState`, which parses it. A blank field stays blank, and nothing substitutes a value the user can't see (no `.get(key, default)`, no dataclass defaults, no fallback numbers). Blank or unreadable text becomes `None`; every result that depends on it shows "needs input" (or is cleared, with the reason shown), and everything that doesn't depend on it still computes. The only values the app fills in by itself are visible ones: the Signal Bandwidth starting values in `constants.py` (each with a source note). There are no part presets: every clamp diode and MCU value comes from the `.div` file or from the user typing it. R_s blank or 0 means no series resistor.
* **Rule: the plot belongs to the app.** The solver returns no plot data. `AppState` sweeps the solver's pin-voltage function over the input range and hands plain lists to `plot_canvas.py`, so the curve and the tables cannot disagree.

## 3. Circuit Topology
    V_input ── R1 ──┬── R_series ──> MCU GPIO Pin
                    │
                    ├── clamp diode ── GND or VDD
                    │
                    └── R2 ── GND

The diode is a two-terminal part. `anode` and `cathode` are each `node` (the junction of R1 and R2), `gnd` or `vdd`; exactly one is `node`.
* Zener: cathode at the node, anode at GND.
* Schottky to the rail: anode at the node, cathode at VDD.
* Schottky to GND: anode at GND, cathode at the node.

`type` (`zener` or `schottky`) is a label for the screen. **The math must not branch on it** (the solver never reads it).

## 4. Mathematical Models (Source of Truth)

### A. Diode Tables
The diode is described by measured points from its data sheet, not by a diode type.
* Two tables, `forward` (anode positive) and `reverse` (cathode positive). Each row is a current (`i_ma`) and the voltage across the diode at that current: `v_min`, `v_typ`, `v_max`. Reverse values are written as positive numbers.
* Rows are in ascending current; each voltage column rises from row to row; `v_min` ≤ `v_typ` ≤ `v_max`; all values above 0; a table has no rows or at least two.
* Between rows, ln(current) is linear in voltage. Outside the table, the first or last segment is extended. At or below 0 V across the diode in a direction, that direction carries no current.
* An empty table means that direction is not modelled (no current), and the Clamp Diode panel says so ("no reverse data: leakage not included").
* `v_min` is the part that conducts most, `v_max` the part that conducts least. One corner uses the same column in both tables. The solver has no temperature input: hot and cold extremes are folded into the two outer columns by whoever writes the file.
* Removed, do not bring back: the three-region Zener model, the 0.94 and 0.97 knee factors, the 0.5 mA rule and its step, ZZK, the low-voltage Zener corner derived from VZ min.

### B. Node Solver
* **Equation:** the current through R1 equals the current through R2 plus the diode current: $\frac{V_{in} - V}{R1} - \frac{V}{R2} - I_{diode}(V) = 0$. The pin draws no current. The VDD rail is fixed at the MCU's VDD value.
* **Method:** bisection on the node voltage, on the bracket from the lowest to the highest of $V_{in}$, 0 and the voltage of the diode's other terminal, until the bracket is 1 nV wide (`SOLVER_TOLERANCE_V = 1e-9`). The left side falls strictly as V rises, so there is one root. If the bracket has no sign change (or doesn't narrow), the result is marked "did not settle" and a warning is shown.
* **One function** (`_solve_node`) serves the results, the input levels and the plot.
* **The solved pin voltage never falls as the input voltage rises** (tested for each wiring).

### C. Typical and Worst Case
* **Typical:** nominal R1 and R2, `v_typ` column.
* **Worst case:** solve all eight corners, R1 {min, max} × R2 {min, max} × diode column {`v_min`, `v_max`}, and take the highest or the lowest as the check requires. R min = R × (1 − tol), R max = R × (1 + tol). **Do not reason about which corner is worst**: with leakage from a rail diode the answer is not always the obvious one (BAT54CV example: the lowest pin voltage at Logic High is with `v_max`, the highest at Logic Low with `v_min`).
* Input levels solved: Min Input (when given), 0 V, Logic Low, Logic High, ADC Scale (when given), Max Input, Touch (when given). Each has `typ`, `low` and `high`.

### D. Checks
Statuses are PASS, TIGHT, FAIL and "needs input". The overall verdict is the worst status among the checks that have one, in the order FAIL, "needs input", TIGHT, PASS.

1. **Highest input** (at Max Input, highest pin voltage):
   * `pin_max_safe` against Safe Max: PASS with at least 50 mV of margin, TIGHT down to 0, FAIL above the limit.
   * `pin_max_abs` against Absolute Max: PASS with at least 100 mV, TIGHT down to 0, FAIL above.
   * **Safe Max is the guard against injection** (STM32: VDDA + 0.3 V, the threshold before internal ESD injection begins). **There is no injection current estimate** (removed 2026-11-09, approved by the owner): the old formula divided by 100 Ω for the internal ESD path, a number from the first version of the app that no data sheet gives. There is no Injection Limit field and no `safe_injection_ma` key.
2. **Lowest input** (`pin_min`): only when Min Input is given and negative. Lowest pin voltage against the MCU's Pin Min. FAIL below the limit, otherwise PASS.
3. **Logic levels:** `logic_high`: at the Logic High input the lowest pin voltage must be above VIH. `logic_low`: at the Logic Low input the highest pin voltage must be below VIL. $V_{IL} = k_{VIL} \times VDD$, $V_{IH} = k_{VIH} \times VDD$ (STM32G4: 0.3 and 0.7, DS12983 Rev 5, Table 54). One pair of levels per file.
4. **Power** at Max Input (`power_r1`, `power_r2`, `power_diode`, `power_rs`):
   * Typical: nominal R1/R2, `v_typ`. $P_{R1} = I_{R1}^2 R1$, $P_{R2} = I_{R2}^2 R2$, $P_{diode} = |V_{diode}| \cdot |I_{diode}|$. Total power = R1 + R2 + diode (typical).
   * Worst case, per part: the maximum over the eight corners, plus the typical point.
   * **R_s** (the pin is taken as held at 0 V, so the whole node voltage is across R_s; no 100 Ω anywhere): typical $P_{Rs} = V_{typ}^2 / R_s$; worst case $P_{Rs} = V_{node,max}^2 / R_{s,min}$.
   * Margins: (rating − power) / rating, shown against both typical and worst-case power. The worst-case margin is the verdict for each part: PASS > 20 %, TIGHT 0–20 %, FAIL ≤ 0 %. The typical margin is information only. A blank rating shows "needs input" (no hint value). R_s blank or 0: the R_s row shows "no R_s" and nothing is asked for.
   * "Power verdict (worst case)": the worst status of the parts.
5. **Analog** (only when ADC Scale is given):
   * `analog_range`: highest pin voltage at ADC Scale against VDD. PASS up to VDD, FAIL above it. No TIGHT band.
   * `analog_error`: at ADC Scale with **nominal** R1 and R2, the pin voltage with the diode minus the pin voltage without it ($V_{fs} \times R2 / (R1 + R2)$); the error of larger size of the `v_min` and `v_max` columns. Shown in mV, percent (of the pin voltage without the diode) and LSB ($VDD / 2^N$). It gets a status only when an allowed error (percent) is given (PASS up to it, FAIL above); otherwise it is information.
6. **Frequency** (`frequency`, only when a required frequency is given): see §4E.

Information rows, with no status and no effect on the verdict:
* Touch voltage (for example 60 V), when given: highest pin voltage, diode current and R1 power at that input (highest of the corners).
* Current into the VDD rail at Max Input, when the diode is connected to VDD.

Also shown: ADC source impedance $R_{source} = \frac{R1 \times R2}{R1 + R2} + R_{series}$ and resolution ($VDD / 2^N$ referred to the input). There is no ADC sampling-cycle table (it did not match DS12983 Rev 5, Table 67).

### E. Signal Bandwidth (Frequency)
The question the tab answers: what input frequency can a pin with this divider and diode handle, for uses such as pulse input and encoders? It is the frequency at the pin (per channel for an encoder), at 50 % duty.
* **Time constant:** $\tau = (R1_{max} \parallel R2_{max} + R_{s,max}) \times (C_{diode} + C_{pin} + C_{stray})$.
* **Edge time:** an edge that starts at pin level A and heads for pin level B crosses threshold T after $t = \tau \times \ln\left(\frac{B - A}{B - T}\right)$.
  * Rising edge: A = 0 V, B = lowest pin voltage at the Logic High level, T = VIH.
  * Falling edge: A = highest pin voltage at Max Input, B = highest pin voltage at the Logic Low level, T = VIL.
  * If B does not get past T, the tab says the pin never reads high (or low) and shows no limits.
* $t_{edge}$ is the larger of the two edge times.
* **May work up to** $= \frac{1}{2 \times (t_{edge} + t_{pulse,min})}$.
* **Reliable up to** = "may work up to" divided by the margin factor.
* **Required** (optional): PASS at or below "reliable", TIGHT between the two, FAIL above "may work" (and FAIL when the pin never reads high or low).
* A Details control shows τ, total capacitance, the two edge times and the shortest usable pulse ($t_{edge} + t_{pulse,min}$).
* Fields: C_diode is the clamp diode's capacitance; C_pin and the minimum pulse width are MCU data; C_stray is a board value; the margin factor is a visible field whose starting value in `constants.py` is 1.5 (owner's example, 2026-11-09: 1 MHz reliable, 1.5 MHz may work).
* Treating the edge as a plain RC curve toward the solved level errs on the safe side.
* Removed, do not bring back: N_samples, the peripheral clock, counter bits, signed, f_read, the counter-overflow limit, the −3 dB bandwidth, the 10–90 % rise time, the two analog limits, the bottleneck name.

### F. The `.div` File and the Checker
* Format 2.0 is described in `docs/div_v2_format.md`; keep that file in step with any change. Every key must be present (`null` for blank), unknown keys are errors, numbers are JSON numbers.
* `results` is written only by the solver: `solver_version` (the constant `SOLVER_VERSION`, not a git hash), the verdict, the checks (id, status, value, limit, unit), information rows, the key voltages, inputs still needed, notes and warnings. The app ignores stored results when it opens a file and solves again. **Bump `SOLVER_VERSION` when a change alters any result.**
* There is no format 1.0 converter. A 1.0 file gets one clear message.
* The loader reports every problem, each with its key path. Format problems (wrong type, missing or unknown key) stop a file from opening. Value problems (out of range, table rows out of order) open in the app and are listed under "Fix:"; `divcheck.py` rejects the file for either kind.
* `python divcheck.py in.div [out.div] [--json out.json]`: exit 0 valid and solved (whatever the statuses), 1 invalid with every problem listed, 2 a file could not be read or written.
* `examples/` holds two fixtures: `zener_gnd_bzb984_c3v3.div` and `schottky_rail_bat54cv.div`. Their stored results are tested against the solver; regenerate with `python divcheck.py examples/x.div examples/x.div`.

## 5. Testing
After ANY code change, run the test suite before committing:

```bash
python -m pytest tests/ -v
```

All 716 tests must pass. The suite covers:
* **Solver** (`test_clamp_solver.py`, 190 tests): reference numbers, the Schottky-to-rail hand check, the three wirings (plus the fourth), pin voltage never falls as the input rises, `type` is only a label, diode tables (interpolation, extension, rules), bisection to 1 nV, "did not settle", "needs input" with the rest still computed, R_s rules, every check and its thresholds, information rows, the overall verdict, standard library only
* **Solver rules** (`test_solver_rules.py`, 44 tests): reference case, one solver for results / levels / plot, bisection, no results from missing inputs, no fallback values, zero ratings, ADC bits, VIL/VIH factors, frequency rules, no injection estimate, worst-case power and hand-checked corners, blank rating, power verdict
* **Design calculation** (`test_design_calculation.py`, 32 tests): diode table model, full baseline calculation, Kirchhoff's current law, power sums, tolerance ratios, input levels, the 8.2 kΩ / 29 kΩ design, edge cases
* **Frequency** (`test_frequency.py`, 11 tests): time constant, the two edge formulas, the two limits, edge cases
* **File format** (`test_div_format.py`, 72 tests): the two example files (valid, inputs, stored results), structure, every problem reported, format and value problems, null is blank, stored results, atomic write, written text
* **Checker** (`test_divcheck.py`, 21 tests): summary, output files, invalid files, exit codes, runs without customtkinter / matplotlib / numpy
* **File I/O** (`test_file_io.py`, 9 tests): save/load round-trip, format version, example file, format 1.0 refused, blank values, dirty tracking
* **AppState** (`test_app_state.py`, 151 tests): frequency inputs and starting values, every field marks unsaved, blank design, "needs input", range checks, R_s rules, unreadable text blocks Save, atomic save, loading (every format problem, state untouched on failure, value problems listed to fix, stored results ignored), clamp-diode tables and connection, new MCU and system values, the plot sweep
* **UI** (`test_ui.py`, 186 tests; needs a desktop session): drives the real, withdrawn window through its widgets: change tracking on every input, blank / 0 / unreadable on every numeric field, New Design clearing everything, save-failure messages, loading, no preset drop-down, "Zener" renamed, the clamp-diode tables (typing, add and delete row, "not modelled" notes), no injection row, power table and verdict, overall verdict line, Input Levels table, Min Input / analog error / information rows, the two-number Signal Bandwidth tab with its Details control

Shared designs for the tests are in `tests/designs.py`.

If a test fails after your change, fix the issue before committing. Do not skip or delete tests.

### Verification Baseline
If you modify `clamp_solver.py`, ensure these reference calculations still hold (`examples/zener_gnd_bzb984_c3v3.div`):
* **Inputs:** R1 = 10 kΩ, R2 = 18 kΩ (1 %), no R_series, V_input = 30 V, VDD 3.3 V, BZB984-C3V3 from the node (cathode) to GND. Reverse table: typical column from the data sheet's Fig. 7; `v_min` = typical − 0.18 V and `v_max` = typical + 0.22 V in every row (Table 8: 3.10 to 3.50 V at 5 mA, where Fig. 7 reads 3.28 V).
* **Expected Outputs:**
  * Input Impedance: 28 kΩ
  * Divider Ratio: 0.643
  * V_mcu Typical: 3.020 V
  * V_mcu Lowest / Highest: 2.840 V / 3.239 V
  * Diode Current: 2.53 mA
  * Verdict: FAIL, on `logic_high` only (3.8 V Logic High leaves the pin at 1.831 V, below VIH 2.31 V)

By hand: at 3.02 V the diode current is (30 − 3.02) / 10 kΩ − 3.02 / 18 kΩ = 2.53 mA, between the 2 mA (2.93 V) and 5 mA (3.28 V) rows.

The same diode with R1 8.2 kΩ, R2 29 kΩ (typical / lowest / highest): 1.928 / 1.803 / 2.065 V at 3.0 V in, 2.156 / 2.007 / 2.334 V at 4.1 V, 3.106 / 2.926 / 3.326 V at 30 V.

Schottky to the rail (`examples/schottky_rail_bat54cv.div`, BAT54CV, same divider, 30 V): with the maximum column and nominal resistors 2.44 mA, 0.351 V across the diode, 3.651 V at the pin.
