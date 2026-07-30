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


func _ready() -> void:
	_apply_theme()
	%BackButton.pressed.connect(func() -> void: back_requested.emit())
	_primary_action.pressed.connect(_activate_selected_slot)


func set_slots(records: Array[Dictionary]) -> void:
	_records = records.duplicate(true)
	for child in _slots.get_children():
		child.queue_free()
	for index in range(maxi(3, _records.size())):
		var record: Dictionary = _records[index] if index < _records.size() else {}
		_slots.add_child(_make_slot_card(index, record))
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
	MainlineTheme.apply_secondary(card)
	card.add_theme_font_size_override("font_size", 15)
	card.pressed.connect(select_slot.bind(index))
	card.gui_input.connect(func(event: InputEvent) -> void:
		if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.double_click:
			slot_requested.emit(index, occupied)
	)
	return card


func _apply_theme() -> void:
	var frame := MainlineTheme._box(MainlineTheme.C_PANEL, MainlineTheme.C_GOLD, 2, 8)
	frame.content_margin_left = 24
	frame.content_margin_right = 24
	frame.content_margin_top = 20
	frame.content_margin_bottom = 20
	add_theme_stylebox_override("panel", frame)
	for section in [%SlotColumn, %PreviewColumn, %IntelColumn]:
		MainlineTheme.apply_section_panel(section, MainlineTheme.C_GOLD)
	for label in [%ArchiveTitle, _preview_title, %IntelTitle]:
		label.add_theme_color_override("font_color", MainlineTheme.C_GOLD_BRIGHT)
	_primary_action.custom_minimum_size = Vector2(0, 48)
	MainlineTheme.apply_primary(_primary_action)
	MainlineTheme.apply_secondary(%BackButton)
