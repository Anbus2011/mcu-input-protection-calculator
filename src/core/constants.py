"""
Constants for the MCU Input Protection Calculator.

There are no part presets here: every clamp diode and MCU value comes from
the .div file or from the user typing it.
"""
from src.core.div_format import FORMAT_VERSION
from src.models.clamp_solver import RESISTOR_UNITS  # noqa: F401  (re-exported)

# ============================================================================
# RESISTOR UNITS
# ============================================================================
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
    # Engineering estimate for a short PCB trace (2-5 pF typical); no datasheet source
    "c_stray_pf": 3,
    # owner's example, 2026-11-09: 1 MHz reliable, 1.5 MHz may work
    "margin_factor": 1.5,
}

# ============================================================================
# PLOT
# ============================================================================
PLOT_POINTS = 200

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
FILE_FORMAT_VERSION = FORMAT_VERSION
