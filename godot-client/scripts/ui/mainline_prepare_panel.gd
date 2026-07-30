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


func _ready() -> void:
	_apply_theme()
	for button in _tabs.get_children():
		if button is Button:
			(button as Button).pressed.connect(_on_tab_pressed.bind((button as Button).name.to_lower()))
	%BackAction.pressed.connect(func() -> void: action_requested.emit("back"))
	%RefreshAction.pressed.connect(func() -> void: action_requested.emit("refresh"))
	%StartAction.pressed.connect(func() -> void: action_requested.emit("start"))
	%CompleteAction.pressed.connect(func() -> void: action_requested.emit("complete"))
	%AbandonAction.pressed.connect(func() -> void: action_requested.emit("abandon"))
	%ChoiceSelect.item_selected.connect(func(index: int) -> void:
		choice_requested.emit(str(%ChoiceSelect.get_meta("choice_kind", "")), index)
	)
	_on_tab_pressed("heroes")


func set_mission(title: String, body: String) -> void:
	_mission_title.text = title
	_mission_body.text = body


func set_heroes(heroes: Array[Dictionary]) -> void:
	for child in _roster.get_children():
		child.queue_free()
	for hero in heroes:
		var button := Button.new()
		button.custom_minimum_size = Vector2(0, 72)
		button.alignment = HORIZONTAL_ALIGNMENT_LEFT
		button.text = "%s  ·  Lv.%s\nHP %s  ·  %s" % [
			str(hero.get("name", "英雄")), str(hero.get("level", 1)),
			str(hero.get("hp", "-")), str(hero.get("equipment_summary", "未装备")),
		]
		MainlineTheme.apply_secondary(button)
		button.pressed.connect(hero_requested.emit.bind(str(hero.get("hero_id", ""))))
		_roster.add_child(button)


func show_content(title: String, body: String) -> void:
	_content_title.text = title
	_content_body.text = body


func set_active_tab(tab: String) -> void:
	for button in _tabs.get_children():
		if button is Button:
			(button as Button).disabled = button.name.to_lower() == tab


func set_prepare_ready(ready: bool) -> void:
	%StartAction.disabled = not ready
	%CompleteAction.disabled = not ready
	%RefreshAction.disabled = not ready


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


func _on_tab_pressed(tab: String) -> void:
	for button in _tabs.get_children():
		if button is Button:
			(button as Button).disabled = button.name.to_lower() == tab
	tab_requested.emit(tab)


func _apply_theme() -> void:
	var frame := MainlineTheme._box(MainlineTheme.C_PANEL, MainlineTheme.C_GOLD, 2, 8)
	frame.content_margin_left = 20
	frame.content_margin_right = 20
	frame.content_margin_top = 18
	frame.content_margin_bottom = 18
	add_theme_stylebox_override("panel", frame)
	for panel in [%RosterPanel, %ContentPanel, %MissionPanel]:
		MainlineTheme.apply_section_panel(panel, MainlineTheme.C_GOLD)
	for button in _tabs.get_children():
		MainlineTheme.apply_tab(button)
	MainlineTheme.apply_secondary(%BackAction)
	MainlineTheme.apply_secondary(%RefreshAction)
	MainlineTheme.apply_option(%ChoiceSelect)
	MainlineTheme.apply_primary(%StartAction)
	MainlineTheme.apply_danger(%AbandonAction)
	for label in [_content_title, _mission_title, %CouncilTitle]:
		label.add_theme_color_override("font_color", MainlineTheme.C_GOLD_BRIGHT)
