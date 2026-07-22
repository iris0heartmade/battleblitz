extends Node
## recruit_e2e.gd — 验证兵营招募 e2e:
##   1) 启游戏(create + join + add_ai + start)
##   2) 等 WS snapshot 填充 GameState.tiles + players
##   3) 找 alice 拥有的空兵营;若该 cell 被自己单位占,先 move knight 走
##   4) 断言 GameState.players[].units[].x/y 在 move event 后**立即**更新(修前是 stale)
##   5) 调 _pick_empty_my_barracks(屏幕坐标) 验证返回非空 dict
##   6) 调 _show_recruit_at + 断言 recruit_panel.visible == true
##   7) POST /recruit 一个 swordsman + 断言 GameState cache 追加新单位
##   8) 截图
##
## 跑法:
##   Godot_v4.7-stable_win64_console.exe --path godot-client res://tools/recruit_e2e.tscn

const _MAP_PRESET := "balanced_2p_15"
const _MAP_BIOME  := "grass"
const _WIN_COND   := "rout"
const _SETUP_TIMEOUT_SEC := 30.0
const _MOVE_WAIT_SEC      := 3.0
const _RECRUIT_WAIT_SEC   := 3.0

var _user_name: String = ""
var _game_id: int = 0
var _player_id: int = 0
var _logf: FileAccess = null

# Verification state
var _empty_barracks_cell: Vector2i = Vector2i(-1, -1)
var _barracks_tile_data: Dictionary = {}
var _stale_after_move: bool = false   # true if bug present
var _panel_shown: bool = false
var _recruit_posted: bool = false
var _new_unit_in_cache: bool = false
var _new_unit_id: int = -1


func _ready() -> void:
	_user_name = "e2e_recruit_%d_%d" % [Time.get_ticks_msec(), randi() % 10000]
	_logf = FileAccess.open("user://recruit_e2e.log", FileAccess.WRITE)
	_log("=== recruit e2e: GameState 缓存同步 + 招募面板验证 ===")
	_log("user=%s backend 127.0.0.1:8000 | godot %s" %
			[_user_name, Engine.get_version_info().get("string", "?")])
	var gs: Node = get_node_or_null("/root/GameState")
	var nc: Node = get_node_or_null("/root/NetworkClient")
	if gs == null or nc == null:
		_finish(false, "autoload 缺失"); return
	gs.unit_moved.connect(_on_unit_moved)

	# 优先用环境变量 BB_GAME_ID + BB_PLAYER_ID(由 setup 脚本 curl 创建/join/start)
	var env_gid: String = OS.get_environment("BB_GAME_ID")
	var env_pid: String = OS.get_environment("BB_PLAYER_ID")
	if env_gid != "" and env_pid != "":
		_game_id = int(env_gid)
		_player_id = int(env_pid)
		gs.local_player_id = _player_id
		_log("[skip setup] 用环境变量 BB_GAME_ID=%d BB_PLAYER_ID=%d" % [_game_id, _player_id])
		# 直接连 WS(已 start 过)
		nc.connect_to_game(_game_id, _player_id)
		_run_setup_phase()
		return

	_log("[1] create_game...")
	nc.create_game("e2e_recruit_room_%d" % Time.get_ticks_msec(),
			_MAP_PRESET, _MAP_BIOME, _WIN_COND, "", "", {}, Callable(self, "_on_created"))


func _on_created(body: Variant, code: int) -> void:
	if not (body is Dictionary) or int(body.get("id", 0)) <= 0:
		_finish(false, "create_game 失败: %s" % str(body).substr(0, 200)); return
	_game_id = int(body.get("id", 0))
	_log("[1] OK game=#%d" % _game_id)
	# 等 server commit(创建后立即 join 可能 race condition)
	await get_tree().create_timer(0.8).timeout
	var nc: Node = get_node("/root/NetworkClient")
	nc.join_game(_game_id, _user_name, "red", "", "", Callable(self, "_on_joined"))


func _on_joined(body: Variant, code: int) -> void:
	var pid: int = 0
	if body is Dictionary:
		pid = int(body.get("id", body.get("player_id", 0)))
	if pid <= 0:
		_finish(false, "join_game 失败: %s" % str(body).substr(0, 200)); return
	_player_id = pid
	var gs: Node = get_node("/root/GameState")
	gs.local_player_id = _player_id
	_log("[2] OK pid=#%d" % _player_id)
	var nc: Node = get_node("/root/NetworkClient")
	nc.add_ai_player(_game_id, "normal", "rules", "balanced", Callable(self, "_on_ai_added"))


func _on_ai_added(body: Variant, code: int) -> void:
	if int(code) not in [200, 201]:
		_finish(false, "add_ai 失败: code=%d" % code); return
	_log("[3] OK AI 已加")
	var nc: Node = get_node("/root/NetworkClient")
	nc.start_game(_game_id, Callable(self, "_on_started"))


func _on_started(body: Variant, code: int) -> void:
	if int(code) not in [200, 201]:
		_finish(false, "start_game 失败: code=%d" % code); return
	_log("[4] OK 对局已开 → connect WS")
	var nc: Node = get_node("/root/NetworkClient")
	nc.connect_to_game(_game_id, _player_id)
	_run_setup_phase()


# 等 snapshot + 找我的空兵营
func _run_setup_phase() -> void:
	var gs: Node = get_node("/root/GameState")
	var nc: Node = get_node("/root/NetworkClient")
	var deadline: float = Time.get_ticks_msec() / 1000.0 + _SETUP_TIMEOUT_SEC
	while Time.get_ticks_msec() / 1000.0 < deadline:
		if gs.tiles.size() > 0 and gs.players.size() >= 2:
			# 找我自己拥有的空兵营
			for t in gs.tiles:
				if not (t is Dictionary): continue
				if str(t.get("terrain", "")) != "barracks": continue
				if int(t.get("owner_id", -1)) != _player_id: continue
				var tx: int = int(t.get("x", -1))
				var ty: int = int(t.get("y", -1))
				var occ: bool = false
				for p in gs.players:
					if not (p is Dictionary): continue
					for u in p.get("units", []):
						if u is Dictionary and int(u.get("x", -1)) == tx and int(u.get("y", -1)) == ty:
							occ = true; break
					if occ: break
				if not occ:
					_empty_barracks_cell = Vector2i(tx, ty)
					_barracks_tile_data = t
					break
			if _empty_barracks_cell.x >= 0:
				break
		await get_tree().create_timer(0.3).timeout
	if _empty_barracks_cell.x < 0:
		_log(">>> 没找到空兵营,找一个被自己单位驻守的兵营,先把单位移开再测")
		# 找被自己单位驻守的兵营
		for t in gs.tiles:
			if not (t is Dictionary): continue
			if str(t.get("terrain", "")) != "barracks": continue
			if int(t.get("owner_id", -1)) != _player_id: continue
			var tx2: int = int(t.get("x", -1))
			var ty2: int = int(t.get("y", -1))
			for p in gs.players:
				if int(p.get("id", -1)) != _player_id: continue
				for u in p.get("units", []):
					if u is Dictionary and int(u.get("x", -1)) == tx2 and int(u.get("y", -1)) == ty2:
						_empty_barracks_cell = Vector2i(tx2, ty2)
						_barracks_tile_data = t
						_log(">>> 选定兵营 (%d,%d),驻守单位=%s,先移开" % [tx2, ty2, str(u.get("unit_type"))])
						break
				if _empty_barracks_cell.x >= 0: break
			if _empty_barracks_cell.x >= 0: break
		if _empty_barracks_cell.x < 0:
			_finish(false, "找不到任何我方拥有的兵营"); return
		# 找该单位能走到的相邻格子,做 move
		var occ_unit_id: int = -1
		for p in gs.players:
			if int(p.get("id", -1)) != _player_id: continue
			for u in p.get("units", []):
				if u is Dictionary and int(u.get("x", -1)) == _empty_barracks_cell.x and int(u.get("y", -1)) == _empty_barracks_cell.y:
					occ_unit_id = int(u.get("id", -1)); break
			if occ_unit_id >= 0: break
		var dest: Vector2i = _find_adjacent_empty(_empty_barracks_cell)
		if dest.x < 0:
			_finish(false, "找不到空地让单位移开"); return
		_log(">>> move unit #%d → (%d,%d)" % [occ_unit_id, dest.x, dest.y])
		# action_move 是 fire-and-forget — 监听 unit_moved 信号即可
		nc.action_move(_game_id, _player_id, occ_unit_id, dest.x, dest.y)
		# 等 unit_moved 信号 + 等几秒 server snapshot
		await get_tree().create_timer(_MOVE_WAIT_SEC).timeout
		# 检查 GameState 缓存是否同步
		var u_after: Dictionary = gs.get_unit(occ_unit_id)
		if u_after.is_empty():
			_stale_after_move = true
			_log(">>> BUG: unit_moved 后 GameState.get_unit 找不到该单位(cache stale)")
		elif int(u_after.get("x", -1)) == dest.x and int(u_after.get("y", -1)) == dest.y:
			_log(">>> OK unit_moved 后 cache 同步:x=%d y=%d" % [dest.x, dest.y])
		else:
			_stale_after_move = true
			_log(">>> BUG: unit_moved 后 cache 未更新: 期望 (%d,%d) 实际 (%d,%d)" %
					[dest.x, dest.y, int(u_after.get("x", -1)), int(u_after.get("y", -1))])

	# 进游戏 view
	var main_app: Node = get_tree().current_scene.get_child(0) if get_tree().current_scene.get_child_count() > 0 else null
	if main_app != null and main_app.has_method("_show_view"):
		main_app.call("_show_view", "game_view")
	_log(">>> GameState 已就绪,空兵营在 (%d,%d)" % [_empty_barracks_cell.x, _empty_barracks_cell.y])
	_run_panel_phase()


# 找兵营相邻 4 邻格中第一个空地
func _find_adjacent_empty(barracks_cell: Vector2i) -> Vector2i:
	var gs: Node = get_node("/root/GameState")
	var dirs: Array = [Vector2i(0,-1), Vector2i(0,1), Vector2i(-1,0), Vector2i(1,0)]
	for d in dirs:
		var c: Vector2i = barracks_cell + (d as Vector2i)
		# 在地图范围内
		var found_terrain: bool = false
		for t in gs.tiles:
			if not (t is Dictionary): continue
			if int(t.get("x", -1)) == c.x and int(t.get("y", -1)) == c.y:
				found_terrain = true
				break
		if not found_terrain: continue
		# 该 cell 上没单位
		var occ: bool = false
		for p in gs.players:
			for u in p.get("units", []):
				if u is Dictionary and int(u.get("x", -1)) == c.x and int(u.get("y", -1)) == c.y:
					occ = true; break
			if occ: break
		if not occ:
			return c
	return Vector2i(-1, -1)


# 验证 _pick_empty_my_barracks + recruit_panel 出现
func _run_panel_phase() -> void:
	# 拿 main scene
	var main_app: Node = get_tree().current_scene.get_child(0) if get_tree().current_scene.get_child_count() > 0 else null
	if main_app == null:
		_finish(false, "no main_app"); return
	# 把 main._player_id 同步到真实 pid(可能 main.gd 走的另一条 join 路径)
	main_app.set("_player_id", _player_id)
	# 构造屏幕坐标 → cell
	var board: Node = main_app.get("board")
	if board == null:
		_finish(false, "no board"); return
	var layer: TileMapLayer = board.get_node_or_null("GroundLayer")
	if layer == null:
		_finish(false, "no GroundLayer"); return
	var cell_local: Vector2 = layer.map_to_local(_empty_barracks_cell)
	var cell_global: Vector2 = layer.to_global(cell_local)
	_log(">>> 模拟点击兵营 (%d,%d) screen=(%.0f,%.0f)" %
			[_empty_barracks_cell.x, _empty_barracks_cell.y, cell_global.x, cell_global.y])
	# 直接调 main._pick_empty_my_barracks(等同 _unhandled_input 分支)
	var batt: Dictionary = main_app.call("_pick_empty_my_barracks", cell_global)
	if batt.is_empty():
		_panel_shown = false
		_log(">>> FAIL _pick_empty_my_barracks 返回 {} — guard fail(等下看 status)")
		_finish(false, "_pick_empty_my_barracks 返回空 — bug 仍存在(stale_after_move=%s)" % str(_stale_after_move))
		return
	_log(">>> OK _pick_empty_my_barracks 返回 %s" % str(batt))
	main_app.call("_show_recruit_at", batt)
	# 断言 recruit_panel.visible
	var recruit_panel: Panel = main_app.get("recruit_panel")
	if recruit_panel == null:
		_finish(false, "recruit_panel 为 null(scene 节点缺失?)"); return
	_panel_shown = recruit_panel.visible
	if not _panel_shown:
		_finish(false, "_show_recruit_at 没把 recruit_panel.visible 置 true"); return
	_log(">>> OK recruit_panel.visible = true")
	_run_post_recruit()


# 验证 POST /recruit + cache 更新
func _run_post_recruit() -> void:
	# 调 swordsman 招募(最便宜)
	_log(">>> POST /recruit swordsman")
	var nc: Node = get_node("/root/NetworkClient")
	nc.action_recruit(_game_id, _player_id,
			_empty_barracks_cell.x, _empty_barracks_cell.y,
			"swordsman", Callable(self, "_on_recruit_response"))


func _on_recruit_response(body: Variant, code: int) -> void:
	_recruit_posted = true
	if int(code) not in [200, 201]:
		_finish(false, "recruit POST 失败: code=%d body=%s" % [code, str(body).substr(0, 200)])
		return
	_log(">>> OK recruit POST 成功: %s" % str(body).substr(0, 200))
	# body 应该含 new_unit_id
	if body is Dictionary:
		_new_unit_id = int(body.get("id", body.get("new_unit_id", body.get("unit_id", -1))))
	_log(">>> new_unit_id = %d" % _new_unit_id)
	# M4.16+:server 不 publish recruit event.delta — 走 REST poll 兜底刷新 GameState
	# 直接用 NetworkClient.get_game_state(绕开 main._poll_state_now 的 game_view.visible 守卫)
	var nc2: Node = get_node("/root/NetworkClient")
	nc2.get_game_state(_game_id, Callable(self, "_on_post_recruit_state"))
	# 等 REST 响应回来
	await get_tree().create_timer(_RECRUIT_WAIT_SEC).timeout
	nc2.get_game_state(_game_id, Callable(self, "_on_post_recruit_state"))
	await get_tree().create_timer(1.5).timeout


func _on_post_recruit_state(body: Variant, _code: int = 0) -> void:
	# 跟 main._on_state_poll_response 一致:把 GameStateOut 喂 ingest_snapshot
	var gs: Node = get_node("/root/GameState")
	if body is Dictionary and gs != null:
		gs.ingest_snapshot(body)
		_log("[diag] _on_post_recruit_state 拉取快照: tiles=%d players=%d" %
				[gs.tiles.size(), gs.players.size()])
	# 验证 GameState.players[].units[] 里有这个新单位
	for p in gs.players:
		if int(p.get("id", -1)) != _player_id: continue
		for u in p.get("units", []):
			if u is Dictionary and int(u.get("id", -1)) == _new_unit_id:
				_new_unit_in_cache = true
				_log(">>> OK 新单位 #%d 已加入 GameState cache at (%d,%d) hp=%s" %
						[_new_unit_id, int(u.get("x", -1)), int(u.get("y", -1)), str(u.get("hp"))])
				break
		if _new_unit_in_cache: break
	# 截图
	_save_screenshot()
	_finalize()


func _on_unit_moved(uid: int, fx: int, fy: int, tx: int, ty: int, cost: int) -> void:
	_log("[diag] unit_moved 信号: uid=%d (%d,%d)→(%d,%d) cost=%d" % [uid, fx, fy, tx, ty, cost])


func _save_screenshot() -> void:
	# 等几帧让 UI 渲染
	for i in 4:
		await RenderingServer.frame_post_draw
	var img: Image = get_viewport().get_texture().get_image()
	if img != null:
		img.save_png("user://recruit_e2e.png")
		img.save_png("res://recruit_e2e.png")
		_log(">>> saved screenshot → res://recruit_e2e.png")


func _finalize() -> void:
	var ok: bool = _panel_shown and _recruit_posted and _new_unit_in_cache and not _stale_after_move
	var msg: String = "panel=%s posted=%s cache_new=%s stale_after_move=%s new_unit_id=%d" % [
		str(_panel_shown), str(_recruit_posted), str(_new_unit_in_cache),
		str(_stale_after_move), _new_unit_id
	]
	_finish(ok, msg)


func _finish(passed: bool, msg: String) -> void:
	var tag: String = "PASS" if passed else "FAIL"
	_log("[RESULT] %s - %s" % [tag, msg])
	if _logf != null: _logf.close()
	print("[recruit-e2e] ===== %s =====" % tag)
	get_tree().quit(0 if passed else 1)


func _log(msg: String) -> void:
	var line: String = "[recruit-e2e] %s" % msg
	print(line)
	if _logf != null:
		_logf.store_string(line + "\n")
		_logf.flush()