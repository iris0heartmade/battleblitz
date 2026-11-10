extends SceneTree
## 房间界面真实切图：二维部署预览与同一份地图JSON一致，不创建3D舞台。
const Summary = preload("res://scripts/ui/map_preview_summary.gd")
var checks := 0
var failures: Array[String] = []

func _initialize() -> void:
	call_deferred("run")
	create_timer(25).timeout.connect(func(): push_error("房间预览验证超时"); quit(1))

func check(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures.append(label)
		push_error(label)

func run() -> void:
	root.get_node("NetworkClient")._req_busy = true
	var main: Node = load("res://scenes/main.tscn").instantiate()
	root.add_child(main)
	main._show_view("lobby")
	var lobby: Node = main.lobby_view
	var records: Array = []
	for map_id in ["balanced_2p_15","balanced_4p_20"]:
		records.append(JSON.parse_string(FileAccess.get_file_as_string("res://../game/maps/%s.json"%map_id)))
	# 高度是独立数据，房间缩略图不改变它，也不从3D网格反推原始地图。
	var elevations: Array = []
	for _y in 15:
		var row: Array = []
		row.resize(15)
		row.fill(0)
		elevations.append(row)
	elevations[7][7] = -5
	elevations[7][8] = 5
	records[0].elevations = elevations
	records.append({"id":"classic","name":"随机地图","size":15,"layout":[],"initial_units":[],"recommended_players":2})
	var before := records.duplicate(true)
	lobby._setup_lobby_map_player_count_options()
	lobby._on_lobby_presets_response({"maps":records})
	lobby._show_lobby_create_view()
	for index in 2:
		lobby.map_preset_option.select(index)
		lobby._on_lobby_map_preset_selected(index)
		await process_frame
		var texture: Texture2D = lobby.map_preview_texture.texture
		check(texture is ImageTexture,"房间显示二维缩略图")
		var image: Image = texture.get_image()
		var dimension := 15 if index==0 else 20
		check(image.get_size()==Vector2i(dimension*9,dimension*9),"缩略图大小与逻辑格一致")
		for unit in records[index].initial_units:
			var center := Vector2i(int(unit.x)*9+4,int(unit.y)*9+4)
			var actual: Color = image.get_pixelv(center)
			var expected: Color = Summary.PLAYER_COLORS[unit.color]
			# RGBA8图片有1/255的量化精度，不使用浮点颜色的近零误差阈值。
			var delta := Vector4(actual.r-expected.r,actual.g-expected.g,actual.b-expected.b,actual.a-expected.a).abs()
			check(maxf(maxf(delta.x,delta.y),maxf(delta.z,delta.w))<=1.0/255.0,"单位部署位置和阵营颜色一致：%s"%unit.color)
		check(lobby.map_faction_summary.text.contains("中立"),"保留建筑与阵营文字摘要")
	check(lobby.map_preview_texture.find_children("*","SubViewport",true,false).is_empty(),"房间预览不创建3D视口")
	check(records==before,"预览不改变原JSON，包括高度矩阵")
	var output := OS.get_environment("BB_LOBBY_SCREENSHOT")
	if not output.is_empty() and DisplayServer.get_name()!="headless":
		await process_frame
		RenderingServer.force_draw(true)
		check(root.get_texture().get_image().save_png(output)==OK,"真实房间界面截图")
	lobby.map_preset_option.select(2)
	lobby._on_lobby_map_preset_selected(2)
	check(lobby.map_preview_texture.texture==null,"随机地图不伪造地形缩略图")
	check(lobby.map_faction_summary.text.contains("开局时生成"),"随机地图提示生成时机")
	check(main.board.board_camera is Camera3D,"正式战场仍使用高差3D相机")
	print("[lobby-map-preview] checks=%d failures=%d"%[checks,failures.size()])
	quit(0 if failures.is_empty() else 1)
