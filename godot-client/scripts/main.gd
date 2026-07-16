extends Node
const MenuTheme = preload("res://scripts/ui/menu_theme.gd")
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
# M4.3 治疗模式状态机
var _heal_mode_unit_id: int = -1
var _heal_targets: Dictionary = {}
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
@onready var co_meter: ProgressBar = $GameView/HUD/BottomLeft/COBar
@onready var war_report_button: Button = $GameView/HUD/BottomRight/WarReportButton
@onready var war_report_panel: Panel = $GameView/HUD/WarReportPanel
@onready var war_report_close_btn: Button = $GameView/HUD/WarReportPanel/CloseBtn

# M5.1 CO Roster(全玩家头像 + 能量条 + Power 按钮)
@onready var co_roster: HBoxContainer = $GameView/HUD/CORoster

# M6.1 BGM player
@onready var bgm_player: AudioStreamPlayer = $BGMPlayer
@onready var action_log: RichTextLabel = $GameView/HUD/WarReportPanel/ActionLog
# V2 第 3 轮:InfoPanel 是左侧 30% 信息区(单位详情 + 玩家列表)
@onready var info_panel: Panel = $GameView/HUD/InfoPanel
@onready var commander_title: Label = $GameView/HUD/InfoPanel/CommanderTitle
@onready var commander_name: RichTextLabel = $GameView/HUD/InfoPanel/CommanderName
@onready var commander_co_bar: ProgressBar = $GameView/HUD/InfoPanel/CommanderCOBar
@onready var unit_info_title: Label = $GameView/HUD/InfoPanel/UnitInfoTitle
@onready var unit_info: RichTextLabel = $GameView/HUD/InfoPanel/UnitInfo
@onready var players_list: RichTextLabel = $GameView/HUD/InfoPanel/PlayersList
@onready var turn_banner: ColorRect = $GameView/TurnBannerFrame
@onready var turn_banner_label: Label = $GameView/TurnBannerFrame/TurnBannerLabel
var _turn_banner_tween: Tween = null
var _ai_pulse_tween: Tween = null

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
@onready var pause_overlay: ColorRect = $GameView/HUD/PauseOverlay
@onready var pause_panel: Panel = $GameView/HUD/PausePanel
@onready var pause_resume_btn: Button = $GameView/HUD/PausePanel/PauseList/ResumeBtn
@onready var pause_settings_btn: Button = $GameView/HUD/PausePanel/PauseList/SettingsBtn
@onready var pause_main_menu_btn: Button = $GameView/HUD/PausePanel/PauseList/MainMenuBtn
@onready var pause_quit_btn: Button = $GameView/HUD/PausePanel/PauseList/QuitBtn

# V2 第 7 轮:对话框 + 教程气泡 + 战斗结算
@onready var dialog_panel: Panel = $GameView/HUD/DialogPanel
@onready var dialog_name: Label = $GameView/HUD/DialogPanel/CharacterName
@onready var dialog_text: RichTextLabel = $GameView/HUD/DialogPanel/DialogBody/DialogText
@onready var dialog_continue_btn: Button = $GameView/HUD/DialogPanel/ContinueBtn

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
@onready var battle_back_menu_btn: Button = $GameView/HUD/BattleResultPanel/ResultBtnRow/BackMenuBtn

# V2 第 4 轮:行动气泡(5 按钮)
@onready var action_bubble: Panel = $GameView/HUD/ActionBubble
@onready var move_btn: Button = $GameView/HUD/ActionBubble/ActionList/MoveBtn
@onready var attack_btn: Button = $GameView/HUD/ActionBubble/ActionList/AttackBtn
@onready var skill_btn: Button = $GameView/HUD/ActionBubble/ActionList/SkillBtn
@onready var wait_btn: Button = $GameView/HUD/ActionBubble/ActionList/WaitBtn
@onready var claim_btn: Button = $GameView/HUD/ActionBubble/ActionList/ClaimBtn

# 当前选中单位 + 待操作 action
var _selected_unit_id: int = -1
var _selected_unit_pos: Vector2i = Vector2i(-1, -1)
# Main menu widgets (GBA 风 V2)
@onready var menu_button: Button = $Menu/CenterContainer/ButtonCol/FreePlayButton
@onready var mainline_button: Button = $Menu/CenterContainer/ButtonCol/MainlineButton

# T:96 MainlineView
@onready var mainline_view: Control = $MainlineView
@onready var ml_title: Label = $MainlineView/MLFrame/MLTitle
@onready var ml_list_container: VBoxContainer = $MainlineView/MLFrame/MLListContainer
@onready var ml_back_btn: Button = $MainlineView/MLFrame/MLBackBtn
@onready var lobby_button: Button = $Menu/CenterContainer/ButtonCol/LobbyButton
@onready var settings_button: Button = $Menu/CenterContainer/ButtonCol/SettingsButton
@onready var exit_button: Button = $Menu/CenterContainer/ButtonCol/ExitButton

# T:5 单槽存档
@onready var resume_button: Button = $Menu/CenterContainer/ButtonCol/ResumeButton
var _resume_game_id: int = 0

# T:3 基础大厅视图
@onready var lobby_view: Control = $Lobby
@onready var lobby_status_label: Label = $Lobby/LobbyFrame/LobbyStatus
@onready var lobby_list: RichTextLabel = $Lobby/LobbyFrame/LobbyList
@onready var lobby_win_banner: Label = $Lobby/LobbyFrame/LobbyWinBanner
@onready var lobby_add_ai_btn: Button = $Lobby/LobbyFrame/LobbyAddAiBtn
@onready var lobby_start_btn: Button = $Lobby/LobbyFrame/LobbyStartBtn
@onready var lobby_back_btn: Button = $Lobby/LobbyFrame/LobbyBackBtn
@onready var lobby_game_id_label: Label = $Lobby/LobbyFrame/LobbyGameIdLabel
@onready var room_list: RichTextLabel = $Lobby/LobbyFrame/RoomList
@onready var room_select_option: OptionButton = $Lobby/LobbyFrame/RoomSelectOption
@onready var refresh_rooms_btn: Button = $Lobby/LobbyFrame/RefreshRoomsBtn
@onready var join_selected_btn: Button = $Lobby/LobbyFrame/JoinSelectedBtn
@onready var create_name_input: LineEdit = $Lobby/LobbyFrame/CreateNameInput
@onready var map_preset_option: OptionButton = $Lobby/LobbyFrame/MapPresetOption
@onready var create_room_btn: Button = $Lobby/LobbyFrame/CreateRoomBtn
var _entry_flow: String = "free"
var _lobby_rooms: Array = []
var _selected_room_id: int = 0
var _preset_options: Array = []
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


func _ready() -> void:
	# Try to restore the last player_name from disk.
	var saved: Variant = UserSettings.get_value("settings.v1.player_name", "")
	if typeof(saved) == TYPE_STRING and (saved as String) != "":
		_user_name = saved
	else:
		_user_name = "学妹喵" if _random_suffix() > 0.5 else "学长"
		UserSettings.set_value("settings.v1.player_name", _user_name)

	# === GBA 火纹风主题注入(V2 第 1+2 轮:主菜单 + HUD 4 角) ===
	_apply_gba_theme()

	_show_view("menu")
	menu_button.pressed.connect(_on_free_play_pressed)
	mainline_button.pressed.connect(_on_mainline_pressed)
	lobby_button.pressed.connect(_on_lobby_pressed)
	# T:96 Mainline
	if ml_back_btn != null and is_instance_valid(ml_back_btn):
		ml_back_btn.pressed.connect(_on_ml_back_pressed)
	# T:3 大厅按钮 — 接 add-ai / start / back
	if lobby_add_ai_btn != null and is_instance_valid(lobby_add_ai_btn):
		lobby_add_ai_btn.pressed.connect(_on_lobby_add_ai_pressed)
	if lobby_start_btn != null and is_instance_valid(lobby_start_btn):
		lobby_start_btn.pressed.connect(_on_lobby_start_pressed)
	if lobby_back_btn != null and is_instance_valid(lobby_back_btn):
		lobby_back_btn.pressed.connect(_on_lobby_back_pressed)
	if room_select_option != null and is_instance_valid(room_select_option):
		room_select_option.item_selected.connect(_on_room_selected)
	if refresh_rooms_btn != null and is_instance_valid(refresh_rooms_btn):
		refresh_rooms_btn.pressed.connect(_refresh_room_list)
	if join_selected_btn != null and is_instance_valid(join_selected_btn):
		join_selected_btn.pressed.connect(_on_join_selected_pressed)
	if create_room_btn != null and is_instance_valid(create_room_btn):
		create_room_btn.pressed.connect(_on_create_room_pressed)
	settings_button.pressed.connect(_on_settings_pressed)
	exit_button.pressed.connect(_on_exit_pressed)
	if resume_button != null and is_instance_valid(resume_button):
		resume_button.pressed.connect(_on_resume_pressed)
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
		settings_theme_dropdown.add_item("深绿 GBA", 0)
		settings_theme_dropdown.add_item("金属银 silver", 1)
		settings_theme_dropdown.add_item("极简 light", 2)
		settings_theme_dropdown.item_selected.connect(_on_theme_dropdown_item_selected)
	pause_resume_btn.pressed.connect(_on_pause_resume_pressed)
	pause_settings_btn.pressed.connect(_on_pause_settings_pressed)
	pause_main_menu_btn.pressed.connect(_on_pause_main_menu_pressed)
	pause_quit_btn.pressed.connect(_on_pause_quit_pressed)
	# V2 第 7 轮:对话 + 教程 + 战斗结算
	dialog_continue_btn.pressed.connect(_on_dialog_continue_pressed)
	tutorial_got_it_btn.pressed.connect(_on_tutorial_got_it_pressed)
	battle_detail_btn.pressed.connect(_on_battle_detail_pressed)
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
		connecting_label.text = "已连接,等待 state.snapshot..."
	)
	NetworkClient.ws_disconnected.connect(func(reason):
		_update_status("WS 断开: %s" % reason)
	)
	NetworkClient.api_response.connect(func(method, path, body, code):
		# New games created / joined surface their IDs in the API reply.
		if method == "POST" and path == "/games" and (code == 200 or code == 201):
			_on_create_game_response(body)
		elif method == "POST" and path.ends_with("/join") and (code == 200 or code == 201):
			_on_join_game_response(body)
		elif method == "POST" and path.ends_with("/start") and (code == 200 or code == 201):
			_on_start_game_response(body)
	)


	# ----- Dev hook: BB_AUTO_PLAY=1 or --auto-play triggers a free-play
	# session immediately. Used by tools/ws_e2e.gd and headless smoke runs
	# to validate the WS pipeline end-to-end without manual clicks.
	if _dev_auto_play_enabled():
		_update_status("DEV auto-play: 自动开始自由模式")
		call_deferred("_on_free_play_pressed")
	# BB_AUTO_QUIT=N — quit after N seconds (for headless e2e runs).
	var quit_sec_str: String = OS.get_environment("BB_AUTO_QUIT")
	if quit_sec_str != "":
		var quit_sec: float = float(quit_sec_str)
		if quit_sec > 0.0:
			await get_tree().create_timer(quit_sec).timeout
			_update_status("DEV auto-quit 触发,退出")
			get_tree().quit(0)
	# V2 第 6 轮:游戏视图下启用菜单"设置"按钮(直接打开 SettingsPanel)
	if settings_button != null and is_instance_valid(settings_button):
		settings_button.disabled = false
		# settings_button.pressed 已经连接到 _on_settings_pressed (M3 stub)
		# 替换:让它在游戏视图下打开 SettingsPanel,菜单视图下保留原提示
		if settings_button.pressed.is_connected(_on_settings_pressed):
			settings_button.pressed.disconnect(_on_settings_pressed)
		settings_button.pressed.connect(_on_settings_open_pressed)


# ============================================================
# View transitions
# ============================================================

enum View { MENU, CONNECTING, GAME }

func _show_view(name: String) -> void:
	menu_panel.visible = (name == "menu")
	connecting_panel.visible = (name == "connecting")
	game_view.visible = (name == "game")
	lobby_view.visible = (name == "lobby")
	mainline_view.visible = (name == "mainline")


func _on_free_play_pressed() -> void:
	_entry_flow = "free"
	_update_status("正在创建对局...")
	_show_view("connecting")
	connecting_label.text = "创建对局中..."
	# T:97 — 每次启动重置,自由对局永远弹 tutorial
	_tutorial_shown = false
	# 1) Create a 2-player classic map. M3 will let the user pick.
	NetworkClient.create_game(
		"自由对局",
		"balanced_2p_15",
		"grass",
		"rout"
	)


func _on_create_game_response(body: Dictionary) -> void:
	# The create-game response is the game summary; pull id.
	_game_id = int(body.get("id", 0))
	if _game_id <= 0:
		# Some FastAPI shapes put the id under `game_id`.
		_game_id = int(body.get("game_id", 0))
	if _game_id <= 0:
		_update_status("创建失败: 响应无 id 字段")
		_show_view("menu")
		return
	UserSettings.set_value("session.v1.last_game_id", _game_id)
	connecting_label.text = "对局 #%d 已创建,加入中..." % _game_id
	# 2) Join as the local player.
	NetworkClient.join_game(_game_id, _user_name, "red")


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
		_update_status("加入失败: 响应无 player_id 字段")
		_show_view("menu")
		return
	GameState.local_player_id = _player_id
	UserSettings.set_value("session.v1.last_player_id", _player_id)
	if _entry_flow != "free":
		_show_view("lobby")
		if lobby_game_id_label != null and is_instance_valid(lobby_game_id_label):
			lobby_game_id_label.text = "Game #%d" % _game_id
		_start_lobby_polling()
		_refresh_room_list()
		return
	connecting_label.text = "已加入(玩家 #%d),添 AI 中..." % _player_id
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
	# 5) Open the WebSocket stream.
	NetworkClient.connect_to_game(_game_id, _player_id)
	# T:97 — 自由对局首次进入 game view 自动弹 tutorial
	_trigger_first_tutorial()


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
func _check_resume_session() -> void:
	if _user_name == "" or _user_name == "Player":
		return
	NetworkClient.list_games(Callable(self, "_on_list_games_for_resume"))


func _on_list_games_for_resume(body: Variant, _code: int = 0) -> void:
	# /games 返回 List[GameSummaryOut] 或错误 dict
	var games: Array = (body as Array) if body is Array else []
	for g in games:
		if not g is Dictionary: continue
		if String(g.get("status", "")) != "playing":
			continue
		# 检查 players 内有没有自己
		var players: Array = (g.get("players", []) as Array)
		for p in players:
			if not p is Dictionary: continue
			if String(p.get("user_name", "")) == _user_name:
				_resume_game_id = int(g.get("id", 0))
				if resume_button != null and is_instance_valid(resume_button):
					resume_button.text = "▶ 继续对局 #%d" % _resume_game_id
					resume_button.visible = true
				return


func _on_resume_pressed() -> void:
	if _resume_game_id <= 0:
		return
	_show_view("connecting")
	connecting_label.text = "正在重连对局 #%d..." % _resume_game_id
	NetworkClient.rejoin_game(_resume_game_id, _user_name,
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
	_show_view("game")
	NetworkClient.connect_to_game(_game_id, _player_id)


# ============================================================
# Game state → HUD
# ============================================================

func _on_state_updated(_snapshot: Dictionary) -> void:
	# Render a fresh frame from GameState.
	_repaint_board_from_state()
	_refresh_hud_from_state()
	_refresh_co_roster()
	# T:94 — battle_config.audio.bgm 触发 BGM 切换(server-authority)
	var summary: Dictionary = GameState.game_summary if GameState != null else {}
	var battle_config: Dictionary = (summary.get("battle_config", {}) as Dictionary)
	if battle_config != null and battle_config.has("audio"):
		var audio_cfg: Dictionary = battle_config.get("audio", {})
		var bgm: Dictionary = audio_cfg.get("bgm", {})
		if AudioManager != null and bgm != null and bgm.has("track_id"):
			AudioManager.apply_battle_bgm(bgm)


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
		var color: String = String(p.get("color", "red"))
		for u in p.get("units", []):
			if not u is Dictionary:
				continue
			initial_units.append({
				"x": int(u.get("x", 0)),
				"y": int(u.get("y", 0)),
				"type": String(u.get("unit_type", "swordsman")),
				"color": color,
				"level": int(u.get("level", 1)),
			})
	return {
		"__id": _game_id,
		"width": w,
		"height": h,
		"biome": GameState.game_summary.get("map_biome", "grass"),
		"layout": rows,
		"initial_units": initial_units,
	}


func _refresh_hud_from_state() -> void:
	var summary: Dictionary = GameState.game_summary
	turn_badge_label.text = "回合 %d" % int(summary.get("turn_number", 1))
	var phase_text: String = String(summary.get("phase", "player"))
	match phase_text:
		"player": phase_badge_label.text = "🟢 你的阶段"
		"ai": phase_badge_label.text = "🤖 AI 阶段"
		"animating": phase_badge_label.text = "✨ 动画中"
		"spectator": phase_badge_label.text = "👀 观战"
		_: phase_badge_label.text = "阶段:%s" % phase_text

	# Current player name
	var cur_pid = GameState.current_player_id
	if cur_pid != null:
		var cp: Dictionary = GameState.get_player(cur_pid)
		var name: String = String(cp.get("user_name", "—"))
		current_player_label.text = "→ %s" % name
	else:
		current_player_label.text = "→ —"

	# End-turn button only enabled when it's the local player's turn
	# AND the phase is "player".
	end_turn_button.disabled = not (phase_text == "player" and int(cur_pid) == _player_id)

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
	co_meter.value = float(meter) / float(threshold) * 100.0
	co_meter.tooltip_text = "CO 能量: %d / %d" % [meter, threshold]

	# Players list (right column)
	_rewrite_players_list()
	# V2 第 3 轮补丁:左上 InfoPanel 当前指挥官
	_refresh_commander_section()


func _rewrite_players_list() -> void:
	players_list.clear()
	for p in GameState.players:
		if not p is Dictionary:
			continue
		var name: String = String(p.get("user_name", "?"))
		var color: String = String(p.get("color", "?"))
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
	var desc: String = String(action.get("description", ""))
	if desc == "":
		desc = String(action.get("event_type", ""))
	if desc == "":
		return
	var importance: String = String(action.get("importance", "normal"))
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
	var name: String = String(cp.get("user_name", "—"))
	var color: String = String(cp.get("color", "?"))
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
		if c is Dictionary and int(c.get("player_id", -1)) == int(cur_pid):
			meter = int(c.get("meter", 0))
			threshold = max(1, int(c.get("threshold", 100)))
			break
	var pct: float = float(meter) / float(threshold) * 100.0
	if commander_co_bar != null and is_instance_valid(commander_co_bar):
		commander_co_bar.value = pct
		commander_co_bar.tooltip_text = "CO 能量: %d / %d" % [meter, threshold]


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
			owners[k] = int(t.get("owner_id", 0))
	var terrain: Dictionary = {}
	if board.tile_lookup != null:
		for k in board.tile_lookup.keys():
			var t: Dictionary = board.tile_lookup[k]
			terrain[k] = String(t.get("terrain", "plain"))
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


# 简化:沿用现有 5-button action_bubble(移动/攻击/技能/待命/占领)
# 由 can_move_after_action 决定可见动作。
func _show_post_action_bubble(unit_id: int, action_name: String) -> void:
	if action_bubble == null or not is_instance_valid(action_bubble):
		return
	if unit_id != _player_id:
		# 不在本玩家身上 → 不弹
		return
	_selected_unit_id = unit_id
	var ud: Dictionary = GameState.get_unit(unit_id) if GameState != null else {}
	if ud.is_empty():
		return
	var cell := Vector2i(int(ud.get("x", 0)), int(ud.get("y", 0)))
	var marker_pos: Vector2 = board.tile_to_viewport(cell) if board != null else Vector2.ZERO
	_show_action_bubble(unit_id, marker_pos)
	_update_status("已 %s — 可继续操作(攻击/技能/占领/待命)" % action_name)


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
	_show_post_action_bubble(unit_id, "move")


func _on_unit_attacked(attacker_id: int, target_id: int, damage: int, is_crit: bool, is_kill: bool) -> void:
	action_log.append_text("[color=#f0c75e]⚔ #%d → #%d: %d dmg%s%s[/color]\n" % [
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
	# M4.14:post-attack bubble — 若目标未死 + can_move_after_action 还能再行动
	if not is_kill:
		_show_post_action_bubble(attacker_id, "attack")


func _on_unit_killed(unit_id: int, _killer_id: int) -> void:
	action_log.append_text("[color=#e85a6a]💀 #%d 被击杀[/color]\n" % unit_id)
	if board != null:
		var u: Dictionary = GameState.get_unit(unit_id) if GameState != null else {}
		if not u.is_empty():
			var cell := Vector2i(int(u.get("x", 0)), int(u.get("y", 0)))
			board.spawn_floating_text_at_cell(cell, "💀击杀", "#c63a3a", "kill")


# M5.1 CO Roster — 顶部全玩家头像 + 名字 + CO 能量条 + Power 按钮
func _refresh_co_roster() -> void:
	if co_roster == null or not is_instance_valid(co_roster):
		return
	for child in co_roster.get_children():
		child.queue_free()
	if GameState == null:
		return
	var players: Array = (GameState.players as Array)
	var co_states: Array = (GameState.co_states as Array)
	for p in players:
		if not p is Dictionary: continue
		var pid: int = int(p.get("id", -1))
		var name: String = String(p.get("user_name", "—"))
		var color_name: String = String(p.get("color", "red"))
		var color_hex: String = _color_name_to_godot(color_name)
		var emoji: String = _color_emoji(color_name)
		var is_ai: bool = bool(p.get("is_ai", false))
		var is_local: bool = (pid == _player_id)
		var meter: int = 0
		var threshold: int = 100
		for c in co_states:
			if not c is Dictionary: continue
			if int(c.get("player_id", -1)) == pid:
				meter = int(c.get("meter", 0))
				threshold = max(1, int(c.get("threshold", 100)))
				break
		var pct: float = clamp(float(meter) / float(threshold) * 100.0, 0.0, 100.0)
		# 简易容器:Panel(无边框背景) + 内含 3 行
		var vb := VBoxContainer.new()
		vb.custom_minimum_size = Vector2(130, 50)
		vb.add_theme_constant_override("separation", 2)
		var title := Label.new()
		title.text = "%s %s%s%s" % [
			emoji, name,
			" 🤖" if is_ai else "",
			" (你)" if is_local else ""
		]
		title.add_theme_color_override("font_color", Color(color_hex))
		title.add_theme_font_size_override("font_size", 11)
		vb.add_child(title)
		var bar := ProgressBar.new()
		bar.value = pct
		bar.custom_minimum_size = Vector2(120, 10)
		bar.tooltip_text = "CO %d / %d" % [meter, threshold]
		vb.add_child(bar)
		var btn := Button.new()
		btn.text = "⚡ Power (%d)" % meter
		btn.disabled = meter < threshold or not is_local
		btn.add_theme_font_size_override("font_size", 10)
		if is_local and meter >= threshold:
			btn.pressed.connect(_on_co_power_pressed.bind(pid))
		vb.add_child(btn)
		co_roster.add_child(vb)


# M5.3 CO Power 激活
func _on_co_power_pressed(pid: int) -> void:
	if _game_id <= 0:
		return
	NetworkClient.action_co_power(_game_id, pid)
	_update_status("⚡ CO Power 激活中 (#%d)..." % pid)


# M6.3 静音 toggle — Settings 上 toggle 按钮
func _on_toggle_mute_pressed() -> void:
	if AudioManager == null: return
	var muted: bool = AudioManager.toggle_muted()
	UserSettings.set_value("settings.v1.muted", muted)
	_update_status("静音: %s" % ("开" if muted else "关"))


# M6.5 主题切换 — 三套主题:deep_gba / metal_silver / minimal_light
# 通过 set_root_theme 设置全局 default_* 颜色与字号。
const _THEMES := ["deep_gba", "metal_silver", "minimal_light"]


func _on_theme_change(theme_name: String) -> void:
	UserSettings.set_value("settings.v1.theme", theme_name)
	_apply_theme(theme_name)


func _apply_theme(theme_name: String) -> void:
	# 主题实际生效 — V2 简化版:仅换背景色 + 部分面板色调。
	# 完整主题需 .tres 文件(M5.5 TODO)
	var bg_color: Color = Color(0.06, 0.13, 0.10)  # GBA default
	if theme_name == "metal_silver":
		bg_color = Color(0.10, 0.10, 0.13)
	elif theme_name == "minimal_light":
		bg_color = Color(0.92, 0.92, 0.88)
	if backdrop != null and is_instance_valid(backdrop):
		backdrop.color = bg_color
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
			+ "3. 单位可移动后还能再行动(post-attack/post-move)\n\n"
			+ "[color=#f4e8c1][b]伤害公式(简化)[/b][/color]\n"
			+ "  ATK × (ATK/(ATK + DEF)) × 类型倍率 × 暴击系数\n\n"
			+ "[color=#f4e8c1][b]CO 系统[/b][/color]\n"
			+ "  每回合能量累计到 100 可发动 Power(瞬间加 buff)\n\n"
			+ "[color=#f4e8c1][b]胜利条件[/b][/color]\n"
			+ "  消灭所有敌方单位,或占领对方 HQ(通用规则)"
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


func _on_turn_ended(next_player_id, turn_number: int) -> void:
	# M4.17:turn banner slide-down + 玩家色 + emoji
	var pid_str := str(next_player_id)
	var cp: Dictionary = GameState.get_player(int(next_player_id)) if next_player_id != null else {}
	var name: String = String(cp.get("user_name", "—"))
	var color_name: String = String(cp.get("color", "red"))
	var color_hex: String = _color_name_to_godot(color_name)
	var emoji: String = _color_emoji(color_name)
	var is_local: bool = (int(next_player_id) == _player_id) if next_player_id != null else false
	var suffix: String = "  →  你的回合" if is_local else ""
	_show_turn_banner("回合 %d  ·  %s [color=%s]%s[/color]%s" % [
		turn_number, emoji, color_hex, name, suffix
	], 3.0)


func _on_match_ended(winner_player_id, win_reason: String) -> void:
	_show_turn_banner("🏆 [color=#f0c75e]玩家 #%s[/color] 获胜! 原因: %s" % [
		str(winner_player_id), win_reason
	], 8.0)
	# S:4:弹 BattleResultPanel — 展示 winner + 战斗统计
	var winner_id: int = int(winner_player_id) if winner_player_id != null else -1
	var winner_p: Dictionary = GameState.get_player(winner_id) if winner_id > 0 else {}
	var winner_name: String = String(winner_p.get("user_name", "—"))
	var winner_color: String = String(winner_p.get("color", "red"))
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
			var action_type: String = String(log.get("action_type", ""))
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
			var desc: String = String(log.get("description", ""))
			detail_lines.append("[color=#a89878]回合 %d[/color]  [color=#c9a14a]%s[/color]  %s" % [
				turn_n, action_type, desc
			])
		# 保留最近 N 条
		var MAX_DETAIL := 12
		if detail_lines.size() > MAX_DETAIL:
			detail_lines = detail_lines.slice(detail_lines.size() - MAX_DETAIL)
	stats["detail_lines"] = detail_lines
	show_battle_result(winner_name, winner_color, stats)


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
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		if game_view == null or not game_view.visible:
			return
		if board == null:
			return
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
			elif _heal_mode_unit_id > 0:
				# 治疗模式:空地点击 → 取消
				_cancel_action_mode()
			else:
				# 走 web 的"空佣兵站(我方 owner)+ 没单位驻守"→ 招募入口
				# (game/app/web/app.js:3015-3024)。
				var batt: Dictionary = _pick_empty_my_barracks(event.global_position)
				if not batt.is_empty():
					_show_recruit_at(batt)
				else:
					board.clear_selection_marks()
					_hide_action_bubble()
		get_viewport().set_input_as_handled()


# 把屏幕坐标转 tile,看是不是"我方 owner + 空 barracks + 是我的回合"。
# 是 → {x, y, gold};否 → {}。
func _pick_empty_my_barracks(global_pos: Vector2) -> Dictionary:
	if board == null or GameState == null:
		return {}
	if not GameState.is_local_turn:
		return {}
	var layer: TileMapLayer = board.get_node_or_null("GroundLayer")
	if layer == null:
		return {}
	var local: Vector2 = layer.to_local(global_pos)
	var cell: Vector2i = layer.local_to_map(local)
	var terrain: Dictionary = board.tile_lookup if board.tile_lookup != null else {}
	for k in terrain.keys():
		var t: Dictionary = terrain[k]
		if Vector2i(int(t.get("x", k.x)), int(t.get("y", k.y))) != cell:
			continue
		if String(t.get("terrain", "")) != "barracks":
			return {}
		if int(t.get("owner_id", -1)) != _player_id:
			return {}
		# 该 tile 上是否有单位(occupied → 不能招募)
		for uu in _all_units_including_self():
			if int(uu.get("x", -1)) == cell.x and int(uu.get("y", -1)) == cell.y:
				return {}
		var me: Dictionary = GameState.get_player(_player_id)
		return {
			"x": cell.x,
			"y": cell.y,
			"gold": int(me.get("gold", 0)),
		}
	return {}


# S:4 — T:4 RecruitPanel 真 modal(替换 status 凑合)。
# 仿照 web 的 showRecruitModal(3276-3325):5 类单位列表 + 金币门槛 disable
# + 类型 buttons — server 是 source of truth。
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
		var unit_type: String = String(opt.get("type", "?"))
		var name: String = String(opt.get("name", "?"))
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
			_attack_unit_to(_attack_mode_unit_id, unit_id)
		else:
			# 点错目标(不是敌方有效目标)→ 取消
			_update_status("目标无效,取消攻击")
			_attack_mode_unit_id = -1
			_attack_targets = {}
			if board != null:
				board.clear_selection_marks()
		return
	# 治疗模式下点单位 → 用作 heal target
	if _heal_mode_unit_id > 0:
		if _heal_targets.has(unit_id):
			_heal_unit_to(_heal_mode_unit_id, unit_id)
		else:
			_update_status("目标无效,取消治疗")
			_heal_mode_unit_id = -1
			_heal_targets = {}
			if board != null:
				board.clear_selection_marks()
		return
	# 否则:正常选中流程
	_handle_unit_click(unit_id, Vector2.ZERO)


# M4.1:点击地图格子(空白区 / 落点)→ 处理
func _on_board_tile_clicked(tile: Vector2i) -> void:
	# 不在移动模式 → 忽略
	if _move_mode_unit_id <= 0:
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
	if not is_my_unit or not can_still_act:
		# 不进入移动/攻击模式
		_move_mode_unit_id = -1
		_move_reachable_set = {}
		_attack_mode_unit_id = -1
		_attack_targets = {}
		_heal_mode_unit_id = -1
		_heal_targets = {}
		if board != null:
			board.clear_selection_marks()
		_hide_action_bubble()
		return
	# 否则:可行动己方 unit → 弹气泡 + reachable 高亮
	_selected_unit_id = unit_id
	var cell := Vector2i(int(ud.get("x", 0)), int(ud.get("y", 0)))
	var marker_pos: Vector2 = board.tile_to_viewport(cell) if board != null else Vector2.ZERO
	_show_action_bubble(unit_id, marker_pos)
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
			owners[k] = int(t.get("owner_id", 0))
	var terrain: Dictionary = {}
	if board != null and board.tile_lookup != null:
		for k in board.tile_lookup.keys():
			var t: Dictionary = board.tile_lookup[k]
			terrain[k] = String(t.get("terrain", "plain"))
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
			terrain[k] = String(t.get("terrain", "plain"))
			owners[k] = int(t.get("owner_id", 0))
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


# T:8 阵营颜色生效 — 仅记 pref,新房间用
func _apply_preferred_color(color_name: String) -> void:
	UserSettings.set_value("settings.v1.color", color_name)
	_update_status("下一局将使用 %s 方 (当前房间不变)" % color_name)


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
	_heal_mode_unit_id = -1
	_heal_targets = {}
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


func _on_pause_quit_pressed() -> void:
	get_tree().quit()


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


func _advance_dialog() -> void:
	if _dialog_queue.is_empty():
		_dialog_active = false
		hide_dialog()
		return
	_dialog_active = true
	var entry: Dictionary = _dialog_queue.pop_front()
	dialog_name.text = String(entry.get("character", ""))
	dialog_text.bbcode_enabled = true
	# 隐藏选项层
	if _dialog_choice_container != null and is_instance_valid(_dialog_choice_container):
		_dialog_choice_container.visible = false
	# typewriter:full text 缓存,visible 渐进加
	var full_text: String = String(entry.get("text", ""))
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
		+ "[color=#a89878]胜利原因: %s[/color]" % String(stats.get("reason", "—")) \
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


# ============================================================
# GBA 火纹风主题注入(UI V2 第 1 轮)
# ============================================================

func _apply_gba_theme() -> void:
	# 1) 全屏深绿背景(ColorRect 颜色已在 .tscn 设)
	backdrop.color = MenuTheme.C_BG_DEEP
	# 2) 边框由 ReferenceRect 画,这里只调整颜色变量(已硬编码在 .tscn)
	# 3) Connecting 框(深绿底)
	connecting_frame.color = MenuTheme.C_BG_PANEL
	# 4) 主菜单 + 游戏内按钮统一灌主题
	for btn in [menu_button, lobby_button, settings_button, exit_button,
				reconnect_button, end_turn_button, war_report_button]:
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
	# CO meter styling (unchanged from before)
	if co_meter != null and is_instance_valid(co_meter):
		var sb_bg := StyleBoxFlat.new()
		sb_bg.bg_color = Color(0.18, 0.12, 0.06, 1)
		sb_bg.border_color = MenuTheme.C_GOLD
		sb_bg.set_border_width_all(1)
		sb_bg.content_margin_left = 2
		sb_bg.content_margin_right = 2
		sb_bg.content_margin_top = 2
		sb_bg.content_margin_bottom = 2
		var sb_fg := StyleBoxFlat.new()
		sb_fg.bg_color = MenuTheme.C_GOLD
		sb_fg.border_color = MenuTheme.C_GOLD_BRIGHT
		sb_fg.set_border_width_all(1)
		co_meter.add_theme_stylebox_override("background", sb_bg)
		co_meter.add_theme_stylebox_override("fill", sb_fg)
	# CO meter:用烫金 progress 色
	if co_meter != null and is_instance_valid(co_meter):
		var sb_bg := StyleBoxFlat.new()
		sb_bg.bg_color = Color(0.18, 0.12, 0.06, 1)   # 深棕,确保 fill 0% 时也有底色
		sb_bg.border_color = MenuTheme.C_GOLD
		sb_bg.set_border_width_all(1)
		sb_bg.content_margin_left = 2
		sb_bg.content_margin_right = 2
		sb_bg.content_margin_top = 2
		sb_bg.content_margin_bottom = 2
		var sb_fg := StyleBoxFlat.new()
		sb_fg.bg_color = MenuTheme.C_GOLD
		sb_fg.border_color = MenuTheme.C_GOLD_BRIGHT
		sb_fg.set_border_width_all(1)
		co_meter.add_theme_stylebox_override("background", sb_bg)
		co_meter.add_theme_stylebox_override("fill", sb_fg)
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
		sb_bubble.bg_color = MenuTheme.C_BG_PANEL
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
	for btn in [dialog_continue_btn, tutorial_got_it_btn, battle_detail_btn, battle_back_menu_btn]:
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


# ============================================================
# 主菜单新增按钮 handler
# ============================================================

func _on_lobby_pressed() -> void:
	_entry_flow = "lobby"
	_show_view("lobby")
	_apply_lobby_theme()
	_stop_lobby_polling()
	_selected_room_id = 0
	if lobby_status_label != null and is_instance_valid(lobby_status_label):
		lobby_status_label.text = "Choose a room or create a new one."
	if lobby_game_id_label != null and is_instance_valid(lobby_game_id_label):
		lobby_game_id_label.text = "No room joined"
	if lobby_list != null and is_instance_valid(lobby_list):
		lobby_list.text = "(Join or create a room to see players.)"
	if create_name_input != null and is_instance_valid(create_name_input):
		create_name_input.text = "%s room" % _user_name
	_load_lobby_presets()
	_refresh_room_list()
	return
	# T:3 进入基础大厅视图
	_show_view("lobby")
	_apply_lobby_theme()
	# 还没 game_id — 帮玩家创建一个并自动 join
	NetworkClient.create_game(
		"联机对局",
		"balanced_2p_15",
		"grass",
		"rout",
		Callable(self, "_on_lobby_create_response")
	)
	lobby_status_label.text = "创建房间中..."
	lobby_game_id_label.text = "对局 #? · 创建中..."


func _on_lobby_create_response(body: Dictionary, _code: int = 0) -> void:
	_game_id = int(body.get("id", 0))
	if _game_id <= 0:
		lobby_status_label.text = "创建失败"
		return
	UserSettings.set_value("session.v1.last_game_id", _game_id)
	lobby_game_id_label.text = "对局 #%d · 等待中" % _game_id
	# 自动 join
	NetworkClient.join_game(_game_id, _user_name, "red",
		Callable(self, "_on_lobby_join_response"))


func _on_lobby_join_response(_body: Dictionary, _code: int = 0) -> void:
	# 拉 lobby 启动轮询
	_start_lobby_polling()


func _load_lobby_presets() -> void:
	if map_preset_option == null or not is_instance_valid(map_preset_option):
		return
	map_preset_option.clear()
	map_preset_option.add_item("balanced_2p_15")
	_preset_options = [{"id": "balanced_2p_15", "biome": "grass"}]
	NetworkClient.list_presets(Callable(self, "_on_lobby_presets_response"))


func _on_lobby_presets_response(body: Variant, _code: int = 0) -> void:
	if map_preset_option == null or not is_instance_valid(map_preset_option):
		return
	var maps: Array = []
	if body is Dictionary:
		maps = (body as Dictionary).get("maps", [])
	if maps.is_empty():
		return
	map_preset_option.clear()
	_preset_options = []
	for item in maps:
		if not item is Dictionary:
			continue
		var id: String = String(item.get("id", ""))
		if id == "":
			continue
		var name: String = String(item.get("name", id))
		var biome: String = String(item.get("biome", "grass"))
		var players: int = int(item.get("recommended_players", 0))
		var label := name
		if players > 0:
			label = "%s (%dp)" % [name, players]
		map_preset_option.add_item(label)
		_preset_options.append({"id": id, "biome": biome})


func _refresh_room_list() -> void:
	if room_list != null and is_instance_valid(room_list):
		room_list.text = "Loading rooms..."
	if room_select_option != null and is_instance_valid(room_select_option):
		room_select_option.clear()
		room_select_option.add_item("Loading rooms...")
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
		if String(g.get("status", "")) != "waiting":
			continue
		_lobby_rooms.append(g)
	if _lobby_rooms.is_empty():
		if room_list != null and is_instance_valid(room_list):
			room_list.text = "(No waiting rooms. Create one on the right.)"
		if room_select_option != null and is_instance_valid(room_select_option):
			room_select_option.clear()
			room_select_option.add_item("No waiting rooms")
			room_select_option.disabled = true
		if join_selected_btn != null and is_instance_valid(join_selected_btn):
			join_selected_btn.disabled = true
		return
	var lines: Array = []
	if room_select_option != null and is_instance_valid(room_select_option):
		room_select_option.clear()
		room_select_option.disabled = false
	for i in range(_lobby_rooms.size()):
		var g: Dictionary = _lobby_rooms[i]
		var id: int = int(g.get("id", 0))
		if i == 0:
			_selected_room_id = id
		var marker := ">" if i == 0 else " "
		var name := String(g.get("name", "Room"))
		var preset := String(g.get("map_preset", "?"))
		var cap := int(g.get("capacity", 0))
		lines.append("%s #%d  %s  [%s]  cap:%d" % [marker, id, name, preset, cap])
		if room_select_option != null and is_instance_valid(room_select_option):
			room_select_option.add_item("#%d  %s" % [id, name])
	if room_list != null and is_instance_valid(room_list):
		room_list.text = "\n".join(lines)
	if join_selected_btn != null and is_instance_valid(join_selected_btn):
		join_selected_btn.disabled = _selected_room_id <= 0


func _on_room_selected(index: int) -> void:
	if index < 0 or index >= _lobby_rooms.size():
		_selected_room_id = 0
	else:
		var g: Dictionary = _lobby_rooms[index]
		_selected_room_id = int(g.get("id", 0))
	if join_selected_btn != null and is_instance_valid(join_selected_btn):
		join_selected_btn.disabled = _selected_room_id <= 0


func _on_create_room_pressed() -> void:
	_entry_flow = "lobby_create"
	var room_name := "%s room" % _user_name
	if create_name_input != null and is_instance_valid(create_name_input):
		var typed := create_name_input.text.strip_edges()
		if typed != "":
			room_name = typed
	var preset_id := "balanced_2p_15"
	var biome := "grass"
	var idx := 0
	if map_preset_option != null and is_instance_valid(map_preset_option):
		idx = map_preset_option.selected
	if idx >= 0 and idx < _preset_options.size():
		var selected: Dictionary = _preset_options[idx]
		preset_id = String(selected.get("id", preset_id))
		biome = String(selected.get("biome", biome))
	if lobby_status_label != null and is_instance_valid(lobby_status_label):
		lobby_status_label.text = "Creating room..."
	NetworkClient.create_game(room_name, preset_id, biome, "rout")


func _on_join_selected_pressed() -> void:
	if _selected_room_id <= 0:
		return
	_entry_flow = "lobby_join"
	_game_id = _selected_room_id
	if lobby_status_label != null and is_instance_valid(lobby_status_label):
		lobby_status_label.text = "Joining room #%d..." % _game_id
	NetworkClient.join_game(_game_id, _user_name, "red")


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
	NetworkClient.get_lobby(_game_id, Callable(self, "_on_lobby_state"))


func _on_lobby_state(body: Dictionary, _code: int = 0) -> void:
	if not (body is Dictionary): return
	var players: Array = (body.get("players", []) as Array)
	var is_waiting: bool = String(body.get("status", "waiting")) == "waiting"
	# 渲染列表 + 人头
	var lines: Array = []
	for p in players:
		if not p is Dictionary: continue
		var name: String = String(p.get("user_name", "—"))
		var color: String = String(p.get("color", "red"))
		var is_ai: bool = bool(p.get("is_ai", false))
		var is_self: bool = int(p.get("id", -1)) == int(_player_id)
		var emoji: String = _color_emoji(color)
		var tag: String = ""
		if is_self: tag = " (你)"
		elif is_ai: tag = " 🤖"
		lines.append("%s %s%s" % [emoji, name, tag])
	if lines.is_empty():
		var teams: Array = body.get("teams", [])
		for t in teams:
			if not t is Dictionary:
				continue
			var team_name := String(t.get("team", "?"))
			var count := int(t.get("player_count", 0))
			var cap := int(t.get("capacity", 0))
			var color := String(t.get("color", "red"))
			var cap_text := str(cap) if cap > 0 else "-"
			lines.append("%s %s  %d/%s" % [_color_emoji(color), team_name, count, cap_text])
	lobby_list.text = "\n".join(lines) if lines.size() > 0 else "(等待加入)"
	var real_count: int = 0
	for p in players:
		if p is Dictionary and not bool(p.get("is_ai", false)):
			real_count += 1
	if real_count == 0:
		real_count = int(body.get("player_count", 0))
	var shown_count: int = int(body.get("player_count", players.size()))
	lobby_status_label.text = "等待玩家加入... (%d 人 · 真人 %d)" % [
		shown_count, real_count
	]
	# Start 按钮 — 只要 ≥1 玩家即可(简化,实际 ≥2)
	lobby_start_btn.disabled = int(body.get("player_count", players.size())) < 1


func _on_lobby_add_ai_pressed() -> void:
	if _game_id <= 0: return
	# POST /games/{id}/add-ai(走 NetworkClient.request)
	if lobby_status_label != null and is_instance_valid(lobby_status_label):
		lobby_status_label.text = "Adding AI..."
	NetworkClient.add_ai_player(_game_id, "normal", "rules", "balanced", Callable(self, "_on_lobby_add_ai_response"))


func _on_lobby_add_ai_response(_body: Variant, _code: int = 0) -> void:
	_refresh_lobby_view()
	_refresh_room_list()


func _on_lobby_start_pressed() -> void:
	if _game_id <= 0: return
	NetworkClient.start_game(_game_id, Callable(self, "_on_lobby_start_response"))


func _on_lobby_start_response(_body: Dictionary, _code: int = 0) -> void:
	# 启动游戏 — 切到 game 视图,接 WS
	_show_view("game")
	NetworkClient.connect_to_game(_game_id, _player_id)
	_stop_lobby_polling()


func _on_lobby_back_pressed() -> void:
	_stop_lobby_polling()
	_show_view("menu")


func _apply_lobby_theme() -> void:
	if lobby_start_btn != null and is_instance_valid(lobby_start_btn):
		MenuTheme.apply_button_theme(lobby_start_btn, 18)
	if lobby_add_ai_btn != null and is_instance_valid(lobby_add_ai_btn):
		MenuTheme.apply_button_theme(lobby_add_ai_btn, 14)
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


# T:96 — MainlineView 章节列表 + 入口
func _on_mainline_pressed() -> void:
	_show_view("mainline")
	ml_title.text = "📖 主线章节 · 加载中..."
	ml_list_container.text = ""
	NetworkClient.list_mainlines(Callable(self, "_on_ml_list_response"))


func _on_ml_list_response(body: Variant, _code: int = 0) -> void:
	ml_title.text = "📖 主线章节"
	for child in ml_list_container.get_children():
		child.queue_free()
	# /mainlines 返回 Array[MainlineSummaryOut]
	var items: Array = body if body is Array else []
	if items.is_empty():
		var empty := Label.new()
		empty.text = "(暂无可用章节)"
		empty.add_theme_color_override("font_color", Color(0.65, 0.6, 0.45))
		ml_list_container.add_child(empty)
		return
	for ml in items:
		if not ml is Dictionary: continue
		var id: int = int(ml.get("id", 0))
		var title: String = String(ml.get("title", "?"))
		var battles: int = int(ml.get("total_battles", 0))
		var state: String = String(ml.get("state", "locked"))
		var desc: String = String(ml.get("description", ""))
		var btn := Button.new()
		btn.text = "%s (%s) · %d 战" % [title, state, battles]
		btn.tooltip_text = desc
		btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		btn.pressed.connect(_on_ml_card_pressed.bind(id))
		ml_list_container.add_child(btn)


func _on_ml_card_pressed(mainline_id: int) -> void:
	# 拉详情 → show_dialog（pre-battle dialogue）→ start
	NetworkClient.get_mainline_detail(mainline_id, Callable(self, "_on_ml_detail_response").bind(mainline_id))


func _on_ml_detail_response(body: Variant, mainline_id: int, _code: int = 0) -> void:
	if not (body is Dictionary):
		_update_status("加载章节详情失败")
		return
	var battles: Array = body.get("battles", []) if body.has("battles") else []
	var dialogue: Variant = body.get("dialogue", null)
	# 有 pre-battle 对话 → 播放
	if dialogue != null and dialogue is Array and dialogue.size() > 0:
		for d in dialogue:
			if d is Dictionary:
				var char_name: String = String(d.get("character", ""))
				var txt: String = String(d.get("text", ""))
				if txt != "":
					show_dialog(char_name, "[color=#f0c75e]%s[/color]\n%s" % [char_name, txt])
	# 对话框完毕后:战斗
	_update_status("主线章节 #%d: 开始战斗 (TODO)" % mainline_id)


func _on_ml_back_pressed() -> void:
	_show_view("menu")


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

func _show_action_bubble(unit_id: int, viewport_pos: Vector2) -> void:
	_selected_unit_id = unit_id
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
	# 计算可攻击目标(只算范围内 + LoS 通的敌方单位)
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
	if _move_mode_unit_id > 0 or _attack_mode_unit_id > 0 or _heal_mode_unit_id > 0:
		_move_mode_unit_id = -1
		_move_reachable_set = {}
		_attack_mode_unit_id = -1
		_attack_targets = {}
		_heal_mode_unit_id = -1
		_heal_targets = {}
		if board != null:
			board.clear_selection_marks()
		_update_status("已取消行动模式")


# 计算攻击范围内所有可攻击的目标(敌方单位所在格 — 需在范围内 + LoS 通)
#
# 重要原则:client 端**不重复**伤害计算 — server (calculate_damage)
# 是唯一公式来源。这里只算"哪几个敌方单位在范围内且被本单位的
# attack_range + LoS 覆盖",对应 game/app/web/app.js:2183 canUnitAttack。
# 真正的伤害值在 server 推 unit_attacked 事件时由服务端返回的
# (damage, is_crit, is_kill) 决定。
func _compute_attack_targets(attacker: Dictionary) -> Dictionary:
	# 范围
	var range_tiles: Array = _get_attack_range_tiles(attacker)
	if range_tiles.is_empty():
		return {}
	var size_v: int = 15
	if board != null and board.map_size.x > 0:
		size_v = board.map_size.x
	# blocked 字典(只看地形 passable,不拦人 — 自己可站)
	var blocked: Dictionary = {}
	for other in GameState.players:
		if not other is Dictionary: continue
		for u in other.get("units", []):
			if u is Dictionary:
				var k := Vector2i(int(u.get("x", 0)), int(u.get("y", 0)))
				blocked[k] = true
	var me_pid: int = int(_player_id)
	var out: Dictionary = {}
	for rt in range_tiles:
		var rt_v := Vector2i(int(rt.x), int(rt.y))
		# 看这个格是否有敌方单位
		for u in GameState.players:
			if not u is Dictionary: continue
			if int(u.get("id", -1)) == me_pid:
				continue
			for uu in u.get("units", []):
				if not uu is Dictionary: continue
				if int(uu.get("x", -1)) != rt_v.x or int(uu.get("y", -1)) != rt_v.y:
					continue
				# LoS 校验(远距离攻击需要通视)
				var attacker_pos := Vector2i(int(attacker.get("x", 0)), int(attacker.get("y", 0)))
				var d: int = abs(attacker_pos.x - rt_v.x) + abs(attacker_pos.y - rt_v.y)
				if d > 1:
					var los_ok: bool = MapLogic.has_line_of_sight(
						attacker_pos, rt_v, blocked, size_v
					)
					if not los_ok:
						continue
				out[int(uu.get("id", -1))] = {
					"x": rt_v.x,
					"y": rt_v.y,
					"defender_name": String(uu.get("name", uu.get("unit_type", "?"))),
					# 不预测,只显示攻击者/目标基本信息。真实伤害由
					# server 决定。
				}
	return out


# (删)旧 _forecast_attack_simple 已移除 — 客户端不抄伤害公式,
# server calculate_damage 单一来源。真要展示预测数字时,
# 走 GET /games/{id}/forecast-attack 端点(M4+ TODO)


# 拿 attack_range(含 snipe 技能 +1),然后用 MapLogic.attack_range_tiles 求出范围
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


# M4.2:发 POST /games/{id}/attack
func _attack_unit_to(attacker_id: int, target_id: int) -> void:
	if _game_id <= 0 or _player_id <= 0:
		return
	var info: Dictionary = _attack_targets.get(target_id, {})
	var tgt_name: String = String(info.get("defender_name", "单位 #%d" % target_id))
	_update_status("正在攻击 %s (单位 #%d → #%d)..." % [tgt_name, attacker_id, target_id])
	NetworkClient.action_attack(_game_id, _player_id, attacker_id, target_id)
	# 客户端不预测伤害 - server 推 unit_attacked 事件后,从 signal args
	# 拿到 (damage, is_crit, is_kill) 直接显示。
	_attack_mode_unit_id = -1
	_attack_targets = {}
	if board != null:
		board.clear_selection_marks()
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
	var skills: Array = (ud.get("skills", []) as Array)
	if not skills.has("heal"):
		_update_status("技能: 该单位不会治疗")
		return
	# 计算 8-邻接范围内 HP<max_hp 的友军
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
			"name": String(uu.get("name", uu.get("unit_type", "?"))),
			"hp": hp_i,
			"max_hp": max_hp_i,
		}
	if out.is_empty():
		_update_status("治疗: 8-邻内无伤兵")
		return
	_heal_mode_unit_id = _selected_unit_id
	_heal_targets = out
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
	_update_status("正在招募 %s 到 (%d, %d)..." % [unit_type, tile_x, tile_y])
	NetworkClient.action_recruit(_game_id, _player_id, tile_x, tile_y, unit_type)
	_hide_action_bubble()


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
	var name: String = String(ud.get("name", ud.get("unit_type", "?")))
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
	var color_name: String = String(ud.get("color", "red"))
	var cur_pid_v: Variant = GameState.current_player_id if GameState != null else null
	var cur_pid: int = -1 if cur_pid_v == null else int(cur_pid_v)
	var is_mine: bool = (owner_pid == _player_id and owner_pid == cur_pid)
	var can_act: bool = not bool(ud.get("has_acted", false)) and not bool(ud.get("has_moved", false)) and is_mine
	var owner_str: String = ("敌方 %s" % _color_emoji(color_name)) if not is_mine else ("[color=#f0c75e]%s[/color] (你)" % _color_emoji(color_name))
	if unit_info_title != null and is_instance_valid(unit_info_title):
		unit_info_title.text = "⚔ %s · Lv.%d" % [name, lvl]
	var lines: Array = [
		"[color=#a89878]⛓ 位置[/color]  (%d, %d)   %s" % [pos.x, pos.y, owner_str],
		("[color=#f4e8c1]❤ HP[/color]  %d / %d   [color=#5fa8e8]⚡ MP[/color]  %d/%d" % [hp, max_hp, mp, max_mp]) if max_mp > 0 else ("[color=#f4e8c1]❤ HP[/color]  %d / %d" % [hp, max_hp]),
		"[color=#c9a14a]⚔ ATK[/color] %d  [color=#c9a14a]🛡 DEF[/color] %d  [color=#c9a14a]✨ MATK[/color] %d  [color=#c9a14a]🔮 MDEF[/color] %d" % [atk, def, matk, mdef],
		"[color=#a89878]👣 MOV[/color] %d   [color=#a89878]🎯 攻击射程[/color] %d-%d" % [mov, range_min + 1, range_max],
		"[color=#a89878]⭐ 士气[/color] %d / 3   [color=#a89878]📜 技能[/color] %s" % [morale, ", ".join(skills) if skills.size() > 0 else "—"],
	]
	if not is_mine:
		lines.append("[color=#c63a3a]⚠ 敌方单位·无法操作[/color]")
	elif not can_act:
		lines.append("[color=#a89878]💤 已结束本回合行动[/color]")
	unit_info.text = "\n".join(lines)


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


func _heal_unit_to(healer_id: int, target_id: int) -> void:
	if _game_id <= 0 or _player_id <= 0: return
	var info: Dictionary = _heal_targets.get(target_id, {})
	var name: String = String(info.get("name", "单位 #%d" % target_id))
	_update_status("治疗 #%d → #%d (%s)..." % [healer_id, target_id, name])
	NetworkClient.action_skill(_game_id, _player_id, healer_id, "heal", target_id)
	_heal_mode_unit_id = -1
	_heal_targets = {}
	if board != null: board.clear_selection_marks()
	_hide_action_bubble()


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
