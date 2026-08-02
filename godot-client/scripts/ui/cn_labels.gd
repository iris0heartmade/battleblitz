extends RefCounted
## cn_labels.gd — 中文标签词典层(P2 从 main.gd 抽离)。
##
## 纯查表函数,无节点访问、无成员状态,全部 static。
## 原先散落在 main.gd 四处(单位/技能/地形/指挥官/颜色/队伍/席位),
## 抽出后 main.gd 与 lobby_controller.gd 都能直接取用,不必再走 _main 绕一圈。
##
## 用法:调用方 `const CnLabels = preload("res://scripts/ui/cn_labels.gd")`。
## 注意:这里刻意不写 `class_name` —— 本项目 headless 跑测试时全局类缓存
## 未建立,跨文件 class_name 引用会撞 Parse Error。统一用 preload 常量。
##
## 调用方为兼容既有 `Callable(self, "_xxx_cn")` 接线,各自保留同名薄壳转发。

const MenuTheme = preload("res://scripts/ui/menu_theme.gd")


# ============================================================
# 单位 / 技能
# ============================================================

static func unit_type_cn(unit_type: String) -> String:
	match unit_type:
		"swordsman":
			return "剑士"
		"archer":
			return "弓箭手"
		"knight":
			return "骑士"
		"warlock":
			return "术士"
		"healer":
			return "治疗师"
		"bard":
			return "吟游诗人"
		"lancer":
			return "枪骑兵"
		"warrior":
			return "战士"
		"berserker":
			return "狂战士"
		"dragon_rider":
			return "龙骑士"
		"falcon_knight":
			return "隼骑士"
		"blade_master":
			return "剑圣"
		"paladin":
			return "圣骑士"
		"sniper":
			return "狙击手"
		"sage":
			return "贤者"
		"saint":
			return "圣者"
		"yuanying":
			return "鸢影"
		_:
			return unit_type


static func skill_cn(skill_id: String) -> String:
	match skill_id:
		"heal":
			return "治疗"
		"snipe":
			return "狙击"
		"double_strike":
			return "连击"
		"arcane_strike":
			return "奥术冲击"
		"sing":
			return "吟诗"
		"poison_burst":
			return "剧毒迸发"
		_:
			return skill_id


## 单位显示名:优先查 unit_type 词典,查不到再退 display_cn / name_cn / fallback。
static func unit_cn_name(unit: Dictionary, fallback: String = "单位") -> String:
	var unit_type := str(unit.get("unit_type", unit.get("type", "")))
	var mapped := unit_type_cn(unit_type)
	if mapped != unit_type:
		return mapped
	if unit.has("display_cn"):
		return str(unit.get("display_cn"))
	if unit.has("name_cn"):
		return str(unit.get("name_cn"))
	return fallback


# ============================================================
# 地形 / 指挥官
# ============================================================

## P2.6+: 地形名中文化(用于 InfoPanel 加成区段)
static func terrain_cn(terrain_name: String, subtype: String = "") -> String:
	# subtype 优先 — castle_floor / castle_wall / etc.
	if subtype != "":
		match subtype:
			"castle_floor": return "城堡内部"
			"castle_wall": return "城墙"
			"castle_door": return "城门"
			"castle_throne": return "王座厅"
			"castle_stairs": return "城梯"
			"castle_vault": return "金库"
	match terrain_name:
		"plain": return "平原"
		"forest": return "森林"
		"mountain": return "山地"
		"snow_peak": return "雪峰"
		"river": return "河流"
		"road": return "道路"
		"bridge": return "桥梁"
		"castle": return "城堡"
		"village": return "村庄"
		"barracks": return "兵营"
		"gate": return "城门"
		_:
			return terrain_name


## P2.6+: 指挥官名中文化(用于 InfoPanel 战斗加成区段)
static func commander_cn(co_id: String) -> String:
	match co_id:
		"anna": return "安娜"
		"yun": return "云"
		"yuanying": return "鸢影"
		"boss": return "Boss"
		_:
			return co_id


## 大厅下拉框用的指挥官显示名(与 commander_cn 词条不同,不合并)
static func commander_label(commander_id: String) -> String:
	match commander_id:
		"yun":
			return "云"
		"anna":
			return "安娜"
		"yuanying":
			return "鸢影"
		_:
			return commander_id


# ============================================================
# 颜色 / 队伍 / 席位
# ============================================================

static func color_name_to_godot(c: String) -> String:
	match c:
		"red": return "#e85a6a"
		"blue": return "#5fa8e8"
		"green": return "#7ec97e"
		"yellow": return "#f0c75e"
		_: return "#cccccc"


static func color_emoji(c: String) -> String:
	match c:
		"red": return "🔴"
		"blue": return "🔵"
		"green": return "🟢"
		"yellow": return "🟡"
		_: return "⚪"


static func color_name_cn(color_name: String) -> String:
	match color_name:
		"red":
			return "红色"
		"blue":
			return "蓝色"
		"green":
			return "绿色"
		"yellow":
			return "黄色"
		_:
			return color_name


static func team_cn(team: String) -> String:
	match team:
		"red":
			return "红队"
		"blue":
			return "蓝队"
		"green":
			return "绿队"
		"yellow":
			return "黄队"
		_:
			return team


static func seat_color_label(color_id: String) -> String:
	match color_id:
		"red": return "红方"
		"blue": return "蓝方"
		"green": return "绿方"
		"yellow": return "黄方"
		_: return color_id


static func seat_display_color(color_id: String) -> Color:
	match color_id:
		"red": return Color(0.95, 0.32, 0.24)
		"blue": return Color(0.36, 0.56, 1.0)
		"green": return Color(0.3, 0.8, 0.38)
		"yellow": return Color(0.95, 0.78, 0.25)
		_: return MenuTheme.C_TEXT_WARM
