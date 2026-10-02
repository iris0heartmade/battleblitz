from __future__ import annotations

import math

from app.classes.heroes import get as get_hero
from app.classes.units import get as get_class
from app.classes.units import type_advantage
from app.progression.policies import STAT_KEYS, resolve_effective_base


HERO_IDS = ("yun", "yuanying", "anna", "youko")
T1_MERC_CLASSES = (
    "swordsman",
    "archer",
    "knight",
    "lancer",
    "warrior",
    "warlock",
    "healer",
    "bard",
    "dragon_rider",
    "falcon_knight",
)


def _expected_class_stats(type_id: str, level: int = 10) -> dict[str, float]:
    profile = get_class(type_id)
    base = {
        "hp": profile.base_hp,
        "atk": profile.base_atk,
        "def": profile.base_def,
        "matk": profile.base_matk,
        "mdef": profile.base_mdef,
        "mov": profile.base_mov,
    }
    return {
        stat: base[stat] + (level - 1) * profile.class_growth_rates.get(stat, 0) / 100
        for stat in STAT_KEYS
    }


def _expected_hero_stats(hero_id: str, level: int = 10) -> dict[str, float]:
    hero = get_hero(hero_id)
    class_profile = get_class(hero.base_class_id)
    base = resolve_effective_base(class_profile, hero)
    if hero.character_growth_rates:
        rates = {stat: hero.character_growth_rates.get(stat, 0) for stat in STAT_KEYS}
    else:
        rates = {
            stat: max(
                0,
                min(
                    100,
                    class_profile.class_growth_rates.get(stat, 0)
                    + hero.personal_growth_modifier.get(stat, 0),
                ),
            )
            for stat in STAT_KEYS
        }
    return {
        stat: base[stat] + (level - 1) * rates.get(stat, 0) / 100
        for stat in STAT_KEYS
    }


def _unit_type(subject_id: str) -> str:
    if subject_id in HERO_IDS:
        return get_hero(subject_id).base_class_id
    return subject_id


def _stats(subject_id: str) -> dict[str, float]:
    if subject_id in HERO_IDS:
        return _expected_hero_stats(subject_id)
    return _expected_class_stats(subject_id)


def _single_damage(attacker_id: str, defender_id: str) -> int:
    attacker_type = _unit_type(attacker_id)
    defender_type = _unit_type(defender_id)
    attack_kind = get_class(attacker_type).attack_kind
    attacker_stats = _stats(attacker_id)
    defender_stats = _stats(defender_id)
    atk = attacker_stats["matk" if attack_kind == "magic" else "atk"]
    defense = defender_stats["mdef" if attack_kind == "magic" else "def"]
    base = atk * (atk / (atk + max(1, defense)))
    return max(1, round(base * type_advantage(attacker_type, defender_type)))


def _hits_to_kill(attacker_id: str, defender_id: str) -> int:
    return math.ceil(_stats(defender_id)["hp"] / _single_damage(attacker_id, defender_id))


def test_support_mercenaries_can_pressure_heroes_without_becoming_carries() -> None:
    for support_id in ("healer", "bard"):
        kill_counts = [_hits_to_kill(support_id, hero_id) for hero_id in HERO_IDS]
        assert max(kill_counts) <= 8
        assert min(kill_counts) >= 6


def test_t1_mercenaries_are_not_too_fast_against_lv10_heroes() -> None:
    kill_counts = [
        _hits_to_kill(class_id, hero_id)
        for class_id in T1_MERC_CLASSES
        for hero_id in HERO_IDS
    ]
    assert sum(kill_counts) / len(kill_counts) >= 5.3
    assert min(kill_counts) >= 3
