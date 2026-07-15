extends Node
## NetworkClient — autoload wrapping HTTP + WebSocket calls to the
## Python backend.
##
## HTTP layer is a thin wrapper over `HTTPRequest` (`request(method, path, body)`).
## WS layer parses incoming `WSMessage` envelopes (see
## `app/protocol/v1.py`) and re-emits one signal per `type`:
##
##   * `server.hello`     → `server_hello_received(seq, payload)`
##   * `state.snapshot`   → `state_snapshot_received(game_dict)`
##   * `event.delta`      → `event_delta_received(event_dict)`
##   * `server.pong`      → `server_pong_received(echo_at_ms)`
##   * `error`            → `protocol_error_received(code, message)`
##   * unknown type       → `raw_message_received(raw)` (fallback)
##
## M2.1 also adds:
##   * auto-reconnect with exponential backoff (max 30s)
##   * client-side `client.ping` heartbeat every 25s
##   * `since_seq` tracked across reconnects
##   * `connect_to_game(game_id, player_id)` high-level helper
##
## Base URLs come from `UserSettings` (which falls back to Config
## defaults). The full REST/WS surface lives in
## `../docs/路线/Godot移植方案.md` §5.6.

signal api_response(method: String, path: String, body: Dictionary, http_code: int)
signal api_error(method: String, path: String, error: String, http_code: int)

signal ws_connecting()
signal ws_connected()
signal ws_disconnected(reason: String)
signal ws_reconnecting(attempt: int, delay_sec: float)

# Low-level fallback (kept for backward compat).
signal ws_message_received(message: Dictionary)

# Typed signals (M2.1)
signal server_hello_received(seq: int, payload: Dictionary)
signal state_snapshot_received(game: Dictionary)
signal event_delta_received(event: Dictionary)
signal server_pong_received(echo_at_ms: int)
signal protocol_error_received(code: String, message: String)

const _REQ_TIMEOUT_SEC := 10.0
const _HEARTBEAT_INTERVAL_SEC := 25.0
const _WS_RECONNECT_BASE_SEC := 0.5
const _WS_RECONNECT_MAX_SEC := 30.0

var _http: HTTPRequest
var _ws: WebSocketPeer = null
var _ws_url: String = ""
var _is_ws_connected: bool = false
var _ws_poll_timer: Timer = null
var _ws_heartbeat_timer: Timer = null

# High-level connection state (M2.1)
var _target_game_id: int = 0
var _target_player_id: int = 0
var _last_received_seq: int = 0
var _reconnect_attempt: int = 0
var _want_ws: bool = false


func _ready() -> void:
	_http = HTTPRequest.new()
	add_child(_http)
	_http.timeout = _REQ_TIMEOUT_SEC
	_http.request_completed.connect(_on_http_completed)


# ============================================================
# HTTP — REST API
# ============================================================

## Generic JSON request. `method` ∈ "GET"/"POST"/"PATCH"/"DELETE".
## `body` is a Dictionary that will be serialised to JSON (omit for GET).
## `callback` is an optional Callable `func(body: Dictionary, code: int)`.
func request(method: String, path: String, body: Dictionary = {}, callback: Callable = Callable()) -> void:
	var url := _resolve_url(path)
	var headers := PackedStringArray(["Content-Type: application/json", "Accept: application/json"])
	var data: Variant = JSON.stringify(body) if not body.is_empty() else ""
	var http_method: int = _method_to_enum(method)
	var err := _http.request(url, headers, http_method, data)
	if err != OK:
		var msg := "HTTPRequest.request failed: %s" % error_string(err)
		api_error.emit(method, path, msg, 0)
		if callback.is_valid():
			callback.call({"error": msg}, 0)
		return
	_http.set_meta("pending_method", method)
	_http.set_meta("pending_path", path)
	_http.set_meta("pending_callback", callback)


static func _method_to_enum(verb: String) -> int:
	match verb.to_upper():
		"GET":    return HTTPClient.METHOD_GET
		"POST":   return HTTPClient.METHOD_POST
		"PUT":    return HTTPClient.METHOD_PUT
		"PATCH":  return HTTPClient.METHOD_PATCH
		"DELETE": return HTTPClient.METHOD_DELETE
		"HEAD":   return HTTPClient.METHOD_HEAD
		"OPTIONS":return HTTPClient.METHOD_OPTIONS
		_:        return HTTPClient.METHOD_GET


func _on_http_completed(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var method: String = _http.get_meta("pending_method", "")
	var path: String = _http.get_meta("pending_path", "")
	var callback: Callable = _http.get_meta("pending_callback", Callable())
	if result != HTTPRequest.RESULT_SUCCESS:
		var msg := "HTTP result %d" % result
		api_error.emit(method, path, msg, response_code)
		if callback.is_valid():
			callback.call({"error": msg}, response_code)
		return
	var text := body.get_string_from_utf8()
	var parsed: Variant = JSON.parse_string(text) if text.length() > 0 else {}
	if not parsed is Dictionary:
		parsed = {"_raw": text}
	if response_code >= 200 and response_code < 300:
		api_response.emit(method, path, parsed, response_code)
		if callback.is_valid():
			callback.call(parsed, response_code)
	else:
		api_error.emit(method, path, "HTTP %d" % response_code, response_code)
		if callback.is_valid():
			callback.call(parsed, response_code)


# ============================================================
# WebSocket — typed dispatch + reconnect + heartbeat (M2.1)
# ============================================================

## High-level helper. Opens WS to `ws://<host>/ws/games/{game_id}?player_id={pid}&since_seq={N}`.
## Stashes the connection target so we can reconnect automatically.
func connect_to_game(game_id: int, player_id: int) -> void:
	_target_game_id = game_id
	_target_player_id = player_id
	_want_ws = true
	_reconnect_attempt = 0
	_open_ws()


## Open a WebSocket connection. `url` should be a full
## `ws://host/ws/games/{id}?player_id={pid}&since_seq={N}` URL.
## Prefer `connect_to_game()` above.
func ws_connect(url: String) -> void:
	# Treat as raw escape hatch — cancel any auto-reconnect state.
	_want_ws = true
	_reconnect_attempt = 0
	_ws_url = url
	_target_game_id = 0
	_target_player_id = 0
	_open_ws()


func ws_close() -> void:
	_want_ws = false
	_reconnect_attempt = 0
	if _ws != null:
		_ws.close()
	_is_ws_connected = false


func _open_ws() -> void:
	var url: String = ""
	if _target_game_id > 0:
		# Build the gateway URL from UserSettings + target ids.
		var base := UserSettings.get_ws_base()
		# Ensure base doesn't have a trailing slash.
		if base.ends_with("/"):
			base = base.substr(0, base.length() - 1)
		url = "%s/ws/games/%d?player_id=%d&since_seq=%d" % [
			base, _target_game_id, _target_player_id, _last_received_seq
		]
	else:
		url = _ws_url
	if url == "":
		return
	_ws_url = url
	ws_connecting.emit()
	if _ws != null:
		_ws.disconnect_from_host()
	_ws = WebSocketPeer.new()
	var err := _ws.connect_to_url(url)
	if err != OK:
		ws_disconnected.emit("connect_to_url: %s" % error_string(err))
		_schedule_reconnect()
		return
	_is_ws_connected = false
	if _ws_poll_timer == null:
		_ws_poll_timer = Timer.new()
		_ws_poll_timer.wait_time = 0.05
		_ws_poll_timer.timeout.connect(_ws_poll)
		add_child(_ws_poll_timer)
	_ws_poll_timer.start()
	if _ws_heartbeat_timer == null:
		_ws_heartbeat_timer = Timer.new()
		_ws_heartbeat_timer.wait_time = _HEARTBEAT_INTERVAL_SEC
		_ws_heartbeat_timer.timeout.connect(_ws_send_ping)
		add_child(_ws_heartbeat_timer)


func _ws_poll() -> void:
	if _ws == null:
		return
	_ws.poll()
	var state := _ws.get_ready_state()
	match state:
		WebSocketPeer.STATE_OPEN:
			if not _is_ws_connected:
				_is_ws_connected = true
				_reconnect_attempt = 0
				ws_connected.emit()
				# Reset heartbeat on (re)connect.
				if _ws_heartbeat_timer != null:
					_ws_heartbeat_timer.start()
			while _ws.get_available_packet_count() > 0:
				var pkt := _ws.get_packet()
				var text := pkt.get_string_from_utf8()
				var parsed: Variant = JSON.parse_string(text) if text.length() > 0 else {}
				if parsed is Dictionary:
					_dispatch_ws_message(parsed)
		WebSocketPeer.STATE_CLOSING:
			pass
		WebSocketPeer.STATE_CLOSED:
			var code := _ws.get_close_code()
			var reason := _ws.get_close_reason()
			ws_disconnected.emit("code %d: %s" % [code, reason])
			_is_ws_connected = false
			_ws = null
			if _ws_poll_timer != null:
				_ws_poll_timer.stop()
			if _ws_heartbeat_timer != null:
				_ws_heartbeat_timer.stop()
			_schedule_reconnect()


## Dispatch a parsed WSMessage by `type`. Each branch re-emits a
## typed signal. Unknown types fall back to `raw_message_received` so
## forward-compat is cheap.
func _dispatch_ws_message(msg: Dictionary) -> void:
	# Always emit the low-level fallback first so existing listeners
	# (HUD/debug overlays) keep working.
	ws_message_received.emit(msg)

	var t: String = String(msg.get("type", ""))
	var seq: int = int(msg.get("seq", 0))
	if seq > 0:
		_last_received_seq = seq
	var payload: Dictionary = msg.get("payload", {})
	if not payload is Dictionary:
		payload = {}

	match t:
		"server.hello":
			server_hello_received.emit(seq, payload)
		"state.snapshot":
			# `payload.game` is the full GameStateOut dict.
			var game_dict: Variant = payload.get("game", {})
			if game_dict is Dictionary:
				state_snapshot_received.emit(game_dict)
		"event.delta":
			event_delta_received.emit(payload)
		"server.pong":
			var echo: int = int(payload.get("echo_at_ms", 0))
			server_pong_received.emit(echo)
		"turn.advance":
			# Gateway doesn't currently emit this, but protocol defines it.
			# Forward as event for future use.
			event_delta_received.emit(payload.duplicate())
		"error":
			var code: String = String(payload.get("code", "UNKNOWN"))
			var message: String = String(payload.get("message", ""))
			protocol_error_received.emit(code, message)
		"commentary.text", "commentary.audio":
			# Reserved for future AI commentary. No-op for now.
			pass
		_:
			# Unknown type — already emitted via ws_message_received.
			pass


func _ws_send_ping() -> void:
	if _ws == null or not _is_ws_connected:
		return
	var ping := {
		"v": 1,
		"type": "client.ping",
		"sent_at_ms": Time.get_ticks_msec(),
		"payload": {},
	}
	var err := _ws.send_text(JSON.stringify(ping))
	# Best-effort. If it fails the next poll will detect the dead
	# socket via STATE_CLOSED and we'll reconnect.


func _schedule_reconnect() -> void:
	if not _want_ws:
		return
	if _target_game_id == 0 and _ws_url == "":
		return
	_reconnect_attempt += 1
	var delay: float = min(
		_WS_RECONNECT_MAX_SEC,
		_WS_RECONNECT_BASE_SEC * pow(2.0, _reconnect_attempt - 1)
	)
	ws_reconnecting.emit(_reconnect_attempt, delay)
	var t := get_tree().create_timer(delay)
	t.timeout.connect(_open_ws, CONNECT_ONE_SHOT)


## Send a raw client→server envelope over the open WS. Used by REST
## fallback (gateway currently doesn't consume `client.action.*`, so
## this is forward-looking for the day it does).
func ws_send(type_str: String, payload: Dictionary = {}) -> bool:
	if _ws == null or not _is_ws_connected:
		return false
	var envelope := {
		"v": 1,
		"type": type_str,
		"sent_at_ms": Time.get_ticks_msec(),
		"payload": payload,
	}
	return _ws.send_text(JSON.stringify(envelope)) == OK


# ============================================================
# High-level REST action wrappers (M2.3 — godot 客户端镜像
# app/schemas.py 的 7 个动作端点)
# ============================================================
##
## 注意:WebSocket 网关当前不消费 `client.action.*`,所以 M2 阶段
## 玩家动作走 REST(per docs/路线/Godot移植方案.md §5.6 建议)。
## 等 ws_gateway 加 dispatcher 后,这些函数可以改走 ws_send()。

const _ACTIONS_GAME_BASE := "/games/{id}"


func action_move(game_id: int, player_id: int, unit_id: int, to_x: int, to_y: int) -> void:
	request("POST", _ACTIONS_GAME_BASE.format({"id": game_id}) + "/move",
		{"player_id": player_id, "unit_id": unit_id, "to_x": to_x, "to_y": to_y})


func action_attack(game_id: int, player_id: int, attacker_id: int, target_id: int) -> void:
	request("POST", _ACTIONS_GAME_BASE.format({"id": game_id}) + "/attack",
		{"player_id": player_id, "attacker_id": attacker_id, "target_id": target_id})


func action_skill(game_id: int, player_id: int, unit_id: int, skill: String, target_id: int = -1) -> void:
	var body := {"player_id": player_id, "unit_id": unit_id, "skill": skill}
	if target_id >= 0:
		body["target_id"] = target_id
	request("POST", _ACTIONS_GAME_BASE.format({"id": game_id}) + "/skill", body)


func action_wait(game_id: int, player_id: int, unit_id: int) -> void:
	request("POST", _ACTIONS_GAME_BASE.format({"id": game_id}) + "/wait",
		{"player_id": player_id, "unit_id": unit_id})


func action_claim(game_id: int, player_id: int, unit_id: int) -> void:
	request("POST", _ACTIONS_GAME_BASE.format({"id": game_id}) + "/claim",
		{"player_id": player_id, "unit_id": unit_id})


func action_recruit(game_id: int, player_id: int, tile_x: int, tile_y: int, unit_type: String) -> void:
	request("POST", _ACTIONS_GAME_BASE.format({"id": game_id}) + "/recruit",
		{"player_id": player_id, "tile_x": tile_x, "tile_y": tile_y, "unit_type": unit_type})


func action_end_turn(game_id: int, player_id: int) -> void:
	request("POST", _ACTIONS_GAME_BASE.format({"id": game_id}) + "/end-turn",
		{"player_id": player_id})


func action_co_power(game_id: int, player_id: int) -> void:
	request("POST", _ACTIONS_GAME_BASE.format({"id": game_id}) + "/co-power",
		{"player_id": player_id})


# ============================================================
# Game lifecycle (M2.5 lobby + create/join)
# ============================================================

func list_presets(callback: Callable = Callable()) -> void:
	request("GET", "/games/presets", {}, callback)


func list_games(callback: Callable = Callable()) -> void:
	request("GET", "/games", {}, callback)


func create_game(name: String, map_preset: String, map_biome: String, win_condition: String, callback: Callable = Callable()) -> void:
	request("POST", "/games", {
		"name": name,
		"map_preset": map_preset,
		"map_biome": map_biome,
		"win_condition": win_condition,
	}, callback)


func join_game(game_id: int, user_name: String, color: String = "", callback: Callable = Callable()) -> void:
	var body := {"user_name": user_name, "color": color}
	request("POST", _ACTIONS_GAME_BASE.format({"id": game_id}) + "/join", body, callback)


func start_game(game_id: int, callback: Callable = Callable()) -> void:
	request("POST", _ACTIONS_GAME_BASE.format({"id": game_id}) + "/start", {}, callback)


func get_lobby(game_id: int, callback: Callable = Callable()) -> void:
	request("GET", _ACTIONS_GAME_BASE.format({"id": game_id}) + "/lobby", {}, callback)


# ============================================================
# Helpers
# ============================================================

func _resolve_url(path: String) -> String:
	if path.begins_with("http://") or path.begins_with("https://") or path.begins_with("ws://") or path.begins_with("wss://"):
		return path
	var base := UserSettings.get_api_base()
	if path.begins_with("/"):
		return base + path
	return base + "/" + path
