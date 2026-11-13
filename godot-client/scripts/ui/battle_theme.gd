extends Node

const Visual = preload("res://scripts/ui/visual_tokens.gd")
## Visual treatment for the battle HUD. It deliberately does not own board state.
## 边框/顶部条/侧栏/行动菜单/对话/姓名牌/紧凑状态牌/结算标题来自 original_v2
## (经 skin_assets 唯一入口)。本文件是这些战斗面板的唯一样式所有者。

const SkinAssets = preload("res://scripts/ui/skin_assets.gd")

const C_INK: Color = Visual.INK
const C_NAVY: Color = Visual.PANEL
const C_NAVY_LIGHT: Color = Visual.RAISED
const C_GOLD: Color = Visual.GOLD
const C_GOLD_BRIGHT: Color = Visual.GOLD_LIGHT
const C_TEXT: Color = Visual.TEXT
const C_TEXT_DIM: Color = Visual.DIM
const C_TEXT_DISABLED: Color = Visual.DISABLED
const C_RUBY: Color = Visual.DANGER
const C_RUBY_DARK: Color = Visual.RAISED


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
	var style := _box(Color(C_INK.r, C_INK.g, C_INK.b, 0.94), border, 1, 4)
	style.shadow_color = Color(0.0, 0.0, 0.0, 0.38)
	style.shadow_size = 8
	style.shadow_offset = Vector2(0, 3)
	panel.add_theme_stylebox_override("panel", style)


static func apply_floating_panel(panel: Panel, border: Color = C_GOLD) -> void:
	panel.add_theme_stylebox_override("panel", Visual.surface(Visual.PANEL, Visual.LINE, 24))

# 顶部状态条:整条拉伸(中心为内容安全区)。
static func apply_top_status_bar(texture_rect: TextureRect) -> void:
	texture_rect.texture = null
	texture_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE

# 紧凑状态牌(回合/阶段/金币/玩家/结束回合等 badge 的九宫格)。
static func apply_compact_plate(nine_patch: NinePatchRect) -> void:
	nine_patch.texture = null
	nine_patch.mouse_filter = Control.MOUSE_FILTER_IGNORE

# 行动菜单底板(点击单位后弹出的 5 按钮菜单)。
static func apply_action_menu(panel: Panel) -> void:
	panel.add_theme_stylebox_override("panel", Visual.surface(Visual.PANEL, Visual.LINE, 16))

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
	Visual.button(button, true, 17, false)

static func apply_secondary(button: Button) -> void:
	Visual.button(button, false, 17, false)

static func apply_danger(button: Button) -> void:
	Visual.button(button, false, 17, true)

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
