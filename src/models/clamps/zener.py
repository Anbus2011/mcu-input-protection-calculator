"""
Zener diode clamp strategy.

Lifts the existing ``calculate_zener_voltage`` logic verbatim into the
``ClampModel`` strategy interface so the rest of the codebase can dispatch
via the strategy pattern without any math changes.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.models.clamps.base import ClampModel


@dataclass
class ZenerClamp(ClampModel):
    """
    Three-region Zener V-I model.

    Parameters mirror ``ZenerParams`` and are stored directly so that
    ``ZenerClamp`` can be constructed from a ``ZenerParams`` instance via
    ``ZenerClamp.from_params()``.
    """
    vz_nom: float = 3.3
    vz_min: float = 3.1
    vz_max: float = 3.5
    izt_ma: float = 5.0
    izk_ma: float = 1.0
    zzt_typ: float = 85.0
    zzt_max: float = 95.0
    zzk_typ: float = 350.0
    zzk_max: float = 600.0
    ptot_mw: float = 265.0

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------
    @classmethod
    def from_params(cls, p) -> "ZenerClamp":
        """Construct from a ZenerParams dataclass instance."""
        return cls(
            vz_nom=p.vz_nom,
            vz_min=p.vz_min,
            vz_max=p.vz_max,
            izt_ma=p.izt_ma,
            izk_ma=p.izk_ma,
            zzt_typ=p.zzt_typ,
            zzt_max=p.zzt_max,
            zzk_typ=p.zzk_typ,
            zzk_max=p.zzk_max,
            ptot_mw=p.ptot_mw,
        )

    # ------------------------------------------------------------------
    # ClampModel interface
    # ------------------------------------------------------------------
    def voltage_at_current(
        self,
        i_ma: float,
        use_worst_case: bool = False,
        vdd: float | None = None,
    ) -> tuple[float, float]:
        """
        Calculate Zener clamp voltage at a given current.
        Returns (v_clamp, r_differential).

        Three-region model:
          - Below IZK: soft breakdown, V ~ 0.97-1.0 x VZ_knee
          - IZK to IZT: linear interpolation VZ_knee -> VZ_nom
          - Above IZT: extrapolate with ZZT slope
        """
        if use_worst_case:
            vz_at_izt = self.vz_max
            vz_at_izk = self.vz_max * 0.97
            zzt = self.zzt_max
            zzk = self.zzk_max
        else:
            vz_at_izt = self.vz_nom
            vz_at_izk = self.vz_nom * 0.94
            zzt = self.zzt_typ
            zzk = self.zzk_typ

        izt = self.izt_ma
        izk = self.izk_ma

        if i_ma <= 0:
            return vz_at_izk, zzk
        elif i_ma <= izk:
            ratio = i_ma / izk
            v_clamp = vz_at_izk * (0.97 + 0.03 * ratio)
            rdif = zzk
        elif i_ma <= izt:
            ratio = (i_ma - izk) / (izt - izk)
            v_clamp = vz_at_izk + (vz_at_izt - vz_at_izk) * ratio
            rdif = zzk + (zzt - zzk) * ratio
        else:
            v_clamp = vz_at_izt + (i_ma - izt) * zzt / 1000
            rdif = zzt

        return v_clamp, rdif
