"""
Headless PNG of the pin-voltage plot, for the MCP server (skill/server.py).

Lists in, PNG bytes out. The lists are AppState's plot sweep
(AppState.plot_data): this module sweeps nothing and solves nothing, so the
picture cannot disagree with the app's plot or with the tables.

Drawn, as in the app's plot: the typical curve, the lowest and the highest
of the corners (V_mcuL and V_mcuH) with the band between them shaded, Abs.
Max, Safe Max and VDD as dashed lines, VIH and VIL as thin lines named at
their right end. A curve or line whose inputs are blank is left out.

matplotlib's Agg canvas only: no window, no pyplot, no Tk, no customtkinter.
"""
from __future__ import annotations

import io
import textwrap

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

SURFACE = "white"
INK = "#1f1f1f"
FIGURE_SIZE_IN = (9.0, 4.5)
DPI = 110

# key in plot_data, legend label, colour. The hues are the app's (cyan,
# orange, violet), at steps that stay readable on a white surface.
CURVES = (
    ("v_mcu_typ", "V_mcu (typical)", "#0099aa"),
    ("v_mcu_worst", "V_mcuH (highest corner)", "#d9730d"),
    ("v_mcu_low", "V_mcuL (lowest corner)", "#6250d6"),
)
# key, name, colour, dash phase (so that lines that coincide stay apart)
LIMITS = (
    ("v_abs_max", "Abs. Max", "#d03b3b", 2),
    ("v_rec_max", "Safe Max", "#b8860b", 4),
    ("vdd", "VDD", "#2e8b57", 0),
)
# key, name, dash pattern: the logic thresholds, thin
LOGIC_LEVELS = (("vih", "VIH", (0, (6, 2, 1, 2))), ("vil", "VIL", (0, (1, 2))))
LOGIC_COLOR = "#c2386b"
LEGEND_ORDER = ("v_mcu_worst", "v_mcu_typ", "v_mcu_low",
                "v_abs_max", "v_rec_max", "vdd", "vih", "vil")
CURVE_LINEWIDTH = 2.0
BAND_ALPHA = 0.12


def render_png(plot_data: dict, message: str = "") -> bytes:
    """PNG bytes of V_mcu against V_input, from AppState.plot_data. *message*
    (AppState.plot_message: which curve is missing and why) is drawn above
    the plot. Raises ValueError when plot_data holds no curve."""
    curves = [key for key, _label, _color in CURVES if key in plot_data]
    if not curves:
        raise ValueError("no curve to draw")

    fig = Figure(figsize=FIGURE_SIZE_IN, dpi=DPI, layout="constrained",
                 facecolor=SURFACE)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    ax.set_facecolor(SURFACE)

    v_in = plot_data["v_in"]
    lines = {}
    if "v_mcu_low" in plot_data and "v_mcu_worst" in plot_data:
        ax.fill_between(v_in, plot_data["v_mcu_low"], plot_data["v_mcu_worst"],
                        color=INK, alpha=BAND_ALPHA, linewidth=0)
    for key, label, color in CURVES:
        if key in plot_data:
            lines[key], = ax.plot(v_in, plot_data[key], color=color,
                                  linewidth=CURVE_LINEWIDTH, label=label)

    y_top = max(max(plot_data[k]) for k in curves) + 0.2
    y_bottom = min(0.0, min(min(plot_data[k]) for k in curves))
    for key, name, color, phase in LIMITS:
        y = plot_data.get(key)
        if y is None:
            continue
        lines[key] = ax.axhline(y=y, color=color, linewidth=1.5,
                                linestyle=(phase, (5, 3)), label=f"{name} ({y:g} V)")
        y_top = max(y_top, y + 0.5)
    for key, name, dashes in LOGIC_LEVELS:
        y = plot_data.get(key)
        if y is None:
            continue
        lines[key] = ax.axhline(y=y, color=LOGIC_COLOR, linestyle=dashes,
                                linewidth=1.0, label=f"{name} ({y:.2f} V)")
        ax.annotate(name, xy=(1.0, y), xycoords=("axes fraction", "data"),
                    xytext=(-4, 2), textcoords="offset points", ha="right",
                    va="bottom", color=INK, fontsize=8)

    ax.set_xlabel("V_input (V)", color=INK)
    ax.set_ylabel("V_mcu (V)", color=INK)
    ax.set_xlim(plot_data["vin_min"], plot_data["vin_max"])
    ax.set_ylim(y_bottom - 0.2 if y_bottom < 0 else 0, y_top)
    ax.tick_params(colors=INK)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(True, alpha=0.25, color=INK, linewidth=0.6)
    # Outside the plot area, so it never covers a curve
    ax.legend(handles=[lines[k] for k in LEGEND_ORDER if k in lines],
              loc="upper left", bbox_to_anchor=(1.01, 1.0), borderaxespad=0.0,
              fontsize=9, frameon=False, labelcolor=INK)
    if message:
        ax.set_title(textwrap.fill(message, 110), color="#b3470a", fontsize=9)

    out = io.BytesIO()
    fig.savefig(out, format="png")
    return out.getvalue()
