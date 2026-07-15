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
@onready var end_turn_button: Button = $GameView/HUD/TopRight/EndTurnButton
@onready var gold_panel: ColorRect = $GameView/HUD/BottomLeft/GoldPanel
@onready var gold_label: Label = $GameView/HUD/BottomLeft/GoldPanel/GoldLabel
@onready var co_meter: ProgressBar = $GameView/HUD/BottomLeft/COBar
@onready var war_report_button: Button = $GameView/HUD/BottomRight/WarReportButton
@onready var war_report_panel: Panel = $GameView/HUD/WarReportPanel
@onready var action_log: RichTextLabel = $GameView/HUD/WarReportPanel/ActionLog
# V2 第 3 轮:InfoPanel 是左侧 30% 信息区(单位详情 + 玩家列表)
@onready var info_panel: Panel = $GameView/HUD/InfoPanel
@onready var commander_title: Label = $GameView/HUD/InfoPanel/CommanderTitle
@onready var commander_name: RichTextLabel = $GameView/HUD/InfoPanel/CommanderName
@onready var commander_co_bar: ProgressBar = $GameView/HUD/InfoPanel/CommanderCOBar
@onready var unit_info_title: Label = $GameView/HUD/InfoPanel/UnitInfoTitle
@onready var unit_info: RichTextLabel = $GameView/HUD/InfoPanel/UnitInfo
@onready var players_list: RichTextLabel = $GameView/HUD/InfoPanel/PlayersList
@onready var turn_banner: Label = $GameView/TurnBanner
# Main menu widgets (GBA 风 V2)
@onready var menu_button: Button = $Menu/CenterContainer/ButtonCol/FreePlayButton
@onready var lobby_button: Button = $Menu/CenterContainer/ButtonCol/LobbyButton
@onready var settings_button: Button = $Menu/CenterContainer/ButtonCol/SettingsButton
@onready var exit_button: Button = $Menu/CenterContainer/ButtonCol/ExitButton
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

# Local game state
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
	lobby_button.pressed.connect(_on_lobby_pressed)
	settings_button.pressed.connect(_on_settings_pressed)
	exit_button.pressed.connect(_on_exit_pressed)
	end_turn_button.pressed.connect(_on_end_turn_pressed)
	reconnect_button.pressed.connect(_on_reconnect_pressed)
	war_report_button.pressed.connect(_on_war_report_pressed)

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
		if path == "/games" and code == 200:
			_on_create_game_response(body)
		elif path.ends_with("/join") and code == 200:
			_on_join_game_response(body)
		elif path.ends_with("/start") and code == 200:
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


# ============================================================
# View transitions
# ============================================================

enum View { MENU, CONNECTING, GAME }

func _show_view(name: String) -> void:
	menu_panel.visible = (name == "menu")
	connecting_panel.visible = (name == "connecting")
	game_view.visible = (name == "game")


func _on_free_play_pressed() -> void:
	_update_status("正在创建对局...")
	_show_view("connecting")
	connecting_label.text = "创建对局中..."
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
	# The join response returns {game_id, player_id, ...}
	_player_id = int(body.get("player_id", 0))
	if _player_id <= 0:
		# Fallback: pull from `player.id` if shape differs.
		var p: Variant = body.get("player", {})
		if p is Dictionary:
			_player_id = int(p.get("id", 0))
	if _player_id <= 0:
		_update_status("加入失败: 响应无 player_id 字段")
		_show_view("menu")
		return
	GameState.local_player_id = _player_id
	UserSettings.set_value("session.v1.last_player_id", _player_id)
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


func _on_reconnect_pressed() -> void:
	if _game_id > 0 and _player_id > 0:
		NetworkClient.connect_to_game(_game_id, _player_id)


func _on_exit_pressed() -> void:
	get_tree().quit()


# ============================================================
# Game state → HUD
# ============================================================

func _on_state_updated(_snapshot: Dictionary) -> void:
	# Render a fresh frame from GameState.
	_repaint_board_from_state()
	_refresh_hud_from_state()


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
					terrain = String(t.get("terrain", "P"))
					subtype = String(t.get("subtype", ""))
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


func _on_unit_moved(unit_id: int, from_x: int, from_y: int, to_x: int, to_y: int, _cost: int) -> void:
	# Update local view: the Board repaints on state_updated, so we
	# just bump a turn-advance marker.
	pass


func _on_unit_attacked(attacker_id: int, target_id: int, damage: int, is_crit: bool, is_kill: bool) -> void:
	action_log.append_text("[color=#f0c75e]⚔ #%d → #%d: %d dmg%s%s[/color]\n" % [
		attacker_id, target_id, damage,
		" (暴击!)" if is_crit else "",
		" (击杀)" if is_kill else "",
	])


func _on_unit_killed(unit_id: int, _killer_id: int) -> void:
	action_log.append_text("[color=#e85a6a]💀 #%d 被击杀[/color]\n" % unit_id)


func _on_turn_ended(next_player_id, turn_number: int) -> void:
	turn_banner.text = "回合 %d → 玩家 #%s" % [turn_number, str(next_player_id)]
	turn_banner.visible = true
	await get_tree().create_timer(1.5).timeout
	turn_banner.visible = false


func _on_match_ended(winner_player_id, win_reason: String) -> void:
	turn_banner.text = "🏆 玩家 #%s 获胜! 原因: %s" % [str(winner_player_id), win_reason]
	turn_banner.visible = true


func _on_ai_thinking(thinking: bool) -> void:
	ai_thinking_label.visible = thinking


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


# ============================================================
# 主菜单新增按钮 handler
# ============================================================

func _on_lobby_pressed() -> void:
	# M3 会实装:进入大厅/创建/加入。这里先给个提示,不破坏 V2 渐进节奏。
	_update_status("联机大厅将在 M3 实装,目前先走自由对局喵~")


func _on_settings_pressed() -> void:
	_update_status("设置面板将在下一轮实现喵~")


func _on_war_report_pressed() -> void:
	# 第 5 轮接,先 toggle 显示/隐藏战报浮层
	war_report_panel.visible = not war_report_panel.visible
	if war_report_panel.visible:
		war_report_button.text = "📜 关闭战报"
	else:
		war_report_button.text = "📜 战报"


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
