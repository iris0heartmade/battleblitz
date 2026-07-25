## section_header.gd — UI V3 section 标题(14px 烫金 + 灰色 hint + 1px 烫金分隔线)。
##
## 用法:
##   var hdr := SectionHeader.new("三存档槽", "按需手存,每槽独立")
##   vbox.add_child(hdr)
##
## 视觉:Label(title) + Label(hint, 灰色小字) 横排 + 下方 1px HSeparator(烫金)。
## 全部 token 走 MenuTheme,不暴露调色 API。

class_name SectionHeader
extends VBoxContainer

const MenuTheme = preload("res://scripts/ui/menu_theme.gd")

var _title_label: Label
var _hint_label: Label
var _separator: HSeparator


func _init(title: String = "", hint: String = "") -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_theme_constant_override("separation", MenuTheme.GRID_2)
	_title_label = Label.new()
	_title_label.add_theme_font_size_override("font_size", MenuTheme.FS_SECTION)
	_title_label.add_theme_color_override("font_color", MenuTheme.C_GOLD)
	_title_label.text = title
	add_child(_title_label)
	if hint != "":
		_hint_label = Label.new()
		_hint_label.add_theme_font_size_override("font_size", MenuTheme.FS_HINT)
		_hint_label.add_theme_color_override("font_color", MenuTheme.C_PLACEHOLDER)
		_hint_label.text = "  · " + hint
		add_child(_hint_label)
	_separator = HSeparator.new()
	MenuTheme.apply_section_divider(_separator)
	add_child(_separator)


func set_title(title: String) -> void:
	if _title_label != null:
		_title_label.text = title


func set_hint(hint: String) -> void:
	if _hint_label == null:
		_hint_label = Label.new()
		_hint_label.add_theme_font_size_override("font_size", MenuTheme.FS_HINT)
		_hint_label.add_theme_color_override("font_color", MenuTheme.C_PLACEHOLDER)
		add_child(_hint_label)
	_hint_label.text = "  · " + hint