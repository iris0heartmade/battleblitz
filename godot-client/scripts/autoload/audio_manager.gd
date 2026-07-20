extends Node
## M6.1 + T:94 AudioManager — BGM 切换 / 静音 / 实际音频加载与渐变。
##
## 单例 autoload。Web 端 app.js:136-260 AudioManager 切换 BGM
## + 渐入渐出 + 静音 + 状态机。Godot 用 AudioStreamPlayer + bus
## volume_db 控制。

const _MUSIC_BUS := "Music"

var _bgm_stream: AudioStream = null
var _bgm_volume: float = 1.0  # 0..1 linear
var _muted: bool = false

# T:94 — 真实音频资源缓存(避免重复磁盘读)
# key 是 track_id(如 "sample_battle_01");value 是 AudioStream
# 在 audio/ 目录匹配 <track_id>.ogg / .mp3 / .wav 任意后缀
# 由 caller 通过 _load_track(track_id) 装填
var _track_cache: Dictionary = {}


func _ready() -> void:
	# 确保 Music bus 存在
	var idx: int = AudioServer.get_bus_index(_MUSIC_BUS)
	if idx == -1:
		AudioServer.add_bus()
		AudioServer.set_bus_name(AudioServer.bus_count - 1, _MUSIC_BUS)
	_apply_volume_to_bus()


func set_bgm_stream(stream: AudioStream) -> void:
	_bgm_stream = stream


func get_bgm_stream() -> AudioStream:
	return _bgm_stream


# T:94 — 按 track_id 装填 BGM(在 audio/ 目录找同 ID 的 .ogg / .mp3 / .wav)
func _load_track(track_id: String) -> AudioStream:
	if track_id == "":
		return null
	if _track_cache.has(track_id):
		return _track_cache[track_id]
	for ext in [".ogg", ".mp3", ".wav"]:
		var path := "res://audio/%s%s" % [track_id, ext]
		if ResourceLoader.exists(path):
			var s: AudioStream = load(path) as AudioStream
			if s != null:
				_track_cache[track_id] = s
				return s
	# 占位 fallback — 不报错,返回 null 让 caller 选择 silent 处理
	return null


# T:94 — 业务后台请求传 battle_config.audio.bgm 时调
# bgm dict 应含: {track_id, loop=true, volume, fade_in_ms, fade_out_ms}
func apply_battle_bgm(bgm: Dictionary) -> void:
	if bgm == null:
		return
	var track_id: String = String(bgm.get("track_id", ""))
	if track_id == "":
		return
	var stream: AudioStream = _load_track(track_id)
	if stream == null:
		# 没找到音频文件 — 静默(no-op,不报错)
		return
	set_bgm_stream(stream)
	# 如果 main.gd 已 bind BGMPlayer,把流塞进去
	var player := get_tree().root.get_node_or_null("Main/BGMPlayer") if get_tree() != null else null
	if player != null and player is AudioStreamPlayer:
		(player as AudioStreamPlayer).stream = stream
		if not (player as AudioStreamPlayer).playing:
			(player as AudioStreamPlayer).play()
	# 音量跟随 bgm.volume
	var v: float = float(bgm.get("volume", 0.8))
	set_volume(v)


func set_muted(m: bool) -> void:
	_muted = m
	_apply_volume_to_bus()


func is_muted() -> bool:
	return _muted


func toggle_muted() -> bool:
	_muted = not _muted
	_apply_volume_to_bus()
	return _muted


func set_volume(v: float) -> void:
	_bgm_volume = clamp(v, 0.0, 1.0)
	_apply_volume_to_bus()


func get_volume() -> float:
	return _bgm_volume


# dB = 20 * log10(volume); 静音映射为 -80dB
func _apply_volume_to_bus() -> void:
	var idx: int = AudioServer.get_bus_index(_MUSIC_BUS)
	if idx == -1: return
	var db: float = -80.0 if _muted else (20.0 * log(max(_bgm_volume, 0.0001)) / log(10.0))
	AudioServer.set_bus_volume_db(idx, db)
