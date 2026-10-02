"""Small input-validation helpers shared by the CO Power endpoints and tests.

Kept separate from `effects.py` so the route layer and the unit-test layer
can import the same pure function without pulling in SQLAlchemy / Pydantic.
"""
from __future__ import annotations

from typing import Optional, Tuple


class CenterOutOfBounds(ValueError):
    """Raised when a CO Power center_xy falls outside the map grid."""


def validate_center_xy(
    center_xy: Optional[Tuple[int, int]],
    *,
    map_size: int,
) -> Optional[Tuple[int, int]]:
    """Validate a (x, y) center coordinate for AOE-style CO Powers.

    - `None` means "no center required" (e.g. stat-only powers like anna/yun).
      Returns `None` unchanged.
    - A tuple must satisfy `0 <= x < map_size` and `0 <= y < map_size`.
      Out-of-bounds raises `CenterOutOfBounds` (a `ValueError` subclass so
      existing `except ValueError` callers keep working).

    Why a helper: the route layer converts this into HTTP 400, and the unit
    tests can call it directly without spinning up the FastAPI app.
    """
    if center_xy is None:
        return None
    if not isinstance(center_xy, tuple) or len(center_xy) != 2:
        raise CenterOutOfBounds(
            f"center_xy must be a (x, y) tuple, got {center_xy!r}"
        )
    cx, cy = center_xy
    if not (0 <= cx < map_size and 0 <= cy < map_size):
        raise CenterOutOfBounds(
            f"center ({cx}, {cy}) out of bounds; map is {map_size}x{map_size}"
        )
    return center_xy
