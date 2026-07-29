extends Node
## Headless smoke test for the 48x48 layer-aware map presentation baseline.

const MAP_METRICS_SCRIPT := preload("res://scripts/core/map_metrics.gd")
const MAP_PREVIEW_SUMMARY_SCRIPT := preload("res://scripts/ui/map_preview_summary.gd")

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

# Resolved autoload singletons (lookup via /root/<Name> so the test never
# depends on the autoload identifier being a compile-time singleton).
# _init_autoloads() short-circuits with a clear failure if the project
# is missing any required autoload.
var _game_state: Node = null
var _input_state: Node = null
var _network_client: Node = null
var _user_settings: Node = null


func _resolve_autoload(name: String) -> Node:
	return get_node_or_null("/root/" + name)


func _init_autoloads() -> bool:
	_game_state = _resolve_autoload("GameState")
	_input_state = _resolve_autoload("InputState")
	_network_client = _resolve_autoload("NetworkClient")
	_user_settings = _resolve_autoload("UserSettings")
	var ok := _game_state != null \
		and _input_state != null \
		and _network_client != null \
		and _user_settings != null
	if not ok:
		print("  FAIL  Missing required autoload(s): "
			% _missing_autoload_names())
	return ok


func _missing_autoload_names() -> String:
	var missing: Array[String] = []
	if _game_state == null:
		missing.append("GameState")
	if _input_state == null:
		missing.append("InputState")
	if _network_client == null:
		missing.append("NetworkClient")
	if _user_settings == null:
		missing.append("UserSettings")
	return ", ".join(missing)


func _ready() -> void:
	_write_result("START", "Smoke test booted")
	print("=== BattleBlitz Godot Client - 48px smoke test ===")
	await get_tree().process_frame

	# Bail out early with a clear failure if any required autoload is
	# missing — autoload identifiers are resolved through /root/* so the
	# test never relies on compile-time singleton bindings.
	if not _init_autoloads():
		_write_result("FAIL", "Missing autoloads: %s" % _missing_autoload_names())
		# Still try to fail gracefully below; autoload guards will skip
		# dependent assertions.

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
	_assert_new_tileset_atlas_sources(ts)
	_assert_tiles_fill_48px_regions(ts)
	_assert_unit_sprite_preserves_aspect()

	for map_id in TEST_MAP_IDS:
		_test_one_map(map_id)
	_test_map_preview_for_all_map_files()

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
		var preview_summary: Dictionary = MAP_PREVIEW_SUMMARY_SCRIPT.summarize_map(parsed_check)
		var preview_factions: Dictionary = preview_summary.get("factions", {})
		var red_preview: Dictionary = preview_factions.get("red", {})
		var blue_preview: Dictionary = preview_factions.get("blue", {})
		_assert_eq("Map preview recommended players", int(preview_summary.get("recommended_players", 0)), 2,
			"preview summary should expose player count filters")
		_assert_eq("Map preview red HQ count", int(red_preview.get("hq", 0)), 1,
			"red starting faction should include one HQ")
		_assert_eq("Map preview blue HQ count", int(blue_preview.get("hq", 0)), 1,
			"blue starting faction should include one HQ")
		_assert_eq("Map preview red initial units", int(red_preview.get("units", 0)), 5,
			"red starting faction should count initial units")
		_assert_eq("Map preview blue initial units", int(blue_preview.get("units", 0)), 5,
			"blue starting faction should count initial units")
		_assert_gte("Map preview red village count", int(red_preview.get("village", 0)), 1,
			"red starting faction should claim nearby villages in the preview")
		_assert_gte("Map preview blue barracks count", int(blue_preview.get("barracks", 0)), 1,
			"blue starting faction should claim nearby barracks in the preview")
		_assert_true("Map preview has neutral building summary", preview_summary.has("neutral_buildings"),
			"preview summary should expose neutral building counts")
		var preview_lines: String = MAP_PREVIEW_SUMMARY_SCRIPT.build_faction_lines(preview_summary)
		_assert_true("Map preview text mentions neutral buildings", preview_lines.contains("中立"),
			"preview text should include neutral building distribution")
		var map4_path := _map_path_for_id("balanced_4p_20")
		if map4_path != "":
			var f4 := FileAccess.open(map4_path, FileAccess.READ)
			var parsed4: Variant = JSON.parse_string(f4.get_as_text())
			f4.close()
			var summary4: Dictionary = MAP_PREVIEW_SUMMARY_SCRIPT.summarize_map(parsed4)
			var lines4: String = MAP_PREVIEW_SUMMARY_SCRIPT.build_faction_lines(summary4)
			_assert_true("Map preview 4P text mentions yellow faction", lines4.contains(str(MAP_PREVIEW_SUMMARY_SCRIPT.COLOR_LABELS.get("yellow", "yellow"))),
				"4P preview text should include every starting faction, including yellow")
			_assert_true("Map preview 4P text mentions neutral buildings", lines4.contains(str(MAP_PREVIEW_SUMMARY_SCRIPT.NEUTRAL_LABEL)),
				"4P preview text should include neutral building distribution")
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
	var lobby_join_col := "Lobby/LobbyFrame/LobbyDualCol/LeftCol"
	var lobby_create_col := "Lobby/LobbyFrame/LobbyDualCol/RightCol"
	var lobby_map_panel := lobby_join_col + "/MapPreviewPanel"
	var lobby_ai_row := "Lobby/LobbyFrame/AiConfigRow"
	var lobby_ai_actions := "Lobby/LobbyFrame/AiActionRow"
	_assert_true("Lobby has MapPlayerCountOption", main_check.get_node_or_null(lobby_join_col + "/MapPickerRow/MapPlayerCountOption") != null,
		"lobby create flow should filter maps by player count above the preview")
	_assert_true("Lobby has MapPresetOption in map preview", main_check.get_node_or_null(lobby_join_col + "/MapPickerRow/MapPresetOption") != null,
		"lobby create flow should choose maps above the preview")
	_assert_true("Lobby has MapPreviewTexture", main_check.get_node_or_null(lobby_map_panel + "/MapPreviewTexture") != null,
		"lobby create flow should show a compact visual map preview")
	_assert_true("Lobby has MapFactionSummary", main_check.get_node_or_null(lobby_map_panel + "/MapFactionSummary") != null,
		"lobby create flow should summarize starting buildings and units per faction")
	_assert_true("Lobby has SeatPanel", main_check.get_node_or_null(lobby_create_col + "/SeatPanel") != null,
		"lobby create flow should show seat cards for the selected map factions")
	_assert_true("Lobby has SeatGrid", main_check.get_node_or_null(lobby_create_col + "/SeatPanel/SeatGrid") != null,
		"lobby create flow should render one seat card per starting faction")
	_assert_true("Lobby has RoomList", main_check.get_node_or_null(lobby_join_col + "/RoomList") != null,
		"lobby hub should expose a waiting-room list")
	_assert_true("Lobby has RoomSelectOption", main_check.get_node_or_null(lobby_join_col + "/RoomSelectOption") != null,
		"lobby hub should expose a selectable room dropdown")
	_assert_true("Lobby has RefreshRoomsBtn", main_check.get_node_or_null(lobby_join_col + "/LeftBtnRow/RefreshRoomsBtn") != null,
		"lobby hub should expose a room refresh button")
	_assert_true("Lobby has JoinSelectedBtn", main_check.get_node_or_null(lobby_join_col + "/LeftBtnRow/JoinSelectedBtn") != null,
		"lobby hub should expose a join-selected button")
	_assert_true("Lobby has JoinModeOption", main_check.get_node_or_null(lobby_join_col + "/JoinModeOption") != null,
		"lobby hub should expose player/spectator join mode")
	_assert_true("Lobby has TeamOption", main_check.get_node_or_null(lobby_create_col + "/TeamRow/TeamOption") != null,
		"lobby hub should expose a team selection option")
	_assert_true("Lobby has LobbyApplyTeamBtn", main_check.get_node_or_null(lobby_create_col + "/TeamRow/LobbyApplyTeamBtn") != null,
		"lobby hub should expose a team update action")
	_assert_true("Lobby has CreateNameInput", main_check.get_node_or_null(lobby_create_col + "/CreateNameInput") != null,
		"lobby hub should expose a room name input")
	_assert_true("Lobby can render lobby map preview", main_check.has_method("_render_lobby_map_preview"),
		"lobby hub should expose a refresh path for map preview and faction summary")
	_assert_true("Lobby can render lobby seat columns", main_check.has_method("_render_lobby_seat_columns"),
		"lobby hub should expose a refresh path for map-driven seat cards")
	_assert_true("Lobby has LobbyCommanderOption", main_check.get_node_or_null(lobby_create_col + "/LobbyCommanderOption") != null,
		"lobby hub should expose commander selection for room creation")
	_assert_true("Lobby has LobbyBgmOption", main_check.get_node_or_null(lobby_create_col + "/LobbyBgmOption") != null,
		"lobby hub should expose BGM selection for room creation")
	_assert_true("Lobby has CreateRoomBtn", main_check.get_node_or_null(lobby_create_col + "/CreateRoomBtn") != null,
		"lobby hub should expose a create room button")
	_assert_true("Lobby has AiDifficultyOption", main_check.get_node_or_null(lobby_ai_row + "/AiDifficultyOption") != null,
		"lobby hub should expose AI difficulty selection")
	_assert_true("Lobby has AiKindOption", main_check.get_node_or_null(lobby_ai_row + "/AiKindOption") != null,
		"lobby hub should expose AI backend selection")
	_assert_true("Lobby has AiPersonalityOption", main_check.get_node_or_null(lobby_ai_row + "/AiPersonalityOption") != null,
		"lobby hub should expose AI personality selection")
	_assert_true("Lobby has AiCommanderOption", main_check.get_node_or_null("Lobby/LobbyFrame/AiCommanderOption") != null,
		"lobby hub should expose a commander preset for AI seats created with the room")
	_assert_true("Lobby has AiPlayerOption", main_check.get_node_or_null(lobby_ai_actions + "/AiPlayerOption") != null,
		"lobby hub should expose an AI player selector")
	_assert_true("Lobby has LobbyRemoveAiBtn", main_check.get_node_or_null(lobby_ai_actions + "/LobbyRemoveAiBtn") != null,
		"lobby hub should expose AI removal")
	_assert_true("Menu has SavesButton", main_check.get_node_or_null("Menu/CenterContainer/FooterRow/SavesButton") != null,
		"main menu should expose save management")
	_assert_true("Menu has no FreePlayButton", main_check.get_node_or_null("Menu/CenterContainer/GroupRow/SoloCard/FreePlayButton") == null,
		"the obsolete home free-play vs AI entry should stay removed")
	_assert_true("Menu has EditorButton", main_check.get_node_or_null("Menu/CenterContainer/FooterRow/EditorButton") != null,
		"main menu should expose the map editor")
	_assert_true("EditorView exists", main_check.get_node_or_null("EditorView") != null,
		"map editor should have a dedicated Godot view")
	_assert_true("EditorView has EditorBoard", main_check.get_node_or_null("EditorView/EditorBoard") != null,
		"map editor should reuse the board renderer for preview/editing")
	_assert_true("EditorView has EditorMapNameInput", main_check.get_node_or_null("EditorView/EditorPanel/EditorMapNameInput") != null,
		"map editor should expose a map name input")
	_assert_true("EditorView has EditorTerrainOption", main_check.get_node_or_null("EditorView/EditorPanel/EditorTerrainOption") != null,
		"map editor should expose a terrain brush selector")
	_assert_true("EditorView has EditorSurfaceOption", main_check.get_node_or_null("EditorView/EditorPanel/EditorSurfaceOption") != null,
		"map editor should expose a surface/building brush selector")
	_assert_true("EditorView has EditorSurfaceOwnerOption", main_check.get_node_or_null("EditorView/EditorPanel/EditorSurfaceOwnerOption") != null,
		"map editor should expose surface/building ownership selection")
	_assert_true("EditorView has EditorApplyBiomeBtn", main_check.get_node_or_null("EditorView/EditorPanel/EditorApplyBiomeBtn") != null,
		"map editor should expose one-click biome branch switching")
	_assert_true("EditorView has EditorModeOption", main_check.get_node_or_null("EditorView/EditorPanel/EditorModeOption") != null,
		"map editor should expose terrain/surface/unit edit modes")
	_assert_true("EditorView has EditorUnitOption", main_check.get_node_or_null("EditorView/EditorPanel/EditorUnitOption") != null,
		"map editor should expose a unit type selector")
	_assert_true("EditorView has EditorUnitToolOption", main_check.get_node_or_null("EditorView/EditorPanel/EditorUnitToolOption") != null,
		"map editor should expose place/erase unit tools")
	_assert_true("EditorView has EditorUnitColorOption", main_check.get_node_or_null("EditorView/EditorPanel/EditorUnitColorOption") != null,
		"map editor should expose a unit color selector")
	_assert_true("EditorView has EditorUnitLevelOption", main_check.get_node_or_null("EditorView/EditorPanel/EditorUnitLevelOption") != null,
		"map editor should expose a unit level selector")
	_assert_true("EditorView has EditorWidthOption", main_check.get_node_or_null("EditorView/EditorPanel/EditorWidthOption") != null,
		"map editor should expose a width selector")
	_assert_true("EditorView has EditorHeightOption", main_check.get_node_or_null("EditorView/EditorPanel/EditorHeightOption") != null,
		"map editor should expose a height selector")
	_assert_true("EditorView has EditorResizeBtn", main_check.get_node_or_null("EditorView/EditorPanel/EditorResizeBtn") != null,
		"map editor should expose a resize action")
	_assert_true("EditorView has EditorUndoBtn", main_check.get_node_or_null("EditorView/EditorPanel/EditorUndoBtn") != null,
		"map editor should expose undo for editing mistakes")
	_assert_true("EditorView has EditorRedoBtn", main_check.get_node_or_null("EditorView/EditorPanel/EditorRedoBtn") != null,
		"map editor should expose redo after undo")
	_assert_true("EditorView has EditorSaveBtn", main_check.get_node_or_null("EditorView/EditorPanel/EditorSaveBtn") != null,
		"map editor should expose a save action")
	_assert_true("EditorView has EditorLoadBtn", main_check.get_node_or_null("EditorView/EditorPanel/EditorLoadBtn") != null,
		"map editor should expose a load-selected action")
	_assert_true("EditorView has EditorDeleteBtn", main_check.get_node_or_null("EditorView/EditorPanel/EditorDeleteBtn") != null,
		"map editor should expose a delete-selected action")
	_assert_true("SavesView has SaveSelectOption", main_check.get_node_or_null("SavesView/SaveFrame/SaveSelectOption") != null,
		"save management should expose selectable saves")
	_assert_true("SavesView has SaveDeleteBtn", main_check.get_node_or_null("SavesView/SaveFrame/SaveDeleteBtn") != null,
		"save management should expose delete action")
	# T:#16 — in_progress 视图存在性
	_assert_true("Main has InProgressView", main_check.get_node_or_null("InProgressView") != null,
		"in_progress view should be wired in main.tscn")
	_assert_true("Main menu has InProgressButton", main_check.get_node_or_null("Menu/CenterContainer/FooterRow/InProgressButton") != null,
		"in_progress view should be reachable from main menu")
	_assert_true("InProgressView has IPFrame", main_check.get_node_or_null("InProgressView/IPFrame") != null,
		"in_progress view should expose IPFrame container")
	_assert_true("InProgressView has IPList", main_check.get_node_or_null("InProgressView/IPFrame/IPScroll/IPList") != null,
		"in_progress view should expose a list container")
	_assert_true("InProgressView has IPBackBtn", main_check.get_node_or_null("InProgressView/IPFrame/IPBackBtn") != null,
		"in_progress view should expose a back button")
	_assert_true("HUD has AttackConfirmPanel", main_check.get_node_or_null("GameView/HUD/AttackConfirmPanel") != null,
		"attack flow should expose a confirm panel before POSTing")
	var battle_top_art := main_check.get_node_or_null("GameView/HUD/TopStatusArt") as TextureRect
	_assert_true("HUD top status art is wired", battle_top_art != null and battle_top_art.texture != null,
		"the always-visible battle header must render its production art asset")
	_assert_true("HUD top status art uses clean center rail",
		battle_top_art != null and battle_top_art.texture.resource_path.contains("top_status_rail_clean"),
		"team meters need a center-safe rail without an overlapping emblem")
	var compact_plaque_paths: Array[String] = [
		"GameView/HUD/TopLeft/TurnBadge/OrnatePlaque",
		"GameView/HUD/TopLeft/PhaseBadge/OrnatePlaque",
		"GameView/HUD/TopRight/CurrentPlayerBadge/OrnatePlaque",
		"GameView/HUD/TopRight/EndTurnButton/OrnatePlaque",
		"GameView/HUD/BottomLeft/GoldPanel/OrnatePlaque",
		"GameView/HUD/BottomRight/AIThinking/OrnatePlaque",
		"GameView/HUD/BottomRight/WarReportButton/OrnatePlaque",
	]
	for plaque_path in compact_plaque_paths:
		var plaque := main_check.get_node_or_null(plaque_path) as NinePatchRect
		_assert_true("Compact HUD art wired: %s" % plaque_path,
			plaque != null and plaque.texture != null and not plaque.draw_center,
			"always-visible corner controls must keep their compact plaque art")
	var ornate_panel_paths: Array[String] = [
		"GameView/HUD/InfoPanel/OrnateFrame",
		"GameView/HUD/ActionBubble/OrnateFrame",
		"GameView/HUD/AttackConfirmPanel/OrnateFrame",
		"GameView/HUD/WarReportPanel/OrnateFrame",
		"SettingsPanel/OrnateFrame",
		"GameView/HUD/PausePanel/OrnateFrame",
		"GameView/HUD/DialogPanel/OrnateFrame",
		"GameView/HUD/TutorialBubble/OrnateFrame",
		"GameView/HUD/BattleResultPanel/OrnateFrame",
	]
	for ornate_path in ornate_panel_paths:
		var ornate_frame := main_check.get_node_or_null(ornate_path) as NinePatchRect
		_assert_true("Battle art wired: %s" % ornate_path,
			ornate_frame != null and ornate_frame.texture != null and not ornate_frame.draw_center,
			"battle panels must keep their non-blocking nine-slice ornament")
	var battle_backdrop := main_check.get_node_or_null("GameView/BattleBackdrop/Background") as ColorRect
	_assert_true("Battle backdrop is camera independent",
		battle_backdrop != null and battle_backdrop.get_parent() is CanvasLayer and battle_backdrop.color.a >= 0.99,
		"side gutters must use a fixed opaque CanvasLayer instead of the camera-transformed root background")
	_assert_true("HUD has AttackConfirmButton", main_check.get_node_or_null("GameView/HUD/AttackConfirmPanel/ButtonRow/ConfirmBtn") != null,
		"attack confirm panel should expose a confirm action")
	_assert_true("BattleResult has MainlineNextBtn", main_check.get_node_or_null("GameView/HUD/BattleResultPanel/ResultBtnRow/MainlineNextBtn") != null,
		"mainline results should expose a next-battle action")
	_assert_true("MainlineView has MLAbandonBtn", main_check.get_node_or_null("MainlineView/MLFrame/MLAbandonBtn") != null,
		"mainline view should expose an abandon action")
	_assert_true("MainlineView has CommanderOption", main_check.get_node_or_null("MainlineView/MLFrame/CommanderOption") != null,
		"mainline view should expose commander selection")
	_assert_true("MainlineView has ApplyCommanderBtn", main_check.get_node_or_null("MainlineView/MLFrame/ApplyCommanderBtn") != null,
		"mainline view should expose commander apply action")
	_assert_true("MainlineView has MLPrepSummary", main_check.get_node_or_null("MainlineView/MLFrame/MLPrepSummary") != null,
		"mainline view should expose a preparation summary panel")
	_assert_true("MainlineView has MLPrepTabs", main_check.get_node_or_null("MainlineView/MLFrame/MLPrepTabs") != null,
		"mainline view should expose tactical preparation tabs")
	_assert_true("MainlineView has MLPrepContent", main_check.get_node_or_null("MainlineView/MLFrame/MLPrepContent") != null,
		"mainline view should expose preparation content")
	_assert_true("MainlineView has MLPrepStartBtn", main_check.get_node_or_null("MainlineView/MLFrame/MLPrepStartBtn") != null,
		"mainline view should require an explicit start battle action")
	_assert_true("MainlineView has MLPrepRefreshBtn", main_check.get_node_or_null("MainlineView/MLFrame/MLPrepRefreshBtn") != null,
		"mainline view should expose a preparation refresh action")
	_assert_true("MainlineView has MLPrepActionBtn", main_check.get_node_or_null("MainlineView/MLFrame/MLPrepActionBtn") != null,
		"mainline view should expose a context preparation action")
	_assert_true("MainlineView has MLPrepAltActionBtn", main_check.get_node_or_null("MainlineView/MLFrame/MLPrepAltActionBtn") != null,
		"mainline view should expose a secondary preparation action")
	_assert_true("MainlineView has MLPrepHeroSelect", main_check.get_node_or_null("MainlineView/MLFrame/MLPrepSelectorRow/MLPrepHeroSelect") != null,
		"preparation UI should expose a concrete hero selector")
	_assert_true("MainlineView has MLPrepEquipmentSelect", main_check.get_node_or_null("MainlineView/MLFrame/MLPrepSelectorRow/MLPrepEquipmentSelect") != null,
		"preparation UI should expose an equipment warehouse selector")
	_assert_true("MainlineView has MLPrepMercUnitSelect", main_check.get_node_or_null("MainlineView/MLFrame/MLPrepSelectorRow/MLPrepMercUnitSelect") != null,
		"preparation UI should expose a mercenary unit selector")
	_assert_true("MainlineView has MLPrepMercStatSelect", main_check.get_node_or_null("MainlineView/MLFrame/MLPrepSelectorRow/MLPrepMercStatSelect") != null,
		"preparation UI should expose a mercenary stat selector")
	_assert_true("MainlineView has MLPrepShopSelect", main_check.get_node_or_null("MainlineView/MLFrame/MLPrepSelectorRow/MLPrepShopSelect") != null,
		"preparation UI should expose a shop item selector")
	_assert_true("Main can build attack confirm text", main_check.has_method("_build_attack_confirm_text"),
		"attack confirm text should be testable without posting an action")
	_assert_true("Main can build attack forecast info text", main_check.has_method("_build_attack_forecast_info_text"),
		"attack forecast should render in the right-side information panel")
	main_check.call("_show_view", "mainline")
	# P2 Batch A+B:提前定义 mainline_view 引用(批量 redirect 都需要它)
	var mainline_view: Node = main_check.get_node("MainlineView")
	# T:#16 — 章节 cleared 标注测试
	mainline_view.call("_on_ml_list_response", [
		{"id": "chapter_01_steel_rebellion", "title": "钢铁叛乱", "battle_count": 3, "synopsis": "测试"},
		{"id": "chapter_02_eirika", "title": "圣剑之光", "battle_count": 5, "synopsis": "测试"},
	], 200)
	_assert_eq("Mainline list cache holds 2 entries", mainline_view._mainline_list_cache.size(), 2,
		"mainline_controller should cache /mainlines response for cleared join")
	# 模拟 cleared:chapter_01 通关(chapter_index == 2 == battle_count-1)
	mainline_view.call("_on_ml_saves_for_cleared", {
		"manual_slots": [
			{"id": 1, "kind": "manual", "slot_index": 0, "mainline_id": "chapter_01_steel_rebellion", "chapter_index": 2},
		],
		"auto_slot": {"id": 50, "kind": "auto", "slot_index": 0, "mainline_id": "chapter_02_eirika", "label": "chapter_02_eirika-结束", "chapter_index": 5},
		"suspend": null,
	}, 200)
	_assert_true("Cleared set contains chapter_01", mainline_view._cleared_mainline_ids.has("chapter_01_steel_rebellion"),
		"manual slot with chapter_index == battle_count-1 should mark mainline as cleared")
	_assert_true("Cleared set contains chapter_02", mainline_view._cleared_mainline_ids.has("chapter_02_eirika"),
		"auto slot with label ending '-结束' should mark mainline as cleared")
	var ml_list_after: VBoxContainer = mainline_view.get_node("MLFrame/MLListContainer")
	_assert_true("Chapter list renders cleared badge", ml_list_after.get_child_count() > 0 and ml_list_after.get_child(0).text.contains("已通关"),
		"chapter card for cleared mainline should show '已通关' annotation")
	mainline_view.call("_on_mainline_prepare_response", {
		"battle_index": 0,
		"total_battles": 2,
		"inventory": {"gold": 320, "iron_sword": 1},
		"heroes": [{
			"hero_id": "anna",
			"name": "Anna",
			"class_id": "swordsman",
			"level": 4,
			"exp": 32,
			"base_stats": {"hp": 25, "atk": 8, "def": 5, "spd": 7},
			"learned_skills": ["guard"],
			"equipment": {"weapon": "iron_sword"},
			"can_promote": true,
			"promotion_options": ["blade_master"],
		}, {
			"hero_id": "yun",
			"name": "Yun",
			"class_id": "archer",
			"level": 3,
			"exp": 12,
			"base_stats": {"hp": 22, "atk": 7, "def": 3, "spd": 9},
			"learned_skills": ["focus"],
			"equipment": {},
			"can_promote": false,
			"promotion_options": [],
		}],
		"roster_units": [{"name": "Anna", "hero_id": "anna", "class_id": "swordsman", "level": 4}],
		"equipment_catalog": [{
			"equipment_id": "iron_sword",
			"name": "Iron Sword",
			"slot": "weapon",
			"stat_bonuses": {"atk": 2},
		}],
	}, 200, "chapter_test")
	var prep_content: RichTextLabel = main_check.get_node("MainlineView/MLFrame/MLPrepContent")
	var prep_summary: RichTextLabel = main_check.get_node("MainlineView/MLFrame/MLPrepSummary")
	var prep_start: Button = main_check.get_node("MainlineView/MLFrame/MLPrepStartBtn")
	_assert_true("Prepare response renders hero", prep_content.text.contains("Anna"),
		"mainline prepare response should render hero details instead of auto-starting")
	_assert_true("Prepare summary renders gold", prep_summary.text.contains("金币 320"),
		"mainline prepare summary should expose inventory gold")
	_assert_true("Prepare start button enabled", not prep_start.disabled,
		"battle start should become explicit and available after prepare loads")
	var prep_hero_select: OptionButton = main_check.get_node("MainlineView/MLFrame/MLPrepSelectorRow/MLPrepHeroSelect")
	var prep_equipment_select: OptionButton = main_check.get_node("MainlineView/MLFrame/MLPrepSelectorRow/MLPrepEquipmentSelect")
	_assert_gte("Prepare hero selector lists heroes", prep_hero_select.item_count, 2,
		"hero selector should list every prepared hero")
	_assert_gte("Prepare equipment selector lists catalog", prep_equipment_select.item_count, 1,
		"equipment selector should list warehouse items")
	prep_hero_select.select(1)
	mainline_view.call("_on_prepare_hero_selected", 1)
	_assert_true("Prepare hero selector changes sheet", prep_content.text.contains("Yun"),
		"selecting another hero should update the hero paper sheet")
	mainline_view.call("_on_prepare_shop_response", {
		"mainline_id": "chapter_test",
		"gold": 320,
		"items": [{"item_id": "hero_crest", "name": "Hero Crest", "price": 100, "description": "Promote a hero"}],
	}, 200)
	mainline_view.call("_on_prepare_tab_pressed", "shop")
	var prep_shop_select: OptionButton = main_check.get_node("MainlineView/MLFrame/MLPrepSelectorRow/MLPrepShopSelect")
	_assert_gte("Prepare shop selector lists stock", prep_shop_select.item_count, 1,
		"shop selector should list buyable stock")
	_assert_true("Prepare shop renders item", prep_content.text.contains("Hero Crest"),
		"shop tab should render post-battle shop stock")
	mainline_view.call("_on_prepare_mercenary_response", {
		"mainline_id": "chapter_test",
		"balance": {
			"allowed_unit_types": ["swordsman"],
			"stat_rules": {"atk": {"cost": 1, "cap": 3}},
		},
		"allocation": {"unit_type_upgrades": {"swordsman": {"atk": 1}}},
		"mercenary_points": 2,
	}, 200)
	mainline_view.call("_on_prepare_tab_pressed", "mercenary")
	var prep_merc_unit_select: OptionButton = main_check.get_node("MainlineView/MLFrame/MLPrepSelectorRow/MLPrepMercUnitSelect")
	var prep_merc_stat_select: OptionButton = main_check.get_node("MainlineView/MLFrame/MLPrepSelectorRow/MLPrepMercStatSelect")
	_assert_gte("Prepare mercenary unit selector lists types", prep_merc_unit_select.item_count, 1,
		"mercenary unit selector should list configurable unit types")
	_assert_gte("Prepare mercenary stat selector lists stats", prep_merc_stat_select.item_count, 1,
		"mercenary stat selector should list configurable stats")
	_assert_true("Prepare mercenary renders points", prep_content.text.contains("可用点数 2"),
		"mercenary tab should render spendable points")
	var hero_node := UnitNode.new()
	add_child(hero_node)
	hero_node.setup({"unit_type": "swordsman", "hero_id": "anna", "name": "Anna", "hp": 20, "max_hp": 20}, Color(0.8, 0.1, 0.1))
	_assert_true("UnitNode exposes hero badge", hero_node.has_method("has_hero_badge") and bool(hero_node.call("has_hero_badge")),
		"battlefield hero units should render a visible hero badge")
	hero_node.queue_free()
	_setup_action_bubble_state(main_check)
	var action_board: Node = main_check.get_node("GameView/Board")
	var source_screen: Vector2 = action_board.call("tile_to_screen", Vector2i(1, 1))
	main_check.call("_show_action_bubble", 10, source_screen)
	var board_screen_rect: Rect2 = action_board.call("screen_rect")
	var action_bubble: Panel = main_check.get_node("GameView/HUD/ActionBubble")
	_assert_true("Action menu remains inside viewport",
		get_viewport().get_visible_rect().encloses(Rect2(action_bubble.position, action_bubble.size)),
		"crowded edge formations may use a side HUD gutter, but must never leave the viewport")
	_assert_true("Action menu never covers source unit",
		not Rect2(action_bubble.position, action_bubble.size).intersects(Rect2(source_screen - Vector2(36, 36), Vector2(72, 72))),
		"the selected unit must remain visible while choosing its action")
	var action_title: Label = main_check.get_node("GameView/HUD/ActionBubble/ActionTitle")
	_assert_true("Action menu identifies source unit", action_title.text.contains("治疗师"),
		"context menus need a visible identity anchor in addition to their pointer")
	await get_tree().process_frame
	var action_list: VBoxContainer = main_check.get_node("GameView/HUD/ActionBubble/ActionList")
	_assert_true("Action menu content clears ornate border",
		action_list.position.y + action_list.size.y <= action_bubble.size.y - 12.0,
		"dynamic action combinations must not push cancel text into the bottom frame")
	_assert_action_button("Initial bubble keeps move", main_check, "MoveBtn", true,
		"fresh unit should be offered movement")
	_assert_action_button("Initial bubble hides attack without target", main_check, "AttackBtn", false,
		"fresh unit should not show attack when no enemy is in current range")
	_assert_action_button("Initial bubble shows active skill with target", main_check, "SkillBtn", true,
		"fresh healer should show skill when a wounded ally is adjacent")
	_assert_action_button("Initial bubble shows claim on foreign building", main_check, "ClaimBtn", true,
		"fresh unit standing on a claimable foreign building should show claim")
	main_check.call("_show_post_action_bubble", 10, "移动")
	_assert_action_button("Post-move bubble keeps continue move", main_check, "MoveBtn", true,
		"post-move menu should allow continued movement when MP remains")
	var continued_reach: Dictionary = main_check.get("_move_reachable_set")
	_assert_true("Post-move bubble rebuilds reachable cache", continued_reach.size() > 1,
		"a visible continue-move command must retain destinations after immediate feedback clears the old cache")
	var post_move_btn: Button = main_check.get_node("GameView/HUD/ActionBubble/ActionList/MoveBtn")
	_assert_true("Post-move bubble relabels move", post_move_btn.text.contains("继续"),
		"post-move menu should distinguish continuing movement from initial movement")
	_assert_action_button("Post-move bubble still shows skill", main_check, "SkillBtn", true,
		"post-move menu should keep legal active skills")
	_assert_action_button("Post-move bubble keeps claim", main_check, "ClaimBtn", true,
		"post-move menu should keep legal claim")
	var moved_unit: Dictionary = _game_state.get_unit(10)
	moved_unit["has_moved"] = true
	moved_unit["mp"] = 2
	main_check.call("_handle_unit_click", 10, Vector2.ZERO)
	_assert_action_button("Reselected moved unit keeps continue move", main_check, "MoveBtn", true,
		"reselecting a unit with remaining MP must not collapse the menu to wait/cancel")
	_assert_true("Reselected moved unit uses continue label", post_move_btn.text.contains("继续"),
		"the reselected unit should retain post-move action context")
	var reselected_reach: Dictionary = main_check.get("_move_reachable_set")
	var within_remaining_mp := true
	for path_cost in reselected_reach.values():
		if int(path_cost) > 4:
			within_remaining_mp = false
	_assert_true("Continued movement respects remaining MP", within_remaining_mp,
		"reachable preview must use remaining mp=2 rather than the unit's base mov=3")
	main_check.call("_show_action_bubble", 11, Vector2(320, 240))
	_assert_action_button("Attack-ready bubble shows attack", main_check, "AttackBtn", true,
		"unit with an enemy in range should show attack")
	var room_select: OptionButton = main_check.get_node(lobby_join_col + "/RoomSelectOption")
	var room_list: RichTextLabel = main_check.get_node(lobby_join_col + "/RoomList")
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
	var ai_player_option: OptionButton = main_check.get_node(lobby_ai_actions + "/AiPlayerOption")
	var remove_ai_btn: Button = main_check.get_node(lobby_ai_actions + "/LobbyRemoveAiBtn")
	_assert_gte("Lobby AI selector lists AI", ai_player_option.item_count, 1,
		"lobby state should populate removable AI players")
	_assert_true("Lobby remove AI enabled when AI present", not remove_ai_btn.disabled,
		"remove-ai button should enable when there is a selected AI")
	main_check.call("_on_lobby_presets_response", {
		"maps": [{"id": "balanced_4p_20", "name": "balanced_4p_20", "biome": "grass", "recommended_players": 4}]
	}, 200)
	var seat_grid: GridContainer = main_check.get_node(lobby_create_col + "/SeatPanel/SeatGrid")
	_assert_eq("Lobby 4P map renders four seat cards", seat_grid.get_child_count(), 4,
		"seat cards should match selected map player count")
	var first_seat: Panel = seat_grid.get_child(0) as Panel
	var first_seat_label: Label = first_seat.get_node("SeatBox/SeatTopRow/SeatStatusBox/SeatName") as Label
	_assert_true("Lobby first seat uses red faction", first_seat_label.text.contains("红方"),
		"first seat should map to the red starting faction")
	_assert_true("Lobby seat has faction portrait", first_seat.get_node_or_null("SeatBox/SeatTopRow/FactionPortrait") != null,
		"seat card should show a compact faction/portrait block")
	_assert_true("Lobby seat has action button", first_seat.get_node_or_null("SeatBox/SeatControlRow/SeatActionBtn") != null,
		"seat card should expose choose-seat or swap-request action")
	_assert_true("Lobby seat has AI toggle", first_seat.get_node_or_null("SeatBox/SeatControlRow/AiReplaceToggle") != null,
		"seat card should expose AI replacement as a visible toggle")
	_assert_true("Lobby seat has commander ability text", first_seat.get_node_or_null("SeatBox/CommanderAbility") != null,
		"seat card should show the selected commander's basic ability summary")
	var first_team_side: OptionButton = first_seat.get_node_or_null("SeatBox/SeatControlRow/TeamSideOption") as OptionButton
	_assert_true("Lobby seat has side selector", first_team_side != null,
		"seat card should expose Team A/B/C/D independently from faction color")
	if first_team_side != null:
		_assert_eq("Lobby side selector lists four sides", first_team_side.item_count, 4,
			"seat side selector should include Team A/B/C/D")
	var host_settings: Label = main_check.get_node(lobby_create_col + "/HostSettingsLabel") as Label
	var create_room_button: Button = main_check.get_node(lobby_create_col + "/CreateRoomBtn") as Button
	var map_summary_label: RichTextLabel = main_check.get_node(lobby_map_panel + "/MapFactionSummary") as RichTextLabel
	_assert_true("Lobby 4P summary includes yellow faction", map_summary_label.text.contains(str(MAP_PREVIEW_SUMMARY_SCRIPT.COLOR_LABELS.get("yellow", "yellow"))),
		"4P lobby preview should not drop the yellow faction line")
	_assert_true("Lobby 4P summary includes neutral buildings", map_summary_label.text.contains(str(MAP_PREVIEW_SUMMARY_SCRIPT.NEUTRAL_LABEL)),
		"4P lobby preview should show unowned building distribution")
	_assert_true("Lobby 4P keeps host settings visible", host_settings.visible,
		"4P seat cards should not hide the host settings area")
	_assert_true("Lobby 4P keeps create button visible", create_room_button.visible,
		"4P seat cards should not push the create action out of the form")
	_assert_true("Lobby primary action reads start game", create_room_button.text.contains("开启游戏"),
		"the completed create-room form should present the final action as starting the game")
	_assert_gte("Lobby 4P seat card has room for text", int(first_seat.custom_minimum_size.y), 150,
		"4P seat cards should be tall enough that labels do not overlap")
	main_check.set("_user_name", "Alice")
	main_check.call("_on_lobby_seat_action_pressed", 0)
	first_seat = seat_grid.get_child(0) as Panel
	var first_occupant: Label = first_seat.get_node("SeatBox/SeatTopRow/SeatStatusBox/SeatOccupant") as Label
	_assert_true("Lobby seat action shows occupant", first_occupant.text.contains("Alice"),
		"clicking a free seat should update the visible seat card occupant instead of leaving it waiting")
	var ai_personality_option := first_seat.get_node_or_null("SeatBox/AiStyleRow/AiPersonalityOption") as OptionButton
	_assert_true("Lobby seat has AI personality option", ai_personality_option != null,
		"AI replacement should expose a per-seat personality picker")
	_assert_eq("Lobby AI personality option count", ai_personality_option.item_count, 3,
		"per-seat AI personality picker should expose the three rules AI styles")
	main_check.call("_on_lobby_presets_response", {
		"maps": [{"id": "balanced_2p_15", "name": "balanced_2p_15", "biome": "grass", "recommended_players": 2}]
	}, 200)
	_assert_eq("Lobby 2P map renders two seat cards", seat_grid.get_child_count(), 2,
		"seat cards should shrink when selecting a 2P map")
	var prev_tiles: Array = _game_state.tiles
	var prev_players: Array = _game_state.players
	var prev_summary: Dictionary = _game_state.game_summary
	var mock_tiles: Array = []
	for y in range(20):
		for x in range(20):
			mock_tiles.append({"x": x, "y": y, "terrain": "plain"})
	_game_state.tiles = mock_tiles
	_game_state.players = []
	_game_state.game_summary = {"map_biome": "grass"}
	var pseudo_map: Dictionary = main_check.call("_snapshot_to_pseudo_map")
	_game_state.tiles = prev_tiles
	_game_state.players = prev_players
	_game_state.game_summary = prev_summary
	var pseudo_size: Dictionary = pseudo_map.get("size", {}) if pseudo_map.get("size", {}) is Dictionary else {}
	_assert_eq("Snapshot pseudo map width uses full state", int(pseudo_size.get("width", 0)), 20,
		"snapshot adapter should preserve maps larger than 15x15 for the board loader")
	_assert_eq("Snapshot pseudo map height uses full state", int(pseudo_size.get("height", 0)), 20,
		"snapshot adapter should preserve maps larger than 15x15 for the board loader")
	main_check.call("_show_view", "game")
	var game_board: Node = main_check.get_node("GameView/Board")
	game_board.set("_panning", false)
	var pan_press := InputEventMouseButton.new()
	pan_press.button_index = MOUSE_BUTTON_LEFT
	pan_press.pressed = true
	pan_press.position = Vector2(320, 320)
	pan_press.global_position = Vector2(320, 320)
	main_check.call("_unhandled_input", pan_press)
	_assert_true("Main forwards left press to board panning", bool(game_board.get("_panning")),
		"main click handling should not starve Board's left-drag panning state")
	prev_tiles = _game_state.tiles
	_game_state.tiles = [{"x": 3, "y": 4, "terrain": "plain", "subtype": ["连击"]}]
	main_check.call("_refresh_unit_info", {
		"id": 9001,
		"name": "Knight",
		"unit_type": "knight",
		"level": 1,
		"hp": 55,
		"max_hp": 55,
		"x": 3,
		"y": 4,
		"player_id": 1,
		"color": "red",
		"skills": ["double_strike"],
	})
	_game_state.tiles = prev_tiles
	var info_text: String = str(main_check.get_node("GameView/HUD/InfoPanel/UnitInfo").text)
	_assert_true("Unit info tolerates string subtype", info_text.length() > 0,
		"clicking a unit must not crash when the tile subtype is a non-empty string")
	_assert_true("Unit info hides backend hero id", not info_text.contains("Hero ID"),
		"production inspection copy must not expose backend field names")
	var inspect_card: Panel = main_check.get_node("GameView/HUD/InfoPanel")
	var viewport_height: float = get_viewport().get_visible_rect().size.y
	_assert_true("Inspect card stays inside the right HUD wing", inspect_card.size.x <= 460.0 and inspect_card.size.y <= viewport_height * 0.84,
		"unit inspection may use the full right wing but must stop above the bottom action rail")
	_assert_true("Hero portrait is integrated with inspection",
		main_check.hero_portrait_panel.get_parent() == inspect_card,
		"hero identity and unit stats must share one visual card instead of opposite screen edges")
	var previous_co_states: Array = _game_state.co_states
	_game_state.co_states = [{
		"player_id": 1,
		"color": "red",
		"commander_id": null,
		"meter": 0,
		"threshold": 20,
	}]
	main_check.call("_refresh_co_roster")
	await get_tree().process_frame
	var roster_text := ""
	for roster_label in main_check.get_node("GameView/HUD/CORoster").find_children("*", "Label", true, false):
		roster_text += str((roster_label as Label).text)
	_assert_true("CO roster localizes missing commander", roster_text.contains("未任命") and not roster_text.contains("<null>"),
		"top status must replace nullable backend ids with player-facing copy")
	_game_state.co_states = previous_co_states
	main_check.call("_refresh_co_roster")
	main_check.call("_set_unit_info_portrait", "yun")
	var tactical_portrait := main_check.get("_unit_info_portrait_tex") as TextureRect
	_assert_true("Hero selection shows compact portrait",
		main_check.hero_portrait_panel.visible and tactical_portrait != null and tactical_portrait.visible,
		"selecting a hero must reveal the compact tactical portrait card")
	_assert_true("Hero portrait texture is loaded",
		tactical_portrait != null and tactical_portrait.texture != null
			and tactical_portrait.texture.resource_path.ends_with("portrait_yun.png"),
		"the tactical card must load the selected hero's portrait resource")
	_assert_true("Hero portrait stays inside compact card",
		tactical_portrait != null and tactical_portrait.size.x <= main_check.hero_portrait_panel.size.x
			and tactical_portrait.size.y <= main_check.hero_portrait_panel.size.y,
		"portrait art must not recreate the removed full-height sidebar")
	main_check.call("_set_unit_info_portrait", "")
	_assert_true("Non-hero selection hides portrait", not main_check.hero_portrait_panel.visible,
		"ordinary units must not leave stale hero art visible")
	main_check.call("show_dialog", "旁白", "对话遮罩应阻止棋盘输入。")
	_assert_true("Dialog overlay becomes visible", main_check.dialog_overlay.visible,
		"opening dialogue should enable the input-blocking overlay")
	_assert_eq("Dialog overlay blocks mouse input", main_check.dialog_overlay.mouse_filter, Control.MOUSE_FILTER_STOP,
		"dialogue overlay must intercept pointer input before it reaches the board")
	main_check.call("hide_dialog")
	_assert_true("Dialog overlay hides with dialogue", not main_check.dialog_overlay.visible,
		"closing dialogue should restore board interaction")
	main_check.queue_free()

	_assert_eq("BBTypes.UNIT_DEF_KEY", BBTypes.UNIT_DEF_KEY, "def_",
		"Unit.def_ must keep its Python-keyword underscore in JSON wire format")
	_assert_true("GameState autoload", _game_state != null,
		"GameState autoload not registered")
	_assert_true("InputState autoload", _input_state != null,
		"InputState autoload not registered")
	_assert_true("NetworkClient autoload", _network_client != null,
		"NetworkClient autoload not registered")
	_assert_true("UserSettings autoload", _user_settings != null,
		"UserSettings autoload not registered")
	if _network_client == null:
		# Subsequent NetworkClient assertions would crash — short-circuit.
		_fail("NetworkClient autoload missing; skipping method-shape assertions")
	else:
		_assert_true("NetworkClient add_ai_player method", _network_client.has_method("add_ai_player"),
			"NetworkClient should expose a typed add-ai wrapper for the lobby")
		_assert_true("NetworkClient remove_player method", _network_client.has_method("remove_player"),
			"NetworkClient should expose DELETE /games/{id}/players/{player_id}")
		_assert_true("NetworkClient update_player_team method", _network_client.has_method("update_player_team"),
			"NetworkClient should expose PATCH /games/{id}/players/{player_id}/team")
		_assert_true("NetworkClient update_player_seat method", _network_client.has_method("update_player_seat"),
			"NetworkClient should expose PATCH /games/{id}/players/{player_id}/seat")
		_assert_true("NetworkClient forecast_attack method", _network_client.has_method("forecast_attack"),
			"NetworkClient should expose GET /games/{id}/forecast-attack")
		_assert_gte("NetworkClient list_games argument count", _method_arg_count(_network_client, "list_games"), 2,
			"list_games should accept callback and optional user_name filter")
		_assert_gte("NetworkClient join_game argument count", _method_arg_count(_network_client, "join_game"), 6,
			"join_game should accept game_id, user_name, color, team, role, callback")
		_assert_gte("NetworkClient create_game argument count", _method_arg_count(_network_client, "create_game"), 9,
			"create_game should accept optional commander, BGM, AI commander, callback, and seat commander arguments")
		_assert_true("NetworkClient delete_game method", _network_client.has_method("delete_game"),
			"NetworkClient should expose DELETE /games/{id}")
		_assert_true("NetworkClient rejoin_game_by_player_id method", _network_client.has_method("rejoin_game_by_player_id"),
			"NetworkClient should expose player_id based rejoin")
		_assert_true("NetworkClient rejoin_game_by_name method", _network_client.has_method("rejoin_game_by_name"),
			"NetworkClient should expose user_name based rejoin")
		_assert_true("NetworkClient get_game_state method", _network_client.has_method("get_game_state"),
			"NetworkClient should expose GET /games/{id}/state for refreshes")
		_assert_gte("NetworkClient action_recruit argument count", _method_arg_count(_network_client, "action_recruit"), 6,
			"action_recruit should accept game_id, player_id, tile, unit_type, callback")
		_assert_gte("NetworkClient start_mainline argument count", _method_arg_count(_network_client, "start_mainline"), 4,
			"start_mainline should accept mainline_id, user_name, skip_intro, callback")
		_assert_gte("NetworkClient advance_mainline argument count", _method_arg_count(_network_client, "advance_mainline"), 4,
			"advance_mainline should accept mainline_id, user_name, game_id, callback")
		_assert_true("NetworkClient fetch_mainline_dialogue method", _network_client.has_method("fetch_mainline_dialogue"),
			"NetworkClient should expose dialogue fetch for mainline pre/post scenes")
		_assert_true("NetworkClient get_unlocked_commanders method", _network_client.has_method("get_unlocked_commanders"),
			"NetworkClient should expose GET /players/me/commanders")
		_assert_true("NetworkClient select_mainline_commander method", _network_client.has_method("select_mainline_commander"),
			"NetworkClient should expose POST /mainlines/{id}/select-commander")
		_assert_true("NetworkClient list_editor_maps method", _network_client.has_method("list_editor_maps"),
			"NetworkClient should expose GET /editor/maps")
		_assert_true("NetworkClient load_editor_map method", _network_client.has_method("load_editor_map"),
			"NetworkClient should expose GET /editor/maps/{map_id}")
		_assert_true("NetworkClient save_editor_map method", _network_client.has_method("save_editor_map"),
			"NetworkClient should expose POST /editor/maps")
		_assert_true("NetworkClient delete_editor_map method", _network_client.has_method("delete_editor_map"),
			"NetworkClient should expose DELETE /editor/maps/{map_id}")

	main_check.set("_user_name", "Alice")
	main_check.call("_on_list_games_for_resume", [
		{"id": 88, "name": "Save 88", "status": "playing"},
	], 200)
	_assert_eq("Resume picks filtered game summary", int(main_check.get("_resume_game_id")), 88,
		"resume should trust /games?user_name summaries and not require embedded players")
	var resume_btn: Button = main_check.get_node("Menu/CenterContainer/FooterRow/ResumeButton")
	_assert_true("Resume button visible for filtered summary", resume_btn.visible,
		"resume button should appear when a filtered playable save exists")

	# P2 + #16:saves 域已搬到 saves_controller;测试走 saves_view 回调
	# #16 — 改用 /saves 新 schema(manual_slots/auto_slot/suspend),验证 3 槽卡片渲染
	var saves_view: Node = main_check.get_node("SavesView")
	saves_view.call("_on_saves_response", {
		"manual_slots": [
			{"id": 1, "kind": "manual", "slot_index": 0, "label": "第 3 章 - 手动", "mainline_id": "chapter_01_steel_rebellion", "chapter_index": 2},
			{"id": 2, "kind": "manual", "slot_index": 1, "label": "自由战 #42 - 手动", "mainline_id": "", "chapter_index": 0},
		],
		"auto_slot": {"id": 50, "kind": "auto", "slot_index": 0, "label": "chapter_01_steel_rebellion-结束", "mainline_id": "chapter_01_steel_rebellion", "chapter_index": 3},
		"suspend": {"user_name": "Player", "game_id": 77, "mainline_id": "chapter_01_steel_rebellion", "battle_id": "battle_02", "suspend_point": "manual"},
	}, 200)
	# contract test:旧节点保留(visible=false)
	var save_open_list: RichTextLabel = main_check.get_node("SavesView/SaveFrame/SaveOpenList")
	var save_select: OptionButton = main_check.get_node("SavesView/SaveFrame/SaveSelectOption")
	_assert_true("Save manager exposes legacy SaveOpenList node", save_open_list != null,
		"legacy SaveOpenList node should remain in tree for contract test")
	_assert_true("Save manager exposes legacy SaveSelectOption node", save_select != null,
		"legacy SaveSelectOption node should remain in tree for contract test")
	# #16 — 新 3 槽卡片验证
	var save_slots_container: VBoxContainer = main_check.get_node_or_null("SavesView/SaveFrame/SaveSlotsContainer")
	var save_auto_row: PanelContainer = main_check.get_node_or_null("SavesView/SaveFrame/SaveAutoRow")
	var save_suspend_row: PanelContainer = main_check.get_node_or_null("SavesView/SaveFrame/SaveSuspendRow")
	_assert_true("SavesView has SaveSlotsContainer", save_slots_container != null,
		"saves view should expose a slots container for the 3 manual cards")
	_assert_true("SavesView has SaveAutoRow", save_auto_row != null,
		"saves view should expose an auto-save row")
	_assert_true("SavesView has SaveSuspendRow", save_suspend_row != null,
		"saves view should expose a suspend row")
	_assert_eq("SavesView renders 3 manual rows", save_slots_container.get_child_count() if save_slots_container else 0, 3,
		"3 manual slot cards should always be rendered (空/手/自)")
	_assert_true("Auto row renders auto-save label", save_auto_row.get_child_count() > 0 and save_auto_row.get_child(0) is HBoxContainer,
		"auto row should contain an HBox with info + load button when present")
	_assert_true("Suspend row renders suspend info", save_suspend_row.get_child_count() > 0,
		"suspend row should render an HBox with game_id + actions")

	var confirm_text: String = main_check.call("_build_attack_confirm_text", {
		"name": "Knight", "unit_type": "knight", "x": 1, "y": 1, "hp": 10
	}, {
		"defender_name": "Bandit", "unit_type": "swordsman", "x": 3, "y": 2, "hp": 7
	})
	_assert_true("Attack confirm text includes attacker", confirm_text.contains("骑士"),
		"attack confirm text should use the attacker's Chinese unit name")
	_assert_true("Attack confirm text includes target", confirm_text.contains("剑士"),
		"attack confirm text should use the target's Chinese unit name")
	_assert_true("Attack confirm text includes distance", confirm_text.contains("距离 3"),
		"attack confirm text should include Manhattan distance")
	var forecast_text: String = main_check.call("_build_attack_forecast_info_text", {
		"damage": 8,
		"target_hp_after": 2,
		"counter_damage": 3,
		"attacker_hp_after": 7,
		"is_kill": false,
		"counter_will_kill": false,
		"target_def_bonus": 1,
	}, {
		"name": "Knight", "hp": 10, "max_hp": 10
	}, {
		"defender_name": "Bandit", "hp": 10, "max_hp": 10
	})
	_assert_true("Attack forecast text is Chinese", forecast_text.contains("战斗预测") and forecast_text.contains("预计伤害"),
		"forecast panel text should be localized")
	_assert_true("Attack forecast text includes counter", forecast_text.contains("反击 3"),
		"forecast panel text should include counter damage")

	_last_recruit_event = []
	if _game_state == null:
		_fail("GameState autoload missing; skipping recruit event assertions")
	else:
		_game_state.unit_recruited.connect(_capture_recruit_event, CONNECT_ONE_SHOT)
		_game_state.ingest_event({
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
	_assert_true("Recruit response status names unit", main_status_label.text.contains("弓箭手"),
		"recruit success status should include the recruited unit name in Chinese")
	_assert_true("Recruit response status includes remaining gold", main_status_label.text.contains("150"),
		"recruit success status should include remaining gold")

	# P2 Batch A:redirect _on_ml_list_response(已在上面定义 mainline_view)
	mainline_view.call("_on_ml_list_response", [
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
	# P2 Batch A:redirect commander response 到 mainline_view(组件 self)
	mainline_view.call("_on_commanders_response", {
		"user_name": "Alice",
		"unlocked_commanders": ["yun", "anna"],
		"mainline_commanders": {"chapter_01_steel_rebellion": "yun"},
	}, 200)
	var commander_option: OptionButton = main_check.get_node("MainlineView/MLFrame/CommanderOption")
	var lobby_commander_option: OptionButton = main_check.get_node(lobby_create_col + "/LobbyCommanderOption")
	var ai_commander_option: OptionButton = main_check.get_node("Lobby/LobbyFrame/AiCommanderOption")
	var commander_status: Label = main_check.get_node("MainlineView/MLFrame/CommanderStatus")
	_assert_gte("Mainline commander selector lists unlocked choices", commander_option.item_count, 3,
		"commander selector should include none plus unlocked commanders")
	_assert_gte("Lobby commander selector lists unlocked choices", lobby_commander_option.item_count, 3,
		"lobby commander selector should include none plus unlocked commanders")
	_assert_gte("Lobby AI commander selector lists unlocked choices", ai_commander_option.item_count, 3,
		"AI commander selector should include auto plus unlocked commanders")
	main_check.set("_game_id", 0)
	main_check.call("_on_lobby_seat_ai_toggled", true, 1)
	ai_commander_option.select(1)
	var ai_commanders: Dictionary = main_check.call("_selected_lobby_ai_commanders")
	var first_ai_seat := -1
	for seat_index in range(main_check.call("_selected_lobby_player_count")):
		if bool(main_check.call("_lobby_ai_replacement_for_seat", seat_index)):
			first_ai_seat = seat_index
			break
	_assert_eq("Lobby AI commander config targets first AI seat", str(ai_commanders.get(first_ai_seat, "")), "yun",
		"room creation should map the selected AI commander to the first AI replacement seat")
	_assert_true("Mainline commander response shows current choice", commander_status.text.contains("云"),
		"commander response should show the selected commander in Chinese")
	# P2 Batch A:redirect select commander response 到 mainline_view
	mainline_view.call("_on_select_mainline_commander_response", {
		"mainline_id": "chapter_01_steel_rebellion",
		"commander_id": "anna",
	}, 200)
	_assert_true("Mainline commander select response updates status", commander_status.text.contains("安娜"),
		"commander select response should show the applied commander in Chinese")
	main_check.call("_on_audio_tracks_response", {
		"tracks": [
			{"track_id": "sample_battle_01", "title": "Sample Battle", "category": "battle"},
		],
	}, 200)
	var lobby_bgm_option: OptionButton = main_check.get_node(lobby_create_col + "/LobbyBgmOption")
	_assert_gte("Lobby BGM selector lists tracks", lobby_bgm_option.item_count, 2,
		"BGM selector should include none plus backend tracks")
	main_check.call("_on_editor_pressed")
	var editor_view: Control = main_check.get_node("EditorView")
	_assert_true("Editor button switches to editor view", editor_view.visible,
		"pressing the editor button should show the map editor")
	var editor_terrain_option: OptionButton = main_check.get_node("EditorView/EditorPanel/EditorTerrainOption")
	_assert_gte("Editor terrain selector lists brushes", editor_terrain_option.item_count, 5,
		"terrain selector should expose the initial paint brushes")
	var editor_surface_option: OptionButton = main_check.get_node("EditorView/EditorPanel/EditorSurfaceOption")
	var editor_surface_owner_option: OptionButton = main_check.get_node("EditorView/EditorPanel/EditorSurfaceOwnerOption")
	var editor_apply_biome_btn: Button = main_check.get_node("EditorView/EditorPanel/EditorApplyBiomeBtn")
	var editor_mode_option: OptionButton = main_check.get_node("EditorView/EditorPanel/EditorModeOption")
	var editor_unit_tool_option: OptionButton = main_check.get_node("EditorView/EditorPanel/EditorUnitToolOption")
	var editor_unit_option: OptionButton = main_check.get_node("EditorView/EditorPanel/EditorUnitOption")
	var editor_unit_color_option: OptionButton = main_check.get_node("EditorView/EditorPanel/EditorUnitColorOption")
	var editor_unit_level_option: OptionButton = main_check.get_node("EditorView/EditorPanel/EditorUnitLevelOption")
	var editor_width_option: OptionButton = main_check.get_node("EditorView/EditorPanel/EditorWidthOption")
	var editor_height_option: OptionButton = main_check.get_node("EditorView/EditorPanel/EditorHeightOption")
	_assert_eq("Editor mode selector lists three deploy modes", editor_mode_option.item_count, 3,
		"editor mode selector should include terrain, surface, and unit deployment")
	_assert_eq("Editor terrain deploy mode text", editor_mode_option.get_item_text(0), "地形部署",
		"first editor mode should be terrain deployment")
	_assert_eq("Editor surface deploy mode text", editor_mode_option.get_item_text(1), "地表部署",
		"second editor mode should be surface deployment")
	_assert_eq("Editor unit deploy mode text", editor_mode_option.get_item_text(2), "单位部署",
		"third editor mode should be unit deployment")
	_assert_gte("Editor surface selector lists buildings", editor_surface_option.item_count, 4,
		"surface selector should include owned buildings and gates")
	_assert_gte("Editor surface owner selector lists teams", editor_surface_owner_option.item_count, 5,
		"surface owner selector should include unowned plus four teams")
	_assert_gte("Editor unit selector lists unit types", editor_unit_option.item_count, 5,
		"editor unit selector should include deployable unit types")
	_assert_gte("Editor unit tool selector lists tools", editor_unit_tool_option.item_count, 2,
		"editor unit tool selector should include place and erase")
	_assert_gte("Editor width selector lists sizes", editor_width_option.item_count, 4,
		"editor width selector should expose common map sizes")
	_assert_gte("Editor height selector lists sizes", editor_height_option.item_count, 4,
		"editor height selector should expose common map sizes")
	editor_view.call("_on_editor_maps_response", [
		{"id": "map_alpha", "name": "Alpha", "width": 15, "height": 15, "biome": "grass"},
		{"id": "map_beta", "name": "Beta", "width": 15, "height": 15, "biome": "snow"},
	], 200)
	var editor_map_select: OptionButton = main_check.get_node("EditorView/EditorPanel/EditorMapSelectOption")
	_assert_eq("Editor map selector stores backend list", editor_map_select.item_count, 2,
		"editor map response should populate saved maps")
	var editor_delete_btn: Button = main_check.get_node("EditorView/EditorPanel/EditorDeleteBtn")
	_assert_true("Editor delete enables with saved map", not editor_delete_btn.disabled,
		"delete should enable when a saved map is selected")
	editor_map_select.select(1)
	editor_view.call("_on_editor_map_selected", 1)
	_assert_eq("Editor selected map id updates", str(editor_view.get("_selected_editor_map_id")), "map_beta",
		"selecting a saved map should store its id")
	editor_view.call("_on_editor_load_response", {
		"id": "map_beta",
		"name": "Beta",
		"size": {"width": 15, "height": 15},
		"biome": "snow",
		"layout": ["S".repeat(15), "P".repeat(15), "P".repeat(15), "P".repeat(15), "P".repeat(15), "P".repeat(15), "P".repeat(15), "P".repeat(15), "P".repeat(15), "P".repeat(15), "P".repeat(15), "P".repeat(15), "P".repeat(15), "P".repeat(15), "P".repeat(15)],
		"initial_units": [],
	}, 200)
	var loaded_editor_map: Dictionary = editor_view.get("_editor_map")
	_assert_eq("Editor load response replaces current map", str(loaded_editor_map.get("id", "")), "map_beta",
		"loading a saved map should replace the editor map")
	editor_view.call("_on_editor_delete_response", {}, 204)
	_assert_eq("Editor delete clears selected map id", str(editor_view.get("_selected_editor_map_id")), "",
		"successful delete should clear the selected map id")
	editor_mode_option.select(2)
	editor_unit_option.select(1)
	editor_unit_color_option.select(1)
	editor_unit_level_option.select(2)
	editor_view.call("_on_editor_tile_clicked", Vector2i(2, 2))
	var unit_editor_map: Dictionary = editor_view.get("_editor_map")
	var editor_units: Array = unit_editor_map.get("initial_units", [])
	_assert_eq("Editor unit mode places one unit", editor_units.size(), 1,
		"unit mode should add an initial unit at the clicked tile")
	_assert_eq("Editor unit mode stores selected unit type", str((editor_units[0] as Dictionary).get("type", "")), "archer",
		"unit placement should use the selected unit type")
	_assert_eq("Editor unit mode stores selected color", str((editor_units[0] as Dictionary).get("color", "")), "blue",
		"unit placement should use the selected color")
	_assert_eq("Editor unit mode stores selected level", int((editor_units[0] as Dictionary).get("level", 0)), 3,
		"unit placement should use the selected level")
	editor_unit_tool_option.select(1)
	editor_view.call("_on_editor_tile_clicked", Vector2i(2, 2))
	unit_editor_map = editor_view.get("_editor_map")
	editor_units = unit_editor_map.get("initial_units", [])
	_assert_eq("Editor unit erase removes unit", editor_units.size(), 0,
		"unit erase mode should remove the unit at the clicked tile")
	editor_unit_tool_option.select(0)
	editor_mode_option.select(1)
	editor_surface_option.select(1)
	editor_surface_owner_option.select(2)
	editor_view.call("_on_editor_tile_clicked", Vector2i(3, 3))
	unit_editor_map = editor_view.get("_editor_map")
	var surface_layout: Array = unit_editor_map.get("layout", [])
	var tile_owners: Array = unit_editor_map.get("tile_owners", [])
	_assert_true("Editor surface mode paints building", str(surface_layout[3])[3] == "v",
		"surface deployment should paint the selected building char")
	_assert_eq("Editor surface mode stores owner", str((tile_owners[0] as Dictionary).get("color", "")), "blue",
		"surface deployment should store the selected owner color")
	editor_surface_owner_option.select(0)
	editor_view.call("_on_editor_tile_clicked", Vector2i(3, 3))
	unit_editor_map = editor_view.get("_editor_map")
	tile_owners = unit_editor_map.get("tile_owners", [])
	_assert_eq("Editor surface unowned clears owner", tile_owners.size(), 0,
		"painting an unowned surface should remove ownership metadata")
	var editor_biome_option: OptionButton = main_check.get_node("EditorView/EditorPanel/EditorBiomeOption")
	editor_biome_option.select(1)
	editor_apply_biome_btn.pressed.emit()
	unit_editor_map = editor_view.get("_editor_map")
	_assert_eq("Editor biome apply updates map", str(unit_editor_map.get("biome", "")), "snow",
		"one-click biome branch switching should update the editor map immediately")
	editor_width_option.select(1)
	editor_height_option.select(0)
	editor_view.call("_on_editor_resize_pressed")
	unit_editor_map = editor_view.get("_editor_map")
	var editor_size: Dictionary = unit_editor_map.get("size", {})
	var resized_layout: Array = unit_editor_map.get("layout", [])
	_assert_eq("Editor resize updates width", int(editor_size.get("width", 0)), 20,
		"resize should update the saved map width")
	_assert_eq("Editor resize keeps selected height", int(editor_size.get("height", 0)), 15,
		"resize should update the saved map height")
	_assert_eq("Editor resize pads row width", str(resized_layout[0]).length(), 20,
		"resize should pad layout rows to the selected width")
	editor_view.call("_on_editor_save_response", {
		"id": "saved_alpha",
		"name": "Saved Alpha",
		"size": {"width": 15, "height": 15},
		"biome": "desert",
		"layout": ["P".repeat(15), "P".repeat(15), "P".repeat(15), "P".repeat(15), "P".repeat(15), "P".repeat(15), "P".repeat(15), "P".repeat(15), "P".repeat(15), "P".repeat(15), "P".repeat(15), "P".repeat(15), "P".repeat(15), "P".repeat(15), "P".repeat(15)],
		"initial_units": [],
	}, 201)
	var preset_options_after_save: Array = main_check.get("_preset_options")
	_assert_true("Editor save adds custom lobby preset", _preset_options_contain(preset_options_after_save, "custom:saved_alpha"),
		"saving an editor map should immediately expose custom:{id} in lobby presets")
	editor_terrain_option.select(1)
	editor_mode_option.select(0)
	editor_view.call("_paint_editor_tile", Vector2i(1, 1))
	var editor_map: Dictionary = editor_view.get("_editor_map")
	var editor_layout: Array = editor_map.get("layout", [])
	_assert_true("Editor terrain paint updates layout", str(editor_layout[1])[1] == "F",
		"painting with the forest brush should mutate the editor layout")
	var editor_undo_btn: Button = main_check.get_node("EditorView/EditorPanel/EditorUndoBtn")
	var editor_redo_btn: Button = main_check.get_node("EditorView/EditorPanel/EditorRedoBtn")
	_assert_true("Editor undo enables after paint", not editor_undo_btn.disabled,
		"painting should push a history entry that can be undone")
	_assert_true("Editor redo disabled before undo", editor_redo_btn.disabled,
		"redo should stay disabled until an undo is performed")
	editor_view.call("_on_editor_undo_pressed")
	editor_map = editor_view.get("_editor_map")
	editor_layout = editor_map.get("layout", [])
	_assert_true("Editor undo restores terrain", str(editor_layout[1])[1] == "P",
		"undo should restore the previous terrain at the painted tile")
	_assert_true("Editor redo enables after undo", not editor_redo_btn.disabled,
		"undo should make redo available")
	editor_view.call("_on_editor_redo_pressed")
	editor_map = editor_view.get("_editor_map")
	editor_layout = editor_map.get("layout", [])
	_assert_true("Editor redo reapplies terrain", str(editor_layout[1])[1] == "F",
		"redo should reapply the terrain change")

	main_check.set("_user_name", "Alice")
	mainline_view.call("_on_mainline_start_response", {
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

	mainline_view.call("_on_mainline_advance_response", {
		"state": "dialogue",
		"mainline_id": "chapter_01_steel_rebellion",
		"battle_index": 1,
		"total_battles": 2,
		"post_battle_dialogue_url": "dialogue/chapter_01/post_01.json",
	}, 200)
	_assert_true("Mainline advance status includes next progress", main_status_label.text.contains("2/2"),
		"mainline advance should show the next battle progress")
	var ml_next_btn: Button = main_check.get_node("GameView/HUD/BattleResultPanel/ResultBtnRow/MainlineNextBtn")
	# Phase 3 (FE8 auto-advance): non-victory advance no longer reveals
	# the MainlineNextBtn button — instead main.gd immediately calls
	# ``NetworkClient.next_battle_mainline``.  The button stays hidden
	# to match the FE8 chapter-advance invariant (server-driven flow,
	# no UI gate).  See commit f96753b (refactor/extract-mainline-modules).
	_assert_true("Mainline advance hides next battle button (FE8 auto-advance)", not ml_next_btn.visible,
		"non-victory advance should hide the next-battle button — advance now auto-calls NetworkClient.next_battle_mainline")
	mainline_view.call("_on_mainline_next_battle_response", {
		"game_id": 321,
		"player_id": 654,
		"mainline_id": "chapter_01_steel_rebellion",
		"battle_index": 1,
		"total_battles": 2,
		"state": "battle",
	}, 201)
	_assert_eq("Mainline next stores game id", int(main_check.get("_game_id")), 321,
		"next battle should store the spawned game id")
	mainline_view.call("_on_mainline_advance_response", {
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
	mainline_view.call("_on_mainline_abandon_response", {
		"ok": true,
		"mainline_id": "chapter_01_steel_rebellion",
		"abandoned_at": "2026-07-16T00:00:00Z",
	}, 200)
	_assert_eq("Mainline abandon clears active id", str(main_check.get("_active_mainline_id")), "",
		"abandon should clear active mainline state")
	_assert_true("Mainline abandon status is shown", main_status_label.text.contains("放弃"),
		"abandon should update status")
	main_check.call("_on_lobby_team_response", {"ok": true, "player_id": 1, "team": "red"}, 200)
	var lobby_status: Label = main_check.get_node("Lobby/LobbyFrame/LobbyInfoBar/LobbyStatus")
	_assert_true("Lobby team response updates status", lobby_status.text.contains("红队"),
		"team update response should show selected team in Chinese")

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
	var viewport_size := board.get_viewport().get_visible_rect().size
	# The compact inspect card is opt-in.  A fresh board must fit against the
	# whole viewport; selecting a unit then reserves a small right-side area.
	var usable_w: float = viewport_size.x
	# The top status rail owns 112 px and the bottom HUD keeps 16 px clear.
	var usable_h: float = viewport_size.y - 128.0
	var board_pixel_w: float = float(w * MAP_METRICS_SCRIPT.TILE_SIZE.x)
	var board_pixel_h: float = float(h * MAP_METRICS_SCRIPT.TILE_SIZE.y)
	var expected_fit_zoom: float = min(
		(usable_w - 16.0) / board_pixel_w,
		(usable_h - 16.0) / board_pixel_h
	)
	_assert_eq("%s camera zoom matches viewport fit" % map_id, snappedf(board.board_camera.zoom.x, 0.001), snappedf(expected_fit_zoom, 0.001),
		"board camera should fit the full battlefield when no inspect card is open")
	board.board_camera.set_inspect_card_visible(true)
	var inspect_expected_zoom: float = min(
		(viewport_size.x * 0.73 - 16.0) / board_pixel_w,
		(usable_h - 16.0) / board_pixel_h
	)
	_assert_eq("%s camera zoom reserves inspect card" % map_id, snappedf(board.board_camera.zoom.x, 0.001), snappedf(inspect_expected_zoom, 0.001),
		"board camera should reserve only the compact inspect-card width")
	print("  %s - %dx%d biome=%s units=%d" % [
		map_id, w, h, biome, board.units.get_child_count()])
	board.queue_free()


func _test_map_preview_for_all_map_files() -> void:
	var paths: Array[String] = []
	var known_map_path := _map_path_for_id("balanced_2p_15")
	var maps_root := known_map_path.get_base_dir() if known_map_path != "" else ""
	if maps_root != "":
		_collect_map_json_paths(ProjectSettings.globalize_path(maps_root), paths)
	_assert_gte("Map preview scans map files", paths.size(), TEST_MAP_IDS.size(),
		"preview compatibility should cover every checked-in map file")
	for path in paths:
		var f := FileAccess.open(path, FileAccess.READ)
		if f == null:
			_fail("preview cannot open %s" % path)
			continue
		var parsed: Variant = JSON.parse_string(f.get_as_text())
		f.close()
		if not parsed is Dictionary:
			_fail("preview map file is not object: %s" % path)
			continue
		var summary: Dictionary = MAP_PREVIEW_SUMMARY_SCRIPT.summarize_map(parsed)
		_assert_true("Map preview summary has factions %s" % path, summary.has("factions"),
			"preview summary should include faction data for every map file")
		var texture: ImageTexture = MAP_PREVIEW_SUMMARY_SCRIPT.render_preview_texture(parsed, 4)
		_assert_true("Map preview texture exists %s" % path, texture != null,
			"preview texture should render for every map file")


func _collect_map_json_paths(root_path: String, out_paths: Array[String]) -> void:
	var dir := DirAccess.open(root_path)
	if dir == null:
		return
	dir.list_dir_begin()
	while true:
		var name := dir.get_next()
		if name == "":
			break
		if name.begins_with("."):
			continue
		var full_path := "%s/%s" % [root_path, name]
		if dir.current_is_dir():
			_collect_map_json_paths(full_path, out_paths)
		elif name.ends_with(".json"):
			out_paths.append(full_path)
	dir.list_dir_end()


func _preset_options_contain(options: Array, preset_id: String) -> bool:
	for option in options:
		if option is Dictionary and str(option.get("id", "")) == preset_id:
			return true
	return false


func _setup_action_bubble_state(main_check: Node) -> void:
	main_check.set("_player_id", 1)
	if _game_state == null:
		_fail("GameState autoload missing; action-bubble state setup aborted")
		return
	_game_state.local_player_id = 1
	var tiles: Array = []
	for y in range(5):
		for x in range(5):
			tiles.append({"x": x, "y": y, "terrain": "plain", "owner_id": null})
	tiles.append({"x": 1, "y": 1, "terrain": "village", "owner_id": 2})
	_game_state.ingest_snapshot({
		"game": {"id": 900, "status": "playing"},
		"current_player_id": 1,
		"tiles": tiles,
		"players": [
			{
				"id": 1,
				"gold": 500,
				"units": [
					{
						"id": 10,
						"player_id": 1,
						"unit_type": "healer",
						"name": "治疗师",
						"x": 1,
						"y": 1,
						"hp": 30,
						"max_hp": 30,
						"mp": 3,
						"mov": 3,
						"attack_range": 1,
						"min_attack_range": 0,
						"skills": ["heal"],
						"has_acted": false,
						"has_moved": false,
					},
					{
						"id": 12,
						"player_id": 1,
						"unit_type": "swordsman",
						"name": "剑士",
						"x": 2,
						"y": 1,
						"hp": 10,
						"max_hp": 30,
						"mp": 3,
						"mov": 3,
						"attack_range": 1,
						"min_attack_range": 0,
						"skills": [],
						"has_acted": false,
						"has_moved": false,
					},
					{
						"id": 11,
						"player_id": 1,
						"unit_type": "swordsman",
						"name": "剑士",
						"x": 3,
						"y": 3,
						"hp": 30,
						"max_hp": 30,
						"mp": 3,
						"mov": 3,
						"attack_range": 1,
						"min_attack_range": 0,
						"skills": [],
						"has_acted": false,
						"has_moved": false,
					},
				],
			},
			{
				"id": 2,
				"gold": 500,
				"units": [
					{
						"id": 20,
						"player_id": 2,
						"unit_type": "swordsman",
						"name": "敌方剑士",
						"x": 4,
						"y": 3,
						"hp": 30,
						"max_hp": 30,
						"mp": 3,
						"mov": 3,
						"attack_range": 1,
						"min_attack_range": 0,
						"skills": [],
						"has_acted": false,
						"has_moved": false,
					},
				],
			},
		],
	})
	var board: Node = main_check.get_node("GameView/Board")
	board.set("map_size", Vector2i(5, 5))
	var lookup: Dictionary = {}
	for t in tiles:
		lookup[Vector2i(int(t.get("x", 0)), int(t.get("y", 0)))] = t
	board.set("tile_lookup", lookup)


func _assert_action_button(label: String, main_check: Node, button_name: String, expected_visible: bool, msg: String) -> void:
	var btn: Button = main_check.get_node("GameView/HUD/ActionBubble/ActionList/" + button_name)
	_assert_eq(label, btn.visible, expected_visible, msg)


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


func _assert_tiles_fill_48px_regions(ts: TileSet) -> void:
	for terrain in Config.TERRAIN_VARIANT_COUNTS.keys():
		var biome := Config.DEFAULT_BIOME if terrain in Config.BIOME_AWARE_TERRAINS else ""
		var sid: int = TileSetBuilder.source_id_for(String(terrain), biome)
		if sid < 0:
			sid = TileSetBuilder.source_id_for(String(terrain), "")
		_assert_gte("tile source exists(%s)" % terrain, sid, 0,
			"each terrain should resolve to a committed 48px source")
		if sid < 0:
			continue
		var source: TileSetSource = ts.get_source(sid)
		if not (source is TileSetAtlasSource):
			_fail("tile source for %s is not an atlas source" % terrain)
			continue
		var atlas_source: TileSetAtlasSource = source
		var tex: Texture2D = atlas_source.texture
		var img: Image = tex.get_image() if tex != null else null
		_assert_true("tile image exists(%s)" % terrain, img != null and not img.is_empty(),
			"terrain source should expose an image")
		if img == null or img.is_empty():
			continue
		_assert_gte("tile image width(%s)" % terrain, img.get_width(), 48,
			"terrain texture must cover a 48px cell")
		_assert_gte("tile image height(%s)" % terrain, img.get_height(), 48,
			"terrain texture must cover a 48px cell")
		var atlas_coord: Vector2i = TileSetBuilder.atlas_coord_for(String(terrain), biome)
		if atlas_coord != Vector2i(-1, -1):
			var tile_has_pixels := _atlas_tile_has_visible_pixels(img, atlas_coord)
			_assert_true("atlas tile has visible pixels(%s)" % terrain, tile_has_pixels,
				"configured atlas tile should contain visible art in its 48px cell")
		else:
			var bottom_right: Color = img.get_pixel(47, 47)
			_assert_true("tile fills bottom-right(%s)" % terrain, bottom_right.a > 0.05,
				"48px tile region should not leave transparent padding")
		var center: Color = img.get_pixel(24, 24)
		_assert_true("tile avoids debug fill(%s)" % terrain, not _is_debug_magenta(center),
			"missing tile assets should fall back to real terrain art, not debug color")


func _atlas_tile_has_visible_pixels(img: Image, atlas_coord: Vector2i) -> bool:
	var x0 := atlas_coord.x * MAP_METRICS_SCRIPT.TILE_SIZE.x
	var y0 := atlas_coord.y * MAP_METRICS_SCRIPT.TILE_SIZE.y
	for y in range(y0, min(y0 + MAP_METRICS_SCRIPT.TILE_SIZE.y, img.get_height())):
		for x in range(x0, min(x0 + MAP_METRICS_SCRIPT.TILE_SIZE.x, img.get_width())):
			if img.get_pixel(x, y).a > 0.05:
				return true
	return false


func _assert_new_tileset_atlas_sources(ts: TileSet) -> void:
	var checks := {
		"plain|": {
			"path": "res://assets/tilesets/base_terrain_roads.png",
			"coord": Vector2i(0, 0),
		},
		"road|": {
			"path": "res://assets/tilesets/base_terrain_roads.png",
			"coord": Vector2i(0, 1),
		},
		"village|": {
			"path": "res://assets/tilesets/village_castle_mountains.png",
			"coord": Vector2i(0, 0),
		},
		"forest|grass": {
			"path": "res://assets/tilesets/trees_mountains.png",
			"coord": Vector2i(0, 0),
		},
	}
	for key in checks.keys():
		var parts := String(key).split("|", false)
		var terrain := String(parts[0])
		var biome := String(parts[1]) if parts.size() > 1 else ""
		var sid: int = TileSetBuilder.source_id_for(terrain, biome)
		_assert_gte("atlas source id(%s)" % key, sid, 0,
			"terrain should resolve to the committed atlas sheet")
		if sid < 0:
			continue
		var source: TileSetSource = ts.get_source(sid)
		if not (source is TileSetAtlasSource):
			_fail("atlas source for %s is not TileSetAtlasSource" % key)
			continue
		var atlas_source: TileSetAtlasSource = source
		_assert_eq("atlas source path(%s)" % key, atlas_source.resource_name, str(checks[key]["path"]),
			"terrain should keep a stable atlas source path for resource replacement")
		var coords: Array = TileSetBuilder.atlas_coords_for(terrain, biome)
		_assert_true("atlas coord pool(%s)" % key, coords.has(checks[key]["coord"]),
			"terrain should include the documented tile inside the new atlas sheet")


func _assert_unit_sprite_preserves_aspect() -> void:
	var tex: Texture2D = UnitNode._load_png("res://assets/classic/archer.png", 48)
	_assert_true("unit sprite texture loads", tex != null, "classic unit sprite should load")
	if tex == null:
		return
	var img: Image = tex.get_image()
	_assert_eq("unit sprite canvas width", img.get_width(), 48, "sprite canvas should match one tile")
	_assert_eq("unit sprite canvas height", img.get_height(), 48, "sprite canvas should match one tile")
	var bounds := _alpha_bounds(img)
	_assert_true("unit sprite has alpha bounds", bounds.size != Vector2i.ZERO,
		"sprite should contain visible pixels")
	if bounds.size != Vector2i.ZERO:
		_assert_true("unit sprite preserves tall silhouette", bounds.size.y > bounds.size.x,
			"classic unit portraits should be fit proportionally, not stretched square")
	var unit := UnitNode.new()
	unit.setup({"unit_type": "archer", "hp": 10, "max_hp": 10}, Color.RED)
	var marker: ColorRect = unit.get("_marker")
	_assert_true("unit sprite hides square marker", marker != null and not marker.visible,
		"units with committed sprite art should not show a pure team-color square")
	unit.queue_free()


func _alpha_bounds(img: Image) -> Dictionary:
	var min_x := img.get_width()
	var min_y := img.get_height()
	var max_x := -1
	var max_y := -1
	for y in range(img.get_height()):
		for x in range(img.get_width()):
			if img.get_pixel(x, y).a <= 0.05:
				continue
			min_x = min(min_x, x)
			min_y = min(min_y, y)
			max_x = max(max_x, x)
			max_y = max(max_y, y)
	if max_x < min_x or max_y < min_y:
		return {"position": Vector2i.ZERO, "size": Vector2i.ZERO}
	return {
		"position": Vector2i(min_x, min_y),
		"size": Vector2i(max_x - min_x + 1, max_y - min_y + 1),
	}


func _is_debug_magenta(color: Color) -> bool:
	return color.r > 0.95 and color.g < 0.05 and color.b > 0.95 and color.a > 0.95


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
