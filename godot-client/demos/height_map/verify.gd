extends SceneTree
## 使用真实模型、生成网格、物理射线和界面事件验证Demo。
const Model = preload("res://demos/height_map/map_model.gd")
var failures: Array[String] = []
var checks := 0
var demo: Node3D
var test_dir := "user://height_map_demo/verification/%d" % OS.get_process_id()

func _initialize() -> void:
	call_deferred("run")
	create_timer(40.0).timeout.connect(func():
		push_error("[height-demo verification] timed out")
		quit(1))

func check(condition: bool, name: String) -> void:
	checks += 1
	if not condition:
		failures.append(name)
		push_error("[height-demo verification] " + name)

func run() -> void:
	var config: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://scripts/board/height_map/geometry.json"))
	var model := Model.new(config)
	var p := Vector2i(1, 1)
	check(model.cells.size() == 144, "地图144格")
	check(model.elevation(Vector2i(9,3)) - model.elevation(Vector2i(8,3)) == 10, "允许相邻10级落差")
	model.edit(p, 99)
	check(model.elevation(p) == 5, "正高度上限")
	model.edit(p, -99)
	check(model.elevation(p) == -5, "负高度下限")
	check(model.undo() and model.elevation(p) == 5, "撤销")
	check(model.redo() and model.elevation(p) == -5, "重做")
	model.undo()
	model.edit(p, 2)
	check(not model.redo(), "分支编辑清空重做")
	var snapshot := model.snapshot()
	for bad in [null, {}, {"format":"other"}, {"format":"battleblitz-height-demo","version":1,"width":12,"depth":12,"cells":[]}]:
		check(not model.restore(bad).is_empty() and model.snapshot() == snapshot, "非法地图不破坏现有数据")
	for h in [-6, 6, 1.5, "1", null]:
		var bad := snapshot.duplicate(true)
		bad.cells[0].height = h
		check(not model.restore(bad).is_empty() and model.snapshot() == snapshot, "拒绝非法高度 " + str(h))
	var unknown := snapshot.duplicate(true)
	unknown.cells[0].terrain = "unknown"
	check(not model.restore(unknown).is_empty(), "拒绝未知地形")
	# 各进程使用独立目录，三档窗口可并行验证，不争用同一临时文件。
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(test_dir))
	var path := test_dir + "/roundtrip.json"
	check(model.save_map(path).is_empty(), "首次保存")
	model.edit(p, 3, "sand")
	check(model.save_map(path).is_empty(), "覆盖保存")
	var saved := model.snapshot()
	model.edit(p, -2)
	var load_error := model.load_map(path)
	check(load_error.is_empty() and model.snapshot() == saved, "磁盘保存重载一致")
	check(not model.load_map("user://height_map_demo/verification/missing.json").is_empty(), "缺文件明确失败")
	demo = load("res://demos/height_map/main.tscn").instantiate()
	demo.start_with_standard = false
	root.add_child(demo)
	await process_frame
	await physics_frame
	check(demo.terrain.terrain_root.get_child_count() == 144, "144格几何与碰撞")
	check(demo.terrain.face_count > 144 and demo.terrain.face_count < 144*5, "侧面仅在可见落差生成")
	var material_ids: Array = []
	for kind in model.TERRAINS:
		var top: StandardMaterial3D = demo.terrain.materials[kind]
		var side: StandardMaterial3D = demo.terrain.side_materials[kind]
		check(top.albedo_texture != null and top.albedo_texture.get_width() >= 1024, "高清顶面：" + kind)
		check(side.albedo_texture != null and side.albedo_texture.get_width() >= 1024, "高清侧面：" + kind)
		check(top.texture_filter == BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC, "非像素过滤：" + kind)
		material_ids.append(side.albedo_texture.resource_path)
	check(material_ids.size() == 4 and material_ids[0] != material_ids[1] and material_ids[1] != material_ids[2] and material_ids[2] != material_ids[3], "四种地形使用独立侧面")
	check(demo.camera.size <= 11, "默认局部近景")
	# 通过相机将已知顶面投到屏幕，再用实际物理射线验证。
	demo.terrain.unit.visible = false
	var visible_cell := Vector2i(10, 10)
	var screen: Vector2 = demo.camera.unproject_position(demo.model.surface(visible_cell))
	var hit: Dictionary = demo.terrain.pick(demo.camera, screen)
	check(not hit.is_empty() and hit.top and hit.cell == visible_cell, "负高度顶面射线选格")
	var side_hits := 0
	var viewport_size := root.get_visible_rect().size
	for sy in range(80, int(viewport_size.y)-40, 16):
		for sx in range(340, int(viewport_size.x)-20, 16):
			var candidate: Dictionary = demo.terrain.pick(demo.camera, Vector2(sx, sy))
			if not candidate.is_empty() and not candidate.top:
				side_hits += 1
	check(side_hits > 0, "真实悬崖侧面命中而非点穿")
	var side_screen := Vector2.ZERO
	for sy in range(150, int(viewport_size.y)-40, 20):
		for sx in range(350, int(viewport_size.x)-20, 20):
			var candidate: Dictionary = demo.terrain.pick(demo.camera, Vector2(sx, sy))
			if not candidate.is_empty() and not candidate.top:
				side_screen = Vector2(sx, sy)
	if side_screen != Vector2.ZERO:
		var before_selection: Vector2i = demo.selected
		await click_at(side_screen)
		check(demo.selected == before_selection, "真实点击侧面不选中后方格")
	# 界面事件：按下真实按钮，验证模型变化与边界禁用。
	demo.select_cell(Vector2i(0, 0))
	await process_frame
	await click_control(demo.editor.buttons.raise)
	check(demo.model.elevation(Vector2i(0,0)) == 1, "鼠标点击升高按钮改变高度")
	check(is_equal_approx(demo.terrain.unit.position.y, 1.17), "编辑同步角色脚底")
	await click_control(demo.editor.buttons.undo)
	check(demo.model.elevation(Vector2i(0,0)) == 0, "鼠标点击撤销")
	demo.edit_selected(5)
	check(demo.editor.buttons.raise.disabled, "上限按钮禁用")
	demo.edit_selected(-5)
	check(demo.editor.buttons.lower.disabled, "下限按钮禁用")
	# 输入框和地形选择信号经同一编辑入口更新地图。
	demo.editor.height_input.value = 2
	check(demo.model.elevation(Vector2i.ZERO) == 2, "高度输入框编辑")
	demo.editor.terrain_input.item_selected.emit(2)
	check(demo.model.cell(Vector2i.ZERO).terrain == "sand", "地形选择更新")
	await click_control(demo.editor.buttons.grid)
	check(demo.terrain.grid.visible, "基准网格按钮")
	await click_control(demo.editor.buttons.unit)
	check(demo.terrain.unit.visible, "角色显隐按钮")
	var test_path := test_dir + "/scene.json"
	check(demo.save_to(test_path), "场景保存入口")
	demo.edit_selected(-2)
	check(demo.load_from(test_path) and demo.model.elevation(Vector2i.ZERO) == 2, "场景加载恢复地形")
	demo.terrain.grid.visible = false
	demo.model.make_sample()
	demo.terrain.rebuild()
	demo.select_cell(Vector2i(4,4))
	demo.terrain.unit.visible = true
	await physics_frame
	await process_frame
	# 实际顶面鼠标事件，需避开编辑面板。
	var target := Vector2i(10,10)
	await click_at(demo.camera.unproject_position(demo.model.surface(target)))
	check(demo.selected == target, "鼠标点击负高度顶面选中正确坐标")
	demo.handle_action("right")
	check(is_equal_approx(demo.camera.target_yaw, 90) and demo.camera.yaw < 90, "相机旋转设置平滑目标")
	await create_timer(0.9).timeout
	check(is_equal_approx(demo.camera.yaw, 90), "平滑旋转准确到达目标")
	for i in 8:
		demo.handle_action("right")
	check(is_equal_approx(demo.camera.target_yaw, 450), "连续旋转跨360度不反向")
	await create_timer(1.2).timeout
	check(is_equal_approx(demo.camera.yaw, 450), "连续旋转完成")
	demo.handle_action("reset")
	check(is_equal_approx(demo.camera.yaw,45), "相机复位")
	await send_key(KEY_E)
	check(is_equal_approx(demo.camera.target_yaw,90), "E快捷键旋转")
	demo.handle_action("reset")
	await click_control(demo.editor.buttons.left)
	check(is_equal_approx(demo.camera.target_yaw,0), "左转按钮真实点击")
	demo.handle_action("reset")
	demo.editor.height_input.get_line_edit().grab_focus()
	await send_key(KEY_E)
	check(is_equal_approx(demo.camera.target_yaw,45), "输入高度时不触发相机快捷键")
	root.gui_release_focus()
	var drag := InputEventMouseMotion.new()
	drag.position = Vector2(750, 400)
	drag.relative = Vector2(80, 20)
	drag.button_mask = MOUSE_BUTTON_MASK_RIGHT
	root.push_input(drag, true)
	await process_frame
	check(demo.camera.yaw < 45 and demo.camera.pitch > 30, "右键拖动同时改变方位与俯角")
	check(is_equal_approx(demo.editor.pitch_input.value, demo.camera.pitch), "拖动同步俯角滑块")
	demo.camera.orbit_drag(Vector2(0,-10000))
	check(is_equal_approx(demo.camera.pitch,20), "拖动俯角下限")
	demo.camera.orbit_drag(Vector2(0,10000))
	check(is_equal_approx(demo.camera.pitch,60), "拖动俯角上限")
	demo.handle_action("reset")
	# 四个朝向均用真实鼠标点击各自可见的近侧顶面。
	var corners := [Vector2i(10,10), Vector2i(10,1), Vector2i(1,1), Vector2i(1,10)]
	for i in 4:
		demo.camera.turn(45.0 + 90.0*i - demo.camera.yaw, false)
		await physics_frame
		await click_at(demo.camera.unproject_position(demo.model.surface(corners[i])))
		check(demo.selected == corners[i], "旋转后顶面真实选格：方向%d" % i)
	demo.handle_action("reset")
	demo.select_cell(Vector2i(5,5))
	await send_key(KEY_RIGHT)
	check(demo.selected == Vector2i(6,5), "方向键逻辑选格")
	await click_control(demo.editor.buttons.focus)
	check(demo.camera.focus.is_equal_approx(demo.model.surface(demo.selected)), "聚焦选格按钮")
	await click_control(demo.editor.buttons.xray)
	check(demo.terrain.xray_selected and demo.terrain.unit.no_depth_test, "透视选中开启")
	demo.edit_selected(-3)
	check(demo.terrain.marker.mesh.surface_get_material(0).no_depth_test, "编辑重建后保留透视")
	await click_control(demo.editor.buttons.xray)
	check(not demo.terrain.xray_selected and not demo.terrain.unit.no_depth_test, "透视关闭恢复遮挡")
	demo.model.make_sample()
	demo.terrain.rebuild()
	demo.handle_action("reset")
	var original_focus: Vector3 = demo.camera.focus
	demo.camera.pan(Vector2(20, 30))
	check(demo.camera.focus != original_focus, "相机平移")
	demo.camera.zoom(0.9)
	check(demo.camera.size < float(config.camera_size), "相机缩放")
	# 光标走到远端时必须推动镜头，最终回到界面右侧安全区。
	demo.handle_action("reset")
	var old_focus: Vector3 = demo.camera.focus
	demo.select_cell(Vector2i(0,0))
	await create_timer(1.0).timeout
	check(demo.camera.focus.distance_to(old_focus) > 0.1, "远端光标推动镜头")
	check(demo.camera.safe_rect().has_point(demo.camera.unproject_position(demo.model.surface(demo.selected))), "光标跟随后位于安全区")
	for i in 11:
		await send_key(KEY_RIGHT)
	await create_timer(1.0).timeout
	check(demo.selected == Vector2i(11,0), "连续方向键移动到地图边界")
	check(demo.camera.safe_rect().has_point(demo.camera.unproject_position(demo.model.surface(demo.selected))), "连续移动后镜头仍跟随")
	var pan_before: Vector3 = demo.camera.focus
	var pan_event := InputEventMouseMotion.new()
	pan_event.position = Vector2(850,400)
	pan_event.relative = Vector2(35,20)
	pan_event.button_mask = MOUSE_BUTTON_MASK_LEFT
	root.push_input(pan_event,true)
	await process_frame
	check(demo.camera.focus.distance_to(pan_before) > 0.01, "左键拖动移动视野")
	check(demo.camera.target_focus.is_equal_approx(demo.camera.focus), "手动拖动取消跟随目标避免回弹")
	# 两种缩放下的实测投影宽度，避免只检查设置值。
	demo.camera.focus_on(demo.model.surface(Vector2i(4,4)))
	var near_width: float = demo.camera.unproject_position(Vector3(5,0,4)).distance_to(demo.camera.unproject_position(Vector3(4,0,4)))
	demo.camera.size = 19.0
	var far_width: float = demo.camera.unproject_position(Vector3(5,0,4)).distance_to(demo.camera.unproject_position(Vector3(4,0,4)))
	check(near_width > far_width * 1.5, "实测地块屏幕尺寸明显放大")
	demo.handle_action("reset")
	demo.select_cell(Vector2i(4,4))
	demo.handle_action("reset")
	await process_frame
	if DisplayServer.get_name() != "headless":
		RenderingServer.force_draw(true)
		var output := OS.get_environment("BB_HEIGHT_SCREENSHOT")
		if not output.is_empty():
			check(root.get_texture().get_image().save_png(output) == OK, "GPU截图保存")
			demo.handle_action("right")
			await create_timer(0.9).timeout
			RenderingServer.force_draw(true)
			check(root.get_texture().get_image().save_png(output.get_basename() + "-turned.png") == OK, "旋转后GPU截图保存")
			# 单独拍摄四种材质柱体，水面不能只检查资源存在却从未显示。
			for y in demo.model.size().y:
				for x in demo.model.size().x:
					demo.model.edit(Vector2i(x,y), -2, "grass")
			var examples := [Vector2i(4,4),Vector2i(6,4),Vector2i(4,6),Vector2i(6,6)]
			for i in 4:
				demo.model.edit(examples[i], 3, demo.model.TERRAINS[i])
			demo.terrain.rebuild()
			demo.terrain.unit.visible = false
			demo.camera.reset_view()
			demo.camera.focus_on(Vector3(5,0,5))
			await process_frame
			demo.editor.sync_camera(demo.camera)
			RenderingServer.force_draw(true)
			check(root.get_texture().get_image().save_png(output.get_basename() + "-materials.png") == OK, "四种顶面与侧面GPU展示截图")
	print("[height-demo verification] checks=%d failures=%d" % [checks, failures.size()])
	demo.queue_free()
	await process_frame
	quit(0 if failures.is_empty() else 1)

func click_control(control: Control) -> void:
	await click_at(control.get_global_rect().get_center())

func send_key(keycode: Key) -> void:
	for pressed in [true, false]:
		var event := InputEventKey.new()
		event.keycode = keycode
		event.pressed = pressed
		root.push_input(event, true)
		await process_frame

func click_at(position: Vector2) -> void:
	var motion := InputEventMouseMotion.new()
	motion.position = position
	root.push_input(motion, true)
	await process_frame
	for pressed in [true, false]:
		var event := InputEventMouseButton.new()
		event.position = position
		event.button_index = MOUSE_BUTTON_LEFT
		event.pressed = pressed
		root.push_input(event, true)
		await process_frame
