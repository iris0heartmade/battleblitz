extends Node
## UserSettings — ConfigFile wrapper replacing `localStorage` from the
## JS frontend. Persists to `user://battleblitz.cfg`.
##
## Keys (kept in sync with the JS frontend's localStorage usage in
## `app.js` showSettings / showLobby):
##   settings.v1.player_name, settings.v1.player_color,
##   settings.v1.theme, settings.v1.volume
##   session.v1.last_game_id, session.v1.last_player_id
##   ui.split_left (left column width)

const _CFG_PATH := "user://battleblitz.cfg"

# Cached in-memory dict. Reads via get_value(), writes via set_value().
# On startup we hydrate from disk; on quit we flush.
var _data: Dictionary = {}
var _dirty: bool = false

# Defaults mirror the JS `loadSettings()` defaults in app.js.
const DEFAULTS: Dictionary = {
	"settings.v1.player_name": "",
	"settings.v1.player_color": "red",
	"settings.v1.theme": "dark",
	"settings.v1.volume": 0.7,
	"session.v1.last_game_id": 0,
	"session.v1.last_player_id": 0,
	"ui.split_left": 0.32,
}

const SERVER_DEFAULTS: Dictionary = {
	"server.api_base": "http://127.0.0.1:8000",
	"server.ws_base": "ws://127.0.0.1:8000",
}


func _ready() -> void:
	_load()


func get_value(key: String, fallback: Variant = null) -> Variant:
	if _data.has(key):
		return _data[key]
	if DEFAULTS.has(key):
		return DEFAULTS[key]
	return fallback


func set_value(key: String, value: Variant) -> void:
	if _data.get(key, null) == value:
		return
	_data[key] = value
	_dirty = true


# Apply the resolved server base URLs onto the live Config autoload.
# Called by NetworkClient.connect_to_server() at startup.
func get_api_base() -> String:
	return get_value("server.api_base", Config.DEFAULT_API_BASE)


func get_ws_base() -> String:
	return get_value("server.ws_base", Config.DEFAULT_WS_BASE)


# ============================================================
# Persistence
# ============================================================

func _load() -> void:
	var cfg := ConfigFile.new()
	var err := cfg.load(_CFG_PATH)
	if err == OK:
		for section in cfg.get_sections():
			for k in cfg.get_section_keys(section):
				_data["%s.%s" % [section, k]] = cfg.get_value(section, k)
	# Always overlay defaults so new keys land even if the file is old.
	for k in DEFAULTS:
		if not _data.has(k):
			_data[k] = DEFAULTS[k]
	for k in SERVER_DEFAULTS:
		if not _data.has(k):
			_data[k] = SERVER_DEFAULTS[k]


func _save() -> void:
	if not _dirty:
		return
	var cfg := ConfigFile.new()
	for key in _data:
		# Explicit Array[String] annotation: `String.split` returns
		# PackedStringArray in Godot 4, which `:=` can't infer.
		var parts: PackedStringArray = key.split(".", true, 1)
		if parts.size() != 2:
			continue
		cfg.set_value(parts[0], parts[1], _data[key])
	cfg.save(_CFG_PATH)
	_dirty = false


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST or what == NOTIFICATION_PREDELETE:
		_save()
