extends Control
## saves_controller.gd — 存档视图控制器(P2 从 main.gd 抽离,#16 三槽卡片重做)。
##
## 三槽卡片布局(对齐 FE8 设计):
##   - SaveSlotsContainer: 3 manual 槽固定渲染(空 / 手动 / 自动覆盖)
##   - SaveAutoRow:        1 自动存档只读行
##   - SaveSuspendRow:     1 中断存档行(继续/放弃)
##
## 每行操作内联(无 SaveSelectOption)— 选槽不再需要 dropdown。
## 旧 SaveOpenList / SaveMainlineList / SaveSelectOption / SaveSlotOption 节点保留
## (visible=false)以兼容 contract test 与外部节点引用,本组件不再使用。
##
## 对外接口:
##   open()                       — main 切到 saves view 后调用:刷新存档列表
##   var _main: Node              — main 注入;跨域访问 _user_name / _active_mainline_id
##                                   / _selected_mainline_id / _resume_game_id / _game_id
##                                   / _show_view / _on_mainline_pressed / _update_status
## 节点路径相对 SavesView: $SaveFrame/<X>(原 main.gd 用 $SavesView/SaveFrame/<X>)

const MenuTheme = preload("res://scripts/ui/menu_theme.gd")
# Components registered with class_name — use global name, not preload
# (preload on a script with class_name returns GDScript resource without .new())

const _MANUAL_SLOT_COUNT := 3

var _main: Node = null

@onready var save_status: Label = $SaveFrame/SaveStatus
@onready var save_slots_container: VBoxContainer = $SaveFrame/SaveSlotsContainer
@onready var save_auto_row: PanelContainer = $SaveFrame/SaveAutoRow
@onready var save_suspend_row: PanelContainer = $SaveFrame/SaveSuspendRow
@onready var save_refresh_btn: Button = $SaveFrame/SaveRefreshBtn
@onready var save_back_btn: Button = $SaveFrame/SaveBackBtn

# Per-manual-slot row data(3 固定槽,由 _ready() 构建)
var _manual_rows: Array = []  # Array[Dictionary] {container, slot_index, badge, status, resume_btn, delete_btn, overwrite_btn}
# Current save state(from /saves response)
var _manual_slot_records: Array = []  # Array[Dictionary] aligned with slot 0/1/2;{} if empty
var _auto_record: Dictionary = {}
var _suspend_record: Dictionary = {}


func _ready() -> void:
	# 新版按钮主题
	var theme_btns := [save_refresh_btn, save_back_btn]
	for btn in theme_btns:
		if btn != null and is_instance_valid(btn):
			MenuTheme.apply_button_theme(btn, MenuTheme.FS_BTN)
	# 新版事件接线
	if save_refresh_btn != null and is_instance_valid(save_refresh_btn):
		save_refresh_btn.pressed.connect(_refresh_saves)
	if save_back_btn != null and is_instance_valid(save_back_btn):
		save_back_btn.pressed.connect(_on_save_back_pressed)
	# 构建 3 槽固定行
	_build_manual_rows()
	# 初始空态
	_render_manual_rows()
	_render_auto_row()
	_render_suspend_row()


# ── Public ──────────────────────────────────────────────────

func open() -> void:
	_refresh_saves()


# ── 3 固定槽行构建(代码生成,避免 tscn 复制粘贴 3 份)──

func _build_manual_rows() -> void:
	if save_slots_container == null or not is_instance_valid(save_slots_container):
		return
	for child in save_slots_container.get_children():
		child.queue_free()
	_manual_rows.clear()
	for slot_index in range(_MANUAL_SLOT_COUNT):
		var row := PanelContainer.new()
		row.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.custom_minimum_size = Vector2(0, 110)
		var hbox := HBoxContainer.new()
		hbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(hbox)
		# Slot badge
		var badge := Label.new()
		badge.custom_minimum_size = Vector2(70, 0)
		badge.text = "槽 %d" % (slot_index + 1)
		badge.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		badge.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		badge.add_theme_font_size_override("font_size", 22)
		hbox.add_child(badge)
		# Status RichTextLabel
		var status := RichTextLabel.new()
		status.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		status.bbcode_enabled = true
		status.fit_content = true
		status.scroll_active = false
		status.custom_minimum_size = Vector2(0, 96)
		hbox.add_child(status)
		# Buttons vertical group
		var btn_box := VBoxContainer.new()
		btn_box.custom_minimum_size = Vector2(330, 0)
		btn_box.alignment = BoxContainer.ALIGNMENT_CENTER
		btn_box.size_flags_vertical = Control.SIZE_EXPAND_FILL
		btn_box.add_theme_constant_override("separation", 4)
		var resume_btn := Button.new()
		resume_btn.text = "▶ 继续"
		resume_btn.custom_minimum_size = Vector2(0, 36)
		MenuTheme.apply_button_theme(resume_btn, MenuTheme.FS_BTN)
		resume_btn.pressed.connect(_on_manual_resume_pressed.bind(slot_index))
		btn_box.add_child(resume_btn)
		var action_row := ButtonRow.new()
		action_row.custom_minimum_size = Vector2(0, 36)
		var delete_btn := action_row.add_button("🗑 删除", ButtonRow.ButtonKind.DANGER)
		delete_btn.custom_minimum_size = Vector2(150, 36)
		delete_btn.pressed.connect(_on_manual_delete_pressed.bind(slot_index))
		var overwrite_btn := action_row.add_button("💾 覆盖", ButtonRow.ButtonKind.SECONDARY)
		overwrite_btn.custom_minimum_size = Vector2(150, 36)
		overwrite_btn.pressed.connect(_on_manual_overwrite_pressed.bind(slot_index))
		btn_box.add_child(action_row)
		hbox.add_child(btn_box)
		save_slots_container.add_child(row)
		_manual_rows.append({
			"container": row,
			"slot_index": slot_index,
			"badge": badge,
			"status": status,
			"resume_btn": resume_btn,
			"delete_btn": delete_btn,
			"overwrite_btn": overwrite_btn,
		})


# ── Data fetch ─────────────────────────────────────────────

func _refresh_saves() -> void:
	if save_status != null and is_instance_valid(save_status):
		save_status.text = "加载存档..."
	# 同步重置,以防响应慢时旧数据仍在
	_manual_slot_records = [{}, {}, {}]
	_auto_record = {}
	_suspend_record = {}
	_render_manual_rows()
	_render_auto_row()
	_render_suspend_row()
	NetworkClient.list_saves(_main._user_name, Callable(self, "_on_saves_response"))


func _on_saves_response(body: Variant, _code: int = 0) -> void:
	var parsed := _save_records_from_response(body)
	_manual_slot_records = [{}, {}, {}]
	_auto_record = {}
	_suspend_record = {}
	for rec in parsed:
		if not (rec is Dictionary):
			continue
		var kind := str(rec.get("kind", ""))
		if kind == "suspend":
			_suspend_record = rec
			continue
		if kind == "auto":
			_auto_record = rec
			continue
		if kind == "manual":
			var idx := int(rec.get("slot_index", -1))
			if idx >= 0 and idx < _MANUAL_SLOT_COUNT:
				_manual_slot_records[idx] = rec
	_render_manual_rows()
	_render_auto_row()
	_render_suspend_row()
	if save_status != null and is_instance_valid(save_status):
		var filled := 0
		for r in _manual_slot_records:
			if not r.is_empty():
				filled += 1
		save_status.text = "三槽已用 %d / 3  ·  自动 %s  ·  中断 %s" % [
			filled,
			"✓" if not _auto_record.is_empty() else "—",
			"✓" if not _suspend_record.is_empty() else "—",
		]


# ── Manual slot rendering ─────────────────────────────────

func _render_manual_rows() -> void:
	for i in range(_manual_rows.size()):
		var row: Dictionary = _manual_rows[i]
		var rec: Dictionary = _manual_slot_records[i] if i < _manual_slot_records.size() else {}
		var status: RichTextLabel = row.get("status")
		var resume: Button = row.get("resume_btn")
		var delete_btn: Button = row.get("delete_btn")
		var overwrite: Button = row.get("overwrite_btn")
		if rec.is_empty():
			if status: status.text = "[color=%s][i]空 — 可写入或被自动填充[/i][/color]" % MenuTheme.C_PLACEHOLDER.to_html(false)
			if resume: resume.disabled = true
			if delete_btn: delete_btn.disabled = true
			if overwrite: overwrite.text = "💾 新建"
		else:
			var label := _format_save_name(str(rec.get("label", "")))
			var mid := str(rec.get("mainline_id", ""))
			var chidx := int(rec.get("chapter_index", 0)) + 1
			var kind_lbl := "主线" if mid != "" else "自由战"
			if status:
				status.text = "[b]%s[/b]\n[color=#d8c48a]%s · 第 %d 章 · %s[/color]" % [
					_bb(label), kind_lbl, chidx, _format_save_status(str(rec.get("status", "manual"))),
				]
			if resume: resume.disabled = false
			if delete_btn: delete_btn.disabled = false
			if overwrite: overwrite.text = "💾 覆盖"


func _render_auto_row() -> void:
	if save_auto_row == null or not is_instance_valid(save_auto_row):
		return
	for child in save_auto_row.get_children():
		child.queue_free()
	if _auto_record.is_empty():
		var empty := StatusBadge.new()
		empty.setup(StatusBadge.Kind.EMPTY, "暂无自动存档 — 完成章节或点「准备好了」后自动写入")
		save_auto_row.add_child(empty)
		return
	var hbox := HBoxContainer.new()
	hbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	hbox.add_theme_constant_override("separation", MenuTheme.GAP_M)
	var label := _format_save_name(str(_auto_record.get("label", "")))
	var mid := str(_auto_record.get("mainline_id", ""))
	var chidx := int(_auto_record.get("chapter_index", 0)) + 1
	var info := RichTextLabel.new()
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	info.bbcode_enabled = true
	info.fit_content = true
	info.text = "[b]%s[/b]\n[color=#d8c48a]%s · 第 %d 章 · 自动[/color]" % [_bb(label), mid if mid != "" else "—", chidx]
	hbox.add_child(info)
	var load_btn := Button.new()
	load_btn.text = "▶ 载入(会清除自动)"
	load_btn.custom_minimum_size = Vector2(220, 40)
	MenuTheme.apply_button_theme(load_btn, MenuTheme.FS_BTN)
	load_btn.pressed.connect(_on_auto_load_pressed)
	hbox.add_child(load_btn)
	save_auto_row.add_child(hbox)


func _render_suspend_row() -> void:
	if save_suspend_row == null or not is_instance_valid(save_suspend_row):
		return
	for child in save_suspend_row.get_children():
		child.queue_free()
	if _suspend_record.is_empty():
		var empty := StatusBadge.new()
		empty.setup(StatusBadge.Kind.EMPTY, "无中断存档 — 游戏中按「暂停 → 中断退出」会写入此处")
		save_suspend_row.add_child(empty)
		return
	var hbox := HBoxContainer.new()
	hbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var game_id := int(_suspend_record.get("game_id", 0))
	var mid := str(_suspend_record.get("mainline_id", ""))
	var info := RichTextLabel.new()
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	info.bbcode_enabled = true
	info.fit_content = true
	info.text = "[b]中断存档[/b] game #%d\n[color=#d8c48a]%s · 触发点: %s[/color]" % [
		game_id, mid if mid != "" else "自由战", str(_suspend_record.get("suspend_point", "manual"))
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
	save_suspend_row.add_child(hbox)


# ── Manual slot actions ───────────────────────────────────

func _on_manual_resume_pressed(slot_index: int) -> void:
	if slot_index < 0 or slot_index >= _manual_slot_records.size():
		return
	var rec: Dictionary = _manual_slot_records[slot_index]
	if rec.is_empty():
		_update_status("槽 %d 是空的" % (slot_index + 1))
		return
	if save_status != null and is_instance_valid(save_status):
		save_status.text = "正在载入槽 %d..." % (slot_index + 1)
	NetworkClient.load_save(
		_main._user_name,
		str(rec.get("kind", "manual")),
		int(rec.get("slot_index", slot_index)),
		Callable(self, "_on_save_load_response").bind(rec)
	)


func _on_manual_delete_pressed(slot_index: int) -> void:
	if slot_index < 0 or slot_index >= _manual_slot_records.size():
		return
	var rec: Dictionary = _manual_slot_records[slot_index]
	if rec.is_empty():
		_update_status("槽 %d 是空的,无需删除" % (slot_index + 1))
		return
	if save_status != null and is_instance_valid(save_status):
		save_status.text = "正在删除槽 %d..." % (slot_index + 1)
	NetworkClient.erase_save(
		_main._user_name,
		str(rec.get("kind", "manual")),
		int(rec.get("slot_index", slot_index)),
		Callable(self, "_on_save_delete_response").bind(slot_index)
	)


func _on_manual_overwrite_pressed(slot_index: int) -> void:
	# 覆盖/新建:语义相同,都是写当前进度到指定 slot
	if _main._user_name == "":
		_main._update_status("请先在设置填写玩家昵称")
		return
	var mid: String = _current_save_mainline_id()
	if mid == "":
		_main._update_status("无法存档:当前没有关联主线/对局")
		return
	var chidx: int = _current_save_chapter_index()
	var label: String = ("第 %d 章 - 手动" % (chidx + 1)) if _main._active_mainline_id != "" else ("自由战 #%d - 手动" % _main._game_id)
	if save_status != null and is_instance_valid(save_status):
		save_status.text = "正在写入槽 %d ..." % (slot_index + 1)
	NetworkClient.save_manual(
		_main._user_name,
		slot_index,
		mid,
		chidx,
		label,
		Callable(self, "_on_save_new_response").bind(slot_index)
	)


# ── Auto / suspend actions ────────────────────────────────

func _on_auto_load_pressed() -> void:
	if _auto_record.is_empty():
		return
	if save_status != null and is_instance_valid(save_status):
		save_status.text = "正在载入自动存档..."
	NetworkClient.load_save(
		_main._user_name,
		"auto",
		0,
		Callable(self, "_on_save_load_response").bind(_auto_record)
	)


func _on_suspend_resume_pressed() -> void:
	if _suspend_record.is_empty():
		return
	if save_status != null and is_instance_valid(save_status):
		save_status.text = "正在恢复中断存档..."
	NetworkClient.load_suspend(_main._user_name, Callable(self, "_on_save_suspend_load_response"))


func _on_suspend_discard_pressed() -> void:
	if _suspend_record.is_empty():
		return
	if save_status != null and is_instance_valid(save_status):
		save_status.text = "正在放弃中断存档..."
	NetworkClient.discard_suspend(_main._user_name, Callable(self, "_on_suspend_discard_response"))


# ── Network callbacks ─────────────────────────────────────

func _on_save_load_response(body: Variant, code: int, record: Dictionary) -> void:
	if code < 200 or code >= 300 or not (body is Dictionary):
		if save_status != null and is_instance_valid(save_status):
			save_status.text = "载入失败"
		return
	_main._active_mainline_id = str(body.get("mainline_id", record.get("mainline_id", "")))
	_main._selected_mainline_id = _main._active_mainline_id if _main._active_mainline_id != "" else _main._selected_mainline_id
	UserSettings.set_value("session.v1.mainline_id", _main._active_mainline_id)
	if save_status != null and is_instance_valid(save_status):
		save_status.text = "已载入 %s" % _save_option_label(record)
	_main._show_view("mainline")
	_main._on_mainline_pressed()


func _on_save_delete_response(_body: Variant, code: int, slot_index: int) -> void:
	if code >= 200 and code < 300:
		if save_status != null and is_instance_valid(save_status):
			save_status.text = "已删除槽 %d" % (slot_index + 1)
		_refresh_saves()
	else:
		if save_status != null and is_instance_valid(save_status):
			save_status.text = "删除失败"


func _on_save_new_response(body: Variant, code: int, slot_index: int) -> void:
	if code < 200 or code >= 300:
		var msg: String = "存档失败"
		if body is Dictionary and body.has("detail"):
			msg = "存档失败: %s" % str(body.get("detail"))
		_main._update_status(msg)
		if save_status != null and is_instance_valid(save_status):
			save_status.text = msg
		return
	if save_status != null and is_instance_valid(save_status):
		save_status.text = "已保存到槽 %d" % (slot_index + 1)
	_main._update_status("💾 已写入槽 %d" % (slot_index + 1))
	_refresh_saves()


func _on_save_suspend_load_response(body: Variant, code: int) -> void:
	if code < 200 or code >= 300 or not (body is Dictionary):
		if save_status != null and is_instance_valid(save_status):
			save_status.text = "恢复中断存档失败"
		return
	var game_id := int(body.get("game_id", 0))
	if game_id <= 0:
		if save_status != null and is_instance_valid(save_status):
			save_status.text = "中断存档没有可恢复对局"
		return
	_main._resume_game_id = game_id
	_main._active_mainline_id = str(body.get("mainline_id", ""))
	UserSettings.set_value("session.v1.mainline_id", _main._active_mainline_id)
	# #16 — 复用了 main._on_resume_rejoin_response(与 _on_ml_slot_resume_response 等价)
	NetworkClient.rejoin_game_by_name(game_id, _main._user_name, Callable(_main, "_on_resume_rejoin_response"))


func _on_suspend_discard_response(body: Variant, code: int) -> void:
	if code >= 200 and code < 300:
		var cleared := false
		if body is Dictionary:
			cleared = bool(body.get("cleared", false))
		if save_status != null and is_instance_valid(save_status):
			save_status.text = "已放弃中断存档" if cleared else "无中断存档可放弃"
		_refresh_saves()
	else:
		if save_status != null and is_instance_valid(save_status):
			save_status.text = "放弃中断存档失败"


# ── Back / helpers ────────────────────────────────────────

func _on_save_back_pressed() -> void:
	_main._show_view("menu")


func _update_status(msg: String) -> void:
	if save_status != null and is_instance_valid(save_status):
		save_status.text = msg
	_main._update_status(msg)


# ── Format helpers (kept for save_load / suspend labels) ─

func _format_save_name(raw_name: String) -> String:
	if raw_name.begins_with("mainline:"):
		var parts := raw_name.split(":")
		if parts.size() >= 3:
			return "%s · %s" % [parts[1], parts[2]]
		if parts.size() >= 2:
			return parts[1]
	return raw_name if raw_name != "" else "未命名存档"


func _format_save_status(status: String) -> String:
	match status:
		"waiting":
			return "等待中"
		"playing":
			return "进行中"
		"finished":
			return "已结束"
		_:
			return status


func _save_option_label(record: Dictionary) -> String:
	if record.is_empty():
		return "存档"
	var kind := str(record.get("kind", "manual"))
	if kind == "suspend":
		return "中断存档 game #%d" % int(record.get("game_id", 0))
	var label := _format_save_name(str(record.get("label", "")))
	if label == "":
		label = "%s slot %d" % [kind, int(record.get("slot_index", 0)) + 1]
	return "%s · %s" % [label, kind]


func _save_records_from_response(body: Variant) -> Array:
	var out: Array = []
	if body is Array:
		return (body as Array).duplicate(true)
	if not (body is Dictionary):
		return out
	var manual_slots: Array = body.get("manual_slots", []) if body.get("manual_slots", []) is Array else []
	for i in range(manual_slots.size()):
		var slot: Variant = manual_slots[i]
		if slot is Dictionary:
			var record: Dictionary = (slot as Dictionary).duplicate(true)
			record["kind"] = str(record.get("kind", "manual"))
			record["slot_index"] = int(record.get("slot_index", i))
			out.append(record)
	var auto_slot: Variant = body.get("auto_slot", null)
	if auto_slot is Dictionary:
		var auto_record: Dictionary = (auto_slot as Dictionary).duplicate(true)
		auto_record["kind"] = "auto"
		auto_record["slot_index"] = int(auto_record.get("slot_index", 0))
		out.append(auto_record)
	var suspend: Variant = body.get("suspend", null)
	if suspend is Dictionary:
		var suspend_record: Dictionary = (suspend as Dictionary).duplicate(true)
		suspend_record["kind"] = "suspend"
		suspend_record["slot_index"] = -1
		out.append(suspend_record)
	return out


# 当前主线 / 章节取自 _main,跨域访问
func _current_save_mainline_id() -> String:
	if _main._active_mainline_id != "":
		return _main._active_mainline_id
	if GameState != null:
		var gs: Dictionary = GameState.game_summary if GameState else {}
		var name: String = str(gs.get("name", ""))
		if name.begins_with("mainline:"):
			var parts := name.split(":")
			if parts.size() >= 2:
				return parts[1]
	if _main._game_id > 0:
		return "freeplay"
	return ""


func _current_save_chapter_index() -> int:
	if _main._active_mainline_id != "" and GameState != null:
		var gs: Dictionary = GameState.game_summary
		return int(gs.get("chapter_index", 0))
	if GameState != null:
		var gs2: Dictionary = GameState.game_summary
		var name: String = str(gs2.get("name", ""))
		if name.begins_with("mainline:"):
			var parts := name.split(":")
			if parts.size() >= 3:
				return int(parts[2]) if parts[2].is_valid_int() else 0
	return 0


# Tiny BB escape so RichTextLabel 不会把 label 里的冒号/方括号当 markup
func _bb(s: String) -> String:
	return s.replace("[", "\\[").replace("]", "\\]")
