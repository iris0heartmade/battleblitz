extends Node
## live_screenshot.gd — drive a real game session and capture UI with live WS data.
##
## Prereq: FastAPI backend listening on 127.0.0.1:8000.
## Triggers the same auto-play flow as a real player (create game →
## join → add AI → start → WS connect → state.snapshot) and waits
## for the snapshot to land in GameState before snapping.

const _OUT_PATH := "user://live_screenshot.png"
const _WAIT_FOR_SNAPSHOT_SEC := 8.0


func _ready() -> void:
	# Set BB_AUTO_PLAY before main's _ready runs so the standard
	# pipeline drives the flow.
	OS.set_environment("BB_AUTO_PLAY", "1")
	for i in 3:
		await RenderingServer.frame_post_draw
	# Manually trigger the free-play flow.
	var main_app: Node = get_tree().current_scene
	if main_app.name == "LiveScreenshot":
		main_app = main_app.get_child(0) if main_app.get_child_count() > 0 else main_app
	if main_app != null and main_app.has_method("_start_dev_ai_game"):
		main_app.call("_start_dev_ai_game")
	# Wait for state.snapshot.
	var deadline: float = Time.get_ticks_msec() + int(_WAIT_FOR_SNAPSHOT_SEC * 1000.0)
	while Time.get_ticks_msec() < deadline:
		if GameState != null and GameState.players.size() > 0 and GameState.tiles.size() > 0:
			break
		await RenderingServer.frame_post_draw
	# Switch to game view.
	var game_view: Node = main_app.find_child("GameView", true, false)
	if game_view != null:
		game_view.visible = true
		var menu: Node = main_app.find_child("Menu", true, false)
		if menu != null:
			menu.visible = false
		var connecting: Node = main_app.find_child("Connecting", true, false)
		if connecting != null:
			connecting.visible = false
	for i in 6:
		await RenderingServer.frame_post_draw
	var img: Image = get_viewport().get_texture().get_image()
	if img == null:
		printerr("viewport returned null image")
		get_tree().quit(1)
		return
	img.save_png(_OUT_PATH)
	img.save_png("res://live_screenshot.png")
	print("Saved live screenshot → %s (state: %d players, %d tiles, turn %s)" % [
		_OUT_PATH,
		GameState.players.size() if GameState != null else 0,
		GameState.tiles.size() if GameState != null else 0,
		str(GameState.game_summary.get("turn_number", "?")) if GameState != null else "?",
	])
	get_tree().quit(0)
