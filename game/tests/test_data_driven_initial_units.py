"""Tests for data-driven initial_units — loader validation + spawn materialization.

P2.6 refactor: every map preset carries its own initial_units list, validated
at load time. This module covers:
  * `_resolve_size` (legacy int vs new {width,height} dict)
  * `generate_map_preset` returning a MapPresetResult
  * All 41 built-in maps under `game/maps/` having a valid initial_units
  * The `test_arena_10x10_2v2` showcase map having exactly 20 units,
    4 colors × 5 units each
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.game_logic import _resolve_size


TEST_MAP_ID = "test_arena_10x10_2v2"
MAPS_DIR = Path(__file__).resolve().parent.parent / "maps"


# ============================================================
# _resolve_size — accept both legacy int and new {width,height}
# ============================================================
class TestResolveSize:
    def test_legacy_int(self):
        r = _resolve_size(15)
        assert r == {"width": 15, "height": 15}

    def test_object(self):
        r = _resolve_size({"width": 10, "height": 7})
        assert r == {"width": 10, "height": 7}

    def test_bad_type(self):
        with pytest.raises(TypeError, match="size must be int or dict"):
            _resolve_size("15")


# ============================================================
# generate_map_preset — MapPresetResult shape
# ============================================================
class TestGenerateMapPreset:
    def test_returns_map_preset_result(self):
        """generate_map_preset returns a MapPresetResult (not raw tiles)."""
        from app.game_logic import generate_map_preset, MapPresetResult
        # "classic" is the special procedural fallback preset; the loader
        # inlines a placeholder initial_units entry for it so the
        # post-2.6 hard validation accepts it.
        result = generate_map_preset("classic", seed=1, num_castles=4)
        assert isinstance(result, MapPresetResult)
        assert hasattr(result, "tiles")
        assert hasattr(result, "initial_units")
        # tiles is the 2D grid; initial_units is a list (possibly empty
        # for procedurally generated maps).
        assert isinstance(result.tiles, list)
        assert isinstance(result.initial_units, list)
        # Tiles grid is non-empty for a valid generation call.
        assert len(result.tiles) > 0
        assert len(result.tiles[0]) > 0

    def test_test_arena_returns_20_units(self):
        """test_arena_10x10_2v2 should produce 20 initial units."""
        from app.game_logic import generate_map_preset
        result = generate_map_preset(TEST_MAP_ID, seed=1, num_castles=4)
        assert len(result.initial_units) == 20


# ============================================================
# Walk every built-in map and verify initial_units integrity.
# ============================================================
class TestMapsHaveInitialUnits:
    """Validate every map JSON in game/maps/ has well-formed initial_units."""

    @pytest.fixture(scope="class")
    def map_files(self) -> list[Path]:
        if not MAPS_DIR.is_dir():
            pytest.skip(f"maps directory not found at {MAPS_DIR}")
        files = sorted(MAPS_DIR.glob("*.json"))
        # P2.7+ — 7 built-in maps remain. The 18 auto-generated outer
        # presets were deleted; replaced by 3 hand-authored balanced
        # maps and 3 realistic maps (one per biome) generated with the
        # improved P2.7 generator (realistic HQ, biome consistency,
        # varied rosters).
        assert len(files) >= 7, (
            f"expected at least 7 built-in maps, found {len(files)}"
        )
        return files

    @pytest.fixture(scope="class")
    def unit_type_ids(self) -> set[str]:
        from app.classes.units import type_ids
        return set(type_ids())

    def test_every_map_has_initial_units_field(self, map_files):
        """Each map JSON declares an `initial_units` list."""
        import json
        for path in map_files:
            data = json.loads(path.read_text(encoding="utf-8"))
            assert "initial_units" in data, (
                f"{path.name} missing 'initial_units'"
            )
            assert isinstance(data["initial_units"], list)
            assert len(data["initial_units"]) > 0, (
                f"{path.name} has empty initial_units"
            )

    def test_every_unit_has_required_fields(self, map_files):
        """Every initial_unit entry has x, y, type, color."""
        import json
        required = ("x", "y", "type", "color")
        for path in map_files:
            data = json.loads(path.read_text(encoding="utf-8"))
            for idx, u in enumerate(data["initial_units"]):
                for k in required:
                    assert k in u, (
                        f"{path.name} unit #{idx} missing {k!r}: {u}"
                    )

    def test_all_coords_unique_within_map(self, map_files):
        """Within a single map no two units may share (x, y)."""
        import json
        for path in map_files:
            data = json.loads(path.read_text(encoding="utf-8"))
            seen = set()
            for u in data["initial_units"]:
                coord = (int(u["x"]), int(u["y"]))
                assert coord not in seen, (
                    f"{path.name} duplicate coord {coord}"
                )
                seen.add(coord)

    def test_all_coords_in_bounds(self, map_files):
        """Every initial_unit (x, y) lies inside the map's size."""
        import json
        for path in map_files:
            data = json.loads(path.read_text(encoding="utf-8"))
            size = _resolve_size(data["size"])
            w, h = size["width"], size["height"]
            for u in data["initial_units"]:
                x, y = int(u["x"]), int(u["y"])
                assert 0 <= x < w and 0 <= y < h, (
                    f"{path.name} unit ({x},{y}) out of bounds "
                    f"for {w}x{h}"
                )

    def test_all_unit_types_are_known(self, map_files, unit_type_ids):
        """Every unit.type appears in app.classes.units.type_ids()."""
        import json
        for path in map_files:
            data = json.loads(path.read_text(encoding="utf-8"))
            for u in data["initial_units"]:
                # If the unit registry is empty (test env without
                # classes loaded), fall back to "non-empty string".
                if unit_type_ids:
                    assert u["type"] in unit_type_ids, (
                        f"{path.name} unknown unit type {u['type']!r}"
                    )
                else:
                    assert isinstance(u["type"], str) and u["type"], (
                        f"{path.name} unit type is empty: {u}"
                    )

    def test_every_map_loaded_into_map_presets(self):
        """Every JSON in game/maps/ shows up in MAP_PRESETS at import time."""
        from app.game_logic import MAP_PRESETS
        for path in MAPS_DIR.glob("*.json"):
            assert path.stem in MAP_PRESETS, (
                f"{path.name} not present in MAP_PRESETS"
            )


# ============================================================
# Specific showcase map: test_arena_10x10_2v2 — 4 colors × 5 units = 20
# ============================================================
class TestTestArenaMap:
    """Showcase test arena: 10x10 2v2 with 4 colors and 20 units total."""

    @pytest.fixture
    def arena_data(self) -> dict:
        from app.game_logic import MAP_PRESETS
        assert TEST_MAP_ID in MAP_PRESETS, (
            f"{TEST_MAP_ID} not in MAP_PRESETS — was it added to game/maps/?"
        )
        return MAP_PRESETS[TEST_MAP_ID]

    def test_total_unit_count(self, arena_data):
        assert len(arena_data["initial_units"]) == 20

    def test_size_is_10x10(self, arena_data):
        size = _resolve_size(arena_data["size"])
        assert size == {"width": 10, "height": 10}

    def test_four_colors(self, arena_data):
        colors = {u["color"] for u in arena_data["initial_units"]}
        assert colors == {"red", "blue", "green", "yellow"}

    def test_five_units_per_color(self, arena_data):
        from collections import Counter
        counts = Counter(u["color"] for u in arena_data["initial_units"])
        for color in ("red", "blue", "green", "yellow"):
            assert counts[color] == 5, (
                f"{color} should have 5 units, got {counts[color]}"
            )

    def test_team_mode_is_2v2(self, arena_data):
        assert arena_data.get("team_mode") == "2v2"

    def test_generate_spawns_twenty_units(self):
        """End-to-end: generate_map_preset → 20 spawn entries."""
        from app.game_logic import generate_map_preset
        result = generate_map_preset(TEST_MAP_ID, seed=1, num_castles=4)
        assert len(result.initial_units) == 20
        # Layout-derived grid is 10x10
        assert len(result.tiles) == 10
        for row in result.tiles:
            assert len(row) == 10


# ============================================================
# Optional e2e test: POST /games with the test arena yields 20 spawn units.
# Skipped when the integration `client` fixture is not requested (e.g.
# running with `-k "not integration"`). Marked as integration so it
# follows the project convention.
# ============================================================
@pytest.mark.integration
class TestSpawnMaterialization:
    async def test_create_game_with_test_arena_yields_20_units(
        self, client, db_session
    ):
        """Creating a game with test_arena_10x10_2v2 spawns 20 units."""
        resp = await client.post("/games", json={
            "name": "test arena spawn",
            "map_preset": TEST_MAP_ID,
        })
        assert resp.status_code == 201, resp.text
        game_id = resp.json()["id"]

        # Add 4 AI players (one per color) to satisfy 4-player capacity.
        for i in range(4):
            r = await client.post(f"/games/{game_id}/add-ai", json={})
            assert r.status_code == 201, r.text

        # Start the game — units are spawned on transition into 'playing'.
        start = await client.post(f"/games/{game_id}/start")
        assert start.status_code == 200, start.text

        # The state endpoint now exposes the spawned units nested
        # under each player; flatten and count.
        state = (await client.get(f"/games/{game_id}/state")).json()
        players = state.get("players", [])
        units = [u for p in players for u in p.get("units", [])]
        assert len(units) == 20, f"expected 20 units, got {len(units)}"