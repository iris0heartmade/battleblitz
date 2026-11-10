extends Node
## 对局编排：后端确认 → 移动/受击反馈 → 最新状态落到3D地图。
const Session = preload("res://demos/height_map/battle_session.gd")
const BattleUI = preload("res://demos/height_map/battle_ui.gd")
const Overlay = preload("res://demos/height_map/battle_overlay.gd")
var host: Node3D
var session: Node
var ui: CanvasLayer
var overlay: Node3D
var active := false
var busy := false
var desynced := false
var actor_id := -1
var mode := "idle"
var moves: Dictionary = {}
var attack_targets: Dictionary = {}
var target_id := -1
var editor_snapshot: Dictionary = {}
var last_result: Dictionary = {}

func setup(scene: Node3D) -> void:
	host = scene
	session = Session.new()
	add_child(session)
	ui = BattleUI.new()
	add_child(ui)
	overlay = Overlay.new()
	host.add_child(overlay)
	ui.action.connect(handle_action)
	ui.attack_confirmed.connect(_confirm_attack)
	_sync()

func _set_busy(value: bool) -> void:
	busy = value
	host.editor.set_editing_enabled(not active and not busy)
	host._sync()
	_sync()

func _sync() -> void:
	var actor: Dictionary = session.unit_by_id(actor_id)
	var playing: bool = active and session.state.get("game",{}).get("status","") == "playing"
	ui.sync(active,busy,playing and not desynced,not actor.is_empty(),not actor.get("has_acted",true))
	if active:
		var faction := ""
		for player in session.state.get("players",[]):
			if int(player.id) == session.current_player():
				faction = host.model.rules.factions[player.color].name
		ui.headline.text = "同机双人｜第%d回合｜%s行动%s" % [int(session.state.get("game",{}).get("turn_number",1)),faction," · 处理中" if busy else ""]
		if not playing:
			var survivors: Array = []
			for player in session.state.get("players",[]):
				if player.is_alive and player.units.any(func(u: Dictionary): return int(u.hp)>0):
					survivors.append(String(host.model.rules.factions[player.color].name))
			ui.headline.text = "战斗结束｜" + (str(survivors[0])+"获胜" if survivors.size()==1 else "已完成结算")
		if desynced:
			ui.headline.text = "连接中断｜请先同步状态"
		if not actor.is_empty():
			ui.info.text = "%s｜生命 %d/%d｜移动力 %d｜%s" % [host.model.rules.unit_names.get(actor.unit_type,actor.name),int(actor.hp),int(actor.max_hp),int(actor.mp),"已行动" if actor.has_acted else "可行动"]
		else:
			ui.info.text = "请选择当前阵营单位；方向键只移动光标"
	else:
		ui.headline.text = "地图预览｜可进入同机双人试战"

func start_match() -> void:
	if active or busy:
		return
	if host.model.map_id != "balanced_2p_15":
		ui.feedback.text = "请先切换到2人标准图"
		return
	editor_snapshot = host.model.snapshot()
	_set_busy(true)
	ui.feedback.text = "正在连接独立试战服务并创建对局…"
	var result: Dictionary = await session.create_match()
	if not result.ok:
		ui.feedback.text = result.error
		_set_busy(false)
		return
	var import_error: String = host.model.import_standard()
	if not import_error.is_empty():
		ui.feedback.text = import_error
		_set_busy(false)
		return
	active = true
	host.camera.top_inset = 160
	host.editor.set_editing_enabled(false)
	_apply_state(result.data,true)
	ui.feedback.text = "试战已开始：点击己方单位，再选择移动或攻击。高差仅用于显示。"
	_set_busy(false)

func _apply_state(snapshot: Dictionary, focus_turn: bool = false) -> void:
	desynced = false
	session.state = snapshot
	var color_for_id: Dictionary = {}
	var live_units: Array = []
	for player in snapshot.players:
		color_for_id[int(player.id)] = player.color
		for source in player.units:
			if int(source.hp) <= 0:
				continue
			var unit: Dictionary = source.duplicate(true)
			unit.type = source.unit_type
			unit.color = player.color
			live_units.append(unit)
	host.model.units = live_units
	for tile in snapshot.tiles:
		var p := Vector2i(int(tile.x),int(tile.y))
		if host.model.contains(p):
			host.model.cell(p).faction = color_for_id.get(int(tile.owner_id),"neutral") if tile.owner_id != null else "neutral"
	var actor: Dictionary = session.unit_by_id(actor_id)
	if actor.is_empty() or int(actor.player_id) != session.current_player():
		actor_id = -1
		focus_turn = true
	if focus_turn:
		for unit in host.model.units:
			if int(unit.player_id) == session.current_player():
				actor_id = int(unit.id)
				host.selected = Vector2i(int(unit.x),int(unit.y))
				break
	else:
		host.selected = Vector2i(int(actor.x),int(actor.y))
	host.terrain.selected = host.selected
	host.terrain.rebuild()
	if focus_turn:
		host.camera.focus_on(host.model.surface(host.selected))
	host._sync()
	mode = "idle"
	moves.clear()
	attack_targets.clear()
	overlay.clear()
	_sync()

func select_cell(p: Vector2i) -> void:
	if busy or ui.confirmation.visible:
		return
	var unit: Dictionary = host.model.unit_at(p)
	if mode == "move" and moves.has(p) and (unit.is_empty() or int(unit.id) != actor_id):
		await move_to(p)
		return
	if mode == "attack" and not unit.is_empty() and attack_targets.has(int(unit.id)):
		await preview_attack(int(unit.id))
		return
	host.select_cell(p)
	if not unit.is_empty() and int(unit.player_id) == session.current_player():
		actor_id = int(unit.id)
		await show_moves()
	else:
		ui.feedback.text = "请选择当前行动方的单位" if not unit.is_empty() else "点击己方单位后选择行动"

func show_moves() -> void:
	if busy or actor_id < 0:
		return
	_set_busy(true)
	var result: Dictionary = await session.options(actor_id)
	moves.clear()
	if result.ok:
		for tile in result.data.tiles:
			moves[Vector2i(int(tile.x),int(tile.y))] = tile
		mode = "move"
		overlay.show_cells(host.model,moves.keys(),Color(0.2,0.6,1,0.42))
		ui.feedback.text = "蓝色格子可移动；点击目的地，由后端确认后移动" if moves.size()>1 else "移动力不足或没有可到达的空格"
	else:
		ui.feedback.text = result.error
	_set_busy(false)

func show_attacks() -> void:
	var actor: Dictionary = session.unit_by_id(actor_id)
	if actor.is_empty():
		return
	mode = "attack"
	attack_targets.clear()
	var cells: Array = []
	for unit in host.model.units:
		var distance := absi(int(actor.x)-int(unit.x))+absi(int(actor.y)-int(unit.y))
		if int(unit.player_id) != session.current_player() and distance > int(actor.get("min_attack_range",0)) and distance <= int(actor.attack_range):
			attack_targets[int(unit.id)] = true
			cells.append(Vector2i(int(unit.x),int(unit.y)))
	overlay.show_cells(host.model,cells,Color(1,0.25,0.2,0.48))
	ui.feedback.text = "点击红色目标查看伤害与反击预览" if not cells.is_empty() else "当前没有射程内敌人，可先移动接近"

func preview_attack(id: int) -> void:
	_set_busy(true)
	var result: Dictionary = await session.forecast(actor_id,id)
	if result.ok:
		target_id = id
		ui.confirmation.dialog_text = "预计伤害 %d（暴击时 %d）\n预计反击 %d\n确认后由后端结算，实际结果可能受暴击影响。" % [int(result.data.damage),int(result.data.crit_damage),int(result.data.counter_damage)]
		ui.confirmation.popup_centered(Vector2i(490,190))
	else:
		ui.feedback.text = result.error
	_set_busy(false)

func move_to(p: Vector2i) -> void:
	if busy or not moves.has(p):
		return
	var path: Array = moves[p].path.duplicate(true)
	_set_busy(true)
	var result: Dictionary = await session.action("move",{"unit_id":actor_id,"to_x":p.x,"to_y":p.y})
	last_result = result
	if result.ok:
		await _animate_move(actor_id,path)
	await _finish_action(result)

func _animate_move(id: int, path: Array) -> void:
	var actor: Dictionary = session.unit_by_id(id)
	if actor.is_empty():
		return
	var key := Vector2i(int(actor.x),int(actor.y))
	if not host.terrain.contents.unit_nodes.has(key):
		return
	var anchor: Node3D = host.terrain.contents.unit_nodes[key].anchor
	for point in path.slice(1):
		var target: Vector3 = host.model.surface(Vector2i(int(point.x),int(point.y)))
		host.camera.keep_visible(target+Vector3.UP*0.6)
		var tween := create_tween()
		tween.tween_property(anchor,"position",target,float(session.config.move_step_seconds))
		await tween.finished

func _confirm_attack() -> void:
	if busy or target_id < 0:
		return
	_set_busy(true)
	var result: Dictionary = await session.action("attack",{"attacker_id":actor_id,"target_id":target_id})
	last_result = result
	if result.ok:
		var target: Dictionary = session.unit_by_id(target_id)
		var key := Vector2i(int(target.get("x",-1)),int(target.get("y",-1)))
		if host.terrain.contents.unit_nodes.has(key):
			var sprite: Sprite3D = host.terrain.contents.unit_nodes[key].sprite
			var previous_color := sprite.modulate
			sprite.modulate = Color(1,0.25,0.25)
			await get_tree().create_timer(float(session.config.attack_flash_seconds)).timeout
			if is_instance_valid(sprite):
				sprite.modulate = previous_color
	await _finish_action(result)

func _finish_action(result: Dictionary, turn_changed: bool = false) -> void:
	# 不重发可能已执行的POST；不论成功/失败都尝试同步权威状态。
	var refreshed: Dictionary = await session.refresh()
	if refreshed.ok:
		_apply_state(refreshed.data,turn_changed)
	ui.feedback.text = _result_text(result.data) if result.ok else result.error
	if not refreshed.ok:
		desynced = true
		ui.feedback.text += "；状态同步失败，请点击同步状态确认"
	_set_busy(false)

func _result_text(data: Dictionary) -> String:
	if data.has("hits"):
		var damage := 0
		for hit in data.hits:
			damage += int(hit.damage)
		return "攻击造成 %d 点伤害，受到 %d 点反击；目标剩余生命 %d" % [damage,int(data.counter_damage),int(data.target_hp_after)]
	if data.has("cost"):
		return "移动至 (%d,%d)，消耗 %d 点移动力" % [int(data.to_x),int(data.to_y),int(data.cost)]
	if data.has("next_player_id"):
		return "回合已交接，请操作新的行动方"
	return "单位已待机"

func handle_action(action: String) -> void:
	if busy or (not active and action != "start") or (desynced and action not in ["refresh","exit"]):
		return
	match action:
		"start": await start_match()
		"move": await show_moves()
		"attack": show_attacks()
		"wait", "end":
			_set_busy(true)
			var result: Dictionary = await session.action("wait" if action == "wait" else "end-turn",{"unit_id":actor_id} if action == "wait" else {})
			last_result = result
			await _finish_action(result,action == "end")
		"refresh":
			_set_busy(true)
			var result: Dictionary = await session.refresh()
			if result.ok:
				_apply_state(result.data)
			else:
				desynced = true
			ui.feedback.text = "已同步后端状态" if result.ok else result.error
			_set_busy(false)
		"exit":
			active = false
			host.camera.top_inset = 80
			actor_id = -1
			mode = "idle"
			overlay.clear()
			host.model.restore(editor_snapshot)
			host.editor.set_editing_enabled(true)
			host._reload_board()
			_sync()
			ui.feedback.text = "已回到进入试战前的地图编辑状态"
