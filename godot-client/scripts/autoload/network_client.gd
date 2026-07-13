extends Node
## NetworkClient — autoload wrapping HTTP + WebSocket calls to the
## Python backend. M0/M1 ships an HTTP stub (GET /games/presets is
## enough to verify the URL wiring); M2 will add the WebSocketPeer
## and the action dispatcher.
##
## Base URLs come from `UserSettings` (which falls back to Config
## defaults). The full REST/WS surface lives in
## `../docs/路线/Godot移植方案.md` §5.6.

signal api_response(method: String, path: String, body: Dictionary, http_code: int)
signal api_error(method: String, path: String, error: String, http_code: int)
signal ws_connected()
signal ws_disconnected(reason: String)
signal ws_message_received(message: Dictionary)

const _REQ_TIMEOUT_SEC := 10.0

var _http: HTTPRequest
var _ws: WebSocketPeer = null
var _ws_url: String = ""
var _is_ws_connected: bool = false
var _ws_poll_timer: Timer = null


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
	# `HTTPRequest.request` signature in Godot 4: (url, headers, method, data).
	# We translate the string verb into the HTTPClient.Method enum.
	var http_method: int = _method_to_enum(method)
	var err := _http.request(url, headers, http_method, data)
	if err != OK:
		var msg := "HTTPRequest.request failed: %s" % error_string(err)
		api_error.emit(method, path, msg, 0)
		if callback.is_valid():
			callback.call({"error": msg}, 0)
		return
	# Tag the in-flight request so the completion handler can route.
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
# WebSocket — M2 stub (parses incoming JSON, no auto-reconnect yet)
# ============================================================

## Open a WebSocket connection. `url` should be a full
## `ws://host/ws/games/{id}?player_id={pid}&since_seq={N}` URL.
## M1 leaves this dormant; M2 will wire reconnect + heartbeat.
func ws_connect(url: String) -> void:
	_ws_url = url
	if _ws != null:
		_ws.disconnect_from_host()
	_ws = WebSocketPeer.new()
	var err := _ws.connect_to_url(url)
	if err != OK:
		ws_disconnected.emit("connect_to_url: %s" % error_string(err))
		return
	_is_ws_connected = false
	if _ws_poll_timer == null:
		_ws_poll_timer = Timer.new()
		_ws_poll_timer.wait_time = 0.05
		_ws_poll_timer.timeout.connect(_ws_poll)
		add_child(_ws_poll_timer)
	_ws_poll_timer.start()


func ws_close() -> void:
	if _ws != null:
		_ws.close()
	_is_ws_connected = false


func _ws_poll() -> void:
	if _ws == null:
		return
	_ws.poll()
	var state := _ws.get_ready_state()
	match state:
		WebSocketPeer.STATE_OPEN:
			if not _is_ws_connected:
				_is_ws_connected = true
				ws_connected.emit()
			while _ws.get_available_packet_count() > 0:
				var pkt := _ws.get_packet()
				var text := pkt.get_string_from_utf8()
				var parsed: Variant = JSON.parse_string(text) if text.length() > 0 else {}
				if parsed is Dictionary:
					ws_message_received.emit(parsed)
		WebSocketPeer.STATE_CLOSING:
			pass  # keep polling until we hit CLOSED
		WebSocketPeer.STATE_CLOSED:
			var code := _ws.get_close_code()
			var reason := _ws.get_close_reason()
			ws_disconnected.emit("code %d: %s" % [code, reason])
			_is_ws_connected = false
			_ws = null
			if _ws_poll_timer != null:
				_ws_poll_timer.stop()


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
