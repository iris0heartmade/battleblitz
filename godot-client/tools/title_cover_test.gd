extends Node

var _failed: int = 0
var _passed: int = 0


func _ready() -> void:
	var main_scene: PackedScene = load("res://scenes/main.tscn")
	var main = main_scene.instantiate()
	add_child(main)
	await get_tree().process_frame

	var title_cover: TextureRect = main.get_node_or_null("Menu/TitleCover")
	var picker: OptionButton = main.get_node_or_null("Menu/TitleCoverDevPicker")
	var center_container: VBoxContainer = main.get_node_or_null("Menu/CenterContainer")
	var group_row: VBoxContainer = main.get_node_or_null("Menu/CenterContainer/GroupRow")
	var footer_row: HBoxContainer = main.get_node_or_null("Menu/CenterContainer/FooterRow")
	var mainline_button: Button = main.get_node_or_null("Menu/CenterContainer/GroupRow/SoloCard/MainlineButton")
	var lobby_button: Button = main.get_node_or_null("Menu/CenterContainer/GroupRow/MultiCard/LobbyButton")
	_assert_true("TitleCover exists", title_cover != null)
	if title_cover != null:
		_assert_eq("TitleCover stretch cover", title_cover.stretch_mode, TextureRect.STRETCH_KEEP_ASPECT_COVERED)
		_assert_eq("TitleCover ignores mouse", title_cover.mouse_filter, Control.MOUSE_FILTER_IGNORE)
		_assert_true("TitleCover texture loaded", title_cover.texture != null)
	_assert_true("menu action stack exists", center_container != null)
	if center_container != null:
		_assert_true("menu actions sit in right title-safe area", center_container.anchor_left >= 0.62 and center_container.anchor_right >= 0.62)
		_assert_true("menu action stack is compact enough for cover art", center_container.offset_right - center_container.offset_left <= 520.0)
	_assert_true("primary actions are vertical", group_row != null)
	if group_row != null:
		_assert_eq("primary action stack type", group_row.get_class(), "VBoxContainer")
	_assert_true("utility actions stay horizontal", footer_row != null)
	if footer_row != null:
		_assert_eq("utility action row type", footer_row.get_class(), "HBoxContainer")
	_assert_true("mainline button is prominent", mainline_button != null and mainline_button.custom_minimum_size.y >= 72.0)
	_assert_true("lobby button is secondary but large", lobby_button != null and lobby_button.custom_minimum_size.y >= 60.0)
	_assert_true("default cover is previewable", main.title_cover_paths.has(main.title_cover_default_path))
	_assert_true("dev picker exists", picker != null)
	if picker != null:
		_assert_eq("dev picker candidate count", picker.item_count, 5)
		_assert_true("dev picker hidden by default", not picker.visible)
		for index in range(picker.item_count):
			picker.select(index)
			main._on_title_cover_dev_selected(index)
			_assert_true("dev picker can switch cover %d" % index, title_cover.texture != null)

	print("=== Title cover test: Passed: %d Failed: %d ===" % [_passed, _failed])
	get_tree().quit(1 if _failed > 0 else 0)


func _assert_true(label: String, cond: bool) -> void:
	if cond:
		_passed += 1
		print("  PASS  " + label)
	else:
		_failed += 1
		printerr("  FAIL  " + label)


func _assert_eq(label: String, got, expected) -> void:
	_assert_true("%s (got=%s expected=%s)" % [label, str(got), str(expected)], got == expected)
