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
The Zener clamp is solved iteratively due to its non-linear V-I curve. 
* **Solver rules:** Iterate 15 times using a 0.3 / 0.7 dampening blend:
  $$V_{node} = (V_{node} \times 0.3) + (V_{clamp} \times 0.7)$$
* **Knee Voltage Baseline:**
  * Typical Case: V_Z_knee = 0.94 * VZ_nom
  * Worst Case: V_Z_knee = 0.97 * VZ_max
* **Three Operating Regions:**
  1. **Below IZK (Soft Breakdown):** Voltage scales linearly from 0.97 * V_Z_knee to V_Z_knee based on the ratio of IZ / IZK.
  2. **Between IZK and IZT:** Linear interpolation of voltage and dynamic impedance (ZZ).
  3. **Above IZT:** Extrapolated using ZZT slope:
     $$V_{clamp} = V_Z + (I_Z - I_{ZT}) \times \frac{Z_{ZT}}{1000}$$
* **Edge Cases:** If IZ < 0.5 mA, clamping is considered ineffective. Cap the return voltage at VZ_nom or VZ_max.

### C. Signal Bandwidth and PPS Analysis (AC Model)
The protection network forms an RC low-pass filter. 
* **Capacitance:**
  $$C_{total} = C_{diode} + C_{pin} + C_{stray}$$ 
  (Use C_diode at 0V bias for worst-case).
* **Time Constant:**
  $$\tau = R_{total} \times C_{total}$$
* **Threshold Crossing Time:** The time spent in the "undefined logic zone" between VIL and VIH:
  $$t_{undefined} = \tau \times \ln \left( \frac{V_{high} - V_{IL}}{V_{high} - V_{IH}} \right)$$
* **Maximum Frequencies:**
  * **Analog Limit (99% swing):** $$f_{max\_analog} = \frac{1}{10 \times \tau}$$
  * **Digital Limit:** $$f_{max\_digital} = \frac{1}{2 \times (t_{undefined} + t_{pulse\_min})}$$
    *(where t_pulse_min = N_samples / f_peripheral_clock)*
  * **Firmware Limit:** $$f_{max\_overflow} = 2^{(N_{bits} - 1)} \times f_{read}$$
* **Effective Max PPS:** The minimum of the three limits above.

### D. STM32 Specific Constants
* **Safe Max Limit:** VDDA + 0.3V (Threshold before internal ESD injection begins).
* **Injection Current Estimate:** If V_mcu > VDD, calculate injection current in mA. The 100Ω represents internal ESD resistance:
  $$I_{inj} = \frac{V_{mcu} - VDD}{R_{series} + 100}$$
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

All 60 tests must pass. The suite covers:
* **Circuit model** (32 tests): Zener 3-region V-I model, ADC sample lookup, full divider calculation, Kirchhoff's current law balance, power sums, tolerance worst-case ratios, operating points, results.div cross-check, edge cases
* **Bandwidth model** (17 tests): RC time constant, -3dB bandwidth, rise time, threshold timing formulas, all 4 frequency limits, counter overflow signed/unsigned, edge cases
* **File I/O** (11 tests): Save/load round-trip, JSON format version, backwards compatibility with shipped results.div, minimal file loading, dirty tracking

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