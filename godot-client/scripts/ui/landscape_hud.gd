extends Control
## 通透地貌底栏：中层插画、局部阅读渐变、前层真实状态。无战斗规则写入。
const Visual = preload("res://scripts/ui/visual_tokens.gd")
const HEIGHT := 270.0
const ART_PATHS := {
	"grassland": "res://assets/ui/terrain_hud/grassland-v1.png",
	"forest": "res://assets/ui/terrain_hud/forest-v1.png",
	"rocky": "res://assets/ui/terrain_hud/rocky-v1.png",
	"sand": "res://assets/ui/terrain_hud/sand-v1.png",
	"waterside": "res://assets/ui/terrain_hud/waterside-v1.png",
	"settlement": "res://assets/ui/terrain_hud/settlement-v1.png",
}
var host: Node
var art: TextureRect
var portrait: TextureRect
var identity: RichTextLabel
var vitality: RichTextLabel
var stats: RichTextLabel
var ground: RichTextLabel
var prediction: RichTextLabel
var health: ProgressBar
var drawer := false
var compact_forecast := ""
var textures: Dictionary = {}
var last_portrait := ""
var last_art := ""
var last_signature := ""

func setup(owner_host: Node) -> void:
	host = owner_host
	name = "LandscapeHUD"
	# 底栏信息区吞掉鼠标，避免文字下方棋盘收到移动落点。
	mouse_filter = Control.MOUSE_FILTER_STOP
	set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
	offset_top = -HEIGHT
	art = TextureRect.new()
	art.mouse_filter = Control.MOUSE_FILTER_IGNORE
	art.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	art.stretch_mode = TextureRect.STRETCH_SCALE
	add_child(art)
	art.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	# 仅文字下方逐渐变暗；插画顶部与地图保持通透。
	for bounds in [Vector2(0.01, 0.52), Vector2(0.54, 0.99)]:
		var shade := TextureRect.new()
		var gradient := Gradient.new()
		gradient.colors = PackedColorArray([Color(0.035, 0.06, 0.09, 0), Color(0.035, 0.06, 0.09, 0.78)])
		var texture := GradientTexture2D.new()
		texture.gradient = gradient
		texture.fill_from = Vector2(0, 0)
		texture.fill_to = Vector2(0, 1)
		shade.texture = texture
		shade.mouse_filter = Control.MOUSE_FILTER_IGNORE
		add_child(shade)
		shade.anchor_left = bounds.x
		shade.anchor_right = bounds.y
		shade.anchor_bottom = 1
		shade.offset_top = 68
	portrait = TextureRect.new()
	portrait.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	portrait.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	portrait.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(portrait)
	portrait.position = Vector2(28, 72)
	portrait.size = Vector2(135, 192)
	identity = _text(0.09, 0.27)
	vitality = _text(0.28, 0.49)
	stats = _text(0.53, 0.75)
	ground = _text(0.77, 0.99)
	prediction = _text(0.53, 0.99)
	prediction.scroll_active = false
	prediction.offset_top = 44
	prediction.offset_bottom = -80
	prediction.mouse_filter = Control.MOUSE_FILTER_STOP
	health = ProgressBar.new()
	add_child(health)
	health.anchor_left = 0.28
	health.anchor_right = 0.48
	health.position.y = 208
	health.offset_bottom = 220
	health.show_percentage = false
	health.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var fill := StyleBoxFlat.new()
	fill.bg_color = Visual.SUCCESS
	health.add_theme_stylebox_override("fill", fill)
	var button := Button.new()
	button.text = "指挥官 / 任务 / 详情"
	add_child(button)
	button.anchor_left = 1
	button.anchor_right = 1
	button.offset_left = -260
	button.offset_right = -24
	button.offset_top = 8
	button.offset_bottom = 52
	Visual.button(button, false, 22)
	button.pressed.connect(func(): drawer = not drawer)

func _text(left: float, right: float) -> RichTextLabel:
	var label := RichTextLabel.new()
	label.bbcode_enabled = true
	label.scroll_active = false
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(label)
	label.anchor_left = left
	label.anchor_right = right
	label.anchor_bottom = 1
	label.offset_top = 100
	label.offset_bottom = -18
	label.add_theme_font_size_override("normal_font_size", 24)
	label.add_theme_color_override("default_color", Visual.TEXT)
	label.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.9))
	label.add_theme_constant_override("shadow_offset_x", 1)
	label.add_theme_constant_override("shadow_offset_y", 2)
	return label

func _process(_delta: float) -> void:
	if host == null:
		return
	visible = host.game_view.visible
	if not visible:
		drawer = false
		last_signature = ""
		return
	# 旧详情保留为抽屉，左右常驻巨框退出地图。
	host.left_hud_wing.visible = false
	host.right_hud_wing.visible = drawer
	host.info_panel.visible = drawer
	var legacy_portrait := host.hud_layer.get_node_or_null("HeroPortraitPanel") as Control
	if legacy_portrait != null:
		legacy_portrait.visible = false
	if host.board != null and host.board.board_camera != null:
		var camera = host.board.board_camera
		camera.left_inset = 24.0
		camera.bottom_inset = HEIGHT
		var wanted := size.x * 0.27 if drawer else 24.0
		if camera.right_inset != wanted:
			camera.right_inset = wanted
			camera.update_view()
	_layout_attack_confirmation()
	var unit: Dictionary = GameState.get_unit(_active_unit_id())
	if not unit.is_empty() and int(unit.get("hp", 1)) <= 0:
		unit = {}
	var cell := Vector2i(int(unit.get("x", -1)), int(unit.get("y", -1)))
	var target := false
	if host._move_mode_unit_id > 0 and host._move_preview_target != Vector2i(-1, -1):
		cell = host._move_preview_target
		target = true
	elif unit.is_empty() and host.board != null:
		cell = host.board._last_cursor
	var tile: Dictionary = GameState.get_tile(cell.x, cell.y)
	var forecasting: bool = host.attack_confirm_panel.visible
	var forecast_text: String = (compact_forecast if compact_forecast != "" else host.unit_info.text) if forecasting else ""
	var signature := str([unit, tile, cell, target, forecast_text, forecasting])
	if signature == last_signature:
		return
	last_signature = signature
	show_state(unit, tile, cell, target, forecast_text, forecasting)

func show_state(unit: Dictionary, tile: Dictionary, cell: Vector2i, target: bool, forecast_text: String, forecasting: bool) -> void:
	var terrain := str(tile.get("terrain", ""))
	var kind := _art_kind(terrain)
	if kind != last_art:
		last_art = kind
		art.texture = _texture(ART_PATHS.get(kind, ""))
	portrait.visible = not unit.is_empty()
	health.visible = not unit.is_empty() and unit.has("hp") and unit.has("max_hp")
	if unit.is_empty():
		identity.text = "[b]战场地形[/b]\n选择单位查看状态"
		vitality.text = "点击友军下达行动\n拖动地图 · 滚轮缩放"
		stats.text = "无锁定单位\n高差收益在选择攻击目标后显示"
		portrait.texture = null
	else:
		var path: String = host._unit_portrait_path_for(unit)
		if path != last_portrait or portrait.texture == null:
			last_portrait = path
			portrait.texture = _texture(path)
		var faction := "我方" if int(unit.get("player_id", unit.get("owner_id", -1))) == host._player_id else "其他阵营"
		identity.text = "[b]%s[/b]\n%s · %s\n%s" % [host._unit_cn_name(unit), host._unit_type_cn(str(unit.get("unit_type", ""))), faction, "已行动" if bool(unit.get("has_acted", false)) else "未行动"]
		vitality.text = "[b]HP  %s / %s[/b]\n移动力  %s / %s\n士气  %s" % [_number(unit, "hp"), _number(unit, "max_hp"), _number(unit, "mp"), _number(unit, "mov"), _number(unit, "morale")]
		health.max_value = maxf(1.0, float(unit.get("max_hp", 1)))
		health.value = float(unit.get("hp", 0))
		stats.text = "物攻 %s    物防 %s\n魔攻 %s    魔防 %s\n基础射程 %s–%s" % [_number(unit,"atk"), _number(unit,"def_"), _number(unit,"matk"), _number(unit,"mdef"), str(int(unit.min_attack_range)+1) if unit.has("min_attack_range") else "—", _number(unit,"attack_range")]
	var defense: Variant = tile.get("defense_bonus", null)
	var subtype := str(tile.get("subtype", ""))
	if defense == null:
		defense = Config.TERRAIN_DEF_BONUS.get(subtype, Config.TERRAIN_DEF_BONUS.get(terrain, null))
	var cost: Variant = tile.get("movement_cost_x2", Config.TERRAIN_MOVE_COST.get(terrain, null))
	var cost_text := "—" if cost == null else ("不可通行" if float(cost) >= 9999 else str(float(cost) / 2.0))
	var elevation := "—"
	if not tile.is_empty() and host.board != null and host.board.model != null and host.board.model.contains(cell) and host.board.model.cells.size() == host.board.model.size().x * host.board.model.size().y:
		elevation = str(host.board.model.elevation(cell))
	ground.text = "[b]%s · %s[/b]\n高度 %s · 地形防御 %s\n基础进入费用 %s" % ["目标地形" if target else "脚下地形", host._terrain_cn(terrain, subtype) if terrain != "" else "—", elevation, str(defense) if defense != null else "—", cost_text]
	stats.visible = not forecasting
	ground.visible = not forecasting
	prediction.visible = forecasting
	prediction.text = forecast_text

func _number(data: Dictionary, key: String) -> String:
	if not data.has(key) or data[key] == null:
		return "—"
	if data[key] is float or data[key] is int:
		return str(int(data[key])) if is_equal_approx(float(data[key]), roundf(float(data[key]))) else str(data[key])
	return str(data[key])

func _texture(path: String) -> Texture2D:
	if path == "":
		return null
	if not textures.has(path):
		if ResourceLoader.exists(path):
			textures[path] = load(path)
		elif FileAccess.file_exists(path):
			var bitmap := Image.load_from_file(path)
			if bitmap != null:
				textures[path] = ImageTexture.create_from_image(bitmap)
	return textures.get(path, null)

func _art_kind(terrain: String) -> String:
	match terrain:
		"plain", "grass", "grassland", "road": return "grassland"
		"forest", "wood": return "forest"
		"mountain", "hill", "rock", "snow_peak": return "rocky"
		"desert", "sand": return "sand"
		"water", "river", "sea", "shoal", "bridge": return "waterside"
		"village", "barracks", "castle", "castle_vault", "gate": return "settlement"
	return "grassland"


# 行动气泡关闭会清除selected；动作模式仍持有当前行动单位。
func _active_unit_id() -> int:
	if host.attack_confirm_panel.visible and host._pending_attack_attacker_id > 0:
		return host._pending_attack_attacker_id
	for active_id in [host._move_mode_unit_id, host._attack_mode_unit_id, host._skill_mode_unit_id, host._selected_unit_id]:
		if int(active_id) > 0:
			return int(active_id)
	return -1


func _layout_attack_confirmation() -> void:
	var panel: Panel = host.attack_confirm_panel
	# 主题或布局改变后才重排，避免每帧创建样式资源。
	if panel.get_theme_stylebox("panel") is StyleBoxEmpty and is_equal_approx(panel.anchor_left, 0.53):
		return
	panel.z_index = 5
	panel.anchor_left = 0.53
	panel.anchor_right = 0.99
	panel.anchor_top = 1
	panel.anchor_bottom = 1
	panel.offset_left = 0
	panel.offset_right = 0
	panel.offset_top = -76
	panel.offset_bottom = -8
	panel.add_theme_stylebox_override("panel", StyleBoxEmpty.new())
	for child_name in ["Title", "Body", "OrnateFrame"]:
		var child := panel.get_node_or_null(child_name) as CanvasItem
		if child != null: child.visible = false
	var row := panel.get_node("ButtonRow") as Control
	row.anchor_left = 0
	row.anchor_right = 1
	row.anchor_top = 0
	row.anchor_bottom = 1
	row.offset_left = 16
	row.offset_right = -16
	row.offset_top = 4
	row.offset_bottom = -4

func show_forecast(data: Dictionary, attacker: Dictionary, defender: Dictionary) -> void:
	compact_forecast = "%s → %s · 战斗预测\n预计伤害 %s · 目标HP %s · 反击 %s\n我方HP %s · 地形防御 %s\n高差 %s · 高地攻击 %s · 射程加成 %s" % [host._unit_cn_name(attacker), host._unit_cn_name(defender), _number(data,"damage"), _number(data,"target_hp_after"), _number(data,"counter_damage"), _number(data,"attacker_hp_after"), _number(data,"target_def_bonus"), _number(data,"height_delta"), _number(data,"height_attack_bonus"), _number(data,"range_bonus")]
	last_signature = ""
