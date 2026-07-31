extends PanelContainer
## Responsive campaign archive desk. Network state remains in the controller.

signal slot_requested(slot_index: int, occupied: bool)
signal back_requested

const MainlineTheme = preload("res://scripts/ui/mainline_theme.gd")

@onready var _slots: VBoxContainer = %Slots
@onready var _preview_title: Label = %PreviewTitle
@onready var _preview_body: Label = %PreviewBody
@onready var _intel_body: Label = %IntelBody
@onready var _primary_action: Button = %PrimaryAction

var _selected_slot := -1
var _records: Array[Dictionary] = []
var _cards: Array[Button] = []


func _ready() -> void:
	_apply_theme()
	%BackButton.pressed.connect(func() -> void: back_requested.emit())
	_primary_action.pressed.connect(_activate_selected_slot)


func set_slots(records: Array[Dictionary]) -> void:
	_records = records.duplicate(true)
	_cards.clear()
	for child in _slots.get_children():
		child.queue_free()
	for index in range(maxi(3, _records.size())):
		var record: Dictionary = _records[index] if index < _records.size() else {}
		_cards.append(_make_slot_card(index, record))
		_slots.add_child(_cards[-1])
	if _selected_slot < 0:
		select_slot(0)


func select_slot(slot_index: int) -> void:
	if slot_index < 0 or slot_index >= maxi(3, _records.size()):
		return
	_selected_slot = slot_index
	var record: Dictionary = _records[slot_index] if slot_index < _records.size() else {}
	var occupied := not record.is_empty()
	_preview_title.text = str(record.get("title", "新游戏")) if occupied else "空白档案"
	_preview_body.text = str(record.get("summary", "从第一章开始新的主线旅程。"))
	_intel_body.text = str(record.get("intel", "选择此档案后，可查看队伍与下一战的出征情报。"))
	_primary_action.text = "继续该档案" if occupied else "开始新游戏"
	_refresh_slot_selection()


# 选中行使用列表行 selected 态(暗红封签强调)+ 2px 金边焦点框,其余回到 neutral 态。
func _refresh_slot_selection() -> void:
	for index in _cards.size():
		var card: Button = _cards[index]
		if card == null or not is_instance_valid(card):
			continue
		MainlineTheme.apply_row(card, index == _selected_slot)
		card.focus_mode = Control.FOCUS_ALL  # 让 2px 金边 focus ring 在键盘聚焦时可见


func _activate_selected_slot() -> void:
	if _selected_slot < 0:
		return
	var record: Dictionary = _records[_selected_slot] if _selected_slot < _records.size() else {}
	slot_requested.emit(_selected_slot, not record.is_empty())


func _make_slot_card(index: int, record: Dictionary) -> Button:
	var occupied := not record.is_empty()
	var card := Button.new()
	card.custom_minimum_size = Vector2(0, 94)
	card.alignment = HORIZONTAL_ALIGNMENT_LEFT
	card.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	var title := str(record.get("title", "空槽")) if occupied else "空槽"
	var detail := str(record.get("summary", "从第一章开始新的主线旅程。"))
	card.text = "档 %d  ·  %s\n%s" % [index + 1, title, detail]
	MainlineTheme.apply_row(card)
	card.add_theme_font_size_override("font_size", 15)
	card.pressed.connect(select_slot.bind(index))
	card.gui_input.connect(func(event: InputEvent) -> void:
		if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.double_click:
			slot_requested.emit(index, occupied)
	)
	return card


func _apply_theme() -> void:
	MainlineTheme.apply_page_frame(self)
	# 三栏:存档列表 / 预览 / 出征情报;预览用档案纸底,其余用墨蓝织纹。
	MainlineTheme.apply_section_panel(%SlotColumn, "navy")
	MainlineTheme.apply_section_panel(%PreviewColumn, "paper")
	MainlineTheme.apply_section_panel(%IntelColumn, "navy")
	MainlineTheme.apply_title_plate(%ArchiveTitle)
	_preview_title.add_theme_color_override("font_color", MainlineTheme.C_GOLD_BRIGHT)
	%IntelTitle.add_theme_color_override("font_color", MainlineTheme.C_GOLD_BRIGHT)
	MainlineTheme.apply_section_title(%IntelTitle)
	_primary_action.custom_minimum_size = Vector2(0, 48)
	MainlineTheme.apply_primary(_primary_action)
	MainlineTheme.apply_secondary(%BackButton)
