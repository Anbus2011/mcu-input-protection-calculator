"""
Unit tests for SchottkyClamp strategy.

Run with: python -m pytest tests/test_schottky_model.py -v
"""
import pytest

from src.models.clamps.schottky import SchottkyClamp
from src.models.clamps import CLAMP_REGISTRY
from src.core.constants import SCHOTTKY_PRESETS


BAT54CV_VF_TYP = 0.32   # V at 10 mA
BAT54CV_VF_MAX = 0.40   # V at 10 mA
BAT54CV_IF_TEST = 10.0  # mA
BAT54CV_RDYN = 4.0      # Ohm
VDD = 3.3               # V supply used throughout tests


class TestSchottkyClampVF:
    """Test VF(I) linear model."""

    def setup_method(self):
        self.clamp = SchottkyClamp(
            vf_typ=BAT54CV_VF_TYP,
            vf_max=BAT54CV_VF_MAX,
            if_test_ma=BAT54CV_IF_TEST,
            r_dynamic=BAT54CV_RDYN,
        )

    def test_vf_at_test_current_typ(self):
        """At IF_test, VF_typ == VF_base, so v_clamp = VDD + VF_typ."""
        v, r = self.clamp.voltage_at_current(BAT54CV_IF_TEST, use_worst_case=False, vdd=VDD)
        assert abs(v - (VDD + BAT54CV_VF_TYP)) < 1e-9
        assert r == BAT54CV_RDYN

    def test_vf_at_higher_current_typ(self):
        """Above IF_test, VF rises by R_dynamic slope."""
        i_ma = 20.0
        expected_vf = BAT54CV_VF_TYP + (i_ma - BAT54CV_IF_TEST) * BAT54CV_RDYN / 1000.0
        v, r = self.clamp.voltage_at_current(i_ma, use_worst_case=False, vdd=VDD)
        assert abs(v - (VDD + expected_vf)) < 1e-9
        assert r == BAT54CV_RDYN

    def test_vf_at_zero_current(self):
        """At zero current, diode is not conducting; v_clamp == VDD."""
        v, r = self.clamp.voltage_at_current(0.0, use_worst_case=False, vdd=VDD)
        assert abs(v - VDD) < 1e-9
        assert r == BAT54CV_RDYN

    def test_vf_negative_current(self):
        """Negative (reverse) current also yields v_clamp == VDD."""
        v, r = self.clamp.voltage_at_current(-5.0, use_worst_case=False, vdd=VDD)
        assert abs(v - VDD) < 1e-9

    def test_worst_case_vf(self):
        """use_worst_case=True switches to VF_max."""
        v, r = self.clamp.voltage_at_current(BAT54CV_IF_TEST, use_worst_case=True, vdd=VDD)
        assert abs(v - (VDD + BAT54CV_VF_MAX)) < 1e-9

    def test_vclamp_equals_vdd_plus_vf(self):
        """V_clamp = VDD + VF at arbitrary current; verify the arithmetic."""
        i_ma = 5.0
        vdd_test = 5.0
        expected_vf = BAT54CV_VF_TYP + (i_ma - BAT54CV_IF_TEST) * BAT54CV_RDYN / 1000.0
        # VF at 5 mA < IF_test, extrapolation can go slightly below typ (still >= 0)
        expected_vf = max(expected_vf, 0.0)
        v, r = self.clamp.voltage_at_current(i_ma, use_worst_case=False, vdd=vdd_test)
        assert abs(v - (vdd_test + expected_vf)) < 1e-9


class TestSchottkyClampErrors:
    """Test error handling."""

    def test_raises_when_vdd_is_none(self):
        """SchottkyClamp must raise ValueError if vdd is not provided."""
        clamp = SchottkyClamp()
        with pytest.raises(ValueError, match="SchottkyClamp requires vdd"):
            clamp.voltage_at_current(10.0, vdd=None)


class TestSchottkyClampFactory:
    """Test from_params factory."""

    def test_from_params_dict(self):
        """from_params() accepts a dict and round-trips all fields."""
        params = SCHOTTKY_PRESETS["BAT54CV"]
        clamp = SchottkyClamp.from_params(params)
        assert clamp.vf_typ == params["vf_typ"]
        assert clamp.vf_max == params["vf_max"]
        assert clamp.if_test_ma == params["if_test_ma"]
        assert clamp.r_dynamic == params["r_dynamic"]
        assert clamp.ir_ua == params["ir_ua"]
        assert clamp.channels == params["channels"]


class TestBAT54CVPreset:
    """Sanity-check BAT54CV preset values match the Nexperia datasheet."""

    def test_bat54cv_preset_exists(self):
        assert "BAT54CV" in SCHOTTKY_PRESETS

    def test_bat54cv_preset_values(self):
        p = SCHOTTKY_PRESETS["BAT54CV"]
        assert p["vf_typ"] == 0.32
        assert p["vf_max"] == 0.40
        assert p["if_test_ma"] == 10
        assert p["r_dynamic"] == 4.0
        assert p["ir_ua"] == 2.0
        assert p["vr_max"] == 30
        assert p["cd_pf"] == 10
        assert p["pd_mw"] == 200
        assert p["channels"] == 4

    def test_custom_preset_exists(self):
        assert "Custom" in SCHOTTKY_PRESETS

    def test_schottky_in_clamp_registry(self):
        """SchottkyClamp must be reachable via CLAMP_REGISTRY."""
        assert "schottky" in CLAMP_REGISTRY
        assert CLAMP_REGISTRY["schottky"] is SchottkyClamp
