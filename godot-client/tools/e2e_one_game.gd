extends Node
## e2e_one_game.gd - 真实端到端验证:Godot 客户端网络层 + 后端跑完一整局 vs AI。
##
## Prereq: 后端在 127.0.0.1:8000 listening。
## 思路:绕开 GUI,直接用 NetworkClient autoload(客户端真实网络层)按序走
##   create -> join -> add-ai -> start -> connect_to_game(WS)
## GameState 自动监听 WS 信号填充状态;轮到己方就 action_end_turn,
## 直到 GameState.match_ended 信号触发或超时。
## 日志同时写 stdout + user://e2e_one_game.log(逐行 flush,避免 Windows 管道缓冲)。
##
## 跑法:
##   Godot_v4.7-stable_win64_console.exe --headless --path godot-client res://tools/e2e_one_game.tscn

const _USER_NAME   := "e2e_tester"
const _MAP_PRESET  := "balanced_2p_15"
const _MAP_BIOME   := "grass"
const _WIN_COND    := "rout"
const _SETUP_TIMEOUT_SEC := 40.0   # create->join->add-ai->start->首帧 snapshot
const _GAME_TIMEOUT_SEC  := 600.0  # 等整局结束上限(rout 靠 AI 杀光单位,可能 10-20 回合)
const _END_TURN_WAIT_SEC := 3.0    # end_turn 后等 server 推 snapshot + AI 调度(10s 轮询)
const _AI_POLL_SEC       := 0.5

var _game_id: int = 0
var _player_id: int = 0
var _started_at: float = 0.0
var _last_turn: int = -1
var _match_ended: bool = false
var _winner_id: int = -1
var _win_reason: String = ""
var _logf: FileAccess = null
var _my_turn_presses: int = 0

# Regression counters (07-19 plan Task 1 + 07-21 plan M5). Each entry
# flow's "reached game view" milestone records a hit; the test only
# passes when every flow reaches the milestone.
var _assertion_total: int = 0
var _assertion_failed: int = 0
var _flow_create_completed: bool = false
var _flow_join_completed: bool = false
var _flow_ai_completed: bool = false
var _flow_start_completed: bool = false
var _flow_game_view_reached: bool = false


func _ready() -> void:
	_logf = FileAccess.open("user://e2e_one_game.log", FileAccess.WRITE)
	_log("=== BattleBlitz e2e: 1 full game vs AI (direct NetworkClient) ===")
	_log("godot %s | backend 127.0.0.1:8000" % Engine.get_version_info().get("string", "?"))
	# Resolve autoloads via /root lookup; this lets the e2e scene run
	# even if a singleton identifier is misconfigured. The smoke test
	# uses the same guard so the production and e2e entry points stay
	# in sync.
	var game_state := get_node_or_null("/root/GameState")
	var network_client := get_node_or_null("/root/NetworkClient")
	if game_state == null or network_client == null:
		_finish(false, "autoload 缺失(GameState/NetworkClient)")
		return
	# Pin the local references so the rest of the script reads from the
	# autoloads through the same names that the production code uses.
	GameState = game_state
	NetworkClient = network_client
	if not GameState.match_ended.is_connected(_on_match_ended):
		GameState.match_ended.connect(_on_match_ended)
	# 诊断:监听 NetworkClient 底层信号,定位 WS 链路断点
	NetworkClient.ws_connecting.connect(_diag_ws_connecting)
	NetworkClient.ws_connected.connect(_diag_ws_connected)
	NetworkClient.ws_disconnected.connect(_diag_ws_disconnected)
	NetworkClient.ws_reconnecting.connect(_diag_ws_reconnecting)
	NetworkClient.ws_message_received.connect(_diag_ws_message)
	NetworkClient.state_snapshot_received.connect(_diag_snapshot)
	NetworkClient.protocol_error_received.connect(_diag_proto_error)
	NetworkClient.api_error.connect(_diag_api_error)
	_started_at = Time.get_ticks_msec() / 1000.0
	_log("[1/5] create_game(%s, %s, %s)..." % [_MAP_PRESET, _MAP_BIOME, _WIN_COND])
	NetworkClient.create_game(_USER_NAME, _MAP_PRESET, _MAP_BIOME, _WIN_COND, "", "", {}, Callable(self, "_on_created"))


# ---------- callback 链 ----------
func _on_created(body: Variant, code: int) -> void:
	if not (body is Dictionary) or int(body.get("id", 0)) <= 0:
		_finish(false, "create_game 失败: code=%d body=%s" % [code, str(body).substr(0, 200)])
		return
	_game_id = int(body.get("id", 0))
	_assertion_total += 1
	if _game_id > 0:
		_flow_create_completed = true
	else:
		_assertion_failed += 1
	_log("[1/5] OK 对局 #%d 已创建 (code=%d)" % [_game_id, code])
	_log("[2/5] join_game(#%d, %s, red)..." % [_game_id, _USER_NAME])
	NetworkClient.join_game(_game_id, _USER_NAME, "red", "", "", Callable(self, "_on_joined"))


func _on_joined(body: Variant, code: int) -> void:
	var pid: int = 0
	if body is Dictionary:
		pid = int(body.get("id", 0))
		if pid <= 0:
			pid = int(body.get("player_id", 0))
		if pid <= 0:
			var p: Variant = body.get("player", {})
			if p is Dictionary:
				pid = int(p.get("id", 0))
	if pid <= 0:
		_finish(false, "join_game 失败: code=%d body=%s" % [code, str(body).substr(0, 200)])
		return
	_player_id = pid
	GameState.local_player_id = _player_id
	_assertion_total += 1
	if _player_id > 0:
		_flow_join_completed = true
	else:
		_assertion_failed += 1
	_log("[2/5] OK 已加入 玩家 #%d (code=%d)" % [_player_id, code])
	_log("[3/5] add_ai_player(normal, rules, balanced)...")
	NetworkClient.add_ai_player(_game_id, "normal", "rules", "balanced", Callable(self, "_on_ai_added"))


func _on_ai_added(body: Variant, code: int) -> void:
	_assertion_total += 1
	if int(code) in [200, 201]:
		_flow_ai_completed = true
	else:
		_assertion_failed += 1
	_log("[3/5] OK AI 已加入 (code=%d)" % code)
	_log("[4/5] start_game(#%d)..." % [_game_id])
	NetworkClient.start_game(_game_id, Callable(self, "_on_started"))


func _on_started(body: Variant, code: int) -> void:
	_assertion_total += 1
	if int(code) in [200, 201]:
		_flow_start_completed = true
	else:
		_assertion_failed += 1
	_log("[4/5] OK 对局已开始 (code=%d)" % code)
	_log("[5/5] connect_to_game(WS)...")
	NetworkClient.connect_to_game(_game_id, _player_id)
	# 进入主循环,等 snapshot + 轮流 end_turn
	_run_game_loop()


# ---------- 主循环 ----------
func _run_game_loop() -> void:
	# 先等 snapshot 到达(GameState 有 tiles + players)
	var setup_deadline: float = Time.get_ticks_msec() / 1000.0 + _SETUP_TIMEOUT_SEC
	while Time.get_ticks_msec() / 1000.0 < setup_deadline:
		if _match_ended:
			_finish(true, "对局在 setup 阶段就结束(异常快速)")
			return
		if GameState.tiles.size() > 0 and GameState.players.size() >= 2:
			break
		await get_tree().create_timer(0.3).timeout
	if GameState.tiles.size() == 0:
		_finish(false, "%ds 内未收到 WS snapshot(GameState 空)" % int(_SETUP_TIMEOUT_SEC))
		return
	_log(">>> 对局可玩: 玩家数=%d 单位数=%d 我的pid=%d 当前pid=%s" %
		[GameState.players.size(), _unit_count(), _player_id, str(GameState.current_player_id)])
	# Regression assertion: every entry flow must have reached "game view"
	# (i.e. GameState has tiles + at least 2 players + a current player).
	_assertion_total += 1
	if GameState.tiles.size() > 0 and GameState.players.size() >= 2 and GameState.current_player_id != null:
		_flow_game_view_reached = true
	else:
		_assertion_failed += 1
		_finish(false, "reached_game_view 断言失败: tiles=%d players=%d current=%s" %
			[GameState.tiles.size(), GameState.players.size(), str(GameState.current_player_id)])
		return

	var game_deadline: float = Time.get_ticks_msec() / 1000.0 + _GAME_TIMEOUT_SEC
	# 服务端 end_turn(及回合推进/对局结束)不往 WS 事件总线 publish 事件 -- 只有
	# move/attack/skill 才 publish。所以 turn_end/match_end 不会通过 event.delta
	# 到达客户端。改用 REST GET /state 周期轮询刷新 GameState + 检测 status=="finished"。
	while Time.get_ticks_msec() / 1000.0 < game_deadline:
		if _match_ended:
			break
		NetworkClient.get_game_state(_game_id, Callable(self, "_on_polled_state"))
		await get_tree().create_timer(1.5).timeout
		if _match_ended:
			break
		var cur_turn: int = int(GameState.game_summary.get("turn_number", 0))
		if cur_turn != _last_turn:
			_last_turn = cur_turn
			var cur_pid: Variant = GameState.current_player_id
			var whose: String = "AI" if (cur_pid == null or int(cur_pid) != _player_id) else "我方"
			_log("回合 %d (%s) | 存活单位=%d status=%s" % [cur_turn, whose, _unit_count(), str(GameState.game_summary.get("status", ""))])
		var cur_pid2: Variant = GameState.current_player_id
		if cur_pid2 != null and int(cur_pid2) == _player_id and not _match_ended:
			# 己方回合 -> end_turn
			_my_turn_presses += 1
			_log("  -> action_end_turn (第 %d 次)" % _my_turn_presses)
			NetworkClient.action_end_turn(_game_id, _player_id)
			await get_tree().create_timer(_END_TURN_WAIT_SEC).timeout

	if _match_ended:
		var elapsed: float = Time.get_ticks_msec() / 1000.0 - _started_at
		var won: String = "胜" if _winner_id == _player_id else "负"
		_finish(true, "对局结束! 胜者=玩家#%d(%s) 原因=%s | 用时=%.1fs 我方end_turn %d 次" %
			[_winner_id, won, _win_reason, elapsed, _my_turn_presses])
	else:
		_finish(false, "%ds 内对局未结束(超时) 我方end_turn %d 次" % [int(_GAME_TIMEOUT_SEC), _my_turn_presses])


# REST GET /state 回调:刷新 GameState + 检测对局结束。
func _on_polled_state(body: Variant, _code: int = 0) -> void:
	if not (body is Dictionary):
		return
	# GET /state 返回 GameStateOut(顶层 tiles/players/current_player_id + game 子字典)
	GameState.ingest_snapshot(body)
	var g: Variant = body.get("game", {})
	if not g is Dictionary:
		return
	if String(g.get("status", "")) != "finished":
		return
	if _match_ended:
		return  # 已检测到
	# rout 胜利:winner = 存活的非观战玩家
	_winner_id = -1
	for p in GameState.players:
		if p is Dictionary and bool(p.get("is_alive", false)) and not bool(p.get("is_spectator", false)):
			_winner_id = int(p.get("id", -1))
			break
	_win_reason = String(g.get("win_reason", ""))
	if _win_reason == "":
		_win_reason = String(g.get("win_condition", "rout"))
	_match_ended = true
	_log(">>> GET /state: status=finished winner=#%d reason=%s" % [_winner_id, _win_reason])


func _on_match_ended(winner_player_id, win_reason: String) -> void:
	_match_ended = true
	_winner_id = int(winner_player_id)
	_win_reason = String(win_reason)
	_log(">>> match_ended 信号: winner=#%d reason=%s" % [_winner_id, _win_reason])


# GameState 没有顶层 units 属性(units 嵌在 players 里),手动统计。
func _unit_count() -> int:
	var n: int = 0
	for p in GameState.players:
		if p is Dictionary:
			var u: Variant = p.get("units", [])
			if u is Array:
				n += u.size()
	return n


# ---------- 诊断回调 ----------
func _diag_ws_connecting() -> void:
	_log("[diag] ws_connecting")
func _diag_ws_connected() -> void:
	_log("[diag] ws_CONNECTED")
func _diag_ws_disconnected(reason: Variant) -> void:
	_log("[diag] ws_DISCONNECTED reason=%s" % str(reason))
func _diag_ws_reconnecting(attempt: int, delay: float) -> void:
	_log("[diag] ws_reconnecting attempt=%d delay=%.1f" % [attempt, delay])
func _diag_ws_message(msg: Dictionary) -> void:
	_log("[diag] ws_msg type=%s" % str(msg.get("type", "?")))
func _diag_snapshot(g: Dictionary) -> void:
	var tcount: int = int(g.get("tiles", []).size()) if g.get("tiles", []) is Array else 0
	var pcount: int = int(g.get("players", []).size()) if g.get("players", []) is Array else 0
	var gs_tiles: int = GameState.tiles.size()
	_log("[diag] state_snapshot_received tiles=%d players=%d | GameState.tiles=%d" % [tcount, pcount, gs_tiles])
func _diag_proto_error(code: Variant, message: Variant) -> void:
	_log("[diag] protocol_error code=%s msg=%s" % [str(code), str(message)])
func _diag_api_error(method: Variant, path: Variant, msg: Variant, code: int) -> void:
	_log("[diag] api_error %s %s code=%d msg=%s" % [str(method), str(path), code, str(msg)])


func _finish(passed: bool, msg: String) -> void:
	var tag: String = "PASS" if passed else "FAIL"
	# Regression summary: a PASS only counts if every milestone fired.
	# This is the M5 / 07-19 Task 1 entry-blocker guard: if any of the
	# five entry flows falls through silently, the run is FAIL.
	_assertion_total += 1
	if not (_flow_create_completed and _flow_join_completed
			and _flow_ai_completed and _flow_start_completed
			and _flow_game_view_reached):
		passed = false
		_assertion_failed += 1
		if msg == "" or msg == "对局已结束":
			msg = "entry flow regression failed"
		msg = "%s | regression: create=%s join=%s ai=%s start=%s game_view=%s" % [
			msg, _flow_create_completed, _flow_join_completed,
			_flow_ai_completed, _flow_start_completed, _flow_game_view_reached,
		]
	_log("[RESULT] %s - %s" % [tag, msg])
	_log("[REGRESSION] total=%d failed=%d" % [_assertion_total, _assertion_failed])
	if _logf != null:
		_logf.close()
	print("[e2e] ===== %s =====" % tag)
	get_tree().quit(0 if passed else 1)


func _log(msg: String) -> void:
	var line: String = "[e2e] %s" % msg
	print(line)
	if _logf != null:
		_logf.store_string(line + "\n")
		_logf.flush()
