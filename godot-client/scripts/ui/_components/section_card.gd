## section_card.gd — UI V3 section 容器(PanelContainer + SectionHeader + body)。
##
## 用法:
##   var card := SectionCard.new("三存档槽", body_vbox, "按需手存,每槽独立")
##   add_child(card)
##
## 视觉:深绿底 + 烫金 4px 边框 + 内边距 PAD_L + 顶部 SectionHeader。
## 全部 token 走 MenuTheme。

class_name SectionCard
extends PanelContainer

const MenuTheme = preload("res://scripts/ui/menu_theme.gd")

var _header: SectionHeader
var _body: Control


func _init(title: String = "", body: Control = null, hint: String = "") -> void:
	mouse_filter = Control.MOUSE_FILTER_PASS
	# Panel 主题:深绿底 + 烫金边 + 内边距
	MenuTheme.apply_panel_theme(self, MenuTheme.C_BG_PANEL)
	# 内边距(PAD_L = 24)
	var sb: StyleBoxFlat = get_theme_stylebox("panel").duplicate()
	sb.content_margin_left = MenuTheme.PAD_L
	sb.content_margin_right = MenuTheme.PAD_L
	sb.content_margin_top = MenuTheme.PAD_M
	sb.content_margin_bottom = MenuTheme.PAD_M
	add_theme_stylebox_override("panel", sb)
	# 内部用 VBoxContainer 装 header + body
	var vbox := VBoxContainer.new()
	vbox.add_theme_constant_override("separation", MenuTheme.GAP_M)
	vbox.mouse_filter = Control.MOUSE_FILTER_PASS
	add_child(vbox)
	# Header(可省,纯 body 也能用)
	if title != "":
		_header = SectionHeader.new(title, hint)
		vbox.add_child(_header)
	# Body(外部传入)
	_body = body if body != null else VBoxContainer.new()
	vbox.add_child(_body)


func get_body() -> Control:
	return _body


func get_header() -> SectionHeader:
	return _header