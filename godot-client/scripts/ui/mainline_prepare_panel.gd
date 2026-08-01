extends PanelContainer
## Responsive war-council desk for a loaded mainline chapter.
## Controllers feed mapped display strings into this component and react only
## to these explicit signals. Each tab owns its own content area.

signal tab_requested(tab: String)
signal hero_requested(hero_id: String)
signal action_requested(action: String)
signal choice_requested(kind: String, index: int)

const MainlineTheme = preload("res://scripts/ui/mainline_theme.gd")

@onready var _roster: VBoxContainer = %Roster
@onready var _content_title: Label = %ContentTitle
@onready var _content_body: Label = %ContentBody
@onready var _mission_title: Label = %MissionTitle
@onready var _mission_body: Label = %MissionBody
@onready var _tabs: HBoxContainer = %Tabs

var _active_tab := "heroes"
var _last_content_body := ""
var _hero_cards: Array[PanelContainer] = []
var _selected_hero_id := ""


func _ready() -> void:
	_apply_theme()
	get_viewport().size_changed.connect(_apply_responsive_layout)
	_apply_responsive_layout()
	for button in _tabs.get_children():
		if button is Button:
			(button as Button).pressed.connect(_on_tab_pressed.bind((button as Button).name.to_lower()))
	%BackAction.pressed.connect(_request_action.bind("back"))
	%RefreshAction.pressed.connect(_request_action.bind("refresh"))
	%StartAction.pressed.connect(_request_action.bind("start"))
	%CompleteAction.pressed.connect(_request_action.bind("complete"))
	%AbandonAction.pressed.connect(_request_action.bind("abandon"))
	%ChoiceSelect.item_selected.connect(func(index: int) -> void:
		_refresh_content_insight(index)
		choice_requested.emit(str(%ChoiceSelect.get_meta("choice_kind", "")), index)
	)
	_on_tab_pressed("heroes")


func _request_action(action: String) -> void:
	match action:
		"start":
			set_action_status("正在创建战斗，请稍候...")
		"complete":
			set_action_status("正在保存整备配置...")
		"abandon":
			set_action_status("正在检查当前主线...")
		"refresh":
			set_action_status("正在刷新整备数据...")
		_:
			set_action_status("")
	action_requested.emit(action)


func set_action_status(message: String, is_error: bool = false) -> void:
	%ActionStatus.text = message
	%ActionStatus.visible = true
	%ActionStatus.add_theme_color_override(
		"font_color",
		Color("d76b68") if is_error else MainlineTheme.C_GOLD_BRIGHT
	)


func set_mission(title: String, body: String) -> void:
	# 标题条保持短标题，战役名下沉至正文，避免窄栏标题与装饰框互相覆盖。
	_mission_title.text = "任务摘要"
	_mission_body.text = "%s\n\n%s" % [title, body]
	%MissionChecklist.text = "出征核对\n◆ 胜利条件已读取\n◆ 英雄与部队可调整\n◆ 装备可在装备页确认\n\n下一步\n完成整备后选择「开始战斗」。"


func set_heroes(heroes: Array[Dictionary]) -> void:
	_hero_cards.clear()
	for child in _roster.get_children():
		child.queue_free()
	for hero in heroes:
		var hero_id := str(hero.get("hero_id", ""))
		var card := PanelContainer.new()
		card.custom_minimum_size = Vector2(0, 96)
		card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var margin := MarginContainer.new()
		margin.mouse_filter = Control.MOUSE_FILTER_IGNORE
		margin.add_theme_constant_override("margin_left", 16)
		margin.add_theme_constant_override("margin_top", 10)
		margin.add_theme_constant_override("margin_right", 16)
		margin.add_theme_constant_override("margin_bottom", 10)
		card.add_child(margin)
		var layout := VBoxContainer.new()
		layout.mouse_filter = Control.MOUSE_FILTER_IGNORE
		layout.add_theme_constant_override("separation", 4)
		margin.add_child(layout)
		var name_label := Label.new()
		name_label.text = "%s  ·  Lv.%s" % [str(hero.get("name", "英雄")), str(hero.get("level", 1))]
		name_label.add_theme_font_size_override("font_size", 20)
		name_label.add_theme_color_override("font_color", MainlineTheme.C_GOLD_BRIGHT)
		name_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
		layout.add_child(name_label)
		var hp_label := Label.new()
		hp_label.text = "HP  %s" % str(hero.get("hp", "-"))
		hp_label.add_theme_font_size_override("font_size", 16)
		hp_label.add_theme_color_override("font_color", MainlineTheme.C_TEXT)
		hp_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
		layout.add_child(hp_label)
		var equip_label := Label.new()
		equip_label.text = "✦  %s" % str(hero.get("equipment_summary", "未装备"))
		equip_label.add_theme_font_size_override("font_size", 14)
		equip_label.add_theme_color_override("font_color", MainlineTheme.C_TEXT_DIM)
		equip_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
		layout.add_child(equip_label)
		var hit := Button.new()
		hit.flat = true
		hit.focus_mode = Control.FOCUS_ALL
		hit.anchor_right = 1.0
		hit.anchor_bottom = 1.0
		hit.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
		card.add_child(hit)
		card.move_child(hit, card.get_child_count() - 1)
		hit.pressed.connect(_select_hero.bind(hero_id))
		# 先 set_meta 再 apply_slot_card_panel — theme 函数依赖 hit_button meta。
		card.set_meta("hit_button", hit)
		card.set_meta("record", {"hero_id": hero_id, "name": str(hero.get("name", "英雄"))})
		MainlineTheme.apply_slot_card_panel(card, true)
		_hero_cards.append(card)
		_roster.add_child(card)
	if _selected_hero_id == "" and not heroes.is_empty():
		_selected_hero_id = str(heroes[0].get("hero_id", ""))
	_refresh_hero_selection()
	_apply_responsive_layout()


func show_content(title: String, body: String) -> void:
	_content_title.text = title
	_content_body.text = body
	_last_content_body = body
	_refresh_content_insight(%ChoiceSelect.selected)


func set_active_tab(tab: String) -> void:
	_active_tab = tab
	for button in _tabs.get_children():
		if button is Button:
			(button as Button).disabled = button.name.to_lower() == tab
	_apply_responsive_layout()


func set_prepare_ready(ready: bool) -> void:
	%StartAction.disabled = not ready
	%CompleteAction.disabled = not ready
	%RefreshAction.disabled = not ready
	# “开始战斗”是整备页唯一主操作；完成整备保留为明确的前置步骤。
	%CompleteAction.text = "1  完成整备"
	%StartAction.text = "2  开始战斗 →"


func set_choices(kind: String, entries: Array, selected_index: int = 0, hint: String = "") -> void:
	%EquipmentIconRow.visible = kind == "equipment"
	%ChoiceSelect.clear()
	for entry in entries:
		%ChoiceSelect.add_item(entry)
	%ChoiceSelect.visible = not entries.is_empty()
	%ChoiceHint.visible = not hint.is_empty()
	%ChoiceHint.text = hint
	%ChoiceSelect.set_meta("choice_kind", kind)
	if not entries.is_empty():
		%ChoiceSelect.select(clampi(selected_index, 0, entries.size() - 1))
	_refresh_content_insight(%ChoiceSelect.selected)


func _on_tab_pressed(tab: String) -> void:
	_active_tab = tab
	for button in _tabs.get_children():
		if button is Button:
			(button as Button).disabled = button.name.to_lower() == tab
	_apply_responsive_layout()
	tab_requested.emit(tab)


func _select_hero(hero_id: String) -> void:
	_selected_hero_id = hero_id
	_refresh_hero_selection()
	hero_requested.emit(hero_id)


func _refresh_hero_selection() -> void:
	for card in _hero_cards:
		if card == null or not is_instance_valid(card):
			continue
		var record: Dictionary = card.get_meta("record", {})
		MainlineTheme.apply_slot_card_panel(card, true, str(record.get("hero_id", "")) == _selected_hero_id)
	_refresh_hero_portrait()


func _refresh_hero_portrait() -> void:
	%HeroPortrait.texture = null
	if _selected_hero_id.is_empty():
		return
	var portrait_path := "res://assets/heroes/portrait_%s.png" % _selected_hero_id
	if ResourceLoader.exists(portrait_path):
		%HeroPortrait.texture = load(portrait_path) as Texture2D


func _refresh_content_insight(choice_index: int = -1) -> void:
	match _active_tab:
		"heroes":
			%ContentKicker.text = "英雄档案 · 当前配置"
			%InsightTitle.text = "出征流程"
			%InsightBody.text = "1  核对英雄、部队与装备\n2  点击「完成整备」保存配置\n3  点击「开始战斗」进入地图"
		"equipment":
			%ContentKicker.text = "装备工房 · 变更预览"
			%InsightTitle.text = "装备前后对照"
			var current_block := _last_content_body.split("\n\n")[0] if not _last_content_body.is_empty() else "当前装备：未读取"
			current_block = current_block.replace("\n", "  /  ")
			var selected_item := "尚未选择候选物品"
			if choice_index >= 0 and choice_index < %ChoiceSelect.item_count:
				selected_item = %ChoiceSelect.get_item_text(choice_index)
			%InsightBody.text = "当前：%s\n候选：%s\n结算：槽位匹配后可保存；最终属性由服务器确认" % [current_block, selected_item]
		"roster":
			%ContentKicker.text = "部队名册 · 部署检查"
			%InsightTitle.text = "编成建议"
			%InsightBody.text = "核对可部署数量与兵种职责。\n主线英雄固定出战，佣兵可在对应页调整。"
		"mercenary":
			%ContentKicker.text = "佣兵配置 · 点数分配"
			%InsightTitle.text = "配置提示"
			%InsightBody.text = "先核对可用点数，再分配兵种与强化。\n变更后完成整备以保存本次配置。"
		"shop":
			%ContentKicker.text = "战前商店 · 物资采购"
			%InsightTitle.text = "采购核对"
			%InsightBody.text = "比较库存、价格与当前金币。\n购买完成后返回英雄或装备页复核配置。"
		_:
			%ContentKicker.text = "战前议事 · 当前页面"
			%InsightTitle.text = "操作提示"
			%InsightBody.text = "核对当前信息后，使用上方页签继续整备。"


func _apply_responsive_layout() -> void:
	# 项目使用固定设计视口，get_viewport_rect() 在 1280 窗口下仍可能返回 1920。
	# 截图流程会显式注入 BB_REVIEW_RES；运行时再退回物理窗口尺寸。
	var viewport_size := Vector2.ZERO
	var review_resolution := OS.get_environment("BB_REVIEW_RES")
	if review_resolution.contains("x"):
		var dimensions := review_resolution.split("x")
		if dimensions.size() == 2:
			viewport_size = Vector2(float(dimensions[0]), float(dimensions[1]))
	if viewport_size.x <= 0.0 or viewport_size.y <= 0.0:
		viewport_size = Vector2(DisplayServer.window_get_size())
	if viewport_size.x <= 0.0 or viewport_size.y <= 0.0:
		viewport_size = get_viewport_rect().size
	var compact_width := viewport_size.x <= 1366.0
	var compact_height := viewport_size.y <= 800.0
	var equipment_page := _active_tab == "equipment"
	var hero_page := _active_tab == "heroes"
	%CouncilTitle.custom_minimum_size.y = 42 if compact_height else 48
	%CouncilTitle.add_theme_font_size_override("font_size", 25 if compact_height else 27)
	$Layout.add_theme_constant_override("separation", 6 if compact_height else 10)
	$Layout/Columns.add_theme_constant_override("separation", 8 if compact_width else 14)
	$Layout/Columns/ContentPanel/ContentMargin.add_theme_constant_override("margin_top", 6 if equipment_page or compact_height else 18)
	$Layout/Columns/ContentPanel/ContentMargin.add_theme_constant_override("margin_bottom", 6 if equipment_page or compact_height else 18)
	$Layout/Columns/ContentPanel/ContentMargin/ContentLayout.add_theme_constant_override("separation", 4 if equipment_page else (6 if compact_height else 10))
	$Layout/Columns/MissionPanel/MissionMargin.add_theme_constant_override("margin_top", 10 if compact_height else 16)
	$Layout/Columns/MissionPanel/MissionMargin.add_theme_constant_override("margin_bottom", 10 if compact_height else 16)
	$Layout/Columns/MissionPanel/MissionMargin/MissionLayout.add_theme_constant_override("separation", 8 if compact_height else 12)
	$Layout/ActionSafe.add_theme_constant_override("margin_top", 8)
	$Layout/ActionSafe.add_theme_constant_override("margin_bottom", 42 if compact_height else 32)
	_content_title.add_theme_font_size_override("font_size", 25 if compact_height else 24)
	_content_body.add_theme_font_size_override("font_size", (18 if compact_height else 16) if equipment_page else (19 if compact_height else 18))
	_mission_body.add_theme_font_size_override("font_size", 21 if compact_height else 16)
	%ContentKicker.add_theme_font_size_override("font_size", (17 if compact_height else 14) if equipment_page else (18 if compact_height else 15))
	%InsightBody.add_theme_font_size_override("font_size", (16 if compact_height else 15) if equipment_page else (17 if compact_height else 16))
	%InsightTitle.add_theme_font_size_override("font_size", (19 if compact_height else 18) if equipment_page else (20 if compact_height else 19))
	%ChoiceHint.add_theme_font_size_override("font_size", 16 if compact_height and equipment_page else 14)
	%MissionChecklist.add_theme_font_size_override("font_size", 16)
	%ContentBody.custom_minimum_size.y = 0 if compact_height or equipment_page else 72
	%HeroPortraitFrame.visible = hero_page
	%HeroPortraitFrame.custom_minimum_size = Vector2(132, 144) if compact_height else Vector2(118, 142)
	%HeroHeaderRow.add_theme_constant_override("separation", 12 if compact_width else 18)
	# 英雄页承载流程，装备页承载当前→候选差异；两者都是核心信息而非装饰。
	%ContentInsightPanel.visible = hero_page or equipment_page
	%ContentInsightPanel.custom_minimum_size.y = (88 if compact_height else 100) if equipment_page else (92 if compact_height else 132)
	$Layout/Columns/ContentPanel/ContentMargin/ContentLayout/ContentInsightPanel/InsightMargin.add_theme_constant_override("margin_top", 10 if equipment_page else 16)
	$Layout/Columns/ContentPanel/ContentMargin/ContentLayout/ContentInsightPanel/InsightMargin.add_theme_constant_override("margin_bottom", 10 if equipment_page else 16)
	%MissionChecklist.visible = not compact_height
	%MissionChecklist.custom_minimum_size.y = 0 if compact_height else 132
	for icon in [$Layout/Columns/ContentPanel/ContentMargin/ContentLayout/EquipmentIconRow/WeaponIcon, $Layout/Columns/ContentPanel/ContentMargin/ContentLayout/EquipmentIconRow/ArmorIcon, $Layout/Columns/ContentPanel/ContentMargin/ContentLayout/EquipmentIconRow/AccessoryIcon]:
		icon.custom_minimum_size = Vector2(26, 26) if equipment_page and compact_height else (Vector2(32, 32) if equipment_page else (Vector2(32, 32) if compact_height else Vector2(40, 40)))
	%ChoiceSelect.custom_minimum_size.y = 42 if equipment_page else (48 if compact_height else 44)
	%ChoiceSelect.add_theme_font_size_override("font_size", (18 if compact_height else 15) if equipment_page else (21 if compact_height else 15))
	for tab in _tabs.get_children():
		if tab is Button:
			(tab as Button).custom_minimum_size = Vector2(82 if compact_width else 72, 44 if compact_height else 42)
			(tab as Button).add_theme_font_size_override("font_size", 21 if compact_height else 15)
	for card in _hero_cards:
		if card != null and is_instance_valid(card):
			card.custom_minimum_size.y = 94 if compact_height else 100
	for action_name in ["BackAction", "RefreshAction", "StartAction", "CompleteAction", "AbandonAction"]:
		var action := get_node("%" + action_name) as Button
		if action != null:
			action.custom_minimum_size.y = 54 if compact_height else 50
			action.add_theme_font_size_override("font_size", 21 if compact_height else 16)
	%RefreshAction.custom_minimum_size.x = 136
	%RefreshAction.add_theme_font_size_override("font_size", 16)
	%CompleteAction.custom_minimum_size.x = 176 if compact_height else 164
	%CompleteAction.add_theme_font_size_override("font_size", 18 if compact_height else 17)
	%StartAction.custom_minimum_size.x = 244 if compact_height else 228
	%StartAction.custom_minimum_size.y = 60 if compact_height else 56
	%StartAction.add_theme_font_size_override("font_size", 23 if compact_height else 20)
	%AbandonAction.custom_minimum_size.x = 160
	%AbandonAction.add_theme_font_size_override("font_size", 16)


func _apply_theme() -> void:
	MainlineTheme.apply_page_frame(self)
	# 三栏:名册 / 内容 / 任务摘要;内容栏用档案纸底,任务栏用墨蓝织纹。
	MainlineTheme.apply_section_panel(%RosterPanel, "navy")
	MainlineTheme.apply_section_panel(%ContentPanel, "paper")
	MainlineTheme.apply_section_panel(%MissionPanel, "navy")
	MainlineTheme.apply_item_card(%ContentInsightPanel)
	MainlineTheme.apply_portrait_anchor(%HeroPortraitFrame)
	for button in _tabs.get_children():
		MainlineTheme.apply_tab(button)
	MainlineTheme.apply_page_heading(%CouncilTitle)
	MainlineTheme.apply_secondary(%BackAction)
	MainlineTheme.apply_secondary(%RefreshAction)
	MainlineTheme.apply_option(%ChoiceSelect)
	MainlineTheme.apply_primary(%StartAction)
	MainlineTheme.apply_danger(%AbandonAction)
	MainlineTheme.apply_secondary(%CompleteAction)
	MainlineTheme.apply_paper_text(_content_title, true)
	MainlineTheme.apply_paper_text(_content_body)
	MainlineTheme.apply_paper_text(%ContentKicker)
	MainlineTheme.apply_paper_text(%InsightTitle, true)
	MainlineTheme.apply_paper_text(%InsightBody)
	%ContentKicker.add_theme_color_override("font_color", MainlineTheme.C_PARCHMENT_DIM)
	_mission_title.add_theme_color_override("font_color", MainlineTheme.C_GOLD_BRIGHT)
	%MissionChecklist.add_theme_color_override("font_color", MainlineTheme.C_GOLD_BRIGHT)
	MainlineTheme.apply_section_title(_mission_title)
