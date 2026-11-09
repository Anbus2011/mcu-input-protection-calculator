"""
Constants for the Resistor Divider Calculator.
Zener presets, ADC reference tables, and application-wide constants.
"""

# ============================================================================
# ZENER PRESETS - BZB984 Series (Nexperia Rev.3 Dec 2022)
# ============================================================================
ZENER_PRESETS = {
    "BZB984-C3V0": {
        "vz_nom": 3.0, "vz_min": 2.8, "vz_max": 3.2, "tolerance_pct": 5,
        "izt_ma": 5, "zzt_typ": 80, "zzt_max": 95,
        "zzk_typ": 325, "zzk_max": 600, "izk_ma": 1, "ptot_mw": 265
    },
    "BZB984-C3V3": {
        "vz_nom": 3.3, "vz_min": 3.1, "vz_max": 3.5, "tolerance_pct": 5,
        "izt_ma": 5, "zzt_typ": 85, "zzt_max": 95,
        "zzk_typ": 350, "zzk_max": 600, "izk_ma": 1, "ptot_mw": 265
    },
    "BZB984-C3V6": {
        "vz_nom": 3.6, "vz_min": 3.4, "vz_max": 3.8, "tolerance_pct": 5,
        "izt_ma": 5, "zzt_typ": 85, "zzt_max": 90,
        "zzk_typ": 375, "zzk_max": 600, "izk_ma": 1, "ptot_mw": 265
    },
    "BZB984-C3V9": {
        "vz_nom": 3.9, "vz_min": 3.7, "vz_max": 4.1, "tolerance_pct": 5,
        "izt_ma": 5, "zzt_typ": 85, "zzt_max": 90,
        "zzk_typ": 400, "zzk_max": 600, "izk_ma": 1, "ptot_mw": 265
    },
    "BZB984-C4V3": {
        "vz_nom": 4.3, "vz_min": 4.0, "vz_max": 4.6, "tolerance_pct": 5,
        "izt_ma": 5, "zzt_typ": 80, "zzt_max": 90,
        "zzk_typ": 410, "zzk_max": 600, "izk_ma": 1, "ptot_mw": 265
    },
    "BZB984-C4V7": {
        "vz_nom": 4.7, "vz_min": 4.4, "vz_max": 5.0, "tolerance_pct": 5,
        "izt_ma": 5, "zzt_typ": 50, "zzt_max": 80,
        "zzk_typ": 425, "zzk_max": 500, "izk_ma": 1, "ptot_mw": 265
    },
    "BZB984-C5V1": {
        "vz_nom": 5.1, "vz_min": 4.8, "vz_max": 5.4, "tolerance_pct": 5,
        "izt_ma": 5, "zzt_typ": 40, "zzt_max": 60,
        "zzk_typ": 400, "zzk_max": 480, "izk_ma": 1, "ptot_mw": 265
    },
    "BZB984-C5V6": {
        "vz_nom": 5.6, "vz_min": 5.2, "vz_max": 6.0, "tolerance_pct": 5,
        "izt_ma": 5, "zzt_typ": 15, "zzt_max": 40,
        "zzk_typ": 80, "zzk_max": 400, "izk_ma": 1, "ptot_mw": 265
    },
    "BZB984-C6V2": {
        "vz_nom": 6.2, "vz_min": 5.8, "vz_max": 6.6, "tolerance_pct": 5,
        "izt_ma": 5, "zzt_typ": 6, "zzt_max": 10,
        "zzk_typ": 40, "zzk_max": 150, "izk_ma": 1, "ptot_mw": 265
    },
}

# ============================================================================
# ADC SAMPLE TIME REFERENCE (STM32G4)
# ============================================================================
ADC_SAMPLE_THRESHOLDS = [
    (1000,   2.5),
    (5000,   6.5),
    (10000,  12.5),
    (20000,  24.5),
    (40000,  47.5),
]
ADC_SAMPLE_DEFAULT = 247.5

# ============================================================================
# ZENER PRESET COMBOBOX
# ============================================================================
# "Custom" is not a part: choosing it keeps the values already in the fields.
CUSTOM_PRESET = "Custom"

# ============================================================================
# RESISTOR UNITS
# ============================================================================
RESISTOR_UNITS = {"Ω": 1.0, "kΩ": 1e3, "MΩ": 1e6}

# Units shown in the unit selectors of a new, blank design (visible, and they
# have no effect until a value is typed).
NEW_DESIGN_UNITS = {"r1": "kΩ", "r2": "kΩ", "rs": "Ω"}

# ============================================================================
# SIGNAL BANDWIDTH STARTING VALUES
# ============================================================================
# These are the only values the app ever puts in a field by itself: a new
# design starts with them in the Signal Bandwidth fields, and the
# "Fill from starting values" button puts them back into blank or unreadable
# bandwidth fields. They are always visible in the fields. Every other input
# starts blank.
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

# ============================================================================
# SVG ICON (Resistor symbol)
# ============================================================================
RESISTOR_SVG = '''<?xml version="1.0" encoding="UTF-8"?>
<svg width="64" height="64" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
  <rect width="64" height="64" rx="8" fill="#2B5EA7"/>
  <path d="M8 32 L16 32 L18 24 L22 40 L26 24 L30 40 L34 24 L38 40 L42 24 L46 40 L48 32 L56 32"
        stroke="#FFFFFF" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="8" cy="32" r="3" fill="#FFFFFF"/>
  <circle cx="56" cy="32" r="3" fill="#FFFFFF"/>
</svg>'''

APP_VERSION = "1.1"
FILE_FORMAT_VERSION = "1.0"
