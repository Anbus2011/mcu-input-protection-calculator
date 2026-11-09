"""
Test suite for file I/O and state serialisation.
Verifies .div file round-trip and backwards compatibility.
Run with: python -m pytest tests/ -v
"""
import json
import os
import tempfile
import pytest

from src.core.app_state import AppState


class TestFileRoundTrip:
    """Save state -> load it back -> verify values match."""

    def test_save_and_reload(self):
        # Rewritten: the old version set model parameters and "display"
        # values separately, which let them disagree (bug 5). Inputs now go
        # through set_field, the same path the UI uses.
        s = AppState()
        s.set_fields({
            "r1.value": "4.7", "r1.unit": "k\u03a9", "r1.tol": "2.0", "r1.rating": "250",
            "r2.value": "20.0", "r2.unit": "k\u03a9", "r2.tol": "0.5", "r2.rating": "125",
            "rs.value": "100", "rs.unit": "\u03a9",
            "zener.vz_nom": "5.1", "zener.vz_min": "4.8", "zener.vz_max": "5.4",
            "mcu.vdd": "5.0", "mcu.v_absolute_max": "6.0",
            "system.v_input_max": "24",
            "notes": "Test round-trip",
        })

        with tempfile.NamedTemporaryFile(suffix=".div", delete=False, mode="w") as f:
            path = f.name

        try:
            assert s.save_to_file(path)

            s2 = AppState()
            s2.open_file(path)

            assert s2.resistors.r1_ohms == 4700
            assert s2.resistors.r2_ohms == 20000
            assert s2.resistors.rs_ohms == 100
            assert s2.resistors.r1_tol_pct == 2.0
            assert s2.resistors.r2_tol_pct == 0.5
            assert s2.zener.vz_nom == 5.1
            assert s2.zener.vz_max == 5.4
            assert s2.mcu.vdd == 5.0
            assert s2.system.v_input_max == 24
            assert s2.notes == "Test round-trip"
        finally:
            os.unlink(path)

    def test_json_format_version(self):
        """Saved file must contain version 1.0 for backwards compat."""
        s = AppState()
        s.r1_display_value = 10
        s.r1_display_unit = "k\u03a9"
        s.r2_display_value = 18
        s.r2_display_unit = "k\u03a9"

        with tempfile.NamedTemporaryFile(suffix=".div", delete=False, mode="w") as f:
            path = f.name

        try:
            s.save_to_file(path)
            with open(path) as f:
                data = json.load(f)
            assert data["version"] == "1.0"
            assert "resistors" in data
            assert "zener" in data
            assert "mcu" in data
            assert "system" in data
        finally:
            os.unlink(path)


class TestBackwardsCompatibility:
    """Verify loading old-format .div files still works."""

    def test_load_results_div(self):
        """Load the shipped results.div and verify key values."""
        path = os.path.join(os.path.dirname(__file__), "..", "results.div")
        if not os.path.exists(path):
            pytest.skip("results.div not found")

        s = AppState()
        s.open_file(path)

        assert s.resistors.r1_ohms == 8200
        assert s.resistors.r2_ohms == 29000
        assert s.zener.vz_nom == 3.3
        assert s.mcu.vdd == 3.3
        assert s.system.v_input_max == 30

    def test_missing_fields_use_defaults(self):
        """A minimal .div file should load without errors."""
        minimal = {
            "version": "1.0",
            "resistors": {
                "r1": {"value": 10, "unit": "k\u03a9"},
                "r2": {"value": 18, "unit": "k\u03a9"},
            },
        }
        with tempfile.NamedTemporaryFile(suffix=".div", delete=False, mode="w") as f:
            json.dump(minimal, f)
            path = f.name

        try:
            s = AppState()
            warnings = s.open_file(path)
            assert s.resistors.r1_ohms == 10000
            assert s.resistors.r2_ohms == 18000
            # Rewritten for bug 5: this used to assert that hidden defaults
            # (VZ 3.3 V, VDD 3.3 V) filled in. Missing fields now load blank
            # and one warning lists them.
            assert s.zener.vz_nom is None
            assert s.mcu.vdd is None
            assert s.fields["zener.vz_nom"] == ""
            assert len(warnings) == 1
            assert "VZ nom" in warnings[0] and "VDD/VDDA" in warnings[0]
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
        s.r1_display_value = 10
        s.r1_display_unit = "k\u03a9"
        s.r2_display_value = 18
        s.r2_display_unit = "k\u03a9"
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
