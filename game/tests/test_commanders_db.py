from __future__ import annotations

import pytest
from sqlalchemy import text

from app.database import Base, dispose_db, engine, init_db


@pytest.fixture
async def commander_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await init_db()
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await dispose_db()


@pytest.mark.asyncio
async def test_commander_persistence_columns_exist(commander_db):
    async with engine.connect() as conn:
        player_rows = (await conn.execute(text("PRAGMA table_info(players)"))).fetchall()
        profile_rows = (
            await conn.execute(text("PRAGMA table_info(player_profiles)"))
        ).fetchall()

    player_cols = {row[1]: row for row in player_rows}
    profile_cols = {row[1]: row for row in profile_rows}

    assert "commander_id" in player_cols
    assert "co_state" in player_cols
    assert player_cols["co_state"][2].upper() == "JSON"
    assert "unlocked_commanders" in profile_cols
    assert profile_cols["unlocked_commanders"][2].upper() == "JSON"
