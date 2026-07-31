extends RefCounted
## hud_theme.gd — GBA 火纹风主题注入层(P2 从 main.gd 抽离)。
##
## 一次性执行、幂等的纯样式代码,原先占据 main.gd 三百余行却与业务逻辑无关。
## 全部 static,采用项目既有的 host 派发约定(参见 mainline_responses.gd):
## `host` 即 main.gd 节点,通过它读取 @onready 节点引用。
##
## 对外接口:
##   apply_gba(host)              — 启动时总入口(内部会调 apply_hud)
##   apply_hud(host)              — HUD 四角 pill / 面板 / 气泡 / 对话 / 结算
##   apply_theme(host, name)      — 用户在设置里切换配色方案时重灌
##
## main.gd 侧保留三个同名薄壳转发,既有调用点无需改动。
## 注意:不写 class_name —— headless 下跨文件 class_name 引用会撞 Parse Error。

const MenuTheme = preload("res://scripts/ui/menu_theme.gd")
const BattleTheme = preload("res://scripts/ui/battle_theme.gd")

static func apply_theme(host: Node, theme_name: String) -> void:
	# 默认主题对齐「边境军议档案」surface/panel:近黑墨蓝 + 哑光黄铜。
	var bg_color: Color = Color(0.03, 0.06, 0.10)   # deep_gba 兜底(近黑墨蓝)
	var panel_color: Color = Color(0.08, 0.14, 0.24)
	var border_color: Color = Color(0.79, 0.63, 0.29)  # 金 C_GOLD
	var text_color: Color = Color(0.96, 0.91, 0.76)   # 暖白 C_TEXT_WARM
	var btn_bg: Color = Color(0.12, 0.20, 0.32)       # 深蓝底 C_BTN_BLUE
	if theme_name == "metal_silver":
		bg_color = Color(0.10, 0.10, 0.13)
		panel_color = Color(0.16, 0.16, 0.18)
		border_color = Color(0.70, 0.73, 0.78)  # 银
		text_color = Color(0.92, 0.94, 0.96)
		btn_bg = Color(0.30, 0.34, 0.40)
	elif theme_name == "minimal_light":
		bg_color = Color(0.92, 0.92, 0.88)
		panel_color = Color(0.96, 0.96, 0.94)
		border_color = Color(0.30, 0.30, 0.30)  # 深灰边
		text_color = Color(0.12, 0.12, 0.12)   # 深色字
		btn_bg = Color(0.78, 0.80, 0.84)       # 浅灰按钮
	if host.backdrop != null and is_instance_valid(host.backdrop):
		host.backdrop.color = bg_color
	# 重灌核心面板的 StyleBoxFlat 让边界和底色跟主题
	var theme_panels: Array = [host.settings_panel, host.pause_panel, host.battle_result_panel, host.war_report_panel]
	for p in theme_panels:
		if p == null or not is_instance_valid(p):
			continue
		var sb: StyleBoxFlat = StyleBoxFlat.new()
		sb.bg_color = panel_color
		sb.border_color = border_color
		sb.set_border_width_all(2)
		sb.set_corner_radius_all(2)
		p.add_theme_stylebox_override("panel", sb)
	# 重灌按钮 StyleBoxFlat 影响主菜单 + 子菜单底部按钮
	# (P2:save_*_btn 由 saves_controller.gd 自管主题,不再列在这里)
	# 设置/暂停/教程/战斗详情按钮的唯一样式所有者 = 本函数(apply_hud 不再重复注入)。
	var theme_btns: Array = [host.settings_button, host.settings_apply_btn, host.settings_cancel_btn,
		host.settings_close_btn, host.settings_font_small_btn, host.settings_font_med_btn, host.settings_font_big_btn,
		host.settings_red_btn, host.settings_blue_btn, host.settings_green_btn, host.settings_yellow_btn,
		host.settings_mute_btn, host.pause_resume_btn, host.pause_suspend_btn, host.pause_main_menu_btn,
		host.pause_quit_btn, host.pause_settings_btn, host.tutorial_got_it_btn,
		host.battle_detail_btn, host.end_turn_button, host.help_button,
		host.exit_button, host.resume_button, host.lobby_button,
		host.lobby_view.lobby_add_ai_btn, host.lobby_view.lobby_remove_ai_btn,
		host.lobby_view.lobby_start_btn, host.lobby_view.lobby_back_btn,
		host.lobby_view.lobby_apply_team_btn, host.lobby_view.lobby_host_apply_btn,
		host.join_by_code_button]
	for b in theme_btns:
		if b == null or not is_instance_valid(b):
			continue
		var sb2: StyleBoxFlat = StyleBoxFlat.new()
		sb2.bg_color = btn_bg
		sb2.border_color = border_color
		sb2.set_border_width_all(2)
		sb2.set_corner_radius_all(4)
		b.add_theme_stylebox_override("normal", sb2)
		var sbh: StyleBoxFlat = sb2.duplicate()
		sbh.bg_color = btn_bg.lightened(0.15)
		b.add_theme_stylebox_override("hover", sbh)
		var sbp: StyleBoxFlat = sb2.duplicate()
		sbp.bg_color = btn_bg.darkened(0.15)
		b.add_theme_stylebox_override("pressed", sbp)
	# 文本色整体调节主菜单 / SettingPanel 内的关键 label
	var theme_text_labels: Array = [host.settings_panel.find_child("Header", true, false)] if host.settings_panel != null else []
	for lbl in theme_text_labels:
		if lbl != null and is_instance_valid(lbl):
			lbl.add_theme_color_override("font_color", text_color)
	host._update_status("主题: %s" % theme_name)

static func apply_gba(host: Node) -> void:
	# 1) 全屏深绿背景(ColorRect 颜色已在 .tscn 设)
	host.backdrop.color = MenuTheme.C_BG_DEEP
	host.backdrop.mouse_filter = Control.MOUSE_FILTER_IGNORE
	# 2) 边框由 ReferenceRect 画,这里只调整颜色变量(已硬编码在 .tscn)
	# 3) Connecting 框(深绿底)
	host.connecting_frame.color = MenuTheme.C_BG_PANEL
	# 4) 主菜单 + 游戏内按钮统一灌主题
	# (P2:save_*_btn 由 saves_controller.gd 自管主题,不再列在这里)
	# (Batch A:ml_*_btn 由 mainline_controller.gd 自管主题,这里只保留 host.mainline_button)
	for btn in [host.lobby_button, host.saves_button, host.mainline_button, host.editor_button, host.settings_button, host.exit_button,
				host.reconnect_button, host.end_turn_button, host.war_report_button,
				host.attack_confirm_btn, host.attack_cancel_btn]:
		if btn != null and is_instance_valid(btn):
			MenuTheme.apply_button_theme(btn, MenuTheme.FS_BTN)
	# end_turn 和 war_report 用小一号字号(4 角极小 pill)
	if host.end_turn_button != null and is_instance_valid(host.end_turn_button):
		MenuTheme.apply_button_theme(host.end_turn_button, 14)
	if host.war_report_button != null and is_instance_valid(host.war_report_button):
		MenuTheme.apply_button_theme(host.war_report_button, 14)
	# 5) 标题/副标题/footer 文字色
	MenuTheme.apply_label_theme(host.menu_title, MenuTheme.FS_HERO, MenuTheme.C_GOLD)
	MenuTheme.apply_label_theme(host.menu_subtitle, MenuTheme.FS_SUB, MenuTheme.C_TEXT_WARM)
	MenuTheme.apply_label_theme(host.menu_footer, MenuTheme.FS_FOOT, MenuTheme.C_TEXT_DIM)
	MenuTheme.apply_label_theme(host.connecting_title, 22, MenuTheme.C_GOLD)
	MenuTheme.apply_label_theme(host.connecting_label, MenuTheme.FS_SUB, MenuTheme.C_TEXT_WARM)
	# === V2 第 2 轮:HUD 4 角 pill 主题 ===
	apply_hud(host)
	# 战报/信息浮层(深绿底 + 烫金边)
	var sb_popup := StyleBoxFlat.new()
	sb_popup.bg_color = MenuTheme.C_BG_PANEL
	sb_popup.border_color = MenuTheme.C_GOLD
	sb_popup.set_border_width_all(2)
	sb_popup.content_margin_left = MenuTheme.PAD
	sb_popup.content_margin_right = MenuTheme.PAD
	sb_popup.content_margin_top = MenuTheme.PAD
	sb_popup.content_margin_bottom = MenuTheme.PAD
	host.war_report_panel.add_theme_stylebox_override("panel", sb_popup)

static func apply_hud(host: Node) -> void:
	# Pills are ColorRect containers with ReferenceRect borders added
	# in _ready. We only need to set font sizes / colors on inner Labels.
	var pill_size: int = 14
	# 物理窗口宽度断点 — 优先从 --resolution 拿(headless 唯一可靠来源),
	# 否则 DisplayServer.window_get_size()(非 headless 时与窗口一致)。
	var win_w: int = 0
	var args: PackedStringArray = OS.get_cmdline_args()
	for i in args.size():
		if args[i] == "--resolution" and i + 1 < args.size():
			var parts: PackedStringArray = args[i + 1].split("x")
			if parts.size() == 2:
				win_w = int(parts[0])
	if win_w == 0:
		var env: String = OS.get_environment("BB_REVIEW_RES")
		if env != "":
			var parts2: PackedStringArray = env.split("x")
			if parts2.size() == 2:
				win_w = int(parts2[0])
	if win_w == 0:
		win_w = DisplayServer.window_get_size().x
	if win_w > 0 and win_w <= 1366:
		pill_size = 20  # 1.4x 字号补偿,1280 下保证正文物理字号可读
	if host.info_panel != null and is_instance_valid(host.info_panel):
		# InfoPanel 常驻右翼;样式由 battle_theme.apply_floating_panel 唯一接管。
		host.info_panel.visible = true
	for lbl in [host.turn_badge_label, host.phase_badge_label, host.current_player_label, host.gold_label]:
		if lbl != null and is_instance_valid(lbl):
			lbl.add_theme_font_size_override("font_size", pill_size)
			lbl.add_theme_color_override("font_color", MenuTheme.C_TEXT_WARM)
	# V2 第 3 轮:InfoPanel 主题(当前指挥官 + 单位详情 + 玩家列表)
	if host.commander_title != null and is_instance_valid(host.commander_title):
		host.commander_title.add_theme_font_size_override("font_size", 16)
		host.commander_title.add_theme_color_override("font_color", MenuTheme.C_GOLD)
	if host.unit_info_title != null and is_instance_valid(host.unit_info_title):
		host.unit_info_title.add_theme_font_size_override("font_size", 20)
		host.unit_info_title.add_theme_color_override("font_color", MenuTheme.C_GOLD)
	if host.unit_info_subtitle != null and is_instance_valid(host.unit_info_subtitle):
		host.unit_info_subtitle.add_theme_font_size_override("font_size", 14)
		host.unit_info_subtitle.add_theme_color_override("font_color", MenuTheme.C_TEXT_DIM)
	if host.commander_name != null and is_instance_valid(host.commander_name):
		host.commander_name.add_theme_font_size_override("normal_font_size", 18 if pill_size >= 20 else 13)
		host.commander_name.add_theme_color_override("default_color", MenuTheme.C_TEXT_WARM)
	if host.commander_co_bar != null and is_instance_valid(host.commander_co_bar):
		var sb_bg := StyleBoxFlat.new()
		sb_bg.bg_color = Color(0.18, 0.12, 0.06, 1)
		sb_bg.border_color = MenuTheme.C_GOLD
		sb_bg.set_border_width_all(1)
		sb_bg.content_margin_left = 4
		sb_bg.content_margin_right = 4
		sb_bg.content_margin_top = 3
		sb_bg.content_margin_bottom = 3
		var sb_fg := StyleBoxFlat.new()
		sb_fg.bg_color = MenuTheme.C_GOLD
		sb_fg.border_color = MenuTheme.C_GOLD_BRIGHT
		sb_fg.set_border_width_all(1)
		host.commander_co_bar.add_theme_stylebox_override("background", sb_bg)
		host.commander_co_bar.add_theme_stylebox_override("fill", sb_fg)
	if host.players_list != null and is_instance_valid(host.players_list):
		host.players_list.add_theme_font_size_override("normal_font_size", 18 if pill_size >= 20 else 13)
		host.players_list.add_theme_color_override("default_color", MenuTheme.C_TEXT_WARM)
	# T:V3 — 英雄立绘槽主题用 MenuTheme.apply_panel_theme + token(替代手写 StyleBoxFlat)
	if host.hero_portrait_panel != null and is_instance_valid(host.hero_portrait_panel):
		host.hero_portrait_panel.self_modulate = Color(1, 1, 1, 0)
		var sb_portrait := StyleBoxFlat.new()
		sb_portrait.bg_color = Color(0, 0, 0, 0)
		sb_portrait.border_color = Color(0, 0, 0, 0)
		sb_portrait.border_width_left = 0
		sb_portrait.border_width_right = 0
		sb_portrait.border_width_top = 0
		sb_portrait.border_width_bottom = 0
		sb_portrait.content_margin_left = 0
		sb_portrait.content_margin_right = 0
		sb_portrait.content_margin_top = 0
		sb_portrait.content_margin_bottom = 0
		host.hero_portrait_panel.add_theme_stylebox_override("panel", sb_portrait)
	if host.unit_info != null and is_instance_valid(host.unit_info):
		host.unit_info.add_theme_font_size_override("normal_font_size", 22 if pill_size >= 20 else 16)
		host.unit_info.add_theme_color_override("default_color", MenuTheme.C_TEXT_WARM)
	if host.hero_portrait_caption != null and is_instance_valid(host.hero_portrait_caption):
		host.hero_portrait_caption.add_theme_color_override("font_color", MenuTheme.C_TEXT_WARM)
	# V2 第 4 轮:行动气泡主题(深绿底 + 烫金粗边)
	if host.action_bubble != null and is_instance_valid(host.action_bubble):
		# 行动菜单底板样式由 battle_theme.apply_action_menu 唯一接管。
		BattleTheme.apply_action_menu(host.action_bubble)
		for btn in [host.move_btn, host.attack_btn, host.skill_btn, host.wait_btn, host.claim_btn]:
			if btn != null and is_instance_valid(btn):
				MenuTheme.apply_button_theme(btn, 17)
				btn.custom_minimum_size.y = 48.0
	if host.left_hud_wing != null and is_instance_valid(host.left_hud_wing):
		var heading: Label = host.left_hud_wing.get_node_or_null("Heading") as Label
		var hint: Label = host.left_hud_wing.get_node_or_null("Hint") as Label
		if heading != null:
			heading.add_theme_font_size_override("font_size", 18)
		if hint != null:
			hint.add_theme_font_size_override("font_size", 15)
	if host.action_title != null and is_instance_valid(host.action_title):
		host.action_title.add_theme_font_size_override("font_size", 17)
	# V2 第 5 轮:战报浮层标题/日志文本主题(面板底色归 apply_theme 唯一接管)
	var war_header: Label = host.war_report_panel.find_child("Header", true, false)
	if war_header != null:
		war_header.add_theme_font_size_override("font_size", 16)
		war_header.add_theme_color_override("font_color", MenuTheme.C_GOLD)
	if host.war_report_close_btn != null and is_instance_valid(host.war_report_close_btn):
		MenuTheme.apply_button_theme(host.war_report_close_btn, 16)
	if host.action_log != null and is_instance_valid(host.action_log):
		host.action_log.add_theme_font_size_override("normal_font_size", 14)
		host.action_log.add_theme_color_override("default_color", MenuTheme.C_TEXT_WARM)
	# V2 第 6 轮:设置 + 暂停面板文本主题(面板底色归 apply_theme 唯一接管)
	# Settings Header(颜色归 apply_theme 唯一接管)
	var settings_header: Label = host.settings_panel.find_child("Header", true, false)
	if settings_header != null:
		settings_header.add_theme_font_size_override("font_size", 20)
	# Settings row labels
	for lbl in host.settings_panel.find_children("NameLabel", "", false, false):
		lbl.add_theme_color_override("font_color", MenuTheme.C_TEXT_WARM)
	for lbl in host.settings_panel.find_children("FontLabel", "", false, false):
		lbl.add_theme_color_override("font_color", MenuTheme.C_TEXT_WARM)
	for lbl in host.settings_panel.find_children("ColorLabel", "", false, false):
		lbl.add_theme_color_override("font_color", MenuTheme.C_TEXT_WARM)
	for lbl in host.settings_panel.find_children("ThemeLabel", "", false, false):
		lbl.add_theme_color_override("font_color", MenuTheme.C_TEXT_WARM)
	# Settings buttons 由 apply_theme 唯一接管,不再在此重复覆盖
	# NameInput style
	if host.settings_name_input != null and is_instance_valid(host.settings_name_input):
		host.settings_name_input.add_theme_font_size_override("font_size", 16)
		host.settings_name_input.add_theme_color_override("font_color", MenuTheme.C_TEXT_WARM)
	# Pause Header
	var pause_header: Label = host.pause_panel.find_child("Header", true, false)
	if pause_header != null:
		pause_header.add_theme_font_size_override("font_size", 24)
		pause_header.add_theme_color_override("font_color", MenuTheme.C_GOLD)
	# Pause buttons 由 apply_theme 唯一接管,不再在此重复覆盖
	# V2 第 7 轮:对话 + 教程 + 战斗结算主题
	# TutorialBubble 表面:半透明墨蓝填充,边框由场景内 OrnateFrame(二级框)负责。
	if host.tutorial_bubble != null and is_instance_valid(host.tutorial_bubble):
		var sb_tut := StyleBoxFlat.new()
		sb_tut.bg_color = Color(MenuTheme.C_BG_PANEL.r, MenuTheme.C_BG_PANEL.g, MenuTheme.C_BG_PANEL.b, 0.9)
		sb_tut.border_color = Color(0, 0, 0, 0)
		sb_tut.set_border_width_all(0)
		host.tutorial_bubble.add_theme_stylebox_override("panel", sb_tut)
	# Tutorial header
	var tut_header: Label = host.tutorial_bubble.find_child("Header", true, false)
	if tut_header != null:
		tut_header.add_theme_font_size_override("font_size", 16)
		tut_header.add_theme_color_override("font_color", MenuTheme.C_GOLD)
	if host.tutorial_text != null and is_instance_valid(host.tutorial_text):
		host.tutorial_text.add_theme_font_size_override("normal_font_size", 14)
		host.tutorial_text.add_theme_color_override("default_color", MenuTheme.C_TEXT_WARM)
	# Dialog/Tutorial/Battle buttons
	# (tutorial_got_it_btn / battle_detail_btn 归 apply_theme 唯一接管)
	for btn in [host.battle_mainline_next_btn, host.battle_back_menu_btn]:
		if btn != null and is_instance_valid(btn):
			MenuTheme.apply_button_theme(btn, 16)
	# Battle result header + winner
	var res_header: Label = host.battle_result_panel.find_child("Header", true, false)
	if res_header != null:
		res_header.add_theme_font_size_override("font_size", 22)
		res_header.add_theme_color_override("font_color", MenuTheme.C_GOLD)
	if host.battle_result_winner != null and is_instance_valid(host.battle_result_winner):
		host.battle_result_winner.add_theme_font_size_override("normal_font_size", 18)
	if host.battle_result_stats != null and is_instance_valid(host.battle_result_stats):
		host.battle_result_stats.add_theme_font_size_override("normal_font_size", 14)
		host.battle_result_stats.add_theme_color_override("default_color", MenuTheme.C_TEXT_WARM)
	BattleTheme.apply_floating_panel(host.info_panel)
	# 大厅主/次按钮主题已随组件搬到 lobby_controller._ready()
