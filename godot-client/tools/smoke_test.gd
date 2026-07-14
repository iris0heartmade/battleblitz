extends Node
## Headless smoke test for the 48x48 layer-aware map presentation baseline.

const MAP_METRICS_SCRIPT := preload("res://scripts/core/map_metrics.gd")

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
	_write_result("START", "Smoke test booted")
	print("=== BattleBlitz Godot Client - 48px smoke test ===")
	await get_tree().process_frame

	_assert_eq("MapMetrics tile size x", MAP_METRICS_SCRIPT.TILE_SIZE.x, 48,
		"tile width must stay locked to the 48px spec")
	_assert_eq("MapMetrics tile size y", MAP_METRICS_SCRIPT.TILE_SIZE.y, 48,
		"tile height must stay locked to the 48px spec")

	var ts := TileSetBuilder.build()
	var source_count := ts.get_source_count()
	_assert_gte("source_count", source_count, 1,
		"TileSet should expose at least one source")
	_assert_lte("source_count sanity cap", source_count, 50,
		"TileSet has too many sources")

	for terrain in Config.FE8_TILE_COORDS.keys():
		var sid: int = TileSetBuilder.source_id_for(String(terrain), "")
		_assert_gte("fe8 source_id(%s,)" % terrain, sid, 0,
			"missing FE8 source for %s" % terrain)

	for map_id in TEST_MAP_IDS:
		_test_one_map(map_id)

	var board_scene: PackedScene = load("res://scenes/board.tscn")
	var board_check = board_scene.instantiate()
	add_child(board_check)
	_assert_true("Board has DecorLayer", board_check.get_node_or_null("DecorLayer") != null,
		"board scene must expose a dedicated decor layer")
	_assert_true("Board has BoardCamera", board_check.get_node_or_null("BoardCamera") != null,
		"board scene must expose the dedicated camera node")

	var map_path_check := _map_path_for_id("balanced_2p_15")
	if map_path_check != "":
		var fcheck := FileAccess.open(map_path_check, FileAccess.READ)
		var parsed_check: Variant = JSON.parse_string(fcheck.get_as_text())
		fcheck.close()
		var result_raw: Variant = board_check.load_map(parsed_check)
		var result: Dictionary = result_raw
		if result.is_empty():
			_fail("Board returned empty result for balanced_2p_15")
		else:
			var centre := Vector2i(7, 7)
			var hq := Vector2i(2, 7)
			_assert_gte("ground layer source at centre", board_check.ground_layer.get_cell_source_id(centre), 0,
				"ground layer should receive terrain cells")
			_assert_gte("ground layer source at HQ", board_check.ground_layer.get_cell_source_id(hq), 0,
				"ground layer should always receive a terrain source")
			_assert_gte("structure layer source at HQ", board_check.structure_layer.get_cell_source_id(hq), 0,
				"structure layer should receive castle/building overlays")
			_assert_gte("unit layer child count", board_check.units.get_child_count(), 1,
				"maps with initial_units should spawn static unit presenters")
			_assert_true("highlight node exists", board_check.highlights != null,
				"board should expose the highlight layer after refactor")
			_assert_true("camera limit right positive", board_check.board_camera.limit_right > 0,
				"camera bounds should be derived from board metrics")
			_assert_eq("loaded map width", int(result.get("width", 0)), 15,
				"balanced_2p_15 should remain a 15x15 map")
	board_check.queue_free()

	_assert_eq("BBTypes.UNIT_DEF_KEY", BBTypes.UNIT_DEF_KEY, "def_",
		"Unit.def_ must keep its Python-keyword underscore in JSON wire format")
	_assert_true("GameState autoload", GameState != null,
		"GameState autoload not registered")
	_assert_true("InputState autoload", InputState != null,
		"InputState autoload not registered")
	_assert_true("NetworkClient autoload", NetworkClient != null,
		"NetworkClient autoload not registered")
	_assert_true("UserSettings autoload", UserSettings != null,
		"UserSettings autoload not registered")

	print("---")
	print("Passed: %d   Failed: %d" % [_passed, _failed])
	if _failed > 0:
		print("FAIL")
		_write_result("FAIL", "Passed=%d Failed=%d" % [_passed, _failed])
		get_tree().quit(1)
	else:
		print("PASS")
		_write_result("PASS", "Passed=%d Failed=%d" % [_passed, _failed])
		get_tree().quit(0)


func _test_one_map(map_id: String) -> void:
	var board_scene: PackedScene = load("res://scenes/board.tscn")
	var board = board_scene.instantiate()
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
	var result_raw: Variant = board.load_map(parsed)
	var result: Dictionary = result_raw
	if result.is_empty():
		_fail("Board returned empty result for %s" % map_id)
		board.queue_free()
		return
	var w: int = int(result["width"])
	var h: int = int(result["height"])
	var biome: String = String(result["biome"])
	var tile_lookup: Dictionary = result["tile_lookup"]
	_assert_eq("%s tile size x" % map_id, MAP_METRICS_SCRIPT.TILE_SIZE.x, 48,
		"board metrics should stay 48px wide")
	_assert_eq("%s tile size y" % map_id, MAP_METRICS_SCRIPT.TILE_SIZE.y, 48,
		"board metrics should stay 48px tall")
	_assert_eq("%s tile count" % map_id, tile_lookup.size(), w * h,
		"tile_lookup should have one entry per cell")
	_assert_true("%s camera node wired" % map_id, board.board_camera != null,
		"board camera should be present")
	print("  %s - %dx%d biome=%s units=%d" % [
		map_id, w, h, biome, board.units.get_child_count()])
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


func _assert_eq(label: String, got, expected, msg: String) -> void:
	if got == expected:
		_passed += 1
	else:
		_failed += 1
		print("  FAIL  %s: got %s expected %s - %s" % [label, str(got), str(expected), msg])


func _assert_gte(label: String, got, minimum, msg: String) -> void:
	if got >= minimum:
		_passed += 1
	else:
		_failed += 1
		print("  FAIL  %s: got %s < %s - %s" % [label, str(got), str(minimum), msg])


func _assert_lte(label: String, got, maximum, msg: String) -> void:
	if got <= maximum:
		_passed += 1
	else:
		_failed += 1
		print("  FAIL  %s: got %s > %s - %s" % [label, str(got), str(maximum), msg])


func _assert_true(label: String, cond: bool, msg: String) -> void:
	if cond:
		_passed += 1
	else:
		_failed += 1
		print("  FAIL  %s: %s" % [label, msg])


func _fail(msg: String) -> void:
	_failed += 1
	print("  FAIL  %s" % msg)


func _write_result(status: String, details: String) -> void:
	var path := ProjectSettings.globalize_path("user://smoke_test_result.txt")
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		return
	file.store_string("%s\n%s\n" % [status, details])
	file.close()
