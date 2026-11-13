extends RefCounted
## 轻量军议：外部公共视觉配置。所有主题入口共享颜色、留白与状态。
const INK := Color("#111d2c")
const PANEL := Color("#172638f2")
const RAISED := Color("#223247")
const HOVER := Color("#30465e")
const TEXT := Color("#f2ebdd")
const DIM := Color("#afbdcb")
const GOLD := Color("#b59b68")
const GOLD_LIGHT := Color("#d6c296")
const LINE := Color("#52607399")
const DISABLED := Color("#788593")
const DANGER := Color("#e48586")
const SUCCESS := Color("#82bd99")
const PAPER := Color("#e9e5dc")
const PAPER_INK := Color("#26354a")
const PAPER_DIM := Color("#526074")
const PAPER_ACCENT := Color("#795f35")
const SPACE := 16
const EDGE := 1

static func surface(fill: Color = PANEL, border: Color = LINE, padding: int = SPACE) -> StyleBoxFlat:
	var box := StyleBoxFlat.new()
	box.bg_color = fill
	box.border_color = border
	box.set_border_width_all(EDGE)
	box.set_corner_radius_all(4)
	box.content_margin_left = padding
	box.content_margin_right = padding
	box.content_margin_top = padding
	box.content_margin_bottom = padding
	return box

static func state_box(state: String, kind: String = "button") -> StyleBoxFlat:
	var box := surface(RAISED, LINE, 12)
	box.content_margin_top = 8
	box.content_margin_bottom = 8
	match state:
		"hover":
			box.bg_color = HOVER
			box.border_color = GOLD_LIGHT
		"pressed":
			box.bg_color = INK
			box.border_color = GOLD
		"selected", "active":
			box.bg_color = HOVER
			box.border_color = GOLD
			box.border_width_left = 3
		"disabled":
			box.bg_color = Color(RAISED, 0.45)
			box.border_color = Color(LINE, 0.3)
		"focus":
			box.bg_color = Color.TRANSPARENT
			box.border_color = GOLD_LIGHT
			box.set_border_width_all(2)
	if kind == "tab":
		box.border_width_top = 0
		box.border_width_left = 0
		box.border_width_right = 0
		box.border_width_bottom = 2 if state in ["selected", "active"] else 1
	elif kind == "row" and state in ["neutral", "normal"]:
		box.bg_color = Color(INK, 0.42)
		box.border_color = Color(LINE, 0.3)
	return box

static func button(button: Button, primary: bool = false, font_size: int = 17, danger: bool = false) -> void:
	button.add_theme_font_size_override("font_size", font_size)
	button.add_theme_color_override("font_color", DANGER if danger else TEXT)
	button.add_theme_color_override("font_hover_color", TEXT)
	button.add_theme_color_override("font_pressed_color", TEXT)
	button.add_theme_color_override("font_disabled_color", DISABLED)
	button.add_theme_constant_override("outline_size", 0)
	for state in ["normal", "hover", "pressed", "disabled", "focus"]:
		var style := state_box("selected" if state == "normal" and primary else state)
		if danger and state != "disabled":
			style.border_color = DANGER
		button.add_theme_stylebox_override(state, style)

## 继承式主题覆盖后续动态创建控件；不遍历重写文字，保留敌我/危险语义。
static func create_theme() -> Theme:
	var theme := Theme.new()
	theme.default_font_size = 18
	for type_name in ["Label", "Button", "OptionButton", "CheckButton", "CheckBox", "LineEdit", "SpinBox", "PopupMenu", "ItemList"]:
		theme.set_color("font_color", type_name, TEXT)
		theme.set_color("font_disabled_color", type_name, DISABLED)
		theme.set_color("font_hover_color", type_name, TEXT)
		theme.set_color("font_selected_color", type_name, TEXT)
	for type_name in ["Button", "OptionButton"]:
		for state in ["normal", "hover", "pressed", "disabled", "focus"]:
			theme.set_stylebox(state, type_name, state_box(state))
	for type_name in ["LineEdit", "TextEdit"]:
		theme.set_stylebox("normal", type_name, surface(INK, LINE, 10))
		theme.set_stylebox("focus", type_name, state_box("focus"))
		theme.set_stylebox("read_only", type_name, state_box("disabled"))
		theme.set_color("font_placeholder_color", type_name, DIM)
		theme.set_color("caret_color", type_name, GOLD_LIGHT)
	for type_name in ["Panel", "PanelContainer", "PopupPanel", "PopupMenu"]:
		theme.set_stylebox("panel", type_name, surface())
	theme.set_stylebox("hover", "PopupMenu", state_box("hover"))
	theme.set_color("default_color", "RichTextLabel", TEXT)
	theme.set_constant("line_separation", "RichTextLabel", 4)
	for type_name in ["HSlider", "VSlider", "HScrollBar", "VScrollBar"]:
		theme.set_stylebox("scroll", type_name, surface(INK, Color.TRANSPARENT, 2))
		for state in ["grabber", "grabber_highlight", "grabber_pressed"]:
			theme.set_stylebox(state, type_name, surface(GOLD if state == "grabber_pressed" else RAISED, LINE, 4))
	return theme
