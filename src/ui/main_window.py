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

from src.core.app_state import AppState, LoadError
from src.ui.input_panels import (
    ResistorPanel, ClampDiodePanel, McuPanel, SystemPanel, NotesPanel,
    BandwidthInputPanel, MUTED,
)
from src.ui.output_panels import (
    ComponentsTab, SafetyTab, OperatingTab, BandwidthTab, CHECK_LABELS,
    status_text,
)
from src.models.clamp_solver import FAIL, TIGHT
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
        self.app_state.set_fields_callback(self._sync_fields_from_state)
        self._refresh_pending = False

        # Build UI
        self._create_menu()
        self._create_layout()
        self._refresh_outputs()

        # Close handler
        self.protocol("WM_DELETE_WINDOW", self._on_close)

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
            warnings = self.app_state.open_file(filepath)
        except LoadError as e:
            messagebox.showerror("Can't Open File",
                                 f"{filepath}\n\n{e}\n\nThe current design was not changed.")
            return
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open file:\n{e}")
            return
        if warnings:
            messagebox.showwarning("Loaded With Blank or Unusable Values",
                                   "\n\n".join(warnings))

    def _save_blocked(self) -> bool:
        """Unreadable text blocks saving: say which fields, and return True."""
        bad = self.app_state.unreadable_fields()
        if not bad:
            return False
        lines = "\n".join(f"  • {label}: '{text}'" for label, text in bad)
        messagebox.showerror("Can't Save",
                             "These fields contain text that isn't a valid value. "
                             "Fix or clear them before saving:\n" + lines)
        return True

    def _save_to(self, filepath: str) -> bool:
        ok = self.app_state.save_to_file(filepath)
        if not ok:
            messagebox.showerror("Save Failed",
                                 self.app_state.last_save_error or "Failed to save file.")
        return ok

    def _file_save(self) -> bool:
        if self._save_blocked():
            return False
        if self.app_state.current_file:
            return self._save_to(self.app_state.current_file)
        return self._file_save_as()

    def _file_save_as(self) -> bool:
        if self._save_blocked():
            return False
        filepath = filedialog.asksaveasfilename(
            title="Save Divider Calculation",
            defaultextension=".div",
            filetypes=[("Divider files", "*.div"), ("All files", "*.*")]
        )
        if not filepath:
            return False
        return self._save_to(filepath)

    def _on_close(self):
        if self._check_save():
            self.destroy()

    # ── Layout ────────────────────────────────────────────────────────────

    def _create_layout(self):
        main = ctk.CTkFrame(self)
        main.pack(fill="both", expand=True, padx=5, pady=5)

        # Left panel — inputs
        left = ctk.CTkScrollableFrame(main, width=470)
        left.pack(side="left", fill="y", padx=(0, 5))

        self.resistor_panel = ResistorPanel(left, self.app_state)
        self.resistor_panel.pack(fill="x", pady=5)

        self.diode_panel = ClampDiodePanel(left, self.app_state)
        self.diode_panel.pack(fill="x", pady=5)

        self.mcu_panel = McuPanel(left, self.app_state)
        self.mcu_panel.pack(fill="x", pady=5)

        self.system_panel = SystemPanel(left, self.app_state)
        self.system_panel.pack(fill="x", pady=5)

        self.notes_panel = NotesPanel(left, self.app_state)
        self.notes_panel.pack(fill="x", pady=5)

        self.field_panels = [self.resistor_panel, self.diode_panel, self.mcu_panel,
                             self.system_panel]

        # Right panel — outputs
        right = ctk.CTkFrame(main)
        right.pack(side="right", fill="both", expand=True)

        # Overall verdict: the worst status among the checks
        self.verdict = ctk.CTkLabel(right, text="", anchor="w", justify="left",
                                    wraplength=880, font=("", 14, "bold"))
        self.verdict.pack(fill="x", padx=10, pady=(5, 0))

        # Input report: what's needed, what's wrong, solver warnings
        self.banner = ctk.CTkLabel(right, text="", anchor="w", justify="left",
                                   wraplength=880, text_color="orange")
        self.banner.pack(fill="x", padx=10, pady=(2, 0))

        # Tabs
        self.tabs = ctk.CTkTabview(right, height=280)
        self.tabs.pack(fill="x", padx=5, pady=5)

        tab_comp = self.tabs.add("Component Analysis")
        tab_safety = self.tabs.add("MCU Input")
        tab_op = self.tabs.add("Input Levels")
        tab_bw = self.tabs.add("Signal Bandwidth")

        self.components_tab = ComponentsTab(tab_comp)
        safety_scroll = ctk.CTkScrollableFrame(tab_safety, fg_color="transparent",
                                               height=300)
        safety_scroll.pack(fill="both", expand=True)
        self.safety_tab = SafetyTab(safety_scroll)
        self.operating_tab = OperatingTab(tab_op)

        # Bandwidth tab: split into input (left) and results (right)
        bw_container = ctk.CTkFrame(tab_bw, fg_color="transparent")
        bw_container.pack(fill="both", expand=True)

        bw_left = ctk.CTkScrollableFrame(bw_container, width=380)
        bw_left.pack(side="left", fill="y", padx=(0, 5))
        self.bw_input_panel = BandwidthInputPanel(bw_left, self.app_state)
        self.bw_input_panel.pack(fill="x")
        self.field_panels.append(self.bw_input_panel)

        bw_right = ctk.CTkScrollableFrame(bw_container)
        bw_right.pack(side="right", fill="both", expand=True)
        self.bandwidth_tab = BandwidthTab(bw_right)

        # Plot
        plot_frame = ctk.CTkFrame(right)
        plot_frame.pack(fill="both", expand=True, padx=5, pady=5)
        self.plot = PlotCanvas(plot_frame)
        self.plot.pack(fill="both", expand=True)

    # ── State → UI synchronisation ────────────────────────────────────────

    def _sync_fields_from_state(self):
        """AppState changed field text itself (load, new, fill, table rows)."""
        for panel in self.field_panels:
            panel.sync_from_state()
        self.notes_panel.sync_from_state()

    def _on_title_changed(self, title: str):
        self.title(title)

    def _on_results_changed(self, results: dict):
        self._schedule_refresh()

    def _schedule_refresh(self):
        """Coalesce bursts of edits into one redraw when Tk is idle."""
        if not self._refresh_pending:
            self._refresh_pending = True
            self.after_idle(self._refresh_outputs)

    def _refresh_outputs(self):
        self._refresh_pending = False
        s = self.app_state
        self.components_tab.refresh(s)
        self.safety_tab.refresh(s)
        self.operating_tab.refresh(s)
        self.bandwidth_tab.refresh(s)
        self.bw_input_panel.refresh_derived()

        # Overall verdict, naming the checks that fail or are tight
        verdict = s.results["verdict"]
        text, color = status_text(verdict)
        named = [CHECK_LABELS[c["id"]] for c in s.results["checks"]
                 if c["status"] == verdict and verdict in (FAIL, TIGHT)]
        self.verdict.configure(
            text=f"Overall verdict: {text}" + (f"  ({', '.join(named)})" if named else ""),
            text_color=color)

        lines = s.report.lines()
        self.banner.configure(text="\n".join(lines) if lines else "All inputs present.",
                              text_color="orange" if lines else MUTED)
        self.plot.refresh(s.plot_data, s.plot_message)
