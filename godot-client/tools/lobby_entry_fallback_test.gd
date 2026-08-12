extends Node

const MAIN_SCENE := preload("res://scenes/main.tscn")


func _ready() -> void:
	print("=== BattleBlitz lobby entry fallback test ===")
	var main: Node = MAIN_SCENE.instantiate()
	add_child(main)
	await get_tree().process_frame
	await get_tree().process_frame

	var lobby: Node = main.get_node_or_null("Lobby")
	if lobby == null:
		_fail("lobby controller not found")
		return

	lobby.call("_on_lobby_list_saves_for_suspend_check", null, 404)
	await get_tree().process_frame

	var lobby_view: CanvasItem = main.get_node_or_null("Lobby") as CanvasItem
	var choose_panel: CanvasItem = main.get_node_or_null("Lobby/LobbyFrame/ChoosePanel") as CanvasItem
	if lobby_view == null or not lobby_view.visible:
		_fail("failed save check did not open Lobby view")
		return
	if choose_panel == null or not choose_panel.visible:
		_fail("failed save check did not show lobby choose panel")
		return

	lobby.call("_on_create_card_pressed")
	await get_tree().process_frame

	var dual_col: CanvasItem = main.get_node_or_null("Lobby/LobbyFrame/LobbyDualCol") as CanvasItem
	var create_btn: Button = main.get_node_or_null("Lobby/LobbyFrame/LobbyDualCol/RightCol/CreateRoomBtn") as Button
	if choose_panel.visible:
		_fail("create card did not hide choose panel")
		return
	if dual_col == null or not dual_col.visible:
		_fail("create card did not show create-room controls")
		return
	if create_btn == null or not create_btn.visible:
		_fail("create-room button is not visible")
		return

	print("[lobby-entry-fallback] PASS")
	get_tree().quit(0)


func _fail(message: String) -> void:
	printerr("[lobby-entry-fallback] FAIL: " + message)
	get_tree().quit(1)
