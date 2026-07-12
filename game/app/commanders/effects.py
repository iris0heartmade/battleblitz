"""Apply persistent commander passives and temporary CO Power effects."""

from app.commanders.registry import get_commander_passive, get_commander_power


def _value(effect, name, default=0):
    return getattr(effect, name, default)


def _unit_attack_range(unit):
    if hasattr(unit, "attack_range"):
        return unit.attack_range
    from app.classes.units import get

    return get(unit.unit_type).attack_range


def bake_passive_into_units(player):
    passive = get_commander_passive(getattr(player, "commander_id", None))
    if passive is None:
        return

    co = dict(getattr(player, "co_state", None) or {})
    persisted = dict(co.get("_passive_units", {}))

    for unit in player.units:
        unit_key = str(getattr(unit, "id", f"@{id(unit)}"))
        saved = persisted.get(unit_key)
        if saved is not None:
            if saved.get("attack_range") is not None:
                unit._base_attack_range = saved["attack_range"]
            unit._commander_passive = passive
            continue
        if hasattr(unit, "_commander_passive"):
            continue
        hp_pct = _value(passive, "hp_pct")
        if hp_pct:
            unit.max_hp = round(unit.max_hp * (1 + hp_pct))
            unit.hp = unit.max_hp
        for stat in ("atk", "def_", "matk", "mdef"):
            pct = _value(passive, f"{stat.rstrip('_')}_pct")
            if pct:
                setattr(unit, stat, round(getattr(unit, stat) * (1 + pct)))
        mov_delta = _value(passive, "mov_delta")
        if mov_delta:
            unit.mov = max(1, unit.mov + mov_delta)
        range_delta = _value(passive, "range_delta")
        if range_delta:
            unit._base_attack_range = _unit_attack_range(unit) + range_delta
        unit._commander_passive = passive
        persisted[unit_key] = {
            "attack_range": getattr(unit, "_base_attack_range", None),
        }
    if hasattr(player, "co_state"):
        co["_passive_units"] = persisted
        player.co_state = co


def can_fire_co_power(player) -> bool:
    commander_id = getattr(player, "commander_id", None)
    if commander_id is None:
        return False
    co = player.co_state or {}
    return (
        not co.get("is_power_active", False)
        and co.get("meter", 0) >= co.get("threshold", 20)
        and get_commander_power(commander_id) is not None
    )


def fire_co_power(player):
    if not can_fire_co_power(player):
        if getattr(player, "commander_id", None) is None:
            raise ValueError("no commander selected")
        co = player.co_state or {}
        if co.get("is_power_active"):
            raise ValueError("power already active")
        if co.get("meter", 0) < co.get("threshold", 20):
            raise ValueError("meter not full")
        raise ValueError("commander has no power")

    power = get_commander_power(player.commander_id)
    baselines = {}
    for index, unit in enumerate(player.units):
        baseline = {}
        for stat in ("atk", "def_", "matk", "mdef"):
            pct = _value(power, f"{stat.rstrip('_')}_pct")
            if pct:
                baseline[stat] = getattr(unit, stat)
                setattr(unit, stat, round(getattr(unit, stat) * (1 + pct)))
        range_delta = _value(power, "range_delta")
        if range_delta:
            baseline["_base_attack_range"] = getattr(unit, "_base_attack_range", None)
            base_range = getattr(unit, "_base_attack_range", _unit_attack_range(unit))
            unit._base_attack_range = base_range + range_delta
        unit._commander_power_baseline = baseline
        unit._commander_power = power
        unit_key = str(getattr(unit, "id", f"@{index}"))
        baselines[unit_key] = baseline

        heal_pct = _value(power, "heal_pct")
        if heal_pct:
            unit.hp = min(unit.max_hp, unit.hp + round(unit.max_hp * heal_pct))
        extra_mov = _value(power, "extra_mov")
        if extra_mov:
            unit.mp = min(unit.mov, unit.mp + extra_mov)

    co = dict(player.co_state or {})
    co["is_power_active"] = True
    co["meter"] = 0
    co["_power_baselines"] = baselines
    player.co_state = co


def expire_power(player):
    co = dict(player.co_state or {})
    persisted = co.get("_power_baselines", {})
    for index, unit in enumerate(player.units):
        unit_key = str(getattr(unit, "id", f"@{index}"))
        baseline = persisted.get(
            unit_key, getattr(unit, "_commander_power_baseline", {}),
        )
        for stat, value in baseline.items():
            if stat == "_base_attack_range" and value is None:
                if hasattr(unit, stat):
                    delattr(unit, stat)
            else:
                setattr(unit, stat, value)
        if hasattr(unit, "_commander_power"):
            del unit._commander_power
        if hasattr(unit, "_commander_power_baseline"):
            del unit._commander_power_baseline
    co["is_power_active"] = False
    co.pop("_power_baselines", None)
    player.co_state = co


def on_player_turn_start(player, game_turn_number: int):
    co = dict(player.co_state or {})
    last = co.get("last_start_turn", -1)
    if last != -1 and game_turn_number > last:
        if co.get("is_power_active"):
            expire_power(player)
            co = dict(player.co_state or {})
        co["meter"] = 0
    co["last_start_turn"] = game_turn_number
    player.co_state = co
