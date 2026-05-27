"""
T6: Infrastructure tests for the clamp-strategy module.

Covers:
  1. Registry resolution (CLAMP_REGISTRY keys map to correct classes)
  2. ABC enforcement (ClampModel cannot be instantiated; all concrete classes
     implement voltage_at_current)
  3. ZenerClamp golden values (regression net for BZB984-C3V3 math)
  4. Round-trip via registry (build instance from preset, check isinstance)
  5. Custom preset presence (all three dicts have "Custom" as last key)
  6. VDD requirement (Zener/TVS ignore vdd; Schottky raises ValueError)
"""
from __future__ import annotations

import pytest

from src.core.constants import ZENER_PRESETS, SCHOTTKY_PRESETS, TVS_PRESETS
from src.models.clamps import (
    ClampModel,
    ZenerClamp,
    SchottkyClamp,
    TVSClamp,
    CLAMP_REGISTRY,
)


# ---------------------------------------------------------------------------
# 1. Registry resolution
# ---------------------------------------------------------------------------
class TestRegistryResolution:
    def test_zener_resolves(self):
        assert CLAMP_REGISTRY["zener"] is ZenerClamp

    def test_schottky_resolves(self):
        assert CLAMP_REGISTRY["schottky"] is SchottkyClamp

    def test_tvs_resolves(self):
        assert CLAMP_REGISTRY["tvs"] is TVSClamp

    def test_unknown_key_raises(self):
        with pytest.raises(KeyError):
            _ = CLAMP_REGISTRY["unknown_clamp_type"]


# ---------------------------------------------------------------------------
# 2. ABC enforcement
# ---------------------------------------------------------------------------
class TestABCEnforcement:
    def test_clampmodel_cannot_be_instantiated(self):
        with pytest.raises(TypeError):
            ClampModel()  # type: ignore[abstract]

    def test_zener_has_voltage_at_current(self):
        assert hasattr(ZenerClamp, "voltage_at_current")
        assert callable(ZenerClamp.voltage_at_current)

    def test_schottky_has_voltage_at_current(self):
        assert hasattr(SchottkyClamp, "voltage_at_current")
        assert callable(SchottkyClamp.voltage_at_current)

    def test_tvs_has_voltage_at_current(self):
        assert hasattr(TVSClamp, "voltage_at_current")
        assert callable(TVSClamp.voltage_at_current)


# ---------------------------------------------------------------------------
# 3. ZenerClamp golden values (BZB984-C3V3, typical case)
# ---------------------------------------------------------------------------
class TestZenerGoldenValues:
    """Lock current ZenerClamp math; computed via bash_research on 2026-05-26."""

    @pytest.fixture()
    def bzb984_c3v3(self):
        p = ZENER_PRESETS["BZB984-C3V3"]
        return ZenerClamp(
            vz_nom=p["vz_nom"],
            vz_min=p["vz_min"],
            vz_max=p["vz_max"],
            izt_ma=p["izt_ma"],
            izk_ma=p["izk_ma"],
            zzt_typ=p["zzt_typ"],
            zzt_max=p["zzt_max"],
            zzk_typ=p["zzk_typ"],
            zzk_max=p["zzk_max"],
            ptot_mw=p["ptot_mw"],
        )

    _GOLDEN = [
        # (i_ma, expected_v_clamp, expected_r_diff)
        (0.5,  3.0554699999999997, 350),
        (1.0,  3.102,              350),
        (2.5,  3.17625,            250.625),
        (5.0,  3.3,                85.0),
        (10.0, 3.7249999999999996, 85),
    ]

    @pytest.mark.parametrize("i_ma,exp_v,exp_r", _GOLDEN)
    def test_golden(self, bzb984_c3v3, i_ma, exp_v, exp_r):
        v_clamp, r_diff = bzb984_c3v3.voltage_at_current(i_ma)
        assert v_clamp == pytest.approx(exp_v, rel=1e-6)
        assert r_diff == pytest.approx(exp_r, rel=1e-6)


# ---------------------------------------------------------------------------
# 4. Round-trip via registry
# ---------------------------------------------------------------------------
class TestRoundTripViaRegistry:
    def test_zener_roundtrip(self):
        p = ZENER_PRESETS["BZB984-C3V3"]
        inst = ZenerClamp(
            vz_nom=p["vz_nom"], vz_min=p["vz_min"], vz_max=p["vz_max"],
            izt_ma=p["izt_ma"], izk_ma=p["izk_ma"],
            zzt_typ=p["zzt_typ"], zzt_max=p["zzt_max"],
            zzk_typ=p["zzk_typ"], zzk_max=p["zzk_max"],
            ptot_mw=p["ptot_mw"],
        )
        assert isinstance(inst, ClampModel)
        assert isinstance(inst, ZenerClamp)

    def test_schottky_roundtrip(self):
        p = SCHOTTKY_PRESETS["BAT54CV"]
        inst = SchottkyClamp.from_params(p)
        assert isinstance(inst, ClampModel)
        assert isinstance(inst, SchottkyClamp)

    def test_tvs_roundtrip(self):
        p = TVS_PRESETS["SMBJ60"]
        inst = TVSClamp.from_params(p)
        assert isinstance(inst, ClampModel)
        assert isinstance(inst, TVSClamp)


# ---------------------------------------------------------------------------
# 5. Custom preset presence (must be last key in Python 3.7+ ordered dict)
# ---------------------------------------------------------------------------
class TestCustomPresetPresence:
    def test_zener_custom_exists_and_is_last(self):
        assert "Custom" in ZENER_PRESETS
        assert list(ZENER_PRESETS.keys())[-1] == "Custom"

    def test_schottky_custom_exists_and_is_last(self):
        assert "Custom" in SCHOTTKY_PRESETS
        assert list(SCHOTTKY_PRESETS.keys())[-1] == "Custom"

    def test_tvs_custom_exists_and_is_last(self):
        assert "Custom" in TVS_PRESETS
        assert list(TVS_PRESETS.keys())[-1] == "Custom"


# ---------------------------------------------------------------------------
# 6. VDD requirement
# ---------------------------------------------------------------------------
class TestVddRequirement:
    def test_zener_ignores_vdd_when_passed(self):
        z = ZenerClamp()
        v, r = z.voltage_at_current(5.0, vdd=3.3)
        assert v > 0

    def test_zener_ignores_vdd_when_omitted(self):
        z = ZenerClamp()
        v, r = z.voltage_at_current(5.0)
        assert v > 0

    def test_tvs_ignores_vdd_when_passed(self):
        t = TVSClamp()
        v, r = t.voltage_at_current(5.0, vdd=3.3)
        assert v > 0

    def test_tvs_ignores_vdd_when_omitted(self):
        t = TVSClamp()
        v, r = t.voltage_at_current(5.0)
        assert v > 0

    def test_schottky_raises_when_vdd_is_none(self):
        s = SchottkyClamp()
        with pytest.raises(ValueError, match="vdd"):
            s.voltage_at_current(5.0, vdd=None)

    def test_schottky_works_when_vdd_provided(self):
        s = SchottkyClamp()
        v, r = s.voltage_at_current(5.0, vdd=3.3)
        assert v > 0
