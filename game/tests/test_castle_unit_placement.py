"""Tests for the policy that initial_units MAY be placed on castle tiles.

Originally the editor backend (game/app/routes/editor.py) rejected units
whose (x, y) was a 'C' tile, on the rationale "they need starting space".
That restriction was removed so that map authors can stack a defender on
their own HQ or design defence-in-depth spawns.

The spawn loop in routes/game.py:start_game sets
``Tile.occupied_unit_id = u.id`` regardless of terrain, so the engine
itself already supported castle placement. The test below pins the new
policy so it cannot regress.

Ref:
- editor.py: _validate_units (allows castle tiles; removed
  _validate_units_on_terrain)
- editor.py: save_custom_map() (no longer calls the castle-on-unit guard)
- game/app/routes/game.py:start_game (Tile.occupied_unit_id is set
  unconditionally; the unit's territory does not affect spawn success)
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

# Make sure we can import the app package on a bare sys.path
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))


class TestEditorAcceptsUnitsOnCastle(unittest.TestCase):
    """Pydantic-level: editor save accepts a unit whose (x, y) is a 'C' tile."""

    def test_snow_peak_tiles_pass_layout_validation(self):
        from app.routes.editor import _validate_layout

        layout = ["S" * 15 for _ in range(15)]

        _validate_layout(layout, 15, 15)

    def test_units_on_castle_tiles_pass_validation(self):
        from app.routes.editor import CustomMapSave, MapSize, InitialUnit
        # Editor's MapSize requires width/height ≥ 15.
        body = CustomMapSave(
            name="CastleOccupier",
            size=MapSize(width=15, height=15),
            biome="grass",
            layout=[
                "PPFFFFFFFFFFFFM",
                "PPFFFFFFFFFFFFM",
                "CCCCCCCCCCCCCCM",
                "CCCCCCCCCCCCCCM",
                "CCCCCCCCCCCCCCM",
                "CCCCCCCCCCCCCCM",
                "MFFFFFFFFFFFFFP",
                "MFFFFFFFFFFFFFP",
                "MFFFFFFFFFFFFFP",
                "MFFFFFFFFFFFFFM",
                "MFFFFFFFFFFFFFM",
                "MFFFFFFFFFFFFFM",
                "MFFFFFFFFFFFFFM",
                "MFFFFFFFFFFFFFM",
                "MFFFFFFFFFFFFFM",
            ],
            initial_units=[
                # Three units placed exactly on castle tiles — used to be rejected.
                InitialUnit(x=0, y=2, type="swordsman", color="red", level=2),
                InitialUnit(x=1, y=2, type="swordsman", color="red", level=1),
                InitialUnit(x=2, y=2, type="archer",    color="red", level=1),
                # And one on plain — always allowed.
                InitialUnit(x=1, y=0, type="knight", color="blue", level=1),
            ],
        )
        # Pydantic validation succeeds.
        self.assertEqual(len(body.initial_units), 4)
        self.assertEqual(body.initial_units[0].x, 0)
        self.assertEqual(body.initial_units[0].y, 2)


class TestEditorSaveHTTP(unittest.IsolatedAsyncioTestCase):
    """HTTP-level: POST /editor/maps accepts units on castle tiles."""

    async def test_post_with_castle_units_succeeds(self):
        # Lazy import — the app pulls in DB / network stacks we don't want
        # to load for the isolated Pydantic test above.
        from httpx import ASGITransport, AsyncClient
        from app.main import app

        layout = [
            "PPFFFFFFFFFFFFM",
            "PPFFFFFFFFFFFFM",
            "CCCCCCCCCCCCCCM",
            "CCCCCCCCCCCCCCM",
            "CCCCCCCCCCCCCCM",
            "CCCCCCCCCCCCCCM",
            "MFFFFFFFFFFFFFP",
            "MFFFFFFFFFFFFFP",
            "MFFFFFFFFFFFFFP",
            "MFFFFFFFFFFFFFM",
            "MFFFFFFFFFFFFFM",
            "MFFFFFFFFFFFFFM",
            "MFFFFFFFFFFFFFM",
            "MFFFFFFFFFFFFFM",
            "MFFFFFFFFFFFFFM",
        ]
        body = {
            "name": "HttpCastleUnitTest",
            "size": {"width": 15, "height": 15},
            "biome": "grass",
            "layout": layout,
            "initial_units": [
                {"x": 0, "y": 2, "type": "swordsman", "color": "red", "level": 2},
                {"x": 1, "y": 2, "type": "swordsman", "color": "red", "level": 1},
                {"x": 2, "y": 2, "type": "archer",    "color": "red", "level": 1},
            ],
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/editor/maps", json=body)
        self.assertEqual(r.status_code, 201, msg=r.text)
        saved = r.json()
        self.assertEqual(len(saved["initial_units"]), 3)
        # Confirm the positions are preserved (i.e. the editor didn't silently
        # move them off castle tiles).
        positions = sorted((u["x"], u["y"]) for u in saved["initial_units"])
        self.assertEqual(positions, [(0, 2), (1, 2), (2, 2)])

        # Cleanup: best-effort delete via the same endpoint.
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.delete(f"/editor/maps/{saved['id']}")

    async def test_saved_map_appears_in_presets_as_custom_map(self):
        from httpx import ASGITransport, AsyncClient
        from app.main import app

        body = {
            "name": "HttpPresetVisibilityTest",
            "size": {"width": 15, "height": 15},
            "biome": "desert",
            "layout": ["P" * 15 for _ in range(15)],
            "initial_units": [],
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            created = await client.post("/editor/maps", json=body)
            self.assertEqual(created.status_code, 201, msg=created.text)
            saved = created.json()
            presets = await client.get("/games/presets")
            self.assertEqual(presets.status_code, 200, msg=presets.text)
            preset_ids = {m["id"] for m in presets.json()["maps"]}
            self.assertIn(f"custom:{saved['id']}", preset_ids)
            await client.delete(f"/editor/maps/{saved['id']}")


class TestEditorUnitFieldShapeMatchesBuiltin(unittest.TestCase):
    """Sanity: editor output uses the SAME 5-field unit schema as built-in maps.

    Built-in map (e.g. test_arena_10x10_2v2.json) declares initial_units as
    {x, y, type, color, level}. The editor MUST produce the same shape so
    /games/presets can be parsed uniformly and start_game can dispatch
    color->player the same way for every preset source.
    """

    def test_unit_keys_match(self):
        builtin = json.loads(
            (_HERE.parent / "maps" / "test_arena_10x10_2v2.json").read_text(
                encoding="utf-8"
            )
        )
        # The editor schema (InitialUnit) is the only place editor output is
        # minted. Inspecting the dataclass via Pydantic is enough; no need to
        # spin up a request handler here.
        from app.routes.editor import InitialUnit
        editor_keys = set(InitialUnit.model_fields.keys())
        builtin_keys = set(builtin["initial_units"][0].keys())

        self.assertEqual(
            editor_keys, builtin_keys,
            f"editor unit schema {editor_keys} diverges from builtin {builtin_keys}",
        )


if __name__ == "__main__":
    unittest.main()
