# Data-Driven Initial Units — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make every map JSON the single source of truth for which units spawn, where, at what level. Delete global preset rosters (`_COMPOSITIONS`) and the hardcoded spawn-offset table (`_spawn_xy_for_castle`).

**Architecture:** Engine reads `initial_units: [{x, y, type, color, level}]` from preset JSON → materializes units per color. Works for built-in maps, custom maps, mainline battles. Startup validation rejects broken presets immediately.

**Tech Stack:** Python 3.13, FastAPI, SQLite (Alembic), vanilla JS frontend

## Current Execution Status (2026-07-13)

This plan is complete in the current branch and should be treated as historical execution detail.

- Implemented and pushed: map-authored `initial_units`, removal of active unit-composition selection, startup validation, and Web UI create-game cleanup.
- The branch has since advanced to commander/CO UI work and AI counter consistency fixes (`b0df415`, `07d2081`).
- Remaining project-level step: full-suite verification and PR creation once GitHub permissions or local `gh` are available.

## Global Constraints

- 41 built-in map JSONs MUST all gain valid `initial_units` (no fallback path)
- `_COMPOSITIONS`, `default_roster()`, `get_roster_for_composition()`, `list_compositions()`, `_spawn_xy_for_castle()`, `create_initial_units_with_roster()`: ALL deleted
- `Game.unit_composition` DB column: dropped via Alembic
- `test_arena_10x10_2v2` map added to `game/maps/` as a showcase test map
- Mainline battles use `map_id + teams` instead of `ally_composition/enemy_composition`
- `size` in map JSON accepts both `int` (legacy, 15) and `{width, height}` (new)
- `size` as `{width:int, height:int}` replaces the old `size: int` for new maps (custom maps already use this format)
- `/games/presets` endpoint drops `unit_compositions` field
- Web UI `#new-unit-composition` dropdown removed from create-game form
- Color→player mapping: seat 0=red, 1=blue, 2=green, 3=yellow

---

### Task 1: Add `_resolve_size()` helper + startup validation for `_load_map_presets()`

**Files:**
- Modify: `game/app/game_logic.py` before line 1000 (near `_load_map_presets`)
- Test: `game/tests/test_data_driven_initial_units.py` (create)

**Interfaces:**
- Consumes: `MAP_PRESETS` dict, `MAP_SIZE` constant from config
- Produces: `_resolve_size(size) -> dict{width, height}` — accepts `int|dict`
- Produces: `_load_map_presets()` raises `ValueError` for missing/empty/broken `initial_units`

- [ ] **Step 1.1: Write test for `_resolve_size`**

```python
"""test_data_driven_initial_units.py — startup."""
import pytest
from app.game_logic import _resolve_size


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
```

- [ ] **Step 1.2: Run to verify it fails**

Run: `pytest game/tests/test_data_driven_initial_units.py::TestResolveSize -v`
Expected: FAIL with `_resolve_size` not defined.

- [ ] **Step 1.3: Write `_resolve_size` helper**

Add near top of `game_logic.py` (below imports, before `_load_map_presets`):

```python
def _resolve_size(size: Union[int, Dict[str, int]]) -> Dict[str, int]:
    """Normalize `size` from JSON to {width, height} dict.

    Legacy preset: ``size=15`` → ``{width: 15, height: 15}``
    New preset: ``size={width:10, height:7}`` → pass-through.
    """
    if isinstance(size, int):
        return {"width": size, "height": size}
    if isinstance(size, dict) and "width" in size and "height" in size:
        return dict(size)
    raise TypeError(
        f"size must be int or dict with width/height, got {type(size).__name__}"
    )
```

- [ ] **Step 1.4: Run to verify passes**

Run: `pytest game/tests/test_data_driven_initial_units.py::TestResolveSize -v`
Expected: PASS

- [ ] **Step 1.5: Write tests for `_load_map_presets` validation**

```python
class TestLoadMapPresets:
    def test_missing_initial_units_raises(self):
        """A map JSON without initial_units must be rejected at load."""
        from app.game_logic import _load_map_presets
        # We'll test indirectly: try loading a minimal bad dict.
        # _load_map_presets reads from disk, so we write a temp test JSON.

    # These tests depend on having a real file — do them in Task 6 (full test map).
```

(Full tests depend on the JSON existing; we'll add more in Task 6.)

- [ ] **Step 1.6: Commit**

```bash
git add game/app/game_logic.py game/tests/test_data_driven_initial_units.py
git commit -m "feat(p2.6): add _resolve_size helper"
```

---

### Task 2: Add startup validation in `_load_map_presets()`

**Files:**
- Modify: `game/app/game_logic.py` inside `_load_map_presets()` (around line 1016-1050)
- Test: same test file

**Interfaces:**
- Consumes: `initial_units` array from each map JSON dict
- Produces: `ValueError` on malformed maps; `MAP_PRESETS` unchanged for valid maps

- [ ] **Step 2.1: Write `_load_map_presets` validation block**

Find the existing `_load_map_presets()` function. After `data = json.load(...)` and before `MAP_PRESETS[data["id"]] = data`, insert:

```python
# P2.6 — validate initial_units is present and well-formed
initial_units = data.get("initial_units")
if not initial_units:
    raise ValueError(
        f"Map preset {data.get('id')!r} missing required 'initial_units'"
    )
size = _resolve_size(data["size"])
seen_positions = set()
for u in initial_units:
    for k in ("x", "y", "type", "color"):
        if k not in u:
            raise ValueError(
                f"Map {data.get('id')!r}: initial_unit missing field {k!r}: {u}"
            )
    x, y = int(u["x"]), int(u["y"])
    if not (0 <= x < size["width"] and 0 <= y < size["height"]):
        raise ValueError(
            f"Map {data.get('id')!r}: initial_unit ({x},{y}) out of bounds"
        )
    if (x, y) in seen_positions:
        raise ValueError(
            f"Map {data.get('id')!r}: duplicate initial_unit at ({x},{y})"
        )
    seen_positions.add((x, y))
```

Note: impassable-terrain and unknown-type checks require imports of `IMPASSABLE_TERRAINS` and `UNIT_CLASS_IDS` — verify those are available at module scope. If the existing _load_map_presets doesn't import them, add:

```python
from app.config import IMPASSABLE_TERRAINS
from app.classes.units import get_class_ids as _get_unit_class_ids
# or whatever the actual import path for UNIT_CLASS_IDS is
```

- [ ] **Step 2.2: Run existing tests to verify nothing broken**

Run: `pytest game/tests/ -q --timeout=120`
Expected: All 496 existing tests pass.

- [ ] **Step 2.3: Commit**

```bash
git add game/app/game_logic.py
git commit -m "feat(p2.6): add initial_units startup validation in _load_map_presets"
```

---

### Task 3: Make `generate_map_preset()` return `MapPresetResult`

**Files:**
- Modify: `game/app/game_logic.py` around `generate_map_preset()` (line ~1056)
- Test: same test file

**Interfaces:**
- Consumes: `MAP_PRESETS[preset_id]`, `_layout_to_tiles()`, `_resolve_size()`
- Produces: `MapPresetResult(tiles, initial_units)` dataclass

- [ ] **Step 3.1: Add `MapPresetResult` dataclass**

```python
from dataclasses import dataclass, field
from typing import Any, Dict, List

@dataclass
class MapPresetResult:
    tiles: List[List[Tile]]
    initial_units: List[Dict[str, Any]]
```

Place this right before `def generate_map_preset(`.

- [ ] **Step 3.2: Rewrite `generate_map_preset`**

```python
def generate_map_preset(
    preset_id: str,
    seed: int,
    num_castles: int,
) -> MapPresetResult:
    """Return (tiles, initial_units) from the map preset JSON."""
    data = MAP_PRESETS[preset_id]
    return MapPresetResult(
        tiles=_layout_to_tiles(data["layout"], _resolve_size(data["size"])),
        initial_units=list(data["initial_units"]),
    )
```

- [ ] **Step 3.3: Write test for return type**

```python
class TestGenerateMapPreset:
    def test_returns_map_preset_result(self):
        """generate_map_preset returns a MapPresetResult with tiles + initial_units."""
        from app.game_logic import generate_map_preset, MapPresetResult
        # Needs a real preset that has initial_units — we'll flesh this out
        # after the test_arena_10x10_2v2.json exists (Task 7).
```

- [ ] **Step 3.4: Update callers of `generate_map_preset`**

Search for all calls to `generate_map_preset(`. They now receive `MapPresetResult` instead of raw tiles.

In `game/app/routes/game.py` (line ~176-181):
```python
result = generate_map_preset(preset_id, seed, num_castles)
tiles = result.tiles
```

In `game/app/game_logic.py` (if any internal calls — `_create_initial_units_with_roster` will be deleted, so check).

- [ ] **Step 3.5: Run tests to verify callers still work**

Run: `pytest game/tests/ -q`
Expected: Failures due to `MapPresetResult.tiles` being accessed as a list directly (not yet at call sites).

- [ ] **Step 3.6: Fix callers that access `tiles` directly**

Update every call site that expects `tiles = generate_map_preset(...)`:

```python
result = generate_map_preset(...)
tiles = result.tiles
```

- [ ] **Step 3.7: Commit**

```bash
git add game/app/game_logic.py game/app/routes/game.py
git commit -m "feat(p2.6): generate_map_preset returns MapPresetResult(tiles, initial_units)"
```

---

### Task 4: Rewrite `_start_battle_internal()` spawn loop to use `initial_units`

**Files:**
- Modify: `game/app/routes/game.py` around line 196-247
- Test: `game/tests/test_data_driven_initial_units.py`

**Interfaces:**
- Consumes: `generate_map_preset()` → `MapPresetResult`
- Consumes: `players` list with `.seat`, `.color`, `.id`
- Produces: `units: List[Unit]` with unit_type, name, level, x, y from initial_units

- [ ] **Step 4.1: Remove old spawn block and replace**

In `_start_battle_internal()`, locate the section that:
1. Calls `generate_map_preset()` at ~line 176
2. Gets `default_roster` at ~line 199
3. Loops per-player and per-unit-type at ~lines 222-244

Replace with:

```python
# ============================================================
# P2.6: Spawn units from map's initial_units
# ============================================================
color_to_player = {p.color: p for p in players if p.color}
result = generate_map_preset(preset_id, seed, num_castles)
tiles = result.tiles

for u in result.initial_units:
    target = color_to_player.get(u["color"])
    if target is None:
        raise ValueError(
            f"initial_unit color {u['color']!r} has no matching player"
        )
    level = int(u.get("level", 1))
    unit_type = u["type"]
    units.append(Unit(
        player_id=target.id,
        unit_type=unit_type,
        name=_unit_name(unit_type, sum(1 for _u in units
                                        if getattr(_u, 'player_id', None) == target.id)),
        level=level,
        x=int(u["x"]), y=int(u["y"]),
        has_acted=False, has_moved=False,
        hp=MAX_HP_BY_TYPE.get(unit_type, 100),
        max_hp=MAX_HP_BY_TYPE.get(unit_type, 100),
    ))
```

- [ ] **Step 4.2: Remove dead parameters**

Delete the `rosters_by_seat`, `roster` parameters from `_start_battle_internal()` signature and all their dispatch code (lines ~124-143, 199-210, 205-210, 222-223, 230). Update docstring.

- [ ] **Step 4.3: Update all callers of `_start_battle_internal`**

Check `routes/mainline.py` and any other files that call `_start_battle_internal(rosters_by_seat=...)` — remove the argument.

- [ ] **Step 4.4: Remove imports for deleted symbols**

Find and remove in `game/app/routes/game.py`:
```python
# DELETE these imports:
from app.game_logic import _spawn_xy_for_castle, _unit_name
from app.game_logic import get_roster_for_composition  # if present
from app.classes.units import list_compositions  # if present
```

Keep `_unit_name` if it's still used elsewhere in the file (it likely is — only remove if unused after the refactor).

- [ ] **Step 4.5: Run tests**

Run: `pytest game/tests/ -q`
Expected: Failures due to `rosters_by_seat` parameter removal — fix remaining callers.

- [ ] **Step 4.6: Commit**

```bash
git add game/app/routes/game.py
git commit -m "feat(p2.6): _start_battle_internal spawns from initial_units JSON"
```

---

### Task 5: Delete all removed symbols and re-exports

**Files:**
- Modify: `game/app/classes/units/__init__.py` — delete lines 99-148
- Modify: `game/app/game_logic.py` — delete lines 283-289, 1163-1216, all re-exports in `__all__`
- Modify: `game/app/game_logic.py` — remove `default_roster` import/alias from existing imports

- [ ] **Step 5.1: Delete from `classes/units/__init__.py`**

Delete:
- `default_roster()` function (lines 99-101)
- Unit-composition presets section header (lines 111-112)
- `_COMPOSITIONS` dict (lines 114-135)
- `get_roster_for_composition()` (lines 138-141)
- `list_compositions()` (lines 144-148)

Also remove `default_roster` from the re-export line at the top of the file (line ~5 if present).

- [ ] **Step 5.2: Delete from `game_logic.py`**

Delete:
- `_spawn_xy_for_castle()` function (lines 283-289)
- The entire `# Unit-composition presets` section header + re-export wrappers (lines 1163-1172)
- `create_initial_units_with_roster()` (lines 1175-1216)
- Remove `default_roster`, `get_roster_for_composition`, `list_compositions` from any `__all__` lists

- [ ] **Step 5.3: Run tests to find remaining references**

Run: `pytest game/tests/ -q`
Expected: ImportError / NameError for each caller still referencing these symbols.

- [ ] **Step 5.4: Fix all remaining callers**

Expected sites (from audit):
- `game/conftest.py`: remove `get_roster_for_composition` import, remove `unit_composition="classic"` from Game fixture
- `game/tests/test_p24_gameplay_bugfixes.py`: remove unused `get_roster_for_composition` import
- Any other test imports

- [ ] **Step 5.5: Run tests again**

Run: `pytest game/tests/ -q`
Expected: All tests pass (some may need fixture updates from Task 13).

- [ ] **Step 5.6: Commit**

```bash
git add game/app/classes/units/__init__.py game/app/game_logic.py game/app/routes/game.py game/conftest.py game/tests/test_p24_gameplay_bugfixes.py
git commit -m "refactor(p2.6): delete _COMPOSITIONS, default_roster, _spawn_xy_for_castle, and all re-exports"
```

---

### Task 6: Remove `Game.unit_composition` from schema + API + DB

**Files:**
- Modify: `game/app/models.py` — line 60
- Modify: `game/app/schemas.py` — lines 34, 114
- Modify: `game/app/routes/game.py` — lines 247, 370, 861
- Create: `game/app/migrations/versions/2026_07_07_drop_unit_composition.py`
- Test: `game/tests/test_integration_smoke.py` — lines 68, 70

- [ ] **Step 6.1: Drop from Pydantic models**

In `game/app/schemas.py`:
```python
# DELETE from CreateGameRequest (line ~34):
# unit_composition: Optional[str] = None

# DELETE from PresetsResponse (line ~114):
# unit_compositions: List[PresetInfo]
```

- [ ] **Step 6.2: Drop from route handlers**

In `game/app/routes/game.py`:
```python
# DELETE line ~247: unit_composition=None,
# DELETE line ~370: unit_composition=body.unit_composition,
# DELETE from `/games/presets` response (line ~861):
#   unit_compositions=[
#       PresetInfo(id=c["id"], name=f'兵种预设: {c["name"]}')
#       for c in list_compositions()
#   ],
```

- [ ] **Step 6.3: Drop DB column**

In `game/app/models.py`, find `unit_composition: Mapped[...]` line and remove it.

Create migration:

```python
# game/app/migrations/versions/2026_07_07_drop_unit_composition.py
"""drop game.unit_composition column

Revision ID: 2026_07_07_drop_ucomp
Revises: <parent_revision>
Create Date: 2026-07-07
"""
from alembic import op
import sqlalchemy as sa

revision = "2026_07_07_drop_ucomp"
down_revision = None  # Set to actual parent revision!

def upgrade():
    op.drop_column("games", "unit_composition")

def downgrade():
    op.add_column("games", sa.Column("unit_composition", sa.String(32), nullable=True))
```

> Check `alembic.ini` or the migrations directory to determine the actual parent revision id.

- [ ] **Step 6.4: Update smoke test**

In `game/tests/test_integration_smoke.py`:
```python
# DELETE or update:
# assert "maps" in body and "unit_compositions" in body  →  assert "maps" in body
# assert len(body["unit_compositions"]) > 0  →  DELETE
```

- [ ] **Step 6.5: Run tests + verify API shape**

```bash
pytest game/tests/ -q
curl -s http://localhost:8000/games/presets | python -c "import sys,json; d=json.load(sys.stdin); assert 'maps' in d; assert 'unit_compositions' not in d; print('OK')"
```

Expected: pytest passes, curl assertion says OK, no `unit_compositions` field in response.

- [ ] **Step 6.6: Commit**

```bash
git add game/app/models.py game/app/schemas.py game/app/routes/game.py game/app/migrations/versions/2026_07_07_drop_unit_composition.py game/tests/test_integration_smoke.py
git commit -m "refactor(p2.6): drop Game.unit_composition column + API fields"
```

---

### Task 7: Write the test map JSON file

**Files:**
- Create: `game/maps/test_arena_10x10_2v2.json`

- [ ] **Step 7.1: Write the full test map JSON**

Create `game/maps/test_arena_10x10_2v2.json`:

```json
{
  "id": "test_arena_10x10_2v2",
  "name": "测试竞技场 10×10 2v2",
  "description": "10×10 紧凑 2v2 测试图，覆盖移动/攻击/占领/招募/路径 cost/团队 全流程，含 4 vault",
  "biome": "grass",
  "size": { "width": 10, "height": 10 },
  "layout": [
    "H..RRRR..H",
    "...R..R...",
    "vRR......Rv",
    "$R.bFFb.R$",
    ".RR....RR.",
    "..R.bb.R..",
    ".RR....RR.",
    "$R.bFFb.R$",
    "vRR......Rv",
    "H..RRRR..H"
  ],
  "recommended_players": 4,
  "team_mode": "2v2",
  "notes": "测试用图 — 所有系统流程均可在此图跑通",
  "initial_units": [
    {"x": 1, "y": 0, "type": "swordsman", "color": "red", "level": 1},
    {"x": 2, "y": 0, "type": "swordsman", "color": "red", "level": 1},
    {"x": 1, "y": 1, "type": "archer",    "color": "red", "level": 1},
    {"x": 3, "y": 1, "type": "knight",    "color": "red", "level": 1},
    {"x": 0, "y": 1, "type": "healer",    "color": "red", "level": 1},
    {"x": 1, "y": 9, "type": "swordsman", "color": "blue", "level": 1},
    {"x": 2, "y": 9, "type": "swordsman", "color": "blue", "level": 1},
    {"x": 1, "y": 8, "type": "archer",    "color": "blue", "level": 1},
    {"x": 3, "y": 8, "type": "knight",    "color": "blue", "level": 1},
    {"x": 0, "y": 8, "type": "healer",    "color": "blue", "level": 1},
    {"x": 8, "y": 0, "type": "swordsman", "color": "green", "level": 1},
    {"x": 7, "y": 0, "type": "swordsman", "color": "green", "level": 1},
    {"x": 8, "y": 1, "type": "archer",    "color": "green", "level": 1},
    {"x": 6, "y": 1, "type": "knight",    "color": "green", "level": 1},
    {"x": 9, "y": 1, "type": "healer",    "color": "green", "level": 1},
    {"x": 8, "y": 9, "type": "swordsman", "color": "yellow", "level": 1},
    {"x": 7, "y": 9, "type": "swordsman", "color": "yellow", "level": 1},
    {"x": 8, "y": 8, "type": "archer",    "color": "yellow", "level": 1},
    {"x": 6, "y": 8, "type": "knight",    "color": "yellow", "level": 1},
    {"x": 9, "y": 8, "type": "healer",    "color": "yellow", "level": 1}
  ]
}
```

- [ ] **Step 7.2: Load-check the JSON is valid**

```bash
cd game && python -c "import json; f=open('maps/test_arena_10x10_2v2.json'); d=json.load(f); print(f'OK: {len(d[\"initial_units\"])} units, layout {len(d[\"layout\"])}x{len(d[\"layout\"][0])}')"
```

Expected: `OK: 20 units, layout 10x10`

- [ ] **Step 7.3: Commit**

```bash
git add game/maps/test_arena_10x10_2v2.json
git commit -m "feat(p2.6): add test_arena_10x10_2v2 map (10x10, 4 vaults, full roster)"
```

---

### Task 8: Write unit tests for loader validation + map loading

**Files:**
- Modify: `game/tests/test_data_driven_initial_units.py`

- [ ] **Step 8.1: Add loader validation tests**

```python
"""Test for data-driven initial_units — loader validation + spawn materialization."""

import pytest

# Use a test map that we know exists
TEST_MAP_ID = "test_arena_10x10_2v2"


class TestMapPresetValidation:

    def test_generate_map_preset_returns_map_preset_result(self):
        from app.game_logic import generate_map_preset, MapPresetResult
        result = generate_map_preset(TEST_MAP_ID, seed=1, num_castles=4)
        assert isinstance(result, MapPresetResult)
        assert hasattr(result, "tiles")
        assert hasattr(result, "initial_units")
        assert len(result.initial_units) == 20

    def test_initial_units_have_all_required_fields(self):
        from app.game_logic import MAP_PRESETS
        data = MAP_PRESETS[TEST_MAP_ID]
        for u in data["initial_units"]:
            for k in ("x", "y", "type", "color"):
                assert k in u, f"missing {k} in {u}"

    def test_initial_units_all_unique_coords(self):
        from app.game_logic import MAP_PRESETS
        data = MAP_PRESETS[TEST_MAP_ID]
        seen = set()
        for u in data["initial_units"]:
            coord = (int(u["x"]), int(u["y"]))
            assert coord not in seen, f"duplicate coord {coord}"
            seen.add(coord)

    def test_initial_units_all_in_bounds(self):
        from app.game_logic import MAP_PRESETS
        data = MAP_PRESETS[TEST_MAP_ID]
        w, h = data["size"]["width"], data["size"]["height"]
        for u in data["initial_units"]:
            x, y = int(u["x"]), int(u["y"])
            assert 0 <= x < w and 0 <= y < h, f"({x},{y}) out of bounds"

    def test_initial_units_all_types_valid(self):
        from app.game_logic import MAP_PRESETS
        from app.config import UNIT_CLASS_IDS
        data = MAP_PRESETS[TEST_MAP_ID]
        for u in data["initial_units"]:
            assert u["type"] in UNIT_CLASS_IDS, f"unknown type {u['type']}"
```

- [ ] **Step 8.2: Add e2e spawn test (fastapi testclient)**

```python
class TestSpawnMaterialization:

    def test_create_game_with_test_arena_expects_4p_20units(self, client, db_session):
        # This test needs the app's TestClient and a DB session fixture.
        from app.routes.game import router
        import json

        resp = client.post("/games", json={
            "name": "test arena spawn",
            "map_preset": TEST_MAP_ID,
            "max_players": 4,
        })
        assert resp.status_code == 201, resp.text
        data = resp.json()
        game_id = data["id"]

        # Check the units are created
        resp_units = client.get(f"/games/{game_id}/units")
        assert resp_units.status_code == 200
        units = resp_units.json()
        assert len(units) == 20, f"expected 20 units, got {len(units)}"
```

- [ ] **Step 8.3: Run the tests**

```bash
pytest game/tests/test_data_driven_initial_units.py -v
```

Expected: All tests PASS.

- [ ] **Step 8.4: Commit**

```bash
git add game/tests/test_data_driven_initial_units.py
git commit -m "test(p2.6): add data-driven initial_units unit tests"
```

---

### Task 9: Write migration script for 40 legacy maps

**Files:**
- Create: `tools/gen_initial_units_for_legacy_maps.py`

- [ ] **Step 9.1: Write the migration script**

```python
#!/usr/bin/env python3
"""
Generate initial_units for legacy map presets.

For each map JSON under game/maps/ that lacks initial_units, generate
a default set based on the map's castle positions and a classic roster.

Usage:
    python tools/gen_initial_units_for_legacy_maps.py [--dry-run] [--write]
"""
import argparse
import json
from pathlib import Path

MAPS_DIR = Path(__file__).resolve().parent.parent / "game" / "maps"

# Default classic roster per player
DEFAULT_ROSTER = {"swordsman": 2, "archer": 1, "knight": 1, "healer": 1}

# Castle positions for 15x15 maps (legacy)
CASTLE_POSITIONS = {
    2: [(2, 2), (12, 12)],
    3: [(2, 2), (12, 2), (7, 12)],
    4: [(2, 2), (12, 2), (2, 12), (12, 12)],
}

# Color order by seat
COLORS = ["red", "blue", "green", "yellow"]

# Spawn offsets (matching the old _spawn_xy_for_castle logic)
SPAWN_OFFSETS = [(0, 1), (1, 0), (1, 1), (2, 0), (0, 2)]


def _generate_units(castle_xy, color, roster):
    """Generate initial_units for one player at castle_xy."""
    units = []
    unit_index = 0
    for unit_type, count in roster.items():
        for _ in range(count):
            dx, dy = SPAWN_OFFSETS[unit_index % len(SPAWN_OFFSETS)]
            x = castle_xy[0] + dx
            y = castle_xy[1] + dy
            units.append({
                "x": x, "y": y,
                "type": unit_type,
                "color": color,
                "level": 1,
            })
            unit_index += 1
    return units


def main():
    parser = argparse.ArgumentParser(description="Generate initial_units for legacy maps")
    parser.add_argument("--dry-run", action="store_true", help="Print only, don't write")
    parser.add_argument("--write", action="store_true", help="Write changes to files")
    args = parser.parse_args()

    for json_path in sorted(MAPS_DIR.glob("*.json")):
        data = json.loads(json_path.read_text())
        if "initial_units" in data:
            continue  # already migrated

        num_players = data.get("recommended_players", 2)
        castles = CASTLE_POSITIONS.get(num_players, CASTLE_POSITIONS[2])
        initial_units = []
        for seat, castle in enumerate(castles):
            color = COLORS[seat] if seat < len(COLORS) else COLORS[-1]
            initial_units.extend(_generate_units(castle, color, DEFAULT_ROSTER))

        data["initial_units"] = initial_units
        data["notes"] = data.get("notes", "") + " [initial_units auto-generated]"
        data["notes"] = data["notes"].strip()

        if args.dry_run:
            print(f"[DRY RUN] {json_path.name}: {len(initial_units)} units added")
        elif args.write:
            json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            print(f"[WRITTEN] {json_path.name}: {len(initial_units)} units")
        else:
            print(f"[SKIP] {json_path.name}: {len(initial_units)} units would be added (use --write)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 9.2: Run dry-run to verify**

```bash
cd "D:/PyCharm Community Edition 2024.3.3/PycharmProjects/BattleBlitz"
python tools/gen_initial_units_for_legacy_maps.py --dry-run
```

Expected: Lists each legacy map with unit count. Check output: no map with >5 hex tiles outside castle bounds.

- [ ] **Step 9.3: Commit**

```bash
git add tools/gen_initial_units_for_legacy_maps.py
git commit -m "tool(p2.6): add gen_initial_units_for_legacy_maps migration script"
```

---

### Task 10: Bulk-migrate 40 built-in maps

**Files:**
- Modify: ~40 built-in map JSONs in `game/maps/*.json` (each gains `initial_units` + `notes`)

- [ ] **Step 10.1: Run migration script with --write**

```bash
cd "D:/PyCharm Community Edition 2024.3.3/PycharmProjects/BattleBlitz"
python tools/gen_initial_units_for_legacy_maps.py --write
```

Expected: ~40 files written, each with `initial_units` array.

- [ ] **Step 10.2: Manual spot-check 3-4 maps**

Check `open_plains.json`, `three_way_25.json`, `fortress_35.json`, `grass_outer_15_3p.json`:
- Verify units aren't placed on castle_wall tiles
- Verify units are near their HQ (within 2-3 tiles)
- Verify no units overlap with each other

- [ ] **Step 10.3: Run full test suite**

```bash
cd game && python -m pytest -q
```

Expected: All 496+ existing tests + new tests pass. If any fail, fix the map's initial_units (likely a wall-collision issue).

- [ ] **Step 10.4: Commit**

```bash
git add game/maps/
git commit -m "feat(p2.6): migrate 40 built-in maps to initial_units"
```

---

### Task 11: Rewrite mainline battle specs + schema

**Files:**
- Modify: `game/app/mainline/schemas.py` — `BattleSpec` rewrite
- Modify: `game/mainlines/chapter_01_steel_rebellion.json` — replace compositions
- Modify: `game/app/routes/mainline.py` — materialization update
- Create: `tools/gen_initial_units_for_mainlines.py` (optional, for future chapters)

- [ ] **Step 11.1: Rewrite BattleSpec schema**

```python
class BattleSpec(BaseModel):
    id: str
    map_id: str
    teams: Dict[str, List[str]] = Field(default_factory=dict)
    win_condition: str = "rout"
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _check_team_colors(self):
        from app.game_logic import MAP_PRESETS  # lazy import to avoid circular
        map_data = MAP_PRESETS.get(self.map_id)
        if not map_data:
            raise ValueError(f"map_id {self.map_id!r} not found")
        all_colors = {c for team in self.teams.values() for c in team}
        map_colors = {u["color"] for u in map_data.get("initial_units", [])}
        missing = all_colors - map_colors
        if missing:
            raise ValueError(f"team colors {missing} have no units in map {self.map_id!r}")
        return self
```

Remove `ally_composition`, `enemy_composition` fields and their validators.

- [ ] **Step 11.2: Rewrite chapter JSON**

Replace `chapter_01_steel_rebellion.json`:

```json
{
  "id": "chapter_01_steel_rebellion",
  "name": "钢铁叛乱",
  "description": "在铁锈平原上，新政府军遭遇了第一次机械化叛军的正面冲击。",
  "battles": [
    {
      "id": "b1",
      "map_id": "three_way_25",
      "teams": { "ally": ["red"], "enemy": ["blue", "green"] },
      "win_condition": "rout"
    },
    {
      "id": "b2",
      "map_id": "river_crossing",
      "teams": { "ally": ["red"], "enemy": ["blue"] },
      "win_condition": "seize"
    }
  ]
}
```

(The map's `initial_units` defines what units each color has — `teams` only says who's on which side.)

- [ ] **Step 11.3: Update `routes/mainline.py` materialization**

In `_spawn_battle_for_index()`, remove the `rosters_by_seat=` construction. The map's `initial_units` drives the spawn. Just call:

```python
result = generate_map_preset(battle.map_id, seed, 2)  # 2 = number of teams
tiles = result.tiles
# Units are created by _start_battle_internal from result.initial_units
```

- [ ] **Step 11.4: Run mainline tests**

```bash
pytest game/tests/test_mainline_loader.py game/tests/test_mainline_api.py -v
```

Expected: Tests fail due to `ally_composition`/`enemy_composition` references.

- [ ] **Step 11.5: Fix test assertions**

In `test_mainline_loader.py`, replace all `assert b1.ally_composition == {...}` with:
```python
# BattleSpec no longer has ally_composition — check teams instead
assert b1.teams.get("ally") == ["red"]
```

In `test_mainline_api.py`, remove comments referencing composition.

- [ ] **Step 11.6: Run mainline tests again**

```bash
pytest game/tests/test_mainline_loader.py game/tests/test_mainline_api.py -v
```

Expected: All PASS.

- [ ] **Step 11.7: Commit**

```bash
git add game/app/mainline/schemas.py game/app/routes/mainline.py game/mainlines/chapter_01_steel_rebellion.json game/tests/test_mainline_loader.py game/tests/test_mainline_api.py
git commit -m "refactor(p2.6): mainline battles use map_id+teams instead of ally/enemy_composition"
```

---

### Task 12: Web UI — Remove unit composition dropdown

**Files:**
- Modify: `game/app/web/index.html` — line ~122-125
- Modify: `game/app/web/app.js` — lines 72, 342, 356, 417, 4328, 4329

- [ ] **Step 12.1: Remove HTML elements**

In `index.html`, find and remove:
```html
<select id="new-unit-composition"> ... </select>
<p id="new-units-desc"> ... </p>
```

- [ ] **Step 12.2: Remove JS references**

In `app.js`:
```javascript
// Remove line ~72: state shape change (remove unit_compositions from comment)
// Remove line ~342: const unitComp = document.getElementById("new-unit-composition").value;
// Remove line ~356: if (unitComp) body.unit_composition = unitComp;
// Remove lines ~417 (the unitsSel populate branch in populatePresetSelects)
// Remove lines ~4328-4329 (change handler + description update)
```

- [ ] **Step 12.3: Manual smoke test**

```bash
# Start server
cd game && uvicorn app.main:app --reload --port 8000 --lifespan off
# In browser: open http://localhost:8000
# 1. Verify no "兵种预设" dropdown in create-game form
# 2. Create a game with test_arena_10x10_2v2
# 3. Add 4 AI players
# 4. Start game → verify 20 units visible on board
```

- [ ] **Step 12.4: Commit**

```bash
git add game/app/web/index.html game/app/web/app.js
git commit -m "feat(p2.6): remove unit composition dropdown from Web UI"
```

---

### Task 13: Update test fixtures

**Files:**
- Modify: `game/conftest.py` — fixture Game() drops `unit_composition`
- Modify: `game/tests/test_integration_smoke.py` — already done in Task 6

- [ ] **Step 13.1: Update conftest Game fixture**

Find the `Game(...)` fixture call (likely `create_game` in conftest.py:121). Remove `unit_composition="classic"`.

- [ ] **Step 13.2: Update remaining test references**

Search for remaining uses of `unit_composition` in all test files:

```bash
cd game && grep -rn "unit_composition" tests/ --include="*.py"
```

Should return 0 results after all cleanup. Fix any remaining match.

- [ ] **Step 13.3: Run full test suite**

```bash
cd game && python -m pytest -q
```

Expected: 100% pass.

- [ ] **Step 13.4: Commit**

```bash
git add game/conftest.py
git commit -m "test(p2.6): update fixtures — drop unit_composition references"
```

---

### Task 14: Update documentation

**Files:**
- Modify: `README.md` — API table
- Modify: `docs/架构.md` — schema table + examples
- Modify: `docs/路线.md` — example payload
- Modify: `docs/superpowers/specs/2026-06-30-victory-conditions-spec.md` — CreateGameRequest shape
- Modify: `docs/superpowers/specs/2026-06-30-magic-attack-warlock-spec.md` — default_roster() references

- [ ] **Step 14.1: Update README.md**

Find the API table row for `POST /games`. Remove `unit_composition` from the body fields.

- [ ] **Step 14.2: Update 架构.md**

Find line ~239 with `unit_composition | VARCHAR(32)` — remove that row.
Find lines ~760/762 with `"composition": "classic"` — remove.

- [ ] **Step 14.3: Update 路线.md**

Find line ~169 with `"unit_composition": "classic"` — remove from payload example.

- [ ] **Step 14.4: Update victory-conditions-spec.md**

Find line ~242 with `unit_composition: Optional[str]` — remove from CreateGameRequest example.

- [ ] **Step 14.5: Update magic-attack-warlock-spec.md**

Find lines ~101, 102, 206, 207, 386, 416 referencing `default_roster()` — replace each with a note:
> `This spec was written before the data-driven initial_units refactor (2026-07-07).`
> `Units now come from the map JSON's initial_units array instead of default_roster().`
> `The Warlock's starting lineup is controlled by the chapter_01 map's initial_units.`

- [ ] **Step 14.6: Commit**

```bash
git add README.md docs/架构.md docs/路线.md docs/superpowers/specs/2026-06-30-victory-conditions-spec.md docs/superpowers/specs/2026-06-30-magic-attack-warlock-spec.md
git commit -m "docs(p2.6): update docs — remove unit_composition, default_roster references"
```

---

### Task 15: Final e2e verification

- [ ] **Step 15.1: Full pytest run**

```bash
cd game && python -m pytest -q
```

Expected: 526+ passed, 0 failed, 0 errors.

- [ ] **Step 15.2: API smoke tests**

```bash
# Start server in background
cd game && uvicorn app.main:app --port 8001 --lifespan off &
sleep 3

# No unit_compositions field
curl -s http://localhost:8001/games/presets | jq '.unit_compositions'
# → null

# Test map present
curl -s http://localhost:8001/games/presets | jq '.maps[] | select(.id=="test_arena_10x10_2v2") | .initial_units | length'
# → 20

# Create game with test map
curl -s -X POST http://localhost:8001/games \
  -H 'Content-Type: application/json' \
  -d '{"name":"e2e","map_preset":"test_arena_10x10_2v2","max_players":4}' | jq '.id'
# → numeric game_id

# Kill background server
kill %1 2>/dev/null
```

- [ ] **Step 15.3: Run AI battle demo**

```bash
cd game && python -m tools.ai_battle_demo --map test_arena_10x10_2v2 --players 4 --max-turns 30
```

Expected: 4 AI players, game runs to completion with a winner. No errors in logs.

- [ ] **Step 15.4: Visual verification (Playwright / screenshot)**

Start server: `cd game && uvicorn app.main:app --port 8000`
Open `http://localhost:8000`
1. Create game → select "测试竞技场 10×10 2v2"
2. Add 4 humans/AI (4 AI clicks)
3. Start game
4. Verify: 20 units visible, each player has 5 units around their HQ
5. Move one unit → verify road cost is 0.5
6. Click a central barracks → verify recruit dialog shows

- [ ] **Step 15.5: Run 40-map bulk validation using ai_battle_demo**

```bash
# Quick smoke: can every map at least load without error?
cd game && python -c "
from app.game_logic import MAP_PRESETS, generate_map_preset
for mid in MAP_PRESETS:
    try:
        r = generate_map_preset(mid, seed=1, num_castles=4)
        assert len(r.initial_units) > 0
        print(f'OK: {mid} ({len(r.initial_units)} units)')
    except Exception as e:
        print(f'FAIL: {mid}: {e}')
"
```

Expected: All 41 maps load cleanly with initial_units.

---

## Verification Summary

| Check | Command | Expected |
|---|---|---|
| Unit tests | `cd game && python -m pytest -q` | 526+ pass, 0 fail |
| Presets API | `curl -s /games/presets \| jq '.unit_compositions'` | `null` |
| Test map | `curl -s /games/presets \| jq '.maps[] \| select(.id=="test_arena_10x10_2v2") \| .initial_units \| length'` | `20` |
| AI demo | `python -m tools.ai_battle_demo --map test_arena_10x10_2v2 --players 4` | Exits cleanly with winner |
| Map load | Python one-liner iterating MAP_PRESETS | All 41 OK |
| Web UI | Browser manual check | No composition dropdown, units visible |
