extends Node
## Dedicated visual language for the campaign and preparation screen.
## Text and interaction stay in native controls; this only owns presentation.

const C_INK: Color = Color("#0b1525")
const C_PANEL: Color = Color("#14233b")
const C_PANEL_LIGHT: Color = Color("#1d3150")
const C_PARCHMENT: Color = Color("#ead9ad")
const C_GOLD: Color = Color("#c99c45")
const C_GOLD_BRIGHT: Color = Color("#f0cf7a")
const C_RUBY: Color = Color("#9b3142")
const C_RUBY_DARK: Color = Color("#5b1725")
const C_TEXT: Color = Color("#fff0cb")
const C_TEXT_DIM: Color = Color("#b6a783")
const PANEL_SKIN: Texture2D = preload("res://assets/ui/mainline_panel_skin_v1.png")


static func _box(fill: Color, border: Color, width: int = 1, radius: int = 4) -> StyleBoxFlat:
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


static func _apply_button_colors(button: Button, normal: Color, hover: Color, pressed: Color, border: Color) -> void:
	button.add_theme_font_size_override("font_size", 15)
	button.add_theme_color_override("font_color", C_TEXT)
	button.add_theme_color_override("font_hover_color", C_GOLD_BRIGHT)
	button.add_theme_color_override("font_pressed_color", C_TEXT)
	button.add_theme_color_override("font_disabled_color", C_TEXT_DIM)
	var normal_style := _box(normal, border, 1, 4)
	var hover_style := _box(hover, C_GOLD_BRIGHT, 2, 4)
	var pressed_style := _box(pressed, border, 2, 4)
	var disabled_style := _box(Color(normal.r * 0.58, normal.g * 0.58, normal.b * 0.58, 0.82), C_TEXT_DIM, 1, 4)
	button.add_theme_stylebox_override("normal", normal_style)
	button.add_theme_stylebox_override("hover", hover_style)
	button.add_theme_stylebox_override("pressed", pressed_style)
	button.add_theme_stylebox_override("disabled", disabled_style)
	button.add_theme_stylebox_override("focus", hover_style)


static func apply_primary(button: Button) -> void:
	button.add_theme_font_size_override("font_size", 16)
	button.add_theme_color_override("font_color", C_INK)
	button.add_theme_color_override("font_hover_color", C_INK)
	button.add_theme_color_override("font_pressed_color", C_TEXT)
	button.add_theme_color_override("font_disabled_color", C_TEXT_DIM)
	var normal_style := _box(C_GOLD, C_GOLD_BRIGHT, 2, 5)
	normal_style.shadow_color = Color(0.0, 0.0, 0.0, 0.35)
	normal_style.shadow_size = 4
	normal_style.shadow_offset = Vector2(0, 2)
	var hover_style := _box(C_GOLD_BRIGHT, C_TEXT, 2, 5)
	hover_style.shadow_color = Color(C_GOLD_BRIGHT.r, C_GOLD_BRIGHT.g, C_GOLD_BRIGHT.b, 0.35)
	hover_style.shadow_size = 7
	var pressed_style := _box(C_RUBY, C_GOLD_BRIGHT, 2, 5)
	var disabled_style := _box(Color("#81735a"), C_TEXT_DIM, 1, 5)
	button.add_theme_stylebox_override("normal", normal_style)
	button.add_theme_stylebox_override("hover", hover_style)
	button.add_theme_stylebox_override("pressed", pressed_style)
	button.add_theme_stylebox_override("disabled", disabled_style)
	button.add_theme_stylebox_override("focus", hover_style)


static func apply_danger(button: Button) -> void:
	_apply_button_colors(button, C_RUBY_DARK, C_RUBY, Color("#43101c"), C_RUBY)


static func apply_secondary(button: Button) -> void:
	_apply_button_colors(button, Color("#162942"), C_PANEL_LIGHT, C_INK, C_GOLD)


static func apply_tab(button: Button) -> void:
	button.add_theme_font_size_override("font_size", 14)
	button.add_theme_color_override("font_color", C_TEXT_DIM)
	button.add_theme_color_override("font_hover_color", C_GOLD_BRIGHT)
	button.add_theme_color_override("font_pressed_color", C_TEXT)
	button.add_theme_color_override("font_disabled_color", C_INK)
	var normal_style := _box(Color("#102038"), Color("#51627a"), 1, 3)
	var hover_style := _box(C_PANEL_LIGHT, C_GOLD, 1, 3)
	var pressed_style := _box(C_RUBY_DARK, C_GOLD_BRIGHT, 1, 3)
	var selected_style := _box(C_GOLD, C_GOLD_BRIGHT, 2, 3)
	button.add_theme_stylebox_override("normal", normal_style)
	button.add_theme_stylebox_override("hover", hover_style)
	button.add_theme_stylebox_override("pressed", pressed_style)
	button.add_theme_stylebox_override("disabled", selected_style)
	button.add_theme_stylebox_override("focus", hover_style)


static func apply_option(option: OptionButton) -> void:
	option.add_theme_font_size_override("font_size", 14)
	option.add_theme_color_override("font_color", C_TEXT)
	option.add_theme_color_override("font_disabled_color", C_TEXT_DIM)
	var normal_style := _box(Color("#0e1c31"), C_GOLD, 1, 3)
	var hover_style := _box(C_PANEL_LIGHT, C_GOLD_BRIGHT, 2, 3)
	var pressed_style := _box(C_INK, C_GOLD_BRIGHT, 2, 3)
	option.add_theme_stylebox_override("normal", normal_style)
	option.add_theme_stylebox_override("hover", hover_style)
	option.add_theme_stylebox_override("pressed", pressed_style)
	option.add_theme_stylebox_override("disabled", normal_style)
	option.add_theme_stylebox_override("focus", hover_style)


static func apply_section_panel(panel: Control, accent: Color) -> void:
	var style := _box(Color("#09172acc"), accent, 1, 5)
	style.shadow_color = Color(0.0, 0.0, 0.0, 0.22)
	style.shadow_size = 5
	panel.add_theme_stylebox_override("panel", style)


static func apply_chapter_button(button: Button) -> void:
	apply_secondary(button)
	button.custom_minimum_size = Vector2(0, 48)
	button.alignment = HORIZONTAL_ALIGNMENT_LEFT
	button.add_theme_font_size_override("font_size", 16)


static func apply_frame(frame: Panel, border: ReferenceRect, title: Label, summary: RichTextLabel, content: RichTextLabel) -> void:
	var frame_style := _box(C_PANEL, C_GOLD, 3, 8)
	frame_style.shadow_color = Color(0.0, 0.0, 0.0, 0.55)
	frame_style.shadow_size = 16
	frame_style.shadow_offset = Vector2(0, 6)
	frame.add_theme_stylebox_override("panel", frame_style)
	var skin := frame.get_node_or_null("ArtSkin") as TextureRect
	if skin == null:
		skin = TextureRect.new()
		skin.name = "ArtSkin"
		skin.mouse_filter = Control.MOUSE_FILTER_IGNORE
		skin.anchor_right = 1.0
		skin.anchor_bottom = 1.0
		skin.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		skin.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
		skin.texture = PANEL_SKIN
		skin.modulate = Color(1.0, 1.0, 1.0, 0.20)
		frame.add_child(skin)
		frame.move_child(skin, 0)
	border.border_color = Color(C_GOLD_BRIGHT.r, C_GOLD_BRIGHT.g, C_GOLD_BRIGHT.b, 0.65)
	border.border_width = 1.0
	border.offset_left = 10
	border.offset_top = 10
	border.offset_right = -10
	border.offset_bottom = -10
	title.add_theme_font_size_override("font_size", 26)
	title.add_theme_color_override("font_color", C_GOLD_BRIGHT)
	for text_panel in [summary, content]:
		text_panel.add_theme_font_size_override("normal_font_size", 15)
		text_panel.add_theme_color_override("default_color", C_TEXT)
		text_panel.add_theme_stylebox_override("normal", _box(Color("#0a1628cc"), Color("#8b7040"), 1, 4))


static func apply_slot_label(label: Label, occupied: bool) -> void:
	label.add_theme_font_size_override("font_size", 13)
	label.add_theme_color_override("font_color", C_TEXT if occupied else C_TEXT_DIM)
