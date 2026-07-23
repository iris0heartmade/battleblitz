extends Node
const MenuTheme = preload("res://scripts/ui/menu_theme.gd")
const MapPreviewSummary = preload("res://scripts/ui/map_preview_summary.gd")
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
var _pending_skill_id: String = ""
const _ACTION_CONTEXT_INITIAL := "initial"
const _ACTION_CONTEXT_POST_MOVE := "post_move"
const _ACTION_CONTEXT_POST_ACTION := "post_action"
# M4.5 招募状态机(unit_type → name 也在用)
const _RECRUIT_OPTIONS := [
	{"type": "swordsman", "name": "剑士",   "cost": 200},
	{"type": "archer",    "name": "弓箭手", "cost": 250},
	{"type": "warlock",   "name": "术士",   "cost": 300},
	{"type": "healer",    "name": "治疗师", "cost": 350},
	{"type": "knight",    "name": "骑士",   "cost": 400},
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

# M6.1 BGM player
@onready var bgm_player: AudioStreamPlayer = $BGMPlayer
@onready var action_log: RichTextLabel = $GameView/HUD/WarReportPanel/ActionLog
@onready var auto_save_toast: Panel = $GameView/HUD/AutoSaveToast
@onready var auto_save_toast_label: Label = $GameView/HUD/AutoSaveToast/ToastLabel
# CreateFormPanel(自由模式专用)— 房间设置表单
# V2 第 3 轮:InfoPanel 是左侧 30% 信息区(单位详情 + 玩家列表)
@onready var info_panel: Panel = $GameView/HUD/InfoPanel
@onready var commander_title: Label = $GameView/HUD/InfoPanel/CommanderTitle
@onready var commander_name: RichTextLabel = $GameView/HUD/InfoPanel/CommanderName
# M5.1 CO Roster — 顶部全玩家头像 + meter + 发动按钮
@onready var co_roster: HBoxContainer = $GameView/HUD/CORoster
@onready var commander_co_bar: ProgressBar = $GameView/HUD/InfoPanel/CommanderCOBar
@onready var unit_info_title: Label = $GameView/HUD/InfoPanel/UnitInfoTitle
@onready var unit_info: RichTextLabel = $GameView/HUD/InfoPanel/UnitInfo
@onready var players_list: RichTextLabel = $GameView/HUD/InfoPanel/PlayersList
@onready var turn_banner: ColorRect = $GameView/TurnBannerFrame
@onready var turn_banner_label: Label = $GameView/TurnBannerFrame/TurnBannerLabel
var _turn_banner_tween: Tween = null
var _ai_pulse_tween: Tween = null
var _auto_save_toast_tween: Tween = null

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
@onready var dialog_panel: Panel = $GameView/HUD/DialogPanel
@onready var dialog_name: Label = $GameView/HUD/DialogPanel/CharacterName
@onready var dialog_text: RichTextLabel = $GameView/HUD/DialogPanel/DialogBody/DialogText
@onready var dialog_continue_btn: Button = $GameView/HUD/DialogPanel/ContinueBtn
@onready var dialog_portrait_panel: Panel = $GameView/HUD/DialogPanel/DialogBody/Portrait
@onready var dialog_portrait_label: Label = $GameView/HUD/DialogPanel/DialogBody/Portrait/PortraitLabel

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
@onready var battle_result_winner: Label = $GameView/HUD/BattleResultPanel/WinnerBanner
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
@onready var cancel_btn: Button = $GameView/HUD/ActionBubble/ActionList/CancelBtn
@onready var move_btn: Button = $GameView/HUD/ActionBubble/ActionList/MoveBtn
@onready var attack_btn: Button = $GameView/HUD/ActionBubble/ActionList/AttackBtn
@onready var skill_btn: Button = $GameView/HUD/ActionBubble/ActionList/SkillBtn
@onready var wait_btn: Button = $GameView/HUD/ActionBubble/ActionList/WaitBtn
@onready var claim_btn: Button = $GameView/HUD/ActionBubble/ActionList/ClaimBtn
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

# T:3 基础大厅视图
@onready var editor_view = $EditorView  # -> editor_controller.gd (P2)

@onready var lobby_view: Control = $Lobby
@onready var lobby_status_label: Label = $Lobby/LobbyFrame/LobbyInfoBar/LobbyStatus
@onready var lobby_list: RichTextLabel = $Lobby/LobbyFrame/LobbyList
@onready var lobby_win_banner: Label = $Lobby/LobbyFrame/LobbyInfoBar/LobbyWinBanner
@onready var ai_difficulty_option: OptionButton = $Lobby/LobbyFrame/AiConfigRow/AiDifficultyOption
@onready var ai_kind_option: OptionButton = $Lobby/LobbyFrame/AiConfigRow/AiKindOption
@onready var ai_personality_option: OptionButton = $Lobby/LobbyFrame/AiConfigRow/AiPersonalityOption
@onready var ai_commander_option: OptionButton = $Lobby/LobbyFrame/AiCommanderOption
@onready var ai_player_option: OptionButton = $Lobby/LobbyFrame/AiActionRow/AiPlayerOption
@onready var lobby_add_ai_btn: Button = $Lobby/LobbyFrame/AiActionRow/LobbyAddAiBtn
@onready var lobby_remove_ai_btn: Button = $Lobby/LobbyFrame/AiActionRow/LobbyRemoveAiBtn
@onready var lobby_start_btn: Button = $Lobby/LobbyFrame/BottomBar/LobbyStartBtn
@onready var player_count_label: Label = $Lobby/LobbyFrame/LobbyDualCol/RightCol/PlayerCountLabel
@onready var start_game_inline_btn: Button = $Lobby/LobbyFrame/LobbyDualCol/RightCol/StartGameInlineBtn
@onready var lobby_back_btn: Button = $Lobby/LobbyFrame/BottomBar/LobbyBackBtn
@onready var lobby_game_id_label: Label = $Lobby/LobbyFrame/LobbyTopBar/LobbyGameIdLabel
@onready var room_list: RichTextLabel = $Lobby/LobbyFrame/LobbyDualCol/LeftCol/RoomList
@onready var room_select_option: OptionButton = $Lobby/LobbyFrame/LobbyDualCol/LeftCol/RoomSelectOption
@onready var join_mode_option: OptionButton = $Lobby/LobbyFrame/LobbyDualCol/LeftCol/JoinModeOption
@onready var refresh_rooms_btn: Button = $Lobby/LobbyFrame/LobbyDualCol/LeftCol/LeftBtnRow/RefreshRoomsBtn
@onready var join_selected_btn: Button = $Lobby/LobbyFrame/LobbyDualCol/LeftCol/LeftBtnRow/JoinSelectedBtn
@onready var lobby_name_input: LineEdit = $Lobby/LobbyFrame/LobbyDualCol/RightCol/CreateNameInput
@onready var lobby_seat_panel: Panel = $Lobby/LobbyFrame/LobbyDualCol/RightCol/SeatPanel
@onready var lobby_seat_grid: GridContainer = $Lobby/LobbyFrame/LobbyDualCol/RightCol/SeatPanel/SeatGrid
@onready var map_player_count_option: OptionButton = $Lobby/LobbyFrame/LobbyDualCol/LeftCol/MapPickerRow/MapPlayerCountOption
@onready var map_preset_option: OptionButton = $Lobby/LobbyFrame/LobbyDualCol/LeftCol/MapPickerRow/MapPresetOption
@onready var map_preview_panel: Panel = $Lobby/LobbyFrame/LobbyDualCol/LeftCol/MapPreviewPanel
@onready var map_preview_texture: TextureRect = $Lobby/LobbyFrame/LobbyDualCol/LeftCol/MapPreviewPanel/MapPreviewTexture
@onready var map_faction_summary: RichTextLabel = $Lobby/LobbyFrame/LobbyDualCol/LeftCol/MapPreviewPanel/MapFactionSummary
@onready var team_option: OptionButton = $Lobby/LobbyFrame/LobbyDualCol/RightCol/TeamRow/TeamOption
@onready var lobby_apply_team_btn: Button = $Lobby/LobbyFrame/LobbyDualCol/RightCol/TeamRow/LobbyApplyTeamBtn
# P1#8 房主行级队伍控制 + P1#7 切换观战(转换自己为观战者)
@onready var lobby_host_player_option: OptionButton = $Lobby/LobbyFrame/HostRow/LobbyHostPlayerOption
@onready var lobby_host_team_option: OptionButton = $Lobby/LobbyFrame/HostRow/LobbyHostTeamOption
@onready var lobby_host_apply_btn: Button = $Lobby/LobbyFrame/HostRow/LobbyHostApplyBtn
@onready var lobby_to_spec_btn: Button = $Lobby/LobbyFrame/LobbyToSpecBtn
@onready var lobby_commander_option: OptionButton = $Lobby/LobbyFrame/LobbyDualCol/RightCol/LobbyCommanderOption
@onready var lobby_bgm_option: OptionButton = $Lobby/LobbyFrame/LobbyDualCol/RightCol/LobbyBgmOption
@onready var win_condition_option: OptionButton = $Lobby/LobbyFrame/LobbyDualCol/RightCol/WinConditionOption
@onready var create_room_btn: Button = $Lobby/LobbyFrame/LobbyDualCol/RightCol/CreateRoomBtn
# Lobby 二层菜单导航
@onready var choose_panel: VBoxContainer = $Lobby/LobbyFrame/ChoosePanel
@onready var create_card_btn: Button = $Lobby/LobbyFrame/ChoosePanel/ChooseBtnRow/CreateCard/CreateCardInner/CreateCardBtn
@onready var join_card_btn: Button = $Lobby/LobbyFrame/ChoosePanel/ChooseBtnRow/JoinCard/JoinCardInner/JoinCardBtn
var _entry_flow: String = "free"
var _lobby_mode: String = "choose"  # choose / create / join / in_room
var _lobby_rooms: Array = []
var _selected_room_id: int = 0
var _selected_ai_player_id: int = 0
var _preset_options: Array = []
var _all_preset_options: Array = []
var _lobby_preset_filter_players: int = 0
var _lobby_commander_ids: Array[String] = [""]
var _lobby_ai_commander_ids: Array[String] = [""]
var _lobby_bgm_track_ids: Array[String] = [""]
# P1#8 房主:seat==0 即房主。_lobby_host_target_id = 当前选中的目标玩家 id。
# _lobby_host_team_ids: 与 lobby_host_team_option 下标对齐的队伍名(""=自由)。
var _lobby_is_host: bool = false
var _lobby_self_is_spectator: bool = false
var _lobby_host_target_id: int = 0
var _lobby_host_team_ids: Array[String] = [""]
var _lobby_last_players: Array = []
var _lobby_host_player_sig: String = ""
var _lobby_seat_team_ids: Array[String] = ["team_a", "team_b", "team_c", "team_d"]
var _lobby_seat_ai_replacements: Array[bool] = [false, false, false, false]
var _lobby_seat_ai_personalities: Array[String] = ["balanced", "balanced", "balanced", "balanced"]
var _lobby_seat_commander_indices: Array[int] = [0, 0, 0, 0]
# M4.16+:game-over 保险。_on_match_ended 触发后置 true,屏蔽后续 state
# poll / AI 操作。重置场景时(_on_lobby_pressed / 新 game 创建)→ false。
var _game_over: bool = false
var _lobby_seat_occupants: Array[String] = ["", "", "", ""]
var _lobby_commanders_fetched: bool = false  # API 响应后置 true,防"加载中…"误判
var _selected_lobby_seat_index: int = 0
var _pending_lobby_start_after_create: bool = false
var _pending_lobby_ai_seats: Array[int] = []
var _pending_lobby_team_updates: Array[Dictionary] = []
# 大厅轮询(2s)— 与 web app.js:918 一致
var _lobby_poll_timer: Timer = null
@onready var menu_title: Label = $Menu/CenterContainer/TitleBlock/TitleLine1
@onready var menu_subtitle: Label = $Menu/CenterContainer/TitleBlock/TitleLine2
@onready var menu_footer: Label = $Menu/Footer/FooterLabel
@onready var connecting_label: Label = $Connecting/ConnectingInner/ConnectingLabel
@onready var connecting_title: Label = $Connecting/ConnectingInner/ConnectingTitle
@onready var reconnect_button: Button = $Connecting/ConnectingInner/ReconnectButton

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
var _ml_slot_records: Array = []
var _mainline_auto_retry_pending: bool = false


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
	if ai_player_option != null and is_instance_valid(ai_player_option):
		ai_player_option.item_selected.connect(_on_ai_player_selected)
	if lobby_remove_ai_btn != null and is_instance_valid(lobby_remove_ai_btn):
		lobby_remove_ai_btn.pressed.connect(_on_lobby_remove_ai_pressed)
	# P1:audit 发现 LobbyAddAiBtn 在 tscn 存在但 var 未接 .pressed.connect
	if lobby_add_ai_btn != null and is_instance_valid(lobby_add_ai_btn):
		lobby_add_ai_btn.pressed.connect(_on_lobby_add_ai_pressed)
	if lobby_start_btn != null and is_instance_valid(lobby_start_btn):
		lobby_start_btn.pressed.connect(_on_lobby_start_pressed)
	if start_game_inline_btn != null and is_instance_valid(start_game_inline_btn):
		start_game_inline_btn.pressed.connect(_on_lobby_start_pressed)
	if lobby_back_btn != null and is_instance_valid(lobby_back_btn):
		lobby_back_btn.pressed.connect(_on_lobby_back_pressed)
	if room_select_option != null and is_instance_valid(room_select_option):
		room_select_option.item_selected.connect(_on_room_selected)
	if join_mode_option != null and is_instance_valid(join_mode_option):
		join_mode_option.item_selected.connect(_on_join_mode_changed)
	if refresh_rooms_btn != null and is_instance_valid(refresh_rooms_btn):
		refresh_rooms_btn.pressed.connect(_refresh_room_list)
	if join_selected_btn != null and is_instance_valid(join_selected_btn):
		join_selected_btn.pressed.connect(_on_join_selected_pressed)
	if map_player_count_option != null and is_instance_valid(map_player_count_option):
		map_player_count_option.item_selected.connect(_on_lobby_map_player_count_selected)
	if map_preset_option != null and is_instance_valid(map_preset_option):
		map_preset_option.item_selected.connect(_on_lobby_map_preset_selected)
	if create_room_btn != null and is_instance_valid(create_room_btn):
		create_room_btn.text = "开启游戏"
		create_room_btn.pressed.connect(_on_create_room_pressed)
	# Lobby 二层菜单导航
	if create_card_btn != null and is_instance_valid(create_card_btn):
		create_card_btn.pressed.connect(_on_create_card_pressed)
	if join_card_btn != null and is_instance_valid(join_card_btn):
		join_card_btn.pressed.connect(_on_join_card_pressed)
	if lobby_apply_team_btn != null and is_instance_valid(lobby_apply_team_btn):
		lobby_apply_team_btn.pressed.connect(_on_lobby_apply_team_pressed)
	if lobby_host_player_option != null and is_instance_valid(lobby_host_player_option):
		lobby_host_player_option.item_selected.connect(_on_lobby_host_player_selected)
	if lobby_host_apply_btn != null and is_instance_valid(lobby_host_apply_btn):
		lobby_host_apply_btn.pressed.connect(_on_lobby_host_apply_pressed)
	if lobby_to_spec_btn != null and is_instance_valid(lobby_to_spec_btn):
		lobby_to_spec_btn.pressed.connect(_on_lobby_to_spec_pressed)
	settings_button.pressed.connect(_on_settings_open_pressed)
	exit_button.pressed.connect(_on_exit_pressed)
	if resume_button != null and is_instance_valid(resume_button):
		resume_button.pressed.connect(_on_resume_pressed)
	# P2: saves_controller.gd 组件接线(跨域引用 + 回调绑定)
	if saves_view != null and is_instance_valid(saves_view):
		saves_view._main = self
	# P2: mainline_controller.gd 组件接线
	if mainline_view != null and is_instance_valid(mainline_view):
		mainline_view._main = self
	# P2: editor_controller.gd 组件接线(注入共享 helper + 跨域信号)
	if editor_view != null and is_instance_valid(editor_view):
		editor_view.unit_label_fn = Callable(self, "_unit_type_cn")
		if not editor_view.back_requested.is_connected(_on_editor_back_requested):
			editor_view.back_requested.connect(_on_editor_back_requested)
		if not editor_view.map_saved.is_connected(_upsert_editor_map_as_lobby_preset):
			editor_view.map_saved.connect(_upsert_editor_map_as_lobby_preset)
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
	dialog_continue_btn.pressed.connect(_on_dialog_continue_pressed)
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
	# HUD 是 CanvasLayer,不受 GameView.visible 控制 — 手动同步显隐
	if name == "game":
		_show_hud()
	else:
		_hide_hud()
	# lobby 视图默认进二层菜单(创建/加入选择)
	if name == "lobby":
		_show_lobby_choose()
	# 最强保险:切到 game view 时强制 GameView 不吞棋盘点击
	# (tscn mouse_filter=2 + _ready 兜底都没生效时,这里再设一次绝对生效)
	if name == "game" and game_view != null and is_instance_valid(game_view):
		game_view.mouse_filter = Control.MOUSE_FILTER_IGNORE
	# game view 时启动状态轮询(每 1s GET /state 追 AI 行动)
	if name == "game":
		_start_state_polling()
		# 棋盘右边有空档(Backdrop 绿色露出来) — 切暗色调融合棋盘边界
		if backdrop != null and is_instance_valid(backdrop):
			backdrop.color = Color.TRANSPARENT
	else:
		_stop_state_polling()
		# 恢复主题背景色
		if backdrop != null and is_instance_valid(backdrop):
			backdrop.color = MenuTheme.C_BG_DEEP
	# P2 修复:BoardCamera 在 apply_metrics() 时 enabled=true,会接管整个 viewport 的
	# canvas_transform(zoom + 平移),连带 Menu 等 Control 一起缩放平移。切到不显示棋盘的
	# view 必须禁用它并归位 canvas,否则从 game / 地图编辑器返回主菜单后整屏右偏放大。
	if name != "game" and name != "editor":
		_reset_board_cameras()


func _reset_board_cameras() -> void:
	_disable_board_camera(board)
	if editor_view != null and is_instance_valid(editor_view):
		_disable_board_camera(editor_view.get_node_or_null("EditorBoard"))
	var vp := get_viewport()
	if vp != null:
		vp.canvas_transform = Transform2D.IDENTITY


func _disable_board_camera(b: Node) -> void:
	if b == null or not is_instance_valid(b):
		return
	var cam := b.get_node_or_null("BoardCamera")
	if cam != null and is_instance_valid(cam):
		cam.enabled = false


# HUD (CanvasLayer) 显隐控制 — CanvasLayer 不受父 Control.visible 影响
func _show_hud() -> void:
	if hud_layer != null and is_instance_valid(hud_layer):
		hud_layer.visible = true


func _hide_hud() -> void:
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
		NetworkClient.join_game(_game_id, _user_name, "red", _selected_join_team(), _selected_join_role())


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
		if lobby_game_id_label != null and is_instance_valid(lobby_game_id_label):
			lobby_game_id_label.text = "对局 #%d" % _game_id
		_start_lobby_polling()
		_refresh_room_list()
		_show_lobby_in_room()
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
	board.load_map(pseudo)
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
			initial_units.append({
				"x": int(u.get("x", 0)),
				"y": int(u.get("y", 0)),
				"type": str(u.get("unit_type", "swordsman")),
				"color": color,
				"level": int(u.get("level", 1)),
			})
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
	for c in states:
		if not (c is Dictionary):
			continue
		var pid: int = int(c.get("player_id", -1))
		var color_name: String = str(c.get("color", "—"))
		var commander_id: String = str(c.get("commander_id", ""))
		var meter: int = int(c.get("meter", 0))
		var threshold: int = max(1, int(c.get("threshold", 100)))
		var pct: float = clamp(float(meter) / float(threshold) * 100.0, 0.0, 100.0)
		var is_active: bool = bool(c.get("is_power_active", false))
		var can_fire: bool = bool(c.get("can_fire", false))
		var is_local: bool = pid == _player_id
		# Panel 容器(单行:HBox)
		var row := Panel.new()
		row.custom_minimum_size = Vector2(160, 32)
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
		# 1) 阵营色块(16x16)
		var swatch := ColorRect.new()
		swatch.custom_minimum_size = Vector2(16, 16)
		swatch.color = Config.player_color(color_name)
		row_inner.add_child(swatch)
		# 2) Label:颜色缩写 + 指挥官名
		var lbl := Label.new()
		lbl.text = "%s:%s" % [color_name.to_upper(), commander_id if commander_id != "" else "—"]
		lbl.add_theme_font_size_override("font_size", 11)
		row_inner.add_child(lbl)
		# 3) ProgressBar(meter / threshold)
		var bar := ProgressBar.new()
		bar.custom_minimum_size = Vector2(56, 12)
		bar.value = pct
		bar.show_percentage = false
		bar.tooltip_text = "指挥官能量: %d / %d" % [meter, threshold]
		row_inner.add_child(bar)
		# 4) 状态标签 / 发动按钮
		if is_active:
			var active_lbl := Label.new()
			active_lbl.text = "⚡ 生效中"
			active_lbl.add_theme_color_override("font_color", Color(0.96, 0.78, 0.18))
			active_lbl.add_theme_font_size_override("font_size", 11)
			row_inner.add_child(active_lbl)
		elif can_fire and is_local:
			var btn := Button.new()
			btn.text = "发动"
			btn.custom_minimum_size = Vector2(36, 20)
			btn.add_theme_font_size_override("font_size", 10)
			btn.tooltip_text = "激活指挥官技(消耗全部能量)"
			# 用 Callable.bind 把 pid 绑到 pressed 信号
			btn.pressed.connect(_on_co_power_pressed.bind(pid))
			row_inner.add_child(btn)
		else:
			var meter_lbl := Label.new()
			meter_lbl.text = "%d/%d" % [meter, threshold]
			meter_lbl.add_theme_font_size_override("font_size", 10)
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
	match c:
		"red": return "#e85a6a"
		"blue": return "#5fa8e8"
		"green": return "#7ec97e"
		"yellow": return "#f0c75e"
		_: return "#cccccc"


func _color_emoji(c: String) -> String:
	match c:
		"red": return "🔴"
		"blue": return "🔵"
		"green": return "🟢"
		"yellow": return "🟡"
		_: return "⚪"


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
	# CO meter from co_states array
	var meter: int = 0
	var threshold: int = 100
	for c in GameState.co_states:
		if c is Dictionary and int(c.get("player_id", -1)) == (int(cur_pid) if cur_pid != null else -1):
			meter = int(c.get("meter", 0))
			threshold = max(1, int(c.get("threshold", 100)))
			break
	var pct: float = float(meter) / float(threshold) * 100.0
	if commander_co_bar != null and is_instance_valid(commander_co_bar):
		commander_co_bar.value = pct
		commander_co_bar.tooltip_text = "指挥官能量: %d / %d" % [meter, threshold]


# M4.13/14 行动后气泡:单位 move/attack 后弹出可再行动气泡
# T:95 — 鼠标 hover 时用 MapLogic.pathfind 算路径并渲染
var _path_hover_last: Vector2i = Vector2i(-1, -1)


func _update_path_dots_on_hover(global_pos: Vector2) -> void:
	if board == null or _move_reachable_set.is_empty():
		return
	var layer: TileMapLayer = board.get_node_or_null("GroundLayer")
	if layer == null:
		return
	var local: Vector2 = layer.to_local(global_pos)
	var target_cell: Vector2i = layer.local_to_map(local)
	if target_cell == _path_hover_last:
		return
	_path_hover_last = target_cell
	if not _move_reachable_set.has(target_cell):
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
	var blocked: Dictionary = {}
	for p in GameState.players:
		if not p is Dictionary: continue
		for u in p.get("units", []):
			if u is Dictionary:
				var k := Vector2i(int(u.get("x", 0)), int(u.get("y", 0)))
				blocked[k] = true
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
		src_cell, target_cell, terrain, owners, mov * 2, _player_id, blocked, size_v
	)
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
	NetworkClient.action_co_power(_game_id, pid)
	_update_status("⚡ 指挥官技激活中 (#%d)..." % pid)
	# 视觉反馈:屏幕中央大飘字 + 屏幕震动
	_play_co_power_fx()


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
	var bg_color: Color = Color(0.06, 0.13, 0.10)  # deep_gba 兜底
	var panel_color: Color = Color(0.06, 0.13, 0.10)
	var border_color: Color = Color(0.79, 0.63, 0.29)  # 金 C_GOLD
	var text_color: Color = Color(0.96, 0.91, 0.76)   # 暖白 C_TEXT_WARM
	var btn_bg: Color = Color(0.16, 0.25, 0.36)       # 蓝底 C_BTN_BLUE
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
	if backdrop != null and is_instance_valid(backdrop):
		backdrop.color = bg_color
	# 重灌核心面板的 StyleBoxFlat 让边界和底色跟主题
	var theme_panels: Array = [settings_panel, pause_panel, dialog_panel, battle_result_panel, war_report_panel]
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
	var theme_btns: Array = [settings_button, settings_apply_btn, settings_cancel_btn,
		settings_close_btn, settings_font_small_btn, settings_font_med_btn, settings_font_big_btn,
		settings_red_btn, settings_blue_btn, settings_green_btn, settings_yellow_btn,
		settings_mute_btn, pause_resume_btn, pause_suspend_btn, pause_main_menu_btn,
		pause_quit_btn, pause_settings_btn, dialog_continue_btn, tutorial_got_it_btn,
		battle_detail_btn, end_turn_button, help_button,
		exit_button, resume_button, lobby_button, lobby_add_ai_btn, lobby_remove_ai_btn,
		lobby_start_btn, lobby_back_btn, lobby_apply_team_btn, lobby_host_apply_btn,
		join_by_code_button]
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
	var theme_text_labels: Array = [settings_panel.find_child("Header", true, false)] if settings_panel != null else []
	for lbl in theme_text_labels:
		if lbl != null and is_instance_valid(lbl):
			lbl.add_theme_color_override("font_color", text_color)
	_update_status("主题: %s" % theme_name)


# M6.13 Help / 玩法说明 — 显示游戏规则静态指南
var _help_panel: Panel = null


func show_help() -> void:
	if _help_panel == null:
		_help_panel = Panel.new()
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
		var title := Label.new()
		title.text = "📖 玩 法 说 明"
		title.anchor_right = 1.0
		title.offset_top = 12.0
		title.offset_bottom = 44.0
		title.horizontal_alignment = 1
		title.add_theme_font_size_override("font_size", 22)
		title.add_theme_color_override("font_color", MenuTheme.C_GOLD)
		_help_panel.add_child(title)
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
		_help_panel.add_child(body)
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
		_help_panel.add_child(close)
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
	if alive_team_to_pid.size() == 1:
		return int(alive_team_to_pid.values()[0])
	return _player_id


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
		var name: String = str(opt.get("name", "?"))
		var cost: int = int(opt.get("cost", 0))
		btn.text = "%s  💰 %d" % [name, cost]
		btn.disabled = gold_i < cost
		btn.pressed.connect(_on_recruit_button_pressed.bind(unit_type))
		recruit_list.add_child(btn)
	recruit_panel.visible = true


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
	if board != null:
		board.clear_selection_marks()
	_update_status("已取消移动")


# M4.1:发 POST /games/{id}/move
func _move_unit_to(unit_id: int, to_x: int, to_y: int) -> void:
	if _game_id <= 0 or _player_id <= 0:
		return
	_update_status("正在移动单位 #%d → (%d, %d)..." % [unit_id, to_x, to_y])
	NetworkClient.action_move(_game_id, _player_id, unit_id, to_x, to_y)
	# 清掉移动模式 + highlights
	_move_mode_unit_id = -1
	_move_reachable_set = {}
	if board != null:
		board.clear_selection_marks()
	_hide_action_bubble()


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
		if tiles.size() > 0 and board != null:
			board.show_path_marks([], tiles)
	elif board != null:
		board.clear_selection_marks()
		_move_reachable_set = {}


# 返回 full Dict {Vector2i: cost} 包括起点;供路径结果判断
func _compute_reachable_tiles_full(unit_data: Dictionary) -> Dictionary:
	var mp: int = int(unit_data.get("mov", int(unit_data.get("move_points", int(unit_data.get("mp", 5))))))
	var unit_pos := Vector2i(int(unit_data.get("x", 0)), int(unit_data.get("y", 0)))
	var size_v: int = 15
	if board != null and board.map_size.x > 0:
		size_v = board.map_size.x
	var blocked: Dictionary = {}
	for other in GameState.players:
		if not other is Dictionary: continue
		for u in other.get("units", []):
			if u is Dictionary:
				var k := Vector2i(int(u.get("x", 0)), int(u.get("y", 0)))
				blocked[k] = true
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
		unit_pos, terrain, owners, mp, owner, blocked, size_v
	)
	print("DEBUG reachable: result_size=%s" % result.size())
	return result


func _compute_reachable_tiles(unit_data: Dictionary) -> Array:
	var mp: int = int(unit_data.get("move_points", int(unit_data.get("mp", 5))))
	var unit_pos := Vector2i(int(unit_data.get("x", 0)), int(unit_data.get("y", 0)))
	var size_v: int = 15
	if board != null and board.map_size.x > 0:
		size_v = board.map_size.x
	var blocked: Dictionary = {}
	for other in GameState.players:
		if not other is Dictionary: continue
		for u in other.get("units", []):
			if u is Dictionary:
				var k := Vector2i(int(u.get("x", 0)), int(u.get("y", 0)))
				blocked[k] = true
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
	# MapLogic.compute_reachable(start, terrain, owners, mov, viewer_owner_id, blocked, size)
	var result: Dictionary = MapLogic.compute_reachable(
		unit_pos, terrain, owners, mp, owner, blocked, size_v
	)
	# 移除起点(不要把自身高亮成可达)
	result.erase(unit_pos)
	return result.keys()


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
	if dialog_panel != null and is_instance_valid(dialog_panel):
		dialog_panel.visible = false
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
	_lobby_seat_commander_indices = [0, 0, 0, 0]
	_lobby_commander_ids = [""]
	_selected_ai_player_id = 0
	_lobby_is_host = false


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

const _DIALOG_TYPE := 0   # 角色说话
const _DIALOG_NARRATION := 1  # 旁白(无角色名)
const _DIALOG_CHOICE := 2   # 选项(底部按钮)

var _dialog_queue: Array = []  # [{character, text, kind, choices?}]
var _hero_speaker_map: Dictionary = {}
var _dialog_portrait_tex: TextureRect = null
var _unit_info_portrait_tex: TextureRect = null
var _dialog_active: bool = false
var _dialog_full_text: String = ""
var _dialog_visible_text: String = ""
var _dialog_type_tween: Tween = null
var _dialog_choice_container: VBoxContainer = null

func show_dialog(character: String, text_bbcode: String) -> void:
	if dialog_panel == null or not is_instance_valid(dialog_panel):
		return
	# 推入队列
	_dialog_queue.append({
		"character": character,
		"text": text_bbcode,
		"kind": _DIALOG_TYPE if character != "" else _DIALOG_NARRATION,
	})
	_ensure_dialog_choice_container()  # 确保选项层存在
	dialog_panel.visible = true
	if not _dialog_active:
		_advance_dialog()


func show_dialog_scene(scene: Dictionary) -> void:
	# 富场景入口:按 server 对话 JSON 的 type 分发(web Dialog parity)。
	# dialogue/narration/choice/battle_ref/wait。简单对话仍用 show_dialog。
	if dialog_panel == null or not is_instance_valid(dialog_panel):
		return
	var stype := str(scene.get("type", "dialogue"))
	if stype == "battle_ref" or stype == "wait":
		return  # 战斗标记/等待:无 UI,跳过(主线靠 start_mainline 单独开战)
	if stype == "choice":
		var q := str(scene.get("question", "请选择:"))
		var choices: Array = scene.get("choices", []) if scene.get("choices", []) is Array else []
		_dialog_queue.append({"kind": _DIALOG_CHOICE, "question": q, "choices": choices})
	else:
		var speaker := str(scene.get("speaker", scene.get("character", "")))
		var text := str(scene.get("text", ""))
		var col := str(scene.get("speaker_color", ""))
		var kind := _DIALOG_TYPE if speaker != "" else _DIALOG_NARRATION
		_dialog_queue.append({"character": speaker, "text": text, "kind": kind, "color": col})
	_ensure_dialog_choice_container()
	dialog_panel.visible = true
	if not _dialog_active:
		_advance_dialog()


func _play_dialogue_scenes(payload: Variant) -> void:
	# 兼容 Array / {scenes:[...]} / 单 scene Dict 三种形状(server /mainlines/dialogue 返回 {scenes:[...]})。
	var scenes: Array = []
	if payload is Array:
		scenes = payload
	elif payload is Dictionary:
		if payload.has("scenes") and payload["scenes"] is Array:
			scenes = payload["scenes"]
		else:
			scenes = [payload]
	for sc in scenes:
		if sc is Dictionary:
			show_dialog_scene(sc)


func _render_dialog_choice(entry: Dictionary) -> void:
	var question: String = str(entry.get("question", "请选择:"))
	dialog_name.text = ""
	if dialog_name.has_theme_color_override("font_color"):
		dialog_name.remove_theme_color_override("font_color")
	_set_dialog_portrait("")
	dialog_text.bbcode_enabled = true
	dialog_text.text = question
	_dialog_full_text = question
	if dialog_continue_btn != null and is_instance_valid(dialog_continue_btn):
		dialog_continue_btn.visible = false
	if _dialog_choice_container != null and is_instance_valid(_dialog_choice_container):
		for child in _dialog_choice_container.get_children():
			child.queue_free()
		var choices: Array = entry.get("choices", []) if entry.get("choices", []) is Array else []
		for ch in choices:
			if not (ch is Dictionary): continue
			var btn := Button.new()
			btn.text = str(ch.get("text", ""))
			btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			btn.pressed.connect(_on_dialog_choice_selected)
			_dialog_choice_container.add_child(btn)
		_dialog_choice_container.visible = true


func _on_dialog_choice_selected() -> void:
	if _dialog_choice_container != null and is_instance_valid(_dialog_choice_container):
		_dialog_choice_container.visible = false
	if dialog_continue_btn != null and is_instance_valid(dialog_continue_btn):
		dialog_continue_btn.visible = true
	_advance_dialog()


func _set_dialog_portrait(speaker: String) -> void:
	if dialog_portrait_panel == null or not is_instance_valid(dialog_portrait_panel):
		return
	if _dialog_portrait_tex == null:
		_dialog_portrait_tex = TextureRect.new()
		_dialog_portrait_tex.anchor_right = 1.0
		_dialog_portrait_tex.anchor_bottom = 1.0
		_dialog_portrait_tex.expand_mode = TextureRect.EXPAND_FIT_WIDTH_PROPORTIONAL
		_dialog_portrait_tex.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		dialog_portrait_panel.add_child(_dialog_portrait_tex)
	var tex: Texture2D = null
	if speaker != "" and _hero_speaker_map.has(speaker):
		var info: Dictionary = _hero_speaker_map[speaker]
		if info.has("portrait_tex") and info["portrait_tex"] != null:
			tex = info["portrait_tex"]
		elif info.has("portrait_path") and str(info["portrait_path"]) != "":
			tex = _load_portrait(str(info["portrait_path"]))
			if tex != null:
				_hero_speaker_map[speaker]["portrait_tex"] = tex
	_dialog_portrait_tex.texture = tex
	_dialog_portrait_tex.visible = tex != null
	if dialog_portrait_label != null and is_instance_valid(dialog_portrait_label):
		dialog_portrait_label.visible = tex == null


func _load_portrait(res_path: String) -> Texture2D:
	var img := Image.new()
	if img.load(res_path) != OK:
		return null
	return ImageTexture.create_from_image(img)


func _on_heroes_response(body: Variant, _code: int = 0) -> void:
	var heroes: Array = body if body is Array else []
	for h in heroes:
		if not (h is Dictionary): continue
		var dialogue_name := str(h.get("dialogue_name", h.get("display_cn", "")))
		if dialogue_name == "": continue
		var portrait_url := str(h.get("portrait_url", ""))
		var portrait_path := ""
		if portrait_url != "":
			portrait_path = "res://assets/heroes/" + portrait_url.get_file()
		_hero_speaker_map[dialogue_name] = {"portrait_path": portrait_path}


func _advance_dialog() -> void:
	if _dialog_queue.is_empty():
		_dialog_active = false
		hide_dialog()
		return
	_dialog_active = true
	var entry: Dictionary = _dialog_queue.pop_front()
	var kind: int = int(entry.get("kind", _DIALOG_TYPE))
	if kind == _DIALOG_CHOICE:
		_render_dialog_choice(entry)
		return
	var speaker: String = str(entry.get("character", ""))
	dialog_name.text = speaker if speaker != "" else "（旁白）"
	var col_str: String = str(entry.get("color", ""))
	if col_str != "":
		dialog_name.add_theme_color_override("font_color", Color(col_str))
	elif dialog_name.has_theme_color_override("font_color"):
		dialog_name.remove_theme_color_override("font_color")
	_set_dialog_portrait(speaker)
	if dialog_continue_btn != null and is_instance_valid(dialog_continue_btn):
		dialog_continue_btn.visible = true
	dialog_text.bbcode_enabled = true
	# 隐藏选项层
	if _dialog_choice_container != null and is_instance_valid(_dialog_choice_container):
		_dialog_choice_container.visible = false
	# typewriter:full text 缓存,visible 渐进加
	var full_text: String = str(entry.get("text", ""))
	_dialog_full_text = full_text
	_dialog_visible_text = ""
	dialog_text.text = ""
	# kill 旧 tween
	if _dialog_type_tween != null and _dialog_type_tween.is_running():
		_dialog_type_tween.kill()
	var per_char: float = 0.03
	# 每 N 个字符加长
	var n: int = full_text.length()
	_dialog_type_tween = create_tween()
	for i in n:
		var ch: String = full_text.substr(i, 1)
		_dialog_visible_text += ch
		dialog_text.text = _dialog_visible_text
	# 用 set_tween + interval 的简化:每 0.03s 显一字符
	_dialog_type_tween.kill()
	_dialog_type_tween = create_tween()
	_dialog_type_tween.set_trans(Tween.TRANS_LINEAR)
	for i in n:
		var ch2: String = full_text.substr(i, 1)
		_dialog_type_tween.tween_callback(func(c=ch2): _dialog_visible_text += c).set_delay(float(i) * per_char)
	_dialog_type_tween.tween_callback(_on_dialog_typing_done).set_delay(float(n) * per_char + 0.05)
	dialog_text.text = ""  # typewriter 在 callback 里推进


func _on_dialog_typing_done() -> void:
	# 打字结束 → show 最终 text
	dialog_text.text = _dialog_full_text


func _ensure_dialog_choice_container() -> void:
	if _dialog_choice_container != null and is_instance_valid(_dialog_choice_container):
		return
	var vb := VBoxContainer.new()
	vb.name = "ChoiceContainer"
	vb.anchor_left = 0.0
	vb.anchor_top = 0.0
	vb.anchor_right = 1.0
	vb.anchor_bottom = 1.0
	vb.offset_left = 16.0
	vb.offset_top = 130.0
	vb.offset_right = -16.0
	vb.offset_bottom = -50.0
	vb.add_theme_constant_override("separation", 6)
	vb.visible = false
	dialog_panel.add_child(vb)
	_dialog_choice_container = vb


func _on_dialog_continue_pressed() -> void:
	# 如果正在打字 → 完成剩余;否则下一行
	if _dialog_type_tween != null and _dialog_type_tween.is_running():
		_dialog_type_tween.kill()
		dialog_text.text = _dialog_full_text
		_dialog_visible_text = _dialog_full_text
		return
	_advance_dialog()


func hide_dialog() -> void:
	if dialog_panel != null and is_instance_valid(dialog_panel):
		dialog_panel.visible = false


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


func _on_battle_back_menu_pressed() -> void:
	hide_battle_result()
	_show_view("menu")


# M4.16+:战斗结束 → 返回联机大厅。复用 _on_lobby_pressed,但先清 game 状态
# 否则 _lobby_commanders_fetched / _game_id 可能残留导致 lobby 加载错位。
func _on_battle_back_lobby_pressed() -> void:
	hide_battle_result()
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
	# 1) 全屏深绿背景(ColorRect 颜色已在 .tscn 设)
	backdrop.color = MenuTheme.C_BG_DEEP
	backdrop.mouse_filter = Control.MOUSE_FILTER_IGNORE
	# 2) 边框由 ReferenceRect 画,这里只调整颜色变量(已硬编码在 .tscn)
	# 3) Connecting 框(深绿底)
	connecting_frame.color = MenuTheme.C_BG_PANEL
	# 4) 主菜单 + 游戏内按钮统一灌主题
	# (P2:save_*_btn 由 saves_controller.gd 自管主题,不再列在这里)
	# (Batch A:ml_*_btn 由 mainline_controller.gd 自管主题,这里只保留 mainline_button)
	for btn in [lobby_button, saves_button, mainline_button, editor_button, settings_button, exit_button,
				reconnect_button, end_turn_button, war_report_button,
				attack_confirm_btn, attack_cancel_btn]:
		if btn != null and is_instance_valid(btn):
			MenuTheme.apply_button_theme(btn, MenuTheme.FS_BTN)
	# end_turn 和 war_report 用小一号字号(4 角极小 pill)
	if end_turn_button != null and is_instance_valid(end_turn_button):
		MenuTheme.apply_button_theme(end_turn_button, 14)
	if war_report_button != null and is_instance_valid(war_report_button):
		MenuTheme.apply_button_theme(war_report_button, 14)
	# 5) 标题/副标题/footer 文字色
	MenuTheme.apply_label_theme(menu_title, MenuTheme.FS_HERO, MenuTheme.C_GOLD)
	MenuTheme.apply_label_theme(menu_subtitle, MenuTheme.FS_SUB, MenuTheme.C_TEXT_WARM)
	MenuTheme.apply_label_theme(menu_footer, MenuTheme.FS_FOOT, MenuTheme.C_TEXT_DIM)
	MenuTheme.apply_label_theme(connecting_title, 22, MenuTheme.C_GOLD)
	MenuTheme.apply_label_theme(connecting_label, MenuTheme.FS_SUB, MenuTheme.C_TEXT_WARM)
	# === V2 第 2 轮:HUD 4 角 pill 主题 ===
	_apply_hud_theme()
	# 战报/信息浮层(深绿底 + 烫金边)
	var sb_popup := StyleBoxFlat.new()
	sb_popup.bg_color = MenuTheme.C_BG_PANEL
	sb_popup.border_color = MenuTheme.C_GOLD
	sb_popup.set_border_width_all(2)
	sb_popup.content_margin_left = MenuTheme.PAD
	sb_popup.content_margin_right = MenuTheme.PAD
	sb_popup.content_margin_top = MenuTheme.PAD
	sb_popup.content_margin_bottom = MenuTheme.PAD
	war_report_panel.add_theme_stylebox_override("panel", sb_popup)
	info_panel.add_theme_stylebox_override("panel", sb_popup)


func _apply_hud_theme() -> void:
	# Pills are ColorRect containers with ReferenceRect borders added
	# in _ready. We only need to set font sizes / colors on inner Labels.
	var pill_size := 14
	# Add a gold ReferenceRect border around each pill ColorRect.
	for p in [turn_badge, phase_badge, current_player_badge, gold_panel, ai_thinking_label]:
		if p == null or not is_instance_valid(p):
			continue
		var border := ReferenceRect.new()
		border.anchor_right = 1.0
		border.anchor_bottom = 1.0
		border.offset_left = 0
		border.offset_top = 0
		border.offset_right = 0
		border.offset_bottom = 0
		border.border_color = MenuTheme.C_GOLD
		border.border_width = 2.0
		border.editor_only = false
		border.mouse_filter = Control.MOUSE_FILTER_IGNORE
		p.add_child(border)
	for lbl in [turn_badge_label, phase_badge_label, current_player_label, gold_label]:
		if lbl != null and is_instance_valid(lbl):
			lbl.add_theme_font_size_override("font_size", pill_size)
			lbl.add_theme_color_override("font_color", MenuTheme.C_TEXT_WARM)
	# V2 第 3 轮:InfoPanel 主题(当前指挥官 + 单位详情 + 玩家列表)
	if commander_title != null and is_instance_valid(commander_title):
		commander_title.add_theme_font_size_override("font_size", 16)
		commander_title.add_theme_color_override("font_color", MenuTheme.C_GOLD)
	if unit_info_title != null and is_instance_valid(unit_info_title):
		unit_info_title.add_theme_font_size_override("font_size", 14)
		unit_info_title.add_theme_color_override("font_color", MenuTheme.C_GOLD)
	if commander_name != null and is_instance_valid(commander_name):
		commander_name.add_theme_font_size_override("normal_font_size", 13)
		commander_name.add_theme_color_override("default_color", MenuTheme.C_TEXT_WARM)
	if commander_co_bar != null and is_instance_valid(commander_co_bar):
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
		commander_co_bar.add_theme_stylebox_override("background", sb_bg)
		commander_co_bar.add_theme_stylebox_override("fill", sb_fg)
	if players_list != null and is_instance_valid(players_list):
		players_list.add_theme_font_size_override("normal_font_size", 13)
		players_list.add_theme_color_override("default_color", MenuTheme.C_TEXT_WARM)
	if unit_info != null and is_instance_valid(unit_info):
		unit_info.add_theme_font_size_override("normal_font_size", 13)
		unit_info.add_theme_color_override("default_color", MenuTheme.C_TEXT_WARM)
	# V2 第 4 轮:行动气泡主题(深绿底 + 烫金粗边)
	if action_bubble != null and is_instance_valid(action_bubble):
		var sb_bubble := StyleBoxFlat.new()
		var bg: Color = MenuTheme.C_BG_PANEL
		bg.a = 0.7
		sb_bubble.bg_color = bg
		sb_bubble.border_color = MenuTheme.C_GOLD
		sb_bubble.set_border_width_all(2)
		sb_bubble.set_corner_radius_all(3)
		sb_bubble.content_margin_left = 6
		sb_bubble.content_margin_right = 6
		sb_bubble.content_margin_top = 6
		sb_bubble.content_margin_bottom = 6
		action_bubble.add_theme_stylebox_override("panel", sb_bubble)
	# V2 第 5 轮:战报浮层主题(深绿底 + 烫金粗边 + Header/Close 烫金)
	var sb_war := StyleBoxFlat.new()
	sb_war.bg_color = MenuTheme.C_BG_PANEL
	sb_war.border_color = MenuTheme.C_GOLD
	sb_war.set_border_width_all(2)
	sb_war.set_corner_radius_all(3)
	sb_war.content_margin_left = MenuTheme.PAD
	sb_war.content_margin_right = MenuTheme.PAD
	sb_war.content_margin_top = MenuTheme.PAD
	sb_war.content_margin_bottom = MenuTheme.PAD
	if war_report_panel != null and is_instance_valid(war_report_panel):
		war_report_panel.add_theme_stylebox_override("panel", sb_war)
	var war_header: Label = war_report_panel.find_child("Header", true, false)
	if war_header != null:
		war_header.add_theme_font_size_override("font_size", 16)
		war_header.add_theme_color_override("font_color", MenuTheme.C_GOLD)
	if war_report_close_btn != null and is_instance_valid(war_report_close_btn):
		MenuTheme.apply_button_theme(war_report_close_btn, 16)
	if action_log != null and is_instance_valid(action_log):
		action_log.add_theme_font_size_override("normal_font_size", 14)
		action_log.add_theme_color_override("default_color", MenuTheme.C_TEXT_WARM)
	# V2 第 6 轮:设置 + 暂停面板主题
	var sb_popup2 := StyleBoxFlat.new()
	sb_popup2.bg_color = MenuTheme.C_BG_PANEL
	sb_popup2.border_color = MenuTheme.C_GOLD
	sb_popup2.set_border_width_all(2)
	sb_popup2.set_corner_radius_all(3)
	sb_popup2.content_margin_left = MenuTheme.PAD
	sb_popup2.content_margin_right = MenuTheme.PAD
	sb_popup2.content_margin_top = MenuTheme.PAD
	sb_popup2.content_margin_bottom = MenuTheme.PAD
	if settings_panel != null and is_instance_valid(settings_panel):
		settings_panel.add_theme_stylebox_override("panel", sb_popup2)
	if pause_panel != null and is_instance_valid(pause_panel):
		pause_panel.add_theme_stylebox_override("panel", sb_popup2)
	# Settings Header
	var settings_header: Label = settings_panel.find_child("Header", true, false)
	if settings_header != null:
		settings_header.add_theme_font_size_override("font_size", 20)
		settings_header.add_theme_color_override("font_color", MenuTheme.C_GOLD)
	# Settings row labels
	for lbl in settings_panel.find_children("NameLabel", "", false, false):
		lbl.add_theme_color_override("font_color", MenuTheme.C_TEXT_WARM)
	for lbl in settings_panel.find_children("FontLabel", "", false, false):
		lbl.add_theme_color_override("font_color", MenuTheme.C_TEXT_WARM)
	for lbl in settings_panel.find_children("ColorLabel", "", false, false):
		lbl.add_theme_color_override("font_color", MenuTheme.C_TEXT_WARM)
	for lbl in settings_panel.find_children("ThemeLabel", "", false, false):
		lbl.add_theme_color_override("font_color", MenuTheme.C_TEXT_WARM)
	# Settings buttons
	for btn_name in ["CloseBtn", "FontSmallBtn", "FontMedBtn", "FontBigBtn",
			"RedBtn", "BlueBtn", "GreenBtn", "YellowBtn",
			"ApplyBtn", "CancelBtn"]:
		var btn: Button = settings_panel.find_child(btn_name, true, false)
		if btn != null and is_instance_valid(btn):
			MenuTheme.apply_button_theme(btn, 16)
	# NameInput style
	if settings_name_input != null and is_instance_valid(settings_name_input):
		settings_name_input.add_theme_font_size_override("font_size", 16)
		settings_name_input.add_theme_color_override("font_color", MenuTheme.C_TEXT_WARM)
	# Pause Header
	var pause_header: Label = pause_panel.find_child("Header", true, false)
	if pause_header != null:
		pause_header.add_theme_font_size_override("font_size", 24)
		pause_header.add_theme_color_override("font_color", MenuTheme.C_GOLD)
	# Pause buttons
	for btn_name in ["ResumeBtn", "SettingsBtn", "MainMenuBtn", "QuitBtn"]:
		var btn: Button = pause_panel.find_child(btn_name, true, false)
		if btn != null and is_instance_valid(btn):
			MenuTheme.apply_button_theme(btn, 18)
	# V2 第 7 轮:对话 + 教程 + 战斗结算主题
	var sb_dlg := StyleBoxFlat.new()
	sb_dlg.bg_color = MenuTheme.C_BG_PANEL
	sb_dlg.border_color = MenuTheme.C_GOLD
	sb_dlg.set_border_width_all(2)
	sb_dlg.set_corner_radius_all(3)
	sb_dlg.content_margin_left = MenuTheme.PAD
	sb_dlg.content_margin_right = MenuTheme.PAD
	sb_dlg.content_margin_top = MenuTheme.PAD
	sb_dlg.content_margin_bottom = MenuTheme.PAD
	if dialog_panel != null and is_instance_valid(dialog_panel):
		dialog_panel.add_theme_stylebox_override("panel", sb_dlg)
	if tutorial_bubble != null and is_instance_valid(tutorial_bubble):
		tutorial_bubble.add_theme_stylebox_override("panel", sb_dlg)
	if battle_result_panel != null and is_instance_valid(battle_result_panel):
		battle_result_panel.add_theme_stylebox_override("panel", sb_dlg)
	# Dialog portrait frame
	var portrait_panel: Panel = dialog_panel.find_child("Portrait", true, false)
	if portrait_panel != null:
		var sb_portrait := StyleBoxFlat.new()
		sb_portrait.bg_color = MenuTheme.C_BG_DEEP
		sb_portrait.border_color = MenuTheme.C_GOLD
		sb_portrait.set_border_width_all(2)
		sb_portrait.set_corner_radius_all(3)
		portrait_panel.add_theme_stylebox_override("panel", sb_portrait)
	# Dialog name
	if dialog_name != null and is_instance_valid(dialog_name):
		dialog_name.add_theme_font_size_override("font_size", 18)
		dialog_name.add_theme_color_override("font_color", MenuTheme.C_GOLD)
	if dialog_text != null and is_instance_valid(dialog_text):
		dialog_text.add_theme_font_size_override("normal_font_size", 16)
		dialog_text.add_theme_color_override("default_color", MenuTheme.C_TEXT_WARM)
	# Tutorial header
	var tut_header: Label = tutorial_bubble.find_child("Header", true, false)
	if tut_header != null:
		tut_header.add_theme_font_size_override("font_size", 16)
		tut_header.add_theme_color_override("font_color", MenuTheme.C_GOLD)
	if tutorial_text != null and is_instance_valid(tutorial_text):
		tutorial_text.add_theme_font_size_override("normal_font_size", 14)
		tutorial_text.add_theme_color_override("default_color", MenuTheme.C_TEXT_WARM)
	# Dialog/Tutorial/Battle buttons
	for btn in [dialog_continue_btn, tutorial_got_it_btn, battle_detail_btn, battle_mainline_next_btn, battle_back_menu_btn]:
		if btn != null and is_instance_valid(btn):
			MenuTheme.apply_button_theme(btn, 16)
	# Battle result header + winner
	var res_header: Label = battle_result_panel.find_child("Header", true, false)
	if res_header != null:
		res_header.add_theme_font_size_override("font_size", 22)
		res_header.add_theme_color_override("font_color", MenuTheme.C_GOLD)
	if battle_result_winner != null and is_instance_valid(battle_result_winner):
		battle_result_winner.add_theme_font_size_override("font_size", 18)
	if battle_result_stats != null and is_instance_valid(battle_result_stats):
		battle_result_stats.add_theme_font_size_override("normal_font_size", 14)
		battle_result_stats.add_theme_color_override("default_color", MenuTheme.C_TEXT_WARM)
	# Round 3:主按钮烫金主题(web 风格)— 联机大厅 启动/添加 AI/改队伍/应用队伍
	for primary_btn in [lobby_start_btn, lobby_add_ai_btn, lobby_host_apply_btn, lobby_apply_team_btn]:
		if primary_btn != null and is_instance_valid(primary_btn):
			MenuTheme.apply_primary_button_theme(primary_btn)
	# 次按钮(web 风格)— 返回/取消/移除/切换观战
	for secondary_btn in [lobby_back_btn, lobby_to_spec_btn, lobby_remove_ai_btn]:
		if secondary_btn != null and is_instance_valid(secondary_btn):
			MenuTheme.apply_secondary_button_theme(secondary_btn)


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
	match unit_type:
		"swordsman":
			return "剑士"
		"archer":
			return "弓箭手"
		"knight":
			return "骑士"
		"warlock":
			return "术士"
		"healer":
			return "治疗师"
		"lancer":
			return "枪骑兵"
		"warrior":
			return "战士"
		"berserker":
			return "狂战士"
		"dragon_rider":
			return "龙骑士"
		"falcon_knight":
			return "隼骑士"
		"blade_master":
			return "剑圣"
		"paladin":
			return "圣骑士"
		"sniper":
			return "狙击手"
		"sage":
			return "贤者"
		"saint":
			return "圣者"
		_:
			return unit_type


func _skill_cn(skill_id: String) -> String:
	match skill_id:
		"heal":
			return "治疗"
		"snipe":
			return "狙击"
		"double_strike":
			return "连击"
		"arcane_strike":
			return "奥术冲击"
		_:
			return skill_id


# P2.6+: 地形名中文化(用于 InfoPanel 加成区段)
func _terrain_cn(terrain_name: String, subtype: String = "") -> String:
	# subtype 优先 — castle_floor / castle_wall / etc.
	if subtype != "":
		match subtype:
			"castle_floor": return "城堡内部"
			"castle_wall": return "城墙"
			"castle_door": return "城门"
			"castle_throne": return "王座厅"
			"castle_stairs": return "城梯"
			"castle_vault": return "金库"
	match terrain_name:
		"plain": return "平原"
		"forest": return "森林"
		"mountain": return "山地"
		"snow_peak": return "雪峰"
		"river": return "河流"
		"road": return "道路"
		"bridge": return "桥梁"
		"castle": return "城堡"
		"village": return "村庄"
		"barracks": return "兵营"
		"gate": return "城门"
		_:
			return terrain_name


# P2.6+: 指挥官名中文化(用于 InfoPanel 战斗加成区段)
func _commander_cn(co_id: String) -> String:
	match co_id:
		"anna": return "安娜"
		"yun": return "云"
		"boss": return "Boss"
		_:
			return co_id


func _color_name_cn(color_name: String) -> String:
	match color_name:
		"red":
			return "红色"
		"blue":
			return "蓝色"
		"green":
			return "绿色"
		"yellow":
			return "黄色"
		_:
			return color_name


func _upsert_editor_map_as_lobby_preset(map_data: Dictionary) -> void:
	var map_id := str(map_data.get("id", ""))
	if map_id == "":
		return
	var preset_id := "custom:%s" % map_id
	var biome := str(map_data.get("biome", "grass"))
	var label := str(map_data.get("name", map_id))
	if not label.begins_with("Custom: "):
		label = "Custom: %s" % label
	for i in range(_preset_options.size()):
		var existing: Dictionary = _preset_options[i]
		if str(existing.get("id", "")) == preset_id:
			_preset_options[i] = {"id": preset_id, "biome": biome}
			if map_preset_option != null and is_instance_valid(map_preset_option) and i < map_preset_option.item_count:
				map_preset_option.set_item_text(i, label)
			return
	_preset_options.append({"id": preset_id, "biome": biome})
	if map_preset_option != null and is_instance_valid(map_preset_option):
		map_preset_option.add_item(label)


func _on_lobby_pressed() -> void:
	# P0 UX gate:进联机大厅前先看主菜单里有没有中断存档。
	# 有的话弹「已经有中断存档,将放弃该中断,是否继续?」
	# - 是 → 调 discard_suspend,然后 _enter_lobby_view()
	# - 否 → 留在主菜单,不进 lobby(避免 stale suspend 污染新房间)
	# 没有就跳过 gate,直接进 lobby。
	if _user_name == "" or _user_name == "Player":
		# 没 user_name 的早期流程不挡人 — 跟原行为一致。
		_enter_lobby_view()
		return
	NetworkClient.list_saves(
		_user_name, Callable(self, "_on_lobby_list_saves_for_suspend_check")
	)


func _on_lobby_list_saves_for_suspend_check(body: Variant, _code: int = 0) -> void:
	if not (body is Dictionary):
		# 拉失败兜底:不进 lobby,避免在用户不知情的情况下与 suspend 冲突。
		_update_status("无法检查中断存档,请稍后重试")
		return
	var suspend: Variant = body.get("suspend", null)
	if not (suspend is Dictionary):
		_enter_lobby_view()
		return
	var suspend_game_id: int = int(suspend.get("game_id", 0))
	if suspend_game_id <= 0:
		_enter_lobby_view()
		return
	_show_confirm(
		"放弃中断存档",
		"已经有中断存档,将放弃该中断,是否继续?",
		Callable(self, "_on_lobby_discard_suspend_yes"),
		Callable(self, "_on_lobby_discard_suspend_no"),
	)


func _on_lobby_discard_suspend_yes() -> void:
	# 用户点「继续」→ 先调 discard_suspend,等服务端 ack 后再进 lobby。
	# 注意:_hide_confirm() 已在 _on_confirm_yes_pressed 里调用过了。
	if _user_name == "" or _user_name == "Player":
		_enter_lobby_view()
		return
	_update_status("正在放弃中断存档...")
	NetworkClient.discard_suspend(
		_user_name, Callable(self, "_on_lobby_discard_suspend_response")
	)


func _on_lobby_discard_suspend_no() -> void:
	# 用户点「取消」→ 留在主菜单。什么都不做。
	_update_status("已取消,可继续点 ▶ 继续中断战斗")


func _on_lobby_discard_suspend_response(body: Variant, code: int = 0) -> void:
	if code < 200 or code >= 300:
		_update_status("放弃中断失败,请重试")
		return
	var cleared: bool = bool((body as Dictionary).get("cleared", false)) if body is Dictionary else false
	if not cleared:
		_update_status("没有可放弃的中断存档")
	_enter_lobby_view()


func _enter_lobby_view() -> void:
	_entry_flow = "lobby"
	_show_view("lobby")
	_apply_lobby_theme()
	_stop_lobby_polling()
	_selected_room_id = 0
	if lobby_name_input != null and is_instance_valid(lobby_name_input):
		lobby_name_input.text = "%s 的房间" % _user_name
	_setup_lobby_join_options()
	NetworkClient.get_unlocked_commanders(_user_name, Callable(self, "_on_commanders_response"))
	_load_lobby_presets()
	_load_lobby_audio_tracks()
	_setup_lobby_win_condition_options()
	_refresh_room_list()
	_show_lobby_choose()

func _show_lobby_choose() -> void:
	_lobby_mode = "choose"
	if choose_panel != null and is_instance_valid(choose_panel):
		choose_panel.visible = true
	_set_lobby_detail_visible(false)
	# 切回非 in_room 模式:恢复 BottomBar 默认 anchor + 切换按钮可见性
	_restore_lobby_default_layout()
	if lobby_back_btn != null and is_instance_valid(lobby_back_btn):
		lobby_back_btn.text = "返回主菜单"


func _show_lobby_create_view() -> void:
	_lobby_mode = "create"
	if choose_panel != null and is_instance_valid(choose_panel):
		choose_panel.visible = false
	_set_lobby_detail_visible(false)
	_set_lobby_dualcol_visible(true)
	_set_lobby_leftcol_visible(true)
	_set_lobby_rightcol_visible(true)
	_set_lobby_join_controls_visible(false)
	_set_lobby_map_controls_visible(true)
	_set_lobby_left_header_text("地图预览")
	_set_lobby_global_team_controls_visible(false)
	if lobby_commander_option != null and is_instance_valid(lobby_commander_option):
		lobby_commander_option.visible = false
	if create_room_btn != null and is_instance_valid(create_room_btn):
		create_room_btn.text = "开启游戏"
	_restore_lobby_default_layout()
	_layout_lobby_entry_form()
	if lobby_back_btn != null and is_instance_valid(lobby_back_btn):
		lobby_back_btn.text = "返回模式选择"


func _show_lobby_join_view() -> void:
	_lobby_mode = "join"
	if choose_panel != null and is_instance_valid(choose_panel):
		choose_panel.visible = false
	_set_lobby_detail_visible(false)
	_set_lobby_dualcol_visible(true)
	_set_lobby_leftcol_visible(true)
	_set_lobby_rightcol_visible(false)
	_set_lobby_join_controls_visible(true)
	_set_lobby_map_controls_visible(false)
	_set_lobby_left_header_text("房间列表")
	_set_lobby_global_team_controls_visible(true)
	if lobby_commander_option != null and is_instance_valid(lobby_commander_option):
		lobby_commander_option.visible = true
	_restore_lobby_default_layout()
	_layout_lobby_entry_form()
	if lobby_back_btn != null and is_instance_valid(lobby_back_btn):
		lobby_back_btn.text = "返回模式选择"


func _show_lobby_in_room() -> void:
	_lobby_mode = "in_room"
	if choose_panel != null and is_instance_valid(choose_panel):
		choose_panel.visible = false
	_set_lobby_detail_visible(true)
	# 房主控制台: 隐藏冗余(房间列表/选房加入是加入者用的,房主不需要)
	_set_lobby_leftcol_visible(false)
	_set_lobby_rightcol_visible(true)
	# 隐藏 HostRow(改队伍)/ LobbyToSpecBtn(切换观战)/ MidSectionBar / AiCommanderOption
	_hide_lobby_host_extras(true)
	# 启动游戏按钮移到 RightCol 底部,BottomBar 那个隐藏
	if lobby_start_btn != null and is_instance_valid(lobby_start_btn):
		lobby_start_btn.visible = false
	if start_game_inline_btn != null and is_instance_valid(start_game_inline_btn):
		start_game_inline_btn.visible = true
	# 动态调整 anchor 让所有元素 fit 进 LobbyFrame(viewport 720 时 LobbyFrame ~648px)
	_layout_lobby_in_room()
	# 同步玩家人数 Label(从 MapPresetOption 的 selected text 取,如 "balanced_2p_15 (2p)")
	if player_count_label != null and is_instance_valid(player_count_label):
		if map_preset_option != null and is_instance_valid(map_preset_option) and map_preset_option.selected >= 0:
			player_count_label.text = map_preset_option.get_item_text(map_preset_option.selected)
		else:
			player_count_label.text = "—"
	if lobby_back_btn != null and is_instance_valid(lobby_back_btn):
		lobby_back_btn.text = "返回主菜单"


func _set_lobby_detail_visible(v: bool) -> void:
	for node_name in ["LobbyInfoBar", "LobbyTopBar", "LobbyDualCol",
			"MidSectionBar", "LobbyList", "HostRow", "LobbyToSpecBtn",
			"AiConfigRow", "AiCommanderOption", "AiActionRow", "BottomBar"]:
		if lobby_view == null:
			continue
		var n: Node = lobby_view.get_node_or_null("LobbyFrame/" + node_name)
		if n != null:
			n.visible = v


# 房主控制台专用: 隐藏"加入者/对局中"才需要的控件
# 保留 LobbyList(玩家列表) + AiConfigRow/AiActionRow(房主需要加 AI)
# 隐藏:LeftCol(房间列表,房主不需要选房) / HostRow(改队伍,合并到 TeamOption) /
#       LobbyToSpecBtn(切换观战) / MidSectionBar(对局管理,合并到顶部信息)
#       AiCommanderOption(AI 指挥官,合并到 AiConfigRow)
func _hide_lobby_host_extras(hide: bool) -> void:
	if lobby_view == null:
		return
	for node_name in ["HostRow", "LobbyToSpecBtn", "MidSectionBar", "AiCommanderOption"]:
		var n: Node = lobby_view.get_node_or_null("LobbyFrame/" + node_name)
		if n != null:
			n.visible = not hide


# 房主控制台专用: 动态调整 in_room 视图下各元素的 anchor
# 让 TopBar / InfoBar / LobbyList / DualCol / AI 配置 / BottomBar
# 全部 fit 进 LobbyFrame(避免 UI 溢出 viewport 720)
#
# viewport 720,LobbyFrame anchor_top=0.05 / anchor_bottom=0.95 → y=36-684,高 648
# 布局(LobbyFrame 内部坐标,0-648):
#   TopBar:       0-44     (标题,44px 紧凑)
#   InfoBar:      48-72    (Game # + 玩家数,24px)
#   LobbyList:    80-176   (玩家列表,96px)
#   DualCol:      184-504  (RightCol 装 6 项 + 启动按钮,320px)
#   AiConfigRow:  512-544  (AI 类型+性格+难度,32px)
#   AiActionRow:  552-584  (添加 AI + 选 AI + 移除,32px)
#   BottomBar:    592-632  (返回主菜单,40px) → 总 632,LobbyFrame 648 内,留 16px 边距
func _layout_lobby_in_room() -> void:
	if lobby_view == null:
		return
	var lobby_list: Control = lobby_view.get_node_or_null("LobbyFrame/LobbyList") as Control
	if lobby_list != null:
		lobby_list.offset_top = 80.0
		lobby_list.offset_bottom = 176.0
	var dual_col: Control = lobby_view.get_node_or_null("LobbyFrame/LobbyDualCol") as Control
	if dual_col != null:
		dual_col.offset_top = 184.0
		dual_col.offset_bottom = 504.0
	var ai_cfg: Control = lobby_view.get_node_or_null("LobbyFrame/AiConfigRow") as Control
	if ai_cfg != null:
		ai_cfg.offset_top = 512.0
		ai_cfg.offset_bottom = 544.0
	var ai_act: Control = lobby_view.get_node_or_null("LobbyFrame/AiActionRow") as Control
	if ai_act != null:
		ai_act.offset_top = 552.0
		ai_act.offset_bottom = 584.0
	# BottomBar 改成绝对位置(原 anchor 1.0/1.0 → 顶部往上挪,避免溢出 LobbyFrame 648)
	var bb: Control = lobby_view.get_node_or_null("LobbyFrame/BottomBar") as Control
	if bb != null:
		bb.anchor_top = 0.0
		bb.anchor_bottom = 0.0
		bb.offset_top = 592.0
		bb.offset_bottom = 632.0


# 还原 LobbyFrame 各元素到 tscn 默认 anchor(切回非 in_room 模式时调用)
# 复位 LobbyList / DualCol / AiConfigRow / AiActionRow / BottomBar
func _restore_lobby_default_layout() -> void:
	if lobby_view == null:
		return
	var lobby_list: Control = lobby_view.get_node_or_null("LobbyFrame/LobbyList") as Control
	if lobby_list != null:
		lobby_list.offset_top = 442.0
		lobby_list.offset_bottom = 580.0
	var dual_col: Control = lobby_view.get_node_or_null("LobbyFrame/LobbyDualCol") as Control
	if dual_col != null:
		dual_col.offset_top = 112.0
		dual_col.offset_bottom = -16.0
	var ai_cfg: Control = lobby_view.get_node_or_null("LobbyFrame/AiConfigRow") as Control
	if ai_cfg != null:
		ai_cfg.offset_top = 654.0
		ai_cfg.offset_bottom = 686.0
	var ai_act: Control = lobby_view.get_node_or_null("LobbyFrame/AiActionRow") as Control
	if ai_act != null:
		ai_act.offset_top = 726.0
		ai_act.offset_bottom = 758.0
	var bb: Control = lobby_view.get_node_or_null("LobbyFrame/BottomBar") as Control
	if bb != null:
		# 还原 tscn 默认 anchor(右下角)
		bb.anchor_left = 1.0
		bb.anchor_right = 1.0
		bb.anchor_top = 0.0
		bb.anchor_bottom = 0.0
		bb.offset_left = -340.0
		bb.offset_top = -56.0
		bb.offset_right = -16.0
		bb.offset_bottom = -16.0
	# 切回非 in_room:BottomBar 的 LobbyStartBtn 可见,RightCol 的 StartGameInlineBtn 隐藏
	if lobby_start_btn != null and is_instance_valid(lobby_start_btn):
		lobby_start_btn.visible = true
	if start_game_inline_btn != null and is_instance_valid(start_game_inline_btn):
		start_game_inline_btn.visible = false


func _layout_lobby_entry_form() -> void:
	if lobby_view == null:
		return
	var dual_col: Control = lobby_view.get_node_or_null("LobbyFrame/LobbyDualCol") as Control
	if dual_col != null:
		dual_col.offset_top = 24.0
		dual_col.offset_bottom = -48.0


func _set_lobby_dualcol_visible(v: bool) -> void:
	if lobby_view == null:
		return
	var dc: Node = lobby_view.get_node_or_null("LobbyFrame/LobbyDualCol")
	if dc != null:
		dc.visible = v


func _set_lobby_leftcol_visible(v: bool) -> void:
	if lobby_view == null:
		return
	var left_col: Node = lobby_view.get_node_or_null("LobbyFrame/LobbyDualCol/LeftCol")
	if left_col != null:
		left_col.visible = v


func _set_lobby_rightcol_visible(v: bool) -> void:
	if lobby_view == null:
		return
	var right_col: Node = lobby_view.get_node_or_null("LobbyFrame/LobbyDualCol/RightCol")
	if right_col != null:
		right_col.visible = v


func _set_lobby_join_controls_visible(v: bool) -> void:
	for node in [room_list, room_select_option, join_mode_option, refresh_rooms_btn, join_selected_btn]:
		if node != null and is_instance_valid(node):
			node.visible = v
	var row := lobby_view.get_node_or_null("LobbyFrame/LobbyDualCol/LeftCol/LeftBtnRow") if lobby_view != null else null
	if row != null:
		row.visible = v
	var spacer := lobby_view.get_node_or_null("LobbyFrame/LobbyDualCol/LeftCol/LeftBottomSpacer") if lobby_view != null else null
	if spacer != null:
		spacer.visible = v


func _set_lobby_map_controls_visible(v: bool) -> void:
	if lobby_view == null:
		return
	var picker: Control = lobby_view.get_node_or_null("LobbyFrame/LobbyDualCol/LeftCol/MapPickerRow") as Control
	if picker != null:
		picker.visible = v
	if map_preview_panel != null and is_instance_valid(map_preview_panel):
		map_preview_panel.visible = v


func _set_lobby_left_header_text(text: String) -> void:
	if lobby_view == null:
		return
	var header: Label = lobby_view.get_node_or_null("LobbyFrame/LobbyDualCol/LeftCol/LeftHeader") as Label
	if header != null:
		header.text = text


func _set_lobby_global_team_controls_visible(v: bool) -> void:
	if lobby_view == null:
		return
	var team_row: Control = lobby_view.get_node_or_null("LobbyFrame/LobbyDualCol/RightCol/TeamRow") as Control
	if team_row != null:
		team_row.visible = v


func _on_create_card_pressed() -> void:
	_show_lobby_create_view()


func _on_join_card_pressed() -> void:
	_show_lobby_join_view()
	_refresh_room_list()


func _on_lobby_create_response(body: Dictionary, _code: int = 0) -> void:
	_game_id = int(body.get("id", 0))
	if _game_id <= 0:
		lobby_status_label.text = "创建失败"
		_pending_lobby_start_after_create = false
		return
	UserSettings.set_value("session.v1.last_game_id", _game_id)
	lobby_game_id_label.text = "对局 #%d · 等待中" % _game_id
	# 自动 join
	var seat_index := clampi(_selected_lobby_seat_index, 0, _selected_lobby_player_count() - 1)
	var seat_color := str(MapPreviewSummary.SEAT_COLORS[seat_index])
	NetworkClient.join_game(_game_id, _user_name, seat_color,
		_selected_lobby_seat_team(seat_index), "", Callable(self, "_on_lobby_join_response"), seat_index)


# 创建房间后自动加 AI(等同 webui app.js 的默认行为)
# join_game 完成后调这里 → add-ai + add-ai(凑够 2 个 AI)
func _on_lobby_join_response(body: Variant, _code: int = 0) -> void:
	if body is Dictionary:
		_player_id = int(body.get("id", 0))
		if _player_id <= 0:
			_player_id = int(body.get("player_id", 0))
		if _player_id <= 0:
			var p: Variant = body.get("player", {})
			if p is Dictionary:
				_player_id = int(p.get("id", 0))
	if _player_id > 0:
		GameState.local_player_id = _player_id
		UserSettings.set_value("session.v1.last_player_id", _player_id)
	if lobby_game_id_label != null and is_instance_valid(lobby_game_id_label):
		lobby_game_id_label.text = "对局 #%d" % _game_id
	_show_lobby_in_room()
	# 拉 lobby 启动轮询
	_start_lobby_polling()
	if _entry_flow == "lobby_create" and _game_id > 0 and _pending_lobby_start_after_create:
		_continue_lobby_create_pipeline()


func _auto_add_ai_after_lobby_create() -> void:
	# 用 lobby AI 选项(如果有);默认 rules/balanced/normal
	var difficulty := "normal"
	var agent_kind := "rules"
	var personality := "balanced"
	if ai_difficulty_option != null and is_instance_valid(ai_difficulty_option):
		var idx: int = ai_difficulty_option.selected
		var items: Array = ["easy", "normal", "hard"]
		if idx >= 0 and idx < items.size():
			difficulty = items[idx]
	NetworkClient.add_ai_player(_game_id, difficulty, agent_kind, personality, Callable(self, "_on_auto_add_ai_response").bind(true))


func _on_auto_add_ai_response(_body: Variant, _code: int, _expect_more: bool = false) -> void:
	pass  # 这里只触发,可以扩展添加多个 AI


func _selected_lobby_player_count() -> int:
	var selected: Dictionary = _selected_lobby_map_data()
	if selected.is_empty():
		return 2
	return clampi(int(selected.get("recommended_players", 2)), 2, MapPreviewSummary.SEAT_COLORS.size())


func _selected_lobby_seat_commanders() -> Dictionary:
	var result: Dictionary = {}
	for seat_index in range(_selected_lobby_player_count()):
		var commander_id := _lobby_seat_commander_id(seat_index)
		if commander_id != "":
			result[seat_index] = commander_id
	return result


func _continue_lobby_create_pipeline() -> void:
	_pending_lobby_ai_seats.clear()
	_pending_lobby_team_updates.clear()
	var host_seat := clampi(_selected_lobby_seat_index, 0, _selected_lobby_player_count() - 1)
	if _player_id > 0:
		_pending_lobby_team_updates.append({
			"player_id": _player_id,
			"team": _selected_lobby_seat_team(host_seat),
		})
	var player_count := _selected_lobby_player_count()
	for seat_index in range(player_count):
		if seat_index != host_seat and _lobby_ai_replacement_for_seat(seat_index):
			_pending_lobby_ai_seats.append(seat_index)
	if lobby_status_label != null and is_instance_valid(lobby_status_label):
		lobby_status_label.text = "正在应用座位、AI 与队伍设置..."
	_continue_lobby_ai_creation()


func _continue_lobby_ai_creation() -> void:
	if _pending_lobby_ai_seats.is_empty():
		_continue_lobby_team_updates()
		return
	var seat_index: int = int(_pending_lobby_ai_seats.pop_front())
	NetworkClient.add_ai_player(
		_game_id,
		_selected_ai_difficulty(),
		_selected_ai_kind(),
		_lobby_ai_personality_for_seat(seat_index),
		Callable(self, "_on_lobby_configured_ai_added").bind(seat_index)
	)


func _on_lobby_configured_ai_added(body: Variant, code: int = 0, seat_index: int = 0) -> void:
	if code >= 200 and code < 300 and body is Dictionary:
		var pid := int(body.get("id", body.get("player_id", 0)))
		var player: Variant = body.get("player", {})
		if pid <= 0 and player is Dictionary:
			pid = int(player.get("id", 0))
		if pid > 0:
			NetworkClient.update_player_seat(
				_game_id,
				pid,
				_player_id,
				seat_index,
				Callable(self, "_on_lobby_configured_ai_seated").bind(pid, seat_index)
			)
			return
	elif lobby_status_label != null and is_instance_valid(lobby_status_label):
		lobby_status_label.text = "AI 座位配置失败，继续尝试开启游戏..."
	_continue_lobby_ai_creation()


func _on_lobby_configured_ai_seated(_body: Variant, _code: int = 0, pid: int = 0, seat_index: int = 0) -> void:
	if pid > 0:
		_pending_lobby_team_updates.append({
			"player_id": pid,
			"team": _selected_lobby_seat_team(seat_index),
		})
	_continue_lobby_ai_creation()


func _continue_lobby_team_updates() -> void:
	if _pending_lobby_team_updates.is_empty():
		_start_configured_lobby_game()
		return
	var update: Dictionary = _pending_lobby_team_updates.pop_front()
	NetworkClient.update_player_team(
		_game_id,
		int(update.get("player_id", 0)),
		_player_id,
		str(update.get("team", "")),
		Callable(self, "_on_lobby_configured_team_updated")
	)


func _on_lobby_configured_team_updated(_body: Variant, _code: int = 0) -> void:
	_continue_lobby_team_updates()


func _start_configured_lobby_game() -> void:
	if not _pending_lobby_start_after_create:
		return
	if lobby_status_label != null and is_instance_valid(lobby_status_label):
		lobby_status_label.text = "配置完成，正在开启游戏..."
	NetworkClient.start_game(_game_id, Callable(self, "_on_lobby_start_response"))




func _setup_lobby_join_options() -> void:
	if join_mode_option != null and is_instance_valid(join_mode_option):
		join_mode_option.clear()
		join_mode_option.add_item("作为玩家加入")
		join_mode_option.add_item("作为观战者加入")
		join_mode_option.select(0)
	if team_option != null and is_instance_valid(team_option):
		team_option.clear()
		# M4.16+ fix:统一 team 命名为 team_a/b/c/d(与 _lobby_seat_team_ids + server
		# JoinGameRequest.team 对齐)。原来用 color(red/blue/green/yellow)作 team_id
		# 跟 _lobby_seat_team_ids(team_a/b/c/d)不一致,创房和手动 join 走两套字段。
		team_option.add_item("自动分队")
		team_option.add_item("队伍 A")
		team_option.add_item("队伍 B")
		team_option.add_item("队伍 C")
		team_option.add_item("队伍 D")
		team_option.select(0)
	_on_join_mode_changed(0)


func _selected_join_role() -> String:
	if join_mode_option != null and is_instance_valid(join_mode_option) and join_mode_option.selected == 1:
		return "spectator"
	return "player"


func _on_join_mode_changed(_index: int) -> void:
	if team_option != null and is_instance_valid(team_option):
		team_option.disabled = _selected_join_role() == "spectator"


func _selected_join_team() -> String:
	# M4.16+ fix:返回 team_a/b/c/d(不再是 red/blue/green/yellow),
	# 跟 _lobby_seat_team_ids + server JoinGameRequest.team 命名一致。
	# 1V1 free-for-all: server 端 team=None → fallback 到 _team_of(player_id) → 各自独立。
	# 2V2: 双方玩家传相同的 team_a 或 team_b → server AI 会把同 team 当 ally(不打)。
	if team_option == null or not is_instance_valid(team_option):
		return ""
	if _selected_join_role() == "spectator":
		return ""
	match team_option.selected:
		1:
			return "team_a"
		2:
			return "team_b"
		3:
			return "team_c"
		4:
			return "team_d"
		_:
			return ""


func _team_cn(team: String) -> String:
	match team:
		"red":
			return "红队"
		"blue":
			return "蓝队"
		"green":
			return "绿队"
		"yellow":
			return "黄队"
		_:
			return team


func _setup_lobby_commander_options(unlocked: Array = []) -> void:
	_lobby_commander_ids = [""]
	_lobby_ai_commander_ids = [""]
	if lobby_commander_option != null and is_instance_valid(lobby_commander_option):
		lobby_commander_option.clear()
		lobby_commander_option.add_item("不选择指挥官")
	if ai_commander_option != null and is_instance_valid(ai_commander_option):
		ai_commander_option.clear()
		ai_commander_option.add_item("电脑自动选择指挥官")
	# 如果 API 返回空(新玩家无解锁),fallback 到硬编码默认指挥官(等同 webui 行为)
	var pool: Array = unlocked if unlocked.size() > 0 else ["yun", "anna"]
	for item in pool:
		var commander_id := str(item)
		if commander_id == "" or _lobby_commander_ids.has(commander_id):
			continue
		_lobby_commander_ids.append(commander_id)
		_lobby_ai_commander_ids.append(commander_id)
		if lobby_commander_option != null and is_instance_valid(lobby_commander_option):
			lobby_commander_option.add_item(_commander_label(commander_id))
		if ai_commander_option != null and is_instance_valid(ai_commander_option):
			ai_commander_option.add_item("电脑: %s" % _commander_label(commander_id))
	if lobby_commander_option != null and is_instance_valid(lobby_commander_option):
		lobby_commander_option.select(0)
		lobby_commander_option.disabled = _lobby_commander_ids.size() <= 1
	if ai_commander_option != null and is_instance_valid(ai_commander_option):
		ai_commander_option.select(0)
		ai_commander_option.disabled = _lobby_ai_commander_ids.size() <= 1


func _selected_lobby_win_condition() -> String:
	# P2.4 polish:win_condition 现在固定为 rout(rout+seize 二合一)。
	# 下拉里只有 1 项,这个函数保持接口以便未来扩展。
	if win_condition_option == null or not is_instance_valid(win_condition_option):
		return "rout"
	return "rout"


func _selected_lobby_commander() -> String:
	if lobby_commander_option == null or not is_instance_valid(lobby_commander_option):
		return ""
	var index := lobby_commander_option.selected
	if index < 0 or index >= _lobby_commander_ids.size():
		return ""
	return _lobby_commander_ids[index]


func _selected_lobby_ai_commander() -> String:
	if ai_commander_option == null or not is_instance_valid(ai_commander_option):
		return ""
	var index := ai_commander_option.selected
	if index < 0 or index >= _lobby_ai_commander_ids.size():
		return ""
	return _lobby_ai_commander_ids[index]


func _selected_lobby_ai_commanders() -> Dictionary:
	var commander_id := _selected_lobby_ai_commander()
	if commander_id == "":
		return {}
	var result: Dictionary = {}
	var host_seat := clampi(_selected_lobby_seat_index, 0, _selected_lobby_player_count() - 1)
	for seat_index in range(_selected_lobby_player_count()):
		if seat_index == host_seat:
			continue
		if _lobby_ai_replacement_for_seat(seat_index):
			result[seat_index] = commander_id
	return result


# 胜利条件下拉:P2.4 polish 后只剩 rout+seize 二合一,默认 "rout"
func _setup_lobby_win_condition_options() -> void:
	if win_condition_option == null or not is_instance_valid(win_condition_option):
		return
	win_condition_option.clear()
	win_condition_option.add_item("消灭所有敌方单位,或占领对方总部", 0)
	win_condition_option.select(0)


func _setup_lobby_bgm_options(tracks: Array = []) -> void:
	_lobby_bgm_track_ids = [""]
	if lobby_bgm_option != null and is_instance_valid(lobby_bgm_option):
		lobby_bgm_option.clear()
		lobby_bgm_option.add_item("不播放背景音乐")
	for item in tracks:
		if not item is Dictionary:
			continue
		var track_id := str(item.get("track_id", ""))
		if track_id == "" or _lobby_bgm_track_ids.has(track_id):
			continue
		var title := str(item.get("title", track_id))
		var category := str(item.get("category", ""))
		var label := title if category == "" else "%s (%s)" % [title, category]
		_lobby_bgm_track_ids.append(track_id)
		if lobby_bgm_option != null and is_instance_valid(lobby_bgm_option):
			lobby_bgm_option.add_item(label)
	if lobby_bgm_option != null and is_instance_valid(lobby_bgm_option):
		lobby_bgm_option.select(0)
		lobby_bgm_option.disabled = _lobby_bgm_track_ids.size() <= 1


func _selected_lobby_bgm_track() -> String:
	if lobby_bgm_option == null or not is_instance_valid(lobby_bgm_option):
		return ""
	var index := lobby_bgm_option.selected
	if index < 0 or index >= _lobby_bgm_track_ids.size():
		return ""
	return _lobby_bgm_track_ids[index]


func _load_lobby_audio_tracks() -> void:
	_setup_lobby_bgm_options()
	NetworkClient.list_audio_tracks(Callable(self, "_on_audio_tracks_response"))


func _on_audio_tracks_response(body: Variant, code: int = 0) -> void:
	if code < 200 or code >= 300 or not (body is Dictionary):
		_setup_lobby_bgm_options()
		return
	var tracks: Array = body.get("tracks", []) if body.get("tracks", []) is Array else []
	_setup_lobby_bgm_options(tracks)


func _setup_lobby_ai_options() -> void:
	if ai_difficulty_option != null and is_instance_valid(ai_difficulty_option):
		ai_difficulty_option.clear()
		ai_difficulty_option.add_item("电脑普通")
		ai_difficulty_option.add_item("电脑简单")
		ai_difficulty_option.add_item("电脑困难")
		ai_difficulty_option.select(0)
	if ai_kind_option != null and is_instance_valid(ai_kind_option):
		ai_kind_option.clear()
		ai_kind_option.add_item("规则电脑")
		ai_kind_option.add_item("大模型电脑")
		ai_kind_option.select(0)
	if ai_personality_option != null and is_instance_valid(ai_personality_option):
		ai_personality_option.clear()
		ai_personality_option.add_item("均衡")
		ai_personality_option.add_item("激进")
		ai_personality_option.add_item("保守")
		ai_personality_option.select(0)


func _selected_ai_difficulty() -> String:
	if ai_difficulty_option == null or not is_instance_valid(ai_difficulty_option):
		return "normal"
	match ai_difficulty_option.selected:
		1:
			return "easy"
		2:
			return "hard"
		_:
			return "normal"


func _selected_ai_kind() -> String:
	if ai_kind_option != null and is_instance_valid(ai_kind_option) and ai_kind_option.selected == 1:
		return "llm"
	return "rules"


func _selected_ai_personality() -> String:
	if ai_personality_option == null or not is_instance_valid(ai_personality_option):
		return "balanced"
	match ai_personality_option.selected:
		1:
			return "aggressive"
		2:
			return "conservative"
		_:
			return "balanced"


func _load_lobby_presets() -> void:
	if map_preset_option == null or not is_instance_valid(map_preset_option):
		return
	_setup_lobby_map_player_count_options()
	map_preset_option.clear()
	map_preset_option.add_item("标准双人图")
	_all_preset_options = [{"id": "balanced_2p_15", "name": "balanced_2p_15", "biome": "grass", "recommended_players": 2}]
	_render_lobby_map_picker_options()
	_render_lobby_map_preview()
	NetworkClient.list_presets(Callable(self, "_on_lobby_presets_response"))


func _on_lobby_presets_response(body: Variant, _code: int = 0) -> void:
	if map_preset_option == null or not is_instance_valid(map_preset_option):
		return
	var maps: Array = []
	if body is Dictionary:
		maps = (body as Dictionary).get("maps", [])
	if maps.is_empty():
		_render_lobby_map_preview()
		return
	map_preset_option.clear()
	_all_preset_options = []
	for item in maps:
		if not item is Dictionary:
			continue
		var id: String = str(item.get("id", ""))
		if id == "":
			continue
		var name: String = str(item.get("name", id))
		var biome: String = str(item.get("biome", "grass"))
		var raw_players = item.get("recommended_players", 0)
		var players: int = 0
		if raw_players != null:
			players = int(raw_players)
		var label := name
		if players > 0:
			label = "%s (%d 人)" % [name, players]
		var record: Dictionary = {"id": id, "name": name, "biome": biome, "recommended_players": players}
		for key in item.keys():
			if not record.has(key):
				record[key] = item[key]
		_all_preset_options.append(record)
	_render_lobby_map_picker_options()
	_render_lobby_map_preview()


func _setup_lobby_map_player_count_options() -> void:
	if map_player_count_option == null or not is_instance_valid(map_player_count_option):
		return
	map_player_count_option.clear()
	map_player_count_option.add_item("全部地图")
	for players in [2, 3, 4]:
		map_player_count_option.add_item("%d人地图" % players)
	map_player_count_option.select(0)


func _on_lobby_map_player_count_selected(index: int) -> void:
	_lobby_preset_filter_players = index + 1 if index > 0 else 0
	_render_lobby_map_picker_options()
	_render_lobby_map_preview()


func _on_lobby_map_preset_selected(_index: int) -> void:
	_render_lobby_map_preview()


func _render_lobby_map_picker_options() -> void:
	if map_preset_option == null or not is_instance_valid(map_preset_option):
		return
	map_preset_option.clear()
	_preset_options = []
	for item in _all_preset_options:
		if not item is Dictionary:
			continue
		var record: Dictionary = item
		var players := int(record.get("recommended_players", 0))
		if _lobby_preset_filter_players > 0 and players != _lobby_preset_filter_players:
			continue
		_preset_options.append(record)
		var name := str(record.get("name", record.get("id", "map")))
		var label := name
		if players > 0:
			label = "%s (%d人)" % [name, players]
		map_preset_option.add_item(label)
	if _preset_options.is_empty():
		map_preset_option.add_item("暂无该人数地图")
		map_preset_option.disabled = true
	else:
		map_preset_option.disabled = false
		map_preset_option.select(0)


func _render_lobby_map_preview() -> void:
	if map_faction_summary == null or not is_instance_valid(map_faction_summary):
		return
	var map_data := _selected_lobby_map_data()
	if map_data.is_empty():
		map_faction_summary.text = "请选择地图查看初始部署。"
		if map_preview_texture != null and is_instance_valid(map_preview_texture):
			map_preview_texture.texture = null
		_render_lobby_seat_columns({})
		return
	var summary: Dictionary = MapPreviewSummary.summarize_map(map_data)
	var title := str(summary.get("name", summary.get("id", "Map")))
	var size_text := "%dx%d" % [int(summary.get("width", 0)), int(summary.get("height", 0))]
	var players := int(summary.get("recommended_players", 0))
	map_faction_summary.text = "[b]%s[/b]  %s  %dP\n%s" % [title, size_text, players, MapPreviewSummary.build_faction_lines(summary)]
	if map_preview_texture != null and is_instance_valid(map_preview_texture):
		map_preview_texture.texture = MapPreviewSummary.render_preview_texture(map_data, 9)
	_render_lobby_seat_columns(summary)


func _selected_lobby_map_data() -> Dictionary:
	var selected := _selected_lobby_preset_record()
	if selected.is_empty():
		return {}
	var map_id := str(selected.get("id", ""))
	var map_data := selected.duplicate(true)
	if map_data.has("layout") and map_data.has("size"):
		return map_data
	var disk_map := _load_lobby_map_from_disk(map_id)
	if not disk_map.is_empty():
		for key in disk_map.keys():
			map_data[key] = disk_map[key]
	return map_data


func _selected_lobby_preset_record() -> Dictionary:
	var idx := 0
	if map_preset_option != null and is_instance_valid(map_preset_option):
		idx = map_preset_option.selected
	if idx >= 0 and idx < _preset_options.size():
		return (_preset_options[idx] as Dictionary)
	return {}


func _load_lobby_map_from_disk(map_id: String) -> Dictionary:
	if map_id.begins_with("custom:"):
		return {}
	for path in ["res://../game/maps/%s.json" % map_id, "res://../../game/maps/%s.json" % map_id, "res://../../../game/maps/%s.json" % map_id]:
		if not FileAccess.file_exists(path):
			continue
		var file := FileAccess.open(path, FileAccess.READ)
		if file == null:
			continue
		var parsed: Variant = JSON.parse_string(file.get_as_text())
		file.close()
		if parsed is Dictionary:
			return parsed
	return {}


func _render_lobby_seat_columns(summary: Dictionary = {}) -> void:
	if lobby_seat_grid == null or not is_instance_valid(lobby_seat_grid):
		return
	# P2 修复:每张座位卡里有 prev_btn / next_btn / action_btn 等,它们的
	# pressed signal 可能在 emit 过程中又来调用本函数导致 child.free() 时
	# "Object freed or unreferenced" 报错。我们改用 queue_free() 来避开这
	# 个问题 — Godot 会等当前帧 idle 处理时才真正释放,且对 PackedScene 的
	# 常驻节点也能友好处理。
	var children := lobby_seat_grid.get_children()
	for child in children:
		if not is_instance_valid(child):
			continue
		lobby_seat_grid.remove_child(child)
		child.queue_free()
	if summary.is_empty():
		var map_data := _selected_lobby_map_data()
		if not map_data.is_empty():
			summary = MapPreviewSummary.summarize_map(map_data)
	var factions: Dictionary = summary.get("factions", {})
	var players := int(summary.get("recommended_players", factions.size()))
	players = mini(maxi(players, 0), MapPreviewSummary.SEAT_COLORS.size())
	for i in range(players):
		var color_id: String = MapPreviewSummary.SEAT_COLORS[i]
		lobby_seat_grid.add_child(_build_lobby_seat_card(i, color_id))


func _build_lobby_seat_card(index: int, color_id: String) -> Panel:
	var card := Panel.new()
	card.name = "Seat%d" % (index + 1)
	card.custom_minimum_size = Vector2(0, 160)
	card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	MenuTheme.apply_panel_theme(card, Color(0.08, 0.13, 0.1, 0.96))
	var box := VBoxContainer.new()
	box.name = "SeatBox"
	box.anchor_right = 1.0
	box.anchor_bottom = 1.0
	box.offset_left = 8.0
	box.offset_top = 6.0
	box.offset_right = -8.0
	box.offset_bottom = -6.0
	box.add_theme_constant_override("separation", 3)
	card.add_child(box)
	var top_row := HBoxContainer.new()
	top_row.name = "SeatTopRow"
	top_row.add_theme_constant_override("separation", 6)
	box.add_child(top_row)
	var portrait := ColorRect.new()
	portrait.name = "FactionPortrait"
	portrait.custom_minimum_size = Vector2(34, 34)
	portrait.color = _seat_display_color(color_id)
	top_row.add_child(portrait)
	var status_box := VBoxContainer.new()
	status_box.name = "SeatStatusBox"
	status_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	top_row.add_child(status_box)
	var seat_name := Label.new()
	seat_name.name = "SeatName"
	seat_name.text = "%d席  %s" % [index + 1, _seat_color_label(color_id)]
	seat_name.add_theme_color_override("font_color", _seat_display_color(color_id))
	status_box.add_child(seat_name)
	var occupant := Label.new()
	occupant.name = "SeatOccupant"
	var occupant_name := _lobby_seat_occupant_name(index)
	occupant.text = "等待玩家入座" if occupant_name == "" else "%s 已入座" % occupant_name
	occupant.add_theme_color_override("font_color", MenuTheme.C_TEXT_WARM)
	status_box.add_child(occupant)
	var control_row := HBoxContainer.new()
	control_row.name = "SeatControlRow"
	control_row.add_theme_constant_override("separation", 6)
	box.add_child(control_row)
	var action_btn := Button.new()
	action_btn.name = "SeatActionBtn"
	action_btn.text = "入座"
	action_btn.custom_minimum_size = Vector2(50, 26)
	MenuTheme.apply_button_theme(action_btn, 12)
	action_btn.pressed.connect(
		_on_lobby_seat_action_pressed.bind(index),
		Object.CONNECT_DEFERRED
	)
	control_row.add_child(action_btn)
	var side_option := OptionButton.new()
	side_option.name = "TeamSideOption"
	side_option.custom_minimum_size = Vector2(78, 26)
	for side_name in ["Team A", "Team B", "Team C", "Team D"]:
		side_option.add_item(side_name)
	side_option.select(_lobby_team_index_for_seat(index))
	side_option.item_selected.connect(_on_lobby_seat_team_selected.bind(index))
	control_row.add_child(side_option)
	var ai_toggle := CheckBox.new()
	ai_toggle.name = "AiReplaceToggle"
	ai_toggle.text = "AI替补"
	ai_toggle.custom_minimum_size = Vector2(80, 26)
	ai_toggle.button_pressed = _lobby_ai_replacement_for_seat(index)
	ai_toggle.toggled.connect(
		_on_lobby_seat_ai_toggled.bind(index),
		Object.CONNECT_DEFERRED
	)
	ai_toggle.add_theme_color_override("font_color", MenuTheme.C_TEXT_DIM)
	control_row.add_child(ai_toggle)
	var ai_style_row := HBoxContainer.new()
	ai_style_row.name = "AiStyleRow"
	ai_style_row.add_theme_constant_override("separation", 6)
	box.add_child(ai_style_row)
	var ai_style_label := Label.new()
	ai_style_label.text = "AI风格"
	ai_style_label.custom_minimum_size = Vector2(70, 24)
	ai_style_label.add_theme_color_override("font_color", MenuTheme.C_TEXT_DIM)
	ai_style_row.add_child(ai_style_label)
	var ai_personality := OptionButton.new()
	ai_personality.name = "AiPersonalityOption"
	ai_personality.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	ai_personality.custom_minimum_size = Vector2(0, 26)
	ai_personality.add_item("均衡")
	ai_personality.add_item("激进")
	ai_personality.add_item("保守")
	ai_personality.select(_lobby_ai_personality_index_for_seat(index))
	ai_personality.disabled = not _lobby_ai_replacement_for_seat(index)
	ai_personality.item_selected.connect(_on_lobby_seat_ai_personality_selected.bind(index))
	ai_style_row.add_child(ai_personality)
	var commander_row := HBoxContainer.new()
	commander_row.name = "CommanderRow"
	commander_row.add_theme_constant_override("separation", 4)
	box.add_child(commander_row)
	var commanders_loaded: bool = _lobby_commander_ids.size() > 1
	var prev_btn := Button.new()
	prev_btn.name = "PrevCommanderBtn"
	prev_btn.text = "<"
	prev_btn.custom_minimum_size = Vector2(28, 22)
	prev_btn.disabled = not commanders_loaded
	MenuTheme.apply_button_theme(prev_btn, 12)
	# CONNECT_DEFERRED:让回调在 idle 阶段执行,避免 pressed emit 中途自
	# 由其持有的 prev/next 按钮树时撞上 "Object freed while signal is
	# being emitted" 报错。
	prev_btn.pressed.connect(
		_on_lobby_seat_commander_step.bind(index, -1),
		Object.CONNECT_DEFERRED
	)
	commander_row.add_child(prev_btn)
	var commander_label := Label.new()
	commander_label.name = "CommanderName"
	commander_label.text = _lobby_seat_commander_label(index) if commanders_loaded else "加载中…"
	commander_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	commander_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	commander_label.add_theme_color_override("font_color", MenuTheme.C_TEXT_DIM)
	commander_row.add_child(commander_label)
	var next_btn := Button.new()
	next_btn.name = "NextCommanderBtn"
	next_btn.text = ">"
	next_btn.custom_minimum_size = Vector2(28, 22)
	next_btn.disabled = not commanders_loaded
	MenuTheme.apply_button_theme(next_btn, 12)
	next_btn.pressed.connect(
		_on_lobby_seat_commander_step.bind(index, 1),
		Object.CONNECT_DEFERRED
	)
	commander_row.add_child(next_btn)
	var ability := Label.new()
	ability.name = "CommanderAbility"
	ability.text = _lobby_seat_commander_ability_text(index)
	ability.add_theme_color_override("font_color", MenuTheme.C_TEXT_DIM)
	box.add_child(ability)
	return card


func _lobby_team_index_for_seat(seat_index: int) -> int:
	if seat_index >= 0 and seat_index < _lobby_seat_team_ids.size():
		match _lobby_seat_team_ids[seat_index]:
			"team_b": return 1
			"team_c": return 2
			"team_d": return 3
			_: return 0
	return mini(maxi(seat_index, 0), 3)


func _lobby_team_id_for_index(index: int) -> String:
	match index:
		1: return "team_b"
		2: return "team_c"
		3: return "team_d"
		_: return "team_a"


func _selected_lobby_seat_team(seat_index: int) -> String:
	if seat_index >= 0 and seat_index < _lobby_seat_team_ids.size():
		return _lobby_seat_team_ids[seat_index]
	return _lobby_team_id_for_index(seat_index)


func _lobby_ai_replacement_for_seat(seat_index: int) -> bool:
	if seat_index >= 0 and seat_index < _lobby_seat_ai_replacements.size():
		return bool(_lobby_seat_ai_replacements[seat_index])
	return false


func _lobby_ai_personality_for_seat(seat_index: int) -> String:
	if seat_index >= 0 and seat_index < _lobby_seat_ai_personalities.size():
		var personality := str(_lobby_seat_ai_personalities[seat_index])
		if personality in ["aggressive", "balanced", "conservative"]:
			return personality
	return "balanced"


func _lobby_ai_personality_index_for_seat(seat_index: int) -> int:
	match _lobby_ai_personality_for_seat(seat_index):
		"aggressive": return 1
		"conservative": return 2
		_: return 0


func _lobby_ai_personality_for_index(index: int) -> String:
	match index:
		1: return "aggressive"
		2: return "conservative"
		_: return "balanced"


func _lobby_seat_occupant_name(seat_index: int) -> String:
	if seat_index >= 0 and seat_index < _lobby_seat_occupants.size():
		return str(_lobby_seat_occupants[seat_index])
	return ""


func _lobby_seat_commander_id(seat_index: int) -> String:
	if _lobby_commander_ids.is_empty():
		return ""
	var idx := 0
	if seat_index >= 0 and seat_index < _lobby_seat_commander_indices.size():
		idx = int(_lobby_seat_commander_indices[seat_index])
	idx = clampi(idx, 0, _lobby_commander_ids.size() - 1)
	return _lobby_commander_ids[idx]


# 服务器真值同步:把 game.battle_config.seat_commanders 写入本地镜像,使
# 大厅其他玩家调左右的指挥官时,本端 2s 轮询后立刻看到。server-authoritative:
# 永远以服务端返回为准(乐观更新被 server 接受后会写回 seat_commanders)。
func _sync_lobby_seat_commanders(game: Dictionary) -> void:
	if _lobby_commander_ids.is_empty():
		return
	var battle_config_v = game.get("battle_config", null)
	if battle_config_v == null or not (battle_config_v is Dictionary):
		return
	var raw_seat_commanders = battle_config_v.get("seat_commanders", null)
	if raw_seat_commanders == null or not (raw_seat_commanders is Dictionary):
		return
	var seat_commanders: Dictionary = raw_seat_commanders
	while _lobby_seat_commander_indices.size() < MapPreviewSummary.SEAT_COLORS.size():
		_lobby_seat_commander_indices.append(0)
	for seat_v in seat_commanders.keys():
		var seat_index := int(seat_v)
		if seat_index < 0 or seat_index >= _lobby_seat_commander_indices.size():
			continue
		var commander_id := str(seat_commanders[seat_v])
		var idx: int = _lobby_commander_ids.find(commander_id)
		if idx < 0:
			continue
		_lobby_seat_commander_indices[seat_index] = idx


func _lobby_seat_commander_label(seat_index: int) -> String:
	var commander_id := _lobby_seat_commander_id(seat_index)
	return "未选择" if commander_id == "" else _commander_label(commander_id)


func _lobby_seat_commander_ability_text(seat_index: int) -> String:
	var commander_id := _lobby_seat_commander_id(seat_index)
	match commander_id:
		"yun": return "能力：稳健推进"
		"anna": return "能力：快速抢点"
		"": return "能力：默认规则"
		_: return "能力：专属指挥"


func _on_lobby_seat_team_selected(option_index: int, seat_index: int) -> void:
	while _lobby_seat_team_ids.size() <= seat_index:
		_lobby_seat_team_ids.append("team_a")
	_lobby_seat_team_ids[seat_index] = _lobby_team_id_for_index(option_index)


func _on_lobby_seat_ai_toggled(pressed: bool, seat_index: int) -> void:
	while _lobby_seat_ai_replacements.size() <= seat_index:
		_lobby_seat_ai_replacements.append(false)
	while _lobby_seat_ai_personalities.size() <= seat_index:
		_lobby_seat_ai_personalities.append("balanced")
	while _lobby_seat_occupants.size() <= seat_index:
		_lobby_seat_occupants.append("")
	_lobby_seat_ai_replacements[seat_index] = pressed
	if _game_id <= 0 or seat_index < 0:
		_render_lobby_seat_columns()
		return
	# 只房主能换人。/start 后 game.status != "waiting",后端会拒绝。
	if not _lobby_is_host:
		_update_status("只有房主可以替换该席位为 AI。")
		_render_lobby_seat_columns()
		return
	var existing_pid: int = 0
	var existing_is_ai: bool = false
	for p in _lobby_last_players:
		if not p is Dictionary:
			continue
		if int(p.get("seat", -1)) == seat_index and not bool(p.get("is_spectator", false)):
			existing_pid = int(p.get("id", 0))
			existing_is_ai = bool(p.get("is_ai", false))
			break
	if not pressed:
		# 取消 AI 替补 → 把这个 seat 上的 AI 删掉(若是 AI)。人类不动。
		if existing_pid > 0 and existing_is_ai:
			_lobby_seat_occupants[seat_index] = ""
			NetworkClient.remove_player(_game_id, existing_pid,
				Callable(self, "_on_lobby_seat_ai_remove_response").bind(seat_index))
		_render_lobby_seat_columns()
		return
	# 按下 AI → 乐观显示"入座中"→ 先删旧的(人类或 AI),再加 AI。
	var ai_placeholder := "电脑-%d (入座中…)" % (seat_index + 1)
	_lobby_seat_occupants[seat_index] = ai_placeholder
	if existing_pid > 0:
		NetworkClient.remove_player(_game_id, existing_pid,
			Callable(self, "_on_lobby_seat_ai_add_after_remove").bind(seat_index))
	else:
		_request_add_ai_for_seat(seat_index)
	_render_lobby_seat_columns()


func _request_add_ai_for_seat(seat_index: int) -> void:
	if _game_id <= 0:
		return
	var personality := _lobby_ai_personality_for_seat(seat_index)
	NetworkClient.add_ai_player(_game_id, "normal", "rules", personality,
		Callable(self, "_on_lobby_seat_ai_add_response").bind(seat_index))


func _on_lobby_seat_ai_remove_response(body: Variant, _code: int, seat_index: int) -> void:
	if not (body is Dictionary) or int(body.get("ok", 0)) != 1:
		_update_status("移除失败:%s" % str(body.get("detail", body)))
		return
	_refresh_lobby_view()


func _on_lobby_seat_ai_add_after_remove(_body: Variant, _code: int, seat_index: int) -> void:
	_request_add_ai_for_seat(seat_index)


func _on_lobby_seat_ai_add_response(body: Variant, code: int, seat_index: int) -> void:
	if code < 200 or code >= 300:
		_update_status("AI 入座失败:HTTP %d" % code)
		return
	_refresh_lobby_view()


func _on_lobby_seat_ai_personality_selected(option_index: int, seat_index: int) -> void:
	while _lobby_seat_ai_personalities.size() <= seat_index:
		_lobby_seat_ai_personalities.append("balanced")
	_lobby_seat_ai_personalities[seat_index] = _lobby_ai_personality_for_index(option_index)


func _on_lobby_seat_commander_step(seat_index: int, delta: int) -> void:
	if _lobby_commander_ids.is_empty():
		return
	while _lobby_seat_commander_indices.size() <= seat_index:
		_lobby_seat_commander_indices.append(0)
	_lobby_seat_commander_indices[seat_index] = posmod(int(_lobby_seat_commander_indices[seat_index]) + delta, _lobby_commander_ids.size())
	_render_lobby_seat_columns()
	# P1:同步服务端 — 房主改任意 seat / 玩家改自己 seat
	var new_idx: int = int(_lobby_seat_commander_indices[seat_index])
	new_idx = clampi(new_idx, 0, _lobby_commander_ids.size() - 1)
	var commander_id: String = str(_lobby_commander_ids[new_idx])
	if commander_id == "":
		# "" = "未选择",服务端应保持现有值 / 或保留空。直接发空字符串让服务端 reset
		pass
	# 找 seat 上 player_id
	var target_pid: int = 0
	for p in _lobby_last_players:
		if not p is Dictionary:
			continue
		if bool(p.get("is_spectator", false)):
			continue
		if int(p.get("seat", -1)) == seat_index:
			target_pid = int(p.get("id", 0))
			break
	if _player_id <= 0 or _game_id <= 0:
		return
	# 空座位:用 player_id=0 + seat=seat_index 让后端只写
	# battle_config.seat_commanders[seat],不需要 player 记录。
	if target_pid <= 0:
		NetworkClient.update_player_commander(
			_game_id, 0, _player_id, commander_id,
			Callable(self, "_on_lobby_seat_commander_response").bind(seat_index, delta),
			seat_index
		)
		return
	# 发送后端;成功才确认;失败回退 1 step 并 toast
	NetworkClient.update_player_commander(
		_game_id,
		target_pid,
		_player_id,
		commander_id,
		Callable(self, "_on_lobby_seat_commander_response").bind(seat_index, delta)
	)


func _on_lobby_seat_commander_response(body: Variant, _code: int, seat_index: int, delta: int) -> void:
	if not (body is Dictionary) or int(body.get("ok", 0)) != 1:
		# 回退:把 index 倒回(因为我们乐观更新了)
		if _lobby_commander_ids.is_empty():
			return
		while _lobby_seat_commander_indices.size() <= seat_index:
			_lobby_seat_commander_indices.append(0)
		var n: int = _lobby_commander_ids.size()
		_lobby_seat_commander_indices[seat_index] = posmod(int(_lobby_seat_commander_indices[seat_index]) - delta, n)
		_render_lobby_seat_columns()
		var detail: String = "切换指挥官失败"
		if body is Dictionary and body.has("detail"):
			detail = "切换指挥官失败: %s" % str(body.get("detail"))
		_update_status(detail)


func _on_lobby_seat_action_pressed(seat_index: int) -> void:
	_selected_lobby_seat_index = clampi(seat_index, 0, MapPreviewSummary.SEAT_COLORS.size() - 1)
	while _lobby_seat_occupants.size() <= seat_index:
		_lobby_seat_occupants.append("")
	_lobby_seat_occupants[seat_index] = _user_name
	while _lobby_seat_ai_replacements.size() <= seat_index:
		_lobby_seat_ai_replacements.append(false)
	_lobby_seat_ai_replacements[seat_index] = false
	if lobby_status_label != null and is_instance_valid(lobby_status_label):
		lobby_status_label.text = "%s 已入座 %d席。" % [_user_name, seat_index + 1]
	_render_lobby_seat_columns()
	if _game_id > 0 and _player_id > 0:
		NetworkClient.update_player_seat(
			_game_id,
			_player_id,
			_player_id,
			_selected_lobby_seat_index,
			Callable(self, "_on_lobby_seat_update_response")
		)


func _on_lobby_seat_update_response(_body: Variant, code: int = 0) -> void:
	if code >= 200 and code < 300:
		_refresh_lobby_view()
	elif lobby_status_label != null and is_instance_valid(lobby_status_label):
		lobby_status_label.text = "座位调整失败，请刷新房间后重试。"


func _seat_color_label(color_id: String) -> String:
	match color_id:
		"red": return "红方"
		"blue": return "蓝方"
		"green": return "绿方"
		"yellow": return "黄方"
		_: return color_id


func _seat_display_color(color_id: String) -> Color:
	match color_id:
		"red": return Color(0.95, 0.32, 0.24)
		"blue": return Color(0.36, 0.56, 1.0)
		"green": return Color(0.3, 0.8, 0.38)
		"yellow": return Color(0.95, 0.78, 0.25)
		_: return MenuTheme.C_TEXT_WARM


func _refresh_room_list() -> void:
	if room_list != null and is_instance_valid(room_list):
		room_list.text = "正在加载房间..."
	if room_select_option != null and is_instance_valid(room_select_option):
		room_select_option.clear()
		room_select_option.add_item("正在加载房间...")
		room_select_option.disabled = true
	if join_selected_btn != null and is_instance_valid(join_selected_btn):
		join_selected_btn.disabled = true
	NetworkClient.list_games(Callable(self, "_on_room_list_response"))


func _on_room_list_response(body: Variant, _code: int = 0) -> void:
	_lobby_rooms = []
	_selected_room_id = 0
	var games: Array = body if body is Array else []
	for g in games:
		if not g is Dictionary:
			continue
		if str(g.get("status", "")) != "waiting":
			continue
		_lobby_rooms.append(g)
	if _lobby_rooms.is_empty():
		if room_list != null and is_instance_valid(room_list):
			room_list.text = "暂无等待中的房间。可在右侧创建新房间。"
		if room_select_option != null and is_instance_valid(room_select_option):
			room_select_option.clear()
			room_select_option.add_item("暂无等待房间")
			room_select_option.disabled = true
		if join_selected_btn != null and is_instance_valid(join_selected_btn):
			join_selected_btn.disabled = true
		return
	if room_select_option != null and is_instance_valid(room_select_option):
		room_select_option.clear()
		room_select_option.disabled = false
	for i in range(_lobby_rooms.size()):
		var g: Dictionary = _lobby_rooms[i]
		var id: int = int(g.get("id", 0))
		if i == 0:
			_selected_room_id = id
		var name := str(g.get("name", "Room"))
		if room_select_option != null and is_instance_valid(room_select_option):
			room_select_option.add_item("#%d  %s" % [id, name])
	_render_room_list()


func _on_room_selected(index: int) -> void:
	if index < 0 or index >= _lobby_rooms.size():
		_selected_room_id = 0
	else:
		var g: Dictionary = _lobby_rooms[index]
		_selected_room_id = int(g.get("id", 0))
	_render_room_list()


func _render_room_list() -> void:
	var lines: Array = []
	var selected_name := ""
	var selected_cap := 0
	for g in _lobby_rooms:
		if not g is Dictionary:
			continue
		var id: int = int(g.get("id", 0))
		var marker := ">" if id == _selected_room_id else " "
		var name := str(g.get("name", "Room"))
		var preset := str(g.get("map_preset", "?"))
		var cap := int(g.get("capacity", 0))
		if id == _selected_room_id:
			selected_name = name
			selected_cap = cap
		lines.append("%s #%d  %s  [%s]  cap:%d" % [marker, id, name, preset, cap])
	if room_list != null and is_instance_valid(room_list):
		room_list.text = "\n".join(lines)
	if lobby_status_label != null and is_instance_valid(lobby_status_label) and _selected_room_id > 0:
		lobby_status_label.text = "已选择房间 #%d: %s (上限 %d 人)" % [_selected_room_id, selected_name, selected_cap]
	if join_selected_btn != null and is_instance_valid(join_selected_btn):
		join_selected_btn.disabled = _selected_room_id <= 0


func _on_create_room_pressed() -> void:
	_entry_flow = "lobby_create"
	var room_name := "%s room" % _user_name
	if lobby_name_input != null and is_instance_valid(lobby_name_input):
		var typed := lobby_name_input.text.strip_edges()
		if typed != "":
			room_name = typed
	var preset_id := "balanced_2p_15"
	var biome := "grass"
	var idx := 0
	if map_preset_option != null and is_instance_valid(map_preset_option):
		idx = map_preset_option.selected
	if idx >= 0 and idx < _preset_options.size():
		var selected: Dictionary = _preset_options[idx]
		preset_id = str(selected.get("id", preset_id))
		biome = str(selected.get("biome", biome))
	if lobby_status_label != null and is_instance_valid(lobby_status_label):
		lobby_status_label.text = "正在创建并开启游戏..."
	_pending_lobby_start_after_create = true
	NetworkClient.create_game(
		room_name,
		preset_id,
		biome,
		_selected_lobby_win_condition(),
		_selected_lobby_commander(),
		_selected_lobby_bgm_track(),
		_selected_lobby_ai_commanders(),
		Callable(self, "_on_lobby_create_response"),
		_selected_lobby_seat_commanders(),
		"free"
	)


func _on_join_selected_pressed() -> void:
	if _selected_room_id <= 0:
		return
	_entry_flow = "lobby_join"
	_game_id = _selected_room_id
	if lobby_status_label != null and is_instance_valid(lobby_status_label):
		lobby_status_label.text = "正在加入房间 #%d..." % _game_id
	NetworkClient.join_game(_game_id, _user_name, "red", _selected_join_team(), _selected_join_role(), Callable(self, "_on_lobby_join_response"))


func _start_lobby_polling() -> void:
	if _lobby_poll_timer == null:
		_lobby_poll_timer = Timer.new()
		_lobby_poll_timer.wait_time = 2.0
		_lobby_poll_timer.timeout.connect(_refresh_lobby_view)
		add_child(_lobby_poll_timer)
	_lobby_poll_timer.start()
	_refresh_lobby_view()


func _stop_lobby_polling() -> void:
	if _lobby_poll_timer != null:
		_lobby_poll_timer.stop()


func _refresh_lobby_view() -> void:
	if _game_id <= 0:
		return
	NetworkClient.get_game_state(_game_id, Callable(self, "_on_lobby_state"))


func _on_lobby_state(body: Dictionary, _code: int = 0) -> void:
	if not (body is Dictionary): return
	# /state 返回 GameStateOut:{ game, players, tiles, ... }。比 /lobby 的 teams
	# 聚合更细 - 能逐玩家拿到 seat / is_ai / team / is_spectator,这是 P1#8
	# 房主行级控制 + P1#7 观战者显示的前提。
	var game: Dictionary = body.get("game", {}) if body.get("game", {}) is Dictionary else {}
	var players: Array = body.get("players", []) if body.get("players", []) is Array else []
	var max_spec: int = int(game.get("max_spectators", 8))
	_lobby_last_players = players
	for i in range(_lobby_seat_occupants.size()):
		_lobby_seat_occupants[i] = ""
	var host_player_id := 0
	for p in players:
		if p is Dictionary and not bool(p.get("is_spectator", false)):
			var pid_for_host := int(p.get("id", 0))
			if pid_for_host > 0 and (host_player_id <= 0 or pid_for_host < host_player_id):
				host_player_id = pid_for_host
			var pseat := int(p.get("seat", -1))
			if pseat >= 0 and pseat < _lobby_seat_occupants.size():
				_lobby_seat_occupants[pseat] = str(p.get("user_name", ""))
				if bool(p.get("is_ai", false)) and pseat < _lobby_seat_ai_personalities.size():
					var personality := str(p.get("agent_personality", "balanced"))
					if personality in ["aggressive", "balanced", "conservative"]:
						_lobby_seat_ai_personalities[pseat] = personality
	# 自己的 seat / 观战标记(房主 = seat 0)
	var self_seat: int = -1
	var self_is_spec: bool = false
	for p in players:
		if p is Dictionary and int(p.get("id", -1)) == int(_player_id):
			self_seat = int(p.get("seat", -1))
			self_is_spec = bool(p.get("is_spectator", false))
			break
	if self_seat >= 0:
		_selected_lobby_seat_index = self_seat
	_lobby_is_host = (_player_id > 0 and _player_id == host_player_id)
	_lobby_self_is_spectator = self_is_spec
	# 同步 seat_commanders(大厅里其他玩家改的指挥官要实时反映给当前客户端)。
	# server-authoritative:服务端 game.battle_config.seat_commanders 是真值,
	# 本地 _lobby_seat_commander_indices 是 UI 镜像 — 始终以服务端为准。
	_sync_lobby_seat_commanders(game)
	_render_lobby_seat_columns()
	# 渲染逐玩家列表(含 seat / 队伍 / 观战标记)
	var lines: Array = []
	var spec_count: int = 0
	var real_count: int = 0
	for p in players:
		if not p is Dictionary: continue
		var pname_v = p.get("user_name")
		var pname: String = pname_v if pname_v is String else "-"
		var color_v = p.get("color")
		var color: String = color_v if color_v is String else "red"
		var ai_v = p.get("is_ai")
		var is_ai: bool = (ai_v == true) if ai_v != null else false
		var spec_v = p.get("is_spectator")
		var is_spec: bool = (spec_v == true) if spec_v != null else false
		var id_v = p.get("id")
		var is_self: bool = (id_v == _player_id) if (id_v != null and _player_id > 0) else false
		var team_v = p.get("team")
		var team: String = team_v if team_v is String else ""
		var seat_v = p.get("seat")
		var seat: int = int(seat_v) if seat_v is int else -1
		if is_spec:
			spec_count += 1
		elif not is_ai:
			real_count += 1
		var emoji: String = "👀" if is_spec else _color_emoji(color)
		var tag: String = ""
		if is_self: tag = " (你)"
		elif is_ai: tag = " 🤖"
		var team_tag: String = " [%s]" % team if team != "" else ""
		var seat_tag: String = " #%d" % seat if seat >= 0 else ""
		lines.append("%s %s%s%s%s" % [emoji, pname, tag, team_tag, seat_tag])
	lobby_list.text = "\n".join(lines) if lines.size() > 0 else "(等待加入)"
	_render_lobby_ai_options(players)
	_render_lobby_host_controls(players)
	var total_count: int = players.size()
	lobby_status_label.text = "等待玩家加入... (%d 人 · 真人 %d · 观战 %d/%d)" % [
		total_count, real_count, spec_count, max_spec
	]
	# Start 按钮:只要有 1 名真人(非 AI/非观战)即可,后端会校验 MIN_PLAYERS
	lobby_start_btn.disabled = real_count < 1
	if start_game_inline_btn != null and is_instance_valid(start_game_inline_btn):
		start_game_inline_btn.disabled = real_count < 1


func _render_lobby_ai_options(players: Array) -> void:
	_selected_ai_player_id = 0
	if ai_player_option == null or not is_instance_valid(ai_player_option):
		return
	ai_player_option.clear()
	for p in players:
		if not (p is Dictionary):
			continue
		if not bool(p.get("is_ai", false)):
			continue
		var pid := int(p.get("id", 0))
		var name := str(p.get("user_name", "AI"))
		ai_player_option.add_item("#%d %s" % [pid, name], pid)
	if ai_player_option.item_count > 0:
		ai_player_option.select(0)
		_selected_ai_player_id = ai_player_option.get_item_id(0)
	if lobby_remove_ai_btn != null and is_instance_valid(lobby_remove_ai_btn):
		lobby_remove_ai_btn.disabled = _selected_ai_player_id <= 0


func _on_ai_player_selected(index: int) -> void:
	if ai_player_option == null or not is_instance_valid(ai_player_option):
		return
	if index < 0 or index >= ai_player_option.item_count:
		_selected_ai_player_id = 0
	else:
		_selected_ai_player_id = ai_player_option.get_item_id(index)
	if lobby_remove_ai_btn != null and is_instance_valid(lobby_remove_ai_btn):
		lobby_remove_ai_btn.disabled = _selected_ai_player_id <= 0


func _on_lobby_add_ai_pressed() -> void:
	if _game_id <= 0: return
	# POST /games/{id}/add-ai(走 NetworkClient.request)
	if lobby_status_label != null and is_instance_valid(lobby_status_label):
		lobby_status_label.text = "正在添加电脑玩家..."
	NetworkClient.add_ai_player(
		_game_id,
		_selected_ai_difficulty(),
		_selected_ai_kind(),
		_selected_ai_personality(),
		Callable(self, "_on_lobby_add_ai_response")
	)


func _on_lobby_add_ai_response(_body: Variant, _code: int = 0) -> void:
	_refresh_lobby_view()
	_refresh_room_list()


func _on_lobby_remove_ai_pressed() -> void:
	if _game_id <= 0 or _selected_ai_player_id <= 0:
		return
	if lobby_status_label != null and is_instance_valid(lobby_status_label):
		lobby_status_label.text = "正在移除电脑玩家 #%d..." % _selected_ai_player_id
	NetworkClient.remove_player(_game_id, _selected_ai_player_id, Callable(self, "_on_lobby_remove_ai_response"))


func _on_lobby_remove_ai_response(_body: Variant, _code: int = 0) -> void:
	_selected_ai_player_id = 0
	_refresh_lobby_view()
	_refresh_room_list()


func _on_lobby_apply_team_pressed() -> void:
	if _game_id <= 0 or _player_id <= 0:
		return
	var team := _selected_join_team()
	if lobby_status_label != null and is_instance_valid(lobby_status_label):
		lobby_status_label.text = "正在更新队伍..."
	NetworkClient.update_player_team(_game_id, _player_id, _player_id, team, Callable(self, "_on_lobby_team_response"))


func _on_lobby_team_response(body: Variant, code: int = 0) -> void:
	if code < 200 or code >= 300 or not (body is Dictionary):
		var msg := "Team update failed"
		if body is Dictionary:
			msg = "Team update failed: %s" % str(body.get("detail", body.get("message", msg)))
		if lobby_status_label != null and is_instance_valid(lobby_status_label):
			lobby_status_label.text = msg
		return
	var team := str(body.get("team", ""))
	if lobby_status_label != null and is_instance_valid(lobby_status_label):
		lobby_status_label.text = "队伍已更新: %s" % (_team_cn(team) if team != "" else "自由分队")
	_refresh_lobby_view()


func _render_lobby_host_controls(players: Array) -> void:
	# 房主可见 目标玩家/队伍/改队伍;所有人可见"切换观战"(转自己)。
	var host_widgets: Array = [lobby_host_player_option, lobby_host_team_option, lobby_host_apply_btn]
	for w in host_widgets:
		if w != null and is_instance_valid(w):
			w.visible = _lobby_is_host
	if lobby_to_spec_btn != null and is_instance_valid(lobby_to_spec_btn):
		lobby_to_spec_btn.visible = not _lobby_self_is_spectator
		lobby_to_spec_btn.disabled = _player_id <= 0
	if not _lobby_is_host:
		return
	if lobby_host_player_option == null or not is_instance_valid(lobby_host_player_option):
		return
	# 仅在玩家集合变化时重建下拉,避免 2s 轮询打断房主操作
	var sig := ""
	for p in players:
		if p is Dictionary:
			sig += "%d:%d:%d:%s|" % [int(p.get("id", 0)), int(p.get("seat", -1)), int(bool(p.get("is_spectator", false))), str(p.get("user_name", ""))]
	if sig == _lobby_host_player_sig:
		return
	_lobby_host_player_sig = sig
	var prev_target := _lobby_host_target_id
	lobby_host_player_option.clear()
	var idx := 0
	var selected_idx := 0
	for p in players:
		if not p is Dictionary: continue
		var pid: int = int(p.get("id", 0))
		var pname: String = str(p.get("user_name", "-"))
		var seat: int = int(p.get("seat", -1))
		var is_spec: bool = bool(p.get("is_spectator", false))
		var emoji: String = "👀" if is_spec else _color_emoji(str(p.get("color", "red")))
		lobby_host_player_option.add_item("%s #%d %s" % [emoji, seat, pname], pid)
		if pid == prev_target:
			selected_idx = idx
		idx += 1
	if lobby_host_player_option.item_count > 0:
		lobby_host_player_option.select(selected_idx)
		_lobby_host_target_id = lobby_host_player_option.get_item_id(selected_idx)
	else:
		_lobby_host_target_id = 0
	_refresh_host_team_options(players)


func _refresh_host_team_options(players: Array) -> void:
	if lobby_host_team_option == null or not is_instance_valid(lobby_host_team_option):
		return
	# 收集已有队伍名(去重,排除空)
	var seen: Dictionary = {}
	var teams: Array = []
	for p in players:
		if not p is Dictionary: continue
		var t_raw = p.get("team")
		var t: String = t_raw if t_raw is String else ""
		if t != "" and not seen.has(t):
			seen[t] = true
			teams.append(t)
	lobby_host_team_option.clear()
	_lobby_host_team_ids = [""]
	# 哨兵值:apply 时按已有队数生成新队名
	_lobby_host_team_ids.append("__new__")
	lobby_host_team_option.add_item("🆕 新建队伍")
	lobby_host_team_option.select(0)


func _on_lobby_host_player_selected(index: int) -> void:
	if lobby_host_player_option == null or not is_instance_valid(lobby_host_player_option):
		return
	if index < 0 or index >= lobby_host_player_option.item_count:
		_lobby_host_target_id = 0
	else:
		_lobby_host_target_id = lobby_host_player_option.get_item_id(index)


func _on_lobby_host_apply_pressed() -> void:
	if not _lobby_is_host or _lobby_host_target_id <= 0 or _game_id <= 0:
		return
	if lobby_host_team_option == null or not is_instance_valid(lobby_host_team_option):
		return
	var team := ""
	var tidx := lobby_host_team_option.selected
	if tidx >= 0 and tidx < _lobby_host_team_ids.size():
		var raw := _lobby_host_team_ids[tidx]
		if raw == "__new__":
			team = _next_team_name()
		else:
			team = raw
	if lobby_status_label != null and is_instance_valid(lobby_status_label):
		lobby_status_label.text = "更新玩家 #%d 队伍..." % _lobby_host_target_id
	NetworkClient.update_player_team(_game_id, _lobby_host_target_id, _player_id, team, Callable(self, "_on_lobby_team_response"))


func _next_team_name() -> String:
	# 基于已有队伍数生成不冲突的新队名(team1 / team2 / ...)
	var existing: Dictionary = {}
	for p in _lobby_last_players:
		if p is Dictionary:
			var t := str(p.get("team", ""))
			if t != "":
				existing[t] = true
	var n := 1
	while existing.has("team%d" % n):
		n += 1
	return "team%d" % n


func _on_lobby_to_spec_pressed() -> void:
	if _game_id <= 0 or _player_id <= 0 or _lobby_self_is_spectator:
		return
	if lobby_status_label != null and is_instance_valid(lobby_status_label):
		lobby_status_label.text = "切换为观战者..."
	# convert:DELETE 自己 + POST /join role=spectator(后端无独立 convert 接口,
	# 与 web 一致;join_game(role=spectator) 会分配 spectator 座位/颜色)。
	NetworkClient.remove_player(_game_id, _player_id, Callable(self, "_on_lobby_to_spec_removed"))


func _on_lobby_to_spec_removed(_body: Variant, _code: int = 0) -> void:
	# 旧座位已删;以观战者身份重新加入。新 player_id 由全局 api_response ->
	# _on_join_game_response 自动捕获。
	NetworkClient.join_game(_game_id, _user_name, "", "", "spectator", Callable(self, "_on_lobby_to_spec_joined"))


func _on_lobby_to_spec_joined(_body: Variant, _code: int = 0) -> void:
	_refresh_lobby_view()


func _on_lobby_start_pressed() -> void:
	if _game_id <= 0: return
	NetworkClient.start_game(_game_id, Callable(self, "_on_lobby_start_response"))


func _on_lobby_start_response(_body: Dictionary, _code: int = 0) -> void:
	if _code < 200 or _code >= 300:
		_pending_lobby_start_after_create = false
		if lobby_status_label != null and is_instance_valid(lobby_status_label):
			lobby_status_label.text = "开启失败"
		return
	_pending_lobby_start_after_create = false
	# 启动游戏 — 切到 game 视图,接 WS
	_show_view("game")
	NetworkClient.connect_to_game(_game_id, _player_id)
	NetworkClient.get_game_state(_game_id, Callable(self, "_on_state_poll_response"))
	_stop_lobby_polling()


func _on_lobby_back_pressed() -> void:
	if _lobby_mode == "create" or _lobby_mode == "join":
		_show_lobby_choose()
	elif _lobby_mode == "in_room":
		_show_lobby_choose()
	else:
		_stop_lobby_polling()
		_show_view("menu")


func _apply_lobby_theme() -> void:
	if lobby_start_btn != null and is_instance_valid(lobby_start_btn):
		MenuTheme.apply_button_theme(lobby_start_btn, 18)
	if lobby_add_ai_btn != null and is_instance_valid(lobby_add_ai_btn):
		MenuTheme.apply_button_theme(lobby_add_ai_btn, 14)
	if lobby_remove_ai_btn != null and is_instance_valid(lobby_remove_ai_btn):
		MenuTheme.apply_button_theme(lobby_remove_ai_btn, 14)
	if lobby_apply_team_btn != null and is_instance_valid(lobby_apply_team_btn):
		MenuTheme.apply_button_theme(lobby_apply_team_btn, 14)
	if lobby_back_btn != null and is_instance_valid(lobby_back_btn):
		MenuTheme.apply_button_theme(lobby_back_btn, 14)
	if lobby_status_label != null and is_instance_valid(lobby_status_label):
		MenuTheme.apply_label_theme(lobby_status_label, 14, MenuTheme.C_TEXT_WARM)
	if lobby_win_banner != null and is_instance_valid(lobby_win_banner):
		MenuTheme.apply_label_theme(lobby_win_banner, 12, MenuTheme.C_GOLD)
	if lobby_game_id_label != null and is_instance_valid(lobby_game_id_label):
		MenuTheme.apply_label_theme(lobby_game_id_label, 12, MenuTheme.C_TEXT_DIM)
	if lobby_list != null and is_instance_valid(lobby_list):
		lobby_list.add_theme_color_override("default_color", MenuTheme.C_TEXT_WARM)


# T:96 — MainlineView 入口 thin wrapper(完整逻辑搬到 mainline_controller.open())
func _on_mainline_pressed() -> void:
	if mainline_view != null and is_instance_valid(mainline_view):
		mainline_view.open()


# Batch A:helper 留 main.gd(batch B 函数还在 main.gd 用)
func _commander_label(commander_id: String) -> String:
	match commander_id:
		"yun":
			return "云"
		"anna":
			return "安娜"
		_:
			return commander_id


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


func _on_ml_slot_resume_response(body: Variant, _code: int, game_id: int) -> void:
	if not (body is Dictionary):
		_update_status("主线存档恢复失败: 响应异常")
		_show_view("mainline")
		return
	var p_dict: Dictionary = body.get("player", body)
	var resp_game_id: int = int(body.get("game_id", game_id))
	var resp_player_id: int = int(p_dict.get("id", 0))
	if resp_game_id > 0:
		_game_id = resp_game_id
	if resp_player_id > 0:
		_player_id = resp_player_id
		GameState.local_player_id = _player_id
		UserSettings.set_value("session.v1.last_player_id", _player_id)
	if _game_id > 0:
		UserSettings.set_value("session.v1.last_game_id", _game_id)
	_update_status("已恢复主线存档 #%d,进入棋盘..." % _game_id)
	_show_view("game")
	NetworkClient.connect_to_game(_game_id, _player_id)
	NetworkClient.get_game_state(_game_id, Callable(self, "_on_state_poll_response"))


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
	# 浮在选中单位右侧(若空间不够则左侧)
	var vp_size: Vector2 = get_viewport().get_visible_rect().size
	var bubble_size: Vector2 = action_bubble.size
	var pos: Vector2 = viewport_pos + Vector2(48, -bubble_size.y * 0.5)
	if pos.x + bubble_size.x > vp_size.x - 16.0:
		pos.x = viewport_pos.x - bubble_size.x - 48
	if pos.y + bubble_size.y > vp_size.y - 16.0:
		pos.y = vp_size.y - bubble_size.y - 16.0
	if pos.y < 32.0:
		pos.y = 32.0
	action_bubble.position = pos
	action_bubble.visible = true


func _refresh_action_bubble_buttons(unit_id: int, context: String) -> void:
	var ud: Dictionary = GameState.get_unit(unit_id) if GameState != null else {}
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
	return ""


func _hide_action_bubble() -> void:
	action_bubble.visible = false
	_selected_unit_id = -1


func _on_move_pressed() -> void:
	# M4.1 进入"移动模式":单位已经在 _move_reachable_set 里,
	# 等用户点击 board emit_tile_clicked → _on_board_tile_clicked
	if _selected_unit_id <= 0:
		_update_status("移动: 请先选中单位")
		return
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
		_attack_mode_unit_id = -1
		_attack_targets = {}
		_skill_mode_unit_id = -1
		_skill_targets = {}
		if board != null:
			board.clear_selection_marks()
		_update_status("已取消行动模式")


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
	var hp_text: String = ""
	if target_info.has("hp"):
		hp_text = " · 生命 %d" % int(target_info.get("hp", 0))
	return "[b]%s[/b] → [color=#f0c75e][b]%s[/b][/color]\n距离 %d%s\n确认后将提交攻击指令。" % [
		attacker_name, target_name, dist, hp_text
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
	else:
		lines.append("目标无法反击")
	lines.append("地形防御: +%d" % def_bonus)
	return "\n".join(lines)


func _unit_cn_name(unit: Dictionary, fallback: String = "单位") -> String:
	var unit_type := str(unit.get("unit_type", unit.get("type", "")))
	var mapped := _unit_type_cn(unit_type)
	if mapped != unit_type:
		return mapped
	if unit.has("display_cn"):
		return str(unit.get("display_cn"))
	if unit.has("name_cn"):
		return str(unit.get("name_cn"))
	return fallback


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
func _attack_unit_to(attacker_id: int, target_id: int) -> void:
	if _game_id <= 0 or _player_id <= 0:
		return
	var info: Dictionary = _attack_targets.get(target_id, {})
	var tgt_name: String = str(info.get("defender_name", "单位 #%d" % target_id))
	_update_status("正在攻击 %s (单位 #%d → #%d)..." % [tgt_name, attacker_id, target_id])
	NetworkClient.action_attack(_game_id, _player_id, attacker_id, target_id)
	# 客户端不预测伤害 - server 推 unit_attacked 事件后,从 signal args
	# 拿到 (damage, is_crit, is_kill) 直接显示。
	_attack_mode_unit_id = -1
	_attack_targets = {}
	_hide_attack_confirm()
	if board != null:
		board.clear_selection_marks()
	_hide_action_bubble()


func _active_skill_of(ud: Dictionary) -> String:
	# 返回单位的首个主动技能 id;被动技能(snipe/double_strike 走 attack 端点)返回空。
	# 主动技能目录见 server app/classes/units/skills(heal, arcane_strike)。
	# 新增主动技能需同步此处与 _on_skill_pressed 分支。
	var skills: Array = (ud.get("skills", []) as Array)
	if skills.has("heal"):
		return "heal"
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
	var can_act: bool = not bool(ud.get("has_acted", false)) and not bool(ud.get("has_moved", false)) and is_mine
	var owner_str: String = ("敌方 %s" % _color_emoji(color_name)) if not is_mine else ("[color=#f0c75e]%s[/color] (你)" % _color_emoji(color_name))
	# Bug fix: GDScript 的 str(null) 返回字面字符串 "<null>",跟空字符串
	# 比较仍然不为空 → 之前会把没有 hero_id 的普通单位误判成英雄。
	# 显式判断 Variant 类型后再 stringify。
	var hero_id_v: Variant = ud.get("hero_id", null)
	var hero_id: String = "" if hero_id_v == null else str(hero_id_v)
	_set_unit_info_portrait(hero_id)
	if unit_info_title != null and is_instance_valid(unit_info_title):
		unit_info_title.text = "✦ %s · 英雄 Lv.%d" % [name, lvl] if hero_id != "" else "⚔ %s · 等级 %d" % [name, lvl]
	var skill_names: Array[String] = []
	for skill in skills:
		skill_names.append(_skill_cn(str(skill)))
	var lines: Array = [
		("[color=#f0c75e]✦ Hero ID[/color]  %s" % mainline_view._bb_escape(hero_id)) if hero_id != "" else "",
		"[color=#a89878]⛓ 位置[/color]  (%d, %d)   %s" % [pos.x, pos.y, owner_str],
		("[color=#f4e8c1]❤ 生命[/color]  %d / %d   [color=#5fa8e8]⚡ 能量[/color]  %d/%d" % [hp, max_hp, mp, max_mp]) if max_mp > 0 else ("[color=#f4e8c1]❤ 生命[/color]  %d / %d" % [hp, max_hp]),
		"[color=#c9a14a]⚔ 攻击[/color] %d  [color=#c9a14a]🛡 防御[/color] %d  [color=#c9a14a]✨ 魔攻[/color] %d  [color=#c9a14a]🔮 魔防[/color] %d" % [atk, def, matk, mdef],
		"[color=#a89878]👣 移动力[/color] %d   [color=#a89878]🎯 攻击射程[/color] %d-%d" % [mov, range_min + 1, range_max],
		"[color=#a89878]⭐ 士气[/color] %d / 3   [color=#a89878]📜 技能[/color] %s" % [morale, ", ".join(skill_names) if skill_names.size() > 0 else "—"],
	]

	# ── 战斗加成 / Buffs 区段(P2.6+ 用户要的逐条列出) ──
	# 每条描述一个 buff 来源:地形 / 士气 / 指挥官 / 装备 / 技能 /
	# 主动技能附带效果等。空 buff 不显示该区段。
	var buffs: Array[String] = []
	# 1) 地形防御加成(单位所站格子的 TERRAIN_DEF_BONUS)
	var tile_d: Dictionary = GameState.get_tile(int(pos.x), int(pos.y)) if GameState != null else {}
	var terrain_v: Variant = tile_d.get("terrain", "")
	var terrain_name: String = "" if terrain_v == null else str(terrain_v)
	if terrain_name != "":
		var def_bonus: int = int(Config.TERRAIN_DEF_BONUS.get(terrain_name, 0))
		# castle_floor / castle_wall 等 subtype 也走同一张表
		var subtype_v: Variant = tile_d.get("subtype", "")
		var subtype: String = "" if subtype_v == null else str(subtype_v)
		if subtype != "" and Config.TERRAIN_DEF_BONUS.has(subtype):
			def_bonus = int(Config.TERRAIN_DEF_BONUS.get(subtype, 0))
		var terrain_cn := _terrain_cn(terrain_name, subtype)
		if def_bonus > 0:
			buffs.append("[color=#7ec97e]🌲 %s[/color] +%d 防御" % [terrain_cn, def_bonus])
		elif terrain_name == "castle" or terrain_name == "village" or terrain_name == "barracks":
			buffs.append("[color=#a89878]🏰 %s (无地形加成,但可驻守/产兵)[/color]" % terrain_cn)
	# 2) 士气加成(MORALE_ATK_PER_STAR / MORALE_DEF_PER_STAR)
	if morale > 0:
		var atk_pct: int = int(round(morale * Config.MORALE_ATK_PER_STAR * 100))
		var def_pct: int = int(round(morale * Config.MORALE_DEF_PER_STAR * 100))
		buffs.append("[color=#fad855]⭐ 士气 %d[/color] → +%d%% 攻击 +%d%% 防御" % [morale, atk_pct, def_pct])
	# 3) 玩家指挥官统御 Power 是否启动(仅自己单位)
	if is_mine:
		var my_player: Dictionary = GameState.get_player(_player_id) if GameState != null else {}
		var co_state_d: Dictionary = my_player.get("co_state", {}) if my_player is Dictionary else {}
		if co_state_d is Dictionary and co_state_d.get("is_power_active", false):
			var co_id: String = str(co_state_d.get("commander_id", ""))
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


func _set_unit_info_portrait(hero_id: String) -> void:
	if info_panel == null or not is_instance_valid(info_panel):
		return
	if _unit_info_portrait_tex == null:
		_unit_info_portrait_tex = TextureRect.new()
		_unit_info_portrait_tex.size = Vector2(86, 118)
		_unit_info_portrait_tex.position = Vector2(282, 108)
		_unit_info_portrait_tex.expand_mode = TextureRect.EXPAND_FIT_WIDTH_PROPORTIONAL
		_unit_info_portrait_tex.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		_unit_info_portrait_tex.mouse_filter = Control.MOUSE_FILTER_IGNORE
		info_panel.add_child(_unit_info_portrait_tex)
	if hero_id == "":
		_unit_info_portrait_tex.visible = false
		if unit_info != null and is_instance_valid(unit_info):
			unit_info.offset_right = -12.0
		return
	var portrait_path := "res://assets/heroes/portrait_%s.png" % hero_id
	if not FileAccess.file_exists(portrait_path):
		_unit_info_portrait_tex.visible = false
		if unit_info != null and is_instance_valid(unit_info):
			unit_info.offset_right = -12.0
		return
	var tex := _load_portrait(portrait_path)
	_unit_info_portrait_tex.texture = tex
	_unit_info_portrait_tex.visible = tex != null
	if unit_info != null and is_instance_valid(unit_info):
		unit_info.offset_right = -108.0 if tex != null else -12.0


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
	NetworkClient.action_claim(_game_id, _player_id, _selected_unit_id)
	_hide_action_bubble()


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
