extends CanvasLayer
signal action(name: String)
signal attack_confirmed
var buttons: Dictionary = {}
var headline: Label
var info: Label
var feedback: Label
var confirmation: ConfirmationDialog

func _ready() -> void:
	var panel := PanelContainer.new()
	panel.position = Vector2(330,12)
	panel.custom_minimum_size = Vector2(925,0)
	add_child(panel)
	var margin := MarginContainer.new()
	for side in ["left","right","top","bottom"]:
		margin.add_theme_constant_override("margin_"+side,10)
	panel.add_child(margin)
	var box := VBoxContainer.new()
	margin.add_child(box)
	headline = _label(box,"地图预览｜可进入同机双人试战",18)
	var row := HBoxContainer.new()
	box.add_child(row)
	for item in [["start","开始试战"],["move","移动"],["attack","攻击"],["wait","待机"],["end","结束回合"],["refresh","同步状态"],["exit","退出试战"]]:
		var button := Button.new()
		button.text = item[1]
		button.custom_minimum_size = Vector2(92,32)
		button.pressed.connect(func(): action.emit(item[0]))
		row.add_child(button)
		buttons[item[0]] = button
	info = _label(box,"蓝色显示可移动格；攻击前会显示后端战斗预览",14)
	feedback = _label(box,"同机双人轮流操作；高度目前只影响画面",14)
	for label in [info,feedback]:
		label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		label.custom_minimum_size.x = 880
	confirmation = ConfirmationDialog.new()
	confirmation.title = "确认攻击"
	confirmation.ok_button_text = "确认攻击"
	confirmation.cancel_button_text = "取消"
	confirmation.confirmed.connect(func(): attack_confirmed.emit())
	add_child(confirmation)

func _label(parent: Node, text: String, size: int) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size",size)
	parent.add_child(label)
	return label

func sync(active: bool, busy: bool, playing: bool, has_actor: bool, can_act: bool) -> void:
	buttons.start.disabled = active or busy
	for key in ["move","attack","wait"]:
		buttons[key].disabled = not active or busy or not playing or not has_actor
	buttons.attack.disabled = buttons.attack.disabled or not can_act
	buttons.wait.disabled = buttons.wait.disabled or not can_act
	buttons.end.disabled = not active or busy or not playing
	buttons.refresh.disabled = not active or busy
	buttons.exit.disabled = not active or busy
