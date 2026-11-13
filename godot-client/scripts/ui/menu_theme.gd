extends Node

const Visual = preload("res://scripts/ui/visual_tokens.gd")
## menu_theme.gd — 轻量军议公共主题兼容入口。
## 色值集中于 visual_tokens.gd，保持旧控制器调用签名。

# === 调色板(全局唯一来源) ===
const C_BG_DEEP: Color = Visual.INK        # 墨蓝主背景
const C_BG_PANEL: Color = Visual.PANEL       # 面板底色(更深一点)
const C_GOLD: Color = Visual.GOLD           # 哑金细线
const C_GOLD_BRIGHT: Color = Visual.GOLD_LIGHT    # 烫金亮(高亮态)
const C_TEXT_WARM: Color = Visual.TEXT      # 暖白正文
const C_TEXT_DIM: Color = Visual.DIM       # 暗金副文
const C_BTN_BLUE: Color = Visual.RAISED       # 按钮蓝底
const C_BTN_BLUE_HOVER: Color = Visual.HOVER # 按钮悬停
const C_BTN_BLUE_PRESS: Color = Visual.INK # 按钮按下
const C_FIRE_RED: Color = Visual.DANGER       # 火红(强调/危险)
const C_HEAL_GREEN: Color = Visual.SUCCESS     # 回血绿
const C_BORDER_THIN: Color = Visual.LINE    # 中性细线
# === 新增(UI Redesign Round 1) ===
const C_DIVIDER: Color = Visual.LINE         # 分隔线色(同 BORDER_THIN)
const C_DISABLED: Color = Visual.DISABLED        # disabled 文字底色

# === 新增(UI V3:状态可读)===
const C_LOADING: Color = Visual.DIM         # 加载中文案(灰绿,跟 disabled 区别)
const C_ERROR: Color = Visual.DANGER           # 错误文案(比 FIRE_RED 更亮)
const C_PLACEHOLDER: Color = Visual.DIM     # placeholder / 空态文案(比 DIM 更暗)

# === 字体大小 ===
const FS_HERO: int = 56      # 主标题(主菜单唯一)
const FS_TITLE: int = 32     # 子页标题(Lobby / Saves 等)
const FS_SECTION: int = 22   # 视图内 section header
const FS_SUBTITLE: int = 20  # 大字号正文(存档行标题)
const FS_BODY: int = 17      # 默认正文/表单 label
const FS_BODY_SM: int = 15   # 副正文(表单 label / 章节列表)
const FS_SUB: int = 18       # 副标题/版本号
const FS_BTN: int = 17       # 按钮
const FS_HINT: int = 15      # 提示/暗色副文
const FS_FOOT: int = 12      # footer 小字
const FS_PILL: int = 14      # 顶部小角标(HUD 4 角)
const FS_LOADING: int = 14   # 加载中文案(斜体,LOADING 色)
const FS_PLACEHOLDER: int = 15  # 占位文案(PLACEHOLDER 色)

# === 尺寸常量(8px 网格 — UI V3)===
const GRID_1: int = 4        # 微间距(标签 ↔ 数值)
const GRID_2: int = 8        # 紧凑间距(行内)
const GRID_3: int = 16       # 标准间距(控件间)
const GRID_4: int = 24       # section 内 padding
const GRID_5: int = 32       # section 间 padding
const GRID_6: int = 48       # 大块留白

const PAD_S: int = GRID_2    # 8  — 紧凑(icon ↔ label)
const PAD_M: int = GRID_3    # 16 — 通用(控件内 padding)
const PAD_L: int = GRID_4    # 24 — section 内 padding
const PAD_X: int = GRID_5    # 32 — section 间 padding(沿用 V2 名字)
const PAD_Y: int = 18        # 外框内边距(沿用 V2)
const PAD: int = 16          # 通用内边距(沿用 V2)

const GAP_S: int = GRID_2    # 8  — 行内元素
const GAP_M: int = GRID_3    # 16 — 控件之间
const GAP_L: int = GRID_4    # 24 — section 之间
const GAP_SM: int = 6        # 紧凑间距(沿用 V2,放在 GRID_2 和 GRID_1 之间)
const GAP: int = 12          # 标准间距(沿用 V2)
const GAP_LG: int = 18       # 大间距(沿用 V2)

const ROW_H: int = 36        # 默认 row 高度
const BTN_W: int = 280       # 主菜单按钮宽
const BTN_H: int = 40        # 主菜单按钮高(从 52 降到 40)
const FRAME_W: int = 1       # 外框粗
const TITLE_BAR_H: int = 44  # 标题栏高度
const FOOTER_BAR_H: int = 48 # 操作栏高度

# === 间距/字号工具 ===
## 返回一段 RichTextLabel 的"colorize" BBCode 包装(用于战报 / 单位信息)。
static func t(text: String, color: Color) -> String:
	return "[color=#%s]%s[/color]" % [color.to_html(false), text]

## 哑金细线风格 Label 文字。
static func gold(text: String) -> String:
	return t(text, C_GOLD)

## 火红强调。
static func fire(text: String) -> String:
	return t(text, C_FIRE_RED)

## 暖白正文。
static func warm(text: String) -> String:
	return t(text, C_TEXT_WARM)


# ============================================================
# Theme builder — 在 _ready 时给一个节点灌入 GBA 主题
# ============================================================

## 给单个 Button 灌入"蓝底烫金边"主题。新按钮优先用这个,别再一个个
## theme_override_* 手写。
static func apply_button_theme(btn: Button, font_size: int = FS_BTN) -> void:
	Visual.button(btn, false, font_size)

## 给一个 Control/Panel 灌入"深绿底 + 烫金外框"主题。
static func apply_panel_theme(panel: Control, fill: Color = C_BG_PANEL) -> void:
	if panel is Panel or panel is PanelContainer:
		panel.add_theme_stylebox_override("panel", Visual.surface(fill))

## 主按钮(烫金底 + 烫金亮边 + 暖白粗字)— web UI "创建并进入大厅"风格。
## 用于关键确认操作:创建房间、启动游戏、添加 AI、改队伍等。
static func apply_primary_button_theme(btn: Button, font_size: int = FS_BTN) -> void:
	Visual.button(btn, true, font_size)

static func hover_soft_glow(sb: StyleBoxFlat) -> void:
	sb.border_color = C_GOLD_BRIGHT
	sb.shadow_size = 0

static func press_dim(sb: StyleBoxFlat) -> void:
	# Dim the background ~10% on press for tactile feedback. Mirrors
	# the hover glow darkening but without the shadow halo.
	sb.bg_color = sb.bg_color.darkened(0.1)

## 普通按钮,但用 section header 风格(小尺寸、淡背景)— 用于"返回/取消"。
static func apply_secondary_button_theme(btn: Button, font_size: int = 14) -> void:
	Visual.button(btn, false, font_size)

## 给 Label 设置统一字号 + 暖白文字。
static func apply_label_theme(lbl: Label, font_size: int = FS_SUB,
		color: Color = C_TEXT_WARM) -> void:
	lbl.add_theme_font_size_override("font_size", font_size)
	lbl.add_theme_color_override("font_color", color)


## 给 Label 设置成 section header(暖金小字)—— web UI 的 section title 风格。
static func apply_section_header(lbl: Label) -> void:
	lbl.add_theme_font_size_override("font_size", 14)
	lbl.add_theme_color_override("font_color", C_GOLD)


## 给 HSeparator 灌入烫金主题(用作 section divider)。
static func apply_section_divider(sep: HSeparator) -> void:
	var sb := StyleBoxFlat.new()
	sb.bg_color = C_DIVIDER
	sb.content_margin_top = 1
	sep.add_theme_stylebox_override("separator", sb)


## 给 RichTextLabel 设置字号 + 暖白。
static func apply_richtext_theme(rt: RichTextLabel, font_size: int = FS_SUB) -> void:
	rt.add_theme_font_size_override("normal_font_size", font_size)
	rt.add_theme_color_override("default_color", C_TEXT_WARM)
