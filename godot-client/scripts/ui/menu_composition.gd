extends Node
## 标题页构图；保留原控件路径和信号，只调整视觉层级。
const Visual = preload("res://scripts/ui/visual_tokens.gd")
var page: Control

func setup(menu: Control) -> void:
	page = menu
	var gradient := Gradient.new()
	gradient.colors = PackedColorArray([Color("#101b29f5"), Color("#101b29e8"), Color("#101b2900")])
	gradient.offsets = PackedFloat32Array([0.0, 0.32, 0.76])
	var texture := GradientTexture2D.new()
	texture.gradient = gradient
	texture.fill_to = Vector2.RIGHT
	var shade := TextureRect.new()
	shade.name = "NavigationScrim"
	shade.texture = texture
	shade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	page.add_child(shade)
	page.move_child(shade, 2)
	shade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var quick_join := page.get_node("CenterContainer/GroupRow/MultiCard/JoinByCodeRow") as Control
	quick_join.visible = false
	var toggle := Button.new()
	toggle.text = "使用房间号加入  ›"
	toggle.alignment = HORIZONTAL_ALIGNMENT_LEFT
	Visual.button(toggle, false, 18)
	quick_join.get_parent().add_child(toggle)
	toggle.pressed.connect(func(): quick_join.visible = not quick_join.visible)
	page.get_viewport().size_changed.connect(layout)
	page.visibility_changed.connect(layout)
	call_deferred("layout")

func layout() -> void:
	if page == null:
		return
	var column := page.get_node("CenterContainer") as VBoxContainer
	column.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
	column.position = Vector2(100, 150)
	column.size = Vector2(480, 770)
	column.alignment = BoxContainer.ALIGNMENT_BEGIN
	column.add_theme_constant_override("separation", 18)
	for path in ["GroupRow/SoloCard", "GroupRow/MultiCard", "FooterRow"]:
		(column.get_node(path) as Control).custom_minimum_size.x = 0
	for path in ["TitleBlock/TitleLine1", "TitleBlock/TitleLine2"]:
		var label := column.get_node(path) as Label
		label.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
	column.get_node("TitleBlock/TitleLine1").add_theme_font_size_override("font_size", 66)
	column.get_node("TitleBlock/TitleLine2").add_theme_font_size_override("font_size", 23)
	for path in ["GroupRow/SoloCard/SoloCardTitle", "GroupRow/MultiCard/MultiCardTitle"]:
		var label := column.get_node(path) as Label
		label.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
		label.add_theme_font_size_override("font_size", 16)
		label.add_theme_color_override("font_color", Visual.DIM)
	for path in ["GroupRow/SoloCard/MainlineButton", "GroupRow/MultiCard/LobbyButton"]:
		var button := column.get_node(path) as Button
		button.alignment = HORIZONTAL_ALIGNMENT_LEFT
		button.custom_minimum_size.y = 64
		Visual.button(button, path.contains("Mainline"), 28)
	var footer := column.get_node("FooterRow") as GridContainer
	footer.columns = 3
	for child in footer.get_children():
		if child is Button:
			child.custom_minimum_size = Vector2(148, 46)
			Visual.button(child, false, 18)
	var quick_join := column.get_node("GroupRow/MultiCard/JoinByCodeRow")
	quick_join.get_node("JoinByCodeInput").custom_minimum_size.x = 260
	quick_join.get_node("JoinByCodeButton").custom_minimum_size.x = 170
	var footer_label := page.get_node("Footer/FooterLabel") as Label
	footer_label.text = "选择征程 · 编成队伍 · 书写战记"
	footer_label.add_theme_color_override("font_color", Visual.DIM)
