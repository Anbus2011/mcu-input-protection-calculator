# MCU Input Protection Calculator - AI System Context

## 1. Project Purpose & Role
You are assisting with the "MCU Input Protection Calculator," a Python desktop application (CustomTkinter) used to analyze DC voltage levels and AC signal bandwidth (PPS) for microcontroller GPIO/ADC inputs protected by resistor dividers and Zener clamps. Works with any MCU family (STM32, ESP32, PIC, AVR, etc.).

When writing or modifying code for this project, you must adhere strictly to the architectural rules and mathematical models defined in this document. 

## 2. Architecture & State Management
This project uses a strict Controller/Model/View decoupled architecture.
* **`src/models/`**: Pure math/physics engines (`circuit_model.py`, `bandwidth_model.py`). **NO UI dependencies.** Returns stateless dataclasses (e.g., `CalculationResult`).
* **`src/ui/`**: CustomTkinter views. **NO math calculations.** Views capture input, send it to `AppState`, and listen for callbacks to update labels/plots.
* **`src/core/app_state.py`**: The central controller. Handles file I/O (.div JSON format), dirty-tracking, and triggers the `CircuitModel` to recalculate.
* **Rule:** Never embed calculation logic inside a UI button click or input callback. Always route through `AppState`.
* **Rule: no hidden defaults.** The UI forwards the raw text of every field to `AppState`, which parses it. A blank field stays blank, and nothing substitutes a value the user can't see (no `.get(key, default)`, no dataclass defaults, no fallback numbers). Blank or unreadable text becomes `None`; every result that depends on it shows "needs input" (or is cleared, with the reason shown), and everything that doesn't depend on it still computes. The only values the app fills in by itself are visible ones: the Signal Bandwidth starting values in `constants.py` (each with a source note) and the fields of a Zener preset the user picks. R_s blank or 0 means no series resistor.

## 3. Circuit Topology
    V_input (0-30V) ──┬── R1 ──┬── R_series ──> MCU GPIO Pin
                      │        │
                      │        ├── Zener (cathode)
                      │        │
                      └── R2 ──┴── GND

## 4. Mathematical Models (Source of Truth)

### A. DC Tolerance Stack-up
To calculate the worst-case voltages at the MCU pin (V_mcu):
* **Lowest V_mcu (V_mcuL):** Use maximum R1 [R1 * (1 + tol)], minimum R2 [R2 * (1 - tol)], and **typical** Zener characteristics.
* **Highest V_mcu (V_mcuH):** Use minimum R1 [R1 * (1 - tol)], maximum R2 [R2 * (1 + tol)], and **worst-case** maximum Zener voltage (VZ_max).

### B. Zener Non-Linear Solver (Crucial)
The Zener clamp is solved numerically due to its non-linear V-I curve.
* **Solver rules:** Bisection on the node voltage. The node satisfies $V = V_{clamp}(I_Z(V))$ with $I_Z(V) = \frac{V_{in} - V}{R1} - \frac{V}{R2}$. If the unclamped divider voltage $V_{div}$ is below $V_{Z\_knee}$ the node is $V_{div}$ (no clamping). Otherwise $h(V) = V - V_{clamp}(I_Z(V))$ is strictly increasing, negative at 0 V and positive just below $V_{div}$, so bisect on $[0, V_{div}]$ until the bracket is 1 µV wide. One function (`solve_node_voltage`) serves the results, the operating points and the plot. If the bracket has no sign change (or doesn't narrow to 1 µV), the result is marked "did not settle" and a warning is shown.
* **Knee Voltage Baseline:**
  * Typical Case: V_Z_knee = 0.94 * VZ_nom
  * Worst Case: V_Z_knee = 0.97 * VZ_max
* **Three Operating Regions:**
  1. **Below IZK (Soft Breakdown):** Voltage scales linearly from 0.97 * V_Z_knee to V_Z_knee based on the ratio of IZ / IZK.
  2. **Between IZK and IZT:** Linear interpolation of voltage and dynamic impedance (ZZ).
  3. **Above IZT:** Extrapolated using ZZT slope:
     $$V_{clamp} = V_Z + (I_Z - I_{ZT}) \times \frac{Z_{ZT}}{1000}$$
* **Edge Cases:** If IZ < 0.5 mA, clamping is considered ineffective. Cap the return voltage at VZ_nom or VZ_max (never above $V_{div}$). A solved voltage below $V_{Z\_knee}$ is raised to $V_{Z\_knee}$.
* **Known limitation of the 0.5 mA rule (kept unchanged):** the curve follows the divider up to VZ, stays flat at VZ while IZ < 0.5 mA, then drops to the knee where IZ reaches 0.5 mA. Reference design (10k/18k, BZB984-C3V3): typical curve 3.300 V → 3.102 V (−198 mV) at 9.753 V in; worst-case curve (V_mcuH) 3.500 V → 3.395 V (−105 mV) at 10.115 V in. An input level right at that point can land on either side of the step.
* **ZZK is reference only:** it is not used in the calculation (the panel says so). The V-I curve uses VZ, IZT, IZK and ZZT.
* **Low-voltage Zener corner (worst-case power only):** VZ_min at IZT, knee 0.94 × VZ_min, ZZT typ, same three regions. *Derived, not a datasheet value:* the datasheet gives only VZ_min at IZT; the 0.94 knee factor and ZZT typ are carried over from the typical curve (approved by DK, 2026-11-08).
* **Injection current estimate (same formula as §4D):** injection starts at VDD + 0.3 V; R_s at its low tolerance, 0 when there is no R_s; 100 Ω stands for the internal ESD path:
  $$I_{inj} = \frac{\max(0,\ V_{mcuH} - (VDD + 0.3))}{R_{s,min} + 100}$$
  Label it an estimate. On STM32G4 FT/TT pins positive injection is not possible (DS12983 Rev 5, Table 15, note 3); pin-type limits come with the MCU part files.
* **Power at max input, typical and worst case:**
  * Typical: nominal R1/R2, typical Zener. $P_{R1} = I_{R1}^2 R1$, $P_{R2} = I_{R2}^2 R2$, $P_Z = V \cdot I_Z$, $P_{Rs} = I_{inj,typ}^2 R_s$ with $I_{inj,typ}$ from the typical node and nominal R_s. Total power = R1 + R2 + Zener (typical).
  * Worst case, per part: the maximum over the corners R1 {min, max} × R2 {min, max} × Zener {low: VZ_min curve, high: VZ_max curve} (8 corners), plus the typical point.
  * R_s worst case: node at V_mcuH; $P = I^2 R$ with $I = \frac{V_{mcuH} - (VDD + 0.3)}{R + 100}$, maximised over R in [R_s min, R_s max]. The maximum is at an end of the band, or at 100 Ω if it lies inside.
  * Margins: (rating − power) / rating, shown against both typical and worst-case power. A blank rating shows "needs input" (no hint value). R_s blank or 0: the R_s row shows "no R_s" and nothing is asked for.
  * Verdict: the worst-case margin is the verdict for each part (R1, R2, Zener, R_s); the typical margin is shown for information only. Thresholds: PASS > 20 %, TIGHT 0–20 %, FAIL ≤ 0 %. The overall "Power verdict (worst case)" is FAIL if any part fails, TIGHT if any is tight, otherwise PASS, or "needs input" if any rating is blank.

### C. Signal Bandwidth and PPS Analysis (AC Model)
The protection network forms an RC low-pass filter. 
* **Capacitance:**
  $$C_{total} = C_{diode} + C_{pin} + C_{stray}$$ 
  (Use C_diode at 0V bias for worst-case).
* **Time Constant:**
  $$\tau = \left(\frac{R1 \times R2}{R1 + R2} + R_{series}\right) \times C_{total}$$
* **Thresholds at the pin:** $V_{IL} = k_{VIL} \times VDD$ and $V_{IH} = k_{VIH} \times VDD$, where $k_{VIL}$ and $k_{VIH}$ are the MCU panel's VIL/VIH factor fields (STM32G4: 0.3 and 0.7, DS12983 Rev 5, Table 54).
* **High level at the pin:** $V_{high}$ = the lowest solved pin voltage at the System panel's Logic High input voltage (V_mcuL: R1 max, R2 min, typical Zener, §4A/§4B). If $V_{high} \le V_{IH}$ the pin never reads high: the tab says so and shows no threshold-based limit and no effective limit.
* **Threshold Crossing Time:** The time spent in the "undefined logic zone" between VIL and VIH:
  $$t_{undefined} = \tau \times \ln \left( \frac{V_{high} - V_{IL}}{V_{high} - V_{IH}} \right)$$
  This is the rising edge. The falling edge (from VIH down to VIL, as coded):
  $$t_{undefined,fall} = \tau \times \ln \left( \frac{V_{IH}}{V_{IL}} \right)$$
  The digital limit uses the larger of the two: $t_{undefined} = \max(t_{undefined,rise},\ t_{undefined,fall})$.
* **Maximum Frequencies:**
  * **Analog Limit, conservative (99% swing):** $$f_{max\_analog} = \frac{1}{10 \times \tau}$$
  * **Analog Limit, practical:** $$f_{max\_practical} = \frac{1}{2 \times t_{VIH}}, \quad t_{VIH} = \tau \times \ln \left( \frac{V_{high}}{V_{high} - V_{IH}} \right)$$
    *(t_VIH is the time for the rising edge to reach VIH from 0 V)*
  * **Digital Limit:** $$f_{max\_digital} = \frac{1}{2 \times (t_{undefined} + t_{pulse\_min})}$$
    *(where t_pulse_min = N_samples / f_peripheral_clock)*
  * **Firmware Limit:** $$f_{max\_overflow} = 2^{N_{bits}} \times f_{read}$$ for an unsigned counter, $$2^{(N_{bits} - 1)} \times f_{read}$$ for a signed counter.
* **Effective Max PPS:** The minimum of the four limits above (analog conservative, analog practical, digital, firmware), with the bottleneck named. Shown only when all four are known.

### D. STM32 Specific Constants
* **Safe Max Limit:** VDDA + 0.3V (Threshold before internal ESD injection begins). The `pin_max_safe` check (highest pin voltage at the maximum input against Safe Max) is the guard against injection.
* **No injection current estimate** (removed 2026-11-09, approved by the owner). The old formula divided by 100 Ω for the internal ESD path; that number came from the first version of the app and no data sheet gives it. There is no injection check, no Injection Limit field and no `safe_injection_ma` key. *Until step 3 of the div-v2 work switches the app to `clamp_solver.py`, the app and §4B still show the old estimate.*
* **R_s power** (the pin is taken as held at 0 V, so the whole node voltage is across R_s; no 100 Ω anywhere):
  * Typical: $P_{Rs} = V_{typ}^2 / R_s$ (typical node voltage at the maximum input, nominal R_s).
  * Worst case (the `power_rs` check): $P_{Rs} = V_{node,max}^2 / R_{s,min}$, with $V_{node,max}$ the highest node voltage at the maximum input and $R_{s,min}$ R_s at its low tolerance.
* **ADC Source Impedance:** $$R_{source} = \frac{R1 \times R2}{R1 + R2} + R_{series}$$
* **STM32G4 ADC Sampling Cycles:**
  * <= 1 kΩ -> 2.5 cycles
  * <= 5 kΩ -> 6.5 cycles
  * <= 10 kΩ -> 12.5 cycles
  * <= 20 kΩ -> 24.5 cycles
  * <= 40 kΩ -> 47.5 cycles
  * > 40 kΩ -> 247.5 cycles

## 5. Testing
After ANY code change, run the test suite before committing:

```bash
python -m pytest tests/ -v
```

All 401 tests must pass. The suite covers:
* **Circuit model** (`test_circuit_model.py`, 35 tests): Zener 3-region V-I model, ADC sample lookup, full divider calculation, Kirchhoff's current law balance, power sums, tolerance worst-case ratios, operating points, results.div cross-check, edge cases
* **Bandwidth model** (`test_bandwidth_model.py`, 17 tests): RC time constant, -3dB bandwidth, rise time, threshold timing formulas, all 4 frequency limits, counter overflow signed/unsigned, edge cases
* **File I/O** (`test_file_io.py`, 8 tests): Save/load round-trip, JSON format version, backwards compatibility with shipped results.div, minimal file loading, dirty tracking
* **Model fixes** (`test_fixes_model.py`, 51 tests): reference case, one solver for results/operating points/plot (V_input max 5 V repro), bisection (R1 = R2 = 100 Ω converges, root within 1 µV, "did not settle" warning when bracketing fails, 0.5 mA cap step kept), no results from missing inputs, no dataclass defaults, ZZK reference only, zero ratings, ADC bits (VREF / 2^N), VIL/VIH factors, V_high, "never reaches VIH" with no fallback, injection estimate (VDD + 0.3 V, R_s min; reference 0 mA), worst-case power ≥ typical and hand-checked corners (R1, R_s), blank rating = "needs input", power verdict from the worst-case margins (typical pass + worst fail = FAIL)
* **AppState** (`test_fixes_app_state.py`, 108 tests): bandwidth derivation (τ resistance, VIL/VIH, V_high), bandwidth starting values / save / load / fill, every field marks unsaved, blank design, "needs input" (VZ min only for worst-case power, R_s rating/tolerance when R_s > 0, blank rating), range checks, R_s rules and R_s min in the injection estimate, unreadable text blocks Save, atomic save, file validation (null, missing, malformed, Ω/kΩ/MΩ), change tracking after a failed load, preset "modified" / Custom + preset_base
* **UI** (`test_ui.py`, 182 tests; needs a desktop session): drives the real, withdrawn window through its widgets: change tracking on every input (typing, paste, cut, delete, notes, checkbox, comboboxes), blank / 0 / unreadable on every numeric field, New Design clearing everything, both save-failure messages, preset shown as modified, results.div giving bandwidth outputs, plot clearing, failed loads, injection row labelled as an estimate (reference 0.00 mA), typical / worst-case power and the R_s row, blank rating = "needs input", ZZK marked reference only, solver warning, the two worst-case voltages labelled apart, power verdict

If a test fails after your change, fix the issue before committing. Do not skip or delete tests.

### Verification Baseline
If you modify `circuit_model.py`, ensure these reference calculations still hold:
* **Inputs:** R1 = 10 kΩ, R2 = 18 kΩ, R_series = 0 Ω, V_input = 30V, BZB984-C3V3.
* **Expected Outputs:**
  * Input Impedance: 28 kΩ
  * Divider Ratio: 0.643
  * V_mcu Typical: ~3.18V
  * V_mcu Worst: ~3.43V
  * Zener Current: ~2.5 mA
  * Injection Current: 0 mA (V_mcuH 3.434 V is below VDD + 0.3 V)