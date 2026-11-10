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

`skill/SKILL.md` is written and not yet tested live in a Claude chat. It is a Claude skill that designs the protection network for one input and writes its `.div`.

**Deterministic, through the MCP server:**
- the solver, reached through an MCP server that lives in `skill/` in this repository. The server imports `src/models/clamp_solver.py` and `src/core/div_format.py` directly, so the repository holds the only copy of the solver. Its tools take the contents of a `.div` (not a file path, so the server can run on another machine), validate and solve it, return the file with `results` filled in and draw the plot. Every call also returns `SOLVER_VERSION`, the commit the server is running and `dirty` (true when the server's folder had uncommitted changes when it started). The server does no math of its own, chooses no values and reads or writes no files.

**Fixed rules, in `SKILL.md`** (`skill/SKILL.md` is the master copy: changes are made there, never in the copy installed in Claude):
- the workflow below and the check list;
- resistor values from the E96 series, 1 % tolerance by default;
- the resistor specification: value, tolerance, power rating after derating to the check temperature, and working voltage;
- the report template.

**In chat:**
- confirming the requirements (asked once per board, then saved);
- assigning a role to each input;
- reading data sheets into the `mcu` and `clamp_diode` sections;
- choosing R1 and R2, writing the `.div`, solving it through the server, and changing values until the checks pass;
- trade-off choices that the requirements don't settle;
- the part-number search, through a distributor's parts search, done only after the resistor specification is agreed.

**Rules:**
- The solver does all the math, through the server. Chat never retypes a number: tables are shown as `solve_div` returned them and plots as `plot_div` drew them.
- Nothing is guessed. A value the skill can't source is written as `null` and shows as "needs input".
- Every data-sheet value is cited in `source` and `note` (document number, revision, table or figure), and the section is written with `checked: false`.
- Before designing, the skill solves both example files through `solve_div` and stops if the results differ from their stored results. It uses its own copies in `skill/examples/`; a test fails if they differ from `examples/`.
- The skill has its own version number and states the `SOLVER_VERSION` it was written and tested for. If the server reports a different `SOLVER_VERSION`, the skill stops and says the skill may need updating. Every `.div` carries `SOLVER_VERSION` in its `results`, and the skill writes its own version, the solver version and the server's commit in the file's `notes` and in its report (format 2.0 has no key for them).
- When `solver_info` reports `dirty: true`, the skill continues. It writes "server dirty: true" with the commit in the file's `notes`, and flags it at the top of its report.
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
5. **Solve.** Claude writes the `.div` and solves it through the MCP server. It changes R1 and R2 (E96 values) and solves again until every check passes, or reports which check can't pass and the options.
6. **Review.** The user opens the file in the app and compares the MCU and diode values with the data sheets. They tick "checked" and adjust any close values.
7. **Bench check.** Before a design is approved, sweep the input to about 5, 12, 24 and 30 V on a built board and compare the measured pin voltage with the typical curve.

## 4. Out of scope

- More than one diode per file.
- Temperature as an input: it is folded into the `v_min` and `v_max` columns.
- VDD tolerance: VDD is one value, which also serves as the ADC reference.
- Current into the MCU's own protection structures: Safe Max is the guard.

## 5. Next work

1. Finish the skill in `skill/`. The MCP server and its tests are done (`skill/server.py`, `tests/test_mcp_server.py`: both files in `examples/` solved through the server's tools give their stored results). `SKILL.md` is written (`skill/SKILL.md`, `tests/test_skill_md.py`: the `SOLVER_VERSION` it states is the solver's, and every tool and field it names exists in the server). `python skill/build_package.py` builds the package that is installed in Claude Desktop, `dist/mcu-input-protection.zip`: `SKILL.md` and `skill/examples/` only, not committed. Still to do: register the server in Claude Desktop, install the package, then test the installed skill live in a Claude chat.
2. Solver bench check (later, on a breadboard). Build one divider with a Schottky to a 3.3 V rail, using parts on hand. Any parts will do, as long as the diode has a data sheet for the `.div` tables. Enter the resistors' measured values in the `.div`. Put a load resistor of a few hundred ohms on the 3.3 V rail, since a bench supply can't sink the clamp current. Sweep the input through about 1, 2, 3, 5, 12, 24 and 30 V, read the node with a DMM, and compare with `solve_div`'s typical curve and min/max band. This checks the solver; workflow step 7 checks a real design on a built board.
3. The first real design, made with the skill: the user inputs of a dual-channel motor controller. Its requirements are kept with that board's project, not in this repository.
