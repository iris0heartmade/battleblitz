"""Presentation heights survive editing, game creation and state/suspend serialization."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def map_client(tmp_path, monkeypatch):
    from app.database import Base, engine, init_db
    from app.main import app
    from app.routes import editor
    monkeypatch.setattr(editor, "_CUSTOM_DIR", tmp_path)
    await init_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


def map_body():
    rows = ["P" * 15 for _ in range(15)]
    rows[2] = "PPC" + "P" * 12
    rows[12] = "P" * 12 + "C" + "P" * 2
    heights = [[0] * 15 for _ in range(15)]
    heights[4][4], heights[4][5] = -5, 5
    return {"name": "高差存读验证", "size": {"width": 15, "height": 15},
            "biome": "grass", "layout": rows, "elevations": heights,
            "initial_units": [{"x": 2, "y": 3, "type": "swordsman", "color": "red", "level": 1},
                              {"x": 12, "y": 11, "type": "swordsman", "color": "blue", "level": 1}]}


async def test_custom_heights_roundtrip_start_and_state(map_client):
    client = map_client
    body = map_body()
    saved = await client.post("/editor/maps", json=body)
    assert saved.status_code == 201, saved.text
    map_id = saved.json()["id"]
    loaded = (await client.get(f"/editor/maps/{map_id}")).json()
    assert loaded["elevations"] == body["elevations"]
    game = (await client.post("/games", json={"name": "height-test", "map_preset": f"custom:{map_id}", "mode": "mainline"})).json()
    assert "id" in game, game
    for seat, color in enumerate(["red", "blue"]):
        joined = await client.post(f"/games/{game['id']}/join", json={"user_name": color, "color": color, "seat": seat})
        assert joined.status_code in (200,201), joined.text
    started = await client.post(f"/games/{game['id']}/start", json={})
    assert started.status_code == 200, started.text
    state = (await client.get(f"/games/{game['id']}/state")).json()
    cells = {(t["x"],t["y"]): t for t in state["tiles"]}
    assert cells[(4,4)]["elevation"] == -5 and cells[(5,4)]["elevation"] == 5
    assert all(cells[(x,y)]["elevation"] == body["elevations"][y][x] for y in range(15) for x in range(15))
    assert cells[(4,4)]["terrain"] == "plain"  # Height does not replace the movement terrain.


@pytest.mark.parametrize("value", [6,-6,1.5,True,"3"])
async def test_reject_invalid_height(map_client, value):
    body = map_body()
    body["elevations"][4][4] = value
    response = await map_client.post("/editor/maps", json=body)
    assert response.status_code == 422


async def test_reject_wrong_dimensions_and_keep_legacy_maps(map_client):
    body = map_body()
    body["elevations"].pop()
    response = await map_client.post("/editor/maps", json=body)
    assert response.status_code == 422
    body.pop("elevations")
    saved = await map_client.post("/editor/maps", json=body)
    assert saved.status_code == 201
    assert saved.json()["elevations"] == []


def test_elevation_migration_preserves_legacy_database():
    from sqlalchemy import create_engine, text
    from app.database import _run_legacy_migrations
    # Use actual schema, then remove only the new column to simulate a legacy DB.
    from app.database import Base
    import app.models  # noqa: F401
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE tiles DROP COLUMN elevation"))
        connection.execute(text("INSERT INTO tiles (game_id,x,y,terrain) VALUES (17,2,3,'mountain')"))
        _run_legacy_migrations(connection)
        columns = {row[1] for row in connection.execute(text("PRAGMA table_info(tiles)"))}
        assert "elevation" in columns
        row = connection.execute(text("SELECT x,y,terrain,elevation FROM tiles")).one()
        assert tuple(row) == (2, 3, "mountain", None)
        _run_legacy_migrations(connection)  # Repeat startup is safe.
