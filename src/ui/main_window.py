"""
Primary application window — the top-level CTk container.
Owns the menu bar, input panels, output panels, and the plot canvas.
Wires everything together through the AppState controller.
"""
from __future__ import annotations

import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image, ImageDraw, ImageTk

from src.core.app_state import AppState
from src.models.circuit_model import CalculationResult
from src.models.bandwidth_model import BandwidthResult
from src.ui.input_panels import (
    ResistorPanel, ZenerPanel, McuPanel, SystemPanel, NotesPanel,
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
        self.title("Divider Calculator v1.1 - Untitled")
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

    # ── Icon ──────────────────────────────────────────────────────────────

    def _set_icon(self):
        """Draw a resistor zigzag icon and set it as the window icon."""
        try:
            size = 64
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            # Blue rounded-rect background
            draw.rounded_rectangle([0, 0, 63, 63], radius=8, fill=(43, 94, 167))

            # Resistor zigzag path: lead-in, 4 zigzag peaks, lead-out
            points = [
                (8, 32), (16, 32),
                (18, 24), (22, 40), (26, 24), (30, 40),
                (34, 24), (38, 40), (42, 24), (46, 40),
                (48, 32), (56, 32),
            ]
            draw.line(points, fill="white", width=3, joint="curve")

            # Terminal dots
            draw.ellipse([5, 29, 11, 35], fill="white")
            draw.ellipse([53, 29, 59, 35], fill="white")

            self._icon_photo = ImageTk.PhotoImage(img)
            self.iconphoto(False, self._icon_photo)
        except Exception:
            pass

    # ── Menu ──────────────────────────────────────────────────────────────

    def _create_menu(self):
        self.menu_frame = ctk.CTkFrame(self, height=30, corner_radius=0)
        self.menu_frame.pack(fill="x", side="top")
        self.menu_frame.pack_propagate(False)

        self.file_btn = ctk.CTkButton(
            self.menu_frame, text="File \u25bc", width=60, height=24,
            command=self._toggle_file_menu, fg_color="transparent",
            hover_color=("gray70", "gray30")
        )
        self.file_btn.pack(side="left", padx=5, pady=3)

        self.load_btn = ctk.CTkButton(
            self.menu_frame, text="Load Design...", width=110, height=24,
            command=self._file_open,
            fg_color="#2B5EA7", hover_color="#1E4A8A"
        )
        self.load_btn.pack(side="left", padx=5, pady=3)

        self._file_menu = None
        self._menu_open = False

        self.bind("<Control-o>", lambda e: self._file_open())
        self.bind("<Control-s>", lambda e: self._file_save())
        self.bind("<Control-S>", lambda e: self._file_save_as())

    def _toggle_file_menu(self):
        if self._menu_open:
            self._close_file_menu()
        else:
            self._open_file_menu()

    def _open_file_menu(self):
        if self._file_menu is not None:
            self._close_file_menu()
            return

        self._menu_open = True
        self._file_menu = ctk.CTkFrame(self, corner_radius=5, border_width=1, border_color="gray50")
        self._file_menu.place(x=5, y=33)

        items = [
            ("New", "Ctrl+N", self._file_new),
            ("Open...", "Ctrl+O", self._file_open),
            ("Save", "Ctrl+S", self._file_save),
            ("Save As...", "Ctrl+Shift+S", self._file_save_as),
        ]

        for label, shortcut, command in items:
            item_frame = ctk.CTkFrame(self._file_menu, fg_color="transparent")
            item_frame.pack(fill="x", padx=2, pady=1)
            ctk.CTkButton(
                item_frame, text=label, width=100, height=26, anchor="w",
                fg_color="transparent", hover_color=("gray70", "gray30"),
                command=lambda c=command: self._menu_action(c)
            ).pack(side="left")
            ctk.CTkLabel(item_frame, text=shortcut, width=80,
                         text_color="gray50", font=("", 12)).pack(side="right", padx=5)

        self.bind("<Button-1>", self._check_menu_click)

    def _check_menu_click(self, event):
        if self._file_menu is None:
            return
        mx = self._file_menu.winfo_rootx()
        my = self._file_menu.winfo_rooty()
        mw = self._file_menu.winfo_width()
        mh = self._file_menu.winfo_height()
        bx = self.file_btn.winfo_rootx()
        by = self.file_btn.winfo_rooty()
        bw = self.file_btn.winfo_width()
        bh = self.file_btn.winfo_height()
        cx, cy = event.x_root, event.y_root
        in_menu = mx <= cx <= mx + mw and my <= cy <= my + mh
        in_btn = bx <= cx <= bx + bw and by <= cy <= by + bh
        if not in_menu and not in_btn:
            self._close_file_menu()

    def _close_file_menu(self):
        self._menu_open = False
        self.unbind("<Button-1>")
        if self._file_menu is not None:
            self._file_menu.destroy()
            self._file_menu = None

    def _menu_action(self, command):
        self._close_file_menu()
        if command:
            self.after(10, command)

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
        self.zener_panel.clear_fields()
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
            self.zener_panel.load_from_data(data)
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
            self.destroy()

    # ── Layout ────────────────────────────────────────────────────────────

    def _create_layout(self):
        main = ctk.CTkFrame(self)
        main.pack(fill="both", expand=True, padx=5, pady=5)

        # Left panel — inputs
        left = ctk.CTkScrollableFrame(main, width=450)
        left.pack(side="left", fill="y", padx=(0, 5))

        self.resistor_panel = ResistorPanel(left, self.app_state)
        self.resistor_panel.pack(fill="x", pady=5)

        self.zener_panel = ZenerPanel(left, self.app_state)
        self.zener_panel.pack(fill="x", pady=5)

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
        self.zener_panel.push_to_state()
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

    def _on_bandwidth_changed(self, result: BandwidthResult):
        self.bandwidth_tab.refresh(result)
