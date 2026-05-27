"""
Primary application window — the top-level CTk container.
Owns the menu bar, input panels, output panels, and the plot canvas.
Wires everything together through the AppState controller.
"""
from __future__ import annotations

import os
import sys
import tempfile

import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image, ImageDraw, ImageTk

from src.core.app_state import AppState
from src.models.circuit_model import CalculationResult
from src.models.bandwidth_model import BandwidthResult
from src.ui.input_panels import (
    ResistorPanel, ClampPanel, McuPanel, SystemPanel, NotesPanel,
    BandwidthInputPanel,
)
from src.ui.output_panels import (
    ComponentsTab, SafetyTab, OperatingTab, BandwidthTab,
)
from src.ui.plot_canvas import PlotCanvas


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window setup
        self.title("MCU Input Protection Calculator - Untitled")
        self.geometry("1400x900")
        self.minsize(1200, 800)

        # Application icon (resistor symbol)
        self._set_icon()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # State / controller
        self.app_state = AppState()
        self.app_state.set_title_callback(self._on_title_changed)
        self.app_state.set_results_callback(self._on_results_changed)
        self.app_state.set_bandwidth_callback(self._on_bandwidth_changed)

        # Build UI
        self._create_menu()
        self._create_layout()

        # Close handler
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Initial calc so output tabs (incl. bandwidth) populate at startup
        # instead of showing "--" until the user touches an input.
        self.app_state.recalculate()

    # ── Icon ──────────────────────────────────────────────────────────────

    def _set_icon(self):
        """Draw a resistor zigzag icon and set it as the window icon."""
        try:
            # Build the resistor image at multiple sizes for crisp display
            sizes = [16, 32, 48, 64, 256]
            images = []
            for size in sizes:
                img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)
                s = size / 64.0  # scale factor

                # Blue rounded-rect background
                r = max(1, int(8 * s))
                draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=r,
                                       fill=(43, 94, 167))

                # Resistor zigzag path scaled
                points = [
                    (8, 32), (16, 32),
                    (18, 24), (22, 40), (26, 24), (30, 40),
                    (34, 24), (38, 40), (42, 24), (46, 40),
                    (48, 32), (56, 32),
                ]
                scaled = [(x * s, y * s) for x, y in points]
                w = max(1, int(3 * s))
                draw.line(scaled, fill="white", width=w, joint="curve")

                # Terminal dots
                dr = max(1, 3 * s)
                cx1, cx2, cy = 8 * s, 56 * s, 32 * s
                draw.ellipse([cx1 - dr, cy - dr, cx1 + dr, cy + dr], fill="white")
                draw.ellipse([cx2 - dr, cy - dr, cx2 + dr, cy + dr], fill="white")
                images.append(img)

            # Save as .ico for Windows taskbar support
            ico_path = os.path.join(tempfile.gettempdir(), "mcu_calc_icon.ico")
            images[-1].save(ico_path, format="ICO",
                            sizes=[(s, s) for s in sizes],
                            append_images=images[:-1])
            self.iconbitmap(ico_path)

            # Also set iconphoto for title bar
            self._icon_photo = ImageTk.PhotoImage(images[3])  # 64px
            self.iconphoto(False, self._icon_photo)
        except Exception:
            pass

    # ── Toolbar ────────────────────────────────────────────────────────────

    def _create_menu(self):
        self.toolbar = ctk.CTkFrame(self, height=36, corner_radius=0)
        self.toolbar.pack(fill="x", side="top")
        self.toolbar.pack_propagate(False)

        btn_style = {"height": 28, "corner_radius": 6,
                     "fg_color": "#2B5EA7", "hover_color": "#1E4A8A"}

        ctk.CTkButton(
            self.toolbar, text="New Design", width=100,
            command=self._file_new, **btn_style
        ).pack(side="left", padx=(8, 4), pady=4)

        ctk.CTkButton(
            self.toolbar, text="Load Design...", width=120,
            command=self._file_open, **btn_style
        ).pack(side="left", padx=4, pady=4)

        ctk.CTkButton(
            self.toolbar, text="Save Design", width=110,
            command=self._file_save, **btn_style
        ).pack(side="left", padx=4, pady=4)

        ctk.CTkButton(
            self.toolbar, text="Save Design As...", width=130,
            command=self._file_save_as, **btn_style
        ).pack(side="left", padx=4, pady=4)

        self.bind("<Control-n>", lambda e: self._file_new())
        self.bind("<Control-o>", lambda e: self._file_open())
        self.bind("<Control-s>", lambda e: self._file_save())
        self.bind("<Control-S>", lambda e: self._file_save_as())

    # ── File operations ───────────────────────────────────────────────────

    def _check_save(self) -> bool:
        if not self.app_state.is_dirty:
            return True
        result = messagebox.askyesnocancel("Unsaved Changes",
                                           "Do you want to save changes before continuing?")
        if result is None:
            return False
        elif result:
            return self._file_save()
        return True

    def _file_new(self):
        if not self._check_save():
            return
        self.app_state.file_new()
        self.app_state.ignore_changes = True
        self.resistor_panel.clear_fields()
        self.clamp_panel.clear_fields()
        self.mcu_panel.clear_fields()
        self.system_panel.clear_fields()
        self.notes_panel.clear_fields()
        self.app_state.ignore_changes = False

    def _file_open(self):
        if not self._check_save():
            return
        filepath = filedialog.askopenfilename(
            title="Open Divider Calculation",
            filetypes=[("Divider files", "*.div"), ("All files", "*.*")]
        )
        if not filepath:
            return
        try:
            data = self.app_state.open_file(filepath)
            self.app_state.ignore_changes = True
            self.resistor_panel.load_from_data(data)
            self.clamp_panel.load_from_data(data)
            self.mcu_panel.load_from_data(data)
            self.system_panel.load_from_data(data)
            self.notes_panel.load_from_data(data)
            self.app_state.ignore_changes = False
            self._push_all_to_state()
            self.app_state.recalculate()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open file:\n{e}")

    def _file_save(self) -> bool:
        self._push_all_to_state()
        if self.app_state.current_file:
            return self.app_state.save_to_file(self.app_state.current_file)
        return self._file_save_as()

    def _file_save_as(self) -> bool:
        self._push_all_to_state()
        filepath = filedialog.asksaveasfilename(
            title="Save Divider Calculation",
            defaultextension=".div",
            filetypes=[("Divider files", "*.div"), ("All files", "*.*")]
        )
        if not filepath:
            return False
        ok = self.app_state.save_to_file(filepath)
        if not ok:
            messagebox.showerror("Error", "Failed to save file.")
        return ok

    def _on_close(self):
        if self._check_save():
            # Cancel all pending after() callbacks before destroy.
            # CustomTkinter registers internal after-handles (DPI scaling, etc.)
            # that fire on dead widgets if we destroy() without cancelling.
            try:
                for after_id in self.tk.eval("after info").split():
                    try:
                        self.after_cancel(after_id)
                    except Exception:
                        pass
            except Exception:
                pass
            self.quit()
            # Defensive: CustomTkinter's destroy() override raises
            # TclError("can't delete Tcl command") on Python 3.14 due to
            # an upstream CTk bug (double-delete of a Tcl command during
            # widget teardown). On Python 3.12/3.13 destroy() succeeds
            # cleanly and this try/except is a no-op. Remove the except
            # once CustomTkinter ships a Python 3.14 fix.
            try:
                self.destroy()
            except Exception:
                pass

    # ── Layout ────────────────────────────────────────────────────────────

    def _create_layout(self):
        main = ctk.CTkFrame(self)
        main.pack(fill="both", expand=True, padx=5, pady=5)

        # Left panel — inputs
        left = ctk.CTkScrollableFrame(main, width=450)
        left.pack(side="left", fill="y", padx=(0, 5))

        self.resistor_panel = ResistorPanel(left, self.app_state)
        self.resistor_panel.pack(fill="x", pady=5)

        self.clamp_panel = ClampPanel(left, self.app_state)
        self.clamp_panel.pack(fill="x", pady=5)

        self.mcu_panel = McuPanel(left, self.app_state)
        self.mcu_panel.pack(fill="x", pady=5)

        self.system_panel = SystemPanel(left, self.app_state)
        self.system_panel.pack(fill="x", pady=5)

        self.notes_panel = NotesPanel(left, self.app_state)
        self.notes_panel.pack(fill="x", pady=5)

        # Right panel — outputs
        right = ctk.CTkFrame(main)
        right.pack(side="right", fill="both", expand=True)

        # Tabs
        self.tabs = ctk.CTkTabview(right, height=280)
        self.tabs.pack(fill="x", padx=5, pady=5)

        tab_comp = self.tabs.add("Component Analysis")
        tab_safety = self.tabs.add("MCU Input")
        tab_op = self.tabs.add("Input Levels")
        tab_bw = self.tabs.add("Signal Bandwidth")

        self.components_tab = ComponentsTab(tab_comp)
        self.safety_tab = SafetyTab(tab_safety)
        self.operating_tab = OperatingTab(tab_op)

        # Bandwidth tab: split into input (left) and results (right)
        bw_container = ctk.CTkFrame(tab_bw, fg_color="transparent")
        bw_container.pack(fill="both", expand=True)

        bw_left = ctk.CTkScrollableFrame(bw_container, width=380)
        bw_left.pack(side="left", fill="y", padx=(0, 5))
        self.bw_input_panel = BandwidthInputPanel(bw_left, self.app_state)
        self.bw_input_panel.pack(fill="x")

        bw_right = ctk.CTkScrollableFrame(bw_container)
        bw_right.pack(side="right", fill="both", expand=True)
        self.bandwidth_tab = BandwidthTab(bw_right)

        # Plot
        plot_frame = ctk.CTkFrame(right)
        plot_frame.pack(fill="both", expand=True, padx=5, pady=5)
        self.plot = PlotCanvas(plot_frame)
        self.plot.pack(fill="both", expand=True)

    # ── State → UI synchronisation ────────────────────────────────────────

    def _push_all_to_state(self):
        """Push current UI values into AppState (without triggering recalc)."""
        self.resistor_panel.push_to_state()
        self.clamp_panel.push_to_state()
        self.mcu_panel.push_to_state()
        self.system_panel.push_to_state()
        self.notes_panel.push_to_state()
        self.bw_input_panel.push_to_state()

    def _on_title_changed(self, title: str):
        self.title(title)

    def _on_results_changed(self, result: CalculationResult):
        self.components_tab.refresh(result)
        self.safety_tab.refresh(result, self.app_state.mcu.safe_injection_ma)
        self.operating_tab.refresh(result)
        self.plot.refresh(result)
        # Auto-update bandwidth tab with values from other panels
        self.bw_input_panel.refresh_auto_values()
        self.bw_input_panel.push_to_state()
        self.app_state.recalculate_bandwidth()

    def _on_bandwidth_changed(self, result: BandwidthResult):
        self.bandwidth_tab.refresh(result)
