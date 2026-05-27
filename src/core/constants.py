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
    "Custom": {
        "vz_nom": 3.3, "vz_min": 3.1, "vz_max": 3.5, "tolerance_pct": 5,
        "izt_ma": 5, "zzt_typ": 85, "zzt_max": 95,
        "zzk_typ": 350, "zzk_max": 600, "izk_ma": 1, "ptot_mw": 265
    }
}


# ============================================================================
# SCHOTTKY PRESETS - BAT54CV (Nexperia SOT-666 4-channel Schottky array)
# ============================================================================
SCHOTTKY_PRESETS = {
    "BAT54CV": {
        "vf_typ": 0.32,
        "vf_max": 0.40,
        "if_test_ma": 10,
        "r_dynamic": 4.0,
        "ir_ua": 2.0,
        "vr_max": 30,
        "cd_pf": 10,
        "pd_mw": 200,
        "channels": 4,
    },
    "Custom": {
        "vf_typ": 0.32,
        "vf_max": 0.40,
        "if_test_ma": 10,
        "r_dynamic": 4.0,
        "ir_ua": 2.0,
        "vr_max": 30,
        "cd_pf": 10,
        "pd_mw": 200,
        "channels": 4,
    },
}
# ============================================================================
# TVS PRESETS
# ============================================================================
TVS_PRESETS = {
    "SMBJ60": {
        "v_rwm": 60.0,
        "v_br_min": 66.7,
        "v_br_max": 73.7,
        "v_c": 96.8,
        "i_pp": 6.2,
        "i_t": 1.0,
        "c_pf": 380,
        "p_ppm_w": 600,
    },
    "SMAJ5.0A": {
        "v_rwm": 5.0,
        "v_br_min": 6.4,
        "v_br_max": 7.0,
        "v_c": 9.2,
        "i_pp": 43.5,
        "i_t": 10.0,
        "c_pf": 850,
        "p_ppm_w": 400,
    },
    "PESD3V3L": {
        "v_rwm": 3.3,
        "v_br_min": 4.2,
        "v_br_max": 6.0,
        "v_c": 9.0,
        "i_pp": 1.0,
        "i_t": 1.0,
        "c_pf": 0.6,
        "p_ppm_w": 0.3,
    },
    "SMAJ5.0CA": {
        "v_rwm": 5.0,
        "v_br_min": 6.4,
        "v_br_max": 7.0,
        "v_c": 9.2,
        "i_pp": 43.5,
        "i_t": 10.0,
        "c_pf": 850,
        "p_ppm_w": 400,
        "polarity_default": "bidirectional",
    },
    "Custom": {
        "v_rwm": 60.0,
        "v_br_min": 66.7,
        "v_br_max": 73.7,
        "v_c": 96.8,
        "i_pp": 6.2,
        "i_t": 1.0,
        "c_pf": 380,
        "p_ppm_w": 600,
    },
}


# ============================================================================
# MCU INTERNAL ESD CLAMP DIODE (STM32 silicon)
# ============================================================================
# Represents the forward path from an I/O pin to VDD through the upper
# internal ESD diode. Current into this path = "injection current".
# These values are STM32-class silicon-CMOS typicals; revisit if porting to
# other MCU families with different ESD structures (e.g. 5V-tolerant pins).
INTERNAL_ESD_VF = 0.6   # V — silicon diode forward voltage threshold
INTERNAL_ESD_R  = 100   # Ω — internal series resistance of the ESD path

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
# APPLICATION DEFAULTS
# ============================================================================
DEFAULT_VALUES = {
    "resistors": {
        "r1": {"value": 10, "unit": "k\u03a9", "rating_mw": 200, "tolerance_pct": 1},
        "r2": {"value": 18, "unit": "k\u03a9", "rating_mw": 100, "tolerance_pct": 1},
        "r_series": {"value": 0, "unit": "\u03a9", "rating_mw": None, "tolerance_pct": None},
    },
    "zener": {
        "preset": "BZB984-C3V3",
        "vz_nom": 3.3, "vz_min": 3.1, "vz_max": 3.5, "tolerance_pct": 5,
        "izt_ma": 5, "zzt_typ": 85, "zzt_max": 95,
        "zzk_typ": 350, "zzk_max": 600, "izk_ma": 1, "ptot_mw": 265,
    },
    "mcu": {
        "vdd": 3.3, "vdda": 3.3, "vref": 3.3,
        "v_recommended_max": 3.6, "v_absolute_max": 4.0,
        "safe_injection_ma": 1.0,
    },
    "system": {
        "v_input_max": 30, "v_analog_fullscale": 5.1,
        "v_logic_high_min": 3.8, "v_logic_low_max": 1.0,
    },
    "bandwidth": {
        "r_series_bw": 100, "c_diode_pf": 95, "c_pin_pf": 10, "c_stray_pf": 3,
        "vil": 0.99, "vih": 2.31,
        "f_peripheral_mhz": 170, "n_samples": 3,
        "counter_bits": 16, "counter_signed": False, "f_read_hz": 1000,
    },
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
FILE_FORMAT_VERSION = "2.0"
