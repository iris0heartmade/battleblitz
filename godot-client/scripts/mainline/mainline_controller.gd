extends Control
## mainline_controller.gd — 主线视图控制器(P2 从 main.gd 抽离, Batch A)。
## 挂在场景 MainlineView 节点上,自管面板内部逻辑;view 可见性仍由 main._show_view 控制。
## 包含:章节列表 + 存档格 UI + 章节详情 + 指挥官 UI + page 切换。
## Batch B 后续接管 prepare 流程 + start/advance/abandon 流。
## 对外接口:
##   open()                  — main 切到 mainline view 后调用:初始化 + 拉取列表
##   var _main: Node         — main 注入;跨域访问 _user_name / _active_mainline_id
##                              / _selected_mainline_id / _show_view / _update_status
##                              / saves_view.<helpers> / _setup_lobby_commander_options
## 节点路径相对 MainlineView: $MLFrame/<X>(原 main.gd 用 $MainlineView/MLFrame/<X>)

const MenuTheme = preload("res://scripts/ui/menu_theme.gd")

var _main: Node = null

@onready var ml_title: Label = $MLFrame/MLTitle
@onready var ml_list_container: VBoxContainer = $MLFrame/MLListContainer
@onready var ml_commander_status: Label = $MLFrame/CommanderStatus
@onready var ml_commander_option: OptionButton = $MLFrame/CommanderOption
@onready var ml_apply_commander_btn: Button = $MLFrame/ApplyCommanderBtn
@onready var ml_back_btn: Button = $MLFrame/MLBackBtn
@onready var ml_abandon_btn: Button = $MLFrame/MLAbandonBtn
@onready var ml_slots_container: VBoxContainer = $MLFrame/MLSlotsContainer
@onready var ml_prep_summary: RichTextLabel = $MLFrame/MLPrepSummary
@onready var ml_prep_tabs: HBoxContainer = $MLFrame/MLPrepTabs
@onready var ml_prep_content: RichTextLabel = $MLFrame/MLPrepContent
@onready var ml_prep_start_btn: Button = $MLFrame/MLPrepStartBtn
@onready var ml_prep_complete_btn: Button = $MLFrame/MLPrepCompleteBtn
@onready var ml_prep_refresh_btn: Button = $MLFrame/MLPrepRefreshBtn
@onready var ml_prep_action_btn: Button = $MLFrame/MLPrepActionBtn
@onready var ml_prep_alt_action_btn: Button = $MLFrame/MLPrepAltActionBtn
@onready var ml_prep_hero_select: OptionButton = $MLFrame/MLPrepSelectorRow/MLPrepHeroSelect
@onready var ml_prep_equipment_select: OptionButton = $MLFrame/MLPrepSelectorRow/MLPrepEquipmentSelect
@onready var ml_prep_merc_unit_select: OptionButton = $MLFrame/MLPrepSelectorRow/MLPrepMercUnitSelect
@onready var ml_prep_merc_stat_select: OptionButton = $MLFrame/MLPrepSelectorRow/MLPrepMercStatSelect
@onready var ml_prep_shop_select: OptionButton = $MLFrame/MLPrepSelectorRow/MLPrepShopSelect
@onready var ml_prep_heroes_tab_btn: Button = $MLFrame/MLPrepTabs/HeroesTabBtn
@onready var ml_prep_roster_tab_btn: Button = $MLFrame/MLPrepTabs/RosterTabBtn
@onready var ml_prep_equipment_tab_btn: Button = $MLFrame/MLPrepTabs/EquipmentTabBtn
@onready var ml_prep_mercenary_tab_btn: Button = $MLFrame/MLPrepTabs/MercenaryTabBtn
@onready var ml_prep_shop_tab_btn: Button = $MLFrame/MLPrepTabs/ShopTabBtn
@onready var ml_prep_saves_tab_btn: Button = $MLFrame/MLPrepTabs/SavesTabBtn

var _ml_slot_records: Array = []
var _mainline_page: String = "chapter_list"
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
var _mainline_commander_ids: Array[String] = [""]


func _ready() -> void:
	# Batch A: commander apply 由组件接(bind 内的函数都在 self)
	if ml_apply_commander_btn != null and is_instance_valid(ml_apply_commander_btn):
		ml_apply_commander_btn.pressed.connect(_on_apply_mainline_commander_pressed)
	# P2: GBA 火纹主题(原 main._apply_gba_theme 按钮列表里的 ml_* 按钮,随组件搬来)
	var theme_btns := [ml_back_btn, ml_abandon_btn, ml_apply_commander_btn,
		ml_prep_start_btn, ml_prep_complete_btn, ml_prep_refresh_btn,
		ml_prep_action_btn, ml_prep_alt_action_btn,
		ml_prep_heroes_tab_btn, ml_prep_roster_tab_btn, ml_prep_equipment_tab_btn,
		ml_prep_mercenary_tab_btn, ml_prep_shop_tab_btn, ml_prep_saves_tab_btn]
	for btn in theme_btns:
		if btn != null and is_instance_valid(btn):
			MenuTheme.apply_button_theme(btn, MenuTheme.FS_BTN)


func open() -> void:
	_main._show_view("mainline")
	_set_mainline_page("chapter_list")
	ml_title.text = "主线章节 · 加载中..."
	_main._mainline_prepare_payload = {}
	_main._mainline_shop_payload = {}
	_main._mainline_mercenary_payload = {}
	_main._mainline_prepare_tab = "heroes"
	_main._selected_prepare_hero_id = ""
	_main._selected_prepare_equipment_id = ""
	_main._selected_prepare_shop_item_id = ""
	_main._selected_prepare_merc_unit_type = ""
	_main._selected_prepare_merc_stat = ""
	_render_mainline_prepare()
	# VBoxContainer 没有 text 属性,清空用 queue_free 子节点
	for child in ml_list_container.get_children():
		child.queue_free()
	_setup_mainline_commander_options()
	if ml_commander_status != null and is_instance_valid(ml_commander_status):
		ml_commander_status.text = "指挥官: 正在加载..."
	if _main._hero_speaker_map.is_empty():
		NetworkClient.list_heroes(Callable(_main, "_on_heroes_response"))
	NetworkClient.get_unlocked_commanders(_main._user_name, Callable(self, "_on_commanders_response"))
	NetworkClient.list_mainlines(Callable(self, "_on_ml_list_response"), _main._user_name)
	if ml_slots_container != null and is_instance_valid(ml_slots_container):
		for child in ml_slots_container.get_children():
			child.queue_free()
		var loading_lbl := Label.new()
		loading_lbl.text = "存档格: 加载中..."
		loading_lbl.modulate = Color(0.65, 0.6, 0.45)
		ml_slots_container.add_child(loading_lbl)
	NetworkClient.list_saves(_main._user_name, Callable(self, "_on_ml_slots_response"))


func _set_node_visible(node: Node, value: bool) -> void:
	if node != null and is_instance_valid(node) and node is CanvasItem:
		(node as CanvasItem).visible = value


func _set_mainline_page(page: String) -> void:
	_main._mainline_page = page
	var showing_prepare := page == "prepare"
	_set_node_visible(ml_slots_container, not showing_prepare)
	_set_node_visible(ml_list_container, not showing_prepare)
	_set_node_visible(ml_commander_status, not showing_prepare)
	_set_node_visible(ml_commander_option, not showing_prepare)
	_set_node_visible(ml_apply_commander_btn, not showing_prepare)
	_set_node_visible(ml_prep_summary, showing_prepare)
	_set_node_visible(ml_prep_tabs, showing_prepare)
	_set_node_visible(ml_prep_content, showing_prepare)
	_set_node_visible(ml_prep_start_btn, showing_prepare)
	_set_node_visible(ml_prep_refresh_btn, showing_prepare)
	_set_node_visible(ml_prep_action_btn, showing_prepare)
	_set_node_visible(ml_prep_alt_action_btn, showing_prepare)
	if ml_prep_hero_select != null and is_instance_valid(ml_prep_hero_select):
		_set_node_visible(ml_prep_hero_select.get_parent(), showing_prepare)


func _on_ml_slots_response(body: Variant, _code: int = 0) -> void:
	# 主线存档格:取该用户 mainline save slot,最多 3 格(web MAINLINE_SLOT_COUNT=3)。
	# P2:save helper 权威在 saves_view;saves_view 为 null 时降级到空 list(异常防御)。
	var saves_view: Node = _main.saves_view
	var games: Array = (saves_view._save_records_from_response(body) if saves_view != null and is_instance_valid(saves_view) else [])
	_main._ml_slot_records = []
	for g in games:
		if not (g is Dictionary): continue
		if str(g.get("kind", "")) == "suspend": continue
		if str(g.get("mainline_id", "")) == "": continue
		_main._ml_slot_records.append(g)
		if _main._ml_slot_records.size() >= 3: break
	_render_mainline_slots()


func _render_mainline_slots() -> void:
	if ml_slots_container == null or not is_instance_valid(ml_slots_container):
		return
	for child in ml_slots_container.get_children():
		child.queue_free()
	var saves_view: Node = _main.saves_view
	var shown: int = _main._ml_slot_records.size()
	for i in range(3):
		if i < shown:
			var g: Dictionary = _main._ml_slot_records[i]
			var save_id: int = int(g.get("id", 0))
			var disp: String = saves_view._format_save_name(str(g.get("label", "")))
			var chapter_index: int = int(g.get("chapter_index", 0)) + 1
			var row := HBoxContainer.new()
			row.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			var lbl := Label.new()
			lbl.text = "💾 %s · 第 %d 章 · #%d" % [disp, chapter_index, save_id]
			lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			row.add_child(lbl)
			var resume_btn := Button.new()
			resume_btn.text = "▶ 继续"
			resume_btn.pressed.connect(_on_ml_slot_resume.bind(g))
			row.add_child(resume_btn)
			var del_btn := Button.new()
			del_btn.text = "🗑"
			del_btn.pressed.connect(_on_ml_slot_delete.bind(g))
			row.add_child(del_btn)
			ml_slots_container.add_child(row)
		else:
			var empty := Label.new()
			empty.text = "▢ 空存档 %d" % (i + 1)
			empty.modulate = Color(0.5, 0.46, 0.35)
			ml_slots_container.add_child(empty)


func _on_ml_slot_resume(record: Dictionary) -> void:
	if record.is_empty(): return
	var saves_view: Node = _main.saves_view
	var label: String = saves_view._save_option_label(record)
	_main._show_view("connecting")
	_main.connecting_label.text = "正在载入 %s..." % label
	NetworkClient.load_save(
		_main._user_name,
		str(record.get("kind", "manual")),
		int(record.get("slot_index", 0)),
		Callable(self, "_on_ml_slot_loaded_response").bind(record)
	)


func _on_ml_slot_loaded_response(body: Variant, code: int, record: Dictionary) -> void:
	if code < 200 or code >= 300 or not (body is Dictionary):
		_main._update_status("主线存档载入失败")
		_main._show_view("mainline")
		return
	_main._active_mainline_id = str(body.get("mainline_id", record.get("mainline_id", "")))
	_main._selected_mainline_id = _main._active_mainline_id if _main._active_mainline_id != "" else _main._selected_mainline_id
	UserSettings.set_value("session.v1.mainline_id", _main._active_mainline_id)
	var saves_view: Node = _main.saves_view
	_main._update_status("已载入 %s" % saves_view._save_option_label(record))
	_main._show_view("mainline")
	open()


func _on_ml_slot_delete(record: Dictionary) -> void:
	if record.is_empty(): return
	var saves_view: Node = _main.saves_view
	_main._update_status("删除 %s..." % saves_view._save_option_label(record))
	NetworkClient.erase_save(
		_main._user_name,
		str(record.get("kind", "manual")),
		int(record.get("slot_index", 0)),
		Callable(self, "_on_ml_slot_delete_response").bind(record)
	)


func _on_ml_slot_delete_response(_body: Variant, code: int, record: Dictionary) -> void:
	if code >= 200 and code < 300:
		var saves_view: Node = _main.saves_view
		_main._update_status("已删除 %s" % saves_view._save_option_label(record))
		NetworkClient.list_saves(_main._user_name, Callable(self, "_on_ml_slots_response"))
	else:
		_main._update_status("删除主线存档失败")


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
		var id: String = str(ml.get("id", ""))
		if id == "": continue
		if _main._selected_mainline_id == "":
			_main._selected_mainline_id = id
		var title: String = str(ml.get("title", "?"))
		var battles: int = int(ml.get("battle_count", ml.get("total_battles", 0)))
		var desc: String = str(ml.get("synopsis", ml.get("description", "")))
		var btn := Button.new()
		btn.text = "%s · %d 场战斗" % [title, battles]
		btn.tooltip_text = desc
		btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		btn.pressed.connect(_on_ml_card_pressed.bind(id))
		ml_list_container.add_child(btn)


func _on_ml_card_pressed(mainline_id: String) -> void:
	_main._selected_mainline_id = mainline_id
	# 拉详情 → show_dialog(pre-battle dialogue)→ start
	NetworkClient.get_mainline_detail(mainline_id, Callable(self, "_on_ml_detail_response").bind(mainline_id))


func _on_ml_detail_response(body: Variant, _code: int = 0, mainline_id: String = "") -> void:
	if not (body is Dictionary):
		_main._update_status("加载章节详情失败")
		return
	_main._mainline_auto_retry_pending = false
	var battles: Array = body.get("battles", []) if body.has("battles") else []
	var dialogue: Variant = body.get("dialogue", null)
	# 有 pre-battle 对话 → 播放
	if dialogue != null:
		_main._play_dialogue_scenes(dialogue)
	_main._update_status("主线章节 %s: 加载战前准备..." % mainline_id)
	NetworkClient.get_mainline_prepare(mainline_id, _main._user_name, Callable(self, "_on_mainline_prepare_response").bind(mainline_id))


# ── Commander UI ────────────────────────────────────────────────

func _setup_mainline_commander_options(unlocked: Array = [], current: String = "") -> void:
	_main._mainline_commander_ids = [""]
	if ml_commander_option != null and is_instance_valid(ml_commander_option):
		ml_commander_option.clear()
		ml_commander_option.add_item("不选择指挥官")
	for item in unlocked:
		var commander_id := str(item)
		if commander_id == "" or _main._mainline_commander_ids.has(commander_id):
			continue
		_main._mainline_commander_ids.append(commander_id)
		if ml_commander_option != null and is_instance_valid(ml_commander_option):
			ml_commander_option.add_item(_commander_label(commander_id))
	var selected_index: int = _main._mainline_commander_ids.find(current)
	if selected_index < 0:
		selected_index = 0
	if ml_commander_option != null and is_instance_valid(ml_commander_option):
		ml_commander_option.select(selected_index)
		ml_commander_option.disabled = _main._mainline_commander_ids.size() <= 1


func _commander_label(commander_id: String) -> String:
	match commander_id:
		"yun":
			return "云"
		"anna":
			return "安娜"
		_:
			return commander_id


func _selected_mainline_commander() -> String:
	if ml_commander_option == null or not is_instance_valid(ml_commander_option):
		return ""
	var index := ml_commander_option.selected
	if index < 0 or index >= _main._mainline_commander_ids.size():
		return ""
	return _main._mainline_commander_ids[index]


func _on_commanders_response(body: Variant, code: int = 0) -> void:
	if code < 200 or code >= 300 or not (body is Dictionary):
		if ml_commander_status != null and is_instance_valid(ml_commander_status):
			ml_commander_status.text = "指挥官: 暂不可用"
		_setup_mainline_commander_options()
		_main._setup_lobby_commander_options()
		return
	var unlocked: Array = body.get("unlocked_commanders", []) if body.get("unlocked_commanders", []) is Array else []
	var mainline_choices: Dictionary = body.get("mainline_commanders", {}) if body.get("mainline_commanders", {}) is Dictionary else {}
	var current := str(mainline_choices.get(_main._selected_mainline_id, ""))
	_setup_mainline_commander_options(unlocked, current)
	_main._setup_lobby_commander_options(unlocked)
	if ml_commander_status != null and is_instance_valid(ml_commander_status):
		ml_commander_status.text = "指挥官: %s" % (_commander_label(current) if current != "" else "未选择")


func _on_apply_mainline_commander_pressed() -> void:
	if _main._selected_mainline_id == "":
		if ml_commander_status != null and is_instance_valid(ml_commander_status):
			ml_commander_status.text = "指挥官: 请先选择章节"
		return
	var commander_id := _selected_mainline_commander()
	if ml_commander_status != null and is_instance_valid(ml_commander_status):
		ml_commander_status.text = "指挥官: 正在应用..."
	NetworkClient.select_mainline_commander(_main._selected_mainline_id, _main._user_name, commander_id, Callable(self, "_on_select_mainline_commander_response"))


func _on_select_mainline_commander_response(body: Variant, code: int = 0) -> void:
	if code < 200 or code >= 300 or not (body is Dictionary):
		var msg := "Commander: apply failed"
		if body is Dictionary:
			msg = "Commander: %s" % str(body.get("detail", body.get("message", "apply failed")))
		if ml_commander_status != null and is_instance_valid(ml_commander_status):
			ml_commander_status.text = msg
		return
	var commander_id := str(body.get("commander_id", ""))
	_setup_mainline_commander_options(_main._mainline_commander_ids.slice(1), commander_id)
	if ml_commander_status != null and is_instance_valid(ml_commander_status):
		ml_commander_status.text = "指挥官: %s" % (_commander_label(commander_id) if commander_id != "" else "未选择")


# ── Stubs for Batch B (kept for compile + batch B to fill in) ──

func _render_mainline_prepare() -> void:
	pass