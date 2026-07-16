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
var _last_recruit_event: Array = []


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

	var main_scene: PackedScene = load("res://scenes/main.tscn")
	var main_check = main_scene.instantiate()
	add_child(main_check)
	_assert_true("Lobby has RoomList", main_check.get_node_or_null("Lobby/LobbyFrame/RoomList") != null,
		"lobby hub should expose a waiting-room list")
	_assert_true("Lobby has RoomSelectOption", main_check.get_node_or_null("Lobby/LobbyFrame/RoomSelectOption") != null,
		"lobby hub should expose a selectable room dropdown")
	_assert_true("Lobby has RefreshRoomsBtn", main_check.get_node_or_null("Lobby/LobbyFrame/RefreshRoomsBtn") != null,
		"lobby hub should expose a room refresh button")
	_assert_true("Lobby has JoinSelectedBtn", main_check.get_node_or_null("Lobby/LobbyFrame/JoinSelectedBtn") != null,
		"lobby hub should expose a join-selected button")
	_assert_true("Lobby has JoinModeOption", main_check.get_node_or_null("Lobby/LobbyFrame/JoinModeOption") != null,
		"lobby hub should expose player/spectator join mode")
	_assert_true("Lobby has TeamOption", main_check.get_node_or_null("Lobby/LobbyFrame/TeamOption") != null,
		"lobby hub should expose a team selection option")
	_assert_true("Lobby has LobbyApplyTeamBtn", main_check.get_node_or_null("Lobby/LobbyFrame/LobbyApplyTeamBtn") != null,
		"lobby hub should expose a team update action")
	_assert_true("Lobby has CreateNameInput", main_check.get_node_or_null("Lobby/LobbyFrame/CreateNameInput") != null,
		"lobby hub should expose a room name input")
	_assert_true("Lobby has MapPresetOption", main_check.get_node_or_null("Lobby/LobbyFrame/MapPresetOption") != null,
		"lobby hub should expose a map preset dropdown")
	_assert_true("Lobby has CreateRoomBtn", main_check.get_node_or_null("Lobby/LobbyFrame/CreateRoomBtn") != null,
		"lobby hub should expose a create room button")
	_assert_true("Lobby has AiDifficultyOption", main_check.get_node_or_null("Lobby/LobbyFrame/AiDifficultyOption") != null,
		"lobby hub should expose AI difficulty selection")
	_assert_true("Lobby has AiKindOption", main_check.get_node_or_null("Lobby/LobbyFrame/AiKindOption") != null,
		"lobby hub should expose AI backend selection")
	_assert_true("Lobby has AiPersonalityOption", main_check.get_node_or_null("Lobby/LobbyFrame/AiPersonalityOption") != null,
		"lobby hub should expose AI personality selection")
	_assert_true("Lobby has AiPlayerOption", main_check.get_node_or_null("Lobby/LobbyFrame/AiPlayerOption") != null,
		"lobby hub should expose an AI player selector")
	_assert_true("Lobby has LobbyRemoveAiBtn", main_check.get_node_or_null("Lobby/LobbyFrame/LobbyRemoveAiBtn") != null,
		"lobby hub should expose AI removal")
	_assert_true("Menu has SavesButton", main_check.get_node_or_null("Menu/CenterContainer/ButtonCol/SavesButton") != null,
		"main menu should expose save management")
	_assert_true("SavesView has SaveSelectOption", main_check.get_node_or_null("SavesView/SaveFrame/SaveSelectOption") != null,
		"save management should expose selectable saves")
	_assert_true("SavesView has SaveDeleteBtn", main_check.get_node_or_null("SavesView/SaveFrame/SaveDeleteBtn") != null,
		"save management should expose delete action")
	_assert_true("HUD has AttackConfirmPanel", main_check.get_node_or_null("GameView/HUD/AttackConfirmPanel") != null,
		"attack flow should expose a confirm panel before POSTing")
	_assert_true("HUD has AttackConfirmButton", main_check.get_node_or_null("GameView/HUD/AttackConfirmPanel/ButtonRow/ConfirmBtn") != null,
		"attack confirm panel should expose a confirm action")
	_assert_true("BattleResult has MainlineNextBtn", main_check.get_node_or_null("GameView/HUD/BattleResultPanel/ResultBtnRow/MainlineNextBtn") != null,
		"mainline results should expose a next-battle action")
	_assert_true("MainlineView has MLAbandonBtn", main_check.get_node_or_null("MainlineView/MLFrame/MLAbandonBtn") != null,
		"mainline view should expose an abandon action")
	_assert_true("Main can build attack confirm text", main_check.has_method("_build_attack_confirm_text"),
		"attack confirm text should be testable without posting an action")
	var room_select: OptionButton = main_check.get_node("Lobby/LobbyFrame/RoomSelectOption")
	var room_list: RichTextLabel = main_check.get_node("Lobby/LobbyFrame/RoomList")
	main_check.call("_on_room_list_response", [
		{"id": 101, "name": "Alpha", "status": "waiting", "map_preset": "balanced_2p_15", "capacity": 2},
		{"id": 202, "name": "Beta", "status": "waiting", "map_preset": "balanced_3p_15", "capacity": 3},
	], 200)
	room_select.select(1)
	main_check.call("_on_room_selected", 1)
	_assert_true("Lobby room selection marker moves", room_list.text.contains("> #202"),
		"selecting a different room should move the visible marker")
	main_check.call("_on_lobby_state", {
		"status": "waiting",
		"player_count": 2,
		"players": [
			{"id": 1, "user_name": "Alice", "color": "red", "is_ai": false},
			{"id": 9, "user_name": "Bot", "color": "blue", "is_ai": true},
		],
	}, 200)
	var ai_player_option: OptionButton = main_check.get_node("Lobby/LobbyFrame/AiPlayerOption")
	var remove_ai_btn: Button = main_check.get_node("Lobby/LobbyFrame/LobbyRemoveAiBtn")
	_assert_gte("Lobby AI selector lists AI", ai_player_option.item_count, 1,
		"lobby state should populate removable AI players")
	_assert_true("Lobby remove AI enabled when AI present", not remove_ai_btn.disabled,
		"remove-ai button should enable when there is a selected AI")
	main_check.queue_free()

	_assert_eq("BBTypes.UNIT_DEF_KEY", BBTypes.UNIT_DEF_KEY, "def_",
		"Unit.def_ must keep its Python-keyword underscore in JSON wire format")
	_assert_true("GameState autoload", GameState != null,
		"GameState autoload not registered")
	_assert_true("InputState autoload", InputState != null,
		"InputState autoload not registered")
	_assert_true("NetworkClient autoload", NetworkClient != null,
		"NetworkClient autoload not registered")
	_assert_true("NetworkClient add_ai_player method", NetworkClient.has_method("add_ai_player"),
		"NetworkClient should expose a typed add-ai wrapper for the lobby")
	_assert_true("NetworkClient remove_player method", NetworkClient.has_method("remove_player"),
		"NetworkClient should expose DELETE /games/{id}/players/{player_id}")
	_assert_true("NetworkClient update_player_team method", NetworkClient.has_method("update_player_team"),
		"NetworkClient should expose PATCH /games/{id}/players/{player_id}/team")
	_assert_gte("NetworkClient list_games argument count", _method_arg_count(NetworkClient, "list_games"), 2,
		"list_games should accept callback and optional user_name filter")
	_assert_gte("NetworkClient join_game argument count", _method_arg_count(NetworkClient, "join_game"), 6,
		"join_game should accept game_id, user_name, color, team, role, callback")
	_assert_true("NetworkClient delete_game method", NetworkClient.has_method("delete_game"),
		"NetworkClient should expose DELETE /games/{id}")
	_assert_true("NetworkClient rejoin_game_by_player_id method", NetworkClient.has_method("rejoin_game_by_player_id"),
		"NetworkClient should expose player_id based rejoin")
	_assert_true("NetworkClient rejoin_game_by_name method", NetworkClient.has_method("rejoin_game_by_name"),
		"NetworkClient should expose user_name based rejoin")
	_assert_true("NetworkClient get_game_state method", NetworkClient.has_method("get_game_state"),
		"NetworkClient should expose GET /games/{id}/state for refreshes")
	_assert_gte("NetworkClient action_recruit argument count", _method_arg_count(NetworkClient, "action_recruit"), 6,
		"action_recruit should accept game_id, player_id, tile, unit_type, callback")
	_assert_gte("NetworkClient start_mainline argument count", _method_arg_count(NetworkClient, "start_mainline"), 4,
		"start_mainline should accept mainline_id, user_name, skip_intro, callback")
	_assert_gte("NetworkClient advance_mainline argument count", _method_arg_count(NetworkClient, "advance_mainline"), 4,
		"advance_mainline should accept mainline_id, user_name, game_id, callback")
	_assert_true("NetworkClient fetch_mainline_dialogue method", NetworkClient.has_method("fetch_mainline_dialogue"),
		"NetworkClient should expose dialogue fetch for mainline pre/post scenes")
	_assert_true("UserSettings autoload", UserSettings != null,
		"UserSettings autoload not registered")

	main_check.set("_user_name", "Alice")
	main_check.call("_on_list_games_for_resume", [
		{"id": 88, "name": "Save 88", "status": "playing"},
	], 200)
	_assert_eq("Resume picks filtered game summary", int(main_check.get("_resume_game_id")), 88,
		"resume should trust /games?user_name summaries and not require embedded players")
	var resume_btn: Button = main_check.get_node("Menu/CenterContainer/ButtonCol/ResumeButton")
	_assert_true("Resume button visible for filtered summary", resume_btn.visible,
		"resume button should appear when a filtered playable save exists")

	main_check.call("_on_saves_response", [
		{"id": 88, "name": "Free Save", "status": "playing", "turn_number": 3, "map_seed": 77},
		{"id": 99, "name": "mainline:chapter_01_steel_rebellion:battle_01", "status": "waiting", "turn_number": 1},
	], 200)
	var save_open_list: RichTextLabel = main_check.get_node("SavesView/SaveFrame/SaveOpenList")
	var save_ml_list: RichTextLabel = main_check.get_node("SavesView/SaveFrame/SaveMainlineList")
	var save_select: OptionButton = main_check.get_node("SavesView/SaveFrame/SaveSelectOption")
	_assert_true("Save manager renders open save", save_open_list.text.contains("Free Save"),
		"open-mode saves should render in the open save list")
	_assert_true("Save manager renders mainline save", save_ml_list.text.contains("chapter_01_steel_rebellion"),
		"mainline saves should render in the mainline save list")
	_assert_gte("Save manager populates select options", save_select.item_count, 2,
		"save manager should populate operation selector")

	var confirm_text: String = main_check.call("_build_attack_confirm_text", {
		"name": "Knight", "x": 1, "y": 1, "hp": 10
	}, {
		"defender_name": "Bandit", "x": 3, "y": 2, "hp": 7
	})
	_assert_true("Attack confirm text includes attacker", confirm_text.contains("Knight"),
		"attack confirm text should name the attacker")
	_assert_true("Attack confirm text includes target", confirm_text.contains("Bandit"),
		"attack confirm text should name the target")
	_assert_true("Attack confirm text includes distance", confirm_text.contains("距离 3"),
		"attack confirm text should include Manhattan distance")

	_last_recruit_event = []
	GameState.unit_recruited.connect(_capture_recruit_event, CONNECT_ONE_SHOT)
	GameState.ingest_event({
		"event_type": "recruit",
		"actor_unit_id": 44,
		"context": {
			"new_unit_id": 44,
			"unit_type": "archer",
			"tile_x": 5,
			"tile_y": 6,
			"cost": 250,
		},
	})
	_assert_eq("GameState emits recruit unit id", int(_last_recruit_event[0]) if _last_recruit_event.size() > 0 else -1, 44,
		"recruit event should emit the new unit id")
	_assert_eq("GameState emits recruit unit type", str(_last_recruit_event[1]) if _last_recruit_event.size() > 1 else "", "archer",
		"recruit event should emit the unit type")

	main_check.call("_on_recruit_response", {
		"new_unit_type": "archer",
		"cost": 250,
		"gold_remaining": 150,
		"description": "Alice 招募了弓箭手",
	}, 200)
	var main_status_label: Label = main_check.get_node("StatusLabel")
	_assert_true("Recruit response status names unit", main_status_label.text.contains("archer"),
		"recruit success status should include the recruited unit type")
	_assert_true("Recruit response status includes remaining gold", main_status_label.text.contains("150"),
		"recruit success status should include remaining gold")

	main_check.call("_on_ml_list_response", [
		{
			"id": "chapter_01_steel_rebellion",
			"title": "Steel Rebellion",
			"synopsis": "Opening chapter",
			"battle_count": 2,
		},
	], 200)
	var ml_list: VBoxContainer = main_check.get_node("MainlineView/MLFrame/MLListContainer")
	_assert_gte("Mainline list renders one item", ml_list.get_child_count(), 1,
		"mainline list should create a button for backend summaries")
	if ml_list.get_child_count() > 0:
		var ml_btn := ml_list.get_child(0) as Button
		_assert_true("Mainline list uses backend battle_count", ml_btn.text.contains("2"),
			"mainline button should render backend battle_count")
		_assert_true("Mainline list uses backend synopsis tooltip", ml_btn.tooltip_text == "Opening chapter",
			"mainline button tooltip should use backend synopsis")

	main_check.set("_user_name", "Alice")
	main_check.call("_on_mainline_start_response", {
		"game_id": 123,
		"player_id": 456,
		"mainline_id": "chapter_01_steel_rebellion",
		"battle_index": 0,
		"total_battles": 2,
		"state": "battle",
	}, 200)
	_assert_eq("Mainline start stores game id", int(main_check.get("_game_id")), 123,
		"mainline start should store spawned game id")
	_assert_eq("Mainline start stores player id", int(main_check.get("_player_id")), 456,
		"mainline start should store human player id")
	_assert_true("Mainline start switches to game view", (main_check.get_node("GameView") as Control).visible,
		"mainline start should enter game view")
	_assert_true("Mainline start status includes progress", main_status_label.text.contains("1/2"),
		"mainline start should show battle progress")

	main_check.call("_on_mainline_advance_response", {
		"state": "dialogue",
		"mainline_id": "chapter_01_steel_rebellion",
		"battle_index": 1,
		"total_battles": 2,
		"post_battle_dialogue_url": "dialogue/chapter_01/post_01.json",
	}, 200)
	_assert_true("Mainline advance status includes next progress", main_status_label.text.contains("2/2"),
		"mainline advance should show the next battle progress")
	var ml_next_btn: Button = main_check.get_node("GameView/HUD/BattleResultPanel/ResultBtnRow/MainlineNextBtn")
	_assert_true("Mainline advance shows next battle button", ml_next_btn.visible,
		"non-victory advance should reveal the next-battle button")
	main_check.call("_on_mainline_next_battle_response", {
		"game_id": 321,
		"player_id": 654,
		"mainline_id": "chapter_01_steel_rebellion",
		"battle_index": 1,
		"total_battles": 2,
		"state": "battle",
	}, 201)
	_assert_eq("Mainline next stores game id", int(main_check.get("_game_id")), 321,
		"next battle should store the spawned game id")
	main_check.call("_on_mainline_advance_response", {
		"state": "victory",
		"mainline_id": "chapter_01_steel_rebellion",
		"battle_index": 2,
		"total_battles": 2,
		"rewards": {"gold": 100},
	}, 200)
	_assert_true("Mainline victory status is shown", main_status_label.text.contains("通关"),
		"mainline victory should show completion status")
	_assert_true("Mainline victory hides next battle button", not ml_next_btn.visible,
		"mainline victory should hide the next-battle button")
	main_check.set("_active_mainline_id", "chapter_01_steel_rebellion")
	main_check.call("_on_mainline_abandon_response", {
		"ok": true,
		"mainline_id": "chapter_01_steel_rebellion",
		"abandoned_at": "2026-07-16T00:00:00Z",
	}, 200)
	_assert_eq("Mainline abandon clears active id", str(main_check.get("_active_mainline_id")), "",
		"abandon should clear active mainline state")
	_assert_true("Mainline abandon status is shown", main_status_label.text.contains("放弃"),
		"abandon should update status")
	main_check.call("_on_lobby_team_response", {"ok": true, "player_id": 1, "team": "red"}, 200)
	var lobby_status: Label = main_check.get_node("Lobby/LobbyFrame/LobbyStatus")
	_assert_true("Lobby team response updates status", lobby_status.text.contains("red"),
		"team update response should show selected team")

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


func _method_arg_count(target: Object, method_name: String) -> int:
	for item in target.get_method_list():
		if String(item.get("name", "")) == method_name:
			var args: Array = item.get("args", [])
			return args.size()
	return -1


func _capture_recruit_event(new_unit_id: int, unit_type: String, tile_x: int, tile_y: int, cost: int) -> void:
	_last_recruit_event = [new_unit_id, unit_type, tile_x, tile_y, cost]


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
