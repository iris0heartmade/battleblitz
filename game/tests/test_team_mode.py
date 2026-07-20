"""End-to-end tests for P2.3 team mode + lobby endpoint.

Covers:
- POST /games/{id}/join with `team` param -> player gets that team_id
- POST /games/{id}/join without team -> falls back to color
- GET /games/{id}/lobby aggregates players by team and reports
  per-team counts
- 2v2 team mode: 2 players share "red", 2 share "blue"
- Win condition aggregates by team: rout + seize trigger per team
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app


# ============================================================
# Join endpoint — team param
# ============================================================

@pytest.mark.asyncio
async def test_join_with_explicit_team_assigns_team_id(db_session, tmp_db_path):
    """POST /join with `team="red"` stores team_id = "red" on the
    Player row even when the joiner's color would have been "blue"."""
    from app.models import Game, Player
    from app.database import AsyncSessionLocal

    game = Game(
        name="team-test", status="waiting", map_seed=0,
        map_preset="classic", current_player_index=0, phase="player",
    )
    db_session.add(game)
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(f"/games/{game.id}/join", json={
            "user_name": "Alice", "color": "blue", "team": "red",
        })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["color"] == "blue"
    assert body["team"] == "red"


@pytest.mark.asyncio
async def test_join_without_team_falls_back_to_color(db_session, tmp_db_path):
    from app.models import Game
    from app.database import AsyncSessionLocal

    game = Game(
        name="no-team", status="waiting", map_seed=0,
        map_preset="classic", current_player_index=0, phase="player",
    )
    db_session.add(game)
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(f"/games/{game.id}/join", json={
            "user_name": "Bob", "color": "green",
        })
    assert r.status_code == 201
    body = r.json()
    assert body["color"] == "green"
    # 1V1 default: no team_id set; _team_of falls back to player_<id>
    # at win-condition time, so the persisted value is None.
    assert body["team"] is None


# ============================================================
# Lobby endpoint — team aggregation
# ============================================================

@pytest.mark.asyncio
async def test_lobby_aggregates_by_team(db_session, tmp_db_path):
    """4-player 2v2: 2 red + 2 blue. Lobby should report 2 teams."""
    from app.models import Game
    from app.database import AsyncSessionLocal

    game = Game(
        name="lobby-2v2", status="waiting", map_seed=0,
        map_preset="classic", current_player_index=0, phase="player",
    )
    db_session.add(game)
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # Each team gets 2 members; their colors are allocated
        # automatically (the (game_id, color) UNIQUE constraint
        # means the second member of a team gets the next free
        # colour, not the team's literal name).
        for name, team in [
            ("A1", "red"),
            ("A2", "red"),
            ("B1", "blue"),
            ("B2", "blue"),
        ]:
            r = await c.post(f"/games/{game.id}/join", json={
                "user_name": name, "team": team,
            })
            assert r.status_code == 201, r.text

        r = await c.get(f"/games/{game.id}/lobby")
    assert r.status_code == 200
    body = r.json()
    assert body["game_id"] == game.id
    assert body["player_count"] == 4
    assert body["status"] == "waiting"
    # 2 teams (red + blue), each with 2 players.
    teams_by_name = {t["team"]: t for t in body["teams"]}
    assert set(teams_by_name) == {"red", "blue"}
    assert teams_by_name["red"]["player_count"] == 2
    assert teams_by_name["blue"]["player_count"] == 2
    # The lobby reports the most-common color on each team.
    # A1=A2=red -> red.  B1=blue, B2=green (next free) -> blue.
    assert teams_by_name["red"]["color"] == "red"
    # Blue team has B1 and B2; B1 took the next free colour after
    # red/blue were used (green), B2 took yellow. The lobby reports
    # the most-common colour — but with one each, dict insertion
    # order breaks the tie. We just assert that the reported colour
    # is one of the team's two members' colours.
    assert teams_by_name["blue"]["color"] in ("green", "yellow")


@pytest.mark.asyncio
async def test_lobby_no_team_fallback_uses_color_per_player(db_session, tmp_db_path):
    """When no team is set, each player is their own team in the
    lobby view (1V1 free-for-all)."""
    from app.models import Game
    from app.database import AsyncSessionLocal

    game = Game(
        name="1v1", status="waiting", map_seed=0,
        map_preset="classic", current_player_index=0, phase="player",
    )
    db_session.add(game)
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.post(f"/games/{game.id}/join", json={"user_name": "R", "color": "red"})
        await c.post(f"/games/{game.id}/join", json={"user_name": "B", "color": "blue"})
        r = await c.get(f"/games/{game.id}/lobby")
    body = r.json()
    assert body["player_count"] == 2
    teams = {t["team"] for t in body["teams"]}
    # Each player is their own team — 2 entries with player_NN IDs.
    assert len(teams) == 2
    assert all(t.startswith("player_") for t in teams)


@pytest.mark.asyncio
async def test_lobby_404_for_missing_game(db_session, tmp_db_path):
    from app.database import AsyncSessionLocal

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/games/99999/lobby")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_join_can_request_open_seat_and_host_still_controls_lobby(db_session, tmp_db_path):
    """The creator may sit in a non-zero color seat without losing host powers."""
    from app.models import Game, Player

    game = Game(
        name="seat-choice", status="waiting", map_seed=0,
        map_preset="classic", current_player_index=0, phase="player",
    )
    db_session.add(game)
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        host = await c.post(f"/games/{game.id}/join", json={
            "user_name": "Host", "color": "green", "team": "team_a", "seat": 2,
        })
        assert host.status_code == 201, host.text
        guest = await c.post(f"/games/{game.id}/join", json={
            "user_name": "Guest", "team": "team_b",
        })
        assert guest.status_code == 201, guest.text

        host_body = host.json()
        guest_body = guest.json()
        assert host_body["seat"] == 2
        assert host_body["color"] == "green"

        update = await c.patch(
            f"/games/{game.id}/players/{guest_body['id']}/team",
            json={"caller_player_id": host_body["id"], "team": "team_c"},
        )
        assert update.status_code == 200, update.text

    guest_row = await db_session.get(Player, guest_body["id"])
    assert guest_row.team_id == "team_c"


@pytest.mark.asyncio
async def test_update_player_seat_swaps_players_for_host(db_session, tmp_db_path):
    from app.models import Game

    game = Game(
        name="seat-swap", status="waiting", map_seed=0,
        map_preset="classic", current_player_index=0, phase="player",
    )
    db_session.add(game)
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        host = (await c.post(f"/games/{game.id}/join", json={
            "user_name": "Host", "seat": 0, "color": "red",
        })).json()
        guest = (await c.post(f"/games/{game.id}/join", json={
            "user_name": "Guest", "seat": 1, "color": "blue",
        })).json()

        swap = await c.patch(
            f"/games/{game.id}/players/{guest['id']}/seat",
            json={"caller_player_id": host["id"], "seat": 0},
        )
        assert swap.status_code == 200, swap.text
        state = swap.json()
        seats = {p["user_name"]: p["seat"] for p in state["players"]}
        colors = {p["user_name"]: p["color"] for p in state["players"]}
        assert seats == {"Host": 1, "Guest": 0}
        assert colors == {"Host": "blue", "Guest": "red"}


# ============================================================
# End-to-end: 2v2 seize mode via the API
# ============================================================

@pytest.mark.asyncio
async def test_2v2_seize_winner_is_correct_team(db_session, tmp_db_path):
    """2v2 seize flow via the API: a blue team player claims a red
    HQ tile, the red team wipes out, and the game ends with
    win_reason='seize' and the winning team = blue."""
    from app.config import CLAIM_TURNS_REQUIRED, TERRAIN_CASTLE
    from app.models import Game, Player, ClaimSession, Tile, Unit
    from app.database import AsyncSessionLocal
    from app.game_logic import check_pending_claims

    game = Game(
        name="2v2-seize", status="waiting", map_seed=0,
        map_preset="classic", current_player_index=0, phase="player",
        win_condition="seize",
    )
    db_session.add(game)
    await db_session.commit()
    # The game_id we need for HTTP calls — must be captured
    # BEFORE we exit the db_session block.
    gid = game.id
    # 4 players: 2 red, 2 blue. We let the server allocate colors
    # so the (game_id, color) UNIQUE constraint isn't violated.
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        player_ids = []
        for name, team in [("R1", "red"), ("R2", "red"), ("B1", "blue"), ("B2", "blue")]:
            r = await c.post(f"/games/{gid}/join", json={
                "user_name": name, "team": team,
            })
            assert r.status_code == 201, r.text
            player_ids.append(r.json()["id"])
        # Reload the players from the DB.
        players = (await db_session.execute(
            select(Player).where(Player.id.in_(player_ids)).order_by(Player.id)
        )).scalars().all()
        # Flip to playing now that the lobby is full.
        game.status = "playing"
        await db_session.commit()
    # Red HQ at (0, 0).
    red_hq = Tile(
        game_id=game.id, x=0, y=0, terrain=TERRAIN_CASTLE,
        owner_id=players[0].id,
    )
    db_session.add(red_hq)
    await db_session.flush()
    # Each red player has 1 unit far from the HQ. B1 has a unit ON
    # the red HQ ready to claim.
    red_units = []
    for i, p in enumerate(players[:2]):
        u = Unit(
            player_id=p.id, unit_type="swordsman", name=f"R{i+1}",
            level=1, exp=0, hp=45, max_hp=45,
            atk=18, def_=12, matk=4, mdef=4,
            mov=5, mp=5, morale=0,
            x=5 + i, y=5 + i, has_acted=False, has_moved=False, skills=[],
        )
        db_session.add(u)
        await db_session.flush()
        red_units.append(u)
    b1_unit = Unit(
        player_id=players[2].id, unit_type="swordsman", name="B1",
        level=1, exp=0, hp=45, max_hp=45,
        atk=18, def_=12, matk=4, mdef=4,
        mov=5, mp=5, morale=0,
        x=0, y=0, has_acted=False, has_moved=False, skills=[],
    )
    db_session.add(b1_unit)
    await db_session.flush()
    b2_unit = Unit(
        player_id=players[3].id, unit_type="swordsman", name="B2",
        level=1, exp=0, hp=45, max_hp=45,
        atk=18, def_=12, matk=4, mdef=4,
        mov=5, mp=5, morale=0,
        x=9, y=9, has_acted=False, has_moved=False, skills=[],
    )
    db_session.add(b2_unit)
    await db_session.flush()
    # A claim session that finalises NOW.
    cs = ClaimSession(
        game_id=game.id, tile_id=red_hq.id, unit_id=b1_unit.id,
        target_player_id=players[2].id,
        started_turn=1, completes_turn=game.turn_number,
    )
    db_session.add(cs)
    # The red HQ is captured + the red team's last unit is wiped.
    red_units[0].hp = 0
    red_units[1].hp = 0
    await db_session.flush()

    # Resolve the claim (this is what turns.py does after end_turn).
    flipped = await check_pending_claims(db_session, game)
    await db_session.flush()
    assert red_hq.id in flipped
    # Seize should fire: blue team wins.
    assert game.status == "finished"
    assert game.win_reason == "seize"
    # The win banner should mention blue (the winning team).
    from sqlalchemy import select as _sel
    from app.models import ActionLog
    log = (await db_session.execute(
        _sel(ActionLog).where(
            ActionLog.game_id == game.id,
            ActionLog.action_type == "victory",
        )
    )).scalars().first()
    assert log is not None
    assert "blue" in log.description


@pytest.mark.asyncio
async def test_2v2_team_survives_until_all_member_factions_are_defeated(db_session, tmp_db_path):
    """A 2-player team is not defeated by losing only one member HQ."""
    from app.config import TERRAIN_CASTLE
    from app.models import Game, Player, ClaimSession, Tile, Unit
    from app.game_logic import check_pending_claims, check_win_condition

    game = Game(
        name="2v2-mixed-defeat", status="playing", map_seed=0,
        map_preset="classic", current_player_index=0, phase="player",
        win_condition="rout",
    )
    db_session.add(game)
    await db_session.flush()
    players = []
    for seat, (name, color, team) in enumerate([
        ("A-red", "red", "team_a"),
        ("A-green", "green", "team_a"),
        ("B-blue", "blue", "team_b"),
        ("B-yellow", "yellow", "team_b"),
    ]):
        p = Player(
            game_id=game.id, user_name=name, color=color, seat=seat,
            team_id=team, is_alive=True, has_ended_turn=False,
        )
        db_session.add(p)
        await db_session.flush()
        players.append(p)

    blue_hq = Tile(game_id=game.id, x=5, y=5, terrain=TERRAIN_CASTLE, owner_id=players[2].id)
    yellow_hq = Tile(game_id=game.id, x=8, y=8, terrain=TERRAIN_CASTLE, owner_id=players[3].id)
    db_session.add_all([blue_hq, yellow_hq])
    await db_session.flush()

    red_unit = Unit(player_id=players[0].id, unit_type="swordsman", name="capturer",
                    level=1, exp=0, hp=45, max_hp=45, atk=18, def_=12, matk=4, mdef=4,
                    mov=5, mp=5, morale=0, x=5, y=5, has_acted=False, has_moved=False, skills=[])
    green_unit = Unit(player_id=players[1].id, unit_type="swordsman", name="ally",
                      level=1, exp=0, hp=45, max_hp=45, atk=18, def_=12, matk=4, mdef=4,
                      mov=5, mp=5, morale=0, x=0, y=1, has_acted=False, has_moved=False, skills=[])
    blue_unit = Unit(player_id=players[2].id, unit_type="swordsman", name="blue",
                     level=1, exp=0, hp=45, max_hp=45, atk=18, def_=12, matk=4, mdef=4,
                     mov=5, mp=5, morale=0, x=4, y=4, has_acted=False, has_moved=False, skills=[])
    yellow_unit = Unit(player_id=players[3].id, unit_type="swordsman", name="yellow",
                       level=1, exp=0, hp=45, max_hp=45, atk=18, def_=12, matk=4, mdef=4,
                       mov=5, mp=5, morale=0, x=9, y=9, has_acted=False, has_moved=False, skills=[])
    db_session.add_all([red_unit, green_unit, blue_unit, yellow_unit])
    await db_session.flush()

    db_session.add(ClaimSession(
        game_id=game.id, tile_id=blue_hq.id, unit_id=red_unit.id,
        target_player_id=players[0].id, started_turn=1, completes_turn=game.turn_number,
    ))
    blue_unit.hp = 0
    await db_session.flush()

    flipped = await check_pending_claims(db_session, game)
    await db_session.flush()
    assert blue_hq.id in flipped
    assert game.status == "playing"
    assert game.win_reason is None

    yellow_unit.hp = 0
    await db_session.flush()
    ended = await check_win_condition(db_session, game)
    assert ended is True
    assert game.status == "finished"
    assert game.win_reason == "rout"
