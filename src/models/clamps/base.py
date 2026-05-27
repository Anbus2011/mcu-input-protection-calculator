"""
Abstract base class for clamp voltage models.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class ClampModel(ABC):
    """Strategy interface for clamp devices (Zener, TVS, Schottky, etc.)."""

    @abstractmethod
    def voltage_at_current(
        self,
        i_ma: float,
        use_worst_case: bool = False,
        vdd: float | None = None,
    ) -> tuple[float, float]:
        """
        Return (v_clamp, r_differential) at the given current.

        Parameters
        ----------
        i_ma : float
            Clamp current in milli-amps.
        use_worst_case : bool
            If True, use worst-case (max) datasheet parameters.
        vdd : float | None
            Supply voltage; used by Schottky clamp, ignored by Zener/TVS.

        Returns
        -------
        tuple[float, float]
            (clamped voltage in V, differential resistance in Ohms)
        """
