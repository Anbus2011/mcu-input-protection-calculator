"""
Schottky diode clamp strategy (upper-rail only).

Models a Schottky diode connected between the protected node and VDD.
The diode conducts when the node tries to rise ABOVE VDD, clamping it to:
    V_clamp = VDD + VF(I_f)

VF is linearised around the datasheet test point using R_dynamic:
    VF(I_f) = VF_base + (I_f - I_f_test_ma) * R_dynamic / 1000

Worst-case uses VF_max instead of VF_typ.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.models.clamps.base import ClampModel


@dataclass
class SchottkyClamp(ClampModel):
    """
    Upper-rail Schottky clamp strategy.

    Parameters
    ----------
    vf_typ : float
        Typical forward voltage (V) at the datasheet test current.
    vf_max : float
        Maximum forward voltage (V) at the datasheet test current.
    if_test_ma : float
        Test current (mA) at which VF_typ / VF_max are specified.
    r_dynamic : float
        Differential (dynamic) resistance (Ohm).
    ir_ua : float
        Reverse leakage current (uA) -- informational.
    vr_max : float
        Maximum reverse voltage (V) -- informational.
    cd_pf : float
        Junction capacitance (pF) at 0 V -- informational.
    pd_mw : float
        Maximum power dissipation per channel (mW) -- informational.
    channels : int
        Number of channels in the package -- informational.
    """

    vf_typ: float = 0.32
    vf_max: float = 0.40
    if_test_ma: float = 10.0
    r_dynamic: float = 4.0
    ir_ua: float = 2.0
    vr_max: float = 30.0
    cd_pf: float = 10.0
    pd_mw: float = 200.0
    channels: int = 4

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------
    @classmethod
    def from_params(cls, p) -> "SchottkyClamp":
        """Construct from a mapping or object that exposes the same fields."""
        if isinstance(p, dict):
            return cls(
                vf_typ=p["vf_typ"],
                vf_max=p["vf_max"],
                if_test_ma=p["if_test_ma"],
                r_dynamic=p["r_dynamic"],
                ir_ua=p.get("ir_ua", 2.0),
                vr_max=p.get("vr_max", 30.0),
                cd_pf=p.get("cd_pf", 10.0),
                pd_mw=p.get("pd_mw", 200.0),
                channels=p.get("channels", 4),
            )
        return cls(
            vf_typ=p.vf_typ,
            vf_max=p.vf_max,
            if_test_ma=p.if_test_ma,
            r_dynamic=p.r_dynamic,
            ir_ua=p.ir_ua,
            vr_max=p.vr_max,
            cd_pf=p.cd_pf,
            pd_mw=p.pd_mw,
            channels=p.channels,
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
        Return (v_clamp_upper, r_differential) for the Schottky upper-rail clamp.

        v_clamp = VDD + VF(i_ma)
        VF(i_ma) = VF_base + (i_ma - IF_test) * R_dynamic / 1000

        If i_ma <= 0, the diode is reverse-biased; VF is 0 so v_clamp = VDD.

        Parameters
        ----------
        i_ma : float
            Forward current through the Schottky diode (mA).
        use_worst_case : bool
            If True, use VF_max; otherwise use VF_typ.
        vdd : float | None
            Supply voltage in Volts.  REQUIRED -- raises ValueError if None.

        Returns
        -------
        tuple[float, float]
            (v_clamp in V, differential resistance in Ohm)
        """
        if vdd is None:
            raise ValueError("SchottkyClamp requires vdd")

        vf_base = self.vf_max if use_worst_case else self.vf_typ
        r_dif = self.r_dynamic

        if i_ma <= 0:
            # Diode not conducting -- node is at or below VDD.
            return vdd + 0.0, r_dif

        # Linear extrapolation around the test point.
        vf = vf_base + (i_ma - self.if_test_ma) * r_dif / 1000.0
        # VF cannot be negative (physical lower bound).
        vf = max(vf, 0.0)

        v_clamp = vdd + vf
        return v_clamp, r_dif
