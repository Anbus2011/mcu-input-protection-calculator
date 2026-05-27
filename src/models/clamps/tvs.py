"""
TVS diode clamp strategy (unidirectional and bidirectional).

Models a TVS diode clamping to GND.
Three-region V-I model:
  - Off region      (|i_ma| <= 0):          not conducting, (v_rwm, 1e9 Ohm)
  - Soft breakdown  (0 < |i_ma| < i_t):     linear V from v_rwm to v_br
  - Hard clamp      (|i_ma| >= i_t):        linear above v_br with R_dynamic slope

Bidirectional support added in T5: mirrors the positive-direction model for
negative currents.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.models.clamps.base import ClampModel

# Sentinel: differential resistance when TVS is off (open-circuit approximation)
_R_OFF: float = 1e9  # Ohms


@dataclass
class TVSClamp(ClampModel):
    """
    TVS diode clamp strategy (unidirectional and bidirectional).

    Parameters
    ----------
    v_rwm : float
        Reverse working / standoff voltage (V). Below this the TVS is off.
    v_br_min : float
        Minimum breakdown voltage (V) at I_T.
    v_br_max : float
        Maximum breakdown voltage (V) at I_T.
    v_c : float
        Clamping voltage (V) at peak pulse current I_PP.
    i_pp : float
        Peak pulse current (A).
    i_t : float
        Test current at which V_BR is specified (mA).
    c_pf : float
        Junction capacitance (pF) -- informational.
    p_ppm_w : float
        Peak pulse power (W) -- informational.
    polarity : str
        "unidirectional" (default) or "bidirectional".
        Unidirectional: negative i_ma returns off-state (v_rwm, 1e9).
        Bidirectional: mirrors the model for negative i_ma, returning
        negative clamped voltages.
    """

    v_rwm: float = 60.0
    v_br_min: float = 66.7
    v_br_max: float = 73.7
    v_c: float = 96.8
    i_pp: float = 6.2      # A
    i_t: float = 1.0       # mA
    c_pf: float = 380.0
    p_ppm_w: float = 600.0
    polarity: str = "unidirectional"

    def __post_init__(self) -> None:
        if self.polarity not in ("unidirectional", "bidirectional"):
            raise ValueError(f"Unknown polarity: {self.polarity!r}")

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------
    @classmethod
    def from_params(cls, p) -> "TVSClamp":
        """Construct from a dict (preset entry) or object with the same fields."""
        if isinstance(p, dict):
            return cls(
                v_rwm=p["v_rwm"],
                v_br_min=p["v_br_min"],
                v_br_max=p["v_br_max"],
                v_c=p["v_c"],
                i_pp=p["i_pp"],
                i_t=p["i_t"],
                c_pf=p.get("c_pf", 0.0),
                p_ppm_w=p.get("p_ppm_w", 0.0),
                polarity=p.get("polarity", "unidirectional"),
            )
        return cls(
            v_rwm=p.v_rwm,
            v_br_min=p.v_br_min,
            v_br_max=p.v_br_max,
            v_c=p.v_c,
            i_pp=p.i_pp,
            i_t=p.i_t,
            c_pf=p.c_pf,
            p_ppm_w=p.p_ppm_w,
            polarity=getattr(p, "polarity", "unidirectional"),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _calc_magnitude(
        self, i_ma_abs: float, use_worst_case: bool
    ) -> tuple[float, float]:
        """
        Compute (v_magnitude, r_differential) for a non-negative current magnitude.

        Three-region model:
          Off (i_ma_abs <= 0):          (v_rwm, 1e9)
          Soft breakdown (0 < i < i_t): linear from v_rwm to v_br
          Hard clamp (i >= i_t):        linear above v_br with R_dynamic
        """
        v_br = self.v_br_max if use_worst_case else self.v_br_min
        i_t_ma: float = self.i_t
        i_pp_ma: float = self.i_pp * 1000.0  # A -> mA

        delta_i_ma = i_pp_ma - i_t_ma
        if delta_i_ma > 0:
            r_dyn_v_per_ma = (self.v_c - v_br) / delta_i_ma
        else:
            r_dyn_v_per_ma = 0.0
        r_dyn_ohm = r_dyn_v_per_ma * 1000.0

        if i_ma_abs <= 0:
            return self.v_rwm, _R_OFF

        if i_ma_abs < i_t_ma:
            v_clamp = self.v_rwm + (v_br - self.v_rwm) * (i_ma_abs / i_t_ma)
            r_soft_v_per_ma = (v_br - self.v_rwm) / i_t_ma
            r_dif = r_soft_v_per_ma * 1000.0
            return v_clamp, r_dif

        # Hard clamp region
        v_clamp = v_br + (i_ma_abs - i_t_ma) * r_dyn_v_per_ma
        return v_clamp, r_dyn_ohm

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
        Return (v_clamp, r_differential) for the TVS at a given current.

        Unidirectional:
          - i_ma <= 0:  off-state (v_rwm, 1e9)
          - i_ma > 0:   three-region model (positive V)

        Bidirectional:
          - i_ma == 0:  symmetric off-state (0.0, 1e9)
          - i_ma > 0:   same as unidirectional positive path
          - i_ma < 0:   sign-mirrored: (-v_mag, r_dif)

        vdd is accepted for interface compatibility but ignored.
        Worst-case uses v_br_max; typical uses v_br_min.
        """
        if self.polarity == "unidirectional":
            # Original unidirectional behavior -- bit-identical to T4
            if i_ma <= 0:
                return self.v_rwm, _R_OFF
            return self._calc_magnitude(i_ma, use_worst_case)

        # Bidirectional: symmetric model
        if i_ma == 0.0:
            return 0.0, _R_OFF
        sign = 1.0 if i_ma > 0 else -1.0
        v_mag, r_dif = self._calc_magnitude(abs(i_ma), use_worst_case)
        return sign * v_mag, r_dif
