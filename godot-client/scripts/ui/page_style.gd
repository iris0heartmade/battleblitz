extends RefCounted
## 非战场页面公共入口。仅移除命名装饰和设置继承主题，不触碰业务或语义色。
const Visual = preload("res://scripts/ui/visual_tokens.gd")

static func apply(page: Control) -> void:
	page.theme = Visual.create_theme()
	for ornament in page.find_children("Ornate*", "", true, false):
		if ornament is NinePatchRect:
			ornament.hide()
	for border in page.find_children("*Border", "ReferenceRect", true, false):
		border.hide()
	for path in ["LobbyFrame", "SaveFrame", "IPFrame", "EditorHud/EditorPanel"]:
		var panel := page.get_node_or_null(path) as Control
		if panel is ColorRect:
			panel.color = Visual.PANEL
		elif panel != null:
			panel.add_theme_stylebox_override("panel", Visual.surface())

## 在 HudTheme 完成样式注入后调用，清除场景静态装饰并覆盖通用浮层。
static func apply_root(host: Node) -> void:
	for path in ["Menu", "Connecting", "GameView/HUD/SettingsPanel", "GameView/HUD/PausePanel"]:
		var page := host.get_node_or_null(path) as Control
		if page == null:
			continue
		apply(page)
		if page.name in ["SettingsPanel", "PausePanel"]:
			for button in page.find_children("*", "Button", true, false):
				Visual.button(button, button.name in ["ApplyBtn", "ResumeBtn"], button.get_theme_font_size("font_size"), button.name == "QuitBtn")
		if page is Panel:
			page.add_theme_stylebox_override("panel", Visual.surface(Visual.PANEL, Visual.LINE, 24))
	var banner := host.get_node_or_null("GameView/HUD/TopStatusArt") as TextureRect
	if banner != null:
		banner.texture = null
		banner.hide()
