extends Node
## Dedicated visual language for the campaign and preparation screen.
## Text and interaction stay in native controls; this only owns presentation.
## 边框/按钮/页签/列表行/铭牌来自 original_v2(经 skin_assets 唯一入口)。

const SkinAssets = preload("res://scripts/ui/skin_assets.gd")

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
# 旧 MLFrame 兼容路径使用的填色/边线,统一进 C_* 常量(UI V3 验证标准 #2)
const C_OPTION_FILL: Color = Color("#0e1c31")
const C_FRAME_INK: Color = Color("#0a1628cc")
const C_FRAME_BORDER: Color = Color("#8b7040")


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


static func _tint(style: StyleBoxTexture, tint: Color) -> StyleBoxTexture:
	var copy: StyleBoxTexture = style.duplicate()
	copy.modulate_color = tint
	return copy


static func _apply_button_colors(button: Button, normal: Color, hover: Color, pressed: Color, border: Color) -> void:
	# 保留颜色入口(供 apply_danger 二次着色),主体纹理仍走 skin_assets。
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
	button.add_theme_color_override("font_color", C_TEXT)
	button.add_theme_color_override("font_hover_color", C_GOLD_BRIGHT)
	button.add_theme_color_override("font_pressed_color", C_TEXT)
	button.add_theme_color_override("font_disabled_color", C_TEXT_DIM)
	# 主操作按钮使用带暗红封签的 selected 态,作为常态强调。
	button.add_theme_stylebox_override("normal", SkinAssets.button_style("selected"))
	button.add_theme_stylebox_override("hover", SkinAssets.button_style("hover"))
	button.add_theme_stylebox_override("pressed", SkinAssets.button_style("pressed"))
	button.add_theme_stylebox_override("disabled", SkinAssets.button_style("disabled"))
	button.add_theme_stylebox_override("focus", SkinAssets.button_style("selected"))


static func apply_danger(button: Button) -> void:
	button.add_theme_font_size_override("font_size", 15)
	button.add_theme_color_override("font_color", C_TEXT)
	button.add_theme_color_override("font_hover_color", C_GOLD_BRIGHT)
	button.add_theme_color_override("font_pressed_color", C_TEXT)
	button.add_theme_color_override("font_disabled_color", C_TEXT_DIM)
	var danger := Color(C_RUBY.r, C_RUBY.g, C_RUBY.b, 1.0)
	button.add_theme_stylebox_override("normal", _tint(SkinAssets.button_style("normal"), danger))
	button.add_theme_stylebox_override("hover", _tint(SkinAssets.button_style("hover"), danger))
	button.add_theme_stylebox_override("pressed", _tint(SkinAssets.button_style("pressed"), danger))
	button.add_theme_stylebox_override("disabled", SkinAssets.button_style("disabled"))
	button.add_theme_stylebox_override("focus", _tint(SkinAssets.button_style("hover"), danger))


static func apply_secondary(button: Button) -> void:
	button.add_theme_font_size_override("font_size", 14)
	button.add_theme_color_override("font_color", C_TEXT)
	button.add_theme_color_override("font_hover_color", C_GOLD_BRIGHT)
	button.add_theme_color_override("font_pressed_color", C_TEXT)
	button.add_theme_color_override("font_disabled_color", C_TEXT_DIM)
	button.add_theme_stylebox_override("normal", SkinAssets.button_style("normal"))
	button.add_theme_stylebox_override("hover", SkinAssets.button_style("hover"))
	button.add_theme_stylebox_override("pressed", SkinAssets.button_style("pressed"))
	button.add_theme_stylebox_override("disabled", SkinAssets.button_style("disabled"))
	button.add_theme_stylebox_override("focus", SkinAssets.button_style("hover"))


static func apply_tab(button: Button) -> void:
	button.add_theme_font_size_override("font_size", 14)
	button.add_theme_color_override("font_color", C_TEXT_DIM)
	button.add_theme_color_override("font_hover_color", C_GOLD_BRIGHT)
	button.add_theme_color_override("font_pressed_color", C_TEXT)
	button.add_theme_color_override("font_disabled_color", C_GOLD_BRIGHT)  # 当前页签在 disabled 态仍亮金,避免被看成空白
	# 当前页签在面板里被 disabled(见 set_active_tab),因此 disabled 态复用 active 纹理。
	button.add_theme_stylebox_override("normal", SkinAssets.tab_style("inactive"))
	button.add_theme_stylebox_override("hover", SkinAssets.tab_style("hover"))
	button.add_theme_stylebox_override("pressed", SkinAssets.tab_style("active"))
	button.add_theme_stylebox_override("disabled", SkinAssets.tab_style("active"))
	button.add_theme_stylebox_override("focus", SkinAssets.tab_style("hover"))


static func apply_row(button: Button, selected: bool = false) -> void:
	button.add_theme_font_size_override("font_size", 15)
	button.add_theme_color_override("font_color", C_TEXT)
	button.add_theme_color_override("font_hover_color", C_GOLD_BRIGHT)
	button.add_theme_color_override("font_pressed_color", C_TEXT)
	button.add_theme_color_override("font_disabled_color", C_TEXT_DIM)
	var state := "selected" if selected else "neutral"
	button.add_theme_stylebox_override("normal", SkinAssets.row_style(state))
	button.add_theme_stylebox_override("hover", SkinAssets.row_style("hover"))
	button.add_theme_stylebox_override("pressed", SkinAssets.row_style("selected"))
	button.add_theme_stylebox_override("disabled", SkinAssets.row_style("disabled"))
	# selected 态叠 2px 金边焦点框,避免"只改色"反馈
	if selected:
		var focus_ring := StyleBoxFlat.new()
		focus_ring.bg_color = Color(0, 0, 0, 0)
		focus_ring.border_color = C_GOLD_BRIGHT
		focus_ring.set_border_width_all(2)
		focus_ring.set_corner_radius_all(2)
		button.add_theme_stylebox_override("focus", focus_ring)
	else:
		button.add_theme_stylebox_override("focus", SkinAssets.row_style("hover"))


static func apply_option(option: OptionButton) -> void:
	option.add_theme_font_size_override("font_size", 14)
	option.add_theme_color_override("font_color", C_TEXT)
	option.add_theme_color_override("font_disabled_color", C_TEXT_DIM)
	var normal_style := _box(C_OPTION_FILL, C_GOLD, 1, 3)
	var hover_style := _box(C_PANEL_LIGHT, C_GOLD_BRIGHT, 2, 3)
	var pressed_style := _box(C_INK, C_GOLD_BRIGHT, 2, 3)
	option.add_theme_stylebox_override("normal", normal_style)
	option.add_theme_stylebox_override("hover", hover_style)
	option.add_theme_stylebox_override("pressed", pressed_style)
	option.add_theme_stylebox_override("disabled", normal_style)
	option.add_theme_stylebox_override("focus", hover_style)


# 二级面板:二级框(中心透明)+ 平铺底纹子节点。kind ∈ "navy","paper","steel"。
# 唯一样式所有者 = 本函数。
static func apply_section_panel(panel: Control, kind: String = "navy") -> void:
	var patch := SkinAssets.FRAME_SECONDARY_PATCH
	var sb := StyleBoxTexture.new()
	sb.texture = SkinAssets.secondary_panel_frame()
	sb.texture_margin_left = patch
	sb.texture_margin_top = patch
	sb.texture_margin_right = patch
	sb.texture_margin_bottom = patch
	sb.content_margin_left = patch + 8
	sb.content_margin_top = patch + 6
	sb.content_margin_right = patch + 8
	sb.content_margin_bottom = patch + 6
	panel.add_theme_stylebox_override("panel", sb)
	_ensure_tiled_background(panel, kind)


static func apply_chapter_button(button: Button) -> void:
	apply_row(button)
	button.custom_minimum_size = Vector2(0, 48)
	button.alignment = HORIZONTAL_ALIGNMENT_LEFT
	button.add_theme_font_size_override("font_size", 16)


# 页面一级框:一级框(中心透明)+ 墨蓝织纹子节点。patch 越大,中心内容区越向内收。
static func apply_page_frame(panel: Control, patch: int = SkinAssets.FRAME_PRIMARY_PATCH) -> void:
	var sb := StyleBoxTexture.new()
	sb.texture = SkinAssets.primary_page_frame()
	sb.texture_margin_left = patch
	sb.texture_margin_top = patch
	sb.texture_margin_right = patch
	sb.texture_margin_bottom = patch
	sb.content_margin_left = patch + 8
	sb.content_margin_top = patch + 6
	sb.content_margin_right = patch + 8
	sb.content_margin_bottom = patch + 6
	panel.add_theme_stylebox_override("panel", sb)
	_ensure_tiled_background(panel, "navy")


# 标题铭牌:在 label 下方垫一块宽铭牌纹理。
static func apply_title_plate(label: Control, wide: bool = true) -> void:
	label.add_theme_stylebox_override("normal", SkinAssets.title_plate_style(wide))
	label.add_theme_font_size_override("font_size", 26)
	label.add_theme_color_override("font_color", C_GOLD_BRIGHT)
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER


# 分节标题条。
static func apply_section_title(label: Label) -> void:
	label.add_theme_stylebox_override("normal", SkinAssets.section_title_bar_style())
	label.add_theme_font_size_override("font_size", 18)
	label.add_theme_color_override("font_color", C_GOLD_BRIGHT)
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT


# 角色摘要卡:4:5 立框,透明中心。用于英雄页的专注卡。
static func apply_character_card(panel: Control) -> void:
	panel.add_theme_stylebox_override("panel", _card_style(SkinAssets.character_summary_card(), SkinAssets.CARD_CHAR_PATCH))


# 物品/数值摘要卡:32:15 横框。
static func apply_item_card(panel: Control) -> void:
	panel.add_theme_stylebox_override("panel", _card_style(SkinAssets.item_value_summary_card(), SkinAssets.CARD_ITEM_PATCH))


static func _card_style(tex: Texture2D, patch: int) -> StyleBoxTexture:
	var sb := StyleBoxTexture.new()
	sb.texture = tex
	sb.texture_margin_left = patch
	sb.texture_margin_top = patch
	sb.texture_margin_right = patch
	sb.texture_margin_bottom = patch
	sb.content_margin_left = patch + 6
	sb.content_margin_top = patch + 6
	sb.content_margin_right = patch + 6
	sb.content_margin_bottom = patch + 6
	return sb


# 在 PanelContainer 内创建/复用平铺底纹子节点(容器会按 stylebox content
# margin 内缩,因此底纹自动落在框架内容区,不遮挡框架装饰)。
static func _ensure_tiled_background(panel: Control, kind: String) -> TextureRect:
	var bg := panel.get_node_or_null("PageBackground") as TextureRect
	if bg == null:
		bg = TextureRect.new()
		bg.name = "PageBackground"
		bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
		panel.add_child(bg)
		panel.move_child(bg, 0)
	var tex := SkinAssets.ink_navy_weave_tile()
	match kind:
		"paper":
			tex = SkinAssets.warm_gray_paper_tile()
		"steel":
			tex = SkinAssets.smoke_black_steel_tile()
	bg.texture = tex
	bg.stretch_mode = TextureRect.STRETCH_TILE
	bg.texture_repeat = CanvasItem.TEXTURE_REPEAT_ENABLED
	bg.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	return bg


# 旧 MLFrame 兼容入口。主框架已拆分面板,这里只保留接口并取消 ArtSkin 清理。
static func apply_frame(frame: Panel, border: ReferenceRect, title: Label, summary: RichTextLabel, content: RichTextLabel) -> void:
	var frame_style := _box(C_PANEL, C_GOLD, 3, 8)
	frame_style.shadow_color = Color(0.0, 0.0, 0.0, 0.55)
	frame_style.shadow_size = 16
	frame_style.shadow_offset = Vector2(0, 6)
	frame.add_theme_stylebox_override("panel", frame_style)
	# 不再 queue_free ArtSkin —— 已批准的美术节点由本主题函数统一接管。
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
		text_panel.add_theme_stylebox_override("normal", _box(C_FRAME_INK, C_FRAME_BORDER, 1, 4))


static func apply_slot_label(label: Label, occupied: bool) -> void:
	label.add_theme_font_size_override("font_size", 13)
	label.add_theme_color_override("font_color", C_TEXT if occupied else C_TEXT_DIM)
