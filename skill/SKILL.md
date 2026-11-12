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

- Skill version: 1.1.0
- Written and tested for SOLVER_VERSION: 2.0.0

## Start of every session

Do both steps before any design work.

1. **Server.** Call `solver_info`.
   - `solver_version` is not the SOLVER_VERSION above: stop. Tell the user both versions and that the skill may need updating.
   - `dirty` is `true`: continue. Write "server dirty: true" with the `commit` in the `notes` of every .div, and flag it at the top of the report.
   - `commit` or `dirty` is `null`: continue. Write the null with its reason (`commit_reason` or `dirty_reason`) in the `notes` of every .div and at the top of the report, as for dirty.
2. **Self-test.** Send the text of each .div in this skill's examples/ folder, unchanged, to `solve_div`. Each must come back `valid`, and the `results` in the returned `div` must equal the `results` stored in the file. Compare them with code when code execution is available, not by eye. If anything differs, stop and say which file and which results. If the examples/ folder can't be read, stop and say so. The examples are test files: what counts is that the results are the stored ones, whatever their verdict.

## Workflow

1. **Requirements.** Confirm them with the user once per board, and save them with that board's project:
   - the highest continuous input voltage (`v_input_max`: the board must survive it, and the Safe Max check runs at it), the touch voltage (`v_touch`) and the most negative input (`v_input_min`);
   - the logic sources' levels (`v_logic_high_min`, `v_logic_low_max`);
   - the required frequency (`f_required_hz`);
   - analog full scale and allowed error (`v_analog_fullscale`, `analog_error_allowed_pct`);
   - the temperature range;
   - the MCU pin type (`pin_type`);
   - for an input whose role includes a quadrature encoder, the encoder's resolution in lines per revolution, when it is known (see Quadrature encoder inputs);
   - the folder that holds the board's data sheets (see Rules).

   Give each input a role. A file holds one pair of logic levels: with several sources, the lowest high and the highest low. Inputs with different roles (analog and digital, say) get one .div each. When one node feeds several MCU pins, the weakest pin's limits go in the file.
2. **MCU.** Read the MCU data sheet and fill in the `mcu` section. The input thresholds follow the threshold basis (see Design basis).
3. **Resistors.** Propose the resistor specification and agree it with the user: value (E96 series), tolerance (1 % by default), power rating after derating to the check temperature, working voltage, package. Search for part numbers, through a distributor's parts search, only after the specification is agreed. `rating_mw` is the data-sheet rating as stated; the derating is the skill's own check, in the report.
4. **Diode.** Read the diode data sheet and write the `forward` and `reverse` tables. Temperature goes into the outer columns: `v_min` is the part that conducts most and `v_max` the part that conducts least, over the temperature range. For a Schottky those are the hot and the cold extremes, in both tables. A reverse table that describes leakage follows the leakage basis (see Design basis). The `note` says how each column was obtained, including any column the data sheet doesn't guarantee.
5. **Solve.** Write the .div and send it to `solve_div`. Correct whatever `problems` lists. Change R1 and R2 (E96 values) and solve again until every check is PASS. A TIGHT check is not the end while a PASS is reachable: keep changing R1 and R2. When a PASS is not reachable, report the TIGHT check as a choice for the user. After about five solves without progress, stop and report which check can't pass and the options. A trade-off the requirements don't settle is the user's choice. Hand over the `div` text exactly as `solve_div` returned it.
6. **Review.** The user opens the file in the app, compares the MCU and diode values with the data sheets, ticks "Checked against the data sheet" and adjusts any close values.
7. **Bench check.** Before a design is approved, the input is swept on a built board, at several voltages up to the highest input, and the measured pin voltage is compared with the typical curve. The chosen diode's leakage is measured hot, at the hot check temperature, and compared with the leakage basis.

## Design basis

- **Threshold basis.** When the MCU data sheet gives more than one pair of input thresholds for the pin, the design basis is the pair the data sheet guarantees by design for that pin: it goes in `vil_factor` and `vih_factor`. `mcu.note` says which pair was used, with its table and footnote, and how the data sheet qualifies each pair (tested in production, characterization, guaranteed by design). The other pair is solved as a what-if and shown in the report. With only one pair in the data sheet, use it and say so in `mcu.note`.
- **Leakage basis.** In a reverse table that describes leakage, the most-leaky column (`v_min`) is the data sheet's typical curve at the hot check temperature: this is the design basis. A worst case is a labeled what-if, never the design file: the data sheet's maximum at temperature when it gives one, otherwise the 25 C maximum scaled by the typical temperature rise (the typical curve's current hot over its current at 25 C, at the same voltage), with the arithmetic shown. `clamp_diode.note` says which basis each column uses.

## Quadrature encoder inputs

For an input whose role includes a quadrature encoder, the report has an Encoder section. All of its arithmetic is the skill's own and is shown in the report: each value, where it came from, the result. The values come from the `summary` of `solve_div` (the f_reliable, t_rise and t_fall rows under Information) and from the .div (`t_pulse_min_ns`, `margin_factor`).

- **No limit, or an old server.** If f_reliable has no value, there is no encoder frequency either: report why, as the summary says (its note, or Needs input). If f_reliable has a value but the summary has no t_rise and t_fall rows, stop and say the server needs updating.
- **Definitions,** stated in the report: one pulse is one full cycle on one channel; lines per revolution is pulses per revolution; counts are 4 per pulse.
- **A-to-B gap limit:** f_gap = 1 / (4 x (|t_rise - t_fall| + t_pulse_min_ns)), divided by `margin_factor` (times in seconds, so f_gap in Hz).
- **Encoder frequency per channel** = the lower of f_reliable and f_gap. Say which one set it.
- **Report:** the frequency per channel, pulses per second (the same number), counts per second (4 x frequency) and max RPM = 60 x frequency / lines per revolution.
- **Max RPM** uses the encoder resolution from the requirements when one is given. Otherwise print a table of max RPM for 500, 1000, 1024, 2048, 2500, 4096 and 5000 lines per revolution.
- **A specific source.** For a specific source (a known high and low level), solve a what-if copy with the input levels narrowed to that source (`v_logic_high_min` and `v_logic_low_max` set to its high and low levels) and report its encoder frequency, worked out the same way, next to the generic one. The copy is a what-if and is never written into the .div that is handed over.
- **Scope.** State that this is the input network's limit only, not the encoder's own output limit or the cable's.

## Rules

- **Every value in `results` comes from `solve_div`** and is shown as returned, never retyped: tables as `solve_div` returned them (`summary`), plots as `plot_div` drew them.
- **Nothing is guessed.** A value with no source is written as `null` and shows as "needs input". The example files show the layout of a .div; never take a value from them.
- **Data sheets come from the user.** Before reading any MCU or diode value, ask the user which folder holds the board's data sheets (once per board, saved with the requirements). Read a data sheet only from the user's copy in that folder or from a file attached to the chat. If the data sheet needed isn't there, stop: give the user a download link to the manufacturer's data sheet (document number and revision) and ask them to save it in that folder. Never read a data sheet through the web.
- **Every data-sheet value is cited** in the `source` and `note` of its section (document number, revision, table or figure), and the section is written with `checked: false`. Only the user ticks it, in the app.
- **Values from other documents.** If a value is available from a project document instead of the data sheet (curve readings or MCU limits recorded earlier, say), don't use it on your own: ask the user. If they agree, cite it in `source` and `note` as second-hand: the document, and the data sheet it came from.
- **No estimates.** A number the skill wants (the R1 needed for a check to pass, say) comes from solving trial values through `solve_div`, never from a hand or rough estimate.
- **What-ifs.** A trial with placeholder values is labeled as a what-if in the report, names every placeholder, and is never written into the .div that is handed over.
- **A check the solver doesn't make** (resistor derating at temperature, the board's minimum rail load) is reported as done by the skill or as not checked. Never as PASS. A check the skill makes shows its arithmetic in the report: which `solve_div` value, which rating or limit, the result.
- **Versions.** The skill version, the `solver_version` and the server's `commit` go in the `notes` of every .div and in the report.
- **The file.** Every key of the format is present, `null` for a blank; an unknown key is an error; `results` is written only by the solver. A diode table with no rows is `null` while it is still to be filled in, and `[]` only when that direction is left out on purpose, which the `note` then says.

## Report template

One report per .div, in this order. Where a section has nothing, write "none".

    SERVER DIRTY: true, commit <commit>            (first line; only when dirty is true)
    SERVER <commit or dirty>: null, <its reason>   (first line; only when commit or dirty is null)

    Design: <file name>: <the input and its role>
    Verdict: <verdict, as solve_div returned it>
    Skill <skill version>, solver <solver_version>, server commit <commit>, dirty <true, false or null>
    Self-test: the example files gave their stored results
    Basis: thresholds <the pair used, its table and how the data sheet qualifies it, or "the only pair">; leakage <the basis of each reverse column>

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
      <check>: done by the skill: <the solve_div value, the rating or limit, the arithmetic, the result in words>
      <check>: not checked

    Encoder                                        (only when the role includes a quadrature encoder)
      Definitions: one pulse is one full cycle on one channel; lines per revolution is pulses per revolution; counts are 4 per pulse
      f_reliable <from the summary>; t_rise, t_fall <from the summary>; t_pulse_min_ns, margin_factor <from the .div>
      f_gap = 1 / (4 x (|t_rise - t_fall| + t_pulse_min_ns)) / margin_factor = <the arithmetic, the result>
      Frequency per channel: <the lower of the two>, set by <f_reliable or f_gap>
      Pulses per second <the same number>; counts per second <4 x frequency>
      Max RPM: <60 x frequency / lines per revolution, or the table for 500 to 5000 lines per revolution>
      Specific source <its high and low levels>: <its frequency per channel, from the what-if below>, next to the generic <frequency per channel>
      This is the input network's limit only, not the encoder's own output limit or the cable's.

    What-ifs
      WHAT-IF: <the trial>; placeholders: <every placeholder value and what it stands in for>; <the result, as solve_div returned it>
      WHAT-IF other threshold pair: <the pair, its table and how the data sheet qualifies it>; <the result, as solve_div returned it>
      WHAT-IF worst-case leakage: <the data sheet's maximum at temperature, or the 25 C maximum scaled by the typical rise, with the arithmetic>; <the result, as solve_div returned it>
      WHAT-IF source <its high and low levels>: <the result, as solve_div returned it>; encoder frequency per channel <the arithmetic, the result>

    Needs input
      <key>: <why it has no source>

    Choices for the user
      <a trade-off the requirements don't settle, or a check that can't pass, with the options>

    Next
      Review in the app: compare the MCU and diode values with the data sheets, tick "Checked against the data sheet".
      Bench check on a built board, before the design is approved.
