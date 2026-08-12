extends Node
const MenuTheme = preload("res://scripts/ui/menu_theme.gd")
const MapPreviewSummary = preload("res://scripts/ui/map_preview_summary.gd")
const CnLabels = preload("res://scripts/ui/cn_labels.gd")
const HudTheme = preload("res://scripts/ui/hud_theme.gd")
const PortraitLoader = preload("res://scripts/core/portrait_loader.gd")
const UIPanelFocus = preload("res://scripts/ui/_components/ui_panel_focus.gd")
## main.gd — top-level UI state machine for the BattleBlitz Godot client.
##
## M2.5 ships the minimum path: main menu → "free play" → auto-create
## game + add AI + start → land in the game view with a live WS
## connection. The M1 board-rendering pipeline (Board + MapMetrics +
## MapTheme + MapLoader + TileSetBuilder) is reused as-is for the
## Game view's board instance.
##
## View flow (M2.5):
##   [menu]  ── "自由模式" ──▶  [connecting]  ──▶  [game]
##                              (loading: create+add-ai+start+ws-connect)
##
## M3 will split [game] into [lobby] (waiting room) + [game] (play)
## and add a real [create] / [join] form with map/biome pickers.

@onready var menu_panel: Control = $Menu
@onready var title_cover: TextureRect = $Menu/TitleCover
@onready var title_cover_dev_picker: OptionButton = $Menu/TitleCoverDevPicker
@onready var connecting_panel: Control = $Connecting
@onready var game_view: Control = $GameView
@onready var status_label: Label = $StatusLabel
@onready var board: Board = $GameView/Board

# HUD widgets (V2 第 2 轮:4 角极小 pill + 战报/信息浮层)
# Pills are ColorRect containers (Panel has display issues in headless);
# the Label child still drives text content.
@onready var turn_badge: ColorRect = $GameView/HUD/TopLeft/TurnBadge
@onready var turn_badge_label: Label = $GameView/HUD/TopLeft/TurnBadge/Label
@onready var phase_badge: ColorRect = $GameView/HUD/TopLeft/PhaseBadge
@onready var phase_badge_label: Label = $GameView/HUD/TopLeft/PhaseBadge/Label
@onready var current_player_badge: ColorRect = $GameView/HUD/TopRight/CurrentPlayerBadge
@onready var current_player_label: Label = $GameView/HUD/TopRight/CurrentPlayerBadge/Label
@onready var ai_thinking_label: ColorRect = $GameView/HUD/BottomRight/AIThinking
# M4.1 移动模式状态机
var _move_mode_unit_id: int = -1
var _move_reachable_set: Dictionary = {}
# M4.2 攻击模式状态机
var _attack_mode_unit_id: int = -1
# 攻击候选目标: {target_unit_id: {x,y,forecast}}
var _attack_targets: Dictionary = {}
var _pending_attack_attacker_id: int = -1
var _pending_attack_target_id: int = -1
# 技能模式状态机(heal 选友军 / arcane_strike 选敌军,通用)
var _skill_mode_unit_id: int = -1
var _skill_targets: Dictionary = {}
# 鸢影·沉默领域选中心模式 (P+):玩家选 5×5 中心后 fire。
# -1 = 未进入模式,>=0 = 该 player_id 的 commander 等待选中心。
var _silence_pick_center_for_pid: int = -1
var _pending_skill_id: String = ""
const _ACTION_CONTEXT_INITIAL := "initial"
const _ACTION_CONTEXT_POST_MOVE := "post_move"
const _ACTION_CONTEXT_POST_ACTION := "post_action"
# M4.5 招募状态机(unit_type → name 也在用)
const _RECRUIT_OPTIONS := [
	{"type": "swordsman", "cost": 200},
	{"type": "archer", "cost": 250},
	{"type": "warrior", "cost": 260},
	{"type": "lancer", "cost": 280},
	{"type": "warlock", "cost": 300},
	{"type": "healer", "cost": 350},
	{"type": "knight", "cost": 400},
	{"type": "falcon_knight", "cost": 450},
	{"type": "dragon_rider", "cost": 500},
	{"type": "berserker", "cost": 500},
	{"type": "blade_master", "cost": 650},
	{"type": "sniper", "cost": 650},
	{"type": "saint", "cost": 650},
	{"type": "paladin", "cost": 700},
	{"type": "sage", "cost": 700},
]
var _recruit_mode_unit_id: int = -1
@onready var end_turn_button: Button = $GameView/HUD/TopRight/EndTurnButton
@onready var gold_panel: ColorRect = $GameView/HUD/BottomLeft/GoldPanel
@onready var gold_label: Label = $GameView/HUD/BottomLeft/GoldPanel/GoldLabel
@onready var war_report_button: Button = $GameView/HUD/BottomRight/WarReportButton
@onready var war_report_panel: Panel = $GameView/HUD/WarReportPanel
@onready var war_report_close_btn: Button = $GameView/HUD/WarReportPanel/CloseBtn

# M5.1 CO Roster(全玩家头像 + 能量条 + Power 按钮)

# HUD 是 CanvasLayer — 独立 transform 层,不受 GameView.visible 控制
@onready var hud_layer: CanvasLayer = $GameView/HUD
@onready var battle_backdrop_layer: CanvasLayer = $GameView/BattleBackdrop

# M6.1 BGM player
@onready var bgm_player: AudioStreamPlayer = $BGMPlayer
@onready var action_log: RichTextLabel = $GameView/HUD/WarReportPanel/ActionLog
@onready var auto_save_toast: Panel = $GameView/HUD/AutoSaveToast
@onready var auto_save_toast_label: Label = $GameView/HUD/AutoSaveToast/ToastLabel
# CreateFormPanel(自由模式专用)— 房间设置表单
# V2 第 3 轮:InfoPanel 是左侧 30% 信息区(单位详情 + 玩家列表)
@onready var info_panel: Panel = $GameView/HUD/InfoPanel
@onready var left_hud_wing: ColorRect = $GameView/HUD/LeftHudWing
@onready var right_hud_wing: ColorRect = $GameView/HUD/RightHudWing
@onready var commander_title: Label = $GameView/HUD/InfoPanel/CommanderTitle
@onready var commander_name: RichTextLabel = $GameView/HUD/InfoPanel/CommanderName
# M5.1 CO Roster — 顶部全玩家头像 + meter + 发动按钮
@onready var co_roster: HBoxContainer = $GameView/HUD/CORoster
@onready var commander_co_bar: ProgressBar = $GameView/HUD/InfoPanel/CommanderCOBar
@onready var commander_co_label: Label = $GameView/HUD/InfoPanel/CommanderCOBar/ValueLabel
@onready var unit_info_title: Label = $GameView/HUD/InfoPanel/UnitInfoTitle
@onready var unit_info_subtitle: Label = $GameView/HUD/InfoPanel/UnitInfoSubtitle
@onready var unit_info: RichTextLabel = $GameView/HUD/InfoPanel/UnitInfo
@onready var players_list: RichTextLabel = $GameView/HUD/InfoPanel/PlayersList
# T:#18 — 英雄立绘与单位详情使用同一张检视卡,避免视线横跨整屏。
# TextureRect 由 _set_unit_info_portrait 程序化写入。
@onready var hero_portrait_panel: Panel = $GameView/HUD/InfoPanel/UnitPortraitPanel
@onready var hero_portrait_caption: Label = $GameView/HUD/InfoPanel/UnitPortraitPanel/Caption
@onready var turn_banner: ColorRect = $GameView/TurnBannerFrame
@onready var turn_banner_label: Label = $GameView/TurnBannerFrame/TurnBannerLabel
var _turn_banner_tween: Tween = null
var _ai_pulse_tween: Tween = null
var _auto_save_toast_tween: Tween = null
var _unit_info_portrait_tex: TextureRect = null

# V2 第 6 轮:设置 + 暂停面板
@onready var settings_panel: Panel = $GameView/HUD/SettingsPanel
@onready var settings_close_btn: Button = $GameView/HUD/SettingsPanel/CloseBtn
@onready var settings_name_input: LineEdit = $GameView/HUD/SettingsPanel/SettingsList/NameRow/NameInput
@onready var settings_apply_btn: Button = $GameView/HUD/SettingsPanel/SettingsList/ButtonRow/ApplyBtn
@onready var settings_cancel_btn: Button = $GameView/HUD/SettingsPanel/SettingsList/ButtonRow/CancelBtn
# T:93 — Settings 按钮节点(节点已建,只差 connect)
@onready var settings_font_small_btn: Button = $GameView/HUD/SettingsPanel/SettingsList/FontRow/FontSmallBtn
@onready var settings_font_med_btn: Button = $GameView/HUD/SettingsPanel/SettingsList/FontRow/FontMedBtn
@onready var settings_font_big_btn: Button = $GameView/HUD/SettingsPanel/SettingsList/FontRow/FontBigBtn
@onready var settings_red_btn: Button = $GameView/HUD/SettingsPanel/SettingsList/ColorRow/RedBtn
@onready var settings_blue_btn: Button = $GameView/HUD/SettingsPanel/SettingsList/ColorRow/BlueBtn
@onready var settings_green_btn: Button = $GameView/HUD/SettingsPanel/SettingsList/ColorRow/GreenBtn
@onready var settings_yellow_btn: Button = $GameView/HUD/SettingsPanel/SettingsList/ColorRow/YellowBtn
@onready var settings_theme_dropdown: OptionButton = $GameView/HUD/SettingsPanel/SettingsList/ThemeRow/ThemeDropdown
@onready var settings_mute_btn: Button = $GameView/HUD/SettingsPanel/SettingsList/AudioRow/MuteBtn
@onready var pause_overlay: ColorRect = $GameView/HUD/PauseOverlay
@onready var pause_panel: Panel = $GameView/HUD/PausePanel
@onready var pause_resume_btn: Button = $GameView/HUD/PausePanel/PauseList/ResumeBtn
@onready var pause_settings_btn: Button = $GameView/HUD/PausePanel/PauseList/SettingsBtn
@onready var pause_main_menu_btn: Button = $GameView/HUD/PausePanel/PauseList/MainMenuBtn
@onready var pause_suspend_btn: Button = $GameView/HUD/PausePanel/PauseList/PauseSuspendBtn
@onready var pause_quit_btn: Button = $GameView/HUD/PausePanel/PauseList/QuitBtn

# V2 第 7 轮:对话框 + 教程气泡 + 战斗结算

# T:4 RecruitPanel — 真 modal(替换 status 凑合)
@onready var recruit_panel: Panel = $GameView/HUD/RecruitPanel
@onready var recruit_status_label: Label = $GameView/HUD/RecruitPanel/RecruitStatusLabel
@onready var recruit_list: VBoxContainer = $GameView/HUD/RecruitPanel/RecruitList
@onready var recruit_close_btn: Button = $GameView/HUD/RecruitPanel/CloseBtn
var _recruit_pending_tile: Vector2i = Vector2i(-1, -1)
@onready var tutorial_bubble: Panel = $GameView/HUD/TutorialBubble
@onready var tutorial_text: RichTextLabel = $GameView/HUD/TutorialBubble/TutorialText
@onready var tutorial_got_it_btn: Button = $GameView/HUD/TutorialBubble/GotItBtn
@onready var battle_result_panel: Panel = $GameView/HUD/BattleResultPanel
@onready var battle_result_winner: RichTextLabel = $GameView/HUD/BattleResultPanel/WinnerBanner
@onready var battle_result_stats: RichTextLabel = $GameView/HUD/BattleResultPanel/StatsList
@onready var battle_detail_btn: Button = $GameView/HUD/BattleResultPanel/ResultBtnRow/DetailBtn
@onready var battle_mainline_next_btn: Button = $GameView/HUD/BattleResultPanel/ResultBtnRow/MainlineNextBtn
@onready var battle_back_lobby_btn: Button = $GameView/HUD/BattleResultPanel/ResultBtnRow/BackLobbyBtn
@onready var battle_back_menu_btn: Button = $GameView/HUD/BattleResultPanel/ResultBtnRow/BackMenuBtn

# 通用 Yes/No 确认弹窗 — 主菜单 / 大厅 / 游戏通用(置于 root,所以能浮在任意 view 上)
@onready var confirm_dialog: Panel = $ConfirmDialog
@onready var confirm_title_label: Label = $ConfirmDialog/ConfirmTitle
@onready var confirm_body_label: Label = $ConfirmDialog/ConfirmBody
@onready var confirm_yes_btn: Button = $ConfirmDialog/ButtonRow/ConfirmYesBtn
@onready var confirm_no_btn: Button = $ConfirmDialog/ButtonRow/ConfirmNoBtn
# 一次性 Callable — 触发后立刻清空,避免 modal 重复触发 / 旧 callback 残留。
var _confirm_yes_callback: Callable = Callable()
var _confirm_no_callback: Callable = Callable()

# V2 第 4 轮:行动气泡(5 按钮)
@onready var action_bubble: Panel = $GameView/HUD/ActionBubble
@onready var action_title: Label = $GameView/HUD/ActionBubble/ActionTitle
@onready var cancel_btn: Button = $GameView/HUD/ActionBubble/ActionList/CancelBtn
@onready var move_btn: Button = $GameView/HUD/ActionBubble/ActionList/MoveBtn
@onready var attack_btn: Button = $GameView/HUD/ActionBubble/ActionList/AttackBtn
@onready var skill_btn: Button = $GameView/HUD/ActionBubble/ActionList/SkillBtn
@onready var wait_btn: Button = $GameView/HUD/ActionBubble/ActionList/WaitBtn
@onready var claim_btn: Button = $GameView/HUD/ActionBubble/ActionList/ClaimBtn
@onready var action_pointer: Polygon2D = $GameView/HUD/ActionBubble/ActionPointer
@onready var attack_confirm_panel: Panel = $GameView/HUD/AttackConfirmPanel
@onready var attack_confirm_body: RichTextLabel = $GameView/HUD/AttackConfirmPanel/Body
@onready var attack_confirm_btn: Button = $GameView/HUD/AttackConfirmPanel/ButtonRow/ConfirmBtn
@onready var attack_cancel_btn: Button = $GameView/HUD/AttackConfirmPanel/ButtonRow/CancelBtn

# 当前选中单位 + 待操作 action
var _selected_unit_id: int = -1
var _selected_unit_pos: Vector2i = Vector2i(-1, -1)

# Board 刷新防抖:server WS 只在 connect 时推 1 次 state.snapshot,
# 后续只推 event.delta。客户端订阅粒度事件后,主动拉 GET /state (200ms 防抖)
# → ingest_snapshot → emit units_changed → board FLIP 单位位置。
const _BOARD_REFRESH_DEBOUNCE_SEC: float = 0.2
var _board_refresh_pending: bool = false

# 状态轮询:server WS 不推 turn_end / 回合结束 / 对局结束事件,
# 这些必须靠 REST GET /state 轮询追踪。每 1 秒拉一次(game view 时)。
const _STATE_POLL_INTERVAL_SEC: float = 1.0
var _state_poll_timer: Timer = null

# Main menu widgets (GBA 风 V2)
@export var title_cover_default_path: String = "res://assets/ui/title_cover_v5_party_dawn.png"
@export var title_cover_paths: Array[String] = [
	"res://assets/ui/title_cover_v1_undead_king.png",
	"res://assets/ui/title_cover_v2_snow_farewell.png",
	"res://assets/ui/title_cover_v3_leviathan_market.png",
	"res://assets/ui/title_cover_v4_cathedral_prayer.png",
	"res://assets/ui/title_cover_v5_party_dawn.png",
	"res://assets/ui/title_cover_v6_bard_market.png",
]
@onready var mainline_button: Button = $Menu/CenterContainer/GroupRow/SoloCard/MainlineButton
@onready var editor_button: Button = $Menu/CenterContainer/FooterRow/EditorButton

# T:96 MainlineView — Batch A:节点搬入 mainline_controller.gd(组件),main.gd 保留指向同一节点的引用供 batch B 使用
@onready var mainline_view = $MainlineView
@onready var ml_prep_summary: RichTextLabel = $MainlineView/MLFrame/MLPrepSummary
@onready var ml_prep_tabs: HBoxContainer = $MainlineView/MLFrame/MLPrepTabs
@onready var ml_prep_content: RichTextLabel = $MainlineView/MLFrame/MLPrepContent
@onready var ml_prep_start_btn: Button = $MainlineView/MLFrame/MLPrepStartBtn
@onready var ml_prep_complete_btn: Button = $MainlineView/MLFrame/MLPrepCompleteBtn
@onready var ml_prep_refresh_btn: Button = $MainlineView/MLFrame/MLPrepRefreshBtn
@onready var ml_prep_action_btn: Button = $MainlineView/MLFrame/MLPrepActionBtn
@onready var ml_prep_alt_action_btn: Button = $MainlineView/MLFrame/MLPrepAltActionBtn
@onready var ml_prep_hero_select: OptionButton = $MainlineView/MLFrame/MLPrepSelectorRow/MLPrepHeroSelect
@onready var ml_prep_equipment_select: OptionButton = $MainlineView/MLFrame/MLPrepSelectorRow/MLPrepEquipmentSelect
@onready var ml_prep_merc_unit_select: OptionButton = $MainlineView/MLFrame/MLPrepSelectorRow/MLPrepMercUnitSelect
@onready var ml_prep_merc_stat_select: OptionButton = $MainlineView/MLFrame/MLPrepSelectorRow/MLPrepMercStatSelect
@onready var ml_prep_shop_select: OptionButton = $MainlineView/MLFrame/MLPrepSelectorRow/MLPrepShopSelect
@onready var ml_prep_heroes_tab_btn: Button = $MainlineView/MLFrame/MLPrepTabs/HeroesTabBtn
@onready var ml_prep_roster_tab_btn: Button = $MainlineView/MLFrame/MLPrepTabs/RosterTabBtn
@onready var ml_prep_equipment_tab_btn: Button = $MainlineView/MLFrame/MLPrepTabs/EquipmentTabBtn
@onready var ml_prep_mercenary_tab_btn: Button = $MainlineView/MLFrame/MLPrepTabs/MercenaryTabBtn
@onready var ml_prep_shop_tab_btn: Button = $MainlineView/MLFrame/MLPrepTabs/ShopTabBtn
@onready var ml_prep_saves_tab_btn: Button = $MainlineView/MLFrame/MLPrepTabs/SavesTabBtn
@onready var lobby_button: Button = $Menu/CenterContainer/GroupRow/MultiCard/LobbyButton
@onready var join_by_code_input: LineEdit = $Menu/CenterContainer/GroupRow/MultiCard/JoinByCodeRow/JoinByCodeInput
@onready var join_by_code_button: Button = $Menu/CenterContainer/GroupRow/MultiCard/JoinByCodeRow/JoinByCodeButton
@onready var saves_button: Button = $Menu/CenterContainer/FooterRow/SavesButton
@onready var settings_button: Button = $Menu/CenterContainer/FooterRow/SettingsButton
@onready var help_button: Button = $Menu/CenterContainer/FooterRow/HelpButton
@onready var exit_button: Button = $Menu/CenterContainer/FooterRow/ExitButton

# T:5 单槽存档
@onready var resume_button: Button = $Menu/CenterContainer/FooterRow/ResumeButton
var _resume_game_id: int = 0
var _resume_player_id: int = 0
# P0:resume 流程分流("game" = 直接 rejoin,"suspend" = load_suspend 后再 rejoin)
var _resume_kind: String = ""

# P2:saves 视图独立为 saves_controller.gd,仅保留节点引用(无类型避开 class_name 缓存)
@onready var saves_view = $SavesView

# T:#16 in_progress 视图独立为 in_progress_controller.gd
@onready var in_progress_view = $InProgressView
@onready var in_progress_button: Button = $Menu/CenterContainer/FooterRow/InProgressButton

# T:3 基础大厅视图
@onready var editor_view = $EditorView  # -> editor_controller.gd (P2)

@onready var lobby_view: Control = $Lobby
# 大厅子控件引用已搬到 lobby_controller.gd(相对 $LobbyFrame 路径)
var _entry_flow: String = "free"
# M4.16+:game-over 保险。_on_match_ended 触发后置 true,屏蔽后续 state
# poll / AI 操作。重置场景时(_on_lobby_pressed / 新 game 创建)→ false。
var _game_over: bool = false
var _death_event_seq: int = 0  # 阵亡事件单调序列号,去重 DialogManager 触发
@onready var menu_title: Label = $Menu/CenterContainer/TitleBlock/TitleLine1
@onready var menu_subtitle: Label = $Menu/CenterContainer/TitleBlock/TitleLine2
@onready var menu_footer: Label = $Menu/Footer/FooterLabel
@onready var connecting_label: Label = $Connecting/ConnectingInner/ConnectingLabel
@onready var connecting_title: Label = $Connecting/ConnectingInner/ConnectingTitle
@onready var reconnect_button: Button = $Connecting/ConnectingInner/ReconnectButton
@onready var connecting_abort_btn: Button = $Connecting/ConnectingInner/AbortButton

# 框架面板(灌主题用) — 改用 ColorRect + ReferenceRect 组合更稳
@onready var backdrop: ColorRect = $Backdrop
@onready var frame_outer: ColorRect = $Menu/FrameOuter
@onready var frame_inner_border: ReferenceRect = $Menu/FrameInnerBorder
@onready var connecting_frame: ColorRect = $Connecting/ConnectingFrame

# T:97 — Tutorial 只弹一次(每次启动 client 不重复烦玩家)
var _tutorial_shown: bool = false
var _game_id: int = 0
var _player_id: int = 0
var _user_name: String = "Player"
var _loaded_board_signature: String = ""
var _active_mainline_id: String = ""
var _mainline_battle_game_id: int = 0
var _selected_mainline_id: String = "chapter_01_steel_rebellion"
# Phase 2: mainline session — backup source of truth for state scattered
# across handlers that re-implement mainline flow.  The new modules
# (``scripts/mainline/mainline_session.gd`` +
# ``scripts/mainline/mainline_responses.gd``) read/write via this
# instance; main.gd's own fields above stay read/write-compat for now
# and get synced through helper methods in the response handlers.
# Preloaded directly instead of relying on `class_name` global registration
# so the project's global_script_class_cache (populated by the editor) is
# not required for headless `--quit` invocations of the smoke test.
const MainlineSession = preload("res://scripts/mainline/mainline_session.gd")
var _mainline_session: MainlineSession = null
# Batch A:成员留在 main.gd(函数搬走,mainline 域成员仍在 main)— 后续 batch B 接管组件时统一搬
var _mainline_page: String = "chapter_list"
var _mainline_commander_ids: Array = [""]
var _mainline_prepare_payload: Dictionary = {}
var _mainline_prepare_tab: String = "heroes"
var _selected_prepare_hero_id: String = ""
var _selected_prepare_equipment_id: String = ""
var _selected_prepare_shop_item_id: String = ""
var _selected_prepare_merc_unit_type: String = ""
var _selected_prepare_merc_stat: String = ""
var _mainline_shop_payload: Dictionary = {}
var _mainline_mercenary_payload: Dictionary = {}
var _mainline_auto_retry_pending: bool = false


func _setup_title_cover() -> void:
	if title_cover == null or not is_instance_valid(title_cover):
		return
	title_cover.mouse_filter = Control.MOUSE_FILTER_IGNORE
	title_cover.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	title_cover.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED

	var selected_path := _configured_title_cover_path()
	_apply_title_cover(selected_path)
	_setup_title_cover_dev_picker(selected_path)


func _configured_title_cover_path() -> String:
	var configured := str(ProjectSettings.get_setting(
		"battleblitz/title_cover/default_path",
		title_cover_default_path
	))
	var env_path := OS.get_environment("BB_TITLE_COVER")
	if env_path != "":
		configured = env_path
	if title_cover_paths.has(configured):
		return configured
	return title_cover_default_path


func _setup_title_cover_dev_picker(selected_path: String) -> void:
	if title_cover_dev_picker == null or not is_instance_valid(title_cover_dev_picker):
		return
	title_cover_dev_picker.clear()
	for path in title_cover_paths:
		title_cover_dev_picker.add_item(path.get_file().get_basename())
		title_cover_dev_picker.set_item_metadata(title_cover_dev_picker.item_count - 1, path)
	var selected_index := title_cover_paths.find(selected_path)
	title_cover_dev_picker.selected = max(0, selected_index)
	title_cover_dev_picker.visible = _title_cover_dev_preview_enabled()
	if not title_cover_dev_picker.item_selected.is_connected(_on_title_cover_dev_selected):
		title_cover_dev_picker.item_selected.connect(_on_title_cover_dev_selected)


func _title_cover_dev_preview_enabled() -> bool:
	if OS.get_environment("BB_TITLE_COVER_DEV") == "1":
		return true
	for arg in OS.get_cmdline_user_args():
		if arg == "--title-cover-dev":
			return true
	return false


func _on_title_cover_dev_selected(index: int) -> void:
	if title_cover_dev_picker == null or not is_instance_valid(title_cover_dev_picker):
		return
	var path := str(title_cover_dev_picker.get_item_metadata(index))
	_apply_title_cover(path)


func _apply_title_cover(path: String) -> void:
	if title_cover == null or not is_instance_valid(title_cover):
		return
	var tex := _load_title_cover_texture(path)
	title_cover.texture = tex
	if tex == null:
		push_warning("Title cover failed to load: %s" % path)


func _load_title_cover_texture(path: String) -> Texture2D:
	var global_path := ProjectSettings.globalize_path(path)
	var file := FileAccess.open(global_path, FileAccess.READ)
	if file != null:
		var bytes := file.get_buffer(file.get_length())
		file.close()
		if bytes.size() >= 3 and bytes[0] == 0xff and bytes[1] == 0xd8 and bytes[2] == 0xff:
			var jpg := Image.new()
			var jpg_err := jpg.load_jpg_from_buffer(bytes)
			if jpg_err == OK and not jpg.is_empty():
				return ImageTexture.create_from_image(jpg)
	var img := Image.new()
	var err := img.load(global_path)
	if err == OK and not img.is_empty():
		return ImageTexture.create_from_image(img)
	var tex := load(path) as Texture2D
	if tex != null:
		return tex
	return null


func _ready() -> void:
	# Try to restore the last player_name from disk.
	var saved: Variant = UserSettings.get_value("settings.v1.player_name", "")
	if typeof(saved) == TYPE_STRING and (saved as String) != "":
		_user_name = saved
	else:
		_user_name = "学妹喵" if _random_suffix() > 0.5 else "学长"
		UserSettings.set_value("settings.v1.player_name", _user_name)

	# === Phase 2: instantiate mainline session (currently a pass-through
	# to the legacy _active_mainline_id / _mainline_battle_game_id fields;
	# a later phase will move those fields into the session object proper).
	_mainline_session = MainlineSession.new()
	_mainline_session.restore_from_settings()

	# === GBA 火纹风主题注入(V2 第 1+2 轮:主菜单 + HUD 4 角) ===
	_apply_gba_theme()
	_setup_title_cover()

	_show_view("menu")
	mainline_button.pressed.connect(_on_mainline_pressed)
	lobby_button.pressed.connect(_on_lobby_pressed)
	# P1:主菜单"按号加入"按钮接 — 接受数字房间号 → join_game
	if join_by_code_button != null and is_instance_valid(join_by_code_button):
		join_by_code_button.pressed.connect(_on_join_by_code_pressed)
	# Enter 键在输入框中直接触发
	if join_by_code_input != null and is_instance_valid(join_by_code_input):
		join_by_code_input.text_submitted.connect(_on_join_by_code_submitted)
	if editor_button != null and is_instance_valid(editor_button):
		editor_button.pressed.connect(_on_editor_pressed)
	if saves_button != null and is_instance_valid(saves_button):
		saves_button.pressed.connect(_on_saves_pressed)
	# CreateFormPanel(自由模式)按钮
	# T:96 Mainline — ml_* connects 全部搬到 mainline_controller._ready(节点在组件里)
	# T:3 联机大厅 —— 全部子控件信号已搬到 lobby_controller._ready()
	settings_button.pressed.connect(_on_settings_open_pressed)
	exit_button.pressed.connect(_on_exit_pressed)
	# T:#16 — InProgressButton 接线(主菜单"▶ 进行中"按钮)
	if in_progress_button != null and is_instance_valid(in_progress_button):
		in_progress_button.pressed.connect(_on_in_progress_pressed)
	if resume_button != null and is_instance_valid(resume_button):
		resume_button.pressed.connect(_on_resume_pressed)
	# P2: saves_controller.gd 组件接线(跨域引用 + 回调绑定)
	if saves_view != null and is_instance_valid(saves_view):
		saves_view._main = self
	# T:#16 in_progress_controller.gd 组件接线
	if in_progress_view != null and is_instance_valid(in_progress_view):
		in_progress_view._main = self
	# P2: mainline_controller.gd 组件接线
	if mainline_view != null and is_instance_valid(mainline_view):
		mainline_view._main = self
	# P2: lobby_controller.gd 组件接线(大厅节点/状态/信号全部自管,这里只注入 _main)
	if lobby_view != null and is_instance_valid(lobby_view):
		lobby_view._main = self
	# P2: editor_controller.gd 组件接线(注入共享 helper + 跨域信号)
	if editor_view != null and is_instance_valid(editor_view):
		editor_view.unit_label_fn = Callable(self, "_unit_type_cn")
		if not editor_view.back_requested.is_connected(_on_editor_back_requested):
			editor_view.back_requested.connect(_on_editor_back_requested)
		if not editor_view.map_saved.is_connected(Callable(lobby_view, "_upsert_editor_map_as_lobby_preset")):
			editor_view.map_saved.connect(Callable(lobby_view, "_upsert_editor_map_as_lobby_preset"))
	# T:5 主菜单 load 时尝试匹配存档
	_check_resume_session()
	# T:8 启动时应用上次的字号偏好
	var saved_fs: int = int(UserSettings.get_value("settings.v1.font_size", 14))
	if saved_fs != 14:
		_apply_font_size(saved_fs)
	# M6.3 静音设置 — 启动时按偏好设
	var saved_mute: bool = bool(UserSettings.get_value("settings.v1.muted", false))
	if AudioManager != null:
		AudioManager.set_muted(saved_mute)
	end_turn_button.pressed.connect(_on_end_turn_pressed)
	reconnect_button.pressed.connect(_on_reconnect_pressed)
	# 2026-08-09:Connecting 面板「放弃,返回主菜单」按钮
	if connecting_abort_btn != null and is_instance_valid(connecting_abort_btn):
		connecting_abort_btn.pressed.connect(_on_connecting_abort_pressed)
	war_report_button.pressed.connect(_on_war_report_pressed)
	war_report_close_btn.pressed.connect(_on_war_report_close_pressed)

	# V2 第 4 轮:行动气泡 5 按钮
	for btn in [move_btn, attack_btn, skill_btn, wait_btn, claim_btn]:
		if btn != null and is_instance_valid(btn):
			MenuTheme.apply_button_theme(btn, 16)
	move_btn.pressed.connect(_on_move_pressed)
	attack_btn.pressed.connect(_on_attack_pressed)
	skill_btn.pressed.connect(_on_skill_pressed)
	wait_btn.pressed.connect(_on_wait_pressed)
	claim_btn.pressed.connect(_on_claim_pressed)
	if cancel_btn != null and is_instance_valid(cancel_btn):
		cancel_btn.pressed.connect(_on_cancel_pressed)
	if attack_confirm_btn != null and is_instance_valid(attack_confirm_btn):
		attack_confirm_btn.pressed.connect(_on_attack_confirm_pressed)
	if attack_cancel_btn != null and is_instance_valid(attack_cancel_btn):
		attack_cancel_btn.pressed.connect(_on_attack_cancel_pressed)
	# 通用 ConfirmDialog 信号接线 — 必须 null/instance_valid 守护,$ConfirmDialog
	# 是顶层节点,但若 godot 编辑器临时缺失也能跑通。
	if confirm_yes_btn != null and is_instance_valid(confirm_yes_btn):
		confirm_yes_btn.pressed.connect(_on_confirm_yes_pressed)
	if confirm_no_btn != null and is_instance_valid(confirm_no_btn):
		confirm_no_btn.pressed.connect(_on_confirm_no_pressed)
	# V2 第 6 轮:设置 + 暂停面板
	settings_close_btn.pressed.connect(_on_settings_close_pressed)
	settings_apply_btn.pressed.connect(_on_settings_apply_pressed)
	settings_cancel_btn.pressed.connect(_on_settings_cancel_pressed)
	# T:93 — Settings 按钮 (font × 3, color × 4, theme picker × 1)
	if settings_font_small_btn != null and is_instance_valid(settings_font_small_btn):
		settings_font_small_btn.pressed.connect(_on_font_small_pressed)
	if settings_font_med_btn != null and is_instance_valid(settings_font_med_btn):
		settings_font_med_btn.pressed.connect(_on_font_med_pressed)
	if settings_font_big_btn != null and is_instance_valid(settings_font_big_btn):
		settings_font_big_btn.pressed.connect(_on_font_big_pressed)
	if settings_red_btn != null and is_instance_valid(settings_red_btn):
		settings_red_btn.pressed.connect(_on_red_color_pressed)
	if settings_blue_btn != null and is_instance_valid(settings_blue_btn):
		settings_blue_btn.pressed.connect(_on_blue_color_pressed)
	if settings_green_btn != null and is_instance_valid(settings_green_btn):
		settings_green_btn.pressed.connect(_on_green_color_pressed)
	if settings_yellow_btn != null and is_instance_valid(settings_yellow_btn):
		settings_yellow_btn.pressed.connect(_on_yellow_color_pressed)
	if settings_theme_dropdown != null and is_instance_valid(settings_theme_dropdown):
		# 填充 3 主题(web CSS 主题)
		settings_theme_dropdown.add_item("深绿像素", 0)
		settings_theme_dropdown.add_item("金属银", 1)
		settings_theme_dropdown.add_item("极简明亮", 2)
		settings_theme_dropdown.item_selected.connect(_on_theme_dropdown_item_selected)
	# P1:静音 toggle 按钮接通 — 用 toggled 信号单向同步到 AudioManager
	if settings_mute_btn != null and is_instance_valid(settings_mute_btn):
		settings_mute_btn.toggled.connect(_on_mute_toggled)
		# 启动时按 UserSettings 里的 muted 状态同步按钮视觉
		var init_mute: bool = bool(UserSettings.get_value("settings.v1.muted", false))
		settings_mute_btn.button_pressed = init_mute
	pause_resume_btn.pressed.connect(_on_pause_resume_pressed)
	pause_settings_btn.pressed.connect(_on_pause_settings_pressed)
	pause_main_menu_btn.pressed.connect(_on_pause_main_menu_pressed)
	# P0:暂停面板"中断退出"按钮 — capture_suspend(主动存中断)
	if pause_suspend_btn != null and is_instance_valid(pause_suspend_btn):
		pause_suspend_btn.pressed.connect(_on_pause_suspend_pressed)
	pause_quit_btn.pressed.connect(_on_pause_quit_pressed)
	# V2 第 7 轮:对话 + 教程 + 战斗结算
	tutorial_got_it_btn.pressed.connect(_on_tutorial_got_it_pressed)
	battle_detail_btn.pressed.connect(_on_battle_detail_pressed)
	if battle_mainline_next_btn != null and is_instance_valid(battle_mainline_next_btn):
		battle_mainline_next_btn.pressed.connect(Callable(mainline_view, "_on_mainline_next_battle_pressed"))
	if battle_back_lobby_btn != null and is_instance_valid(battle_back_lobby_btn):
		battle_back_lobby_btn.pressed.connect(_on_battle_back_lobby_pressed)
	battle_back_menu_btn.pressed.connect(_on_battle_back_menu_pressed)
	# T:4 招募 modal — CloseBtn
	if recruit_close_btn != null and is_instance_valid(recruit_close_btn):
		recruit_close_btn.pressed.connect(_on_recruit_close_pressed)

	# Wire NetworkClient → GameState. The autoload `GameState._ready`
	# does this too, but routing through main makes the dependency
	# explicit and lets us log it.
	if not NetworkClient.ws_message_received.is_connected(_on_raw_ws_message):
		NetworkClient.ws_message_received.connect(_on_raw_ws_message)
	if not GameState.state_updated.is_connected(_on_state_updated):
		GameState.state_updated.connect(_on_state_updated)
	# GameState autoload already binds its own event-delta handler
	# that dispatches typed signals (log_received / unit_moved / ...).
	# We just react to the high-level ones for the HUD.
	# Subscribe to the typed signals GameState emits.
	if not GameState.log_received.is_connected(_on_log_received):
		GameState.log_received.connect(_on_log_received)
	if not GameState.unit_moved.is_connected(_on_unit_moved):
		GameState.unit_moved.connect(_on_unit_moved)
	if not GameState.unit_attacked.is_connected(_on_unit_attacked):
		GameState.unit_attacked.connect(_on_unit_attacked)
	if not GameState.unit_killed.is_connected(_on_unit_killed):
		GameState.unit_killed.connect(_on_unit_killed)
	if not GameState.unit_recruited.is_connected(_on_unit_recruited):
		GameState.unit_recruited.connect(_on_unit_recruited)
	if not GameState.turn_ended.is_connected(_on_turn_ended):
		GameState.turn_ended.connect(_on_turn_ended)
	if not GameState.match_ended.is_connected(_on_match_ended):
		GameState.match_ended.connect(_on_match_ended)
	if not GameState.ai_thinking.is_connected(_on_ai_thinking):
		GameState.ai_thinking.connect(_on_ai_thinking)

	# M4.10:Board 单位点击 → _show_action_bubble + 可达范围显示
	if board != null and is_instance_valid(board) \
			and not board.unit_clicked.is_connected(_on_board_unit_clicked):
		board.unit_clicked.connect(_on_board_unit_clicked)
	# M4.1:Board tile 点击 → 移动模式落子
	if board != null and is_instance_valid(board) \
			and not board.tile_clicked.is_connected(_on_board_tile_clicked):
		board.tile_clicked.connect(_on_board_tile_clicked)
	# 2026-08-09:棋盘地图真正加载完成后进入光标模式。
	# _show_view("game") 里 deferred 的 _enter_board_focus 常因棋盘还没加载
	# (WS 快照未到,map_size == 0)提前 return,之后无人重试 → board_focused
	# 永远 false,光标不画、方向键/摇杆无效。这里在 load_map 完成后补一次。
	if board != null and is_instance_valid(board) \
			and not board.map_loaded.is_connected(_on_board_map_loaded):
		board.map_loaded.connect(_on_board_map_loaded)

	# NetworkClient status
	NetworkClient.ws_connected.connect(func():
		_update_status("已连接到服务器")
		connecting_label.text = "已连接,等待战场同步..."
	)
	NetworkClient.ws_disconnected.connect(func(reason):
		_update_status("连接断开: %s" % reason)
	)
	NetworkClient.api_response.connect(func(method, path, body, code):
		# Lobby and mainline flows use explicit callbacks. Keep this legacy
		# auto chain scoped so POST /mainlines/{id}/start cannot enter GameView
		# before the mainline callback has stored game_id/player_id.
		if _entry_flow == "free" and method == "POST" and path == "/games" and (code == 200 or code == 201):
			_on_create_game_response(body)
		elif _entry_flow == "free" and method == "POST" and path.begins_with("/games/") and path.ends_with("/join") and (code == 200 or code == 201):
			_on_join_game_response(body)
		elif _entry_flow == "free" and method == "POST" and path.begins_with("/games/") and path.ends_with("/start") and (code == 200 or code == 201):
			_on_start_game_response(body)
		elif method == "GET" and path.ends_with("/state") and code == 200:
			# M_WS_REFRESH:server WS 只在 connect 时推 1 次 state.snapshot,
			# 后续只推 event.delta。粒度事件后我们主动拉一次 /state(防抖 200ms 合并),
			# 把响应喂回 GameState → emit units_changed → board 自动 FLIP 单位位置。
			_on_state_poll_response(body)
	)

	# P1:Reparent SettingsPanel to root so 主菜单 SettingsButton 可直接打开它
	# (SettingsPanel 默认挂在 GameView/HUD 下,主菜单时 GameView 不可见)。
	# reparent() 保留节点对象,@onready 引用继续有效。
	if settings_panel != null and is_instance_valid(settings_panel) \
			and settings_panel.get_parent() != self:
		settings_panel.reparent(self)
		settings_panel.visible = false

	# ----- Dev hook: BB_AUTO_PLAY=1 or --auto-play opens the lobby
	# session immediately. Used by tools/ws_e2e.gd and headless smoke runs
	# to validate the WS pipeline end-to-end without manual clicks.
	if _dev_auto_play_enabled():
		_update_status("测试自动流程: 自动开始对局")
		call_deferred("_on_lobby_pressed")
	# BB_AUTO_QUIT=N — quit after N seconds (for headless e2e runs).
	# 注意:_maybe_screenshot_menu() 必须在 BB_AUTO_QUIT await 之前,因为
	# 它调 get_tree().quit() 会提早结束 _ready。
	var quit_sec_str: String = OS.get_environment("BB_AUTO_QUIT")
	var quit_sec: float = 0.0
	if quit_sec_str != "":
		quit_sec = float(quit_sec_str)
	# UI Redesign Round 1/2 临时:env-gated screenshots(Round 完后清理)
	if OS.get_environment("BB_SCREENSHOT_MENU") != "":
		await _maybe_screenshot_menu()
	elif OS.get_environment("BB_SCREENSHOT_VIEWS") != "":
		await _maybe_screenshot_views()
	if quit_sec > 0.0:
		await get_tree().create_timer(quit_sec).timeout
		_update_status("测试自动流程结束,退出")
		get_tree().quit(0)
	# V2 第 6 轮:游戏视图下启用菜单"设置"按钮(直接打开 SettingsPanel)
	if settings_button != null and is_instance_valid(settings_button):
		settings_button.disabled = false
		# settings_button.pressed 已经连接到 _on_settings_pressed (M3 stub)
		# 替换:让它在游戏视图下打开 SettingsPanel,菜单视图下保留原提示
	if settings_button.pressed.is_connected(_on_settings_pressed):
		settings_button.pressed.disconnect(_on_settings_pressed)
	if settings_button.pressed.is_connected(_on_settings_open_pressed):
		settings_button.pressed.disconnect(_on_settings_open_pressed)
	settings_button.pressed.connect(_on_settings_open_pressed)
	# P1:主菜单 HelpButton → 玩法说明浮层
	if help_button != null and is_instance_valid(help_button):
		if help_button.pressed.is_connected(_on_help_pressed):
			help_button.pressed.disconnect(_on_help_pressed)
		help_button.pressed.connect(_on_help_pressed)
	# TSCN-FIX:强制覆盖,确保 GameView 不吞棋盘点击(以防 tscn mouse_filter=2 没生效)
	if game_view != null and is_instance_valid(game_view):
		game_view.mouse_filter = Control.MOUSE_FILTER_IGNORE
	# (诊断 HUD 改到 _show_view("game") 里调,确保切到 game view 时创建并可见)


# ============================================================
# View transitions
# ============================================================

enum View { MENU, CONNECTING, GAME }

# P2+: 当前是哪个 view? 兜底 reset 用作关闭条件(避免误清游戏内 transform)。
var _current_view: String = "menu"

# P2+: 帧末兜底 reset 调度锁,避免 call_deferred 重入。
var _viewport_safety_reset_pending: bool = false

# P2+: 兜底 reset 自愈计数器。若一帧 reset 不够(回调又把相机开了),再排下一帧。
# 8 次硬上限防止 tween/WS 重连风暴拖死引擎。
var _post_frame_retry_count: int = 0

# UI Redesign Round 1 临时:BB_SCREENSHOT_MENU=1 时 _ready 后截 menu view。
# Round 1 完成后会清理。
func _maybe_screenshot_menu() -> void:
	if OS.get_environment("BB_SCREENSHOT_MENU") == "":
		return
	await get_tree().create_timer(0.8).timeout
	_show_view("menu")
	await get_tree().create_timer(0.6).timeout
	var vp: Viewport = get_viewport()
	var img: Image = vp.get_texture().get_image() if vp != null else null
	if img == null or img.is_empty():
		print("[MENU_SS] image empty")
	else:
		var path: String = ProjectSettings.globalize_path("user://diag_view_menu.png")
		img.save_png(path)
		print("[MENU_SS] saved " + path + " (%dx%d)" % [img.get_width(), img.get_height()])
	get_tree().quit()


# UI Redesign Round 2 临时:BB_SCREENSHOT_VIEWS=menu,connecting,lobby,saves,mainline,editor
# 依次截图各 view(Round 完成后清理)
func _maybe_screenshot_views() -> void:
	if OS.get_environment("BB_SCREENSHOT_VIEWS") == "":
		return
	var names_str: String = OS.get_environment("BB_SCREENSHOT_VIEWS")
	var names: PackedStringArray = names_str.split(",")
	await get_tree().create_timer(0.8).timeout
	for view_name in names:
		_show_view(view_name)
		await get_tree().create_timer(0.6).timeout
		var vp: Viewport = get_viewport()
		var img: Image = vp.get_texture().get_image() if vp != null else null
		if img == null or img.is_empty():
			print("[VIEWS] %s: empty" % view_name)
			continue
		var path: String = ProjectSettings.globalize_path("user://diag_view_%s.png" % view_name)
		img.save_png(path)
		print("[VIEWS] %s -> %s" % [view_name, path])
	get_tree().quit()


func _show_view(name: String) -> void:
	menu_panel.visible = (name == "menu")
	connecting_panel.visible = (name == "connecting")
	game_view.visible = (name == "game")
	lobby_view.visible = (name == "lobby")
	mainline_view.visible = (name == "mainline")
	saves_view.visible = (name == "saves")
	editor_view.visible = (name == "editor")
	in_progress_view.visible = (name == "in_progress")
	# HUD 是 CanvasLayer,不受 GameView.visible 控制 — 手动同步显隐
	if name == "game":
		_show_hud()
	else:
		_hide_hud()
	# lobby 视图默认进二层菜单(创建/加入选择)
	if name == "lobby":
		lobby_view.show_choose()
	# 最强保险:切到 game view 时强制 GameView 不吞棋盘点击
	# (tscn mouse_filter=2 + _ready 兜底都没生效时,这里再设一次绝对生效)
	if name == "game" and game_view != null and is_instance_valid(game_view):
		game_view.mouse_filter = Control.MOUSE_FILTER_IGNORE
	# game view 时启动状态轮询(每 1s GET /state 追 AI 行动)
	if name == "game":
		_start_state_polling()
		# 棋盘以外的侧翼必须属于战斗 HUD，而不是透出窗口默认灰色。
		# 使用不抢地图视觉权重的深海军蓝，和金边面板保持同一套色阶。
		if backdrop != null and is_instance_valid(backdrop):
			backdrop.color = Color(0.018, 0.035, 0.055, 1.0)
	else:
		_stop_state_polling()
		# 恢复主题背景色
		if backdrop != null and is_instance_valid(backdrop):
			backdrop.color = MenuTheme.C_BG_DEEP
	# P2 修复:BoardCamera 在 apply_metrics() 时 enabled=true,会接管整个 viewport 的
	# canvas_transform(zoom + 平移),连带 Menu 等 Control 一起缩放平移。切到不显示棋盘的
	# view 必须禁用它并归位 canvas,否则从 game / 地图编辑器返回主菜单后整屏右偏放大。
	# P2+:
	# 1) 不只是 disable,还得先 reset zoom/position + 关闭 position_smoothing,
	#    否则 CO 技震动 / 拖拽缩放留下的 tween 残值会让主菜单被相机拖飞一帧。
	# 2) 不只处理"已知"的两个 BoardCamera,扫整棵 scene tree 把所有 Camera2D
	#    一并 neutralize,防未来的 Editor/UI 相机漏网。
	# 3) 把 HUD/Backdrop 的 CanvasLayer.transform 也归零,确保 CanvasLayer 不残留
	#    任何外层 transform。
	# 4) 帧末再 reset 一次(call_deferred),接住同帧内 tween/回调又把相机设回去的
	#    残余路径(典型:state poll 回调里 board._on_state_updated 触发刷新)。
	if name != "game" and name != "editor":
		_reset_board_cameras()
	_current_view = name
	# 2026-08-09:view 切换时同步 InputState.board_focused + grab focus
	# menu/lobby/mainline 等"非棋盘 view":board_focused = false,默认 focus 到该 view 的主按钮
	# game view:board_focused = true,光标可被方向键 / 摇杆控制
	# 切到 game 前先解掉 board_focused(防上一次没关),然后 view 真正显示后再 enter
	if name == "game":
		# 切到棋盘:延迟到下一帧再 enter,等 Board 加载完
		call_deferred("_enter_board_focus")
	else:
		InputState.board_focused = false
		InputState.cursor_cell = Vector2i(-1, -1)
		# 给当前 view 一个默认 focus 目标
		_focus_default_for_view(name)


func _reset_board_cameras() -> void:
	# (1) 把"已知"BoardCamera 拉回中性态再 disable。
	_disable_board_camera(board, true)
	if editor_view != null and is_instance_valid(editor_view):
		_disable_board_camera(editor_view.get_node_or_null("EditorBoard"), true)
	# (2) 兜底:扫整棵树把所有 Camera2D 归位(防未知相机漏网)。
	_disable_all_cameras_in_tree(get_tree().root, true)
	# (3) viewport.canvas_transform 直接置 IDENTITY。已 disabled 的 Camera2D
	#	下一帧不会被纳入相机计算,这一行可以持久。
	var vp := get_viewport()
	if vp != null:
		vp.canvas_transform = Transform2D.IDENTITY
	# (4) 兜底:CanvasLayer.transform 也归零。HUD / BattleBackdrop 一般不写
	#	这一项,但万一一并清掉。
	if hud_layer != null and is_instance_valid(hud_layer):
		hud_layer.transform = Transform2D.IDENTITY
	if battle_backdrop_layer != null and is_instance_valid(battle_backdrop_layer):
		battle_backdrop_layer.transform = Transform2D.IDENTITY
	# (5) 帧末兜底 reset:同帧内任何残留 tween/回调又把 Camera2D 属性改回去,
	#	call_deferred 在帧末再跑一次,接住它。新一轮切 view 时把 retry 数归零。
	if is_inside_tree() and not _viewport_safety_reset_pending:
		_post_frame_retry_count = 0
		_viewport_safety_reset_pending = true
		call_deferred("_post_frame_viewport_reset")


# === 2026-08-09:键盘 + 手柄 view 切换的 focus 管理 ===
# game view:进入 board_focus(光标模式);其它 view:grab focus 到该 view 主按钮
func _enter_board_focus() -> void:
	if board == null or not is_instance_valid(board):
		return
	if board.map_size.x <= 0 or board.map_size.y <= 0:
		return
	# 光标初始化:第一个我方单位 > 地图中心 > (0,0)
	var initial_cell: Vector2i = _find_cursor_initial_cell()
	InputState.cursor_cell = initial_cell
	InputState.board_focused = true
	# 释放所有 Control 的 focus(否则 ui_accept 会被某个 Button 抢走)
	get_viewport().gui_release_focus()


func _safe_int(value: Variant, fallback: int = -1) -> int:
	if value == null:
		return fallback
	match typeof(value):
		TYPE_INT:
			return value
		TYPE_FLOAT:
			return int(value)
		TYPE_STRING:
			var text := (value as String).strip_edges()
			if text.is_valid_int():
				return text.to_int()
	return fallback


func _find_local_hq_cell() -> Vector2i:
	if board == null or not is_instance_valid(board) or board.map_size.x <= 0:
		return Vector2i(-1, -1)
	if GameState == null:
		return Vector2i(-1, -1)
	var my_pid: int = _safe_int(GameState.local_player_id, -1)
	for t in GameState.tiles:
		if typeof(t) != TYPE_DICTIONARY:
			continue
		var terrain: String = str(t.get("terrain", ""))
		var subtype: String = str(t.get("subtype", ""))
		if _safe_int(t.get("owner_id", null), -1) == my_pid \
				and (terrain == "castle" or subtype == "castle_throne"):
			return Vector2i(_safe_int(t.get("x", 0), 0), _safe_int(t.get("y", 0), 0))
	return Vector2i(-1, -1)


func _find_cursor_initial_cell() -> Vector2i:
	if board == null or not is_instance_valid(board) or board.map_size.x <= 0:
		return Vector2i(0, 0)
	var hq_cell := _find_local_hq_cell()
	if hq_cell.x >= 0:
		return hq_cell
	# 找第一个当前玩家的单位
	if GameState != null:
		var my_pid: int = int(GameState.local_player_id)
		for u in GameState.latest_snapshot.get("units", []):
			if typeof(u) != TYPE_DICTIONARY:
				continue
			if _safe_int(u.get("player_id", null), -1) == my_pid:
				return Vector2i(_safe_int(u.get("x", 0), 0), _safe_int(u.get("y", 0), 0))
	# 退而求其次:地图中心
	return Vector2i(board.map_size.x / 2, board.map_size.y / 2)


# 2026-08-09:board.load_map 完成后由 map_loaded 信号触发。
# 覆盖"新建/重连/续档"里 _show_view("game") 的 deferred _enter_board_focus
# 因棋盘未加载而空跑的场景;已在焦点中则不动(避免打断进行中的移动/攻击模式)。
func _on_board_map_loaded(_width: int, _height: int, _biome: String) -> void:
	if _current_view != "game":
		return
	if InputState == null:
		return
	if InputState.board_focused:
		return
	_enter_board_focus()


func _focus_default_for_view(view_name: String) -> void:
	# 给常见 view 落默认 focus(避免玩家连按 Tab 才能进菜单)
	match view_name:
		"menu":
			# 主菜单:ResumeButton 优先(如有),否则 MainlineButton
			if resume_button != null and is_instance_valid(resume_button) and resume_button.is_visible_in_tree() and not resume_button.disabled:
				resume_button.grab_focus()
			elif mainline_button != null and is_instance_valid(mainline_button):
				mainline_button.grab_focus()
		"lobby":
			# lobby 内部子控件太多,留给 lobby_controller 自己管
			pass
		"mainline":
			# mainline 内部子控件也很多,留给 mainline_controller
			pass
		"editor":
			# editor 内部有自己的 focus
			pass
		"saves":
			pass
		"in_progress":
			pass
		"connecting":
			# 2026-08-09:Connecting 面板默认 focus 落「放弃」按钮
			# 玩家进入这个面板通常已经卡住,默认要"退出"的概率高于"再试一次"。
			# 没新增 AbortButton 时,fallback 到 ReconnectButton(老行为)。
			if connecting_abort_btn != null and is_instance_valid(connecting_abort_btn):
				connecting_abort_btn.grab_focus()
			elif reconnect_button != null and is_instance_valid(reconnect_button):
				reconnect_button.grab_focus()
		_:
			pass


# P2+: 帧末兜底 reset。同帧内 _tween_killed_too_early / state_updated 回调可能
# 又设了 camera 属性,call_deferred 排在帧末再跑一次,确保下一帧渲染时 canvas_transform
# 绝对是干净的。仅当当前不在 game/editor view 才生效。
# 持续自愈:reset 完再扫一次,若仍有相机被重新 enable(典型:tween 残值、state_updated
# 回调、WS reconnect handler),再 call_deferred 一次,直到整棵树清净为止。
func _post_frame_viewport_reset() -> void:
	_viewport_safety_reset_pending = false
	if not is_inside_tree():
		return
	if _current_view == "game" or _current_view == "editor":
		return
	_disable_board_camera(board, true)
	if editor_view != null and is_instance_valid(editor_view):
		_disable_board_camera(editor_view.get_node_or_null("EditorBoard"), true)
	_disable_all_cameras_in_tree(get_tree().root, true)
	var vp := get_viewport()
	if vp != null:
		vp.canvas_transform = Transform2D.IDENTITY
	if hud_layer != null and is_instance_valid(hud_layer):
		hud_layer.transform = Transform2D.IDENTITY
	if battle_backdrop_layer != null and is_instance_valid(battle_backdrop_layer):
		battle_backdrop_layer.transform = Transform2D.IDENTITY
	# 自愈检查:仍有一个 enabled 的 Camera2D(viewport canvas_transform 不为 IDENTITY 的话
	# 多半是这个原因),再 call_deferred 一次。设上限 8 防极端死循环。
	if _any_camera_still_enabled() and _post_frame_retry_count < 8:
		_post_frame_retry_count += 1
		_viewport_safety_reset_pending = true
		call_deferred("_post_frame_viewport_reset")


func _any_camera_still_enabled() -> bool:
	# 已知两个 BoardCamera + 整棵树兜底扫描
	if board != null and is_instance_valid(board):
		var cam := board.get_node_or_null("BoardCamera")
		if cam != null and is_instance_valid(cam) and (cam is Camera2D) and (cam as Camera2D).enabled:
			return true
	if editor_view != null and is_instance_valid(editor_view):
		var eboard = editor_view.get_node_or_null("EditorBoard")
		if eboard != null and is_instance_valid(eboard):
			var ecam := eboard.get_node_or_null("BoardCamera")
			if ecam != null and is_instance_valid(ecam) and (ecam is Camera2D) and (ecam as Camera2D).enabled:
				return true
	# 兜底:整棵树里只要还有 enabled 的 Camera2D 也算
	var cams: Array = get_tree().root.find_children("*", "Camera2D", true, false)
	for cam in cams:
		if cam != null and is_instance_valid(cam) and (cam is Camera2D) and (cam as Camera2D).enabled:
			return true
	return false


func _disable_board_camera(b: Node, neutralize: bool = true) -> void:
	if b == null or not is_instance_valid(b):
		return
	var cam := b.get_node_or_null("BoardCamera")
	_neutralize_camera(cam, neutralize)


func _disable_all_cameras_in_tree(root: Node, neutralize: bool = true) -> void:
	if root == null or not is_instance_valid(root):
		return
	# find_children 找出所有 Camera2D 子节点(不会包含 disabled 节点外的特例)
	var cams := root.find_children("*", "Camera2D", true, false)
	for cam in cams:
		_neutralize_camera(cam, neutralize)


# P2+: 单个 Camera2D 的"拉回中性 + 关 smoothing + disable"。
# neutralize=false 时只 disable,不动 zoom/position(正常切回游戏视图时用)。
func _neutralize_camera(cam: Node, neutralize: bool) -> void:
	if cam == null or not is_instance_valid(cam) or not (cam is Camera2D):
		return
	if neutralize:
		# 关 smoothing:tween 残值会让位置/zoom "漂一帧",瞬切 UI 必须瞬时归零。
		cam.set("position_smoothing_enabled", false)
		cam.set("zoom_smoothing_enabled", false)
		cam.set("zoom", Vector2(1.0, 1.0))
		cam.set("position", Vector2.ZERO)
	cam.set("enabled", false)


# HUD (CanvasLayer) 显隐控制 — CanvasLayer 不受父 Control.visible 影响
func _show_hud() -> void:
	if battle_backdrop_layer != null and is_instance_valid(battle_backdrop_layer):
		battle_backdrop_layer.visible = true
	if hud_layer != null and is_instance_valid(hud_layer):
		hud_layer.visible = true


func _hide_hud() -> void:
	if battle_backdrop_layer != null and is_instance_valid(battle_backdrop_layer):
		battle_backdrop_layer.visible = false
	if hud_layer != null and is_instance_valid(hud_layer):
		hud_layer.visible = false


func _start_state_polling() -> void:
	if _state_poll_timer != null and is_instance_valid(_state_poll_timer):
		return
	_state_poll_timer = Timer.new()
	_state_poll_timer.wait_time = _STATE_POLL_INTERVAL_SEC
	_state_poll_timer.autostart = true
	_state_poll_timer.timeout.connect(_poll_state_now)
	add_child(_state_poll_timer)


func _stop_state_polling() -> void:
	if _state_poll_timer != null and is_instance_valid(_state_poll_timer):
		_state_poll_timer.queue_free()
	_state_poll_timer = null


func _poll_state_now() -> void:
	if _game_over:
		return
	if _game_id <= 0:
		return
	if game_view == null or not is_instance_valid(game_view) or not game_view.visible:
		return
	NetworkClient.get_game_state(_game_id)


func _on_create_game_response(body: Dictionary) -> void:
	# The create-game response is the game summary; pull id.
	_game_id = int(body.get("id", 0))
	if _game_id <= 0:
		# Some FastAPI shapes put the id under `game_id`.
		_game_id = int(body.get("game_id", 0))
	if _game_id <= 0:
		_update_status("创建失败: 响应缺少对局编号")
		_show_view("menu")
		return
	UserSettings.set_value("session.v1.last_game_id", _game_id)
	connecting_label.text = "对局 #%d 已创建,加入中..." % _game_id
	# 2) Join as the local player.
	if _entry_flow == "free":
		NetworkClient.join_game(_game_id, _user_name, "red")
	else:
		NetworkClient.join_game(_game_id, _user_name, "red", lobby_view.selected_join_team(), lobby_view.selected_join_role())


func _on_join_game_response(body: Dictionary) -> void:
	# The join response returns the Player dict directly
	# (top-level `id` is the player_id). Some FastAPI shapes wrap
	# under `player` or include `player_id` — check both.
	_player_id = int(body.get("id", 0))
	if _player_id <= 0:
		_player_id = int(body.get("player_id", 0))
	if _player_id <= 0:
		var p: Variant = body.get("player", {})
		if p is Dictionary:
			_player_id = int(p.get("id", 0))
	if _player_id <= 0:
		_update_status("加入失败: 响应缺少玩家编号")
		_show_view("menu")
		return
	GameState.local_player_id = _player_id
	UserSettings.set_value("session.v1.last_player_id", _player_id)
	if _entry_flow != "free":
		_show_view("lobby")
		lobby_view.enter_room_after_join()
		return
	connecting_label.text = "已加入(玩家 #%d),添加电脑对手中..." % _player_id
	# 3) Add an AI opponent. M3 will let the user pick kind/personality.
	NetworkClient.request(
		"POST",
		"/games/%d/add-ai" % _game_id,
		{
			"difficulty": "normal",
			"agent_kind": "rules",
			"personality": "balanced",
		},
		Callable()
	)
	# 4) Start immediately (auto-start also fires once MIN_PLAYERS
	# join; manual start is a no-op in that case but harmless).
	NetworkClient.start_game(_game_id)


func _on_start_game_response(_body: Dictionary) -> void:
	# 5) 切到 game 视图并打开 WebSocket 流(与 _on_lobby_start_response 一致:
	# 先切视图,首帧 state.snapshot 到达后 _on_state_updated 刷新棋盘/HUD)。
	# 之前漏了 _show_view("game"),导致快捷 AI 对局 start 后视图停在 connecting,
	# 一直显示"已连接,等待 state.snapshot..."进不去游戏。
	_show_view("game")
	NetworkClient.connect_to_game(_game_id, _player_id)
	NetworkClient.get_game_state(_game_id, Callable(self, "_on_state_poll_response"))
	# T:97 — 快捷 AI 对局首次进入 game view 自动弹 tutorial
	_trigger_first_tutorial()


func _start_dev_ai_game() -> void:
	_entry_flow = "dev_ai"
	_show_view("connecting")
	if connecting_label != null and is_instance_valid(connecting_label):
		connecting_label.text = "测试流程: 正在创建电脑对局..."
	NetworkClient.create_game(
		"%s dev room" % _user_name,
		"balanced_2p_15",
		"grass",
		"rout",
		"",
		"",
		{},
		Callable(self, "_on_dev_ai_created")
	)


func _on_dev_ai_created(body: Variant, code: int = 0) -> void:
	if code < 200 or code >= 300 or not (body is Dictionary):
		_update_status("测试电脑对局创建失败")
		return
	_game_id = int(body.get("id", body.get("game_id", 0)))
	UserSettings.set_value("session.v1.last_game_id", _game_id)
	NetworkClient.join_game(_game_id, _user_name, "red", "", "", Callable(self, "_on_dev_ai_joined"))


func _on_dev_ai_joined(body: Variant, code: int = 0) -> void:
	if code < 200 or code >= 300 or not (body is Dictionary):
		_update_status("测试电脑对局加入失败")
		return
	_player_id = int(body.get("id", body.get("player_id", 0)))
	if _player_id <= 0:
		var p: Variant = body.get("player", {})
		if p is Dictionary:
			_player_id = int(p.get("id", 0))
	GameState.local_player_id = _player_id
	UserSettings.set_value("session.v1.last_player_id", _player_id)
	NetworkClient.add_ai_player(_game_id, "normal", "rules", "balanced", Callable(self, "_on_dev_ai_added"))


func _on_dev_ai_added(_body: Variant, _code: int = 0) -> void:
	NetworkClient.start_game(_game_id, Callable(self, "_on_dev_ai_started"))


func _on_dev_ai_started(_body: Variant, _code: int = 0) -> void:
	_show_view("game")
	NetworkClient.connect_to_game(_game_id, _player_id)
	NetworkClient.get_game_state(_game_id, Callable(self, "_on_state_poll_response"))


# T:97 — 触发 tutorial 弹窗(只在第一次进 game view 时)
func _trigger_first_tutorial() -> void:
	if _tutorial_shown:
		return
	_tutorial_shown = true
	# 等 snapshot 进来再弹,延后一点点让玩家先看到棋盘
	call_deferred("_show_first_tutorial_deferred")


func _show_first_tutorial_deferred() -> void:
	# 5 条核心玩法提示(参考 web app.js 5671)
	if tutorial_text != null and is_instance_valid(tutorial_text):
		tutorial_text.bbcode_enabled = true
		tutorial_text.text = (
			"[color=#f0c75e][b]📖 BattleBlitz · 玩法说明[/b][/color]\n\n"
			+ "1. [color=#a8c9ff]点击己方单位[/color] → 浮出 5 按钮气泡\n"
			+ "2. [color=#5fa8e8]蓝色高亮[/color]是可移动的范围\n"
			+ "3. [color=#e85a6a]红色高亮[/color]是攻击的范围\n"
			+ "4. 选单位后点 [b]移动[/b] / [b]攻击[/b] 按钮 → 在范围点格子\n"
			+ "5. 行动完 → 点右上 [b]结束回合 →[/b] 进入 AI 回合\n\n"
			+ "[color=#a89878]💡 提示:占领己方城堡/兵营可召唤新单位[/color]"
		)
	show_tutorial()


func _on_reconnect_pressed() -> void:
	if _game_id > 0 and _player_id > 0:
		NetworkClient.connect_to_game(_game_id, _player_id)


# 2026-08-09:Connecting 面板的"放弃重连,返回主菜单"按钮 handler。
# 关键:disconnect WS,重置 _game_id / _player_id / _resume_* 状态,
# 切回 menu。否则下次进游戏会从上次的中断存档续上,不是玩家预期。
func _on_connecting_abort_pressed() -> void:
	# 1) 关 WS
	if NetworkClient != null and NetworkClient.has_method("ws_close"):
		NetworkClient.ws_close()
	# 2) 切回 menu
	_show_view("menu")
	# 3) 状态清理(主菜单要的"白纸"状态)
	_game_id = 0
	_player_id = 0
	_resume_game_id = 0
	_resume_player_id = 0
	_resume_kind = ""
	# 4) 顺手清 connecting label 文字(下次进别留尾巴)
	if connecting_label != null and is_instance_valid(connecting_label):
		connecting_label.text = "已断开,正在返回主菜单..."
	_update_status("已放弃重连,返回主菜单")


func _on_exit_pressed() -> void:
	get_tree().quit()


# T:5 单槽存档 / Resume — 主菜单可见按钮 + 一键 rejoin
# P0 强化:优先检查中断存档(WebUI 行为对齐),再 fallback 到 playing/waiting game。
func _check_resume_session() -> void:
	if _user_name == "" or _user_name == "Player":
		return
	# 先并行拉两路:list_saves(看是否有 suspend)+ list_games(找 in-flight game)
	NetworkClient.list_saves(_user_name, Callable(self, "_on_list_saves_for_resume"))
	NetworkClient.list_games(Callable(self, "_on_list_games_for_resume"), _user_name)


# 优先选 suspend 中断存档;有则按钮"▶ 继续中断战斗" → 走 load_suspend 分支
func _on_list_saves_for_resume(body: Variant, _code: int = 0) -> void:
	if not (body is Dictionary):
		return
	var suspend: Variant = body.get("suspend", null)
	if not (suspend is Dictionary):
		return
	var game_id := int(suspend.get("game_id", 0))
	if game_id <= 0:
		return
	_resume_game_id = game_id
	_resume_player_id = 0  # suspend 走 rejoin_by_name,不需 pid
	_resume_kind = "suspend"
	if resume_button != null and is_instance_valid(resume_button):
		resume_button.text = "▶ 继续中断战斗"
		resume_button.visible = true


func _on_list_games_for_resume(body: Variant, _code: int = 0) -> void:
	# /games?user_name= 返回该用户可继续的 GameSummaryOut 列表,不带 players。
	# 若 _resume_game_id 已被 suspend 分支设置,则不覆盖。
	if _resume_game_id > 0:
		return
	var games: Array = (body as Array) if body is Array else []
	var last_game_id: int = int(UserSettings.get_value("session.v1.last_game_id", 0))
	var last_player_id: int = int(UserSettings.get_value("session.v1.last_player_id", 0))
	for g in games:
		if not g is Dictionary: continue
		var status := str(g.get("status", ""))
		if status != "playing" and status != "waiting":
			continue
		_resume_game_id = int(g.get("id", 0))
		_resume_player_id = last_player_id if _resume_game_id == last_game_id else 0
		if resume_button != null and is_instance_valid(resume_button):
			resume_button.text = "继续对局 #%d" % _resume_game_id
			resume_button.visible = _resume_game_id > 0
		_resume_kind = "game"
		return


# P0:resume 按钮按下 → 根据 kind 分流到 game(直接 rejoin)或 suspend(load_suspend 后再 rejoin)
func _on_resume_pressed() -> void:
	if _resume_game_id <= 0:
		return
	_show_view("connecting")
	connecting_label.text = "正在重连对局 #%d..." % _resume_game_id
	if _resume_kind == "suspend":
		# suspend 流程:先调 load_suspend 告知服务端把中断游戏变成当前游戏 → 再 rejoin
		NetworkClient.load_suspend(_user_name, Callable(self, "_on_resume_suspend_load_response"))
		return
	if _resume_player_id > 0:
		NetworkClient.rejoin_game_by_player_id(_resume_game_id, _resume_player_id,
			Callable(self, "_on_resume_rejoin_response"))
	else:
		NetworkClient.rejoin_game_by_name(_resume_game_id, _user_name,
			Callable(self, "_on_resume_rejoin_response"))


func _on_resume_suspend_load_response(body: Variant, code: int) -> void:
	# load_suspend 成功后,body 含 game_id + mainline_id
	if code < 200 or code >= 300 or not (body is Dictionary):
		_update_status("恢复中断存档失败")
		return
	var game_id := int(body.get("game_id", 0))
	if game_id <= 0:
		_update_status("中断存档没有可恢复对局")
		return
	_resume_game_id = game_id  # 用服务端回的新 game_id 覆盖
	NetworkClient.rejoin_game_by_name(game_id, _user_name,
		Callable(self, "_on_resume_rejoin_response"))


func _on_resume_rejoin_response(body: Variant, _code: int = 0) -> void:
	if not (body is Dictionary):
		_update_status("重连失败: 响应异常")
		_show_view("menu")
		return
	var p_dict: Dictionary = body.get("player", body)
	var resp_game_id: int = int(body.get("game_id", _resume_game_id))
	var resp_player_id: int = int(p_dict.get("id", _player_id))
	if resp_game_id > 0:
		_game_id = resp_game_id
	if resp_player_id > 0:
		_player_id = resp_player_id
		GameState.local_player_id = _player_id
		UserSettings.set_value("session.v1.last_player_id", _player_id)
	if _game_id > 0:
		UserSettings.set_value("session.v1.last_game_id", _game_id)
	_show_view("game")
	NetworkClient.connect_to_game(_game_id, _player_id)
	NetworkClient.get_game_state(_game_id, Callable(self, "_on_state_poll_response"))


func _on_saves_pressed() -> void:
	_show_view("saves")
	if saves_view != null and is_instance_valid(saves_view):
		saves_view.open()


# T:#16 — in_progress 视图入口(主菜单"▶ 进行中"按钮)
func _on_in_progress_pressed() -> void:
	_show_view("in_progress")
	if in_progress_view != null and is_instance_valid(in_progress_view):
		in_progress_view.open()


# P1:主菜单"按号加入"按钮接 — 解析输入房间号 → 入大厅选队入场
func _on_join_by_code_submitted(_text: String) -> void:
	_on_join_by_code_pressed()


func _on_join_by_code_pressed() -> void:
	if join_by_code_input == null or not is_instance_valid(join_by_code_input):
		return
	var raw: String = join_by_code_input.text.strip_edges()
	if raw == "":
		_update_status("请输入房间号")
		return
	# 接受纯数字 game_id
	var gid: int = -1
	if raw.is_valid_int():
		gid = raw.to_int()
	else:
		_update_status("房间号必须是数字")
		return
	if gid <= 0 or gid > 99999:
		_update_status("房间号超出范围")
		return
	# 切到 connecting 视图,展示等待 toast,然后 join_game
	_show_view("connecting")
	_update_status("按号加入: #%d" % gid)
	# 默认以玩家身份入席(role=player);玩家偏好色由 join_game 内部派生。
	NetworkClient.join_game(
		gid,
		_user_name,
		"",  # color — server 派生
		"",  # team — player 自选 team 在 game view 内调整
		"player",
		Callable(self, "_on_join_game_response")
	)


# ============================================================
# Game state → HUD
# ============================================================

# P2:THREAT 攻击威胁区 — 算所有敌方单位攻击范围,标记 (橙) 在 board 高亮层
# 客户端 UI 镜像,服务端仍权威;玩家据此判断"我脚下"有没有敌人能打到我。
func _compute_threat_tiles() -> Array:
	var threat: Array = []
	if GameState == null or board == null or board.map_size.x <= 0:
		return threat
	var size: int = board.map_size.x
	var players: Array = GameState.players if GameState else []
	for p in players:
		if not p is Dictionary:
			continue
		if bool(p.get("is_spectator", false)):
			continue
		var pid: int = int(p.get("id", -1))
		if pid == _player_id:
			continue  # skip self
		var units: Array = (p.get("units", []) as Array)
		for u in units:
			if not u is Dictionary:
				continue
			var ux: int = int(u.get("x", 0))
			var uy: int = int(u.get("y", 0))
			var rng: int = int(u.get("attack_range", 1))
			var min_r: int = int(u.get("min_attack_range", 0))
			threat.append_array(MapLogic.attack_range_tiles(Vector2i(ux, uy), rng, min_r, size))
	return threat


func _show_threat_tiles() -> void:
	if board == null:
		return
	var tiles: Array = _compute_threat_tiles()
	# 去重 + 转 Vector2i
	var seen: Dictionary = {}
	var uniq: Array = []
	for t in tiles:
		var v := Vector2i(int(t.x), int(t.y))
		if seen.has(v):
			continue
		seen[v] = true
		uniq.append(v)
	# 用 red attack marks(视觉上标"敌可打我")复用 — 简化,后续可做独立橙色 Mode.THREAT
	board.show_attack_marks(uniq)


func _on_state_updated(_snapshot: Dictionary) -> void:
	var _sum: Dictionary = GameState.game_summary if GameState != null else {}
	if String(_sum.get("status", "")) == "finished":
		_handle_finished_snapshot(_sum)
		return
	# Render a fresh frame from GameState.
	_repaint_board_from_state()
	_refresh_hud_from_state()

	# 8a: 回合开始(仅本地玩家),DialogManager 去重避免 state poll 反复触发
	if GameState != null and not DialogManager.is_playing() and _player_id > 0:
		var _sum_turn := int(GameState.game_summary.get("turn_number", 0))
		var _sum_pid: Variant = GameState.current_player_id
		if _sum_turn > 0 and _sum_pid != null and int(_sum_pid) == _player_id:
			if DialogManager.record_turn_shown(_game_id, _sum_turn, int(_sum_pid)):
				DialogManager.show_dialog({
					"speaker": "",
					"text": "— 第 %d 回合,你的部队开始行动。" % _sum_turn,
					"type": "narration",
				})

	var summary: Dictionary = GameState.game_summary if GameState != null else {}
	var battle_config: Dictionary = (summary.get("battle_config", {}) as Dictionary)
	if battle_config != null and battle_config.has("audio"):
		var audio_cfg: Dictionary = battle_config.get("audio", {})
		var bgm: Dictionary = audio_cfg.get("bgm", {})
		if AudioManager != null and bgm != null and bgm.has("track_id"):
			AudioManager.apply_battle_bgm(bgm)


# GET /state 响应处理:REST 响应直接是 GameStateOut,跟 WS payload.game 形状一致,
# 直接喂 GameState.ingest_snapshot。事件→响应→ingest→units_changed→board FLIP。
func _on_state_poll_response(body: Variant, _code: int = 0) -> void:
	if not body is Dictionary:
		return
	if GameState == null:
		return
	GameState.ingest_snapshot(body)



func _repaint_board_from_state() -> void:
	if board == null or not is_instance_valid(board):
		return
	# Re-build the map by emitting a fake load_map call from snapshot.
	# The board consumes the `width/height/biome/initial_units/layout`
	# subset, plus our custom tile_lookup. We adapt the snapshot shape
	# into what Board.load_map expects.
	var pseudo: Dictionary = _snapshot_to_pseudo_map()
	if pseudo.is_empty():
		return
	# Avoid thrash: only repaint if the game id actually changed
	# (state.snapshot updates on every WS event; the layout rarely does).
	if int(pseudo.get("__id", 0)) != _game_id:
		return
	var board_signature := "%s:%sx%s:%s" % [
		str(pseudo.get("__id", 0)),
		str(pseudo.get("width", 0)),
		str(pseudo.get("height", 0)),
		str(pseudo.get("layout", [])),
	]
	if board_signature != _loaded_board_signature:
		board.load_map(pseudo)
		_loaded_board_signature = board_signature
	else:
		board.initial_units = pseudo.get("initial_units", [])
		board._on_units_changed(board.initial_units)
	# M4.16+:重建建筑阵营旗(从最新 GameState.tiles + owner_id)。
	# 必须放在 load_map 之后 — board.tile_lookup 已建好,flag 需要 metrics。
	if not GameState.tiles.is_empty():
		board.rebuild_flags(GameState.tiles)


func _snapshot_to_pseudo_map() -> Dictionary:
	# Convert GameStateOut `tiles` (list of TileOut dicts) into the
	# compact layout row-string format that MapLoader expects.
	if GameState.tiles.is_empty():
		return {}
	var w: int = 0
	var h: int = 0
	for t in GameState.tiles:
		w = max(w, int(t.get("x", 0)) + 1)
		h = max(h, int(t.get("y", 0)) + 1)
	if w <= 0 or h <= 0:
		return {}
	var rows: Array = []
	for y in h:
		var row: String = ""
		for x in w:
			var terrain: String = "P"
			var subtype: String = ""
			for t in GameState.tiles:
				if int(t.get("x", -1)) == x and int(t.get("y", -1)) == y:
					var terrain_v: Variant = t.get("terrain", "P")
					var subtype_v: Variant = t.get("subtype", "")
					terrain = str(terrain_v) if terrain_v != null else "P"
					subtype = str(subtype_v) if subtype_v != null else ""
					break
			if subtype != "":
				row += terrain[0] if terrain.length() > 0 else "C"
				row += subtype[0] if subtype.length() > 0 else "f"
			else:
				# Map short terrain names back to single-char codes.
				match terrain:
					"plain": row += "P"
					"forest": row += "F"
					"mountain": row += "M"
					"snow_peak": row += "S"
					"river": row += "R"
					"castle": row += "C"
					"village": row += "v"
					"barracks": row += "b"
					"road": row += "r"
					"gate": row += "g"
					"bridge": row += "j"
					_: row += "P"
		rows.append(row)
	# Reconstruct initial_units from PlayerOut.units.
	var initial_units: Array = []
	for p in GameState.players:
		if not p is Dictionary:
			continue
		var color: String = str(p.get("color", "red"))
		for u in p.get("units", []):
			if not u is Dictionary:
				continue
			var unit_copy: Dictionary = u.duplicate()
			unit_copy["x"] = int(unit_copy.get("x", 0))
			unit_copy["y"] = int(unit_copy.get("y", 0))
			unit_copy["type"] = str(unit_copy.get("unit_type", unit_copy.get("type", "swordsman")))
			unit_copy["color"] = color
			unit_copy["level"] = int(unit_copy.get("level", 1))
			initial_units.append(unit_copy)
	return {
		"__id": _game_id,
		"size": {"width": w, "height": h},
		"width": w,
		"height": h,
		"biome": GameState.game_summary.get("map_biome", "grass"),
		"layout": rows,
		"initial_units": initial_units,
	}


func _refresh_hud_from_state() -> void:
	var summary: Dictionary = GameState.game_summary
	turn_badge_label.text = "回合 %d" % int(summary.get("turn_number", 1))
	var phase_text: String = str(summary.get("phase", "player"))
	match phase_text:
		"player": phase_badge_label.text = "🟢 你的阶段"
		"ai": phase_badge_label.text = "🤖 电脑阶段"
		"animating": phase_badge_label.text = "✨ 动画中"
		"spectator": phase_badge_label.text = "👀 观战"
		_: phase_badge_label.text = "阶段:%s" % phase_text

	# Current player name
	var cur_pid = GameState.current_player_id
	if cur_pid != null:
		var cp: Dictionary = GameState.get_player(cur_pid)
		var name: String = str(cp.get("user_name", "—"))
		current_player_label.text = "→ %s" % name
	else:
		current_player_label.text = "→ —"

	# End-turn button:玩家阶段(自己回合)或观战者阶段(自己观战回合)时启用。
	# 观战者无单位、不能操作,但必须手动"确认(继续)"推进自己的观战回合,
	# 否则对局卡在观战者回合(后端 end_turn 接受 is_spectator,turns.py:167)。
	# cur_pid 在 _reset_game_state_for_main_menu 后是 null,需守护。
	var my_turn: bool = cur_pid != null and int(cur_pid) == _player_id
	if my_turn and phase_text == "spectator":
		end_turn_button.disabled = false
		end_turn_button.text = "✅ 确认(继续)"
	elif my_turn and phase_text == "player":
		end_turn_button.disabled = false
		end_turn_button.text = "⏭ 结束回合"
	else:
		end_turn_button.disabled = true
		end_turn_button.text = "⏭ 结束回合"

	# Local player's gold
	var me: Dictionary = GameState.get_player(_player_id)
	gold_label.text = "💰 %d" % int(me.get("gold", 0))

	# CO meter (use my seat's meter if present, else 0).
	var my_co: Dictionary = {}
	for c in GameState.co_states:
		if c is Dictionary and int(c.get("player_id", -1)) == _player_id:
			my_co = c
			break
	var meter: int = int(my_co.get("meter", 0))
	var threshold: int = max(1, int(my_co.get("threshold", 100)))
	# CO 能量进度只在 InfoPanel/CommanderCOBar 里更新;BottomLeft/COBar 已删除

	# Players list (right column)
	_rewrite_players_list()
	# V2 第 3 轮补丁:左上 InfoPanel 当前指挥官
	_refresh_commander_section()
	# M5.1 顶部 CORoster — 全玩家 CO meter + 发动按钮
	_refresh_co_roster()


# M5.1 CO Roster — 顶部全玩家头像 + 名字 + meter + 发动按钮
# 每个 co_state 一行:Panel(VBox:头像色块 + Label + ProgressBar + Button)
# 按钮只在 can_fire=true(且是自己)时显示;is_power_active 时显示 "⚡ 生效中"
func _refresh_co_roster() -> void:
	if co_roster == null or not is_instance_valid(co_roster):
		return
	# 清空旧 children(每次刷新重建)
	for child in co_roster.get_children():
		child.queue_free()
	var states: Array = GameState.co_states if GameState != null else []
	if states.is_empty():
		return
	var compact := states.size() > 2
	var density := _hud_density_scale()
	for c in states:
		if not (c is Dictionary):
			continue
		var pid: int = int(c.get("player_id", -1))
		var color_v: Variant = c.get("color", "")
		var color_name: String = "" if color_v == null else str(color_v)
		var commander_v: Variant = c.get("commander_id", null)
		var commander_id: String = "" if commander_v == null else str(commander_v)
		var stars: int = int(c.get("stars_earned_total", 0))
		var threshold: int = max(1, int(c.get("threshold", 100)))
		var power_cost: int = int(c.get("power_cost", 6))
		var pct: float = clamp(float(stars) / float(threshold) * 100.0, 0.0, 100.0)
		var is_active: bool = bool(c.get("is_power_active", false))
		var can_fire: bool = bool(c.get("can_fire", false))
		var is_local: bool = pid == _player_id
		# Panel 容器(单行:HBox)
		var row := Panel.new()
		row.custom_minimum_size = Vector2(115 if compact else 238, 38)
		row.mouse_filter = Control.MOUSE_FILTER_PASS
		co_roster.add_child(row)
		var row_inner := HBoxContainer.new()
		row_inner.anchor_right = 1.0
		row_inner.anchor_bottom = 1.0
		row_inner.offset_left = 4.0
		row_inner.offset_top = 2.0
		row_inner.offset_right = -4.0
		row_inner.offset_bottom = -2.0
		row_inner.add_theme_constant_override("separation", 4)
		row.add_child(row_inner)
		# 1) 阵营色条。窄色条比大色块更接近顶部对阵栏的视觉语言。
		var swatch := ColorRect.new()
		swatch.custom_minimum_size = Vector2(6, 24)
		swatch.color = Config.player_color(color_name)
		row_inner.add_child(swatch)
		# 2) 正式界面禁止暴露 RED:<null> 之类内部值。
		var lbl := Label.new()
		var side_name := _team_cn(color_name)
		if side_name == "":
			side_name = "阵营"
		var commander_name_text := _commander_cn(commander_id) if commander_id != "" else "未任命"
		lbl.text = side_name if compact else "%s · %s" % [side_name, commander_name_text]
		lbl.custom_minimum_size = Vector2(40 if compact else 92, 0)
		lbl.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		lbl.add_theme_font_size_override("font_size", roundi((12 if compact else 14) * density))
		row_inner.add_child(lbl)
		# 3) ProgressBar(meter / threshold)
		var bar := ProgressBar.new()
		bar.custom_minimum_size = Vector2(30 if compact else 48, 14)
		bar.value = pct
		bar.show_percentage = false
		bar.tooltip_text = "指挥官士气星: %d / %d(放 power 消耗 %d 颗)" % [stars, threshold, power_cost]
		var bar_bg := StyleBoxFlat.new()
		bar_bg.bg_color = Color(0.025, 0.05, 0.075, 0.96)
		bar_bg.border_color = Color(0.31, 0.27, 0.18, 1.0)
		bar_bg.set_border_width_all(1)
		bar_bg.set_corner_radius_all(3)
		var bar_fill := StyleBoxFlat.new()
		bar_fill.bg_color = Config.player_color(color_name).lightened(0.12)
		bar_fill.set_corner_radius_all(3)
		bar.add_theme_stylebox_override("background", bar_bg)
		bar.add_theme_stylebox_override("fill", bar_fill)
		row_inner.add_child(bar)
		# 4) 状态标签 / 发动按钮
		if is_active:
			var active_lbl := Label.new()
			active_lbl.text = "⚡ 生效中"
			active_lbl.add_theme_color_override("font_color", Color(0.96, 0.78, 0.18))
			active_lbl.add_theme_font_size_override("font_size", roundi(11 * density))
			row_inner.add_child(active_lbl)
		elif can_fire and is_local:
			var btn := Button.new()
			btn.text = "发动"
			btn.custom_minimum_size = Vector2(36, 20)
			btn.add_theme_font_size_override("font_size", roundi(10 * density))
			btn.tooltip_text = "激活指挥官技(消耗 %d 颗士气星)" % power_cost
			# 用 Callable.bind 把 pid 绑到 pressed 信号
			btn.pressed.connect(_on_co_power_pressed.bind(pid))
			row_inner.add_child(btn)
		else:
			var meter_lbl := Label.new()
			meter_lbl.text = "%d/%d" % [stars, threshold]
			meter_lbl.add_theme_font_size_override("font_size", roundi((10 if compact else 12) * density))
			row_inner.add_child(meter_lbl)


func _rewrite_players_list() -> void:
	players_list.clear()
	for p in GameState.players:
		if not p is Dictionary:
			continue
		var name: String = str(p.get("user_name", "?"))
		# P1#7 观战者:灰色卡,显示"观战中-无单位"(观战者无单位无金币)
		var is_spec: bool = bool(p.get("is_spectator", false))
		var ended_early: String = " ⏳" if p.get("has_ended_turn", false) else ""
		if is_spec:
			players_list.append_text("[color=#9aa0a6]👀 %s · 观战中-无单位%s[/color]\n" % [name, ended_early])
			continue
		var color: String = str(p.get("color", "?"))
		var units: int = (p.get("units", []) as Array).size()
		var gold: int = int(p.get("gold", 0))
		var alive: String = "✅" if p.get("is_alive", true) else "💀"
		var ended: String = " ⏳" if p.get("has_ended_turn", false) else ""
		players_list.append_text("[color=%s]%s %s[/color] — %d 兵 · 💰%d%s\n" % [
			_color_name_to_godot(color), alive, name, units, gold, ended
		])


func _color_name_to_godot(c: String) -> String:
	return CnLabels.color_name_to_godot(c)


func _color_emoji(c: String) -> String:
	return CnLabels.color_emoji(c)


# ============================================================
# Event-delta handlers
# ============================================================

func _on_log_received(action: Dictionary) -> void:
	var desc: String = str(action.get("description", ""))
	if desc == "":
		desc = str(action.get("event_type", ""))
	if desc == "":
		return
	var importance: String = str(action.get("importance", "normal"))
	var color: String = "white"
	match importance:
		"critical": color = "#e85a6a"
		"important": color = "#f0c75e"
	action_log.append_text("[color=%s]%s[/color]\n" % [color, desc])


func _refresh_commander_section() -> void:
	# 当前轮到谁的回合 → 显示该玩家的指挥官信息 + CO 能量条
	if commander_name == null or not is_instance_valid(commander_name):
		return
	var cur_pid = GameState.current_player_id
	if cur_pid == null:
		commander_name.text = "—"
		if commander_co_bar != null and is_instance_valid(commander_co_bar):
			commander_co_bar.value = 0.0
		return
	var cp: Dictionary = GameState.get_player(cur_pid)
	var name: String = str(cp.get("user_name", "—"))
	var color: String = str(cp.get("color", "?"))
	var units: int = (cp.get("units", []) as Array).size()
	var gold: int = int(cp.get("gold", 0))
	var color_godot: String = _color_name_to_godot(color)
	var emoji: String = "👤"
	match color:
		"red": emoji = "🔴"
		"blue": emoji = "🔵"
		"green": emoji = "🟢"
		"yellow": emoji = "🟡"
	commander_name.text = "%s [color=%s][b]%s[/b][/color]  ·  %d 单位 · 💰 %d" % [
		emoji, color_godot, name, units, gold
	]
	# CO 进度 from co_states array
	# 新机制:进度 = stars_earned_total / threshold(累计士气星 / 累计上限)
	var stars: int = 0
	var threshold: int = 100
	var power_cost: int = 6
	for c in GameState.co_states:
		if c is Dictionary and int(c.get("player_id", -1)) == (int(cur_pid) if cur_pid != null else -1):
			stars = int(c.get("stars_earned_total", 0))
			threshold = max(1, int(c.get("threshold", 100)))
			power_cost = int(c.get("power_cost", 6))
			break
	var pct: float = float(stars) / float(threshold) * 100.0
	if commander_co_bar != null and is_instance_valid(commander_co_bar):
		commander_co_bar.value = pct
		commander_co_bar.tooltip_text = "指挥官士气星: %d / %d(消耗 %d 颗放 power)" % [stars, threshold, power_cost]


# M4.13/14 行动后气泡:单位 move/attack 后弹出可再行动气泡
# T:95 — 鼠标 hover 时用 MapLogic.pathfind 算路径并渲染
var _path_hover_last: Vector2i = Vector2i(-1, -1)
var _move_preview_path: Array = []
var _move_preview_target: Vector2i = Vector2i(-1, -1)


func _clear_move_preview_path() -> void:
	_move_preview_path = []
	_move_preview_target = Vector2i(-1, -1)


func _update_path_dots_on_hover(global_pos: Vector2) -> void:
	if board == null or _move_reachable_set.is_empty():
		return
	var layer: TileMapLayer = board.get_node_or_null("GroundLayer")
	if layer == null:
		return
	var local: Vector2 = layer.to_local(global_pos)
	var target_cell: Vector2i = layer.local_to_map(local)
	_update_path_dots_at_cell(target_cell)


# 2026-08-09:键盘/手柄光标模式 — 玩家光标移到哪格,这里直接收 cell。
# 复用 _update_path_dots_on_hover 内部的 path 计算 + dots 渲染逻辑,
# 把"screen pos → cell"这一步在外面完成。
func _update_path_dots_at_cell(target_cell: Vector2i) -> void:
	if board == null or _move_reachable_set.is_empty():
		return
	if target_cell == _path_hover_last:
		return
	_path_hover_last = target_cell
	if not _move_reachable_set.has(target_cell):
		_clear_move_preview_path()
		# hover 离开 reachable → 保留 outline(没 path)
		if board != null:
			board.clear_selection_marks()
			var reach_tiles: Array = _move_reachable_set.keys()
			if reach_tiles.size() > 0:
				board.show_path_marks([], reach_tiles)
		return
	var src_unit: Dictionary = GameState.get_unit(_move_mode_unit_id) if GameState != null else {}
	if src_unit.is_empty():
		return
	var src_cell := Vector2i(int(src_unit.get("x", 0)), int(src_unit.get("y", 0)))
	var size_v: int = 15
	if board != null and board.map_size.x > 0:
		size_v = board.map_size.x
	var occupancy := _movement_occupancy_for_unit(src_unit)
	var blocked: Dictionary = occupancy.get("blocked", {})
	var no_end: Dictionary = occupancy.get("no_end", {})
	var owners: Dictionary = {}
	if board.tile_lookup != null:
		for k in board.tile_lookup.keys():
			var t: Dictionary = board.tile_lookup[k]
			var owner_v = t.get("owner_id", null)
			owners[k] = int(owner_v) if owner_v != null else 0
	var terrain: Dictionary = {}
	if board.tile_lookup != null:
		for k in board.tile_lookup.keys():
			var t: Dictionary = board.tile_lookup[k]
			terrain[k] = str(t.get("terrain", "plain"))
	var mov: int = int(src_unit.get("mov", int(src_unit.get("move_points", 5))))
	var path: Array = MapLogic.pathfind(
		src_cell, target_cell, terrain, owners, mov, _player_id, blocked, no_end, size_v
	)
	_move_preview_path = path.duplicate()
	_move_preview_target = target_cell
	var path_dots: Array = []
	for p in path:
		if Vector2i(p) != src_cell:
			path_dots.append(Vector2i(p))
	var reach_tiles: Array = _move_reachable_set.keys()
	board.show_path_marks(path_dots, reach_tiles)


func _show_post_action_bubble(unit_id: int, action_name: String) -> void:
	if action_bubble == null or not is_instance_valid(action_bubble):
		return
	_selected_unit_id = unit_id
	var ud: Dictionary = GameState.get_unit(unit_id) if GameState != null else {}
	if ud.is_empty():
		return
	var owner_pid: int = int(ud.get("player_id", int(ud.get("owner_id", -1))))
	if owner_pid != _player_id:
		return
	var cell := Vector2i(int(ud.get("x", 0)), int(ud.get("y", 0)))
	var marker_pos: Vector2 = board.tile_to_viewport(cell) if board != null else Vector2.ZERO
	var context := _ACTION_CONTEXT_POST_MOVE if action_name == "移动" else _ACTION_CONTEXT_POST_ACTION
	_show_action_bubble(unit_id, marker_pos, context)
	_update_status("已%s,请选择后续指令" % ("移动" if action_name == "移动" else "行动"))


func _on_unit_moved(unit_id: int, from_x: int, from_y: int, to_x: int, to_y: int, _cost: int) -> void:
	if action_log != null and is_instance_valid(action_log):
		action_log.append_text("[color=#5fa8e8]🚶 #%d 移动 (%d,%d) → (%d,%d) 耗能 %d[/color]\n" % [
			unit_id, from_x, from_y, to_x, to_y, _cost
		])
	_update_status("单位 #%d 已移动到 (%d,%d)" % [unit_id, to_x, to_y])
	_move_mode_unit_id = -1
	_move_reachable_set = {}
	_clear_move_preview_path()
	if board != null:
		board.clear_selection_marks()
	# M4.13:post-move bubble — 移动后若 can_move_after_action,
	# 弹气泡让玩家可选 "再次移动 / 攻击 / 待命"
	if unit_id != _player_id and _selected_unit_id != unit_id:
		return
	_show_post_action_bubble(unit_id, "移动")
	_schedule_board_refresh()


func _on_unit_attacked(attacker_id: int, target_id: int, damage: int, is_crit: bool, is_kill: bool, counter_damage: int) -> void:
	action_log.append_text("[color=#f0c75e]⚔ #%d → #%d: %d 伤害%s%s[/color]\n" % [
		attacker_id, target_id, damage,
		" (暴击!)" if is_crit else "",
		" (击杀)" if is_kill else "",
	])
	if board != null:
		var tgt: Dictionary = GameState.get_unit(target_id) if GameState != null else {}
		if not tgt.is_empty():
			var cell := Vector2i(int(tgt.get("x", 0)), int(tgt.get("y", 0)))
			var text: String = ("💥%d" % damage) if not is_crit else ("⚡%d" % damage)
			var color_hex: String = "#c9a14a" if is_crit else "#e85a6a"
			if is_kill:
				text = "💀%d" % damage
				color_hex = "#c63a3a"
			board.spawn_floating_text_at_cell(cell, text, color_hex, "damage")
	# M4.14+:反击伤害飘字 — 显示在攻击者位置,触发条件与服务端 actions.py:537 的 not is_kill 对齐
	if counter_damage > 0 and board != null:
		var atk: Dictionary = GameState.get_unit(attacker_id) if GameState != null else {}
		if not atk.is_empty():
			var acell := Vector2i(int(atk.get("x", 0)), int(atk.get("y", 0)))
			var is_counter_kill: bool = int(atk.get("hp", 1)) <= 0
			var atext: String = ("💀%d" % counter_damage) if is_counter_kill else ("↩%d" % counter_damage)
			var acolor: String = "#c63a3a" if is_counter_kill else "#e85a6a"
			board.spawn_floating_text_at_cell(acell, atext, acolor, "counter_damage")
	# M4.14:post-attack bubble — 若目标未死 + can_move_after_action 还能再行动
	if not is_kill:
		_show_post_action_bubble(attacker_id, "攻击")
	_schedule_board_refresh()


func _on_unit_killed(unit_id: int, _killer_id: int) -> void:
	action_log.append_text("[color=#e85a6a]💀 #%d 被击杀[/color]\n" % unit_id)
	if board != null:
		var u: Dictionary = GameState.get_unit(unit_id) if GameState != null else {}
		if not u.is_empty():
			var cell := Vector2i(int(u.get("x", 0)), int(u.get("y", 0)))
			board.spawn_floating_text_at_cell(cell, "💀击杀", "#c63a3a", "kill")
	_schedule_board_refresh()
	# 8b: 阵亡旁白(去重:每次 GameState 重新连接也算新 seq)
	_death_event_seq += 1
	if DialogManager.record_death_shown(_game_id, unit_id, _death_event_seq):
		var _u := GameState.get_unit(unit_id) if GameState != null else {}
		var _name := str(_u.get("display_cn", _u.get("unit_type", "单位"))) if not _u.is_empty() else "单位"
		DialogManager.show_dialog({
			"speaker": "",
			"text": "「%s」阵亡。" % _name,
			"type": "narration",
		})


# 200ms 防抖拉一次 GET /state。多个连续事件会被合并成一次 REST 调用,
# 避免 AI 回合里 N 个 event.delta 各拉一次。事件→响应回来→ingest→
# units_changed → board._on_units_changed 自动 FLIP 单位位置。
func _schedule_board_refresh() -> void:
	if _game_over:
		return
	if _board_refresh_pending:
		return
	_board_refresh_pending = true
	get_tree().create_timer(_BOARD_REFRESH_DEBOUNCE_SEC).timeout.connect(_do_board_refresh, CONNECT_ONE_SHOT)


func _do_board_refresh() -> void:
	_board_refresh_pending = false
	if _game_over:
		return
	if _game_id <= 0:
		return
	NetworkClient.get_game_state(_game_id)


func _on_unit_recruited(new_unit_id: int, unit_type: String, tile_x: int, tile_y: int, cost: int) -> void:
	if action_log != null and is_instance_valid(action_log):
		action_log.append_text("[color=#c9a14a]💰 招募 %s #%d @ (%d,%d) -%d[/color]\n" % [
			unit_type, new_unit_id, tile_x, tile_y, cost
		])
	_update_status("招募事件: %s #%d" % [unit_type, new_unit_id])
	if board != null:
		board.spawn_floating_text_at_cell(Vector2i(tile_x, tile_y), "+%s" % unit_type, "#c9a14a", "gold")
	_schedule_board_refresh()


# M5.1 CO Roster — 顶部全玩家头像 + 名字 + CO 能量条 + Power 按钮
# M5.3 CO Power 激活
func _on_co_power_pressed(pid: int) -> void:
	if _game_id <= 0:
		return
	# 鸢影·沉默领域:需要先选 5×5 中心,不立即 fire。
	var co_id: String = ""
	for co_entry in GameState.co_states:
		if co_entry is Dictionary and int(co_entry.get("player_id", -1)) == pid:
			co_id = String(co_entry.get("commander_id", "") or "")
			break
	if co_id == "yuanying":
		_enter_silence_pick_center_mode(pid)
		return
	# 8c: 可选 pre-action 对话(默认关闭,设置开关)
	if UserSettings.get_value("dialog.v1.co_power_confirm", false):
		await DialogManager.play([{
			"speaker": "",
			"text": "指挥官技即将发动,确认?",
			"type": "narration",
		}])
	NetworkClient.action_co_power(
		_game_id, pid,
		Vector2i(-1, -1),  # 无中心
		Callable(self, "_on_co_power_response"),
	)
	_update_status("⚡ 指挥官技激活中 (#%d)..." % pid)
	# 视觉反馈:屏幕中央大飘字 + 屏幕震动
	_play_co_power_fx()


# 鸢影·沉默领域:进入"选中心"模式,玩家点格子选 5×5 中心。
func _enter_silence_pick_center_mode(pid: int) -> void:
	_silence_pick_center_for_pid = pid
	_update_status("沉默领域:点选 5×5 中心(右键取消)")
	if board != null:
		board.highlight_silence_pick_mode(true)


# 鸢影·沉默领域:玩家点格子 → 设 center → fire。
func _handle_silence_center_pick(tile: Vector2i) -> void:
	var pid: int = _silence_pick_center_for_pid
	if pid <= 0:
		return
	if tile.x < 0 or tile.y < 0:
		return
	_silence_pick_center_for_pid = -1
	if board != null:
		board.highlight_silence_pick_mode(false)
	# 8c: 可选 pre-action 对话
	if UserSettings.get_value("dialog.v1.co_power_confirm", false):
		await DialogManager.play([{
			"speaker": "",
			"text": "沉默领域即将发动(中心 (%d, %d)),确认?" % [tile.x, tile.y],
			"type": "narration",
		}])
	NetworkClient.action_co_power(
		_game_id, pid,
		tile,
		Callable(self, "_on_co_power_response"),
	)
	_update_status("⚡ 沉默领域激活中 (中心 (%d, %d))..." % [tile.x, tile.y])
	_play_co_power_fx()


# 鸢影·沉默领域:右键 / ESC 取消。
func _cancel_silence_pick() -> void:
	if _silence_pick_center_for_pid <= 0:
		return
	_silence_pick_center_for_pid = -1
	if board != null:
		board.highlight_silence_pick_mode(false)
	_update_status("已取消沉默领域选择")


## 8c: CO power 响应 — 成功后播一句旁白
func _on_co_power_response(body: Variant, code: int) -> void:
	if code < 200 or code >= 300:
		_update_status("指挥官技失败 (HTTP %d)" % code)
		return
	if DialogManager.is_playing():
		return
	DialogManager.show_dialog({
		"speaker": "",
		"text": "⚡ 指挥官技已就绪。",
		"type": "narration",
	})


# M5.3 CO Power 视觉反馈:屏幕中央大飘字 + Camera2D 抖动 0.4s
func _play_co_power_fx() -> void:
	var viewport := get_viewport()
	if viewport == null:
		return
	# 1) 中央大飘字(用 hud_layer CanvasLayer,避免受 Camera2D 影响)
	if hud_layer != null and is_instance_valid(hud_layer):
		var lbl := Label.new()
		lbl.text = "⚡ 指挥官技已激活!"
		lbl.add_theme_color_override("font_color", Color(1.0, 0.86, 0.30))
		lbl.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.9))
		lbl.add_theme_constant_override("shadow_offset_x", 3)
		lbl.add_theme_constant_override("shadow_offset_y", 3)
		lbl.add_theme_font_size_override("font_size", 48)
		lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		lbl.mouse_filter = Control.MOUSE_FILTER_IGNORE
		# 中央位置
		var vp_size: Vector2 = viewport.get_visible_rect().size
		lbl.position = Vector2(vp_size.x * 0.5 - 200, vp_size.y * 0.4)
		lbl.size = Vector2(400, 64)
		hud_layer.add_child(lbl)
		# Tween:1.2s 内 alpha 1.0→0.0 + 向上飘 40px
		var t: Tween = create_tween()
		t.set_parallel(true)
		t.tween_property(lbl, "position:y", lbl.position.y - 40, 1.2).set_trans(Tween.TRANS_CUBIC)
		t.tween_property(lbl, "modulate:a", 0.0, 1.2).set_trans(Tween.TRANS_LINEAR)
		t.set_parallel(false)
		t.tween_callback(lbl.queue_free)
	# 2) Camera2D 抖动 0.4s
	var board_node: Node = get_node_or_null("GameView/Board")
	if board_node != null:
		var cam: Camera2D = board_node.get_node_or_null("BoardCamera") as Camera2D
		if cam != null:
			var orig_pos: Vector2 = cam.position
			var t2: Tween = create_tween()
			t2.set_loops(8)
			var seed_amp: float = 6.0
			t2.tween_property(cam, "position", orig_pos + Vector2(seed_amp, 0), 0.05)
			t2.tween_property(cam, "position", orig_pos + Vector2(-seed_amp, seed_amp), 0.05)
			t2.tween_property(cam, "position", orig_pos + Vector2(seed_amp, -seed_amp), 0.05)
			t2.tween_property(cam, "position", orig_pos, 0.05)


# M6.3 静音 toggle — Settings 上 toggle 按钮
func _on_toggle_mute_pressed() -> void:
	if AudioManager == null: return
	var muted: bool = AudioManager.toggle_muted()
	UserSettings.set_value("settings.v1.muted", muted)
	_update_status("静音: %s" % ("开" if muted else "关"))


# P1:SettingsPanel 里的 MuteBtn 用了 toggle_mode,toggled(toggled_on) signal
# 直连到 set_muted(单向),无需 toggle。
func _on_mute_toggled(toggled_on: bool) -> void:
	if AudioManager == null: return
	AudioManager.set_muted(toggled_on)
	UserSettings.set_value("settings.v1.muted", toggled_on)
	_update_status("静音: %s" % ("开" if toggled_on else "关"))


# M6.5 主题切换 — 三套主题:deep_gba / metal_silver / minimal_light
# P2 完整版:每套主题覆盖 backdrop / 面板色调 / 按钮色 / 文本色;
# 在 _apply_theme 里集中灌,运行期热切换无需重新打开视图。
const _THEMES := ["deep_gba", "metal_silver", "minimal_light"]


func _on_theme_change(theme_name: String) -> void:
	UserSettings.set_value("settings.v1.theme", theme_name)
	_apply_theme(theme_name)


func _apply_theme(theme_name: String) -> void:
	HudTheme.apply_theme(self, theme_name)


# M6.13 Help / 玩法说明 — 显示游戏规则静态指南
#
# 实现用 ColorRect 当背景(不是 Panel),因为 Panel 是 Control 容器,
# 没有 .color 属性 —— 用 Panel.color 会在第一次调用时 SCRIPT ERROR。
# (Found via headless button smoke test on 2026-08-09.)
var _help_panel: ColorRect = null


func show_help() -> void:
	if _help_panel == null:
		_help_panel = ColorRect.new()
		_help_panel.anchor_left = 0.5
		_help_panel.anchor_top = 0.5
		_help_panel.anchor_right = 0.5
		_help_panel.anchor_bottom = 0.5
		_help_panel.offset_left = -360.0
		_help_panel.offset_top = -240.0
		_help_panel.offset_right = 360.0
		_help_panel.offset_bottom = 240.0
		_help_panel.color = Color(0.06, 0.13, 0.10, 0.96)
		get_tree().root.add_child(_help_panel)
		# 内容容器(Panel 不会挡事件也不画背景,只用来 group)
		var content := Panel.new()
		content.anchor_right = 1.0
		content.anchor_bottom = 1.0
		_help_panel.add_child(content)
		var title := Label.new()
		title.text = "📖 玩 法 说 明"
		title.anchor_right = 1.0
		title.offset_top = 12.0
		title.offset_bottom = 44.0
		title.horizontal_alignment = 1
		title.add_theme_font_size_override("font_size", 22)
		title.add_theme_color_override("font_color", MenuTheme.C_GOLD)
		content.add_child(title)
		var body := RichTextLabel.new()
		body.bbcode_enabled = true
		body.anchor_right = 1.0
		body.anchor_bottom = 1.0
		body.offset_left = 24.0
		body.offset_top = 56.0
		body.offset_right = -24.0
		body.offset_bottom = -56.0
		body.text = (
			"[color=#f4e8c1][b]基础回合[/b][/color]\n"
			+ "1. 点己方单位 → 弹 5 个动作(移动/攻击/技能/待命/占领)\n"
			+ "2. 蓝框为可移动范围;红框为攻击范围\n"
			+ "3. 单位移动后可能继续攻击、施法或待命\n\n"
			+ "[color=#f4e8c1][b]伤害公式(简化)[/b][/color]\n"
			+ "  攻击力 × 攻防比 × 类型倍率 × 暴击系数\n\n"
			+ "[color=#f4e8c1][b]指挥官系统[/b][/color]\n"
			+ "  每回合能量累计到 100 可发动指挥官技\n\n"
			+ "[color=#f4e8c1][b]胜利条件[/b][/color]\n"
			+ "  消灭所有敌方单位,或占领对方总部(通用规则)"
		)
		content.add_child(body)
		var close := Button.new()
		close.text = "关 闭"
		close.anchor_left = 0.5
		close.anchor_top = 1.0
		close.anchor_right = 0.5
		close.anchor_bottom = 1.0
		close.offset_left = -80.0
		close.offset_top = -48.0
		close.offset_right = 80.0
		close.offset_bottom = -16.0
		close.pressed.connect(hide_help)
		close.add_theme_font_size_override("font_size", 14)
		content.add_child(close)
	_help_panel.visible = true


func hide_help() -> void:
	if _help_panel != null and is_instance_valid(_help_panel):
		_help_panel.visible = false


# P1:主菜单 HelpButton → 触发玩法说明浮层
func _on_help_pressed() -> void:
	show_help()


func _on_turn_ended(next_player_id, turn_number: int) -> void:
	# M4.17:turn banner slide-down + 玩家色 + emoji
	var pid_str := str(next_player_id)
	var cp: Dictionary = GameState.get_player(int(next_player_id)) if next_player_id != null else {}
	var name: String = str(cp.get("user_name", "—"))
	var color_name: String = str(cp.get("color", "red"))
	var color_hex: String = _color_name_to_godot(color_name)
	var emoji: String = _color_emoji(color_name)
	var is_local: bool = (int(next_player_id) == _player_id) if next_player_id != null else false
	var suffix: String = "  →  你的回合" if is_local else ""
	_show_turn_banner("回合 %d  ·  %s [color=%s]%s[/color]%s" % [
		turn_number, emoji, color_hex, name, suffix
	], 3.0)
	_schedule_board_refresh()


func _winner_player_id_from_finished_snapshot() -> int:
	if GameState == null:
		return -1
	var alive_team_to_pid: Dictionary = {}
	for p in GameState.players:
		if not p is Dictionary:
			continue
		if bool(p.get("is_spectator", false)) or not bool(p.get("is_alive", true)):
			continue
		if (p.get("units", []) as Array).is_empty():
			continue
		var pid: int = int(p.get("id", -1))
		var key: String = _player_team_key(pid)
		if not alive_team_to_pid.has(key):
			alive_team_to_pid[key] = pid
	# 唯一活着的队伍 = 真正的胜者;0 队伍(全员阵亡的 draw)或 ≥2 队伍
	# 都返回 -1,让 show_battle_result 把 winner 留空、不冒认"学长 获胜!"。
	if alive_team_to_pid.size() == 1:
		return int(alive_team_to_pid.values()[0])
	return -1


func _handle_finished_snapshot(summary: Dictionary) -> void:
	if _game_over:
		return
	var reason: String = str(summary.get("win_reason", "rout"))
	var winner_pid: int = _winner_player_id_from_finished_snapshot()
	_on_match_ended(winner_pid, reason)


func _on_match_ended(winner_player_id, win_reason: String) -> void:
	# M4.16+ game-over 保险:置 flag 后,后续的 _on_state_updated /
	# ai_thinking 都会被屏蔽,避免循环刷新或 AI 推事件导致卡死。
	_game_over = true
	_board_refresh_pending = false
	if _state_poll_timer != null and is_instance_valid(_state_poll_timer):
		_state_poll_timer.stop()
	# 关闭可能还在显示的 AI thinking / end-turn 提示
	if ai_thinking_label != null and is_instance_valid(ai_thinking_label):
		ai_thinking_label.visible = false
	# Hide any in-flight action bubble so the result panel sits on a clean canvas
	_hide_action_bubble()
	_show_turn_banner("🏆 [color=#f0c75e]玩家 #%s[/color] 获胜! 原因: %s" % [
		str(winner_player_id), win_reason
	], 8.0)
	# S:4:弹 BattleResultPanel — 展示 winner + 战斗统计
	var winner_id: int = int(winner_player_id) if winner_player_id != null else -1
	var winner_p: Dictionary = GameState.get_player(winner_id) if winner_id > 0 else {}
	var winner_name: String = str(winner_p.get("user_name", "—"))
	var winner_color: String = str(winner_p.get("color", "red"))
	var summary: Dictionary = GameState.game_summary if GameState != null else {}
	var stats: Dictionary = {
		"kills": 0,
		"deaths": 0,
		"captures": 0,
		"co_peak": int(winner_p.get("co_meter", 0)),
		"turns": int(summary.get("turn_number", 0)),
		"skills": 0,
		"reason": win_reason,
	}
	# T:6 详细战报:从 logs 抽最近 N=12 条(按创建时间倒序)。
	var detail_lines: Array = []
	if GameState != null:
		var all_logs: Array = (GameState.logs as Array)
		for log in all_logs:
			if not (log is Dictionary): continue
			var action_type: String = str(log.get("action_type", ""))
			var actor_pid_v: Variant = log.get("player_id", -1)
			var actor_pid: int = -1 if actor_pid_v == null else int(actor_pid_v)
			if action_type == "kill":
				if actor_pid == winner_id:
					stats["kills"] = int(stats.get("kills", 0)) + 1
				elif winner_id > 0 and actor_pid > 0:
					stats["deaths"] = int(stats.get("deaths", 0)) + 1
			elif action_type == "claim_complete":
				if actor_pid == winner_id:
					stats["captures"] = int(stats.get("captures", 0)) + 1
			elif action_type == "skill":
				if actor_pid == winner_id:
					stats["skills"] = int(stats.get("skills", 0)) + 1
			# 战报行(全部):turn N · action_type · description
			var turn_n: int = int(log.get("turn_number", 0))
			var desc: String = str(log.get("description", ""))
			detail_lines.append("[color=#a89878]回合 %d[/color]  [color=#c9a14a]%s[/color]  %s" % [
				turn_n, action_type, desc
			])
		# 保留最近 N 条
		var MAX_DETAIL := 12
		if detail_lines.size() > MAX_DETAIL:
			detail_lines = detail_lines.slice(detail_lines.size() - MAX_DETAIL)
	stats["detail_lines"] = detail_lines
	show_battle_result(winner_name, winner_color, stats)
	if _active_mainline_id != "" and _mainline_battle_game_id == _game_id and winner_id == _player_id:
		_update_status("主线战斗胜利,推进章节...")
		NetworkClient.advance_mainline(_active_mainline_id, _user_name, _game_id, Callable(self, "_on_mainline_advance_response"))


## M4.17:slide-down banner from above + auto-hide.
func _show_turn_banner(bbcode: String, duration: float = 3.0) -> void:
	if turn_banner == null or not is_instance_valid(turn_banner):
		return
	# Stop any in-flight tween.
	if _turn_banner_tween != null and _turn_banner_tween.is_running():
		_turn_banner_tween.kill()
	turn_banner_label.text = bbcode
	# Start 60px above its resting position + invisible.
	var start_pos: Vector2 = turn_banner.position + Vector2(0, -60)
	turn_banner.modulate.a = 0.0
	turn_banner.position = start_pos
	turn_banner.visible = true
	# Tween to resting pos + opacity 1.
	_turn_banner_tween = create_tween()
	_turn_banner_tween.set_trans(Tween.TRANS_CUBIC)
	_turn_banner_tween.set_ease(Tween.EASE_OUT)
	_turn_banner_tween.set_parallel(true)
	_turn_banner_tween.tween_property(turn_banner, "position", start_pos + Vector2(0, 60), 0.45)
	_turn_banner_tween.tween_property(turn_banner, "modulate:a", 1.0, 0.45)
	# Wait, then fade out and hide.
	_turn_banner_tween.set_parallel(false)
	_turn_banner_tween.tween_interval(duration)
	_turn_banner_tween.tween_property(turn_banner, "modulate:a", 0.0, 0.6)
	_turn_banner_tween.tween_callback(func(): turn_banner.visible = false)


func _on_ai_thinking(thinking: bool) -> void:
	# M4.18:pulse 动效 — 颜色 alpha 0.4 ↔ 1.0,每 0.8s 一个循环
	if ai_thinking_label == null or not is_instance_valid(ai_thinking_label):
		return
	if _ai_pulse_tween != null and _ai_pulse_tween.is_running():
		_ai_pulse_tween.kill()
		_ai_pulse_tween = null
	if not thinking:
		ai_thinking_label.visible = false
		ai_thinking_label.modulate.a = 1.0
		return
	ai_thinking_label.visible = true
	ai_thinking_label.modulate.a = 1.0
	_ai_pulse_tween = create_tween().set_loops()
	_ai_pulse_tween.set_trans(Tween.TRANS_SINE)


# 2026-08-09:全局返回上一级 — LIFO 关掉最上层 modal。
# 返回:true 表示关掉了某 modal(让 caller 调 set_input_as_handled);
#       false 表示没 modal 在最上层,让其它逻辑继续走(棋盘 cancel / 暂停 toggle)。
func _try_close_topmost_modal() -> bool:
	# LIFO 顺序:后开的先关。最靠"玩家"的最先关。
	# 顺序按 panel 显隐的常见 LIFO 路径调:
	#   ConfirmDialog(顶层) > BattleResult(终局) > AttackConfirm(战斗中)
	#   > Recruit(选中空兵营后) > WarReport(终局后) > Settings(任何时候)
	#   > Pause(战斗中) > TutorialBubble(任何时候)
	# 注意:ActionBubble 不接 ui_cancel(玩家按 ui_cancel 时通常是要退出行动模式,
	# ActionBubble 跟 board.cancel_cursor 同语义,留给 board._handle_cursor_input 处理)。
	if _is_visible(confirm_dialog):
		# Confirm 弹窗 Esc = 选 No(默认焦点,更安全)
		_on_confirm_no_pressed()
		return true
	if _is_visible(battle_result_panel):
		# BattleResult Esc = 关闭面板(玩家可能想看棋盘)
		hide_battle_result()
		return true
	if _is_visible(attack_confirm_panel):
		# 攻击确认 Esc = 取消攻击
		_on_attack_cancel_pressed()
		return true
	if _is_visible(recruit_panel):
		_on_recruit_close_pressed()
		return true
	if _is_visible(war_report_panel):
		war_report_panel.visible = false
		return true
	if _is_visible(tutorial_bubble):
		_on_tutorial_got_it_pressed()
		return true
	if _is_visible(settings_panel):
		_hide_settings_panel()
		return true
	if _is_visible(pause_panel):
		# pause 在 board_focused 已被让给 board.cancel(我们在 _unhandled_input 顶部分流)
		# 这里 pause.visible 时一律关暂停
		_toggle_pause()
		return true
	if _is_visible(connecting_panel):
		# 重连卡住 → 放弃,回主菜单
		_on_connecting_abort_pressed()
		return true
	return false


func _is_visible(panel: Control) -> bool:
	if panel == null or not is_instance_valid(panel):
		return false
	return panel.visible
	_ai_pulse_tween.tween_property(ai_thinking_label, "modulate:a", 0.4, 0.8)
	_ai_pulse_tween.tween_property(ai_thinking_label, "modulate:a", 1.0, 0.8)


# ============================================================
# Click → action
# ============================================================

func _on_end_turn_pressed() -> void:
	if _game_id > 0 and _player_id > 0:
		NetworkClient.action_end_turn(_game_id, _player_id)


func _on_raw_ws_message(_msg: Dictionary) -> void:
	# Existing connection to ws_message_received lets us log raw
	# frames for debugging. (GameState already did the typed dispatch.)
	pass


# ============================================================
# Helpers
# ============================================================

func _update_status(text: String) -> void:
	status_label.text = text


# ============================================================
# V2 第 6 轮:设置 + 暂停面板 — 输入 + handlers
# ============================================================

func _unhandled_input(event: InputEvent) -> void:
	# 2026-08-09:全局返回上一级(模态 LIFO)— Esc / 手柄 A 先关最上层 modal
	# 优先级(从上到下,先匹配先关):
	#   ConfirmDialog → BattleResultPanel → AttackConfirmPanel → RecruitPanel
	#   → WarReportPanel → SettingsPanel → PausePanel → ConnectingPanel(放弃重连)
	# 命中即 set_input_as_handled,后续 board / ui_cancel / ui_back 不再处理。
	# 注意:board_focused 棋盘模式让位给 modal(玩家开的 modal 优先于棋盘微观操作)。
	if event.is_action_pressed("ui_cancel"):
		if _try_close_topmost_modal():
			get_viewport().set_input_as_handled()
			return
	if event is InputEventKey and event.pressed and not event.echo:
		if editor_view != null and is_instance_valid(editor_view) and editor_view.visible and event.ctrl_pressed:
			if event.keycode == KEY_Z:
				editor_view.request_undo()
				get_viewport().set_input_as_handled()
				return
			if event.keycode == KEY_Y:
				editor_view.request_redo()
				get_viewport().set_input_as_handled()
				return
	# ESC 键暂停 / 关闭上层面板(只在 game view)
	if event.is_action_pressed("pause"):
		# 2026-08-09:board_focused 时(棋盘光标模式)Esc 走"取消行动模式",
		# 不触发暂停。玩家按 Start(手柄)/ 主动点暂停按钮才暂停。
		if InputState != null and InputState.board_focused \
				and not (settings_panel != null and is_instance_valid(settings_panel) and settings_panel.visible):
			return
		# 优先级:settings_panel 打开 → 关 settings;否则 toggle pause
		if settings_panel != null and is_instance_valid(settings_panel) and settings_panel.visible:
			_hide_settings_panel()
			get_viewport().set_input_as_handled()
			return
		if game_view != null and is_instance_valid(game_view) and game_view.visible:
			_toggle_pause()
			get_viewport().set_input_as_handled()
		return
	# T:95 — 鼠标移动 → 移动模式里画 path dots
	if event is InputEventMouseMotion:
		if _move_mode_unit_id > 0 and board != null:
			_update_path_dots_on_hover(event.global_position)
		# 鸢影·沉默领域:跟踪 hover cell,显示 5×5 outline
		if _silence_pick_center_for_pid > 0 and board != null:
			board.update_silence_pick_hover(event.global_position)
		return
	# M4.10:鼠标左键 → 选中单位 / 行动目标
	# 右键:有面板→关面板;行动模式→取消;点单位→显示射程;空地→清除
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_RIGHT:
		if game_view == null or not game_view.visible:
			return
		if board == null:
			return
		# ① 面板 → 关闭
		if settings_panel != null and settings_panel.visible:
			_hide_settings_panel()
			get_viewport().set_input_as_handled()
			return
		if pause_panel != null and pause_panel.visible:
			_toggle_pause()
			get_viewport().set_input_as_handled()
			return
		if war_report_panel != null and war_report_panel.visible:
			war_report_panel.visible = false
			get_viewport().set_input_as_handled()
			return
		# ② 行动模式 → 取消
		if _silence_pick_center_for_pid > 0:
			_cancel_silence_pick()
			get_viewport().set_input_as_handled()
			return
		if _move_mode_unit_id > 0 or _attack_mode_unit_id > 0 or _skill_mode_unit_id > 0:
			_cancel_action_mode()
			_hide_action_bubble()
			get_viewport().set_input_as_handled()
			return
		# ③ 右键点单位 → 显示该单位所有可能射程
		var rtu_id: int = board.pick_unit_at_screen(event.global_position)
		if rtu_id > 0:
			var rtu: Dictionary = GameState.get_unit(rtu_id) if GameState != null else {}
			if not rtu.is_empty():
				var rtiles: Array = _get_attack_range_tiles(rtu)
				if rtiles.size() > 0 and board != null:
					board.show_attack_marks(rtiles)
				_update_status("查看射程: %s (%d格)" % [rtu.get("name", rtu.get("unit_type", "?")), rtiles.size()])
			get_viewport().set_input_as_handled()
			return
		# ④ 空地右键 → 清除选中
		_cancel_action_mode()
		_hide_action_bubble()
		if board != null and board.has_method("clear_selection_marks"):
			board.clear_selection_marks()
		get_viewport().set_input_as_handled()
		return
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		if game_view == null or not game_view.visible:
			return
		if board == null:
			return
		if board.has_method("handle_camera_input_from_owner"):
			board.call("handle_camera_input_from_owner", event)
		# 关 pause/settings 后再处理
		if (settings_panel != null and settings_panel.visible) \
				or (pause_panel != null and pause_panel.visible) \
				or (war_report_panel != null and war_report_panel.visible):
			return
		var unit_id: int = board.pick_unit_at_screen(event.global_position)
		if unit_id > 0:
			board.emit_unit_clicked(unit_id)
		else:
			# 点击非单位区域 → 落点 / 取消行动模式
			if _move_mode_unit_id > 0:
				# 移动模式下:把屏幕坐标转成 tile 再 emit
				board.emit_tile_clicked(event.global_position)
			elif _attack_mode_unit_id > 0:
				# 攻击模式:空地点击 → 取消
				_cancel_action_mode()
			elif _skill_mode_unit_id > 0:
				# 治疗模式:空地点击 → 取消
				_cancel_action_mode()
			else:
				board.emit_tile_clicked(event.global_position)
		get_viewport().set_input_as_handled()


# 把屏幕坐标转 tile,看是不是"我方 owner + 空 barracks + 是我的回合"。
# 是 → {x, y, gold};否 → {}。
func _pick_empty_my_barracks(global_pos: Vector2) -> Dictionary:
	if board == null:
		return {}
	var layer: TileMapLayer = board.get_node_or_null("GroundLayer")
	if layer == null:
		return {}
	var local: Vector2 = layer.to_local(global_pos)
	return _pick_empty_my_barracks_at_cell(layer.local_to_map(local))


func _pick_empty_my_barracks_at_cell(cell: Vector2i) -> Dictionary:
	if board == null or GameState == null:
		return {}
	if not GameState.is_local_turn:
		_update_status("Not your turn...")
		return {}
	var tile := GameState.get_tile(cell.x, cell.y)
	if tile.is_empty() and board.tile_lookup != null:
		tile = board.tile_lookup.get(cell, {})
	if tile.is_empty():
		_update_status("Map data not loaded")
		return {}
	if str(tile.get("terrain", "")) != "barracks":
		return {}
	var owner_id := int(tile.get("owner_id", -1))
	if owner_id != _player_id:
		_update_status("This barracks is not yours (owner=%d)" % owner_id)
		return {}
	var occ_v: Variant = tile.get("occupied_unit_id", null)
	if occ_v != null and int(occ_v) > 0:
		_update_status("Barracks occupied; move the unit away first")
		return {}
	var me: Dictionary = GameState.get_player(_player_id)
	return {"x": cell.x, "y": cell.y, "gold": int(me.get("gold", 0))}


func _try_open_recruit_at_tile(tile: Vector2i) -> bool:
	var batt: Dictionary = _pick_empty_my_barracks_at_cell(tile)
	if batt.is_empty():
		return false
	_show_recruit_at(batt)
	return true


func _show_recruit_at(info: Dictionary) -> void:
	if recruit_panel == null or not is_instance_valid(recruit_panel):
		return
	var tx: int = int(info.get("x", -1))
	var ty: int = int(info.get("y", -1))
	var gold_i: int = int(info.get("gold", 0))
	_recruit_pending_tile = Vector2i(tx, ty)
	recruit_status_label.text = "佣兵站 (%d, %d) · 当前金币 💰 %d" % [tx, ty, gold_i]
	# 清空旧内容,生成 5 个按钮
	for child in recruit_list.get_children():
		child.queue_free()
	for opt in _RECRUIT_OPTIONS:
		var btn := Button.new()
		var unit_type: String = str(opt.get("type", "?"))
		var name: String = _unit_type_cn(unit_type)
		var cost: int = int(opt.get("cost", 0))
		btn.text = "%s  💰 %d" % [name, cost]
		btn.disabled = gold_i < cost
		btn.pressed.connect(_on_recruit_button_pressed.bind(unit_type))
		recruit_list.add_child(btn)
	recruit_panel.visible = true
	# 2026-08-09:grab focus 到第一个可点按钮(动态列表,用 first focusable)
	UIPanelFocus.grab_first_focusable(recruit_panel)


func _on_recruit_button_pressed(unit_type: String) -> void:
	if _recruit_pending_tile.x < 0:
		return
	_recruit_unit_to(_recruit_pending_tile.x, _recruit_pending_tile.y, unit_type)
	# 关闭 modal
	if recruit_panel != null and is_instance_valid(recruit_panel):
		recruit_panel.visible = false


func _on_recruit_close_pressed() -> void:
	if recruit_panel != null and is_instance_valid(recruit_panel):
		recruit_panel.visible = false
	_recruit_pending_tile = Vector2i(-1, -1)


func _on_board_unit_clicked(unit_id: int) -> void:
	# 来自 board.emit_unit_clicked — 单位已经被选中
	# 攻击模式下点单位 → 用作 attack target
	if _attack_mode_unit_id > 0:
		if _attack_targets.has(unit_id):
			_show_attack_confirm(_attack_mode_unit_id, unit_id)
		else:
			# 点错目标(不是敌方有效目标)→ 取消
			_update_status("目标无效,取消攻击")
			_attack_mode_unit_id = -1
			_attack_targets = {}
			if board != null:
				board.clear_selection_marks()
		return
	# 治疗模式下点单位 → 用作 heal target
	if _skill_mode_unit_id > 0:
		if _skill_targets.has(unit_id):
			_use_skill_on_target(_pending_skill_id, _skill_mode_unit_id, unit_id)
		else:
			_update_status("目标无效,取消技能")
			_skill_mode_unit_id = -1
			_skill_targets = {}
			if board != null:
				board.clear_selection_marks()
		return
	# 否则:正常选中流程
	_handle_unit_click(unit_id, Vector2.ZERO)


# M4.1:点击地图格子(空白区 / 落点)→ 处理
func _on_board_tile_clicked(tile: Vector2i) -> void:
	# 鸢影·沉默领域选中心:任何 tile 点击都优先处理(玩家选 center)
	if _silence_pick_center_for_pid > 0:
		_handle_silence_center_pick(tile)
		return
	if _move_mode_unit_id <= 0:
		if tile.x >= 0 and tile.y >= 0 and _try_open_recruit_at_tile(tile):
			return
		if board != null:
			board.clear_selection_marks()
		_hide_action_bubble()
		return
	if tile.x < 0 or tile.y < 0:
		_cancel_move_mode()
		return
	# 必须落在 reachable set 内
	if not _move_reachable_set.has(tile):
		# 落点无效 → 取消移动模式
		_cancel_move_mode()
		return
	# 提交动作
	_move_unit_to(_move_mode_unit_id, tile.x, tile.y)


# M4.1:取消移动模式
func _cancel_move_mode() -> void:
	_move_mode_unit_id = -1
	_move_reachable_set = {}
	_clear_move_preview_path()
	if board != null:
		board.clear_selection_marks()
	_update_status("已取消移动")


# M4.1:发 POST /games/{id}/move
func _apply_immediate_move_feedback(unit_id: int, to_cell: Vector2i, path_cells: Array = []) -> void:
	var spent_mp: int = -1
	if _move_reachable_set.has(to_cell):
		spent_mp = int(_move_reachable_set.get(to_cell, 0)) / 2
	if GameState != null and GameState.has_method("apply_local_move_preview"):
		GameState.apply_local_move_preview(unit_id, to_cell, spent_mp)
	_move_mode_unit_id = -1
	_move_reachable_set = {}
	_clear_move_preview_path()
	if board != null:
		if path_cells.size() >= 2 and board.has_method("preview_unit_path"):
			board.preview_unit_path(unit_id, path_cells, 0.45)
		elif board.has_method("preview_unit_move"):
			board.preview_unit_move(unit_id, to_cell, 0.28)
		board.clear_selection_marks()
	_hide_action_bubble()
	_show_post_action_bubble(unit_id, "移动")
	_update_status("移动指令已下达: #%d -> (%d, %d)" % [unit_id, to_cell.x, to_cell.y])


func _move_unit_to(unit_id: int, to_x: int, to_y: int) -> void:
	if _game_id <= 0 or _player_id <= 0:
		return
	var to_cell := Vector2i(to_x, to_y)
	var path_cells: Array = []
	if _move_preview_target == to_cell and _move_preview_path.size() >= 2:
		path_cells = _move_preview_path.duplicate()
	_apply_immediate_move_feedback(unit_id, to_cell, path_cells)
	NetworkClient.action_move(_game_id, _player_id, unit_id, to_x, to_y)


func _handle_unit_click(unit_id: int, _global_pos: Vector2) -> void:
	var ud: Dictionary = GameState.get_unit(unit_id) if GameState != null else {}
	if ud.is_empty():
		return
	# T:7:不论是什么单位,先填 InfoPanel(对手 / 已行动 unit 也能看)
	_refresh_unit_info(ud)
	# T:7 inspect bubble:点击敌方 / 已行动 / 非己方单位 → 直接填 InfoPanel
	# 不弹 action bubble,也不进入任何行动模式。
	var owner_pid: int = int(ud.get("player_id", int(ud.get("owner_id", -1))))
	var cur_pid: int = int(GameState.current_player_id) if GameState.current_player_id != null else -1
	var is_my_unit: bool = (owner_pid == _player_id)
	var can_still_act: bool = not bool(ud.get("has_acted", false))
	print("[CLICK] handle_unit: unit=%d owner=%d me=%d cur=%d my=%s acted=%s moved=%s" % [unit_id, owner_pid, _player_id, cur_pid, is_my_unit, bool(ud.get("has_acted", false)), bool(ud.get("has_moved", false))])
	if not is_my_unit or not can_still_act:
		# 不进入移动/攻击模式
		_move_mode_unit_id = -1
		_move_reachable_set = {}
		_clear_move_preview_path()
		_attack_mode_unit_id = -1
		_attack_targets = {}
		_hide_attack_confirm()
		_skill_mode_unit_id = -1
		_skill_targets = {}
		if board != null:
			board.clear_selection_marks()
		_hide_action_bubble()
		return
	# 否则:可行动己方 unit → 弹气泡 + reachable 高亮
	_selected_unit_id = unit_id
	var cell := Vector2i(int(ud.get("x", 0)), int(ud.get("y", 0)))
	var marker_pos: Vector2 = board.tile_to_viewport(cell) if board != null else Vector2.ZERO
	_show_action_bubble(unit_id, marker_pos, _ACTION_CONTEXT_INITIAL)
	var is_mine: bool = (owner_pid == _player_id and owner_pid == cur_pid)
	if is_mine and not bool(ud.get("has_acted", false)) and not bool(ud.get("has_moved", false)):
		var reach_dict: Dictionary = _compute_reachable_tiles_full(ud)
		var tiles: Array = reach_dict.keys()
		_move_reachable_set = reach_dict
		_clear_move_preview_path()
		if tiles.size() > 0 and board != null:
			board.show_path_marks([], tiles)
	elif board != null:
		board.clear_selection_marks()
		_move_reachable_set = {}
		_clear_move_preview_path()


# 返回 full Dict {Vector2i: cost} 包括起点;供路径结果判断
func _compute_reachable_tiles_full(unit_data: Dictionary) -> Dictionary:
	var mp: int = int(unit_data.get("mov", int(unit_data.get("move_points", int(unit_data.get("mp", 5))))))
	var unit_pos := Vector2i(int(unit_data.get("x", 0)), int(unit_data.get("y", 0)))
	var size_v: int = 15
	if board != null and board.map_size.x > 0:
		size_v = board.map_size.x
	var occupancy := _movement_occupancy_for_unit(unit_data)
	var blocked: Dictionary = occupancy.get("blocked", {})
	var no_end: Dictionary = occupancy.get("no_end", {})
	var owners: Dictionary = {}
	if board.tile_lookup != null:
		for k in board.tile_lookup.keys():
			var t: Dictionary = board.tile_lookup[k]
			var owner_v = t.get("owner_id", null)
			owners[k] = int(owner_v) if owner_v != null else 0
	var terrain: Dictionary = {}
	if board != null and board.tile_lookup != null:
		for k in board.tile_lookup.keys():
			var t: Dictionary = board.tile_lookup[k]
			terrain[k] = str(t.get("terrain", "plain"))
	var owner: int = int(unit_data.get("player_id", int(unit_data.get("owner_id", int(_player_id)))))
	var result: Dictionary = MapLogic.compute_reachable(
		unit_pos, terrain, owners, mp, owner, blocked, no_end, size_v
	)
	print("DEBUG reachable: result_size=%s" % result.size())
	return result


func _compute_reachable_tiles(unit_data: Dictionary) -> Array:
	var mp: int = int(unit_data.get("move_points", int(unit_data.get("mp", 5))))
	var unit_pos := Vector2i(int(unit_data.get("x", 0)), int(unit_data.get("y", 0)))
	var size_v: int = 15
	if board != null and board.map_size.x > 0:
		size_v = board.map_size.x
	var occupancy := _movement_occupancy_for_unit(unit_data)
	var blocked: Dictionary = occupancy.get("blocked", {})
	var no_end: Dictionary = occupancy.get("no_end", {})
	# terrain: tile (Vector2i) → terrain_name(String);owner 编码另外从
	# tile_lookup_inverse 或 Players 推,这里先用 0 当占位
	var terrain: Dictionary = {}
	var owners: Dictionary = {}
	if board != null and board.tile_lookup != null:
		for k in board.tile_lookup.keys():
			var t: Dictionary = board.tile_lookup[k]
			terrain[k] = str(t.get("terrain", "plain"))
			var owner_v = t.get("owner_id", null)
			owners[k] = int(owner_v) if owner_v != null else 0
	var owner: int = int(unit_data.get("owner_id", int(_player_id)))
	# MapLogic.compute_reachable(start, terrain, owners, mov, viewer_owner_id, blocked, no_end, size)
	var result: Dictionary = MapLogic.compute_reachable(
		unit_pos, terrain, owners, mp, owner, blocked, no_end, size_v
	)
	# 移除起点(不要把自身高亮成可达)
	result.erase(unit_pos)
	return result.keys()


func _movement_occupancy_for_unit(unit_data: Dictionary) -> Dictionary:
	var blocked: Dictionary = {}
	var no_end: Dictionary = {}
	if GameState == null:
		return {"blocked": blocked, "no_end": no_end}
	var mover_pid: int = int(unit_data.get("player_id", int(unit_data.get("owner_id", int(_player_id)))))
	var mover_team: String = _player_team_key(mover_pid)
	var mover_id: int = int(unit_data.get("id", -1))
	for player in GameState.players:
		if not player is Dictionary:
			continue
		var other_pid: int = int(player.get("id", -1))
		var same_team: bool = other_pid > 0 and _player_team_key(other_pid) == mover_team
		for unit in player.get("units", []):
			if not unit is Dictionary:
				continue
			var unit_id: int = int(unit.get("id", -1))
			if unit_id == mover_id:
				continue
			if int(unit.get("hp", 1)) == 0:
				continue
			var cell := Vector2i(int(unit.get("x", 0)), int(unit.get("y", 0)))
			if same_team:
				no_end[cell] = true
			else:
				blocked[cell] = true
	return {"blocked": blocked, "no_end": no_end}


func _toggle_pause() -> void:
	var open: bool = not (pause_panel != null and is_instance_valid(pause_panel) and pause_panel.visible)
	if open:
		pause_overlay.process_mode = Node.PROCESS_MODE_WHEN_PAUSED
		pause_panel.process_mode = Node.PROCESS_MODE_WHEN_PAUSED
		pause_overlay.visible = true
		pause_panel.visible = true
		# 暂停时关闭行动气泡 + 战报面板
		if action_bubble != null and is_instance_valid(action_bubble):
			action_bubble.visible = false
		if war_report_panel != null and is_instance_valid(war_report_panel):
			war_report_panel.visible = false
		get_tree().paused = true
		# 2026-08-09:grab focus 到默认按钮(resume),手柄/键盘可立即点
		UIPanelFocus.grab_on_show(pause_panel, pause_resume_btn)
	else:
		_hide_pause_panel()


func _hide_pause_panel() -> void:
	pause_overlay.visible = false
	pause_panel.visible = false
	get_tree().paused = false


func _show_settings_panel() -> void:
	if settings_panel == null or not is_instance_valid(settings_panel):
		return
	# 同步当前玩家名到 input
	if settings_name_input != null and is_instance_valid(settings_name_input):
		settings_name_input.text = _user_name
	settings_panel.visible = true
	# 2026-08-09:grab focus 到关闭按钮(玩家可能想直接退),手柄/键盘可立即按
	UIPanelFocus.grab_on_show(settings_panel, settings_close_btn)


func _hide_settings_panel() -> void:
	if settings_panel != null and is_instance_valid(settings_panel):
		settings_panel.visible = false


func _on_settings_open_pressed() -> void:
	# 主菜单的"设置"按钮 → 打开 SettingsPanel (主菜单状态下也能调字号/玩家名)
	_show_settings_panel()


func _on_settings_close_pressed() -> void:
	_hide_settings_panel()


# P0:自动存档 toast — 服务端 /advance 与 /mainlines/{id}/prepare/complete 写 auto-save
# response.body.auto_save = AutoSaveCheckpointOut {label, auto_kind, saved_at}
func _show_auto_save_toast(label: String, ms: float = 1800.0) -> void:
	if auto_save_toast == null or not is_instance_valid(auto_save_toast):
		return
	if auto_save_toast_label != null and is_instance_valid(auto_save_toast_label):
		auto_save_toast_label.text = label
	auto_save_toast.visible = true
	# kill 旧 tween 以支持叠加调用
	if _auto_save_toast_tween != null and _auto_save_toast_tween.is_valid():
		_auto_save_toast_tween.kill()
	_auto_save_toast_tween = create_tween()
	_auto_save_toast_tween.tween_interval(ms / 1000.0)
	_auto_save_toast_tween.tween_callback(func():
		if auto_save_toast != null and is_instance_valid(auto_save_toast):
			auto_save_toast.visible = false
	)


func _on_settings_apply_pressed() -> void:
	if settings_name_input != null and is_instance_valid(settings_name_input):
		var new_name: String = settings_name_input.text.strip_edges()
		if new_name != "":
			_user_name = new_name
			UserSettings.set_value("settings.v1.player_name", _user_name)
	_update_status("设置已应用 (玩家名: %s)" % _user_name)
	_hide_settings_panel()


# T:93 — Settings 按钮接线(字号 / 颜色 / 主题)
func _on_font_small_pressed() -> void:
	_apply_font_size(12)


func _on_font_med_pressed() -> void:
	_apply_font_size(14)


func _on_font_big_pressed() -> void:
	_apply_font_size(16)


func _on_red_color_pressed() -> void:
	_apply_preferred_color("red")


func _on_blue_color_pressed() -> void:
	_apply_preferred_color("blue")


func _on_green_color_pressed() -> void:
	_apply_preferred_color("green")


func _on_yellow_color_pressed() -> void:
	_apply_preferred_color("yellow")


func _on_theme_dropdown_item_selected(idx: int) -> void:
	var theme_name: String = "deep_gba"
	match idx:
		1: theme_name = "metal_silver"
		2: theme_name = "minimal_light"
	_on_theme_change(theme_name)


# T:8 字号生效 — 设全局 default font_size + 重 apply HUD
func _apply_font_size(size: int) -> void:
	UserSettings.set_value("settings.v1.font_size", size)
	var theme: Theme = ThemeDB.get_project_theme()
	if theme != null:
		theme.default_font_size = size
	# 重 apply HUD 让所有 Label/Btn 立即生效
	if has_method("_apply_hud_theme"):
		_apply_hud_theme()
	_update_status("字号已设为 %d" % size)


# T:8 阵营颜色生效 + P2 hot-effect:4 色按钮立即视觉反馈
func _apply_preferred_color(color_name: String) -> void:
	UserSettings.set_value("settings.v1.color", color_name)
	# P2 hot-effect:立刻更新 PlayersList / 自己标记色(若在局内)。
	# 已开战对局的 player.color 是服务端权威,只能等下一局换色;
	# 但大厅视图/无对局时的 status/player 头像色块可以立刻反映偏好。
	_apply_local_color_hint(color_name)
	_update_status("✓ 偏好色已记下: %s (新对局才生效)" % color_name)


func _apply_local_color_hint(color_name: String) -> void:
	# 在没有对局时,改 status label 颜色块作为可见反馈;
	# 在大厅 / 战斗中时,改 lobby_self_color 风格 chip 由所属渲染逻辑读取 pref_color。
	var hint_color: Color = Config.player_color(color_name) if Config != null else Color.WHITE
	hint_color.a = 0.85
	var status_label: Label = get_node_or_null("Menu/.../StatusLabel")
	if status_label == null:
		status_label = get_node_or_null("/root/Main/Menu/ConnectingPanel/StatusLabel")
	# 此处不强求 status label hot-update(各视图 position 不同),
	# 主要是给玩家一个"按了就有反应"的反馈信号 — 已在 _update_status 文案体现 ✓ mark。


func _on_settings_cancel_pressed() -> void:
	_hide_settings_panel()


func _on_pause_resume_pressed() -> void:
	_hide_pause_panel()


func _on_pause_settings_pressed() -> void:
	_hide_pause_panel()
	_show_settings_panel()


func _on_pause_main_menu_pressed() -> void:
	# T:88 — 真清状态再返菜单(player 再 resume 时不会撞 WS 残留)
	_reset_game_state_for_main_menu()
	_hide_pause_panel()
	_show_view("menu")
	_update_status("已返主菜单")


# M:98 — pause/quit → 主菜单的整体清理:close WS + 清 action 模式 +
# 重置 GameState + 关掉所有浮层。
func _reset_game_state_for_main_menu() -> void:
	# 1) 关闭 WS 不让旧游戏的事件持续推送
	if NetworkClient != null:
		NetworkClient.ws_close()
	# 2) 重置所有行动模式
	_move_mode_unit_id = -1
	_move_reachable_set = {}
	_clear_move_preview_path()
	_attack_mode_unit_id = -1
	_attack_targets = {}
	_skill_mode_unit_id = -1
	_skill_targets = {}
	# 3) 停 CO / 战斗反馈 tween
	if _ai_pulse_tween != null and _ai_pulse_tween.is_running():
		_ai_pulse_tween.kill()
	if _turn_banner_tween != null and _turn_banner_tween.is_running():
		_turn_banner_tween.kill()
	# 4) 清 GameState(autoload,保留 autoload 实例但清数据)
	if GameState != null:
		GameState._on_state_snapshot({
			"game": {},
			"tiles": [],
			"players": [],
			"current_player_id": null,
			"phase": "player",
			"logs": [],
			"co_states": [],
			"pending_claims": [],
		})
	# 5) 关 game 视图一切浮层
	_hide_action_bubble()
	if action_bubble != null and is_instance_valid(action_bubble):
		action_bubble.visible = false
	if recruit_panel != null and is_instance_valid(recruit_panel):
		recruit_panel.visible = false
	if battle_result_panel != null and is_instance_valid(battle_result_panel):
		battle_result_panel.visible = false
	# DialogManager:回主菜单硬重置(清队列 + heroes + 锁)
	if DialogManager != null:
		DialogManager.reset()
		DialogManager.hide_dialog()

	# 6) 关 board 高亮
	if board != null:
		board.clear_selection_marks()
	# 7) 关 Resume "暂停" — game state 没了,但 Resume 按钮仍然是 enabled
	# (它从 list_games 重新拉的)— 我们不动 _resume_game_id,下次进入
	# resume 会再拉一次。
	# 8) 注意:不调 UserSettings.set_value 清 last_game_id — 玩家
	# 还可以用 Resume 按钮回到刚才那局。
	# 9) 清旧 player_id + lobby 快照 — 不清的话,新房间的 lobby 渲染 / cycle
	# 会带着上一局的 _player_id,触发 400(后端找不到旧 id / status 已翻 playing)。
	# Resume 走 _resume_game_id/_resume_player_id,跟 _player_id 解耦,所以这里
	# 清掉不影响 Resume 流程。
	_player_id = 0
	_game_id = 0
	if lobby_view != null and is_instance_valid(lobby_view):
		lobby_view.reset_state()


func _on_pause_quit_pressed() -> void:
	get_tree().quit()


# P0:暂停面板"中断退出"按钮 — 玩家主动 capture_suspend 然后回到主菜单
# 与 MainMenuBtn 不同:MainMenuBtn 不写中断、可能丢进度;此处显式存为中断存档
func _on_pause_suspend_pressed() -> void:
	if _game_id <= 0 or _user_name == "":
		_update_status("无法中断:无对局")
		return
	if pause_suspend_btn != null and is_instance_valid(pause_suspend_btn):
		pause_suspend_btn.disabled = true
	_update_status("正在保存中断状态...")
	NetworkClient.capture_suspend(_game_id, _user_name,
		Callable(self, "_on_capture_suspend_response"))


func _on_capture_suspend_response(body: Variant, code: int) -> void:
	if pause_suspend_btn != null and is_instance_valid(pause_suspend_btn):
		pause_suspend_btn.disabled = false
	if code < 200 or code >= 300:
		var msg: String = "中断保存失败"
		if body is Dictionary and body.has("detail"):
			msg = "中断保存失败: %s" % str(body.get("detail"))
		_update_status(msg)
		return
	# Bug fix: 中断存档成功后必须主动切回主菜单 + toast 提示。否则玩家
	# 停在 pause 面板,不知道刚才那一按到底有没有生效。
	_update_status("💾 中断已保存,返回主菜单(可继续中断战斗)")
	_show_view("menu")
	_reset_game_state_for_main_menu()


# ============================================================
# V2 第 7 轮:对话 + 教程 + 战斗结算
# ============================================================

# M5.10 Dialog 系统 — server 端推 [{character, text, choices?}, ...]
# typewrite 一次显示一字符(0.03s/字),Continue 跳过/next。
# 简化版:本地一份队列 + typewriter,不接 server side (Mainline
# _requestNextBattle 待 V5.4 实装)。


	if DialogManager != null: DialogManager.hide_dialog()


func show_tutorial() -> void:
	if tutorial_bubble != null and is_instance_valid(tutorial_bubble):
		tutorial_bubble.visible = true


func hide_tutorial() -> void:
	if tutorial_bubble != null and is_instance_valid(tutorial_bubble):
		tutorial_bubble.visible = false


func show_battle_result(winner_name: String, winner_color: String, stats: Dictionary) -> void:
	if battle_result_panel == null or not is_instance_valid(battle_result_panel):
		return
	if battle_mainline_next_btn != null and is_instance_valid(battle_mainline_next_btn):
		battle_mainline_next_btn.visible = false
	var color_godot: String = _color_name_to_godot(winner_color)
	battle_result_winner.bbcode_enabled = true
	battle_result_winner.text = "🎉 [color=%s][b]%s[/b][/color] 获胜!" % [color_godot, winner_name]
	var detail_lines: Array = (stats.get("detail_lines", []) as Array)
	var detail_text: String = ""
	if detail_lines.size() > 0:
		detail_text = "\n\n[color=#c9a14a]📜 最近战报[/color]\n" + "\n".join(detail_lines)
	var stats_text: String = "[color=#c9a14a]📊 战 报 统 计[/color]\n\n" \
		+ "[color=#f4e8c1]击杀:[/color] [color=#f0c75e]%d[/color]      [color=#f4e8c1]被击杀:[/color] [color=#c63a3a]%d[/color]\n" % [int(stats.get("kills", 0)), int(stats.get("deaths", 0))] \
		+ "[color=#f4e8c1]占领建筑:[/color] [color=#f0c75e]%d[/color]   [color=#f4e8c1]CO 峰值:[/color] [color=#c9a14a]%d/100[/color]\n" % [int(stats.get("captures", 0)), int(stats.get("co_peak", 0))] \
		+ "[color=#f4e8c1]持续回合:[/color] [color=#f0c75e]%d[/color]    [color=#f4e8c1]技能使用:[/color] [color=#f0c75e]%d[/color]\n\n" % [int(stats.get("turns", 0)), int(stats.get("skills", 0))] \
		+ "[color=#a89878]胜利原因: %s[/color]" % str(stats.get("reason", "—")) \
		+ detail_text
	battle_result_stats.bbcode_enabled = true
	battle_result_stats.text = stats_text
	battle_result_panel.visible = true
	# 2026-08-09:grab focus 到主按钮(看情况,优先 DetailBtn,否则 BackLobbyBtn)
	var default_btn: Button = battle_detail_btn if battle_detail_btn != null else battle_back_lobby_btn
	UIPanelFocus.grab_on_show(battle_result_panel, default_btn)


func hide_battle_result() -> void:
	if battle_result_panel != null and is_instance_valid(battle_result_panel):
		battle_result_panel.visible = false


func _on_tutorial_got_it_pressed() -> void:
	hide_tutorial()
	UserSettings.set_value("settings.v1.tutorial_seen", true)


func _on_battle_detail_pressed() -> void:
	# 直接弹出战报面板(复用)
	if war_report_panel != null and is_instance_valid(war_report_panel):
		war_report_panel.visible = true
		# 2026-08-09:grab focus 到关闭按钮(战报面板只读,默认落 close)
		UIPanelFocus.grab_on_show(war_report_panel, war_report_close_btn)


func _on_battle_back_menu_pressed() -> void:
	# P2+ bug:这条路径之前只 hide_battle_result 然后 _show_view("menu"),
	# 漏掉 _reset_game_state_for_main_menu 的副作用清理(action bubble / recruit /
	# move-attack-skill mode / state poll) → 玩家返回主菜单时如果上次操作
	# 留了 selection 高亮或 tween,会污染整屏视觉。现与 pause→menu 一致:
	# 先做完整状态清理,再切 view。
	hide_battle_result()
	_reset_game_state_for_main_menu()
	_show_view("menu")


# M4.16+:战斗结束 → 返回联机大厅。复用 _on_lobby_pressed,但先清 game 状态
# 否则 _lobby_commanders_fetched / _game_id 可能残留导致 lobby 加载错位。
# P2+:先把整套 game 状态清掉(关 WS / action 模式 / GameState / Board 高亮 /
# 浮层 / tween),再清 lobby 专属字段,最后 _on_lobby_pressed。
func _on_battle_back_lobby_pressed() -> void:
	hide_battle_result()
	_reset_game_state_for_main_menu()
	_game_id = 0
	_player_id = 0
	_selected_mainline_id = ""
	_mainline_battle_game_id = 0
	# 复用主菜单"在线大厅"按钮处理流程(刷新 commander 列表 + 房间列表)
	_on_lobby_pressed()


# ============================================================
# GBA 火纹风主题注入(UI V2 第 1 轮)
# ============================================================

func _apply_gba_theme() -> void:
	HudTheme.apply_gba(self)


func _hud_density_scale() -> float:
	var window_width := float(DisplayServer.window_get_size().x)
	if window_width <= 0.0:
		return 1.0
	return clampf(1920.0 / window_width, 1.0, 1.4)


func _apply_hud_theme() -> void:
	HudTheme.apply_hud(self)


# ============================================================
# 主菜单新增按钮 handler
# ============================================================

func _on_editor_pressed() -> void:
	_entry_flow = "editor"
	_show_view("editor")
	editor_view.open()


func _on_editor_back_requested() -> void:
	_show_view("menu")


func _unit_type_cn(unit_type: String) -> String:
	return CnLabels.unit_type_cn(unit_type)


func _skill_cn(skill_id: String) -> String:
	return CnLabels.skill_cn(skill_id)


# P2.6+: 地形名中文化(用于 InfoPanel 加成区段)
func _terrain_cn(terrain_name: String, subtype: String = "") -> String:
	return CnLabels.terrain_cn(terrain_name, subtype)


# P2.6+: 指挥官名中文化(用于 InfoPanel 战斗加成区段)
func _commander_cn(co_id: String) -> String:
	return CnLabels.commander_cn(co_id)


func _color_name_cn(color_name: String) -> String:
	return CnLabels.color_name_cn(color_name)


func _team_cn(team: String) -> String:
	return CnLabels.team_cn(team)


# ============================================================
# 联机大厅 —— 逻辑已抽到 scripts/ui/lobby_controller.gd(挂 $Lobby 节点)
# 这里只保留 main 侧的入口与转发,节点/状态/信号全部由控制器自管。
# ============================================================

func _on_lobby_pressed() -> void:
	if lobby_view != null and is_instance_valid(lobby_view):
		lobby_view.open()


## mainline_controller 经 _main 转发过来的指挥官下拉刷新
func _setup_lobby_commander_options(unlocked: Array = []) -> void:
	if lobby_view != null and is_instance_valid(lobby_view):
		lobby_view._setup_lobby_commander_options(unlocked)


# T:96 — MainlineView 入口 thin wrapper(完整逻辑搬到 mainline_controller.open())
func _on_mainline_pressed() -> void:
	if mainline_view != null and is_instance_valid(mainline_view):
		mainline_view.open()


# Batch A:helper 留 main.gd(batch B 函数还在 main.gd 用)
func _commander_label(commander_id: String) -> String:
	return CnLabels.commander_label(commander_id)


func _set_node_visible(node: Node, value: bool) -> void:
	if node != null and is_instance_valid(node) and node is CanvasItem:
		(node as CanvasItem).visible = value


func _set_mainline_page(page: String) -> void:
	_mainline_page = page
	var showing_prepare := page == "prepare"
	_set_node_visible(ml_prep_summary, showing_prepare)
	_set_node_visible(ml_prep_tabs, showing_prepare)
	_set_node_visible(ml_prep_content, showing_prepare)
	_set_node_visible(ml_prep_start_btn, showing_prepare)
	_set_node_visible(ml_prep_refresh_btn, showing_prepare)
	_set_node_visible(ml_prep_action_btn, showing_prepare)
	_set_node_visible(ml_prep_alt_action_btn, showing_prepare)
	if ml_prep_hero_select != null and is_instance_valid(ml_prep_hero_select):
		_set_node_visible(ml_prep_hero_select.get_parent(), showing_prepare)


# P2:主线"准备好了"按钮 — 触发 /prepare/complete 写自动存档,
# response.body 应包含 AutoSaveCheckpointOut({label,auto_kind,saved_at});
# 我们把 auto_save 走 toast 让玩家看到 "💾 准备完毕,自动存档完毕 ✓ {label}"。
func _set_prepare_content(text: String) -> void:
	if ml_prep_content != null and is_instance_valid(ml_prep_content):
		ml_prep_content.text = text


func _is_mainline_already_active_response(body: Variant) -> bool:
	if not (body is Dictionary):
		return false
	var detail: Variant = body.get("detail", {})
	if detail is Dictionary:
		return str(detail.get("error", "")) == "mainline_already_active"
	return str(detail).contains("mainline_already_active")


func _on_settings_pressed() -> void:
	_update_status("设置面板将在下一轮实现喵~")


func _on_war_report_pressed() -> void:
	# 第 5 轮接,先 toggle 显示/隐藏战报浮层
	war_report_panel.visible = not war_report_panel.visible
	if war_report_panel.visible:
		war_report_button.text = "📜 关闭战报"
	else:
		war_report_button.text = "📜 战报"


func _on_war_report_close_pressed() -> void:
	war_report_panel.visible = false
	war_report_button.text = "📜 战报"


# ============================================================
# V2 第 4 轮:行动气泡 — 显示/隐藏 + 5 个 action
# ============================================================

func _show_action_bubble(unit_id: int, viewport_pos: Vector2, context: String = _ACTION_CONTEXT_INITIAL) -> void:
	_selected_unit_id = unit_id
	_refresh_action_bubble_buttons(unit_id, context)
	var selected_unit: Dictionary = GameState.get_unit(unit_id) if GameState != null else {}
	if action_title != null and is_instance_valid(action_title):
		action_title.text = "%s · 行动" % _unit_cn_name(selected_unit, "单位")
	# Keep this as a compact contextual menu anchored to the selected unit.
	# Board coordinates live under Camera2D while this panel lives in a
	# CanvasLayer, so viewport_pos must already be converted by tile_to_screen().
	var vp_size: Vector2 = get_viewport().get_visible_rect().size
	var visible_actions := 0
	var actions_height := 0.0
	for button in [move_btn, attack_btn, skill_btn, wait_btn, claim_btn, cancel_btn]:
		if button != null and is_instance_valid(button) and button.visible:
			visible_actions += 1
			actions_height += maxf(button.custom_minimum_size.y, button.get_combined_minimum_size().y)
	# The header occupies 42 px; the action list keeps 12 px side/bottom padding.
	# Derive height from each visible button so the shorter cancel row never
	# gets pushed into the ornamental bottom border.
	var bubble_size := Vector2(300.0, 94.0 + actions_height + float(max(0, visible_actions - 1)) * 4.0)
	action_bubble.size = bubble_size
	var viewport_safe := Rect2(Vector2(14.0, 108.0), Vector2(vp_size.x - 28.0, vp_size.y - 196.0))
	var safe_rect := viewport_safe
	var board_screen := Rect2()
	if board != null and board.has_method("screen_rect"):
		board_screen = board.screen_rect()
	var gap := 34.0
	var raw_candidates := {
		"right": viewport_pos + Vector2(gap, -bubble_size.y * 0.5),
		"left": viewport_pos + Vector2(-bubble_size.x - gap, -bubble_size.y * 0.5),
		"above": viewport_pos + Vector2(-bubble_size.x * 0.5, -bubble_size.y - gap),
		"below": viewport_pos + Vector2(-bubble_size.x * 0.5, gap),
	}
	if board_screen.size.x > 0.0:
		raw_candidates["left_gutter"] = Vector2(board_screen.position.x - bubble_size.x - 12.0, viewport_pos.y - bubble_size.y * 0.5)
		raw_candidates["right_gutter"] = Vector2(board_screen.end.x + 12.0, viewport_pos.y - bubble_size.y * 0.5)
	# On wide layouts the tactical menu belongs to the left HUD wing rather than
	# floating over the map. This creates a stable reading path and preserves the
	# selected unit and movement grid underneath.
	if left_hud_wing != null and is_instance_valid(left_hud_wing) and left_hud_wing.size.x >= bubble_size.x + 40.0:
		raw_candidates["left_gutter"] = Vector2(
			left_hud_wing.position.x + left_hud_wing.size.x - bubble_size.x - 20.0,
			left_hud_wing.position.y + 150.0
		)
	if right_hud_wing != null and is_instance_valid(right_hud_wing) and right_hud_wing.size.x >= bubble_size.x + 40.0:
		raw_candidates["right_gutter"] = Vector2(
			right_hud_wing.position.x + 20.0,
			viewport_pos.y - bubble_size.y * 0.5
		)
	var best_direction := "right"
	var pos: Vector2 = raw_candidates[best_direction]
	var best_score := INF
	for direction in raw_candidates.keys():
		var raw_pos: Vector2 = raw_candidates[direction]
		var candidate_pos := Vector2(
			clamp(raw_pos.x, safe_rect.position.x, max(safe_rect.position.x, safe_rect.end.x - bubble_size.x)),
			clamp(raw_pos.y, safe_rect.position.y, max(safe_rect.position.y, safe_rect.end.y - bubble_size.y))
		)
		var candidate_rect := Rect2(candidate_pos, bubble_size)
		var score: float = candidate_pos.distance_to(raw_pos) * 4.0
		# Prefer horizontal placement when equally clear, but never at the cost of
		# covering another unit. This keeps the menu connected to its source while
		# allowing crowded formations to use the space above or below.
		if direction == "left":
			score += 6.0
		elif direction == "above" or direction == "below":
			score += 14.0
		elif direction.ends_with("_gutter"):
			score -= 80.0
		for other in _all_units_including_self():
			var other_tile := Vector2i(int(other.get("x", 0)), int(other.get("y", 0)))
			var other_screen: Vector2 = board.tile_to_screen(other_tile) if board != null and board.has_method("tile_to_screen") else Vector2.ZERO
			var is_source := int(other.get("id", -1)) == unit_id
			var exclusion_size := 72.0 if is_source else 64.0
			var unit_rect := Rect2(other_screen - Vector2.ONE * exclusion_size * 0.5, Vector2.ONE * exclusion_size)
			if candidate_rect.intersects(unit_rect):
				var overlap_area: float = candidate_rect.intersection(unit_rect).get_area()
				score += (5000.0 if is_source else 1200.0) + overlap_area * 2.0
		if score < best_score:
			best_score = score
			best_direction = direction
			pos = candidate_pos
	action_bubble.position = pos
	if action_pointer != null and is_instance_valid(action_pointer):
		action_pointer.visible = not best_direction.ends_with("_gutter")
		action_pointer.rotation = 0.0
		action_pointer.scale = Vector2.ONE
		match best_direction:
			"left", "left_gutter":
				action_pointer.position = Vector2(bubble_size.x + 12.0, bubble_size.y * 0.5 - 10.0)
				action_pointer.scale.x = -1.0
			"above":
				action_pointer.position = Vector2(bubble_size.x * 0.5 + 10.0, bubble_size.y + 12.0)
				action_pointer.rotation = -PI * 0.5
			"below":
				action_pointer.position = Vector2(bubble_size.x * 0.5 - 10.0, -12.0)
				action_pointer.rotation = PI * 0.5
			"right_gutter", "right":
				action_pointer.position = Vector2(-12.0, bubble_size.y * 0.5 - 10.0)
	action_bubble.visible = true
	# Keyboard/gamepad users receive an explicit default action. The marker is
	# deliberately non-color-only and remains readable when focus glow is subtle.
	if InputState != null:
		InputState.board_focused = false
	for button in [move_btn, attack_btn, skill_btn, wait_btn, claim_btn, cancel_btn]:
		if button != null and is_instance_valid(button) and button.visible and not button.disabled:
			button.text = "▶ %s" % button.text
			button.grab_focus()
			break
	UIPanelFocus.grab_first_focusable(action_bubble)


func _refresh_action_bubble_buttons(unit_id: int, context: String) -> void:
	var ud: Dictionary = GameState.get_unit(unit_id) if GameState != null else {}
	attack_btn.text = "攻击"
	wait_btn.text = "待命"
	claim_btn.text = "占领"
	var has_unit := not ud.is_empty()
	var can_attack := has_unit and _compute_attack_targets(ud).size() > 0 and not bool(ud.get("has_acted", false))
	var active_skill := _available_active_skill(ud) if has_unit and not bool(ud.get("has_acted", false)) else ""
	var can_skill := active_skill != ""
	var can_claim := has_unit and _can_claim_here(ud)
	var can_move := false
	if has_unit:
		if context == _ACTION_CONTEXT_INITIAL:
			can_move = _can_initial_move(ud)
			move_btn.text = "移动"
		elif context == _ACTION_CONTEXT_POST_MOVE:
			can_move = _can_continue_move(ud)
			move_btn.text = "继续移动"
		else:
			can_move = _can_continue_move_after_action(ud)
			move_btn.text = "继续移动"
	if context == _ACTION_CONTEXT_POST_ACTION:
		can_attack = false
		can_skill = false
		can_claim = false
	_set_action_button(move_btn, can_move)
	_set_action_button(attack_btn, can_attack)
	_set_action_button(skill_btn, can_skill)
	_set_action_button(wait_btn, has_unit)
	_set_action_button(claim_btn, can_claim)
	if skill_btn != null and is_instance_valid(skill_btn):
		skill_btn.text = _skill_cn(active_skill) if active_skill != "" else "技能"
	if claim_btn != null and is_instance_valid(claim_btn):
		claim_btn.text = "占领"


func _set_action_button(btn: Button, can_show: bool) -> void:
	if btn == null or not is_instance_valid(btn):
		return
	btn.visible = can_show
	btn.disabled = not can_show


func _can_initial_move(ud: Dictionary) -> bool:
	if bool(ud.get("has_moved", false)):
		return false
	if int(ud.get("mp", int(ud.get("mov", 0)))) <= 0:
		return false
	return _compute_reachable_tiles_full(ud).size() > 1


func _can_continue_move(ud: Dictionary) -> bool:
	return int(ud.get("mp", 0)) > 0


func _can_continue_move_after_action(ud: Dictionary) -> bool:
	return int(ud.get("mp", 0)) > 0 and _unit_can_move_after_action(ud)


func _unit_can_move_after_action(ud: Dictionary) -> bool:
	if ud.has("can_move_after_action"):
		return bool(ud.get("can_move_after_action", false))
	var unit_type := str(ud.get("unit_type", ""))
	return unit_type == "archer" or unit_type == "knight"


func _can_claim_here(ud: Dictionary) -> bool:
	if bool(ud.get("has_acted", false)):
		return false
	var pos := Vector2i(int(ud.get("x", 0)), int(ud.get("y", 0)))
	var tile: Dictionary = {}
	if board != null and board.tile_lookup != null:
		tile = board.tile_lookup.get(pos, {})
	if tile.is_empty() and GameState != null:
		tile = GameState.get_tile(pos.x, pos.y)
	if tile.is_empty():
		return false
	var terrain := str(tile.get("terrain", ""))
	var subtype := str(tile.get("subtype", ""))
	var claimable := terrain == "village" or terrain == "barracks" or terrain == "castle_vault" or terrain == "castle" or subtype == "castle_vault"
	if not claimable:
		return false
	var owner_id := int(tile.get("owner_id", -1)) if tile.get("owner_id", null) != null else -1
	return owner_id != _player_id


func _available_active_skill(ud: Dictionary) -> String:
	var skill_id := _active_skill_of(ud)
	if skill_id == "":
		return ""
	if skill_id == "arcane_strike":
		return skill_id if _arcane_targets(ud).size() > 0 else ""
	if skill_id == "heal":
		return skill_id if _heal_targets(ud).size() > 0 else ""
	if skill_id == "sing":
		return skill_id if _sing_targets(ud).size() > 0 else ""
	return ""


func _hide_action_bubble() -> void:
	action_bubble.visible = false
	_selected_unit_id = -1
	_return_focus_to_board_if_game_active()


func _return_focus_to_board_if_game_active() -> void:
	if _current_view != "game":
		return
	if InputState == null:
		return
	if action_bubble != null and is_instance_valid(action_bubble) and action_bubble.visible:
		return
	if board == null or not is_instance_valid(board) or board.map_size.x <= 0 or board.map_size.y <= 0:
		return
	InputState.board_focused = true
	get_viewport().gui_release_focus()


func _on_move_pressed() -> void:
	# M4.1 进入"移动模式":单位已经在 _move_reachable_set 里,
	# 等用户点击 board emit_tile_clicked → _on_board_tile_clicked
	if _selected_unit_id <= 0:
		_update_status("移动: 请先选中单位")
		return
	# Immediate move feedback clears the old cache. Rebuild it from the unit's
	# remaining MP so a visible "继续移动" command always works.
	if _move_reachable_set.is_empty():
		var selected_unit: Dictionary = GameState.get_unit(_selected_unit_id) if GameState != null else {}
		if not selected_unit.is_empty():
			_move_reachable_set = _compute_reachable_tiles_full(selected_unit)
	if _move_reachable_set.is_empty() or _move_reachable_set.size() <= 1:
		_update_status("移动: 该单位没有可达格")
		return
	_move_mode_unit_id = _selected_unit_id
	_update_status("移动: 点击蓝色高亮的格子 (右键/空白取消)")
	_hide_action_bubble()


func _on_attack_pressed() -> void:
	# M4.2:进入"攻击模式" — 红色 attack range outline + 落点是敌方单位
	if _selected_unit_id <= 0:
		_update_status("攻击: 请先选中单位")
		return
	var ud: Dictionary = GameState.get_unit(_selected_unit_id) if GameState != null else {}
	if ud.is_empty():
		_update_status("攻击: 找不到单位 #%d" % _selected_unit_id)
		return
	# Compute attack targets by Manhattan range only; no terrain or unit blockers.
	var targets: Dictionary = _compute_attack_targets(ud)
	_attack_mode_unit_id = _selected_unit_id
	_attack_targets = targets
	# 即使没目标也显示红色范围 outline — 让用户能看到攻击射程
	var range_tiles: Array = _get_attack_range_tiles(ud)
	if range_tiles.size() > 0 and board != null:
		board.show_attack_marks(range_tiles)
	if targets.is_empty():
		_update_status("攻击: 射程内无敌人(红框显示攻击范围 %d 格)" % range_tiles.size())
	else:
		_update_status("攻击: 点击红色高亮范围内的敌方单位 (可选 %d)" % targets.size())
	_hide_action_bubble()


# 取消移动/攻击模式的统一接口
func _cancel_action_mode() -> void:
	if _move_mode_unit_id > 0 or _attack_mode_unit_id > 0 or _skill_mode_unit_id > 0:
		_move_mode_unit_id = -1
		_move_reachable_set = {}
		_clear_move_preview_path()
		_attack_mode_unit_id = -1
		_attack_targets = {}
		_skill_mode_unit_id = -1
		_skill_targets = {}
		if board != null:
			board.clear_selection_marks()
		_update_status("已取消行动模式")


# 2026-08-09:board.gd 棋盘光标按取消(A / Esc)时调。
# 包装 _cancel_action_mode + _hide_action_bubble + 清光标,
# 行为对齐 main.gd 里"右键空地"的分支(也调这俩)。
func _cursor_cancel_action() -> void:
	_cancel_action_mode()
	_hide_action_bubble()
	if board != null and board.has_method("clear_selection_marks"):
		board.clear_selection_marks()
	# 重置光标到第一个我方单位,避免"取消完光标停在地块上看起来像死锁"
	if board != null and is_instance_valid(board) and board.map_size.x > 0:
		InputState.cursor_cell = _find_cursor_initial_cell()


# 行动气泡的"取消"按钮 + 右键取消都走这里
func _on_cancel_pressed() -> void:
	_cancel_action_mode()
	_hide_action_bubble()
	_update_status("已取消(右键亦可)")


# Compute attackable enemy units by Manhattan range only.
# Damage remains server-authoritative via calculate_damage / unit_attacked events.
func _player_team_key(player_id: int) -> String:
	var p: Dictionary = GameState.get_player(player_id) if GameState != null else {}
	if p.is_empty():
		return "player_%d" % player_id
	var team_v: Variant = p.get("team", null)
	if team_v != null and str(team_v) != "":
		return str(team_v)
	return "player_%d" % player_id


func _compute_attack_targets(attacker: Dictionary) -> Dictionary:
	var range_tiles: Array = _get_attack_range_tiles(attacker)
	if range_tiles.is_empty():
		return {}
	var me_pid: int = int(_player_id)
	var my_team_key: String = _player_team_key(me_pid)
	var out: Dictionary = {}
	for rt in range_tiles:
		var rt_v := Vector2i(int(rt.x), int(rt.y))
		for p in GameState.players:
			if not p is Dictionary:
				continue
			var candidate_pid: int = int(p.get("id", -1))
			if candidate_pid <= 0 or _player_team_key(candidate_pid) == my_team_key:
				continue
			for uu in p.get("units", []):
				if not uu is Dictionary:
					continue
				if int(uu.get("x", -1)) != rt_v.x or int(uu.get("y", -1)) != rt_v.y:
					continue
				out[int(uu.get("id", -1))] = {
					"x": rt_v.x,
					"y": rt_v.y,
					"defender_name": str(uu.get("name", uu.get("unit_type", "?"))),
					"unit_type": str(uu.get("unit_type", "")),
					"hp": int(uu.get("hp", 0)),
					"max_hp": int(uu.get("max_hp", uu.get("hp", 0))),
				}
	return out


func _get_attack_range_tiles(attacker: Dictionary) -> Array:
	var max_range: int = int(attacker.get("attack_range", 1))
	if (attacker.get("skills", []) as Array).has("snipe"):
		max_range += 1
	# 测试钩子 — `BB_ATTACK_FORCE_RANGE=N` 把范围设为 N,用于 e2e 截图
	# 验证(spawn 太远的地图也能强制打到敌人)。**仅 dev/test 用**。
	if OS.has_environment("BB_ATTACK_FORCE_RANGE"):
		max_range = int(OS.get_environment("BB_ATTACK_FORCE_RANGE"))
	var min_range: int = int(attacker.get("min_attack_range", 0))
	var pos := Vector2i(int(attacker.get("x", 0)), int(attacker.get("y", 0)))
	var size_v: int = 15
	if board != null and board.map_size.x > 0:
		size_v = board.map_size.x
	return MapLogic.attack_range_tiles(pos, max_range, min_range, size_v)


# ============================================================
# ConfirmDialog — 通用 Yes/No 弹窗 helper
# 用法: _show_confirm("标题", "正文", Callable(self, "_on_yes"), Callable(self, "_on_no"))
# 设计要点:
#   * 一次性 Callable — yes/no 触发后立刻清空,避免重复点 / 旧 callback 残留
#   * on_no 可省略(取消按钮 = 关闭即可,不做事)
#   * 顶层 Panel,与 view 切换解耦 — 不依赖 _show_view()
# ============================================================

func _show_confirm(title: String, body: String, on_yes: Callable, on_no: Callable = Callable()) -> void:
	_confirm_yes_callback = on_yes
	_confirm_no_callback = on_no
	if confirm_title_label != null and is_instance_valid(confirm_title_label):
		confirm_title_label.text = title
	if confirm_body_label != null and is_instance_valid(confirm_body_label):
		confirm_body_label.text = body
	if confirm_dialog != null and is_instance_valid(confirm_dialog):
		confirm_dialog.visible = true
		# 2026-08-09:grab focus 到默认按钮 = No(更安全,误按不会真退出)
		UIPanelFocus.grab_on_show(confirm_dialog, confirm_no_btn)


func _hide_confirm() -> void:
	_confirm_yes_callback = Callable()
	_confirm_no_callback = Callable()
	if confirm_dialog != null and is_instance_valid(confirm_dialog):
		confirm_dialog.visible = false


func _on_confirm_yes_pressed() -> void:
	# 在 hide 之前先 cache callback,hide() 会立刻清空
	var cb: Callable = _confirm_yes_callback
	_hide_confirm()
	if cb.is_valid():
		cb.call()


func _on_confirm_no_pressed() -> void:
	var cb: Callable = _confirm_no_callback
	_hide_confirm()
	if cb.is_valid():
		cb.call()


func _show_attack_confirm(attacker_id: int, target_id: int) -> void:
	var attacker: Dictionary = GameState.get_unit(attacker_id) if GameState != null else {}
	var info: Dictionary = _attack_targets.get(target_id, {})
	if attacker.is_empty() or info.is_empty():
		_update_status("攻击确认失败: 缺少单位信息")
		return
	_pending_attack_attacker_id = attacker_id
	_pending_attack_target_id = target_id
	if attack_confirm_body != null and is_instance_valid(attack_confirm_body):
		attack_confirm_body.text = _build_attack_confirm_text(attacker, info)
	if attack_confirm_panel != null and is_instance_valid(attack_confirm_panel):
		attack_confirm_panel.visible = true
		# 2026-08-09:grab focus 到 Cancel(默认取消更安全,等 forecast 出来再确认)
		UIPanelFocus.grab_on_show(attack_confirm_panel, attack_cancel_btn)
	_show_attack_forecast_loading(attacker, info)
	if _game_id > 0 and _player_id > 0 and NetworkClient != null:
		NetworkClient.forecast_attack(
			_game_id,
			_player_id,
			attacker_id,
			target_id,
			Callable(self, "_on_attack_forecast_response").bind(attacker_id, target_id, info)
		)
	_update_status("确认攻击目标 #%d" % target_id)


func _build_attack_confirm_text(attacker: Dictionary, target_info: Dictionary) -> String:
	var attacker_name := _unit_cn_name(attacker, "单位")
	var target_name := _unit_cn_name(target_info, "目标")
	var ax := int(attacker.get("x", 0))
	var ay := int(attacker.get("y", 0))
	var tx := int(target_info.get("x", 0))
	var ty := int(target_info.get("y", 0))
	var dist: int = abs(ax - tx) + abs(ay - ty)

	# 双方基础信息(取自 GameState 已有字段,后端无需扩 schema)
	var attacker_lv := int(attacker.get("level", 1))
	var target_lv := int(target_info.get("level", 1))
	var attacker_morale := int(attacker.get("morale", 0))
	var target_morale := int(target_info.get("morale", 0))
	var attacker_hp := int(attacker.get("hp", 0))
	var attacker_max_hp := int(attacker.get("max_hp", attacker_hp))
	if attacker_max_hp <= 0:
		attacker_max_hp = max(1, attacker_hp)
	var target_hp := int(target_info.get("hp", 0))
	var target_max_hp := int(target_info.get("max_hp", target_hp))
	if target_max_hp <= 0:
		target_max_hp = max(1, target_hp)
	var attacker_atk := int(attacker.get("atk", 0))
	var attacker_matk := int(attacker.get("matk", 0))
	var target_def := int(target_info.get("def_", 0))
	var target_mdef := int(target_info.get("mdef", 0))
	var atk_min := int(attacker.get("min_attack_range", 0))
	var atk_range := int(attacker.get("attack_range", 1))
	var in_range := dist > atk_min and dist <= atk_range

	var attacker_stars := "★".repeat(max(0, attacker_morale)) + "☆".repeat(max(0, 3 - attacker_morale))
	var target_stars := "★".repeat(max(0, target_morale)) + "☆".repeat(max(0, 3 - target_morale))

	var attacker_card := "[color=#f4e8c1][b]⚔ 攻击方[/b][/color]\n[b]%s[/b] · Lv.%d · %s\n[color=#c9a14a]攻 %d[/color] · [color=#c9a14a]魔攻 %d[/color]\n[color=#5fa8e8]生命 %d/%d[/color]" % [
		attacker_name, attacker_lv, attacker_stars,
		attacker_atk, attacker_matk, attacker_hp, attacker_max_hp,
	]
	var target_card := "[color=#f4e8c1][b]🛡 目标[/b][/color]\n[b]%s[/b] · Lv.%d · %s\n[color=#c9a14a]防 %d[/color] · [color=#c9a14a]魔防 %d[/color]\n[color=#5fa8e8]生命 %d/%d[/color]" % [
		target_name, target_lv, target_stars,
		target_def, target_mdef, target_hp, target_max_hp,
	]

	var range_text: String
	if in_range:
		range_text = "距离 %d · 攻击范围 %d < d ≤ %d" % [dist, atk_min, atk_range]
	else:
		range_text = "[color=#c63a3a]距离 %d 超出攻击范围(需 %d < d ≤ %d)[/color]" % [dist, atk_min, atk_range]

	return "%s\n\n%s\n\n%s\n\n[color=#a89878]等待战斗预测…[/color]" % [
		attacker_card, target_card, range_text
	]


func _show_attack_forecast_loading(attacker: Dictionary, target_info: Dictionary) -> void:
	if unit_info_title != null and is_instance_valid(unit_info_title):
		unit_info_title.text = "战斗预测"
	if unit_info != null and is_instance_valid(unit_info):
		unit_info.bbcode_enabled = true
		var attacker_name := _unit_cn_name(attacker, "单位")
		var target_name := _unit_cn_name(target_info, "目标")
		unit_info.text = "[b]%s[/b] → [color=#f0c75e][b]%s[/b][/color]\n正在计算战斗预测..." % [
			attacker_name, target_name
		]


func _on_attack_forecast_response(body: Variant, code: int = 0, attacker_id: int = -1, target_id: int = -1, target_info: Dictionary = {}) -> void:
	if attacker_id != _pending_attack_attacker_id or target_id != _pending_attack_target_id:
		return
	var attacker: Dictionary = GameState.get_unit(attacker_id) if GameState != null else {}
	if unit_info_title != null and is_instance_valid(unit_info_title):
		unit_info_title.text = "战斗预测"
	if unit_info == null or not is_instance_valid(unit_info):
		return
	unit_info.bbcode_enabled = true
	if code < 200 or code >= 300 or not (body is Dictionary):
		unit_info.text = "无法预测本次攻击。\n仍可手动确认攻击，后端会校验真实结果。"
		return
	unit_info.text = _build_attack_forecast_info_text(body, attacker, target_info)


func _build_attack_forecast_info_text(forecast: Dictionary, attacker: Dictionary, target_info: Dictionary) -> String:
	var attacker_name: String = _unit_cn_name(attacker, "我方单位")
	var target_name: String = _unit_cn_name(target_info, "目标")
	var attacker_hp: int = int(attacker.get("hp", int(forecast.get("attacker_hp_after", 0))))
	var attacker_max_hp: int = max(1, int(attacker.get("max_hp", attacker_hp)))
	var target_hp: int = int(target_info.get("hp", int(forecast.get("target_hp_after", 0))))
	var target_max_hp: int = max(1, int(target_info.get("max_hp", target_hp)))
	var damage: int = int(forecast.get("damage", 0))
	var target_after: int = int(forecast.get("target_hp_after", max(0, target_hp - damage)))
	var counter_damage: int = int(forecast.get("counter_damage", 0))
	var attacker_after: int = int(forecast.get("attacker_hp_after", max(0, attacker_hp - counter_damage)))
	var is_kill: bool = bool(forecast.get("is_kill", false))
	var counter_will_kill: bool = bool(forecast.get("counter_will_kill", false))
	var def_bonus: int = int(forecast.get("target_def_bonus", 0))
	var lines: Array = [
		"[color=#f0c75e][b]战斗预测[/b][/color]",
		"[b]%s[/b] → [color=#f0c75e][b]%s[/b][/color]" % [attacker_name, target_name],
		"预计伤害: [color=#c63a3a][b]%d[/b][/color]" % damage,
		"目标剩余生命: %d/%d%s" % [target_after, target_max_hp, "  可击杀" if is_kill else ""],
	]
	if counter_damage > 0:
		lines.append("反击 %d，我方剩余生命 %d/%d%s" % [
			counter_damage,
			attacker_after,
			attacker_max_hp,
			"  可能被击倒" if counter_will_kill else "",
		])
	elif is_kill:
		lines.append("目标已被击杀,无反击")
	else:
		# COUNTER_IMMUNE_SKILLS 暂为空,只能因距离过远无法反击
		var ax := int(attacker.get("x", 0))
		var ay := int(attacker.get("y", 0))
		var tx := int(target_info.get("x", 0))
		var ty := int(target_info.get("y", 0))
		var dist: int = abs(ax - tx) + abs(ay - ty)
		lines.append("目标无法反击(距离 %d,超出反击范围)" % dist)
	lines.append("地形防御: +%d" % def_bonus)
	return "\n".join(lines)


func _unit_cn_name(unit: Dictionary, fallback: String = "单位") -> String:
	return CnLabels.unit_cn_name(unit, fallback)


func _hide_attack_confirm() -> void:
	_pending_attack_attacker_id = -1
	_pending_attack_target_id = -1
	if attack_confirm_panel != null and is_instance_valid(attack_confirm_panel):
		attack_confirm_panel.visible = false


func _on_attack_confirm_pressed() -> void:
	if _pending_attack_attacker_id <= 0 or _pending_attack_target_id <= 0:
		_hide_attack_confirm()
		return
	var attacker_id := _pending_attack_attacker_id
	var target_id := _pending_attack_target_id
	_hide_attack_confirm()
	_attack_unit_to(attacker_id, target_id)


func _on_attack_cancel_pressed() -> void:
	_hide_attack_confirm()
	_cancel_action_mode()


# M4.2:发 POST /games/{id}/attack
func _apply_immediate_attack_feedback(attacker_id: int, target_id: int) -> void:
	_attack_mode_unit_id = -1
	_attack_targets = {}
	_hide_attack_confirm()
	if board != null:
		var target: Dictionary = GameState.get_unit(target_id) if GameState != null else {}
		if not target.is_empty():
			var cell := Vector2i(int(target.get("x", 0)), int(target.get("y", 0)))
			board.spawn_floating_text_at_cell(cell, "!", "#f0c75e", "attack_preview")
		board.clear_selection_marks()
	_hide_action_bubble()
	_update_status("攻击指令已下达: #%d -> #%d" % [attacker_id, target_id])


func _attack_unit_to(attacker_id: int, target_id: int) -> void:
	if _game_id <= 0 or _player_id <= 0:
		return
	# 8d: 可选 pre-action 对话
	if UserSettings.get_value("dialog.v1.attack_confirm", false):
		await DialogManager.play([{
			"speaker": "",
			"text": "即将发动攻击,确认?",
			"type": "narration",
		}])
	_apply_immediate_attack_feedback(attacker_id, target_id)
	NetworkClient.action_attack(
		_game_id, _player_id, attacker_id, target_id,
		Callable(self, "_on_attack_response").bind(attacker_id, target_id),
	)


## 8d: 攻击响应 — 成功后播旁白(lethal 优先,非致命带反击)
## ⚠ 致命攻击后端只发 kill 不发 attack(WS 通道),但本 handler 走 REST 永远触发
func _on_attack_response(body: Variant, code: int, attacker_id: int, target_id: int) -> void:
	if code < 200 or code >= 300:
		_update_status("攻击失败 (HTTP %d)" % code)
		return
	if not (body is Dictionary):
		return
	var turn: int = int(GameState.game_summary.get("turn_number", 0))
	if not DialogManager.record_attack_shown(attacker_id, target_id, turn):
		return
	if DialogManager.is_playing():
		return
	# AttackResult 字段:damage / is_kill / counter_damage;hits[] 数组含 is_crit
	var hits: Array = (body.get("hits", []) as Array)
	var dmg: int = int(body.get("damage", hits[0].get("damage", 0) if not hits.is_empty() else 0))
	var is_crit: bool = bool(hits[0].get("is_crit", false) if not hits.is_empty() else false)
	var is_kill: bool = bool(body.get("is_kill", false))
	var counter: int = int(body.get("counter_damage", 0))
	var a: Dictionary = GameState.get_unit(attacker_id) if GameState != null else {}
	var t: Dictionary = GameState.get_unit(target_id) if GameState != null else {}
	var a_name: String = str(a.get("display_cn", a.get("unit_type", "?"))) if not a.is_empty() else "?"
	var t_name: String = str(t.get("display_cn", t.get("unit_type", "?"))) if not t.is_empty() else "?"
	var crit_str: String = " · 暴击" if is_crit else ""
	var lines: Array = [{
		"speaker": "",
		"text": ("「%s」击破「%s」(%d 伤害%s)。" % [a_name, t_name, dmg, crit_str]) if is_kill else ("「%s」对「%s」造成 %d 伤害%s。" % [a_name, t_name, dmg, crit_str]),
		"type": "narration",
	}]
	if not is_kill and counter > 0:
		lines.append({
			"speaker": "",
			"text": "「%s」反击,造成 %d 伤害。" % [t_name, counter],
			"type": "narration",
		})
	DialogManager.play(lines)


func _active_skill_of(ud: Dictionary) -> String:
	# 返回单位的首个主动技能 id;被动技能(snipe/double_strike 走 attack 端点)返回空。
	# 主动技能目录见 server app/classes/units/skills(heal, arcane_strike)。
	# 新增主动技能需同步此处与 _on_skill_pressed 分支。
	var skills: Array = (ud.get("skills", []) as Array)
	if skills.has("heal"):
		return "heal"
	if skills.has("sing"):
		return "sing"
	if skills.has("arcane_strike"):
		return "arcane_strike"
	return ""


func _arcane_targets(ud: Dictionary) -> Dictionary:
	var pos_h := Vector2i(int(ud.get("x", 0)), int(ud.get("y", 0)))
	var me_pid2: int = int(_player_id)
	var out: Dictionary = {}
	for uu in _all_units_including_self():
		var adx: int = abs(int(uu.get("x", 0)) - pos_h.x)
		var ady: int = abs(int(uu.get("y", 0)) - pos_h.y)
		var manh: int = adx + ady
		if manh < 1 or manh > 2: continue
		if int(uu.get("player_id", -1)) == me_pid2: continue
		if int(uu.get("hp", 0)) <= 0: continue
		out[int(uu.get("id", -1))] = {
			"x": int(uu.get("x", 0)),
			"y": int(uu.get("y", 0)),
			"name": str(uu.get("name", uu.get("unit_type", "?"))),
			"hp": int(uu.get("hp", 0)),
			"max_hp": int(uu.get("max_hp", 0)),
		}
	return out


func _heal_targets(ud: Dictionary) -> Dictionary:
	var pos_h := Vector2i(int(ud.get("x", 0)), int(ud.get("y", 0)))
	var me_pid2: int = int(_player_id)
	var out: Dictionary = {}
	for uu in _all_units_including_self():
		var dx: int = abs(int(uu.get("x", 0)) - pos_h.x)
		var dy: int = abs(int(uu.get("y", 0)) - pos_h.y)
		var cheb: int = max(dx, dy)
		if cheb != 1: continue
		if int(uu.get("player_id", -1)) != me_pid2: continue
		var hp_i: int = int(uu.get("hp", 0))
		var max_hp_i: int = int(uu.get("max_hp", hp_i + 1))
		if hp_i >= max_hp_i: continue
		out[int(uu.get("id", -1))] = {
			"x": int(uu.get("x", 0)),
			"y": int(uu.get("y", 0)),
			"name": str(uu.get("name", uu.get("unit_type", "?"))),
			"hp": hp_i,
			"max_hp": max_hp_i,
		}
	return out


func _sing_targets(ud: Dictionary) -> Dictionary:
	var pos_h := Vector2i(int(ud.get("x", 0)), int(ud.get("y", 0)))
	var me_pid2: int = int(_player_id)
	var self_id: int = int(ud.get("id", -1))
	var out: Dictionary = {}
	for uu in _all_units_including_self():
		var unit_id: int = int(uu.get("id", -1))
		if unit_id == self_id:
			continue
		var dx: int = abs(int(uu.get("x", 0)) - pos_h.x)
		var dy: int = abs(int(uu.get("y", 0)) - pos_h.y)
		var cheb: int = max(dx, dy)
		if cheb != 1: continue
		if int(uu.get("player_id", -1)) != me_pid2: continue
		if int(uu.get("hp", 0)) <= 0: continue
		if not bool(uu.get("has_acted", false)) and not bool(uu.get("has_moved", false)):
			continue
		out[unit_id] = {
			"x": int(uu.get("x", 0)),
			"y": int(uu.get("y", 0)),
			"name": str(uu.get("name", uu.get("unit_type", "?"))),
			"hp": int(uu.get("hp", 0)),
			"max_hp": int(uu.get("max_hp", 0)),
		}
	return out


func _enter_arcane_mode(ud: Dictionary) -> void:
	# arcane_strike: Manhattan 距离 1-2 内的敌方存活单位
	var out: Dictionary = _arcane_targets(ud)
	if out.is_empty():
		_update_status("奥术冲击: 1-2 格内无敌方目标")
		return
	_pending_skill_id = "arcane_strike"
	_skill_mode_unit_id = _selected_unit_id
	_skill_targets = out
	if board != null:
		var tiles: Array = []
		for k in out.keys():
			tiles.append(Vector2i(int(out[k].get("x", 0)), int(out[k].get("y", 0))))
		board.show_attack_marks(tiles)
	_update_status("奥术冲击: 点击红框内敌人 (可选 %d)" % out.size())
	_hide_action_bubble()


func _on_skill_pressed() -> void:
	# M4.3:进入治疗模式 — 用 healer 唯一默认技能 "heal"
	if _selected_unit_id <= 0:
		_update_status("技能: 请先选中单位")
		return
	var ud: Dictionary = GameState.get_unit(_selected_unit_id) if GameState != null else {}
	if ud.is_empty():
		_update_status("技能: 找不到单位")
		return
	# 仅 healer 默认技能 — 检查 skills 数组
	var skill_id: String = _active_skill_of(ud)
	if skill_id == "":
		_update_status("技能: 该单位无可用主动技能")
		return
	if skill_id == "arcane_strike":
		_enter_arcane_mode(ud)
		return
	# 计算 8-邻接范围内 HP<max_hp 的友军
	if skill_id == "sing":
		var sing_out: Dictionary = _sing_targets(ud)
		if sing_out.is_empty():
			_update_status("Sing: no adjacent acted ally")
			return
		_pending_skill_id = "sing"
		_skill_mode_unit_id = _selected_unit_id
		_skill_targets = sing_out
		if board != null:
			var sing_tiles: Array = []
			for k in sing_out.keys():
				sing_tiles.append(Vector2i(int(sing_out[k].get("x", 0)), int(sing_out[k].get("y", 0))))
			board.show_attack_marks(sing_tiles)
		_update_status("Sing: choose acted ally (%d)" % sing_out.size())
		_hide_action_bubble()
		return
	var out: Dictionary = _heal_targets(ud)
	if out.is_empty():
		_update_status("治疗: 8-邻内无伤兵")
		return
	_pending_skill_id = "heal"
	_skill_mode_unit_id = _selected_unit_id
	_skill_targets = out
	if board != null:
		var tiles: Array = []
		for k in out.keys():
			tiles.append(Vector2i(int(out[k].get("x", 0)), int(out[k].get("y", 0))))
		board.show_attack_marks(tiles)
	_update_status("治疗: 点击蓝框内伤兵 (可选 %d)" % out.size())
	_hide_action_bubble()


# M4.5:发 POST /games/{id}/recruit
# 客户端不该"校验"foreign / occupied — server 是 source of truth
# (game/app/routes/actions.py:recruit_unit)。这里只发。
func _recruit_unit_to(tile_x: int, tile_y: int, unit_type: String) -> void:
	if _game_id <= 0 or _player_id <= 0: return
	_update_status("正在招募%s到 (%d, %d)..." % [_unit_type_cn(unit_type), tile_x, tile_y])
	NetworkClient.action_recruit(_game_id, _player_id, tile_x, tile_y, unit_type, Callable(self, "_on_recruit_response"))
	_hide_action_bubble()


func _on_recruit_response(body: Variant, code: int = 0) -> void:
	if code < 200 or code >= 300:
		var msg := "招募失败"
		if body is Dictionary:
			msg = "招募失败: %s" % str(body.get("detail", body.get("message", msg)))
		_update_status(msg)
		return
	if not (body is Dictionary):
		_update_status("招募完成")
		return
	var unit_type := str(body.get("new_unit_type", "unit"))
	var unit_name := _unit_type_cn(unit_type)
	var cost := int(body.get("cost", 0))
	var gold_remaining := int(body.get("gold_remaining", -1))
	if gold_remaining >= 0:
		_update_status("招募成功: %s · -%d 金币 · 剩余 %d" % [unit_name, cost, gold_remaining])
	else:
		_update_status("招募成功: %s · -%d 金币" % [unit_name, cost])
	if _game_id > 0:
		NetworkClient.get_game_state(_game_id, Callable(self, "_on_state_response"))
	# 8e: 招募后旁白
	if not DialogManager.is_playing():
		DialogManager.show_dialog({
			"speaker": "",
			"text": "新「%s」已加入战场 (花费 %d 金币)。" % [unit_name, cost],
			"type": "narration",
		})


# S:4 适配 — 在 _unhandled_input 的空地点击分支里,加 empty-my-barracks → 招募入口
# 对应 web 行为(见 game/app/web/app.js:3012-3024):
#   !occupant && isMyTurn + tile.terrain == "barracks" && tile.owner_id == me_pid
#   → showRecruitModal 弹 5 类单位的列表
#
# 完整 modal 是后续工作;目前 status 显示可以招募的单位集合,
# 用户输 unit_type 字符串就 POST(简版)。


# T:7:把选中单位的属性填到 InfoPanel.UnitInfo(顶级 RichTextLabel)。
# 字段取自 server UnitOut schema(godot 客户端不复制公式)。
func _refresh_unit_info(ud: Dictionary) -> void:
	if unit_info == null or not is_instance_valid(unit_info):
		return
	if info_panel != null and is_instance_valid(info_panel):
		info_panel.visible = true
	_set_board_inspect_card_visible(true)
	unit_info.bbcode_enabled = true
	var name: String = _unit_cn_name(ud, "单位")
	var lvl: int = int(ud.get("level", 1))
	var hp: int = int(ud.get("hp", 0))
	var max_hp: int = max(1, int(ud.get("max_hp", 1)))
	var mp: int = int(ud.get("mp", 0))
	var max_mp: int = int(ud.get("max_mp", 0))
	var mov: int = int(ud.get("mov", int(ud.get("move_points", 5))))
	var atk: int = int(ud.get("atk", 0))
	var def: int = int(ud.get("def_", 0))
	var matk: int = int(ud.get("matk", 0))
	var mdef: int = int(ud.get("mdef", 0))
	var range_min: int = int(ud.get("min_attack_range", 0))
	var range_max: int = int(ud.get("attack_range", 1))
	var morale: int = int(ud.get("morale", 0))
	var skills: Array = (ud.get("skills", []) as Array)
	var pos := Vector2i(int(ud.get("x", 0)), int(ud.get("y", 0)))
	var owner_pid: int = int(ud.get("player_id", int(ud.get("owner_id", -1))))
	var color_name: String = str(ud.get("color", "red"))
	var cur_pid_v: Variant = GameState.current_player_id if GameState != null else null
	var cur_pid: int = -1 if cur_pid_v == null else int(cur_pid_v)
	var is_mine: bool = (owner_pid == _player_id and owner_pid == cur_pid)
	var can_act: bool = not bool(ud.get("has_acted", false)) and is_mine
	var owner_str: String = ("敌方 %s" % _color_emoji(color_name)) if not is_mine else ("[color=#f0c75e]%s[/color] (你)" % _color_emoji(color_name))
	# Bug fix: GDScript 的 str(null) 返回字面字符串 "<null>",跟空字符串
	# 比较仍然不为空 → 之前会把没有 hero_id 的普通单位误判成英雄。
	# 显式判断 Variant 类型后再 stringify。
	var hero_id_v: Variant = ud.get("hero_id", null)
	var hero_id: String = "" if hero_id_v == null else str(hero_id_v)
	_set_unit_info_portrait(ud)
	if unit_info != null and is_instance_valid(unit_info):
		unit_info.offset_left = 172.0 if hero_portrait_panel.visible else 44.0
	if hero_portrait_caption != null and is_instance_valid(hero_portrait_caption):
		hero_portrait_caption.text = "%s · %s" % [name, "未行动" if can_act else "已行动"]
	if unit_info_title != null and is_instance_valid(unit_info_title):
		unit_info_title.text = name
	if unit_info_subtitle != null and is_instance_valid(unit_info_subtitle):
		var profession := _unit_type_cn(str(ud.get("unit_type", "unit")))
		var rank := "英雄" if hero_id != "" else "部队"
		unit_info_subtitle.text = "%s · %s Lv.%d · %s" % [profession, rank, lvl, "未行动" if can_act else "已行动"]
	var skill_names: Array[String] = []
	for skill in skills:
		skill_names.append(_skill_cn(str(skill)))
	var compact_hud := DisplayServer.window_get_size().x <= 1366
	var stat_gap := " · " if compact_hud else "       "
	var lines: Array = [
		"[color=#a89878]位置 (%d, %d)[/color] · %s" % [pos.x, pos.y, owner_str],
		("[color=#f4e8c1]生命[/color] %d/%d%s[color=#5fa8e8]能量[/color] %d/%d" % [hp, max_hp, stat_gap, mp, max_mp]) if max_mp > 0 else ("[color=#f4e8c1]生命[/color] %d/%d" % [hp, max_hp]),
		"[color=#c9a14a]攻[/color] %d%s[color=#c9a14a]防[/color] %d" % [atk, stat_gap, def],
		"[color=#c9a14a]魔攻[/color] %d%s[color=#c9a14a]魔防[/color] %d" % [matk, stat_gap, mdef],
		"[color=#a89878]移动[/color] %d%s[color=#a89878]射程[/color] %d-%d" % [mov, stat_gap, range_min + 1, range_max],
		"[color=#a89878]士气[/color] %d/3" % morale,
		"[color=#a89878]技能[/color] %s" % (", ".join(skill_names) if skill_names.size() > 0 else "—"),
	]

	# ── 战斗加成 / Buffs 区段(P2.6+ 用户要的逐条列出) ──
	# 每条描述一个 buff 来源:地形 / 士气 / 指挥官 / 装备 / 技能 /
	# 主动技能附带效果等。空 buff 不显示该区段。
	var buffs: Array[String] = []
	# 1) 地形防御加成(单位所站格子的 TERRAIN_DEF_BONUS)
	var tile_d: Dictionary = GameState.get_tile(int(pos.x), int(pos.y)) if GameState != null else {}
	var terrain_v: Variant = tile_d.get("terrain", "")
	var terrain_name: String = "plain" if terrain_v == null or str(terrain_v) == "" else str(terrain_v)
	if terrain_name != "":
		var def_bonus: int = int(Config.TERRAIN_DEF_BONUS.get(terrain_name, 0))
		# castle_floor / castle_wall 等 subtype 也走同一张表
		var subtype_v: Variant = tile_d.get("subtype", "")
		var subtype: String = "" if subtype_v == null else str(subtype_v)
		if subtype != "" and Config.TERRAIN_DEF_BONUS.has(subtype):
			def_bonus = int(Config.TERRAIN_DEF_BONUS.get(subtype, 0))
		var terrain_cn := _terrain_cn(terrain_name, subtype)
		var move_cost_x2: int = int(Config.TERRAIN_MOVE_COST.get(terrain_name, 9999))
		var move_cost_text := "不可通行" if move_cost_x2 >= 9999 else ("%.1f" % (float(move_cost_x2) / 2.0))
		var bonus_color := "#7ec97e" if def_bonus > 0 else "#c8baa0"
		buffs.append("[color=%s]▦ %s[/color] · 移动消耗 %s · 防御 %+d" % [bonus_color, terrain_cn, move_cost_text, def_bonus])
		if terrain_name == "castle" or terrain_name == "village" or terrain_name == "barracks":
			buffs.append("[color=#a89878]驻守设施 · 可占领或执行设施行动[/color]")
	# 2) 士气加成(MORALE_ATK_PER_STAR / MORALE_DEF_PER_STAR)
	if morale > 0:
		var atk_pct: int = int(round(morale * Config.MORALE_ATK_PER_STAR * 100))
		var def_pct: int = int(round(morale * Config.MORALE_DEF_PER_STAR * 100))
		buffs.append("[color=#fad855]⭐ 士气 %d[/color] → +%d%% 攻击 +%d%% 防御" % [morale, atk_pct, def_pct])
	# 3) 玩家指挥官统御 Power 是否启动(仅自己单位)
	# 修 Bug:之前读 GameState.players[].co_state,这个字段不在 PlayerOut schema
	# 里,通常拿到空 dict。改为读顶层 GameState.co_states[] 找本玩家。
	if is_mine and GameState != null:
		var is_power_active: bool = false
		var co_id: String = ""
		for co_entry in GameState.co_states:
			if co_entry is Dictionary and int(co_entry.get("player_id", -1)) == _player_id:
				is_power_active = bool(co_entry.get("is_power_active", false))
				co_id = str(co_entry.get("commander_id", "") or "")
				break
		if is_power_active:
			var co_name_cn := _commander_cn(co_id) if co_id != "" else "指挥官"
			buffs.append("[color=#f2666b]🔥 %s 统御 Power 启动中[/color] → 全军 buff" % co_name_cn)
	# 4) 转职加成(高等级 → 转职后等级加成)
	if lvl >= 10:
		buffs.append("[color=#5fa8e8]📈 等级 %d 已解锁转职[/color]" % lvl)
	# 5) 技能被动效果(只对未在 skill list 中显示的通用增益提示)
	for sk_name in skills:
		var sk_cn: String = _skill_cn(str(sk_name))
		if sk_cn != "" and sk_cn != str(sk_name):
			buffs.append("[color=#a69a73]💠 技能:[/color] %s" % sk_cn)

	if buffs.size() > 0:
		var header: String = "[color=#c9a14a][b]— ⚡ 战斗加成 —[/b][/color]"
		var buff_block: Array[String] = [header]
		buff_block.append_array(buffs)
		lines.append("")
		lines.append_array(buff_block)

	if not is_mine:
		lines.append("[color=#c63a3a]⚠ 敌方单位·无法操作[/color]")
	elif not can_act:
		lines.append("[color=#a89878]💤 已结束本回合行动[/color]")
	lines = lines.filter(func(line): return str(line) != "")
	unit_info.text = "\n".join(lines)


func _unit_portrait_path_for(unit: Dictionary) -> String:
	var hero_id_v: Variant = unit.get("hero_id", null)
	var hero_id: String = "" if hero_id_v == null else str(hero_id_v)
	if hero_id != "":
		return "res://assets/heroes/portrait_%s.png" % hero_id
	var unit_type_v: Variant = unit.get("unit_type", unit.get("type", null))
	var unit_type: String = "" if unit_type_v == null else str(unit_type_v)
	if unit_type == "":
		return ""
	return "res://assets/unit_portraits/portrait_%s.png" % unit_type


func _set_unit_info_portrait(unit: Dictionary) -> void:
	if hero_portrait_panel == null or not is_instance_valid(hero_portrait_panel):
		return
	if _unit_info_portrait_tex == null:
		_unit_info_portrait_tex = TextureRect.new()
		_unit_info_portrait_tex.name = "PortraitTexture"
		_unit_info_portrait_tex.mouse_filter = Control.MOUSE_FILTER_IGNORE
		_unit_info_portrait_tex.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		_unit_info_portrait_tex.offset_left = 12.0
		_unit_info_portrait_tex.offset_top = 12.0
		_unit_info_portrait_tex.offset_right = -12.0
		_unit_info_portrait_tex.offset_bottom = -12.0
		_unit_info_portrait_tex.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		_unit_info_portrait_tex.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		hero_portrait_panel.add_child(_unit_info_portrait_tex)
		hero_portrait_panel.move_child(_unit_info_portrait_tex, 0)
	var portrait_path := _unit_portrait_path_for(unit)
	if portrait_path == "":
		_unit_info_portrait_tex.texture = null
		_unit_info_portrait_tex.visible = false
		hero_portrait_panel.visible = false
		if unit_info != null and is_instance_valid(unit_info):
			unit_info.offset_left = 44.0
		return
	var tex := PortraitLoader.load(portrait_path)
	_unit_info_portrait_tex.texture = tex
	_unit_info_portrait_tex.set_deferred("size", hero_portrait_panel.size)
	_unit_info_portrait_tex.visible = tex != null
	hero_portrait_panel.visible = tex != null


func _set_board_inspect_card_visible(is_visible: bool) -> void:
	if board == null or not is_instance_valid(board):
		return
	var camera := board.get_node_or_null("BoardCamera")
	if camera != null and camera.has_method("set_inspect_card_visible"):
		camera.call("set_inspect_card_visible", is_visible)


# 辅助:GameState.players 摊平所有 unit(含本方玩家)
func _all_units_including_self() -> Array:
	var out: Array = []
	if GameState == null: return out
	for p in GameState.players:
		if not p is Dictionary: continue
		for u in p.get("units", []):
			if u is Dictionary:
				out.append(u)
	return out


func _use_skill_on_target(skill_id: String, unit_id: int, target_id: int) -> void:
	if _game_id <= 0 or _player_id <= 0: return
	var info: Dictionary = _skill_targets.get(target_id, {})
	var name: String = str(info.get("name", "单位 #%d" % target_id))
	_update_status("技能 %s #%d→ #%d (%s)..." % [_skill_cn(skill_id), unit_id, target_id, name])
	NetworkClient.action_skill(_game_id, _player_id, unit_id, skill_id, target_id)
	_skill_mode_unit_id = -1
	_skill_targets = {}
	if board != null: board.clear_selection_marks()
	_hide_action_bubble()
	_schedule_board_refresh()


func _on_wait_pressed() -> void:
	if _selected_unit_id > 0 and _game_id > 0 and _player_id > 0:
		NetworkClient.action_wait(_game_id, _player_id, _selected_unit_id)
	_update_status("单位 #%d 待命" % _selected_unit_id)
	_hide_action_bubble()


func _on_claim_pressed() -> void:
	# M4.4:占领 — 服务端自己校验 unit 站在中立/敌方建筑 tile 上方,
	# 客户端只发 POST。2 回合后占领完成(详情 game/app/config.py:CLAIM_TURNS_REQUIRED)。
	if _selected_unit_id <= 0:
		_update_status("占领: 请先选中单位")
		return
	if _game_id <= 0 or _player_id <= 0:
		return
	_update_status("正在占领(#%d)..." % _selected_unit_id)
	NetworkClient.action_claim(
		_game_id, _player_id, _selected_unit_id,
		Callable(self, "_on_claim_response").bind(_selected_unit_id),
	)
	_hide_action_bubble()


## 8f: 占领响应 — 仅在 completed=true 时旁白
func _on_claim_response(body: Variant, code: int, _unit_id: int) -> void:
	if code < 200 or code >= 300:
		return
	if not (body is Dictionary):
		return
	if not bool(body.get("completed", false)):
		return
	if DialogManager.is_playing():
		return
	DialogManager.show_dialog({
		"speaker": "",
		"text": "占领完成。",
		"type": "narration",
	})


func _random_suffix() -> float:
	return randf()


func _dev_auto_play_enabled() -> bool:
	# Env var wins (cleaner in headless contexts).
	if OS.get_environment("BB_AUTO_PLAY") == "1":
		return true
	# Cmdline fallback (Godot strips args after the scene path).
	for a in OS.get_cmdline_user_args():
		if a == "--auto-play":
			return true
	return false
