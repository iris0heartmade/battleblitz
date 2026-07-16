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
signal tile_state_changed(tile_x: int, tile_y: int, new_state: Dictionary)
signal units_changed(units: Array)
signal unit_acted(unit_id: int, has_acted: bool, has_moved: bool)
signal current_player_changed(player_id)
signal phase_changed(phase: String)
signal connection_state_changed(connected: bool)

# Granular event-delta signals (M2.2)
signal log_received(action: Dictionary)            # every event → log line
signal unit_moved(unit_id: int, from_x: int, from_y: int, to_x: int, to_y: int, cost: int)
signal unit_attacked(attacker_id: int, target_id: int, damage: int, is_crit: bool, is_kill: bool)
signal unit_killed(unit_id: int, killer_id: int)
signal unit_leveled_up(unit_id: int, new_level: int)
signal unit_waited(unit_id: int)
signal unit_used_skill(unit_id: int, skill: String, target_id: int, restored_hp: int)
signal unit_claimed(unit_id: int, tile_x: int, tile_y: int, completed: bool, new_owner_id: int)
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

var is_connected: bool = false:
	set(value):
		if is_connected == value:
			return
		is_connected = value
		connection_state_changed.emit(value)


func _ready() -> void:
	# Wire to NetworkClient's typed signals.
	var nc := get_node_or_null("/root/NetworkClient")
	if nc == null:
		nc = Engine.get_singleton("NetworkClient") if Engine.has_singleton("NetworkClient") else null
	# In Godot 4 autoloads aren't on Engine singleton; resolve by absolute path.
	if nc == null:
		nc = get_node("/root/NetworkClient")
	if nc != null:
		nc.state_snapshot_received.connect(_on_state_snapshot)
		nc.event_delta_received.connect(_on_event_delta)
		nc.server_hello_received.connect(_on_server_hello)
		nc.ws_connected.connect(func(): is_connected = true)
		nc.ws_disconnected.connect(func(_r): is_connected = false)


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
			unit_moved.emit(
				actor_unit_id,
				int(context.get("from_x", -1)),
				int(context.get("from_y", -1)),
				int(context.get("to_x", -1)),
				int(context.get("to_y", -1)),
				int(context.get("cost", 0))
			)
		"attack":
			unit_attacked.emit(
				actor_unit_id, target_unit_id,
				int(context.get("damage", 0)),
				bool(context.get("is_crit", false)),
				bool(context.get("is_kill", false))
			)
		"kill":
			unit_killed.emit(target_unit_id, actor_unit_id)
		"level_up":
			unit_leveled_up.emit(actor_unit_id, int(context.get("new_level", 0)))
		"wait":
			unit_waited.emit(actor_unit_id)
		"skill":
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
			unit_recruited.emit(
				int(context.get("new_unit_id", actor_unit_id)),
				String(context.get("unit_type", "")),
				int(context.get("tile_x", -1)),
				int(context.get("tile_y", -1)),
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
