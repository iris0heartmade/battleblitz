from __future__ import annotations

from copy import deepcopy
from typing import Any


class SpawnOverrideError(ValueError):
    """Raised when a battle's spawn_overrides cannot be applied."""


def _match_key(entry: dict[str, Any]) -> tuple[str, int, int]:
    return (
        str(entry["color"]),
        int(entry["x"]),
        int(entry["y"]),
    )


def _coord_key(entry: dict[str, Any]) -> tuple[int, int]:
    return (int(entry["x"]), int(entry["y"]))


def _find_index(
    entries: list[dict[str, Any]],
    *,
    color: str,
    x: int,
    y: int,
) -> int | None:
    target = (str(color), int(x), int(y))
    for idx, entry in enumerate(entries):
        if _match_key(entry) == target:
            return idx
    return None


def apply_spawn_overrides(
    base_units: list[dict[str, Any]],
    overrides: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Apply battle-level spawn overrides to a map's initial_units.

    Order is fixed:
      1. ``remove``
      2. ``replace``
      3. ``add``

    Matching for ``remove`` / ``replace.match`` is exact
    ``(color, x, y)``. Replacement units inherit the matched entry's
    ``x`` / ``y`` when the override omits them.
    """
    resolved = [deepcopy(u) for u in (base_units or [])]
    if not overrides:
        return resolved

    for entry in overrides.get("remove") or []:
        idx = _find_index(
            resolved,
            color=str(entry["color"]),
            x=int(entry["x"]),
            y=int(entry["y"]),
        )
        if idx is None:
            raise SpawnOverrideError(
                "spawn_overrides.remove target not found: "
                f"{_match_key(entry)}"
            )
        resolved.pop(idx)

    for entry in overrides.get("replace") or []:
        match = entry["match"]
        idx = _find_index(
            resolved,
            color=str(match["color"]),
            x=int(match["x"]),
            y=int(match["y"]),
        )
        if idx is None:
            raise SpawnOverrideError(
                "spawn_overrides.replace target not found: "
                f"{_match_key(match)}"
            )
        unit = deepcopy(entry["unit"])
        unit.setdefault("x", int(match["x"]))
        unit.setdefault("y", int(match["y"]))
        resolved[idx] = unit

    for entry in overrides.get("add") or []:
        resolved.append(deepcopy(entry))

    seen_coords: dict[tuple[int, int], dict[str, Any]] = {}
    for entry in resolved:
        coord = _coord_key(entry)
        if coord in seen_coords:
            raise SpawnOverrideError(
                "spawn_overrides produced duplicate coord "
                f"{coord}: {seen_coords[coord]!r} vs {entry!r}"
            )
        seen_coords[coord] = entry

    return resolved


__all__ = [
    "SpawnOverrideError",
    "apply_spawn_overrides",
]
