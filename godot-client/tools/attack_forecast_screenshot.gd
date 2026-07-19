extends Node
## 进入近距离测试局，打开攻击确认，等待右侧战斗预测后截图。
##
## 前置条件：FastAPI 后端监听 127.0.0.1:8000。

const _MAP_ID := "codex_forecast_screenshot"
const _OUT_USER := "user://attack_forecast_screenshot.png"
const _OUT_RES := "res://attack_forecast_screenshot.png"
const _WAIT_SEC := 8.0
const _DEFAULT_API_BASE := "http://127.0.0.1:8000"
const _DEFAULT_WS_BASE := "ws://127.0.0.1:8000"

var _last_body: Variant = null
var _last_code: int = 0
var _waiting: bool = false


func _ready() -> void:
	OS.set_environment("BB_AUTO_PLAY", "1")
	UserSettings.set_value("server.api_base", "http://127.0.0.1:8010")
	UserSettings.set_value("server.ws_base", "ws://127.0.0.1:8010")
	for i in 3:
		await RenderingServer.frame_post_draw
	var main_app: Node = get_tree().current_scene
	if main_app.name == "AttackForecastScreenshot":
		main_app = main_app.get_child(0) if main_app.get_child_count() > 0 else main_app
	if main_app == null:
		printerr("找不到主场景")
		_quit(1)
		return

	var saved := await _request("POST", "/editor/maps", _forecast_map())
	if int(saved.get("code", 0)) < 200 or int(saved.get("code", 0)) >= 300:
		printerr("保存预测截图地图失败: %s %s" % [str(saved.get("code", 0)), str(saved.get("body", {}))])
		_quit(1)
		return

	var created := await _request("POST", "/games", {
		"name": "预测截图测试",
		"map_preset": "custom:%s" % _MAP_ID,
		"map_biome": "grass",
		"win_condition": "rout",
	})
	var game_body: Dictionary = created.get("body", {}) if created.get("body", {}) is Dictionary else {}
	var game_id := int(game_body.get("id", game_body.get("game_id", 0)))
	if game_id <= 0:
		printerr("创建预测截图房间失败")
		_quit(1)
		return
	print("预测截图房间: %d" % game_id)

	var joined := await _request("POST", "/games/%d/join" % game_id, {"user_name": "截图玩家", "color": "red"})
	var join_body: Dictionary = joined.get("body", {}) if joined.get("body", {}) is Dictionary else {}
	var player_id := int(join_body.get("id", join_body.get("player_id", 0)))
	if player_id <= 0:
		var player: Variant = join_body.get("player", {})
		if player is Dictionary:
			player_id = int(player.get("id", 0))
	if player_id <= 0:
		printerr("加入预测截图房间失败")
		_quit(1)
		return

	await _request("POST", "/games/%d/add-ai" % game_id, {
		"difficulty": "normal",
		"agent_kind": "rules",
		"personality": "balanced",
	})
	await _request("POST", "/games/%d/start" % game_id, {})

	main_app.set("_game_id", game_id)
	main_app.set("_player_id", player_id)
	GameState.local_player_id = player_id
	main_app.call("_show_view", "game")
	NetworkClient.connect_to_game(game_id, player_id)
	NetworkClient.get_game_state(game_id, Callable(main_app, "_on_state_poll_response"))

	var deadline := Time.get_ticks_msec() + int(_WAIT_SEC * 1000.0)
	while Time.get_ticks_msec() < deadline:
		if GameState.players.size() > 0 and GameState.tiles.size() > 0:
			break
		await RenderingServer.frame_post_draw
	if GameState.current_player_id != null:
		player_id = int(GameState.current_player_id)
		main_app.set("_player_id", player_id)
		GameState.local_player_id = player_id

	var board: Node = main_app.get("board") if main_app.get("board") != null else main_app.find_child("Board", true, false)
	if board == null:
		printerr("找不到棋盘")
		_quit(1)
		return
	var attacker_id := _find_unit_id(true, "swordsman")
	var target_id := _find_unit_id(false, "swordsman")
	print("预测截图单位: attacker=%d target=%d player=%d" % [attacker_id, target_id, player_id])
	if attacker_id <= 0 or target_id <= 0:
		printerr("找不到预测截图所需单位")
		_quit(1)
		return

	board.emit_unit_clicked(attacker_id)
	for i in 4:
		await RenderingServer.frame_post_draw
	var attack_btn: Button = main_app.get_node_or_null("GameView/HUD/ActionBubble/ActionList/AttackBtn")
	if attack_btn != null and is_instance_valid(attack_btn):
		attack_btn.pressed.emit()
	for i in 4:
		await RenderingServer.frame_post_draw
	main_app.call("_show_attack_confirm", attacker_id, target_id)
	var direct_forecast := await _request(
		"GET",
		"/games/%d/forecast-attack?player_id=%d&attacker_id=%d&target_id=%d" % [
			game_id, player_id, attacker_id, target_id,
		],
		{}
	)
	var forecast_body: Dictionary = direct_forecast.get("body", {}) if direct_forecast.get("body", {}) is Dictionary else {}
	print("预测接口直连: %s 伤害=%d 反击=%d" % [
		str(direct_forecast.get("code", 0)),
		int(forecast_body.get("damage", 0)),
		int(forecast_body.get("counter_damage", 0)),
	])

	var info_label: RichTextLabel = main_app.get_node_or_null("GameView/HUD/InfoPanel/UnitInfo")
	deadline = Time.get_ticks_msec() + int(_WAIT_SEC * 1000.0)
	while Time.get_ticks_msec() < deadline:
		if info_label != null and is_instance_valid(info_label):
			var text := info_label.text
			if text.contains("战斗预测") and text.contains("预计伤害"):
				break
		await RenderingServer.frame_post_draw

	for i in 4:
		await RenderingServer.frame_post_draw
	var img := get_viewport().get_texture().get_image()
	if img == null:
		printerr("截图失败")
		_quit(1)
		return
	img.save_png(_OUT_USER)
	img.save_png(_OUT_RES)
	await _request("DELETE", "/editor/maps/%s" % _MAP_ID.uri_encode(), {})
	print("保存战斗预测截图 -> %s" % _OUT_USER)
	_quit(0)


func _request(method: String, path: String, body: Dictionary) -> Dictionary:
	_last_body = null
	_last_code = 0
	_waiting = true
	NetworkClient.request(method, path, body, Callable(self, "_on_response"))
	var deadline := Time.get_ticks_msec() + int(_WAIT_SEC * 1000.0)
	while _waiting and Time.get_ticks_msec() < deadline:
		await RenderingServer.frame_post_draw
	return {"body": _last_body, "code": _last_code}


func _quit(code: int) -> void:
	UserSettings.set_value("server.api_base", _DEFAULT_API_BASE)
	UserSettings.set_value("server.ws_base", _DEFAULT_WS_BASE)
	if UserSettings.has_method("_save"):
		UserSettings.call("_save")
	get_tree().quit(code)


func _on_response(body: Variant, code: int = 0) -> void:
	_last_body = body
	_last_code = code
	_waiting = false


func _find_unit_id(own: bool, unit_type: String) -> int:
	for player in GameState.players:
		if not (player is Dictionary):
			continue
		var is_own_player := int(player.get("id", -1)) == GameState.local_player_id
		if is_own_player != own:
			continue
		for raw_unit in player.get("units", []):
			if not (raw_unit is Dictionary):
				continue
			var unit: Dictionary = raw_unit
			if str(unit.get("unit_type", "")) == unit_type:
				return int(unit.get("id", 0))
	return 0


func _forecast_map() -> Dictionary:
	return {
		"id": _MAP_ID,
		"name": "预测截图测试图",
		"description": "自动化截图使用的近距离测试图",
		"biome": "grass",
		"size": {"width": 15, "height": 15},
		"recommended_players": 2,
		"layout": [
			"PPPPPPPPPPPPPPP",
			"PPPPPPPPPPPPPPP",
			"PPPPPPPPPPPPPPP",
			"PPPPPPPPPPPPPPP",
			"PPPPPPPPPPPPPPP",
			"PPPPPPPPPPPPPPP",
			"PPPPPPPPPPPPPPP",
			"PPPPPPPPPPPPPPP",
			"PPPPPPPPPPPPPPP",
			"PPPPPPPPPPPPPPP",
			"PPPPPPPPPPPPPPP",
			"PPPPPPPPPPPPPPP",
			"PPPPPPPPPPPPPPP",
			"PPPPPPPPPPPPPPP",
			"PPPPPPPPPPPPPPP",
		],
		"initial_units": [
			{"x": 2, "y": 2, "type": "swordsman", "color": "red", "level": 1},
			{"x": 3, "y": 2, "type": "swordsman", "color": "blue", "level": 1},
		],
	}
