extends SceneTree
## 正式main.tscn端到端验证。独立服务、真实HTTP/WS、真实鼠标与按钮输入。
const Session = preload("res://demos/height_map/battle_session.gd")
var main: Node
var board: Node
var session: Node
var gs: Node
var network: Node
var settings: Node
var saved_settings: Dictionary
var saved_dirty := false
var checks := 0
var failures: Array[String] = []
var api_errors: Array = []
var drag_verified := false

func _initialize() -> void:
	call_deferred("run")
	create_timer(150).timeout.connect(func():
		push_error("[formal-height] timeout")
		finish(1))

func check(condition: bool, label: String) -> void:
	checks += 1
	if not condition:
		failures.append(label)
		push_error("[formal-height] "+label)

func finish(code: int) -> void:
	if settings:
		settings._data = saved_settings
		settings._dirty = saved_dirty
	if network:
		network.ws_close()
	print("[formal-height] checks=%d failures=%d" % [checks,failures.size()])
	quit(code)

func run() -> void:
	settings = root.get_node("UserSettings")
	saved_settings = settings._data.duplicate(true)
	saved_dirty = settings._dirty
	var url := OS.get_environment("BB_HEIGHT_BATTLE_URL")
	if url.is_empty():
		url = "http://127.0.0.1:8768"
	settings._data["server.api_base"] = url
	settings._data["server.ws_base"] = url.replace("http://","ws://")
	settings._data["dialog.v1.attack_confirm"] = false
	settings._data["settings.v1.player_name"] = ""
	gs = root.get_node("GameState")
	network = root.get_node("NetworkClient")
	network.api_error.connect(func(method,path,error,code):
		# 独立数据库没有本机账户旧存档，菜单查询404是预期状态。
		if not (method=="GET" and path.begins_with("/saves?") and code==404):
			api_errors.append("%s %s %s %s" % [method,path,error,code]))
	session = Session.new()
	root.add_child(session)
	session.config.base_url = url
	var created: Dictionary = await session.create_match()
	check(created.ok,"实际创建并开始标准对局")
	if not created.ok:
		finish(1)
		return
	main = load("res://scenes/main.tscn").instantiate()
	root.add_child(main)
	board = main.board
	main._game_id = session.game_id
	main._player_id = int(created.data.players[0].id)
	gs.local_player_id = main._player_id
	main._tutorial_shown = true
	main._on_start_game_response({})
	await sync_state()
	check(board.terrain!=null and board.board_camera is Camera3D,"正式入口实际创建3D地图")
	check(board.find_children("*","TileMapLayer",true,false).is_empty(),"正式棋盘无旧TileMap层")
	check(board.model.cells.size()==225 and board.model.units.size()==10,"正式快照225格10人完整呈现")
	if board.model.cells.size()!=225:
		finish(1)
		return
	check(board.model.elevation(Vector2i(0,0))==3,"旧地图山地自动转为高地")
	var red := unit("red","warlock")
	await move_unit(int(red.id),Vector2i(6,7))
	var knight := unit("red","knight")
	await move_unit(int(knight.id),Vector2i(5,6))
	# 实际点击腾空的己方佣兵站并点击招募按钮。
	main._cursor_cancel_action()
	await click_cell(Vector2i(4,7))
	check(main.recruit_panel.visible,"点击3D佣兵站打开正式招募界面")
	var before_count: int = board.model.units.size()
	await click_button(main.recruit_list.get_child(0))
	await idle_network()
	await sync_state()
	check(board.model.units.size()==before_count+1,"真实招募后新单位同步3D")
	main._on_recruit_close_pressed()
	await capture("move-recruit")
	await click_button(main.end_turn_button)
	await idle_network()
	await sync_state()
	check(gs.current_player_id != main._player_id,"正式结束回合切换玩家")
	main._player_id = int(gs.current_player_id)
	gs.local_player_id = main._player_id
	network.connect_to_game(session.game_id,main._player_id)
	await sync_state()
	var blue := unit("blue","warlock")
	await move_unit(int(blue.id),Vector2i(8,7))
	await select_unit(int(blue.id))
	await click_button(main.attack_btn)
	await click_cell(Vector2i(6,7))
	await idle_network()
	check(main.attack_confirm_panel.visible,"真实敌方点击打开正式伤害预览")
	await capture("forecast")
	var hp_before := int(gs.get_unit(int(red.id)).hp)
	await click_button(main.attack_confirm_btn)
	await idle_network()
	await dismiss_dialogs()
	await sync_state()
	check(int(gs.get_unit(int(red.id)).hp)<hp_before,"正式确认攻击产生真实伤害")
	check(bool(gs.get_unit(int(blue.id)).has_acted),"正式攻击行动标记同步")
	await capture("attack")
	var healer := unit("blue","healer")
	await move_unit(int(healer.id),Vector2i(9,8))
	await select_unit(int(healer.id))
	var wounded_hp := int(gs.get_unit(int(blue.id)).hp)
	await click_button(main.skill_btn)
	await click_cell(Vector2i(8,7))
	await idle_network()
	await sync_state()
	check(int(gs.get_unit(int(blue.id)).hp)>wounded_hp,"正式治疗技能点击目标后真实回血")
	# 菜单和编辑器切换不会被3D相机缩放/移动。
	main._show_view("menu")
	await process_frame
	check(not board.surface.is_visible_in_tree(),"返回菜单关闭战场画面")
	check(root.canvas_transform==Transform2D.IDENTITY,"3D相机不污染菜单坐标")
	main._show_view("editor")
	main.editor_view.open()
	await idle_network()
	var editor: Node = main.editor_view
	var eb: Node = editor.editor_board
	check(eb.board_camera is Camera3D,"正式编辑器共用3D地图")
	editor.editor_mode_option.select(3)
	editor._on_editor_mode_selected(3)
	editor.elevation_input.value = -5
	await editor_click(eb,Vector2i(6,6))
	editor.elevation_input.value = 5
	await editor_click(eb,Vector2i(7,6))
	check(eb.model.elevation(Vector2i(6,6))==-5 and eb.model.elevation(Vector2i(7,6))==5,"正式编辑器相邻10级落差")
	editor.request_undo()
	check(eb.model.elevation(Vector2i(7,6))==0,"高度编辑撤销")
	editor.request_redo()
	check(eb.model.elevation(Vector2i(7,6))==5,"高度编辑重做")
	editor.elevation_input.value = 0
	await click_button(editor.elevation_apply)
	check(eb.model.elevation(Vector2i(7,6))==0,"高度按钮可直接修改已选格")
	editor.request_undo()
	var left := InputEventKey.new()
	left.keycode = KEY_LEFT
	left.pressed = true
	root.push_input(left,true)
	await process_frame
	check(eb.controls.editor_cursor==Vector2i(6,6),"方向键可选择被高地遮挡的深坑")
	var confirm := InputEventKey.new()
	confirm.keycode = KEY_SPACE
	confirm.pressed = true
	root.push_input(confirm,true)
	await process_frame
	check(eb.model.elevation(Vector2i(6,6))==0,"空格可编辑遮挡格而不穿透鼠标射线")
	editor.request_undo()
	await capture("editor")
	# 仅在独立验证服务新建测试地图；保存/读回均走正式网络接口。
	editor.editor_map_name_input.text = "高差整合验证-%d" % OS.get_process_id()
	await click_button(editor.editor_save_btn)
	await idle_network()
	var map_id: String = str(editor._editor_map.get("id",""))
	check(not map_id.is_empty(),"正式编辑器真实保存地图")
	if not map_id.is_empty():
		var loaded: Dictionary = await session.request("GET","/editor/maps/"+map_id)
		check(loaded.ok and loaded.data.elevations.size()==15 and loaded.data.elevations[6][6]==-5 and loaded.data.elevations[6][7]==5,"高度保存后HTTP读回一致")
	await verify_ai_match()
	await verify_lobby_preview()
	check(api_errors.is_empty(),"正式网络操作无API错误："+str(api_errors))
	finish(0 if failures.is_empty() else 1)

func verify_lobby_preview() -> void:
	main._show_view("lobby")
	var lobby: Node = main.lobby_view
	lobby._load_lobby_presets()
	await idle_network()
	lobby._show_lobby_create_view()
	lobby._render_lobby_map_preview()
	for index in lobby._preset_options.size():
		if str(lobby._preset_options[index].id)=="balanced_2p_15":
			lobby.map_preset_option.select(index)
			lobby._on_lobby_map_preset_selected(index)
			break
	await process_frame
	check(lobby._height_preview!=null and lobby._height_preview.preview_mode,"大厅地图预览使用正式3D舞台")
	lobby.map_player_count_option.select(3)
	lobby._on_lobby_map_player_count_selected(3)
	for index in lobby._preset_options.size():
		if str(lobby._preset_options[index].id)=="balanced_4p_20":
			lobby.map_preset_option.select(index)
			lobby._on_lobby_map_preset_selected(index)
			break
	await process_frame
	var preview: Node = lobby._height_preview
	check(preview.model.units.any(func(u): return u.color=="green") and preview.model.units.any(func(u): return u.color=="yellow"),"大厅四人标准图呈现绿黄阵营")
	check(preview.stage.size==Vector2i(lobby.map_preview_texture.size),"地图预览与实际控件尺寸一致")
	await capture("lobby-4p")

func verify_ai_match() -> void:
	# 与正式自由对战相同：真人加入、添加规则AI、开局、结束回合驱动AI。
	var made: Dictionary = await session.request("POST","/games",{"name":"正式高差AI回归","mode":"free","map_preset":"balanced_2p_15","battle_config":{"commander":"anna"}})
	check(made.ok,"自由对战房间创建")
	if not made.ok:
		return
	session.game_id = int(made.data.id)
	var joined: Dictionary = await session.request("POST","/games/%d/join"%session.game_id,{"user_name":"高差AI验证","color":"red","seat":0})
	var ai: Dictionary = await session.request("POST","/games/%d/add-ai"%session.game_id,{"difficulty":"normal","agent_kind":"rules","personality":"balanced"})
	var started: Dictionary = await session.request("POST","/games/%d/start"%session.game_id)
	check(joined.ok and ai.ok and started.ok,"自由对战真人与AI实际开局")
	if not started.ok or not joined.ok:
		return
	main._game_id = session.game_id
	main._player_id = int(joined.data.id)
	gs.local_player_id = main._player_id
	main._loaded_board_signature = ""
	main._on_start_game_response({})
	await sync_state()
	check(board.model.units.any(func(u): return u.get("hero_id")!=null),"自由模式主将立绘接入3D")
	var before: Array = []
	for p in gs.players:
		if p.is_ai:
			for u in p.units:
				before.append([u.id,u.x,u.y])
	await click_button(main.end_turn_button)
	var deadline := Time.get_ticks_msec()+35000
	await create_timer(0.5).timeout
	while Time.get_ticks_msec()<deadline and (int(gs.game_summary.get("turn_number",1))<2 or int(gs.current_player_id)!=main._player_id):
		await create_timer(0.4).timeout
	await sync_state()
	check(int(gs.game_summary.get("turn_number",1))>=2 and int(gs.current_player_id)==main._player_id,"AI真实行动后交回玩家回合")
	var after: Array = []
	for p in gs.players:
		if p.is_ai:
			for u in p.units:
				after.append([u.id,u.x,u.y])
	check(before!=after,"AI单位实际移动并同步到3D")
	await capture("ai")

func sync_state() -> void:
	var fresh: Dictionary = await session.refresh()
	check(fresh.ok,"服务端状态读取成功")
	if fresh.ok:
		session.state = fresh.data
		gs.ingest_snapshot(fresh.data)
		main._repaint_board_from_state()
	await create_timer(0.35).timeout
	await physics_frame
	await dismiss_dialogs()

func unit(color: String, kind: String) -> Dictionary:
	for p in gs.players:
		if p.color == color:
			for u in p.units:
				if u.unit_type == kind and int(u.hp)>0:
					return u
	return {}

func idle_network() -> void:
	var deadline := Time.get_ticks_msec()+15000
	await process_frame
	while (network._req_busy or not network._req_queue.is_empty()) and Time.get_ticks_msec()<deadline:
		await process_frame
	check(not network._req_busy,"正式网络请求完成")
	await create_timer(0.2).timeout

func select_unit(uid: int) -> void:
	var u: Dictionary = gs.get_unit(uid)
	await click_cell(Vector2i(int(u.x),int(u.y)))
	check(main._selected_unit_id==uid,"真实3D点击选中单位")

func move_unit(uid: int, target: Vector2i) -> void:
	await select_unit(uid)
	check(main._move_reachable_set.has(target),"正式移动范围包含目的地")
	await click_button(main.move_btn)
	if not drag_verified:
		await ensure_cell_visible(target)
		var original: Dictionary = gs.get_unit(uid).duplicate(true)
		var point: Vector2 = board.tile_to_screen(target)
		var press := InputEventMouseButton.new()
		press.button_index = MOUSE_BUTTON_LEFT
		press.position = point
		press.pressed = true
		root.push_input(press,true)
		var motion := InputEventMouseMotion.new()
		motion.position = point+Vector2(40,20)
		motion.relative = Vector2(40,20)
		motion.button_mask = MOUSE_BUTTON_MASK_LEFT
		root.push_input(motion,true)
		await process_frame
		press.pressed = false
		press.position = motion.position
		root.push_input(press,true)
		await idle_network()
		var authoritative: Dictionary = await session.refresh()
		var actual: Dictionary = {}
		for player in authoritative.data.players:
			for entry in player.units:
				if int(entry.id)==uid:
					actual = entry
		check(actual.x==original.x and actual.y==original.y and actual.mp==original.mp,"蓝格真实拖动不提交移动或消耗移动力")
		drag_verified = true
	await click_cell(target)
	await idle_network()
	await sync_state()
	var u: Dictionary = gs.get_unit(uid)
	check(Vector2i(int(u.x),int(u.y))==target,"正式移动已在服务端生效")
	check(board._unit_nodes_by_id[uid].position.distance_to(board.model.surface(target))<0.01,"3D单位落到真实格顶")

func click_cell(cell: Vector2i) -> void:
	await ensure_cell_visible(cell)
	await mouse_click(board.tile_to_screen(cell))

func ensure_cell_visible(cell: Vector2i) -> void:
	board.board_camera.focus_on(board.model.surface(cell))
	await process_frame
	await physics_frame
	# 高地遮挡时真的转动相机寻找可见顶面，不用穿透射线伪装点击成功。
	for _i in 8:
		if board.viewport_to_tile(board.tile_to_screen(cell)) == cell:
			break
		var turn := InputEventKey.new()
		turn.keycode = KEY_E
		turn.pressed = true
		root.push_input(turn,true)
		await create_timer(0.5).timeout
	check(board.viewport_to_tile(board.tile_to_screen(cell))==cell,"可见格投影与真实拾取一致")

func editor_click(eb: Node, cell: Vector2i) -> void:
	eb.board_camera.focus_on(eb.model.surface(cell))
	await process_frame
	await physics_frame
	check(eb.viewport_to_tile(eb.tile_to_screen(cell))==cell,"编辑格投影与真实拾取一致")
	await mouse_click(eb.tile_to_screen(cell))

func click_button(button: Control) -> void:
	check(button.is_visible_in_tree(),"按钮实际可见："+str(button.name))
	await mouse_click(button.get_global_rect().get_center())

func mouse_click(pos: Vector2) -> void:
	var down := InputEventMouseButton.new()
	down.button_index = MOUSE_BUTTON_LEFT
	down.position = pos
	down.global_position = pos
	down.pressed = true
	root.push_input(down,true)
	await process_frame
	var up := down.duplicate()
	up.pressed = false
	root.push_input(up,true)
	await process_frame

func dismiss_dialogs() -> void:
	var dialog := root.get_node("DialogManager")
	for _i in 12:
		if not dialog.is_playing():
			break
		await click_button(dialog._continue_btn)

func capture(suffix: String) -> void:
	var prefix := OS.get_environment("BB_FORMAL_SCREENSHOT")
	if not prefix.is_empty() and DisplayServer.get_name()!="headless":
		await process_frame
		RenderingServer.force_draw(true)
		check(root.get_texture().get_image().save_png(prefix+"-"+suffix+".png")==OK,"截图保存："+suffix)
