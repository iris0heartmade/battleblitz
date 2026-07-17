extends Node
## views_screenshot.gd — 一键截图所有 view
func _ready() -> void:
	print("AAA _ready fired")
	var packed: PackedScene = load("res://scenes/main.tscn")
	print("BBB loaded=" + str(packed != null))
	if packed == null:
		get_tree().quit()
		return
	var main_inst: Node = packed.instantiate()
	print("CCC inst=" + str(main_inst != null))
	get_tree().root.add_child(main_inst)
	print("DDD added")
	await get_tree().create_timer(2.0).timeout
	print("EEE timer fired")
	main_inst.call("_show_view", "menu")
	await get_tree().create_timer(0.5).timeout
	print("FFF shooting")
	_shoot(main_inst, "view_menu")
	get_tree().quit()

func _shoot(main_inst: Node, label: String) -> void:
	var vp: Viewport = main_inst.get_viewport()
	var img: Image = vp.get_texture().get_image() if vp != null else null
	if img == null or img.is_empty():
		print("[VIEWS] %s: empty" % label)
		return
	var path: String = ProjectSettings.globalize_path("user://diag_%s.png" % label)
	img.save_png(path)
	print("[VIEWS] %s -> %s (%dx%d)" % [label, path, img.get_width(), img.get_height()])

