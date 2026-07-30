extends Control
## editor_controller.gd — 地图编辑器视图控制器(P2 从 main.gd 抽离)。
## 挂在场景 EditorView 节点上,自管面板内部逻辑;view 可见性仍由 main._show_view 控制。
## 对外接口:
##   open()                  — main 切到 editor view 后调用:初始化选项 + 拉取地图列表
##   request_undo/redo()     — 供 main 的 Ctrl+Z/Y 快捷键转发
##   signal back_requested   — 用户点返回 → main 切回 menu
##   signal map_saved(map)   — 保存成功 → main upsert lobby 自定义地图预设
##   unit_label_fn: Callable — 注入 main._unit_type_cn(单位名中文化,多域共享)

signal back_requested
signal map_saved(map_data)

const MenuTheme = preload("res://scripts/ui/menu_theme.gd")

var unit_label_fn: Callable = Callable()

const _EDITOR_HISTORY_LIMIT := 50

@onready var editor_board = $EditorBoard
@onready var editor_map_name_input: LineEdit = $EditorPanel/EditorMapNameInput
@onready var editor_biome_option: OptionButton = $EditorPanel/EditorBiomeOption
@onready var editor_apply_biome_btn: Button = $EditorPanel/EditorApplyBiomeBtn
@onready var editor_terrain_option: OptionButton = $EditorPanel/EditorTerrainOption
@onready var editor_surface_option: OptionButton = $EditorPanel/EditorSurfaceOption
@onready var editor_map_select_option: OptionButton = $EditorPanel/EditorMapSelectOption
@onready var editor_load_btn: Button = $EditorPanel/EditorLoadBtn
@onready var editor_mode_option: OptionButton = $EditorPanel/EditorModeOption
@onready var editor_unit_tool_option: OptionButton = $EditorPanel/EditorUnitToolOption
@onready var editor_unit_option: OptionButton = $EditorPanel/EditorUnitOption
@onready var editor_unit_color_option: OptionButton = $EditorPanel/EditorUnitColorOption
@onready var editor_surface_owner_option: OptionButton = $EditorPanel/EditorSurfaceOwnerOption
@onready var editor_unit_level_option: OptionButton = $EditorPanel/EditorUnitLevelOption
@onready var editor_width_option: OptionButton = $EditorPanel/EditorWidthOption
@onready var editor_height_option: OptionButton = $EditorPanel/EditorHeightOption
@onready var editor_resize_btn: Button = $EditorPanel/EditorResizeBtn
@onready var editor_undo_btn: Button = $EditorPanel/EditorUndoBtn
@onready var editor_redo_btn: Button = $EditorPanel/EditorRedoBtn
@onready var editor_status: Label = $EditorPanel/EditorStatus
@onready var editor_new_btn: Button = $EditorPanel/EditorNewBtn
@onready var editor_save_btn: Button = $EditorPanel/EditorSaveBtn
@onready var editor_delete_btn: Button = $EditorPanel/EditorDeleteBtn
@onready var editor_back_btn: Button = $EditorPanel/EditorBackBtn

var _editor_map: Dictionary = {}
var _editor_map_ids: Array[String] = []
var _selected_editor_map_id: String = ""
var _editor_terrain_chars: Array[String] = ["P", "F", "M", "R", "r", "S"]
var _editor_surface_chars: Array[String] = ["C", "v", "b", "g"]
var _editor_unit_types: Array[String] = [
	"swordsman", "archer", "knight", "healer", "warlock",
	"lancer", "warrior", "berserker", "dragon_rider", "falcon_knight",
	"blade_master", "paladin", "sniper", "sage", "saint",
]
var _editor_unit_colors: Array[String] = ["red", "blue", "green", "yellow"]
var _editor_owner_colors: Array[String] = ["", "red", "blue", "green", "yellow"]
var _editor_size_choices: Array[int] = [15, 20, 25, 30, 35, 40, 45]
var _editor_undo_stack: Array[Dictionary] = []
var _editor_redo_stack: Array[Dictionary] = []


func _ready() -> void:
	editor_new_btn.pressed.connect(_on_editor_new_pressed)
	editor_save_btn.pressed.connect(_on_editor_save_pressed)
	editor_load_btn.pressed.connect(_on_editor_load_pressed)
	editor_delete_btn.pressed.connect(_on_editor_delete_pressed)
	editor_apply_biome_btn.pressed.connect(_on_editor_apply_biome_pressed)
	editor_resize_btn.pressed.connect(_on_editor_resize_pressed)
	editor_undo_btn.pressed.connect(_on_editor_undo_pressed)
	editor_redo_btn.pressed.connect(_on_editor_redo_pressed)
	editor_map_select_option.item_selected.connect(_on_editor_map_selected)
	editor_mode_option.item_selected.connect(_on_editor_mode_selected)
	editor_back_btn.pressed.connect(_on_editor_back_pressed)
	if not editor_board.tile_clicked.is_connected(_on_editor_tile_clicked):
		editor_board.tile_clicked.connect(_on_editor_tile_clicked)
	# P2: GBA 火纹主题(原在 main._apply_gba_theme 的按钮列表里,随组件一起搬来)
	for btn in [editor_new_btn, editor_save_btn, editor_load_btn, editor_delete_btn, editor_resize_btn, editor_back_btn]:
		if btn != null and is_instance_valid(btn):
			MenuTheme.apply_button_theme(btn, MenuTheme.FS_BTN)


func open() -> void:
	_setup_editor_options()
	if _editor_map.is_empty():
		_editor_map = _build_blank_editor_map()
		_reset_editor_history()
	_render_editor_map()
	if editor_status != null and is_instance_valid(editor_status):
		editor_status.text = "地图编辑器已就绪。"
	NetworkClient.list_editor_maps(Callable(self, "_on_editor_maps_response"))


func request_undo() -> void:
	_on_editor_undo_pressed()


func request_redo() -> void:
	_on_editor_redo_pressed()


func _setup_editor_options() -> void:
	if editor_biome_option != null and is_instance_valid(editor_biome_option):
		editor_biome_option.clear()
		for biome in ["grass", "snow", "desert"]:
			editor_biome_option.add_item(_editor_biome_label(biome))
		editor_biome_option.select(0)
	if editor_terrain_option != null and is_instance_valid(editor_terrain_option):
		editor_terrain_option.clear()
		for terrain_char in _editor_terrain_chars:
			editor_terrain_option.add_item(_editor_terrain_label(terrain_char))
		editor_terrain_option.select(0)
	if editor_surface_option != null and is_instance_valid(editor_surface_option):
		editor_surface_option.clear()
		for surface_char in _editor_surface_chars:
			editor_surface_option.add_item(_editor_terrain_label(surface_char))
		editor_surface_option.select(0)
	if editor_mode_option != null and is_instance_valid(editor_mode_option):
		editor_mode_option.clear()
		editor_mode_option.add_item("地形部署")
		editor_mode_option.add_item("地表部署")
		editor_mode_option.add_item("单位部署")
		editor_mode_option.select(0)
	if editor_unit_tool_option != null and is_instance_valid(editor_unit_tool_option):
		editor_unit_tool_option.clear()
		editor_unit_tool_option.add_item("放置")
		editor_unit_tool_option.add_item("擦除")
		editor_unit_tool_option.select(0)
	if editor_unit_option != null and is_instance_valid(editor_unit_option):
		editor_unit_option.clear()
		for unit_type in _editor_unit_types:
			editor_unit_option.add_item(unit_label_fn.call(unit_type))
		editor_unit_option.select(0)
	if editor_unit_color_option != null and is_instance_valid(editor_unit_color_option):
		editor_unit_color_option.clear()
		for color in _editor_unit_colors:
			editor_unit_color_option.add_item(_team_color_label(color))
		editor_unit_color_option.select(0)
	if editor_surface_owner_option != null and is_instance_valid(editor_surface_owner_option):
		editor_surface_owner_option.clear()
		for color in _editor_owner_colors:
			editor_surface_owner_option.add_item(_owner_color_label(color))
		editor_surface_owner_option.select(0)
	if editor_unit_level_option != null and is_instance_valid(editor_unit_level_option):
		editor_unit_level_option.clear()
		for level in range(1, 11):
			editor_unit_level_option.add_item("等级 %d" % level)
		editor_unit_level_option.select(0)
	if editor_width_option != null and is_instance_valid(editor_width_option):
		editor_width_option.clear()
		for size in _editor_size_choices:
			editor_width_option.add_item("宽 %d" % size)
		editor_width_option.select(0)
	if editor_height_option != null and is_instance_valid(editor_height_option):
		editor_height_option.clear()
		for size in _editor_size_choices:
			editor_height_option.add_item("高 %d" % size)
		editor_height_option.select(0)
	if editor_map_name_input != null and is_instance_valid(editor_map_name_input):
		if editor_map_name_input.text.strip_edges() == "":
			editor_map_name_input.text = "自定义地图"
	_update_editor_mode_controls()


func _editor_terrain_label(terrain_char: String) -> String:
	match terrain_char:
		"P":
			return "平原"
		"F":
			return "森林"
		"M":
			return "山地"
		"R":
			return "河流"
		"C":
			return "城堡"
		"v":
			return "村庄"
		"b":
			return "兵营"
		"r":
			return "道路"
		"g":
			return "城门"
		"S":
			return "雪峰"
		_:
			return terrain_char


func _editor_biome_label(biome: String) -> String:
	match biome:
		"grass":
			return "草原"
		"snow":
			return "雪地"
		"desert":
			return "沙漠"
		_:
			return biome


func _team_color_label(color_name: String) -> String:
	match color_name:
		"red":
			return "红方"
		"blue":
			return "蓝方"
		"green":
			return "绿方"
		"yellow":
			return "黄方"
		_:
			return color_name


func _owner_color_label(color_name: String) -> String:
	if color_name == "":
		return "无主"
	return _team_color_label(color_name)


func _selected_editor_biome() -> String:
	if editor_biome_option == null or not is_instance_valid(editor_biome_option):
		return "grass"
	match editor_biome_option.selected:
		1:
			return "snow"
		2:
			return "desert"
		_:
			return "grass"


func _selected_editor_terrain_char() -> String:
	if editor_terrain_option == null or not is_instance_valid(editor_terrain_option):
		return "P"
	var index := editor_terrain_option.selected
	if index < 0 or index >= _editor_terrain_chars.size():
		return "P"
	return _editor_terrain_chars[index]


func _selected_editor_surface_char() -> String:
	if editor_surface_option == null or not is_instance_valid(editor_surface_option):
		return "C"
	var index := editor_surface_option.selected
	if index < 0 or index >= _editor_surface_chars.size():
		return "C"
	return _editor_surface_chars[index]


func _selected_editor_surface_owner_color() -> String:
	if editor_surface_owner_option == null or not is_instance_valid(editor_surface_owner_option):
		return ""
	var index := editor_surface_owner_option.selected
	if index < 0 or index >= _editor_owner_colors.size():
		return ""
	return _editor_owner_colors[index]


func _selected_editor_mode() -> String:
	if editor_mode_option == null or not is_instance_valid(editor_mode_option):
		return "terrain"
	match editor_mode_option.selected:
		1:
			return "surface"
		2:
			return "unit"
		_:
			return "terrain"


func _on_editor_mode_selected(_index: int) -> void:
	_update_editor_mode_controls()


func _update_editor_mode_controls() -> void:
	var mode := _selected_editor_mode()
	if editor_terrain_option != null and is_instance_valid(editor_terrain_option):
		editor_terrain_option.visible = mode == "terrain"
	if editor_surface_option != null and is_instance_valid(editor_surface_option):
		editor_surface_option.visible = mode == "surface"
	if editor_surface_owner_option != null and is_instance_valid(editor_surface_owner_option):
		editor_surface_owner_option.visible = mode == "surface"
	if editor_unit_tool_option != null and is_instance_valid(editor_unit_tool_option):
		editor_unit_tool_option.visible = mode == "unit"
	if editor_unit_option != null and is_instance_valid(editor_unit_option):
		editor_unit_option.visible = mode == "unit"
	if editor_unit_color_option != null and is_instance_valid(editor_unit_color_option):
		editor_unit_color_option.visible = mode == "unit"
	if editor_unit_level_option != null and is_instance_valid(editor_unit_level_option):
		editor_unit_level_option.visible = mode == "unit"


func _is_editor_unit_mode() -> bool:
	return _selected_editor_mode() == "unit"


func _is_editor_surface_mode() -> bool:
	return _selected_editor_mode() == "surface"


func _selected_editor_unit_type() -> String:
	if editor_unit_option == null or not is_instance_valid(editor_unit_option):
		return "swordsman"
	var index := editor_unit_option.selected
	if index < 0 or index >= _editor_unit_types.size():
		return "swordsman"
	return _editor_unit_types[index]


func _selected_editor_unit_color() -> String:
	if editor_unit_color_option == null or not is_instance_valid(editor_unit_color_option):
		return "red"
	var index := editor_unit_color_option.selected
	if index < 0 or index >= _editor_unit_colors.size():
		return "red"
	return _editor_unit_colors[index]


func _selected_editor_unit_level() -> int:
	if editor_unit_level_option == null or not is_instance_valid(editor_unit_level_option):
		return 1
	return clampi(editor_unit_level_option.selected + 1, 1, 10)


func _selected_editor_size(option: OptionButton) -> int:
	if option == null or not is_instance_valid(option):
		return 15
	var index := option.selected
	if index < 0 or index >= _editor_size_choices.size():
		return 15
	return _editor_size_choices[index]


func _select_editor_size_option(option: OptionButton, size: int) -> void:
	if option == null or not is_instance_valid(option):
		return
	var index := _editor_size_choices.find(size)
	if index < 0:
		index = 0
	option.select(index)


func _is_editor_unit_erase_mode() -> bool:
	return editor_unit_tool_option != null and is_instance_valid(editor_unit_tool_option) and editor_unit_tool_option.selected == 1


func _build_blank_editor_map() -> Dictionary:
	var rows: Array[String] = []
	for _y in range(15):
		rows.append("P".repeat(15))
	var name := "自定义地图"
	if editor_map_name_input != null and is_instance_valid(editor_map_name_input):
		var typed := editor_map_name_input.text.strip_edges()
		if typed != "":
			name = typed
	return {
		"name": name,
		"size": {"width": 15, "height": 15},
		"biome": _selected_editor_biome(),
		"layout": rows,
		"initial_units": [],
		"tile_owners": [],
	}


func _render_editor_map() -> void:
	if editor_board == null or not is_instance_valid(editor_board):
		return
	if _editor_map.is_empty():
		return
	editor_board.load_map(_editor_map)
	_update_editor_history_buttons()


func _snapshot_editor_map() -> Dictionary:
	if _editor_map.is_empty():
		return {}
	return (_editor_map.duplicate(true) as Dictionary)


func _push_editor_history() -> void:
	var snapshot := _snapshot_editor_map()
	if snapshot.is_empty():
		return
	_editor_undo_stack.append(snapshot)
	if _editor_undo_stack.size() > _EDITOR_HISTORY_LIMIT:
		_editor_undo_stack.pop_front()
	_editor_redo_stack.clear()
	_update_editor_history_buttons()


func _reset_editor_history() -> void:
	_editor_undo_stack.clear()
	_editor_redo_stack.clear()
	_update_editor_history_buttons()


func _update_editor_history_buttons() -> void:
	if editor_undo_btn != null and is_instance_valid(editor_undo_btn):
		editor_undo_btn.disabled = _editor_undo_stack.is_empty()
	if editor_redo_btn != null and is_instance_valid(editor_redo_btn):
		editor_redo_btn.disabled = _editor_redo_stack.is_empty()


func _restore_editor_snapshot(snapshot: Dictionary) -> void:
	_editor_map = snapshot.duplicate(true)
	var size: Dictionary = _editor_map.get("size", {})
	_select_editor_size_option(editor_width_option, int(size.get("width", 15)))
	_select_editor_size_option(editor_height_option, int(size.get("height", 15)))
	if editor_map_name_input != null and is_instance_valid(editor_map_name_input):
		editor_map_name_input.text = str(_editor_map.get("name", "自定义地图"))
	if editor_biome_option != null and is_instance_valid(editor_biome_option):
		match str(_editor_map.get("biome", "grass")):
			"snow":
				editor_biome_option.select(1)
			"desert":
				editor_biome_option.select(2)
			_:
				editor_biome_option.select(0)
	_render_editor_map()


func _on_editor_undo_pressed() -> void:
	if _editor_undo_stack.is_empty():
		return
	var current := _snapshot_editor_map()
	if not current.is_empty():
		_editor_redo_stack.append(current)
	var previous: Dictionary = _editor_undo_stack.pop_back()
	_restore_editor_snapshot(previous)
	if editor_status != null and is_instance_valid(editor_status):
		editor_status.text = "已撤销上一步编辑。"
	_update_editor_history_buttons()


func _on_editor_redo_pressed() -> void:
	if _editor_redo_stack.is_empty():
		return
	var current := _snapshot_editor_map()
	if not current.is_empty():
		_editor_undo_stack.append(current)
	var next: Dictionary = _editor_redo_stack.pop_back()
	_restore_editor_snapshot(next)
	if editor_status != null and is_instance_valid(editor_status):
		editor_status.text = "已重做上一步编辑。"
	_update_editor_history_buttons()


func _paint_editor_tile(tile: Vector2i) -> void:
	if _editor_map.is_empty():
		_editor_map = _build_blank_editor_map()
	var size: Dictionary = _editor_map.get("size", {})
	var width := int(size.get("width", 0))
	var height := int(size.get("height", 0))
	if tile.x < 0 or tile.y < 0 or tile.x >= width or tile.y >= height:
		return
	var layout: Array = _editor_map.get("layout", [])
	if tile.y >= layout.size():
		return
	var row := str(layout[tile.y])
	if tile.x >= row.length():
		return
	var terrain_char := _selected_editor_terrain_char()
	if row.substr(tile.x, 1) == terrain_char:
		return
	_push_editor_history()
	layout[tile.y] = row.substr(0, tile.x) + terrain_char + row.substr(tile.x + 1)
	_editor_map["layout"] = layout
	_render_editor_map()
	if editor_status != null and is_instance_valid(editor_status):
		editor_status.text = "已在 %d,%d 绘制 %s" % [tile.x, tile.y, _editor_terrain_label(terrain_char)]


func _set_editor_tile_owner(tile: Vector2i, color: String) -> void:
	var owners: Array = _editor_map.get("tile_owners", [])
	var next_owners: Array = []
	for owner in owners:
		if not owner is Dictionary:
			continue
		if int(owner.get("x", -1)) == tile.x and int(owner.get("y", -1)) == tile.y:
			continue
		next_owners.append(owner)
	if color != "":
		next_owners.append({"x": tile.x, "y": tile.y, "color": color})
	_editor_map["tile_owners"] = next_owners


func _paint_editor_surface(tile: Vector2i) -> void:
	if _editor_map.is_empty():
		_editor_map = _build_blank_editor_map()
	var size: Dictionary = _editor_map.get("size", {})
	var width := int(size.get("width", 0))
	var height := int(size.get("height", 0))
	if tile.x < 0 or tile.y < 0 or tile.x >= width or tile.y >= height:
		return
	var layout: Array = _editor_map.get("layout", [])
	if tile.y >= layout.size():
		return
	var row := str(layout[tile.y])
	if tile.x >= row.length():
		return
	var surface_char := _selected_editor_surface_char()
	var owner_color := _selected_editor_surface_owner_color()
	var old_owner := ""
	for owner in _editor_map.get("tile_owners", []):
		if owner is Dictionary and int(owner.get("x", -1)) == tile.x and int(owner.get("y", -1)) == tile.y:
			old_owner = str(owner.get("color", ""))
			break
	if row.substr(tile.x, 1) == surface_char and old_owner == owner_color:
		return
	_push_editor_history()
	layout[tile.y] = row.substr(0, tile.x) + surface_char + row.substr(tile.x + 1)
	_editor_map["layout"] = layout
	_set_editor_tile_owner(tile, owner_color)
	_render_editor_map()
	if editor_status != null and is_instance_valid(editor_status):
		editor_status.text = "已在 %d,%d 部署%s（%s）" % [
			tile.x, tile.y, _editor_terrain_label(surface_char), _owner_color_label(owner_color)
		]


func _on_editor_tile_clicked(tile: Vector2i) -> void:
	if _is_editor_unit_mode():
		if _is_editor_unit_erase_mode():
			_erase_editor_unit(tile)
			return
		_place_editor_unit(tile)
		return
	if _is_editor_surface_mode():
		_paint_editor_surface(tile)
		return
	_paint_editor_tile(tile)


func _erase_editor_unit(tile: Vector2i) -> void:
	if _editor_map.is_empty():
		return
	var units: Array = _editor_map.get("initial_units", [])
	var next_units: Array = []
	var removed := false
	for unit in units:
		if not unit is Dictionary:
			continue
		if int(unit.get("x", -1)) == tile.x and int(unit.get("y", -1)) == tile.y:
			removed = true
			continue
		next_units.append(unit)
	if removed:
		_push_editor_history()
		_editor_map["initial_units"] = next_units
		_render_editor_map()
		if editor_status != null and is_instance_valid(editor_status):
			editor_status.text = "已移除 %d,%d 的单位" % [tile.x, tile.y]


func _place_editor_unit(tile: Vector2i) -> void:
	if _editor_map.is_empty():
		_editor_map = _build_blank_editor_map()
	var size: Dictionary = _editor_map.get("size", {})
	var width := int(size.get("width", 0))
	var height := int(size.get("height", 0))
	if tile.x < 0 or tile.y < 0 or tile.x >= width or tile.y >= height:
		return
	var units: Array = _editor_map.get("initial_units", [])
	var next_units: Array = []
	for unit in units:
		if not unit is Dictionary:
			continue
		if int(unit.get("x", -1)) == tile.x and int(unit.get("y", -1)) == tile.y:
			continue
		next_units.append(unit)
	next_units.append({
		"x": tile.x,
		"y": tile.y,
		"type": _selected_editor_unit_type(),
		"color": _selected_editor_unit_color(),
		"level": _selected_editor_unit_level(),
	})
	_push_editor_history()
	_editor_map["initial_units"] = next_units
	_render_editor_map()
	if editor_status != null and is_instance_valid(editor_status):
		editor_status.text = "已在 %d,%d 放置%s" % [
			tile.x, tile.y, unit_label_fn.call(_selected_editor_unit_type())
		]


func _on_editor_new_pressed() -> void:
	if not _editor_map.is_empty():
		_push_editor_history()
	_editor_map = _build_blank_editor_map()
	_render_editor_map()
	if editor_status != null and is_instance_valid(editor_status):
		editor_status.text = "已新建 15×15 地图。"


func _on_editor_apply_biome_pressed() -> void:
	if _editor_map.is_empty():
		_editor_map = _build_blank_editor_map()
	var biome := _selected_editor_biome()
	if str(_editor_map.get("biome", "grass")) == biome:
		if editor_status != null and is_instance_valid(editor_status):
			editor_status.text = "生态分支未变化。"
		return
	_push_editor_history()
	_editor_map["biome"] = biome
	_render_editor_map()
	if editor_status != null and is_instance_valid(editor_status):
		editor_status.text = "已切换为%s生态。" % _editor_biome_label(biome)


func _on_editor_resize_pressed() -> void:
	if _editor_map.is_empty():
		_editor_map = _build_blank_editor_map()
	var new_width := _selected_editor_size(editor_width_option)
	var new_height := _selected_editor_size(editor_height_option)
	var current_size: Dictionary = _editor_map.get("size", {})
	if int(current_size.get("width", 0)) == new_width and int(current_size.get("height", 0)) == new_height:
		if editor_status != null and is_instance_valid(editor_status):
			editor_status.text = "尺寸未变化。"
		return
	var layout: Array = _editor_map.get("layout", [])
	var new_layout: Array[String] = []
	for y in range(new_height):
		var row := ""
		if y < layout.size():
			row = str(layout[y])
		if row.length() > new_width:
			row = row.substr(0, new_width)
		elif row.length() < new_width:
			row += "P".repeat(new_width - row.length())
		new_layout.append(row)
	var units: Array = _editor_map.get("initial_units", [])
	var kept_units: Array = []
	for unit in units:
		if unit is Dictionary and int(unit.get("x", -1)) < new_width and int(unit.get("y", -1)) < new_height:
			kept_units.append(unit)
	var tile_owners: Array = _editor_map.get("tile_owners", [])
	var kept_tile_owners: Array = []
	for owner in tile_owners:
		if owner is Dictionary and int(owner.get("x", -1)) < new_width and int(owner.get("y", -1)) < new_height:
			kept_tile_owners.append(owner)
	_push_editor_history()
	_editor_map["size"] = {"width": new_width, "height": new_height}
	_editor_map["layout"] = new_layout
	_editor_map["initial_units"] = kept_units
	_editor_map["tile_owners"] = kept_tile_owners
	_render_editor_map()
	if editor_status != null and is_instance_valid(editor_status):
		editor_status.text = "已调整为 %d×%d" % [new_width, new_height]


func _on_editor_load_pressed() -> void:
	if _selected_editor_map_id == "":
		if editor_status != null and is_instance_valid(editor_status):
			editor_status.text = "请先选择已保存地图。"
		return
	if editor_status != null and is_instance_valid(editor_status):
		editor_status.text = "正在加载 %s..." % _selected_editor_map_id
	NetworkClient.load_editor_map(_selected_editor_map_id, Callable(self, "_on_editor_load_response"))


func _on_editor_delete_pressed() -> void:
	if _selected_editor_map_id == "":
		if editor_status != null and is_instance_valid(editor_status):
			editor_status.text = "请先选择已保存地图。"
		return
	if editor_status != null and is_instance_valid(editor_status):
		editor_status.text = "正在删除 %s..." % _selected_editor_map_id
	NetworkClient.delete_editor_map(_selected_editor_map_id, Callable(self, "_on_editor_delete_response"))


func _on_editor_save_pressed() -> void:
	if _editor_map.is_empty():
		_editor_map = _build_blank_editor_map()
	var name := str(_editor_map.get("name", "Godot custom map"))
	if editor_map_name_input != null and is_instance_valid(editor_map_name_input):
		var typed := editor_map_name_input.text.strip_edges()
		if typed != "":
			name = typed
	_editor_map["name"] = name
	_editor_map["biome"] = _selected_editor_biome()
	if not _editor_map.has("tile_owners"):
		_editor_map["tile_owners"] = []
	if editor_status != null and is_instance_valid(editor_status):
		editor_status.text = "正在保存地图..."
	NetworkClient.save_editor_map(_editor_map, Callable(self, "_on_editor_save_response"))


func _on_editor_back_pressed() -> void:
	back_requested.emit()


func _on_editor_maps_response(body: Variant, code: int = 0) -> void:
	if editor_map_select_option == null or not is_instance_valid(editor_map_select_option):
		return
	editor_map_select_option.clear()
	_editor_map_ids = []
	_selected_editor_map_id = ""
	if code < 200 or code >= 300 or not (body is Array):
		editor_map_select_option.add_item("暂无已保存地图")
		if editor_load_btn != null and is_instance_valid(editor_load_btn):
			editor_load_btn.disabled = true
		if editor_delete_btn != null and is_instance_valid(editor_delete_btn):
			editor_delete_btn.disabled = true
		return
	var maps: Array = body
	if maps.is_empty():
		editor_map_select_option.add_item("暂无已保存地图")
		if editor_load_btn != null and is_instance_valid(editor_load_btn):
			editor_load_btn.disabled = true
		if editor_delete_btn != null and is_instance_valid(editor_delete_btn):
			editor_delete_btn.disabled = true
		return
	for item in maps:
		if not item is Dictionary:
			continue
		var map_id := str(item.get("id", ""))
		var name := str(item.get("name", map_id))
		if map_id != "":
			_editor_map_ids.append(map_id)
			editor_map_select_option.add_item("%s (%s)" % [name, map_id])
	if not _editor_map_ids.is_empty():
		_selected_editor_map_id = _editor_map_ids[0]
		editor_map_select_option.select(0)
	if editor_load_btn != null and is_instance_valid(editor_load_btn):
		editor_load_btn.disabled = _selected_editor_map_id == ""
	if editor_delete_btn != null and is_instance_valid(editor_delete_btn):
		editor_delete_btn.disabled = _selected_editor_map_id == ""


func _on_editor_map_selected(index: int) -> void:
	if index < 0 or index >= _editor_map_ids.size():
		_selected_editor_map_id = ""
	else:
		_selected_editor_map_id = _editor_map_ids[index]
	if editor_load_btn != null and is_instance_valid(editor_load_btn):
		editor_load_btn.disabled = _selected_editor_map_id == ""
	if editor_delete_btn != null and is_instance_valid(editor_delete_btn):
		editor_delete_btn.disabled = _selected_editor_map_id == ""


func _on_editor_load_response(body: Variant, code: int = 0) -> void:
	if code >= 200 and code < 300 and body is Dictionary:
		_editor_map = body
		_reset_editor_history()
		if editor_map_name_input != null and is_instance_valid(editor_map_name_input):
			editor_map_name_input.text = str(body.get("name", "自定义地图"))
		var biome := str(body.get("biome", "grass"))
		if editor_biome_option != null and is_instance_valid(editor_biome_option):
			match biome:
				"snow":
					editor_biome_option.select(1)
				"desert":
					editor_biome_option.select(2)
				_:
					editor_biome_option.select(0)
		var size: Dictionary = body.get("size", {})
		_select_editor_size_option(editor_width_option, int(size.get("width", 15)))
		_select_editor_size_option(editor_height_option, int(size.get("height", 15)))
		_render_editor_map()
		if editor_status != null and is_instance_valid(editor_status):
			editor_status.text = "已加载: %s" % str(body.get("id", "自定义地图"))
		return
	if editor_status != null and is_instance_valid(editor_status):
		editor_status.text = "加载失败"


func _on_editor_delete_response(_body: Variant, code: int = 0) -> void:
	if code >= 200 and code < 300:
		_selected_editor_map_id = ""
		_editor_map_ids = []
		if editor_map_select_option != null and is_instance_valid(editor_map_select_option):
			editor_map_select_option.clear()
			editor_map_select_option.add_item("暂无已保存地图")
		if editor_load_btn != null and is_instance_valid(editor_load_btn):
			editor_load_btn.disabled = true
		if editor_delete_btn != null and is_instance_valid(editor_delete_btn):
			editor_delete_btn.disabled = true
		if editor_status != null and is_instance_valid(editor_status):
			editor_status.text = "已删除地图。"
		NetworkClient.list_editor_maps(Callable(self, "_on_editor_maps_response"))
		return
	if editor_status != null and is_instance_valid(editor_status):
		editor_status.text = "删除失败"


func _on_editor_save_response(body: Variant, code: int = 0) -> void:
	if code >= 200 and code < 300 and body is Dictionary:
		_editor_map = body
		_reset_editor_history()
		_render_editor_map()
		map_saved.emit(body)
		if editor_status != null and is_instance_valid(editor_status):
			editor_status.text = "已保存: %s" % str(body.get("id", "自定义地图"))
		NetworkClient.list_editor_maps(Callable(self, "_on_editor_maps_response"))
		return
	if editor_status != null and is_instance_valid(editor_status):
		editor_status.text = "保存失败"
