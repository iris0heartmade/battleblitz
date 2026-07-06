"""P2.5 — AI personality system (aggressive / balanced / conservative).

Covers:
  * AIProfile dataclass is frozen and has all required fields.
  * _ai_profile lookup falls back to "balanced" for unknown / empty
    personality.
  * _ai_should_flee thresholds (10% / 20% / 30%).
  * _ai_pick_claim_target: distance filter, distance_weight penalty,
    risk_penalty for nearby enemies, claim_emergency_bonus, the
    graduated behaviour between 3 档.
  * _ai_pick_attack_target: kill-shots bypass aggression scaling;
    non-kill shots are scaled by profile.aggression.
"""
from __future__ import annotations

import pytest

from app.game_logic import (
    AIProfile, _AI_PROFILES, _ai_profile, _ai_should_flee,
    _ai_pick_claim_target, _ai_pick_attack_target, _AISnapshot,
)
from app.models import Unit


# ============================================================
# AIProfile structure
# ============================================================

def test_three_personalities_present():
    assert set(_AI_PROFILES.keys()) == {"aggressive", "balanced", "conservative"}


def test_profiles_are_frozen():
    for prof in _AI_PROFILES.values():
        assert isinstance(prof, AIProfile)
        with pytest.raises((AttributeError, Exception)):
            prof.aggression = 0.5  # type: ignore[misc]


def test_profile_graduation_ordering():
    """Every numeric field should graduate aggressive > balanced > conservative
    (or the opposite direction for the "more conservative" metrics like
    flee_hp_pct / distance_weight / risk_penalty)."""
    a = _AI_PROFILES["aggressive"]
    b = _AI_PROFILES["balanced"]
    c = _AI_PROFILES["conservative"]
    # Higher = more aggressive
    assert a.claim_distance > b.claim_distance > c.claim_distance
    assert a.castle_pull > b.castle_pull > c.castle_pull
    assert a.aggro_range > b.aggro_range > c.aggro_range
    assert a.aggression > b.aggression > c.aggression
    assert a.kill_bonus_move > b.kill_bonus_move > c.kill_bonus_move
    assert a.recruit_max_roster > b.recruit_max_roster > c.recruit_max_roster
    assert a.recruit_threshold < b.recruit_threshold < c.recruit_threshold
    # Lower = more conservative
    assert a.distance_weight < b.distance_weight < c.distance_weight
    assert a.risk_penalty < b.risk_penalty < c.risk_penalty
    assert abs(a.in_range_penalty) < abs(b.in_range_penalty) < abs(c.in_range_penalty)
    assert a.flee_hp_pct < b.flee_hp_pct < c.flee_hp_pct


def test_ai_profile_fallback_to_balanced():
    """A player with no / unknown personality gets balanced."""
    p = type("P", (), {"agent_personality": "trickster"})()
    assert _ai_profile(p) is _AI_PROFILES["balanced"]
    p_none = type("P", (), {"agent_personality": None})()
    assert _ai_profile(p_none) is _AI_PROFILES["balanced"]
    p_empty = type("P", (), {"agent_personality": ""})()
    assert _ai_profile(p_empty) is _AI_PROFILES["balanced"]


# ============================================================
# Flee thresholds
# ============================================================

def _stub(max_hp=100, hp=100):
    return Unit(
        player_id=1, unit_type="swordsman", name="X", level=1, exp=0,
        hp=hp, max_hp=max_hp, atk=18, def_=12, matk=4, mdef=4,
        mov=5, mp=5, morale=0, x=0, y=0,
        has_acted=False, has_moved=False, skills=[],
    )


def test_should_flee_thresholds():
    u_full = _stub(hp=100)        # 100% HP
    u_30 = _stub(hp=30)           # 30% HP
    u_21 = _stub(hp=21)           # 21% HP — above balanced threshold
    u_20 = _stub(hp=20)           # 20% HP — at balanced threshold
    u_11 = _stub(hp=11)           # 11% HP — above aggressive threshold
    u_10 = _stub(hp=10)           # 10% HP — at aggressive threshold
    u_5 = _stub(hp=5)             # 5% HP
    # Aggressive: flee at-or-below 10% HP.
    assert _ai_should_flee(u_5, _AI_PROFILES["aggressive"]) is True
    assert _ai_should_flee(u_10, _AI_PROFILES["aggressive"]) is True
    assert _ai_should_flee(u_11, _AI_PROFILES["aggressive"]) is False
    # Balanced: flee at-or-below 20% HP.
    assert _ai_should_flee(u_20, _AI_PROFILES["balanced"]) is True
    assert _ai_should_flee(u_21, _AI_PROFILES["balanced"]) is False
    assert _ai_should_flee(u_30, _AI_PROFILES["balanced"]) is False
    # Conservative: flee at-or-below 30% HP.
    assert _ai_should_flee(u_30, _AI_PROFILES["conservative"]) is True
    assert _ai_should_flee(u_full, _AI_PROFILES["conservative"]) is False


# ============================================================
# Claim target scoring
# ============================================================

def _build_snap(tiles, enemy_units=None):
    """Build a minimal _AISnapshot for _ai_pick_claim_target."""
    terrain = {(x, y): t for (x, y, t) in tiles}
    return _AISnapshot(
        terrain=terrain,
        owners={(x, y): None for (x, y, _) in tiles},
        occ={(x, y): None for (x, y, _) in tiles},
        enemy_units=enemy_units or [],
        ally_units=[],
        my_units=[],
        enemy_castles=[],
        unowned_castles=[],
    )


def _stub_enemy(x, y):
    return Unit(
        player_id=2, unit_type="swordsman", name="E", level=1, exp=0,
        hp=45, max_hp=45, atk=18, def_=12, matk=4, mdef=4,
        mov=5, mp=5, morale=0, x=x, y=y,
        has_acted=False, has_moved=False, skills=[],
    )


def test_claim_target_filters_beyond_distance():
    """claim_distance=4 (conservative) refuses a village 5 tiles away."""
    tiles = [(0, 0, "plain"), (5, 0, "village")]
    snap = _build_snap(tiles)
    unit = _stub()
    prof = _AI_PROFILES["conservative"]
    assert prof.claim_distance == 4
    result = _ai_pick_claim_target(unit, snap, prof, active_claims=set(),
                                    my_castle_xy=None)
    assert result is None  # 5 tiles > 4 → rejected


def test_claim_target_aggressive_reaches_far_village():
    """claim_distance=8 (aggressive) accepts a village 5 tiles away
    (barracks would have a bigger base value to cover more distance,
    but villages are still reachable for the eager aggressor)."""
    tiles = [(0, 0, "plain"), (5, 0, "barracks")]
    snap = _build_snap(tiles)
    unit = _stub()
    prof = _AI_PROFILES["aggressive"]
    assert prof.claim_distance == 8
    result = _ai_pick_claim_target(unit, snap, prof, active_claims=set(),
                                    my_castle_xy=None)
    # barracks base 100 - 5 * 8 distance_weight = 60 > 0 → takes it
    assert result == (5, 0)


def test_claim_target_picks_closer_when_score_says_so():
    """Of two claimable villages, the one closer wins (distance_weight
    penalty makes farther ones worse)."""
    tiles = [(0, 0, "plain"), (2, 0, "village"), (4, 0, "village")]
    snap = _build_snap(tiles)
    unit = _stub()
    prof = _AI_PROFILES["balanced"]  # distance_weight=18
    result = _ai_pick_claim_target(unit, snap, prof, active_claims=set(),
                                    my_castle_xy=None)
    # (2,0): 50 - 36 = 14. (4,0): 50 - 72 = -22. Closer wins.
    assert result == (2, 0)


def test_claim_target_risk_penalty_deters_conservative():
    """Conservative AI refuses a village next to an enemy; aggressive
    AI still takes it."""
    tiles = [(0, 0, "plain"), (2, 0, "village")]
    enemy = _stub_enemy(2, 1)  # 1 tile from the village
    snap = _build_snap(tiles, [enemy])
    unit = _stub()
    a = _ai_pick_claim_target(unit, snap, _AI_PROFILES["aggressive"],
                              active_claims=set(), my_castle_xy=None)
    c = _ai_pick_claim_target(unit, snap, _AI_PROFILES["conservative"],
                              active_claims=set(), my_castle_xy=None)
    # Aggressive: 50 - 2*8 - 1*5 = 29 → still picks
    assert a == (2, 0)
    # Conservative: 50 - 2*28 - 1*20 = -26 → rejects
    assert c is None


def test_claim_emergency_bonus_overrides_distance_skepticism():
    """All 3 档 grab a tile the enemy is actively claiming, even if
    the conservative AI's distance_weight would otherwise reject it.

    Distance 5 exceeds conservative.claim_distance=4, but the
    emergency bonus (150) bypasses the distance cap.
    """
    tiles = [(0, 0, "plain"), (5, 0, "village")]
    enemy = _stub_enemy(5, 0)
    snap = _build_snap(tiles, [enemy])
    unit = _stub()
    # Conservative: distance 5 > 4 normally, but the active-claim
    # bonus should pull it in (and we don't want to add a 4th
    # nearby enemy that would push the score to <=0).
    c = _ai_pick_claim_target(
        unit, snap, _AI_PROFILES["conservative"],
        active_claims={(5, 0)}, my_castle_xy=None,
    )
    assert c == (5, 0)


def test_claim_emergency_bonus_graduates_across_profiles():
    """claim_emergency_bonus is 200/175/150. Verify the
    'aggressive > balanced > conservative' graduation."""
    a = _AI_PROFILES["aggressive"]
    b = _AI_PROFILES["balanced"]
    c = _AI_PROFILES["conservative"]
    assert a.claim_emergency_bonus > b.claim_emergency_bonus > c.claim_emergency_bonus
    assert (a.claim_emergency_bonus, b.claim_emergency_bonus, c.claim_emergency_bonus) == (200, 175, 150)


def test_castle_pull_graduates_high_across_all_profiles():
    """castle_pull is intentionally high for ALL 3 档 (seize = win)."""
    assert _AI_PROFILES["aggressive"].castle_pull == 400
    assert _AI_PROFILES["balanced"].castle_pull == 300
    assert _AI_PROFILES["conservative"].castle_pull == 250
    # All are way above any other single bonus in the system.
    for prof in _AI_PROFILES.values():
        assert prof.castle_pull >= 250


# ============================================================
# Attack target — aggression scaling
# ============================================================

def _build_snap_with_enemy_at(unit_xy, enemy_xy, *, enemy_hp=30, enemy_atk=10):
    """A snap with the unit's position, one enemy, plain terrain."""
    return _AISnapshot(
        terrain={unit_xy: "plain", enemy_xy: "plain"},
        owners={unit_xy: 1, enemy_xy: None},
        occ={unit_xy: 1, enemy_xy: 2},
        enemy_units=[
            Unit(player_id=2, unit_type="swordsman", name="E", level=1, exp=0,
                 hp=enemy_hp, max_hp=enemy_hp, atk=enemy_atk, def_=10,
                 matk=0, mdef=0, mov=5, mp=5, morale=0,
                 x=enemy_xy[0], y=enemy_xy[1],
                 has_acted=False, has_moved=False, skills=[])
        ],
        ally_units=[],
        my_units=[],
        enemy_castles=[],
        unowned_castles=[],
    )


def test_attack_target_kill_shot_always_picked():
    """A killable enemy (hp <= attacker.atk) is taken by ALL 3 档 —
    kill-shots bypass the aggression scaling."""
    # attacker at (0,0), enemy at (0,1), enemy hp=10, attacker atk=18 → killable
    unit = Unit(player_id=1, unit_type="swordsman", name="A", level=1, exp=0,
                hp=45, max_hp=45, atk=18, def_=12, matk=4, mdef=4,
                mov=5, mp=5, morale=0, x=0, y=0,
                has_acted=False, has_moved=False, skills=[])
    for prof_name in ("aggressive", "balanced", "conservative"):
        prof = _AI_PROFILES[prof_name]
        snap = _build_snap_with_enemy_at((0, 0), (0, 1), enemy_hp=10)
        target = _ai_pick_attack_target(unit, snap, prof)
        assert target is not None, f"{prof_name} refused a kill shot"
        assert target.hp == 10