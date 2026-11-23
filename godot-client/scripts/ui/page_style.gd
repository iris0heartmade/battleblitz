extends RefCounted
## 非战场页面公共入口。仅移除命名装饰和设置继承主题，不触碰业务或语义色。
const Visual = preload("res://scripts/ui/visual_tokens.gd")

static func apply(page: Control) -> void:
	page.theme = Visual.create_theme()
	_style_shell(page)
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
	var menu := host.get_node_or_null("Menu") as Control
	if menu != null and not menu.has_node("MenuComposition"):
		var composition := preload("res://scripts/ui/menu_composition.gd").new()
		composition.name = "MenuComposition"
		menu.add_child(composition)
		composition.setup(menu)
	var banner := host.get_node_or_null("GameView/HUD/TopStatusArt") as TextureRect
	if banner != null:
		banner.texture = null
		banner.hide()


static func _style_shell(page: Control) -> void:
	# 管理页共用标题层级和阅读面；保留列表/表单的业务布局。
	for title_name in ["LobbyTitle", "SaveTitle", "IPTitle", "Header"]:
		var title := page.find_child(title_name, true, false) as Label
		if title != null:
			title.add_theme_font_size_override("font_size", 32)
			title.add_theme_color_override("font_color", Visual.GOLD_LIGHT)
	for frame_name in ["LobbyFrame", "SaveFrame", "IPFrame"]:
		var frame := page.get_node_or_null(frame_name) as Control
		if frame == null or frame.has_node("SectionRule"):
			continue
		var rule := ColorRect.new()
		rule.name = "SectionRule"
		rule.color = Visual.GOLD
		rule.mouse_filter = Control.MOUSE_FILTER_IGNORE
		frame.add_child(rule)
		rule.anchor_right = 1
		rule.offset_left = 30
		rule.offset_right = -30
		rule.offset_top = 88
		rule.offset_bottom = 89
	if page.name == "SettingsPanel":
		_settings_categories(page)
		var rows := page.get_node_or_null("SettingsList") as VBoxContainer
		if rows != null:
			rows.add_theme_constant_override("separation", 18)
			for row in rows.get_children():
				if row is HBoxContainer:
					row.add_theme_constant_override("separation", 12)
					for child in row.get_children():
						if child is Label:
							child.custom_minimum_size.x = 96


static func _settings_categories(page: Control) -> void:
	if page.has_node("CategoryNav"):
		return
	page.visibility_changed.connect(_settings_geometry.bind(page))
	var rows := page.get_node("SettingsList") as VBoxContainer
	rows.offset_left = 260
	rows.offset_right = -40
	var nav := VBoxContainer.new()
	nav.name = "CategoryNav"
	page.add_child(nav)
	nav.position = Vector2(36, 108)
	nav.size = Vector2(188, 320)
	nav.add_theme_constant_override("separation", 12)
	var groups := {"个人资料": ["NameRow", "ColorRow"], "显示与阅读": ["FontRow", "ThemeRow"], "声音": ["AudioRow"]}
	for category in groups:
		var button := Button.new()
		button.text = category
		button.custom_minimum_size.y = 52
		button.alignment = HORIZONTAL_ALIGNMENT_LEFT
		button.pressed.connect(_select_settings_category.bind(page, category, groups))
		nav.add_child(button)
	var space := Control.new()
	space.name = "ActionSpacer"
	space.size_flags_vertical = Control.SIZE_EXPAND_FILL
	rows.add_child(space)
	rows.move_child(space, rows.get_child_count() - 2)
	var hint := Label.new()
	hint.text = "调整后选择应用，或取消本次修改。"
	hint.add_theme_font_size_override("font_size", 16)
	hint.add_theme_color_override("font_color", Visual.DIM)
	rows.add_child(hint)
	rows.move_child(hint, rows.get_child_count() - 3)
	_select_settings_category(page, "个人资料", groups)

static func _select_settings_category(page: Control, category: String, groups: Dictionary) -> void:
	var rows := page.get_node("SettingsList")
	for group in groups:
		for row_name in groups[group]:
			rows.get_node(row_name).visible = group == category
	for button in page.get_node("CategoryNav").get_children():
		Visual.button(button, button.text == category, 20)
	(page.get_node("Header") as Label).text = "系统设置  /  " + category

static func lobby_cards(page: Control) -> void:
	var choose := page.get_node_or_null("LobbyFrame/ChoosePanel")
	if choose == null:
		return
	choose.get_node("ChooseTitle").text = "自由对战"
	choose.get_node("ChooseSubtitle").text = "创建你的战场，或加入同伴的征程"
	for card_name in ["CreateCard", "JoinCard"]:
		var card := choose.get_node("ChooseBtnRow/" + card_name) as Panel
		card.custom_minimum_size = Vector2(520, 290)
		card.add_theme_stylebox_override("panel", Visual.surface(Visual.RAISED, Visual.LINE, 24))
		var content := card.get_node(card_name + "Inner") as VBoxContainer
		content.offset_left = 30
		content.offset_top = 28
		content.offset_right = -30
		content.offset_bottom = -28
		content.add_theme_constant_override("separation", 26)
		for child in content.get_children():
			if child is Label:
				child.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
				child.modulate = Color.WHITE
				child.add_theme_color_override("font_color", Visual.TEXT if child.name.ends_with("Title") else Visual.DIM)
			elif child is Button:
				Visual.button(child, card_name == "CreateCard", 22)


static func _settings_geometry(page: Control) -> void:
	if not page.visible:
		return
	page.size.x = 1020
	page.position.x = (page.get_viewport_rect().size.x - 1020) * 0.5
	page.add_theme_stylebox_override("panel", Visual.surface(Visual.INK, Visual.LINE, 24))
