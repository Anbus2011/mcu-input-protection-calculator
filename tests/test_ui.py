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
from src.ui.input_panels import NEEDS_INPUT, _Tooltip
from src.ui.main_window import MainWindow
from tests.designs import V1_FILE, schottky_gnd, schottky_rail, typed, zener_reference

EXAMPLES = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "examples"))
ZENER_DIV = os.path.join(EXAMPLES, "zener_gnd_bzb984_c3v3.div")
SCHOTTKY_DIV = os.path.join(EXAMPLES, "schottky_rail_bat54cv.div")
OHM, KOHM, MOHM = "Ω", "kΩ", "MΩ"

NUMERIC_KEYS = [k for k, f in FIELDS.items() if f.kind in ("float", "int")]
BLOCKED, NOT_GIVEN, NO_RS = "n/a (see note)", "--", "no R_s"


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
        for i, row in enumerate(rows):
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


BW_CELLS = ("c_total", "tau", "t_rise", "t_fall", "t_shortest", "f_may_work", "f_reliable")


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
    assert text(w.bandwidth_tab.f_may_work) == "1346.9"
    assert text(w.bandwidth_tab.f_reliable) == "898.0"
    d = w.bw_input_panel.derived
    assert text(d["c_diode_pf"]) == "10" and text(d["c_pin_pf"]) == "5"
    assert text(d["t_pulse_min_ns"]) == "17.65"
    assert text(d["vil_v"]) == "0.990" and text(d["vih_v"]) == "2.310"
    assert not w.app_state.is_dirty
    # the fill button puts back only what is blank
    type_into(w, "bw.c_stray_pf", "")
    assert text(w.bandwidth_tab.c_total) == NEEDS_INPUT
    w.bw_input_panel.fill_button.invoke()
    w.update()
    assert widget(w, "bw.c_stray_pf").get() == "3"
    assert text(w.bandwidth_tab.c_total) == "18.0"


def test_pin_never_reads_high_shown_on_tab(w):
    load_reference(w)                       # 3.8 V Logic High: pin 1.83 V < VIH 2.31 V
    assert "never reads high" in text(w.bandwidth_tab.note)
    assert text(w.bandwidth_tab.f_reliable) == BLOCKED
    assert text(w.bandwidth_tab.f_may_work) == BLOCKED
    assert text(w.bandwidth_tab.tau) not in (NEEDS_INPUT, BLOCKED)
    type_into(w, "system.v_logic_high_min", "24")
    assert text(w.bandwidth_tab.note) == ""
    assert text(w.bandwidth_tab.f_reliable) not in (NEEDS_INPUT, BLOCKED)


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
    assert text(forward.note) == "" and text(reverse.note) == ""
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
    assert forward.cells == [] and text(forward.note) == \
        "no forward data: forward conduction not included"
    w.app_state.is_dirty = False
    forward.add_button.invoke()
    forward.add_button.invoke()
    w.update()
    assert len(forward.cells) == 2 and len(w.app_state.tables["forward"]) == 2
    assert text(forward.note) == "" and w.app_state.is_dirty
    assert "Forward table row 1 current" in text(w.banner)
    for i, row in enumerate(((1, 0.6, 0.7, 0.8), (10, 0.7, 0.8, 0.9))):
        for key, value in zip(("i_ma", "v_min", "v_typ", "v_max"), row):
            type_cell(w, "forward", i, key, str(value))
    assert text(w.banner) == "All inputs present."
    forward.delete_buttons[0].invoke()
    w.update()
    assert len(forward.cells) == 1 and forward.cells[0]["i_ma"].get() == "10"
    assert "Forward table: needs at least 2 rows" in text(w.banner)
    forward.delete_buttons[0].invoke()
    w.update()
    assert forward.cells == [] and text(w.banner) == "All inputs present."
    assert text(forward.note) == "no forward data: forward conduction not included"


def test_no_reverse_data_note(w):
    load_reference(w)
    assert text(table(w, "reverse").note) == ""
    w.app_state.set_table("reverse", [])
    w.update()
    assert text(table(w, "reverse").note) == "no reverse data: leakage not included"
    assert text(w.components_tab.vclamp_typ) == f"{30 * 18 / 28:.3f}"


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
    assert [text(c) for c in rows["logic_high"].values()] == [
        "3.80 V", "1.831 V", "2.110 V", "> VIH 2.31V", "✗ FAIL"]
    assert [text(c) for c in rows["logic_low"].values()] == [
        "1.00 V", "0.637 V", "0.647 V", "< VIL 0.99V", "✓ PASS"]
    assert [text(c) for c in rows["analog_fullscale"].values()] == [
        "5.10 V", "2.019 V", "2.352 V", "≤ VDD 3.30V", "✓ PASS"]
    assert [text(c) for c in rows["max_input"].values()] == [
        "30.00 V", "2.840 V", "3.239 V", "≤ 4.0V abs", "✓ PASS"]
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
    assert text(row["thresh"]) == "≥ -0.30V pin min" and text(row["status"]) == "✓ PASS"
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
