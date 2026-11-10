extends CanvasLayer
## 控件只发操作信号，地形与存储规则由主场景调用模型处理。

signal action(name: String)
signal height_changed(value: int)
signal terrain_changed(value: String)
signal pitch_changed(value: float)
signal preset_changed(value: String)

var selected_label: Label
var dimensions_label: Label
var status: Label
var height_input: SpinBox
var terrain_input: OptionButton
var pitch_input: HSlider
var angle_label: Label
var preset_input: OptionButton
var detail_label: Label
var buttons: Dictionary = {}
var file_dialog: FileDialog
var syncing := false
var editing_enabled := true

func _ready() -> void:
	var root := Control.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(root)
	var panel := PanelContainer.new()
	panel.position = Vector2(20, 20)
	panel.custom_minimum_size = Vector2(290, 680)
	root.add_child(panel)
	var margin := MarginContainer.new()
	for side in ["left", "top", "right", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 16)
	panel.add_child(margin)
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	margin.add_child(scroll)
	var box := VBoxContainer.new()
	box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	box.add_theme_constant_override("separation", 5)
	scroll.add_child(box)
	_label(box, "高差地图 · 独立试验场", 21)
	preset_input = OptionButton.new()
	preset_input.add_item("2人标准图 · 建筑与预设单位")
	preset_input.add_item("高度试验场 · 极限高差")
	box.add_child(preset_input)
	preset_input.item_selected.connect(func(i: int): preset_changed.emit("standard" if i == 0 else "sandbox"))
	dimensions_label = _label(box, "", 15)
	selected_label = _label(box, "", 17)
	detail_label = _label(box,"",14)
	detail_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	detail_label.custom_minimum_size.x = 240
	var teams := HBoxContainer.new()
	box.add_child(teams)
	_button(teams,"定位红方","red")
	_button(teams,"定位蓝方","blue")
	var row := HBoxContainer.new()
	box.add_child(row)
	_button(row, "降低", "lower")
	height_input = SpinBox.new()
	height_input.step = 1
	height_input.custom_minimum_size.x = 94
	row.add_child(height_input)
	height_input.value_changed.connect(func(v: float):
		if not syncing:
			height_changed.emit(int(v)))
	_button(row, "升高", "raise")
	var edits := HBoxContainer.new()
	box.add_child(edits)
	_button(edits, "归零", "zero")
	_button(edits, "撤销", "undo")
	_button(edits, "重做", "redo")
	terrain_input = OptionButton.new()
	for name_zh in ["草地", "岩石", "沙地", "水面"]:
		terrain_input.add_item(name_zh)
	box.add_child(terrain_input)
	terrain_input.item_selected.connect(func(i: int):
		if not syncing:
			terrain_changed.emit(["grass", "rock", "sand", "water"][i]))
	var toggles := HBoxContainer.new()
	box.add_child(toggles)
	_button(toggles, "基准网格", "grid")
	_button(toggles, "角色显隐", "unit")
	var rotate := HBoxContainer.new()
	box.add_child(rotate)
	_button(rotate, "左转", "left")
	_button(rotate, "视角复位", "reset")
	_button(rotate, "右转", "right")
	angle_label = _label(box, "", 15)
	var inspect := HBoxContainer.new()
	box.add_child(inspect)
	_button(inspect, "聚焦选格", "focus")
	_button(inspect, "透视选中", "xray")
	buttons.xray.toggle_mode = true
	_label(box, "俯角（20°～60°）", 15)
	pitch_input = HSlider.new()
	pitch_input.min_value = 20
	pitch_input.max_value = 60
	pitch_input.value = 30
	box.add_child(pitch_input)
	pitch_input.value_changed.connect(func(v: float): pitch_changed.emit(v))
	var files := HBoxContainer.new()
	box.add_child(files)
	_button(files, "保存", "save")
	_button(files, "加载", "load")
	_button(files, "另存为", "files")
	_button(box, "打开地图文件…", "open")
	status = _label(box, "点击顶面选格；侧面不可点穿", 15)
	status.custom_minimum_size.x = 250
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_label(box, "拖动平移 · 右键旋转 · 滚轮缩放\n方向键光标 · Q/E转向 · F聚焦\n加减升降 · Ctrl+S保存 · Ctrl+Z/Y撤销", 13)
	file_dialog = FileDialog.new()
	file_dialog.access = FileDialog.ACCESS_FILESYSTEM
	file_dialog.filters = PackedStringArray(["*.json ; 地图文件"])
	root.add_child(file_dialog)

func _label(parent: Node, text: String, font_size: int) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", font_size)
	parent.add_child(label)
	return label

func _button(parent: Node, text: String, key: String) -> void:
	var button := Button.new()
	button.text = text
	button.custom_minimum_size = Vector2(72, 34)
	button.pressed.connect(func(): action.emit(key))
	parent.add_child(button)
	buttons[key] = button

func sync(model: RefCounted, p: Vector2i) -> void:
	syncing = true
	preset_input.select(0 if model.map_id == "balanced_2p_15" else 1)
	dimensions_label.text = "%d × %d 方格｜高度 %+d ～ %+d" % [model.size().x, model.size().y, model.settings.min_height, model.settings.max_height]
	selected_label.text = "选中 (%d, %d) · 高度 %+d" % [p.x, p.y, model.elevation(p)]
	var feature: String = model.cell(p).get("feature", "")
	var source: String = model.cell(p).get("source_terrain", "")
	detail_label.text = model.rules.source_names.get(source, model.rules.feature_names[feature])
	if feature in ["castle","village","barracks"]:
		detail_label.text += " · " + String(model.rules.factions[model.cell(p).get("faction","neutral")].name)
	var occupant: Dictionary = model.unit_at(p)
	if not occupant.is_empty():
		detail_label.text += "｜%s %s %d级" % [model.rules.factions[occupant.color].name,model.rules.unit_names[occupant.type],occupant.level]
	buttons.red.disabled = model.units.is_empty()
	buttons.blue.disabled = model.units.is_empty()
	height_input.min_value = model.settings.min_height
	height_input.max_value = model.settings.max_height
	height_input.value = model.elevation(p)
	terrain_input.select(model.TERRAINS.find(model.cell(p).terrain))
	buttons.lower.disabled = not editing_enabled or model.elevation(p) <= int(model.settings.min_height)
	buttons.raise.disabled = not editing_enabled or model.elevation(p) >= int(model.settings.max_height)
	buttons.undo.disabled = not editing_enabled or model.undo_stack.is_empty()
	buttons.redo.disabled = not editing_enabled or model.redo_stack.is_empty()
	syncing = false

func set_editing_enabled(enabled: bool) -> void:
	editing_enabled = enabled
	preset_input.disabled = not enabled
	height_input.editable = enabled
	terrain_input.disabled = not enabled
	for key in ["raise","lower","zero","undo","redo","save","load","files","open"]:
		buttons[key].disabled = not enabled

func sync_camera(camera: Camera3D) -> void:
	angle_label.text = "方位 %03d° · 俯角 %02d°" % [roundi(fposmod(camera.yaw, 360.0)) % 360, roundi(camera.pitch)]
	pitch_input.set_value_no_signal(camera.pitch)
