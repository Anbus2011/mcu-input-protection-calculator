# MCU Input Protection Calculator

A Python desktop application for designing and analyzing voltage divider circuits with Zener clamp protection for microcontroller GPIO/ADC inputs. Calculates safe operating margins when interfacing external signals with MCU pins. Works with any MCU family — STM32, ESP32, PIC, AVR, and more.

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)

---

## Circuit Topology

```
V_input (0-30V) ──┬── R1 ──┬── R_series ──> MCU GPIO Pin
                  │        │
                  │        ├── Zener (cathode)
                  │        │
                  └── R2 ──┴── GND
```

| Component | Role |
|-----------|------|
| **R1** | Upper resistor (current limiting) |
| **R2** | Lower resistor (sets divider ratio) |
| **R_series** | Optional series resistor for additional protection |
| **Zener** | Clamps voltage to protect the MCU pin (e.g., BZB984 series) |

---

## Features

- **Real-time calculation** - all outputs update instantly as inputs change
- **Tolerance worst-case analysis** - combines resistor tolerances with Zener worst-case voltages
- **Iterative Zener model** - non-linear 3-region V-I characteristic (knee, linear, saturation)
- **Safety margin analysis** - checks against MCU recommended max, absolute max, and injection current limits
- **Signal bandwidth / PPS analysis** - determines maximum pulse frequency through the protection network
- **Interactive plot** - V_mcu vs V_input with typical and worst-case traces, dark/light theme toggle
- **File save/load** - JSON-based `.div` format preserves complete design state; atomic saves, validated loads
- **No hidden defaults** - blank inputs stay blank; results that need them say "needs input"
- **Built-in Zener presets** - BZB984 series (Nexperia) with full datasheet parameters
- **ADC sample time lookup** - automatic minimum sample cycle recommendation (STM32G4)
- **Color-coded status indicators** - green/orange/red pass/fail throughout all tables

---

## Requirements

- **Python 3.9** or newer

### Python Packages

| Package | Purpose |
|---------|---------|
| `customtkinter` | Modern dark-themed GUI framework |
| `matplotlib` | Embedded plotting (V_mcu vs V_input chart) |
| `numpy` | Numerical arrays for plot data generation |
| `pillow` | Image processing support |

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/Resistor_Calculator.git
cd Resistor_Calculator
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
pip install customtkinter matplotlib numpy pillow
```

### 4. Run the application

```bash
python main.py
```

### VS Code Users

A launch configuration is included. Open the project folder in VS Code, then press **F5** to run and debug. Make sure the **Python** and **Python Debugger** extensions are installed.

---

## Usage Guide

### Application Layout

The window is split into two panels:

- **Left panel** (scrollable) - all input parameters
- **Right panel** - an input report line, the output tabs and the plot

### No Hidden Defaults

The app starts with a blank design, and **New Design** gives a blank design. Nothing is ever filled in behind your back:

- A blank field stays blank. Every result that needs it shows **needs input**, and the report line above the tabs lists the fields that are needed (for example `Needs input: R1 value, VDD/VDDA`).
- Results that don't depend on a blank field are still calculated.
- Text that isn't a valid number, or a value out of range (negative resistance, tolerance outside 0 to below 100 %, VZ min > VZ nom > VZ max, IZK not below IZT, a rating or Ptot of 0, ...), is listed as `Fix: <field>: <reason>`, and results that depend on it show **needs input**.
- Unreadable text blocks Save until it's fixed or cleared; the error names the field.
- The only values the app fills in itself are visible ones: the Signal Bandwidth starting values (see below) and the values of a Zener preset you pick. A new design also shows kΩ / kΩ / Ω in the unit selectors.

### Input Panels

#### Resistors

Enter values for R1, R2, and the optional R_series. Each resistor has:
- **Value** with unit selector (Ω, kΩ or MΩ)
- **Power rating** (mW) - used to calculate margin percentage
- **Tolerance** (%) - used for worst-case analysis

R_series blank or 0 means there is no series resistor; its unit, rating and tolerance are then not needed, and the R_s row of the power table shows "no R_s". When R_series is above 0 all three are needed: the rating for the R_s power margins, the tolerance for the worst-case R_s power and for the injection estimate (which uses R_s at its low tolerance).

#### Zener Diode

Select a preset from the dropdown. The BZB984 series presets (Nexperia BZB984 datasheet Rev 3, Table 8) are built in:

| Preset | VZ_nom |
|--------|--------|
| BZB984-C3V0 | 3.0V |
| BZB984-C3V3 | 3.3V |
| BZB984-C3V6 | 3.6V |
| BZB984-C3V9 | 3.9V |
| BZB984-C4V3 | 4.3V |
| BZB984-C4V7 | 4.7V |
| BZB984-C5V1 | 5.1V |
| BZB984-C5V6 | 5.6V |
| BZB984-C6V2 | 6.2V |

Each preset fills: VZ (nom/min/max), IZT, IZK, ZZT (typ/max), ZZK (typ/max), and Ptot. ZZK is **reference only, not used in the calculation** (the panel says so); it can be left blank. VZ min is used only for the worst-case power (low-voltage corner). As soon as any value differs from the preset, the selector shows **Custom** with "modified from <preset>", and the design is saved as `"preset": "Custom"` with `"preset_base": "<preset>"`. Changing the value back shows the preset again. Choosing **Custom** keeps the values that are in the fields.

#### MCU Pin Input Limits

| Parameter | Description |
|-----------|-------------|
| VDD/VDDA | MCU supply voltage; also used as the ADC reference (VREF) |
| Safe Max | Recommended maximum (VDDA + 0.3V) |
| Abs. Max | Absolute maximum (damage threshold) |
| Injection Limit | Maximum safe ESD clamp current |
| ADC bits | ADC resolution N (STM32G4: 12) |
| VIL factor | Pin input-low threshold as a fraction of VDD (STM32G4: 0.3, DS12983 Rev 5, Table 54) |
| VIH factor | Pin input-high threshold as a fraction of VDD (STM32G4: 0.7, DS12983 Rev 5, Table 54) |

#### System Requirements

| Parameter | Description |
|-----------|-------------|
| Max Input | Maximum signal voltage at the divider input |
| ADC Scale | External voltage that maps to ADC full scale |
| Logic High | Minimum input voltage that must read as logic high |
| Logic Low | Maximum input voltage that must read as logic low |

#### Design Notes

Free-form text area for annotations. Saved with the `.div` file.

### Output Tabs

#### Tab 1: Component Analysis

- **Divider Network** - input impedance, divider ratio, ADC source impedance (R1∥R2 + R_s), total typical power dissipation (R1 + R2 + Zener)
- **Component Power** - for R1, R2, the Zener and R_s at max input: typical current, typical power, worst-case power, rating, and margin % against both the typical and the worst-case power
- **Voltage at MCU Pin** - typical and worst-case V_mcu at maximum input voltage

Typical power uses nominal resistors and the typical Zener (VZ nom). Worst-case power is the highest value over these corners, taken separately for each part:

- R1 at min or max tolerance x R2 at min or max tolerance x the Zener at **VZ min** (low-voltage corner: knee 0.94 x VZ min, ZZT typ) or **VZ max** (high-voltage corner: knee 0.97 x VZ max, ZZT max) - eight corners - plus the typical point;
- R_s: the estimated injection current at the worst-case pin voltage (V_mcuH), with R_s anywhere in its tolerance band (the maximum of I^2 x R_s is at an end of the band, or at 100 Ω if that lies inside it).

A blank rating shows **needs input** in both margin cells.

Margin indicators:
- **Green** (> 20% margin) - safe
- **Orange** (0-20% margin) - tight
- **Red** (negative margin) - exceeds rating

#### Tab 2: MCU Input

- **Voltage Limits** - V_mcu vs Safe Max and Absolute Max with margin in mV and pass/fail status
- **Injection Current (estimate)** - I_inj = max(0, V_mcuH - (VDD + 0.3 V)) / (R_s min + 100 Ω), where R_s min is R_s at its low tolerance (0 when there is no R_s) and 100 Ω stands for the internal ESD path. It is a rough model: on STM32G4 FT/TT pins positive injection is not possible at all (DS12983 Rev 5, Table 15, note 3). The reference design gives 0 mA.
- **ADC Performance** - source impedance, recommended minimum sample cycles (STM32G4), and resolution in mV/LSB (VREF / 2^N referred to the divider input)

#### Tab 3: Input Levels

Operating point table showing the MCU pin voltage at five key input levels:

| Level | Check |
|-------|-------|
| 0V | Zero reference |
| Logic Low | V_mcuH must be below VIL (VIL factor x VDD) |
| Logic High | V_mcuL must be above VIH (VIH factor x VDD) |
| ADC Scale | V_mcu must not exceed VDD |
| Max Input | V_mcu must not exceed Absolute Max |

Each row shows both **V_mcuL** (lowest, from R1 high / R2 low / typical Zener) and **V_mcuH** (highest, from R1 low / R2 high / worst Zener).

The pin voltage is solved by bisection between 0 V and the unclamped divider voltage, to 1 µV, on the Zener V-I curve of CLAUDE.md §4B. Low-value dividers (for example R1 = R2 = 100 Ω) converge too. If the bisection can't bracket a solution, the report line says "did not settle" and names the input levels affected.

Known limitation: §4B treats the clamp as ineffective below 0.5 mA and caps the voltage at VZ there. The curve therefore follows the divider up to VZ, stays flat at VZ, and then drops to the knee voltage where the Zener current reaches 0.5 mA: by about 0.2 V on the typical curve (3.300 V to 3.102 V at 9.75 V in for the reference 10 kΩ / 18 kΩ / BZB984-C3V3 design) and about 0.1 V on the worst-case curve (3.500 V to 3.395 V at 10.12 V in). An input level that sits right at that point can land on either side of the step.

#### Tab 4: Signal Bandwidth

Analyzes the RC low-pass filter formed by the protection network to determine the maximum signal frequency the MCU pin can reliably detect.

Shown read-only, derived from the other panels:

- **τ resistance** = R1∥R2 + R_series
- **VIL** = VIL factor x VDD, **VIH** = VIH factor x VDD
- **V_high** = the lowest solved pin voltage at the Logic High input (R1 max, R2 min, typical Zener)

Entered on the tab:

- **C_diode** (junction capacitance at 0 V), **C_pin** (GPIO capacitance), **C_stray** (PCB estimate)
- **Peripheral clock** and **digital filter samples** for digital sampling limit
- **Counter width**, **signedness**, and **firmware read rate** for overflow limit

These fields start from visible starting values (see `BANDWIDTH_STARTING_VALUES` below). **Fill from starting values** puts the starting value back into any blank or unreadable bandwidth field and leaves the others alone.

Results show four frequency limits and the effective maximum PPS:

| Limit | Formula |
|-------|---------|
| Analog (conservative) | 1 / (10 x tau) |
| Analog (practical) | 1 / (2 x t_vih) |
| Digital sampling | 1 / (2 x (t_undefined + t_pulse_min)) |
| Counter overflow | 2^N x f_read (unsigned), 2^(N-1) x f_read (signed) |

where t_vih = tau x ln(V_high / (V_high - VIH)) is the time the rising edge takes to reach VIH from 0 V, and t_undefined is the larger of the two undefined-zone times:

- rising: tau x ln((V_high - VIL) / (V_high - VIH))
- falling (from VIH down to VIL): tau x ln(VIH / VIL)

The **effective limit** is the minimum of all four, with the bottleneck identified. It is shown only when all four are known. If V_high never reaches VIH, the tab says so and shows no threshold-based or effective limit.

### Plot

The bottom of the right panel shows **V_mcu vs V_input**:

- **Cyan line** - typical V_mcu (nominal components, typical Zener)
- **Orange line** - worst-case V_mcu (tolerance-shifted resistors, worst Zener)
- **Green dashed** - VDD threshold
- **Gold dashed** - Safe Max threshold
- **Red dashed** - Absolute Max threshold

Each curve and line is drawn only when its inputs are present. When neither curve can be calculated, the plot is cleared and says which inputs are needed.

Use the **Theme** dropdown to switch between Dark and Light plot styles.

### File Operations

| Action | Shortcut | Description |
|--------|----------|-------------|
| New | Ctrl+N | Blank design (bandwidth fields get their starting values) |
| Open | Ctrl+O | Load a `.div` file |
| Save | Ctrl+S | Save to current file |
| Save As | Ctrl+Shift+S | Save to a new file |

The title bar shows the current filename and an asterisk (*) when there are unsaved changes. Any edit to any input (typing, paste, cut, delete, the notes, the checkbox, the selectors) marks the design unsaved. The application prompts to save before closing, opening, or creating a new file.

- Saving writes a temporary file and then replaces the target, so a failed save never truncates the existing file. Save and Save As both report a failure.
- Opening checks the whole file first. Malformed data (wrong type, non-numeric text, unknown unit, broken structure) is rejected with an error that names the field, and the current design is left exactly as it was.
- Missing or null fields load blank, with one warning listing them. Files from before the ADC bits, VIL/VIH factor and bandwidth fields existed (format "1.0", such as `results.div`) still load; those fields are blank.

---

## File Format

Designs are saved as `.div` files (JSON). Blank fields are saved as `null`. Units are `"Ω"`, `"kΩ"` or `"MΩ"` (written as `Ω` escapes). Example:

```json
{
  "version": "1.0",
  "created": "2026-02-01T14:58:49.721771",
  "notes": "Test design for 4.7k/20k divider",
  "resistors": {
    "r1": { "value": 4.7, "unit": "kΩ", "rating_mw": 200.0, "tolerance_pct": 1.0 },
    "r2": { "value": 20.0, "unit": "kΩ", "rating_mw": 100.0, "tolerance_pct": 1.0 },
    "r_series": { "value": 0.0, "unit": "Ω", "rating_mw": null, "tolerance_pct": null }
  },
  "zener": {
    "preset": "Custom", "preset_base": "BZB984-C3V3",
    "vz_nom": 3.3, "vz_min": 3.1, "vz_max": 3.6, "tolerance_pct": 5,
    "izt_ma": 5.0, "zzt_typ": 85.0, "zzt_max": 95.0,
    "izk_ma": 1.0, "zzk_typ": 350.0, "zzk_max": 600.0, "ptot_mw": 265.0
  },
  "mcu": {
    "vdd": 3.3, "vdda": 3.3, "vref": 3.3,
    "v_recommended_max": 3.6, "v_absolute_max": 4.0, "safe_injection_ma": 1.0,
    "adc_bits": 12, "vil_factor": 0.3, "vih_factor": 0.7
  },
  "system": {
    "v_input_max": 30.0, "v_analog_fullscale": 5.1,
    "v_logic_high_min": 3.8, "v_logic_low_max": 1.0
  },
  "bandwidth": {
    "c_diode_pf": 450, "c_pin_pf": 10, "c_stray_pf": 3,
    "f_peripheral_mhz": 170, "n_samples": 3,
    "counter_bits": 16, "counter_signed": false, "f_read_hz": 1000
  }
}
```

`preset_base` is set only when the values were edited after picking a preset. `"vdda"` and `"vref"` are written as copies of `"vdd"` and ignored when loading.

---

## Project Structure

```
mcu_input_calculator/
├── main.py                       # Application entry point
├── requirements.txt              # Python dependencies
├── README.md
├── results.div                   # Sample design (format 1.0)
│
├── src/
│   ├── core/
│   │   ├── constants.py          # Zener presets, ADC tables, bandwidth starting values
│   │   └── app_state.py          # Controller: field parsing, file I/O, dirty tracking, recalc dispatch
│   │
│   ├── models/
│   │   ├── circuit_model.py      # DC analysis engine (pure math, no UI)
│   │   └── bandwidth_model.py    # AC bandwidth / PPS analysis engine
│   │
│   └── ui/
│       ├── main_window.py        # Top-level window, toolbar, layout
│       ├── input_panels.py       # Resistor, Zener, MCU, System, Bandwidth input panels
│       ├── output_panels.py      # Component, Safety, Operating, Bandwidth result tabs
│       └── plot_canvas.py        # Matplotlib V_mcu vs V_input chart
│
├── tests/                        # pytest suite (python -m pytest tests/ -v)
│
└── .vscode/
    └── launch.json               # VS Code debug configuration
```

### Architecture

The application follows a **Model-View-Controller** pattern:

- **Models** (`src/models/`) contain pure calculation logic with no UI dependencies. Inputs are dataclasses whose fields may be `None` (blank); each output is calculated only when its inputs are present, and the missing inputs are reported per output.
- **View** (`src/ui/`) contains all CustomTkinter widgets. Every input is bound to a Tk variable whose trace forwards the raw text to the controller. Output panels display the result objects; they don't parse or calculate.
- **Controller** (`src/core/app_state.py`) owns the text of every field, parses and range-checks it, triggers model recalculation, derives the bandwidth inputs from the DC results, and dispatches results back to the view via callbacks.

---

## Customizing Presets and Starting Values

All hardware presets and starting values live in a single file: **`src/core/constants.py`**. No other files need to change when adding new components or targeting a different processor.

### Adding or Replacing Zener Diodes

The `ZENER_PRESETS` dictionary holds every diode available in the preset dropdown. Each entry is a key (the display name) mapped to a dict of datasheet parameters.

To add a new diode, copy an existing block and fill in values from your datasheet:

```python
ZENER_PRESETS = {
    # ... existing presets ...

    "BZX84-C5V1": {
        "vz_nom": 5.1,       # Nominal Zener voltage (V) at IZT
        "vz_min": 4.8,       # Minimum Zener voltage (V) at IZT
        "vz_max": 5.4,       # Maximum Zener voltage (V) at IZT
        "tolerance_pct": 5,   # Voltage tolerance (%)
        "izt_ma": 5,          # Test current (mA) where VZ is specified
        "zzt_typ": 30,        # Dynamic impedance at IZT, typical (ohms)
        "zzt_max": 60,        # Dynamic impedance at IZT, maximum (ohms)
        "zzk_typ": 400,       # Dynamic impedance at IZK (knee), typical (ohms)
        "zzk_max": 600,       # Dynamic impedance at IZK (knee), maximum (ohms)
        "izk_ma": 1,          # Knee current (mA) - onset of Zener breakdown
        "ptot_mw": 350        # Maximum power dissipation (mW)
    },
}
```

**Where to find these values on a datasheet:**

| Parameter | Datasheet Section |
|-----------|-------------------|
| `vz_nom` / `vz_min` / `vz_max` | "Zener voltage" or "VZ" at test current IZT |
| `izt_ma` | "Test current" (IZT), usually 5 mA for low-power Zeners |
| `izk_ma` | "Knee current" (IZK), typically 1 mA |
| `zzt_typ` / `zzt_max` | "Dynamic impedance at IZT" (ZZT) |
| `zzk_typ` / `zzk_max` | "Dynamic impedance at IZK" (ZZK); reference only, not used in the calculation |
| `ptot_mw` | "Total power dissipation" (Ptot) at 25 deg C |

To remove a preset, delete its block from the dictionary. **Custom** is always offered in the dropdown; it is not an entry in `ZENER_PRESETS`.

### Changing the Target MCU

**ADC Sample Time Lookup Table**

The `ADC_SAMPLE_THRESHOLDS` list maps source impedance (ohms) to minimum ADC sample cycles. The defaults are for the **STM32G4** family. Replace with values from your MCU's datasheet (usually in the ADC electrical characteristics table):

```python
# Format: (max_source_impedance_ohms, min_sample_cycles)
# The list is checked top-to-bottom; first match wins.

# Example: STM32G4 (default)
ADC_SAMPLE_THRESHOLDS = [
    (1000,   2.5),    # <= 1 kOhm  -> 2.5 cycles
    (5000,   6.5),    # <= 5 kOhm  -> 6.5 cycles
    (10000,  12.5),   # <= 10 kOhm -> 12.5 cycles
    (20000,  24.5),   # <= 20 kOhm -> 24.5 cycles
    (40000,  47.5),   # <= 40 kOhm -> 47.5 cycles
]
ADC_SAMPLE_DEFAULT = 247.5  # Used when impedance exceeds all thresholds

# Example: STM32F4 (12-bit, different sample time options)
# ADC_SAMPLE_THRESHOLDS = [
#     (600,    3),
#     (2000,   15),
#     (10000,  28),
#     (25000,  56),
#     (50000,  84),
# ]
# ADC_SAMPLE_DEFAULT = 480
```

The MCU pin limits, ADC bits and VIL/VIH factors are entered in the MCU panel for each design (they start blank) and are saved in the `.div` file.

### Changing the Bandwidth Starting Values

`BANDWIDTH_STARTING_VALUES` sets the values a new design shows in the Signal Bandwidth fields, and what **Fill from starting values** puts back. Keep a one-line source note above each value:

```python
BANDWIDTH_STARTING_VALUES = {
    # Nexperia BZB984 series datasheet Rev 3, Table 8: Cd max 450 pF for C3V3 (f = 1 MHz, VR = 0 V)
    "c_diode_pf": 450,
    # STM32G484 datasheet DS12983 Rev 5, Table 54: CIO 5 pF typ (no max given); 10 pF = 2x typ as margin
    "c_pin_pf": 10,
    # Engineering estimate for a short PCB trace (2-5 pF typical); no datasheet source
    "c_stray_pf": 3,
    # STM32G484 datasheet DS12983 Rev 5, Table 17: fHCLK / fPCLK1 / fPCLK2 max 170 MHz
    "f_peripheral_mhz": 170,
    # Original project value, no datasheet source: set to your timer input filter's N
    "n_samples": 3,
    # STM32G484 datasheet DS12983 Rev 5, Table 7: TIM1/3/4/8/20 counters are 16-bit
    "counter_bits": 16,
    # Original project value: TIMx up-counter used as an unsigned count
    "counter_signed": False,
    # Original project value, no datasheet source: firmware counter read rate
    "f_read_hz": 1000,
}
```

**Key datasheet lookups:**

| Parameter | Where to Find |
|-----------|---------------|
| `c_diode_pf` | Protection diode datasheet, "diode capacitance" / "junction capacitance" at 0V reverse bias (use the max) |
| `c_pin_pf` | MCU datasheet, I/O static characteristics (CIO) |
| `f_peripheral_mhz` | MCU reference manual, clock tree diagram |
| `n_samples` | MCU reference manual, timer/input capture digital filter settings |

---

## Running the Tests

```bash
python -m pytest tests/ -v
```

All 394 tests must pass. `tests/test_ui.py` drives the real window (withdrawn), so it needs a desktop session.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError: No module named 'customtkinter'` | Run `pip install -r requirements.txt` |
| F5 does nothing in VS Code | Install the **Python** and **Python Debugger** extensions, then ensure `main.py` is the active file |
| Window appears but is blank | Try resizing the window, or check the terminal for error messages |
| `.div` file won't open | The error names the field that is wrong (for example `resistors.r1.unit`). Fix it in a text editor; units must be Ω, kΩ or MΩ |
| Plot doesn't render | Verify `matplotlib` and `numpy` are installed: `pip show matplotlib numpy` |
