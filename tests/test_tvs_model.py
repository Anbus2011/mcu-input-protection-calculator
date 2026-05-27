"""
Unit tests for TVSClamp strategy (unidirectional, T4).

Run with: python -m pytest tests/test_tvs_model.py -v
"""
import pytest

from src.models.clamps.tvs import TVSClamp
from src.models.clamps import CLAMP_REGISTRY
from src.core.constants import TVS_PRESETS


# ---------------------------------------------------------------------------
# SMBJ60 datasheet values (Littelfuse, unidirectional 60V standoff)
# ---------------------------------------------------------------------------
SMBJ60 = TVS_PRESETS["SMBJ60"]
SMBJ60_V_RWM   = 60.0
SMBJ60_V_BR_MIN = 66.7
SMBJ60_V_BR_MAX = 73.7
SMBJ60_V_C     = 96.8
SMBJ60_I_PP    = 6.2    # A
SMBJ60_I_T     = 1.0    # mA


class TestTVSOffRegion:
    """Off region: i_ma <= 0 returns (v_rwm, 1e9)."""

    def setup_method(self):
        self.clamp = TVSClamp.from_params(SMBJ60)

    def test_off_region_zero_current(self):
        """At i_ma=0, TVS is off; returns (v_rwm, 1e9)."""
        v, r = self.clamp.voltage_at_current(0.0)
        assert v == SMBJ60_V_RWM
        assert r == 1e9

    def test_off_region_negative_current(self):
        """Negative current also returns off-region result."""
        v, r = self.clamp.voltage_at_current(-10.0)
        assert v == SMBJ60_V_RWM
        assert r == 1e9

    def test_off_region_high_resistance(self):
        """Off-region resistance is >= 1e9 Ohm (solver open-circuit sentinel)."""
        _, r = self.clamp.voltage_at_current(0.0)
        assert r >= 1e9


class TestTVSSoftBreakdown:
    """Soft-breakdown region: 0 < i_ma < i_t."""

    def setup_method(self):
        self.clamp = TVSClamp.from_params(SMBJ60)

    def test_soft_breakdown_linearity(self):
        """At i_ma = i_t/2, V should be midpoint between v_rwm and v_br_min."""
        i_half = SMBJ60_I_T / 2.0
        v, _ = self.clamp.voltage_at_current(i_half, use_worst_case=False)
        expected = SMBJ60_V_RWM + (SMBJ60_V_BR_MIN - SMBJ60_V_RWM) * 0.5
        assert abs(v - expected) < 1e-9

    def test_soft_breakdown_uses_vbr_min_typical(self):
        """Typical case uses v_br_min."""
        i_ma = SMBJ60_I_T * 0.9
        v_typ, _ = self.clamp.voltage_at_current(i_ma, use_worst_case=False)
        expected = SMBJ60_V_RWM + (SMBJ60_V_BR_MIN - SMBJ60_V_RWM) * (i_ma / SMBJ60_I_T)
        assert abs(v_typ - expected) < 1e-9

    def test_soft_breakdown_uses_vbr_max_worst_case(self):
        """Worst case uses v_br_max, giving higher voltage."""
        i_ma = SMBJ60_I_T * 0.5
        v_typ, _ = self.clamp.voltage_at_current(i_ma, use_worst_case=False)
        v_wc, _  = self.clamp.voltage_at_current(i_ma, use_worst_case=True)
        assert v_wc > v_typ


class TestTVSHardClamp:
    """Hard-clamp region: i_ma >= i_t."""

    def setup_method(self):
        self.clamp = TVSClamp.from_params(SMBJ60)

    def test_hard_clamp_at_i_t(self):
        """At exactly i_t, hard-clamp voltage equals v_br_min (typical)."""
        v, _ = self.clamp.voltage_at_current(SMBJ60_I_T, use_worst_case=False)
        assert abs(v - SMBJ60_V_BR_MIN) < 1e-9

    def test_hard_clamp_at_i_pp_matches_datasheet(self):
        """At I_PP (in mA), v_clamp should equal v_c from datasheet (typical)."""
        i_pp_ma = SMBJ60_I_PP * 1000.0  # A -> mA
        v, _ = self.clamp.voltage_at_current(i_pp_ma, use_worst_case=False)
        assert abs(v - SMBJ60_V_C) < 1e-6

    def test_hard_clamp_slope(self):
        """Slope between i_t and I_PP equals R_dynamic."""
        i_pp_ma = SMBJ60_I_PP * 1000.0
        r_dyn_expected = (SMBJ60_V_C - SMBJ60_V_BR_MIN) / (i_pp_ma - SMBJ60_I_T)  # V/mA
        # At i_t + delta, v = v_br_min + delta * r_dyn
        delta = 100.0  # mA
        v1, _ = self.clamp.voltage_at_current(SMBJ60_I_T + delta, use_worst_case=False)
        v0, _ = self.clamp.voltage_at_current(SMBJ60_I_T, use_worst_case=False)
        slope = (v1 - v0) / delta
        assert abs(slope - r_dyn_expected) < 1e-9

    def test_r_dynamic_derivation(self):
        """R_dynamic returned by voltage_at_current equals (V_C-V_BR)/(I_PP-I_T)."""
        i_pp_ma = SMBJ60_I_PP * 1000.0
        r_expected_v_per_ma = (SMBJ60_V_C - SMBJ60_V_BR_MIN) / (i_pp_ma - SMBJ60_I_T)
        r_expected_ohm = r_expected_v_per_ma * 1000.0
        _, r = self.clamp.voltage_at_current(SMBJ60_I_T + 1.0, use_worst_case=False)
        assert abs(r - r_expected_ohm) < 1e-6

    def test_worst_case_higher_voltage(self):
        """Worst-case (v_br_max) gives higher clamp voltage than typical."""
        i_ma = 500.0
        v_typ, _ = self.clamp.voltage_at_current(i_ma, use_worst_case=False)
        v_wc,  _ = self.clamp.voltage_at_current(i_ma, use_worst_case=True)
        assert v_wc > v_typ


class TestTVSFactory:
    """Test from_params factory."""

    def test_from_params_dict_roundtrip(self):
        """from_params(dict) round-trips all mandatory fields."""
        p = TVS_PRESETS["SMBJ60"]
        clamp = TVSClamp.from_params(p)
        assert clamp.v_rwm == p["v_rwm"]
        assert clamp.v_br_min == p["v_br_min"]
        assert clamp.v_br_max == p["v_br_max"]
        assert clamp.v_c == p["v_c"]
        assert clamp.i_pp == p["i_pp"]
        assert clamp.i_t == p["i_t"]

    def test_vdd_ignored(self):
        """vdd kwarg is accepted but does not affect result."""
        clamp = TVSClamp.from_params(TVS_PRESETS["SMBJ60"])
        i_ma = 500.0
        v1, r1 = clamp.voltage_at_current(i_ma, vdd=None)
        v2, r2 = clamp.voltage_at_current(i_ma, vdd=3.3)
        assert v1 == v2
        assert r1 == r2


class TestTVSPresetssSanity:
    """Sanity-check all three manufacturer presets."""

    def test_smbj60_preset_exists_and_values(self):
        p = TVS_PRESETS["SMBJ60"]
        assert p["v_rwm"] == 60.0
        assert p["v_br_min"] == 66.7
        assert p["v_br_max"] == 73.7
        assert p["v_c"] == 96.8
        assert p["i_pp"] == 6.2
        assert p["i_t"] == 1.0
        assert p["c_pf"] == 380
        assert p["p_ppm_w"] == 600

    def test_smaj5a_preset_exists_and_values(self):
        p = TVS_PRESETS["SMAJ5.0A"]
        assert p["v_rwm"] == 5.0
        assert p["v_br_min"] == 6.4
        assert p["v_br_max"] == 7.0
        assert p["v_c"] == 9.2
        assert p["i_pp"] == 43.5
        assert p["i_t"] == 10.0

    def test_pesd3v3l_preset_exists_and_values(self):
        p = TVS_PRESETS["PESD3V3L"]
        assert p["v_rwm"] == 3.3
        assert p["v_br_min"] == 4.2
        assert p["v_br_max"] == 6.0
        assert p["v_c"] == 9.0
        assert p["i_pp"] == 1.0
        assert p["c_pf"] == 0.6

    def test_custom_preset_exists(self):
        assert "Custom" in TVS_PRESETS
        # Custom is a copy of SMBJ60
        assert TVS_PRESETS["Custom"]["v_rwm"] == TVS_PRESETS["SMBJ60"]["v_rwm"]

    def test_all_presets_instantiate(self):
        """All presets can be used to construct a TVSClamp without error."""
        for name, params in TVS_PRESETS.items():
            clamp = TVSClamp.from_params(params)
            assert clamp.v_rwm == params["v_rwm"], f"{name}: v_rwm mismatch"


class TestTVSBidirectionalGuard:
    """Polarity validation (T5: bidirectional is now supported)."""

    def test_bidirectional_instantiates(self):
        """Bidirectional polarity no longer raises -- T5 implements it."""
        clamp = TVSClamp(polarity="bidirectional")
        assert clamp.polarity == "bidirectional"

    def test_unknown_polarity_raises_value_error(self):
        with pytest.raises(ValueError):
            TVSClamp(polarity="unknown")


class TestTVSRegistry:
    """TVSClamp must be reachable via CLAMP_REGISTRY."""

    def test_tvs_in_registry(self):
        assert "tvs" in CLAMP_REGISTRY
        assert CLAMP_REGISTRY["tvs"] is TVSClamp


# ---------------------------------------------------------------------------
# T5 Bidirectional tests
# ---------------------------------------------------------------------------

# Use SMAJ5.0A params (same electrical values as SMAJ5.0CA, unidirectional)
SMAJ5A = {
    "v_rwm": 5.0, "v_br_min": 6.4, "v_br_max": 7.0,
    "v_c": 9.2, "i_pp": 43.5, "i_t": 10.0,
    "c_pf": 850, "p_ppm_w": 400,
}


class TestTVSBidirectional:
    """Bidirectional TVS: mirrors unidirectional model for negative current."""

    def setup_method(self):
        self.uni = TVSClamp.from_params({**SMAJ5A, "polarity": "unidirectional"})
        self.bi  = TVSClamp.from_params({**SMAJ5A, "polarity": "bidirectional"})

    def test_bidir_positive_matches_unidirectional(self):
        """Bidirectional positive direction gives same result as unidirectional."""
        for i_ma in [0.5, 10.0, 100.0, 5000.0]:
            v_uni, r_uni = self.uni.voltage_at_current(i_ma)
            v_bi,  r_bi  = self.bi.voltage_at_current(i_ma)
            assert abs(v_bi - v_uni) < 1e-12, f"i_ma={i_ma}: v mismatch"
            assert abs(r_bi - r_uni) < 1e-9,  f"i_ma={i_ma}: r mismatch"

    def test_bidir_negative_is_sign_mirrored(self):
        """Bidirectional negative current returns negative V_clamp, same |V| as positive."""
        for i_ma in [10.0, 100.0, 5000.0]:
            v_pos, r_pos = self.bi.voltage_at_current( i_ma)
            v_neg, r_neg = self.bi.voltage_at_current(-i_ma)
            assert abs(v_neg + v_pos) < 1e-12, f"i_ma={i_ma}: not sign-mirrored"
            assert abs(r_neg - r_pos) < 1e-9,  f"i_ma={i_ma}: r differs"
            assert v_neg < 0

    def test_bidir_zero_current_returns_zero_voltage(self):
        """Bidirectional at I=0 returns (0, 1e9) -- symmetric off-state."""
        v, r = self.bi.voltage_at_current(0.0)
        assert v == 0.0
        assert r >= 1e9

    def test_smaj5ca_preset_polarity_default(self):
        """SMAJ5.0CA preset has polarity_default='bidirectional'."""
        p = TVS_PRESETS["SMAJ5.0CA"]
        assert p["polarity_default"] == "bidirectional"
        # All other named presets (excluding Custom) have no polarity_default or unidirectional
        for name in ("SMBJ60", "SMAJ5.0A", "PESD3V3L"):
            assert TVS_PRESETS[name].get("polarity_default", "unidirectional") == "unidirectional"

    def test_switching_polarity_changes_behavior(self):
        """Changing polarity on an instance changes voltage_at_current behavior."""
        clamp = TVSClamp.from_params({**SMAJ5A, "polarity": "unidirectional"})
        # Unidirectional: negative current -> off state (positive v_rwm)
        v_uni, r_uni = clamp.voltage_at_current(-100.0)
        assert v_uni == clamp.v_rwm
        assert r_uni >= 1e9
        # Switch to bidirectional
        clamp.polarity = "bidirectional"
        v_bi, r_bi = clamp.voltage_at_current(-100.0)
        assert v_bi < 0, "bidirectional negative current should return negative voltage"
        assert r_bi < 1e9, "bidirectional should be conducting (not open)"
