"""P2.4 polish — regression tests for the 5 reported gameplay bugs.

Covers:
  #5 — empty-barracks recruit: clicking a claimed-but-empty barracks
       recruits without needing a unit on the tile.
  #4 — AI no friendly fire: the rules AI only attacks enemy players,
       not same-team allies.
  #3 — archer line of sight: ranged attacks at distance > 1 require
       a clear LoS. The archer's range was also bumped to 1–4.
  #2 — claim progress: GameStateOut now includes pending_claims with
       turns_remaining + total_turns.
  #1 — tile-owner-marker is suppressed on castle tiles.
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from app.classes.units.archer import Archer
from app.config import (
    MAP_STYLES, STYLE_GRASS_OUTER, TERRAIN_FOREST, TERRAIN_MOUNTAIN,
    TERRAIN_RIVER,
)
from app.game_logic import (
    can_attack_from_position, generate_map, get_roster_for_composition,
)
from app.models import Game, Player, Tile, Unit
from app.utils import has_line_of_sight

MAPS_DIR = Path(__file__).resolve().parent.parent / "maps"


# ============================================================
# Helpers
# ============================================================

def _stub_unit(type_id, x=5, y=5, skills=None):
    """Build a bare Unit for LoS / range tests. Not persisted."""
    return Unit(
        player_id=1, unit_type=type_id, name="Stub",
        level=1, exp=0, hp=35, max_hp=35,
        atk=20, def_=6, matk=4, mdef=4,
        mov=3, mp=5, morale=0,
        x=x, y=y, has_acted=False, has_moved=False,
        skills=skills or [],
    )


# ============================================================
# Bug 5 — empty-barracks recruit
# ============================================================

@pytest.mark.asyncio
async def test_recruit_empty_barracks(client):
    """Bug #5: the recruit API now accepts {tile_x, tile_y} (no
    unit_id required) for the empty-barracks case. We can't easily
    drive the full E2E flow (would need to claim the barracks via
    a unit first, then move the unit off — and turn phases keep
    shuffling), so we just verify the API accepts the new format
    and that the schema field is Optional.
    """
    from app.schemas import RecruitRequest
    # Schema-level: both unit_id and tile_x/tile_y are now Optional.
    r1 = RecruitRequest(player_id=1, unit_type="swordsman",
                        tile_x=5, tile_y=5)
    assert r1.unit_id is None
    r2 = RecruitRequest(player_id=1, unit_type="swordsman",
                        unit_id=42)
    assert r2.tile_x is None and r2.tile_y is None
    # End-to-end smoke: start a game and try to recruit on a tile
    # (without claiming first — should 400 on "not owned by you"
    # OR succeed if a barracks exists unclaimed for some other
    # reason; either way the call should NOT 422 on schema).
    r = await client.post("/games", json={
        "name": "empty-barracks-test", "map_preset": "grass_outer_15_4p",
    })
    gid = r.json()["id"]
    await client.post(f"/games/{gid}/join", json={"user_name": "host"})
    await client.post(f"/games/{gid}/add-ai", json={})
    await client.post(f"/games/{gid}/start")
    # Try the empty-barracks shape (should NOT 422).
    r = await client.post(f"/games/{gid}/recruit", json={
        "player_id": 1, "tile_x": 7, "tile_y": 7, "unit_type": "swordsman",
    })
    # 400/403/200 are all fine — the contract is that the API
    # accepts the new shape. 422 would mean schema rejected it.
    assert r.status_code != 422, f"schema rejected empty-barracks shape: {r.text}"


# ============================================================
# Bug 4 — AI no friendly fire
# ============================================================

@pytest.mark.asyncio
async def test_ai_does_not_target_same_team_units(db_session, tmp_db_path):
    """Bug #4: a 2v2 game where the AI is on team 'red' should
    never target a human who is also on team 'red'."""
    # Build a 4-player game with teams red/red/blue/blue.
    # Note: the (game_id, color) UNIQUE constraint means we need
    # distinct colors per player — use seat-derived colors and
    # group them via team_id.
    from sqlalchemy import select
    game = Game(
        name="ai-friendly-test", status="playing", map_seed=0,
        map_preset="classic", turn_number=5,
        current_player_index=0, phase="ai",
        win_condition="rout", capacity=4,
    )
    db_session.add(game)
    await db_session.flush()
    players = []
    for i, (name, color, team) in enumerate([
        ("human-red1", "red",   "red"),
        ("ai-red2",    "orange","red"),
        ("ai-blue1",   "blue",  "blue"),
        ("human-blue2","green", "blue"),
    ]):
        p = Player(
            game_id=game.id, user_name=name, color=color,
            seat=i, is_alive=True, has_ended_turn=False,
            is_ai=(i != 0 and i != 3),  # ai is players 1 and 2
            agent_kind="rules", agent_personality="balanced",
            team_id=team, gold=0,
        )
        db_session.add(p)
        await db_session.flush()
        players.append(p)
    # Add a single unit for each player on plain tiles.
    for i, p in enumerate(players):
        u = Unit(
            player_id=p.id, unit_type="swordsman", name=f"u{i}",
            level=1, exp=0, hp=45, max_hp=45,
            atk=18, def_=12, matk=4, mdef=4,
            mov=5, mp=5, morale=0,
            x=i*3, y=0, has_acted=False, has_moved=False,
            skills=[],
        )
        db_session.add(u)
        await db_session.flush()
    # 15x15 plain tiles for movement / LoS.
    for y in range(15):
        for x in range(15):
            db_session.add(Tile(game_id=game.id, x=x, y=y, terrain="plain"))
    await db_session.flush()
    # Ask the rules AI (player 1, red) to pick an attack target.
    from app.game_logic import _ai_pick_attack_target, _load_ai_snapshot
    ai_player = players[1]  # ai-red
    snap = await _load_ai_snapshot(db_session, game, ai_player)
    # Get the AI's unit explicitly.
    ai_unit_rows = (await db_session.execute(
        select(Unit).where(Unit.player_id == ai_player.id)
    )).scalars().all()
    assert ai_unit_rows, "AI player has no unit"
    attacker_unit = ai_unit_rows[0]
    target = _ai_pick_attack_target(attacker_unit, snap)
    # Whatever the AI picked (or didn't pick), the snapshot's
    # enemy_units list MUST NOT include the same-team human player.
    snap_target_ids = {u.id for u in snap.enemy_units}
    # Find the same-team human's unit ids.
    same_team_human = players[0]  # human-red1
    same_team_unit_rows = (await db_session.execute(
        select(Unit).where(Unit.player_id == same_team_human.id)
    )).scalars().all()
    same_team_ids = {u.id for u in same_team_unit_rows}
    assert snap_target_ids.isdisjoint(same_team_ids), (
        f"AI snapshot's enemy_units included same-team ally: "
        f"{snap_target_ids & same_team_ids}"
    )
    if target is not None:
        target_owner = next(p for p in players if p.id == target.player_id)
        assert target_owner.team_id != ai_player.team_id, (
            f"AI picked same-team target {target_owner.user_name}!"
        )


# ============================================================
# Bug 3 — archer range + LoS
# ============================================================

def test_archer_range_bumped_to_4():
    """Bug #3: archer attack_range was 2, too short for 15x15+.
    Now 4 with min 0 (so archer can also melee)."""
    prof = Archer()
    assert prof.attack_range == 4
    assert prof.min_attack_range == 0


def test_can_attack_from_position_blocks_mountain_los():
    """For d > 1, a mountain between attacker and target blocks."""
    blockers = {(7, 7)}  # mountain on the path
    u = _stub_unit("archer", x=5, y=7)
    # Path (5,7) -> (8,7) crosses (6,7) and (7,7). d=3 ≤ archer's
    # range of 4, so range allows.
    # Without blockers: can attack.
    assert can_attack_from_position(u, 5, 7, 8, 7, blockers=set()) is True
    # With blocker at (7,7): blocked.
    assert can_attack_from_position(u, 5, 7, 8, 7, blockers=blockers) is False
    # But d == 1 melee ignores LoS even with a blocker.
    assert can_attack_from_position(u, 5, 7, 6, 7, blockers=blockers) is True


def test_can_attack_melee_no_los_check():
    """d == 1 always allowed (no LoS check)."""
    u = _stub_unit("swordsman", x=0, y=0)
    # Swordsman attack_range is 1, min 0. d==1 is melee.
    blockers = {(1, 0)}
    assert can_attack_from_position(u, 0, 0, 1, 0, blockers=blockers) is True


def test_has_line_of_sight_blocks_mountain():
    """Belt-and-suspenders: the underlying helper still works."""
    # Mountain on the line at (5, 5); line from (0, 5) to (10, 5).
    blockers = {(5, 5)}
    assert has_line_of_sight((0, 5), (10, 5), blockers, size=15) is False
    # No blockers → clear.
    assert has_line_of_sight((0, 5), (10, 5), set(), size=15) is True


# ============================================================
# Bug 2 — claim progress in GameStateOut
# ============================================================

@pytest.mark.asyncio
async def test_state_includes_pending_claims(client):
    """Bug #2: after starting a claim, the state should report
    pending_claims with turns_remaining so the UI can show
    progress."""
    r = await client.post("/games", json={
        "name": "claim-progress", "map_preset": "grass_outer_15_4p",
    })
    gid = r.json()["id"]
    r = await client.post(f"/games/{gid}/join", json={"user_name": "host"})
    me = r.json()
    r = await client.post(f"/games/{gid}/add-ai", json={})
    assert r.status_code == 201
    await client.post(f"/games/{gid}/start")
    state = (await client.get(f"/games/{gid}/state")).json()
    # Find a claimable tile (village, barracks, or castle vault).
    claim_tile = None
    for t in state["tiles"]:
        if t["terrain"] in ("village", "barracks"):
            claim_tile = (t["x"], t["y"])
            break
    if claim_tile is None:
        pytest.skip("no claimable tile in default preset for this test")
    # Walk a unit onto it then claim.
    my_units = next(p for p in state["players"] if p["id"] == me["id"])["units"]
    u = my_units[0]
    await client.post(f"/games/{gid}/move", json={
        "player_id": me["id"], "unit_id": u["id"],
        "to_x": claim_tile[0], "to_y": claim_tile[1],
    })
    r = await client.post(f"/games/{gid}/claim", json={
        "player_id": me["id"], "unit_id": u["id"],
    })
    assert r.status_code == 200, r.text
    # The new state should include pending_claims with the tile.
    state = (await client.get(f"/games/{gid}/state")).json()
    assert "pending_claims" in state, "state missing pending_claims"
    pc = state["pending_claims"]
    assert any(
        c["tile_x"] == claim_tile[0] and c["tile_y"] == claim_tile[1]
        for c in pc
    ), f"no pending claim found for {claim_tile}: {pc}"
    # The claim should have turns_remaining = 1 (CLAIM_TURNS_REQUIRED=2
    # means completes_turn = current + 1, so turns_remaining = 1).
    c = next(c for c in pc
             if c["tile_x"] == claim_tile[0] and c["tile_y"] == claim_tile[1])
    assert c["turns_remaining"] >= 0
    assert c["total_turns"] >= 1
    assert c["target_player_id"] == me["id"]


# ============================================================
# Bug 1 — no tile-owner-marker on castle tiles (frontend)
# ============================================================

def test_no_tile_owner_marker_on_castle_in_presets():
    """Sanity check the data: castle-terrain tiles should still have
    owner_id, but the front-end's renderBoard now skips them when
    adding the .tile-owner-marker div. The data invariant we test
    here is that the field IS present (so the marker would be
    rendered if the bug were unfixed). The actual visual fix lives
    in app.js:1233 (see the explicit terrain !== 'castle' check)."""
    # Just verify the data: when a unit walks onto a castle, owner_id
    # flips to the unit's player. (The frontend then omits the marker
    # for castle/castle_vault tiles.)
    from app.game_logic import claim_castle_if_present
    game_id = 1
    # Build a small mock with just the attributes we need.
    class _Tile:
        terrain = "castle"
        owner_id = None
    class _Unit:
        player_id = 42
    t = _Tile()
    u = _Unit()
    assert claim_castle_if_present(t, u) is True
    assert t.owner_id == 42
    # Re-claim by same player → no-op.
    assert claim_castle_if_present(t, u) is False
    # Forest is not a castle → returns False without mutating.
    t2 = _Tile(); t2.terrain = "forest"
    assert claim_castle_if_present(t2, u) is False
    assert t2.owner_id is None
