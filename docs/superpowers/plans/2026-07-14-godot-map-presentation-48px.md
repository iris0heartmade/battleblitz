# Godot 48x48 Map Presentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Godot client's map presentation layer into a 48x48, multi-layer tactics board that reads existing map JSONs, renders ground/structure/decor separately, places static units, and keeps camera/highlight behavior cleanly extensible.

**Architecture:** Keep the current `godot-client` project and JSON map contract, but split responsibilities into focused units: `MapMetrics` for coordinate math, `MapTheme` for terrain-to-asset mapping, `Board`/`BoardCamera` for scene orchestration, and dedicated layers for ground, structure, decor, highlights, and units. Refactor the existing prototype instead of replacing the whole client so headless smoke tests and current assets remain usable throughout the migration.

**Tech Stack:** Godot 4.7, GDScript, `TileMapLayer`, headless Godot smoke tests, existing BattleBlitz map JSON files and synced tile PNG assets.

---

## File Structure

### New files

- `godot-client/scripts/core/map_metrics.gd`
  Owns the authoritative `48x48` tile size, cell/world conversion helpers, board pixel bounds, and board center calculations.
- `godot-client/scripts/core/map_theme.gd`
  Owns terrain/subtype routing to the correct layer and source lookup keys, so `MapLoader` no longer hard-codes rendering semantics.
- `godot-client/scripts/board/board_camera.gd`
  Owns camera centering, zoom fitting, and map-bound clamping.
- `godot-client/scripts/board/unit_node.gd`
  Minimal static unit presenter for one unit sprite/fallback marker.

### Modified files

- `godot-client/scripts/core/tile_set_builder.gd`
  Continue building the runtime `TileSet`, but consume `MapMetrics.TILE_SIZE` instead of carrying rendering size itself.
- `godot-client/scripts/core/map_loader.gd`
  Decode map JSON into ground/structure/decor writes plus unit placement data using `MapTheme`.
- `godot-client/scripts/board/board.gd`
  Shrink into a board coordinator that wires scene children, owns the loaded `MapMetrics`, and delegates camera/unit/highlight work.
- `godot-client/scripts/board/highlights.gd`
  Stop reading `TileSetBuilder` directly; accept tile metrics from `Board`.
- `godot-client/scripts/main.gd`
  Keep the demo entry point but adapt status text and click handling to the new board contract.
- `godot-client/scenes/board.tscn`
  Rename/add nodes to `GroundLayer`, `StructureLayer`, `DecorLayer`, `HighlightLayer`, `UnitLayer`, `EffectsLayer`, `BoardCamera`.
- `godot-client/tools/smoke_test.gd`
  Extend the headless smoke test to assert 48x48 metrics, multi-layer writes, and static unit placement.
- `godot-client/README.md`
  Refresh status text so the documented map prototype matches the new 48x48 layer model.

## Task 1: Add Shared 48x48 Board Metrics

**Files:**
- Create: `godot-client/scripts/core/map_metrics.gd`
- Modify: `godot-client/scripts/board/board.gd`
- Modify: `godot-client/scripts/board/highlights.gd`
- Test: `godot-client/tools/smoke_test.gd`

- [ ] **Step 1: Write the failing smoke-test assertions for shared metrics**

```gdscript
# In godot-client/tools/smoke_test.gd inside _ready(), after loading a board:
_assert_eq("MapMetrics tile size x", MapMetrics.TILE_SIZE.x, 48,
	"tile width must stay locked to the 48px spec")
_assert_eq("MapMetrics tile size y", MapMetrics.TILE_SIZE.y, 48,
	"tile height must stay locked to the 48px spec")
```

- [ ] **Step 2: Run the smoke test to verify it fails before MapMetrics exists**

```bash
"D:/PyCharm Community Edition 2024.3.3/PycharmProjects/Godot_v4.7-stable_win64/Godot_v4.7-stable_win64.exe" --headless --path godot-client res://tools/smoke_test.tscn
```

Expected: `FAIL` with a parser/runtime error mentioning `MapMetrics` not found.

- [ ] **Step 3: Create `map_metrics.gd` and move the authoritative tile-size math there**

```gdscript
extends RefCounted
class_name MapMetrics

const TILE_SIZE := Vector2i(48, 48)

var board_size: Vector2i

func _init(size: Vector2i) -> void:
	board_size = size

func cell_to_local(cell: Vector2i) -> Vector2:
	return Vector2(cell * TILE_SIZE) + Vector2(TILE_SIZE) * 0.5

func local_to_cell(pos: Vector2) -> Vector2i:
	return Vector2i(floori(pos.x / TILE_SIZE.x), floori(pos.y / TILE_SIZE.y))

func board_pixel_size() -> Vector2:
	return Vector2(board_size * TILE_SIZE)

func board_center() -> Vector2:
	return board_pixel_size() * 0.5

func bounds_rect() -> Rect2:
	return Rect2(Vector2.ZERO, board_pixel_size())
```

- [ ] **Step 4: Update `board.gd` and `highlights.gd` to use shared metrics**

```gdscript
# In godot-client/scripts/board/board.gd
var metrics: MapMetrics = null

func load_map(map_json: Dictionary) -> Dictionary:
	var result := MapLoader.apply_to_board(self, map_json)
	map_size = Vector2i(int(result["width"]), int(result["height"]))
	metrics = MapMetrics.new(map_size)
	highlights.reset(metrics)
	map_loaded.emit(map_size.x, map_size.y, map_biome)
	return result

func tile_to_viewport(tile: Vector2i) -> Vector2:
	if terrain_layer == null:
		return Vector2.ZERO
	return terrain_layer.to_global(metrics.cell_to_local(tile))
```

```gdscript
# In godot-client/scripts/board/highlights.gd
var _metrics: MapMetrics = null

func reset(metrics: MapMetrics) -> void:
	_metrics = metrics
	_board_size = metrics.board_size
	_tile_size = MapMetrics.TILE_SIZE
	_pool.clear()
	for mode in _COLORS.keys():
		_ensure_mode_node(mode)
```

- [ ] **Step 5: Run the smoke test again**

```bash
"D:/PyCharm Community Edition 2024.3.3/PycharmProjects/Godot_v4.7-stable_win64/Godot_v4.7-stable_win64.exe" --headless --path godot-client res://tools/smoke_test.tscn
```

Expected: `MapMetrics` assertions pass; later tasks may still fail for unimplemented layer/camera changes.

- [ ] **Step 6: Commit the metrics refactor**

```bash
git add godot-client/scripts/core/map_metrics.gd godot-client/scripts/board/board.gd godot-client/scripts/board/highlights.gd godot-client/tools/smoke_test.gd
git commit -m "refactor(godot-client): centralize 48px board metrics"
```

## Task 2: Add Theme-Based Multi-Layer Map Loading

**Files:**
- Create: `godot-client/scripts/core/map_theme.gd`
- Modify: `godot-client/scripts/core/map_loader.gd`
- Modify: `godot-client/scripts/core/tile_set_builder.gd`
- Modify: `godot-client/scripts/board/board.gd`
- Test: `godot-client/tools/smoke_test.gd`

- [ ] **Step 1: Add failing assertions for ground/structure layer separation**

```gdscript
# In godot-client/tools/smoke_test.gd after loading balanced_2p_15:
var hq := Vector2i(1, 7)
_assert_gte("ground layer source at HQ", board_check.ground_layer.get_cell_source_id(hq), 0,
	"ground layer should always receive a terrain source")
_assert_gte("structure layer source at HQ", board_check.structure_layer.get_cell_source_id(hq), 0,
	"structure layer should receive castle/building overlays")
```

- [ ] **Step 2: Run the smoke test to verify the new layer assertions fail**

```bash
"D:/PyCharm Community Edition 2024.3.3/PycharmProjects/Godot_v4.7-stable_win64/Godot_v4.7-stable_win64.exe" --headless --path godot-client res://tools/smoke_test.tscn
```

Expected: `FAIL` because `ground_layer` / `structure_layer` members or writes do not exist yet.

- [ ] **Step 3: Create `map_theme.gd` to own layer routing**

```gdscript
extends RefCounted
class_name MapTheme

enum LayerKind { GROUND, STRUCTURE, DECOR }

static func layer_for_cell(terrain: String, subtype: String) -> int:
	if subtype != "":
		return LayerKind.STRUCTURE
	if terrain in ["village", "barracks", "gate"]:
		return LayerKind.STRUCTURE
	return LayerKind.GROUND

static func source_lookup_key(terrain: String, subtype: String) -> String:
	if subtype != "":
		return subtype
	return terrain

static func uses_biome(terrain: String) -> bool:
	return terrain in Config.BIOME_AWARE_TERRAINS
```

- [ ] **Step 4: Refactor the loader and tileset builder around `MapTheme` and `MapMetrics`**

```gdscript
# In godot-client/scripts/core/map_loader.gd
var ground_layer: TileMapLayer = board.ground_layer
var structure_layer: TileMapLayer = board.structure_layer
var decor_layer: TileMapLayer = board.decor_layer
ground_layer.clear()
structure_layer.clear()
decor_layer.clear()

var theme_key := MapTheme.source_lookup_key(terrain, subtype)
_apply_cell_to_layer(ground_layer, x, y, terrain, biome)
if MapTheme.layer_for_cell(terrain, subtype) == MapTheme.LayerKind.STRUCTURE:
	_apply_cell_to_layer(structure_layer, x, y, theme_key, biome)
```

```gdscript
# In godot-client/scripts/core/tile_set_builder.gd
const TILE_SIZE := MapMetrics.TILE_SIZE

static func _biomes_for(terrain: String) -> Array:
	if MapTheme.uses_biome(terrain):
		return Config.BIOMES.duplicate()
	return [""]
```

- [ ] **Step 5: Run the smoke test and inspect that layer assertions now pass**

```bash
"D:/PyCharm Community Edition 2024.3.3/PycharmProjects/Godot_v4.7-stable_win64/Godot_v4.7-stable_win64.exe" --headless --path godot-client res://tools/smoke_test.tscn
```

Expected: the HQ/building source-id assertions pass; later tasks may still fail for scene or unit work.

- [ ] **Step 6: Commit the theme/layer refactor**

```bash
git add godot-client/scripts/core/map_theme.gd godot-client/scripts/core/map_loader.gd godot-client/scripts/core/tile_set_builder.gd godot-client/scripts/board/board.gd godot-client/tools/smoke_test.gd
git commit -m "refactor(godot-client): route map rendering through theme layers"
```

## Task 3: Rebuild the Board Scene and Camera Contract

**Files:**
- Create: `godot-client/scripts/board/board_camera.gd`
- Modify: `godot-client/scenes/board.tscn`
- Modify: `godot-client/scripts/board/board.gd`
- Modify: `godot-client/scripts/main.gd`
- Test: `godot-client/tools/smoke_test.gd`

- [ ] **Step 1: Add failing smoke-test assertions for board scene node names**

```gdscript
_assert_true("Board has DecorLayer", board_check.get_node_or_null("DecorLayer") != null,
	"board scene must expose a dedicated decor layer")
_assert_true("Board has BoardCamera", board_check.get_node_or_null("BoardCamera") != null,
	"board scene must expose the dedicated camera node")
```

- [ ] **Step 2: Run the smoke test to verify it fails on the old scene structure**

```bash
"D:/PyCharm Community Edition 2024.3.3/PycharmProjects/Godot_v4.7-stable_win64/Godot_v4.7-stable_win64.exe" --headless --path godot-client res://tools/smoke_test.tscn
```

Expected: `FAIL` because `DecorLayer` and `BoardCamera` do not exist yet.

- [ ] **Step 3: Create `board_camera.gd` and move fit/clamp behavior out of `Board`**

```gdscript
extends Camera2D
class_name BoardCamera

func apply_metrics(metrics: MapMetrics) -> void:
	var board_rect := metrics.bounds_rect()
	position = metrics.board_center()
	var viewport := get_viewport().get_visible_rect().size
	var zoom_x := min(1.0, (viewport.x - 16.0) / board_rect.size.x)
	var zoom_y := min(1.0, (viewport.y - 16.0) / board_rect.size.y)
	zoom = Vector2(min(zoom_x, zoom_y), min(zoom_x, zoom_y))
	limit_left = int(board_rect.position.x)
	limit_top = int(board_rect.position.y)
	limit_right = int(board_rect.end.x)
	limit_bottom = int(board_rect.end.y)
```

- [ ] **Step 4: Rebuild `board.tscn` and `board.gd` around the new names**

```gdscript
# In godot-client/scripts/board/board.gd
@onready var ground_layer: TileMapLayer = $GroundLayer
@onready var structure_layer: TileMapLayer = $StructureLayer
@onready var decor_layer: TileMapLayer = $DecorLayer
@onready var highlights: Node2D = $HighlightLayer
@onready var units: Node2D = $UnitLayer
@onready var effects: Node2D = $EffectsLayer
@onready var board_camera: BoardCamera = $BoardCamera

func _ready() -> void:
	tile_set = TileSetBuilder.build()
	ground_layer.tile_set = tile_set
	structure_layer.tile_set = tile_set
	decor_layer.tile_set = tile_set
	highlights.bind_terrain_layer(ground_layer)
```

```text
# In godot-client/scenes/board.tscn make the node tree:
Board
  GroundLayer
  StructureLayer
  DecorLayer
  HighlightLayer
  UnitLayer
  EffectsLayer
  BoardCamera
```

- [ ] **Step 5: Update `main.gd` to use the new scene contract**

```gdscript
if event.button_index == MOUSE_BUTTON_LEFT:
	board.highlights.show_hover(tile)
	status_label.text = "tile=(%d,%d) terrain=%s" % [tile.x, tile.y, board.terrain_at(tile)]
```

- [ ] **Step 6: Re-run the smoke test**

```bash
"D:/PyCharm Community Edition 2024.3.3/PycharmProjects/Godot_v4.7-stable_win64/Godot_v4.7-stable_win64.exe" --headless --path godot-client res://tools/smoke_test.tscn
```

Expected: scene-structure assertions pass and camera wiring no longer depends on the old `Camera2D` node.

- [ ] **Step 7: Commit the board scene rebuild**

```bash
git add godot-client/scripts/board/board_camera.gd godot-client/scripts/board/board.gd godot-client/scripts/main.gd godot-client/scenes/board.tscn godot-client/tools/smoke_test.gd
git commit -m "refactor(godot-client): rebuild board scene around dedicated layers"
```

## Task 4: Add Static Unit Presentation on the Unit Layer

**Files:**
- Create: `godot-client/scripts/board/unit_node.gd`
- Modify: `godot-client/scripts/board/board.gd`
- Modify: `godot-client/tools/smoke_test.gd`
- Test: `godot-client/tools/smoke_test.gd`

- [ ] **Step 1: Add a failing smoke-test assertion for initial-unit placement**

```gdscript
_assert_gte("unit layer child count", board_check.units.get_child_count(), 1,
	"maps with initial_units should spawn static unit presenters")
```

- [ ] **Step 2: Run the smoke test to verify there are still no unit presenters**

```bash
"D:/PyCharm Community Edition 2024.3.3/PycharmProjects/Godot_v4.7-stable_win64/Godot_v4.7-stable_win64.exe" --headless --path godot-client res://tools/smoke_test.tscn
```

Expected: `FAIL` because `initial_units` are decoded but not instantiated.

- [ ] **Step 3: Create a minimal `unit_node.gd` presenter**

```gdscript
extends Node2D
class_name UnitNode

var unit_data: Dictionary = {}

func setup(data: Dictionary, color: Color) -> void:
	unit_data = data
	var marker := ColorRect.new()
	marker.size = Vector2(24, 24)
	marker.position = -marker.size * 0.5
	marker.color = color
	marker.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(marker)
```

- [ ] **Step 4: Instantiate unit presenters from `Board.load_map()`**

```gdscript
# In godot-client/scripts/board/board.gd
const UNIT_NODE_SCENE := preload("res://scripts/board/unit_node.gd")

func _rebuild_units(units_data: Array) -> void:
	for child in units.get_children():
		child.queue_free()
	for unit in units_data:
		var presenter: UnitNode = UnitNode.new()
		var color_name := String(unit.get("color", "red"))
		presenter.setup(unit, Config.player_color(color_name))
		presenter.position = metrics.cell_to_local(Vector2i(int(unit["x"]), int(unit["y"])))
		units.add_child(presenter)
```

- [ ] **Step 5: Re-run the smoke test**

```bash
"D:/PyCharm Community Edition 2024.3.3/PycharmProjects/Godot_v4.7-stable_win64/Godot_v4.7-stable_win64.exe" --headless --path godot-client res://tools/smoke_test.tscn
```

Expected: maps with `initial_units` now report at least one child under `UnitLayer`.

- [ ] **Step 6: Commit the static unit layer**

```bash
git add godot-client/scripts/board/unit_node.gd godot-client/scripts/board/board.gd godot-client/tools/smoke_test.gd
git commit -m "feat(godot-client): render static unit markers on unit layer"
```

## Task 5: Finish Validation and Refresh Docs

**Files:**
- Modify: `godot-client/tools/smoke_test.gd`
- Modify: `godot-client/README.md`
- Test: `godot-client/tools/smoke_test.gd`

- [ ] **Step 1: Add final smoke assertions for highlight reset and camera bounds**

```gdscript
_assert_true("highlight node exists", board_check.highlights != null,
	"board should expose the highlight layer after refactor")
_assert_true("camera limit right positive", board_check.board_camera.limit_right > 0,
	"camera bounds should be derived from board metrics")
```

- [ ] **Step 2: Run the smoke test and make sure the full 48x48 flow passes**

```bash
"D:/PyCharm Community Edition 2024.3.3/PycharmProjects/Godot_v4.7-stable_win64/Godot_v4.7-stable_win64.exe" --headless --path godot-client res://tools/smoke_test.tscn
```

Expected: `PASS`.

- [ ] **Step 3: Update the README status and layout notes**

```markdown
## Status

> **Status:** 48x48 map presentation baseline complete. The client now renders ground, structure, decor placeholders, highlights, static units, and board-bounded camera behavior from the existing BattleBlitz map JSON files.
```

```markdown
## Project layout

- `scripts/core/map_metrics.gd` - authoritative board scale and coordinate helpers
- `scripts/core/map_theme.gd` - terrain/subtype routing for layer-aware rendering
- `scripts/board/board_camera.gd` - fit/clamp camera behavior
- `scripts/board/unit_node.gd` - static unit presenter used by the map prototype
```

- [ ] **Step 4: Re-run the smoke test after the doc-only edit as a final no-regression check**

```bash
"D:/PyCharm Community Edition 2024.3.3/PycharmProjects/Godot_v4.7-stable_win64/Godot_v4.7-stable_win64.exe" --headless --path godot-client res://tools/smoke_test.tscn
```

Expected: `PASS`.

- [ ] **Step 5: Commit the validation and docs refresh**

```bash
git add godot-client/tools/smoke_test.gd godot-client/README.md
git commit -m "docs(godot-client): document 48px map presentation baseline"
```

## Self-Review

### Spec coverage

- 48x48 rendering contract: covered by Task 1 and Task 2.
- Multi-layer board structure: covered by Task 2 and Task 3.
- Static unit placement: covered by Task 4.
- Camera and highlight separation: covered by Task 1, Task 3, and Task 5.
- No backend changes: respected throughout; every touched path is under `godot-client/` or docs only.

### Placeholder scan

- No `TODO`, `TBD`, or “implement later” instructions remain in tasks.
- Every task lists concrete file paths, commands, and expected outputs.
- Each commit message is explicit and scoped to the described change.

### Type consistency

- Shared names used consistently across tasks: `MapMetrics`, `MapTheme`, `BoardCamera`, `GroundLayer`, `StructureLayer`, `DecorLayer`, `UnitLayer`, `HighlightLayer`.
- `board.gd` is the single orchestrator; `MapLoader` decodes data; `TileSetBuilder` builds assets; `UnitNode` handles per-unit visuals.

