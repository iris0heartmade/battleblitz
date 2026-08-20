extends PanelContainer
## Responsive campaign archive desk. Network state remains in the controller.

signal slot_requested(slot_index: int, occupied: bool)
signal back_requested

const MainlineTheme = preload("res://scripts/ui/mainline_theme.gd")

@onready var _slots: VBoxContainer = %Slots
@onready var _preview_title: Label = %PreviewTitle
@onready var _preview_body: Label = %PreviewBody
@onready var _briefing_body: Label = %BriefingBody
@onready var _intel_body: Label = %IntelBody
@onready var _intel_status: Label = %IntelStatus
@onready var _primary_action: Button = %PrimaryAction

var _selected_slot := -1
var _records: Array[Dictionary] = []
var _cards: Array[PanelContainer] = []
var _primary_action_busy := false


func _ready() -> void:
	_apply_theme()
	get_viewport().size_changed.connect(_apply_responsive_typography)
	_apply_responsive_typography()
	%BackButton.pressed.connect(func() -> void: back_requested.emit())
	_primary_action.pressed.connect(_activate_selected_slot)


func set_slots(records: Array[Dictionary]) -> void:
	_records = records.duplicate(true)
	_cards.clear()
	for child in _slots.get_children():
		child.queue_free()
	for index in range(maxi(3, _records.size())):
		var record: Dictionary = _records[index] if index < _records.size() else {}
		var card := _make_slot_card(index, record)
		_cards.append(card)
		_slots.add_child(card)
	if _selected_slot < 0:
		select_slot(0)


func select_slot(slot_index: int) -> void:
	if slot_index < 0 or slot_index >= maxi(3, _records.size()):
		return
	_selected_slot = slot_index
	var record: Dictionary = _records[slot_index] if slot_index < _records.size() else {}
	var occupied := not record.is_empty()
	_preview_title.text = str(record.get("title", "新游戏")) if occupied else "空白档案"
	var summary: String = str(record.get("summary", "从第一章开始新的主线旅程。"))
	var chapter: String = str(record.get("chapter", "第 ? 章"))
	var progress: String = str(record.get("progress", "进度: 0%"))
	var heroes_line: String = str(record.get("heroes_line", "队伍英雄: 待任命"))
	var enemy_preview: String = str(record.get("enemy_preview", "敌人预览: 待定"))
	var next_mission: String = str(record.get("next_mission", "下一战: 待定"))
	var recommend: String = str(record.get("recommend", "推荐等级: Lv.?"))
	var save_time: String = str(record.get("save_time", "保存: —"))
	# 中央只讲战役进度与队伍；下一战目标放进独立简报，避免同一份元数据重复三次。
	_preview_body.text = "%s\n\n战役进度\n◆ %s\n✦ %s\n\n队伍编成\n⚔ %s" % [
		summary, _without_prefix(chapter), _without_prefix(progress), _without_prefix(heroes_line),
	]
	_briefing_body.text = "行动目标\n➤ %s\n\n敌方态势\n☠ %s\n\n建议与记录\n✧ %s    ⌚ %s" % [
		_without_prefix(next_mission), _without_prefix(enemy_preview),
		_without_prefix(recommend), _without_prefix(save_time),
	]
	_intel_body.text = "出征流程\n1  进入战前整备\n2  检查英雄、装备与部队\n3  完成整备并开始战斗\n\n档案操作\n单击切换档案\n双击可直接进入整备"
	_intel_status.text = "◆ 档案已同步 · 可继续" if occupied else "◇ 空白档案 · 将创建新进度"
	_primary_action.text = "▶  进入战役" if occupied else "▶  开始新战役"
	_refresh_slot_selection()


func _refresh_slot_selection() -> void:
	for index in _cards.size():
		var card: PanelContainer = _cards[index]
		if card == null or not is_instance_valid(card):
			continue
		var selected := index == _selected_slot
		MainlineTheme.apply_slot_card_panel(card, _card_occupied(card), selected)
		var hit := card.get_meta("hit_button") as Button
		if hit != null and is_instance_valid(hit):
			hit.focus_mode = Control.FOCUS_ALL
			if selected:
				hit.grab_focus()


func _card_occupied(card: PanelContainer) -> bool:
	if not card.has_meta("record"):
		return false
	var record: Dictionary = card.get_meta("record", {})
	return not record.is_empty()


func _activate_selected_slot() -> void:
	if _selected_slot < 0:
		return
	var record: Dictionary = _records[_selected_slot] if _selected_slot < _records.size() else {}
	# 按下反馈:disable 主操作按钮 + 改文字为"处理中..." — 即便后端没响应,
	# 玩家也立刻看到点击生效。_primary_action_busy 让 controller 在切到 PreparePanel
	# 后重新 enable。
	_primary_action_busy = true
	_primary_action.disabled = true
	var occupied := not record.is_empty()
	_primary_action.text = "▶  处理中..." if occupied else "▶  创建中..."
	slot_requested.emit(_selected_slot, occupied)


func finish_primary_action(new_text: String) -> void:
	# controller 调用:在切到 PreparePanel / 完成整备后恢复按钮可用态 + 文字。
	_primary_action.disabled = false
	_primary_action.text = new_text
	_primary_action_busy = false


# 用 PanelContainer(深蓝填充 + 金属角钉做底)+ 内嵌 3 行 Label 显示内容,
# 透明 Button 覆盖做热区 — 这样装饰纹理不会盖住文字。
func _make_slot_card(index: int, record: Dictionary) -> PanelContainer:
	var occupied := not record.is_empty()
	var card := PanelContainer.new()
	var viewport_size := _physical_viewport_size()
	var compact := viewport_size.x <= 1366.0 or viewport_size.y <= 800.0
	# 720p 必须给页脚和标题留出安全区；1080p 则让三个档案卡真正占满左栏。
	card.custom_minimum_size = Vector2(0, 104 if compact else 164)
	card.size_flags_horizontal = Control.SIZE_EXPAND_FILL  # 拉满 SlotColumn
	# 内层 MarginContainer 给文字留 padding
	var margin := MarginContainer.new()
	margin.mouse_filter = Control.MOUSE_FILTER_IGNORE
	margin.add_theme_constant_override("margin_left", 18)
	margin.add_theme_constant_override("margin_top", 8 if compact else 18)
	margin.add_theme_constant_override("margin_right", 18)
	margin.add_theme_constant_override("margin_bottom", 8 if compact else 18)
	card.add_child(margin)
	# 三行:档号 / 标题 / 描述
	var layout := VBoxContainer.new()
	layout.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layout.add_theme_constant_override("separation", 4)
	margin.add_child(layout)
	var title: String
	var detail: String
	var chapter: String
	if occupied:
		title = _truncate_title(str(record.get("title", "新游戏")), 22)
		detail = _truncate_title(str(record.get("summary", "从第一章开始新的主线旅程。")), 36)
		chapter = _truncate_title(str(record.get("chapter", "第 ? 章")), 24)
	else:
		title = "空  槽"
		detail = "从第一章开始新的旅程"
		chapter = "等待新的旅程"
	var tag := Label.new()
	tag.text = "档  %d" % (index + 1)
	tag.add_theme_font_size_override("font_size", 15 if compact else 14)
	tag.add_theme_color_override("font_color", MainlineTheme.C_GOLD)
	tag.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layout.add_child(tag)
	var title_label := Label.new()
	title_label.text = title
	title_label.add_theme_font_size_override("font_size", 23 if compact else 21)
	title_label.add_theme_color_override("font_color", MainlineTheme.C_GOLD_BRIGHT if occupied else MainlineTheme.C_TEXT_DIM)
	title_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layout.add_child(title_label)
	var detail_label := Label.new()
	detail_label.text = detail
	detail_label.add_theme_font_size_override("font_size", 17 if compact else 16)
	detail_label.add_theme_color_override("font_color", MainlineTheme.C_TEXT if occupied else MainlineTheme.C_TEXT_DIM)
	detail_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	detail_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layout.add_child(detail_label)
	var chapter_label := Label.new()
	chapter_label.text = chapter
	chapter_label.add_theme_font_size_override("font_size", 15 if compact else 14)
	chapter_label.add_theme_color_override("font_color", MainlineTheme.C_TEXT_DIM)
	chapter_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layout.add_child(chapter_label)
	# 透明 Button 覆盖做热区(保留 Button 的键盘焦点/hover/press 信号)
	var hit := Button.new()
	hit.flat = true
	hit.focus_mode = Control.FOCUS_ALL
	hit.anchor_right = 1.0
	hit.anchor_bottom = 1.0
	hit.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	card.add_child(hit)
	# 把 hit 移到最上层
	card.move_child(hit, card.get_child_count() - 1)
	hit.pressed.connect(select_slot.bind(index))
	hit.gui_input.connect(func(event: InputEvent) -> void:
		if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.double_click:
			slot_requested.emit(index, occupied)
	)
	# 先 set_meta 再 apply_slot_card_panel — panel 需要 hit_button 来设置 focus ring。
	card.set_meta("hit_button", hit)
	card.set_meta("record", record)
	card.set_meta("index", index)
	MainlineTheme.apply_slot_card_panel(card, occupied)
	return card


func _truncate_title(s: String, max_chars: int) -> String:
	# 按可见字符数截断(CJK + ASCII 宽度按字符数);超出加省略号。空串保留。
	if s == "":
		return s
	var chars: int = 0
	var out: String = ""
	for i in s.length():
		var c: String = s.substr(i, 1)
		out += c
		chars += 1
		if chars >= max_chars:
			return out + "…"
	return out


func _without_prefix(value: String) -> String:
	# Payload 同时存在中文/英文冒号；展示时去掉字段名，只保留信息值。
	var chinese_colon := value.find("：")
	if chinese_colon >= 0:
		return value.substr(chinese_colon + 1).strip_edges()
	var ascii_colon := value.find(":")
	if ascii_colon >= 0:
		return value.substr(ascii_colon + 1).strip_edges()
	return value


func _apply_responsive_typography() -> void:
	var viewport_size := _physical_viewport_size()
	var compact_width := viewport_size.x <= 1366.0
	var compact_height := viewport_size.y <= 800.0
	var compact := compact_width or compact_height
	%ArchiveTitle.custom_minimum_size.y = 42 if compact_height else 58
	%ArchiveTitle.add_theme_font_size_override("font_size", 27 if compact else 28)
	$Layout.add_theme_constant_override("separation", 6 if compact_height else 14)
	$Layout/Columns.add_theme_constant_override("separation", 8 if compact_width else 16)
	%SlotColumn.custom_minimum_size.x = 310 if compact_width else 360
	%IntelColumn.custom_minimum_size.x = 310 if compact_width else 336
	$Layout/Columns/SlotColumn/SlotsMargin.add_theme_constant_override("margin_top", 8 if compact_height else 18)
	$Layout/Columns/SlotColumn/SlotsMargin.add_theme_constant_override("margin_bottom", 8 if compact_height else 18)
	$Layout/Columns/PreviewColumn/PreviewMargin.add_theme_constant_override("margin_top", 10 if compact_height else 24)
	$Layout/Columns/PreviewColumn/PreviewMargin.add_theme_constant_override("margin_bottom", 10 if compact_height else 24)
	$Layout/Columns/PreviewColumn/PreviewMargin/PreviewLayout.add_theme_constant_override("separation", 7 if compact_height else 16)
	$Layout/Columns/IntelColumn/IntelMargin.add_theme_constant_override("margin_top", 10 if compact_height else 20)
	$Layout/Columns/IntelColumn/IntelMargin.add_theme_constant_override("margin_bottom", 10 if compact_height else 20)
	$Layout/FooterSafe.add_theme_constant_override("margin_top", 2 if compact_height else 6)
	$Layout/FooterSafe.add_theme_constant_override("margin_bottom", 34 if compact_height else 24)
	_preview_title.add_theme_font_size_override("font_size", 28 if compact_height else 32)
	_preview_body.add_theme_font_size_override("font_size", 22 if compact_height else 19)
	%PreviewBody.custom_minimum_size.y = 116 if compact_height else 190
	%BriefingPanel.custom_minimum_size.y = 170 if compact_height else 250
	%BriefingTitle.add_theme_font_size_override("font_size", 21 if compact_height else 20)
	_briefing_body.add_theme_font_size_override("font_size", 20 if compact_height else 17)
	_briefing_body.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	%IntelTitle.add_theme_font_size_override("font_size", 21 if compact_height else 20)
	_intel_body.add_theme_font_size_override("font_size", 19 if compact_height else 16)
	_intel_status.add_theme_font_size_override("font_size", 18 if compact_height else 16)
	%PreviewHint.add_theme_font_size_override("font_size", 17 if compact_height else 15)
	_primary_action.custom_minimum_size.y = 66 if compact_height else 88
	_primary_action.add_theme_font_size_override("font_size", 23 if compact else 24)
	%BackButton.custom_minimum_size = Vector2(220 if compact_width else 260, 48 if compact_height else 54)
	%BackButton.add_theme_font_size_override("font_size", 18 if compact else 17)


func _physical_viewport_size() -> Vector2:
	# The project stretches a fixed design canvas, so the logical viewport remains
	# 1920x1080 even when the actual window is 1280x720.
	var review_resolution := OS.get_environment("BB_REVIEW_RES")
	if review_resolution.contains("x"):
		var dimensions := review_resolution.split("x")
		if dimensions.size() == 2:
			var review_size := Vector2(float(dimensions[0]), float(dimensions[1]))
			if review_size.x > 0.0 and review_size.y > 0.0:
				return review_size
	var window_size := Vector2(DisplayServer.window_get_size())
	if window_size.x > 0.0 and window_size.y > 0.0:
		return window_size
	return get_viewport_rect().size


func _apply_theme() -> void:
	MainlineTheme.apply_page_frame(self)
	# 三栏:存档列表 / 预览 / 出征情报;预览用档案纸底,其余用墨蓝织纹。
	MainlineTheme.apply_section_panel(%SlotColumn, "navy")
	MainlineTheme.apply_section_panel(%PreviewColumn, "paper")
	MainlineTheme.apply_section_panel(%IntelColumn, "navy")
	MainlineTheme.apply_item_card(%BriefingPanel)
	MainlineTheme.apply_page_heading(%ArchiveTitle)
	MainlineTheme.apply_paper_text(_preview_title, true)
	MainlineTheme.apply_paper_text(_preview_body)
	MainlineTheme.apply_paper_text(_briefing_body)
	%PreviewHint.add_theme_color_override("font_color", MainlineTheme.C_PARCHMENT_DIM)
	%IntelTitle.add_theme_color_override("font_color", MainlineTheme.C_GOLD_BRIGHT)
	MainlineTheme.apply_section_title(%IntelTitle)
	MainlineTheme.apply_section_title(%BriefingTitle)
	MainlineTheme.apply_paper_text(%BriefingTitle, true)
	_intel_status.add_theme_color_override("font_color", MainlineTheme.C_GOLD_BRIGHT)
	MainlineTheme.apply_primary(_primary_action)
	MainlineTheme.apply_secondary(%BackButton)
