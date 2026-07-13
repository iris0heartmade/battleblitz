from __future__ import annotations

from app.hero_domain.free_mode import build_standardized_hero_state
from app.hero_domain.materialize import build_hero_battle_state
from app.hero_domain.state import HeroCampaignState
from app.hero_domain.templates import HeroCharacterTemplate, HeroClassTemplate


def test_hero_campaign_state_can_be_built_from_templates():
    char = HeroCharacterTemplate(
        hero_id="yun",
        default_class_id="warlock",
        base_stats={"hp": 45, "atk": 8, "def": 10, "matk": 22, "mdef": 12, "mp": 8},
        growth_rates={"hp": 70, "atk": 35, "def": 25, "matk": 55, "mdef": 30},
        base_weapon_ranks={"anima": 1},
    )
    cls = HeroClassTemplate(
        class_id="warlock",
        tier=1,
        base_modifiers={"hp": 0, "atk": 0, "def": 0, "matk": 0, "mdef": 0, "mp": 0},
        caps={"hp": 60, "atk": 30, "def": 24, "matk": 34, "mdef": 28},
        promotion_options=["sage"],
        promotion_bonuses={"hp": 3, "matk": 2},
    )
    state = HeroCampaignState.from_templates(char, cls)
    assert state.hero_id == "yun"
    assert state.class_id == "warlock"
    assert state.level == 1
    assert state.exp == 0
    assert state.base_stats["matk"] == 22


def test_build_hero_battle_state_resets_temporary_resources():
    state = HeroCampaignState(
        hero_id="yun",
        class_id="warlock",
        level=7,
        exp=40,
        base_stats={"hp": 52, "atk": 18, "def": 11, "matk": 28, "mdef": 13, "mov": 4, "mp": 8},
        weapon_ranks={"anima": 2},
    )
    battle = build_hero_battle_state(state, x=3, y=4, player_id=1)
    assert battle.current_hp == 52
    assert battle.current_mp == 8
    assert battle.x == 3
    assert battle.y == 4


def test_standardized_free_mode_hero_does_not_depend_on_campaign_growth():
    state = build_standardized_hero_state(
        hero_id="yun",
        class_id="warlock",
        preset_level=5,
    )
    assert state.level == 5
    assert state.exp == 0
