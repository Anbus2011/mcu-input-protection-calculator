"""
Clamp strategy registry.

Maps clamp-type strings to their ``ClampModel`` implementation classes.
New clamp types (TVS, Schottky) will be registered here in subsequent tasks.
"""
from __future__ import annotations

from src.models.clamps.base import ClampModel
from src.models.clamps.zener import ZenerClamp
from src.models.clamps.schottky import SchottkyClamp
from src.models.clamps.tvs import TVSClamp

# Registry: clamp-type string -> ClampModel subclass
CLAMP_REGISTRY: dict[str, type[ClampModel]] = {
    "zener": ZenerClamp,
    "schottky": SchottkyClamp,
    "tvs": TVSClamp,
}

__all__ = [
    "ClampModel",
    "ZenerClamp",
    "SchottkyClamp",
    "TVSClamp",
    "CLAMP_REGISTRY",
]
