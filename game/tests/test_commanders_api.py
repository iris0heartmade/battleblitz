"""HTTP/API contracts for commander selection and CO Power."""

from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from types import SimpleNamespace

import pytest

from app.commanders.actions import can_player_fire_now
from app.main import app
from app.schemas import BattleConfig


client = TestClient(app)


@pytest.fixture
async def commander_client():
    from app.database import AsyncSessionLocal, Base, dispose_db, engine, init_db

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await init_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, AsyncSessionLocal
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await dispose_db()


def test_battle_config_accepts_commander_assignments():
    config = BattleConfig(commander="yun", ai_commanders={1: "anna"})
    assert config.commander == "yun"
    assert config.ai_commanders == {1: "anna"}


def test_commander_routes_are_registered_and_require_identity():
    assert client.get("/players/me/commanders").status_code == 401
    response = client.post(
        "/mainlines/chapter_01_steel_rebellion/select-commander",
        json={"commander_id": "yun"},
    )
    assert response.status_code == 401


def test_unknown_commander_is_rejected_before_database_lookup():
    response = client.post(
        "/mainlines/chapter_01_steel_rebellion/select-commander",
        json={"user_name": "nobody", "commander_id": "ghost"},
    )
    assert response.status_code == 422


def test_battle_selection_is_locked():
    response = client.post(
        "/games/999/select-commander",
        json={"player_id": 1, "commander_id": "yun"},
    )
    assert response.status_code == 409


def test_co_power_body_rejects_unknown_fields():
    response = client.post("/games/1/co-power", json={"foo": "bar"})
    assert response.status_code == 422


def test_can_player_fire_now_checks_turn_owner():
    class Player:
        seat = 2
        is_alive = True
        is_ai = False
        is_spectator = False

    class Game:
        current_player_index = 2
        status = "playing"

    player = Player()
    assert can_player_fire_now(player, Game(), [player]) is True
    Game.current_player_index = 1
    current = SimpleNamespace(seat=1, is_alive=True, is_ai=False, is_spectator=False)
    assert can_player_fire_now(player, Game(), [current, player]) is False


def test_current_player_resolution_handles_dead_seat_holes_and_wrap():
    players = [
        SimpleNamespace(id=1, seat=0, is_alive=False, is_ai=False, is_spectator=False),
        SimpleNamespace(id=2, seat=2, is_alive=True, is_ai=False, is_spectator=False),
        SimpleNamespace(id=3, seat=5, is_alive=True, is_ai=False, is_spectator=False),
    ]
    game = SimpleNamespace(status="playing", current_player_index=1)
    assert can_player_fire_now(players[1], game, players) is True
    game.current_player_index = 6
    assert can_player_fire_now(players[0], game, players) is False
    assert can_player_fire_now(players[1], game, players) is True


def test_fire_co_power_requires_player_id_contract():
    operation = app.openapi()["paths"]["/games/{game_id}/co-power"]["post"]
    schema = operation["requestBody"]["content"]["application/json"]["schema"]
    model_ref = next(item["$ref"] for item in schema.get("anyOf", [schema]) if "$ref" in item)
    body_schema = app.openapi()["components"]["schemas"][model_ref.split("/")[-1]]
    assert body_schema.get("required", []) == ["player_id"]
    assert operation["requestBody"].get("required", False) is True


@pytest.mark.integration
async def test_fire_co_power_rejects_completely_absent_body(commander_client):
    c, _ = commander_client
    response = await c.post("/games/999999/co-power")
    assert response.status_code == 422


@pytest.mark.integration
async def test_free_mode_battle_config_commander_spawns_on_host(commander_client):
    from sqlalchemy import select
    from app.models import Player, Tile, Unit

    c, sessions = commander_client
    created = await c.post("/games", json={
        "name": "free commander",
        "map_preset": "balanced_2p_15",
        "mode": "free",
        "battle_config": {"commander": "anna"},
    })
    assert created.status_code == 201, created.text
    game_id = created.json()["id"]

    joined_host = await c.post(f"/games/{game_id}/join", json={"user_name": "host"})
    assert joined_host.status_code == 201, joined_host.text
    joined_guest = await c.post(f"/games/{game_id}/join", json={"user_name": "guest"})
    assert joined_guest.status_code == 201, joined_guest.text

    started = await c.post(f"/games/{game_id}/start")
    assert started.status_code == 200, started.text

    async with sessions() as session:
        host = await session.scalar(
            select(Player).where(Player.game_id == game_id, Player.seat == 0)
        )
        guest = await session.scalar(
            select(Player).where(Player.game_id == game_id, Player.seat == 1)
        )
        assert host.commander_id == "anna"
        assert host.co_state["commander_id"] == "anna"
        # 新机制:anna 阈值 14
        assert host.co_state["threshold"] == 14
        assert guest.commander_id is None
        host_hq = await session.scalar(
            select(Tile).where(
                Tile.game_id == game_id,
                Tile.owner_id == host.id,
                Tile.terrain == "castle",
            )
        )
        assert host_hq is not None
        hq_unit = await session.scalar(
            select(Unit).where(
                Unit.player_id == host.id,
                Unit.x == host_hq.x,
                Unit.y == host_hq.y,
            )
        )
        assert hq_unit is not None
        assert hq_unit.unit_type == "healer"
        assert hq_unit.hero_id == "anna"


@pytest.mark.integration
async def test_free_mode_empty_commander_spawns_dragon_rider_on_hq(commander_client):
    from sqlalchemy import select
    from app.models import Player, Tile, Unit

    c, sessions = commander_client
    created = await c.post("/games", json={
        "name": "free empty commander",
        "map_preset": "balanced_2p_15",
        "mode": "free",
    })
    assert created.status_code == 201, created.text
    game_id = created.json()["id"]

    joined_host = await c.post(f"/games/{game_id}/join", json={"user_name": "host"})
    assert joined_host.status_code == 201, joined_host.text
    joined_guest = await c.post(f"/games/{game_id}/join", json={"user_name": "guest"})
    assert joined_guest.status_code == 201, joined_guest.text

    started = await c.post(f"/games/{game_id}/start")
    assert started.status_code == 200, started.text

    async with sessions() as session:
        host = await session.scalar(
            select(Player).where(Player.game_id == game_id, Player.seat == 0)
        )
        host_hq = await session.scalar(
            select(Tile).where(
                Tile.game_id == game_id,
                Tile.owner_id == host.id,
                Tile.terrain == "castle",
            )
        )
        assert host_hq is not None
        hq_unit = await session.scalar(
            select(Unit).where(
                Unit.player_id == host.id,
                Unit.x == host_hq.x,
                Unit.y == host_hq.y,
            )
        )
        assert hq_unit is not None
        assert hq_unit.unit_type == "dragon_rider"
        assert hq_unit.hero_id is None


@pytest.mark.integration
async def test_free_mode_seat_commanders_spawn_on_human_and_ai_hqs(commander_client):
    from sqlalchemy import select
    from app.models import Player, Tile, Unit

    c, sessions = commander_client
    created = await c.post("/games", json={
        "name": "free seat commanders",
        "map_preset": "balanced_2p_15",
        "mode": "free",
        "battle_config": {"seat_commanders": {"0": "yun", "1": "anna"}},
    })
    assert created.status_code == 201, created.text
    game_id = created.json()["id"]

    joined_host = await c.post(f"/games/{game_id}/join", json={"user_name": "host"})
    assert joined_host.status_code == 201, joined_host.text
    ai = await c.post(f"/games/{game_id}/add-ai", json={})
    assert ai.status_code == 201, ai.text

    started = await c.post(f"/games/{game_id}/start")
    assert started.status_code == 200, started.text

    async with sessions() as session:
        players = (await session.scalars(
            select(Player).where(Player.game_id == game_id)
        )).all()
        by_seat = {p.seat: p for p in players}
        assert by_seat[0].commander_id == "yun"
        assert by_seat[1].commander_id == "anna"

        for seat, expected_type, expected_hero in [
            (0, "warlock", "yun"),
            (1, "healer", "anna"),
        ]:
            player = by_seat[seat]
            hq = await session.scalar(
                select(Tile).where(
                    Tile.game_id == game_id,
                    Tile.owner_id == player.id,
                    Tile.terrain == "castle",
                )
            )
            assert hq is not None
            hq_unit = await session.scalar(
                select(Unit).where(
                    Unit.player_id == player.id,
                    Unit.x == hq.x,
                    Unit.y == hq.y,
                )
            )
            assert hq_unit is not None
            assert hq_unit.unit_type == expected_type
            assert hq_unit.hero_id == expected_hero


def test_profile_has_prebattle_commander_selection_field():
    from app.progression.models import PlayerProfile

    assert "mainline_commanders" in PlayerProfile.__table__.columns


@pytest.mark.integration
async def test_prebattle_selection_is_isolated_consumed_and_locked(commander_client):
    c, sessions = commander_client
    from sqlalchemy import select
    from app.progression.models import PlayerProfile
    from app.models import Player, Unit

    for name in ("alice", "bob"):
        response = await c.post("/progression/profiles", json={"user_name": name})
        assert response.status_code == 201
    async with sessions() as session:
        profiles = (await session.scalars(select(PlayerProfile))).all()
        for profile in profiles:
            profile.unlocked_classes = ["swordsman", "archer", "healer"]
            profile.unlocked_commanders = ["yun"]
        await session.commit()

    selected = await c.post(
        "/mainlines/chapter_01_steel_rebellion/select-commander",
        json={"user_name": "alice", "commander_id": "yun"},
    )
    assert selected.status_code == 200, selected.text
    async with sessions() as session:
        alice = await session.scalar(select(PlayerProfile).where(PlayerProfile.user_name == "alice"))
        bob = await session.scalar(select(PlayerProfile).where(PlayerProfile.user_name == "bob"))
        assert alice.mainline_commanders == {"chapter_01_steel_rebellion": "yun"}
        assert bob.mainline_commanders == {}

    started = await c.post(
        "/mainlines/chapter_01_steel_rebellion/start",
        json={"user_name": "alice", "skip_intro": True},
    )
    assert started.status_code == 201, started.text
    async with sessions() as session:
        spawned = await session.get(Player, started.json()["player_id"])
        assert spawned.commander_id == "yun"
        # 新机制:yun 阈值 18,power_cost 6;stars_earned_total=18 可放
        spawned.co_state = {**spawned.co_state, "stars_earned_total": 18,
                            "threshold": 18, "power_cost": 6}
        unit = await session.scalar(select(Unit).where(Unit.player_id == spawned.id).order_by(Unit.id))
        atk_before = unit.atk
        await session.commit()

    fired = await c.post(
        f"/games/{started.json()['game_id']}/co-power",
        json={"player_id": started.json()["player_id"]},
    )
    assert fired.status_code == 200, fired.text
    async with sessions() as session:
        spawned = await session.get(Player, started.json()["player_id"])
        assert spawned.co_state["meter"] == 0
        assert spawned.co_state["is_power_active"] is True
        unit = await session.scalar(select(Unit).where(Unit.player_id == spawned.id).order_by(Unit.id))
        assert unit.atk > atk_before

    locked = await c.post(
        "/mainlines/chapter_01_steel_rebellion/select-commander",
        json={"user_name": "alice", "commander_id": None},
    )
    assert locked.status_code == 409


@pytest.mark.integration
async def test_concurrent_co_power_requests_only_fire_once(commander_client):
    import asyncio
    from sqlalchemy import select
    from app.models import Player

    c, sessions = commander_client
    await c.post("/progression/profiles", json={"user_name": "alice"})
    async with sessions() as session:
        from app.progression.models import PlayerProfile
        profile = await session.scalar(select(PlayerProfile).where(PlayerProfile.user_name == "alice"))
        profile.unlocked_classes = ["swordsman", "archer", "healer"]
        profile.unlocked_commanders = ["yun"]
        await session.commit()
    await c.post(
        "/mainlines/chapter_01_steel_rebellion/select-commander",
        json={"user_name": "alice", "commander_id": "yun"},
    )
    started = (await c.post(
        "/mainlines/chapter_01_steel_rebellion/start",
        json={"user_name": "alice", "skip_intro": True},
    )).json()
    async with sessions() as session:
        player = await session.get(Player, started["player_id"])
        # 新机制:yun stars_earned_total=18 / threshold=18 / power_cost=6
        player.co_state = {**player.co_state, "stars_earned_total": 18,
                           "threshold": 18, "power_cost": 6}
        await session.commit()

    url = f"/games/{started['game_id']}/co-power"
    payload = {"player_id": started["player_id"]}
    responses = await asyncio.gather(c.post(url, json=payload), c.post(url, json=payload))

    assert sorted(response.status_code for response in responses) == [200, 422]
    async with sessions() as session:
        player = await session.get(Player, started["player_id"])
        assert player.co_state["meter"] == 0


@pytest.mark.integration
@pytest.mark.parametrize("historical_status", ["finished", "abandoned"])
async def test_historical_mainline_game_does_not_lock_new_selection(
    commander_client, historical_status
):
    c, sessions = commander_client
    from sqlalchemy import select
    from app.models import Game, Player
    from app.progression.models import PlayerProfile

    await c.post("/progression/profiles", json={"user_name": "alice"})
    async with sessions() as session:
        profile = await session.scalar(select(PlayerProfile).where(PlayerProfile.user_name == "alice"))
        profile.unlocked_commanders = ["yun"]
        profile.active_mainline = None
        game = Game(
            name="mainline:chapter_01_steel_rebellion:battle_old",
            status=historical_status,
            map_seed=1,
        )
        session.add(game)
        await session.flush()
        session.add(Player(game_id=game.id, user_name="alice", color="red", seat=0))
        await session.commit()

    response = await c.post(
        "/mainlines/chapter_01_steel_rebellion/select-commander",
        json={"user_name": "alice", "commander_id": "yun"},
    )
    assert response.status_code == 200, response.text
