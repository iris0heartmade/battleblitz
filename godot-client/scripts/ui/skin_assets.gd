extends RefCounted
## skin_assets.gd — Frontier Council Archive 原创资产唯一入口。
##
## original_v2 全部纹理与派生 StyleBoxTexture 的唯一所有权在这里。
## 场景/主题脚本一律通过本模块取资源,禁止各自散落 load()。
## 只引用 base/ controls/ battle/ 的透明成品,不触碰 sources/。
##
## 与菜单不同,这是纯静态资源层:不持有任何 Node 引用,headless 安全。
## 区域常量来自 2026-07-31 的 alpha 边界实测(见 original_v2/README.md 接入说明)。

const DIR := "res://assets/ui/original_v2"


# ── 基础读取 ────────────────────────────────────────────────

static func _load(path: String) -> Texture2D:
	return load("%s/%s" % [DIR, path]) as Texture2D


# ── base: 页面框架 / 卡片 / 织纹 ────────────────────────────

static func primary_page_frame() -> Texture2D:
	return _load("base/primary_page_frame_9slice.png")


static func secondary_panel_frame() -> Texture2D:
	return _load("base/secondary_panel_frame_9slice.png")


static func character_summary_card() -> Texture2D:
	return _load("base/character_summary_card.png")


static func item_value_summary_card() -> Texture2D:
	return _load("base/item_value_summary_card.png")


static func ink_navy_weave_tile() -> Texture2D:
	return _load("base/ink_navy_weave_tile.png")


static func warm_gray_paper_tile() -> Texture2D:
	return _load("base/warm_gray_archive_paper_tile.png")


static func smoke_black_steel_tile() -> Texture2D:
	return _load("base/smoke_black_steel_tile.png")


static func modal_overlay_tile() -> Texture2D:
	return _load("base/modal_overlay_tile.png")


# ── controls: 按钮 / 页签 / 列表行 / 铭牌 / 分隔 / 状态框 ──

static func button_sheet() -> Texture2D:
	return _load("controls/button_states.png")


static func tab_sheet() -> Texture2D:
	return _load("controls/tab_states.png")


static func row_sheet() -> Texture2D:
	return _load("controls/list_row_states.png")


static func title_nameplates() -> Texture2D:
	return _load("controls/title_nameplates.png")


static func section_divider_sheet() -> Texture2D:
	return _load("controls/section_divider.png")


static func status_frame_sheet() -> Texture2D:
	return _load("controls/status_frames.png")


static func bar_sheet() -> Texture2D:
	return _load("controls/bar_components.png")


static func scrollbar_sheet() -> Texture2D:
	return _load("controls/scrollbar_components.png")


static func capsule_sheet() -> Texture2D:
	return _load("controls/input_hint_capsules.png")


static func function_icon_sheet() -> Texture2D:
	return _load("controls/function_icons.png")


# ── battle: 顶部状态条 / 侧栏 / 行动菜单 / 对话 / 结算 ──────

static func top_battle_status_bar() -> Texture2D:
	return _load("battle/top_battle_status_bar.png")


static func battle_sidebar_drawer() -> Texture2D:
	return _load("battle/battle_sidebar_drawer.png")


static func action_menu_panel() -> Texture2D:
	return _load("battle/action_menu_panel.png")


static func dialogue_panel() -> Texture2D:
	return _load("battle/dialogue_panel.png")


static func nameplate() -> Texture2D:
	return _load("battle/nameplate.png")


static func compact_status_plate() -> Texture2D:
	return _load("battle/compact_status_plate.png")


static func chapter_result_title() -> Texture2D:
	return _load("battle/chapter_result_title.png")


# ── 九宫格 patch 边距(由 alpha 边界实测折算) ────────────────

const FRAME_PRIMARY_PATCH := 56
const FRAME_SECONDARY_PATCH := 52
const CARD_CHAR_PATCH := 48
const CARD_ITEM_PATCH := 40


# ── StyleBoxTexture 构造器 ─────────────────────────────────

static func _stbox(tex: Texture2D, region: Rect2, margins: Array) -> StyleBoxTexture:
	# margins = [left, top, right, bottom]
	var sb := StyleBoxTexture.new()
	sb.texture = tex
	if region.size.x > 0 and region.size.y > 0:
		sb.region_rect = region
	sb.texture_margin_left = margins[0]
	sb.texture_margin_top = margins[1]
	sb.texture_margin_right = margins[2]
	sb.texture_margin_bottom = margins[3]
	return sb


# 页面一级框:外框 + 内边距,中心透明(配合底色填充使用)。
static func primary_frame_style(content_margin: int = 18) -> StyleBoxTexture:
	var sb := _stbox(primary_page_frame(), Rect2(), [FRAME_PRIMARY_PATCH, FRAME_PRIMARY_PATCH, FRAME_PRIMARY_PATCH, FRAME_PRIMARY_PATCH])
	sb.content_margin_left = content_margin + 8
	sb.content_margin_top = content_margin + 6
	sb.content_margin_right = content_margin + 8
	sb.content_margin_bottom = content_margin + 6
	return sb


# 二级面板框:窄装饰,中心透明。
static func secondary_frame_style(content_margin: int = 14) -> StyleBoxTexture:
	var sb := _stbox(secondary_panel_frame(), Rect2(), [FRAME_SECONDARY_PATCH, FRAME_SECONDARY_PATCH, FRAME_SECONDARY_PATCH, FRAME_SECONDARY_PATCH])
	sb.content_margin_left = content_margin + 6
	sb.content_margin_top = content_margin + 6
	sb.content_margin_right = content_margin + 6
	sb.content_margin_bottom = content_margin + 6
	return sb


# 按钮五态。state ∈ "normal","hover","pressed","disabled","selected"。
static func button_style(state: String) -> StyleBoxTexture:
	var region := Rect2()
	match state:
		"hover":
			region = Rect2(426, 275, 423, 179)
		"pressed":
			region = Rect2(882, 275, 369, 179)
		"disabled":
			region = Rect2(1292, 275, 370, 179)
		"selected":
			region = Rect2(1705, 275, 372, 180)
		_:
			region = Rect2(56, 275, 370, 179)
	var sb := _stbox(button_sheet(), region, [48, 48, 48, 48])
	sb.content_margin_left = 20
	sb.content_margin_top = 8
	sb.content_margin_right = 20
	sb.content_margin_bottom = 8
	return sb


# 页签四态。state ∈ "inactive","hover","active","disabled"。
static func tab_style(state: String) -> StyleBoxTexture:
	var region := Rect2()
	match state:
		"hover":
			region = Rect2(571, 232, 484, 233)
		"active":
			region = Rect2(1114, 232, 485, 233)
		"disabled":
			region = Rect2(1658, 232, 484, 233)
		_:
			region = Rect2(28, 232, 484, 233)
	var sb := _stbox(tab_sheet(), region, [36, 28, 64, 48])
	sb.content_margin_left = 18
	sb.content_margin_top = 6
	sb.content_margin_right = 18
	sb.content_margin_bottom = 8
	return sb


# 列表行四态。state ∈ "neutral","hover","selected","disabled"。
static func row_style(state: String) -> StyleBoxTexture:
	var region := Rect2()
	match state:
		"hover":
			region = Rect2(565, 286, 499, 127)
		"selected":
			region = Rect2(1104, 286, 502, 127)
		"disabled":
			region = Rect2(1651, 286, 498, 127)
		_:
			region = Rect2(24, 286, 498, 127)
	var sb := _stbox(row_sheet(), region, [24, 24, 24, 24])
	sb.content_margin_left = 16
	sb.content_margin_top = 8
	sb.content_margin_right = 16
	sb.content_margin_bottom = 8
	return sb


# 标题铭牌。wide=true 用宽板,false 用窄板。用于页面/分节标题底。
# 区域裁剪到 full-alpha 铭牌带(去掉上下透明 padding),保证 9-slice 边距不超半高。
static func title_plate_style(wide: bool = true) -> StyleBoxTexture:
	var region := Rect2(17, 329, 861, 216) if wide else Rect2(896, 348, 860, 192)
	var sb := _stbox(title_nameplates(), region, [48, 40, 48, 40])
	sb.content_margin_left = 44
	sb.content_margin_top = 12
	sb.content_margin_right = 44
	sb.content_margin_bottom = 12
	return sb


# 分节标题条(section_title_bar)。
static func section_title_bar_style() -> StyleBoxTexture:
	var sb := _stbox(section_divider_sheet(), Rect2(75, 285, 946, 150), [56, 40, 56, 40])
	sb.content_margin_left = 36
	sb.content_margin_top = 8
	sb.content_margin_right = 36
	sb.content_margin_bottom = 8
	return sb


# 状态框。kind ∈ "focus","error","success"(仅描边,中心透明)。
static func status_frame_style(kind: String) -> StyleBoxTexture:
	var region := Rect2()
	match kind:
		"error":
			region = Rect2(773, 132, 629, 434)
		"success":
			region = Rect2(1484, 132, 629, 434)
		_:
			region = Rect2(60, 132, 630, 434)
	var sb := _stbox(status_frame_sheet(), region, [56, 56, 56, 56])
	return sb


# 进度条:底槽 + 填充。fill ∈ "ink","brass","oxblood"。
static func bar_trough_style() -> StyleBoxTexture:
	var sb := _stbox(bar_sheet(), Rect2(23, 293, 498, 139), [20, 24, 20, 24])
	return sb


static func bar_fill_style(fill: String) -> StyleBoxTexture:
	var region := Rect2()
	match fill:
		"brass":
			region = Rect2(566, 293, 498, 139)
		"oxblood":
			region = Rect2(1109, 293, 498, 139)
		_:
			region = Rect2(1109, 293, 498, 139)
	var sb := _stbox(bar_sheet(), region, [20, 24, 20, 24])
	return sb


# 输入提示胶囊。kind ∈ "short","medium","long"。
static func capsule_style(kind: String) -> StyleBoxTexture:
	var region := Rect2()
	match kind:
		"medium":
			region = Rect2(724, 267, 724, 193)
		"long":
			region = Rect2(1448, 267, 648, 193)
		_:
			region = Rect2(84, 267, 640, 193)
	var sb := _stbox(capsule_sheet(), region, [36, 32, 36, 32])
	sb.content_margin_left = 24
	sb.content_margin_top = 10
	sb.content_margin_right = 24
	sb.content_margin_bottom = 10
	return sb


# ── 战斗面板 ───────────────────────────────────────────────

# 顶部状态条:整条拉伸(边缘留安全区,中心为内容)。
static func battle_top_bar_style() -> StyleBoxTexture:
	var sb := _stbox(top_battle_status_bar(), Rect2(), [150, 18, 200, 18])
	return sb


# 侧栏抽屉。
static func battle_sidebar_style() -> StyleBoxTexture:
	var sb := _stbox(battle_sidebar_drawer(), Rect2(), [72, 72, 82, 88])
	sb.content_margin_left = 60
	sb.content_margin_top = 60
	sb.content_margin_right = 60
	sb.content_margin_bottom = 60
	return sb


# 行动菜单底板。
static func battle_action_menu_style() -> StyleBoxTexture:
	var sb := _stbox(action_menu_panel(), Rect2(), [54, 54, 61, 81])
	sb.content_margin_left = 44
	sb.content_margin_top = 40
	sb.content_margin_right = 44
	sb.content_margin_bottom = 44
	return sb


# 对话框。
static func battle_dialogue_style() -> StyleBoxTexture:
	var sb := _stbox(dialogue_panel(), Rect2(), [115, 70, 155, 75])
	sb.content_margin_left = 84
	sb.content_margin_top = 56
	sb.content_margin_right = 84
	sb.content_margin_bottom = 56
	return sb


# 姓名牌。
static func battle_nameplate_style() -> StyleBoxTexture:
	var sb := _stbox(nameplate(), Rect2(), [42, 18, 48, 18])
	sb.content_margin_left = 36
	sb.content_margin_top = 8
	sb.content_margin_right = 36
	sb.content_margin_bottom = 8
	return sb


# 紧凑状态牌。
static func battle_compact_plate_style() -> StyleBoxTexture:
	var sb := _stbox(compact_status_plate(), Rect2(), [48, 20, 50, 22])
	return sb


# 章节结果标题。
static func battle_result_title_style() -> StyleBoxTexture:
	var sb := _stbox(chapter_result_title(), Rect2(), [145, 48, 200, 54])
	sb.content_margin_left = 96
	sb.content_margin_top = 40
	sb.content_margin_right = 96
	sb.content_margin_bottom = 40
	return sb


# 可平铺底纹(StyleBoxTexture 的 axis_stretch 支持 tile)。
static func tile_style(kind: String) -> StyleBoxTexture:
	var tex := ink_navy_weave_tile()
	match kind:
		"paper":
			tex = warm_gray_paper_tile()
		"steel":
			tex = smoke_black_steel_tile()
	var sb := _stbox(tex, Rect2(), [0, 0, 0, 0])
	sb.axis_stretch_horizontal = StyleBoxTexture.AXIS_STRETCH_MODE_TILE
	sb.axis_stretch_vertical = StyleBoxTexture.AXIS_STRETCH_MODE_TILE
	return sb


# 弹窗遮罩底纹(半透明近黑墨蓝织纹)。
static func overlay_tile_style() -> StyleBoxTexture:
	var sb := _stbox(modal_overlay_tile(), Rect2(), [0, 0, 0, 0])
	sb.axis_stretch_horizontal = StyleBoxTexture.AXIS_STRETCH_MODE_TILE
	sb.axis_stretch_vertical = StyleBoxTexture.AXIS_STRETCH_MODE_TILE
	return sb


# 通用功能图标。name ∈ "equipment","troops","shop","save","back","confirm","warning"。
# 返回 48px 的 TextureRect(带透明 padding 的原始区域,用 STRETCH_KEEP_ASPECT)。
static func function_icon(name: String) -> TextureRect:
	var region := Rect2()
	match name:
		"troops":
			region = Rect2(310, 170, 310, 384)
		"shop":
			region = Rect2(620, 170, 310, 384)
		"save":
			region = Rect2(930, 170, 310, 384)
		"back":
			region = Rect2(1240, 170, 310, 383)
		"confirm":
			region = Rect2(1550, 170, 310, 384)
		"warning":
			region = Rect2(1860, 170, 294, 383)
		_:
			region = Rect2(16, 170, 294, 384)
	var tr := TextureRect.new()
	tr.texture = function_icon_sheet()
	tr.region_enabled = true
	tr.region_rect = region
	tr.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	tr.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	tr.custom_minimum_size = Vector2(48, 48)
	tr.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return tr
