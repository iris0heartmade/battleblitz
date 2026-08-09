from __future__ import annotations

from app.classes.heroes import get as get_hero
from app.classes.units import get as get_unit_class
from app.hero_domain.promotion import is_promoted_class
from app.hero_domain.state import HeroCampaignState
from app.hero_domain.templates import HeroCharacterTemplate, HeroClassTemplate

_HERO_PROMOTION_ROUTES: dict[str, list[str]] = {
    "yun": ["sage"],
    "anna": ["saint"],
}

_HERO_CLASS_SPECS: dict[str, dict] = {
    "swordsman": {
        "tier": 1,
        "promotion_options": ["blade_master"],
        "promotion_bonuses": {},
        "caps": {"hp": 72, "atk": 36, "def": 24, "matk": 12, "mdef": 18, "mov": 7, "mp": 12},
    },
    "archer": {
        "tier": 1,
        "promotion_options": ["sniper"],
        "promotion_bonuses": {},
        "caps": {"hp": 64, "atk": 38, "def": 20, "matk": 12, "mdef": 16, "mov": 7, "mp": 12},
    },
    "knight": {
        "tier": 1,
        "promotion_options": ["paladin"],
        "promotion_bonuses": {},
        "caps": {"hp": 78, "atk": 40, "def": 22, "matk": 12, "mdef": 16, "mov": 8, "mp": 14},
    },
    "warlock": {
        "tier": 1,
        "promotion_options": ["sage"],
        "promotion_bonuses": {},
        "caps": {"hp": 66, "atk": 22, "def": 22, "matk": 42, "mdef": 28, "mov": 7, "mp": 16},
    },
    "healer": {
        "tier": 1,
        "promotion_options": ["saint"],
        "promotion_bonuses": {},
        "caps": {"hp": 60, "atk": 18, "def": 22, "matk": 28, "mdef": 30, "mov": 7, "mp": 14},
    },
    "blade_master": {
        "tier": 2,
        "promotion_options": [],
        # 2026-08-10 平衡: 删 mov +1,mp +1 — 不能再涨 mov(6 已封顶)
        "promotion_bonuses": {"hp": 9, "atk": 7, "def": 3},
        "caps": {"hp": 78, "atk": 40, "def": 28, "matk": 16, "mdef": 22, "mov": 8, "mp": 14},
    },
    "sniper": {
        "tier": 2,
        "promotion_options": [],
        # 2026-08-10 平衡: 删 mov +1,mp +1
        "promotion_bonuses": {"hp": 9, "atk": 6, "def": 4},
        "caps": {"hp": 70, "atk": 42, "def": 24, "matk": 16, "mdef": 20, "mov": 8, "mp": 14},
    },
    "paladin": {
        "tier": 2,
        "promotion_options": [],
        # 2026-08-10 平衡: 删 mov +1,mp +1
        "promotion_bonuses": {"hp": 9, "atk": 6, "def": 4},
        "caps": {"hp": 84, "atk": 44, "def": 26, "matk": 16, "mdef": 20, "mov": 9, "mp": 15},
    },
    "sage": {
        "tier": 2,
        "promotion_options": [],
        # 2026-08-10 平衡: 删 mov +1,mp +2 — 转职不能再涨 mov/移动池
        # (mov 6 已封顶,移动池 == mov 已在 §9 合并)
        "promotion_bonuses": {"hp": 4, "atk": 3, "def": 2, "matk": 4, "mdef": 4},
        "caps": {"hp": 70, "atk": 24, "def": 24, "matk": 48, "mdef": 34, "mov": 8, "mp": 18},
    },
    "saint": {
        "tier": 2,
        "promotion_options": [],
        # 2026-08-10 平衡: 删 mov +1,mp +2(同 sage)
        "promotion_bonuses": {"hp": 2, "atk": 2, "def": 3, "matk": 4, "mdef": 4},
        "caps": {"hp": 64, "atk": 20, "def": 24, "matk": 34, "mdef": 34, "mov": 8, "mp": 16},
    },
}


def build_hero_character_template(hero_id: str) -> HeroCharacterTemplate:
    hero = get_hero(hero_id)
    unit_class = get_unit_class(hero.base_class_id)
    # See module-level NOTE on the "mp" key — `base_stats["mp"]` here
    # is the hero's long-term campaign MP resource (independent of
    # the per-turn movement budget).  `mp_pool_override` is gone per
    # spec §9; we fall through to `unit_class.base_mov` as a sane
    # default for hero's starting MP pool (same value the
    # runtime-side unit uses for its movement budget).
    effective_stats = {
        "hp": hero.hp_override if hero.hp_override is not None else unit_class.base_hp,
        "atk": hero.atk_override if hero.atk_override is not None else unit_class.base_atk,
        "def": hero.def_override if hero.def_override is not None else unit_class.base_def,
        "matk": hero.matk_override if hero.matk_override is not None else unit_class.base_matk,
        "mdef": hero.mdef_override if hero.mdef_override is not None else unit_class.base_mdef,
        "mov": hero.mov_override if hero.mov_override is not None else unit_class.base_mov,
        "mp": (hero.mov_override if hero.mov_override is not None else unit_class.base_mov),
    }
    return HeroCharacterTemplate(
        hero_id=hero.hero_id,
        default_class_id=hero.base_class_id,
        base_stats=effective_stats,
        growth_rates={},
        promotion_routes=list(_HERO_PROMOTION_ROUTES.get(hero.hero_id, [])),
    )


def build_hero_class_template(class_id: str) -> HeroClassTemplate:
    # NOTE on "mp" field below:
    #   The Unit-class / runtime-side `mp` was merged with `mov` per
    #   spec §9 (MOV/MP merge).  This module's `caps["mp"]` and the
    #   `_HERO_CLASS_SPECS[*]["promotion_bonuses"]["mp"]` entries
    #   below still surface an `mp` key, but they are the HERO
    #   CAMPAIGN resource cap (a long-term pool stored on
    #   HeroCampaignState.base_stats["mp"] and read by
    #   `app.hero_domain.promote_hero`), NOT the per-turn movement
    #   budget.  See `app.hero_domain.promotion` and the
    #   HeroCampaignState dataclass for the campaign-side definition.
    #   Out of scope for the MOV/MP merge commit; left as-is.
    spec = _HERO_CLASS_SPECS.get(class_id)
    if spec is None:
        unit_class = get_unit_class(class_id)
        spec = {
            "tier": 2 if class_id.startswith(("blade_", "paladin", "sage", "saint", "sniper")) else 1,
            "promotion_options": [],
            "promotion_bonuses": {},
            "caps": {
                "hp": unit_class.base_hp + 20,
                "atk": unit_class.base_atk + 15,
                "def": unit_class.base_def + 15,
                "matk": unit_class.base_matk + 15,
                "mdef": unit_class.base_mdef + 15,
                "mov": unit_class.base_mov + 3,
            },
        }
    return HeroClassTemplate(
        class_id=class_id,
        tier=int(spec["tier"]),
        base_modifiers={},
        caps=dict(spec["caps"]),
        promotion_options=list(spec.get("promotion_options", [])),
        promotion_bonuses=dict(spec.get("promotion_bonuses", {})),
    )


def build_initial_campaign_state(hero_id: str) -> HeroCampaignState:
    """Bridge the legacy hero registry into the new persistent Hero model."""

    hero = get_hero(hero_id)
    unit_class = get_unit_class(hero.base_class_id)
    character = build_hero_character_template(hero_id)
    hero_class = build_hero_class_template(hero.base_class_id)
    state = HeroCampaignState.from_templates(character, hero_class)
    state.learned_skills = list(dict.fromkeys([
        *unit_class.default_skills,
        *hero.active_skills,
        *hero.passive_skills,
    ]))
    from app.hero_domain.equipment import default_equipment_for_class
    state.equipment = default_equipment_for_class(state.class_id)
    state.equipment_initialized = True
    return state


def hero_campaign_state_to_dict(state: HeroCampaignState) -> dict:
    return {
        "hero_id": state.hero_id,
        "class_id": state.class_id,
        "level": state.level,
        "exp": state.exp,
        "base_stats": dict(state.base_stats),
        "weapon_ranks": dict(state.weapon_ranks),
        "learned_skills": list(state.learned_skills),
        "promoted": state.promoted,
        "equipment": dict(state.equipment),
        "equipment_initialized": state.equipment_initialized,
    }


def hero_campaign_state_from_dict(payload: dict) -> HeroCampaignState:
    return HeroCampaignState(
        hero_id=payload["hero_id"],
        class_id=payload["class_id"],
        level=int(payload.get("level", 1)),
        exp=int(payload.get("exp", 0)),
        base_stats=dict(payload.get("base_stats", {})),
        weapon_ranks=dict(payload.get("weapon_ranks", {})),
        learned_skills=list(payload.get("learned_skills", [])),
        promoted=bool(payload.get("promoted", False))
        or is_promoted_class(
            payload["class_id"],
            build_hero_class_template,
        ),
        equipment=dict(payload.get("equipment", {})),
        equipment_initialized=bool(payload.get("equipment_initialized", False)),
    )
