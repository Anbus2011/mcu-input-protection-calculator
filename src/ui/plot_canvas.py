"""
Encapsulated Matplotlib plotting logic for the V_mcu vs V_input chart.
Decoupled from the main UI class — receives data arrays, draws to its own canvas.
"""
from __future__ import annotations

import customtkinter as ctk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np

from src.models.circuit_model import CalculationResult


class PlotCanvas(ctk.CTkFrame):
    """Embeddable plot widget showing V_mcu vs V_input with threshold lines."""

    def __init__(self, parent):
        super().__init__(parent)
        self._build()

    def _build(self):
        # Header with theme toggle
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

        # Matplotlib figure
        self.fig, self.ax = plt.subplots(figsize=(8, 4))
        self.fig.patch.set_facecolor("#2b2b2b")
        self.ax.set_facecolor("#2b2b2b")
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=5)

        self._last_result: CalculationResult | None = None

    def _on_theme_change(self, value):
        if self._last_result is not None:
            self.refresh(self._last_result)

    def refresh(self, result: CalculationResult):
        self._last_result = result
        pd = result.plot_data
        if not pd:
            return

        self.ax.clear()

        is_dark = self.theme_var.get() == "Dark"
        bg = "#2b2b2b" if is_dark else "white"
        tc = "white" if is_dark else "black"
        ga = 0.3 if is_dark else 0.4

        self.fig.patch.set_facecolor(bg)
        self.ax.set_facecolor(bg)

        v_in = pd["v_in"]
        v_mcu_typ = pd["v_mcu_typ"]
        v_mcu_worst = pd["v_mcu_worst"]
        vdd = pd["vdd"]
        v_rec_max = pd["v_rec_max"]
        v_abs_max = pd["v_abs_max"]
        vin_max = pd["vin_max"]

        # Curves
        self.ax.plot(v_in, v_mcu_typ, "c-", linewidth=2, label="V_mcu (typical)")
        self.ax.plot(v_in, v_mcu_worst, color="orange", linewidth=2, linestyle="-",
                     label="V_mcu (worst)")

        # Threshold lines with offset dash phases
        dash_seq = (5, 3)
        vdd_line = self.ax.axhline(y=vdd, color="green", linewidth=1.5, alpha=0.9,
                                   label=f"VDD ({vdd}V)")
        vdd_line.set_linestyle((0, dash_seq))
        rec_line = self.ax.axhline(y=v_rec_max, color="gold", linewidth=1.5, alpha=0.9,
                                   label=f"Safe Max ({v_rec_max}V)")
        rec_line.set_linestyle((4, dash_seq))
        abs_line = self.ax.axhline(y=v_abs_max, color="red", linewidth=1.5, alpha=0.9,
                                   label=f"Abs. Max ({v_abs_max}V)")
        abs_line.set_linestyle((2, dash_seq))

        # Formatting
        self.ax.set_xlabel("V_input (V)", color=tc)
        self.ax.set_ylabel("V_mcu (V)", color=tc)
        self.ax.set_xlim(0, vin_max)
        self.ax.set_ylim(0, max(v_abs_max + 0.5, float(np.max(v_mcu_worst)) + 0.2))
        self.ax.grid(True, alpha=ga, color=tc)
        self.ax.legend(loc="lower right", fontsize=10, facecolor=bg, labelcolor=tc)
        self.ax.tick_params(colors=tc)
        for spine in self.ax.spines.values():
            spine.set_color(tc)

        self.fig.tight_layout()
        self.canvas.draw()
