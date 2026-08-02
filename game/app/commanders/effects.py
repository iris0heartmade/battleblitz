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
    # 新机制:stars_earned_total 累计达到 power_cost 即可放
    return (
        not co.get("is_power_active", False)
        and co.get("stars_earned_total", 0) >= co.get("power_cost", 6)
        and get_commander_power(commander_id) is not None
    )


def fire_co_power(player, *, center_xy=None, current_turn=0, all_units=None):
    """激活玩家 CO power。

    Args:
        center_xy: 沉默领域等的中心坐标 (x, y)。silence_radius > 0 时必传。
        current_turn: 当前 game.turn_number(silence_until_turn 用)。
        all_units: 全场 unit 列表(silence 区域选取用)。silence_radius > 0 时必传。
    """
    if not can_fire_co_power(player):
        if getattr(player, "commander_id", None) is None:
            raise ValueError("no commander selected")
        co = player.co_state or {}
        if co.get("is_power_active"):
            raise ValueError("power already active")
        if co.get("stars_earned_total", 0) < co.get("power_cost", 6):
            raise ValueError("insufficient stars")
        raise ValueError("commander has no power")

    power = get_commander_power(player.commander_id)
    silence_radius = int(getattr(power, "silence_radius", 0))
    silence_turns = int(getattr(power, "silence_duration_turns", 0))
    if silence_radius > 0:
        if center_xy is None or all_units is None:
            raise ValueError(
                f"silence_radius={silence_radius} requires center_xy and all_units"
            )
        apply_silence_aura(
            all_units,
            center_xy=center_xy,
            radius=silence_radius,
            duration_turns=silence_turns,
            current_turn=current_turn,
            owner_player_id=getattr(player, "id", None),
        )

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
    # 新机制:扣 power_cost 颗星(默认 6),放 power 后剩余继续累计
    from app.commanders.meter import consume_power_stars
    consume_power_stars(player)
    co = dict(player.co_state or {})  # consume 已改 in-place,重读保证最新
    co["is_power_active"] = True
    co["_power_baselines"] = baselines
    player.co_state = co


def apply_silence_aura(
    units,
    *,
    center_xy,
    radius,
    duration_turns,
    current_turn,
    owner_player_id,
) -> list:
    """沉默领域:在 (center_x ± radius, center_y ± radius) 范围内,标记
    非 owner_player_id、且攻击类型为 magic 的单位 silence_until_turn。

    新机制:走通用 status_effects 框架(详见 app/status/engine.py)。
    同时保留旧 silence_until_turn 字段的写入以做向后兼容。

    Args:
        units: 全场 unit 列表(已 dead 的也会被传入,但会被 hp <= 0 过滤)
        center_xy: (x, y) 元组
        radius: 整数半径(2 = 5×5 方形)
        duration_turns: 持续大回合数(1 = 持续到下次自己回合开始)
        current_turn: 当前 game.turn_number
        owner_player_id: 沉默施放者(自己人不沉默)

    Returns:
        被沉默的单位列表(供 _log / 反馈用)
    """
    if radius <= 0 or duration_turns <= 0:
        return []
    from app.status import add_effect
    cx, cy = center_xy
    expire_at = current_turn + duration_turns
    silenced: list = []
    for unit in units:
        if unit.hp <= 0:
            continue
        if unit.player_id == owner_player_id:
            continue
        if unit.x < cx - radius or unit.x > cx + radius:
            continue
        if unit.y < cy - radius or unit.y > cy + radius:
            continue
        # 只沉默魔法单位(attack_kind == "magic")
        # 从 unit class 注册表查;查不到默认 non-magic(避免误沉默物理单位)
        try:
            from app.classes.units import get as get_unit_class
            attack_kind = get_unit_class(unit.unit_type).attack_kind
        except Exception:
            attack_kind = "physical"
        if attack_kind != "magic":
            continue
        # 新机制:写入 status_effects(通用框架);同时保留旧字段做兜底。
        add_effect(
            unit,
            "silence",
            applied_turn=current_turn,
            applied_by=owner_player_id,
            remaining_turns=duration_turns,
        )
        # 旧字段兼容(过渡期)
        if unit.silence_until_turn < expire_at:
            unit.silence_until_turn = expire_at
        silenced.append(unit)
    return silenced


def is_unit_silenced(unit, *, current_turn) -> bool:
    """检查单位当前是否被沉默(全局工具,供 attack / counter 拦截使用)。

    优先查通用 status_effects(新机制),fallback 到 silence_until_turn 旧字段。
    """
    from app.status import is_silenced as _is_silenced_new
    if _is_silenced_new(unit):
        return True
    return int(getattr(unit, "silence_until_turn", 0)) > int(current_turn)


def clear_expired_silences(units, *, current_turn) -> int:
    """清空已过期沉默(silence_until_turn <= current_turn → 0)。

    新机制下,通用 tick_effects_at_turn_start 已经把 status_effects 里
    silence 的 remaining_turns 减到 0 自动过期(详见 app.status.engine)。
    本函数保留旧字段(silence_until_turn)的清空兜底。
    """
    cleared = 0
    for unit in units:
        if int(getattr(unit, "silence_until_turn", 0)) > 0 and unit.silence_until_turn <= current_turn:
            unit.silence_until_turn = 0
            cleared += 1
    return cleared


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


def _refresh_mov_debuff(unit):
    """turn_start 时刷新 unit.mov:slow 临时减半,过期恢复。

    第一次调用时把 unit.mov 当作 _base_mov 存档;之后每次按
    modify_mov(unit, base) 重算。
    """
    from app.status import modify_mov
    base = getattr(unit, "_base_mov", None)
    if base is None:
        unit._base_mov = int(getattr(unit, "mov", 0))
        base = unit._base_mov
    unit.mov = modify_mov(unit, base=base)


def on_player_turn_start(player, game_turn_number: int, all_units=None):
    # 用 _ensure_co_state 把 co_state 字段补齐(含 stars_earned_total 等)
    from app.commanders.meter import _ensure_co_state
    from app.status import should_skip_action, tick_effects_at_turn_start
    co = dict(_ensure_co_state(player))  # 强制新建 dict(避免与旧引用同一对象)
    last = co.get("last_start_turn", -1)
    if last != -1 and game_turn_number > last:
        if co.get("is_power_active"):
            expire_power(player)
            co = dict(_ensure_co_state(player))
        # 新机制:每回合不重置 stars_earned_total(累计型,放 power 才扣)
        # 沉默领域 (鸢影 P+) 持续 N 大回合:game_turn_number 推进到 N 时清空。
        if all_units is not None:
            clear_expired_silences(all_units, current_turn=game_turn_number)
            # status effects (P+):tick 倒计时,poison 扣 HP,paralyze skip,slow 调 mov
            # 玩家的所有 unit(同 team + 自己) 走这条路径:
            owner_units = [u for u in all_units if u.player_id == player.id]
            for u in owner_units:
                if u.hp <= 0:
                    continue
                # paralyze 在 tick 前判断:剩余 0 → tick 后过期清理 → 查不到
                skip, reason = should_skip_action(u)
                if skip:
                    u.has_acted = True  # 本回合无法主动行动(仍可被攻击)
                    u.paralyzed_until_turn = game_turn_number
                # slow 的 mov 调整在 tick 前读(slow effect 还在生效)
                _refresh_mov_debuff(u)
                # 最后 tick:扣 remaining_turns,过期清理
                tick_effects_at_turn_start(u, game_turn_number=game_turn_number)
    co["last_start_turn"] = game_turn_number
    player.co_state = co
