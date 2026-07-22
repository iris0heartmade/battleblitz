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
    """At L10 (+9 levels above L1) the Boss autolevel rate kicks in.

    For HP (rate=85): +9 × 85 / 100 = +7 (rounded)
    For Atk (rate=50): +9 × 50 / 100 = +4 (rounded)
    For Def (rate=10): +9 × 10 / 100 = +0 (rounded)
    """
    from app.classes.units import get

    p = get("lancer")
    s_l1 = spawn_generic_stats("lancer", start_level=1)
    s_l10 = spawn_generic_stats("lancer", start_level=10)

    # HP: +9 × 0.85 = +7.65 → 7
    assert s_l10["hp"] == s_l1["hp"] + int(9 * 0.85)
    # Atk: +9 × 0.50 = +4.5 → 4
    assert s_l10["atk"] == s_l1["atk"] + int(9 * 0.50)
    # Def: +9 × 0.10 = +0.9 → 0
    assert s_l10["def"] == s_l1["def"] + int(9 * 0.10)


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
    """At L20 (+19 levels) Boss-autolevel bumps should not produce absurd stats."""
    s = spawn_generic_stats("warrior", start_level=20)
    # warrior L1 = HP 28 Atk 10 Def 3
    # +19 × 0.85 HP = +16 → 44
    # +19 × 0.50 Atk = +9 → 19
    # +19 × 0.10 Def = +1 → 4
    assert s["hp"] == 44
    assert s["atk"] == 19
    assert s["def"] == 4


def test_spawn_generic_zero_levels_above_l1():
    """start_level=1 must produce a clean L1 base (no autolevel)."""
    s = spawn_generic_stats("berserker", start_level=1)
    assert s["hp"] == 30   # berserker.base_hp
    assert s["atk"] == 14  # berserker.base_atk
    assert s["def"] == 5   # berserker.base_def
    assert s["mov"] == 4
    assert s["attack_range"] == 1


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
