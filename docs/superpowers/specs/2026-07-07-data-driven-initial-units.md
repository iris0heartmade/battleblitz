# Spec: Data-Driven Initial Units — Map-Authored Spawn

**Date:** 2026-07-07
**Status:** Draft (awaiting user review)
**Scope:** Engine + 41 map JSONs + mainline JSONs + Web UI + DB migration

## Context

The current BattleBlitz engine hard-codes two things that should be data:

1. **Default unit composition.** `_COMPOSITIONS` dict in `game/app/classes/units/__init__.py:114-135` lists 4 fixed `Dict[str, int]` rosters (classic / aggressive / defensive / ranged). `Game.unit_composition` selects one. There is no way to give specific units to specific players in specific positions on a specific map — every player gets the same roster, dropped at the same relative offsets to their HQ.

2. **Spawn positions.** `_spawn_xy_for_castle(castle_xy, unit_index)` in `game/app/game_logic.py:283-289` lays units at 5 fixed SE-of-castle offsets `[(0,1), (1,0), (1,1), (2,0), (0,2)]`. A roster of >5 units collides on the same 5 tiles. Position is purely a function of castle + roster index — never of map layout.

A custom-map editor already exists (`game/maps/custom/mytestbattle_c8d5aa.json` plus `game/app/routes/editor.py`) that supports `initial_units: [{x, y, type, color, level}]` — but this path is only active for `preset_id` starting with `custom:`. Built-in presets silently ignore it.

**Goal:** every map (built-in, custom, mainline battle) is the single source of truth for which units spawn, where, and at what level. The engine reads `initial_units` from the preset JSON. There is no global default roster and no global spawn-offset table.

The Advance Wars series has done this for two decades: a map file declares `startingUnits: [{owner, country, unitType, x, y, co}]` and the engine materializes them verbatim. We adopt the same philosophy.

## Decisions

| Decision | Choice |
|---|---|
| Schema | Single `initial_units: [{x, y, type, color, level}]` array per map |
| Old composition presets (`_COMPOSITIONS`) | **Deleted** — not deprecated, not aliased, gone |
| `Game.unit_composition` DB column | **Dropped** — Alembic migration |
| `CreateGameRequest.unit_composition` API field | **Removed** |
| `PresetsResponse.unit_compositions` API field | **Removed** |
| Web UI `#new-unit-composition` dropdown | **Removed** |
| Legacy 41 built-in map JSONs | **All migrated** — must contain `initial_units` |
| Mainline `ally_composition` / `enemy_composition` dicts | **Replaced** by `initial_units` on the map |
| Per-seat override hook (`rosters_by_seat`) | **Removed** — no longer reachable |
| `_spawn_xy_for_castle()` | **Deleted** |
| `create_initial_units_with_roster()` | **Deleted** (was already on the dead-code list) |
| Validation timing | **Startup** — `_load_map_presets` raises on the first broken preset |

## Schema

### Map JSON (built-in)

```json
{
  "id": "test_arena_6x7_2v2",
  "name": "测试竞技场 6×7 2v2",
  "description": "6×7 极限紧凑 2v2 测试图，覆盖移动/攻击/占领/招募/路径 cost/团队 全流程",
  "biome": "grass",
  "size": { "width": 6, "height": 7 },
  "layout": [
    "H....H",
    ".RRRR.",
    "v.bF.v",
    ".RRRR.",
    "v.b$.v",
    ".RRRR.",
    "H....H"
  ],
  "recommended_players": 4,
  "team_mode": "2v2",
  "notes": "测试用",
  "initial_units": [
    // ===== P1 (red) — 左上 HQ at (0,0) =====
    {"x": 1, "y": 0, "type": "swordsman", "color": "red", "level": 1},
    {"x": 0, "y": 1, "type": "swordsman", "color": "red", "level": 1},
    {"x": 2, "y": 1, "type": "archer",    "color": "red", "level": 1},
    {"x": 1, "y": 1, "type": "knight",    "color": "red", "level": 1},
    {"x": 0, "y": 2, "type": "healer",    "color": "red", "level": 1},

    // ===== P2 (blue) — 左下 HQ at (0,6) =====
    {"x": 1, "y": 6, "type": "swordsman", "color": "blue", "level": 1},
    {"x": 0, "y": 5, "type": "swordsman", "color": "blue", "level": 1},
    {"x": 2, "y": 5, "type": "archer",    "color": "blue", "level": 1},
    {"x": 1, "y": 5, "type": "knight",    "color": "blue", "level": 1},
    {"x": 0, "y": 4, "type": "healer",    "color": "blue", "level": 1},

    // ===== P3 (green) — 右上 HQ at (5,0) =====
    {"x": 4, "y": 0, "type": "swordsman", "color": "green", "level": 1},
    {"x": 5, "y": 1, "type": "swordsman", "color": "green", "level": 1},
    {"x": 3, "y": 1, "type": "archer",    "color": "green", "level": 1},
    {"x": 4, "y": 1, "type": "knight",    "color": "green", "level": 1},
    {"x": 5, "y": 2, "type": "healer",    "color": "green", "level": 1},

    // ===== P4 (yellow) — 右下 HQ at (5,6) =====
    {"x": 4, "y": 6, "type": "swordsman", "color": "yellow", "level": 1},
    {"x": 5, "y": 5, "type": "swordsman", "color": "yellow", "level": 1},
    {"x": 3, "y": 5, "type": "archer",    "color": "yellow", "level": 1},
    {"x": 4, "y": 5, "type": "knight",    "color": "yellow", "level": 1},
    {"x": 5, "y": 4, "type": "healer",    "color": "yellow", "level": 1}
  ]
}
```

**`size` is now an object `{width, height}` for built-in maps too**, matching what custom maps already use. This allows non-square test maps like 6×7 without breaking the layout string parser.

### Mainline battle spec

```json
{
  "id": "b1",
  "map_id": "three_way_25",
  "teams": { "ally": ["red"], "enemy": ["blue", "green"] },
  "win_condition": "rout"
}
```

The map's `initial_units` is the source of truth; `teams` just declares which colors are allies.

## Engine Changes

### `game/app/game_logic.py`

**`_load_map_presets()` — startup validation**
```python
def _load_map_presets():
    for json_path in maps_dir.glob("*.json"):
        data = json.loads(json_path.read_text())
        initial_units = data.get("initial_units")
        if not initial_units:
            raise ValueError(f"Map preset {data.get('id')!r} missing 'initial_units'")
        size = _resolve_size(data["size"])
        terrain = {coord: t for coord, t in _layout_to_terrain_map(data["layout"], size)}
        seen_positions = set()
        for u in initial_units:
            for k in ("x", "y", "type", "color"):
                if k not in u:
                    raise ValueError(f"initial_unit missing field {k!r}: {u}")
            x, y = int(u["x"]), int(u["y"])
            if not (0 <= x < size["width"] and 0 <= y < size["height"]):
                raise ValueError(f"initial_unit ({x},{y}) out of bounds")
            if (x, y) in seen_positions:
                raise ValueError(f"duplicate initial_unit at ({x},{y})")
            seen_positions.add((x, y))
            if terrain.get((x, y)) in IMPASSABLE_TERRAINS:
                raise ValueError(f"initial_unit at ({x},{y}) on impassable {terrain[(x,y)]}")
            if u["type"] not in UNIT_CLASS_IDS:
                raise ValueError(f"initial_unit type {u['type']!r} unknown")
            level = int(u.get("level", 1))
            if not 1 <= level <= 3:
                raise ValueError(f"initial_unit level {level} not in 1..3")
        MAP_PRESETS[data["id"]] = data
```

**`generate_map_preset()` — return both tiles and units**
```python
@dataclass
class MapPresetResult:
    tiles: List[List[Tile]]
    initial_units: List[Dict[str, Any]]

def generate_map_preset(preset_id, seed, num_castles) -> MapPresetResult:
    data = MAP_PRESETS[preset_id]
    return MapPresetResult(
        tiles=_layout_to_tiles(data["layout"], _resolve_size(data["size"])),
        initial_units=list(data["initial_units"]),
    )
```

**Delete:** `_spawn_xy_for_castle()`, `create_initial_units_with_roster()`, the re-export wrapper block at lines 1163-1172, the `__all__` entries for those names.

### `game/app/routes/game.py`

**`_start_battle_internal()` — new spawn loop**
```python
result = generate_map_preset(preset_id, seed, num_castles)
tiles = result.tiles
color_to_player = {p.color: p for p in players if p.color}
units = []
for u in result.initial_units:
    target = color_to_player.get(u["color"])
    if target is None:
        raise ValueError(
            f"initial_unit color {u['color']!r} has no matching player"
        )
    units.append(Unit(
        player_id=target.id,
        unit_type=u["type"],
        name=_unit_name(u["type"], len(units_for_player.get(target.id, []))),
        level=int(u.get("level", 1)),
        x=int(u["x"]), y=int(u["y"]),
        has_acted=False, has_moved=False, hp=MAX_HP_BY_TYPE[u["type"]],
    ))
```

**Delete:**
- `rosters_by_seat` parameter and per-seat dispatch (lines 124, 141-143, 205-210)
- `_spawn_xy_for_castle` import (line 223)
- `default_roster` / `get_roster_for_composition` imports (line 39)
- `unit_compositions=[...]` from `/games/presets` response (line 861)
- `unit_composition=body.unit_composition` from create-game (line 370)
- The hardcoded `unit_composition=None` residue (line 247)

### `game/app/routes/mainline.py`

**`_spawn_battle_for_index()` — no more roster dicts**
```python
result = generate_map_preset(battle.map_id, seed, num_castles)
# result.initial_units already has color attribution
# team assignment comes from battle.teams
```

**Delete:**
- The `rosters_by_seat=` construction (line 273-275)
- The `ally_units = sum(...)` / `enemy_units = sum(...)` log computation (lines 291-292)

### `game/app/mainline/schemas.py`

**`BattleSpec` rewrite**
```python
class BattleSpec(BaseModel):
    id: str
    map_id: str
    teams: Dict[str, List[str]]  # {"ally": ["red"], "enemy": ["blue"]}
    win_condition: str = "rout"
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _check_team_colors(self):
        map_data = MAP_PRESETS.get(self.map_id)
        if not map_data:
            raise ValueError(f"map_id {self.map_id!r} not found")
        all_colors = {c for team in self.teams.values() for c in team}
        map_colors = {u["color"] for u in map_data.get("initial_units", [])}
        missing = all_colors - map_colors
        if missing:
            raise ValueError(
                f"team colors {missing} have no units in map {self.map_id!r}"
            )
        return self
```

`ally_composition` and `enemy_composition` fields are gone.

## Persistence Changes

### `game/app/models.py`

```python
# REMOVE this line:
unit_composition: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
```

### `game/app/schemas.py`

```python
# REMOVE from CreateGameRequest:
unit_composition: Optional[str] = None

# REMOVE from PresetsResponse:
unit_compositions: List[PresetInfo]
```

### `game/app/migrations/versions/2026_07_07_drop_unit_composition.py`

```python
def upgrade():
    op.drop_column("games", "unit_composition")

def downgrade():
    op.add_column("games", sa.Column("unit_composition", sa.String(32), nullable=True))
```

## Web UI Changes

### `game/app/web/index.html`

- Remove the `<select id="new-unit-composition">` block (line 122)
- Remove the `<p id="new-units-desc">` block (line 125)

### `game/app/web/app.js`

- Remove `state.presets.unit_compositions` reference (line 72)
- Remove `if (unitComp) body.unit_composition = unitComp;` from createGame() (line 356)
- Remove the `unitsSel` populate branch in `populatePresetSelects()` (line 417)
- Remove the change handler at line 4328
- Remove the description update at line 4329

## The Test Map: `test_arena_6x7_2v2`

6 columns wide × 7 rows tall (42 tiles total), 2v2 team mode (red+blue vs green+yellow). Deliberately minimal — every tile earns its place.

```
. = plain    R = road (cost 0.5)    F = forest (cost 2)
b = barracks    v = village        $ = vault (gold income)
H = HQ (only the center tile, no walls/gates)

        x:0   1   2   3   4   5
y:0    [H]   .   .   .   .  [H]   ← red ───┐  ┌─── green
y:1     .   R   R   R   R   .            team: red+blue | green+yellow
y:2     v   b   F   b   v   .            blue──┘  └────yellow
y:3     .   R   R   R   R   .
y:4     v   b   $   b   v   .   ← 中间一横：village + barracks + vault + barracks + village
y:5     .   R   R   R   R   .
y:6    [H]   .   .   .   .  [H]
```

(注意：上面 v / b / F / $ 是建筑位，本身不算 unit。实际 playable 区域是 . R H 三种 terrain)

**Coverage matrix:**
| System | How it's exercised |
|---|---|
| Movement | Road network R connecting every HQ to every central building |
| Attack | HQs are 6 tiles apart diagonally — sword/archer/knight all reach |
| Claim village | 4 v at (0,2), (5,2), (0,4), (5,4) — edges contested |
| Claim vault | 4 $ at... wait, this layout only has 1 $. **Tradeoff accepted.** |
| Recruit | 2 b at (1,2) and (3,2) (top row) + (1,4) and (3,4) (bottom row) — 4 total |
| Forest defense | F at (2,2) — single tile 2-MP cost test |
| HQ seize | 4 HQs in corners — walking onto enemy HQ wins |
| 2v2 team | Pair (red,blue) vs (green,yellow) — friendly fire off |
| Full roster | Each player has 2 swordsman + 1 archer + 1 knight + 1 healer |
| Path cost | R + plain + F all in one map → cost comparison visible |

**20 initial units total**, `recommended_players=4`, `team_mode=2v2`.

**Tradeoff note:** at 6×7 the **4 vault** requirement (user-requested exception) is reduced to **1 vault** at the map center. We added 2 extra barracks to make recruitment more interesting. If the user requires all 4 vaults, the map must grow to 8×8 minimum.

**Healer-on-village quirk:** red's healer starts at (0,2) which is a `v` tile. The healer is not yet "claiming" the village — claim only happens when a unit moves onto an empty building tile as a deliberate `claim` action. Starting on top of a building does not auto-claim. The village is unowned at turn 1 and stays unowned until someone does a `claim` action on it.

## Migration Plan

### Step 1 — Engine

1. Add `_resolve_size()` helper (accepts both `int` and `{width, height}`)
2. Update `_load_map_presets()` with validation
3. Replace `generate_map_preset()` to return `MapPresetResult`
4. Rewrite `_start_battle_internal()` spawn loop
5. Delete all removed symbols
6. Delete `Game.unit_composition` column + Alembic migration

### Step 2 — Test Map First

7. Author `test_arena_6x7_2v2.json` with full `initial_units`
8. Add 12 unit tests in `test_data_driven_initial_units.py`
9. Run `pytest -q` against just this map — must pass clean

### Step 3 — Bulk Migrate Built-Ins

10. Run `tools/gen_initial_units_for_legacy_maps.py` to auto-generate `initial_units` for the other 40 maps based on `_CASTLE_LAYOUTS` + classic roster
11. Manual review each generated map's `initial_units` for layout sanity (no overlap with walls, sensible placement near HQ)
12. Run full pytest

### Step 4 — Mainline

13. Rewrite `game/mainlines/chapter_01_steel_rebellion.json` battles — replace `ally_composition`/`enemy_composition` with map references
14. Update `BattleSpec` schema and validator
15. Update `routes/mainline.py` materialization
16. Update `test_mainline_loader.py` and `test_mainline_api.py`

### Step 5 — Web UI

17. Remove `#new-unit-composition` from `index.html`
18. Remove all JS references in `app.js`
19. Manual smoke: load `/presets`, verify response shape, create a game, verify units spawn at correct positions

### Step 6 — Documentation

20. Update `README.md`, `docs/架构.md`, `docs/路线.md`
21. Update or supersede `2026-06-30-magic-attack-warlock-spec.md` references to `default_roster()`

## Files Touched

### Production code
- `game/app/game_logic.py` (engine refactor + symbol deletion)
- `game/app/models.py` (drop column)
- `game/app/schemas.py` (drop request/response fields)
- `game/app/routes/game.py` (new spawn loop + symbol deletion)
- `game/app/routes/mainline.py` (new spawn flow + symbol deletion)
- `game/app/mainline/schemas.py` (BattleSpec rewrite)
- `game/app/web/index.html` (remove dropdown)
- `game/app/web/app.js` (remove JS handlers)
- `game/app/migrations/versions/2026_07_07_drop_unit_composition.py` (new)

### Map data
- `game/maps/test_arena_6x7_2v2.json` (new)
- `game/maps/grass_outer_15_2p.json` + 39 others (each gains `initial_units`)
- `game/maps/custom/mytestbattle_c8d5aa.json` (no change — already has field)
- `game/mainlines/chapter_01_steel_rebellion.json` (replace per-battle compositions)

### Tools
- `tools/gen_initial_units_for_legacy_maps.py` (new)
- `tools/gen_initial_units_for_mainlines.py` (new)

### Tests
- `game/tests/test_data_driven_initial_units.py` (new — 12 tests)
- `game/tests/test_integration_smoke.py` (drop `unit_compositions` assertions)
- `game/tests/test_mainline_loader.py` (drop composition assertions)
- `game/tests/test_mainline_api.py` (drop comments)
- `game/tests/test_p24_gameplay_bugfixes.py` (drop unused import)
- `game/conftest.py` (drop `unit_composition` field + `get_roster_for_composition` import)

### Docs
- `README.md` (drop `unit_composition` from API table)
- `docs/架构.md` (drop column + examples)
- `docs/路线.md` (update payload example)
- `docs/superpowers/specs/2026-06-30-victory-conditions-spec.md` (update CreateGameRequest shape)
- `docs/superpowers/specs/2026-06-30-magic-attack-warlock-spec.md` (drop `default_roster()` references)

## Verification

### Automated

```bash
cd "D:/PyCharm Community Edition 2024.3.3/PycharmProjects/BattleBlitz/game"
python -m pytest -q
```
Expected: 496 existing + ~30 new ≈ 526 passed, 0 failed.

### Procedural regeneration

```bash
cd "D:/PyCharm Community Edition 2024.3.3/PycharmProjects/BattleBlitz"
python tools/gen_initial_units_for_legacy_maps.py --dry-run
```
Expected: 40 maps listed, each showing proposed `initial_units` for review.

### Manual smoke

```bash
# Start the server
cd "D:/PyCharm Community Edition 2024.3.3/PycharmProjects/BattleBlitz/game"
uvicorn app.main:app --reload --port 8000

# 1. Verify presets endpoint no longer mentions unit_compositions
curl -s http://localhost:8000/games/presets | jq '.unit_compositions'   # → null
curl -s http://localhost:8000/games/presets | jq '.maps[] | select(.id=="test_arena_6x7_2v2") | .initial_units | length'  # → 20

# 2. Verify create-game with old field silently ignored
curl -X POST http://localhost:8000/games -H 'Content-Type: application/json' \
  -d '{"name":"smoke","map_preset":"test_arena_6x7_2v2","unit_composition":"classic","max_players":4}'
# → 201 Created, 4 players + 20 units in DB

# 3. Run 4-AI battle demo
python tools/ai_battle_demo.py --map test_arena_6x7_2v2 --players 4 --max-turns 30
# → exits cleanly, all 4 AIs make moves, game ends with a winner
```

### Playwright e2e

1. Open `http://localhost:8000`
2. Click **Create Game** → select `test_arena_6x7_2v2`
3. Add 4 players (4 "Add AI" clicks) → all 4 AIs auto-pick personalities
4. Start game → verify 20 units appear at the 20 specified positions
5. Run 5 turns → verify all 4 systems (move/attack/claim/recruit) are exercised at least once
6. Take screenshot → visually confirm map matches the ASCII layout

## Risks

| Risk | Mitigation |
|---|---|
| Bulk-migrating 40 maps may produce overlapping units on tight maps | Migration script runs `--dry-run` first; generated output is reviewed before write |
| `size` schema change (int → object) breaks existing custom maps | Migration handles both: `_resolve_size()` accepts int (legacy) and `{w, h}` (new) |
| Player color assignment is by AI join order, not deterministic | Document convention: seat 0=red, 1=blue, 2=green, 3=yellow; AI auto-assign follows seat |
| Mainline JSON change breaks chapter progression saves | Acceptable — pre-refactor saves are orphaned, document in release notes |
| Removing `_COMPOSITIONS` breaks anyone hardcoding the dict name | Comprehensive grep audit completed; no remaining external callers |
| The warlock spec mandates `default_roster()` unchanged | That spec is superseded by this one; update its body to reference `initial_units` instead |

## Rollback

Single-commit revert of the merge commit re-creates `_COMPOSITIONS`, `unit_composition` column, and the legacy spawn path. Map JSONs that were updated remain updated (they still have valid `initial_units`), and the engine would just ignore the field under the legacy code — this means rollback is **forward-compatible at the data layer**.

If a per-map rollback is needed (e.g., one specific map produces broken spawns), `git checkout HEAD~1 -- game/maps/<id>.json` reverts just that map's `initial_units` while keeping the new engine. That map would then fail to load (no `initial_units`) — intentional, fix forward.