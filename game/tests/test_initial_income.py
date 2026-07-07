"""Test that initial gold is granted to ALL players at game start.

Discovered by verify_economy.py: start_game calls
_collect_income_for_player(first_player) but only for seat 0, and even
that call appears to not stick in some configurations. This test pins
the expected behaviour: every player who owns at least one income tile
at game start gets one turn's worth of income credited IMMEDIATELY
(before any turn advance).
"""
from __future__ import annotations

import pytest
from sqlalchemy import select


@pytest.mark.asyncio
async def test_all_players_get_initial_income_at_start(client):
    """After POST /games/{id}/start, every player should have gold ==
    income from buildings they own at start."""
    from app.config import BUILDING_INCOME
    from app.database import AsyncSessionLocal
    from app.models import Player, Tile

    # Create game via HTTP
    r = await client.post("/games", json={
        "name": "Initial income test",
        "map_preset": "test_arena_10x10_2v2",
        "capacity": 2,
        "map_seed": 42,
        "win_condition": "rout",
    })
    assert r.status_code in (200, 201), r.text
    game_id = r.json()["id"]

    # Add host + 1 AI via HTTP so all players route through the same
    # Depends(get_session) machinery the production code uses
    r = await client.post(f"/games/{game_id}/join",
                          json={"user_name": "host", "color": "red"})
    assert r.status_code in (200, 201), r.text
    r = await client.post(f"/games/{game_id}/add-ai", json={
        "difficulty": "normal", "agent_kind": "rules",
        "personality": "balanced",
    })
    assert r.status_code in (200, 201), r.text

    # Start the game
    r = await client.post(f"/games/{game_id}/start")
    assert r.status_code in (200, 201), r.text

    # Now read fresh state via a brand-new session so we don't get
    # any in-flight cached values from the route handlers
    from collections import Counter
    async with AsyncSessionLocal() as session:
        players = (await session.execute(
            select(Player).where(Player.game_id == game_id)
        )).scalars().all()
        tiles = (await session.execute(
            select(Tile).where(Tile.game_id == game_id)
        )).scalars().all()

    failed = []
    for p in players:
        if p.is_spectator:
            continue
        owned = [
            t for t in tiles
            if t.owner_id == p.id and t.terrain in BUILDING_INCOME
        ]
        counts = Counter(t.terrain for t in owned)
        expected = sum(
            BUILDING_INCOME[ter]["amount"] * n for ter, n in counts.items()
        )
        actual = p.gold or 0
        status = "OK" if actual == expected else "FAIL"
        print(
            f"  [{status}] seat {p.seat} ({p.color}): "
            f"expected={expected}, actual={actual}, "
            f"buildings={dict(counts)}",
            flush=True,
        )
        if actual != expected:
            failed.append(
                f"seat {p.seat} ({p.color}): expected {expected}, got {actual}"
            )

    assert not failed, "initial income mismatch: " + "; ".join(failed)