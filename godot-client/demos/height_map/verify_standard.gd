extends SceneTree
const Model = preload("res://demos/height_map/map_model.gd")
const Importer = preload("res://demos/height_map/preset_importer.gd")
var checks := 0
var failures: Array[String] = []
var demo: Node3D

func _initialize() -> void:
	call_deferred("run")
	create_timer(50).timeout.connect(func():
		push_error("[standard-map verification] timed out")
		quit(1))

func check(condition: bool, label: String) -> void:
	checks += 1
	if not condition:
		failures.append(label)
		push_error("[standard-map verification] " + label)

func run() -> void:
	var config: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://scripts/board/height_map/geometry.json"))
	var model := Model.new(config)
	var source_text := FileAccess.get_file_as_string(String(model.rules.source_map))
	var original := ProjectSettings.globalize_path("res://").path_join("../game/maps/balanced_2p_15.json").simplify_path()
	check(source_text == FileAccess.get_file_as_string(original), "打包原图与后端原文件逐字一致")
	var source: Dictionary = JSON.parse_string(source_text)
	check(model.import_standard().is_empty(), "标准图导入")
	check(model.size() == Vector2i(15,15) and model.cells.size() == 225, "225格尺寸")
	var counts: Dictionary = {}
	for y in 15:
		for x in 15:
			var code: String = source.layout[y][x]
			var p := Vector2i(x,y)
			var expected: Dictionary = model.rules.codes[code]
			check(model.cell(p).source_terrain == expected.source_terrain and model.cell(p).feature == expected.feature and model.cell(p).terrain == expected.terrain and model.elevation(p) == expected.height, "原图格子保持：%d,%d" % [x,y])
			counts[model.cell(p).feature] = int(counts.get(model.cell(p).feature,0))+1
	check(counts.castle == 2 and counts.village == 4 and counts.barracks == 2, "建筑数量2/4/2")
	check(model.cell(Vector2i(2,7)).faction == "red" and model.cell(Vector2i(12,7)).faction == "blue", "原图席位城堡红蓝归属")
	check(model.units.size() == 10, "原图10个预设单位")
	var team_counts := {"red":0,"blue":0}
	for i in source.initial_units.size():
		var actual: Dictionary = model.units[i]
		var expected: Dictionary = source.initial_units[i]
		check(actual.x == expected.x and actual.y == expected.y and actual.type == expected.type and actual.color == expected.color and actual.level == expected.level, "原图单位数据完整：%d" % i)
		team_counts[actual.color] += 1
	check(team_counts.red == 5 and team_counts.blue == 5, "双方各5人")
	model.edit(Vector2i(4,7),2,"sand")
	check(model.cell(Vector2i(4,7)).feature == "barracks" and model.unit_at(Vector2i(4,7)).type == "knight", "地形编辑不删除佣兵站或驻军")
	model.undo()
	var before := model.snapshot()
	for mutate in ["duplicate","outside","unknown","fraction","feature"]:
		var bad := before.duplicate(true)
		match mutate:
			"duplicate": bad.units[1].x = bad.units[0].x; bad.units[1].y = bad.units[0].y
			"outside": bad.units[0].x = 15
			"unknown": bad.units[0].type = "missing"
			"fraction": bad.units[0].level = 1.5
			"feature": bad.cells[0].feature = "missing"
		check(not model.restore(bad).is_empty() and model.snapshot() == before, "拒绝非法数据且原图不变："+mutate)
	var bad_source := source.duplicate(true)
	bad_source.layout[0] = "?" + String(bad_source.layout[0]).substr(1)
	check(not String(Importer.convert(bad_source,model.rules).error).is_empty(), "未知原图字符拒绝，不默默变成草地")
	var directory := "user://height_map_demo/verification/standard-%d" % OS.get_process_id()
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(directory))
	var path := directory+"/standard.json"
	check(model.save_map(path).is_empty(), "标准图保存")
	model.make_sample()
	check(model.size() == Vector2i(12,12), "原高度试验场保留")
	check(model.load_map(path).is_empty() and model.snapshot() == before, "跨尺寸保存重载完整保留建筑与单位")
	# 旧版本12×12文件仍可加载。
	var legacy_model := Model.new(config)
	var legacy := {"format":"battleblitz-height-demo","version":1,"width":12,"depth":12,"cells":legacy_model.cells.duplicate(true)}
	check(model.restore(legacy).is_empty() and model.units.is_empty() and model.size()==Vector2i(12,12), "兼容旧版高度存档")
	demo = load("res://demos/height_map/main.tscn").instantiate()
	root.add_child(demo)
	await process_frame
	await physics_frame
	check(demo.model.map_id == "balanced_2p_15", "启动默认进入2人标准图")
	check(demo.selected == Vector2i(2,8) and demo.terrain.selected == demo.selected, "启动光标、地形高亮和首个预设单位一致")
	check(demo.terrain.contents.feature_counts.castle == 2 and demo.terrain.contents.feature_counts.village == 4 and demo.terrain.contents.feature_counts.barracks == 2, "三类建筑实际生成")
	check(demo.terrain.contents.units.get_child_count() == 10 and not demo.terrain.unit.visible, "实际生成10个固定单位且隐藏随光标假人")
	for p in demo.terrain.contents.unit_nodes:
		var rendered: Dictionary = demo.terrain.contents.unit_nodes[p]
		check(rendered.anchor.position.is_equal_approx(demo.model.surface(p)) and rendered.sprite.texture != null, "单位坐标落位与贴图：%s" % p)
	var first: Node3D = demo.terrain.contents.unit_nodes[Vector2i(2,8)].anchor
	var first_position := first.position
	demo.select_cell(Vector2i(7,7))
	check(first.position == first_position and demo.model.units.size()==10 and not demo.terrain.unit.visible, "空格光标不移动预设单位或产生新单位")
	await click(demo.editor.buttons.blue)
	check(demo.selected == Vector2i(12,8), "蓝方定位按钮")
	await click(demo.editor.buttons.red)
	check(demo.selected == Vector2i(2,8), "红方定位按钮")
	# 佣兵站上确实有红方骑兵；升降后建筑、单位、高亮均跟随。
	demo.select_cell(Vector2i(4,7))
	demo.edit_selected(2)
	check(is_equal_approx(demo.terrain.contents.unit_nodes[Vector2i(4,7)].anchor.position.y,1), "驻军随所在格升高")
	var barracks: Node3D = demo.terrain.contents.features.get_node("barracks_4_7")
	check(is_equal_approx(barracks.position.y,1), "佣兵站随所在格升高")
	check(demo.editor.detail_label.text.contains("佣兵站") and demo.editor.detail_label.text.contains("红方"), "选格显示建筑和驻军信息")
	demo.handle_action("undo")
	check(is_equal_approx(demo.terrain.contents.features.get_node("barracks_4_7").position.y,0), "撤销同步建筑位置")
	# 从真实镜头点击建筑顶部及单位，而不是只查节点存在。
	for p in [Vector2i(2,7),Vector2i(2,4),Vector2i(4,7),Vector2i(3,8)]:
		var target_height := 0.9 if demo.model.cell(p).get("feature", "") == "castle" else 0.4
		demo.camera.reset_view()
		demo.camera.focus_on(demo.model.surface(p)+Vector3.UP*target_height)
		await physics_frame
		var screen: Vector2 = demo.camera.unproject_position(demo.model.surface(p)+Vector3.UP*target_height)
		await click_at(screen)
		check(demo.selected == p, "建筑/单位真实点击：%s" % p)
	demo.select_cell(Vector2i(2,8))
	demo.handle_action("xray")
	check(demo.terrain.contents.unit_nodes[Vector2i(2,8)].sprite.no_depth_test and not demo.terrain.contents.unit_nodes[Vector2i(3,8)].sprite.no_depth_test, "透视仅作用于被选中单位")
	demo.handle_action("xray")
	check(demo.terrain.contents.feature_counts.forest == counts.forest, "森林地貌完整生成")
	demo.camera.reset_view()
	demo.camera.focus_on(demo.model.surface(Vector2i(2,7))+Vector3.UP*0.4)
	demo.handle_action("unit")
	await physics_frame
	var castle_screen: Vector2 = demo.camera.unproject_position(demo.model.surface(Vector2i(2,7))+Vector3.UP*0.4)
	var hidden_hit: Dictionary = demo.terrain.pick(demo.camera,castle_screen)
	check(not demo.terrain.contents.units.visible and not hidden_hit.is_empty() and hidden_hit.cell==Vector2i(2,7), "隐藏单位后不再拦截后方建筑点击")
	demo.handle_action("unit")
	check(demo.terrain.contents.units.visible,"恢复所有预设单位显示")
	# 场景切换再返回，未丢失尺寸、建筑和预设阵容。
	demo.editor.preset_input.item_selected.emit(1)
	check(demo.model.size()==Vector2i(12,12) and demo.model.units.is_empty(), "界面切回高度试验场")
	demo.editor.preset_input.item_selected.emit(0)
	check(demo.model.size()==Vector2i(15,15) and demo.terrain.contents.unit_nodes.size()==10, "界面重载标准图")
	if DisplayServer.get_name() != "headless":
		var output := OS.get_environment("BB_STANDARD_SCREENSHOT")
		if not output.is_empty():
			for view in ["red","blue","village","barracks","overview"]:
				demo.terrain.contents.units.visible = true
				demo.camera.reset_view()
				match view:
					"red": demo.handle_action("red")
					"blue": demo.handle_action("blue")
					"village": demo.select_cell(Vector2i(2,4)); demo.handle_action("focus")
					"barracks":
						demo.select_cell(Vector2i(4,7))
						demo.handle_action("focus")
						demo.terrain.contents.units.visible = false
					"overview": demo.camera.size=20; demo.camera.focus_on(Vector3(7,0,7))
				await process_frame
				demo.editor.sync_camera(demo.camera)
				RenderingServer.force_draw(true)
				check(root.get_texture().get_image().save_png(output+"-"+view+".png")==OK,"GPU截图："+view)
	print("[standard-map verification] checks=%d failures=%d" % [checks,failures.size()])
	demo.queue_free()
	await process_frame
	quit(0 if failures.is_empty() else 1)

func click(control: Control) -> void:
	await click_at(control.get_global_rect().get_center())

func click_at(position: Vector2) -> void:
	var motion := InputEventMouseMotion.new()
	motion.position = position
	root.push_input(motion,true)
	await process_frame
	for pressed in [true,false]:
		var event := InputEventMouseButton.new()
		event.position = position
		event.pressed = pressed
		event.button_index = MOUSE_BUTTON_LEFT
		root.push_input(event,true)
		await process_frame
