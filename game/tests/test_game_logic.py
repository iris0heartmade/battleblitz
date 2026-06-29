"""
Unit tests for `app.game_logic` — combat math, map gen, level-up, AI helpers.

Most of `game_logic` is pure (damage calc, map gen) so we can test without
a database. The DB-touching functions (apply_end_of_turn, ai_take_turn)
need an integration test instead — see `test_integration_smoke.py`.
"""
from __future__ import annotations

import random

import pytest

from app.config import (
    MAP_SIZE,
    MORALE_MAX,
    SKILL_DOUBLE_STRIKE,
    TERRAIN_CASTLE,
    TERRAIN_PLAIN,
)
from app.classes.units.skills.base import SkillContext
from app.classes.units.skills.heal import HealSkill
from app.game_logic import (
    _type_multiplier,
    apply_damage,
    attack_with_double_strike,
    award_morale,
    calculate_damage,
    castle_positions,
    generate_map,
    unit_attack_range,
)
from app.models import Unit


# ============================================================
# Helpers to construct Unit stubs without touching the DB.
# ============================================================

def _stub_unit(
    unit_type: str = "swordsman",
    *,
    atk: int = 20,
    def_: int = 10,
    matk: int = 0,
    mdef: int = 0,
    hp: int = 50,
    morale: int = 0,
    skills: list | None = None,
    x: int = 0,
    y: int = 0,
) -> Unit:
    """In-memory Unit row, never persisted. Note: `id` stays None."""
    return Unit(
        player_id=1,
        unit_type=unit_type,
        name="Stub",
        level=1,
        exp=0,
        hp=hp,
        max_hp=hp,
        atk=atk,
        def_=def_,
        matk=matk,
        mdef=mdef,
        mov=5,
        mp=5,
        morale=morale,
        x=x,
        y=y,
        has_acted=False,
        skills=skills or [],
    )


# ============================================================
# calculate_damage
# ============================================================

@pytest.mark.unit
class TestCalculateDamage:
    def test_kill_when_damage_exceeds_hp(self):
        atk = _stub_unit(atk=100)
        df = _stub_unit(hp=10)
        r = calculate_damage(atk, df, tile_def_bonus=0,
                             crit=False, rng=random.Random(0))
        assert r.is_kill is True
        assert r.damage >= 10

    def test_minimum_damage_is_one(self):
        # Pathological: attacker weaker than defender + huge terrain
        atk = _stub_unit(atk=1)
        df = _stub_unit(def_=1000, hp=9999)
        r = calculate_damage(atk, df, tile_def_bonus=100,
                             crit=False, rng=random.Random(0))
        assert r.damage >= 1

    def test_morale_scales_attack(self):
        # morale=0 vs morale=MORALE_MAX: damage should be larger with morale.
        df = _stub_unit(hp=200, def_=20)
        a0 = _stub_unit(atk=20, morale=0)
        a3 = _stub_unit(atk=20, morale=MORALE_MAX)
        r0 = calculate_damage(a0, df, 0, crit=False, rng=random.Random(1))
        r3 = calculate_damage(a3, df, 0, crit=False, rng=random.Random(1))
        assert r3.damage > r0.damage

    def test_terrain_bonus_increases_defense(self):
        atk = _stub_unit(atk=30)
        df = _stub_unit(hp=999, def_=10)
        r_plain = calculate_damage(atk, df, tile_def_bonus=0,
                                   crit=False, rng=random.Random(2))
        r_castle = calculate_damage(atk, df, tile_def_bonus=5,
                                    crit=False, rng=random.Random(2))
        # Higher effective defense → less damage
        assert r_castle.damage < r_plain.damage

    def test_crit_multiplies_damage(self):
        atk = _stub_unit(atk=30)
        df = _stub_unit(hp=999, def_=10)
        r_no = calculate_damage(atk, df, 0, crit=False, rng=random.Random(3))
        r_yes = calculate_damage(atk, df, 0, crit=True, rng=random.Random(3))
        # The crit multiplier is applied to the *base*, not the after-defence ratio.
        # We just check that crit is strictly greater.
        assert r_yes.damage > r_no.damage
        assert r_yes.is_crit is True
        assert r_no.is_crit is False

    # ----- Magic combat (2026-06-30 refactor) -----

    def test_warlock_deals_magic_damage_to_swordsman(self):
        # Warlock (magic) attacks Swordsman (physical). Damage type is
        # magic → MATK vs MDEF. Swordsman's mdef is 0, so the hit is
        # near-max. Compare a high-MDEF variant to confirm the formula
        # picks MDEF (the magic path) — if it accidentally picked DEF,
        # the two values would be equal.
        warlock = _stub_unit(unit_type="warlock", atk=8, matk=22, hp=999)
        sword   = _stub_unit(unit_type="swordsman", def_=12, mdef=0, hp=999)
        sword_high_mdef = _stub_unit(unit_type="swordsman", def_=12,
                                     mdef=15, hp=999)
        r = calculate_damage(warlock, sword, tile_def_bonus=0,
                             crit=False, rng=random.Random(0))
        r_high = calculate_damage(warlock, sword_high_mdef, 0, crit=False,
                                  rng=random.Random(0))
        assert r.damage > 15, (
            "Magic damage path (MATK=22 vs MDEF=0) should be near max."
        )
        assert r.damage > r_high.damage, (
            "Raising MDEF must reduce damage — confirms the formula is "
            "using MDEF for the magic attack. If it had used DEF, both "
            "values would be equal."
        )

    def test_swordsman_deals_physical_damage_to_warlock(self):
        # Swordsman (physical) attacks Warlock (magic). Damage type is
        # physical → ATK vs DEF. Warlock's DEF is 10, so the hit lands
        # near max. Compare against the physical fallback on the
        # defender to confirm the formula picks DEF, not MDEF.
        sword   = _stub_unit(unit_type="swordsman", atk=18, matk=4, hp=999)
        warlock = _stub_unit(unit_type="warlock", def_=10, mdef=12, hp=999)
        r = calculate_damage(sword, warlock, tile_def_bonus=0,
                             crit=False, rng=random.Random(0))
        # If the formula wrongly used MDEF=12 instead of DEF=10, damage
        # would be smaller. We sanity-check by comparing against a
        # variant with DEF inflated — physical damage should react to it.
        warlock_high_def = _stub_unit(unit_type="warlock", def_=20, mdef=12,
                                      hp=999)
        r_high = calculate_damage(sword, warlock_high_def, 0, crit=False,
                                  rng=random.Random(0))
        assert r.damage > r_high.damage, (
            "Physical attack path must use DEF, so raising DEF should "
            "reduce damage. If the formula picked MDEF by mistake the "
            "two values would be equal."
        )

    def test_healer_blocks_magic_damage_with_mdef(self):
        # Healer is now magic-type (attack_kind="magic"). A Warlock's
        # magic attack should be blocked by Healer's MDEF (12), not its
        # DEF (9). Verify by comparing damage with high vs low MDEF.
        warlock = _stub_unit(unit_type="warlock", atk=8, matk=22, hp=999)
        healer  = _stub_unit(unit_type="healer", def_=9, mdef=12, hp=999)
        r = calculate_damage(warlock, healer, tile_def_bonus=0,
                             crit=False, rng=random.Random(0))
        healer_low_mdef = _stub_unit(unit_type="healer", def_=9, mdef=2,
                                     hp=999)
        r_low = calculate_damage(warlock, healer_low_mdef, 0, crit=False,
                                rng=random.Random(0))
        assert r.damage < r_low.damage, (
            "Healer is a magic unit, so a magic attacker should hit its "
            "MDEF. Lowering MDEF should INCREASE damage. If the formula "
            "used DEF instead, the two values would be equal."
        )

    def test_counter_attack_picks_attackers_own_kind(self):
        """Counter-attack damage type must follow the COUNTER's
        attack_kind, not the original attacker's. Otherwise a
        Swordsman hitting a Warlock would trigger a physical counter
        (Swordsman doesn't have MATK), making the counter basically
        harmless even though Warlocks are squishy. The existing
        attack_with_double_strike(target=counter, attacker=original)
        signature must route through the same calculate_damage
        function so this test stays the single source of truth."""
        sword   = _stub_unit(unit_type="swordsman", atk=18, matk=4, hp=999)
        warlock = _stub_unit(unit_type="warlock", atk=8, matk=22, def_=10,
                             mdef=12, hp=999)
        # Counter path: warlock attacks swordsman.
        r = attack_with_double_strike(warlock, sword, tile_def_bonus=0,
                                      rng=random.Random(0))
        # Total damage should be substantial — warlock's MATK=22 hits
        # swordsman's MDEF=4 (high damage). If the formula mistakenly
        # used warlock's atk=8 against swordsman's def_=12 instead, the
        # damage would be much smaller.
        total = sum(h.damage for h in r)
        assert total >= 12, (
            f"Counter should be magic (high damage, expected >=12, "
            f"got {total}). If the counter used physical (ATK=8 vs "
            f"DEF=12) the total would be tiny."
        )


# ============================================================
# attack_with_double_strike
# ============================================================

@pytest.mark.unit
class TestDoubleStrike:
    def test_no_double_strike_returns_single_hit(self):
        atk = _stub_unit(atk=30, skills=[])
        df = _stub_unit(hp=999, def_=10)
        hits = attack_with_double_strike(atk, df, 0, rng=random.Random(0))
        assert len(hits) == 1

    def test_double_strike_returns_two_hits(self):
        atk = _stub_unit(atk=30, skills=[SKILL_DOUBLE_STRIKE])
        df = _stub_unit(hp=999, def_=10)
        hits = attack_with_double_strike(atk, df, 0, rng=random.Random(0))
        assert len(hits) == 2

    def test_double_strike_damage_is_half_per_hit(self):
        atk = _stub_unit(atk=30, skills=[SKILL_DOUBLE_STRIKE])
        df = _stub_unit(hp=999, def_=10)
        single = attack_with_double_strike(
            _stub_unit(atk=30, skills=[]), df, 0, rng=random.Random(0)
        )[0]
        double = attack_with_double_strike(atk, df, 0, rng=random.Random(0))
        # Each double-strike hit should be ~half of the single hit.
        for h in double:
            assert h.damage == max(1, single.damage // 2)


# ============================================================
# apply_damage
# ============================================================

@pytest.mark.unit
class TestApplyDamage:
    def test_subtracts_hp(self):
        u = _stub_unit(hp=50)
        killed = apply_damage(u, 20)
        assert u.hp == 30
        assert killed is False

    def test_kill_flag(self):
        u = _stub_unit(hp=50)
        killed = apply_damage(u, 100)
        assert u.hp == 0
        assert killed is True

    def test_clamps_at_zero(self):
        u = _stub_unit(hp=10)
        apply_damage(u, 999)
        assert u.hp == 0


# ============================================================
# award_morale
# ============================================================

@pytest.mark.unit
class TestAwardMorale:
    def test_increments(self):
        u = _stub_unit(morale=1)
        award_morale(u)
        assert u.morale == 2

    def test_caps_at_max(self):
        u = _stub_unit(morale=MORALE_MAX)
        award_morale(u)
        assert u.morale == MORALE_MAX


# ============================================================
# type advantage
# ============================================================

@pytest.mark.unit
class TestTypeAdvantage:
    def test_swordsman_beats_knight(self):
        assert _type_multiplier(_stub_unit("swordsman"),
                                _stub_unit("knight")) == 1.20

    def test_knight_beats_archer(self):
        assert _type_multiplier(_stub_unit("knight"),
                                _stub_unit("archer")) == 1.20

    def test_no_advantage_between_non_matched(self):
        assert _type_multiplier(_stub_unit("archer"),
                                _stub_unit("swordsman")) == 1.0
        assert _type_multiplier(_stub_unit("healer"),
                                _stub_unit("healer")) == 1.0


# ============================================================
# unit_attack_range
# ============================================================

@pytest.mark.unit
class TestAttackRange:
    def test_swordsman_is_melee(self):
        # Swordsman base attack_range = 1 (melee)
        assert unit_attack_range(_stub_unit("swordsman")) == 1

    def test_archer_default(self):
        assert unit_attack_range(_stub_unit("archer")) == 2

    def test_archer_with_snipe(self):
        u = _stub_unit("archer", skills=["snipe"])
        assert unit_attack_range(u) == 3


# ============================================================
# heal skill (HealSkill)
# ============================================================

@pytest.mark.unit
class TestHeal:
    _skill = HealSkill()

    def test_heals_adjacent(self):
        """HealSkill.execute() restores HP on an adjacent injured ally."""
        import asyncio
        from unittest.mock import AsyncMock

        h = _stub_unit("healer", skills=["heal"], x=0, y=0)
        a = _stub_unit("swordsman", hp=20, x=1, y=0)
        a.player_id = h.player_id
        a.max_hp = 50
        ctx = SkillContext(user=h, target=a)
        session = AsyncMock()

        result = asyncio.run(self._skill.execute(session, ctx))
        assert result.restored_hp == 20
        assert a.hp == 40

    def test_can_use_adjacent_injured_same_player(self):
        """can_use returns True when all conditions are met."""
        h = _stub_unit("healer", skills=["heal"], x=0, y=0)
        a = _stub_unit("swordsman", hp=20, x=1, y=0)
        a.player_id = h.player_id
        a.max_hp = 50
        ctx = SkillContext(user=h, target=a)
        assert self._skill.can_use(ctx) is True

    def test_cannot_use_when_not_adjacent(self):
        h = _stub_unit("healer", skills=["heal"], x=0, y=0)
        a = _stub_unit("swordsman", hp=20, x=2, y=0)
        a.player_id = h.player_id
        a.max_hp = 50
        ctx = SkillContext(user=h, target=a)
        assert self._skill.can_use(ctx) is False

    def test_cannot_use_when_full_hp(self):
        h = _stub_unit("healer", skills=["heal"], x=0, y=0)
        a = _stub_unit("swordsman", hp=50, x=1, y=0)
        a.player_id = h.player_id
        a.max_hp = 50
        ctx = SkillContext(user=h, target=a)
        assert self._skill.can_use(ctx) is False

    def test_cannot_use_when_other_player(self):
        h = _stub_unit("healer", skills=["heal"], x=0, y=0)
        a = _stub_unit("swordsman", hp=20, x=1, y=0)
        a.player_id = 99  # different from h.player_id=1
        a.max_hp = 50
        ctx = SkillContext(user=h, target=a)
        assert self._skill.can_use(ctx) is False


# ============================================================
# Map generation
# ============================================================

@pytest.mark.unit
class TestGenerateMap:
    def test_grid_size_is_correct(self):
        grid = generate_map(seed=42, num_castles=4)
        assert len(grid) == MAP_SIZE
        assert all(len(row) == MAP_SIZE for row in grid)

    def test_seed_is_deterministic(self):
        a = generate_map(seed=999, num_castles=2)
        b = generate_map(seed=999, num_castles=2)
        # Same seed → same terrain grid
        for y in range(MAP_SIZE):
            for x in range(MAP_SIZE):
                assert a[y][x].terrain == b[y][x].terrain

    def test_castle_count_matches_players(self):
        for n in (2, 3, 4):
            grid = generate_map(seed=1, num_castles=n)
            castles = sum(
                1 for row in grid for t in row if t.terrain == TERRAIN_CASTLE
            )
            assert castles == n, f"expected {n} castles, got {castles}"

    def test_invalid_castle_count_falls_back(self):
        grid = generate_map(seed=1, num_castles=99)
        castles = sum(
            1 for row in grid for t in row if t.terrain == TERRAIN_CASTLE
        )
        # Falls back to CASTLES_PER_GAME (= 4)
        assert castles == 4

    def test_castle_positions_helper(self):
        for n in (2, 3, 4):
            pos = castle_positions(n)
            assert len(pos) == n
            for seat, (x, y) in pos.items():
                assert 0 <= x < MAP_SIZE
                assert 0 <= y < MAP_SIZE
                assert seat < n
