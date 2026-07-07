"""P2.4 — multi-style procedural map generator tests."""
from __future__ import annotations

import pytest

from app.config import (
    CASTLE_DOOR, CASTLE_FLOOR, CASTLE_STAIRS, CASTLE_THRONE, CASTLE_VAULT,
    CASTLE_WALL, MAP_STYLES, STYLE_CASTLE_INTERNAL, STYLE_COMPACT_OUTER,
    STYLE_DESERT_OUTER, STYLE_GRASS_OUTER, STYLE_SNOW_OUTER,
    TERRAIN_BARRACKS, TERRAIN_CASTLE, TERRAIN_FOREST, TERRAIN_GATE,
    TERRAIN_PLAIN, TERRAIN_RIVER, TERRAIN_ROAD, TERRAIN_VILLAGE,
)
from app.game_logic import (
    MAP_PRESETS, _layout_to_tiles, generate_map, generate_map_preset,
)


# ============================================================
# Style table integrity
# ============================================================

def test_all_styles_have_required_keys():
    for sid, cfg in MAP_STYLES.items():
        assert "biome" in cfg, f"style {sid} missing biome"
        assert "mode" in cfg, f"style {sid} missing mode"
        assert "display_cn" in cfg
        # outer styles need weights + safe_zone_radius
        if cfg["mode"] != "castle_internal":
            assert "weights" in cfg
            assert cfg["weights"].get(TERRAIN_PLAIN, 0) > 0
        # castle_internal needs tile_palette
        if cfg["mode"] == "castle_internal":
            assert "tile_palette" in cfg
            assert cfg["tile_palette"].get(CASTLE_FLOOR, 0) > 0


# ============================================================
# generate_map — outer styles
# ============================================================

@pytest.mark.parametrize("style", [
    STYLE_GRASS_OUTER, STYLE_SNOW_OUTER, STYLE_DESERT_OUTER, STYLE_COMPACT_OUTER,
])
@pytest.mark.parametrize("size,players", [
    (15, 2), (15, 4), (20, 2), (20, 4), (25, 4),
])
def test_outer_styles_have_correct_hq_count(style, size, players):
    g = generate_map(seed=1, num_castles=players, style=style, size=size)
    # Each player gets exactly one whole-tile `castle` centre.
    castles = sum(1 for row in g for t in row if t.terrain == TERRAIN_CASTLE)
    assert castles == players, f"{style} {size}x{size} {players}p got {castles} castles"


@pytest.mark.parametrize("style", [
    STYLE_GRASS_OUTER, STYLE_SNOW_OUTER, STYLE_DESERT_OUTER, STYLE_COMPACT_OUTER,
])
def test_outer_styles_no_castle_subtypes(style):
    """Outer styles must NOT bleed castle_* sub-features — those are
    reserved for the castle_internal style and hand-authored layouts."""
    g = generate_map(seed=42, num_castles=2, style=style, size=15)
    for row in g:
        for t in row:
            assert getattr(t, "subtype", None) is None, (
                f"{style} leaked a {t.subtype!r} subtype at ({t.x},{t.y})"
            )


def test_outer_styles_respect_safe_zone():
    """In a 15×15 grass_outer map with 2 castles, the cells immediately
    surrounding the castle centres must be plain (no forest / river /
    village)."""
    g = generate_map(seed=99, num_castles=2, style=STYLE_GRASS_OUTER, size=15)
    castle_cells = {(t.x, t.y) for row in g for t in row if t.terrain == TERRAIN_CASTLE}
    assert castle_cells == {(2, 2), (12, 12)}
    for cx, cy in castle_cells:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < 15 and 0 <= ny < 15:
                    assert g[ny][nx].terrain == TERRAIN_PLAIN, (
                        f"safe-zone at ({nx},{ny}) is {g[ny][nx].terrain}"
                    )


# ============================================================
# generate_map — castle_internal style
# ============================================================

def test_castle_internal_has_no_outer_terrains():
    g = generate_map(seed=7, num_castles=2, style=STYLE_CASTLE_INTERNAL, size=20)
    for row in g:
        for t in row:
            assert t.terrain == TERRAIN_CASTLE, (
                f"castle_internal leaked {t.terrain!r} at ({t.x},{t.y})"
            )
            assert t.subtype in {
                CASTLE_FLOOR, CASTLE_WALL, CASTLE_THRONE, CASTLE_DOOR,
                CASTLE_STAIRS, CASTLE_VAULT,
            }


def test_castle_internal_throne_count_matches_players():
    g = generate_map(seed=8, num_castles=4, style=STYLE_CASTLE_INTERNAL, size=20)
    thrones = sum(1 for row in g for t in row if t.subtype == CASTLE_THRONE)
    assert thrones == 4


def test_castle_internal_hq_has_door_and_stairs():
    """Each HQ centre should have at least 1 castle_door cell on a
    cardinal neighbour, and 1 castle_stairs somewhere nearby."""
    g = generate_map(seed=11, num_castles=2, style=STYLE_CASTLE_INTERNAL, size=20)
    castles = [(t.x, t.y) for row in g for t in row if t.subtype == CASTLE_THRONE]
    for cx, cy in castles:
        doors = 0
        for dx, dy in [(0, -1), (1, 0), (0, 1), (-1, 0)]:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < 20 and 0 <= ny < 20:
                if g[ny][nx].subtype == CASTLE_DOOR:
                    doors += 1
        assert doors >= 1, (
            f"HQ at ({cx},{cy}) has no castle_door on any cardinal neighbour"
        )


# ============================================================
# Determinism
# ============================================================

@pytest.mark.parametrize("style", [
    STYLE_GRASS_OUTER, STYLE_CASTLE_INTERNAL, STYLE_SNOW_OUTER,
])
def test_same_seed_same_map(style):
    """Two generate_map calls with the same seed must produce the
    byte-identical grid (terrain + subtype + x + y)."""
    g1 = generate_map(seed=314, num_castles=2, style=style, size=15)
    g2 = generate_map(seed=314, num_castles=2, style=style, size=15)
    for y in range(15):
        for x in range(15):
            assert g1[y][x].terrain == g2[y][x].terrain
            assert getattr(g1[y][x], "subtype", None) == getattr(g2[y][x], "subtype", None)


# ============================================================
# Layout → tile parser
# ============================================================

def test_layout_parser_handles_castle_subtype_chars():
    layout = [
        "fffwwwfff",
        "ffTffffff",
        "wffdfffff",
        "wwwfffffw",
    ]
    g = _layout_to_tiles(layout)
    # T at row 1, col 2
    assert g[1][2].subtype == CASTLE_THRONE, f"got {g[1][2].subtype}"
    # d at row 2, col 3 (next to T at column 2)
    assert g[2][3].subtype == CASTLE_DOOR, f"got {g[2][3].subtype}"
    # f at row 0, col 0
    assert g[0][0].terrain == TERRAIN_CASTLE
    assert g[0][0].subtype == CASTLE_FLOOR
    # w at row 0, col 3
    assert g[0][3].subtype == CASTLE_WALL, f"got {g[0][3].subtype}"
    # Every subtyped tile's terrain is still 'castle' (compatibility).
    for row in g:
        for t in row:
            if t.subtype is not None:
                assert t.terrain == TERRAIN_CASTLE


def test_generate_map_preset_round_trips_castle_internal_json():
    """A generated castle_internal preset must round-trip through
    `generate_map_preset(preset_id, ...)` without losing subtypes."""
    # Pick the first castle_internal preset we can find.
    presets_with_internal = [
        (pid, p) for pid, p in MAP_PRESETS.items()
        if p.get("style") == STYLE_CASTLE_INTERNAL
    ]
    assert presets_with_internal, "expected at least one castle_internal preset"
    pid, preset = presets_with_internal[0]
    grid = generate_map_preset(pid, seed=42).tiles
    # Re-load via _layout_to_tiles and compare subtype counts.
    reloaded = _layout_to_tiles(preset["layout"])
    sub_a = sum(1 for r in grid for t in r if getattr(t, "subtype", None))
    sub_b = sum(1 for r in reloaded for t in r if getattr(t, "subtype", None))
    assert sub_a == sub_b, (
        f"subtype count mismatch: live={sub_a} vs json-replay={sub_b}"
    )
