"""
Encapsulated Matplotlib plotting logic for the V_mcu vs V_input chart.
Decoupled from the main UI class and from the solver: it receives plain
lists from AppState (which sweeps the solver's pin-voltage function) and
draws them on its own canvas. When no curve can be computed the axes are
cleared and a message says which inputs are needed.

Drawn: the typical curve, the lowest and the highest of the corners (V_mcuL
and V_mcuH of the tables) with the band between them shaded, and the
thresholds as horizontal lines: Abs. Max, Safe Max and VDD dashed, VIH and
VIL thin and labelled on the line. The legend is outside the plot area, to
its right, in the order the lines appear from top to bottom.
"""
from __future__ import annotations

import textwrap

import customtkinter as ctk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


# Colours: (dark theme, light theme)
SURFACE = ("#2b2b2b", "white")
TEXT = ("white", "black")
# key in plot_data, legend label, colour
CURVES = (
    ("v_mcu_typ", "V_mcu (typical)", ("c", "c")),
    ("v_mcu_worst", "V_mcuH (worst case)", ("orange", "orange")),
    ("v_mcu_low", "V_mcuL (worst case)", ("#9085e9", "#6250d6")),
)
# key, name, colour, dash phase (so that lines that coincide stay apart)
LIMITS = (
    ("v_abs_max", "Abs. Max", "red", 2),
    ("v_rec_max", "Safe Max", "gold", 4),
    ("vdd", "VDD", "green", 0),
)
# key, name, dash pattern: the logic thresholds, thin
LOGIC_LEVELS = (("vih", "VIH", (0, (6, 2, 1, 2))), ("vil", "VIL", (0, (1, 2))))
LOGIC_COLOR = "#d55181"
LOGIC_LINEWIDTH = 1.0
CURVE_LINEWIDTH = 2.0
BAND_ALPHA = 0.14
LEGEND_ORDER = ("v_mcu_worst", "v_mcu_typ", "v_mcu_low",
                "v_abs_max", "v_rec_max", "vdd", "vih", "vil")


class PlotCanvas(ctk.CTkFrame):
    """Embeddable plot widget showing V_mcu vs V_input with threshold lines."""

    def __init__(self, parent):
        super().__init__(parent)
        self._last = None
        self.message = ""
        self.lines: dict = {}       # plot_data key -> the line drawn for it
        self.band = None            # the shading between V_mcuL and V_mcuH
        self.level_labels: dict = {}  # "vih" / "vil" -> the label on its line
        self._build()

    def _build(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(header, text="V_mcu vs V_input", font=("", 14, "bold")).pack(side="left")

        # Packed from the right: the drop-down first, so "Theme:" sits before it
        self.theme_var = ctk.CTkOptionMenu(
            header, values=["Dark", "Light"], width=80,
            command=self._on_theme_change
        )
        self.theme_var.set("Dark")
        self.theme_var.pack(side="right")
        self.theme_label = ctk.CTkLabel(header, text="Theme:")
        self.theme_label.pack(side="right", padx=(10, 6))

        # Constrained layout makes room for the legend outside the axes
        self.fig = Figure(figsize=(8, 4), layout="constrained")
        self.ax = self.fig.add_subplot(111)
        self.fig.patch.set_facecolor("#2b2b2b")
        self.ax.set_facecolor("#2b2b2b")
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=5)

    def _on_theme_change(self, value):
        if self._last is not None:
            self.refresh(*self._last)

    @property
    def has_curves(self) -> bool:
        return len(self.ax.lines) > 0

    def refresh(self, plot_data: dict, message: str = ""):
        """Draw the curves in *plot_data* (AppState.plot_data: plain lists);
        if there are none, clear the plot and show *message* (which inputs
        are needed)."""
        self._last = (plot_data, message)
        pd = plot_data or {}

        self.ax.clear()
        self.lines, self.band, self.level_labels = {}, None, {}
        theme = 0 if self.theme_var.get() == "Dark" else 1
        bg, tc = SURFACE[theme], TEXT[theme]
        ga = 0.3 if theme == 0 else 0.4
        self.fig.patch.set_facecolor(bg)
        self.ax.set_facecolor(bg)
        self.ax.tick_params(colors=tc)
        for spine in self.ax.spines.values():
            spine.set_color(tc)

        curves = [k for k, _label, _color in CURVES if k in pd]
        if not curves:
            self.message = message or "Nothing to plot"
            self.ax.set_xticks([])
            self.ax.set_yticks([])
            self.ax.text(0.5, 0.5, textwrap.fill(self.message, 80), ha="center",
                         va="center", color=tc, transform=self.ax.transAxes)
            self.canvas.draw_idle()
            return
        self.message = message

        v_in = pd["v_in"]
        # The band between the lowest and the highest of the corners
        if "v_mcu_low" in pd and "v_mcu_worst" in pd:
            self.band = self.ax.fill_between(v_in, pd["v_mcu_low"], pd["v_mcu_worst"],
                                             color=tc, alpha=BAND_ALPHA, linewidth=0)
        for key, label, color in CURVES:
            if key in pd:
                self.lines[key], = self.ax.plot(v_in, pd[key], color=color[theme],
                                                linewidth=CURVE_LINEWIDTH, label=label)

        # Threshold lines (only those whose inputs are present)
        dash_seq = (5, 3)
        y_top = max(max(pd[k]) for k in curves) + 0.2
        y_bottom = min(0.0, min(min(pd[k]) for k in curves))
        for key, name, color, phase in LIMITS:
            y = pd.get(key)
            if y is None:
                continue
            line = self.ax.axhline(y=y, color=color, linewidth=1.5, alpha=0.9,
                                   label=f"{name} ({y}V)")
            line.set_linestyle((phase, dash_seq))
            self.lines[key] = line
            y_top = max(y_top, y + 0.5)
        # Logic thresholds: thin lines, each named on the line at its right end
        for key, name, dashes in LOGIC_LEVELS:
            y = pd.get(key)
            if y is None:
                continue
            self.lines[key] = self.ax.axhline(y=y, color=LOGIC_COLOR, linestyle=dashes,
                                              linewidth=LOGIC_LINEWIDTH,
                                              label=f"{name} ({y:.2f}V)")
            self.level_labels[key] = self.ax.annotate(
                name, xy=(1.0, y), xycoords=("axes fraction", "data"),
                xytext=(-4, 2), textcoords="offset points", ha="right", va="bottom",
                color=tc, fontsize=8)

        self.ax.set_xlabel("V_input (V)", color=tc)
        self.ax.set_ylabel("V_mcu (V)", color=tc)
        self.ax.set_xlim(pd["vin_min"], pd["vin_max"])
        self.ax.set_ylim(y_bottom - 0.2 if y_bottom < 0 else 0, y_top)
        self.ax.grid(True, alpha=ga, color=tc)
        # Outside the plot area, so it never covers a curve
        handles = [self.lines[k] for k in LEGEND_ORDER if k in self.lines]
        self.ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.01, 1.0),
                       borderaxespad=0.0, fontsize=9, facecolor=bg, edgecolor=tc,
                       labelcolor=tc)
        if message:
            self.ax.set_title(textwrap.fill(message, 110), color="orange", fontsize=9)
        self.canvas.draw_idle()
