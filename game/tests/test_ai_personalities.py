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
  * add-ai HTTP endpoint stores `personality` on Player.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
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
    u_full = _stub(hp=100)
    u_30 = _stub(hp=30)
    u_21 = _stub(hp=21)
    u_20 = _stub(hp=20)
    u_11 = _stub(hp=11)
    u_10 = _stub(hp=10)
    u_5 = _stub(hp=5)
    assert _ai_should_flee(u_5, _AI_PROFILES["aggressive"]) is True
    assert _ai_should_flee(u_10, _AI_PROFILES["aggressive"]) is True
    assert _ai_should_flee(u_11, _AI_PROFILES["aggressive"]) is False
    assert _ai_should_flee(u_20, _AI_PROFILES["balanced"]) is True
    assert _ai_should_flee(u_21, _AI_PROFILES["balanced"]) is False
    assert _ai_should_flee(u_30, _AI_PROFILES["balanced"]) is False
    assert _ai_should_flee(u_30, _AI_PROFILES["conservative"]) is True
    assert _ai_should_flee(u_full, _AI_PROFILES["conservative"]) is False


# ============================================================
# Claim target scoring
# ============================================================

def _build_snap(tiles, enemy_units=None):
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
    tiles = [(0, 0, "plain"), (5, 0, "village")]
    snap = _build_snap(tiles)
    unit = _stub()
    prof = _AI_PROFILES["conservative"]
    assert prof.claim_distance == 4
    result = _ai_pick_claim_target(unit, snap, prof, active_claims=set(),
                                    my_castle_xy=None)
    assert result is None


def test_claim_target_aggressive_reaches_far_village():
    tiles = [(0, 0, "plain"), (5, 0, "barracks")]
    snap = _build_snap(tiles)
    unit = _stub()
    prof = _AI_PROFILES["aggressive"]
    assert prof.claim_distance == 8
    result = _ai_pick_claim_target(unit, snap, prof, active_claims=set(),
                                    my_castle_xy=None)
    assert result == (5, 0)


def test_claim_target_picks_closer_when_score_says_so():
    tiles = [(0, 0, "plain"), (2, 0, "village"), (4, 0, "village")]
    snap = _build_snap(tiles)
    unit = _stub()
    prof = _AI_PROFILES["balanced"]
    result = _ai_pick_claim_target(unit, snap, prof, active_claims=set(),
                                    my_castle_xy=None)
    assert result == (2, 0)


def test_claim_target_risk_penalty_deters_conservative():
    tiles = [(0, 0, "plain"), (2, 0, "village")]
    enemy = _stub_enemy(2, 1)
    snap = _build_snap(tiles, [enemy])
    unit = _stub()
    a = _ai_pick_claim_target(unit, snap, _AI_PROFILES["aggressive"],
                              active_claims=set(), my_castle_xy=None)
    c = _ai_pick_claim_target(unit, snap, _AI_PROFILES["conservative"],
                              active_claims=set(), my_castle_xy=None)
    assert a == (2, 0)
    assert c is None


def test_claim_emergency_bonus_overrides_distance_skepticism():
    tiles = [(0, 0, "plain"), (5, 0, "village")]
    enemy = _stub_enemy(5, 0)
    snap = _build_snap(tiles, [enemy])
    unit = _stub()
    c = _ai_pick_claim_target(
        unit, snap, _AI_PROFILES["conservative"],
        active_claims={(5, 0)}, my_castle_xy=None,
    )
    assert c == (5, 0)


def test_claim_emergency_bonus_graduates_across_profiles():
    a = _AI_PROFILES["aggressive"]
    b = _AI_PROFILES["balanced"]
    c = _AI_PROFILES["conservative"]
    assert a.claim_emergency_bonus > b.claim_emergency_bonus > c.claim_emergency_bonus
    assert (a.claim_emergency_bonus, b.claim_emergency_bonus, c.claim_emergency_bonus) == (200, 175, 150)


def test_castle_pull_graduates_high_across_all_profiles():
    assert _AI_PROFILES["aggressive"].castle_pull == 400
    assert _AI_PROFILES["balanced"].castle_pull == 300
    assert _AI_PROFILES["conservative"].castle_pull == 250
    for prof in _AI_PROFILES.values():
        assert prof.castle_pull >= 250


# ============================================================
# Attack target — aggression scaling
# ============================================================

def _build_snap_with_enemy_at(unit_xy, enemy_xy, *, enemy_hp=30, enemy_atk=10):
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


# ============================================================
# E2E: add-ai stores personality on Player
# ============================================================

@pytest.mark.asyncio
async def test_add_ai_stores_personality_on_player(db_session):
    """POST /games/{id}/add-ai with personality=aggressive should
    store agent_personality on the new Player row. The lobby GET
    should return it back."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # Create a game + host.
        r = await c.post("/games", json={
            "name": "personality-test", "map_preset": "classic",
        })
        gid = r.json()["id"]
        await c.post(f"/games/{gid}/join", json={"user_name": "host"})

        # Add an AI with each personality; verify it sticks.
        for pers in ("aggressive", "balanced", "conservative"):
            r = await c.post(f"/games/{gid}/add-ai", json={
                "difficulty": "normal",
                "agent_kind": "rules",
                "personality": pers,
            })
            assert r.status_code == 201, r.text
            assert r.json()["agent_personality"] == pers

        # 3 AI players all stored with their chosen personality.
        # Use /state since /lobby returns a team-aggregated view.
        state = (await c.get(f"/games/{gid}/state")).json()
        ai_personalities = [
            p["agent_personality"] for p in state["players"] if p["is_ai"]
        ]
        assert ai_personalities == ["aggressive", "balanced", "conservative"]


@pytest.mark.asyncio
async def test_add_ai_defaults_to_balanced_when_omitted(db_session):
    """If the request doesn't include `personality`, the AI gets balanced."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/games", json={
            "name": "personality-default", "map_preset": "classic",
        })
        gid = r.json()["id"]
        await c.post(f"/games/{gid}/join", json={"user_name": "host"})
        # No personality field.
        r = await c.post(f"/games/{gid}/add-ai", json={
            "difficulty": "normal",
            "agent_kind": "rules",
        })
        assert r.status_code == 201
        assert r.json()["agent_personality"] == "balanced"
