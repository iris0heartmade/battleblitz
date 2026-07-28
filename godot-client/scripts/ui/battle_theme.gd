extends Node
## Visual treatment for the battle HUD. It deliberately does not own board state.

const C_INK: Color = Color("#081321")
const C_NAVY: Color = Color("#10243b")
const C_NAVY_LIGHT: Color = Color("#1a3858")
const C_GOLD: Color = Color("#c99c45")
const C_GOLD_BRIGHT: Color = Color("#f0cf7a")
const C_TEXT: Color = Color("#fff0cb")
const C_TEXT_DIM: Color = Color("#b6a783")
const C_RUBY: Color = Color("#8c273b")
const C_RUBY_DARK: Color = Color("#4e1421")
const SIDE_PANEL_ART: Texture2D = preload("res://assets/ui/battle_side_panel_translucent_v1.png")


static func _box(fill: Color, border: Color, width: int = 1, radius: int = 3) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = fill
	style.border_color = border
	style.set_border_width_all(width)
	style.set_corner_radius_all(radius)
	style.content_margin_left = 10
	style.content_margin_right = 10
	style.content_margin_top = 6
	style.content_margin_bottom = 6
	return style


static func apply_hud_badge(badge: ColorRect, label: Label) -> void:
	badge.color = Color(C_INK.r, C_INK.g, C_INK.b, 0.92)
	label.add_theme_font_size_override("font_size", 14)
	label.add_theme_color_override("font_color", C_TEXT)


static func apply_panel(panel: Panel, border: Color = C_GOLD) -> void:
	var style := _box(Color(C_INK.r, C_INK.g, C_INK.b, 0.94), border, 2, 5)
	style.shadow_color = Color(0.0, 0.0, 0.0, 0.38)
	style.shadow_size = 8
	style.shadow_offset = Vector2(0, 3)
	panel.add_theme_stylebox_override("panel", style)


static func apply_floating_panel(panel: Panel, border: Color = C_GOLD) -> void:
	# Side intelligence panels should reveal the battlefield beneath them.
	var style := _box(Color(C_INK.r, C_INK.g, C_INK.b, 0.18), border, 1, 5)
	style.shadow_color = Color(0.0, 0.0, 0.0, 0.28)
	style.shadow_size = 6
	style.shadow_offset = Vector2(0, 2)
	panel.add_theme_stylebox_override("panel", style)
	var skin := panel.get_node_or_null("ArtSkin") as TextureRect
	if skin == null:
		skin = TextureRect.new()
		skin.name = "ArtSkin"
		skin.mouse_filter = Control.MOUSE_FILTER_IGNORE
		skin.anchor_right = 1.0
		skin.anchor_bottom = 1.0
		skin.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		skin.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
		skin.texture = SIDE_PANEL_ART
		skin.modulate = Color(1.0, 1.0, 1.0, 0.24)
		panel.add_child(skin)
		panel.move_child(skin, 0)


static func apply_primary(button: Button) -> void:
	button.add_theme_font_size_override("font_size", 15)
	button.add_theme_color_override("font_color", C_INK)
	button.add_theme_color_override("font_hover_color", C_INK)
	button.add_theme_color_override("font_disabled_color", C_TEXT_DIM)
	var normal_style := _box(C_GOLD, C_GOLD_BRIGHT, 2, 3)
	var hover_style := _box(C_GOLD_BRIGHT, C_TEXT, 2, 3)
	var pressed_style := _box(C_NAVY_LIGHT, C_GOLD_BRIGHT, 2, 3)
	var disabled_style := _box(Color("#756746"), C_TEXT_DIM, 1, 3)
	button.add_theme_stylebox_override("normal", normal_style)
	button.add_theme_stylebox_override("hover", hover_style)
	button.add_theme_stylebox_override("pressed", pressed_style)
	button.add_theme_stylebox_override("disabled", disabled_style)
	button.add_theme_stylebox_override("focus", hover_style)


static func apply_secondary(button: Button) -> void:
	button.add_theme_font_size_override("font_size", 14)
	button.add_theme_color_override("font_color", C_TEXT)
	button.add_theme_color_override("font_hover_color", C_GOLD_BRIGHT)
	button.add_theme_color_override("font_disabled_color", C_TEXT_DIM)
	var normal_style := _box(C_NAVY, C_GOLD, 1, 3)
	var hover_style := _box(C_NAVY_LIGHT, C_GOLD_BRIGHT, 2, 3)
	var pressed_style := _box(C_INK, C_GOLD, 2, 3)
	var disabled_style := _box(Color("#182333"), Color("#5b6570"), 1, 3)
	button.add_theme_stylebox_override("normal", normal_style)
	button.add_theme_stylebox_override("hover", hover_style)
	button.add_theme_stylebox_override("pressed", pressed_style)
	button.add_theme_stylebox_override("disabled", disabled_style)
	button.add_theme_stylebox_override("focus", hover_style)


static func apply_danger(button: Button) -> void:
	apply_secondary(button)
	button.add_theme_color_override("font_color", C_TEXT)
	var normal_style := _box(C_RUBY_DARK, C_RUBY, 1, 3)
	var hover_style := _box(C_RUBY, C_GOLD_BRIGHT, 2, 3)
	button.add_theme_stylebox_override("normal", normal_style)
	button.add_theme_stylebox_override("hover", hover_style)
	button.add_theme_stylebox_override("focus", hover_style)


static func apply_header(label: Label, font_size: int = 15) -> void:
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", C_GOLD_BRIGHT)


static func apply_rich_text(text: RichTextLabel, font_size: int = 14) -> void:
	text.add_theme_font_size_override("normal_font_size", font_size)
	text.add_theme_color_override("default_color", C_TEXT)


static func apply_co_row(row: Panel, label: Label, meter: ProgressBar) -> void:
	row.add_theme_stylebox_override("panel", _box(Color("#0c1b2ed9"), Color("#77633b"), 1, 3))
	label.add_theme_color_override("font_color", C_TEXT)
	meter.add_theme_stylebox_override("background", _box(C_INK, Color("#695a39"), 1, 2))
	meter.add_theme_stylebox_override("fill", _box(C_GOLD, C_GOLD_BRIGHT, 1, 2))
