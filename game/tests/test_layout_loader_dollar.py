"""Tests for `_layout_to_tiles` char-to-terrain mapping.

Caught a real bug during economy verification: the test_arena_10x10_2v2
map uses the `$` character for castle_vault tiles (per its description
"含 4 vault"), but `_layout_to_tiles` (`app/game_logic.py:1257-1268`)
has no entry for `$` in its `char_to_terrain` table. Result: 4 vault
tiles were silently dropped into the default `plain` bucket, breaking
gold income from those tiles.

This file pins the `$` → castle_vault mapping so it cannot regress.
"""
from __future__ import annotations

import pytest


class TestDollarToCastleVault:
    """`$` in a layout must map to CASTLE_VAULT."""

    def test_dollar_char_in_char_to_terrain_table(self):
        from app.game_logic import _layout_to_tiles
        # Build a Tile from each mapped char by inspecting the function's
        # local char_to_terrain dict via a tiny mock layout.
        layout = ["$"]
        from app.config import CASTLE_VAULT
        # The character needs to be tested through the actual loader.
        # Use a 1x1 layout to force the tile to be created.
        tiles = _layout_to_tiles([list("$")])
        assert len(tiles) == 1 and len(tiles[0]) == 1
        t = tiles[0][0]
        assert t.terrain == CASTLE_VAULT, (
            f"`$` should map to CASTLE_VAULT ({CASTLE_VAULT!r}), "
            f"got {t.terrain!r}"
        )

    def test_test_arena_layout_has_four_castle_vault_tiles(self):
        """test_arena_10x10_2v2.json declares 4 `$` cells; they must all
        load as castle_vault tiles, not plain."""
        from app.game_logic import generate_map_preset
        from app.config import CASTLE_VAULT
        result = generate_map_preset(
            "test_arena_10x10_2v2", seed=1, num_castles=4,
        )
        vaults = [t for row in result.tiles for t in row
                  if t.terrain == CASTLE_VAULT]
        assert len(vaults) == 4, (
            f"expected 4 castle_vault tiles from test_arena layout, "
            f"got {len(vaults)} (terrain dropped to plain)"
        )