extends Node
## Visual treatment for the battle HUD. It deliberately does not own board state.
## 边框/顶部条/侧栏/行动菜单/对话/姓名牌/紧凑状态牌/结算标题来自 original_v2
## (经 skin_assets 唯一入口)。本文件是这些战斗面板的唯一样式所有者。

const SkinAssets = preload("res://scripts/ui/skin_assets.gd")

const C_INK: Color = Color("#081321")
const C_NAVY: Color = Color("#10243b")
const C_NAVY_LIGHT: Color = Color("#1a3858")
const C_GOLD: Color = Color("#c99c45")
const C_GOLD_BRIGHT: Color = Color("#f0cf7a")
const C_TEXT: Color = Color("#fff0cb")
const C_TEXT_DIM: Color = Color("#b6a783")
const C_TEXT_DISABLED: Color = Color("#a9a38f")
const C_RUBY: Color = Color("#8c273b")
const C_RUBY_DARK: Color = Color("#4e1421")


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
	label.add_theme_font_size_override("font_size", 17)
	label.add_theme_color_override("font_color", C_TEXT)
	label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.82))
	label.add_theme_constant_override("outline_size", 1)


static func apply_panel(panel: Panel, border: Color = C_GOLD) -> void:
	var style := _box(Color(C_INK.r, C_INK.g, C_INK.b, 0.94), border, 2, 5)
	style.shadow_color = Color(0.0, 0.0, 0.0, 0.38)
	style.shadow_size = 8
	style.shadow_offset = Vector2(0, 3)
	panel.add_theme_stylebox_override("panel", style)


static func apply_floating_panel(panel: Panel, border: Color = C_GOLD) -> void:
	# InfoPanel 使用侧栏抽屉纹理(单位详情/任务信息),唯一样式所有者 = 本函数。
	# 纹理原始 60px 安全边距会挤压 720p 正文；收紧后仍避开装饰角件。
	# 略微降低满高抽屉的底纹重量，避免少量信息被巨型实心框包围。
	var style: StyleBoxTexture = SkinAssets.battle_sidebar_style()
	style.content_margin_left = 40
	style.content_margin_top = 42
	style.content_margin_right = 40
	style.content_margin_bottom = 42
	style.modulate_color = Color(1, 1, 1, 0.90)
	panel.add_theme_stylebox_override("panel", style)


# 顶部状态条:整条拉伸(中心为内容安全区)。
static func apply_top_status_bar(texture_rect: TextureRect) -> void:
	texture_rect.texture = SkinAssets.top_battle_status_bar()
	texture_rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	texture_rect.stretch_mode = TextureRect.STRETCH_SCALE


# 紧凑状态牌(回合/阶段/金币/玩家/结束回合等 badge 的九宫格)。
static func apply_compact_plate(nine_patch: NinePatchRect) -> void:
	nine_patch.texture = SkinAssets.compact_status_plate()
	nine_patch.patch_margin_left = 48
	nine_patch.patch_margin_top = 20
	nine_patch.patch_margin_right = 50
	nine_patch.patch_margin_bottom = 22
	nine_patch.draw_center = false


# 行动菜单底板(点击单位后弹出的 5 按钮菜单)。
static func apply_action_menu(panel: Panel) -> void:
	var style: StyleBoxTexture = SkinAssets.battle_action_menu_style()
	style.content_margin_left = 28
	style.content_margin_top = 32
	style.content_margin_right = 28
	style.content_margin_bottom = 34
	style.modulate_color = Color(1, 1, 1, 0.96)
	panel.add_theme_stylebox_override("panel", style)


# 对话框。
static func apply_dialogue(panel: Panel) -> void:
	panel.add_theme_stylebox_override("panel", SkinAssets.battle_dialogue_style())


# 说话人姓名牌。
static func apply_nameplate(control: Control) -> void:
	control.add_theme_stylebox_override("normal", SkinAssets.battle_nameplate_style())


# 章节结果标题(胜利/失败横幅)。
static func apply_result_title(control: Control) -> void:
	control.add_theme_stylebox_override("normal", SkinAssets.battle_result_title_style())


static func apply_primary(button: Button) -> void:
	button.add_theme_font_size_override("font_size", 17)
	button.add_theme_color_override("font_color", C_TEXT)
	button.add_theme_color_override("font_hover_color", C_GOLD_BRIGHT)
	button.add_theme_color_override("font_disabled_color", C_TEXT_DISABLED)
	button.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.82))
	button.add_theme_constant_override("outline_size", 1)
	button.add_theme_stylebox_override("normal", SkinAssets.button_style("selected"))
	button.add_theme_stylebox_override("hover", SkinAssets.button_style("hover"))
	button.add_theme_stylebox_override("pressed", SkinAssets.button_style("pressed"))
	button.add_theme_stylebox_override("disabled", SkinAssets.button_style("disabled"))
	button.add_theme_stylebox_override("focus", SkinAssets.button_style("selected"))


static func apply_secondary(button: Button) -> void:
	button.add_theme_font_size_override("font_size", 16)
	button.add_theme_color_override("font_color", C_TEXT)
	button.add_theme_color_override("font_hover_color", C_GOLD_BRIGHT)
	button.add_theme_color_override("font_disabled_color", C_TEXT_DISABLED)
	button.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.82))
	button.add_theme_constant_override("outline_size", 1)
	button.add_theme_stylebox_override("normal", SkinAssets.button_style("normal"))
	button.add_theme_stylebox_override("hover", SkinAssets.button_style("hover"))
	button.add_theme_stylebox_override("pressed", SkinAssets.button_style("pressed"))
	button.add_theme_stylebox_override("disabled", SkinAssets.button_style("disabled"))
	button.add_theme_stylebox_override("focus", SkinAssets.button_style("hover"))


static func apply_danger(button: Button) -> void:
	apply_secondary(button)
	button.add_theme_color_override("font_color", C_TEXT)
	var danger := Color(C_RUBY.r, C_RUBY.g, C_RUBY.b, 1.0)
	var tinted: StyleBoxTexture = SkinAssets.button_style("normal").duplicate()
	tinted.modulate_color = danger
	button.add_theme_stylebox_override("normal", tinted)
	button.add_theme_stylebox_override("hover", tinted)
	button.add_theme_stylebox_override("focus", tinted)


static func apply_header(label: Label, font_size: int = 17) -> void:
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", C_GOLD_BRIGHT)


static func apply_rich_text(text: RichTextLabel, font_size: int = 16) -> void:
	text.add_theme_font_size_override("normal_font_size", font_size)
	text.add_theme_color_override("default_color", C_TEXT)


static func apply_co_row(row: Panel, label: Label, meter: ProgressBar) -> void:
	row.add_theme_stylebox_override("panel", _box(Color("#0c1b2ed9"), Color("#77633b"), 1, 3))
	label.add_theme_color_override("font_color", C_TEXT)
	meter.add_theme_stylebox_override("background", _box(C_INK, Color("#695a39"), 1, 2))
	meter.add_theme_stylebox_override("fill", _box(C_GOLD, C_GOLD_BRIGHT, 1, 2))
