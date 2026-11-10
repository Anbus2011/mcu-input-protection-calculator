---
name: mcu-input-protection
description: Designs the resistor divider and clamp diode for one MCU input pin and writes its .div file, solved by the mcu-input-calculator MCP server. Use to design, check or change an MCU input or a .div file.
---

# MCU input protection

Designs the protection network for one MCU input pin and writes its .div file (format 2.0): a resistor divider (R1 from the input to the node, R2 from the node to GND, an optional R_series to the pin) and one clamp diode (a Zener or a Schottky, to GND or to the VDD rail). The user reviews the file in the MCU Input Protection Calculator app.

The solver does the math. It is reached through the MCP server `mcu-input-calculator`, whose tools take the whole .div as JSON text, never a file path:

| Tool | What it gives |
|---|---|
| `solver_info` | `solver_version`, `commit` and `dirty` of the server |
| `solve_div` | `valid`, `problems`, `div` (the file with `results` filled in) and `summary` (the results as plain text) |
| `plot_div` | the plot of pin voltage against input voltage |

If these tools are not available, stop and say so.

## Versions

- Skill version: 1.0.0
- Written and tested for SOLVER_VERSION: 2.0.0

## Start of every session

Do both steps before any design work.

1. **Server.** Call `solver_info`.
   - `solver_version` is not the SOLVER_VERSION above: stop. Tell the user both versions and that the skill may need updating.
   - `dirty` is `true`: continue. Write "server dirty: true" with the `commit` in the `notes` of every .div, and flag it at the top of the report.
2. **Self-test.** Send the text of each .div in this skill's examples/ folder, unchanged, to `solve_div`. Each must come back `valid`, and the `results` in the returned `div` must equal the `results` stored in the file. If anything differs, stop and say which file and which results. The examples are test files: what counts is that the results are the stored ones, whatever their verdict.

## Workflow

1. **Requirements.** Confirm them with the user once per board, and save them with that board's project:
   - the highest continuous input voltage (`v_input_max`: the board must survive it, and the Safe Max check runs at it), the touch voltage (`v_touch`) and the most negative input (`v_input_min`);
   - the logic sources' levels (`v_logic_high_min`, `v_logic_low_max`);
   - the required frequency (`f_required_hz`);
   - analog full scale and allowed error (`v_analog_fullscale`, `analog_error_allowed_pct`);
   - the temperature range;
   - the MCU pin type (`pin_type`).

   Give each input a role. A file holds one pair of logic levels: with several sources, the lowest high and the highest low. Inputs with different roles (analog and digital, say) get one .div each. When one node feeds several MCU pins, the weakest pin's limits go in the file.
2. **MCU.** Read the MCU data sheet and fill in the `mcu` section.
3. **Resistors.** Propose the resistor specification and agree it with the user: value (E96 series), tolerance (1 % by default), power rating after derating to the check temperature, working voltage, package. Search for part numbers, through a distributor's parts search, only after the specification is agreed. `rating_mw` is the data-sheet rating as stated; the derating is the skill's own check, in the report.
4. **Diode.** Read the diode data sheet and write the `forward` and `reverse` tables. Temperature goes into the outer columns: `v_min` is the part that conducts most and `v_max` the part that conducts least, over the temperature range. For a Schottky those are the hot and the cold extremes, in both tables. The `note` says how each column was obtained, including any column the data sheet doesn't guarantee.
5. **Solve.** Write the .div and send it to `solve_div`. Correct whatever `problems` lists. Change R1 and R2 (E96 values) and solve again until every check passes, or report which check can't pass and the options. A trade-off the requirements don't settle is the user's choice. Hand over the `div` text exactly as `solve_div` returned it.
6. **Review.** The user opens the file in the app, compares the MCU and diode values with the data sheets, ticks "Checked against the data sheet" and adjusts any close values.
7. **Bench check.** Before a design is approved, the input is swept on a built board, at several voltages up to the highest input, and the measured pin voltage is compared with the typical curve.

## Rules

- **The solver does all the math.** Every result comes from `solve_div`. Don't work one out and don't retype one: show tables as `solve_div` returned them (`summary`) and plots as `plot_div` drew them.
- **Nothing is guessed.** A value with no source is written as `null` and shows as "needs input". The example files show the layout of a .div; never take a value from them.
- **Every data-sheet value is cited** in the `source` and `note` of its section (document number, revision, table or figure), and the section is written with `checked: false`. Only the user ticks it, in the app.
- **A check the solver doesn't make** (resistor derating at temperature, the board's minimum rail load) is reported as done by the skill, with what was compared, or as not checked. Never as PASS.
- **Versions.** The skill version, the `solver_version` and the server's `commit` go in the `notes` of every .div and in the report.
- **The file.** Every key of the format is present, `null` for a blank; an unknown key is an error; `results` is written only by the solver. A diode table with no rows is `null` while it is still to be filled in, and `[]` only when that direction is left out on purpose, which the `note` then says.

## Report template

One report per .div, in this order. Where a section has nothing, write "none".

    SERVER DIRTY: true, commit <commit>            (first line; only when dirty is true)

    Design: <file name>: <the input and its role>
    Verdict: <verdict, as solve_div returned it>
    Skill <skill version>, solver <solver_version>, server commit <commit>, dirty <true or false>
    Self-test: the example files gave their stored results

    Requirements
      <the confirmed requirements this file uses>

    Parts
      R1, R2, R_series: value, tolerance, rating, working voltage, package; part number, or "not searched"
      Clamp diode: part, source
      MCU: part, pin type, source

    Results
      <summary, exactly as solve_div returned it>
      <the plot, as plot_div drew it>

    Checks the solver doesn't make
      <check>: done by the skill: <what was compared, and the outcome in words>
      <check>: not checked

    Needs input
      <key>: <why it has no source>

    Choices for the user
      <a trade-off the requirements don't settle, or a check that can't pass, with the options>

    Next
      Review in the app: compare the MCU and diode values with the data sheets, tick "Checked against the data sheet".
      Bench check on a built board, before the design is approved.
