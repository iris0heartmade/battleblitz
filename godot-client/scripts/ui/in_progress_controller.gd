extends Control
## in_progress_controller.gd — 进行中视图控制器(#16 新增, 与 saves_view 互补)。
##
## 跟 main menu 的 ResumeButton 不同:ResumeButton 只显示"最近一个可恢复"的一键按钮;
## InProgressView 列出**所有**可恢复的项目(中断 / 活动对局 / 活动主线存档),每项独立操作。
## 配色与 SavesView 一致:暗背景 + 金色边框 + 白/暗黄文字。
##
## 对外接口:
##   open()                       — main 切到 in_progress view 后调用:并行拉 /saves + /games
##   var _main: Node              — main 注入;跨域访问 _user_name / _active_mainline_id
##                                   / _resume_game_id / _show_view / _update_status
## 节点路径相对 InProgressView: $IPFrame/<X>

const MenuTheme = preload("res://scripts/ui/menu_theme.gd")

const _MAX_GAMES_SHOWN := 5  # 防止一次性显示几十个 waiting 游戏(去重后取最近 N 个)

var _main: Node = null

@onready var ip_status: Label = $IPFrame/IPStatus
@onready var ip_list: VBoxContainer = $IPFrame/IPScroll/IPList
@onready var ip_back_btn: Button = $IPFrame/IPBackBtn

# State
var _suspend_record: Dictionary = {}
var _active_games: Array = []  # Array[Dictionary] from /games?user_name= (status in playing/waiting)
var _mainline_save_records: Array = []  # Array[Dictionary] from /saves manual_slots (filtered to mainline_id != "")


func _ready() -> void:
	if ip_back_btn != null and is_instance_valid(ip_back_btn):
		ip_back_btn.pressed.connect(_on_back_pressed)
		MenuTheme.apply_button_theme(ip_back_btn, MenuTheme.FS_BTN)
	_render_empty()


# ── Public ──────────────────────────────────────────────────

func open() -> void:
	_refresh()


# ── Data fetch ─────────────────────────────────────────────

func _refresh() -> void:
	if ip_status != null and is_instance_valid(ip_status):
		ip_status.text = "加载中..."
	_suspend_record = {}
	_active_games = []
	_mainline_save_records = []
	_render_empty()
	# 并行拉两路(不阻塞)
	NetworkClient.list_saves(_main._user_name, Callable(self, "_on_saves_response"))
	NetworkClient.list_games(Callable(self, "_on_games_response"), _main._user_name)


func _on_saves_response(body: Variant, _code: int = 0) -> void:
	# /saves schema: { manual_slots, auto_slot, suspend }
	if not (body is Dictionary):
		return
	var suspend: Variant = body.get("suspend", null)
	if suspend is Dictionary:
		_suspend_record = (suspend as Dictionary).duplicate(true)
		_suspend_record["kind"] = "suspend"
	var manual_slots: Array = body.get("manual_slots", []) if body.get("manual_slots", []) is Array else []
	_mainline_save_records = []
	for slot in manual_slots:
		if not (slot is Dictionary): continue
		if str(slot.get("mainline_id", "")) == "": continue
		var record: Dictionary = (slot as Dictionary).duplicate(true)
		record["kind"] = "manual"
		_mainline_save_records.append(record)
	_render_full()


func _on_games_response(body: Variant, _code: int = 0) -> void:
	# /games?user_name= 返回 Array[GameSummaryOut]
	_active_games = []
	if body is Array:
		for g in body:
			if not (g is Dictionary): continue
			var status := str(g.get("status", ""))
			if status != "playing" and status != "waiting": continue
			_active_games.append(g)
	# 限制最多显示 N 个(playing 优先,waiting 次之)
	_active_games.sort_custom(func(a, b):
		var ap := str(a.get("status", "")) == "playing"
		var bp := str(b.get("status", "")) == "playing"
		if ap == bp:
			return int(a.get("id", 0)) > int(b.get("id", 0))
		return ap
	)
	if _active_games.size() > _MAX_GAMES_SHOWN:
		_active_games = _active_games.slice(0, _MAX_GAMES_SHOWN)
	_render_full()


# ── Render ─────────────────────────────────────────────────

func _render_empty() -> void:
	# 占位渲染(空态)
	_render_full()


func _render_full() -> void:
	if ip_list == null or not is_instance_valid(ip_list):
		return
	for child in ip_list.get_children():
		child.queue_free()
	var total := 0
	if not _suspend_record.is_empty():
		_render_section_title("⏸  中断存档  (战斗中保存的临时进度)")
		_render_suspend_row()
		total += 1
	if not _active_games.is_empty():
		_render_section_title("🎮  进行中游戏  (在 /games 列表里 status = playing/waiting)")
		for g in _active_games:
			_render_game_row(g)
		total += _active_games.size()
	if not _mainline_save_records.is_empty():
		_render_section_title("📖  已存档的活动主线  (manual 槽且 mainline_id != \"\")")
		for rec in _mainline_save_records:
			_render_mainline_save_row(rec)
		total += _mainline_save_records.size()
	if total == 0:
		var empty := Label.new()
		empty.text = "(无进行中项目 — 玩主线 / 开房 / 战斗中按暂停写入中断存档后,会出现在这里)"
		empty.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		empty.modulate = Color(0.65, 0.6, 0.45)
		empty.add_theme_font_size_override("font_size", 18)
		ip_list.add_child(empty)
	if ip_status != null and is_instance_valid(ip_status):
		ip_status.text = "共 %d 个可恢复项" % total


func _render_section_title(text: String) -> void:
	var spacer_top := Control.new()
	spacer_top.custom_minimum_size = Vector2(0, 6)
	ip_list.add_child(spacer_top)
	var title := Label.new()
	title.text = text
	title.add_theme_font_size_override("font_size", 20)
	title.modulate = Color(0.65, 0.6, 0.45)
	ip_list.add_child(title)


func _render_suspend_row() -> void:
	var row := PanelContainer.new()
	row.custom_minimum_size = Vector2(0, 80)
	var hbox := HBoxContainer.new()
	hbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(hbox)
	var info := RichTextLabel.new()
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	info.bbcode_enabled = true
	info.fit_content = true
	info.text = "[b]中断存档[/b] game #%d\n[color=#d8c48a]%s · 触发点: %s[/color]" % [
		int(_suspend_record.get("game_id", 0)),
		str(_suspend_record.get("mainline_id", "自由战")),
		str(_suspend_record.get("suspend_point", "manual")),
	]
	hbox.add_child(info)
	var btn_box := VBoxContainer.new()
	btn_box.add_theme_constant_override("separation", 4)
	var resume_btn := Button.new()
	resume_btn.text = "▶ 继续"
	resume_btn.custom_minimum_size = Vector2(180, 36)
	MenuTheme.apply_button_theme(resume_btn, MenuTheme.FS_BTN)
	resume_btn.pressed.connect(_on_suspend_resume_pressed)
	btn_box.add_child(resume_btn)
	var discard_btn := Button.new()
	discard_btn.text = "🗑 放弃"
	discard_btn.custom_minimum_size = Vector2(180, 36)
	MenuTheme.apply_button_theme(discard_btn, MenuTheme.FS_BTN)
	discard_btn.pressed.connect(_on_suspend_discard_pressed)
	btn_box.add_child(discard_btn)
	hbox.add_child(btn_box)
	ip_list.add_child(row)


func _render_game_row(g: Dictionary) -> void:
	var row := PanelContainer.new()
	row.custom_minimum_size = Vector2(0, 70)
	var hbox := HBoxContainer.new()
	hbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(hbox)
	var game_id := int(g.get("id", 0))
	var status := str(g.get("status", "?"))
	var name := str(g.get("name", ""))
	var status_cn := "进行中" if status == "playing" else ("等待中" if status == "waiting" else status)
	var info := RichTextLabel.new()
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	info.bbcode_enabled = true
	info.fit_content = true
	info.text = "[b]对局 #%d[/b]  ·  %s\n[color=#d8c48a]%s[/color]" % [
		game_id, status_cn, name if name != "" else "(未命名)"
	]
	hbox.add_child(info)
	var resume_btn := Button.new()
	resume_btn.text = "▶ 继续"
	resume_btn.custom_minimum_size = Vector2(180, 50)
	MenuTheme.apply_button_theme(resume_btn, MenuTheme.FS_BTN)
	resume_btn.pressed.connect(_on_game_resume_pressed.bind(game_id))
	hbox.add_child(resume_btn)
	ip_list.add_child(row)


func _render_mainline_save_row(rec: Dictionary) -> void:
	var row := PanelContainer.new()
	row.custom_minimum_size = Vector2(0, 70)
	var hbox := HBoxContainer.new()
	hbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(hbox)
	var mid := str(rec.get("mainline_id", ""))
	var chidx := int(rec.get("chapter_index", 0)) + 1
	var label := str(rec.get("label", ""))
	var info := RichTextLabel.new()
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	info.bbcode_enabled = true
	info.fit_content = true
	info.text = "[b]%s[/b]  ·  第 %d 章  ·  槽 %d\n[color=#d8c48a]%s[/color]" % [
		mid, chidx, int(rec.get("slot_index", 0)) + 1,
		label if label != "" else "(无标签)"
	]
	hbox.add_child(info)
	var btn_box := VBoxContainer.new()
	btn_box.add_theme_constant_override("separation", 4)
	var resume_btn := Button.new()
	resume_btn.text = "▶ 继续"
	resume_btn.custom_minimum_size = Vector2(150, 32)
	MenuTheme.apply_button_theme(resume_btn, MenuTheme.FS_BTN)
	resume_btn.pressed.connect(_on_mainline_save_resume_pressed.bind(rec))
	btn_box.add_child(resume_btn)
	var delete_btn := Button.new()
	delete_btn.text = "🗑 删除"
	delete_btn.custom_minimum_size = Vector2(150, 32)
	MenuTheme.apply_button_theme(delete_btn, MenuTheme.FS_BTN)
	delete_btn.pressed.connect(_on_mainline_save_delete_pressed.bind(rec))
	btn_box.add_child(delete_btn)
	hbox.add_child(btn_box)
	ip_list.add_child(row)


# ── Action callbacks ───────────────────────────────────────

func _on_back_pressed() -> void:
	_main._show_view("menu")


func _on_suspend_resume_pressed() -> void:
	if ip_status != null and is_instance_valid(ip_status):
		ip_status.text = "正在恢复中断存档..."
	NetworkClient.load_suspend(_main._user_name, Callable(self, "_on_load_suspend_response"))


func _on_load_suspend_response(body: Variant, code: int) -> void:
	if code < 200 or code >= 300 or not (body is Dictionary):
		if ip_status != null and is_instance_valid(ip_status):
			ip_status.text = "恢复中断存档失败"
		return
	var game_id := int(body.get("game_id", 0))
	if game_id <= 0:
		if ip_status != null and is_instance_valid(ip_status):
			ip_status.text = "中断存档没有可恢复对局"
		return
	_main._resume_game_id = game_id
	_main._active_mainline_id = str(body.get("mainline_id", ""))
	UserSettings.set_value("session.v1.mainline_id", _main._active_mainline_id)
	NetworkClient.rejoin_game_by_name(game_id, _main._user_name, Callable(_main, "_on_resume_rejoin_response"))


func _on_suspend_discard_pressed() -> void:
	if ip_status != null and is_instance_valid(ip_status):
		ip_status.text = "正在放弃中断存档..."
	NetworkClient.discard_suspend(_main._user_name, Callable(self, "_on_discard_suspend_response"))


func _on_discard_suspend_response(body: Variant, code: int) -> void:
	if code >= 200 and code < 300:
		var cleared := false
		if body is Dictionary:
			cleared = bool(body.get("cleared", false))
		if ip_status != null and is_instance_valid(ip_status):
			ip_status.text = "已放弃中断存档" if cleared else "无中断存档可放弃"
		_refresh()
	else:
		if ip_status != null and is_instance_valid(ip_status):
			ip_status.text = "放弃中断存档失败"


func _on_game_resume_pressed(game_id: int) -> void:
	if game_id <= 0: return
	if ip_status != null and is_instance_valid(ip_status):
		ip_status.text = "正在重连对局 #%d..." % game_id
	_main._resume_game_id = game_id
	_main._resume_kind = "game"
	NetworkClient.rejoin_game_by_name(game_id, _main._user_name, Callable(_main, "_on_resume_rejoin_response"))


func _on_mainline_save_resume_pressed(rec: Dictionary) -> void:
	if rec.is_empty(): return
	if ip_status != null and is_instance_valid(ip_status):
		ip_status.text = "正在载入主线存档..."
	NetworkClient.load_save(
		_main._user_name,
		str(rec.get("kind", "manual")),
		int(rec.get("slot_index", 0)),
		Callable(self, "_on_load_save_response").bind(rec)
	)


func _on_load_save_response(body: Variant, code: int, rec: Dictionary) -> void:
	if code < 200 or code >= 300 or not (body is Dictionary):
		if ip_status != null and is_instance_valid(ip_status):
			ip_status.text = "载入主线存档失败"
		return
	_main._active_mainline_id = str(body.get("mainline_id", rec.get("mainline_id", "")))
	_main._selected_mainline_id = _main._active_mainline_id if _main._active_mainline_id != "" else _main._selected_mainline_id
	UserSettings.set_value("session.v1.mainline_id", _main._active_mainline_id)
	if ip_status != null and is_instance_valid(ip_status):
		ip_status.text = "已载入主线存档"
	_main._show_view("mainline")
	_main._on_mainline_pressed()


func _on_mainline_save_delete_pressed(rec: Dictionary) -> void:
	if rec.is_empty(): return
	if ip_status != null and is_instance_valid(ip_status):
		ip_status.text = "正在删除主线存档..."
	NetworkClient.erase_save(
		_main._user_name,
		str(rec.get("kind", "manual")),
		int(rec.get("slot_index", 0)),
		Callable(self, "_on_erase_save_response")
	)


func _on_erase_save_response(_body: Variant, code: int) -> void:
	if code >= 200 and code < 300:
		if ip_status != null and is_instance_valid(ip_status):
			ip_status.text = "已删除主线存档"
		_refresh()
	else:
		if ip_status != null and is_instance_valid(ip_status):
			ip_status.text = "删除主线存档失败"
