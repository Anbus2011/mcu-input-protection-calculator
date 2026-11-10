"""
Test suite for file I/O and state serialisation.
Verifies .div format 2.0 round-trip and the handling of other files.
Run with: python -m pytest tests/ -v
"""
import copy
import json
import os
import tempfile

import pytest

from src.core.app_state import AppState, LoadError
from tests.designs import V1_FILE, blank_design, zener_reference

EXAMPLES = os.path.join(os.path.dirname(__file__), "..", "examples")


class TestFileRoundTrip:
    """Save state -> load it back -> verify values match."""

    def test_save_and_reload(self):
        s = AppState()
        s.set_fields({
            "r1.value": "4.7", "r1.unit": "kΩ", "r1.tol": "2.0", "r1.rating": "250",
            "r2.value": "20.0", "r2.unit": "kΩ", "r2.tol": "0.5", "r2.rating": "125",
            "rs.value": "100", "rs.unit": "Ω",
            "diode.part": "BZX84-C5V1", "diode.type": "zener",
            "diode.anode": "gnd", "diode.cathode": "node", "diode.ptot_mw": "250",
            "mcu.vdd": "5.0", "mcu.v_absolute_max": "6.0",
            "system.v_input_max": "24",
            "notes": "Test round-trip",
        })
        s.set_table("reverse", [dict(i_ma=1, v_min=4.6, v_typ=4.9, v_max=5.2),
                                dict(i_ma=5, v_min=4.8, v_typ=5.1, v_max=5.4)])

        with tempfile.NamedTemporaryFile(suffix=".div", delete=False, mode="w") as f:
            path = f.name

        try:
            assert s.save_to_file(path)

            s2 = AppState()
            s2.open_file(path)

            ohms = s2.circuit.v
            assert ohms["resistors.r1"] == 4700
            assert ohms["resistors.r2"] == 20000
            assert ohms["resistors.r_series"] == 100
            assert ohms["resistors.r1.tolerance_pct"] == 2.0
            assert ohms["resistors.r2.tolerance_pct"] == 0.5
            assert s2.fields["diode.part"] == "BZX84-C5V1"
            assert s2.design["clamp_diode"]["reverse"][1]["v_typ"] == 5.1
            assert s2.design["clamp_diode"]["reverse"][1]["v_max"] == 5.4
            assert s2.design["mcu"]["vdd"] == 5.0
            assert s2.design["system"]["v_input_max"] == 24
            assert s2.notes == "Test round-trip"
            assert s2.tables == s.tables
            assert s2.results == s.results
        finally:
            os.unlink(path)

    def test_json_format_version(self):
        """Saved file must contain version 2.0 and the format 2.0 sections."""
        s = AppState()
        s.set_fields({"r1.value": "10", "r2.value": "18"})

        with tempfile.NamedTemporaryFile(suffix=".div", delete=False, mode="w") as f:
            path = f.name

        try:
            s.save_to_file(path)
            with open(path) as f:
                data = json.load(f)
            assert data["version"] == "2.0"
            assert "resistors" in data
            assert "clamp_diode" in data and "zener" not in data
            assert "mcu" in data
            assert "system" in data
            assert "bandwidth" in data and "results" in data
        finally:
            os.unlink(path)


class TestOtherFiles:
    """Files the app did not just save: an example file, a file with blank
    values, and a format 1.0 file (refused: there is no reader for it)."""

    def test_load_example_file(self):
        """Load a shipped example and verify key values."""
        path = os.path.join(EXAMPLES, "zener_gnd_bzb984_c3v3.div")
        s = AppState()
        assert s.open_file(path) == []

        assert s.circuit.v["resistors.r1"] == 10000
        assert s.circuit.v["resistors.r2"] == 18000
        assert s.fields["diode.part"] == "BZB984-C3V3"
        assert len(s.tables["reverse"]) == 13 and s.tables["forward"] == []
        assert s.design["mcu"]["vdd"] == 3.3
        assert s.design["system"]["v_input_max"] == 30
        assert not s.is_dirty

    def test_format_1_file_is_refused_with_a_clear_message(self, tmp_path):
        path = tmp_path / "old.div"
        path.write_text(json.dumps(copy.deepcopy(V1_FILE)), encoding="utf-8")
        s = AppState()
        with pytest.raises(LoadError) as exc:
            s.open_file(str(path))
        message = str(exc.value)
        assert message.startswith("version: this is a format 1.0 file")
        assert "reads .div format 2.0 only" in message and "no converter" in message
        assert s.current_file is None and s.fields["r1.value"] == ""

    def test_blank_values_load_blank_with_one_warning(self):
        """A file whose values are null loads without errors. Nothing is
        filled in: blank stays blank, and one warning lists what the results
        need. (A file with keys left out is refused: see test_app_state.)"""
        data = blank_design()
        data["resistors"]["r1"].update(value=10, unit="kΩ")
        data["resistors"]["r2"].update(value=18, unit="kΩ")
        with tempfile.NamedTemporaryFile(suffix=".div", delete=False, mode="w") as f:
            json.dump(data, f)
            path = f.name

        try:
            s = AppState()
            warnings = s.open_file(path)
            assert s.circuit.v["resistors.r1"] == 10000
            assert s.circuit.v["resistors.r2"] == 18000
            assert s.design["mcu"]["vdd"] is None
            assert s.fields["mcu.vdd"] == "" and s.fields["diode.ptot_mw"] == ""
            assert s.fields["bw.c_stray_pf"] == ""       # not even a starting value
            assert len(warnings) == 1
            assert "VDD/VDDA" in warnings[0] and "Anode connection" in warnings[0]
        finally:
            os.unlink(path)


class TestDirtyTracking:
    def test_starts_clean(self):
        s = AppState()
        assert not s.is_dirty

    def test_mark_dirty(self):
        s = AppState()
        s.mark_dirty()
        assert s.is_dirty

    def test_save_clears_dirty(self):
        s = AppState()
        s.set_fields({"r1.value": "10", "r2.value": "18"})
        s.mark_dirty()

        with tempfile.NamedTemporaryFile(suffix=".div", delete=False, mode="w") as f:
            path = f.name

        try:
            s.save_to_file(path)
            assert not s.is_dirty
        finally:
            os.unlink(path)

    def test_ignore_changes_suppresses_dirty(self):
        s = AppState()
        s.ignore_changes = True
        s.mark_dirty()
        assert not s.is_dirty
