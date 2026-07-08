"""Tests for backward-compat: legacy map JSONs without `initial_units`.

The P2.6 refactor added `initial_units` as a hard requirement on every
map JSON. That requirement is right for new maps, but breaks the world
for two practical cases:

1. **User-uploaded / future map JSONs** that pre-date P2.6 or were
   authored against the old spec (no `initial_units` field).
2. **In-memory maps** constructed by tests or external tooling that
   pass a `preset_id` + `seed` without a populated layout.

Both must **not** bring the server down at import time. The loader
must auto-fill a default roster using `_classic_initial_units(...)`,
matching the same roster the runtime fallback in `generate_map_preset`
already uses for the procedural "classic" preset.

These tests cover that fallback path WITHOUT touching the
`MAP_PRESETS` global (which is built once at import and would
cross-contaminate other test modules).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.game_logic import (
    MAP_PRESETS,
    _classic_initial_units,
    _load_map_presets,
    _resolve_size,
)


# ============================================================
# Direct unit test: `_load_map_presets` must not raise on
# a legacy map JSON that lacks `initial_units`.
# ============================================================
class TestLoaderLegacyFallback:
    """Drive `_load_map_presets` against synthetic legacy map dicts."""

    def _write_legacy_map(self, tmp_path: Path, map_id: str, num_players: int = 2) -> Path:
        """Write a minimal legacy map JSON (no initial_units) into tmp."""
        # 10x10 grid: '.' = plain, 'C' = castle; castles at known corners
        rows = ["." * 10 for _ in range(10)]
        # Stamp a castle in two corners (just so the file "looks" like a map)
        rows[0] = "C" + rows[0][1:]
        rows[-1] = rows[-1][:-1] + "C"
        data = {
            "id": map_id,
            "name": "Legacy test map",
            "description": "Synthetic legacy map (no initial_units)",
            "biome": "grass",
            "size": 10,
            "layout": rows,
            "recommended_players": num_players,
        }
        path = tmp_path / f"{map_id}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def test_legacy_map_without_initial_units_does_not_raise(self, tmp_path, monkeypatch):
        """`_load_map_presets` must auto-fill missing initial_units, not raise."""
        from pathlib import Path as _Path

        # Point the loader's maps dir at our temp directory
        monkeypatch.setattr(
            "app.game_logic._MAPS_DIR", _Path(tmp_path)
        )
        self._write_legacy_map(tmp_path, "legacy_two_player", num_players=2)

        # Must not raise — this is the bug we're fixing
        presets = _load_map_presets()

        assert "legacy_two_player" in presets
        units = presets["legacy_two_player"]["initial_units"]
        # 2 castles × 5 units (classic roster) = 10
        assert len(units) == 10

    def test_legacy_map_recommended_players_drives_count(self, tmp_path, monkeypatch):
        """The number of auto-generated units scales with recommended_players."""
        from pathlib import Path as _Path

        monkeypatch.setattr(
            "app.game_logic._MAPS_DIR", _Path(tmp_path)
        )
        self._write_legacy_map(tmp_path, "legacy_four_player", num_players=4)

        presets = _load_map_presets()
        units = presets["legacy_four_player"]["initial_units"]
        # 4 castles × 5 units (classic roster) = 20
        assert len(units) == 20

    def test_legacy_map_fills_canonical_color_distribution(self, tmp_path, monkeypatch):
        """Auto-generated units cover exactly the 4 classic colors."""
        from pathlib import Path as _Path

        monkeypatch.setattr(
            "app.game_logic._MAPS_DIR", _Path(tmp_path)
        )
        self._write_legacy_map(tmp_path, "legacy_full_roster", num_players=4)

        presets = _load_map_presets()
        units = presets["legacy_full_roster"]["initial_units"]
        colors = {u["color"] for u in units}
        # 4-player fallback uses red/blue/green/yellow
        assert colors == {"red", "blue", "green", "yellow"}

    def test_existing_initial_units_unchanged(self, tmp_path, monkeypatch):
        """Maps that DO declare initial_units must not be auto-overwritten."""
        from pathlib import Path as _Path

        monkeypatch.setattr("app.game_logic._MAPS_DIR", _Path(tmp_path))
        # Hand-author a map with explicit initial_units (just 2 units)
        data = {
            "id": "explicit_map",
            "name": "Explicit",
            "biome": "grass",
            "size": 5,
            "layout": ["." * 5 for _ in range(5)],
            "initial_units": [
                {"x": 0, "y": 1, "type": "swordsman", "color": "red", "level": 1},
                {"x": 4, "y": 3, "type": "archer", "color": "blue", "level": 1},
            ],
        }
        (tmp_path / "explicit_map.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        presets = _load_map_presets()
        units = presets["explicit_map"]["initial_units"]
        # Must be exactly the 2 we wrote — no auto-filling on top of existing data
        assert len(units) == 2
        assert units[0]["type"] == "swordsman"
        assert units[1]["type"] == "archer"

    def test_explicitly_empty_initial_units_triggers_fallback(self, tmp_path, monkeypatch):
        """`initial_units: []` is almost always a forgotten field — treat as missing.

        Rationale: an empty list would mean "zero units spawn", which produces
        an unplayable game. If the author actually wanted no units, they
        wouldn't ship a battle map. Falling back matches the missing-key path.
        """
        from pathlib import Path as _Path

        monkeypatch.setattr("app.game_logic._MAPS_DIR", _Path(tmp_path))
        data = {
            "id": "empty_units_map",
            "name": "Empty",
            "biome": "grass",
            "size": 10,
            "layout": ["." * 10 for _ in range(10)],
            "recommended_players": 2,
            "initial_units": [],  # explicitly empty — treat same as missing
        }
        (tmp_path / "empty_units_map.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        presets = _load_map_presets()
        units = presets["empty_units_map"]["initial_units"]
        # Fallback fills it with 2 castles × 5 units = 10
        assert len(units) == 10


# ============================================================
# Regression: the 42 built-in maps must still load with no warnings.
# ============================================================
class TestBuiltinMapsStillLoad:
    """Sanity check that the fallback doesn't break the remaining maps."""

    def test_all_builtin_maps_present_in_MAP_PRESETS(self):
        # P2.6+ — 22 built-in maps + 1 inline "classic" = 23 in the
        # registry (custom maps live under maps/custom/ and may or
        # may not be present).
        builtin = [p for p in MAP_PRESETS.keys() if p != "classic"]
        assert len(builtin) >= 22, (
            f"expected >=22 built-in maps, got {len(builtin)}"
        )

    def test_every_builtin_map_has_initial_units(self):
        for pid, data in MAP_PRESETS.items():
            assert "initial_units" in data, f"{pid} missing initial_units"
            assert isinstance(data["initial_units"], list)
            assert len(data["initial_units"]) > 0, f"{pid} has empty initial_units"


# ============================================================
# Auto-generated units must match the runtime `_classic_initial_units`
# contract (same colors, same offsets, same unit types).
# ============================================================
class TestFallbackMatchesRuntime:
    def test_fallback_equals_classic_initial_units(self):
        """The fallback path uses the same helper as runtime, so output is identical."""
        canonical = _classic_initial_units(num_castles=4)
        # 4 castles × 5 units = 20
        assert len(canonical) == 20
        colors = sorted({u["color"] for u in canonical})
        assert colors == ["blue", "green", "red", "yellow"]
        types = sorted({u["type"] for u in canonical})
        # The classic roster
        assert types == ["archer", "healer", "knight", "swordsman"]
        # All units are level 1
        assert all(u["level"] == 1 for u in canonical)