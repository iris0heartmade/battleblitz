"""
Tests for the temporary test mainline chapters (chapter_test_01/02/03).

Verifies:
  * Each chapter loads through the mainline loader without error.
  * ``/start`` for each chapter spawns exactly 1 blue enemy unit.
  * The lone enemy unit has ``hp == max_hp == 1`` (wounded), thanks
    to the new ``SpawnUnit.hp`` override.
  * Hero campaign state is initialised on first ``/start`` and the
    hero appears in the unit set with the expected class / level.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
async def tml_client():
    from app.main import app
    from app.database import (
        AsyncSessionLocal,
        Base,
        dispose_db,
        engine,
        init_db,
    )
    from app.mainline import clear_cache

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await init_db()
    # Force the loader to re-read the JSON files (in case a prior
    # test cached an older snapshot).
    clear_cache()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, AsyncSessionLocal
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await dispose_db()


async def _create_profile(client, user_name="alice"):
    r = await client.post("/progression/profiles", json={"user_name": user_name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ============================================================
# Loader visibility
# ============================================================

def test_test_chapters_define_an_ordered_campaign_chain():
    """The test chapters are separate files but form one campaign path."""
    from app.mainline import clear_cache, load_mainline

    clear_cache()
    assert load_mainline("chapter_test_01").next_mainline_id == "chapter_test_02"
    assert load_mainline("chapter_test_02").next_mainline_id == "chapter_test_03"
    assert load_mainline("chapter_test_03").next_mainline_id is None


@pytest.mark.integration
class TestListTestMainlines:
    async def test_test_chapters_appear_in_list(self, tml_client):
        client, _ = tml_client
        r = await client.get("/mainlines")
        assert r.status_code == 200, r.text
        ids = {m["id"] for m in r.json()}
        assert "chapter_test_01" in ids
        assert "chapter_test_02" in ids
        assert "chapter_test_03" in ids

    async def test_test_chapter_01_detail(self, tml_client):
        client, _ = tml_client
        r = await client.get("/mainlines/chapter_test_01")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["battle_count"] == 1
        assert body["battles"][0]["id"] == "battle_01"
        assert "intro" in body["dialogue_keys"]
        assert "battle_01_after" in body["dialogue_keys"]


# ============================================================
# Spawn: 1 blue enemy, hp == 1
# ============================================================

@pytest.mark.integration
class TestWoundedEnemySpawn:
    async def test_chapter_test_01_spawns_one_wounded_swordsman(
        self, tml_client,
    ):
        client, SessionLocal = tml_client
        await _create_profile(client, "alice")
        r = await client.post(
            "/mainlines/chapter_test_01/start",
            json={"user_name": "alice", "skip_intro": True},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        game_id = body["game_id"]

        from app.models import Game, Player, Unit
        async with SessionLocal() as s:
            game = (await s.execute(select(Game))).scalar_one()
            assert game.id == game_id
            players = (await s.execute(
                select(Player).where(Player.game_id == game_id)
            )).scalars().all()
            ai = next(p for p in players if p.is_ai)
            enemy_units = (await s.execute(
                select(Unit).where(Unit.player_id == ai.id)
            )).scalars().all()
            # exactly 1 wounded enemy
            assert len(enemy_units) == 1, (
                f"expected 1 enemy, got {len(enemy_units)}: "
                f"{[(u.unit_type, u.hp, u.max_hp, u.x, u.y) for u in enemy_units]}"
            )
            only = enemy_units[0]
            assert only.unit_type == "swordsman"
            assert only.hp == 1
            assert only.max_hp == 1
            # The wounded swordsman is at the position we kept
            # (match color=blue, x=14, y=7 in chapter_test_01).
            assert (only.x, only.y) == (14, 7)

    async def test_chapter_test_02_spawns_one_wounded_archer(
        self, tml_client,
    ):
        client, _ = tml_client
        await _create_profile(client, "alice")
        r = await client.post(
            "/mainlines/chapter_test_02/start",
            json={"user_name": "alice", "skip_intro": True},
        )
        assert r.status_code == 201, r.text

        from app.database import AsyncSessionLocal
        from app.models import Player, Unit
        async with AsyncSessionLocal() as s:
            players = (await s.execute(
                select(Player).where(Player.game_id == r.json()["game_id"])
            )).scalars().all()
            ai = next(p for p in players if p.is_ai)
            enemy_units = (await s.execute(
                select(Unit).where(Unit.player_id == ai.id)
            )).scalars().all()
            assert len(enemy_units) == 1
            only = enemy_units[0]
            assert only.unit_type == "archer"
            assert only.hp == 1
            assert only.max_hp == 1
            assert (only.x, only.y) == (13, 8)

    async def test_chapter_test_03_spawns_one_wounded_warlock(
        self, tml_client,
    ):
        client, _ = tml_client
        await _create_profile(client, "alice")
        r = await client.post(
            "/mainlines/chapter_test_03/start",
            json={"user_name": "alice", "skip_intro": True},
        )
        assert r.status_code == 201, r.text

        from app.database import AsyncSessionLocal
        from app.models import Player, Unit
        async with AsyncSessionLocal() as s:
            players = (await s.execute(
                select(Player).where(Player.game_id == r.json()["game_id"])
            )).scalars().all()
            ai = next(p for p in players if p.is_ai)
            enemy_units = (await s.execute(
                select(Unit).where(Unit.player_id == ai.id)
            )).scalars().all()
            assert len(enemy_units) == 1
            only = enemy_units[0]
            assert only.unit_type == "warlock"
            assert only.hp == 1
            assert only.max_hp == 1
            assert (only.x, only.y) == (12, 8)


# ============================================================
# Hero spawn sanity
# ============================================================

@pytest.mark.integration
class TestHeroSpawnInTestChapters:
    async def test_chapter_test_03_yun_at_level_20_via_campaign_state(
        self, tml_client,
    ):
        """chapter_test_03 declares yun at level 20 so the prepare
        panel can offer promotion. The JSON's per-spec ``level``
        field is *not* honoured for hero-tagged units (the spawn
        pipeline always takes the level from ``hero_campaign_states``)
        so the realistic flow is:

          1. Player previously advanced yun to level 20 in earlier
             chapters → ``hero_campaign_states["yun"].level == 20``.
          2. /prepare reads the level, exposes the promote button.
          3. /start spawns yun at level 20.

        This test simulates step 1 by writing the state directly,
        then verifies steps 2-3.
        """
        client, SessionLocal = tml_client
        await _create_profile(client, "alice")

        from app.progression.models import PlayerProfile
        async with SessionLocal() as s:
            profile = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            profile.hero_campaign_states = {
                "yun": {
                    "hero_id": "yun",
                    "class_id": "warlock",
                    "level": 20,
                    "exp": 0,
                    "base_stats": {
                        "hp": 50, "atk": 20, "def": 11,
                        "matk": 27, "mdef": 12, "mov": 4, "mp": 8,
                    },
                    "weapon_ranks": {},
                    "learned_skills": ["arcane_strike"],
                    "promoted": False,
                    "equipment": {},
                }
            }
            profile.hero_inventory = {"hero_crest": 1}
            await s.commit()

        r = await client.post(
            "/mainlines/chapter_test_03/start",
            json={"user_name": "alice", "skip_intro": True},
        )
        assert r.status_code == 201, r.text

        from app.models import Player, Unit
        async with SessionLocal() as s:
            players = (await s.execute(
                select(Player).where(Player.game_id == r.json()["game_id"])
            )).scalars().all()
            human = next(p for p in players if not p.is_ai)
            units = (await s.execute(
                select(Unit).where(Unit.player_id == human.id)
            )).scalars().all()
            yun = next(u for u in units if u.hero_id == "yun")
            assert yun.level == 20, (
                f"yun should spawn at level 20 from campaign_state, got {yun.level}"
            )
            assert yun.unit_type == "warlock"  # not yet promoted

    async def test_chapter_test_03_promote_then_start_spawns_sage(
        self, tml_client,
    ):
        """End-to-end: pre-set yun state → /prepare/promote to sage →
        /start. Verifies the spawn honours the promoted class."""
        client, SessionLocal = tml_client
        await _create_profile(client, "alice")

        from app.progression.models import PlayerProfile
        async with SessionLocal() as s:
            profile = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            profile.hero_campaign_states = {
                "yun": {
                    "hero_id": "yun",
                    "class_id": "warlock",
                    "level": 20,
                    "exp": 88,
                    "base_stats": {
                        "hp": 50, "atk": 20, "def": 11,
                        "matk": 27, "mdef": 12, "mov": 4, "mp": 8,
                    },
                    "weapon_ranks": {},
                    "learned_skills": ["arcane_strike"],
                    "promoted": False,
                    "equipment": {},
                }
            }
            profile.hero_inventory = {"hero_crest": 1}
            await s.commit()

        # Promote yun to sage through the prepare endpoint.
        r1 = await client.post(
            "/mainlines/chapter_test_03/prepare/promote",
            json={
                "user_name": "alice",
                "hero_id": "yun",
                "target_class_id": "sage",
            },
        )
        assert r1.status_code == 200, r1.text
        assert r1.json()["class_id"] == "sage"

        # Now start the mainline.
        r2 = await client.post(
            "/mainlines/chapter_test_03/start",
            json={"user_name": "alice", "skip_intro": True},
        )
        assert r2.status_code == 201, r2.text

        from app.models import Player as _Player, Unit as _Unit
        async with SessionLocal() as s:
            players = (await s.execute(
                select(_Player).where(_Player.game_id == r2.json()["game_id"])
            )).scalars().all()
            human = next(p for p in players if not p.is_ai)
            units = (await s.execute(
                select(_Unit).where(_Unit.player_id == human.id)
            )).scalars().all()
            yun = next(u for u in units if u.hero_id == "yun")
            assert yun.unit_type == "sage"
            assert yun.level == 1  # promote resets level to 1
