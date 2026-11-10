extends Node
## 仅负责HTTP与对局会话，不读取或更改正式客户端的全局GameState。

var config: Dictionary
var game_id := 0
var state: Dictionary = {}
var last_error := ""

func _init() -> void:
	config = JSON.parse_string(FileAccess.get_file_as_string("res://demos/height_map/battle.json"))
	var override_url := OS.get_environment("BB_HEIGHT_BATTLE_URL")
	if not override_url.is_empty():
		config.base_url = override_url.trim_suffix("/")

func request(method: String, path: String, body: Dictionary = {}) -> Dictionary:
	var http := HTTPRequest.new()
	http.timeout = float(config.request_timeout)
	add_child(http)
	var verb := HTTPClient.METHOD_GET if method == "GET" else HTTPClient.METHOD_POST
	var error := http.request(String(config.base_url)+path,PackedStringArray(["Content-Type: application/json"]),verb,"" if method == "GET" else JSON.stringify(body))
	if error != OK:
		http.queue_free()
		return {"ok":false,"code":0,"error":"无法发出请求，请检查试战服务"}
	var response: Array = await http.request_completed
	http.queue_free()
	if int(response[0]) != HTTPRequest.RESULT_SUCCESS:
		return {"ok":false,"code":0,"error":"试战服务连接失败或超时；请使用启动器打开Demo"}
	var json := JSON.new()
	if json.parse(response[3].get_string_from_utf8()) != OK:
		return {"ok":false,"code":int(response[1]),"error":"服务响应格式不正确"}
	var code := int(response[1])
	return {"ok":code >= 200 and code < 300,"code":code,"data":json.data,"error":"" if code >= 200 and code < 300 else str(json.data.get("detail","操作被服务拒绝"))}

func create_match() -> Dictionary:
	var health: Dictionary = await request("GET","/healthz")
	if not health.ok:
		return health
	var created: Dictionary = await request("POST","/games",{"name":config.room_name,"map_preset":config.map_preset,"map_biome":"grass","mode":config.mode,"win_condition":config.win_condition})
	if not created.ok:
		return created
	game_id = int(created.data.id)
	for player in config.players:
		var joined: Dictionary = await request("POST","/games/%d/join"%game_id,player)
		if not joined.ok:
			return joined
	return await request("POST","/games/%d/start"%game_id)

func refresh() -> Dictionary:
	return await request("GET","/games/%d/state"%game_id)

func current_player() -> int:
	return int(state.get("current_player_id",0)) if state.get("current_player_id") != null else 0

func unit_by_id(id: int) -> Dictionary:
	for player in state.get("players",[]):
		for unit in player.get("units",[]):
			if int(unit.id) == id and int(unit.hp) > 0:
				return unit
	return {}

func options(unit_id: int) -> Dictionary:
	return await request("GET","/games/%d/movement-options?player_id=%d&unit_id=%d"%[game_id,current_player(),unit_id])

func forecast(actor_id: int, target_id: int) -> Dictionary:
	return await request("GET","/games/%d/forecast-attack?player_id=%d&attacker_id=%d&target_id=%d"%[game_id,current_player(),actor_id,target_id])

func action(kind: String, fields: Dictionary) -> Dictionary:
	var body := fields.duplicate(true)
	body.player_id = current_player()
	return await request("POST","/games/%d/%s"%[game_id,kind],body)
