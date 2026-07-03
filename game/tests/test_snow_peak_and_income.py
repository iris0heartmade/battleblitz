"""P2.4 — Tests for the BUILDING_INCOME refactor + TERRAIN_SNOW_PEAK terrain."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.config import (
    BUILDING_INCOME, CASTLE_VAULT, INCOME_PER_TURN, INCOME_TERRAINS,
    MAP_STYLES, TERRAIN_BARRACKS, TERRAIN_SNOW_PEAK, TERRAIN_VILLAGE,
    STYLE_GRASS_OUTER, STYLE_SNOW_OUTER, STYLE_DESERT_OUTER, STYLE_COMPACT_OUTER,
)
from app.game_logic import _layout_to_tiles, generate_map


# ============================================================
# BUILDING_INCOME table
# ============================================================

def test_building_income_covers_all_income_terrains():
    """The refactor's BUILDING_INCOME table must produce the same keys
    as the legacy INCOME_TERRAINS tuple, so the income flow stays
    identical."""
    assert set(BUILDING_INCOME.keys()) == set(INCOME_TERRAINS)


def test_building_income_amounts_unchanged():
    """The user already approved the income numbers; the refactor
    must preserve them bit-for-bit. If a new yield tile is added
    later, add a key here AND to BUILDING_INCOME."""
    assert BUILDING_INCOME[TERRAIN_VILLAGE]["amount"] == 50
    assert BUILDING_INCOME[TERRAIN_BARRACKS]["amount"] == 100
    assert BUILDING_INCOME[CASTLE_VAULT]["amount"] == 150


def test_income_aliases_still_match():
    """The legacy INCOME_PER_TURN / INCOME_TERRAINS are derived from
    BUILDING_INCOME; they must be consistent."""
    for terrain, cfg in BUILDING_INCOME.items():
        assert INCOME_PER_TURN[terrain] == cfg["amount"], (
            f"{terrain}: INCOME_PER_TURN disagrees with BUILDING_INCOME"
        )
    assert set(INCOME_PER_TURN) == set(INCOME_TERRAINS)


def test_building_income_cap_field():
    """Every entry must have a cap_per_player field (None = no cap)."""
    for terrain, cfg in BUILDING_INCOME.items():
        assert "cap_per_player" in cfg, f"{terrain} missing cap_per_player"
        assert cfg["cap_per_player"] is None or isinstance(cfg["cap_per_player"], int)


def test_building_income_requires_owner():
    """Every current yield tile requires an owner (no toll-road style
    entries yet)."""
    for terrain, cfg in BUILDING_INCOME.items():
        assert cfg.get("requires_owner", True) is True, (
            f"{terrain} should require an owner"
        )


# ============================================================
# TERRAIN_SNOW_PEAK — schema and config
# ============================================================

def test_snow_peak_registered_in_move_cost():
    from app.config import TERRAIN_MOVE_COST
    assert TERRAIN_SNOW_PEAK in TERRAIN_MOVE_COST
    # Same as mountain (impassable).
    assert TERRAIN_MOVE_COST[TERRAIN_SNOW_PEAK] == 6


def test_snow_peak_registered_in_def_bonus():
    from app.config import TERRAIN_DEF_BONUS
    assert TERRAIN_SNOW_PEAK in TERRAIN_DEF_BONUS
    assert TERRAIN_DEF_BONUS[TERRAIN_SNOW_PEAK] == 3


def test_snow_peak_in_terrain_types():
    from app.config import TERRAIN_TYPES
    assert TERRAIN_SNOW_PEAK in TERRAIN_TYPES


# ============================================================
# Style weight tables
# ============================================================

def test_snow_outer_includes_snow_peak():
    """The snow-biome style must use snow_peak, not just plain mountain.
    Otherwise the user would never see the new asset."""
    weights = MAP_STYLES[STYLE_SNOW_OUTER]["weights"]
    assert TERRAIN_SNOW_PEAK in weights
    assert weights[TERRAIN_SNOW_PEAK] > 0


def test_snow_peak_absent_from_non_snow_styles():
    """Snow peaks are snow-biome-only. The grass/desert/compact styles
    must NOT spawn them — otherwise a desert map would have silver
    peaks, which is wrong."""
    for style_id in (STYLE_GRASS_OUTER, STYLE_DESERT_OUTER, STYLE_COMPACT_OUTER):
        weights = MAP_STYLES[style_id]["weights"]
        assert TERRAIN_SNOW_PEAK not in weights, (
            f"{style_id} should not include snow_peak (snow-biome-only)"
        )


# ============================================================
# Procedural generation
# ============================================================

@pytest.mark.parametrize("style", [STYLE_GRASS_OUTER, STYLE_DESERT_OUTER, STYLE_COMPACT_OUTER])
@pytest.mark.parametrize("size,players", [(15, 2), (20, 4), (25, 4)])
def test_non_snow_styles_never_emit_snow_peak(style, size, players):
    g = generate_map(seed=7, num_castles=players, style=style, size=size)
    snow_peak_count = sum(1 for row in g for t in row if t.terrain == TERRAIN_SNOW_PEAK)
    assert snow_peak_count == 0, (
        f"{style} {size}x{size} {players}p generated {snow_peak_count} snow_peaks"
    )


def test_snow_outer_can_emit_snow_peak():
    """Across a range of seeds, at least one must produce a snow peak."""
    found = False
    for seed in range(50):
        g = generate_map(seed=seed, num_castles=2, style=STYLE_SNOW_OUTER, size=20)
        if any(t.terrain == TERRAIN_SNOW_PEAK for row in g for t in row):
            found = True
            break
    assert found, "snow_outer generated 0 snow_peaks across 50 seeds"


# ============================================================
# Layout parser
# ============================================================

def test_layout_parser_s_char():
    from app.config import TERRAIN_PLAIN
    layout = [
        "SSSSSS",
        "SPSPSP",
        "SSSSSS",
    ]
    g = _layout_to_tiles(layout)
    assert g[0][0].terrain == TERRAIN_SNOW_PEAK
    assert g[1][0].terrain == TERRAIN_SNOW_PEAK
    assert g[1][1].terrain == TERRAIN_PLAIN  # P → plain, not village
