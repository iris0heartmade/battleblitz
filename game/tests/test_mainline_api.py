"""
Integration tests for the ``/mainlines`` routes (Step 3 backend).

Uses the same ``prog_client`` fixture style as
``tests/test_progression_api.py``: per-test DB reset so tests are
hermetic.

Coverage map (matches ``doc/step3_plan.md`` §6):
  1.  GET /mainlines returns chapter_01
  2.  GET /mainlines/{id} returns detail with 2 battles + 4 dialogue keys
  3.  POST /mainlines/{id}/start creates Game + AI enemy
  4.  POST /mainlines/{id}/start rejects insufficient classes (403)
  5.  POST /mainlines/{id}/start writes mainline_progress on profile
  6.  POST /mainlines/{id}/advance returns post_battle_dialogue
  7.  POST /mainlines/{id}/advance last battle grants rewards
  8.  POST /mainlines/{id}/abandon clears active mainline
  9.  POST /mainlines/{id}/next-battle spawns second battle
  10. GET /mainlines/dialogue returns scenes array
  11. GET /mainlines/dialogue rejects path traversal
  12. mainline enemy Player.agent_kind == "rules"
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
async def ml_client():
    """ASGI client + fresh DB per test, mirroring ``prog_client``."""
    from app.main import app
    from app.database import (
        AsyncSessionLocal,
        Base,
        dispose_db,
        engine,
        init_db,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # Hand the caller an open session factory so they can seed
        # data directly (avoids HTTP round-trips for fixture setup).
        yield c, AsyncSessionLocal
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await dispose_db()


async def _create_profile(client, user_name="alice", unlocked=None):
    """Helper: create a PlayerProfile via the /progression API.

    Returns the profile id (int).
    """
    body = {"user_name": user_name}
    if unlocked is not None:
        body["initial_rating"] = 1000
    r = await client.post("/progression/profiles", json=body)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    if unlocked is not None:
        # The POST profile payload doesn't expose unlocked_classes
        # directly, so patch via the DB session.
        from app.database import AsyncSessionLocal
        from app.progression.models import PlayerProfile
        async with AsyncSessionLocal() as s:
            row = await s.get(PlayerProfile, pid)
            row.unlocked_classes = list(unlocked)
            await s.commit()
    return pid


# ============================================================
# 1. List
# ============================================================

@pytest.mark.integration
class TestListMainlines:
    async def test_list_mainlines_returns_chapter_01(self, ml_client):
        client, _ = ml_client
        r = await client.get("/mainlines")
        assert r.status_code == 200
        ids = [m["id"] for m in r.json()]
        assert "chapter_01_steel_rebellion" in ids

    async def test_list_includes_battle_count(self, ml_client):
        client, _ = ml_client
        r = await client.get("/mainlines")
        assert r.status_code == 200
        for m in r.json():
            assert m["battle_count"] >= 1


# ============================================================
# 2. Detail
# ============================================================

@pytest.mark.integration
class TestMainlineDetail:
    async def test_get_detail_includes_battles_and_dialogues(self, ml_client):
        client, _ = ml_client
        r = await client.get(
            "/mainlines/chapter_01_steel_rebellion"
        )
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == "chapter_01_steel_rebellion"
        assert body["battle_count"] == 2
        assert len(body["battles"]) == 2
        assert {b["id"] for b in body["battles"]} == {"battle_01", "battle_02"}
        # chapter_01 declares 4 dialogue keys: intro + 3 battle aftermaths
        assert len(body["dialogue_keys"]) == 4
        assert "intro" in body["dialogue_keys"]

    async def test_get_detail_unknown_returns_404(self, ml_client):
        client, _ = ml_client
        r = await client.get("/mainlines/does_not_exist_xyz")
        assert r.status_code == 404


# ============================================================
# 3 / 5. Start (happy path + writes mainline_progress)
# ============================================================

@pytest.mark.integration
class TestStartMainline:
    async def test_start_creates_game_and_enemy(self, ml_client):
        client, _ = ml_client
        await _create_profile(client, "alice")
        r = await client.post(
            "/mainlines/chapter_01_steel_rebellion/start",
            json={"user_name": "alice", "skip_intro": True},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["mainline_id"] == "chapter_01_steel_rebellion"
        assert body["battle_id"] == "battle_01"
        assert body["battle_index"] == 0
        assert body["total_battles"] == 2
        # skip_intro=True means no pre-battle dialogue URL
        assert body["state"] == "battle"
        assert body["pre_battle_dialogue_url"] is None

        # Verify DB rows
        from app.database import AsyncSessionLocal
        from app.models import Game, Player, Unit
        async with AsyncSessionLocal() as s:
            games = (await s.execute(select(Game))).scalars().all()
            assert len(games) == 1
            game = games[0]
            assert game.name == "mainline:chapter_01_steel_rebellion:battle_01"
            assert game.status == "playing"

            players = (await s.execute(
                select(Player).where(Player.game_id == game.id)
            )).scalars().all()
            assert len(players) == 2
            seats = sorted(p.seat for p in players)
            assert seats == [0, 1]
            human = next(p for p in players if p.seat == 0)
            enemy = next(p for p in players if p.seat == 1)
            assert human.user_name == "alice"
            assert human.is_ai is False
            assert enemy.is_ai is True

            # ally composition says {"swordsman":3, "archer":1} = 4 units
            ally_units = (await s.execute(
                select(Unit).where(Unit.player_id == human.id)
            )).scalars().all()
            assert len(ally_units) == 4
            # enemy composition says {"knight":4} = 4 units
            enemy_units = (await s.execute(
                select(Unit).where(Unit.player_id == enemy.id)
            )).scalars().all()
            assert len(enemy_units) == 4
            assert all(u.unit_type == "knight" for u in enemy_units)

    async def test_start_with_intro_returns_dialogue_url(self, ml_client):
        client, _ = ml_client
        await _create_profile(client, "alice")
        r = await client.post(
            "/mainlines/chapter_01_steel_rebellion/start",
            json={"user_name": "alice"},  # don't skip intro
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["state"] == "dialogue"
        assert body["pre_battle_dialogue_key"] == "intro"
        assert body["pre_battle_dialogue_url"] and \
            body["pre_battle_dialogue_url"].endswith("intro.json")

    async def test_start_writes_mainline_progress(self, ml_client):
        client, _ = ml_client
        await _create_profile(client, "alice")
        r = await client.post(
            "/mainlines/chapter_01_steel_rebellion/start",
            json={"user_name": "alice", "skip_intro": True},
        )
        assert r.status_code == 201

        # Profile should now have active_mainline set + progress cursor
        from app.database import AsyncSessionLocal
        from app.progression.models import PlayerProfile
        async with AsyncSessionLocal() as s:
            row = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            assert row.active_mainline == "chapter_01_steel_rebellion"
            assert row.mainline_progress["battle_index"] == 0
            # 'scene_id' should be 'intro' or the first dialogue key
            assert row.mainline_progress["scene_id"]
            assert row.mainline_progress["started_at"] is not None


# ============================================================
# 4. Start — class prerequisite check
# ============================================================

@pytest.mark.integration
class TestStartClassPrereq:
    async def test_rejects_insufficient_classes(self, ml_client):
        client, _ = ml_client
        # Profile has only swordsman; chapter_01 needs swordsman + archer
        await _create_profile(client, "bob", unlocked=["swordsman"])
        r = await client.post(
            "/mainlines/chapter_01_steel_rebellion/start",
            json={"user_name": "bob", "skip_intro": True},
        )
        assert r.status_code == 403
        assert "archer" in r.json()["detail"]

    async def test_start_auto_creates_missing_profile(self, ml_client):
        """管 1 兜底：profile 不存在时 /start 应自动建档，不再 404。

        业务端点（advance / next-battle / abandon）仍要 404（用户填错
        昵称时不能静默建错 profile），但 /start 是入口，必须宽松。
        """
        client, _ = ml_client
        r = await client.post(
            "/mainlines/chapter_01_steel_rebellion/start",
            json={"user_name": "玩家-828", "skip_intro": True},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["mainline_id"] == "chapter_01_steel_rebellion"
        assert body["battle_id"] == "battle_01"
        assert body["battle_index"] == 0

        # Profile 现在存在了
        from app.progression.models import PlayerProfile
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as s:
            row = (await s.execute(
                select(PlayerProfile).where(
                    PlayerProfile.user_name == "玩家-828"
                )
            )).scalar_one()
            assert row is not None
            assert row.active_mainline == "chapter_01_steel_rebellion"

    async def test_advance_with_unknown_profile_still_returns_404(self, ml_client):
        """业务端点（advance）的 404 行为必须保留 —— 不能自动建。

        用户填错昵称时如果 advance 静默建档，会污染数据库。
        """
        client, _ = ml_client
        r = await client.post(
            "/mainlines/chapter_01_steel_rebellion/advance",
            json={"user_name": "ghost", "game_id": 1},
        )
        assert r.status_code == 404


# ============================================================
# 12. Enemy AI metadata
# ============================================================

@pytest.mark.integration
class TestEnemyAiMetadata:
    async def test_enemy_player_has_agent_kind_rules(self, ml_client):
        client, _ = ml_client
        await _create_profile(client, "alice")
        r = await client.post(
            "/mainlines/chapter_01_steel_rebellion/start",
            json={"user_name": "alice", "skip_intro": True},
        )
        assert r.status_code == 201

        from app.database import AsyncSessionLocal
        from app.models import Player
        async with AsyncSessionLocal() as s:
            players = (await s.execute(select(Player))).scalars().all()
            enemy = next(p for p in players if p.is_ai)
            assert enemy.agent_kind == "rules"


# ============================================================
# 6. Advance after victory — post-battle dialogue
# ============================================================

async def _start_then_finish_battle(client, ml_factory, profile_name="alice"):
    """Helper: start mainline, force-mark the game as finished, return ids."""
    r = await client.post(
        "/mainlines/chapter_01_steel_rebellion/start",
        json={"user_name": profile_name, "skip_intro": True},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    game_id = body["game_id"]

    # Mutate Game.status to "finished" directly via the session so we
    # don't have to simulate a real battle.
    from app.database import AsyncSessionLocal
    from app.models import Game
    async with AsyncSessionLocal() as s:
        g = await s.get(Game, game_id)
        g.status = "finished"
        await s.commit()
    return game_id, body


@pytest.mark.integration
class TestAdvance:
    async def test_advance_after_victory_returns_post_dialogue(self, ml_client):
        client, _ = ml_client
        await _create_profile(client, "alice")
        game_id, _ = await _start_then_finish_battle(client, _, "alice")

        r = await client.post(
            "/mainlines/chapter_01_steel_rebellion/advance",
            json={"user_name": "alice", "game_id": game_id},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["state"] == "dialogue"
        assert body["post_battle_dialogue_key"] == "battle_01_after"
        assert body["post_battle_dialogue_url"] and \
            body["post_battle_dialogue_url"].endswith("battle_01_after.json")
        assert body["rewards"] is None  # not the last battle
        assert body["battle_index"] == 1  # cursor advanced

    async def test_advance_unfinished_game_rejected(self, ml_client):
        client, _ = ml_client
        await _create_profile(client, "alice")
        r = await client.post(
            "/mainlines/chapter_01_steel_rebellion/start",
            json={"user_name": "alice", "skip_intro": True},
        )
        body = r.json()
        # Game is "playing", not "finished"
        r2 = await client.post(
            "/mainlines/chapter_01_steel_rebellion/advance",
            json={"user_name": "alice", "game_id": body["game_id"]},
        )
        assert r2.status_code == 409

    async def test_advance_with_unrelated_game_rejected(self, ml_client):
        client, _ = ml_client
        await _create_profile(client, "alice")
        # Create an unrelated finished game
        from app.database import AsyncSessionLocal
        from app.models import Game
        async with AsyncSessionLocal() as s:
            g = Game(name="random_lobby", status="finished", map_seed=1)
            s.add(g)
            await s.commit()
            gid = g.id

        r = await client.post(
            "/mainlines/chapter_01_steel_rebellion/advance",
            json={"user_name": "alice", "game_id": gid},
        )
        assert r.status_code == 409


# ============================================================
# 7. Advance last battle → VICTORY + rewards
# ============================================================

@pytest.mark.integration
class TestVictory:
    async def test_last_battle_victory_grants_rewards(self, ml_client):
        client, _ = ml_client
        await _create_profile(client, "alice")

        # Start the mainline.
        r = await client.post(
            "/mainlines/chapter_01_steel_rebellion/start",
            json={"user_name": "alice", "skip_intro": True},
        )
        assert r.status_code == 201

        # Advance past battle_01 -> cursor at 1.
        from app.database import AsyncSessionLocal
        from app.models import Game
        async with AsyncSessionLocal() as s:
            games = (await s.execute(select(Game))).scalars().all()
            g1 = next(g for g in games if g.name.endswith("battle_01"))
            g1.status = "finished"
            await s.commit()
            gid1 = g1.id

        r = await client.post(
            "/mainlines/chapter_01_steel_rebellion/advance",
            json={"user_name": "alice", "game_id": gid1},
        )
        assert r.status_code == 200

        # Spawn battle 2 via /next-battle.
        r2 = await client.post(
            "/mainlines/chapter_01_steel_rebellion/next-battle",
            json={"user_name": "alice"},
        )
        assert r2.status_code == 201, r2.text
        gid2 = r2.json()["game_id"]

        async with AsyncSessionLocal() as s:
            g2 = await s.get(Game, gid2)
            g2.status = "finished"
            await s.commit()

        # Advance past battle_02 -> VICTORY
        r3 = await client.post(
            "/mainlines/chapter_01_steel_rebellion/advance",
            json={"user_name": "alice", "game_id": gid2},
        )
        assert r3.status_code == 200, r3.text
        body = r3.json()
        assert body["state"] == "victory"
        # chapter_01 declares rewards_on_clear: gold=500, unlock_class="knight", exp_per_unit=120
        assert body["rewards"]["gold"] == 500
        assert body["rewards"]["unlock_class"] == "knight"
        assert body["rewards"]["exp_per_unit"] == 120

        # Verify profile: gold credited, knight unlocked, active cleared
        from app.progression.models import PlayerProfile
        async with AsyncSessionLocal() as s:
            row = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            assert row.gold == 500
            assert "knight" in row.unlocked_classes
            assert row.active_mainline is None


# ============================================================
# 9. Next battle
# ============================================================

@pytest.mark.integration
class TestNextBattle:
    async def test_next_battle_after_advance(self, ml_client):
        client, _ = ml_client
        await _create_profile(client, "alice")
        r = await client.post(
            "/mainlines/chapter_01_steel_rebellion/start",
            json={"user_name": "alice", "skip_intro": True},
        )
        assert r.status_code == 201

        # Finish battle_01 and advance.
        from app.database import AsyncSessionLocal
        from app.models import Game
        async with AsyncSessionLocal() as s:
            g = (await s.execute(select(Game))).scalars().one()
            g.status = "finished"
            await s.commit()
            gid = g.id

        r = await client.post(
            "/mainlines/chapter_01_steel_rebellion/advance",
            json={"user_name": "alice", "game_id": gid},
        )
        assert r.status_code == 200

        # Now request next-battle.
        r2 = await client.post(
            "/mainlines/chapter_01_steel_rebellion/next-battle",
            json={"user_name": "alice"},
        )
        assert r2.status_code == 201, r2.text
        body = r2.json()
        assert body["battle_id"] == "battle_02"
        assert body["battle_index"] == 1
        # battle_02 has no pre_battle_dialogue
        assert body["state"] == "battle"
        assert body["pre_battle_dialogue_url"] is None

    async def test_next_battle_without_active_mainline_rejected(self, ml_client):
        client, _ = ml_client
        await _create_profile(client, "alice")
        r = await client.post(
            "/mainlines/chapter_01_steel_rebellion/next-battle",
            json={"user_name": "alice"},
        )
        assert r.status_code == 409


# ============================================================
# 8. Abandon
# ============================================================

@pytest.mark.integration
class TestAbandon:
    async def test_abandon_clears_active_mainline(self, ml_client):
        client, _ = ml_client
        await _create_profile(client, "alice")
        r = await client.post(
            "/mainlines/chapter_01_steel_rebellion/start",
            json={"user_name": "alice", "skip_intro": True},
        )
        assert r.status_code == 201

        # Game should still exist on disk.
        from app.database import AsyncSessionLocal
        from app.models import Game
        async with AsyncSessionLocal() as s:
            game_count = len((await s.execute(select(Game))).scalars().all())
            assert game_count == 1

        r2 = await client.post(
            "/mainlines/chapter_01_steel_rebellion/abandon",
            json={"user_name": "alice"},
        )
        assert r2.status_code == 200
        body = r2.json()
        assert body["ok"] is True
        assert body["mainline_id"] == "chapter_01_steel_rebellion"
        assert body["abandoned_at"]

        # Profile.active_mainline is now None.
        from app.progression.models import PlayerProfile
        async with AsyncSessionLocal() as s:
            row = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            assert row.active_mainline is None

        # Game row is NOT deleted (the orchestrator only clears profile state).
        async with AsyncSessionLocal() as s:
            game_count_after = len(
                (await s.execute(select(Game))).scalars().all()
            )
            assert game_count_after == 1

    async def test_abandon_without_active_mainline_is_idempotent(self, ml_client):
        client, _ = ml_client
        await _create_profile(client, "alice")
        r = await client.post(
            "/mainlines/chapter_01_steel_rebellion/abandon",
            json={"user_name": "alice"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        # Nothing was active, so no mainline_id / abandoned_at
        assert body["mainline_id"] is None
        assert body["abandoned_at"] is None


# ============================================================
# 10. Dialogue file service
# ============================================================

@pytest.mark.integration
class TestDialogueEndpoint:
    async def test_get_dialogue_returns_scenes_array(self, ml_client):
        client, _ = ml_client
        r = await client.get(
            "/mainlines/dialogue",
            params={"path": "stories/chapter_01/intro.json"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "scenes" in body
        assert isinstance(body["scenes"], list)
        assert len(body["scenes"]) >= 1

    async def test_get_dialogue_rejects_path_traversal(self, ml_client):
        client, _ = ml_client
        r = await client.get(
            "/mainlines/dialogue",
            params={"path": "../../../etc/passwd"},
        )
        assert r.status_code == 400

    async def test_get_dialogue_rejects_absolute_path(self, ml_client):
        client, _ = ml_client
        r = await client.get(
            "/mainlines/dialogue",
            params={"path": "/etc/passwd"},
        )
        # Absolute paths are coerced into game/ by the resolve() check,
        # which produces a path that doesn't exist -> 404.
        assert r.status_code in (400, 404)

    async def test_get_dialogue_missing_file_returns_404(self, ml_client):
        client, _ = ml_client
        r = await client.get(
            "/mainlines/dialogue",
            params={"path": "stories/chapter_01/nope.json"},
        )
        assert r.status_code == 404


# ============================================================
# 13. Battle-finished detection via game.status (used by FE poll)
# ============================================================

@pytest.mark.integration
class TestGameStateAfterStart:
    async def test_mainline_battle_uses_existing_action_routes(self, ml_client):
        """Sanity: after /start the game is reachable via /games/{id}/state."""
        client, _ = ml_client
        await _create_profile(client, "alice")
        r = await client.post(
            "/mainlines/chapter_01_steel_rebellion/start",
            json={"user_name": "alice", "skip_intro": True},
        )
        body = r.json()
        gid = body["game_id"]

        # /games/{id}/state should return the full GameStateOut payload.
        r2 = await client.get(f"/games/{gid}/state")
        assert r2.status_code == 200, r2.text
        state = r2.json()
        assert state["game"]["id"] == gid
        assert state["game"]["status"] == "playing"
        assert len(state["players"]) == 2
        # Tiles populated
        assert len(state["tiles"]) > 0
        # Each player has units
        for p in state["players"]:
            assert len(p["units"]) > 0
