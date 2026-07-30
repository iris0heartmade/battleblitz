extends Control
## lobby_controller.gd — 联机大厅视图控制器(P2 从 main.gd 抽离)。
##
## 挂在场景 Lobby 节点上,自管面板内部逻辑与全部子控件信号;
## view 可见性仍由 main._show_view 控制(与 saves / mainline / editor 一致)。
## 覆盖:选择卡片(建房/加入)→ 建房表单 → 房列表 → 房内席位 → 房主控制 → 开局。
##
## 对外接口:
##   open()                     — main._on_lobby_pressed 调用:入口 + 挂起存档检查
##   show_choose()              — main._show_view 切到 lobby 时复位到选择页
##   enter_room_after_join()    — main._on_join_game_response 加入成功后切入房内
##   selected_join_role()       — main 发 join_game 请求时取当前角色选择
##   selected_join_team()       — 同上,取队伍选择
##   _setup_lobby_commander_options(unlocked) — mainline_controller 经 main 转发
##   var _main: Node            — main 注入;跨域访问 _user_name / _game_id /
##                                _player_id / _entry_flow / _show_view /
##                                _update_status / _show_confirm / mainline_view
##
## 节点路径相对 Lobby: $LobbyFrame/<X>(原 main.gd 用 $Lobby/LobbyFrame/<X>)
##
## ⚠ 时序:Godot 先跑子节点 _ready 再跑父节点 _ready,所以本文件 _ready() 执行时
##   _main 仍是 null。_ready() 里只做 connect 与主题上色,任何 _main 访问都必须
##   推迟到 open() 或信号回调里(与 mainline_controller 同约定)。

const MenuTheme = preload("res://scripts/ui/menu_theme.gd")
const MapPreviewSummary = preload("res://scripts/ui/map_preview_summary.gd")
const CnLabels = preload("res://scripts/ui/cn_labels.gd")

var _main: Node = null

@onready var lobby_status_label: Label = $LobbyFrame/LobbyInfoBar/LobbyStatus
@onready var lobby_list: RichTextLabel = $LobbyFrame/LobbyList
@onready var lobby_win_banner: Label = $LobbyFrame/LobbyInfoBar/LobbyWinBanner
@onready var ai_difficulty_option: OptionButton = $LobbyFrame/AiConfigRow/AiDifficultyOption
@onready var ai_kind_option: OptionButton = $LobbyFrame/AiConfigRow/AiKindOption
@onready var ai_personality_option: OptionButton = $LobbyFrame/AiConfigRow/AiPersonalityOption
@onready var ai_commander_option: OptionButton = $LobbyFrame/AiCommanderOption
@onready var ai_player_option: OptionButton = $LobbyFrame/AiActionRow/AiPlayerOption
@onready var lobby_add_ai_btn: Button = $LobbyFrame/AiActionRow/LobbyAddAiBtn
@onready var lobby_remove_ai_btn: Button = $LobbyFrame/AiActionRow/LobbyRemoveAiBtn
@onready var lobby_start_btn: Button = $LobbyFrame/BottomBar/LobbyStartBtn
@onready var player_count_label: Label = $LobbyFrame/LobbyDualCol/RightCol/PlayerCountLabel
@onready var start_game_inline_btn: Button = $LobbyFrame/LobbyDualCol/RightCol/StartGameInlineBtn
@onready var lobby_back_btn: Button = $LobbyFrame/BottomBar/LobbyBackBtn
@onready var lobby_game_id_label: Label = $LobbyFrame/LobbyTopBar/LobbyGameIdLabel
@onready var room_list: RichTextLabel = $LobbyFrame/LobbyDualCol/LeftCol/RoomList
@onready var room_select_option: OptionButton = $LobbyFrame/LobbyDualCol/LeftCol/RoomSelectOption
@onready var join_mode_option: OptionButton = $LobbyFrame/LobbyDualCol/LeftCol/JoinModeOption
@onready var refresh_rooms_btn: Button = $LobbyFrame/LobbyDualCol/LeftCol/LeftBtnRow/RefreshRoomsBtn
@onready var join_selected_btn: Button = $LobbyFrame/LobbyDualCol/LeftCol/LeftBtnRow/JoinSelectedBtn
@onready var lobby_name_input: LineEdit = $LobbyFrame/LobbyDualCol/RightCol/CreateNameInput
@onready var lobby_seat_panel: Panel = $LobbyFrame/LobbyDualCol/RightCol/SeatPanel
@onready var lobby_seat_grid: GridContainer = $LobbyFrame/LobbyDualCol/RightCol/SeatPanel/SeatGrid
@onready var map_player_count_option: OptionButton = $LobbyFrame/LobbyDualCol/LeftCol/MapPickerRow/MapPlayerCountOption
@onready var map_preset_option: OptionButton = $LobbyFrame/LobbyDualCol/LeftCol/MapPickerRow/MapPresetOption
@onready var map_preview_panel: Panel = $LobbyFrame/LobbyDualCol/LeftCol/MapPreviewPanel
@onready var map_preview_texture: TextureRect = $LobbyFrame/LobbyDualCol/LeftCol/MapPreviewPanel/MapPreviewTexture
@onready var map_faction_summary: RichTextLabel = $LobbyFrame/LobbyDualCol/LeftCol/MapPreviewPanel/MapFactionSummary
@onready var team_option: OptionButton = $LobbyFrame/LobbyDualCol/RightCol/TeamRow/TeamOption
@onready var lobby_apply_team_btn: Button = $LobbyFrame/LobbyDualCol/RightCol/TeamRow/LobbyApplyTeamBtn
# P1#8 房主行级队伍控制 + P1#7 切换观战(转换自己为观战者)
@onready var lobby_host_player_option: OptionButton = $LobbyFrame/HostRow/LobbyHostPlayerOption
@onready var lobby_host_team_option: OptionButton = $LobbyFrame/HostRow/LobbyHostTeamOption
@onready var lobby_host_apply_btn: Button = $LobbyFrame/HostRow/LobbyHostApplyBtn
@onready var lobby_to_spec_btn: Button = $LobbyFrame/LobbyToSpecBtn
@onready var lobby_commander_option: OptionButton = $LobbyFrame/LobbyDualCol/RightCol/LobbyCommanderOption
@onready var lobby_bgm_option: OptionButton = $LobbyFrame/LobbyDualCol/RightCol/LobbyBgmOption
@onready var win_condition_option: OptionButton = $LobbyFrame/LobbyDualCol/RightCol/WinConditionOption
@onready var create_room_btn: Button = $LobbyFrame/LobbyDualCol/RightCol/CreateRoomBtn
# Lobby 二层菜单导航
@onready var choose_panel: VBoxContainer = $LobbyFrame/ChoosePanel
@onready var create_card_btn: Button = $LobbyFrame/ChoosePanel/ChooseBtnRow/CreateCard/CreateCardInner/CreateCardBtn
@onready var join_card_btn: Button = $LobbyFrame/ChoosePanel/ChooseBtnRow/JoinCard/JoinCardInner/JoinCardBtn

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
var _lobby_seat_occupants: Array[String] = ["", "", "", ""]
var _lobby_commanders_fetched: bool = false  # API 响应后置 true,防"加载中…"误判
var _selected_lobby_seat_index: int = 0
var _pending_lobby_start_after_create: bool = false
var _pending_lobby_ai_seats: Array[int] = []
var _pending_lobby_team_updates: Array[Dictionary] = []
# 大厅轮询(2s)— 与 web app.js:918 一致
var _lobby_poll_timer: Timer = null


func _ready() -> void:
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
	# 随组件搬来:原 main._apply_hud_theme 尾部的大厅主/次按钮烫金主题
	for primary_btn in [lobby_start_btn, lobby_add_ai_btn, lobby_host_apply_btn, lobby_apply_team_btn]:
		if primary_btn != null and is_instance_valid(primary_btn):
			MenuTheme.apply_primary_button_theme(primary_btn)
	for secondary_btn in [lobby_back_btn, lobby_to_spec_btn, lobby_remove_ai_btn]:
		if secondary_btn != null and is_instance_valid(secondary_btn):
			MenuTheme.apply_secondary_button_theme(secondary_btn)


# ============================================================
# 对外接口(main.gd 调用)
# ============================================================

## main._on_lobby_pressed 入口
func open() -> void:
	_on_lobby_pressed()


## main._show_view("lobby") 时复位到二层选择页
func show_choose() -> void:
	_show_lobby_choose()


## main._on_join_game_response:加入成功 → 标题 + 起轮询 + 拉房列表 + 切房内视图
func enter_room_after_join() -> void:
	if lobby_game_id_label != null and is_instance_valid(lobby_game_id_label):
		lobby_game_id_label.text = "对局 #%d" % _main._game_id
	_start_lobby_polling()
	_refresh_room_list()
	_show_lobby_in_room()


## main._reset_game_state_for_main_menu:回主菜单时清掉大厅快照,
## 否则新房间会带着上一局的 seat/指挥官/房主状态渲染。
func reset_state() -> void:
	_lobby_seat_commander_indices = [0, 0, 0, 0]
	_lobby_commander_ids = [""]
	_selected_ai_player_id = 0
	_lobby_is_host = false


func selected_join_role() -> String:
	return _selected_join_role()


func selected_join_team() -> String:
	return _selected_join_team()


# ============================================================
# 本地词典薄壳(原在 main.gd,大厅内多处调用)
# ============================================================

func _color_emoji(c: String) -> String:
	return CnLabels.color_emoji(c)


func _commander_label(commander_id: String) -> String:
	return CnLabels.commander_label(commander_id)


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
	if _main._user_name == "" or _main._user_name == "Player":
		# 没 user_name 的早期流程不挡人 — 跟原行为一致。
		_enter_lobby_view()
		return
	NetworkClient.list_saves(
		_main._user_name, Callable(self, "_on_lobby_list_saves_for_suspend_check")
	)


func _on_lobby_list_saves_for_suspend_check(body: Variant, _code: int = 0) -> void:
	if not (body is Dictionary):
		# 拉失败兜底:不进 lobby,避免在用户不知情的情况下与 suspend 冲突。
		_main._update_status("无法检查中断存档,请稍后重试")
		return
	var suspend: Variant = body.get("suspend", null)
	if not (suspend is Dictionary):
		_enter_lobby_view()
		return
	var suspend_game_id: int = int(suspend.get("game_id", 0))
	if suspend_game_id <= 0:
		_enter_lobby_view()
		return
	_main._show_confirm(
		"放弃中断存档",
		"已经有中断存档,将放弃该中断,是否继续?",
		Callable(self, "_on_lobby_discard_suspend_yes"),
		Callable(self, "_on_lobby_discard_suspend_no"),
	)


func _on_lobby_discard_suspend_yes() -> void:
	# 用户点「继续」→ 先调 discard_suspend,等服务端 ack 后再进 lobby。
	# 注意:_hide_confirm() 已在 _on_confirm_yes_pressed 里调用过了。
	if _main._user_name == "" or _main._user_name == "Player":
		_enter_lobby_view()
		return
	_main._update_status("正在放弃中断存档...")
	NetworkClient.discard_suspend(
		_main._user_name, Callable(self, "_on_lobby_discard_suspend_response")
	)


func _on_lobby_discard_suspend_no() -> void:
	# 用户点「取消」→ 留在主菜单。什么都不做。
	_main._update_status("已取消,可继续点 ▶ 继续中断战斗")


func _on_lobby_discard_suspend_response(body: Variant, code: int = 0) -> void:
	if code < 200 or code >= 300:
		_main._update_status("放弃中断失败,请重试")
		return
	var cleared: bool = bool((body as Dictionary).get("cleared", false)) if body is Dictionary else false
	if not cleared:
		_main._update_status("没有可放弃的中断存档")
	_enter_lobby_view()


func _enter_lobby_view() -> void:
	_main._entry_flow = "lobby"
	_main._show_view("lobby")
	_apply_lobby_theme()
	_stop_lobby_polling()
	_selected_room_id = 0
	if lobby_name_input != null and is_instance_valid(lobby_name_input):
		lobby_name_input.text = "%s 的房间" % _main._user_name
	_setup_lobby_join_options()
	# T:#16 — commander 拉取统一收口在 mainline_controller._on_commanders_response,
	# 它会同时刷新主线指挥官下拉和联机大厅下拉(末尾 _main._setup_lobby_commander_options)。
	# 之前挂 Callable(self, ...) 是死链:main.gd 没有这个方法,导致不先点过主线的话
	# lobby_commander_option 永远只剩"不选择指挥官"一项,创房时所有座位都拿不到 host commander。
	NetworkClient.get_unlocked_commanders(_main._user_name, Callable(_main.mainline_view, "_on_commanders_response"))
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
	_refresh_lobby_create_start_gate()
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
		if not is_inside_tree():
			continue
		var n: Node = get_node_or_null("LobbyFrame/" + node_name)
		if n != null:
			n.visible = v


# 房主控制台专用: 隐藏"加入者/对局中"才需要的控件
# 保留 LobbyList(玩家列表) + AiConfigRow/AiActionRow(房主需要加 AI)
# 隐藏:LeftCol(房间列表,房主不需要选房) / HostRow(改队伍,合并到 TeamOption) /
#       LobbyToSpecBtn(切换观战) / MidSectionBar(对局管理,合并到顶部信息)
#       AiCommanderOption(AI 指挥官,合并到 AiConfigRow)
func _hide_lobby_host_extras(hide: bool) -> void:
	if not is_inside_tree():
		return
	for node_name in ["HostRow", "LobbyToSpecBtn", "MidSectionBar", "AiCommanderOption"]:
		var n: Node = get_node_or_null("LobbyFrame/" + node_name)
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
	if not is_inside_tree():
		return
	var lobby_list: Control = get_node_or_null("LobbyFrame/LobbyList") as Control
	if lobby_list != null:
		lobby_list.offset_top = 80.0
		lobby_list.offset_bottom = 176.0
	var dual_col: Control = get_node_or_null("LobbyFrame/LobbyDualCol") as Control
	if dual_col != null:
		dual_col.offset_top = 184.0
		dual_col.offset_bottom = 504.0
	var ai_cfg: Control = get_node_or_null("LobbyFrame/AiConfigRow") as Control
	if ai_cfg != null:
		ai_cfg.offset_top = 512.0
		ai_cfg.offset_bottom = 544.0
	var ai_act: Control = get_node_or_null("LobbyFrame/AiActionRow") as Control
	if ai_act != null:
		ai_act.offset_top = 552.0
		ai_act.offset_bottom = 584.0
	# BottomBar 改成绝对位置(原 anchor 1.0/1.0 → 顶部往上挪,避免溢出 LobbyFrame 648)
	var bb: Control = get_node_or_null("LobbyFrame/BottomBar") as Control
	if bb != null:
		bb.anchor_top = 0.0
		bb.anchor_bottom = 0.0
		bb.offset_top = 592.0
		bb.offset_bottom = 632.0


# 还原 LobbyFrame 各元素到 tscn 默认 anchor(切回非 in_room 模式时调用)
# 复位 LobbyList / DualCol / AiConfigRow / AiActionRow / BottomBar
func _restore_lobby_default_layout() -> void:
	if not is_inside_tree():
		return
	var lobby_list: Control = get_node_or_null("LobbyFrame/LobbyList") as Control
	if lobby_list != null:
		lobby_list.offset_top = 442.0
		lobby_list.offset_bottom = 580.0
	var dual_col: Control = get_node_or_null("LobbyFrame/LobbyDualCol") as Control
	if dual_col != null:
		dual_col.offset_top = 112.0
		dual_col.offset_bottom = -16.0
	var ai_cfg: Control = get_node_or_null("LobbyFrame/AiConfigRow") as Control
	if ai_cfg != null:
		ai_cfg.offset_top = 654.0
		ai_cfg.offset_bottom = 686.0
	var ai_act: Control = get_node_or_null("LobbyFrame/AiActionRow") as Control
	if ai_act != null:
		ai_act.offset_top = 726.0
		ai_act.offset_bottom = 758.0
	var bb: Control = get_node_or_null("LobbyFrame/BottomBar") as Control
	if bb != null:
		# 还原 tscn 默认 anchor(右下角)
		bb.anchor_left = 1.0
		bb.anchor_right = 1.0
		bb.anchor_top = 1.0
		bb.anchor_bottom = 1.0
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
	if not is_inside_tree():
		return
	var dual_col: Control = get_node_or_null("LobbyFrame/LobbyDualCol") as Control
	if dual_col != null:
		dual_col.offset_top = 24.0
		dual_col.offset_bottom = -48.0


func _set_lobby_dualcol_visible(v: bool) -> void:
	if not is_inside_tree():
		return
	var dc: Node = get_node_or_null("LobbyFrame/LobbyDualCol")
	if dc != null:
		dc.visible = v


func _set_lobby_leftcol_visible(v: bool) -> void:
	if not is_inside_tree():
		return
	var left_col: Node = get_node_or_null("LobbyFrame/LobbyDualCol/LeftCol")
	if left_col != null:
		left_col.visible = v


func _set_lobby_rightcol_visible(v: bool) -> void:
	if not is_inside_tree():
		return
	var right_col: Node = get_node_or_null("LobbyFrame/LobbyDualCol/RightCol")
	if right_col != null:
		right_col.visible = v


func _set_lobby_join_controls_visible(v: bool) -> void:
	for node in [room_list, room_select_option, join_mode_option, refresh_rooms_btn, join_selected_btn]:
		if node != null and is_instance_valid(node):
			node.visible = v
	var row := get_node_or_null("LobbyFrame/LobbyDualCol/LeftCol/LeftBtnRow") if is_inside_tree() else null
	if row != null:
		row.visible = v
	var spacer := get_node_or_null("LobbyFrame/LobbyDualCol/LeftCol/LeftBottomSpacer") if is_inside_tree() else null
	if spacer != null:
		spacer.visible = v


func _set_lobby_map_controls_visible(v: bool) -> void:
	if not is_inside_tree():
		return
	var picker: Control = get_node_or_null("LobbyFrame/LobbyDualCol/LeftCol/MapPickerRow") as Control
	if picker != null:
		picker.visible = v
	if map_preview_panel != null and is_instance_valid(map_preview_panel):
		map_preview_panel.visible = v


func _set_lobby_left_header_text(text: String) -> void:
	if not is_inside_tree():
		return
	var header: Label = get_node_or_null("LobbyFrame/LobbyDualCol/LeftCol/LeftHeader") as Label
	if header != null:
		header.text = text


func _set_lobby_global_team_controls_visible(v: bool) -> void:
	if not is_inside_tree():
		return
	var team_row: Control = get_node_or_null("LobbyFrame/LobbyDualCol/RightCol/TeamRow") as Control
	if team_row != null:
		team_row.visible = v


func _on_create_card_pressed() -> void:
	_show_lobby_create_view()


func _on_join_card_pressed() -> void:
	_show_lobby_join_view()
	_refresh_room_list()


func _on_lobby_create_response(body: Dictionary, _code: int = 0) -> void:
	_main._game_id = int(body.get("id", 0))
	if _main._game_id <= 0:
		lobby_status_label.text = "创建失败"
		_pending_lobby_start_after_create = false
		return
	UserSettings.set_value("session.v1.last_game_id", _main._game_id)
	lobby_game_id_label.text = "对局 #%d · 等待中" % _main._game_id
	# 自动 join
	var seat_index := clampi(_selected_lobby_seat_index, 0, _selected_lobby_player_count() - 1)
	var seat_color := str(MapPreviewSummary.SEAT_COLORS[seat_index])
	NetworkClient.join_game(_main._game_id, _main._user_name, seat_color,
		_selected_lobby_seat_team(seat_index), "", Callable(self, "_on_lobby_join_response"), seat_index)


# 创建房间后自动加 AI(等同 webui app.js 的默认行为)
# join_game 完成后调这里 → add-ai + add-ai(凑够 2 个 AI)
func _on_lobby_join_response(body: Variant, _code: int = 0) -> void:
	if body is Dictionary:
		_main._player_id = int(body.get("id", 0))
		if _main._player_id <= 0:
			_main._player_id = int(body.get("player_id", 0))
		if _main._player_id <= 0:
			var p: Variant = body.get("player", {})
			if p is Dictionary:
				_main._player_id = int(p.get("id", 0))
	if _main._player_id > 0:
		GameState.local_player_id = _main._player_id
		UserSettings.set_value("session.v1.last_player_id", _main._player_id)
	if lobby_game_id_label != null and is_instance_valid(lobby_game_id_label):
		lobby_game_id_label.text = "对局 #%d" % _main._game_id
	if _main._entry_flow == "lobby_create" and _main._game_id > 0 and _pending_lobby_start_after_create:
		_continue_lobby_create_pipeline()
		return
	_show_lobby_in_room()
	# 拉 lobby 启动轮询
	_start_lobby_polling()


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
	NetworkClient.add_ai_player(_main._game_id, difficulty, agent_kind, personality, Callable(self, "_on_auto_add_ai_response").bind(true))


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
	if _main._player_id > 0:
		_pending_lobby_team_updates.append({
			"player_id": _main._player_id,
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
		_main._game_id,
		_selected_ai_difficulty(),
		_selected_ai_kind(),
		_lobby_ai_personality_for_seat(seat_index),
		Callable(self, "_on_lobby_configured_ai_added").bind(seat_index),
		seat_index
	)


func _on_lobby_configured_ai_added(body: Variant, code: int = 0, seat_index: int = 0) -> void:
	if code >= 200 and code < 300 and body is Dictionary:
		var pid := int(body.get("id", body.get("player_id", 0)))
		var player: Variant = body.get("player", {})
		if pid <= 0 and player is Dictionary:
			pid = int(player.get("id", 0))
		if pid > 0:
			_pending_lobby_team_updates.append({
				"player_id": pid,
				"team": _selected_lobby_seat_team(seat_index),
			})
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
		_main._game_id,
		int(update.get("player_id", 0)),
		_main._player_id,
		str(update.get("team", "")),
		Callable(self, "_on_lobby_configured_team_updated")
	)


func _on_lobby_configured_team_updated(_body: Variant, _code: int = 0) -> void:
	_continue_lobby_team_updates()


func _start_configured_lobby_game() -> void:
	if not _pending_lobby_start_after_create:
		return
	# T:#17 — 不在大厅里插一句"配置完成，正在开启游戏...":这条文案
	# 会在 _on_lobby_start_response 跳到 game view 之前短暂闪在大厅,
	# 让玩家误以为有中间过渡页面要再点一次。直接发 start_game,等
	# 响应里 _main._show_view("game") 切走即可,大厅文本不更新。
	NetworkClient.start_game(_main._game_id, Callable(self, "_on_lobby_start_response"))




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
	return CnLabels.team_cn(team)


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
	_refresh_lobby_create_start_gate()


func _on_lobby_map_preset_selected(_index: int) -> void:
	_render_lobby_map_preview()
	_refresh_lobby_create_start_gate()


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
		_refresh_lobby_create_start_gate()
		return
	var summary: Dictionary = MapPreviewSummary.summarize_map(map_data)
	var title := str(summary.get("name", summary.get("id", "Map")))
	var size_text := "%dx%d" % [int(summary.get("width", 0)), int(summary.get("height", 0))]
	var players := int(summary.get("recommended_players", 0))
	map_faction_summary.text = "[b]%s[/b]  %s  %dP\n%s" % [title, size_text, players, MapPreviewSummary.build_faction_lines(summary)]
	if map_preview_texture != null and is_instance_valid(map_preview_texture):
		map_preview_texture.texture = MapPreviewSummary.render_preview_texture(map_data, 9)
	_render_lobby_seat_columns(summary)
	_refresh_lobby_create_start_gate()


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


func _configured_lobby_create_participant_count() -> int:
	var required := _selected_lobby_player_count()
	var host_seat := clampi(_selected_lobby_seat_index, 0, required - 1)
	var configured: Dictionary = {host_seat: true}
	for seat_index in range(required):
		if _lobby_ai_replacement_for_seat(seat_index):
			configured[seat_index] = true
		if _lobby_seat_occupant_name(seat_index) != "":
			configured[seat_index] = true
	return configured.size()


func _refresh_lobby_create_start_gate() -> void:
	if create_room_btn == null or not is_instance_valid(create_room_btn):
		return
	if _lobby_mode != "create":
		create_room_btn.disabled = false
		return
	var required := _selected_lobby_player_count()
	var configured := _configured_lobby_create_participant_count()
	create_room_btn.disabled = configured < required
	if configured < required:
		create_room_btn.text = "开启游戏 (%d/%d)" % [configured, required]
	else:
		create_room_btn.text = "开启游戏"


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
	card.custom_minimum_size = Vector2(0, 190)
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
	occupant.text = _lobby_seat_status_text(index)
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
	if commanders_loaded:
		commander_label.text = _lobby_seat_commander_label(index)
		commander_label.add_theme_color_override("font_color", MenuTheme.C_TEXT_WARM)
	else:
		# T:V3 — 加载中用 LOADING 色,跟 EMPTY 的 PLACEHOLDER 色区分开
		commander_label.text = "⏳ 加载中…"
		commander_label.add_theme_color_override("font_color", MenuTheme.C_LOADING)
	commander_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	commander_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
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
	ability.custom_minimum_size = Vector2(0, 34)
	ability.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	ability.clip_text = true
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


func _lobby_seat_status_text(seat_index: int) -> String:
	var occupant_name := _lobby_seat_occupant_name(seat_index)
	if occupant_name != "":
		return "%s 已入座" % occupant_name
	if _lobby_ai_replacement_for_seat(seat_index):
		return "电脑-%d（入座中…）" % (seat_index + 1)
	return "等待玩家入座"


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
	# T:#19 — 不变式:同一真人玩家至多占 1 槽。AI 替补是逐座位状态,
	# 多个空座可以同时由不同 AI 补位。
	if pressed:
		_clear_player_from_other_seats(_main._user_name, seat_index)
	if _main._game_id <= 0 or seat_index < 0:
		_render_lobby_seat_columns()
		_refresh_lobby_create_start_gate()
		return
	# 只房主能换人。/start 后 game.status != "waiting",后端会拒绝。
	if not _lobby_is_host:
		_main._update_status("只有房主可以替换该席位为 AI。")
		_render_lobby_seat_columns()
		_refresh_lobby_create_start_gate()
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
			NetworkClient.remove_player(_main._game_id, existing_pid,
				Callable(self, "_on_lobby_seat_ai_remove_response").bind(seat_index))
		_render_lobby_seat_columns()
		_refresh_lobby_create_start_gate()
		return
	# 按下 AI → 乐观显示"入座中"→ 先删旧的(人类或 AI),再加 AI。
	var ai_placeholder := "电脑-%d (入座中…)" % (seat_index + 1)
	_lobby_seat_occupants[seat_index] = ai_placeholder
	if existing_pid > 0:
		NetworkClient.remove_player(_main._game_id, existing_pid,
			Callable(self, "_on_lobby_seat_ai_add_after_remove").bind(seat_index))
	else:
		_request_add_ai_for_seat(seat_index)
	_render_lobby_seat_columns()
	_refresh_lobby_create_start_gate()


func _request_add_ai_for_seat(seat_index: int) -> void:
	if _main._game_id <= 0:
		return
	var personality := _lobby_ai_personality_for_seat(seat_index)
	NetworkClient.add_ai_player(_main._game_id, "normal", "rules", personality,
		Callable(self, "_on_lobby_seat_ai_add_response").bind(seat_index),
		seat_index)


func _on_lobby_seat_ai_remove_response(body: Variant, _code: int, seat_index: int) -> void:
	if not (body is Dictionary) or int(body.get("ok", 0)) != 1:
		_main._update_status("移除失败:%s" % str(body.get("detail", body)))
		return
	_refresh_lobby_view()


func _on_lobby_seat_ai_add_after_remove(_body: Variant, _code: int, seat_index: int) -> void:
	_request_add_ai_for_seat(seat_index)


func _on_lobby_seat_ai_add_response(body: Variant, code: int, seat_index: int) -> void:
	if code < 200 or code >= 300:
		_main._update_status("AI 入座失败:HTTP %d" % code)
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
	if _main._player_id <= 0 or _main._game_id <= 0:
		return
	# 空座位:用 player_id=0 + seat=seat_index 让后端只写
	# battle_config.seat_commanders[seat],不需要 player 记录。
	if target_pid <= 0:
		NetworkClient.update_player_commander(
			_main._game_id, 0, _main._player_id, commander_id,
			Callable(self, "_on_lobby_seat_commander_response").bind(seat_index, delta),
			seat_index
		)
		return
	# 发送后端;成功才确认;失败回退 1 step 并 toast
	NetworkClient.update_player_commander(
		_main._game_id,
		target_pid,
		_main._player_id,
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
		_main._update_status(detail)


func _on_lobby_seat_action_pressed(seat_index: int) -> void:
	_selected_lobby_seat_index = clampi(seat_index, 0, MapPreviewSummary.SEAT_COLORS.size() - 1)
	# T:#19 — 不变式:同一玩家至多占 1 个座位(同样 AI 至多占 1 槽)。
	# 在写入目标座位前,先把其它座位里出现的 _main._user_name / ai placeholder 全部清掉。
	_clear_player_from_other_seats(_main._user_name, seat_index)
	while _lobby_seat_occupants.size() <= seat_index:
		_lobby_seat_occupants.append("")
	while _lobby_seat_ai_replacements.size() <= seat_index:
		_lobby_seat_ai_replacements.append(false)
	_lobby_seat_occupants[seat_index] = _main._user_name
	_lobby_seat_ai_replacements[seat_index] = false
	if lobby_status_label != null and is_instance_valid(lobby_status_label):
		lobby_status_label.text = "%s 已入座 %d席。" % [_main._user_name, seat_index + 1]
	_render_lobby_seat_columns()
	_refresh_lobby_create_start_gate()
	if _main._game_id > 0 and _main._player_id > 0:
		NetworkClient.update_player_seat(
			_main._game_id,
			_main._player_id,
			_main._player_id,
			_selected_lobby_seat_index,
			Callable(self, "_on_lobby_seat_update_response")
		)


# T:#19 — 清掉所有其它座位里出现的 player_name / ai 占位(确保"一个玩家最多一槽")。
# exclude_seat = -1 表示所有座位都清。
func _clear_player_from_other_seats(player_name: String, exclude_seat: int = -1) -> void:
	for i in range(_lobby_seat_occupants.size()):
		if i == exclude_seat:
			continue
		if _lobby_seat_occupants[i] == player_name:
			_lobby_seat_occupants[i] = ""


func _on_lobby_seat_update_response(_body: Variant, code: int = 0) -> void:
	if code >= 200 and code < 300:
		_refresh_lobby_view()
	elif lobby_status_label != null and is_instance_valid(lobby_status_label):
		lobby_status_label.text = "座位调整失败，请刷新房间后重试。"


func _seat_color_label(color_id: String) -> String:
	return CnLabels.seat_color_label(color_id)


func _seat_display_color(color_id: String) -> Color:
	return CnLabels.seat_display_color(color_id)


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
	if _configured_lobby_create_participant_count() < _selected_lobby_player_count():
		_refresh_lobby_create_start_gate()
		if lobby_status_label != null and is_instance_valid(lobby_status_label):
			lobby_status_label.text = "请先补齐地图要求的玩家或 AI 座位。"
		return
	_main._entry_flow = "lobby_create"
	var room_name := "%s room" % _main._user_name
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
	_main._entry_flow = "lobby_join"
	_main._game_id = _selected_room_id
	if lobby_status_label != null and is_instance_valid(lobby_status_label):
		lobby_status_label.text = "正在加入房间 #%d..." % _main._game_id
	NetworkClient.join_game(_main._game_id, _main._user_name, "red", _selected_join_team(), _selected_join_role(), Callable(self, "_on_lobby_join_response"))


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
	if _main._game_id <= 0:
		return
	NetworkClient.get_game_state(_main._game_id, Callable(self, "_on_lobby_state"))


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
		if p is Dictionary and int(p.get("id", -1)) == int(_main._player_id):
			self_seat = int(p.get("seat", -1))
			self_is_spec = bool(p.get("is_spectator", false))
			break
	if self_seat >= 0:
		_selected_lobby_seat_index = self_seat
	_lobby_is_host = (_main._player_id > 0 and _main._player_id == host_player_id)
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
	var fighter_count: int = 0
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
		var is_self: bool = (id_v == _main._player_id) if (id_v != null and _main._player_id > 0) else false
		var team_v = p.get("team")
		var team: String = team_v if team_v is String else ""
		var seat_v = p.get("seat")
		var seat: int = int(seat_v) if seat_v is int else -1
		if is_spec:
			spec_count += 1
		else:
			fighter_count += 1
			if not is_ai:
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
	var required_count: int = int(game.get("capacity", _selected_lobby_player_count()))
	# Start 按钮:参战玩家 + AI 必须补齐地图要求席位。
	lobby_start_btn.disabled = fighter_count < required_count
	if start_game_inline_btn != null and is_instance_valid(start_game_inline_btn):
		start_game_inline_btn.disabled = fighter_count < required_count


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
	if _main._game_id <= 0: return
	# POST /games/{id}/add-ai(走 NetworkClient.request)
	if lobby_status_label != null and is_instance_valid(lobby_status_label):
		lobby_status_label.text = "正在添加电脑玩家..."
	NetworkClient.add_ai_player(
		_main._game_id,
		_selected_ai_difficulty(),
		_selected_ai_kind(),
		_selected_ai_personality(),
		Callable(self, "_on_lobby_add_ai_response")
	)


func _on_lobby_add_ai_response(_body: Variant, _code: int = 0) -> void:
	_refresh_lobby_view()
	_refresh_room_list()


func _on_lobby_remove_ai_pressed() -> void:
	if _main._game_id <= 0 or _selected_ai_player_id <= 0:
		return
	if lobby_status_label != null and is_instance_valid(lobby_status_label):
		lobby_status_label.text = "正在移除电脑玩家 #%d..." % _selected_ai_player_id
	NetworkClient.remove_player(_main._game_id, _selected_ai_player_id, Callable(self, "_on_lobby_remove_ai_response"))


func _on_lobby_remove_ai_response(_body: Variant, _code: int = 0) -> void:
	_selected_ai_player_id = 0
	_refresh_lobby_view()
	_refresh_room_list()


func _on_lobby_apply_team_pressed() -> void:
	if _main._game_id <= 0 or _main._player_id <= 0:
		return
	var team := _selected_join_team()
	if lobby_status_label != null and is_instance_valid(lobby_status_label):
		lobby_status_label.text = "正在更新队伍..."
	NetworkClient.update_player_team(_main._game_id, _main._player_id, _main._player_id, team, Callable(self, "_on_lobby_team_response"))


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
		lobby_to_spec_btn.disabled = _main._player_id <= 0
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
	if not _lobby_is_host or _lobby_host_target_id <= 0 or _main._game_id <= 0:
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
	NetworkClient.update_player_team(_main._game_id, _lobby_host_target_id, _main._player_id, team, Callable(self, "_on_lobby_team_response"))


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
	if _main._game_id <= 0 or _main._player_id <= 0 or _lobby_self_is_spectator:
		return
	if lobby_status_label != null and is_instance_valid(lobby_status_label):
		lobby_status_label.text = "切换为观战者..."
	# convert:DELETE 自己 + POST /join role=spectator(后端无独立 convert 接口,
	# 与 web 一致;join_game(role=spectator) 会分配 spectator 座位/颜色)。
	NetworkClient.remove_player(_main._game_id, _main._player_id, Callable(self, "_on_lobby_to_spec_removed"))


func _on_lobby_to_spec_removed(_body: Variant, _code: int = 0) -> void:
	# 旧座位已删;以观战者身份重新加入。新 player_id 由全局 api_response ->
	# _on_join_game_response 自动捕获。
	NetworkClient.join_game(_main._game_id, _main._user_name, "", "", "spectator", Callable(self, "_on_lobby_to_spec_joined"))


func _on_lobby_to_spec_joined(_body: Variant, _code: int = 0) -> void:
	_refresh_lobby_view()


func _on_lobby_start_pressed() -> void:
	if _main._game_id <= 0: return
	NetworkClient.start_game(_main._game_id, Callable(self, "_on_lobby_start_response"))


func _on_lobby_start_response(_body: Dictionary, _code: int = 0) -> void:
	if _code < 200 or _code >= 300:
		_pending_lobby_start_after_create = false
		if lobby_status_label != null and is_instance_valid(lobby_status_label):
			lobby_status_label.text = "开启失败"
		return
	_pending_lobby_start_after_create = false
	# 启动游戏 — 切到 game 视图,接 WS
	_main._show_view("game")
	NetworkClient.connect_to_game(_main._game_id, _main._player_id)
	NetworkClient.get_game_state(_main._game_id, Callable(self, "_on_state_poll_response"))
	_stop_lobby_polling()


func _on_lobby_back_pressed() -> void:
	if _lobby_mode == "create" or _lobby_mode == "join":
		_show_lobby_choose()
	elif _lobby_mode == "in_room":
		_show_lobby_choose()
	else:
		_stop_lobby_polling()
		_main._show_view("menu")


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
