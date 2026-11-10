extends SceneTree
## 真实HTTP后端端到端试战；不修改数据库中的坐标、血量或战斗结果。
var demo: Node3D
var checks := 0
var failures: Array[String] = []

func _initialize() -> void:
	call_deferred("run")
	create_timer(120).timeout.connect(func():
		push_error("[height-battle verification] timed out")
		quit(1))

func check(condition: bool, name: String) -> void:
	checks += 1
	if not condition:
		failures.append(name)
		push_error("[height-battle verification] " + name)

func settle() -> void:
	var deadline := Time.get_ticks_msec()+20000
	await process_frame
	while demo.battle.busy and Time.get_ticks_msec() < deadline:
		await process_frame
	check(not demo.battle.busy,"异步操作完成")

func run() -> void:
	demo = load("res://demos/height_map/main.tscn").instantiate()
	root.add_child(demo)
	await process_frame
	var original: Dictionary = demo.model.snapshot()
	await click(demo.battle.ui.buttons.start)
	await settle()
	check(demo.battle.active,"真实创建并开始同机对局")
	if not demo.battle.active:
		print(demo.battle.ui.feedback.text)
		quit(1)
		return
	check(demo.model.units.size()==10,"后端10个单位同步到3D地图")
	check(not demo.editor.height_input.editable and demo.editor.preset_input.disabled,"战斗中禁用地图编辑")
	var h: int = demo.model.elevation(demo.selected)
	demo.edit_selected(5)
	check(demo.model.elevation(demo.selected)==h,"直接编辑入口也被锁住")
	var url: String = demo.battle.session.config.base_url
	var before_disconnect: Dictionary = demo.model.snapshot()
	demo.battle.session.config.base_url = "http://127.0.0.1:1"
	await demo.battle.handle_action("refresh")
	check(demo.battle.desynced and demo.battle.ui.buttons.end.disabled,"断线后禁用战斗操作")
	check(demo.model.snapshot()==before_disconnect,"断线未伪造状态变化")
	demo.battle.session.config.base_url = url
	await demo.battle.handle_action("refresh")
	check(not demo.battle.desynced,"重新同步恢复操作")
	var red_id := find_unit("red","warlock")
	var blue_id := find_unit("blue","warlock")
	var actor: Dictionary = demo.battle.session.unit_by_id(red_id)
	await click_unit(actor)
	await settle()
	check(demo.battle.actor_id==red_id and demo.battle.moves.size()>1,"真实点击单位得到后端移动范围")
	check(demo.battle.moves.has(Vector2i(6,7)),"原图前线格可达")
	await capture("range")
	var bad: Dictionary = await demo.battle.session.action("move",{"unit_id":red_id,"to_x":14,"to_y":14})
	check(not bad.ok,"远距离非法移动被后端拒绝")
	var from := Vector2i(int(actor.x),int(actor.y))
	check(demo.model.unit_at(from).id==red_id,"非法移动未改变3D站位")
	demo.camera.focus_on(demo.model.surface(Vector2i(6,7)))
	await physics_frame
	# 在蓝格上按下并拖动属于浏览，不得在按下时就提交移动。
	var drag_origin: Vector2 = demo.camera.unproject_position(demo.model.surface(Vector2i(6,7)))
	var press := InputEventMouseButton.new()
	press.position = drag_origin
	press.button_index = MOUSE_BUTTON_LEFT
	press.pressed = true
	root.push_input(press,true)
	await process_frame
	var motion := InputEventMouseMotion.new()
	motion.position = drag_origin+Vector2(30,15)
	motion.relative = Vector2(30,15)
	motion.button_mask = MOUSE_BUTTON_MASK_LEFT
	root.push_input(motion,true)
	await process_frame
	press = press.duplicate()
	press.position = motion.position
	press.pressed = false
	root.push_input(press,true)
	await process_frame
	check(not demo.battle.busy and int(demo.battle.session.unit_by_id(red_id).x)==from.x,"蓝格拖动画面不会误提交移动")
	demo.camera.focus_on(demo.model.surface(Vector2i(6,7)))
	await physics_frame
	await click_at(root,demo.camera.unproject_position(demo.model.surface(Vector2i(6,7))))
	await settle()
	actor = demo.battle.session.unit_by_id(red_id)
	check(int(actor.x)==6 and int(actor.y)==7 and int(actor.mp)<int(actor.mov),"真实点击目的地完成移动并扣除移动力")
	check(demo.terrain.contents.unit_nodes.has(Vector2i(6,7)) and not demo.terrain.contents.unit_nodes.has(from),"动画后站位与后端一致")
	await capture("move")
	await click(demo.battle.ui.buttons.end)
	await settle()
	check(int(demo.battle.session.unit_by_id(blue_id).player_id)==demo.battle.session.current_player(),"结束回合切到蓝方")
	actor = demo.battle.session.unit_by_id(blue_id)
	await click_unit(actor)
	await settle()
	check(demo.battle.moves.has(Vector2i(8,7)),"蓝方前线格可达")
	await demo.battle.move_to(Vector2i(8,7))
	await settle()
	await click(demo.battle.ui.buttons.attack)
	check(demo.battle.attack_targets.has(red_id),"攻击范围包含敌方前线单位")
	var defender_before: Dictionary = demo.battle.session.unit_by_id(red_id).duplicate(true)
	var attacker_before: Dictionary = demo.battle.session.unit_by_id(blue_id).duplicate(true)
	await demo.battle.preview_attack(red_id)
	check(demo.battle.ui.confirmation.visible,"攻击前真实服务预览与确认框")
	await process_frame
	await click(demo.battle.ui.confirmation.get_ok_button())
	await settle()
	check(demo.battle.last_result.ok,"确认框提交真实攻击")
	if not demo.battle.last_result.get("data",{}).has("target_hp_after"):
		check(false,"确认攻击未收到伤害结果")
		quit(1)
		return
	var result: Dictionary = demo.battle.last_result.data
	check(int(result.target_hp_after)<int(defender_before.hp),"后端结算目标扣血")
	check(int(result.attacker_hp_after)<int(attacker_before.hp) and int(result.counter_damage)>0,"后端结算反击伤害")
	var defender_after: Dictionary = demo.battle.session.unit_by_id(red_id)
	check(not defender_after.is_empty() and int(defender_after.hp)==int(result.target_hp_after),"3D单位血量与权威快照一致")
	check(demo.battle.session.unit_by_id(blue_id).has_acted,"攻击后行动标记生效")
	var duplicate: Dictionary = await demo.battle.session.action("attack",{"attacker_id":blue_id,"target_id":red_id})
	check(not duplicate.ok,"同一单位重复攻击被拒绝")
	await capture("attack")
	await click(demo.battle.ui.buttons.end)
	await settle()
	# 待机走真实接口，检查行动锁与下一回合恢复。
	var swordsman_id := find_unit("red","swordsman")
	demo.battle.actor_id = swordsman_id
	demo.battle._sync()
	await click(demo.battle.ui.buttons.wait)
	await settle()
	check(demo.battle.session.unit_by_id(swordsman_id).has_acted,"待机标记同步")
	# 按规则自动轮流操作这局直到分胜负：每次移动/攻击都经同一控制器和HTTP。
	var safety := 0
	var attacks := 0
	while demo.battle.session.state.game.status=="playing" and safety < 45:
		var side: int = demo.battle.session.current_player()
		var ids: Array = []
		for unit in demo.model.units:
			if int(unit.player_id)==side and not unit.has_acted:
				ids.append(int(unit.id))
		for id in ids:
			if demo.battle.session.state.game.status != "playing":
				break
			var own: Dictionary = demo.battle.session.unit_by_id(id)
			if own.is_empty() or own.has_acted:
				continue
			demo.battle.actor_id = id
			await demo.battle.show_moves()
			var best := Vector2i(int(own.x),int(own.y))
			var score := distance_score(own,best)
			for p in demo.battle.moves:
				var candidate := distance_score(own,p)
				if candidate < score:
					score = candidate
					best = p
			if best != Vector2i(int(own.x),int(own.y)):
				await demo.battle.move_to(best)
			demo.battle.show_attacks()
			if not demo.battle.attack_targets.is_empty():
				var target := int(demo.battle.attack_targets.keys()[0])
				await demo.battle.preview_attack(target)
				if demo.battle.ui.confirmation.visible:
					await click(demo.battle.ui.confirmation.get_ok_button())
					await settle()
					attacks += 1
		if demo.battle.session.state.game.status == "playing":
			await demo.battle.handle_action("end")
		safety += 1
	check(attacks>0 and demo.battle.session.state.game.status=="finished","真实移动攻击直到整局结束")
	check(demo.model.units.size()<10,"阵亡单位从地图移除")
	check(demo.battle.ui.buttons.end.disabled and demo.battle.ui.buttons.attack.disabled,"结算后禁用行动")
	await capture("finished")
	await click(demo.battle.ui.buttons.exit)
	check(not demo.battle.active and demo.model.snapshot()==original,"退出试战恢复原地图编辑内容")
	check(demo.editor.height_input.editable,"退出后重新允许编辑")
	print("[height-battle verification] checks=%d failures=%d turns=%d attacks=%d"%[checks,failures.size(),safety,attacks])
	demo.queue_free()
	await process_frame
	quit(0 if failures.is_empty() else 1)

func find_unit(color: String, type: String) -> int:
	for unit in demo.model.units:
		if unit.color==color and unit.type==type:
			return int(unit.id)
	return -1

func distance_score(own: Dictionary, p: Vector2i) -> int:
	var best := 99999
	for enemy in demo.model.units:
		if int(enemy.player_id)==int(own.player_id):
			continue
		var distance := absi(p.x-int(enemy.x))+absi(p.y-int(enemy.y))
		best = mini(best,maxi(maxi(int(own.min_attack_range)+1-distance,distance-int(own.attack_range)),0))
	return best

func click_unit(unit: Dictionary) -> void:
	var p := Vector2i(int(unit.x),int(unit.y))
	demo.camera.focus_on(demo.model.surface(p))
	await physics_frame
	await click_at(root,demo.camera.unproject_position(demo.model.surface(p)+Vector3.UP*0.9))

func click(control: Control) -> void:
	var viewport := control.get_viewport()
	var point := control.get_global_rect().get_center()
	if viewport is Window and viewport != root and viewport.is_embedded():
		point += Vector2(viewport.position)
		viewport = root
	await click_at(viewport,point)

func click_at(viewport: Viewport, position: Vector2) -> void:
	var motion := InputEventMouseMotion.new()
	motion.position = position
	viewport.push_input(motion,true)
	await process_frame
	for pressed in [true,false]:
		var event := InputEventMouseButton.new()
		event.position = position
		event.pressed = pressed
		event.button_index = MOUSE_BUTTON_LEFT
		viewport.push_input(event,true)
		await process_frame

func capture(suffix: String) -> void:
	var output := OS.get_environment("BB_BATTLE_SCREENSHOT")
	if not output.is_empty() and DisplayServer.get_name() != "headless":
		await process_frame
		RenderingServer.force_draw(true)
		check(root.get_texture().get_image().save_png(output+"-"+suffix+".png")==OK,"GPU截图："+suffix)
