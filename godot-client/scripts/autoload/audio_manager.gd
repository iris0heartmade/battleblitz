extends Node
## M6.1 AudioManager — BGM 切换 / 静音切换 / 简单播放状态。
##
## 单例 autoload。Web 端 app.js:136-260 AudioManager 切换 BGM
## + 渐入渐出 + 静音 + 状态机。Godot 用 AudioStreamPlayer + bus
## volume_db 控制。
##
## 用法:
##   AudioManager.set_bgm_stream(stream)
##   AudioManager.set_muted(true)
##   AudioManager.set_volume(0.5)

const _MUSIC_BUS := "Music"

var _bgm_stream: AudioStream = null
var _bgm_volume: float = 1.0  # 0..1 linear
var _muted: bool = false


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
