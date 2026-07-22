extends Node
## M6.1 + T:94 AudioManager — BGM 切换 / 静音 / 实际音频加载与渐变。
##
## 单例 autoload。Web 端 app.js:136-260 AudioManager 切换 BGM
## + 渐入渐出 + 静音 + 状态机。Godot 用 AudioStreamPlayer + bus
## volume_db 控制。

const _MUSIC_BUS := "Music"
const _DEFAULT_CROSSFADE_MS := 600

var _bgm_stream: AudioStream = null
var _bgm_volume: float = 1.0  # 0..1 linear
var _muted: bool = false

# 当前 BGM 的 track_id,用于在 apply_battle_bgm 被反复调用时
# 跳过 crossfade,避免每次 state snapshot 都把音乐从头播放。
var _current_track_id: String = ""

# T:94 — 真实音频资源缓存(避免重复磁盘读)
# key 是 track_id(如 "sample_battle_01");value 是 AudioStream
# 在 audio/ 目录匹配 <track_id>.ogg / .mp3 / .wav 任意后缀
# 由 caller 通过 _load_track(track_id) 装填
var _track_cache: Dictionary = {}

# 07-21 M7 — BGM crossfade state. The active player is the one we are
# currently fading in / holding at the target volume; the "previous"
# player is the one we fade out and free. Both are owned by this
# autoload so freeing them does not collide with main.gd's BGMPlayer.
var _active_player: AudioStreamPlayer = null
var _fade_player: AudioStreamPlayer = null
var _fade_tween: Tween = null


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
	# 07-22 fix:同一首 BGM 重复触发时不要重新 crossfade — 否则每次
	# state snapshot 都会把音乐从头播放,出现"卡在开头"的症状。
	if track_id == _current_track_id and _active_player != null and _active_player.playing:
		return
	var stream: AudioStream = _load_track(track_id)
	if stream == null:
		# 没找到音频文件 — 静默(no-op,不报错)
		return
	_current_track_id = track_id
	var target_volume: float = float(bgm.get("volume", 0.8))
	var fade_in_ms: int = int(bgm.get("fade_in_ms", _DEFAULT_CROSSFADE_MS))
	# 07-21 M7 — crossfade BGM 切换:旧流 fade-out,新流 fade-in。
	# 没有 crossfade 时旧版是直接 set_stream,会有明显的"咔嗒"。
	crossfade_to(stream, fade_in_ms, target_volume)


# 07-21 M7 — 把 ``stream`` 设为活动 BGM,使用 ``ms`` 毫秒做 crossfade。
# 旧的活动流被移到 _fade_player,在同时间内淡出后被释放;新流从
# 静音 0 淡入到 ``target_volume``(默认使用 _bgm_volume)。
func crossfade_to(stream: AudioStream, ms: int = _DEFAULT_CROSSFADE_MS, target_volume: float = -1.0) -> void:
	if stream == null:
		return
	# 取消任何进行中的 fade。
	if _fade_tween != null and _fade_tween.is_running():
		_fade_tween.kill()
	_fade_tween = null
	# 旧流交给 _fade_player 做淡出。
	if _active_player != null and _active_player.playing:
		_fade_player = _active_player
	else:
		if _active_player != null:
			_active_player.queue_free()
		_fade_player = null
	# 新流作为 _active_player,从 0 音量开始。
	var new_player := AudioStreamPlayer.new()
	new_player.bus = _MUSIC_BUS
	new_player.stream = stream
	new_player.volume_db = -80.0
	add_child(new_player)
	new_player.play()
	_active_player = new_player
	# 记录用户期望的目标音量(默认沿用当前 _bgm_volume)。
	if target_volume < 0.0:
		target_volume = _bgm_volume
	_bgm_stream = stream
	# 用 Tween 在 ``ms`` 毫秒内做两条对向渐变。
	var tween := create_tween()
	tween.set_parallel(true)
	tween.tween_property(_active_player, "volume_db", _db_for_volume(target_volume), float(ms) / 1000.0)
	if _fade_player != null:
		tween.tween_property(_fade_player, "volume_db", -80.0, float(ms) / 1000.0)
	_fade_tween = tween
	tween.finished.connect(_on_crossfade_finished.bind(_fade_player), CONNECT_ONE_SHOT)


func _on_crossfade_finished(prev: AudioStreamPlayer) -> void:
	# 释放淡出完的旧 player。
	if prev != null and is_instance_valid(prev):
		prev.stop()
		prev.queue_free()
	if _fade_player == prev:
		_fade_player = null


# dB 换算(0..1 linear → dB);0 映射为 -80dB(几乎静音)
func _db_for_volume(volume: float) -> float:
	if _muted:
		return -80.0
	return 20.0 * log(max(volume, 0.0001)) / log(10.0)


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
