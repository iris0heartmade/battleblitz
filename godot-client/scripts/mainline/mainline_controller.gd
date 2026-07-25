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
const StatusBadge = preload("res://scripts/ui/_components/status_badge.gd")
const SectionHeader = preload("res://scripts/ui/_components/section_header.gd")

var _main: Node = null

@onready var ml_title: Label = $MLFrame/MLTitle
@onready var ml_list_container: VBoxContainer = $MLFrame/MLListContainer
@onready var ml_commander_status: Label = $MLFrame/CommanderStatus
@onready var ml_commander_option: OptionButton = $MLFrame/CommanderOption
@onready var ml_apply_commander_btn: Button = $MLFrame/ApplyCommanderBtn
@onready var ml_back_btn: Button = $MLFrame/MLBackBtn
@onready var ml_abandon_btn: Button = $MLFrame/MLAbandonBtn
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
@onready var ml_right_placeholder: Panel = $MLFrame/MLRightPlaceholder
@onready var ml_rp_hint: Label = $MLFrame/MLRightPlaceholder/MLRPHint
@onready var ml_prep_heroes_tab_btn: Button = $MLFrame/MLPrepTabs/HeroesTabBtn
@onready var ml_prep_roster_tab_btn: Button = $MLFrame/MLPrepTabs/RosterTabBtn
@onready var ml_prep_equipment_tab_btn: Button = $MLFrame/MLPrepTabs/EquipmentTabBtn
@onready var ml_prep_mercenary_tab_btn: Button = $MLFrame/MLPrepTabs/MercenaryTabBtn
@onready var ml_prep_shop_tab_btn: Button = $MLFrame/MLPrepTabs/ShopTabBtn
@onready var ml_prep_saves_tab_btn: Button = $MLFrame/MLPrepTabs/SavesTabBtn

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
# T:#16 — 章节 cleared 标注(join /saves → 算 mainline_id → "✓ 已通关" badge)
var _mainline_list_cache: Array = []  # 缓存 /mainlines 响应,等 /saves 回来后统一渲染
var _cleared_mainline_ids: Dictionary = {}  # { mainline_id: true }


func _ready() -> void:
	# Batch A: commander apply 由组件接(bind 内的函数都在 self)
	if ml_apply_commander_btn != null and is_instance_valid(ml_apply_commander_btn):
		ml_apply_commander_btn.pressed.connect(_on_apply_mainline_commander_pressed)
	if ml_back_btn != null and is_instance_valid(ml_back_btn):
		ml_back_btn.pressed.connect(_on_ml_back_pressed)
	if ml_abandon_btn != null and is_instance_valid(ml_abandon_btn):
		ml_abandon_btn.pressed.connect(_on_ml_abandon_pressed)
	if ml_prep_start_btn != null and is_instance_valid(ml_prep_start_btn):
		ml_prep_start_btn.pressed.connect(_on_prepare_start_pressed)
	if ml_prep_complete_btn != null and is_instance_valid(ml_prep_complete_btn):
		ml_prep_complete_btn.pressed.connect(_on_prepare_complete_pressed)
	if ml_prep_refresh_btn != null and is_instance_valid(ml_prep_refresh_btn):
		ml_prep_refresh_btn.pressed.connect(_on_prepare_refresh_pressed)
	if ml_prep_action_btn != null and is_instance_valid(ml_prep_action_btn):
		ml_prep_action_btn.pressed.connect(_on_prepare_primary_action_pressed)
	if ml_prep_alt_action_btn != null and is_instance_valid(ml_prep_alt_action_btn):
		ml_prep_alt_action_btn.pressed.connect(_on_prepare_secondary_action_pressed)
	var prep_tabs := {
		ml_prep_heroes_tab_btn: "heroes",
		ml_prep_roster_tab_btn: "roster",
		ml_prep_equipment_tab_btn: "equipment",
		ml_prep_mercenary_tab_btn: "mercenary",
		ml_prep_shop_tab_btn: "shop",
		ml_prep_saves_tab_btn: "saves",
	}
	for tab_btn in prep_tabs:
		if tab_btn != null and is_instance_valid(tab_btn):
			tab_btn.pressed.connect(_on_prepare_tab_pressed.bind(prep_tabs[tab_btn]))
	if ml_prep_hero_select != null and is_instance_valid(ml_prep_hero_select):
		ml_prep_hero_select.item_selected.connect(_on_prepare_hero_selected)
	if ml_prep_equipment_select != null and is_instance_valid(ml_prep_equipment_select):
		ml_prep_equipment_select.item_selected.connect(_on_prepare_equipment_selected)
	if ml_prep_merc_unit_select != null and is_instance_valid(ml_prep_merc_unit_select):
		ml_prep_merc_unit_select.item_selected.connect(_on_prepare_merc_unit_selected)
	if ml_prep_merc_stat_select != null and is_instance_valid(ml_prep_merc_stat_select):
		ml_prep_merc_stat_select.item_selected.connect(_on_prepare_merc_stat_selected)
	if ml_prep_shop_select != null and is_instance_valid(ml_prep_shop_select):
		ml_prep_shop_select.item_selected.connect(_on_prepare_shop_item_selected)
	# P2: GBA 火纹主题(原 main._apply_gba_theme 按钮列表里的 ml_* 按钮,随组件搬来)
	var theme_btns := [ml_back_btn, ml_abandon_btn, ml_apply_commander_btn,
		ml_prep_start_btn, ml_prep_complete_btn, ml_prep_refresh_btn,
		ml_prep_action_btn, ml_prep_alt_action_btn,
		ml_prep_heroes_tab_btn, ml_prep_roster_tab_btn, ml_prep_equipment_tab_btn,
		ml_prep_mercenary_tab_btn, ml_prep_shop_tab_btn, ml_prep_saves_tab_btn]
	for btn in theme_btns:
		if btn != null and is_instance_valid(btn):
			MenuTheme.apply_button_theme(btn, MenuTheme.FS_BTN)
	# T:V4 — 右半屏占位卡主题:深绿底 + 烫金边 + placeholder 文字 PLACEHOLDER 色
	if ml_right_placeholder != null and is_instance_valid(ml_right_placeholder):
		MenuTheme.apply_panel_theme(ml_right_placeholder, MenuTheme.C_BG_PANEL)
	if ml_rp_hint != null and is_instance_valid(ml_rp_hint):
		ml_rp_hint.add_theme_color_override("font_color", MenuTheme.C_PLACEHOLDER)
	# T:V4 — 主操作分组:
	# - ✅ 准备好了 + 选定指挥官 走 PRIMARY(金底烫金亮边)— 关键确认操作
	# - 放弃主线 走 SECONDARY(蓝底)— 默认次要按钮
	if ml_prep_complete_btn != null and is_instance_valid(ml_prep_complete_btn):
		MenuTheme.apply_primary_button_theme(ml_prep_complete_btn, MenuTheme.FS_BTN)
	if ml_apply_commander_btn != null and is_instance_valid(ml_apply_commander_btn):
		MenuTheme.apply_primary_button_theme(ml_apply_commander_btn, MenuTheme.FS_BODY_SM)
	if ml_abandon_btn != null and is_instance_valid(ml_abandon_btn):
		MenuTheme.apply_secondary_button_theme(ml_abandon_btn, MenuTheme.FS_BODY_SM)


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
	# T:#16 — 并行拉 /saves 用于 cleared 标注(不阻塞主流程)
	NetworkClient.list_saves(_main._user_name, Callable(self, "_on_ml_saves_for_cleared"))


func _set_node_visible(node: Node, value: bool) -> void:
	if node != null and is_instance_valid(node) and node is CanvasItem:
		(node as CanvasItem).visible = value


# #16 — 主线存档格 UI 已搬到 saves_view 三槽卡片;saves tab 改为跳转存档页。
func _set_mainline_page(page: String) -> void:
	_main._mainline_page = page
	var showing_prepare := page == "prepare"
	_set_node_visible(ml_list_container, not showing_prepare)
	_set_node_visible(ml_commander_status, not showing_prepare)
	_set_node_visible(ml_commander_option, not showing_prepare)
	_set_node_visible(ml_apply_commander_btn, not showing_prepare)
	# T:V4 — 章节列表右侧 placeholder 卡,prepare 模式被 prep 控件覆盖
	_set_node_visible(ml_right_placeholder, not showing_prepare)
	_set_node_visible(ml_prep_summary, showing_prepare)
	_set_node_visible(ml_prep_tabs, showing_prepare)
	_set_node_visible(ml_prep_content, showing_prepare)
	_set_node_visible(ml_prep_start_btn, showing_prepare)
	# T:#17 — ml_prep_complete_btn (✅ 准备好了) 在 chapter_list 也常驻可见,
	# 让玩家在选章节后能立刻点"准备好了"进对战。刷新整备 / 开始战斗
	# 等 prepare 模式专属控件才在 chapter_list 隐藏。
	_set_node_visible(ml_prep_refresh_btn, showing_prepare)
	_set_node_visible(ml_prep_action_btn, showing_prepare)
	_set_node_visible(ml_prep_alt_action_btn, showing_prepare)
	if ml_prep_hero_select != null and is_instance_valid(ml_prep_hero_select):
		_set_node_visible(ml_prep_hero_select.get_parent(), showing_prepare)


func _on_ml_list_response(body: Variant, _code: int = 0) -> void:
	ml_title.text = "📖 主线章节"
	# T:#16 — 缓存列表响应,等 cleared 集合就绪后重渲
	_mainline_list_cache = (body as Array).duplicate(true) if body is Array else []
	_render_mainline_list()


# T:#16 — 章节 cleared 集合构建(join /saves 后的 manual_slots + auto_slot)
# 规则:有任意 save 记录 chapter_index >= mainline.battle_count - 1(0-based)即视为通关
func _on_ml_saves_for_cleared(body: Variant, _code: int = 0) -> void:
	_cleared_mainline_ids = {}
	if not (body is Dictionary):
		_render_mainline_list()
		return
	# 1) 收集所有 save 的 (mainline_id → max chapter_index) — 这里只关心是否通关,简化用 set
	#    如果有 manual slot 推进到 chapter_index >= battle_count - 1 → cleared
	#    如果 auto slot 标 "结束"(label 以 "-结束" 结尾) → cleared
	var auto_slot: Variant = body.get("auto_slot", null)
	if auto_slot is Dictionary:
		var mid: String = str((auto_slot as Dictionary).get("mainline_id", ""))
		var label: String = str((auto_slot as Dictionary).get("label", ""))
		if mid != "" and label.ends_with("-结束"):
			_cleared_mainline_ids[mid] = true
	var manual_slots: Array = body.get("manual_slots", []) if body.get("manual_slots", []) is Array else []
	for slot in manual_slots:
		if not (slot is Dictionary): continue
		var mid2: String = str(slot.get("mainline_id", ""))
		if mid2 == "": continue
		# manual slot 通关判定:chapter_index == battle_count - 1 (即已完成最后一场)
		# 严格判定需要 battle_count,从 mainline_list_cache 反查
		var chidx: int = int(slot.get("chapter_index", 0))
		var battle_count: int = _battle_count_for_mainline(mid2)
		if battle_count > 0 and chidx >= battle_count - 1:
			_cleared_mainline_ids[mid2] = true
	_render_mainline_list()


func _battle_count_for_mainline(mainline_id: String) -> int:
	for ml in _mainline_list_cache:
		if not (ml is Dictionary): continue
		if str(ml.get("id", "")) == mainline_id:
			return int(ml.get("battle_count", ml.get("total_battles", 0)))
	return 0


func _render_mainline_list() -> void:
	if ml_list_container == null or not is_instance_valid(ml_list_container):
		return
	for child in ml_list_container.get_children():
		child.queue_free()
	if _mainline_list_cache.is_empty():
		var empty := Label.new()
		empty.text = "(暂无可用章节)"
		empty.add_theme_color_override("font_color", Color(0.65, 0.6, 0.45))
		ml_list_container.add_child(empty)
		return
	for ml in _mainline_list_cache:
		if not ml is Dictionary: continue
		var id: String = str(ml.get("id", ""))
		if id == "": continue
		if _main._selected_mainline_id == "":
			_main._selected_mainline_id = id
		var title: String = str(ml.get("title", "?"))
		var battles: int = int(ml.get("battle_count", ml.get("total_battles", 0)))
		var desc: String = str(ml.get("synopsis", ml.get("description", "")))
		var cleared := _cleared_mainline_ids.has(id)
		var btn := Button.new()
		# T:#16 — cleared 标注 + 金色微调(不影响 disabled,可重玩)
		btn.text = ("✓  %s · %d 场战斗  [已通关]" % [title, battles]) if cleared else ("%s · %d 场战斗" % [title, battles])
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


# ── _on_mainline_prepare_response ────────────────────────────────────────

func _on_mainline_prepare_response(body: Variant, code: int = 0, mainline_id: String = "") -> void:
	if code < 200 or code >= 300 or not (body is Dictionary):
		var msg := "战前准备加载失败"
		if body is Dictionary:
			msg = "战前准备加载失败: %s" % str(body.get("detail", body.get("message", msg)))
		_main._update_status(msg)
		return
	_main._mainline_prepare_payload = (body as Dictionary).duplicate(true)
	var heroes: Array = body.get("heroes", []) if body.get("heroes", []) is Array else []
	var roster_units: Array = body.get("roster_units", []) if body.get("roster_units", []) is Array else []
	var inventory: Dictionary = body.get("inventory", {}) if body.get("inventory", {}) is Dictionary else {}
	var battle_index: int = int(body.get("battle_index", 0)) + 1
	var total_battles: int = int(body.get("total_battles", 1))
	_main._update_status("战前准备: 第 %d/%d 战 · 英雄 %d · 可部署 %d · 金币 %d" % [
		battle_index, total_battles, heroes.size(), roster_units.size(), int(inventory.get("gold", 0))
	])
	if _main._selected_prepare_hero_id == "" and not heroes.is_empty() and heroes[0] is Dictionary:
		_main._selected_prepare_hero_id = str((heroes[0] as Dictionary).get("hero_id", ""))
	_main._mainline_prepare_tab = "heroes"
	_set_mainline_page("prepare")
	_render_mainline_prepare()




# ── _on_prepare_tab_pressed ────────────────────────────────────────

func _on_prepare_tab_pressed(tab: String) -> void:
	_main._mainline_prepare_tab = tab
	if tab == "shop" and _main._selected_mainline_id != "" and _main._mainline_shop_payload.is_empty():
		_main._set_prepare_content("[color=#a69a73]正在加载战后商店...[/color]")
		NetworkClient.get_post_battle_shop(_main._selected_mainline_id, _main._user_name, Callable(self, "_on_prepare_shop_response"))
		return
	if tab == "mercenary" and _main._selected_mainline_id != "" and _main._mainline_mercenary_payload.is_empty():
		_main._set_prepare_content("[color=#a69a73]正在加载佣兵配置...[/color]")
		NetworkClient.get_mercenary_config(_main._selected_mainline_id, _main._user_name, Callable(self, "_on_prepare_mercenary_response"))
		return
	_render_mainline_prepare()




# ── _on_prepare_start_pressed ────────────────────────────────────────

func _on_prepare_start_pressed() -> void:
	if _main._selected_mainline_id == "":
		_main._update_status("请先选择主线章节")
		return
	if _main._mainline_prepare_payload.is_empty():
		_main._update_status("请先载入战前整备")
		NetworkClient.get_mainline_prepare(_main._selected_mainline_id, _main._user_name, Callable(self, "_on_mainline_prepare_response").bind(_main._selected_mainline_id))
		return
	_main._update_status("主线: 创建战斗...")
	NetworkClient.start_mainline(_main._selected_mainline_id, _main._user_name, false, [], Callable(self, "_on_mainline_start_response"))




# ── _on_prepare_complete_pressed ────────────────────────────────────────

func _on_prepare_complete_pressed() -> void:
	if _main._selected_mainline_id == "":
		_main._update_status("请先选择主线章节")
		return
	if ml_prep_complete_btn != null and is_instance_valid(ml_prep_complete_btn):
		ml_prep_complete_btn.disabled = true
	_main._update_status("写入自动存档...")
	NetworkClient.complete_mainline_prepare(
		_main._selected_mainline_id,
		_main._user_name,
		[],
		Callable(self, "_on_prepare_complete_response")
	)




# ── _on_prepare_complete_response ────────────────────────────────────────

func _on_prepare_complete_response(body: Variant, code: int) -> void:
	if ml_prep_complete_btn != null and is_instance_valid(ml_prep_complete_btn):
		ml_prep_complete_btn.disabled = false
	if code < 200 or code >= 300:
		var msg: String = "准备完毕写自动存档失败"
		if body is Dictionary and body.has("detail"):
			msg = "准备完毕写自动存档失败: %s" % str(body.get("detail"))
		_main._update_status(msg)
		return
	# P2:显示自动存档 toast
	if body is Dictionary:
		var auto_save: Variant = body.get("auto_save", {})
		if auto_save is Dictionary and auto_save.has("label"):
			_main._show_auto_save_toast("💾 自动存档完毕 ✓  %s" % str(auto_save.get("label", "")), 1800.0)
	_main._update_status("✅ 准备完成,自动存档已写,可以开始战斗")




# ── _on_prepare_refresh_pressed ────────────────────────────────────────

func _on_prepare_refresh_pressed() -> void:
	if _main._selected_mainline_id == "":
		_main._update_status("请先选择主线章节")
		return
	_main._mainline_shop_payload = {}
	_main._mainline_mercenary_payload = {}
	_main._update_status("正在刷新战前整备...")
	NetworkClient.get_mainline_prepare(_main._selected_mainline_id, _main._user_name, Callable(self, "_on_mainline_prepare_response").bind(_main._selected_mainline_id))




# ── _render_mainline_prepare ────────────────────────────────────────

func _render_mainline_prepare() -> void:
	if ml_prep_summary == null or not is_instance_valid(ml_prep_summary):
		return
	_update_prepare_tab_buttons()
	_update_prepare_action_buttons()
	if _main._mainline_prepare_payload.is_empty():
		_sync_prepare_selectors()
		ml_prep_summary.text = "[b]战前整备[/b]\n[color=#a69a73]选择章节后载入英雄、装备、佣兵和商店。[/color]"
		_main._set_prepare_content("[color=#a69a73]尚未载入整备资料。[/color]")
		if ml_prep_start_btn != null and is_instance_valid(ml_prep_start_btn):
			ml_prep_start_btn.disabled = true
		_update_prepare_action_buttons()
		return
	if ml_prep_start_btn != null and is_instance_valid(ml_prep_start_btn):
		ml_prep_start_btn.disabled = false
	var inventory: Dictionary = _main._mainline_prepare_payload.get("inventory", {}) if _main._mainline_prepare_payload.get("inventory", {}) is Dictionary else {}
	var heroes: Array = _main._mainline_prepare_payload.get("heroes", []) if _main._mainline_prepare_payload.get("heroes", []) is Array else []
	var roster_units: Array = _main._mainline_prepare_payload.get("roster_units", []) if _main._mainline_prepare_payload.get("roster_units", []) is Array else []
	var battle_index: int = int(_main._mainline_prepare_payload.get("battle_index", 0)) + 1
	var total_battles: int = int(_main._mainline_prepare_payload.get("total_battles", 1))
	ml_prep_summary.text = "[b]%s[/b]\n第 %d/%d 战 · 英雄 %d · 部队 %d · 金币 %d" % [
		_bb_escape(_main._selected_mainline_id), battle_index, total_battles, heroes.size(), roster_units.size(), int(inventory.get("gold", 0))
	]
	_sync_prepare_selectors()
	match _main._mainline_prepare_tab:
		"roster":
			_main._set_prepare_content(_build_prepare_roster_text(_main._mainline_prepare_payload))
		"equipment":
			_main._set_prepare_content(_build_prepare_equipment_text(_main._mainline_prepare_payload))
		"mercenary":
			_main._set_prepare_content(_build_prepare_mercenary_text())
		"shop":
			_main._set_prepare_content(_build_prepare_shop_text())
		"saves":
			_main._set_prepare_content(_build_prepare_saves_text())
		_:
			_main._set_prepare_content(_build_prepare_heroes_text(_main._mainline_prepare_payload))




# ── _on_prepare_hero_selected ────────────────────────────────────────

func _on_prepare_hero_selected(index: int) -> void:
	if ml_prep_hero_select == null or not is_instance_valid(ml_prep_hero_select):
		return
	if index < 0 or index >= ml_prep_hero_select.item_count:
		return
	_main._selected_prepare_hero_id = str(ml_prep_hero_select.get_item_metadata(index))
	_render_mainline_prepare()




# ── _on_prepare_equipment_selected ────────────────────────────────────────

func _on_prepare_equipment_selected(index: int) -> void:
	if ml_prep_equipment_select == null or not is_instance_valid(ml_prep_equipment_select):
		return
	if index < 0 or index >= ml_prep_equipment_select.item_count:
		return
	_main._selected_prepare_equipment_id = str(ml_prep_equipment_select.get_item_metadata(index))
	_render_mainline_prepare()




# ── _on_prepare_shop_item_selected ────────────────────────────────────────

func _on_prepare_shop_item_selected(index: int) -> void:
	if ml_prep_shop_select == null or not is_instance_valid(ml_prep_shop_select):
		return
	if index < 0 or index >= ml_prep_shop_select.item_count:
		return
	_main._selected_prepare_shop_item_id = str(ml_prep_shop_select.get_item_metadata(index))
	_render_mainline_prepare()




# ── _on_prepare_merc_unit_selected ────────────────────────────────────────

func _on_prepare_merc_unit_selected(index: int) -> void:
	if ml_prep_merc_unit_select == null or not is_instance_valid(ml_prep_merc_unit_select):
		return
	if index < 0 or index >= ml_prep_merc_unit_select.item_count:
		return
	_main._selected_prepare_merc_unit_type = str(ml_prep_merc_unit_select.get_item_metadata(index))
	_render_mainline_prepare()




# ── _on_prepare_merc_stat_selected ────────────────────────────────────────

func _on_prepare_merc_stat_selected(index: int) -> void:
	if ml_prep_merc_stat_select == null or not is_instance_valid(ml_prep_merc_stat_select):
		return
	if index < 0 or index >= ml_prep_merc_stat_select.item_count:
		return
	_main._selected_prepare_merc_stat = str(ml_prep_merc_stat_select.get_item_metadata(index))
	_render_mainline_prepare()




# ── _update_prepare_action_buttons ────────────────────────────────────────

func _update_prepare_action_buttons() -> void:
	if ml_prep_action_btn == null or not is_instance_valid(ml_prep_action_btn):
		return
	if _main._mainline_page != "prepare":
		ml_prep_action_btn.visible = false
		if ml_prep_alt_action_btn != null and is_instance_valid(ml_prep_alt_action_btn):
			ml_prep_alt_action_btn.visible = false
		return
	var has_prepare: bool = not _main._mainline_prepare_payload.is_empty()
	ml_prep_action_btn.visible = true
	if ml_prep_alt_action_btn != null and is_instance_valid(ml_prep_alt_action_btn):
		ml_prep_alt_action_btn.visible = true
	ml_prep_action_btn.disabled = not has_prepare
	if ml_prep_alt_action_btn != null and is_instance_valid(ml_prep_alt_action_btn):
		ml_prep_alt_action_btn.disabled = not has_prepare
	match _main._mainline_prepare_tab:
		"heroes":
			ml_prep_action_btn.text = "转职"
			ml_prep_action_btn.disabled = not _focused_prepare_hero_can_promote()
			if ml_prep_alt_action_btn != null and is_instance_valid(ml_prep_alt_action_btn):
				ml_prep_alt_action_btn.text = "刷新英雄"
				ml_prep_alt_action_btn.disabled = not has_prepare
		"equipment":
			ml_prep_action_btn.text = "装备首件"
			ml_prep_action_btn.text = "装备选中"
			ml_prep_action_btn.disabled = not _selected_equippable_item().has("slot")
			if ml_prep_alt_action_btn != null and is_instance_valid(ml_prep_alt_action_btn):
				ml_prep_alt_action_btn.text = "卸下武器"
				ml_prep_alt_action_btn.disabled = _focused_prepare_hero().is_empty()
		"mercenary":
			ml_prep_action_btn.text = "分配一点"
			ml_prep_action_btn.disabled = not has_prepare
			if ml_prep_alt_action_btn != null and is_instance_valid(ml_prep_alt_action_btn):
				ml_prep_alt_action_btn.text = "刷新佣兵"
				ml_prep_alt_action_btn.disabled = not has_prepare
		"shop":
			ml_prep_action_btn.text = "购买选中"
			ml_prep_action_btn.disabled = _main._mainline_shop_payload.is_empty()
			if ml_prep_alt_action_btn != null and is_instance_valid(ml_prep_alt_action_btn):
				ml_prep_alt_action_btn.text = "刷新商店"
				ml_prep_alt_action_btn.disabled = not has_prepare
		"saves":
			ml_prep_action_btn.text = "刷新存档"
			ml_prep_action_btn.disabled = false
			if ml_prep_alt_action_btn != null and is_instance_valid(ml_prep_alt_action_btn):
				ml_prep_alt_action_btn.text = "返回列表"
				ml_prep_alt_action_btn.disabled = false
		_:
			ml_prep_action_btn.text = "查看部队"
			ml_prep_action_btn.disabled = not has_prepare
			if ml_prep_alt_action_btn != null and is_instance_valid(ml_prep_alt_action_btn):
				ml_prep_alt_action_btn.text = "刷新整备"
				ml_prep_alt_action_btn.disabled = not has_prepare




# ── _on_prepare_primary_action_pressed ────────────────────────────────────────

func _on_prepare_primary_action_pressed() -> void:
	match _main._mainline_prepare_tab:
		"heroes":
			_promote_focused_prepare_hero()
		"equipment":
			var item := _selected_equippable_item()
			if item.has("slot"):
				_equip_focused_prepare_hero(str(item.get("slot", "")), item.get("equipment_id", item.get("item_id", "")))
		"mercenary":
			_allocate_first_mercenary_point()
		"shop":
			_purchase_first_shop_item()
		"saves":
			# #16 — 主线存档已搬到 saves_view 三槽卡片。这里提示玩家切到存档页管理。
			_main._update_status("请到「存档管理」页查看三存档槽")
			_render_mainline_prepare()
		_:
			_main._mainline_prepare_tab = "roster"
			_render_mainline_prepare()




# ── _on_prepare_secondary_action_pressed ────────────────────────────────────────

func _on_prepare_secondary_action_pressed() -> void:
	match _main._mainline_prepare_tab:
		"equipment":
			_equip_focused_prepare_hero("weapon", null)
		"mercenary":
			_main._mainline_mercenary_payload = {}
			_on_prepare_tab_pressed("mercenary")
		"shop":
			_main._mainline_shop_payload = {}
			_on_prepare_tab_pressed("shop")
		"saves":
			# #16 — 切回 heroes tab;saves 管理已搬到 saves_view
			_main._mainline_prepare_tab = "heroes"
			_render_mainline_prepare()
		_:
			_on_prepare_refresh_pressed()




# ── _build_prepare_heroes_text ────────────────────────────────────────

func _build_prepare_heroes_text(payload: Dictionary) -> String:
	var heroes: Array = payload.get("heroes", []) if payload.get("heroes", []) is Array else []
	if heroes.is_empty():
		return "[b]英雄[/b]\n[color=#a69a73]本章暂无英雄资料。[/color]"
	var focused := _focused_prepare_hero()
	var lines: Array[String] = ["[b]英雄详情纸页[/b]  选择英雄后可转职或切到装备页整理仓库。"]
	if not focused.is_empty():
		var equipment: Dictionary = focused.get("equipment", {}) if focused.get("equipment", {}) is Dictionary else {}
		var stats: Dictionary = focused.get("base_stats", {}) if focused.get("base_stats", {}) is Dictionary else {}
		var skills: Array = focused.get("learned_skills", []) if focused.get("learned_skills", []) is Array else []
		var options: Array = focused.get("promotion_options", []) if focused.get("promotion_options", []) is Array else []
		lines.append("\n[color=#f0c75e][b]%s[/b][/color] · %s · Lv.%d · EXP %d" % [
			_bb_escape(str(focused.get("name", focused.get("hero_id", "?")))),
			_bb_escape(str(focused.get("class_id", "?"))),
			int(focused.get("level", 1)),
			int(focused.get("exp", 0)),
		])
		lines.append("HP %s / ATK %s / DEF %s / SPD %s / MATK %s / MDEF %s" % [
			str(stats.get("hp", "-")), str(stats.get("atk", "-")), str(stats.get("def", "-")),
			str(stats.get("spd", "-")), str(stats.get("matk", "-")), str(stats.get("mdef", "-"))
		])
		lines.append("技能: %s" % (_bb_escape(", ".join(skills)) if not skills.is_empty() else "—"))
		lines.append("装备: 武器 %s / 防具 %s / 饰品 %s" % [
			_bb_escape(str(equipment.get("weapon", "未装备"))),
			_bb_escape(str(equipment.get("armor", "未装备"))),
			_bb_escape(str(equipment.get("accessory", "未装备"))),
		])
		lines.append("转职: %s" % (_bb_escape(", ".join(options)) if bool(focused.get("can_promote", false)) and not options.is_empty() else ("已完成" if bool(focused.get("promoted", false)) else "暂不可用")))
	lines.append("\n[b]队伍英雄[/b]")
	for h in heroes:
		if not (h is Dictionary): continue
		var hero: Dictionary = h
		var hero_id := str(hero.get("hero_id", ""))
		var selected := "▶ " if hero_id == _main._selected_prepare_hero_id else "  "
		var promo := "可转职" if bool(hero.get("can_promote", false)) else ("已转职" if bool(hero.get("promoted", false)) else "未满足转职")
		lines.append("%s[b]%s[/b] · %s · Lv.%d · EXP %d · %s" % [
			selected,
			_bb_escape(str(hero.get("name", hero_id))),
			_bb_escape(str(hero.get("class_id", "?"))),
			int(hero.get("level", 1)),
			int(hero.get("exp", 0)),
			_bb_escape(promo),
		])
		var stats: Dictionary = hero.get("base_stats", {}) if hero.get("base_stats", {}) is Dictionary else {}
		if not stats.is_empty():
			lines.append("    HP %s / ATK %s / DEF %s / SPD %s" % [
				str(stats.get("hp", "-")), str(stats.get("atk", "-")), str(stats.get("def", "-")), str(stats.get("spd", "-"))
			])
		var skills: Array = hero.get("learned_skills", []) if hero.get("learned_skills", []) is Array else []
		if not skills.is_empty():
			lines.append("    技能: %s" % _bb_escape(", ".join(skills)))
	return "\n".join(lines)




# ── _build_prepare_roster_text ────────────────────────────────────────

func _build_prepare_roster_text(payload: Dictionary) -> String:
	var roster_units: Array = payload.get("roster_units", []) if payload.get("roster_units", []) is Array else []
	if roster_units.is_empty():
		return "[b]部队[/b]\n[color=#a69a73]暂无可部署单位。[/color]"
	var lines: Array[String] = ["[b]部队[/b]  英雄固定出战，佣兵将在后续支持待命切换。"]
	for i in range(roster_units.size()):
		var u: Variant = roster_units[i]
		if not (u is Dictionary): continue
		var unit: Dictionary = u
		var role := "英雄" if str(unit.get("hero_id", "")) != "" else "佣兵"
		lines.append("%02d. [b]%s[/b] · %s · %s · Lv.%d" % [
			i + 1,
			_bb_escape(str(unit.get("name", unit.get("hero_id", unit.get("class_id", "?"))))),
			_bb_escape(role),
			_bb_escape(str(unit.get("class_id", "?"))),
			int(unit.get("level", 1)),
		])
	return "\n".join(lines)




# ── _build_prepare_equipment_text ────────────────────────────────────────

func _build_prepare_equipment_text(payload: Dictionary) -> String:
	var heroes: Array = payload.get("heroes", []) if payload.get("heroes", []) is Array else []
	var catalog: Array = payload.get("equipment_catalog", []) if payload.get("equipment_catalog", []) is Array else []
	var inventory: Dictionary = payload.get("inventory", {}) if payload.get("inventory", {}) is Dictionary else {}
	var focused: Dictionary = _focused_prepare_hero()
	var lines: Array[String] = ["[b]装备[/b]  当前英雄: %s" % _bb_escape(str(focused.get("name", focused.get("hero_id", "未选择"))))]
	if focused.is_empty():
		lines.append("[color=#a69a73]没有可配置装备的英雄。[/color]")
		return "\n".join(lines)
	var equipment: Dictionary = focused.get("equipment", {}) if focused.get("equipment", {}) is Dictionary else {}
	for slot in ["weapon", "armor", "accessory"]:
		lines.append("%s: %s" % [slot, _bb_escape(str(equipment.get(slot, "未装备")))])
	if catalog.is_empty():
		lines.append("\n[color=#a69a73]暂无装备目录。[/color]")
		return "\n".join(lines)
	lines.append("\n[b]库存[/b]")
	for item in catalog:
		if not (item is Dictionary): continue
		var it: Dictionary = item
		var item_id := str(it.get("equipment_id", it.get("item_id", "")))
		var count := int(inventory.get(item_id, 0))
		var bonuses: Dictionary = it.get("stat_bonuses", {}) if it.get("stat_bonuses", {}) is Dictionary else {}
		var marker := "▶ " if item_id == _main._selected_prepare_equipment_id else "  "
		lines.append("%s%s · %s · x%d · %s" % [
			marker,
			_bb_escape(str(it.get("name", item_id))),
			_bb_escape(str(it.get("slot", "item"))),
			count,
			_bb_escape(str(bonuses)),
		])
	return "\n".join(lines)




# ── _build_prepare_saves_text ────────────────────────────────────────

func _build_prepare_saves_text() -> String:
	# #16 — 主线存档管理已搬到 saves_view 三槽卡片。这里只给提示。
	return "[b]存档[/b]  请到主菜单的「存档管理」页查看三存档槽(各槽独立、可重玩)。"




# ── _build_prepare_shop_text ────────────────────────────────────────

func _build_prepare_shop_text() -> String:
	if _main._mainline_shop_payload.is_empty():
		return "[b]商店[/b]\n[color=#a69a73]切换到商店时会加载商品。[/color]"
	var items: Array = _main._mainline_shop_payload.get("items", []) if _main._mainline_shop_payload.get("items", []) is Array else []
	var lines: Array[String] = ["[b]商店[/b]  金币 %d" % int(_main._mainline_shop_payload.get("gold", 0))]
	if items.is_empty():
		lines.append("[color=#a69a73]本次商店暂无商品。[/color]")
		return "\n".join(lines)
	for item in items:
		if not (item is Dictionary): continue
		var it: Dictionary = item
		var item_id := str(it.get("item_id", ""))
		var marker := "▶ " if item_id == _main._selected_prepare_shop_item_id else "  "
		lines.append("%s%s · %dG · %s" % [
			marker,
			_bb_escape(str(it.get("name", it.get("item_id", "?")))),
			int(it.get("price", 0)),
			_bb_escape(str(it.get("description", ""))),
		])
	return "\n".join(lines)




# ── _build_prepare_mercenary_text ────────────────────────────────────────

func _build_prepare_mercenary_text() -> String:
	if _main._mainline_mercenary_payload.is_empty():
		return "[b]佣兵[/b]\n[color=#a69a73]切换到佣兵时会加载配置。[/color]"
	var balance: Dictionary = _main._mainline_mercenary_payload.get("balance", {}) if _main._mainline_mercenary_payload.get("balance", {}) is Dictionary else {}
	var allocation: Dictionary = _main._mainline_mercenary_payload.get("allocation", {}) if _main._mainline_mercenary_payload.get("allocation", {}) is Dictionary else {}
	var lines: Array[String] = ["[b]佣兵[/b]  可用点数 %d" % int(_main._mainline_mercenary_payload.get("mercenary_points", 0))]
	var allowed: Array = balance.get("allowed_unit_types", []) if balance.get("allowed_unit_types", []) is Array else []
	var upgrades: Dictionary = allocation.get("unit_type_upgrades", {}) if allocation.get("unit_type_upgrades", {}) is Dictionary else {}
	var stat_rules: Dictionary = balance.get("stat_rules", {}) if balance.get("stat_rules", {}) is Dictionary else {}
	lines.append("可用兵种: %s" % _bb_escape(", ".join(allowed)))
	for unit_type in allowed:
		var per_unit: Dictionary = upgrades.get(str(unit_type), {}) if upgrades.get(str(unit_type), {}) is Dictionary else {}
		var marker := "▶ " if str(unit_type) == _main._selected_prepare_merc_unit_type else "  "
		lines.append("%s%s · %s" % [marker, _bb_escape(str(unit_type)), _bb_escape(str(per_unit))])
	if not stat_rules.is_empty():
		lines.append("选中属性: %s" % (_bb_escape(_main._selected_prepare_merc_stat.to_upper()) if _main._selected_prepare_merc_stat != "" else "—"))
		lines.append("规则: %s" % _bb_escape(str(stat_rules)))
	return "\n".join(lines)




# ── _on_prepare_shop_response ────────────────────────────────────────

func _on_prepare_shop_response(body: Variant, code: int = 0) -> void:
	if code < 200 or code >= 300 or not (body is Dictionary):
		_main._mainline_shop_payload = {}
		_main._set_prepare_content("[b]商店[/b]\n[color=#d36b5f]商店加载失败。[/color]")
		_update_prepare_action_buttons()
		return
	_main._mainline_shop_payload = (body as Dictionary).duplicate(true)
	_render_mainline_prepare()




# ── _on_prepare_mercenary_response ────────────────────────────────────────

func _on_prepare_mercenary_response(body: Variant, code: int = 0) -> void:
	if code < 200 or code >= 300 or not (body is Dictionary):
		_main._mainline_mercenary_payload = {}
		_main._set_prepare_content("[b]佣兵[/b]\n[color=#d36b5f]佣兵配置加载失败。[/color]")
		_update_prepare_action_buttons()
		return
	_main._mainline_mercenary_payload = (body as Dictionary).duplicate(true)
	_render_mainline_prepare()




# ── _promote_focused_prepare_hero ────────────────────────────────────────

func _promote_focused_prepare_hero() -> void:
	var hero := _focused_prepare_hero()
	if hero.is_empty() or not _focused_prepare_hero_can_promote():
		_main._update_status("当前英雄不可转职")
		return
	var options: Array = hero.get("promotion_options", []) if hero.get("promotion_options", []) is Array else []
	if options.is_empty():
		_main._update_status("当前英雄没有可用转职")
		return
	var hero_id := str(hero.get("hero_id", ""))
	var target_class_id := str(options[0])
	_main._update_status("正在将 %s 转职为 %s..." % [str(hero.get("name", hero_id)), target_class_id])
	NetworkClient.promote_mainline_hero(_main._selected_mainline_id, _main._user_name, hero_id, target_class_id, Callable(self, "_on_prepare_mutation_response").bind("转职"))




# ── _equip_focused_prepare_hero ────────────────────────────────────────

func _equip_focused_prepare_hero(slot: String, equipment_id: Variant) -> void:
	var hero := _focused_prepare_hero()
	if hero.is_empty():
		_main._update_status("请先选择英雄")
		return
	var hero_id := str(hero.get("hero_id", ""))
	_main._update_status("正在配置装备...")
	NetworkClient.equip_mainline_hero(_main._selected_mainline_id, _main._user_name, hero_id, slot, equipment_id, Callable(self, "_on_prepare_mutation_response").bind("装备"))




# ── _purchase_first_shop_item ────────────────────────────────────────

func _purchase_first_shop_item() -> void:
	var items: Array = _main._mainline_shop_payload.get("items", []) if _main._mainline_shop_payload.get("items", []) is Array else []
	var item := _selected_shop_item()
	if item.is_empty() and not items.is_empty() and items[0] is Dictionary:
		item = items[0]
	if item.is_empty():
		_main._update_status("商店暂无可购买商品")
		return
	var item_id := str(item.get("item_id", ""))
	if item_id == "":
		_main._update_status("商品缺少 item_id")
		return
	_main._update_status("购买 %s..." % str(item.get("name", item_id)))
	NetworkClient.purchase_post_battle_shop_item(_main._selected_mainline_id, _main._user_name, item_id, 1, Callable(self, "_on_prepare_shop_purchase_response"))




# ── _allocate_first_mercenary_point ────────────────────────────────────────

func _allocate_first_mercenary_point() -> void:
	if _main._mainline_mercenary_payload.is_empty():
		_on_prepare_tab_pressed("mercenary")
		return
	var choice := _first_mercenary_allocation_choice()
	if choice.is_empty():
		_main._update_status("没有可分配的佣兵点")
		return
	_main._update_status("分配佣兵点: %s %s" % [choice.get("unit_type", ""), choice.get("stat", "")])
	NetworkClient.allocate_mercenary_points(
		_main._selected_mainline_id,
		_main._user_name,
		str(choice.get("unit_type", "")),
		str(choice.get("stat", "")),
		int(choice.get("value", 1)),
		Callable(self, "_on_prepare_mercenary_allocate_response")
	)




# ── _on_prepare_mutation_response ────────────────────────────────────────

func _on_prepare_mutation_response(body: Variant, code: int, label: String) -> void:
	if code < 200 or code >= 300:
		_main._update_status("%s失败" % label)
		return
	_main._update_status("%s完成，正在刷新整备..." % label)
	NetworkClient.get_mainline_prepare(_main._selected_mainline_id, _main._user_name, Callable(self, "_on_mainline_prepare_response").bind(_main._selected_mainline_id))




# ── _on_prepare_shop_purchase_response ────────────────────────────────────────

func _on_prepare_shop_purchase_response(body: Variant, code: int = 0) -> void:
	if code < 200 or code >= 300:
		_main._update_status("购买失败")
		return
	if body is Dictionary:
		_main._update_status("购买完成，剩余金币 %d" % int((body as Dictionary).get("gold_remaining", 0)))
	_main._mainline_shop_payload = {}
	NetworkClient.get_mainline_prepare(_main._selected_mainline_id, _main._user_name, Callable(self, "_on_mainline_prepare_response").bind(_main._selected_mainline_id))
	NetworkClient.get_post_battle_shop(_main._selected_mainline_id, _main._user_name, Callable(self, "_on_prepare_shop_response"))




# ── _on_prepare_mercenary_allocate_response ────────────────────────────────────────

func _on_prepare_mercenary_allocate_response(body: Variant, code: int = 0) -> void:
	if code < 200 or code >= 300:
		_main._update_status("佣兵点分配失败")
		return
	_main._update_status("佣兵点已分配")
	_main._mainline_mercenary_payload = {}
	NetworkClient.get_mercenary_config(_main._selected_mainline_id, _main._user_name, Callable(self, "_on_prepare_mercenary_response"))




# ── _focused_prepare_hero_can_promote ────────────────────────────────────────

func _focused_prepare_hero_can_promote() -> bool:
	var hero := _focused_prepare_hero()
	if hero.is_empty():
		return false
	var options: Array = hero.get("promotion_options", []) if hero.get("promotion_options", []) is Array else []
	return bool(hero.get("can_promote", false)) and not options.is_empty()




# ── _find_first_equippable_item ────────────────────────────────────────

func _find_first_equippable_item() -> Dictionary:
	var focused := _focused_prepare_hero()
	if focused.is_empty():
		return {}
	var catalog: Array = _main._mainline_prepare_payload.get("equipment_catalog", []) if _main._mainline_prepare_payload.get("equipment_catalog", []) is Array else []
	var inventory: Dictionary = _main._mainline_prepare_payload.get("inventory", {}) if _main._mainline_prepare_payload.get("inventory", {}) is Dictionary else {}
	for item in catalog:
		if not (item is Dictionary): continue
		var it: Dictionary = item
		var item_id := str(it.get("equipment_id", it.get("item_id", "")))
		if item_id == "" or int(inventory.get(item_id, 0)) <= 0:
			continue
		var out := it.duplicate(true)
		out["equipment_id"] = item_id
		return out
	return {}




# ── _first_mercenary_allocation_choice ────────────────────────────────────────

func _first_mercenary_allocation_choice() -> Dictionary:
	var points := int(_main._mainline_mercenary_payload.get("mercenary_points", 0))
	if points <= 0:
		return {}
	var balance: Dictionary = _main._mainline_mercenary_payload.get("balance", {}) if _main._mainline_mercenary_payload.get("balance", {}) is Dictionary else {}
	var allowed: Array = balance.get("allowed_unit_types", []) if balance.get("allowed_unit_types", []) is Array else []
	var stat_rules: Dictionary = balance.get("stat_rules", {}) if balance.get("stat_rules", {}) is Dictionary else {}
	if allowed.is_empty() or stat_rules.is_empty():
		return {}
	var unit_type: String = _main._selected_prepare_merc_unit_type if _main._selected_prepare_merc_unit_type != "" else str(allowed[0])
	var stat: String = _main._selected_prepare_merc_stat if _main._selected_prepare_merc_stat != "" else str(stat_rules.keys()[0])
	return {"unit_type": unit_type, "stat": stat, "value": 1}




# ── _focused_prepare_hero ────────────────────────────────────────

func _focused_prepare_hero() -> Dictionary:
	var heroes: Array = _main._mainline_prepare_payload.get("heroes", []) if _main._mainline_prepare_payload.get("heroes", []) is Array else []
	for h in heroes:
		if h is Dictionary and str((h as Dictionary).get("hero_id", "")) == _main._selected_prepare_hero_id:
			return h
	if not heroes.is_empty() and heroes[0] is Dictionary:
		return heroes[0]
	return {}




# ── _selected_equippable_item ────────────────────────────────────────

func _selected_equippable_item() -> Dictionary:
	var catalog: Array = _main._mainline_prepare_payload.get("equipment_catalog", []) if _main._mainline_prepare_payload.get("equipment_catalog", []) is Array else []
	var inventory: Dictionary = _main._mainline_prepare_payload.get("inventory", {}) if _main._mainline_prepare_payload.get("inventory", {}) is Dictionary else {}
	for item in catalog:
		if not (item is Dictionary): continue
		var it: Dictionary = item
		var item_id := str(it.get("equipment_id", it.get("item_id", "")))
		if item_id == "" or item_id != _main._selected_prepare_equipment_id:
			continue
		if int(inventory.get(item_id, 0)) <= 0:
			return {}
		var out := it.duplicate(true)
		out["equipment_id"] = item_id
		return out
	return _find_first_equippable_item()




# ── _selected_shop_item ────────────────────────────────────────

func _selected_shop_item() -> Dictionary:
	var items: Array = _main._mainline_shop_payload.get("items", []) if _main._mainline_shop_payload.get("items", []) is Array else []
	for item in items:
		if not (item is Dictionary): continue
		var it: Dictionary = item
		if str(it.get("item_id", "")) == _main._selected_prepare_shop_item_id:
			return it
	return {}




# ── _bb_escape ────────────────────────────────────────

func _bb_escape(value: String) -> String:
	return value.replace("[", "\\[").replace("]", "\\]")




# ── _on_mainline_start_response ────────────────────────────────────────

func _on_mainline_start_response(body: Variant, code: int = 0) -> void:
	if code < 200 or code >= 300 or not (body is Dictionary):
		if code == 409 and _main._is_mainline_already_active_response(body) and not _main._mainline_auto_retry_pending:
			_main._mainline_auto_retry_pending = true
			var retry_id: String = _main._selected_mainline_id
			if retry_id == "":
				retry_id = "chapter_01_steel_rebellion"
			_main._update_status("已有主线进度,正在放弃旧进度并重试...")
			NetworkClient.abandon_mainline(retry_id, _main._user_name, Callable(self, "_on_mainline_auto_abandon_response").bind(retry_id))
			return
		_main._mainline_auto_retry_pending = false
		var msg := "主线启动失败"
		if body is Dictionary:
			msg = "主线启动失败: %s" % str(body.get("detail", body.get("message", msg)))
		_main._update_status(msg)
		_main._show_view("mainline")
		return
	_main._mainline_auto_retry_pending = false
	_main._game_id = int(body.get("game_id", 0))
	_main._player_id = int(body.get("player_id", 0))
	if _main._game_id <= 0 or _main._player_id <= 0:
		_main._update_status("主线启动失败: 响应缺少对局或玩家编号")
		_main._show_view("mainline")
		return
	GameState.local_player_id = _main._player_id
	UserSettings.set_value("session.v1.last_game_id", _main._game_id)
	UserSettings.set_value("session.v1.last_player_id", _main._player_id)
	_main._active_mainline_id = str(body.get("mainline_id", ""))
	_main._mainline_battle_game_id = _main._game_id
	UserSettings.set_value("session.v1.mainline_id", _main._active_mainline_id)
	UserSettings.set_value("session.v1.mainline_game_id", _main._game_id)
	UserSettings.set_value("session.v1.mainline_player_id", _main._player_id)
	var battle_index: int = int(body.get("battle_index", 0)) + 1
	var total_battles: int = int(body.get("total_battles", 1))
	_main._update_status("主线战斗 %d/%d 已创建,进入棋盘..." % [battle_index, total_battles])
	var dialogue_path := str(body.get("pre_battle_dialogue_url", ""))
	if dialogue_path != "":
		NetworkClient.fetch_mainline_dialogue(dialogue_path, Callable(self, "_on_mainline_dialogue_response"))
	_main._show_view("game")
	if _main.battle_mainline_next_btn != null and is_instance_valid(_main.battle_mainline_next_btn):
		_main.battle_mainline_next_btn.visible = false
	NetworkClient.connect_to_game(_main._game_id, _main._player_id)
	NetworkClient.get_game_state(_main._game_id, Callable(self, "_on_state_poll_response"))




# ── _on_mainline_auto_abandon_response ────────────────────────────────────────

func _on_mainline_auto_abandon_response(body: Variant, code: int, mainline_id: String) -> void:
	if code < 200 or code >= 300:
		_main._mainline_auto_retry_pending = false
		var msg := "放弃旧主线失败"
		if body is Dictionary:
			msg = "放弃旧主线失败: %s" % str(body.get("detail", body.get("message", msg)))
		_main._update_status(msg)
		_main._show_view("mainline")
		return
	_main._update_status("旧主线已放弃,重新创建战斗...")
	NetworkClient.start_mainline(mainline_id, _main._user_name, false, [], Callable(self, "_on_mainline_start_response"), true)




# ── _on_mainline_dialogue_response ────────────────────────────────────────

func _on_mainline_dialogue_response(body: Variant, _code: int = 0) -> void:
	_main._play_dialogue_scenes(body)




# ── _on_mainline_advance_response ────────────────────────────────────────

func _on_mainline_advance_response(body: Variant, code: int = 0) -> void:
	if code < 200 or code >= 300 or not (body is Dictionary):
		var msg := "主线推进失败"
		if body is Dictionary:
			msg = "主线推进失败: %s" % str(body.get("detail", body.get("message", msg)))
		_main._update_status(msg)
		return
	var state := str(body.get("state", "battle"))
	var battle_index: int = int(body.get("battle_index", 0)) + 1
	var total_battles: int = int(body.get("total_battles", 1))
	var dialogue_path := str(body.get("post_battle_dialogue_url", ""))
	if dialogue_path != "":
		NetworkClient.fetch_mainline_dialogue(dialogue_path, Callable(self, "_on_mainline_dialogue_response"))
	if state == "victory":
		var rewards: Dictionary = body.get("rewards", {}) if body.get("rewards", {}) is Dictionary else {}
		var reward_bits: Array[String] = []
		if int(rewards.get("gold", 0)) > 0:
			reward_bits.append("+%d 金币" % int(rewards.get("gold", 0)))
		if str(rewards.get("unlock_class", "")) != "":
			reward_bits.append("解锁 %s" % str(rewards.get("unlock_class", "")))
		_main._active_mainline_id = ""
		_main._mainline_battle_game_id = 0
		UserSettings.set_value("session.v1.mainline_id", "")
		if _main.battle_mainline_next_btn != null and is_instance_valid(_main.battle_mainline_next_btn):
			_main.battle_mainline_next_btn.visible = false
		_main._update_status("主线通关%s" % (": " + ", ".join(reward_bits) if reward_bits.size() > 0 else ""))
	else:
		_main._update_status("主线推进到战斗 %d/%d" % [battle_index, total_battles])
		# Phase 3 (FE8-style): bypass the MainlineNextBtn click and
		# immediately auto-spawn the next battle.  Dialogue fetch above
		# plays in parallel; the response handler is the same one the
		# button would have invoked, so behaviour is identical to the
		# old flow minus the click.  See docs/路线/FE8-vs-BattleBlitz-
		# 对照改进建议.md §FE8 风格改造.
		if _main.battle_mainline_next_btn != null and is_instance_valid(_main.battle_mainline_next_btn):
			_main.battle_mainline_next_btn.visible = false
		if _main._active_mainline_id != "":
			NetworkClient.next_battle_mainline(
				_main._active_mainline_id, _main._user_name, [],
				Callable(self, "_on_mainline_next_battle_response")
			)
	# P0:服务端 /advance 写自动存档 → toast 提示(对齐 WebUI autoSaveToast)
	var auto_save: Variant = body.get("auto_save", {})
	if auto_save is Dictionary and auto_save.has("label"):
		_main._show_auto_save_toast("💾 自动存档完毕 ✓  %s" % str(auto_save.get("label", "")), 1800.0)




# ── _on_mainline_next_battle_pressed ────────────────────────────────────────

func _on_mainline_next_battle_pressed() -> void:
	if _main._active_mainline_id == "":
		_main._update_status("没有可继续的主线")
		return
	_main._update_status("主线: 创建下一战...")
	NetworkClient.next_battle_mainline(_main._active_mainline_id, _main._user_name, [], Callable(self, "_on_mainline_next_battle_response"))




# ── _on_mainline_next_battle_response ────────────────────────────────────────

func _on_mainline_next_battle_response(body: Variant, code: int = 0) -> void:
	_on_mainline_start_response(body, code)




# ── _on_ml_back_pressed ────────────────────────────────────────

func _on_ml_back_pressed() -> void:
	if _main._mainline_page == "prepare":
		_main._mainline_prepare_payload = {}
		_main._mainline_shop_payload = {}
		_main._mainline_mercenary_payload = {}
		_set_mainline_page("chapter_list")
		return
	_main._show_view("menu")




# ── _on_ml_abandon_pressed ────────────────────────────────────────

func _on_ml_abandon_pressed() -> void:
	var mainline_id: String = _main._active_mainline_id
	if mainline_id == "":
		mainline_id = str(UserSettings.get_value("session.v1.mainline_id", ""))
	if mainline_id == "":
		_main._update_status("没有活跃主线可放弃")
		return
	_main._update_status("正在放弃主线 %s..." % mainline_id)
	NetworkClient.abandon_mainline(mainline_id, _main._user_name, Callable(self, "_on_mainline_abandon_response"))




# ── _on_mainline_abandon_response ────────────────────────────────────────

func _on_mainline_abandon_response(body: Variant, code: int = 0) -> void:
	if code < 200 or code >= 300 or not (body is Dictionary):
		var msg := "放弃主线失败"
		if body is Dictionary:
			msg = "放弃主线失败: %s" % str(body.get("detail", body.get("message", msg)))
		_main._update_status(msg)
		return
	_main._active_mainline_id = ""
	_main._mainline_battle_game_id = 0
	UserSettings.set_value("session.v1.mainline_id", "")
	UserSettings.set_value("session.v1.mainline_game_id", 0)
	UserSettings.set_value("session.v1.mainline_player_id", 0)
	if _main.battle_mainline_next_btn != null and is_instance_valid(_main.battle_mainline_next_btn):
		_main.battle_mainline_next_btn.visible = false
	_main._update_status("已放弃主线")
	_main._show_view("mainline")




# ── Round 2 helpers(prepare UI 同步)— Batch B 补 ──────

# ── _update_prepare_tab_buttons ──
func _update_prepare_tab_buttons() -> void:
	var map := {
		"heroes": ml_prep_heroes_tab_btn,
		"roster": ml_prep_roster_tab_btn,
		"equipment": ml_prep_equipment_tab_btn,
		"mercenary": ml_prep_mercenary_tab_btn,
		"shop": ml_prep_shop_tab_btn,
		"saves": ml_prep_saves_tab_btn,
	}
	for key in map.keys():
		var btn: Button = map[key]
		if btn == null or not is_instance_valid(btn):
			continue
		btn.disabled = key == _main._mainline_prepare_tab



# ── _sync_prepare_selectors ──
func _sync_prepare_selectors() -> void:
	_sync_prepare_hero_select()
	_sync_prepare_equipment_select()
	_sync_prepare_shop_select()
	_sync_prepare_mercenary_selects()



# ── _sync_prepare_hero_select ──
func _sync_prepare_hero_select() -> void:
	if ml_prep_hero_select == null or not is_instance_valid(ml_prep_hero_select):
		return
	var heroes: Array = _main._mainline_prepare_payload.get("heroes", []) if _main._mainline_prepare_payload.get("heroes", []) is Array else []
	ml_prep_hero_select.clear()
	var selected_index := 0
	for i in range(heroes.size()):
		if not (heroes[i] is Dictionary): continue
		var hero: Dictionary = heroes[i]
		var hero_id := str(hero.get("hero_id", ""))
		if hero_id == "":
			continue
		ml_prep_hero_select.add_item("%s · %s" % [str(hero.get("name", hero_id)), str(hero.get("class_id", "?"))])
		var idx := ml_prep_hero_select.item_count - 1
		ml_prep_hero_select.set_item_metadata(idx, hero_id)
		if hero_id == _main._selected_prepare_hero_id:
			selected_index = idx
	if ml_prep_hero_select.item_count > 0:
		ml_prep_hero_select.select(selected_index)
		_main._selected_prepare_hero_id = str(ml_prep_hero_select.get_item_metadata(selected_index))
	ml_prep_hero_select.disabled = ml_prep_hero_select.item_count <= 0



# ── _sync_prepare_equipment_select ──
func _sync_prepare_equipment_select() -> void:
	if ml_prep_equipment_select == null or not is_instance_valid(ml_prep_equipment_select):
		return
	var catalog: Array = _main._mainline_prepare_payload.get("equipment_catalog", []) if _main._mainline_prepare_payload.get("equipment_catalog", []) is Array else []
	var inventory: Dictionary = _main._mainline_prepare_payload.get("inventory", {}) if _main._mainline_prepare_payload.get("inventory", {}) is Dictionary else {}
	ml_prep_equipment_select.clear()
	var selected_index := 0
	for item in catalog:
		if not (item is Dictionary): continue
		var it: Dictionary = item
		var item_id := str(it.get("equipment_id", it.get("item_id", "")))
		if item_id == "":
			continue
		var count := int(inventory.get(item_id, 0))
		ml_prep_equipment_select.add_item("%s · %s · x%d" % [str(it.get("name", item_id)), str(it.get("slot", "item")), count])
		var idx := ml_prep_equipment_select.item_count - 1
		ml_prep_equipment_select.set_item_metadata(idx, item_id)
		if item_id == _main._selected_prepare_equipment_id:
			selected_index = idx
	if ml_prep_equipment_select.item_count > 0:
		ml_prep_equipment_select.select(selected_index)
		_main._selected_prepare_equipment_id = str(ml_prep_equipment_select.get_item_metadata(selected_index))
	ml_prep_equipment_select.disabled = ml_prep_equipment_select.item_count <= 0



# ── _sync_prepare_shop_select ──
func _sync_prepare_shop_select() -> void:
	if ml_prep_shop_select == null or not is_instance_valid(ml_prep_shop_select):
		return
	var items: Array = _main._mainline_shop_payload.get("items", []) if _main._mainline_shop_payload.get("items", []) is Array else []
	ml_prep_shop_select.clear()
	var selected_index := 0
	for item in items:
		if not (item is Dictionary): continue
		var it: Dictionary = item
		var item_id := str(it.get("item_id", ""))
		if item_id == "":
			continue
		ml_prep_shop_select.add_item("%s · %dG" % [str(it.get("name", item_id)), int(it.get("price", 0))])
		var idx := ml_prep_shop_select.item_count - 1
		ml_prep_shop_select.set_item_metadata(idx, item_id)
		if item_id == _main._selected_prepare_shop_item_id:
			selected_index = idx
	if ml_prep_shop_select.item_count > 0:
		ml_prep_shop_select.select(selected_index)
		_main._selected_prepare_shop_item_id = str(ml_prep_shop_select.get_item_metadata(selected_index))
	ml_prep_shop_select.disabled = ml_prep_shop_select.item_count <= 0



# ── _sync_prepare_mercenary_selects ──
func _sync_prepare_mercenary_selects() -> void:
	var balance: Dictionary = _main._mainline_mercenary_payload.get("balance", {}) if _main._mainline_mercenary_payload.get("balance", {}) is Dictionary else {}
	var allowed: Array = balance.get("allowed_unit_types", []) if balance.get("allowed_unit_types", []) is Array else []
	var stat_rules: Dictionary = balance.get("stat_rules", {}) if balance.get("stat_rules", {}) is Dictionary else {}
	if ml_prep_merc_unit_select != null and is_instance_valid(ml_prep_merc_unit_select):
		ml_prep_merc_unit_select.clear()
		var selected_unit_index := 0
		for unit_type in allowed:
			ml_prep_merc_unit_select.add_item(_main._unit_type_cn(str(unit_type)))
			var idx := ml_prep_merc_unit_select.item_count - 1
			ml_prep_merc_unit_select.set_item_metadata(idx, str(unit_type))
			if str(unit_type) == _main._selected_prepare_merc_unit_type:
				selected_unit_index = idx
		if ml_prep_merc_unit_select.item_count > 0:
			ml_prep_merc_unit_select.select(selected_unit_index)
			_main._selected_prepare_merc_unit_type = str(ml_prep_merc_unit_select.get_item_metadata(selected_unit_index))
		ml_prep_merc_unit_select.disabled = ml_prep_merc_unit_select.item_count <= 0
	if ml_prep_merc_stat_select != null and is_instance_valid(ml_prep_merc_stat_select):
		ml_prep_merc_stat_select.clear()
		var selected_stat_index := 0
		for stat in stat_rules.keys():
			ml_prep_merc_stat_select.add_item(str(stat).to_upper())
			var idx := ml_prep_merc_stat_select.item_count - 1
			ml_prep_merc_stat_select.set_item_metadata(idx, str(stat))
			if str(stat) == _main._selected_prepare_merc_stat:
				selected_stat_index = idx
		if ml_prep_merc_stat_select.item_count > 0:
			ml_prep_merc_stat_select.select(selected_stat_index)
			_main._selected_prepare_merc_stat = str(ml_prep_merc_stat_select.get_item_metadata(selected_stat_index))
		ml_prep_merc_stat_select.disabled = ml_prep_merc_stat_select.item_count <= 0


