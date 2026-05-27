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
from src.models.clamps.schottky import SchottkyClamp
from src.models.clamps.tvs import TVSClamp
from src.core.constants import SCHOTTKY_PRESETS, TVS_PRESETS


class TestFileRoundTrip:
    """Save state -> load it back -> verify values match."""

    def test_save_and_reload(self):
        s = AppState()
        s.resistors.r1_ohms = 4700
        s.resistors.r2_ohms = 20000
        s.resistors.rs_ohms = 100
        s.resistors.r1_tol_pct = 2.0
        s.resistors.r2_tol_pct = 0.5
        s.resistors.r1_rating_mw = 250
        s.resistors.r2_rating_mw = 125
        s.r1_display_value = 4.7
        s.r1_display_unit = "k\u03a9"
        s.r2_display_value = 20.0
        s.r2_display_unit = "k\u03a9"
        s.rs_display_value = 100
        s.rs_display_unit = "\u03a9"
        s.zener.vz_nom = 5.1
        s.zener.vz_min = 4.8
        s.zener.vz_max = 5.4
        s.mcu.vdd = 5.0
        s.mcu.v_absolute_max = 6.0
        s.system.v_input_max = 24
        s.notes = "Test round-trip"

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
        """Saved file must contain version 2.0 and a clamp block."""
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
            assert data["version"] == "2.0"
            assert "resistors" in data
            assert "clamp" in data          # v2.0 uses clamp block
            assert "mcu" in data
            assert "system" in data
            # Verify clamp block structure
            assert data["clamp"]["type"] == "zener"
            assert "params" in data["clamp"]
        finally:
            os.unlink(path)


class TestBackwardsCompatibility:
    """Verify loading old-format .div files still works."""

    def test_load_results_div(self):
        """Load the shipped results.div (v1.0) and verify key values."""
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
            s.open_file(path)
            assert s.resistors.r1_ohms == 10000
            assert s.resistors.r2_ohms == 18000
            # Defaults should fill in
            assert s.zener.vz_nom == 3.3
            assert s.mcu.vdd == 3.3
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


class TestV2FormatAndV1Migration:
    """Tests for v2.0 file format and v1.0 migration."""

    def test_zener_roundtrip_v2(self):
        """Save Zener config, reload, verify clamp.type=="zener" and results match."""
        from src.models.circuit_model import calculate_all
        s = AppState()
        # Default Zener BZB984-C3V3 with R1=10k, R2=18k, Vin=30V
        s.resistors.r1_ohms = 10000
        s.resistors.r2_ohms = 18000
        s.r1_display_value = 10
        s.r1_display_unit = "k\u03a9"
        s.r2_display_value = 18
        s.r2_display_unit = "k\u03a9"
        s.system.v_input_max = 30
        s.clamp_preset_name = "BZB984-C3V3"

        with tempfile.NamedTemporaryFile(suffix=".div", delete=False, mode="w") as f:
            path = f.name

        try:
            assert s.save_to_file(path)

            s2 = AppState()
            s2.open_file(path)

            assert s2.clamp_type == "zener"
            assert s2.clamp_preset_name == "BZB984-C3V3"

            # Verify computed results match
            r1 = calculate_all(s2.resistors, s2.zener, s2.mcu, s2.system)
            r2 = calculate_all(s.resistors, s.zener, s.mcu, s.system)
            assert abs(r1.v_mcu_typ - r2.v_mcu_typ) < 0.01
            assert abs(r1.v_mcu_worst - r2.v_mcu_worst) < 0.01
        finally:
            os.unlink(path)

    def test_schottky_roundtrip(self):
        """Save Schottky config, reload, verify clamp.type=="schottky" and preset."""
        preset = SCHOTTKY_PRESETS["BAT54CV"]
        s = AppState()
        s.clamp_type = "schottky"
        s.clamp_preset_name = "BAT54CV"
        s.clamp = SchottkyClamp.from_params(preset)
        s.clamp_params = dict(preset)
        s.r1_display_value = 10
        s.r1_display_unit = "k\u03a9"
        s.r2_display_value = 18
        s.r2_display_unit = "k\u03a9"

        with tempfile.NamedTemporaryFile(suffix=".div", delete=False, mode="w") as f:
            path = f.name

        try:
            assert s.save_to_file(path)

            s2 = AppState()
            s2.open_file(path)

            assert s2.clamp_type == "schottky"
            assert s2.clamp_preset_name == "BAT54CV"
            assert isinstance(s2.clamp, SchottkyClamp)
            assert s2.clamp.vf_typ == preset["vf_typ"]
        finally:
            os.unlink(path)

    def test_tvs_roundtrip_polarity_preserved(self):
        """Save TVS config, reload, verify clamp.type=="tvs" and polarity."""
        preset = dict(TVS_PRESETS["SMAJ5.0CA"])
        preset.setdefault("polarity", "bidirectional")
        s = AppState()
        s.clamp_type = "tvs"
        s.clamp_preset_name = "SMAJ5.0CA"
        s.clamp = TVSClamp.from_params(preset)
        s.clamp_params = dict(preset)
        s.r1_display_value = 10
        s.r1_display_unit = "k\u03a9"
        s.r2_display_value = 18
        s.r2_display_unit = "k\u03a9"

        with tempfile.NamedTemporaryFile(suffix=".div", delete=False, mode="w") as f:
            path = f.name

        try:
            assert s.save_to_file(path)

            with open(path) as f:
                raw = json.load(f)
            assert raw["clamp"]["type"] == "tvs"
            assert raw["clamp"]["polarity"] == "bidirectional"

            s2 = AppState()
            s2.open_file(path)

            assert s2.clamp_type == "tvs"
            assert isinstance(s2.clamp, TVSClamp)
            assert s2.clamp.polarity == "bidirectional"
        finally:
            os.unlink(path)

    def test_v1_programmatic_migration(self):
        """Load a programmatically-created v1.0 dict, verify auto-migration."""
        from src.models.circuit_model import calculate_all
        v1_data = {
            "version": "1.0",
            "created": "2026-01-01T00:00:00",
            "notes": "",
            "resistors": {
                "r1": {"value": 10, "unit": "k\u03a9", "rating_mw": 200.0, "tolerance_pct": 1.0},
                "r2": {"value": 18, "unit": "k\u03a9", "rating_mw": 100.0, "tolerance_pct": 1.0},
                "r_series": {"value": 0, "unit": "\u03a9", "rating_mw": None, "tolerance_pct": None},
            },
            "zener": {
                "preset": "BZB984-C3V3",
                "vz_nom": 3.3, "vz_min": 3.1, "vz_max": 3.5, "tolerance_pct": 5,
                "izt_ma": 5.0, "zzt_typ": 85.0, "zzt_max": 95.0,
                "zzk_typ": 350.0, "zzk_max": 600.0, "izk_ma": 1.0, "ptot_mw": 265.0,
            },
            "mcu": {"vdd": 3.3, "vdda": 3.3, "vref": 3.3,
                    "v_recommended_max": 3.6, "v_absolute_max": 4.0, "safe_injection_ma": 1.0},
            "system": {"v_input_max": 30.0, "v_analog_fullscale": 5.1,
                       "v_logic_high_min": 3.8, "v_logic_low_max": 1.0},
        }

        with tempfile.NamedTemporaryFile(suffix=".div", delete=False, mode="w") as f:
            json.dump(v1_data, f)
            path = f.name

        try:
            s = AppState()
            s.open_file(path)

            # Should auto-migrate to v2.0 state
            assert s.clamp_type == "zener"
            assert s.clamp_preset_name == "BZB984-C3V3"
            assert s.zener.vz_nom == 3.3
            assert s.resistors.r1_ohms == 10000
            assert s.resistors.r2_ohms == 18000

            # Computed results should be identical to direct v1 calculation
            from src.models.circuit_model import ResistorParams, ZenerParams, McuParams, SystemParams
            r_direct = calculate_all(s.resistors, s.zener, s.mcu, s.system)
            assert abs(r_direct.v_mcu_typ - 3.177) < 0.05
            assert abs(r_direct.v_mcu_worst - 3.434) < 0.05
        finally:
            os.unlink(path)

    def test_results_div_v1_migration_baseline(self):
        """Load shipped results.div (v1.0), verify migration produces correct results.

        results.div uses R1=8.2k, R2=29k, Vin=30V, BZB984-C3V3.
        This test verifies the v1->v2 migration path preserves computed correctness.
        """
        from src.models.circuit_model import calculate_all
        path = os.path.join(os.path.dirname(__file__), "..", "results.div")
        if not os.path.exists(path):
            pytest.skip("results.div not found")

        s = AppState()
        s.open_file(path)

        # Verify migration
        assert s.clamp_type == "zener"
        assert s.zener.vz_nom == 3.3
        assert s.resistors.r1_ohms == pytest.approx(8200.0)
        assert s.resistors.r2_ohms == pytest.approx(29000.0)
        assert s.system.v_input_max == 30.0

        # Compute results
        result = calculate_all(s.resistors, s.zener, s.mcu, s.system)
        # R1=8.2k, R2=29k -> k = 29/37.2 = 0.7796
        # With BZB984-C3V3 clamp, v_mcu_typ and v_mcu_worst should be near 3.3V
        assert result.v_mcu_typ > 3.0, f"v_mcu_typ={result.v_mcu_typ}"
        assert result.v_mcu_typ < 3.6, f"v_mcu_typ={result.v_mcu_typ}"
        assert result.v_mcu_worst > 3.0, f"v_mcu_worst={result.v_mcu_worst}"
        assert result.v_mcu_worst < 3.7, f"v_mcu_worst={result.v_mcu_worst}"

    def test_v2_roundtrip_clamp_fields_preserved(self):
        """Round-trip v2.0 -> save -> reload -> verify all clamp-block fields preserved."""
        s = AppState()
        # Set up a specific Zener config
        s.zener.vz_nom = 4.7
        s.zener.vz_min = 4.4
        s.zener.vz_max = 5.0
        s.zener.izt_ma = 5.0
        s.zener.ptot_mw = 265.0
        s.clamp_preset_name = "BZB984-C4V7"
        s.clamp_type = "zener"
        s.r1_display_value = 10
        s.r1_display_unit = "k\u03a9"
        s.r2_display_value = 18
        s.r2_display_unit = "k\u03a9"

        with tempfile.NamedTemporaryFile(suffix=".div", delete=False, mode="w") as f:
            path = f.name

        try:
            assert s.save_to_file(path)

            with open(path) as f:
                data = json.load(f)

            # v2.0 structure
            assert data["version"] == "2.0"
            assert data["clamp"]["type"] == "zener"
            assert data["clamp"]["preset"] == "BZB984-C4V7"
            assert data["clamp"]["params"]["vz_nom"] == pytest.approx(4.7)
            assert data["clamp"]["params"]["vz_max"] == pytest.approx(5.0)

            # Reload and verify
            s2 = AppState()
            s2.open_file(path)
            assert s2.clamp_type == "zener"
            assert s2.clamp_preset_name == "BZB984-C4V7"
            assert s2.zener.vz_nom == pytest.approx(4.7)
            assert s2.zener.vz_max == pytest.approx(5.0)
        finally:
            os.unlink(path)

    def test_unknown_version_raises(self):
        """Loading an unknown version should raise ValueError."""
        bad_data = {
            "version": "99.0",
            "resistors": {},
            "clamp": {"type": "zener", "preset": "Custom", "params": {}},
        }
        with tempfile.NamedTemporaryFile(suffix=".div", delete=False, mode="w") as f:
            json.dump(bad_data, f)
            path = f.name

        try:
            s = AppState()
            with pytest.raises(ValueError, match="99.0"):
                s.open_file(path)
        finally:
            os.unlink(path)
