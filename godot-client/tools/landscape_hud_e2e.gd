extends Node
## 隔离测试地图上的正式REST/WS实战验收，禁止使用伪造预测。
var main: Node
var hud: Control
var map_id := ""
var game_id := 0
var attacker := 0
var target := 0
var saved_api: Variant
var saved_ws: Variant
var last_body: Variant
var last_code := 0
var waiting := false
var out := "res://.refactor_shots/landscape_e2e/"

func _ready() -> void:
	OS.set_environment("BB_AUTO_PLAY", "0")
	saved_api = UserSettings.get_value("server.api_base", "http://127.0.0.1:8000")
	saved_ws = UserSettings.get_value("server.ws_base", "ws://127.0.0.1:8000")
	UserSettings.set_value("server.api_base", "http://127.0.0.1:8000")
	UserSettings.set_value("server.ws_base", "ws://127.0.0.1:8000")
	main = get_node("Main")
	await _frames(5)
	hud = main.landscape_hud
	map_id = "landscape_e2e_%d_%d" % [Time.get_unix_time_from_system(), OS.get_process_id()]
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(out))
	var result := await _request("POST", "/editor/maps", _map())
	if not await _check(result.code == 200 or result.code == 201, "map save %s" % result): return
	result = await _request("POST", "/games", {"name": map_id, "map_preset": "custom:"+map_id, "map_biome": "grass", "win_condition": "rout"})
	game_id = int(result.body.get("id", result.body.get("game_id", 0))) if result.body is Dictionary else 0
	if not await _check(game_id > 0, "create game %s" % result): return
	for color in ["red", "blue"]:
		result = await _request("POST", "/games/%d/join" % game_id, {"user_name": "HUD验收_"+color, "color": color})
		if not await _check(result.code >= 200 and result.code < 300, "join %s" % result): return
	result = await _request("POST", "/games/%d/start" % game_id, {})
	if not await _check(result.code >= 200 and result.code < 300, "start %s" % result): return
	await _poll()
	var player := int(GameState.current_player_id)
	main._game_id = game_id
	main._player_id = player
	GameState.local_player_id = player
	main._show_view("game")
	NetworkClient.connect_to_game(game_id, player)
	await _frames(15)
	await _poll()
	for p in GameState.players:
		for u in p.get("units", []):
			if int(p.id) == player: attacker = int(u.id)
			else: target = int(u.id)
	if not await _check(attacker > 0 and target > 0, "server units unavailable"): return
	await _dismiss_dialogs()
	main._handle_unit_click(attacker, Vector2.ZERO)
	await _frames(4)
	if not await _check(hud._active_unit_id() == attacker and hud.portrait.texture != null and hud.art.texture != null, "selected portrait/art"): return
	await _shot("01_selected")
	main._on_move_pressed()
	await _frames(3)
	if not await _check(hud._active_unit_id() == attacker and hud.portrait.visible, "move mode lost attacker"): return
	main._on_board_tile_clicked(Vector2i(3,2))
	var deadline := Time.get_ticks_msec()+12000
	while Time.get_ticks_msec() < deadline:
		await _poll()
		var u := GameState.get_unit(attacker)
		if int(u.get("x", -1)) == 3 and str(GameState.get_tile(3,2).get("terrain", "")) == "forest": break
		await get_tree().create_timer(0.2).timeout
	var moved := GameState.get_unit(attacker)
	if not await _check(int(moved.get("x", -1)) == 3 and int(moved.get("y", -1)) == 2, "server move timeout"): return
	await _frames(6)
	if not await _check(hud.last_art == "forest" and hud.art.texture != null, "terrain art did not update"): return
	var mp := float(moved.get("mp", -1))
	if not await _check(not is_equal_approx(mp, roundf(mp)) and hud.vitality.text.contains(str(mp)), "server fractional MP missing: %s / %s" % [moved, hud.vitality.text]): return
	print("HUD_E2E move server position=(3,2), mp=%s, art=%s" % [mp, hud.last_art])
	await _shot("02_moved_forest")
	main._on_attack_pressed()
	await _frames(3)
	if not await _check(hud._active_unit_id() == attacker and hud.portrait.visible, "attack mode lost attacker"): return
	main._show_attack_confirm(attacker, target)
	if not await _forecast(): return
	await _shot("03_forecast")
	main._on_attack_cancel_pressed()
	await _frames(3)
	if not await _check(not hud.prediction.visible and hud._active_unit_id() == attacker, "cancel did not restore attacker"): return
	await _shot("04_cancel")
	main._on_attack_pressed()
	main._show_attack_confirm(attacker, target)
	if not await _forecast(): return
	var before: Dictionary = GameState.get_unit(target).duplicate()
	main._on_attack_confirm_pressed()
	deadline = Time.get_ticks_msec()+12000
	var after: Dictionary
	while Time.get_ticks_msec() < deadline:
		await _poll()
		after = GameState.get_unit(target)
		if after.is_empty() or int(after.hp) < int(before.hp): break
		await get_tree().create_timer(0.2).timeout
	if not await _check(after.is_empty() or int(after.get("hp", 99999)) < int(before.hp), "server attack HP did not change"): return
	await _frames(8)
	var actual := GameState.get_unit(attacker)
	if not await _check(hud._active_unit_id() == attacker and hud.vitality.text.contains("HP  %s /" % hud._number(actual, "hp")), "HUD HP differs from authoritative attacker HP"): return
	print("HUD_E2E attack target HP %s -> %s; attacker HP=%s; HUD=%s" % [before.hp, after.get("hp", 0), actual.hp, hud.vitality.text])
	await _shot("05_attacked")
	var window_size := get_viewport().get_texture().get_image().get_size()
	var evidence := {"status":"PASS", "game_id":game_id, "physical_resolution":str(window_size), "server_move_position":[int(moved.x), int(moved.y)], "server_move_mp":mp, "terrain_art":"forest", "target_hp_before":before.hp, "target_hp_after":after.get("hp",0), "attacker_hp_after":actual.hp, "hud_text":hud.vitality.text, "forecast_source":"official REST", "map_cleanup_scope":map_id}
	var record := FileAccess.open(out+"result_%dx%d.json" % [window_size.x, window_size.y], FileAccess.WRITE)
	record.store_string(JSON.stringify(evidence, "  "))
	record.close()
	print("LANDSCAPE_HUD_E2E PASS game=%d resolution=%s" % [game_id, get_viewport().get_visible_rect().size])
	await _finish(0)

func _poll() -> void:
	var response := await _request("GET", "/games/%d/state" % game_id, {})
	if response.code == 200:
		main._on_state_poll_response(response.body, response.code)

func _forecast() -> bool:
	var deadline := Time.get_ticks_msec()+12000
	while Time.get_ticks_msec() < deadline:
		if main.unit_info.text.contains("预计伤害"):
			await _frames(3)
			return await _check(hud.prediction.visible and hud.prediction.text.contains("预计伤害"), "forecast not reflected in HUD")
		await get_tree().process_frame
	return await _check(false, "real forecast timeout: "+main.unit_info.text)

func _request(method: String, path: String, body: Dictionary) -> Dictionary:
	last_body = null
	last_code = 0
	waiting = true
	var http := HTTPRequest.new()
	add_child(http)
	http.timeout = 10.0
	http.request_completed.connect(func(_result, code, _headers, payload):
		last_body = JSON.parse_string(payload.get_string_from_utf8()) if not payload.is_empty() else {}
		last_code = code
		waiting = false
	)
	http.request("http://127.0.0.1:8000"+path, ["Content-Type: application/json"], NetworkClient._method_to_enum(method), JSON.stringify(body) if not body.is_empty() else "")
	var deadline := Time.get_ticks_msec()+12000
	while waiting and Time.get_ticks_msec() < deadline:
		await get_tree().process_frame
	http.queue_free()
	return {"body": last_body, "code": last_code}

func _check(ok: bool, message: String) -> bool:
	if not ok:
		printerr("HUD_E2E FAIL "+message)
		await _shot("failure")
		await _finish(1)
	return ok

func _finish(code: int) -> void:
	if map_id != "": await _request("DELETE", "/editor/maps/"+map_id, {})
	UserSettings.set_value("server.api_base", saved_api)
	UserSettings.set_value("server.ws_base", saved_ws)
	get_tree().quit(code)

func _frames(count: int) -> void:
	for i in count: await get_tree().process_frame

func _shot(label: String) -> void:
	await _dismiss_dialogs()
	await RenderingServer.frame_post_draw
	var image := get_viewport().get_texture().get_image()
	image.save_png(out+"%s_%dx%d.png" % [label, image.get_width(), image.get_height()])

func _map() -> Dictionary:
	var rows: Array = []
	var heights: Array = []
	for y in 15:
		rows.append("PPPFPPPPPPPPPPP" if y==2 else "PPPPPPPPPPPPPPP")
		var line: Array = []
		for x in 15: line.append(1 if x==3 and y==2 else 0)
		heights.append(line)
	return {"id":map_id,"name":"底栏隔离实战验收","biome":"grass","size":{"width":15,"height":15},"recommended_players":2,"layout":rows,"elevations":heights,"initial_units":[{"x":2,"y":2,"type":"swordsman","color":"red","level":1},{"x":4,"y":2,"type":"swordsman","color":"blue","level":1}]}


func _dismiss_dialogs() -> void:
	# 与用户点击继续相同的推进路径，防止旁白遮住被验收的底栏。
	for i in 24:
		if not DialogManager.is_playing(): return
		DialogManager._advance()
		await get_tree().process_frame
