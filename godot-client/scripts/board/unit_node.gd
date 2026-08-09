extends Node2D
class_name UnitNode
## M4.7 — 重写单位节点,新增 HP bar / MP badge / 士气星 + 阵营色边框
##
## 数据字典由 Board._rebuild_units 传入,典型 shape(UnitOut schema):
## {
##   id: int,
##   unit_type: String ("archer"/"swordsman"/"knight"/"healer"/"warlock"/"heavy_armor"/...),
##   player_id: int (owner),
##   color: String (player color: "red"/"blue"/...),
##   level: int (1-3),
##   hp: int, max_hp: int,
##   mp: int, mov: int,
##   morale: int (0-3,or 0-5 visualised),
##   has_acted: bool, has_moved: bool,
##   x: int, y: int
## }
##
## Icon source: 镜像 app.js 的 unitSpriteUrl — 复用 web 的
## `assets/classic/<unit_type>.png`(7 类),作为 TextureRect 渲染。
## Hero(esprit):先不支持,fallback 默认色块 + 单字母 label。
##
## M4.tiny — 之前用 `data.type` 第一字母是 bug:UnitOut 的字段名是
## `unit_type`。这解释了为什么之前 unit 都是 "?"。

const _SPRITE_DIR := "res://assets/classic/"
const _HERO_SPRITE_DIR := "res://assets/heroes/"
# 镜像 game/app/web/assets/classic/ 7 类 sprite
const _KNOWN_TYPES := [
	"archer", "berserker", "blade_master", "dragon_rider",
	"falcon_knight", "healer", "heavy_armor", "knight",
	"lancer", "paladin", "sage", "saint", "sniper",
	"swordsman", "warlock", "warrior",
]
# 英雄单位 — 用 hero 立绘(anna.png / yun.png)替代 base class sprite。
# 后续可在 .import 注册更多(用 `find_hero_sprite_path` 字典扩展)。
const _HERO_SPRITES := {
	"anna": "anna.png",
	"yun":  "yun.png",
	"yuanying": "yuanying.png",
}
# team_id → 右上角字母(team_a=A / team_b=B / team_c=C / team_d=D)。
# 1V1 free-for-all(team=None)→ 不显示字母,只显示阵营色块。
const _TEAM_GLYPH := {
	"team_a": "A",
	"team_b": "B",
	"team_c": "C",
	"team_d": "D",
}
# 没 sprite 时 fallback 单字母 + 颜色
const _FALLBACK_GLYPH := {
	"archer":      "A",
	"healer":      "H",
	"heavy_armor": "T",
	"knight":      "K",
	"swordsman":   "S",
	"warlock":     "W",
}

const _TILE_WIDTH := 48
const _COL_HP_GREEN := Color(0.50, 0.86, 0.55)
const _COL_HP_YELLOW := Color(0.97, 0.78, 0.37)
const _COL_HP_RED := Color(0.91, 0.36, 0.42)
const _COL_BG_BAR := Color(0.05, 0.05, 0.05, 0.85)
const _COL_MP_BLUE := Color(0.31, 0.71, 0.95)
const _COL_STAR := Color(0.96, 0.85, 0.30)

var unit_data: Dictionary = {}
var _marker: ColorRect = null
var _sprite: TextureRect = null
var _type_label: Label = null
var _star_label: Label = null
var _hp_bar: ColorRect = null
var _hp_bar_bg: ColorRect = null
var _mp_badge: ColorRect = null
var _mp_badge_label: Label = null
var _team_badge: ColorRect = null
var _team_badge_label: Label = null
var _acted_overlay: ColorRect = null
# 通用 status effect (P+):紫色蒙版 + glyphs(☠⚡◌❄🔇)行,显示在单位顶部
# unit_data.status_effects 是 list[dict],每个 dict 含 type / remaining_turns / glyph
var _status_overlay: ColorRect = null
var _status_label: Label = null

# status effect type → 显示 glyph(对齐后端 app/status/effects.py EFFECT_DEFS)。
# 后端没暴露 glyph 时本地兜底,避免空字符串渲染。
const _STATUS_GLYPH := {
	"poison":   "☠",
	"paralyze": "⚡",
	"blind":    "◌",
	"slow":     "❄",
	"silence":  "🔇",
}


func setup(data: Dictionary, color: Color, team_id: Variant = null) -> void:
	unit_data = data
	_team_id = team_id
	_clear_children()
	_build_pieces(color)
	_refresh()

var _team_id: Variant = null


func _clear_children() -> void:
	for child in get_children():
		remove_child(child)
		child.queue_free()


# static — PNG 在 godot-client/assets/classic/ 下,没经过 .import 系统
# (项目从未在 Editor 里打开过),所以走 TextureLoader 的两段式兜底:
# 1. ResourceLoader.load() 拿到已注册的 Texture2D(优先)
# 2. fallback: Image.load_from_file() 直接读 raw 字节
# 然后统一通过 TextureLoader.fit_image_to_square 缩到目标尺寸,这样
# TextureRect 不需要 stretch_mode,就能在 1 tile(48px)里清晰显示。
# (07-21 M7) — 把"运行时 I/O"路径收口到 TextureLoader 单一审计点。
static func _load_png(res_path: String, target_size: int = 40) -> Texture2D:
	return TextureLoader.load_resized(res_path, target_size)


static func _fit_image_to_square(img: Image, target_size: int) -> Texture2D:
	if img.get_format() != Image.FORMAT_RGBA8:
		img.convert(Image.FORMAT_RGBA8)
	var crop_rect: Rect2i = _alpha_crop_rect(img)
	if crop_rect.size.x > 0 and crop_rect.size.y > 0:
		var cropped: Image = Image.create(crop_rect.size.x, crop_rect.size.y, false, Image.FORMAT_RGBA8)
		cropped.fill(Color(0, 0, 0, 0))
		cropped.blit_rect(img, crop_rect, Vector2i.ZERO)
		img = cropped
	var scale: float = min(float(target_size) / float(max(1, img.get_width())), float(target_size) / float(max(1, img.get_height())))
	var out_w: int = max(1, int(round(float(img.get_width()) * scale)))
	var out_h: int = max(1, int(round(float(img.get_height()) * scale)))
	img.resize(out_w, out_h, Image.INTERPOLATE_LANCZOS)
	var canvas: Image = Image.create(target_size, target_size, false, Image.FORMAT_RGBA8)
	canvas.fill(Color(0, 0, 0, 0))
	canvas.blit_rect(img, Rect2i(0, 0, out_w, out_h), Vector2i((target_size - out_w) / 2, (target_size - out_h) / 2))
	return ImageTexture.create_from_image(canvas)


static func _alpha_crop_rect(img: Image) -> Rect2i:
	var min_x := img.get_width()
	var min_y := img.get_height()
	var max_x := -1
	var max_y := -1
	for y in range(img.get_height()):
		for x in range(img.get_width()):
			if img.get_pixel(x, y).a <= 0.05:
				continue
			min_x = min(min_x, x)
			min_y = min(min_y, y)
			max_x = max(max_x, x)
			max_y = max(max_y, y)
	if max_x < min_x or max_y < min_y:
		return Rect2i(0, 0, img.get_width(), img.get_height())
	return Rect2i(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)


func _unit_type() -> String:
	# UnitOut schema 用 `unit_type`,旧版本地 snapshot 也兼容 `type`
	var t: String = String(unit_data.get("unit_type", unit_data.get("type", "")))
	return t.to_lower().strip_edges()


func _build_pieces(team_color: Color) -> void:
	# ---- 中心 marker(底色块 — 半透,叠在 sprite 下) ----
	_marker = ColorRect.new()
	_marker.size = Vector2(40, 40)
	_marker.position = -_marker.size * 0.5
	_marker.color = Color(team_color.r, team_color.g, team_color.b, 0.28)
	_marker.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_marker)

	# ---- sprite 优先 — TextureRect 中心 48x48(满 1 tile)
	# (texture 在 _load_png 里 resize 到 48×48 直接)
	var ut := _unit_type()
	# M4.16+:英雄单位(hero_id 已绑定)用 hero 立绘(anna/yun)替代 base class sprite。
	# 不再画 hero badge — 视觉上靠"完整立绘"+"阵营色 team badge"区分。
	var hero_sprite_path := _hero_sprite_path(unit_data.get("hero_id", null))
	if hero_sprite_path != "":
		var hero_tex: Texture2D = _load_png(hero_sprite_path, 48)
		if hero_tex != null:
			_sprite = TextureRect.new()
			_sprite.texture = hero_tex
			_sprite.size = Vector2(48, 48)
			_sprite.position = -_sprite.size * 0.5
			_sprite.mouse_filter = Control.MOUSE_FILTER_IGNORE
			add_child(_sprite)
	elif ut != "" and _KNOWN_TYPES.has(ut):
		var sprite_path := _SPRITE_DIR + ut + ".png"
		var tex: Texture2D = _load_png(sprite_path, 48)
		if tex != null:
			_sprite = TextureRect.new()
			_sprite.texture = tex
			_sprite.size = Vector2(48, 48)
			_sprite.position = -_sprite.size * 0.5
			_sprite.mouse_filter = Control.MOUSE_FILTER_IGNORE
			add_child(_sprite)
	# fallback 单字母标签(sprite 缺失时显示,sprite 在时隐藏)
	_marker.visible = (_sprite == null)
	_type_label = Label.new()
	_type_label.text = String(_FALLBACK_GLYPH.get(ut, "?")) if ut != "" else "?"
	_type_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_type_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_type_label.size = Vector2(40, 40)
	_type_label.position = -_type_label.size * 0.5
	_type_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_type_label.add_theme_color_override("font_color", Color(1, 1, 1))
	_type_label.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.85))
	_type_label.add_theme_constant_override("shadow_offset_x", 1)
	_type_label.add_theme_constant_override("shadow_offset_y", 1)
	_type_label.add_theme_font_size_override("font_size", 22)
	_type_label.visible = (_sprite == null)
	add_child(_type_label)

	# ---- HP bar(底部,42 × 5) ----
	var bar_w := 42
	_hp_bar_bg = ColorRect.new()
	_hp_bar_bg.size = Vector2(bar_w, 5)
	_hp_bar_bg.position = Vector2(-bar_w * 0.5, 24)
	_hp_bar_bg.color = _COL_BG_BAR
	_hp_bar_bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_hp_bar_bg)
	_hp_bar = ColorRect.new()
	_hp_bar.size = Vector2(bar_w - 2, 3)
	_hp_bar.position = Vector2(-bar_w * 0.5 + 1, 25)
	_hp_bar.color = _COL_HP_GREEN
	_hp_bar.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_hp_bar)

	# ---- MP badge(右下角小圆点,非 0 才显示) ----
	_mp_badge = ColorRect.new()
	_mp_badge.size = Vector2(12, 12)
	_mp_badge.position = Vector2(14, -22)
	_mp_badge.color = _COL_MP_BLUE
	_mp_badge.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_mp_badge.visible = false
	add_child(_mp_badge)
	_mp_badge_label = Label.new()
	_mp_badge_label.size = Vector2(20, 12)
	_mp_badge_label.position = Vector2(8, -24)
	_mp_badge_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_mp_badge_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_mp_badge_label.add_theme_font_size_override("font_size", 9)
	_mp_badge_label.add_theme_color_override("font_color", Color(0.05, 0.05, 0.05))
	_mp_badge_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_mp_badge_label)

	# ---- Team badge(右上角阵营色 + team 字母)取代原 hero badge ----
	# M4.16+ 重构:每个单位右上角显示所属玩家阵营色块(red/blue/green/yellow)
	# + team 字母(A/B/C/D)。1V1 free-for-all(team=None)→ 只显示色块,不显示字母。
	# 英雄单位靠"完整 hero 立绘(anna/yun)"区分,不再用 H 角标。
	_team_badge = ColorRect.new()
	_team_badge.size = Vector2(14, 14)
	_team_badge.position = Vector2(10, -24)
	_team_badge.color = team_color  # 调用方传入的阵营色(red/blue/...)
	_team_badge.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_team_badge.visible = true
	add_child(_team_badge)
	_team_badge_label = Label.new()
	_team_badge_label.size = Vector2(18, 14)
	_team_badge_label.position = Vector2(8, -25)
	_team_badge_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_team_badge_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_team_badge_label.add_theme_font_size_override("font_size", 10)
	_team_badge_label.add_theme_color_override("font_color", Color(1, 1, 1))
	_team_badge_label.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.85))
	_team_badge_label.add_theme_constant_override("shadow_offset_x", 1)
	_team_badge_label.add_theme_constant_override("shadow_offset_y", 1)
	# team_id 是 Variant:None(1V1)/ "team_a"~"team_d"。
	var team_str: String = ""
	if _team_id != null:
		team_str = String(_team_id)
	_team_badge_label.text = String(_TEAM_GLYPH.get(team_str, ""))
	_team_badge_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_team_badge_label)

	# ---- 士气星(左上,小角) ----
	_star_label = Label.new()
	_star_label.size = Vector2(20, 16)
	_star_label.position = Vector2(-26, -22)
	_star_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
	_star_label.add_theme_font_size_override("font_size", 12)
	_star_label.add_theme_color_override("font_color", _COL_STAR)
	_star_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_star_label)

	# ---- 已行动 overlay(灰色蒙版) ----
	_acted_overlay = ColorRect.new()
	_acted_overlay.size = Vector2(40, 40)
	_acted_overlay.position = -_acted_overlay.size * 0.5
	_acted_overlay.color = Color(0, 0, 0, 0.55)
	_acted_overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_acted_overlay.visible = false
	add_child(_acted_overlay)

	# ---- status effect overlay(紫色蒙版 + glyph 行)----
	# 通用 status_effects 列表里有任意 effect 时显示;过去单一 silence 现在
	# 跟 poison / paralyze / blind / slow 共享同一渲染路径。
	_status_overlay = ColorRect.new()
	_status_overlay.size = Vector2(40, 40)
	_status_overlay.position = -_status_overlay.size * 0.5
	_status_overlay.color = Color(0.55, 0.30, 0.85, 0.55)
	_status_overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_status_overlay.visible = false
	add_child(_status_overlay)
	_status_label = Label.new()
	_status_label.text = ""
	_status_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_status_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	var sl_sz := Vector2(40, 16)
	_status_label.size = sl_sz
	_status_label.position = Vector2(-sl_sz.x * 0.5, -28)  # 顶部居中
	_status_label.add_theme_font_size_override("font_size", 13)
	_status_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_status_label.visible = false
	add_child(_status_label)


func _refresh() -> void:
	if unit_data.is_empty():
		return
	# HP bar
	var hp: int = int(unit_data.get("hp", 0))
	var raw_max_hp: int = int(unit_data.get("max_hp", 1))
	var hp_known := hp >= 0 and raw_max_hp > 0
	if not hp_known:
		_hp_bar.visible = false
		_hp_bar_bg.visible = false
	else:
		_hp_bar.visible = true
		var max_hp: int = max(1, raw_max_hp)
		var pct: float = clamp(float(hp) / float(max_hp), 0.0, 1.0)
		var bar_w: float = 42.0 - 2.0
		_hp_bar.size.x = bar_w * pct
		if pct > 0.5:
			_hp_bar.color = _COL_HP_GREEN
		elif pct > 0.25:
			_hp_bar.color = _COL_HP_YELLOW
		else:
			_hp_bar.color = _COL_HP_RED
		_hp_bar_bg.visible = hp < max_hp
	# MP badge(mage/healer/skill 单位有,显示百分比)
	var mp: int = int(unit_data.get("mp", 0))
	var max_mp: int = int(unit_data.get("max_mp", 0))
	if max_mp > 0:
		_mp_badge.visible = true
		_mp_badge_label.visible = true
		var mp_pct: int = int(round(float(mp) / float(max_mp) * 100.0))
		_mp_badge_label.text = "%d" % mp_pct if mp_pct < 100 else "★"
	else:
		_mp_badge.visible = false
		_mp_badge_label.visible = false
	# 士气:0 空 / 1-5 显示 ⭐
	var morale: int = int(unit_data.get("morale", 0))
	if morale > 0:
		_star_label.text = "⭐".repeat(clamp(morale, 1, 5))
	else:
		_star_label.text = ""
	# 已行动
	var has_acted: bool = bool(unit_data.get("has_acted", false))
	_acted_overlay.visible = has_acted
	# 通用 status effect (P+):unit_data.status_effects 是 list[dict],
# 每个 dict 含 type / remaining_turns / glyph。任一 effect 非空时显示。
	var status_effects: Array = unit_data.get("status_effects", [])
	if not (status_effects is Array):
		status_effects = []
	# 同时读旧 silence_until_turn(过渡期 fallback),有值也算被沉默
	var legacy_silence: int = int(unit_data.get("silence_until_turn", 0))
	var has_status: bool = status_effects.size() > 0 or legacy_silence > 0
	_status_overlay.visible = has_status
	if has_status:
		var glyphs: Array = []
		for eff in status_effects:
			if not (eff is Dictionary):
				continue
			var t: String = String(eff.get("type", ""))
			if t == "":
				continue
			var g: String = String(_STATUS_GLYPH.get(t, "?"))
			glyphs.append(g)
		# 过渡期:旧字段非空但新字段空 → 显示 🔇
		if glyphs.is_empty() and legacy_silence > 0:
			glyphs.append("🔇")
		_status_label.text = "".join(glyphs)
		_status_label.visible = true
	else:
		_status_label.text = ""
		_status_label.visible = false


func has_hero_badge() -> bool:
	# M4.16+:保持向后兼容 — 现在"hero badge"等同于"用了 hero 立绘"。
	# 调用方原本判断"该单位是 hero",改用 _hero_sprite_path 是否非空。
	var sprite := _hero_sprite_path(unit_data.get("hero_id", null))
	return sprite != ""


# M4.16+:hero_id → anna.png / yun.png 路径。没在 _HERO_SPRITES 注册返回 ""。
static func _hero_sprite_path(hero_id_v: Variant) -> String:
	if hero_id_v == null:
		return ""
	var hid := String(hero_id_v)
	if hid == "":
		return ""
	var fn: String = String(_HERO_SPRITES.get(hid, ""))
	if fn == "":
		return ""
	return _HERO_SPRITE_DIR + fn
