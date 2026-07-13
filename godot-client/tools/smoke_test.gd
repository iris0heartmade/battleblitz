extends Node
## smoke_test.gd — M1 headless smoke test. Run as a scene (NOT -s)
## so the autoloads (Config etc.) are loaded.
##
## Run with:
##   "<godot_exe>" --headless --path godot-client res://tools/smoke_test.tscn
##
## Exits with code 0 on success, 1 on any assertion failure.

const TEST_MAP_IDS := [
	"balanced_2p_15",
	"balanced_3p_15",
	"balanced_4p_20",
	"realistic_grass_2p_20",
	"realistic_desert_2p_25",
	"realistic_snow_2p_20",
]

var _failed: int = 0
var _passed: int = 0


func _ready() -> void:
	print("=== BattleBlitz Godot Client — M1 smoke test ===")
	# Wait one frame so the Board autoload is fully ready.
	await get_tree().process_frame

	# 1. TileSetBuilder: count sources. With the new architecture, we
	#    have ONE big FE8 atlas (source_id 0) + a small number of
	#    legacy per-terrain sources (for terrains that don't have an
	#    FE8 overworld equivalent — currently `bridge` if its PNG is
	#    missing). The smoke test asserts the expected ranges.
	var ts := TileSetBuilder.build()
	var source_count := ts.get_source_count()
	_assert_gte("source_count (FE8 + legacy)", source_count, 1,
		"TileSet should have at least the FE8 atlas (got %d)" % source_count)
	_assert_lte("source_count (sanity cap)", source_count, 50,
		"TileSet has too many sources — regression (got %d)" % source_count)

	# 2. Every FE8-mapped terrain has a source_id lookup. The MapLoader
	#    looks up with the empty biome key for non-biome-aware terrains.
	#    (FE8 atlas is biome-agnostic; we only register it under "".)
	for terrain in Config.FE8_TILE_COORDS.keys():
		var sid: int = TileSetBuilder.source_id_for(terrain, "")
		_assert_gte("fe8 source_id(%s,)" % terrain, sid, 0,
			"missing FE8 source for %s" % terrain)

	# 3. Legacy terrains (bridge, snow_peak, etc.) — at least one
	#    source_id is registered when the PNG is present.
	#    (Skipped intentionally: most legacy PNGs are missing.)

	# 3. MapLoader: apply each demo map to a fresh board.
	for map_id in TEST_MAP_IDS:
		_test_one_map(map_id)

	# 3b. CRITICAL REGRESSION TEST: after MapLoader, the cells
	#     must render — not just exist in `tile_lookup`. The M1.5
	#     `alternative_tile` bug made `set_cell` address (0,1) etc.
	#     in the atlas, which produced visually-empty cells even
	#     though the API call "succeeded". Verify the rendered
	#     source_id on the terrain layer for the centre cell.
	var board_scene_check: PackedScene = load("res://scenes/board.tscn")
	var board_check: Board = board_scene_check.instantiate()
	add_child(board_check)
	var map_path_check := _map_path_for_id("balanced_2p_15")
	if map_path_check != "":
		var fcheck := FileAccess.open(map_path_check, FileAccess.READ)
		var parsed_check: Variant = JSON.parse_string(fcheck.get_as_text())
		fcheck.close()
		MapLoader.apply_to_board(board_check, parsed_check)
		# Sample the centre cell — must have a valid source_id and
		# must not be the "default" empty source.
		var centre := Vector2i(7, 7)
		var src_at_centre: int = board_check.terrain_layer.get_cell_source_id(centre)
		_assert_gte("terrain_layer source at centre (7,7)", src_at_centre, 0,
			"centre cell has no source_id — MapLoader failed to write")
		# Sample a known mountain cell (row 0).
		var mt := Vector2i(7, 0)
		var mt_src: int = board_check.terrain_layer.get_cell_source_id(mt)
		_assert_gte("mountain row 0 has source_id", mt_src, 0,
			"row 0 (all mountains) has no source_id")
		# Make sure we wrote to the full board.
		var written_count := 0
		var missing: Array = []
		for yy in 15:
			for xx in 15:
				if board_check.terrain_layer.get_cell_source_id(Vector2i(xx, yy)) != -1:
					written_count += 1
				else:
					missing.append(Vector2i(xx, yy))
		if not missing.is_empty():
			print("  missing %d cells: %s..." % [missing.size(), str(missing.slice(0, 5))])
			# Diagnose first missing cell
			var m: Vector2i = missing[0]
			var key: String = board_check.tile_lookup.get(m, {}).get("terrain", "?")
			print("    first missing at %s, terrain=%s, in FE8 coords=%s" % [
				str(m), key, "yes" if key in Config.FE8_TILE_COORDS else "no"])
		_assert_eq("all 225 cells written", written_count, 225,
			"expected every cell to have a source_id")
	board_check.queue_free()

	# 4. Unit.def_ key round-trip (Python keyword quirk).
	_assert_eq("BBTypes.UNIT_DEF_KEY", BBTypes.UNIT_DEF_KEY, "def_",
		"Unit.def_ must keep its Python-keyword underscore in JSON wire format")
	var sample_unit := {
		"id": 1, "player_id": 1, "unit_type": "swordsman",
		"name": "Sword", "level": 1, "exp": 0,
		"hp": 10, "max_hp": 10, "atk": 5, "def_": 3,
		"matk": 0, "mdef": 0, "mov": 5, "mp": 5, "morale": 0,
		"x": 0, "y": 0, "has_acted": false, "has_moved": false,
		"skills": [], "attack_range": 1, "min_attack_range": 0,
		"hero_id": null,
	}
	_assert_eq("unit_def(sample)", BBTypes.unit_def(sample_unit), 3,
		"unit_def() must read from 'def_' key")
	_assert_eq("unit_mp_budget(sample)", BBTypes.unit_mp_budget(sample_unit), 10,
		"unit_mp_budget() should be mp * 2 (half-point encoding)")

	# 5. GameState autoload is reachable.
	_assert_true("GameState autoload", GameState != null,
		"GameState autoload not registered")
	_assert_true("InputState autoload", InputState != null,
		"InputState autoload not registered")
	_assert_true("NetworkClient autoload", NetworkClient != null,
		"NetworkClient autoload not registered")
	_assert_true("UserSettings autoload", UserSettings != null,
		"UserSettings autoload not registered")

	# Summary.
	print("---")
	print("Passed: %d   Failed: %d" % [_passed, _failed])
	if _failed > 0:
		print("FAIL")
		get_tree().quit(1)
	else:
		print("PASS")
		get_tree().quit(0)


func _test_one_map(map_id: String) -> void:
	# Use the .tscn (not `Board.new()`) so the @onready children
	# (TerrainLayer / CastleLayer / Highlights / Units / Effects /
	# Camera2D) get wired up. Plain `Board.new()` would leave them
	# all null and the loader's `clear()` calls would NPE.
	var board_scene: PackedScene = load("res://scenes/board.tscn")
	var board: Board = board_scene.instantiate()
	add_child(board)
	var map_path := _map_path_for_id(map_id)
	if map_path == "":
		_fail("no map file found for %s" % map_id)
		board.queue_free()
		return
	var f := FileAccess.open(map_path, FileAccess.READ)
	if f == null:
		_fail("cannot open %s" % map_path)
		board.queue_free()
		return
	var text := f.get_as_text()
	f.close()
	var parsed: Variant = JSON.parse_string(text)
	if not parsed is Dictionary:
		_fail("%s: not a JSON object" % map_path)
		board.queue_free()
		return
	var result: Dictionary = MapLoader.apply_to_board(board, parsed)
	if result.is_empty():
		_fail("MapLoader returned empty result for %s" % map_id)
		board.queue_free()
		return
	var w: int = int(result["width"])
	var h: int = int(result["height"])
	var biome: String = String(result["biome"])
	var tile_lookup: Dictionary = result["tile_lookup"]
	_assert_eq("%s width" % map_id, w, int(parsed.get("size", {}).get("width", parsed.get("size", w))),
		"width mismatch")
	_assert_eq("%s height" % map_id, h, int(parsed.get("size", {}).get("height", parsed.get("size", h))),
		"height mismatch")
	_assert_eq("%s tile count" % map_id, tile_lookup.size(), w * h,
		"tile_lookup should have one entry per cell")
	# Spot-check the first cell.
	if not tile_lookup.is_empty():
		var first_key: Vector2i = tile_lookup.keys()[0]
		var first: Dictionary = tile_lookup[first_key]
		_assert_true("%s first cell has terrain" % map_id,
			first.has("terrain") and not String(first["terrain"]).is_empty(),
			"first cell missing terrain key")
	# Castle sub-features appear in `realistic_*` maps (and the new
	# generator). Older `balanced_*` use bare 'C' (terrain only).
	var has_castle_subtype := false
	for k in tile_lookup:
		var cell: Dictionary = tile_lookup[k]
		var sub: String = String(cell.get("subtype", ""))
		if sub.begins_with("castle_") and sub != "castle":
			has_castle_subtype = true
			break
	print("  %s — %dx%d biome=%s  castle_subtype=%s" % [
		map_id, w, h, biome, has_castle_subtype])
	board.queue_free()


func _map_path_for_id(map_id: String) -> String:
	var candidates := [
		"res://../../game/maps/%s.json" % map_id,
		"res://../game/maps/%s.json" % map_id,
		"res://game/maps/%s.json" % map_id,
	]
	for c in candidates:
		if FileAccess.file_exists(c):
			return c
	return ""


# ============================================================
# Assertion helpers
# ============================================================

func _assert_eq(label: String, got, expected, msg: String) -> void:
	if got == expected:
		_passed += 1
	else:
		_failed += 1
		print("  FAIL  %s: got %s expected %s — %s" % [label, str(got), str(expected), msg])

func _assert_gte(label: String, got, minimum, msg: String) -> void:
	if got >= minimum:
		_passed += 1
	else:
		_failed += 1
		print("  FAIL  %s: got %s < %s — %s" % [label, str(got), str(minimum), msg])

func _assert_lte(label: String, got, maximum, msg: String) -> void:
	if got <= maximum:
		_passed += 1
	else:
		_failed += 1
		print("  FAIL  %s: got %s > %s — %s" % [label, str(got), str(maximum), msg])

func _assert_true(label: String, cond: bool, msg: String) -> void:
	if cond:
		_passed += 1
	else:
		_failed += 1
		print("  FAIL  %s: %s" % [label, msg])

func _fail(msg: String) -> void:
	_failed += 1
	print("  FAIL  %s" % msg)
