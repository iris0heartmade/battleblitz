extends RefCounted
class_name UIPanelFocus
## UIPanelFocus — "打开 panel 时 grab focus 到默认按钮"工具 (2026-08-09 接入)
##
## 纯静态方法,被 main.gd 在每个 panel 显示/隐藏时调用。
## 把这个写成一个类只是为了 namespace,避免在 main.gd 里堆 helper 函数。
##
## 配套机制:Godot Button 默认 focus_mode = FOCUS_ALL,自动响应:
##   - ui_accept (Enter / 手柄 A)→ emit pressed
##   - 方向键 (ui_up/down/left/right)→ focus_neighbor_* 跳转
##   - Tab / Shift+Tab → focus next/prev
## tscn 里设的 focus_neighbor_* 决定方向键的跳转目标,本工具不替玩家配置。
## 如果 tscn 没设,Godot 用 built-in 几何邻居(下/右),大部分 case 够用。
## 多个按钮在 HBoxContainer 里,默认几何邻居是 →,得用 Shift+Tab 反向。
## 复杂布局用 focus_neighbor_top/bottom 显式设。

## 在 panel 第一次显示时 grab focus 到 default_focus。
## 重复调用是安全的(visible 已经是 true 的话啥也不做)。
static func grab_on_show(panel_root: Control, default_focus: Button) -> void:
	if panel_root == null or not is_instance_valid(panel_root):
		return
	if not panel_root.visible:
		return
	if default_focus == null or not is_instance_valid(default_focus):
		return
	if not default_focus.is_visible_in_tree():
		return
	default_focus.grab_focus()


## 兜底:从 panel_root 的子节点里挑第一个可见、可 focus 的 Button。
## 在没显式 default_focus 的 panel 上用。
static func grab_first_focusable(panel_root: Control) -> void:
	if panel_root == null or not is_instance_valid(panel_root):
		return
	if not panel_root.visible:
		return
	var found := _find_focusable(panel_root)
	if found != null:
		found.grab_focus()


static func _find_focusable(node: Node) -> Button:
	if node is Button:
		var b: Button = node
		if b.is_visible_in_tree() and b.focus_mode != Control.FOCUS_NONE and not b.disabled:
			return b
	for child in node.get_children():
		var r: Button = _find_focusable(child)
		if r != null:
			return r
	return null
