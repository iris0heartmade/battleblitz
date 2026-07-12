"""Contracts for commander state exposed by the real game-state endpoint."""

import pytest
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Player
from app.schemas import GameStateOut, PlayerCOStateOut


def test_player_co_state_out_fields_and_defaults():
    state = PlayerCOStateOut(
        player_id=1,
        seat=0,
        color="red",
        commander_id="yun",
    )

    assert state.model_dump() == {
        "player_id": 1,
        "seat": 0,
        "color": "red",
        "commander_id": "yun",
        "meter": 0,
        "threshold": 20,
        "is_power_active": False,
        "can_fire": False,
    }


def test_game_state_out_has_independent_co_states_default():
    assert "co_states" in GameStateOut.model_fields
    assert GameStateOut.model_fields["co_states"].default_factory() == []


@pytest.mark.integration
async def test_state_endpoint_exposes_ordered_public_co_states(client):
    game = (await client.post("/games", json={"name": "CO HUD"})).json()
    game_id = game["id"]
    await client.post(f"/games/{game_id}/join", json={"user_name": "first"})
    await client.post(f"/games/{game_id}/join", json={"user_name": "second"})

    async with AsyncSessionLocal() as session:
        players = (
            await session.execute(
                select(Player)
                .where(Player.game_id == game_id)
                .order_by(Player.seat)
            )
        ).scalars().all()
        players[0].commander_id = "yun"
        players[0].co_state = {
            "meter": 22,
            "threshold": 22,
            "is_power_active": False,
            "_power_baselines": {"99": {"atk": 10}},
        }
        players[1].commander_id = "anna"
        players[1].co_state = {"is_power_active": True}
        await session.commit()
        expected_ids = [player.id for player in players]

    response = await client.get(f"/games/{game_id}/state")
    assert response.status_code == 200
    co_states = response.json()["co_states"]

    assert [state["player_id"] for state in co_states] == expected_ids
    assert co_states[0] == {
        "player_id": expected_ids[0],
        "seat": 0,
        "color": "red",
        "commander_id": "yun",
        "meter": 22,
        "threshold": 22,
        "is_power_active": False,
        "can_fire": False,
    }
    assert co_states[1] == {
        "player_id": expected_ids[1],
        "seat": 1,
        "color": "blue",
        "commander_id": "anna",
        "meter": 0,
        "threshold": 20,
        "is_power_active": True,
        "can_fire": False,
    }
    assert "_power_baselines" not in response.text
