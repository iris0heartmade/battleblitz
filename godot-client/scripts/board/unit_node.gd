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
const _HERO_CREST_DIR := "res://assets/heroes/"
# 镜像 game/app/web/assets/classic/ 7 类 sprite
const _KNOWN_TYPES := [
	"archer", "healer", "heavy_armor", "knight",
	"swordsman", "warlock",
]
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
var _hero_badge: ColorRect = null
var _hero_crest: TextureRect = null
var _hero_badge_label: Label = null
var _acted_overlay: ColorRect = null


func setup(data: Dictionary, color: Color) -> void:
	unit_data = data
	_clear_children()
	_build_pieces(color)
	_refresh()
	position = Vector2.ZERO


func _clear_children() -> void:
	for child in get_children():
		child.queue_free()


# static — PNG 在 godot-client/assets/classic/ 下,没经过 .import 系统
# (项目从未在 Editor 里打开过),所以不能 ResourceLoader.load()。
# 改走 Image.load(path) — Image 支持直接 load res:// 路径(绕过 .import)。
# 同时缩到 marker 大小(40×40)再生成 ImageTexture,这样 TextureRect
# 不需要 stretch_mode,就能在 1 tile(48px)里清晰显示。
static func _load_png(res_path: String, target_size: int = 40) -> Texture2D:
	var img: Image = null
	if ResourceLoader.exists(res_path):
		var res: Resource = load(res_path)
		if res is Texture2D:
			var tex: Texture2D = res
			img = tex.get_image()
	if img == null:
		img = Image.new()
		var err := img.load(res_path)
		if err != OK:
			return null
	return _fit_image_to_square(img, target_size)


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
	if ut != "" and _KNOWN_TYPES.has(ut):
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

	# ---- Hero badge(右上角金色徽记):素材未覆盖的 hero 也能被识别 ----
	var hero_id := str(unit_data.get("hero_id", ""))
	if hero_id != "":
		var crest_path := _HERO_CREST_DIR + "crest_" + hero_id + ".png"
		var crest_tex := _load_png(crest_path, 18)
		if crest_tex != null:
			_hero_crest = TextureRect.new()
			_hero_crest.texture = crest_tex
			_hero_crest.size = Vector2(18, 18)
			_hero_crest.position = Vector2(8, -26)
			_hero_crest.mouse_filter = Control.MOUSE_FILTER_IGNORE
			add_child(_hero_crest)
		else:
			_hero_badge = ColorRect.new()
			_hero_badge.size = Vector2(14, 14)
			_hero_badge.position = Vector2(10, -24)
			_hero_badge.color = Color(0.95, 0.72, 0.24, 0.95)
			_hero_badge.mouse_filter = Control.MOUSE_FILTER_IGNORE
			add_child(_hero_badge)
			_hero_badge_label = Label.new()
			_hero_badge_label.size = Vector2(18, 14)
			_hero_badge_label.position = Vector2(8, -25)
			_hero_badge_label.text = "H"
			_hero_badge_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
			_hero_badge_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
			_hero_badge_label.add_theme_font_size_override("font_size", 9)
			_hero_badge_label.add_theme_color_override("font_color", Color(0.08, 0.05, 0.02))
			_hero_badge_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
			add_child(_hero_badge_label)

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


func _refresh() -> void:
	if unit_data.is_empty():
		return
	# HP bar
	var hp: int = int(unit_data.get("hp", 0))
	var max_hp: int = max(1, int(unit_data.get("max_hp", 1)))
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


func has_hero_badge() -> bool:
	if _hero_crest != null and is_instance_valid(_hero_crest) and _hero_crest.visible:
		return true
	return _hero_badge != null and is_instance_valid(_hero_badge) and _hero_badge.visible
