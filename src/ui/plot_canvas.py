"""
Encapsulated Matplotlib plotting logic for the V_mcu vs V_input chart.
Decoupled from the main UI class and from the solver: it receives plain
lists from AppState (which sweeps the solver's pin-voltage function) and
draws them on its own canvas. When no curve can be computed the axes are
cleared and a message says which inputs are needed.
"""
from __future__ import annotations

import textwrap

import customtkinter as ctk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


class PlotCanvas(ctk.CTkFrame):
    """Embeddable plot widget showing V_mcu vs V_input with threshold lines."""

    def __init__(self, parent):
        super().__init__(parent)
        self._last = None
        self.message = ""
        self._build()

    def _build(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(header, text="V_mcu vs V_input", font=("", 14, "bold")).pack(side="left")

        ctk.CTkLabel(header, text="Theme:").pack(side="right", padx=(10, 2))
        self.theme_var = ctk.CTkOptionMenu(
            header, values=["Dark", "Light"], width=80,
            command=self._on_theme_change
        )
        self.theme_var.set("Dark")
        self.theme_var.pack(side="right")

        self.fig = Figure(figsize=(8, 4))
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
        is_dark = self.theme_var.get() == "Dark"
        bg = "#2b2b2b" if is_dark else "white"
        tc = "white" if is_dark else "black"
        ga = 0.3 if is_dark else 0.4
        self.fig.patch.set_facecolor(bg)
        self.ax.set_facecolor(bg)
        self.ax.tick_params(colors=tc)
        for spine in self.ax.spines.values():
            spine.set_color(tc)

        curves = [k for k in ("v_mcu_typ", "v_mcu_worst") if k in pd]
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
        if "v_mcu_typ" in pd:
            self.ax.plot(v_in, pd["v_mcu_typ"], "c-", linewidth=2, label="V_mcu (typical)")
        if "v_mcu_worst" in pd:
            self.ax.plot(v_in, pd["v_mcu_worst"], color="orange", linewidth=2,
                         linestyle="-", label="V_mcuH (worst case)")

        # Threshold lines (only those whose inputs are present)
        dash_seq = (5, 3)
        y_top = max(max(pd[k]) for k in curves) + 0.2
        y_bottom = min(0.0, min(min(pd[k]) for k in curves))
        for key, color, label, phase in (("vdd", "green", "VDD", 0),
                                         ("v_rec_max", "gold", "Safe Max", 4),
                                         ("v_abs_max", "red", "Abs. Max", 2)):
            y = pd.get(key)
            if y is None:
                continue
            line = self.ax.axhline(y=y, color=color, linewidth=1.5, alpha=0.9,
                                   label=f"{label} ({y}V)")
            line.set_linestyle((phase, dash_seq))
            y_top = max(y_top, y + 0.5)

        self.ax.set_xlabel("V_input (V)", color=tc)
        self.ax.set_ylabel("V_mcu (V)", color=tc)
        self.ax.set_xlim(pd["vin_min"], pd["vin_max"])
        self.ax.set_ylim(y_bottom - 0.2 if y_bottom < 0 else 0, y_top)
        self.ax.grid(True, alpha=ga, color=tc)
        self.ax.legend(loc="lower right", fontsize=10, facecolor=bg, labelcolor=tc)
        if message:
            self.ax.set_title(textwrap.fill(message, 110), color="orange", fontsize=9)
        self.fig.tight_layout()
        self.canvas.draw_idle()
