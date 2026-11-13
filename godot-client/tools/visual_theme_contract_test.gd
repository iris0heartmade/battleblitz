extends SceneTree
const Visual = preload("res://scripts/ui/visual_tokens.gd")
const Menu = preload("res://scripts/ui/menu_theme.gd")

func _initialize() -> void:
	var button := Button.new()
	Menu.apply_primary_button_theme(button)
	var result := {}
	for state in ["normal", "hover", "pressed", "disabled", "focus"]:
		var box := button.get_theme_stylebox(state) as StyleBoxFlat
		result[state] = {"fill": box.bg_color.to_html(), "border": box.border_color.to_html(), "left": box.border_width_left, "right": box.border_width_right}
	result["tokens"] = {"blue": Visual.HOVER.to_html(), "gold": Visual.GOLD.to_html(), "focus": Visual.GOLD_LIGHT.to_html()}
	print("CONTRACT_RESULT=" + JSON.stringify(result))
	button.free()
	quit()
