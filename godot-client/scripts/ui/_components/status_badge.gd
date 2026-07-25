## status_badge.gd — UI V3 状态徽章(单 Label,带前缀图标 + 配色 token)。
##
## 用法:
##   var badge := StatusBadge.new()
##   badge.setup(StatusBadge.Kind.OK, "已选")
##   add_child(badge)
##
## 颜色 / 字号 / 间距全部走 MenuTheme token,不暴露任何调色 API。

class_name StatusBadge
extends Label

const MenuTheme = preload("res://scripts/ui/menu_theme.gd")

enum Kind { OK, EMPTY, WARNING, LOADING, ERROR }

# 这些字典在 _init 里初始化 — 不能在 const 里引用 MenuTheme,
# 因为 Godot parse 阶段不会解析跨脚本的常量引用。
static var _PREFIX: Dictionary = {}
static var _COLOR: Dictionary = {}
static var _FONT_SIZE: Dictionary = {}


func _init() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	if _PREFIX.is_empty():
		_PREFIX = {
			Kind.OK: "✓ ",
			Kind.EMPTY: "— ",
			Kind.WARNING: "⚠ ",
			Kind.LOADING: "⏳ ",
			Kind.ERROR: "✕ ",
		}
		_COLOR = {
			Kind.OK: MenuTheme.C_HEAL_GREEN,
			Kind.EMPTY: MenuTheme.C_TEXT_DIM,
			Kind.WARNING: MenuTheme.C_FIRE_RED,
			Kind.LOADING: MenuTheme.C_LOADING,
			Kind.ERROR: MenuTheme.C_ERROR,
		}
		_FONT_SIZE = {
			Kind.OK: MenuTheme.FS_BODY_SM,
			Kind.EMPTY: MenuTheme.FS_PLACEHOLDER,
			Kind.WARNING: MenuTheme.FS_BODY_SM,
			Kind.LOADING: MenuTheme.FS_LOADING,
			Kind.ERROR: MenuTheme.FS_BODY_SM,
		}


func setup(kind: Kind, text: String) -> void:
	text = _PREFIX.get(kind, "") + text
	var color: Color = _COLOR.get(kind, MenuTheme.C_TEXT_WARM)
	var font_size: int = _FONT_SIZE.get(kind, MenuTheme.FS_BODY_SM)
	add_theme_font_size_override("font_size", font_size)
	add_theme_color_override("font_color", color)
	if kind == Kind.LOADING:
		text = "[i]%s[/i]" % text
	self.text = text.replace("[i]", "").replace("[/i]", "")