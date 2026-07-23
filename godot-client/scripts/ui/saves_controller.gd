extends Control
## saves_controller.gd — 存档视图控制器(P2 从 main.gd 抽离)。
## 挂在场景 SavesView 节点上,自管面板内部逻辑;view 可见性仍由 main._show_view 控制。
## 对外接口:
##   open()                  — main 切到 saves view 后调用:刷新存档列表
##   var _main: Node         — main 注入;跨域访问 _user_name / _active_mainline_id
##                              / _selected_mainline_id / _resume_game_id / _game_id
##                              / _show_view / _on_mainline_pressed / _update_status
## 节点路径相对 SavesView: $SaveFrame/<X>(原 main.gd 用 $SavesView/SaveFrame/<X>)
## 保留 Callable 跨域转发,所有 _on_save_* 内部回调仍写 self。

const MenuTheme = preload("res://scripts/ui/menu_theme.gd")

var _main: Node = null

@onready var save_status: Label = $SaveFrame/SaveStatus
@onready var save_open_list: RichTextLabel = $SaveFrame/SaveOpenList
@onready var save_mainline_list: RichTextLabel = $SaveFrame/SaveMainlineList
@onready var save_select_option: OptionButton = $SaveFrame/SaveSelectOption
@onready var save_resume_btn: Button = $SaveFrame/SaveResumeBtn
@onready var save_delete_btn: Button = $SaveFrame/SaveDeleteBtn
@onready var save_refresh_btn: Button = $SaveFrame/SaveRefreshBtn
@onready var save_new_btn: Button = $SaveFrame/SaveNewBtn
@onready var save_slot_option: OptionButton = $SaveFrame/SaveSlotOption
@onready var save_back_btn: Button = $SaveFrame/SaveBackBtn

var _save_records: Array = []
var _selected_save_id: int = 0


func _ready() -> void:
	if save_select_option != null and is_instance_valid(save_select_option):
		save_select_option.item_selected.connect(_on_save_selected)
	if save_resume_btn != null and is_instance_valid(save_resume_btn):
		save_resume_btn.pressed.connect(_on_save_resume_pressed)
	if save_delete_btn != null and is_instance_valid(save_delete_btn):
		save_delete_btn.pressed.connect(_on_save_delete_pressed)
	if save_refresh_btn != null and is_instance_valid(save_refresh_btn):
		save_refresh_btn.pressed.connect(_refresh_saves)
	if save_new_btn != null and is_instance_valid(save_new_btn):
		save_new_btn.pressed.connect(_on_save_new_pressed)
	if save_back_btn != null and is_instance_valid(save_back_btn):
		save_back_btn.pressed.connect(_on_save_back_pressed)
	# P2: GBA 火纹主题(原 main._apply_gba_theme 按钮列表里的 saves 按钮,随组件搬来)
	var theme_btns := [save_resume_btn, save_delete_btn, save_refresh_btn, save_new_btn, save_back_btn]
	for btn in theme_btns:
		if btn != null and is_instance_valid(btn):
			MenuTheme.apply_button_theme(btn, MenuTheme.FS_BTN)


func open() -> void:
	_refresh_saves()


func _refresh_saves() -> void:
	_selected_save_id = 0
	_save_records.clear()
	if save_status != null and is_instance_valid(save_status):
		save_status.text = "加载存档..."
	if save_open_list != null and is_instance_valid(save_open_list):
		save_open_list.text = "[color=#a69a73]加载中...[/color]"
	if save_mainline_list != null and is_instance_valid(save_mainline_list):
		save_mainline_list.text = "[color=#a69a73]加载中...[/color]"
	if save_select_option != null and is_instance_valid(save_select_option):
		save_select_option.clear()
	NetworkClient.list_saves(_main._user_name, Callable(self, "_on_saves_response"))


func _on_saves_response(body: Variant, _code: int = 0) -> void:
	var games: Array = _save_records_from_response(body)
	_save_records = []
	var open_lines: Array[String] = []
	var mainline_lines: Array[String] = []
	if save_select_option != null and is_instance_valid(save_select_option):
		save_select_option.clear()
	for record_index in range(games.size()):
		var g: Variant = games[record_index]
		if not (g is Dictionary):
			continue
		_save_records.append(g)
		var line := _format_save_line(g)
		var name := str(g.get("name", ""))
		var mainline_id := str(g.get("mainline_id", ""))
		var kind := str(g.get("kind", "manual"))
		if mainline_id != "" or kind == "suspend" or name.begins_with("mainline:"):
			mainline_lines.append(line)
		else:
			open_lines.append(line)
		if save_select_option != null and is_instance_valid(save_select_option):
			save_select_option.add_item(_save_option_label(g), record_index + 1)
	if open_lines.is_empty():
		open_lines.append("[color=#a69a73]暂无开房模式存档[/color]")
	if mainline_lines.is_empty():
		mainline_lines.append("[color=#a69a73]暂无主线模式存档[/color]")
	if save_open_list != null and is_instance_valid(save_open_list):
		save_open_list.text = "\n".join(open_lines)
	if save_mainline_list != null and is_instance_valid(save_mainline_list):
		save_mainline_list.text = "\n".join(mainline_lines)
	if save_select_option != null and is_instance_valid(save_select_option) and save_select_option.item_count > 0:
		save_select_option.select(0)
		_on_save_selected(0)
	else:
		_selected_save_id = 0
	if save_status != null and is_instance_valid(save_status):
		save_status.text = "共 %d 个存档" % _save_records.size()


func _format_save_line(g: Dictionary) -> String:
	var save_id: int = int(g.get("id", 0))
	var kind := str(g.get("kind", "manual"))
	if kind == "suspend":
		var game_id := int(g.get("game_id", 0))
		return "[b]中断存档[/b] [color=#a69a73]game #%d[/color]\n[color=#d8c48a]%s · %s[/color]" % [
			game_id, str(g.get("mainline_id", "自由战斗")), str(g.get("suspend_point", "manual"))
		]
	var label := _format_save_name(str(g.get("label", g.get("name", ""))))
	var mainline_id := str(g.get("mainline_id", ""))
	var chapter_index := int(g.get("chapter_index", 0)) + 1
	var detail := "%s · 第 %d 章 · %s" % [mainline_id, chapter_index, kind] if mainline_id != "" else "%s · 回合 %d · 种子 %s" % [
		_format_save_status(str(g.get("status", kind))),
		int(g.get("turn_number", 0)),
		str(g.get("map_seed", g.get("seed", "?"))),
	]
	return "[b]%s[/b] [color=#a69a73]#%d[/color]\n[color=#d8c48a]%s[/color]" % [label, save_id, detail]


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


func _on_save_selected(index: int) -> void:
	if save_select_option == null or not is_instance_valid(save_select_option):
		return
	if index < 0 or index >= save_select_option.item_count:
		_selected_save_id = 0
		return
	_selected_save_id = save_select_option.get_item_id(index)
	if save_status != null and is_instance_valid(save_status):
		var record := _selected_save_record()
		save_status.text = "已选择 %s" % (_save_option_label(record) if not record.is_empty() else "存档")


func _on_save_resume_pressed() -> void:
	var record := _selected_save_record()
	if record.is_empty():
		return
	var kind := str(record.get("kind", "manual"))
	if kind == "suspend":
		if save_status != null and is_instance_valid(save_status):
			save_status.text = "正在恢复中断存档..."
		NetworkClient.load_suspend(_main._user_name, Callable(self, "_on_save_suspend_load_response"))
		return
	if save_status != null and is_instance_valid(save_status):
		save_status.text = "正在载入 %s..." % _save_option_label(record)
	NetworkClient.load_save(
		_main._user_name,
		kind,
		int(record.get("slot_index", 0)),
		Callable(self, "_on_save_load_response").bind(record)
	)


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


# P0:主菜单存档页"新建存档"按钮 — 手动存档
# 优先选 SaveSlotOption(用户指定)或第一个空 slot,全部占用则覆盖选定 slot
func _find_free_save_slot() -> int:
	if save_slot_option != null and is_instance_valid(save_slot_option):
		var chosen: int = int(save_slot_option.get_selected_id() if save_slot_option.get_selected_id() >= 0 else save_slot_option.selected)
		return clamp(chosen, 0, 2)
	# 没选 slot_option 时找第一个不在 _save_records 的 manual slot
	var used := {}
	for rec in _save_records:
		if str(rec.get("kind", "")) == "manual":
			used[int(rec.get("slot_index", -1))] = true
	for i in range(3):
		if not used.has(i):
			return i
	return 0


func _current_save_mainline_id() -> String:
	# 主线模式优先;无主线时用当前 game.name(FE8 风格的 mainline:chapter_N:battle_N:seed)
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
				# battle_id 数字作为 chapter 索引
				return int(parts[2]) if parts[2].is_valid_int() else 0
	return 0


func _on_save_new_pressed() -> void:
	if _main._user_name == "":
		_main._update_status("请先在设置填写玩家昵称")
		return
	if save_new_btn != null and is_instance_valid(save_new_btn):
		save_new_btn.disabled = true
	var mid: String = _current_save_mainline_id()
	if mid == "":
		_main._update_status("无法存档:当前没有关联主线/对局")
		if save_new_btn != null and is_instance_valid(save_new_btn):
			save_new_btn.disabled = false
		return
	var slot: int = _find_free_save_slot()
	var chidx: int = _current_save_chapter_index()
	var label: String = ("第 %d 章 - 手动" % (chidx + 1)) if _main._active_mainline_id != "" else ("自由战 #%d - 手动" % _main._game_id)
	if save_status != null and is_instance_valid(save_status):
		save_status.text = "正在写入存档 %d ..." % (slot + 1)
	NetworkClient.save_manual(
		_main._user_name,
		slot,
		mid,
		chidx,
		label,
		Callable(self, "_on_save_new_response")
	)


func _on_save_new_response(body: Variant, code: int) -> void:
	if save_new_btn != null and is_instance_valid(save_new_btn):
		save_new_btn.disabled = false
	if code < 200 or code >= 300:
		var msg: String = "存档失败"
		if body is Dictionary and body.has("detail"):
			msg = "存档失败: %s" % str(body.get("detail"))
		_main._update_status(msg)
		if save_status != null and is_instance_valid(save_status):
			save_status.text = msg
		return
	if save_status != null and is_instance_valid(save_status):
		save_status.text = "已保存到存档"
	_main._update_status("💾 已写入手动存档")
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
	NetworkClient.rejoin_game_by_name(game_id, _main._user_name, Callable(_main, "_on_ml_slot_resume_response").bind(game_id))


func _on_save_delete_pressed() -> void:
	var record := _selected_save_record()
	if record.is_empty():
		return
	if str(record.get("kind", "")) == "suspend":
		if save_status != null and is_instance_valid(save_status):
			save_status.text = "中断存档暂不支持手动删除"
		return
	if save_status != null and is_instance_valid(save_status):
		save_status.text = "删除 %s..." % _save_option_label(record)
	NetworkClient.erase_save(
		_main._user_name,
		str(record.get("kind", "manual")),
		int(record.get("slot_index", 0)),
		Callable(self, "_on_save_delete_response").bind(record)
	)


func _on_save_delete_response(_body: Variant, code: int, record: Dictionary) -> void:
	if code >= 200 and code < 300:
		if save_status != null and is_instance_valid(save_status):
			save_status.text = "已删除 %s" % _save_option_label(record)
		_refresh_saves()
	else:
		if save_status != null and is_instance_valid(save_status):
			save_status.text = "删除失败"


func _on_save_back_pressed() -> void:
	_main._show_view("menu")


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


func _selected_save_record() -> Dictionary:
	var idx := _selected_save_id - 1
	if idx < 0 or idx >= _save_records.size():
		return {}
	var record: Variant = _save_records[idx]
	return record if record is Dictionary else {}


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