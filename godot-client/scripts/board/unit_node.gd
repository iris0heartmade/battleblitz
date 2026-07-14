extends Node2D
class_name UnitNode

var unit_data: Dictionary = {}


func setup(data: Dictionary, color: Color) -> void:
	unit_data = data
	for child in get_children():
		child.queue_free()

	var marker := ColorRect.new()
	marker.size = Vector2(24, 24)
	marker.position = -marker.size * 0.5
	marker.color = color
	marker.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(marker)

	var label := Label.new()
	label.text = String(data.get("type", "?")).left(1).to_upper()
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	label.size = Vector2(24, 24)
	label.position = -label.size * 0.5
	add_child(label)
