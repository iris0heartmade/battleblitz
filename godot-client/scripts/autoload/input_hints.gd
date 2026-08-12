extends Node
## InputHints — 平台感知的按键提示文案 (2026-08-09 接入)
##
## 统一在 UI 里写"按 X 确认"的时候,不要硬编码 "[A] 确认",
## 而是调 InputHints.confirm() → 根据当前平台返回 "[B] 确认" / "[A] 确认" / "[Enter] 确认"。
##
## 平台判断:
##   - 当前 Godot 没暴露"玩家实际使用的手柄型号",只能通过
##     `Input.get_connected_joypads()` 看有没有手柄。
##   - 玩家可在 user_settings 写 "settings.v1.controller_style" 覆盖
##     (auto / xbox / playstation / switch)。默认 auto(用手柄时显示 switch 反转)。
##   - 没手柄时强制显示键盘提示。
##
## 用法:
##   Label.text = "[%s] 确认  [%s] 取消" % [InputHints.confirm(), InputHints.cancel()]

# 当前显示的风格(auto 解析一次,玩家可手动覆盖)
enum Style { AUTO, KEYBOARD, XBOX, PLAYSTATION, SWITCH }

const _STYLE_KEY := "settings.v1.controller_style"

# 5 个平台 × 4 个动作的提示文字
# confirm/cancel/zoom_in/zoom_out — phase 2 棋盘用
# ↑↓←→ 不在这里,UI 走系统 ui_* 自动就显示方向键,棋盘走 cell 光标不需要方向键提示
const _TEXTS := {
	Style.KEYBOARD: {
		"confirm": "Z/Enter",
		"cancel":  "X/Esc",
		"zoom_in": "E/+",
		"zoom_out": "Q/-",
		"pause":   "Esc",
		"end_turn": "E",
	},
	Style.XBOX: {
		"confirm": "A",
		"cancel":  "B",
		"zoom_in": "RB",
		"zoom_out": "LB",
		"pause":   "Start",
		"end_turn": "Y",
	},
	Style.PLAYSTATION: {
		"confirm": "×",
		"cancel":  "○",
		"zoom_in": "R1",
		"zoom_out": "L1",
		"pause":   "Options",
		"end_turn": "△",
	},
	Style.SWITCH: {
		"confirm": "B",  # Switch 反转:B=确认 / A=取消
		"cancel":  "A",
		"zoom_in": "R",
		"zoom_out": "L",
		"pause":   "+",
		"end_turn": "X",
	},
}

var _cached_style: int = -1
var _has_joypad_cached: bool = false
var _joypad_cached_frame: int = -1


func _ready() -> void:
	# 不在 _ready 里调 Input(autoload _ready 早于 main scene,_ready 阶段
	# Input.get_connected_joypads() 可能还没就绪)。第一次访问时再 cache。
	pass


# === Public API ===

func confirm() -> String:
	return _text("confirm")


func cancel() -> String:
	return _text("cancel")


func zoom_in() -> String:
	return _text("zoom_in")


func zoom_out() -> String:
	return _text("zoom_out")


func pause() -> String:
	return _text("pause")


func end_turn() -> String:
	return _text("end_turn")


# 平台是否手柄(用于决定按钮/光标操作的文案)。
# 即使有手柄也用 Keyboard 显示也是 OK 的 — 玩家手柄坏了用键盘的 case。
# 实际游戏里 UI 文案会调 confirm()/cancel() 等拿对应平台文字。
func is_using_joypad() -> bool:
	_refresh_joypad_cache()
	return _has_joypad_cached


func current_style_name() -> String:
	_refresh_style()
	match _cached_style:
		Style.KEYBOARD: return "keyboard"
		Style.XBOX: return "xbox"
		Style.PLAYSTATION: return "playstation"
		Style.SWITCH: return "switch"
		_: return "auto"


# === Internal ===

func _text(action: String) -> String:
	_refresh_style()
	var table: Dictionary = _TEXTS.get(_cached_style, _TEXTS[Style.KEYBOARD])
	return String(table.get(action, "?"))


func _refresh_style() -> void:
	var configured: String = String(UserSettings.get_value(_STYLE_KEY, "auto"))
	if configured == "auto":
		_refresh_joypad_cache()
		# auto 模式:有手柄 → switch 反转(因为玩家选了 Switch 风格)
		# 没手柄 → keyboard
		_cached_style = Style.SWITCH if _has_joypad_cached else Style.KEYBOARD
		return
	match configured:
		"keyboard":    _cached_style = Style.KEYBOARD
		"xbox":        _cached_style = Style.XBOX
		"playstation": _cached_style = Style.PLAYSTATION
		"switch":      _cached_style = Style.SWITCH
		_:
			_refresh_joypad_cache()
			_cached_style = Style.SWITCH if _has_joypad_cached else Style.KEYBOARD


func _refresh_joypad_cache() -> void:
	# 手柄拔插频繁,不要每帧去查 Input.get_connected_joypads()。
	# 但也不要太久才更新 — 简单策略:每 30 帧刷一次。
	var now: int = Engine.get_process_frames()
	if now - _joypad_cached_frame < 30:
		return
	_joypad_cached_frame = now
	_has_joypad_cached = Input.get_connected_joypads().size() > 0
