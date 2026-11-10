"""
UI tests that drive the real MainWindow.

One window is created per module and withdrawn; tests type into the real
widgets, call update(), and patch messagebox / filedialog. Needs a desktop
session (Tk display).
Run with: python -m pytest tests/ -v
"""
import copy
import json
import types
import os
from unittest import mock

import customtkinter as ctk
import pytest

from src.core.app_state import FIELDS
from src.ui import main_window as main_window_module
from src.ui import input_panels
from src.ui.input_panels import NEEDS_INPUT, _Tooltip
from src.ui.main_window import MainWindow
from tests.designs import V1_FILE, schottky_gnd, schottky_rail, typed, zener_reference

EXAMPLES = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "examples"))
ZENER_DIV = os.path.join(EXAMPLES, "zener_gnd_bzb984_c3v3.div")
SCHOTTKY_DIV = os.path.join(EXAMPLES, "schottky_rail_bat54cv.div")
OHM, KOHM, MOHM = "Ω", "kΩ", "MΩ"

# Deselect with:  python -m pytest tests/ -m "not ui"
pytestmark = pytest.mark.ui

NUMERIC_KEYS = [k for k, f in FIELDS.items() if f.kind in ("float", "int")]
BLOCKED, NOT_GIVEN, NO_RS = "n/a (see note)", "--", "no R_s"
NOT_FILLED = "Not filled in: needs input"
NOT_MODELLED = "Not modelled: current taken as zero"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def window():
    w = MainWindow()
    w.withdraw()
    w.update()
    yield w
    w.destroy()


@pytest.fixture
def dialogs(monkeypatch):
    mb = main_window_module.messagebox
    fd = main_window_module.filedialog
    m = types.SimpleNamespace(
        showerror=mock.MagicMock(), showwarning=mock.MagicMock(),
        askyesnocancel=mock.MagicMock(return_value=False),
        askopenfilename=mock.MagicMock(return_value=""),
        asksaveasfilename=mock.MagicMock(return_value=""),
    )
    monkeypatch.setattr(mb, "showerror", m.showerror)
    monkeypatch.setattr(mb, "showwarning", m.showwarning)
    monkeypatch.setattr(mb, "askyesnocancel", m.askyesnocancel)
    monkeypatch.setattr(fd, "askopenfilename", m.askopenfilename)
    monkeypatch.setattr(fd, "asksaveasfilename", m.asksaveasfilename)
    return m


@pytest.fixture
def w(window, dialogs):
    """Fresh blank design for each test; fails the test on any Tk callback error."""
    errors = []
    window.report_callback_exception = lambda *exc: errors.append(exc)
    window._file_new()
    window.update()
    yield window
    window.update()
    assert not errors, errors


# ── Helpers ───────────────────────────────────────────────────────────────────

def widget(w, key):
    for panel in w.field_panels:
        if key in panel.widgets:
            return panel.widgets[key]
    raise KeyError(key)


def set_widget(wd, text):
    if isinstance(wd, ctk.CTkComboBox):
        wd.set(text)
    elif isinstance(wd, ctk.CTkCheckBox):
        if (wd.get() == "1") != (text == "1"):
            wd.toggle()
    elif isinstance(wd, ctk.CTkTextbox):
        wd.delete("1.0", "end")
        if text:
            wd.insert("1.0", text)
    else:
        wd.delete(0, "end")
        if text:
            wd.insert(0, text)


def type_into(w, key, text):
    """Set a field the way a user would, through its widget."""
    set_widget(widget(w, key), text)
    w.update()


def table(w, name):
    return w.diode_panel.tables[name]


def type_cell(w, name, row, key, text):
    set_widget(table(w, name).cells[row][key], text)
    w.update()


def type_reference(w):
    """Type the whole baseline through the widgets (slow, used once)."""
    fields, tables = typed()
    for key, text in fields.items():
        if key != "notes" and text != w.app_state.fields[key]:
            type_into(w, key, text)
    for name, rows in tables.items():
        if rows == []:
            table(w, name).not_modelled_box.toggle()
            w.update()
        for i, row in enumerate(rows or []):
            table(w, name).add_button.invoke()
            w.update()
            for key, text in row.items():
                type_cell(w, name, i, key, text)


def load_design(w, design=None):
    """Fast setup: put a design (the baseline by default) in AppState; the
    widgets follow."""
    fields, tables = typed(design)
    for name, rows in tables.items():
        w.app_state.set_table(name, rows)
    w.app_state.set_fields(fields)
    w.update()
    assert widget(w, "r1.value").get() == fields["r1.value"]


def load_reference(w):
    load_design(w)
    assert widget(w, "r1.value").get() == "10"


def run_class_binding(tk_widget, cls, sequence):
    """Run Tk's own class binding (what Ctrl+V / Ctrl+X execute). Generated
    events are dropped by Tk while the window is withdrawn, so the binding
    script is evaluated directly."""
    script = tk_widget.bind_class(cls, sequence)
    tk_widget.tk.eval(script.replace("%W", str(tk_widget)))


def output_labels(w):
    """Every result cell on every tab: {name: label}."""
    c, s, o, b = w.components_tab, w.safety_tab, w.operating_tab, w.bandwidth_tab
    out = {
        "r_total": c.r_total, "ratio": c.ratio, "r_source": c.r_source, "p_total": c.p_total,
        "vclamp_typ": c.vclamp_typ, "vclamp_worst": c.vclamp_worst,
        "power_verdict": c.power_verdict,
        "source_z": s.source_z, "resolution": s.resolution,
        "touch_pin": s.touch_pin, "touch_diode": s.touch_diode, "touch_r1": s.touch_r1,
        "rail_current": s.rail_current,
    }
    for name, row in (("r1", c.r1_row), ("r2", c.r2_row), ("diode", c.diode_row),
                      ("rs", c.rs_row), ("rec", s.rec_row), ("abs", s.abs_row),
                      ("min", s.min_row), ("error", s.error_row)):
        for k, lbl in row.items():
            out[f"{name}.{k}"] = lbl
    for level, row in o.rows.items():
        for k, lbl in row.items():
            out[f"lv.{level}.{k}"] = lbl
    for name in BW_CELLS:
        out[f"bw.{name}"] = getattr(b, name)
    return out


BW_CELLS = ("f_may_work", "f_reliable", "required_value",
            "tau", "c_total", "t_rise", "t_fall", "t_shortest")


def text(lbl):
    return lbl.cget("text")


def all_label_texts(widget_):
    for child in widget_.winfo_children():
        if isinstance(child, ctk.CTkLabel):
            yield child.cget("text")
        yield from all_label_texts(child)


# ── Change tracking on every input ────────────────────────────────────────────

@pytest.mark.parametrize("key", list(FIELDS))
def test_every_input_marks_unsaved_and_recalculates(w, key):
    w.app_state.is_dirty = False
    before = w.app_state.results
    if key == "notes":
        w.notes_panel.textbox.insert("1.0", "note")
        w.update()
        assert w.app_state.fields["notes"] == "note"
    else:
        spec = FIELDS[key]
        value = {"unit": MOHM, "bool": "1"}.get(spec.kind, "7")
        if spec.kind == "choice":
            value = spec.choices[-1]
        type_into(w, key, value)
        assert w.app_state.fields[key] == value
        if spec.kind != "text":     # free text changes no result
            assert w.app_state.results is not before, "no recalculation"
    assert w.app_state.is_dirty
    assert w.title().endswith(" *")


def test_power_rating_edit_updates_margin(w):
    load_reference(w)
    type_into(w, "r1.rating", "200")
    old = text(w.components_tab.r1_row["margin"])
    w.app_state.is_dirty = False
    type_into(w, "r1.rating", "75")
    assert text(w.components_tab.r1_row["margin"]) != old
    assert w.app_state.is_dirty


def test_paste_cut_and_delete(w):
    entry = widget(w, "r1.rating")
    w.clipboard_clear()
    w.clipboard_append("75")
    run_class_binding(entry._entry, "Entry", "<<Paste>>")
    w.update()
    assert w.app_state.fields["r1.rating"] == "75"
    entry.select_range(0, "end")
    run_class_binding(entry._entry, "Entry", "<<Cut>>")
    w.update()
    assert w.app_state.fields["r1.rating"] == ""
    entry.insert(0, "12")
    entry.delete(1, "end")
    w.update()
    assert w.app_state.fields["r1.rating"] == "1"
    # paste into the notes
    w.app_state.is_dirty = False
    w.clipboard_clear()
    w.clipboard_append("pasted note")
    run_class_binding(w.notes_panel.textbox._textbox, "Text", "<<Paste>>")
    w.update()
    assert w.app_state.fields["notes"] == "pasted note"
    assert w.app_state.is_dirty


def test_unit_combo_and_checkbox(w):
    load_reference(w)
    type_into(w, "r1.unit", OHM)
    assert w.app_state.circuit.v["resistors.r1"] == 10
    w.app_state.is_dirty = False
    w.diode_panel.widgets["diode.checked"].toggle()
    w.update()
    assert w.app_state.fields["diode.checked"] == "1"
    assert w.app_state.is_dirty


# ── Blank, 0 and unreadable on every numeric field ────────────────────────────

@pytest.mark.parametrize("value", ["", "0", "abc"])
@pytest.mark.parametrize("key", NUMERIC_KEYS)
def test_blank_zero_unreadable(w, key, value):
    load_reference(w)
    type_into(w, key, value)
    s = w.app_state
    assert s.fields[key] == value
    label = FIELDS[key].label
    banner = text(w.banner)
    if value == "abc":
        assert f"{label}: 'abc' is not a" in banner
    elif value == "" and label in s.report.needs:
        assert label in banner
    # Every result cell shows a value, "needs input" or a blocked note: never stale
    for name, lbl in output_labels(w).items():
        assert text(lbl) != "", name
    # Whatever is computed must agree with the solver results now in AppState
    d = s.details
    if d["k_nominal"] is None:
        assert text(w.components_tab.ratio) == NEEDS_INPUT
    else:
        assert text(w.components_tab.ratio) == f"{d['k_nominal']:.4f}"
    if d["v_pin_high"] is None:
        assert text(w.safety_tab.rec_row["value"]) == NEEDS_INPUT
    assert w.plot.has_curves == bool(s.plot_data)


@pytest.mark.parametrize("key", ["r1.value", "r2.value"])
@pytest.mark.parametrize("value", ["", "0"])
def test_r1_r2_blank_or_zero_clears_tables_and_plot(w, key, value):
    load_reference(w)
    assert w.plot.has_curves
    type_into(w, key, value)
    for name in ("lv.logic_low.v_mcu_l", "lv.logic_low.v_mcu_h", "lv.max_input.v_mcu_h",
                 "lv.max_input.status", "rec.value", "rec.status", "abs.status",
                 "vclamp_typ", "ratio"):
        assert text(output_labels(w)[name]) == NEEDS_INPUT, name
    assert not w.plot.has_curves
    assert FIELDS[key].label in w.plot.message


# ── New Design clears everything ──────────────────────────────────────────────

def test_new_design_clears_everything(w, dialogs):
    load_reference(w)
    w.notes_panel.textbox.insert("1.0", "old notes")
    w.update()
    assert w.plot.has_curves
    assert text(w.components_tab.vclamp_typ) == "3.020"
    assert len(table(w, "reverse").cells) == 13
    w._file_new()
    w.update()
    dialogs.askyesnocancel.assert_called()       # it was unsaved
    # the 0 V row knows its input voltage whatever else is blank
    independent = {"lv.zero.v_in": "0.00 V", "lv.zero.thresh": NOT_GIVEN,
                   "lv.zero.status": "Zero ref"}
    for name, lbl in output_labels(w).items():
        if name.startswith("rs."):
            assert text(lbl) == NO_RS, (name, text(lbl))    # R_s blank
        elif name in independent:
            assert text(lbl) == independent[name], (name, text(lbl))
        else:
            # "--": a row whose optional input (Min Input, ADC Scale, Touch) is blank
            assert text(lbl) in (NEEDS_INPUT, BLOCKED, NOT_GIVEN), (name, text(lbl))
    assert text(w.components_tab.vclamp_typ) == NEEDS_INPUT
    assert not w.plot.has_curves
    assert "Plot needs input" in w.plot.message
    fields, _ = typed()
    for key in fields:
        if FIELDS[key].kind in ("float", "int", "choice") and not key.startswith("bw."):
            assert widget(w, key).get() == "", key
    assert widget(w, "diode.part").get() == "" and widget(w, "diode.checked").get() == "0"
    assert widget(w, "diode.note").get("1.0", "end-1c") == ""
    assert table(w, "forward").cells == [] and table(w, "reverse").cells == []
    # New Design starts both tables blank (null), not "not modelled"
    assert w.app_state.tables == {"forward": None, "reverse": None}
    assert table(w, "forward").state_text == table(w, "reverse").state_text == NOT_FILLED
    assert "Forward table" in text(w.banner) and "Reverse table" in text(w.banner)
    assert widget(w, "diode.source").get("1.0", "end-1c") == ""
    assert w.notes_panel.textbox.get("1.0", "end-1c") == ""
    assert not w.app_state.is_dirty and w.title().endswith("Untitled")


# ── Both save-failure messages ────────────────────────────────────────────────

def test_save_as_failure_reported(w, dialogs, tmp_path):
    load_reference(w)
    dialogs.asksaveasfilename.return_value = str(tmp_path / "missing" / "x.div")
    assert w._file_save_as() is False
    dialogs.showerror.assert_called_once()
    assert dialogs.showerror.call_args[0][0] == "Save Failed"


def test_plain_save_failure_reported(w, dialogs, tmp_path):
    load_reference(w)
    w.app_state.current_file = str(tmp_path / "missing" / "x.div")
    assert w._file_save() is False
    dialogs.showerror.assert_called_once()
    assert dialogs.showerror.call_args[0][0] == "Save Failed"
    dialogs.asksaveasfilename.assert_not_called()
    assert w.app_state.is_dirty


def test_unreadable_text_blocks_save(w, dialogs, tmp_path):
    load_reference(w)
    type_into(w, "r1.value", "1O")      # letter O
    assert w._file_save() is False
    title, message = dialogs.showerror.call_args[0]
    assert title == "Can't Save" and "R1 value" in message and "1O" in message
    dialogs.asksaveasfilename.assert_not_called()


def test_unreadable_table_cell_blocks_save(w, dialogs):
    load_reference(w)
    type_cell(w, "reverse", 2, "v_max", "1,61")
    assert w._file_save() is False
    title, message = dialogs.showerror.call_args[0]
    assert title == "Can't Save" and "Reverse table row 3 V max" in message and "1,61" in message


def test_reference_typed_through_widgets(w):
    type_reference(w)
    assert text(w.components_tab.r_total) == "28.00"
    assert text(w.components_tab.ratio) == "0.6429"
    assert text(w.components_tab.vclamp_typ) == "3.020"
    assert text(w.components_tab.vclamp_worst) == "3.235"
    assert text(w.components_tab.diode_row["current"]) == "2.53 mA"
    assert text(w.safety_tab.rec_row["value"]) == "3.239 V"
    assert text(w.banner) == "All inputs present."
    assert w.app_state.design == zener_reference(created=None, notes="")


def test_save_and_reopen(w, dialogs, tmp_path):
    load_reference(w)
    path = str(tmp_path / "ok.div")
    dialogs.asksaveasfilename.return_value = path
    assert w._file_save_as() is True
    assert w.title().endswith("ok.div")
    w._file_new()
    dialogs.askopenfilename.return_value = path
    w._file_open()
    w.update()
    dialogs.showwarning.assert_not_called()
    assert widget(w, "r1.value").get() == "10"
    assert text(w.components_tab.vclamp_typ) == "3.020"
    assert len(table(w, "reverse").cells) == 13
    assert table(w, "reverse").cells[11]["v_max"].get() == "3.5"


# ── Loading from the window ───────────────────────────────────────────────────

def test_malformed_file_keeps_current_design(w, dialogs, tmp_path):
    load_reference(w)
    data = zener_reference()
    data["resistors"]["r1"]["unit"] = "kOhm"
    del data["mcu"]["vdd"]
    bad = tmp_path / "bad.div"
    bad.write_text(json.dumps(data), encoding="utf-8")
    title_before = w.title()
    dialogs.askopenfilename.return_value = str(bad)
    w._file_open()
    w.update()
    title, message = dialogs.showerror.call_args[0]
    assert "resistors.r1.unit" in message and "mcu.vdd" in message   # every problem
    assert "The current design was not changed." in message
    assert widget(w, "r1.value").get() == "10"
    assert w.title() == title_before and w.app_state.is_dirty


def test_format_1_file_gets_a_clear_message(w, dialogs, tmp_path):
    old = tmp_path / "results.div"
    old.write_text(json.dumps(copy.deepcopy(V1_FILE)), encoding="utf-8")
    dialogs.askopenfilename.return_value = str(old)
    w._file_open()
    title, message = dialogs.showerror.call_args[0]
    assert title == "Can't Open File"
    assert "format 1.0" in message and "reads .div format 2.0 only" in message
    assert w.title().endswith("Untitled")


def test_failed_load_keeps_change_tracking(w, dialogs, monkeypatch):
    def boom():
        raise RuntimeError("sync failed")
    monkeypatch.setattr(w.resistor_panel, "sync_from_state", boom)
    dialogs.askopenfilename.return_value = ZENER_DIV
    w._file_open()
    dialogs.showerror.assert_called_once()
    monkeypatch.undo()
    assert w.app_state.ignore_changes is False
    w.app_state.is_dirty = False
    type_into(w, "r2.rating", "50")
    assert w.app_state.is_dirty


def test_file_with_unusable_values_opens_with_a_warning(w, dialogs, tmp_path):
    data = zener_reference(resistors__r1__tolerance_pct=150)
    path = tmp_path / "range.div"
    path.write_text(json.dumps(data), encoding="utf-8")
    dialogs.askopenfilename.return_value = str(path)
    w._file_open()
    w.update()
    dialogs.showerror.assert_not_called()
    assert "resistors.r1.tolerance_pct" in dialogs.showwarning.call_args[0][1]
    assert widget(w, "r1.tol").get() == "150"
    assert "Fix: R1 tolerance: must be at least 0 and below 100 %" in text(w.banner)


# ── No presets: values come from the file or from typing ──────────────────────

def test_no_preset_dropdown(w):
    """Rewritten (was: preset shown as modified). The Clamp Diode panel has
    no drop-down of parts and nothing fills its fields by itself."""
    panel = w.diode_panel
    assert not hasattr(panel, "preset") and not hasattr(panel, "modified_label")
    labels = set(all_label_texts(panel))
    assert "Clamp Diode" in labels and "Preset:" not in labels
    combos = {key for key, wd in panel.widgets.items() if isinstance(wd, ctk.CTkComboBox)}
    assert combos == {"diode.type", "diode.anode", "diode.cathode"}
    assert panel.widgets["diode.type"].cget("values") == ["zener", "schottky"]
    assert panel.widgets["diode.anode"].cget("values") == ["node", "gnd", "vdd"]
    type_into(w, "diode.part", "BZB984-C3V3")
    type_into(w, "diode.type", "zener")
    assert widget(w, "diode.ptot_mw").get() == "" and table(w, "reverse").cells == []


# ── An example file gives frequency outputs ───────────────────────────────────

def test_example_file_gives_frequency_outputs(w, dialogs):
    """Rewritten (was: results.div gives bandwidth outputs after a fill)."""
    dialogs.askopenfilename.return_value = SCHOTTKY_DIV
    w._file_open()
    w.update()
    dialogs.showwarning.assert_not_called()
    labels = output_labels(w)
    for name in BW_CELLS:
        assert text(labels[f"bw.{name}"]) not in (NEEDS_INPUT, BLOCKED, ""), name
    assert text(w.bandwidth_tab.f_may_work) == "1.347 MHz"
    assert text(w.bandwidth_tab.f_reliable) == "898.0 kHz"
    assert not w.app_state.is_dirty
    # the fill button puts back only what is blank
    type_into(w, "bw.c_stray_pf", "")
    assert text(w.bandwidth_tab.c_total) == NEEDS_INPUT
    w.bw_input_panel.fill_button.invoke()
    w.update()
    assert widget(w, "bw.c_stray_pf").get() == "3"
    assert text(w.bandwidth_tab.c_total) == "18.0"


def test_pin_never_reads_high_shown_on_tab(w):
    """The tab says so and shows no limits."""
    load_reference(w)                       # 3.8 V Logic High: pin 1.83 V < VIH 2.31 V
    b = w.bandwidth_tab
    assert text(b.note).startswith("The pin never reads high")
    assert text(b.f_reliable) == BLOCKED and text(b.f_may_work) == BLOCKED
    assert text(b.t_rise) == BLOCKED and text(b.t_shortest) == BLOCKED
    assert text(b.tau) == "2973.73" and text(b.c_total) == "458.0"
    type_into(w, "system.f_required_hz", "1000")
    assert text(b.required_value) == "1.0 kHz" and text(b.required_status) == "✗ FAIL"
    type_into(w, "system.v_logic_high_min", "24")
    assert text(b.note) == ""
    assert text(b.f_reliable) == "55.2 kHz" and text(b.f_may_work) == "82.9 kHz"
    assert text(b.required_status) == "✓ PASS"


def test_pin_never_reads_low_shown_on_tab(w):
    load_design(w, schottky_rail(system__v_logic_low_max=1.6))
    b = w.bandwidth_tab
    assert text(b.note).startswith("The pin never reads low")
    assert text(b.f_reliable) == BLOCKED and text(b.f_may_work) == BLOCKED


# ── Signal Bandwidth tab: two numbers ─────────────────────────────────────────

def test_two_numbers_answer_the_question(w):
    load_design(w, schottky_rail())
    b = w.bandwidth_tab
    labels = set(all_label_texts(w))
    assert "Input frequency this pin can handle" in labels
    assert "May work up to" in labels and "Reliable up to" in labels
    assert any("per channel for an encoder" in t and "50 % duty" in t for t in labels)
    assert text(b.f_may_work) == "1.347 MHz" and text(b.f_reliable) == "898.0 kHz"
    d = w.app_state.details
    assert d["f_reliable_hz"] == pytest.approx(d["f_may_work_hz"] / 1.5)
    # the two headline numbers are the large ones
    assert b.f_may_work.cget("font")[1] == b.f_reliable.cget("font")[1] == 20
    assert b.required_value.cget("font")[1] == 13


def test_margin_factor_is_a_visible_field(w):
    assert widget(w, "bw.margin_factor").get() == "1.5"      # starting value, new design
    load_design(w, schottky_rail())
    type_into(w, "bw.margin_factor", "2")
    assert text(w.bandwidth_tab.f_may_work) == "1.347 MHz"
    assert text(w.bandwidth_tab.f_reliable) == "673.5 kHz"
    type_into(w, "bw.margin_factor", "")
    assert text(w.bandwidth_tab.f_reliable) == NEEDS_INPUT
    assert "Margin factor" in text(w.banner)
    w.bw_input_panel.fill_button.invoke()
    w.update()
    assert widget(w, "bw.margin_factor").get() == "1.5"
    tips = [t for t in _Tooltip.all_texts if "Starting value 1.5" in t]
    assert tips and "1 MHz" in tips[0] and "1.5 MHz may work" in tips[0]


def test_required_frequency_status(w):
    load_design(w, schottky_rail())
    b = w.bandwidth_tab
    assert text(b.required_value) == NOT_GIVEN and text(b.required_status) == ""
    for hz, shown, status in (("800000", "800.0 kHz", "✓ PASS"),
                              ("1000000", "1.000 MHz", "⚠ TIGHT"),
                              ("1400000", "1.400 MHz", "✗ FAIL")):
        type_into(w, "system.f_required_hz", hz)
        assert text(b.required_value) == shown and text(b.required_status) == status
    assert text(w.verdict) == "Overall verdict: ✗ FAIL  (Safe Max, ADC range, Required frequency)"
    type_into(w, "mcu.t_pulse_min_ns", "")
    assert text(b.required_status) == NEEDS_INPUT and text(b.f_may_work) == NEEDS_INPUT


def test_details_control(w):
    """Details shows tau, total capacitance, the two edge times and the
    shortest usable pulse; it is closed until asked for."""
    load_design(w, schottky_rail())
    b = w.bandwidth_tab
    if b.details_shown:
        b.toggle_details()
    assert not b.details_shown and b.details_button.cget("text") == "Details ▸"
    b.details_button.invoke()
    w.update()
    assert b.details_shown and b.details_button.cget("text") == "Details ▾"
    rows = [t for t in all_label_texts(b.details_frame)]
    for label in ("Time constant (τ)", "Total capacitance", "Rising edge to VIH",
                  "Falling edge to VIL", "Shortest usable pulse"):
        assert label in rows
    assert [text(x) for x in (b.tau, b.c_total, b.t_rise, b.t_fall, b.t_shortest)] == [
        "116.87", "18.0", "353.56", "255.19", "371.21"]
    assert len([t for t in rows if t in ("ns", "pF")]) == 5      # five rows, no more
    b.details_button.invoke()
    w.update()
    assert not b.details_shown


def test_old_bandwidth_fields_and_limits_are_gone(w):
    labels = set(all_label_texts(w))
    for old in ("N_samples:", "f_periph:", "Bits:", "Signed:", "f_read:", "C_diode:",
                "-3 dB bandwidth", "10–90% rise time", "Analog (conservative)",
                "Analog (practical)", "Digital sampling", "Counter overflow",
                "Effective Limit", "Undefined zone (rise)", "Bottleneck"):
        assert old not in labels, old
    assert sorted(w.bw_input_panel.widgets) == ["bw.c_stray_pf", "bw.margin_factor"]
    for old in ("f_3db", "t_undef_rise", "f_analog", "f_practical", "f_digital",
                "f_overflow", "f_effective"):
        assert not hasattr(w.bandwidth_tab, old)
    assert not hasattr(w.bw_input_panel, "derived")
    # C_diode, C_pin and the minimum pulse width are part data now
    assert widget(w, "diode.capacitance_pf") is w.diode_panel.widgets["diode.capacitance_pf"]
    assert widget(w, "mcu.c_pin_pf") is w.mcu_panel.widgets["mcu.c_pin_pf"]
    assert widget(w, "mcu.t_pulse_min_ns") is w.mcu_panel.widgets["mcu.t_pulse_min_ns"]
    assert widget(w, "system.f_required_hz") is w.system_panel.widgets["system.f_required_hz"]


# ── Plot clearing ─────────────────────────────────────────────────────────────

def test_plot_clears_and_redraws(w):
    load_reference(w)
    assert w.plot.has_curves
    type_into(w, "system.v_input_max", "")
    assert not w.plot.has_curves
    assert "Max Input" in w.plot.message
    type_into(w, "system.v_input_max", "30")
    assert w.plot.has_curves


def test_plot_draws_the_lists_from_app_state(w):
    load_design(w, schottky_gnd(system__v_input_min=-5.0))
    p = w.app_state.plot_data
    typ_line = w.plot.ax.lines[0]
    assert list(typ_line.get_xdata()) == p["v_in"]
    assert list(typ_line.get_ydata()) == p["v_mcu_typ"]
    assert w.plot.ax.get_xlim() == (-5.0, 30.0)
    assert w.plot.ax.get_ylim()[0] < p["v_mcu_typ"][0] < 0


# ── Labels and warnings ───────────────────────────────────────────────────────

def test_source_impedance_label_renamed(w):
    labels = set(all_label_texts(w))
    assert "ADC Source Impedance (R1∥R2 + R_s)" in labels
    assert "ADC Source Impedance (R1∥R2)" not in labels


def test_zener_renamed_to_clamp_diode(w):
    labels = set(all_label_texts(w))
    assert not [t for t in labels if "zener" in t.lower()]
    for name in ("Clamp Diode", "Clamp diode", "Typical clamp diode",
                 "Worst clamp diode (nominal R)"):
        assert name in labels
    assert not hasattr(w, "zener_panel") and not hasattr(w.components_tab, "z_row")


def test_min_sample_cycles_row_removed(w):
    labels = set(all_label_texts(w))
    assert "Min Sample Cycles" not in labels
    assert "Source Impedance" in labels and "Resolution" in labels
    assert not hasattr(w.safety_tab, "sample_cyc")


def test_low_value_divider_converges_without_warning(w):
    load_reference(w)
    type_into(w, "r1.value", "100")
    type_into(w, "r1.unit", OHM)
    type_into(w, "r2.value", "100")
    type_into(w, "r2.unit", OHM)
    assert "did not settle" not in text(w.banner)
    assert text(w.components_tab.vclamp_typ) == f"{w.app_state.details['v_pin_typ']:.3f}"
    assert 4.0 < w.app_state.details["v_pin_typ"] < 5.0


def test_solver_warning_visible(w, monkeypatch):
    """The warning is still shown when bracketing fails."""
    from src.models import clamp_solver
    real = clamp_solver._solve_node
    monkeypatch.setattr(clamp_solver, "_solve_node",
                        lambda *a, **k: (real(*a, **k)[0], False))
    load_reference(w)
    assert "did not settle" in text(w.banner)


# ── No injection estimate; Safe Max is the guard ──────────────────────────────

def test_no_injection_row_and_safe_max_is_the_guard(w):
    """Rewritten (owner, 2026-11-09; was: the injection row is an estimate).
    The row, its limit field and the 100 Ω are gone."""
    load_design(w, schottky_rail())
    labels = set(all_label_texts(w))
    assert not [t for t in labels if "njection" in t]
    assert not hasattr(w.safety_tab, "inj_row")
    with pytest.raises(KeyError):
        widget(w, "mcu.safe_injection_ma")
    assert not [t for t in _Tooltip.all_texts if "100 Ω" in t or "+ 100" in t]
    guard = [t for t in _Tooltip.all_texts if "guard against" in t]
    assert len(guard) >= 2                  # Safe Max field and the Limit column
    assert all("no separate\ninjection-current estimate" in t or "protection diodes" in t
               for t in guard)
    assert text(w.safety_tab.rec_row["value"]) == "3.651 V"
    assert text(w.safety_tab.rec_row["margin"]) == "-51 mV"
    assert text(w.safety_tab.rec_row["status"]) == "✗ FAIL"


def test_power_typical_and_worst_shown(w):
    load_reference(w)
    d = w.app_state.details
    c = w.components_tab
    for row, name in ((c.r1_row, "r1"), (c.r2_row, "r2"), (c.diode_row, "diode")):
        assert text(row["power"]) == f"{d[f'p_{name}_mw']:.1f} mW"
        assert text(row["power_worst"]) == f"{d[f'p_{name}_worst_mw']:.1f} mW"
        assert text(row["margin_worst"]) != NEEDS_INPUT
    assert text(c.r1_row["power_worst"]) == "74.5 mW"
    for lbl in c.rs_row.values():
        assert text(lbl) == NO_RS


def test_rs_row_needs_and_shows_values(w):
    load_reference(w)
    type_into(w, "rs.value", "100")
    rs = w.components_tab.rs_row
    assert text(rs["power_worst"]) == NEEDS_INPUT and text(rs["rating"]) == NEEDS_INPUT
    assert "R_s power rating" in text(w.banner) and "R_s tolerance" in text(w.banner)
    assert "Also blank" not in text(w.banner)
    type_into(w, "rs.rating", "250")
    type_into(w, "rs.tol", "1")
    # pin held at 0 V: 3.239 V^2 / 99 Ω
    assert text(rs["power_worst"]) == "106.0 mW"
    assert text(rs["current"]) == "30.20 mA"
    assert text(rs["rating"]) == "250 mW"
    assert text(rs["margin_worst"]) == "✓ 58%"
    assert text(w.banner) == "All inputs present."
    tips = [t for t in _Tooltip.all_texts if "V² / R_s min" in t]
    assert tips and "pin held at 0 V" in tips[0]


def test_blank_rating_margin_shows_needs_input(w):
    load_reference(w)
    type_into(w, "r1.rating", "")
    assert text(w.components_tab.r1_row["margin"]) == NEEDS_INPUT
    assert text(w.components_tab.r1_row["margin_worst"]) == NEEDS_INPUT
    assert "≥" not in " ".join(all_label_texts(w.components_tab.r1_row["margin"].master))


# ── Worst-case labels and the power verdict ───────────────────────────────────

def test_two_worst_case_voltages_labelled_apart(w):
    """Component tab: nominal R1/R2 with the diode's maximum column (3.235 V).
    MCU tab: V_mcuH, the highest of all corners (3.239 V)."""
    load_reference(w)
    labels = set(all_label_texts(w))
    assert "Worst clamp diode (nominal R)" in labels and "Worst Case" not in labels
    assert "Voltage at MCU Pin (nominal R1/R2)" in labels
    assert "V_mcuH" in labels
    d = w.app_state.details
    assert text(w.components_tab.vclamp_worst) == f"{d['v_pin_diode_max']:.3f}" == "3.235"
    assert text(w.safety_tab.rec_row["value"]) == f"{d['v_pin_high']:.3f} V" == "3.239 V"
    legend = [t.get_text() for t in w.plot.ax.get_legend().get_texts()]
    assert "V_mcuH (worst case)" in legend


def test_power_verdict_shown(w):
    load_reference(w)
    assert text(w.components_tab.power_verdict) == "✓ PASS"
    # typical margin is information only: no tick
    assert text(w.components_tab.r1_row["margin"]) == "64%"
    assert text(w.components_tab.r1_row["margin_worst"]) == "✓ 63%"
    type_into(w, "r1.tol", "25")
    type_into(w, "r2.tol", "25")
    p_typ = w.app_state.details["p_r1_mw"]
    type_into(w, "r1.rating", f"{1.3 * p_typ:.1f}")
    assert text(w.components_tab.r1_row["margin"]) == "23%"
    assert text(w.components_tab.r1_row["margin_worst"]).startswith("✗")
    assert text(w.components_tab.power_verdict) == "✗ FAIL"
    type_into(w, "r1.rating", "")
    assert text(w.components_tab.power_verdict) == NEEDS_INPUT


# ── Clamp diode tables ────────────────────────────────────────────────────────

def test_example_file_fills_the_tables(w, dialogs):
    dialogs.askopenfilename.return_value = SCHOTTKY_DIV
    w._file_open()
    w.update()
    forward, reverse = table(w, "forward"), table(w, "reverse")
    assert len(forward.cells) == 5 and len(reverse.cells) == 2
    assert [forward.cells[1][k].get() for k in ("i_ma", "v_min", "v_typ", "v_max")] == [
        "1", "0.106", "0.213", "0.32"]
    assert reverse.cells[0]["i_ma"].get() == "0.00065"
    assert forward.state_text == "" and reverse.state_text == ""
    assert widget(w, "diode.source").get("1.0", "end-1c") == \
        "Nexperia BAT54CV, 27 December 2022: Tables 5 and 7, Figs. 1 and 2"
    assert widget(w, "diode.type").get() == "schottky"
    assert widget(w, "diode.anode").get() == "node" and widget(w, "diode.cathode").get() == "vdd"
    assert widget(w, "diode.part").get() == "BAT54CV"
    assert widget(w, "diode.note").get("1.0", "end-1c").startswith("forward: v_max is Table 7")
    assert widget(w, "diode.checked").get() == "0"
    assert widget(w, "mcu.pin_type").get() == "TT"


def test_table_cell_typing_recalculates_and_marks_unsaved(w):
    load_reference(w)
    w.app_state.is_dirty = False
    type_cell(w, "reverse", 11, "v_typ", "3.30")
    assert w.app_state.tables["reverse"][11]["v_typ"] == "3.30"
    assert w.app_state.is_dirty and w.title().endswith(" *")
    assert text(w.components_tab.vclamp_typ) == "3.025"
    type_cell(w, "reverse", 11, "v_typ", "")
    assert text(w.components_tab.vclamp_typ) == NEEDS_INPUT
    assert "Reverse table row 12 V typ" in text(w.banner)
    assert not w.plot.has_curves or "v_mcu_typ" not in w.app_state.plot_data


def test_add_and_delete_row_buttons(w):
    load_reference(w)
    forward = table(w, "forward")
    assert forward.cells == [] and forward.state_text == NOT_MODELLED
    w.app_state.is_dirty = False
    forward.add_button.invoke()
    forward.add_button.invoke()
    w.update()
    assert len(forward.cells) == 2 and len(w.app_state.tables["forward"]) == 2
    assert forward.state_text == "" and w.app_state.is_dirty
    assert "Forward table row 1 current" in text(w.banner)
    for i, row in enumerate(((1, 0.6, 0.7, 0.8), (10, 0.7, 0.8, 0.9))):
        for key, value in zip(("i_ma", "v_min", "v_typ", "v_max"), row):
            type_cell(w, "forward", i, key, str(value))
    assert text(w.banner) == "All inputs present."
    forward.delete_buttons[0].invoke()
    w.update()
    assert len(forward.cells) == 1 and forward.cells[0]["i_ma"].get() == "10"
    assert "Forward table: needs at least 2 rows" in text(w.banner)
    # deleting the last row returns the table to "not filled in"
    forward.delete_buttons[0].invoke()
    w.update()
    assert forward.cells == [] and forward.state_text == NOT_FILLED
    assert w.app_state.tables["forward"] is None
    assert text(w.banner) == "Needs input: Forward table"
    assert text(w.components_tab.vclamp_typ) == NEEDS_INPUT


def test_table_has_three_states_shown_plainly(w):
    """Rewritten (was: the "no reverse data" note)."""
    load_reference(w)
    reverse = table(w, "reverse")
    box = reverse.not_modelled_box
    # c) rows: no state line, and the "Not modelled" box has no meaning
    assert reverse.state_text == "" and box.cget("state") == "disabled" and box.get() == "0"
    assert reverse.grid_frame.winfo_manager() == "pack"
    # a) blank: needed, and it blocks the results that use it
    w.app_state.set_table("reverse", None)
    w.update()
    assert reverse.state_text == NOT_FILLED and reverse.state_label.cget("text_color") == "orange"
    assert box.cget("state") == "normal" and box.get() == "0"
    assert reverse.grid_frame.winfo_manager() == ""           # no header without rows
    assert text(w.banner) == "Needs input: Reverse table"
    assert text(w.components_tab.vclamp_typ) == NEEDS_INPUT and not w.plot.has_curves
    # b) not modelled: the checkbox switches between a) and b)
    w.app_state.is_dirty = False
    box.toggle()
    w.update()
    assert w.app_state.tables["reverse"] == [] and w.app_state.is_dirty
    assert reverse.state_text == NOT_MODELLED and box.get() == "1"
    assert text(w.banner) == "All inputs present."
    assert text(w.components_tab.vclamp_typ) == f"{30 * 18 / 28:.3f}"
    box.toggle()
    w.update()
    assert w.app_state.tables["reverse"] is None and reverse.state_text == NOT_FILLED
    # "+ Add row" turns either state into rows
    for start in (None, []):
        w.app_state.set_table("reverse", start)
        w.update()
        reverse.add_button.invoke()
        w.update()
        assert len(reverse.cells) == 1 and reverse.state_text == ""
        assert box.cget("state") == "disabled" and box.get() == "0"
        reverse.delete_buttons[0].invoke()
        w.update()
        assert reverse.state_text == NOT_FILLED


def test_connection_combo_changes_the_result(w):
    load_design(w, schottky_rail())
    assert text(w.components_tab.vclamp_typ) == "3.547"
    assert text(w.safety_tab.rail_current) == "2.493"
    type_into(w, "diode.cathode", "gnd")            # anode node, cathode gnd
    assert text(w.safety_tab.rail_current) == NOT_GIVEN
    assert float(text(w.components_tab.vclamp_typ)) < 0.5
    type_into(w, "diode.anode", "gnd")              # both at gnd
    assert "Fix: Anode connection: one of anode and cathode must be node" in text(w.banner)
    assert text(w.components_tab.vclamp_typ) == NEEDS_INPUT


# ── New checks and information rows ───────────────────────────────────────────

def test_overall_verdict_label(w):
    assert text(w.verdict) == "Overall verdict: needs input"
    load_reference(w)
    assert text(w.verdict) == "Overall verdict: ✗ FAIL  (Logic High)"
    type_into(w, "system.v_logic_high_min", "24")
    assert text(w.verdict) == "Overall verdict: ✓ PASS"
    load_design(w, schottky_rail())
    assert text(w.verdict) == "Overall verdict: ✗ FAIL  (Safe Max, ADC range)"
    type_into(w, "mcu.v_recommended_max", "3.67")
    type_into(w, "system.v_analog_fullscale", "")
    assert text(w.verdict) == "Overall verdict: ⚠ TIGHT  (Safe Max)"


def test_input_levels_table(w):
    load_reference(w)
    rows = w.operating_tab.rows
    assert list(rows) == ["min_input", "zero", "logic_low", "logic_high",
                          "analog_fullscale", "max_input", "touch"]
    # Rewritten: the Max Input row shows both of its limits (was "≤ 4.0V abs"),
    # and every requirement has a space before its unit, as the row's
    # voltages have (was "> VIH 2.31V").
    assert [text(c) for c in rows["logic_high"].values()] == [
        "3.80 V", "1.831 V", "2.110 V", "> VIH 2.31 V", "✗ FAIL"]
    assert [text(c) for c in rows["logic_low"].values()] == [
        "1.00 V", "0.637 V", "0.647 V", "< VIL 0.99 V", "✓ PASS"]
    assert [text(c) for c in rows["analog_fullscale"].values()] == [
        "5.10 V", "2.019 V", "2.352 V", "≤ VDD 3.30 V", "✓ PASS"]
    assert [text(c) for c in rows["max_input"].values()] == [
        "30.00 V", "2.840 V", "3.239 V", "≤ 3.60 V safe / ≤ 4.00 V abs", "✓ PASS"]
    assert [text(c) for c in rows["zero"].values()] == [
        "0.00 V", "0.000 V", "0.000 V", NOT_GIVEN, "Zero ref"]
    for level in ("min_input", "touch"):
        assert {text(c) for c in rows[level].values()} == {NOT_GIVEN}
    type_into(w, "system.v_touch", "60")
    assert [text(c) for c in rows["touch"].values()][:3] == ["60.00 V", "3.134 V", "3.538 V"]
    assert text(rows["touch"]["status"]) == "info"
    type_into(w, "system.v_analog_fullscale", "")
    assert {text(c) for c in rows["analog_fullscale"].values()} == {NOT_GIVEN}


def test_min_input_row(w):
    load_design(w, schottky_gnd())
    s = w.safety_tab
    assert {text(c) for c in s.min_row.values()} == {NOT_GIVEN}
    type_into(w, "system.v_input_min", "-5")
    assert [text(c) for c in s.min_row.values()] == ["-0.293 V", "-0.30 V", "+7 mV", "✓ PASS"]
    row = w.operating_tab.rows["min_input"]
    # Rewritten: a space before the unit (was "≥ -0.30V pin min")
    assert text(row["thresh"]) == "≥ -0.30 V pin min" and text(row["status"]) == "✓ PASS"
    type_into(w, "mcu.v_pin_min", "-0.2")
    assert text(s.min_row["status"]) == "✗ FAIL" and text(s.min_row["margin"]) == "-93 mV"
    type_into(w, "mcu.v_pin_min", "")
    assert text(s.min_row["status"]) == NEEDS_INPUT and "Pin Min" in text(w.banner)


def test_analog_error_row(w):
    load_design(w, schottky_rail())
    row = w.safety_tab.error_row
    assert [text(c) for c in row.values()] == ["+3.8 mV", "+0.12 %", "+4.7", NOT_GIVEN, "info"]
    type_into(w, "system.analog_error_allowed_pct", "0.5")
    assert text(row["allowed"]) == "0.50 %" and text(row["status"]) == "✓ PASS"
    type_into(w, "system.analog_error_allowed_pct", "0.1")
    assert text(row["status"]) == "✗ FAIL"
    type_into(w, "mcu.adc_bits", "")
    assert text(row["lsb"]) == NEEDS_INPUT and text(row["mv"]) == "+3.8 mV"
    type_into(w, "system.v_analog_fullscale", "")
    assert {text(c) for c in row.values()} == {NOT_GIVEN}


def test_information_rows(w):
    load_reference(w)
    s = w.safety_tab
    for lbl in (s.touch_pin, s.touch_diode, s.touch_r1, s.rail_current):
        assert text(lbl) == NOT_GIVEN
    verdict = text(w.verdict)
    type_into(w, "system.v_touch", "60")
    assert text(s.touch_pin) == "3.538"
    assert text(s.touch_diode) == "5.57" and text(s.touch_r1) == "326.6"
    assert text(w.verdict) == verdict                    # information only
    assert text(s.rail_current) == NOT_GIVEN             # diode is to GND
    assert "Information (no verdict)" in set(all_label_texts(w))


# ── Tables round-trip through the window ──────────────────────────────────────

@pytest.mark.parametrize("value,state", [(None, NOT_FILLED), ([], NOT_MODELLED)],
                         ids=["null", "empty"])
def test_table_state_survives_open_and_save(w, dialogs, tmp_path, value, state):
    data = zener_reference(clamp_diode__forward=value)
    source, out = tmp_path / "in.div", tmp_path / "out.div"
    source.write_text(json.dumps(data), encoding="utf-8")
    dialogs.askopenfilename.return_value = str(source)
    w._file_open()
    w.update()
    assert table(w, "forward").state_text == state
    assert table(w, "forward").not_modelled_box.get() == ("1" if value == [] else "0")
    dialogs.asksaveasfilename.return_value = str(out)
    assert w._file_save_as() is True
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["clamp_diode"]["forward"] == value
    assert type(saved["clamp_diode"]["forward"]) is type(value)
    assert saved["clamp_diode"]["reverse"] == data["clamp_diode"]["reverse"]


@pytest.mark.parametrize("path", [ZENER_DIV, SCHOTTKY_DIV], ids=["zener", "schottky"])
def test_open_and_save_without_editing_gives_the_file_back(w, dialogs, tmp_path, path):
    """Through the window: every input section exactly as written."""
    out = tmp_path / "out.div"
    dialogs.askopenfilename.return_value = path
    w._file_open()
    w.update()
    assert not w.app_state.is_dirty             # filling the widgets is not an edit
    dialogs.asksaveasfilename.return_value = str(out)
    assert w._file_save_as() is True
    assert out.read_text(encoding="utf-8") == open(path, encoding="utf-8").read()


# ── Panel layout ──────────────────────────────────────────────────────────────

def grid_of(widget_):
    return widget_.master


def test_part_panels_share_one_grid(w):
    """A fixed label column, a field column, a unit column and a "?" column,
    the same in the Clamp Diode, MCU and System panels."""
    keys = {"diode": "diode.part", "diode tail": "diode.source", "mcu": "mcu.vdd",
            "system": "system.v_input_max"}
    for name, key in keys.items():
        grid = grid_of(widget(w, key))
        assert grid.grid_columnconfigure(0)["minsize"] == input_panels.LABEL_W, name
        assert grid.grid_columnconfigure(1)["minsize"] == input_panels.FIELD_W, name
        assert grid.grid_columnconfigure(2)["minsize"] == input_panels.UNIT_W, name
        assert grid.grid_columnconfigure(input_panels.HELP_COL)["minsize"] == input_panels.HELP_W
    # every plain row: entry in the field column, its "?" in the "?" column
    for panel in (w.mcu_panel, w.system_panel):
        for key, btn in panel.help.items():
            if not key.endswith(".source"):
                assert int(panel.widgets[key].grid_info()["column"]) == 1, key
            assert int(btn.grid_info()["column"]) == input_panels.HELP_COL, key
    assert int(w.diode_panel.help["diode.type"].grid_info()["column"]) == input_panels.HELP_COL
    assert int(w.diode_panel.help["diode.anode"].grid_info()["column"]) == input_panels.HELP_COL


def test_clamp_diode_rows(w):
    d = w.diode_panel
    grid = grid_of(widget(w, "diode.part"))
    row = lambda wd: int(wd.grid_info()["row"])
    # Part across the full width
    info = widget(w, "diode.part").grid_info()
    assert (int(info["column"]), int(info["columnspan"]), info["sticky"]) == (1, 4, "ew")
    # Type with its "?"
    assert row(widget(w, "diode.type")) == row(d.help["diode.type"]) == 1
    # Anode and Cathode on one row, with one "?"
    pair = grid_of(widget(w, "diode.anode"))
    assert pair is grid_of(widget(w, "diode.cathode")) and pair.master is grid
    assert row(pair) == row(d.help["diode.anode"]) == 2
    assert "diode.cathode" not in d.help
    assert [t for t in all_label_texts(pair)] == ["Anode", "Cathode"]
    # Rewritten: Capacitance (pF) and Ptot (mW) have a row each on the grid,
    # with the "?" in the "?" column (was: one row, each "?" beside its unit).
    for i, (key, unit) in enumerate((("diode.capacitance_pf", "pF"), ("diode.ptot_mw", "mW")),
                                    start=3):
        entry, help_ = widget(w, key), d.help[key]
        assert entry.master is grid and help_.master is grid
        assert row(entry) == row(help_) == i
        assert int(entry.grid_info()["column"]) == 1
        assert int(help_.grid_info()["column"]) == input_panels.HELP_COL
        units = [c for c in grid.grid_slaves(row=i, column=2)]
        assert [text(u) for u in units] == [unit]
    assert d.help["diode.capacitance_pf"] is not d.help["diode.ptot_mw"]
    labels = [t for t in all_label_texts(grid) if t.endswith(":")]
    assert labels == ["Part:", "Type:", "Connection:", "Capacitance:", "Ptot:"]


def test_diode_tables_are_real_grids(w):
    load_design(w, schottky_rail())
    for name in ("forward", "reverse"):
        t = table(w, name)
        assert [h.cget("text") for h in t.headers] == ["I (mA)", "V min", "V typ", "V max"]
        for col, (header, key) in enumerate(zip(t.headers, ("i_ma", "v_min", "v_typ", "v_max"))):
            assert int(header.grid_info()["column"]) == col and int(header.grid_info()["row"]) == 0
            assert header.master is t.grid_frame
            for i, cells in enumerate(t.cells):
                info = cells[key].grid_info()
                assert (int(info["column"]), int(info["row"])) == (col, i + 1)
                assert cells[key].cget("width") == t.CELL_W == header.cget("width")
                assert info["padx"] == header.grid_info()["padx"]
        # one delete button per row, after the last column
        assert len(t.delete_buttons) == len(t.cells)
        assert all(int(b.grid_info()["column"]) == 4 for b in t.delete_buttons)
        # "+ Add row" directly under the table, on the left
        order = t.pack_slaves()
        assert order.index(t.foot) == order.index(t.grid_frame) + 1 == len(order) - 1
        assert t.foot.pack_slaves()[0] is t.add_button
        assert t.add_button.pack_info()["side"] == "left"
        assert t.not_modelled_box.cget("text") == "Not modelled"


# ── Source and Note ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("section", ["diode", "mcu"])
def test_source_and_note_boxes(w, dialogs, tmp_path, section):
    load_design(w, schottky_rail())
    panel = w.diode_panel if section == "diode" else w.mcu_panel
    source, note = widget(w, f"{section}.source"), widget(w, f"{section}.note")
    key = "clamp_diode" if section == "diode" else "mcu"
    # Source: a two-line wrapping box holding the file's "source"
    assert isinstance(source, ctk.CTkTextbox) and isinstance(note, ctk.CTkTextbox)
    assert source._textbox.cget("wrap") == "word" and note._textbox.cget("wrap") == "word"
    assert source.cget("height") == panel._lines_height(2)
    assert source.get("1.0", "end-1c") == schottky_rail()[key]["source"]
    # Note: shows the whole note; the box grows with it, up to 16 lines, then scrolls
    assert note.get("1.0", "end-1c") == schottky_rail()[key]["note"]
    lines = panel.wrapped_lines(f"{section}.note")
    assert note.cget("height") == panel._lines_height(max(3, min(16, lines)))
    type_into(w, f"{section}.note", "short")
    assert note.cget("height") == panel._lines_height(3)
    # saved back unchanged unless edited
    out = tmp_path / "out.div"
    dialogs.asksaveasfilename.return_value = str(out)
    type_into(w, f"{section}.source", "DS rev 9,\nTable 1")
    assert w._file_save_as() is True
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved[key]["source"] == "DS rev 9,\nTable 1" and saved[key]["note"] == "short"
    other = "mcu" if section == "diode" else "clamp_diode"
    assert saved[other]["source"] == schottky_rail()[other]["source"]
    assert saved[other]["note"] == schottky_rail()[other]["note"]


def test_editing_a_value_unticks_checked(w):
    load_design(w, schottky_rail())
    diode_box, mcu_box = widget(w, "diode.checked"), widget(w, "mcu.checked")

    def tick():
        for box in (diode_box, mcu_box):
            if box.get() != "1":
                box.toggle()
        w.update()
        assert diode_box.get() == mcu_box.get() == "1"

    tick()
    # name, source and note are not values
    for key in ("diode.part", "diode.source", "diode.note", "mcu.part", "mcu.source", "mcu.note"):
        type_into(w, key, "edited")
    type_into(w, "r1.value", "12")
    type_into(w, "system.v_input_max", "24")
    assert diode_box.get() == mcu_box.get() == "1"
    # a diode value unticks the diode's box only
    type_into(w, "diode.capacitance_pf", "12")
    assert diode_box.get() == "0" and mcu_box.get() == "1"
    assert w.app_state.fields["diode.checked"] == "0"
    for edit in (lambda: type_into(w, "diode.type", "zener"),
                 lambda: type_into(w, "diode.cathode", "gnd"),
                 lambda: type_cell(w, "forward", 0, "v_typ", "0.16"),
                 lambda: (table(w, "reverse").add_button.invoke(), w.update()),
                 lambda: (table(w, "reverse").delete_buttons[-1].invoke(), w.update())):
        tick()
        edit()
        assert diode_box.get() == "0" and mcu_box.get() == "1"
    # an MCU value unticks the MCU's box only
    for key, value in (("mcu.vdd", "3.0"), ("mcu.pin_type", "FT"), ("mcu.c_pin_pf", "6")):
        tick()
        type_into(w, key, value)
        assert mcu_box.get() == "0" and diode_box.get() == "1", key
    # ticking is never undone by ticking itself or by saving
    tick()
    assert w.app_state.get_data()["mcu"]["checked"] is True


# ── Tooltips ──────────────────────────────────────────────────────────────────

def pump(w, ms):
    """Let Tk run for *ms* milliseconds (timers included)."""
    done = []
    w.after(ms, lambda: done.append(1))
    while not done:
        w.update()


@pytest.fixture
def tips(w):
    _Tooltip.hide_current()
    yield w.mcu_panel.help["mcu.vdd"].tooltip, w.mcu_panel.help["mcu.v_recommended_max"].tooltip
    _Tooltip.hide_current()


def test_tooltip_is_gone_after_a_leave_event(w, tips):
    tip, _ = tips
    tip.show()
    w.update()
    assert tip.visible and _Tooltip.current is tip and tip._tw.winfo_exists()
    window = tip._tw
    tip.on_leave(None)
    w.update()
    assert not tip.visible and _Tooltip.current is None and not window.winfo_exists()
    # the handler is what <Leave> and a click on the "?" are bound to
    for sequence in ("<Enter>", "<Leave>", "<ButtonPress>"):
        assert tip.widget._canvas.bind(sequence) or tip.widget._label.bind(sequence), sequence


def test_tooltip_is_gone_after_a_tab_change(w, tips):
    tip, _ = tips
    w.tabs.set("Component Analysis")
    tip.show()
    w.update()
    assert tip.visible
    w.tabs._segmented_button_callback("MCU Input")      # what a click on the tab does
    w.update()
    assert w.tabs.get() == "MCU Input"
    assert not tip.visible and _Tooltip.current is None
    w.tabs.set("Component Analysis")


def test_tooltip_waits_and_is_cancelled_by_leaving(w, tips, monkeypatch):
    tip, _ = tips
    assert _Tooltip.DELAY_MS == 500
    monkeypatch.setattr(tip, "_pointer_over", lambda: True)
    # leaves before the delay: never shown
    tip.on_enter(None)
    pump(w, 150)
    assert tip.pending and not tip.visible
    tip.on_leave(None)
    pump(w, 500)
    assert not tip.pending and not tip.visible
    # stays: shown after about 500 ms, not before
    tip.on_enter(None)
    pump(w, 350)
    assert not tip.visible
    pump(w, 300)
    assert tip.visible and not tip.pending
    # ... and it goes by itself once the pointer is no longer over the "?"
    monkeypatch.setattr(tip, "_pointer_over", lambda: False)
    pump(w, 2 * _Tooltip.WATCH_MS + 100)
    assert not tip.visible


def test_tooltip_not_shown_if_the_pointer_has_gone(w, tips):
    tip, _ = tips
    tip.on_enter(None)                  # the real pointer is not over the withdrawn window
    pump(w, 650)
    assert not tip.visible and not tip.pending


def test_only_one_tooltip_at_a_time(w, tips):
    first, second = tips
    first.show()
    w.update()
    second.show()
    w.update()
    assert second.visible and not first.visible and _Tooltip.current is second
    assert len([t for t in _Tooltip.instances if t.visible]) == 1
    # a waiting tooltip is cancelled when another event hides tooltips
    first.on_enter(None)
    _Tooltip.hide_current()
    assert not first.pending and not second.visible


def test_tooltip_hides_on_scroll_click_focus_loss_and_window_move(w, tips):
    tip, _ = tips
    # scroll and click anywhere: bound for the whole application
    for sequence in ("<MouseWheel>", "<ButtonPress>"):
        assert "hide_current" in w.bind_all(sequence), sequence
    for sequence in ("<FocusOut>", "<Configure>"):
        assert w.bind(sequence), sequence
    on_configure, on_focus_out = w.tooltip_handlers["configure"], w.tooltip_handlers["focus_out"]

    # window move: a <Configure> of the window itself with a new position
    def configure(widget_, x, y):
        on_configure(types.SimpleNamespace(widget=widget_, x=x, y=y, width=1400, height=900))
    configure(w, 10, 10)
    tip.show()
    w.update()
    configure(w, 10, 10)                    # same place: not a move
    configure(w.banner, 300, 40)            # a child being laid out: not a move
    assert tip.visible
    configure(w, 50, 40)
    assert not tip.visible

    # focus moving inside the window is not a loss; focus leaving the application is
    tip.show()
    w.update()
    real = w.focus_displayof
    try:
        w.focus_displayof = lambda: w.banner
        on_focus_out(types.SimpleNamespace(widget=w))
        pump(w, 30)
        assert tip.visible
        w.focus_displayof = lambda: None
        on_focus_out(types.SimpleNamespace(widget=w))
        pump(w, 30)
        assert not tip.visible
    finally:
        w.focus_displayof = real


def test_tooltip_is_placed_away_from_the_pointer(w, tips, monkeypatch):
    """Offset from the pointer, and flipped to the other side at a screen
    edge, so it is never under the cursor."""
    tip, _ = tips
    screen_w, screen_h = w.winfo_screenwidth(), w.winfo_screenheight()
    for px, py in ((300, 200), (screen_w - 5, 200), (300, screen_h - 5),
                   (screen_w - 5, screen_h - 5)):
        monkeypatch.setattr(tip.widget, "winfo_pointerxy", lambda px=px, py=py: (px, py))
        tip.show()
        w.update()
        x, y, width, height = tip.position
        assert not (x <= px < x + width and y <= py < y + height), (px, py)
        assert x == px + 16 or x + width == px - 16, (px, py)
        assert y == py + 20 or y + height == py - 20, (px, py)
        assert x + width <= screen_w and y + height <= screen_h
        assert tip._tw.winfo_x() == x and tip._tw.winfo_y() == y
        tip.hide()
    assert tip.position[:2] != (300 + 16, 200 + 20)       # the last one was flipped


# ── Small fixes ───────────────────────────────────────────────────────────────

def test_abs_max_has_a_help_button(w):
    help_ = w.mcu_panel.help
    for key in ("mcu.pin_type", "mcu.vdd", "mcu.v_recommended_max", "mcu.v_absolute_max",
                "mcu.v_pin_min", "mcu.adc_bits", "mcu.vil_factor", "mcu.vih_factor",
                "mcu.c_pin_pf", "mcu.t_pulse_min_ns"):
        assert key in help_, key
    assert "Absolute maximum pin voltage" in help_["mcu.v_absolute_max"].tooltip.text
    for key in ("system.v_input_max", "system.v_logic_high_min", "system.v_logic_low_max"):
        assert key in w.system_panel.help, key


def test_system_footnote_is_fully_visible(w):
    note = w.system_panel.footnote
    assert text(note) == "Optional values left blank leave their check out."
    info = note.pack_info()
    assert info["fill"] == "x" and info["pady"] == (2, 12)      # room below it
    assert w.system_panel.pack_slaves()[-1] is note             # its own row, last
    assert 0 < note.cget("wraplength") <= 420                   # wraps inside the panel


def test_theme_label_comes_before_the_drop_down(w):
    label, menu = w.plot.theme_label, w.plot.theme_var
    assert text(label) == "Theme:"
    assert label.pack_info()["side"] == menu.pack_info()["side"] == "right"
    # packed from the right: the drop-down first, so the label is to its left
    order = label.master.pack_slaves()
    assert order.index(menu) < order.index(label)


# ── Input Levels: both limits at Max Input, the judged value in bold ──────────

def test_max_input_row_shows_both_limits_and_the_worse_status(w):
    """Safe Max and Absolute Max, with the worse of the two statuses, so the
    row agrees with the overall verdict."""
    load_design(w, schottky_rail())
    row, safety = w.operating_tab.rows["max_input"], w.safety_tab
    assert [text(c) for c in row.values()] == [
        "30.00 V", "3.442 V", "3.651 V", "≤ 3.60 V safe / ≤ 4.00 V abs", "✗ FAIL"]
    assert text(safety.rec_row["status"]) == "✗ FAIL"
    assert text(safety.abs_row["status"]) == "✓ PASS"
    assert "Safe Max" in text(w.verdict) and "Abs. Max" not in text(w.verdict)
    # TIGHT against Safe Max, PASS against Absolute Max
    type_into(w, "mcu.v_recommended_max", "3.67")
    assert text(row["thresh"]) == "≤ 3.67 V safe / ≤ 4.00 V abs"
    assert text(row["status"]) == "⚠ TIGHT"
    # PASS against both
    type_into(w, "mcu.v_recommended_max", "3.8")
    assert text(row["status"]) == "✓ PASS"
    # the status follows Absolute Max as well
    type_into(w, "mcu.v_absolute_max", "3.7")
    assert text(row["thresh"]) == "≤ 3.80 V safe / ≤ 3.70 V abs"
    assert text(row["status"]) == text(safety.abs_row["status"]) == "⚠ TIGHT"
    type_into(w, "mcu.v_absolute_max", "3.6")
    assert text(row["status"]) == text(safety.abs_row["status"]) == "✗ FAIL"
    # a blank limit is named; with both blank the cell says "needs input"
    type_into(w, "mcu.v_absolute_max", "")
    assert text(row["thresh"]) == "≤ 3.80 V safe / Abs. Max: needs input"
    assert text(row["status"]) == NEEDS_INPUT
    type_into(w, "mcu.v_recommended_max", "")
    assert text(row["thresh"]) == NEEDS_INPUT and text(row["status"]) == NEEDS_INPUT


def test_value_each_row_is_judged_on_is_bold(w):
    rows = w.operating_tab.rows

    def bold(level):
        return {key for key in ("v_in", "v_mcu_l", "v_mcu_h", "thresh")
                if "bold" in rows[level][key].cget("font")}

    load_reference(w)
    assert bold("logic_high") == {"v_mcu_l"}        # must stay above VIH
    assert bold("logic_low") == {"v_mcu_h"}         # must stay below VIL
    assert bold("analog_fullscale") == {"v_mcu_h"}
    assert bold("max_input") == {"v_mcu_h"}
    # rows with no check: nothing in bold
    for level in ("zero", "touch", "min_input"):
        assert bold(level) == set(), level
    type_into(w, "system.v_touch", "60")
    assert text(rows["touch"]["v_mcu_h"]) == "3.538 V" and bold("touch") == set()
    type_into(w, "system.v_analog_fullscale", "")
    assert bold("analog_fullscale") == set()
    # Min Input is judged (on V_mcuL) only when it is negative
    load_design(w, schottky_gnd())
    type_into(w, "system.v_input_min", "-5")
    assert text(rows["min_input"]["v_mcu_l"]) == "-0.293 V" and bold("min_input") == {"v_mcu_l"}
    type_into(w, "system.v_input_min", "2")
    assert text(rows["min_input"]["status"]) == "info" and bold("min_input") == set()
    assert any("Bold: the value the row is judged on." in t for t in all_label_texts(w))


# ── Plot: lowest curve, band, VIH and VIL, legend outside ─────────────────────

def test_plot_has_the_lowest_curve_and_the_band(w):
    load_reference(w)
    plot, p = w.plot, w.app_state.plot_data
    low, high = plot.lines["v_mcu_low"], plot.lines["v_mcu_worst"]
    assert low.get_label() == "V_mcuL (worst case)"
    assert list(low.get_xdata()) == p["v_in"] and list(low.get_ydata()) == p["v_mcu_low"]
    assert list(high.get_ydata()) == p["v_mcu_worst"]
    assert low in plot.ax.lines and plot.ax.lines[0] is plot.lines["v_mcu_typ"]
    # the band between the lowest and the highest is shaded
    assert plot.band is not None and plot.band in plot.ax.collections
    ys = [float(y) for y in plot.band.get_paths()[0].vertices[:, 1]]
    assert min(ys) == min(p["v_mcu_low"]) and max(ys) == max(p["v_mcu_worst"])
    assert 0 < plot.band.get_alpha() < 0.3
    # the curve and the Input Levels table agree at Max Input
    row = w.operating_tab.rows["max_input"]
    assert f"{low.get_ydata()[-1]:.3f} V" == text(row["v_mcu_l"]) == "2.840 V"
    assert f"{high.get_ydata()[-1]:.3f} V" == text(row["v_mcu_h"]) == "3.239 V"
    # no tolerance: no corners, so no lowest curve and no band
    type_into(w, "r1.tol", "")
    assert set(plot.lines) & {"v_mcu_typ", "v_mcu_low", "v_mcu_worst"} == {"v_mcu_typ"}
    assert plot.band is None and not plot.ax.collections


def test_plot_has_vih_and_vil_lines_with_labels(w):
    load_reference(w)
    plot, volts = w.plot, w.app_state.results["voltages"]
    for key, name in (("vih", "VIH"), ("vil", "VIL")):
        line = plot.lines[key]
        assert [float(y) for y in line.get_ydata()] == [volts[key], volts[key]]    # horizontal
        assert line.get_linewidth() <= 1 < plot.lines["v_mcu_typ"].get_linewidth()  # thin
        assert line.get_linewidth() < plot.lines["vdd"].get_linewidth()
        label = plot.level_labels[key]              # named on the line itself
        assert label.get_text() == name and label.xy == (1.0, volts[key])
    legend = [t.get_text() for t in plot.ax.get_legend().get_texts()]
    assert "VIH (2.31V)" in legend and "VIL (0.99V)" in legend
    # the logic-high failure shows: at the Logic High input the lowest curve is under VIH
    lowest = w.app_state.circuit.pin_voltage(3.8, "low")
    assert lowest < volts["vih"] and text(w.operating_tab.rows["logic_high"]["status"]) == "✗ FAIL"
    # a blank factor removes its line only
    type_into(w, "mcu.vih_factor", "")
    assert "vih" not in plot.lines and "vih" not in plot.level_labels
    assert "vil" in plot.lines and plot.has_curves


@pytest.mark.parametrize("theme", ["Dark", "Light"])
@pytest.mark.parametrize("design", [zener_reference, schottky_rail, schottky_gnd])
def test_legend_is_outside_the_plot_area(w, design, theme):
    load_design(w, design(system__v_input_min=-5.0) if design is schottky_gnd else design())
    plot = w.plot
    plot.theme_var.set(theme)
    plot._on_theme_change(theme)
    try:
        plot.canvas.draw()
        renderer = plot.canvas.get_renderer()
        axes = plot.ax.get_window_extent(renderer)
        legend = plot.ax.get_legend().get_window_extent(renderer)
        figure = plot.fig.bbox
        assert legend.x0 >= axes.x1                 # to the right of the plot area
        assert legend.x1 <= figure.x1 and figure.y0 <= legend.y0 and legend.y1 <= figure.y1
        assert axes.width > 0.6 * figure.width      # and the plot area keeps most of the width
        # every line is in the legend, in the order they appear from top to bottom
        assert [t.get_text() for t in plot.ax.get_legend().get_texts()] == [
            "V_mcuH (worst case)", "V_mcu (typical)", "V_mcuL (worst case)",
            "Abs. Max (4V)", "Safe Max (3.6V)", "VDD (3.3V)", "VIH (2.31V)", "VIL (0.99V)"]
    finally:
        plot.theme_var.set("Dark")
        plot._on_theme_change("Dark")


# ── Layout in the shown window (1400x900) ─────────────────────────────────────

TAB_NAMES = ("Component Analysis", "MCU Input", "Input Levels", "Signal Bandwidth")


@pytest.fixture
def shown(w):
    """The window on the screen at 1400x900: these tests need real sizes,
    which a withdrawn window does not have."""
    w.geometry("1400x900+40+40")
    w.deiconify()
    pump(w, 300)
    if (w.winfo_width(), w.winfo_height()) != (1400, 900):
        w.withdraw()
        pytest.skip("needs a screen that a 1400x900 window fits on")
    yield w
    w.tabs.set("Component Analysis")
    pump(w, 200)
    w.withdraw()
    w.update()


def select_tab(w, name):
    w.tabs.set(name)
    pump(w, 200)        # CTkTabview.set() finishes 100 ms later


def left_x(wd):
    return wd.winfo_rootx()


def test_plot_keeps_its_height_on_every_tab(shown):
    """About 350 px for the plot at 1400x900, on the Component Analysis tab
    too: that tab's content scrolls."""
    w = shown
    load_design(w, schottky_rail())
    canvas = w.plot.canvas.get_tk_widget()
    for name in TAB_NAMES:
        select_tab(w, name)
        assert canvas.winfo_height() >= 350, name
    select_tab(w, "Component Analysis")
    scroll = w.components_scroll
    assert isinstance(scroll, ctk.CTkScrollableFrame)
    assert w.components_tab.r_total.winfo_ismapped()
    # more content than fits: all of it is reached by scrolling
    first, last = scroll._parent_canvas.yview()
    assert first == 0 and last < 1
    scroll._parent_canvas.yview_moveto(1)
    w.update()
    assert scroll._parent_canvas.yview()[1] == 1
    assert w.components_tab.vclamp_worst.winfo_ismapped()
    scroll._parent_canvas.yview_moveto(0)


def test_resistor_panel_is_on_the_shared_grid(shown):
    """The label column, the value column and the "?" column of the other
    panels; value, unit, rating and tolerance on one row."""
    w = shown
    load_design(w, schottky_rail())
    panel, grid = w.resistor_panel, w.resistor_panel.grid_frame
    assert grid.grid_columnconfigure(0)["minsize"] == input_panels.LABEL_W
    assert grid.grid_columnconfigure(1)["minsize"] == input_panels.FIELD_W
    assert grid.grid_columnconfigure(panel.HELP_COL)["minsize"] == input_panels.HELP_W
    field, help_ = widget(w, "mcu.vdd"), w.mcu_panel.help["mcu.vdd"]
    part_label = [c for c in grid_of(field).grid_slaves(column=0) if text(c) == "VDD/VDDA:"][0]
    assert [text(h) for h in panel.headers] == ["Value", "Unit", "Rating (mW)", "Tol. (%)"]
    for i, (prefix, name) in enumerate((("r1", "R1:"), ("r2", "R2:"), ("rs", "R_s:")), start=1):
        fields = [widget(w, f"{prefix}.{n}") for n in ("value", "unit", "rating", "tol")]
        # one row, in the grid, left to right
        assert all(f.master is grid and int(f.grid_info()["row"]) == i for f in fields)
        assert [int(f.grid_info()["column"]) for f in fields] == [1, 2, 3, 4]
        xs = [left_x(f) for f in fields]
        assert xs == sorted(xs)
        # the label, the value field and the "?" line up with the panels below
        label = grid.grid_slaves(row=i, column=0)[0]
        assert text(label) == name and left_x(label) == left_x(part_label)
        assert left_x(fields[0]) == left_x(field)
        assert fields[0].winfo_width() == field.winfo_width() == input_panels.FIELD_W
        button = panel.help[f"{prefix}.value"]
        assert int(button.grid_info()["row"]) == i
        assert int(button.grid_info()["column"]) == panel.HELP_COL
        assert left_x(button) == left_x(help_)
        # nothing runs into the "?" column
        assert left_x(fields[-1]) + fields[-1].winfo_width() < left_x(button)
        for header, f in zip(panel.headers, fields):
            assert left_x(header) == left_x(f)
    assert "no series resistor" in panel.help["rs.value"].tooltip.text
    assert "power rating" in panel.help["r1.value"].tooltip.text


def test_capacitance_and_ptot_help_is_in_the_help_column(shown):
    w = shown
    d = w.diode_panel
    field, help_ = widget(w, "mcu.vdd"), w.mcu_panel.help["mcu.vdd"]
    for key in ("diode.capacitance_pf", "diode.ptot_mw"):
        assert left_x(d.help[key]) == left_x(d.help["diode.type"]) == left_x(help_)
        assert left_x(widget(w, key)) == left_x(field)
        assert widget(w, key).winfo_width() == field.winfo_width()
    assert "Signal Bandwidth time constant" in d.help["diode.capacitance_pf"].tooltip.text
    assert "Power rating of the diode" in d.help["diode.ptot_mw"].tooltip.text
