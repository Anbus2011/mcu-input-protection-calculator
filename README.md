# STM32 Resistor Divider Calculator

A Python desktop application for designing and analyzing voltage divider circuits with Zener clamp protection for STM32 microcontroller GPIO/ADC inputs. Calculates safe operating margins when interfacing external 0-30V signals with 3.3V MCU pins.

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
- **File save/load** - JSON-based `.div` format preserves complete design state
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
- **Right panel** - output tabs and plot

### Input Panels

#### Resistors

Enter values for R1, R2, and the optional R_series. Each resistor has:
- **Value** with unit selector (Ohm or kOhm)
- **Power rating** (mW) - used to calculate margin percentage
- **Tolerance** (%) - used for worst-case analysis

| Default | Value |
|---------|-------|
| R1 | 10 kOhm, 200 mW, 1% |
| R2 | 18 kOhm, 100 mW, 1% |
| R_series | 0 Ohm |

#### Zener Diode

Select a preset from the dropdown or choose **Custom** to enter your own parameters. The BZB984 series presets (Nexperia) are built in:

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

Each preset populates: VZ (nom/min/max), IZT, IZK, ZZT (typ/max), ZZK (typ/max), and Ptot.

#### MCU Pin Input Limits

| Parameter | Default | Description |
|-----------|---------|-------------|
| VDD/VDDA | 3.3V | MCU supply voltage |
| Safe Max | 3.6V | Recommended maximum (VDDA + 0.3V) |
| Abs. Max | 4.0V | Absolute maximum (damage threshold) |
| Injection Limit | 1.0 mA | Maximum safe ESD clamp current |

#### System Requirements

| Parameter | Default | Description |
|-----------|---------|-------------|
| Max Input | 30V | Maximum signal voltage at the divider input |
| ADC Scale | 5.1V | External voltage that maps to ADC full scale |
| Logic High | 3.8V | Minimum input voltage that must read as logic high |
| Logic Low | 1.0V | Maximum input voltage that must read as logic low |

#### Design Notes

Free-form text area for annotations. Saved with the `.div` file.

### Output Tabs

#### Tab 1: Component Analysis

- **Divider Network** - input impedance, divider ratio, ADC source impedance, total power dissipation
- **Component Power** - current, power, rating, and margin % for R1, R2, and Zener at max input
- **Voltage at MCU Pin** - typical and worst-case V_mcu at maximum input voltage

Margin indicators:
- **Green** (> 20% margin) - safe
- **Orange** (0-20% margin) - tight
- **Red** (negative margin) - exceeds rating

#### Tab 2: MCU Input

- **Voltage Limits** - V_mcu vs Safe Max and Absolute Max with margin in mV and pass/fail status
- **Injection Current** - estimated current into ESD clamp vs the safe limit
- **ADC Performance** - source impedance, recommended minimum sample cycles (STM32G4), and resolution in mV/LSB

#### Tab 3: Input Levels

Operating point table showing the MCU pin voltage at five key input levels:

| Level | Check |
|-------|-------|
| 0V | Zero reference |
| Logic Low | V_mcu must be below VIL (0.3 x VDD) |
| Logic High | V_mcu must be above VIH (0.7 x VDD) |
| ADC Scale | V_mcu must not exceed VDD |
| Max Input | V_mcu must not exceed Absolute Max |

Each row shows both **V_mcuL** (lowest, from R1 high / R2 low / typical Zener) and **V_mcuH** (highest, from R1 low / R2 high / worst Zener).

#### Tab 4: Signal Bandwidth

Analyzes the RC low-pass filter formed by the protection network to determine the maximum signal frequency the MCU pin can reliably detect. Enter:

- **R_series**, **C_diode** (junction capacitance), **C_pin** (GPIO capacitance), **C_stray** (PCB estimate)
- **VIL** and **VIH** thresholds from the MCU datasheet
- **Peripheral clock** and **digital filter samples** for digital sampling limit
- **Counter width**, **signedness**, and **firmware read rate** for overflow limit

Results show four frequency limits and the effective maximum PPS:

| Limit | Formula |
|-------|---------|
| Analog (conservative) | 1 / (10 x tau) |
| Analog (practical) | 1 / (2 x t_vih) |
| Digital sampling | 1 / (2 x (t_undefined + t_pulse_min)) |
| Counter overflow | 2^(bits) x f_read |

The **effective limit** is the minimum of all four, with the bottleneck identified.

### Plot

The bottom of the right panel shows **V_mcu vs V_input**:

- **Cyan line** - typical V_mcu (nominal components, typical Zener)
- **Orange line** - worst-case V_mcu (tolerance-shifted resistors, worst Zener)
- **Green dashed** - VDD threshold
- **Gold dashed** - Safe Max threshold
- **Red dashed** - Absolute Max threshold

Use the **Theme** dropdown to switch between Dark and Light plot styles.

### File Operations

| Action | Shortcut | Description |
|--------|----------|-------------|
| New | Ctrl+N | Reset all inputs to defaults |
| Open | Ctrl+O | Load a `.div` file |
| Save | Ctrl+S | Save to current file |
| Save As | Ctrl+Shift+S | Save to a new file |

The title bar shows the current filename and an asterisk (*) when there are unsaved changes. The application prompts to save before closing, opening, or creating a new file.

---

## File Format

Designs are saved as `.div` files (JSON). Example:

```json
{
  "version": "1.0",
  "created": "2026-02-01T14:58:49.721771",
  "notes": "Test design for 4.7k/20k divider",
  "resistors": {
    "r1": { "value": 4.7, "unit": "kOhm", "rating_mw": 200.0, "tolerance_pct": 1.0 },
    "r2": { "value": 20.0, "unit": "kOhm", "rating_mw": 100.0, "tolerance_pct": 1.0 },
    "r_series": { "value": 0.0, "unit": "Ohm", "rating_mw": null, "tolerance_pct": null }
  },
  "zener": {
    "preset": "BZB984-C3V3",
    "vz_nom": 3.3, "vz_min": 3.1, "vz_max": 3.5,
    "izt_ma": 5.0, "zzt_typ": 85.0, "zzt_max": 95.0,
    "zzk_typ": 350.0, "zzk_max": 600.0, "izk_ma": 1.0, "ptot_mw": 265.0
  },
  "mcu": {
    "vdd": 3.3, "v_recommended_max": 3.6,
    "v_absolute_max": 4.0, "safe_injection_ma": 1.0
  },
  "system": {
    "v_input_max": 30.0, "v_analog_fullscale": 5.1,
    "v_logic_high_min": 3.8, "v_logic_low_max": 1.0
  }
}
```

---

## Project Structure

```
Resistor_Calculator/
├── main.py                       # Application entry point
├── requirements.txt              # Python dependencies
├── README.md
│
├── src/
│   ├── core/
│   │   ├── constants.py          # Zener presets, ADC tables, defaults
│   │   └── app_state.py          # Controller: file I/O, dirty tracking, recalc dispatch
│   │
│   ├── models/
│   │   ├── circuit_model.py      # DC analysis engine (pure math, no UI)
│   │   └── bandwidth_model.py    # AC bandwidth / PPS analysis engine
│   │
│   └── ui/
│       ├── main_window.py        # Top-level window, menu, layout
│       ├── input_panels.py       # Resistor, Zener, MCU, System, Bandwidth input panels
│       ├── output_panels.py      # Component, Safety, Operating, Bandwidth result tabs
│       └── plot_canvas.py        # Matplotlib V_mcu vs V_input chart
│
├── div/                          # Example .div design files
│   ├── test1.div
│   └── test2.div
│
├── MD_Files/                     # Project documentation
│   ├── stm32_divider_calculator_project.md
│   └── stm32_divider_calculator_project_with_PPS.md
│
└── .vscode/
    └── launch.json               # VS Code debug configuration
```

### Architecture

The application follows a **Model-View-Controller** pattern:

- **Models** (`src/models/`) contain pure calculation logic with no UI dependencies. All inputs are plain floats and dataclasses, all outputs are result dataclasses.
- **View** (`src/ui/`) contains all CustomTkinter widgets. Input panels push values to the controller on change. Output panels receive result objects and update their display.
- **Controller** (`src/core/app_state.py`) owns the state, triggers model recalculation, and dispatches results back to the view via callbacks.

---

## Customizing Presets and Defaults

All hardware presets and MCU defaults live in a single file: **`src/core/constants.py`**. No other files need to change when adding new components or targeting a different processor.

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

    # "Custom" must always be the last entry
    "Custom": { ... }
}
```

**Where to find these values on a datasheet:**

| Parameter | Datasheet Section |
|-----------|-------------------|
| `vz_nom` / `vz_min` / `vz_max` | "Zener voltage" or "VZ" at test current IZT |
| `izt_ma` | "Test current" (IZT), usually 5 mA for low-power Zeners |
| `izk_ma` | "Knee current" (IZK), typically 1 mA |
| `zzt_typ` / `zzt_max` | "Dynamic impedance at IZT" (ZZT) |
| `zzk_typ` / `zzk_max` | "Dynamic impedance at IZK" (ZZK) |
| `ptot_mw` | "Total power dissipation" (Ptot) at 25 deg C |

To remove a preset, delete its block from the dictionary. The **"Custom"** entry should always remain as the last item -- it serves as the editable fallback.

### Changing the Target MCU

The MCU-specific values are in two places within `constants.py`:

**1. ADC Sample Time Lookup Table**

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

**2. MCU Pin Limits (defaults)**

The `DEFAULT_VALUES["mcu"]` section sets what appears in the MCU input panel when the application starts or a new file is created:

```python
DEFAULT_VALUES = {
    # ...
    "mcu": {
        "vdd": 3.3,                  # Supply voltage (V)
        "vdda": 3.3,                 # Analog supply voltage (V)
        "vref": 3.3,                 # ADC reference voltage (V)
        "v_recommended_max": 3.6,    # VDD + 0.3V (safe operating limit)
        "v_absolute_max": 4.0,       # Absolute max from datasheet
        "safe_injection_ma": 1.0,    # Max ESD clamp current (mA)
    },
    # ...
}
```

To target a **5V-tolerant** MCU (e.g., STM32F1), you might change these to:

```python
"mcu": {
    "vdd": 3.3,
    "vdda": 3.3,
    "vref": 3.3,
    "v_recommended_max": 5.0,    # 5V-tolerant pins
    "v_absolute_max": 5.5,
    "safe_injection_ma": 5.0,
},
```

### Changing the Bandwidth / PPS Defaults

The `DEFAULT_VALUES["bandwidth"]` section controls the starting values for the Signal Bandwidth tab. Adjust these for your specific MCU and protection diode:

```python
"bandwidth": {
    "r_series_bw": 100,         # Series resistance in signal path (ohms)
    "c_diode_pf": 95,           # Zener junction capacitance at 0V bias (pF)
    "c_pin_pf": 10,             # MCU GPIO input capacitance (pF)
    "c_stray_pf": 3,            # PCB parasitic capacitance estimate (pF)
    "vil": 0.99,                # Input low threshold voltage (V)
    "vih": 2.31,                # Input high threshold voltage (V)
    "f_peripheral_mhz": 170,    # Peripheral clock frequency (MHz)
    "n_samples": 3,             # Digital filter: min samples for valid edge
    "counter_bits": 16,         # Hardware counter width (bits)
    "counter_signed": False,    # True if counter is signed (+/-)
    "f_read_hz": 1000,          # Firmware counter read rate (Hz)
},
```

**Key datasheet lookups:**

| Parameter | Where to Find |
|-----------|---------------|
| `c_diode_pf` | Protection diode datasheet, "junction capacitance" at 0V reverse bias |
| `c_pin_pf` | MCU datasheet, GPIO electrical specifications |
| `vil` / `vih` | MCU datasheet, I/O DC characteristics (VIL max, VIH min) |
| `f_peripheral_mhz` | MCU reference manual, clock tree diagram |
| `n_samples` | MCU reference manual, timer/input capture digital filter settings |

### Changing System Defaults

The `DEFAULT_VALUES["system"]` section sets the starting signal and threshold voltages:

```python
"system": {
    "v_input_max": 30,           # Maximum expected input voltage (V)
    "v_analog_fullscale": 5.1,   # Input voltage that maps to ADC full-scale
    "v_logic_high_min": 3.8,     # Input voltage that must read as logic HIGH
    "v_logic_low_max": 1.0,      # Input voltage that must read as logic LOW
},
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError: No module named 'customtkinter'` | Run `pip install -r requirements.txt` |
| F5 does nothing in VS Code | Install the **Python** and **Python Debugger** extensions, then ensure `main.py` is the active file |
| Window appears but is blank | Try resizing the window, or check the terminal for error messages |
| `.div` file won't open | Ensure the file is valid JSON. Open it in a text editor to check for corruption |
| Plot doesn't render | Verify `matplotlib` and `numpy` are installed: `pip show matplotlib numpy` |
