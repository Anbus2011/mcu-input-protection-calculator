# MCU Input Protection Calculator - AI System Context

## 1. Project Purpose & Role
You are assisting with the "MCU Input Protection Calculator," a Python desktop application (CustomTkinter) used to analyze DC voltage levels and input frequency limits for microcontroller GPIO/ADC inputs protected by a resistor divider and one clamp diode: a Zener or a Schottky, connected to GND or to the VDD rail. Works with any MCU family (STM32, ESP32, PIC, AVR, etc.).

A design lives in a `.div` file (format 2.0, `docs/div_v2_format.md`). A Claude skill (`skill/SKILL.md`) will read the MCU and diode data sheets and write that file; the app opens it so the user can review and adjust it. The skill, the app and the command-line checker `divcheck.py` all get their numbers from the same solver.

When writing or modifying code for this project, you must adhere strictly to the architectural rules and mathematical models defined in this document. What the screen shows (labels, messages, colours, layout) is described in `README.md`.

**Repository files.** `docs/project_guide.md` says what the app does, what the planned skill will do, and the workflow from requirements to an approved design. `docs/bzb984_fig7_typical.json` and `docs/bat54cv_fig1_fig2_typical.json` are readings of data-sheet graphs, which the tables of the two example files come from. The tests read `bzb984_fig7_typical.json` (`test_clamp_solver.py`), so don't move or delete these files. `skill/` holds the MCP server (`skill/server.py`), copies of the two example files for the skill's self-test (`skill/examples/`), the skill itself (`skill/SKILL.md`, the master copy) and `skill/build_package.py`, which builds the package installed in Claude Desktop (`SKILL.md` and `skill/examples/` only) into `dist/`, which is not committed.

## 2. Architecture & State Management
This project uses a strict Controller/Model/View decoupled architecture.
* **`src/models/clamp_solver.py`**: The one solver. Python standard library only (no numpy), **no UI imports**: the skill calls it under a plain Python install. `solve(design)` takes the design as a dict (the layout of a `.div` file) and returns the results as a dict. `prepare(design).pin_voltage(v_in, case)` is the pin-voltage function for sweeps.
* **`src/core/div_format.py`**: The `.div` format 2.0: structure, `validate()` (every problem with its key path), atomic write, and the part of the results that is stored in a file. Standard library only.
* **`src/core/app_state.py`**: The central controller. Owns the text of every field and table cell, builds the design dict, calls `solve()`, sweeps the solver for the plot, handles file I/O and dirty-tracking.
* **`src/ui/`**: CustomTkinter views. **NO math calculations.** Views capture input, send it to `AppState`, and display the solver's results.
* **`divcheck.py`**: Command-line checker. Must not import customtkinter, matplotlib or numpy.
* **`skill/server.py`**: The MCP server: a gateway from a Claude chat to the solver, with **no math of its own**. Its tools (`solver_info`, `solve_div`, `plot_div`) are read-only and take the text of a `.div`, never a file path. It reuses divcheck's path (`parse_json`, `validate()`, `solve()`, `with_results`, `to_text`, `divcheck.summary`), so it returns what `divcheck.py` prints and writes for the same file; the plot is `AppState`'s sweep, drawn headless by `skill/plot_png.py`. Must not import customtkinter, directly or through another module (matplotlib for the PNG only).
* **Rule: one solver.** Never embed calculation logic inside a UI button click or input callback. Always route through `AppState`, which calls `solve()`. Do not add a second calculation path.
* **Rule: one set of input rules.** Range and table rules live in `clamp_solver.py` (`NUMBER_RULES`, `CROSS_RULES`, `table_problems`, `wiring_problems`). The file validator and `AppState` use them; do not copy them.
* **Rule: no hidden defaults.** The UI forwards the raw text of every field to `AppState`, which parses it. A blank field stays blank, and nothing substitutes a value the user can't see (no `.get(key, default)`, no dataclass defaults, no fallback numbers). Blank or unreadable text becomes `None`; every result that depends on it shows "needs input" (or is cleared, with the reason shown), and everything that doesn't depend on it still computes. The only values the app fills in by itself are visible ones, both in `constants.py`: the Signal Bandwidth starting values (`BANDWIDTH_STARTING_VALUES`, each with a source note) and the unit selectors of a new design (`NEW_DESIGN_UNITS`: kΩ, kΩ, Ω). Every clamp diode and MCU value comes from the `.div` file or from the user typing it. R_s blank or 0 means no series resistor: nothing else is asked for it and it has no power check.
* **Rule: part-agnostic.** Nothing in `src/` or in the code of `skill/` (code, labels, tooltips, comments) or in the rules of this file names a specific MCU, diode, resistor, vendor or data sheet, or gives a part's data-sheet value. Every part value comes from the `.div` file or the user. Part names and data-sheet values belong only in `examples/` (and its copies in `skill/examples/`), the data-sheet readings in `docs/`, `tests/`, and the Verification Baseline (which describes the example files). Zener and Schottky are kinds of diode the app supports and may be named. A test reads the `.py` files of `src/` and `skill/`, `divcheck.py` and `main.py` for part names (`test_solver_rules.py`, `PART_SPECIFIC_PATTERNS`).
* **Rule: three table states.** Each clamp-diode table is blank (`null`: not filled in; it is listed under "Needs input" and blocks the results that use it), not modelled (`[]`: its current is taken as zero) or rows. The Clamp Diode panel and the `divcheck.py` summary say which state a table is in, and tell blank and not modelled apart. New Design starts both tables blank. A "Not modelled" box per table switches a table with no rows between blank and not modelled; "+ Add row" turns either into rows; deleting the last row returns the table to blank.
* **Rule: open + save gives the inputs back.** A file that is opened and saved without editing gets every input section back exactly as written (10 stays 10, 10.0 stays 10.0; `null`, `[]` and `created` stay). `AppState` remembers the value each field and table cell was loaded with and writes it back while its text is unchanged. An edited value is written as entered. Only `results` may change.
* **Rule: an edit unticks "checked".** Editing any value of the clamp diode or of the MCU (table cells and rows included) unticks that part's "Checked against the data sheet" box. Editing its Part, Source or Note does not.
* **Rule: the view does not rank statuses.** Where one row shows more than one check (the Max Input row of the Input Levels tab: `pin_max_safe` and `pin_max_abs`), its status is the worse of them, from `AppState.worst_status()`, which uses the solver's ordering.
* **Rule: the plot belongs to the app.** The solver returns no plot data. `AppState` sweeps the solver over the input range and hands plain lists to `plot_canvas.py`, so the curves and the tables cannot disagree. Three curves: typical (`pin_voltage(v_in, "typ")`), and the lowest and the highest of the eight corners (V_mcuL and V_mcuH of the tables). The lowest and the highest come from the solver's corners: one call to `corners(v_in)` per plot point, taking the min and the max of its eight voltages. They equal `pin_voltage(v_in, "low")` and `"high"` exactly (tested at every plot point of both examples); do not call those two in the sweep, since each solves the eight corners again. The plot's "did not settle" warning counts plot points: a point counts once if any of its solves (the typical or a corner) did not settle (`AppState.plot_unsettled_points`). VIL and VIH on the plot are the solver's results, passed on.

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
* Rows are in ascending current; each voltage column rises from row to row; `v_min` ≤ `v_typ` ≤ `v_max`; all values above 0; a table has no rows or at least two. A table with no rows is `null` or `[]`: see the three table states in §2.
* Between rows, ln(current) is linear in voltage. Outside the table, the first or last segment is extended. At or below 0 V across the diode in a direction, that direction carries no current.
* `v_min` is the part that conducts most, `v_max` the part that conducts least. One corner uses the same column in both tables. The solver has no temperature input: hot and cold extremes are folded into the two outer columns by whoever writes the file.

### B. Node Solver
* **Equation:** the current through R1 equals the current through R2 plus the diode current: $\frac{V_{in} - V}{R1} - \frac{V}{R2} - I_{diode}(V) = 0$. The pin draws no current. The VDD rail is fixed at the MCU's VDD value.
* **Method:** bisection on the node voltage, on the bracket from the lowest to the highest of $V_{in}$, 0 and the voltage of the diode's other terminal, until the bracket is 1 nV wide (`SOLVER_TOLERANCE_V = 1e-9`). The left side falls strictly as V rises, so there is one root. If the bracket has no sign change (or doesn't narrow), the result is marked "did not settle" and a warning is shown.
* **One function** (`_solve_node`) serves the results, the input levels and the plot.
* `_LN_CURRENT_MAX = 690` caps ln(current) in an extended segment so that `exp()` cannot overflow. It has no effect at any physical current (e^690 A) and is not a model parameter.
* **The solved pin voltage never falls as the input voltage rises** (tested for each wiring).

### C. Typical and Worst Case
* **Typical:** nominal R1 and R2, `v_typ` column.
* **Worst case:** solve all eight corners, R1 {min, max} × R2 {min, max} × diode column {`v_min`, `v_max`}, and take the highest or the lowest as the check requires. R min = R × (1 − tol), R max = R × (1 + tol). **Do not reason about which corner is worst**: with leakage from a rail diode the answer is not always the obvious one (in the Schottky-to-rail example file: the lowest pin voltage at Logic High is with `v_max`, the highest at Logic Low with `v_min`).
* Input levels solved: Min Input (when given), 0 V, Logic Low, Logic High, ADC Scale (when given), Max Input, Touch (when given). Each has `typ`, `low` and `high`.

### D. Checks
Statuses are PASS, TIGHT, FAIL and "needs input". The overall verdict is the worst status among the checks that have one, in the order FAIL, "needs input", TIGHT, PASS.

1. **Highest input** (at Max Input, highest pin voltage):
   * `pin_max_safe` against Safe Max: PASS with at least 50 mV of margin, TIGHT down to 0, FAIL above the limit. Safe Max is the highest pin voltage in normal operation, from the MCU data sheet; its check is the guard against current into the pin's protection structures.
   * `pin_max_abs` against Absolute Max: PASS with at least 100 mV, TIGHT down to 0, FAIL above.
2. **Lowest input** (`pin_min`): only when Min Input is given and negative. Lowest pin voltage against the MCU's Pin Min. FAIL below the limit, otherwise PASS.
3. **Logic levels:** `logic_high`: at the Logic High input the lowest pin voltage must be above VIH. `logic_low`: at the Logic Low input the highest pin voltage must be below VIL. $V_{IL} = k_{VIL} \times VDD$, $V_{IH} = k_{VIH} \times VDD$. One pair of levels per file.
4. **Power** at Max Input (`power_r1`, `power_r2`, `power_diode`, `power_rs`):
   * Typical: nominal R1/R2, `v_typ`. $P_{R1} = I_{R1}^2 R1$, $P_{R2} = I_{R2}^2 R2$, $P_{diode} = |V_{diode}| \cdot |I_{diode}|$. Total power = R1 + R2 + diode (typical).
   * Worst case, per part: the maximum over the eight corners, plus the typical point.
   * **R_s** (the pin is taken as held at 0 V, so the whole node voltage is across R_s): typical $P_{Rs} = V_{typ}^2 / R_s$; worst case $P_{Rs} = V_{node,max}^2 / R_{s,min}$.
   * Margins: (rating − power) / rating, shown against both typical and worst-case power. The worst-case margin is the verdict for each part: PASS > 20 %, TIGHT 0–20 %, FAIL ≤ 0 %. The typical margin is information only. A blank rating gives "needs input".
   * "Power verdict (worst case)": the worst status of the parts.
5. **Analog** (only when ADC Scale is given):
   * `analog_range`: highest pin voltage at ADC Scale against VDD. PASS up to VDD, FAIL above it. No TIGHT band.
   * `analog_error`: at ADC Scale with **nominal** R1 and R2, the pin voltage with the diode minus the pin voltage without it ($V_{fs} \times R2 / (R1 + R2)$); the error of larger size of the `v_min` and `v_max` columns. Shown in mV, percent (of the pin voltage without the diode) and LSB ($VDD / 2^N$). It gets a status only when an allowed error (percent) is given (PASS up to it, FAIL above); otherwise it is information.
6. **Frequency** (`frequency`, only when a required frequency is given): see §4E.

Information rows, with no status and no effect on the verdict:
* Touch voltage (for example 60 V), when given: highest pin voltage, diode current and R1 power at that input (highest of the corners).
* Current into the VDD rail at Max Input, when the diode is connected to VDD.

Also shown: ADC source impedance $R_{source} = \frac{R1 \times R2}{R1 + R2} + R_{series}$ and resolution ($VDD / 2^N$ referred to the input).

### E. Signal Bandwidth (Frequency)
The question the tab answers: what input frequency can a pin with this divider and diode handle, for uses such as pulse input and encoders? It is the frequency at the pin (per channel for an encoder), at 50 % duty.
* **Time constant:** $\tau = (R1_{max} \parallel R2_{max} + R_{s,max}) \times (C_{diode} + C_{pin} + C_{stray})$.
* **Edge time:** an edge that starts at pin level A and heads for pin level B crosses threshold T after $t = \tau \times \ln\left(\frac{B - A}{B - T}\right)$.
  * Rising edge: A = 0 V, B = lowest pin voltage at the Logic High level, T = VIH.
  * Falling edge: A = highest pin voltage at Max Input, B = highest pin voltage at the Logic Low level, T = VIL.
  * If B does not get past T, the pin never reads high (or low): the tab says so and there are no limits.
* $t_{edge}$ is the larger of the two edge times.
* **May work up to** $= \frac{1}{2 \times (t_{edge} + t_{pulse,min})}$.
* **Reliable up to** = "may work up to" divided by the margin factor.
* **Required** (optional): PASS at or below "reliable", TIGHT between the two, FAIL above "may work" (and FAIL when the pin never reads high or low).
* Also reported: τ, total capacitance, the two edge times and the shortest usable pulse ($t_{edge} + t_{pulse,min}$).
* Fields: C_diode is the clamp diode's capacitance; C_pin and the minimum pulse width are MCU data; C_stray is a board value; the margin factor is a visible field whose starting value in `constants.py` is 1.5 (1.5 MHz "may work" gives 1 MHz "reliable").
* Treating the edge as a plain RC curve toward the solved level errs on the safe side.

### F. The `.div` File and the Checker
* Format 2.0 is described in `docs/div_v2_format.md`; keep that file in step with any change. Every key must be present (`null` for blank), unknown keys are errors, numbers are JSON numbers.
* `results` is written only by the solver: `solver_version` (`SOLVER_VERSION`: a constant in the code, not a git hash, so a file's results can be traced to a solver version without git), the verdict, the checks (id, status, value, limit, unit), information rows, the key voltages, inputs still needed, notes and warnings. The app ignores stored results when it opens a file and solves again. **Bump `SOLVER_VERSION` when a change alters any result.**
* The loader reports every problem, each with its key path. Format problems (a wrong type, a missing or unknown key, or a unit, an anode/cathode terminal or a diode type that is not one of the allowed values) stop a file from opening. Value problems (out of range, table rows out of order) open in the app and are listed under "Fix:"; `divcheck.py` rejects the file for either kind.
* `python divcheck.py in.div [out.div] [--json out.json]`: exit 0 valid and solved (whatever the statuses), 1 invalid with every problem listed, 2 a file could not be read or written.
* `examples/` holds two fixtures: `zener_gnd_bzb984_c3v3.div` and `schottky_rail_bat54cv.div`. Their stored results are tested against the solver; regenerate with `python divcheck.py examples/x.div examples/x.div`, then copy the file to `skill/examples/`: the skill's self-test solves those copies through `solve_div`, and a test fails if they differ from `examples/`.

## 5. Testing
After ANY code change, run the test suite before committing:

```bash
python -m pytest tests/ -v
```

All 910 tests must pass. The UI tests carry the pytest marker `ui` (registered in `pytest.ini`); they need a desktop session and take a little over three minutes. While working, `python -m pytest tests/ -m "not ui"` runs the others in about 35 seconds. Run the whole suite before committing.

The non-UI tests still need the packages in `requirements.txt` installed: pytest imports `tests/test_ui.py` to collect it even when its tests are deselected, and one non-UI test (`test_plot_is_not_numpy` in `test_app_state.py`) imports the plot module. Only the UI tests also need a desktop session.

What each file covers:
* `test_clamp_solver.py`: the solver: reference numbers, the wirings, the diode tables, bisection, "needs input", every check and its thresholds, the verdict.
* `test_solver_rules.py`: the solver's rules: one solver, nothing computed from a missing input, no fallback values, worst-case power, no part named in the app (part-agnostic).
* `test_design_calculation.py`: the whole calculation on the baseline design and the 8.2 kΩ / 29 kΩ design.
* `test_frequency.py`: the time constant, the two edge times, the two frequency limits.
* `test_div_format.py`: the file format: the two example files and their stored results, every format and value problem, atomic write.
* `test_divcheck.py`: the checker: summary, output files, the same `results` as the app's Save, exit codes, no GUI packages.
* `test_mcp_server.py`: the MCP server: the same results, file text, summary and problems as `divcheck.py`, the copies in `skill/examples/`, the commit and `dirty` in every answer, the PNG and its curves against `AppState`'s sweep, no customtkinter, a client round trip in process, over stdio and over HTTP.
* `test_skill_md.py`: the skill: the `SOLVER_VERSION` that `skill/SKILL.md` states is the solver's, every tool and field it names exists in `skill/server.py` (and every `.div` key in the format), no part named; the package of `skill/build_package.py` holds `SKILL.md` and `skill/examples/` only.
* `test_file_io.py`: save and load round trip, other files refused, dirty tracking.
* `test_app_state.py`: `AppState`: parsing, "needs input", range checks, the table states, loading and saving, open + save, "checked", the plot sweep.
* `test_ui.py`: drives the real, withdrawn window through its widgets: every input, panel and tab, the tooltips, the plot. Three layout tests show the window at 1400×900 and are skipped on a screen it does not fit.
* `designs.py`: the designs the tests share.

If a test fails after your change, fix the issue before committing. Do not skip or delete tests.

### Verification Baseline
The parts named here are the parts of the example files, not assumptions of the app.

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

Schottky to the rail (`examples/schottky_rail_bat54cv.div`, BAT54CV, same divider, 30 V): with the maximum column and nominal resistors 2.43 mA (the solver gives 2.432 mA), 0.351 V across the diode, 3.651 V at the pin.

## 6. Removed: do not bring back
* The three-region Zener model: the diode tables replace it (§4A).
* The 0.94 and 0.97 knee factors.
* The 0.5 mA rule and its step.
* ZZK.
* The low-voltage Zener corner derived from VZ min: the `v_min` column is that corner.
* Part presets (a drop-down of diodes or MCUs): values come from the file or the user.
* The name "Zener" for the clamp diode on the screen: the diode can be a Schottky.
* The injection current estimate, the Injection Limit field and the `safe_injection_ma` key: Safe Max is the guard.
* The 100 Ω internal ESD path, in any formula: no data sheet gives it.
* The ADC sampling-cycle table: it did not match the MCU data sheet.
* A hint value for a blank rating: it gives "needs input".
* Signal Bandwidth inputs N_samples, peripheral clock, counter bits and signed.
* f_read and the counter-overflow limit.
* The −3 dB bandwidth.
* The 10–90 % rise time.
* The two analog frequency limits.
* The bottleneck name.
* A format 1.0 reader or converter: a 1.0 file gets one clear message.
