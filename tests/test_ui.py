"""
UI tests that drive the real MainWindow (bug 11).

One window is created per module and withdrawn; tests type into the real
widgets, call update(), and patch messagebox / filedialog. Needs a desktop
session (Tk display).
Run with: python -m pytest tests/ -v
"""
import json
import types
import os
from unittest import mock

import customtkinter as ctk
import pytest

from src.core.app_state import FIELDS
from src.ui import main_window as main_window_module
from src.ui.input_panels import NEEDS_INPUT
from src.ui.main_window import MainWindow

RESULTS_DIV = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "results.div"))
OHM, KOHM, MOHM = "Ω", "kΩ", "MΩ"

REFERENCE = {
    "r1.value": "10", "r1.unit": KOHM, "r1.rating": "200", "r1.tol": "1",
    "r2.value": "18", "r2.unit": KOHM, "r2.rating": "100", "r2.tol": "1",
    "rs.value": "0", "rs.unit": OHM,
    "mcu.vdd": "3.3", "mcu.v_recommended_max": "3.6", "mcu.v_absolute_max": "4.0",
    "mcu.safe_injection_ma": "1.0", "mcu.adc_bits": "12",
    "mcu.vil_factor": "0.3", "mcu.vih_factor": "0.7",
    "system.v_input_max": "30", "system.v_analog_fullscale": "5.1",
    "system.v_logic_high_min": "3.8", "system.v_logic_low_max": "1.0",
}
NUMERIC_KEYS = [k for k, f in FIELDS.items() if f.kind in ("float", "int")]


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


def type_into(w, key, text):
    """Set a field the way a user would, through its widget."""
    wd = widget(w, key)
    if isinstance(wd, ctk.CTkComboBox):
        wd.set(text)
    elif isinstance(wd, ctk.CTkCheckBox):
        if (wd.get() == "1") != (text == "1"):
            wd.toggle()
    else:
        wd.delete(0, "end")
        if text:
            wd.insert(0, text)
    w.update()


def type_reference(w):
    """Type the whole reference case through the widgets (slow, used once)."""
    for key, text in REFERENCE.items():
        type_into(w, key, text)
    w.zener_panel.preset._dropdown_callback("BZB984-C3V3")
    w.update()


def load_reference(w):
    """Fast setup: put the reference case in AppState; the widgets follow."""
    w.app_state.set_fields(REFERENCE)
    w.app_state.select_zener_preset("BZB984-C3V3")
    w.update()
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
        "source_z": s.source_z, "sample_cyc": s.sample_cyc, "resolution": s.resolution,
    }
    for name, row in (("r1", c.r1_row), ("r2", c.r2_row), ("z", c.z_row), ("rs", c.rs_row),
                      ("rec", s.rec_row), ("abs", s.abs_row), ("inj", s.inj_row)):
        for k, lbl in row.items():
            out[f"{name}.{k}"] = lbl
    for i, row in enumerate(o.rows):
        for k, lbl in row.items():
            out[f"op{i}.{k}"] = lbl
    for name in ("c_total", "tau", "f_3db", "t_rise", "t_undef_rise", "t_undef_fall",
                 "f_analog", "f_practical", "f_digital", "f_overflow", "f_effective"):
        out[f"bw.{name}"] = getattr(b, name)
    return out


def text(lbl):
    return lbl.cget("text")


def all_label_texts(widget_):
    for child in widget_.winfo_children():
        if isinstance(child, ctk.CTkLabel):
            yield child.cget("text")
        yield from all_label_texts(child)


# ── Bug 3: change tracking on every input ─────────────────────────────────────

@pytest.mark.parametrize("key", list(FIELDS))
def test_every_input_marks_unsaved_and_recalculates(w, key):
    w.app_state.is_dirty = False
    before = w.app_state.result
    if key == "notes":
        w.notes_panel.textbox.insert("1.0", "note")
        w.update()
        assert w.app_state.fields["notes"] == "note"
    else:
        kind = FIELDS[key].kind
        value = {"unit": MOHM, "bool": "1"}.get(kind, "7")
        type_into(w, key, value)
        assert w.app_state.fields[key] == value
        assert w.app_state.result is not before, "no recalculation"
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
    assert w.app_state.resistors.r1_ohms == 10
    w.app_state.is_dirty = False
    w.bw_input_panel.widgets["bw.counter_signed"].toggle()
    w.update()
    assert w.app_state.fields["bw.counter_signed"] == "1"
    assert w.app_state.is_dirty


# ── Bug 4/5/6: blank, 0 and unreadable on every numeric field ─────────────────

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
    # Whatever is computed must agree with the model result now in AppState
    r = s.result
    if r.k_nominal is None:
        assert text(w.components_tab.ratio) == NEEDS_INPUT
    else:
        assert text(w.components_tab.ratio) == f"{r.k_nominal:.4f}"
    if r.v_mcu_worst is None:
        assert text(w.safety_tab.rec_row["value"]) == NEEDS_INPUT
    assert w.plot.has_curves == bool(r.plot_data)


@pytest.mark.parametrize("key", ["r1.value", "r2.value"])
@pytest.mark.parametrize("value", ["", "0"])
def test_r1_r2_blank_or_zero_clears_tables_and_plot(w, key, value):
    load_reference(w)
    assert w.plot.has_curves
    type_into(w, key, value)
    for name in ("op1.v_mcu_l", "op1.v_mcu_h", "op4.v_mcu_h", "op4.status",
                 "rec.value", "rec.status", "abs.status", "inj.value", "inj.status",
                 "vclamp_typ", "ratio"):
        assert text(output_labels(w)[name]) == NEEDS_INPUT, name
    assert not w.plot.has_curves
    assert FIELDS[key].label in w.plot.message


# ── Bug 4: New Design clears everything ───────────────────────────────────────

def test_new_design_clears_everything(w, dialogs):
    load_reference(w)
    w.notes_panel.textbox.insert("1.0", "old notes")
    w.update()
    assert w.plot.has_curves
    assert text(w.components_tab.vclamp_typ) == "3.177"
    w._file_new()
    w.update()
    dialogs.askyesnocancel.assert_called()       # it was unsaved
    # c_total and the counter limit depend only on bandwidth starting values
    independent = {"bw.c_total", "bw.f_overflow", "op0.v_in", "op0.v_mcu_l",
                   "op0.v_mcu_h", "op0.thresh", "op0.status"}
    for name, lbl in output_labels(w).items():
        if name.startswith("rs."):
            assert text(lbl) == "no R_s", (name, text(lbl))    # R_s blank
        elif name not in independent:
            assert text(lbl) in (NEEDS_INPUT, "n/a (see note)"), (name, text(lbl))
    assert not w.plot.has_curves
    assert "Plot needs input" in w.plot.message
    for key in REFERENCE:
        if FIELDS[key].kind != "unit":
            assert widget(w, key).get() == "", key
    assert w.notes_panel.textbox.get("1.0", "end-1c") == ""
    assert w.zener_panel.preset.get() == ""
    assert not w.app_state.is_dirty and w.title().endswith("Untitled")


# ── Bug 7: both save-failure messages ─────────────────────────────────────────

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


def test_reference_typed_through_widgets(w):
    type_reference(w)
    assert text(w.components_tab.r_total) == "28.00"
    assert text(w.components_tab.ratio) == "0.6429"
    assert text(w.components_tab.vclamp_typ) == "3.177"
    assert text(w.components_tab.vclamp_worst) == "3.433"
    assert text(w.components_tab.z_row["current"]) == "2.51 mA"
    assert text(w.banner) == "All inputs present."


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
    assert widget(w, "r1.value").get() == "10"
    assert text(w.components_tab.vclamp_typ) == "3.177"


# ── Bug 8: loading from the window ────────────────────────────────────────────

def test_malformed_file_keeps_current_design(w, dialogs, tmp_path):
    load_reference(w)
    data = json.load(open(RESULTS_DIV, encoding="utf-8"))
    data["resistors"]["r1"]["unit"] = "kOhm"
    bad = tmp_path / "bad.div"
    bad.write_text(json.dumps(data), encoding="utf-8")
    title_before = w.title()
    dialogs.askopenfilename.return_value = str(bad)
    w._file_open()
    w.update()
    title, message = dialogs.showerror.call_args[0]
    assert "resistors.r1.unit" in message
    assert widget(w, "r1.value").get() == "10"
    assert w.title() == title_before and w.app_state.is_dirty


def test_failed_load_keeps_change_tracking(w, dialogs, monkeypatch):
    def boom():
        raise RuntimeError("sync failed")
    monkeypatch.setattr(w.resistor_panel, "sync_from_state", boom)
    dialogs.askopenfilename.return_value = RESULTS_DIV
    w._file_open()
    dialogs.showerror.assert_called_once()
    monkeypatch.undo()
    assert w.app_state.ignore_changes is False
    w.app_state.is_dirty = False
    type_into(w, "r2.rating", "50")
    assert w.app_state.is_dirty


# ── Bug 9: preset shown as modified ───────────────────────────────────────────

def test_preset_shows_modified(w):
    w.zener_panel.preset._dropdown_callback("BZB984-C3V3")
    w.update()
    assert widget(w, "zener.vz_max").get() == "3.5"
    assert w.zener_panel.preset.get() == "BZB984-C3V3"
    assert text(w.zener_panel.modified_label) == ""
    type_into(w, "zener.vz_max", "3.6")
    assert w.zener_panel.preset.get() == "Custom"
    assert text(w.zener_panel.modified_label) == "modified from BZB984-C3V3"
    type_into(w, "zener.vz_max", "3.5")
    assert w.zener_panel.preset.get() == "BZB984-C3V3"


# ── Bug 1: results.div gives non-blank bandwidth outputs ──────────────────────

def test_results_div_bandwidth_outputs(w, dialogs):
    dialogs.askopenfilename.return_value = RESULTS_DIV
    w._file_open()
    w.update()
    warning = dialogs.showwarning.call_args[0][1]
    assert "C_diode" in warning and "VIL factor" in warning
    w.bw_input_panel.fill_button.invoke()
    type_into(w, "mcu.vil_factor", "0.3")
    type_into(w, "mcu.vih_factor", "0.7")
    labels = output_labels(w)
    for name in ("bw.c_total", "bw.tau", "bw.f_3db", "bw.t_rise", "bw.t_undef_rise",
                 "bw.t_undef_fall", "bw.f_analog", "bw.f_practical", "bw.f_digital",
                 "bw.f_overflow", "bw.f_effective"):
        assert text(labels[name]) not in (NEEDS_INPUT, "n/a (see note)", ""), name
    d = w.bw_input_panel.derived
    assert text(d["r_tau_ohms"]) == f"{8200 * 29000 / 37200:.0f}"
    assert text(d["vil_v"]) == "0.990" and text(d["vih_v"]) == "2.310"
    assert float(text(d["v_high"])) > 2.31
    assert w.app_state.is_dirty


def test_never_reaches_vih_shown_on_tab(w):
    load_reference(w)
    type_into(w, "system.v_logic_high_min", "3.0")
    assert "never reaches VIH" in text(w.bandwidth_tab.note)
    assert text(w.bandwidth_tab.f_effective) == "n/a (see note)"
    assert text(w.bandwidth_tab.f_overflow) not in (NEEDS_INPUT, "n/a (see note)")


# ── Plot clearing ─────────────────────────────────────────────────────────────

def test_plot_clears_and_redraws(w):
    load_reference(w)
    assert w.plot.has_curves
    type_into(w, "system.v_input_max", "")
    assert not w.plot.has_curves
    assert "Max Input" in w.plot.message
    type_into(w, "system.v_input_max", "30")
    assert w.plot.has_curves


# ── Bug 10 / question c: label and warnings ───────────────────────────────────

def test_source_impedance_label_renamed(w):
    labels = set(all_label_texts(w))
    assert "ADC Source Impedance (R1∥R2 + R_s)" in labels
    assert "ADC Source Impedance (R1∥R2)" not in labels


def test_low_value_divider_converges_without_warning(w):
    """Rewritten: R1 = R2 = 100 ohm used to show "did not settle"; the
    bisection solver converges there."""
    load_reference(w)
    type_into(w, "r1.value", "100")
    type_into(w, "r1.unit", OHM)
    type_into(w, "r2.value", "100")
    type_into(w, "r2.unit", OHM)
    assert "did not settle" not in text(w.banner)
    assert text(w.components_tab.vclamp_typ) == f"{28.375 / 2.7:.3f}"


def test_solver_warning_visible(w, monkeypatch):
    """The warning is still shown when bracketing fails."""
    from src.models import circuit_model
    real = circuit_model.solve_node_voltage
    monkeypatch.setattr(circuit_model, "solve_node_voltage",
                        lambda *a, **k: circuit_model.SolveResult(real(*a, **k).v_node, False))
    load_reference(w)
    assert "did not settle" in text(w.banner)


# ── Follow-up: injection estimate, power typical / worst, R_s row, ZZK ────────

def test_injection_row_is_an_estimate_and_zero_for_reference(w):
    load_reference(w)
    labels = set(all_label_texts(w))
    assert "Injection Current (estimate)" in labels
    assert "Estimate (approx.)" in labels
    assert text(w.safety_tab.inj_row["value"]) == "0.00 mA"
    assert text(w.safety_tab.inj_row["status"]) == "✓ OK"


def test_power_typical_and_worst_shown(w):
    load_reference(w)
    r = w.app_state.result
    c = w.components_tab
    for row, name in ((c.r1_row, "r1"), (c.r2_row, "r2"), (c.z_row, "z")):
        assert text(row["power"]) == f"{getattr(r, f'p_{name}_mw'):.1f} mW"
        assert text(row["power_worst"]) == f"{getattr(r, f'p_{name}_worst_mw'):.1f} mW"
        assert text(row["margin_worst"]) != NEEDS_INPUT
    assert text(c.r1_row["power_worst"]) == "73.7 mW"
    for lbl in c.rs_row.values():
        assert text(lbl) == "no R_s"


def test_rs_row_needs_and_shows_values(w):
    load_reference(w)
    type_into(w, "rs.value", "100")
    rs = w.components_tab.rs_row
    assert text(rs["power_worst"]) == NEEDS_INPUT and text(rs["rating"]) == NEEDS_INPUT
    assert "R_s power rating" in text(w.banner) and "R_s tolerance" in text(w.banner)
    assert "Also blank" not in text(w.banner)
    type_into(w, "rs.rating", "250")
    type_into(w, "rs.tol", "1")
    assert text(rs["power_worst"]) == "0.0 mW"
    assert text(rs["rating"]) == "250 mW"
    assert text(rs["margin_worst"]) == "✓ 100%"
    assert text(w.banner) == "All inputs present."


def test_blank_rating_margin_shows_needs_input(w):
    load_reference(w)
    type_into(w, "r1.rating", "")
    assert text(w.components_tab.r1_row["margin"]) == NEEDS_INPUT
    assert text(w.components_tab.r1_row["margin_worst"]) == NEEDS_INPUT
    assert "≥" not in " ".join(all_label_texts(w.components_tab.r1_row["margin"].master))


def test_zzk_marked_reference_only(w):
    assert text(w.zener_panel.zzk_note) == "ZZK: reference only, not used in the calculation"
    assert "not used in the calculation" in w.zener_panel.zzk_tooltip.text


# ── Follow-up 2: worst-case labels and the power verdict ──────────────────────

def test_two_worst_case_voltages_labelled_apart(w):
    """Component tab: nominal R1/R2 with the Zener at VZ max (3.43348 V).
    MCU tab: V_mcuH, R1 min / R2 max / VZ max (3.43423 V)."""
    load_reference(w)
    labels = set(all_label_texts(w))
    assert "Worst Zener (nominal R)" in labels and "Worst Case" not in labels
    assert "Voltage at MCU Pin (nominal R1/R2)" in labels
    assert "V_mcuH" in labels
    r = w.app_state.result
    assert text(w.components_tab.vclamp_worst) == f"{r.v_mcu_worst_zener:.3f}" == "3.433"
    assert text(w.safety_tab.rec_row["value"]) == f"{r.v_mcu_worst:.3f} V" == "3.434 V"
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
    p_typ = w.app_state.result.p_r1_mw
    type_into(w, "r1.rating", f"{1.3 * p_typ:.1f}")
    assert text(w.components_tab.r1_row["margin"]) == "23%"
    assert text(w.components_tab.r1_row["margin_worst"]).startswith("✗")
    assert text(w.components_tab.power_verdict) == "✗ FAIL"
    type_into(w, "r1.rating", "")
    assert text(w.components_tab.power_verdict) == NEEDS_INPUT
