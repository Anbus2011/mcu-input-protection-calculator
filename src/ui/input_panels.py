"""
Input panel classes for the MCU Input Protection Calculator.

Each panel owns its CTk widgets. Every input is bound to a Tk variable whose
write trace forwards the raw text to AppState.set_field (or set_cell for the
clamp-diode tables), so typing, paste, cut, delete, selection and
programmatic changes are all seen. Panels never parse or calculate; AppState
does. sync_from_state() copies AppState's text back into the widgets after
AppState changed it (load, new, fill, table rows, an unticked "checked" box).

The Clamp Diode, MCU and System panels share one grid: a fixed label column,
a field column, a unit column and a "?" column (with the slack between the
unit and the "?"), so every row lines up. The Resistors panel has the same
label column, field column and "?" column; between them each resistor has
its unit, rating and tolerance, named by a header row.
"""
from __future__ import annotations

import tkinter as tk

import customtkinter as ctk
from typing import TYPE_CHECKING

from src.core.app_state import BLANK, NOT_MODELLED, ROWS
from src.core.constants import RESISTOR_UNITS
from src.core.div_format import DIODE_TYPES
from src.models.clamp_solver import ROW_KEYS, TERMINALS

if TYPE_CHECKING:
    from src.core.app_state import AppState


UNIT_CHOICES = list(RESISTOR_UNITS.keys())
NEEDS_INPUT = "needs input"
MUTED = "gray60"

# Column widths of the part panels' grid (Clamp Diode, MCU, System)
LABEL_W, FIELD_W, UNIT_W, HELP_W = 124, 84, 46, 26
HELP_COL = 4            # columns: label, field, unit, slack, "?"

# What a clamp-diode table with no rows says, by state
TABLE_STATE_TEXT = {
    BLANK: "Not filled in: needs input",
    NOT_MODELLED: "Not modelled: current taken as zero",
    ROWS: "",
}
TABLE_TITLES = {
    "forward": "Forward table (anode positive)",
    "reverse": "Reverse table (cathode positive)",
}
TABLE_TIPS = {
    "forward": "The diode with its anode more positive than its cathode.\n"
               "Each row: a current and the voltage across the diode at that\n"
               "current (minimum, typical, maximum). Rows in ascending current.\n"
               "Tick \"Not modelled\" if there is no data for this direction:\n"
               "its current is then taken as zero.",
    "reverse": "The diode with its cathode more positive than its anode: the\n"
               "working direction of a Zener, the leakage direction of a\n"
               "Schottky. Voltages and currents are entered as positive numbers.\n"
               "Tick \"Not modelled\" if there is no data for this direction:\n"
               "its current is then taken as zero.",
}
OTHER_PANELS_NOTE = (
    "The other inputs of this tab are on the left: the diode capacitance in "
    "the Clamp Diode panel, C_pin and the minimum pulse width in the MCU "
    "panel, the logic levels and the required frequency in the System panel.")


# ── Tooltips ──────────────────────────────────────────────────────────────────

class _Tooltip:
    """A tooltip for one widget.

    It appears about half a second after the pointer comes onto the widget
    (not at all if the pointer leaves first), offset from the pointer so it
    is never under it. It goes when the pointer leaves or on a click. Only
    one tooltip is ever shown. install_tooltip_dismissal() also hides it on
    scroll, window focus loss and window move, and the tab view hides it on
    a tab change.
    """

    DELAY_MS = 500
    WATCH_MS = 200
    OFFSET = (16, 20)
    all_texts: list = []     # every tooltip text created (read by the UI tests)
    instances: list = []
    current = None           # the one tooltip that is showing, if any

    def __init__(self, widget: ctk.CTkBaseClass, text: str):
        self.widget = widget
        self.text = text
        self._tw = None
        self._pending = None
        _Tooltip.all_texts.append(text)
        _Tooltip.instances.append(self)
        widget.bind("<Enter>", self.on_enter, add="+")
        widget.bind("<Leave>", self.on_leave, add="+")
        widget.bind("<ButtonPress>", self.on_leave, add="+")

    @property
    def visible(self) -> bool:
        return self._tw is not None

    @property
    def pending(self) -> bool:
        return self._pending is not None

    def on_enter(self, event=None):
        """Pointer came onto the widget: show after DELAY_MS unless it leaves."""
        self.cancel()
        self._pending = self.widget.after(self.DELAY_MS, self._show_if_still_over)

    def on_leave(self, event=None):
        """Pointer left the widget, or it was clicked: cancel and hide."""
        self.cancel()
        self.hide()

    def cancel(self):
        """Drop a tooltip that is waiting to appear."""
        if self._pending is not None:
            try:
                self.widget.after_cancel(self._pending)
            except Exception:
                pass
            self._pending = None

    def _pointer_over(self) -> bool:
        try:
            x, y = self.widget.winfo_pointerxy()
            under = self.widget.winfo_containing(x, y)
        except Exception:
            return False
        while under is not None:
            if under is self.widget:
                return True
            under = getattr(under, "master", None)
        return False

    def _show_if_still_over(self):
        self._pending = None
        if self._pointer_over():
            self.show()
            self._watch()

    def _watch(self):
        """Safety net for a missed <Leave>: hide once the pointer is elsewhere."""
        if not self.visible:
            return
        if not self._pointer_over():
            self.hide()
        else:
            self.widget.after(self.WATCH_MS, self._watch)

    def show(self):
        """Show now, next to the pointer. Any other tooltip is hidden first."""
        _Tooltip.hide_current()
        px, py = self.widget.winfo_pointerxy()
        dark = ctk.get_appearance_mode() == "Dark"
        self._tw = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.attributes("-topmost", True)
        tk.Label(tw, text=self.text, wraplength=320, justify="left", padx=8, pady=6,
                 bg="#333333" if dark else "#e5e5e5", fg="#f0f0f0" if dark else "#101010",
                 relief="solid", borderwidth=1, font=("", 9)).pack()
        tw.update_idletasks()
        # Offset from the pointer, flipped to the other side at a screen edge,
        # so the tooltip is never under the cursor.
        width, height = tw.winfo_reqwidth(), tw.winfo_reqheight()
        x, y = px + self.OFFSET[0], py + self.OFFSET[1]
        if x + width > tw.winfo_screenwidth():
            x = px - self.OFFSET[0] - width
        if y + height > tw.winfo_screenheight():
            y = py - self.OFFSET[1] - height
        self.position = (max(0, x), max(0, y), width, height)
        tw.wm_geometry(f"+{self.position[0]}+{self.position[1]}")
        _Tooltip.current = self

    def hide(self):
        if self._tw is not None:
            try:
                self._tw.destroy()
            except Exception:
                pass
            self._tw = None
        if _Tooltip.current is self:
            _Tooltip.current = None

    @classmethod
    def hide_current(cls, event=None):
        """Hide the tooltip that is showing and cancel any that is waiting."""
        if cls.current is not None:
            cls.current.hide()
        for tip in cls.instances:
            if tip.pending:
                tip.cancel()


def install_tooltip_dismissal(root) -> None:
    """Hide the tooltip on scroll, on any click, when the application loses
    focus and when the window is moved or resized."""
    geometry = {}

    def on_configure(event):
        if event.widget is not root:
            return
        now = (event.x, event.y, event.width, event.height)
        if geometry.get("last") not in (None, now):
            _Tooltip.hide_current()
        geometry["last"] = now

    def on_focus_out(event):
        # Focus moving between widgets of this window is not a loss of focus
        def check():
            try:
                lost = root.focus_displayof() is None
            except Exception:
                lost = True
            if lost:
                _Tooltip.hide_current()
        root.after(1, check)

    for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>", "<ButtonPress>"):
        root.bind_all(sequence, _Tooltip.hide_current, add="+")
    root.bind("<FocusOut>", on_focus_out, add="+")
    root.bind("<Configure>", on_configure, add="+")
    root.tooltip_handlers = {"configure": on_configure, "focus_out": on_focus_out}


def _help_btn(parent, text: str, pack: bool = True):
    """Create a small '?' button with a tooltip."""
    btn = ctk.CTkLabel(parent, text="?", width=18, height=18,
                       fg_color=("gray75", "gray35"), corner_radius=9,
                       font=("", 11, "bold"), text_color=("gray30", "gray80"),
                       cursor="hand2")
    if pack:
        btn.pack(side="left", padx=(4, 0))
    btn.tooltip = _Tooltip(btn, text)
    return btn


# ── Base panel: field registration and syncing ────────────────────────────────

class _FieldPanel(ctk.CTkFrame):
    def __init__(self, parent, state: AppState, **kw):
        super().__init__(parent, **kw)
        self.app_state = state
        self.vars: dict = {}      # field key -> Tk variable
        self.widgets: dict = {}   # field key -> widget
        self.textboxes: dict = {}  # field key -> CTkTextbox (no Tk variable)
        self.help: dict = {}      # field key -> its "?" button
        self._fit_lines: dict = {}  # field key -> (min, max) lines of a box that grows
        self._build()
        self.sync_from_state()

    def _build(self):
        raise NotImplementedError

    def _add_field(self, key, var, widget):
        self.vars[key] = var
        self.widgets[key] = widget
        var.trace_add("write", lambda *_: self.app_state.set_field(key, var.get()))

    def _entry(self, parent, key, width):
        var = ctk.StringVar(master=self, value="")
        e = ctk.CTkEntry(parent, width=width, textvariable=var)
        self._add_field(key, var, e)
        return e

    def _combo(self, parent, key, values, width=70):
        var = ctk.StringVar(master=self, value="")
        c = ctk.CTkComboBox(parent, values=list(values), width=width,
                            variable=var, state="readonly")
        self._add_field(key, var, c)
        return c

    def _unit_combo(self, parent, key, width=70):
        return self._combo(parent, key, UNIT_CHOICES, width)

    def _checkbox(self, parent, key, text="", width=24):
        var = ctk.StringVar(master=self, value="0")
        c = ctk.CTkCheckBox(parent, text=text, width=width, variable=var,
                            onvalue="1", offvalue="0")
        self._add_field(key, var, c)
        return c

    def _textbox(self, parent, key, lines=2, max_lines=None):
        """Free text over several lines, wrapped at word boundaries and
        scrollable. With *max_lines* the box grows with its text, from
        *lines* up to *max_lines* lines.

        Text widgets have no Tk variable, so edits are caught with
        <<Modified>>, which Tk raises for typing, paste, cut and delete alike."""
        box = ctk.CTkTextbox(parent, height=self._lines_height(lines), wrap="word",
                             border_width=1, border_color=("gray60", "gray40"))

        def on_modified(event=None):
            if not box.edit_modified():
                return
            box.edit_modified(False)
            self.app_state.set_field(key, box.get("1.0", "end-1c"))
            self._fit(key)
        box.bind("<<Modified>>", on_modified)
        self.textboxes[key] = box
        self.widgets[key] = box
        if max_lines:
            self._fit_lines[key] = (lines, max_lines)
            box.bind("<Configure>", lambda e: self._fit(key), add="+")
        return box

    @staticmethod
    def _lines_height(lines: int) -> int:
        """Height (CTk units) of a text box that shows *lines* lines."""
        return 18 * lines + 16

    def wrapped_lines(self, key) -> int:
        """Display lines the text of a text box takes at its present width."""
        box = self.textboxes[key]
        inner = box._textbox
        if inner.winfo_width() > 1:
            counted = inner.count("1.0", "end-1c", "displaylines")
            return (counted[0] if isinstance(counted, tuple) else counted or 0) + 1
        # not laid out yet: estimate from the text
        return sum(len(part) // 50 + 1 for part in box.get("1.0", "end-1c").split("\n"))

    def _fit(self, key):
        """Size a growing text box to its text."""
        if key not in self._fit_lines:
            return
        box = self.textboxes[key]
        low, high = self._fit_lines[key]
        height = self._lines_height(max(low, min(high, self.wrapped_lines(key))))
        if box.cget("height") != height:
            box.configure(height=height)

    # ── the shared grid ───────────────────────────────────────────────────

    def _grid(self, parent=None, padx=10):
        """A grid frame with the columns the part panels share: label, field,
        unit, slack, "?"."""
        grid = ctk.CTkFrame(parent or self, fg_color="transparent")
        grid.pack(fill="x", padx=padx, pady=(0, 4))
        grid.grid_columnconfigure(0, minsize=LABEL_W)
        grid.grid_columnconfigure(1, minsize=FIELD_W)
        grid.grid_columnconfigure(2, minsize=UNIT_W)
        grid.grid_columnconfigure(3, weight=1)
        grid.grid_columnconfigure(HELP_COL, minsize=HELP_W)
        grid.next_row = 0
        return grid

    @staticmethod
    def _label(grid, text, row, sticky="w"):
        ctk.CTkLabel(grid, text=text, anchor="w").grid(row=row, column=0, sticky=sticky, pady=3)

    def _help(self, grid, row, tip, key=None, column=HELP_COL):
        if tip:
            btn = _help_btn(grid, tip, pack=False)
            btn.grid(row=row, column=column, sticky="e", padx=(4, 2))
            if key:
                self.help[key] = btn

    def _row(self, grid, label, key, unit="", tip=None):
        """label | entry | unit | ?"""
        row = grid.next_row
        grid.next_row += 1
        self._label(grid, label, row)
        self._entry(grid, key, FIELD_W).grid(row=row, column=1, sticky="w", pady=3)
        ctk.CTkLabel(grid, text=unit, anchor="w").grid(row=row, column=2, sticky="w", padx=(4, 0))
        self._help(grid, row, tip, key)

    def _wide_row(self, grid, label, key):
        """label | entry across the full width"""
        row = grid.next_row
        grid.next_row += 1
        self._label(grid, label, row)
        self._entry(grid, key, FIELD_W).grid(row=row, column=1, columnspan=HELP_COL,
                                             sticky="ew", pady=3)

    def _part_rows(self, grid, prefix):
        """Source, note and the "checked" box that a diode or MCU carries."""
        row = grid.next_row
        grid.next_row += 3
        self._label(grid, "Source:", row, sticky="nw")
        self._textbox(grid, f"{prefix}.source", lines=2).grid(
            row=row, column=1, columnspan=3, sticky="ew", pady=3)
        self._help(grid, row, "Where the values come from: data sheet, revision, tables or\n"
                              "figures used. Saved in the file's \"source\".", f"{prefix}.source")
        self._label(grid, "Note:", row + 1, sticky="nw")
        self._textbox(grid, f"{prefix}.note", lines=3, max_lines=16).grid(
            row=row + 1, column=1, columnspan=HELP_COL, sticky="ew", pady=3)
        self._checkbox(grid, f"{prefix}.checked", text="Checked against the data sheet").grid(
            row=row + 2, column=1, columnspan=HELP_COL, sticky="w", pady=(3, 6))

    def _labelled(self, parent, label, key, unit="", tip=None, lbl_w=110, ent_w=80, unit_w=45):
        """A packed row (the Signal Bandwidth tab's two fields)."""
        r = ctk.CTkFrame(parent, fg_color="transparent")
        r.pack(fill="x", pady=2)
        ctk.CTkLabel(r, text=label, width=lbl_w, anchor="w").pack(side="left")
        self._entry(r, key, ent_w).pack(side="left", padx=2)
        ctk.CTkLabel(r, text=unit, width=unit_w, anchor="w").pack(side="left")
        if tip:
            _help_btn(r, tip)
        return r

    def sync_from_state(self):
        """Copy AppState's field text into the widgets (no-op where equal)."""
        for key, var in self.vars.items():
            text = self.app_state.fields[key]
            if var.get() != text:
                var.set(text)
        for key, box in self.textboxes.items():
            text = self.app_state.fields[key]
            if box.get("1.0", "end-1c") != text:
                box.delete("1.0", "end")
                box.insert("1.0", text)
            self._fit(key)


# ── Resistor Panel ────────────────────────────────────────────────────────────

class ResistorPanel(_FieldPanel):
    """R1, R2 and R_s, one row each: value, unit, power rating, tolerance.

    The label column, the value (field) column and the "?" column are those
    of the part panels' grid, so the three line up with the panels below. A
    header row names the columns."""

    # header, field key suffix, width
    COLUMNS = (("Value", "value", FIELD_W), ("Unit", "unit", 70),
               ("Rating (mW)", "rating", 68), ("Tol. (%)", "tol", 48))
    HELP_COL = len(COLUMNS) + 2     # columns: label, the four fields, slack, "?"
    ROWS = (
        ("r1", "R1:",
         "R1: from the input to the node (the junction with R2 and the\n"
         "clamp diode).\n"
         "Rating: its power rating. The worst-case power at Max Input is\n"
         "checked against it.\n"
         "Tol.: its tolerance. The worst case takes R1 at both ends of it."),
        ("r2", "R2:",
         "R2: from the node to GND.\n"
         "Rating: its power rating. The worst-case power at Max Input is\n"
         "checked against it.\n"
         "Tol.: its tolerance. The worst case takes R2 at both ends of it."),
        ("rs", "R_s:",
         "R_s: optional series resistor from the node to the MCU pin.\n"
         "Blank or 0 = no series resistor; rating and tolerance are then\n"
         "not needed.\n"
         "Its power is worked out with the pin held at 0 V."),
    )

    def _build(self):
        ctk.CTkLabel(self, text="Resistors", font=("", 14, "bold")).pack(anchor="w", padx=10, pady=5)
        grid = self.grid_frame = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="x", padx=10, pady=(0, 2))
        grid.grid_columnconfigure(0, minsize=LABEL_W)
        grid.grid_columnconfigure(1, minsize=FIELD_W)
        grid.grid_columnconfigure(self.HELP_COL - 1, weight=1)
        grid.grid_columnconfigure(self.HELP_COL, minsize=HELP_W)

        self.headers = []
        for col, (text, _name, _width) in enumerate(self.COLUMNS, start=1):
            header = ctk.CTkLabel(grid, text=text, anchor="w", text_color=MUTED,
                                  font=("", 11), height=18)
            header.grid(row=0, column=col, sticky="w", padx=(0 if col == 1 else 6, 0))
            self.headers.append(header)

        for row, (prefix, label, tip) in enumerate(self.ROWS, start=1):
            self._label(grid, label, row)
            for col, (_text, name, width) in enumerate(self.COLUMNS, start=1):
                key = f"{prefix}.{name}"
                field = (self._unit_combo(grid, key, width) if name == "unit"
                         else self._entry(grid, key, width))
                field.grid(row=row, column=col, sticky="w", pady=3,
                           padx=(0 if col == 1 else 6, 0))
            self._help(grid, row, tip, f"{prefix}.value", column=self.HELP_COL)
        ctk.CTkLabel(self, text="R_s blank or 0 = no series resistor.",
                     text_color=MUTED, font=("", 11)).pack(anchor="w", padx=10)


# ── Clamp Diode Panel ─────────────────────────────────────────────────────────

class _DiodeTable(ctk.CTkFrame):
    """One editable clamp-diode table: a row is a current and the voltage
    across the diode at that current (minimum, typical, maximum).

    The table is in one of three states, shown plainly: not filled in (it is
    needed), not modelled (its current is taken as zero), or rows."""

    HEADERS = ("I (mA)", "V min", "V typ", "V max")
    CELL_W = 80

    def __init__(self, parent, state: AppState, table: str):
        super().__init__(parent, fg_color="transparent")
        self.app_state = state
        self.table = table
        self.cells: list = []     # per row: {row key: CTkEntry}
        self._vars: list = []     # per row: {row key: StringVar}
        self.delete_buttons: list = []

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x")
        ctk.CTkLabel(head, text=TABLE_TITLES[table], font=("", 12, "bold")).pack(side="left")
        _help_btn(head, TABLE_TIPS[table])

        # Header row and entry rows share one grid of fixed-width columns
        self.grid_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.headers = []
        for col, text in enumerate(self.HEADERS):
            self.grid_frame.grid_columnconfigure(col, minsize=self.CELL_W + 4)
            header = ctk.CTkLabel(self.grid_frame, text=text, width=self.CELL_W, anchor="w",
                                  text_color=MUTED, font=("", 11))
            header.grid(row=0, column=col, padx=(0, 4), sticky="w")
            self.headers.append(header)

        self.state_label = ctk.CTkLabel(self, text="", anchor="w", font=("", 12))

        # "+ Add row" directly under the table, on the left
        self.foot = ctk.CTkFrame(self, fg_color="transparent")
        self.add_button = ctk.CTkButton(self.foot, text="+ Add row", width=84, height=24,
                                        command=lambda: state.add_row(table))
        self.add_button.pack(side="left")
        self._not_modelled = ctk.StringVar(master=self, value="0")
        self.not_modelled_box = ctk.CTkCheckBox(
            self.foot, text="Not modelled", variable=self._not_modelled, onvalue="1",
            offvalue="0", checkbox_width=18, checkbox_height=18,
            command=lambda: state.set_not_modelled(table, self._not_modelled.get() == "1"))
        self.not_modelled_box.pack(side="left", padx=(16, 0))
        self.sync_from_state()

    def _rebuild(self, rows):
        for row in self.cells:
            for entry in row.values():
                entry.destroy()
        for button in self.delete_buttons:
            button.destroy()
        self.cells, self._vars, self.delete_buttons = [], [], []
        for i, texts in enumerate(rows):
            entries, variables = {}, {}
            for col, key in enumerate(ROW_KEYS):
                var = ctk.StringVar(master=self, value=texts[key])
                var.trace_add("write", lambda *_, i=i, key=key, var=var:
                              self.app_state.set_cell(self.table, i, key, var.get()))
                entry = ctk.CTkEntry(self.grid_frame, width=self.CELL_W, textvariable=var)
                entry.grid(row=i + 1, column=col, padx=(0, 4), pady=1, sticky="w")
                entries[key], variables[key] = entry, var
            button = ctk.CTkButton(self.grid_frame, text="×", width=24, height=24,
                                   fg_color="gray40", hover_color="gray30",
                                   command=lambda i=i: self.app_state.delete_row(self.table, i))
            button.grid(row=i + 1, column=len(ROW_KEYS), padx=(2, 0))
            self.cells.append(entries)
            self._vars.append(variables)
            self.delete_buttons.append(button)

    def sync_from_state(self):
        state = self.app_state.table_state(self.table)
        rows = self.app_state.tables[self.table] or []
        if len(rows) != len(self.cells):
            self._rebuild(rows)
        else:
            for variables, texts in zip(self._vars, rows):
                for key, var in variables.items():
                    if var.get() != texts[key]:
                        var.set(texts[key])

        # Rows: the header and the entries. No rows: one line naming the state.
        self.grid_frame.pack_forget()
        self.state_label.pack_forget()
        self.foot.pack_forget()
        if state == ROWS:
            self.grid_frame.pack(fill="x", pady=(2, 0))
        else:
            self.state_label.configure(
                text=TABLE_STATE_TEXT[state],
                text_color="orange" if state == BLANK else MUTED)
            self.state_label.pack(fill="x", pady=(2, 0))
        self.foot.pack(fill="x", pady=(3, 0))

        # The "Not modelled" box switches between blank and not modelled; it
        # has no meaning while the table has rows.
        self._not_modelled.set("1" if state == NOT_MODELLED else "0")
        self.not_modelled_box.configure(state="disabled" if state == ROWS else "normal")

    @property
    def state_text(self) -> str:
        """The state line as shown ("" while the table has rows)."""
        return self.state_label.cget("text") if self.state_label.winfo_manager() else ""


class ClampDiodePanel(_FieldPanel):
    """One clamp diode of either kind: part name, type, connection, the
    forward and reverse tables, capacitance, power rating, source, note and
    the "checked" box. No presets: values are typed or come from the file."""

    def _build(self):
        ctk.CTkLabel(self, text="Clamp Diode", font=("", 14, "bold")).pack(anchor="w", padx=10, pady=5)
        grid = self._grid()

        self._wide_row(grid, "Part:", "diode.part")

        row = grid.next_row
        grid.next_row += 1
        self._label(grid, "Type:", row)
        self._combo(grid, "diode.type", DIODE_TYPES, 120).grid(row=row, column=1, columnspan=3,
                                                              sticky="w", pady=3)
        self._help(grid, row, "Zener or Schottky. A label only: the calculation uses the\n"
                              "connection and the two tables, whatever the type.", "diode.type")

        row = grid.next_row
        grid.next_row += 1
        self._label(grid, "Connection:", row)
        pair = ctk.CTkFrame(grid, fg_color="transparent")
        pair.grid(row=row, column=1, columnspan=3, sticky="w", pady=3)
        ctk.CTkLabel(pair, text="Anode").pack(side="left")
        self._combo(pair, "diode.anode", TERMINALS, 84).pack(side="left", padx=(6, 0))
        ctk.CTkLabel(pair, text="Cathode").pack(side="left", padx=(18, 0))
        self._combo(pair, "diode.cathode", TERMINALS, 84).pack(side="left", padx=(6, 0))
        self._help(grid, row, "Where each terminal of the diode is connected. \"node\" is the\n"
                              "junction of R1 and R2; exactly one terminal is at the node.\n"
                              "Zener to GND: anode gnd, cathode node.\n"
                              "Schottky to the rail: anode node, cathode vdd.\n"
                              "Schottky to GND: anode gnd, cathode node.", "diode.anode")

        # One row each, on the grid: field, unit and "?" where every row has them
        self._row(grid, "Capacitance:", "diode.capacitance_pf", "pF",
                  "Diode capacitance at 0 V bias, or the data-sheet maximum.\n"
                  "Used for the Signal Bandwidth time constant.")
        self._row(grid, "Ptot:", "diode.ptot_mw", "mW",
                  "Power rating of the diode (total power dissipation).\n"
                  "The worst-case diode power at Max Input is checked against it.")

        self.tables = {}
        for table in ("forward", "reverse"):
            self.tables[table] = _DiodeTable(self, self.app_state, table)
            self.tables[table].pack(fill="x", padx=10, pady=(6, 4))

        self._part_rows(self._grid(), "diode")

    def sync_from_state(self):
        super().sync_from_state()
        for table in getattr(self, "tables", {}).values():
            table.sync_from_state()


# ── MCU Panel ─────────────────────────────────────────────────────────────────

class McuPanel(_FieldPanel):
    def _build(self):
        ctk.CTkLabel(self, text="MCU Pin Input Limits", font=("", 14, "bold")).pack(anchor="w", padx=10, pady=5)
        grid = self._grid()

        self._wide_row(grid, "Part:", "mcu.part")
        self._row(grid, "Pin type:", "mcu.pin_type", "",
                  "A label for the kind of pin, such as TT or FT. The limits\n"
                  "below are the ones the data sheet gives for that pin type.")
        rows = [
            ("mcu.vdd", "VDD/VDDA:", "V",
             "Supply voltage. Also used as the ADC reference (VREF), and as the\n"
             "voltage of the rail when the clamp diode is connected to vdd."),
            ("mcu.v_recommended_max", "Safe Max:", "V",
             "Highest pin voltage in normal operation. The check against it is\n"
             "the guard against current into the pin's protection diodes.\n"
             "STM32G4 TT pins: VDD + 0.3 V (DS12983 Rev 5, Table 17)."),
            ("mcu.v_absolute_max", "Abs. Max:", "V",
             "Absolute maximum pin voltage: above it the pin may be damaged.\n"
             "The highest pin voltage at Max Input is checked against it.\n"
             "STM32G4 TT pins: 4.0 V (DS12983 Rev 5, Table 14)."),
            ("mcu.v_pin_min", "Pin Min:", "V",
             "Lowest allowed pin voltage (0 or negative). Checked only when a\n"
             "negative Min Input is given.\n"
             "STM32G4: VSS - 0.3 V (DS12983 Rev 5, Table 14)."),
            ("mcu.adc_bits", "ADC bits:", "bits",
             "ADC resolution N; resolution = VREF / 2^N.\n"
             "STM32G4: 12-bit ADCs (STM32G484 datasheet DS12983 Rev 5, "
             "Features: 5 x 12-bit ADCs)."),
            ("mcu.vil_factor", "VIL factor:", "×VDD",
             "Pin input-low threshold as a fraction of VDD (VIL = factor × VDD).\n"
             "STM32G4: 0.3 (STM32G484 datasheet DS12983 Rev 5, Table 54, "
             "all I/Os except FT_c)."),
            ("mcu.vih_factor", "VIH factor:", "×VDD",
             "Pin input-high threshold as a fraction of VDD (VIH = factor × VDD).\n"
             "STM32G4: 0.7 (STM32G484 datasheet DS12983 Rev 5, Table 54, "
             "all I/Os except FT_c)."),
            ("mcu.c_pin_pf", "C_pin:", "pF",
             "MCU pin input capacitance. Used for the Signal Bandwidth time\n"
             "constant. STM32G4: CIO 5 pF typ (DS12983 Rev 5, Table 54)."),
            ("mcu.t_pulse_min_ns", "Min pulse width:", "ns",
             "Shortest pulse the input peripheral accepts. Used for the Signal\n"
             "Bandwidth limits. STM32G4 timer inputs: 2 to 3 timer clock\n"
             "periods (DS12983 Rev 5, Table 84)."),
        ]
        for key, label, unit, tip in rows:
            self._row(grid, label, key, unit, tip)
        self._part_rows(grid, "mcu")


# ── System Panel ──────────────────────────────────────────────────────────────

class SystemPanel(_FieldPanel):
    FOOTNOTE = "Optional values left blank leave their check out."

    def _build(self):
        ctk.CTkLabel(self, text="System Requirements", font=("", 14, "bold")).pack(anchor="w", padx=10, pady=5)
        grid = self._grid()
        for key, label, unit, tip in (
                ("system.v_input_max", "Max Input:", "V",
                 "The highest input voltage. The pin voltage and the power in\n"
                 "each part are checked at this input."),
                ("system.v_input_min", "Min Input:", "V",
                 "Optional: the lowest input voltage. When it is negative, the\n"
                 "lowest pin voltage is checked against Pin Min."),
                ("system.v_analog_fullscale", "ADC Scale:", "V",
                 "Optional: the input voltage at ADC full scale. Gives the\n"
                 "analog range check and the analog error."),
                ("system.analog_error_allowed_pct", "Allowed error:", "%",
                 "Optional: allowed analog error at ADC Scale, in percent.\n"
                 "Without it the analog error is shown for information only."),
                ("system.v_logic_high_min", "Logic High:", "V min",
                 "The lowest input voltage that must read as logic high."),
                ("system.v_logic_low_max", "Logic Low:", "V max",
                 "The highest input voltage that must read as logic low."),
                ("system.v_touch", "Touch voltage:", "V",
                 "Optional: a voltage the input may touch, for example 60 V.\n"
                 "Gives information rows only: it changes no verdict."),
                ("system.f_required_hz", "Required freq.:", "Hz",
                 "Optional: the input frequency the pin must handle (at the pin,\n"
                 "50 % duty). Compared with the Signal Bandwidth limits.")):
            self._row(grid, label, key, unit, tip)
        # Its own row below the grid, wrapped, with room under it
        self.footnote = ctk.CTkLabel(self, text=self.FOOTNOTE, text_color=MUTED, font=("", 11),
                                     anchor="w", justify="left", wraplength=400, height=20)
        self.footnote.pack(fill="x", padx=10, pady=(2, 12))


# ── Notes Panel ───────────────────────────────────────────────────────────────

class NotesPanel(ctk.CTkFrame):
    """Text widgets have no Tk variable, so edits are caught with <<Modified>>,
    which Tk raises for typing, paste, cut and delete alike."""

    def __init__(self, parent, state: AppState):
        super().__init__(parent)
        self.app_state = state
        ctk.CTkLabel(self, text="Design Notes", font=("", 14, "bold")).pack(anchor="w", padx=10, pady=5)
        self.textbox = ctk.CTkTextbox(self, height=80, wrap="word")
        self.textbox.pack(fill="x", padx=10, pady=(5, 10))
        self.textbox.bind("<<Modified>>", self._on_modified)
        self.sync_from_state()

    def _on_modified(self, event=None):
        if not self.textbox.edit_modified():
            return
        self.textbox.edit_modified(False)
        self.app_state.set_field("notes", self.textbox.get("1.0", "end-1c"))

    def sync_from_state(self):
        text = self.app_state.fields["notes"]
        if self.textbox.get("1.0", "end-1c") != text:
            self.textbox.delete("1.0", "end")
            self.textbox.insert("1.0", text)


# ── Signal Bandwidth Input Panel ──────────────────────────────────────────────

class BandwidthInputPanel(_FieldPanel):
    """Input fields of the Signal Bandwidth tab: the two board values. The
    diode capacitance comes from the Clamp Diode panel, the pin capacitance
    and the minimum pulse width from the MCU panel, and the required
    frequency from the System panel."""

    def __init__(self, parent, state: AppState):
        super().__init__(parent, state, fg_color="transparent")

    def _build(self):
        LBL_W, ENT_W, UNIT_W = 110, 80, 35

        ctk.CTkLabel(self, text="Board", font=("", 13, "bold")).pack(anchor="w", padx=5, pady=(5, 2))
        board = ctk.CTkFrame(self, fg_color="transparent")
        board.pack(fill="x", padx=5)
        self._labelled(board, "C_stray:", "bw.c_stray_pf", "pF",
                       "PCB parasitic/stray capacitance estimate.\n"
                       "Typically 2-5 pF. Depends on trace length and layout.",
                       lbl_w=LBL_W, ent_w=ENT_W, unit_w=UNIT_W)
        self._labelled(board, "Margin factor:", "bw.margin_factor", "",
                       "\"Reliable up to\" = \"may work up to\" ÷ this factor (1 or more).\n"
                       "Starting value 1.5: owner's example, 2026-11-09: 1 MHz\n"
                       "reliable, 1.5 MHz may work.",
                       lbl_w=LBL_W, ent_w=ENT_W, unit_w=UNIT_W)

        self.fill_button = ctk.CTkButton(
            self, text="Fill from starting values", height=28,
            command=self.app_state.fill_bandwidth_starting_values)
        self.fill_button.pack(anchor="w", padx=5, pady=(12, 2))
        ctk.CTkLabel(self, text="Fills only blank or unreadable fields above.",
                     text_color=MUTED, font=("", 11)).pack(anchor="w", padx=5)
        ctk.CTkLabel(self, text=OTHER_PANELS_NOTE, text_color=MUTED, font=("", 11),
                     justify="left", wraplength=340).pack(anchor="w", padx=5, pady=(12, 2))
