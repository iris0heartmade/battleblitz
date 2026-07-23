"""Tests for game/app/modes.py (Phase 2 双轨制 spawn helpers).

Covers:
  - GameMode enum membership
  - ModeConfig.mainline() / .free() builders
  - AUTOEVEL_RATES match FE8 Boss pattern
  - spawn_generic_stats L1 == class.base
  - spawn_generic_stats L10 adds Boss-autolevel bonus
  - spawn_generic_stats L=20 caps reasonable
  - spawn_hero_stats deliberately raises NotImplementedError
  - mov / attack_range don't scale with level
"""
from __future__ import annotations

import pytest

from app.classes.units import type_ids
from app.modes import (
    AUTOEVEL_RATES,
    GameMode,
    ModeConfig,
    spawn_generic_stats,
    spawn_hero_stats,
)


# ── GameMode enum ────────────────────────────────────────────────


def test_gamemode_enum_has_three_modes():
    assert {m.value for m in GameMode} == {"mainline", "free", "tutorial"}


# ── ModeConfig builders ────────────────────────────────────────


def test_modeconfig_mainline_defaults_l1():
    cfg = ModeConfig.mainline()
    assert cfg.name == GameMode.MAINLINE
    assert cfg.start_level == 1
    assert cfg.chapter_multiplier == 1.0
    assert cfg.autolevel_pace == "boss"


def test_modeconfig_free_defaults_l10():
    cfg = ModeConfig.free()
    assert cfg.name == GameMode.FREE
    assert cfg.start_level == 10
    assert cfg.chapter_multiplier == 1.0
    assert cfg.autolevel_pace == "boss"


def test_modeconfig_free_custom_start_level():
    cfg = ModeConfig.free(start_level=20)
    assert cfg.start_level == 20


def test_modeconfig_is_frozen():
    """Frozen dataclass: cannot mutate after construction."""
    cfg = ModeConfig.mainline()
    with pytest.raises(Exception):  # FrozenInstanceError
        cfg.start_level = 5  # type: ignore[misc]


# ── AUTOEVEL_RATES (FE8 Boss pattern) ──────────────────────────


def test_autolevel_rates_match_boss_pattern():
    """FE8 boss-class units use 85/50/10/10/10/15/30 per level.

    We only carry HP/Atk/Def/MAtk/MDef on the BaseUnitClass right now;
    the missing four stats (Skl/Spd/Res/Lck) are filled with 0 below
    until Phase 1 step 4 (Hero roster) extends the class surface.
    """
    assert AUTOEVEL_RATES["hp"] == 85
    assert AUTOEVEL_RATES["atk"] == 50
    assert AUTOEVEL_RATES["matk"] == 50
    assert AUTOEVEL_RATES["def"] == 10
    assert AUTOEVEL_RATES["mdef"] == 15


# ── spawn_generic_stats: numeric behaviour ────────────────────────


def test_spawn_generic_l1_returns_class_base():
    """At L1 no autolevel is applied — result == class.base directly."""
    # Pick a real class and verify L1.
    for tid in ["lancer", "warrior", "berserker", "falcon_knight"]:
        from app.classes.units import get

        p = get(tid)
        stats = spawn_generic_stats(tid, start_level=1)
        assert stats["hp"] == p.base_hp, f"{tid} hp mismatch at L1"
        assert stats["atk"] == p.base_atk, f"{tid} atk mismatch at L1"
        assert stats["def"] == p.base_def, f"{tid} def mismatch at L1"
        assert stats["matk"] == p.base_matk, f"{tid} matk mismatch at L1"
        assert stats["mdef"] == p.base_mdef, f"{tid} mdef mismatch at L1"


def test_spawn_generic_l10_autolevel_applied():
    """At L10 (+9 levels above L1) the lane autolevel rate kicks in.

    Bonus per stat = int(9 × lane_rate / 100), where lane_rate comes from
    the unit's combat lane (physical/magic) — see lane_growth_rates().
    Expectations are derived from the implementation's own base + rates so
    this stays correct across数值 re-calibration.
    """
    from app.classes.units import get
    from app.progression.policies import lane_growth_rates

    p = get("lancer")
    rates = lane_growth_rates(p.attack_kind)
    s_l1 = spawn_generic_stats("lancer", start_level=1)
    s_l10 = spawn_generic_stats("lancer", start_level=10)

    assert s_l10["hp"] == s_l1["hp"] + int(9 * rates["hp"] / 100)
    assert s_l10["atk"] == s_l1["atk"] + int(9 * rates["atk"] / 100)
    assert s_l10["def"] == s_l1["def"] + int(9 * rates["def"] / 100)


def test_spawn_generic_mov_does_not_scale():
    """mov is class-static — must not change with level."""
    s_l1 = spawn_generic_stats("falcon_knight", start_level=1)
    s_l10 = spawn_generic_stats("falcon_knight", start_level=10)
    assert s_l1["mov"] == s_l10["mov"]
    assert s_l10["mov"] == 6  # falcon_knight.base_mov = 6


def test_spawn_generic_attack_range_does_not_scale():
    """attack_range is class-static — must not change with level."""
    s_l1 = spawn_generic_stats("lancer", start_level=1)
    s_l10 = spawn_generic_stats("lancer", start_level=20)
    assert s_l1["attack_range"] == s_l10["attack_range"]
    assert s_l10["attack_range"] == 1


def test_spawn_generic_l20_caps_are_reasonable():
    """At L20 (+19 levels) lane-autolevel bumps follow the formula and stay sane."""
    from app.classes.units import get
    from app.progression.policies import lane_growth_rates

    p = get("warrior")
    rates = lane_growth_rates(p.attack_kind)
    s = spawn_generic_stats("warrior", start_level=20)
    # Formula: base + int(19 × lane_rate / 100) — derived from implementation.
    assert s["hp"] == p.base_hp + int(19 * rates["hp"] / 100)
    assert s["atk"] == p.base_atk + int(19 * rates["atk"] / 100)
    assert s["def"] == p.base_def + int(19 * rates["def"] / 100)
    # Sanity caps: a 19-level autolevel must not explode into absurd stats.
    assert s["hp"] < 120
    assert s["atk"] < 60
    assert s["def"] < 40


def test_spawn_generic_zero_levels_above_l1():
    """start_level=1 must produce a clean L1 base (no autolevel)."""
    from app.classes.units import get

    p = get("berserker")
    s = spawn_generic_stats("berserker", start_level=1)
    assert s["hp"] == p.base_hp
    assert s["atk"] == p.base_atk
    assert s["def"] == p.base_def
    assert s["mov"] == p.base_mov
    assert s["attack_range"] == p.attack_range


def test_spawn_generic_start_level_below_1_clamps_to_zero():
    """start_level=0 must not produce negative stats (clamp to L1)."""
    s = spawn_generic_stats("warrior", start_level=0)
    p_l1 = spawn_generic_stats("warrior", start_level=1)
    assert s == p_l1  # clamped — same as L1


def test_spawn_generic_all_classes_callable():
    """Every registered unit type_id should accept L1 + L10 without error."""
    for tid in type_ids():
        s_l1 = spawn_generic_stats(tid, start_level=1)
        s_l10 = spawn_generic_stats(tid, start_level=10)
        for s in (s_l1, s_l10):
            assert isinstance(s["hp"], int)
            assert isinstance(s["atk"], int)
            assert isinstance(s["def"], int)
            assert isinstance(s["matk"], int)
            assert isinstance(s["mdef"], int)
            assert isinstance(s["mov"], int)
            assert isinstance(s["attack_range"], int)


# ── spawn_hero_stats: deferred ───────────────────────────────────


def test_spawn_hero_raises_not_implemented():
    """Per Phase 2 §4 the function deliberately awaits Hero design draft."""
    with pytest.raises(NotImplementedError):
        spawn_hero_stats("swordsman", char_growth={"hp": 80}, level=1)


# ── apply_spawn_generic_to_unit — Phase 2 Step 2 ───────────────


def _make_unit(type_id: str, **overrides):
    """Build a Unit row with sensible defaults for in-memory tests."""
    from app.classes.units import get as get_class
    from app.models import Unit

    profile = get_class(type_id)
    defaults = {
        "player_id": 1,
        "unit_type": type_id,
        "name": f"Test {type_id}",
        "level": 1,
        "exp": 0,
        "hp": 1,
        "max_hp": 1,
        "atk": 1,
        "def_": 1,
        "matk": 0,
        "mdef": 0,
        "mov": 1,
        "mp": 0,
        "morale": 0,
        "x": 5,
        "y": 5,
        "has_acted": False,
        "has_moved": False,
        "skills": [],
    }
    defaults.update(overrides)
    # Construct Unit object directly (in-memory, no DB flush needed for field mutation tests).
    unit = Unit(**defaults)
    return unit


def test_apply_spawn_to_unit_mainline_l1_uses_class_base():
    """Mainline at L1 = pure class.base, no autolevel bump."""
    from app.modes import apply_spawn_generic_to_unit
    from app.classes.units import get as get_class

    for tid in ("lancer", "warrior", "berserker", "falcon_knight"):
        unit = _make_unit(tid)
        apply_spawn_generic_to_unit(unit, tid, start_level=1)
        profile = get_class(tid)
        assert unit.hp == profile.base_hp, f"{tid} hp"
        assert unit.atk == profile.base_atk, f"{tid} atk"
        assert unit.def_ == profile.base_def, f"{tid} def"
        assert unit.matk == profile.base_matk
        assert unit.mdef == profile.base_mdef
        # mov uses class.base_mov (not mp_pool — autolevel would otherwise
        # mid-attack-modify it, which the existing path was wrongly doing
        # via mov=uc.mp_pool).
        assert unit.mov == profile.base_mov, f"{tid} mov"


def test_apply_spawn_to_unit_free_l10_autolevel_hp():
    """Free mode L10 → hp grows by 9 × 85 / 100 = +7."""
    from app.modes import apply_spawn_generic_to_unit

    unit_l1 = _make_unit("lancer")
    apply_spawn_generic_to_unit(unit_l1, "lancer", start_level=1)

    unit_l10 = _make_unit("lancer")
    apply_spawn_generic_to_unit(unit_l10, "lancer", start_level=10)

    hp_bump = int(9 * 0.85)  # +7
    assert unit_l10.hp == unit_l1.hp + hp_bump


def test_apply_spawn_to_unit_skips_level_below_one():
    """start_level=0 must not produce negative stats."""
    from app.modes import apply_spawn_generic_to_unit

    unit_l1 = _make_unit("warrior")
    apply_spawn_generic_to_unit(unit_l1, "warrior", start_level=1)

    unit_zero = _make_unit("warrior")
    apply_spawn_generic_to_unit(unit_zero, "warrior", start_level=0)

    assert unit_zero.hp == unit_l1.hp
    assert unit_zero.atk == unit_l1.atk
    assert unit_zero.def_ == unit_l1.def_


def test_apply_spawn_preserves_max_hp_when_unit_is_alive():
    """spawn writes BOTH hp and max_hp to the same value (no wounded-spawn via spawn)."""
    from app.modes import apply_spawn_generic_to_unit

    unit = _make_unit("warrior")
    apply_spawn_generic_to_unit(unit, "warrior", start_level=1)
    assert unit.hp == unit.max_hp, "spawn must keep hp == max_hp"


def test_apply_spawn_to_unit_does_not_touch_position_or_skills():
    """apply_spawn_generic_to_unit must preserve x/y/name/skills — those are caller-managed."""
    from app.modes import apply_spawn_generic_to_unit

    unit = _make_unit("lancer", name="Hero☆", x=7, y=9, skills=["snipe"])
    apply_spawn_generic_to_unit(unit, "lancer", start_level=10)
    assert unit.name == "Hero☆"
    assert (unit.x, unit.y) == (7, 9)
    assert unit.skills == ["snipe"]


# ── New unit classes can spawn (Phase 2 Step 2 acceptance) ────────


def test_four_new_classes_can_spawn_in_memory():
    """All four Phase 2 new classes produce a valid Unit row.

    Acceptance test for the commit's "ordinary units onto the board"
    scope — no sprite/UI yet, but data path must succeed end-to-end.
    """
    from app.classes.units import get_or_none
    from app.modes import apply_spawn_generic_to_unit

    for tid in ("lancer", "warrior", "berserker", "falcon_knight"):
        profile = get_or_none(tid)
        assert profile is not None, f"{tid} must be in registry"
        unit = _make_unit(tid, x=5, y=5)
        apply_spawn_generic_to_unit(unit, tid, start_level=1)
        # All four values are populated and non-negative.
        for attr in ("hp", "max_hp", "atk", "def_", "matk", "mdef", "mov"):
            value = getattr(unit, attr)
            assert isinstance(value, int) and value >= 0, f"{tid} {attr}={value}"
        assert unit.unit_type == tid
        # Class-static fields come from compile().
        assert unit.mov == profile.base_mov


# ── Phase 2 Step 3 — Free mode L10 baseline ─────────────────────


def test_mode_config_mainline_yields_l1_start_level():
    """Default ModeConfig.mainline() should result in L1 spawn for Generic."""
    from app.modes import ModeConfig

    cfg = ModeConfig.mainline()
    start_level = 10 if cfg.name.value == "free" else 1
    assert start_level == 1


def test_mode_config_free_yields_l10_start_level():
    from app.modes import ModeConfig

    cfg = ModeConfig.free()
    start_level = 10 if cfg.name.value == "free" else 1
    assert start_level == 10


def test_mode_config_free_with_custom_start_level():
    from app.modes import ModeConfig

    cfg = ModeConfig.free(start_level=15)
    assert cfg.start_level == 15
    assert cfg.name.value == "free"


def test_gamemode_string_values_match_api_schema():
    """GameMode enum strings must match the Literal["mainline","free"]
    type used in CreateGameRequest — schema ↔ mode.py must stay in sync."""
    from app.modes import GameMode

    assert GameMode.MAINLINE.value == "mainline"
    assert GameMode.FREE.value == "free"


def test_apply_spawn_free_l10_matches_applied_l10_dictionary():
    """End-to-end: start_level=10 via apply_spawn_generic_to_unit must match
    spawn_generic_stats free config output."""
    from app.modes import spawn_generic_stats, apply_spawn_generic_to_unit

    stats_dict = spawn_generic_stats("lancer", start_level=10)
    unit = _make_unit("lancer")
    apply_spawn_generic_to_unit(unit, "lancer", start_level=10)
    assert unit.hp == stats_dict["hp"]
    assert unit.atk == stats_dict["atk"]
    assert unit.def_ == stats_dict["def"]
    assert unit.matk == stats_dict["matk"]
    assert unit.mdef == stats_dict["mdef"]
    assert unit.mov == stats_dict["mov"]


def test_apply_spawn_free_l10_actually_raises_stats_above_l1():
    """Acceptance: free L10 must show measurable stat boost vs L1.

    For a lancer: HP rises 27→34 (+9 × 0.85 ≈ +7);
    Atk rises 8→12 (+9 × 0.50 ≈ +4).  No regression to L1 defaults.
    """
    from app.modes import apply_spawn_generic_to_unit

    unit_l1 = _make_unit("lancer")
    apply_spawn_generic_to_unit(unit_l1, "lancer", start_level=1)
    unit_l10 = _make_unit("lancer")
    apply_spawn_generic_to_unit(unit_l10, "lancer", start_level=10)

    assert unit_l10.hp > unit_l1.hp, "free L10 should have higher HP than L1"
    assert unit_l10.atk > unit_l1.atk, "free L10 should have higher Atk than L1"
