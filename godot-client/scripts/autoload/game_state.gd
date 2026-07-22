extends Node
## GameState — autoload singleton caching the latest server snapshot.
##
## The Python backend is authoritative: all player actions POST to REST
## and the server replies via WebSocket `state.snapshot` /
## `event.delta` messages. This singleton holds the parsed snapshot
## and emits typed signals so the Board scene (or any HUD widget) can react.
##
## M2.2 wires the full WS message dispatch:
##   * `state.snapshot`      → re-parse, refresh cached fields, emit
##                              `state_updated` + targeted change signals
##   * `event.delta`         → dispatch by `event_type` to typed signals
##                              (unit_moved / unit_attacked / unit_killed /
##                               phase_changed / log_received / ...)
##
## All signal names mirror the `*Out` schema fields so the UI layer can
## bind to the precise change (e.g. "the unit at (3,4) just moved to (5,6)")
## without re-scanning the whole snapshot.

signal snapshot_received(snapshot: Dictionary)
signal state_updated(snapshot: Dictionary)
signal units_changed(units: Array)
signal current_player_changed(player_id)
signal phase_changed(phase: String)
signal connection_state_changed(connected: bool)

# Granular event-delta signals (M2.2)
signal log_received(action: Dictionary)            # every event → log line
signal unit_moved(unit_id: int, from_x: int, from_y: int, to_x: int, to_y: int, cost: int)
signal unit_attacked(attacker_id: int, target_id: int, damage: int, is_crit: bool, is_kill: bool, counter_damage: int)
signal unit_killed(unit_id: int, killer_id: int)
signal unit_leveled_up(unit_id: int, new_level: int)
signal unit_waited(unit_id: int)
signal unit_used_skill(unit_id: int, skill: String, target_id: int, restored_hp: int)
signal unit_recruited(new_unit_id: int, unit_type: String, tile_x: int, tile_y: int, cost: int)
signal turn_ended(next_player_id, turn_number: int)
signal round_started(turn_number: int)
signal match_started()
signal match_ended(winner_player_id, win_reason: String)
signal castle_captured(tile_x: int, tile_y: int, new_owner_id: int)
signal ai_thinking(thinking: bool)               # true on ai_step, false on auto_skip / turn_end
signal low_hp_warning(unit_id: int, current_hp: int, max_hp: int)
signal comeback(player_id: int)
signal victory_imminent(player_id: int)

# Latest snapshot (parsed JSON dict from `state.snapshot.payload.game`).
# Empty until the first WS message arrives.
var latest_snapshot: Dictionary = {}

# Convenience accessors (filled in by `ingest_snapshot`).
var game_summary: Dictionary = {}              # GameSummaryOut
var tiles: Array = []                          # Array[TileOut]
var players: Array = []                         # Array[PlayerOut]
var current_player_id: Variant = null           # int | null
var pending_claims: Array = []                  # Array[PendingClaimOut]
var co_states: Array = []                       # Array[PlayerCOStateOut]
var logs: Array = []                            # Array[ActionLogOut]
var phase: String = "player"                    # "player" | "ai" | "spectator" | "animating"
var local_player_id: int = 0                    # set by main scene on join — used for "is your turn" checks
var is_local_turn: bool = false:
	set(value):
		if is_local_turn == value:
			return
		is_local_turn = value
		phase_changed.emit(phase)

var ws_connected: bool = false:
	set(value):
		if ws_connected == value:
			return
		ws_connected = value
		connection_state_changed.emit(value)


func _ready() -> void:
	# NOTE: NetworkClient is an autoload that loads AFTER GameState
	# (order: Config, UserSettings, GameState, InputState, NetworkClient,
	# AudioManager), so it is NOT in the tree yet here. The actual signal
	# wiring is done from NetworkClient._ready (which runs after GameState
	# is in the tree) - see network_client.gd::_wire_to_game_state().
	pass


# ============================================================
# Public API
# ============================================================

## Replace the cached state with a fresh `state.snapshot` payload.
## `payload.game` follows the GameStateOut schema in schemas.py.
func ingest_snapshot(snapshot: Dictionary) -> void:
	_on_state_snapshot(snapshot)


## Apply a single `event.delta` (forwarded as a GameEvent dict from
## protocol/v1.py + ws_gateway.py). The event_type drives which typed
## signal to emit.
func ingest_event(event: Dictionary) -> void:
	_on_event_delta(event)


## Lookup helpers used by Board / Highlight / Action-bubble.
func get_unit(unit_id: int) -> Dictionary:
	for u in _flatten_units(players):
		if int(u.get("id", -1)) == unit_id:
			return u
	return {}


func get_player(player_id) -> Dictionary:
	for p in players:
		if int(p.get("id", -1)) == int(player_id):
			return p
	return {}


func get_tile(x: int, y: int) -> Dictionary:
	for t in tiles:
		if int(t.get("x", -1)) == x and int(t.get("y", -1)) == y:
			return t
	return {}


func get_local_player() -> Dictionary:
	return get_player(local_player_id)


func get_units_for_player(player_id) -> Array:
	var out: Array = []
	var p := get_player(player_id)
	if p.is_empty():
		return out
	for u in p.get("units", []):
		if u is Dictionary:
			out.append(u)
	return out


# ============================================================
# Signal handlers
# ============================================================

func _on_server_hello(_seq: int, payload: Dictionary) -> void:
	# server.hello is informational. We log via log_received so the
	# HUD can show "connected to server v0.1.0".
	log_received.emit({
		"event_type": "system",
		"description": "Connected to server %s" % String(payload.get("server_version", "?")),
		"importance": "normal",
	})


func _on_state_snapshot(snapshot: Dictionary) -> void:
	latest_snapshot = snapshot
	game_summary = snapshot.get("game", {})
	tiles = snapshot.get("tiles", [])
	players = snapshot.get("players", [])
	current_player_id = snapshot.get("current_player_id", null)
	pending_claims = snapshot.get("pending_claims", [])
	co_states = snapshot.get("co_states", [])
	logs = snapshot.get("logs", [])
	phase = game_summary.get("phase", "player")
	is_local_turn = (current_player_id != null) and (int(current_player_id) == local_player_id)
	snapshot_received.emit(snapshot)
	state_updated.emit(snapshot)
	units_changed.emit(_flatten_units(players))
	current_player_changed.emit(current_player_id)
	phase_changed.emit(phase)


func _on_event_delta(event: Dictionary) -> void:
	# Every event is also surfaced as a log line for the HUD log pane.
	log_received.emit(event)

	var event_type: String = String(event.get("event_type", ""))
	# M4.1 fix:server event 可能省略 actor_unit_id / target_unit_id
	# (例如 turn.advance / match.ended)。用 Variant + null check,值是 null
	# 时默认 -1。
	var actor_v: Variant = event.get("actor_unit_id", -1)
	var actor_unit_id: int = -1 if actor_v == null else int(actor_v)
	var target_v: Variant = event.get("target_unit_id", -1)
	var target_unit_id: int = -1 if target_v == null else int(target_v)
	var context: Dictionary = event.get("context", {})
	if not context is Dictionary:
		context = {}
	var turn: int = int(event.get("turn", 0))

	match event_type:
		"move":
			# M4.16+:同步更新 players 缓存中的 x/y — 否则 _all_units_including_self()
			# 等用 GameState.players 数据的代码会读到 stale 位置(knight 移开后
			# 还显示在原 cell,导致 _pick_empty_my_barracks 误判"已驻守")。
			var moved_to_x: int = int(context.get("to_x", -1))
			var moved_to_y: int = int(context.get("to_y", -1))
			_update_unit_in_cache(actor_unit_id, func(u: Dictionary) -> void:
				u["x"] = moved_to_x
				u["y"] = moved_to_y
			)
			unit_moved.emit(
				actor_unit_id,
				int(context.get("from_x", -1)),
				int(context.get("from_y", -1)),
				moved_to_x,
				moved_to_y,
				int(context.get("cost", 0))
			)
		"attack":
			# M4.16+:同步 HP — attack/kill 影响 units[].hp,_all_units_including_self 也读 hp
			var attacker_hp_after: int = int(context.get("attacker_hp", -1))
			var target_hp_after: int = int(context.get("target_hp", -1))
			var is_kill_v: bool = bool(context.get("is_kill", false))
			if attacker_hp_after >= 0:
				_update_unit_in_cache(actor_unit_id, func(u: Dictionary) -> void:
					u["hp"] = attacker_hp_after
				)
			if target_hp_after >= 0:
				_update_unit_in_cache(target_unit_id, func(u: Dictionary) -> void:
					u["hp"] = target_hp_after
				)
			unit_attacked.emit(
				actor_unit_id, target_unit_id,
				int(context.get("damage", 0)),
				bool(context.get("is_crit", false)),
				is_kill_v,
				int(context.get("counter_damage", 0))
			)
		"kill":
			# M4.16+:从 players 缓存中移除死亡单位 — 否则 _all_units_including_self 还会看到尸体
			_remove_unit_from_cache(target_unit_id)
			unit_killed.emit(target_unit_id, actor_unit_id)
		"level_up":
			_update_unit_in_cache(actor_unit_id, func(u: Dictionary) -> void:
				u["level"] = int(context.get("new_level", int(u.get("level", 1))))
			)
			unit_leveled_up.emit(actor_unit_id, int(context.get("new_level", 0)))
		"wait":
			unit_waited.emit(actor_unit_id)
		"skill":
			# M4.16+:同步 HP(heal 技能 restore_hp)
			var skill_restored: int = int(context.get("restored_hp", -1))
			if skill_restored >= 0:
				_update_unit_in_cache(actor_unit_id, func(u: Dictionary) -> void:
					u["hp"] = int(u.get("hp", 0)) + skill_restored
				)
			unit_used_skill.emit(
				actor_unit_id,
				String(context.get("skill", "")),
				target_unit_id,
				int(context.get("restored_hp", 0))
			)
		"castle_captured":
			castle_captured.emit(
				int(context.get("tile_x", -1)),
				int(context.get("tile_y", -1)),
				int(context.get("new_owner_id", -1))
			)
		"recruit":
			# M4.16+:把新单位推到 local player 的 units 缓存 — 下一次
			# _all_units_including_self 立刻能看到(避免 REST polling 延迟
			# 期间新单位被当作"未驻守"允许二次招募)。
			var new_uid: int = int(context.get("new_unit_id", actor_unit_id))
			var rec_tx: int = int(context.get("tile_x", -1))
			var rec_ty: int = int(context.get("tile_y", -1))
			if new_uid >= 0 and rec_tx >= 0 and rec_ty >= 0 and local_player_id > 0:
				_add_unit_to_player_cache(local_player_id, {
					"id": new_uid,
					"unit_type": String(context.get("unit_type", "")),
					"x": rec_tx,
					"y": rec_ty,
					"hp": -1,         # 待 REST polling 补完整 HP
					"max_hp": -1,
					"has_acted": true,
					"has_moved": true,
				})
			unit_recruited.emit(
				new_uid,
				String(context.get("unit_type", "")),
				rec_tx,
				rec_ty,
				int(context.get("cost", 0))
			)
		"turn_end":
			turn_ended.emit(int(context.get("next_player_id", -1)), turn)
		"round_end":
			round_started.emit(turn + 1)
		"match_start":
			match_started.emit()
		"match_end":
			match_ended.emit(int(context.get("winner_player_id", -1)), String(context.get("win_reason", "")))
		"low_hp_warning":
			low_hp_warning.emit(actor_unit_id, int(context.get("current_hp", 0)), int(context.get("max_hp", 1)))
		"comeback":
			comeback.emit(int(context.get("player_id", -1)))
		"victory_imminent":
			victory_imminent.emit(int(context.get("player_id", -1)))
		"ai_step":
			ai_thinking.emit(true)
		"auto_skip":
			ai_thinking.emit(false)
		"error":
			# Bubble up to protocol_error_received-equivalent for log pane.
			log_received.emit({
				"event_type": "system",
				"description": "Error: %s" % String(context.get("message", "unknown")),
				"importance": "critical",
			})
		_:
			# Unknown event type — already emitted as log.
			pass


# P2:commentary WS 接通 — AI 旁白文本/音频帧转 log_received
# 由 NetworkClient.commentary_received 触发,客户端无需新建 signal,
# 直接借用 log_received(action) 让 WarReportPanel 统一显示。
func _on_commentary_received(text: String) -> void:
	# 用现有 log_received 派发一条评论日志;main.gd 的 _on_log_received 会渲染
	var fake_action: Dictionary = {
		"action_type": "commentary.text",
		"description": text,
		"importance": "info",
	}
	log_received.emit(fake_action)


# ============================================================
# Internal helpers
# ============================================================

func _flatten_units(players_in: Array) -> Array:
	var out: Array = []
	for p in players_in:
		if not p is Dictionary:
			continue
		var units: Variant = p.get("units", [])
		if units is Array:
			for u in units:
				if u is Dictionary:
					out.append(u)
	return out


# M4.16+:在 players 缓存里按 id 找单位并应用 updater。
# event.delta 不重发整套 state,只有 typed signals — 但 main.gd 用
# GameState.players[].units[] 做占用判定/HP 显示,必须同步更新,否则
# _pick_empty_my_barracks / _show_threat_tiles 等用 stale data 出 bug。
func _update_unit_in_cache(unit_id: int, updater: Callable) -> bool:
	if unit_id < 0:
		return false
	for p in players:
		if not p is Dictionary:
			continue
		var units_v: Variant = p.get("units", [])
		if not units_v is Array:
			continue
		for u in units_v:
			if u is Dictionary and int(u.get("id", -1)) == unit_id:
				updater.call(u)
				return true
	return false


# 从 players 缓存中移除死亡/被解散的单位(actor_unit_id)
func _remove_unit_from_cache(unit_id: int) -> bool:
	if unit_id < 0:
		return false
	for p in players:
		if not p is Dictionary:
			continue
		var units_v: Variant = p.get("units", [])
		if not units_v is Array:
			continue
		for i in range(units_v.size() - 1, -1, -1):
			var u: Variant = units_v[i]
			if u is Dictionary and int(u.get("id", -1)) == unit_id:
				units_v.remove_at(i)
				return true
	return false


# 给指定 player 追加新单位(recruit / summon 事件用)
func _add_unit_to_player_cache(player_id: int, new_unit: Dictionary) -> bool:
	for p in players:
		if not p is Dictionary:
			continue
		if int(p.get("id", -1)) != player_id:
			continue
		var units_v: Variant = p.get("units", [])
		if not units_v is Array:
			units_v = []
			p["units"] = units_v
		units_v.append(new_unit)
		return true
	return false
