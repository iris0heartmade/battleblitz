extends Node
## InputState — autoload tracking the user's current interaction mode.
##
## Mirrors the transient `state.selectedUnit / actionMode / path / ...`
## from the JS frontend. Lives in an autoload so the InputState survives
## scene changes (board ↔ menu) without re-derivation.
##
## M1 leaves most fields at their defaults — the Board scene just
## displays the map. M2 wires `set_mode` to the click handlers.

signal mode_changed(new_mode: int)
signal selected_unit_changed(unit_id: Variant)
signal hover_tile_changed(tile: Vector2i)
# 2026-08-09:棋盘虚拟光标信号 — 键盘/手柄移动 + 视觉高亮
signal cursor_cell_changed(cell: Vector2i)
signal board_focus_changed(focused: bool)

# Interaction modes — see `app.js` `onCellClick` for the JS equivalents.
enum Mode {
	IDLE,        # nothing selected, hover shows info only
	UNIT_SELECTED,  # a friendly unit is selected; show reach + path on hover
	MOVE_MODE,      # user is choosing a destination tile
	ATTACK_MODE,    # user is choosing a target
	CLAIM_MODE,     # user is targeting a claimable tile
	RECRUIT_MODE,   # user is targeting an empty barracks
	SKILL_MODE,     # user is choosing a skill target
}

var mode: int = Mode.IDLE:
	set(value):
		if mode == value:
			return
		mode = value
		mode_changed.emit(value)

var selected_unit_id: Variant = null:           # int | null
	set(value):
		selected_unit_id = value
		selected_unit_changed.emit(value)

var hover_tile: Vector2i = Vector2i(-1, -1):
	set(value):
		hover_tile = value
		hover_tile_changed.emit(value)

# 2026-08-09:棋盘虚拟光标 + 棋盘 focus 模式
# cursor_cell:键盘/手柄模式下"我正看着的格子",在 board 上画黄方框。
#   (-1, -1) 表示未初始化(由 GameView 启动时设到地图中心或第一个单位)。
# board_focused:true 时 InputHints 走 board_* action(光标移动 / 确认 / 取消),
#   HUD / 菜单的 ui_accept 走 Button 默认行为。
#   切换 GameView 时 main 负责 enter_board_focus(),切到 menu/pause 时
#   exit_board_focus() 释放光标。
var cursor_cell: Vector2i = Vector2i(-1, -1):
	set(value):
		if cursor_cell == value:
			return
		cursor_cell = value
		cursor_cell_changed.emit(value)
var board_focused: bool = false:
	set(value):
		if board_focused == value:
			return
		board_focused = value
		board_focus_changed.emit(value)

# Cached reachable tiles + best path for the currently selected unit.
# M2 will populate these via MapLogic.compute_reachable + pathfind.
var reachable_tiles: Array = []                 # Array[Vector2i]
var current_path: Array = []                    # Array[Vector2i]


# --- Board-click lock for modal interactions (dialogs, confirm prompts) ---
# 嵌套可重入 — N 个 lock() 必须 N 个 unlock() 才解锁
var _lock_count: int = 0
signal lock_changed(locked: bool)

func lock() -> void:
	_lock_count += 1
	if _lock_count == 1:
		lock_changed.emit(true)


func unlock() -> void:
	_lock_count = max(0, _lock_count - 1)
	if _lock_count == 0:
		lock_changed.emit(false)


func set_locked(value: bool) -> void:
	if value:
		lock()
	elif _lock_count > 0:
		while _lock_count > 0:
			unlock()


func is_input_locked() -> bool:
	return _lock_count > 0
