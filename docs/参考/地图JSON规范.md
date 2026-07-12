# 🗺️ Map Authoring Guide — P2.6 Data-Driven Initial Units

**Status**: Stable since 2026-07-07 (`feat/p2.6-data-driven-initial-units`)
**Audience**: Map designers, content creators, anyone editing `game/maps/*.json`

---

## 1. TL;DR

Every map under `game/maps/` is a self-contained JSON file. The map
declares its **terrain layout** (a char grid), its **starting unit
placements** (`initial_units` array), and a few metadata fields.
At game start, the engine reads the JSON, validates it, and uses
`initial_units` to spawn units directly — no separate "roster" or
"composition" table is involved.

If a map is dropped into `game/maps/` **without** an `initial_units`
array, the loader auto-generates a default roster using the same
`_classic_initial_units()` helper that powers the procedural "classic"
preset, scoped to the map's `recommended_players` and its actual
dimensions. (See §7 *Legacy Fallback* below.)

---

## 2. Required JSON Fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | ✅ | Unique across `game/maps/`. Used as `map_preset` in `POST /games`. Snake-case recommended. |
| `name` | string | ✅ | Display name (Chinese or English). |
| `description` | string | recommended | Short blurb shown in the Web UI dropdown. |
| `biome` | string | recommended | One of: `grass`, `desert`, `snow`, `castle`. Defaults to `grass`. |
| `size` | int **or** `{width, height}` | ✅ | Both forms accepted; legacy maps use `int` (square), new maps may use the dict for non-square layouts. |
| `layout` | string[] | ✅ | One string per row; each char is one tile. See §3. |
| `initial_units` | array | ✅ (or auto-filled) | See §5. |
| `recommended_players` | int | recommended | 2 / 3 / 4. Drives Web UI cascading filter. Defaults to 4. |
| `team_mode` | string | optional | `2v2` for teamed play, `ffa` (or absent) for free-for-all. |
| `notes` | string | optional | Designer notes shown beneath the dropdown. |

### Minimal example

```json
{
  "id": "my_first_map",
  "name": "我的第一张地图",
  "description": "10×10 入门图，2 人对角",
  "biome": "grass",
  "size": 10,
  "layout": [
    "C........C",
    "..........",
    "..........",
    "..........",
    "..........",
    "..........",
    "..........",
    "..........",
    "..........",
    "C........C"
  ],
  "recommended_players": 2,
  "initial_units": [
    {"x": 0, "y": 1, "type": "swordsman", "color": "red", "level": 1},
    {"x": 1, "y": 0, "type": "archer",    "color": "red", "level": 1},
    {"x": 9, "y": 8, "type": "swordsman", "color": "blue", "level": 1},
    {"x": 8, "y": 9, "type": "archer",    "color": "blue", "level": 1}
  ]
}
```

---

## 3. Layout Char Map (`_layout_to_tiles` reference)

Each row of `layout` is a string whose **length must equal `size.width`**
and the **array length must equal `size.height`**. The loader does
not pad or truncate — mismatched dimensions raise a `ValueError` at
startup.

### Outer terrains (stored in `Tile.terrain`)

| Char | `Tile.terrain` | Notes |
|---|---|---|
| `P` | `plain` | Default. Cheapest movement. |
| `F` | `forest` | Blocks LOS, slows movement. |
| `M` | `mountain` | Impassable. |
| `S` | `snow_peak` | Snow biome's silver mountain (P2.4). |
| `R` | `river` | Crossable but expensive; often borders. |
| `C` | `castle` | HQ tile. Each player gets one. |
| `v` | `village` | **Income source** — 50 gold/turn to its owner. |
| `b` | `barracks` | **Income source (100g/turn) + recruitment location**. |
| `r` | `road` | Cheap movement. |
| `g` | `gate` | Castle boundary. |
| **`$`** | `castle_vault` | **Income source** — 150 gold/turn to its owner. |

> **`$` was previously silently dropped to `plain` before the 2026-07-07
> loader fix (`38a7cda`).** If your map uses `$`, make sure you're on
> a commit from then or later — otherwise the 4 vaults produce 0 gold.

### Castle sub-features (stored in `Tile.subtype`, terrain becomes `"castle"`)

These are only valid on tiles already marked `castle`. They are
specified **inside the layout row** using one of two forms:

| Form | Example | Effect |
|---|---|---|
| Single lowercase letter | `f`, `w`, `t`, `d`, `s` | Sets `subtype` directly. |
| `>` prefix + word | `>vault`, `>floor` | Multi-char codes for unambiguous sub-features. |

Subtype names:

| Code | Subtype | Notes |
|---|---|---|
| `f` / `>floor` | `castle_floor` | Walkable inside the castle. |
| `w` / `>wall` | `castle_wall` | Blocks movement. |
| `t` / `>throne` | `castle_throne` | Future Seize-mode objective. |
| `d` / `>door` | `castle_door` | Castle entry point. |
| `s` / `>stairs` | `castle_stairs` | Vertical movement. |
| `>vault` | `castle_vault` | Same as `$` in outer-notation. |

> **Note**: `v` is overloaded — it maps to `TERRAIN_VILLAGE` by
> default; to express a castle vault sub-feature inside a `C` tile,
> use `>vault` instead.

---

## 4. Income Rules (`BUILDING_INCOME`)

Defined in `app/config.py`:

| Terrain | Gold / turn | Per-player cap |
|---|---|---|
| `village` | 50 | none |
| `barracks` | 100 | none |
| `castle_vault` | 150 | none |

Income fires at the **start** of every player's turn. A player who
owns tiles of these terrains gets `gold += Σ (rate × count)`.

> **2026-07-07 fix**: `start_game` now grants this initial income to
> **every** non-spectator player, not just seat 0. Previously only
> seat 0 received gold at game start; other seats had to wait for
> their first turn cycle. Also fixed a missing `session.flush()`
> that hid the ownership changes from the income query.
> (See commit `26dd8d4`.)

---

## 5. `initial_units` schema

Each entry spawns one Unit at game start.

| Field | Type | Required | Notes |
|---|---|---|---|
| `x` | int | ✅ | 0-indexed tile column, `0 ≤ x < size.width`. |
| `y` | int | ✅ | 0-indexed tile row, `0 ≤ y < size.height`. |
| `type` | string | ✅ | Must be in `app.classes.units.type_ids()`. E.g. `swordsman`, `archer`, `knight`, `healer`, `warlock`. Unknown types are silently skipped at spawn. |
| `color` | string | ✅ | One of: `red`, `blue`, `green`, `yellow`. Used to match the entry to the player of the same color. Entries whose color has no matching player are skipped. |
| `level` | int | optional | Defaults to 1. Currently cosmetic — no XP curve uses it. |

### Validation (raises `ValueError` at startup)

- Every `(x, y)` is inside the map's `size`.
- No two entries share the same `(x, y)` (no overstacking).
- Every entry has all four required fields.
- All `type` values are recognized unit types (test asserts via
  `app.classes.units.type_ids()`).

### Spawn-time mapping

The spawn loop in `game/app/routes/game.py:179-230`:

1. Builds `color_to_player = {p.color: p for p in real_players if p.color}`.
2. For each entry, looks up the player with matching color.
3. Looks up the unit's `UnitClassProfile` for HP/ATK/DEF/MATK/MDEF/mov.
4. Creates a `Unit` row at the entry's `(x, y)`.
5. Tiles get `occupied_unit_id` set; castle tiles get owner assigned
   by Manhattan proximity to the player's castle.

### Unit counts per the showcase map

`test_arena_10x10_2v2.json` has 20 units = 4 colors × 5 units.
Each color gets 2 swordsman + 1 archer + 1 knight + 1 healer.

---

## 6. Recommended Player Count & Team Mode

`recommended_players` (2/3/4) drives the Web UI's cascading filter:
when the user picks "4 人地图" in the create-game form, the map
dropdown shows only maps with `recommended_players == 4`. Defaults
to 4 if the field is absent.

`team_mode` is informational and is consumed by `BattleSpec` validation
in `game/app/mainline/schemas.py`:

| Value | Effect |
|---|---|
| `"2v2"` | The 4 player colors map to teams: `red+blue` vs `green+yellow`. The `BattleSpec.teams` validator cross-references team colors against the map's `initial_units` colors and refuses any chapter that names a color the map has no units for. |
| `"ffa"` or absent | Free-for-all. No team validation. |

---

## 7. Legacy Fallback (Backwards Compatibility)

If a map JSON does **not** declare `initial_units`, the loader
auto-fills a default roster using `_classic_initial_units(num_castles)`
sized to the map's actual dimensions and `recommended_players`.

**Auto-fill rules** (commit `91dc021`):

- Per castle, spawn 5 units: 2 swordsman, 1 archer, 1 knight, 1 healer.
- Castle positions are computed from the map's `size` (inset by
  `width/4`, `height/4`) so the fallback works for 10×10, 20×20,
  45×45, etc. — **not** just 15×15 like the legacy hardcoded table.
- For 4-player maps, colors are assigned in order: `red`, `blue`,
  `green`, `yellow`.
- For 5+ player maps (only via `capacity`), the 5th+ seat is clamped
  to the same color as the 4th seat (`yellow`).

The exact same `_classic_initial_units()` helper is also used by the
procedural "classic" preset (`generate_map_preset("classic")`), so
the fallback path and the runtime "classic" path produce **identical**
unit placements — guaranteed by `test_legacy_map_initial_units_fallback.py`.

---

## 8. Adding a New Map — Step-by-step

1. Drop your JSON file into `game/maps/<your_map_id>.json`.
2. Restart the server (`uvicorn` reloads automatically if enabled).
   The loader will validate it at import time and raise `ValueError`
   on the first failure.
3. Run the full test suite:
   ```bash
   cd game && python -m pytest -q
   ```
   The P2.6 map integrity tests (`test_data_driven_initial_units.py`
   + `test_legacy_map_initial_units_fallback.py` +
   `test_layout_loader_dollar.py`) will catch missing fields,
   out-of-bounds units, duplicate coordinates, and unknown unit types.
4. Optional: run the spawn-correctness harness:
   ```bash
   cd game && python ../tools/verify_map_spawn.py --map <your_map_id> --players 4 --duration 30
   ```
5. Optional: run the headless-browser end-to-end test to confirm
   the map shows up in the Web UI:
   ```bash
   cd tools && npm install && node playwright_e2e.js
   ```

---

## 9. Common Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `ValueError: Map preset 'X' missing required 'initial_units'` | Pre-P2.6 map JSON without `initial_units` | Either add the field, OR rely on the auto-fallback (just delete the explicit `initial_units` line — see §7). |
| 4 vault tiles (`$`) showing as `plain`, no income | Loader bug, fixed in `38a7d7a`. | Pull latest; verify your commit includes the fix. |
| Map shows up in API but not in Web UI dropdown | `recommended_players` doesn't match the player's selection | Set `recommended_players` correctly, or set it to 4 as a fallback. |
| Game crashes with `out of bounds` at startup | An `initial_unit` `(x, y)` is outside `size`. | All coords must satisfy `0 ≤ x < width` and `0 ≤ y < height`. |
| Units overlap (`duplicate initial_unit`) | Two entries share the same `(x, y)`. | Each tile can host at most one starting unit. |
| Color mismatch — units don't appear | `initial_units` references a color with no matching player. | Player colors are `red`/`blue`/`green`/`yellow`; verify the map only references colors that match `recommended_players` (e.g. a 2-player map uses only `red` + `blue`). |

---

## 10. Reference Implementations

- **Data-driven showcase**: `game/maps/test_arena_10x10_2v2.json`
  — 4 castles, 20 units, 4 vault tiles, 2v2 team mode. Used by the
  showcase integration test.
- **Economic showcase**: `game/maps/economic_expansion_30.json`
  — 4 villages + 2 barracks + 1 vault per player quadrant. Designed
  to exercise the claim/gold/recruit flow.
- **Procedural fallback**: the inline `classic` entry in
  `game/app/game_logic.py:1077-1086` — used when no map is specified
  (`map_preset=null`).