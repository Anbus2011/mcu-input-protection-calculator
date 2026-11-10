# MCU Input Protection Calculator

A Python desktop application for designing and analyzing a resistor divider with one clamp diode in front of a microcontroller GPIO/ADC input. The clamp can be a Zener or a Schottky, connected to GND or to the VDD rail. The app checks the pin voltage against the MCU's limits, the logic levels, the power in each part, the analog error and the input frequency the pin can handle. Works with any MCU family — STM32, ESP32, PIC, AVR, and more.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)

---

## Circuit Topology

```
V_input ── R1 ──┬── R_series ──> MCU GPIO Pin
                │
                ├── clamp diode ── GND or VDD
                │
                └── R2 ── GND
```

| Component | Role |
|-----------|------|
| **R1** | Upper resistor (current limiting) |
| **R2** | Lower resistor (sets divider ratio) |
| **R_series** | Optional series resistor |
| **Clamp diode** | Limits the pin voltage. Zener to GND, Schottky to the VDD rail, or Schottky to GND |

---

## Features

- **Real-time calculation** - all outputs update as inputs change
- **Clamp diode from data-sheet points** - the diode is described by two tables (forward and reverse) of current against voltage, minimum / typical / maximum, so a Zener and a Schottky are handled the same way
- **Worst case from all corners** - R1 min/max × R2 min/max × diode minimum/maximum column; the lowest or highest is used as each check requires
- **Checks with one verdict** - pin voltage against Safe Max, Absolute Max and Pin Min, logic levels, power in every part, analog range and error, required frequency
- **Signal bandwidth in two numbers** - "may work up to" and "reliable up to"
- **Interactive plot** - V_mcu vs V_input with the typical, lowest and highest traces, the band between them, and the VIH / VIL levels; dark/light theme toggle
- **`.div` files, format 2.0** - JSON; holds every input, the part data with its source, and the calculated results
- **Command-line checker** - `divcheck.py` validates and solves a `.div` file with the same calculation, without the GUI packages
- **No hidden defaults** - blank inputs stay blank; results that need them say "needs input"
- **Color-coded status indicators** - green / orange / red throughout the tables

---

## Requirements

- **Python 3.10** or newer

### Python Packages

| Package | Purpose |
|---------|---------|
| `customtkinter` | Modern dark-themed GUI framework |
| `matplotlib` | Embedded plotting (V_mcu vs V_input chart) |
| `numpy` | Required by matplotlib |
| `pillow` | Image processing support |
| `pytest` | Running the test suite |
| `mcp` | The MCP server (`skill/server.py`) and its tests: 1.26.0 or newer, below 2 |

The test suite needs all of them, the tests that don't open a window included. Only the UI tests also need a desktop session.

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/Anbus2011/mcu-input-protection-calculator.git
cd mcu-input-protection-calculator
```

### 2. (Optional) Create a virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

Or install manually:

```bash
pip install customtkinter matplotlib numpy pillow pytest "mcp>=1.26.0,<2"
```

### 4. Run the application

```bash
python main.py
```

Then **Load Design...** and open one of the files in `examples/`.

### VS Code Users

A launch configuration is included. Open the project folder in VS Code, then press **F5** to run and debug. Make sure the **Python** and **Python Debugger** extensions are installed.

---

## Usage Guide

### Application Layout

The window is split into two panels:

- **Left panel** (scrollable) - all input parameters
- **Right panel** - the overall verdict, an input report line, the output tabs and the plot

Most fields and table headers have a **?** at the right. Hold the pointer on it for about half a second and a tooltip appears beside the pointer, never under it. One tooltip is shown at a time. It goes when the pointer leaves, and on a click, a scroll, a change of tab, a move or resize of the window, or when the app loses focus.

### No Hidden Defaults

The app starts with a blank design, and **New Design** gives a blank design. Nothing is ever filled in behind your back:

- A blank field stays blank. Every result that needs it shows **needs input**, and the report line above the tabs lists the fields that are needed (for example `Needs input: R1 value, VDD/VDDA`).
- Results that don't depend on a blank field are still calculated.
- Text that isn't a valid number, or a value that can't be used (negative resistance, tolerance outside 0 to below 100 %, table rows out of order, a rating of 0, ...), is listed as `Fix: <field>: <reason>`, and results that depend on it show **needs input**.
- Unreadable text blocks Save until it's fixed or cleared; the error names the field.
- The only values the app fills in itself are visible ones: the two Signal Bandwidth starting values (see [Starting Values](#starting-values)). A new design also shows kΩ / kΩ / Ω in the unit selectors.
- Every clamp diode and MCU value comes from the `.div` file or from typing it in.

### Input Panels

The labels, the value fields and the "?" buttons of all the panels line up.

#### Resistors

One row each for R1, R2 and the optional R_series:

| Column | Description |
|--------|-------------|
| Value, Unit | Resistance, in Ω, kΩ or MΩ |
| Rating (mW) | Power rating, used for the power margins |
| Tol. (%) | Tolerance, used for the worst case |

R_series blank or 0 means there is no series resistor; its unit, rating and tolerance are then not needed, and the R_s row of the power table shows "no R_s". When R_series is above 0 all three are needed.

#### Clamp Diode

| Field | Description |
|-------|-------------|
| Part | Part name |
| Type | `zener` or `schottky`. A label only: the calculation uses the connection and the tables, whatever the type |
| Connection | Where the anode and the cathode are connected: `node` (the junction of R1 and R2), `gnd` or `vdd`. Exactly one of the two is `node` |
| Capacitance | Diode capacitance (pF), used for the Signal Bandwidth time constant |
| Ptot | Power rating (mW) |
| Forward / Reverse | The two tables, see below |
| Source | One line: data sheet, revision, tables or figures used |
| Note | How each column of the tables was obtained |
| Checked against the data sheet | Tick it once you have compared the values with the data sheet. Editing any value of the diode afterwards (a table cell included) unticks it; editing Part, Source or Note does not |

The usual connections:

| Clamp | Anode | Cathode |
|-------|-------|---------|
| Zener to GND | `gnd` | `node` |
| Schottky to the VDD rail | `node` | `vdd` |
| Schottky to GND (negative inputs) | `gnd` | `node` |

**The tables.** *Forward* describes the diode with its anode positive; *Reverse* with its cathode positive (the working direction of a Zener, the leakage direction of a Schottky). Each row is a current (mA) and the voltage across the diode at that current: minimum, typical and maximum. Reverse values are entered as positive numbers.

- Rows go in ascending current, and each voltage column rises from row to row.
- In every row V min ≤ V typ ≤ V max.
- **+ Add row** (under the table) adds a blank row; **×** deletes a row. A table with rows needs at least two.

Each table is in one of three states, and the panel says which:

| State | Shown as | Meaning |
|-------|----------|---------|
| Blank | "Not filled in: needs input" | Nothing has been entered yet. The table is listed under `Needs input` and the results that use it wait for it. A new design starts here. |
| Not modelled | "Not modelled: current taken as zero" | There is no data for this direction and it is left out on purpose. |
| Rows | the table | The data-sheet points. |

The **Not modelled** box next to "+ Add row" switches a table with no rows between blank and not modelled. Adding a row turns either into rows; deleting the last row returns the table to blank.

Between two rows, ln(current) is taken as linear in voltage; below the first row and above the last, the nearest segment is extended. So enter rows over the whole range of currents the design can reach. V min is the part that conducts most and V max the part that conducts least; fold temperature extremes into those two columns.

#### MCU Pin Input Limits

| Parameter | Description | Usually found in the MCU data sheet under |
|-----------|-------------|-------------------------------------------|
| Part, Pin type | Part name and a label for the kind of pin (for example "5 V tolerant") | Pin descriptions |
| VDD/VDDA | MCU supply voltage; also the ADC reference (VREF) and the voltage of the rail when the diode is connected to `vdd` | Your design's supply, within the operating conditions |
| Safe Max | Highest pin voltage in normal operation. Its check is the guard against current into the pin's protection structures | Operating conditions (pin input voltage), for the pin type used |
| Abs. Max | Absolute maximum pin voltage (damage threshold) | Absolute maximum ratings |
| Pin Min | Lowest allowed pin voltage, 0 or negative | Absolute maximum ratings |
| ADC bits | ADC resolution N | ADC characteristics |
| VIL factor | Pin input-low threshold as a fraction of VDD | I/O static characteristics, for the pin type used |
| VIH factor | Pin input-high threshold as a fraction of VDD | I/O static characteristics, for the pin type used |
| C_pin | Pin capacitance (pF) | I/O static characteristics |
| Min pulse width | Shortest pulse the input peripheral accepts (ns) | Timer input characteristics |
| Source, Note, Checked | As for the clamp diode: editing any MCU value unticks "Checked" | |

The two files in `examples/` each hold a complete worked set of these values, with the data sheet and the tables they came from in `source` and `note`.

#### System Requirements

| Parameter | Description |
|-----------|-------------|
| Max Input | Maximum signal voltage at the divider input |
| Min Input | Optional. Lowest input voltage; when negative, the pin is checked against Pin Min |
| ADC Scale | Optional. Input voltage that maps to ADC full scale |
| Allowed error | Optional. Allowed analog error at ADC Scale, in percent |
| Logic High | Minimum input voltage that must read as logic high |
| Logic Low | Maximum input voltage that must read as logic low |
| Touch voltage | Optional. A voltage the input may touch (for example 60 V); gives information rows only |
| Required freq. | Optional. Input frequency the pin must handle |

An optional value left blank leaves its check out.

#### Design Notes

Free-form text area for annotations. Saved with the `.div` file.

### Overall Verdict

The line above the tabs shows the worst status among all the checks: **FAIL**, else **needs input**, else **TIGHT**, else **PASS**. When it is FAIL or TIGHT it names the checks concerned.

### Output Tabs

V_mcuL and V_mcuH are the lowest and the highest pin voltage over all eight corners: R1 min or max × R2 min or max × the diode's minimum or maximum column.

#### Tab 1: Component Analysis

The tab scrolls, so that the plot under it keeps its height.

- **Divider Network** - input impedance, divider ratio, ADC source impedance (R1∥R2 + R_s), total typical power dissipation (R1 + R2 + clamp diode)
- **Component Power** - for R1, R2, the clamp diode and R_s at max input: typical current, typical power, worst-case power, rating, and margin % against both the typical and the worst-case power
- **Power verdict (worst case)** - the worst status of the parts
- **Voltage at MCU Pin (nominal R1/R2)** - "Typical clamp diode" (typical column) and "Worst clamp diode (nominal R)" (maximum column) at maximum input voltage, with R1 and R2 at their nominal values. This is not the full worst case: that is V_mcuH on the MCU Input tab (the Zener example shows 3.235 V here and 3.239 V there).

Typical power uses nominal resistors and the diode's typical column. Worst-case power is the highest value over the eight corners plus the typical point, taken separately for each part.

R_s power takes the pin as held at 0 V, so the whole node voltage is across R_s: typical V² / R_s, worst case (highest node voltage)² / R_s at its low tolerance.

A blank rating shows **needs input** in both margin cells. The worst-case margin is the verdict for every part; the typical margin is shown for information only (no tick or cross).

Margin indicators (worst-case margin column and the power verdict):
- **Green** (> 20% margin) - safe
- **Orange** (0-20% margin) - tight
- **Red** (no margin) - exceeds rating

#### Tab 2: MCU Input

- **Voltage Limits** - at Max Input, V_mcuH against Safe Max and Absolute Max; at a negative Min Input, V_mcuL against Pin Min. Margin in mV and status. Safe Max is the guard against current into the pin's protection structures.
- **ADC Performance** - source impedance and resolution in mV/LSB (VREF / 2^N referred to the divider input)
- **Analog Error** - at ADC Scale with nominal resistors: the pin voltage with the diode minus the pin voltage without it, in mV, percent and LSB. It has a status only when an allowed error is given.
- **Information (no verdict)** - at the Touch voltage: highest pin voltage, clamp diode current and R1 power; and the current into the VDD rail at Max Input when the diode is connected to VDD

#### Tab 3: Input Levels

The MCU pin voltage at each input level, as **V_mcuL** and **V_mcuH**:

| Level | Check |
|-------|-------|
| Min Input | When negative: V_mcuL must not be below Pin Min |
| 0V | Zero reference |
| Logic Low | V_mcuH must be below VIL (VIL factor x VDD) |
| Logic High | V_mcuL must be above VIH (VIH factor x VDD) |
| ADC Scale | V_mcuH must not exceed VDD |
| Max Input | V_mcuH against Safe Max and Absolute Max. Both limits are shown ("≤ 3.60 V safe / ≤ 4.00 V abs") and the status is the worse of the two, so the row agrees with the overall verdict |
| Touch | Information only |

The value a row is judged on is in bold; rows with no check (0V, Touch, a Min Input that is not negative) have nothing in bold. Rows whose input is not given show "--".

If no pin voltage can be found at a level, the report line says "did not settle" and names the input levels affected; those voltages are not reliable.

#### Tab 4: Signal Bandwidth

Answers one question: what input frequency can this pin handle, for uses such as pulse inputs and encoders? It is the frequency at the pin (per channel for an encoder), at 50 % duty.

- **May work up to** = 1 / (2 × (edge time + minimum pulse width))
- **Reliable up to** = "may work up to" ÷ margin factor
- **Required** (when a required frequency is given in the System panel): PASS at or below "reliable", TIGHT between the two, FAIL above "may work". It is also FAIL when the pin never reads high or low
- **Details** opens the values behind the numbers: time constant, total capacitance, the two edge times and the shortest usable pulse (edge time + minimum pulse width)

How the edge time is found:

- τ = (R1 max ∥ R2 max + R_s max) × (C_diode + C_pin + C_stray)
- An edge from pin level A towards level B crosses threshold T after τ × ln((B − A) / (B − T))
- Rising edge: from 0 V towards V_mcuL at Logic High, to VIH
- Falling edge: from V_mcuH at Max Input towards V_mcuH at Logic Low, to VIL
- The edge time is the longer of the two

If the pin never gets above VIH at the Logic High input (or below VIL at Logic Low), the tab says so and shows no limits.

Entered on the tab: **C_stray** (PCB estimate) and the **margin factor**. Both start from visible starting values (see [Starting Values](#starting-values)). **Fill from starting values** puts the starting value back into a blank or unreadable field and leaves the others alone. C_diode is the clamp diode's capacitance; C_pin and the minimum pulse width are in the MCU panel.

### Plot

The bottom of the right panel shows **V_mcu vs V_input**, from 0 V (or a negative Min Input) to Max Input:

- **Cyan line** - typical V_mcu (nominal resistors, typical diode column)
- **Orange line** - V_mcuH
- **Violet line** - V_mcuL
- **Shaded band** - between V_mcuL and V_mcuH: where the pin voltage can lie
- **Red dashed** - Absolute Max threshold
- **Gold dashed** - Safe Max threshold
- **Green dashed** - VDD threshold
- **Thin pink lines** - VIH (dash-dot) and VIL (dotted), each named at its right end. Where the V_mcuL curve is under the VIH line, the input does not read high

The legend is to the right of the plot area, so it never covers a curve, and lists the lines in this order. The plot is at least 350 px high in a 1400×900 window, whichever tab is open.

Each curve and line is drawn only when its inputs are present; V_mcuL, V_mcuH and the band need the tolerances and both outer diode columns. When no curve can be calculated, the plot is cleared and says which inputs are needed. The curves and the tables come from the same calculation, so they agree.

If no pin voltage can be found at some points of a curve, the report line says "Clamp diode solver did not settle at N plot point(s). The curve is not reliable there." N counts plot points, each once.

Use the **Theme** dropdown to switch between Dark and Light plot styles.

### File Operations

| Action | Shortcut | Description |
|--------|----------|-------------|
| New | Ctrl+N | Blank design (the two bandwidth fields get their starting values) |
| Open | Ctrl+O | Load a `.div` file |
| Save | Ctrl+S | Save to current file |
| Save As | Ctrl+Shift+S | Save to a new file |

The title bar shows the current filename and an asterisk (*) when there are unsaved changes. Any edit to any input (typing, paste, cut, delete, the notes, a checkbox, a selector, a table cell, adding or deleting a table row) marks the design unsaved. The application prompts to save before closing, opening, or creating a new file.

- Saving writes a temporary file and then replaces the target, so a failed save never truncates the existing file. Save and Save As both report a failure. The calculated results are saved with the design.
- Opening checks the whole file first. Every format problem (wrong type, missing or unknown key, or a unit, terminal or diode type that is not an allowed value) is listed with its key path, and the current design is left exactly as it was.
- A value that is readable but can't be used (out of range, table rows out of order) still opens; it is listed after `Fix:`.
- `null` values load blank; one warning lists those the results need.
- Stored results are ignored when a file is opened: the design is solved again.
- A file that is opened and saved without editing gets every input back exactly as it was written (`10` stays `10`, `10.0` stays `10.0`, `null` stays `null`). A value you edit is written as you entered it. Only `results` can change.

---

## File Format

Designs are saved as `.div` files: JSON, format 2.0. The format is described in **[docs/div_v2_format.md](docs/div_v2_format.md)**, and two complete files are in `examples/`:

- `examples/zener_gnd_bzb984_c3v3.div` - Zener to GND
- `examples/schottky_rail_bat54cv.div` - Schottky to the VDD rail

In short: every key must be present, `null` means blank, unknown keys are errors, and `results` is written by the app and the checker.

### Command-Line Checker

```bash
python divcheck.py in.div [out.div] [--json out.json]
```

Validates the file, solves it with the same calculation the app uses, and prints a summary. With `out.div` it writes the file back with `results` filled in; with `--json` it writes the results alone. Exit code 0: valid and solved, whatever the statuses. 1: invalid, with every problem listed (the value problems that the app opens and lists after `Fix:` included). 2: a file could not be read or written. It needs only a plain Python install.

The summary tells a blank diode table from one that is not modelled: "Forward table not filled in: needs input" against "No forward data: forward conduction is not modelled" (and the same for the reverse table).

---

## MCP Server

`skill/server.py` is an [MCP](https://modelcontextprotocol.io) server that lets a Claude chat use the solver. Claude sends the text of a `.div` file and gets back the results and a plot. The server is a gateway only: it validates and solves with the same code as `divcheck.py`, so it gives the same results. It does no math of its own, chooses no values and reads or writes no design files.

| Tool | What it returns |
|------|-----------------|
| `solver_info` | The solver version, the `.div` format version, the git commit the server is running, and `dirty`: whether its folder had uncommitted changes when it started (with the reason when git can't give the commit or `dirty`) |
| `solve_div` | Whether the file is valid, every problem as `key.path: message`, the file's text with `results` filled in, and the summary `divcheck.py` prints |
| `plot_div` | A PNG of pin voltage against input voltage: typical, lowest and highest of the eight corners, with VIL, VIH and the pin limits. It is the same sweep as the app's plot |

All three are read-only and take the `.div` as JSON text, not a file path, so the server can run on another machine. An invalid file is a normal answer (`valid` false and the problems), not an error. Every answer carries the solver version, the commit and `dirty`.

The server needs the `mcp` package (in `requirements.txt`; Python 3.10 or newer, `mcp` 1.x) and `matplotlib` for the plot. It does not use `customtkinter`.

### Running it

The server runs over stdio: Claude Desktop starts it from the registration entry below and stops it again, so there is nothing to start by hand.

```bash
python skill/server.py            # stdio: what the registration entry runs
```

`--http` is an optional switch, kept only for a later move to a dedicated server. It serves streamable HTTP at `http://127.0.0.1:8000/mcp`; `--host` and `--port` change the address and the port. The HTTP form has no login.

```bash
python skill/server.py --http
```

`skill/examples/` holds copies of the two files in `examples/` for the skill's self-test: before designing, the skill solves both through `solve_div` and stops if the results differ from the stored ones. A test keeps the copies identical to `examples/`.

### Registering it in Claude Desktop

Add the server to `claude_desktop_config.json` (Claude Desktop: Settings > Developer > Edit Config), then restart Claude Desktop:

```json
{
  "mcpServers": {
    "mcu-input-calculator": {
      "command": "C:\\path\\to\\python.exe",
      "args": ["C:\\path\\to\\mcu-input-protection-calculator\\skill\\server.py"]
    }
  }
}
```

Use full paths: the Python that has the packages of `requirements.txt` installed, and `skill/server.py` in this folder. If the file already has an `mcpServers` section, add the `mcu-input-calculator` entry to it.

---

## The Skill

`skill/SKILL.md` is the Claude skill that designs the protection network for one input and writes its `.div`. It holds the workflow from requirements to bench check, the rules and the report template. It does no math: every result comes from the MCP server above, so the server must be registered in Claude Desktop as well. `skill/SKILL.md` is the master copy: change it there, never in the copy installed in Claude.

`SKILL.md` states its own version and the solver version it was written and tested for. At the start of every session the skill calls `solver_info` and stops if the server runs another solver version. It then solves its copies of the two example files through `solve_div` and stops if the results differ from the stored ones. A test fails if the solver version in `SKILL.md` is not the solver's, or if `SKILL.md` names a tool or a field the server does not have.

### Building the package

```bash
python skill/build_package.py
```

This writes `dist/mcu-input-protection.zip` and prints its path and contents. The zip holds one folder, `mcu-input-protection/` (the `name` in the front matter of `SKILL.md`), with `SKILL.md` and `examples/` (the two `.div` copies) and nothing else: the server is not in the package, it runs from this folder. `dist/` is in `.gitignore`, so the package is built, not committed. To write it somewhere else, give the folder: `python skill/build_package.py some/folder`.

### Installing it in Claude Desktop

Upload the zip in Claude Desktop's skill settings (Settings > Capabilities > Skills) and switch the skill on. After any change to `skill/SKILL.md` or to the example files, build the package and upload it again.

---

## Project Structure

```
mcu-input-protection-calculator/
├── main.py                       # Application entry point
├── divcheck.py                   # Command-line checker for .div files
├── requirements.txt              # Python dependencies
├── pytest.ini                    # Registers the "ui" test marker
├── README.md
├── CLAUDE.md                     # Rules for AI assistants working on the code
├── LICENSE                       # MIT
│
├── docs/
│   ├── div_v2_format.md          # The .div format 2.0
│   ├── project_guide.md          # What the app and the skill do, and the workflow
│   ├── bzb984_fig7_typical.json  # Graph readings behind the Zener example's table (read by the tests)
│   └── bat54cv_fig1_fig2_typical.json   # Graph readings behind the Schottky example's tables
├── examples/                     # Two example designs (format 2.0)
│
├── skill/
│   ├── SKILL.md                  # The Claude skill: workflow, rules, report template
│   ├── build_package.py          # Builds the skill package for Claude Desktop into dist/
│   ├── server.py                 # MCP server: solves and plots a .div for a Claude chat
│   ├── plot_png.py               # Headless PNG of the plot, for the server
│   └── examples/                 # Copies of examples/, for the skill's self-test
│
├── src/
│   ├── core/
│   │   ├── constants.py          # Bandwidth starting values, units
│   │   ├── div_format.py         # .div format 2.0: structure, validation, read / write
│   │   └── app_state.py          # Controller: field parsing, file I/O, dirty tracking, plot sweep
│   │
│   ├── models/
│   │   └── clamp_solver.py       # The solver (standard library only, no UI)
│   │
│   └── ui/
│       ├── main_window.py        # Top-level window, toolbar, layout
│       ├── input_panels.py       # Resistor, Clamp Diode, MCU, System, Bandwidth input panels
│       ├── output_panels.py      # Component, MCU Input, Input Levels, Signal Bandwidth tabs
│       └── plot_canvas.py        # Matplotlib V_mcu vs V_input chart
│
├── tests/                        # pytest suite (python -m pytest tests/ -v)
│   ├── designs.py                # Shared test designs
│   └── test_*.py                 # The tests
│
└── .vscode/
    └── launch.json               # VS Code debug configuration
```

`datasheets/` (data-sheet PDFs), `docs/screenshots/` and `dist/` (the built skill package) are local only: they are listed in `.gitignore` and are not in git.

### Architecture

The application follows a **Model-View-Controller** pattern:

- **Model** (`src/models/clamp_solver.py`) is the one solver. `solve(design)` takes the design as a dict in the layout of a `.div` file and returns the results as a dict. Any value may be `None` (blank); each result is calculated only when its inputs are present, and the missing inputs are reported per result. The pin voltage is found by bisection on the node equation (current through R1 = current through R2 + diode current). The app, `divcheck.py` and the tests all call this solver.
- **View** (`src/ui/`) contains all CustomTkinter widgets. Every input is bound to a Tk variable whose trace forwards the raw text to the controller. Output panels display the solver's results; they don't parse or calculate.
- **Controller** (`src/core/app_state.py`) owns the text of every field and table cell, parses it, builds the design dict, calls the solver, sweeps the solver over the input range for the plot (the typical curve from its pin-voltage function, the lowest and the highest from its eight corners, solved once per point), and dispatches results back to the view via callbacks.

---

## Starting Values

A new design shows two values in the Signal Bandwidth fields, and **Fill from starting values** puts them back. They are set in `BANDWIDTH_STARTING_VALUES` in `src/core/constants.py`, each with a one-line source note:

| Field | Starting value | Source |
|-------|----------------|--------|
| C_stray | 3 pF | Estimate for a short PCB trace (2-5 pF typical); no data-sheet source |
| Margin factor | 1.5 | 1.5 MHz "may work" gives 1 MHz "reliable" |

Everything else about a part (diode tables, capacitance, MCU limits, pin capacitance, minimum pulse width) is entered per design and saved in the `.div` file. To use a different diode or MCU, enter its data-sheet values or open a file that has them; there is nothing to add to the source code.

**Where to find the values:**

| Value | Where to Find |
|-------|---------------|
| Reverse table of a Zener | "Working voltage against current" figure (typical); VZ min / max at the test current from the characteristics table |
| Forward table of a Schottky | Maximum VF at several currents from the characteristics table; typical from the "forward current against forward voltage" figure |
| Reverse table of a Schottky | "Reverse current against reverse voltage" figure and the maximum IR |
| Capacitance | Diode data sheet, "diode capacitance" at 0 V or the maximum |
| Safe Max, Abs. Max, Pin Min | MCU data sheet: general operating conditions and absolute maximum ratings, for the pin type used |
| C_pin | MCU data sheet, I/O static characteristics (CIO) |
| Min pulse width | MCU data sheet, timer or external-interrupt input characteristics |

---

## Running the Tests

```bash
python -m pytest tests/ -v
```

All 910 tests must pass. `tests/test_ui.py` drives the real window (withdrawn, and shown for three layout tests), so it needs a desktop session and takes a little over three minutes. Its tests carry the marker `ui`; to run the rest in about 35 seconds:

```bash
python -m pytest tests/ -m "not ui"
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError: No module named 'customtkinter'` | Run `pip install -r requirements.txt` |
| F5 does nothing in VS Code | Install the **Python** and **Python Debugger** extensions, then ensure `main.py` is the active file |
| Window appears but is blank | Try resizing the window, or check the terminal for error messages |
| `.div` file won't open | The error lists every problem with its key path (for example `resistors.r1.unit`). Fix them in a text editor, or run `python divcheck.py file.div`; units must be Ω, kΩ or MΩ |
| "this is a format 1.0 file" | The file was saved by an older version. Format 1.0 is not read and there is no converter: enter the design again with the clamp diode's data-sheet tables |
| Plot doesn't render | Verify `matplotlib` and `numpy` are installed: `pip show matplotlib numpy` |
