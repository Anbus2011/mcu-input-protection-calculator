# Project guide

What this project is for, what the planned Claude skill will do, and the workflow from requirements to an approved input design.

| Document | What it covers |
|---|---|
| `README.md` | Installing and running the app, what each panel and tab shows |
| `CLAUDE.md` | Rules for changing the code: architecture, the solver's math, tests, the Verification Baseline |
| `docs/div_v2_format.md` | The `.div` file, format 2.0: every key, every check, the checker |
| `docs/project_guide.md` | This file |

## 1. What the app does

- One `.div` file is one MCU input pin behind a resistor divider (R1 from the input to the node, R2 from the node to GND, an optional R_series to the pin) and one clamp diode (a Zener or a Schottky, to GND or to the VDD rail).
- The app opens a `.div` and solves it again. It ignores any stored results.
- It shows every check and the verdict:
  - the pin's highest voltage against Safe Max and Absolute Max;
  - the lowest pin voltage;
  - logic high and low;
  - worst-case power in each part;
  - analog range and error;
  - the frequency the pin can follow.
- The user reviews the file, ticks "Checked against the data sheet" for the diode and the MCU, and adjusts values when a check is close. Save writes the inputs back as they were read, except values the user edited, plus fresh `results`.
- `python divcheck.py in.div [out.div] [--json out.json]` gives the same results from the command line, with a plain Python install.
- The app, `divcheck.py` and the skill all use the one solver, `src/models/clamp_solver.py`. The app is a way to review the solver's results, not an independent check of its math. The example files, the tests and hand calculations are the safety net.

## 2. What the skill will be

The skill is not built yet. It will be a Claude skill that designs the protection network for one input and writes its `.div`.

**In the skill (deterministic):**
- the solver, reached through an MCP server that lives in `skill/` in this repository. The server imports `src/models/clamp_solver.py` and `src/core/div_format.py` directly, so the repository holds the only copy of the solver. Its tools take the contents of a `.div` (not a file path, so the server can run on another machine), validate and solve it, return the file with `results` filled in and draw the plot. Every call also returns `SOLVER_VERSION` and the commit the server is running. `skill/` also holds the skill's `SKILL.md`. That folder is the master copy: changes are made there, never in the copy installed in Claude;
- a value search over E96 R1/R2 pairs, ranked by a fixed rule;
- the resistor specification: value, tolerance, power rating after derating to the check temperature, and working voltage;
- the `.div` writer and the report template.

**In chat:**
- confirming the requirements (asked once per board, then saved);
- assigning a role to each input;
- reading data sheets into the `mcu` and `clamp_diode` sections;
- trade-off choices that the requirements don't settle;
- the part-number search, done only after the resistor specification is agreed.

**Rules:**
- The script does all the math. Chat never retypes a number: tables and plots are shown as the script printed them.
- Nothing is guessed. A value the skill can't source is written as `null` and shows as "needs input".
- Every data-sheet value is cited in `source` and `note` (document number, revision, table or figure), and the section is written with `checked: false`.
- Before designing, the skill runs `divcheck.py` on both files in `examples/` and stops if the results differ from the stored ones.
- The skill has its own version number and states the `SOLVER_VERSION` it was written and tested for. If the server reports a different `SOLVER_VERSION`, the skill stops and says the skill may need updating. Every `.div` carries `SOLVER_VERSION` in its `results`, and the skill writes its own version, the solver version and the server's commit in the file's `notes` and in its report (format 2.0 has no key for them).
- A check the solver doesn't make (for example resistor derating at temperature, or the board's minimum rail load) is reported as done by the skill or as not checked, never as PASS.
- `rating_mw` in the `.div` is the data-sheet rating as stated. Derating to the check temperature is the skill's own check, in its report.

## 3. The workflow

1. **Requirements.** The user gives them through the skill:
   - the highest continuous input voltage (`v_input_max`: the board must survive it, and the Safe Max check runs at it), the touch voltage (`v_touch`) and the most negative input (`v_input_min`);
   - the logic sources' levels;
   - the required frequency;
   - analog full scale and allowed error;
   - the temperature range;
   - the MCU pin type.

   A file holds one pair of logic levels, so with several sources it takes the lowest high and the highest low. Inputs with different roles (for example analog and digital) get one `.div` each. When one node feeds several MCU pins, the weakest pin's limits go in the file.
2. **MCU.** The skill reads the MCU data sheet and fills in the `mcu` section, with `source`, `note` and `checked: false`.
3. **Resistors.** The skill proposes the resistor criteria (values, tolerance, power rating, package) and agrees them with the user. It searches for part numbers only after that.
4. **Diode.** The skill reads the diode data sheet and writes the `forward` and `reverse` tables. Temperature goes into the outer columns: `v_min` is the part that conducts most and `v_max` the part that conducts least, over the temperature range. For a Schottky those are the hot and the cold extremes, in both tables. The `note` says how each column was obtained, including any column the data sheet doesn't guarantee.
5. **Solve.** The skill writes the `.div` and runs `divcheck.py`. It iterates over the value search until every check passes, or reports which check can't pass and the options.
6. **Review.** The user opens the file in the app and compares the MCU and diode values with the data sheets. They tick "checked" and adjust any close values.
7. **Bench check.** Before a design is approved, sweep the input to about 5, 12, 24 and 30 V on a built board and compare the measured pin voltage with the typical curve.

## 4. Out of scope

- More than one diode per file.
- Temperature as an input: it is folded into the `v_min` and `v_max` columns.
- VDD tolerance: VDD is one value, which also serves as the ADC reference.
- Current into the MCU's own protection structures: Safe Max is the guard.

## 5. Next work

1. Build the skill in `skill/`: the MCP server, its tests (both files in `examples/` solved through the server's tools give their stored results), and `SKILL.md`. Then test the installed skill live in a Claude chat.
2. The first real design, made with the skill: the user inputs of a dual-channel motor controller. Its requirements are kept with that board's project, not in this repository.
