## button_row.gd — UI V3 按钮行(HBoxContainer + 自动间距 + 主/次/危险三态主题)。
##
## 用法:
##   var row := ButtonRow.new()
##   row.add_button("继续", ButtonRow.ButtonKind.PRIMARY)
##   row.add_button("删除", ButtonRow.ButtonKind.DANGER)
##   row.add_button("覆盖", ButtonRow.ButtonKind.SECONDARY)
##   parent.add_child(row)
##
## 视觉:HBoxContainer,GAP_M(16px) 间距;按钮按下自动走 MenuTheme.apply_*_theme。
## PRIMARY=金底烫金亮边(关键操作),DANGER=红边(删除/危险),SECONDARY=蓝底(默认)。

class_name ButtonRow
extends HBoxContainer

enum ButtonKind { PRIMARY, SECONDARY, DANGER }

const MenuTheme = preload("res://scripts/ui/menu_theme.gd")

var _buttons: Array[Button] = []


func _init() -> void:
	mouse_filter = Control.MOUSE_FILTER_PASS
	add_theme_constant_override("separation", MenuTheme.GAP_M)


func add_button(text: String, kind: ButtonKind = ButtonKind.SECONDARY) -> Button:
	var btn := Button.new()
	btn.text = text
	match kind:
		ButtonKind.PRIMARY:
			MenuTheme.apply_primary_button_theme(btn, MenuTheme.FS_BTN)
		ButtonKind.DANGER:
			MenuTheme.apply_secondary_button_theme(btn, MenuTheme.FS_BTN)
			# DANGER:把 secondary 的边从 GOLD 改成 FIRE_RED(改 stylebox)
			var sb := btn.get_theme_stylebox("normal").duplicate()
			sb.border_color = MenuTheme.C_FIRE_RED
			btn.add_theme_stylebox_override("normal", sb)
			var sb_h := sb.duplicate()
			sb_h.border_color = MenuTheme.C_FIRE_RED
			btn.add_theme_stylebox_override("hover", sb_h)
		_:
			MenuTheme.apply_button_theme(btn, MenuTheme.FS_BTN)
	_buttons.append(btn)
	add_child(btn)
	return btn


func add_buttons(items: Array) -> Array[Button]:
	var out: Array[Button] = []
	for item in items:
		var text: String = str(item.get("text", ""))
		var kind: int = int(item.get("kind", ButtonKind.SECONDARY))
		out.append(add_button(text, kind))
	return out


func get_buttons() -> Array[Button]:
	return _buttons