class_name ElevationRules
extends RefCounted
## 只供预览；数值来自服务端快照，正式判定仍由服务端执行。
static var warned_missing_rules := false

static func _has_rules(rules: Dictionary, keys: Array) -> bool:
	for key in keys:
		if not rules.has(key):
			if not warned_missing_rules:
				push_warning("高差预览缺少服务端规则；暂不预览跨高度行动，请刷新对局快照。")
				warned_missing_rules = true
			return false
	return true

static func context(unit: Dictionary, cells: Dictionary, heights: Dictionary, rules: Dictionary) -> Dictionary:
	return {"unit":unit,"cells":cells,"heights":heights,"rules":rules}

static func step(terrain: Dictionary, start: Vector2i, finish: Vector2i, ctx: Dictionary) -> int:
	var unit: Dictionary = ctx.get("unit",{})
	var cells: Dictionary = ctx.get("cells",{})
	var tile: Dictionary = cells.get(finish,{})
	var kind: String = str(tile.get("subtype") if tile.get("subtype")!=null and tile.get("subtype")!="" else terrain[finish])
	var profile: Dictionary = unit.get("terrain_movement",{})
	var rule: Dictionary = profile.get(kind,{})
	var cost: int = int(tile.get("movement_cost_x2",Config.TERRAIN_MOVE_COST.get(kind,9999)))
	if bool(unit.get("flying",false)):
		return 2
	if not bool(rule.get("can_traverse",cost<9999)):
		return -1
	cost = maxi(1,int(rule.get("cost_override_x2",cost))+int(rule.get("cost_delta_x2",0)))
	var heights: Dictionary = ctx.get("heights",{})
	var rules: Dictionary = ctx.get("rules",{})
	var delta: int = int(heights.get(finish,0))-int(heights.get(start,0))
	if not _has_rules(rules, ["max_step", "uphill_cost_x2"]):
		return cost if delta == 0 else -1
	if abs(delta)>int(rules["max_step"]):
		return -1
	var source: Dictionary = cells.get(start,{})
	var stairs: bool = kind=="castle_stairs" or str(source.get("subtype",""))=="castle_stairs"
	return cost + (0 if stairs else maxi(0,delta)*int(rules["uphill_cost_x2"]))

static func can_end(terrain: String, point: Vector2i, ctx: Dictionary) -> bool:
	var unit: Dictionary = ctx.get("unit",{})
	var cells: Dictionary = ctx.get("cells",{})
	var tile: Dictionary = cells.get(point,{})
	var kind: String = str(tile.get("subtype") if tile.get("subtype")!=null and tile.get("subtype")!="" else terrain)
	if bool(unit.get("flying",false)) and kind in ["castle_wall","gate"]:
		return false
	var profile: Dictionary = unit.get("terrain_movement",{})
	var rule: Dictionary = profile.get(kind,{})
	return bool(rule.get("can_end_on",true))

static func can_attack(unit: Dictionary, start: Vector2i, finish: Vector2i, heights: Dictionary, rules: Dictionary) -> bool:
	var d: int = absi(start.x-finish.x)+absi(start.y-finish.y)
	var delta: int = int(heights.get(start,0))-int(heights.get(finish,0))
	var maximum: int = int(unit.get("attack_range",1))
	if not _has_rules(rules, ["melee_step", "ranged_height", "ranged_bonus"]):
		return delta == 0 and d>int(unit.get("min_attack_range",0)) and d<=maximum
	if d==1 and absi(delta)>int(rules["melee_step"]):
		return false
	if str(unit.get("attack_kind","physical"))=="physical" and int(unit.get("base_attack_range",maximum))>=2 and delta>=int(rules["ranged_height"]):
		maximum+=int(rules["ranged_bonus"])
	return d>int(unit.get("min_attack_range",0)) and d<=maximum

