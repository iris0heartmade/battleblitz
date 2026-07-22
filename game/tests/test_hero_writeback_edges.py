"""
Edge-case tests for ``_persist_mainline_hero_results`` (routes/mainline.py).

Covers scenarios the scaffold commit did not exercise:
  * Hero died in battle — does the long-term state lose data?
  * Hero temporarily swapped equipment — does it overwrite the long-term set?
  * Promoted hero whose class is a tier-2 unit — does ``promoted`` flag
    stay in sync with the unit_type?
  * Human player swapped seats between battles (spectator join) — does
    the writeback find the right unit set?

Each test follows the same shape as ``test_mainline_api.py``: a
real ASGI client + per-test DB reset, with the in-flight ``Unit``
rows mutated via direct SQLAlchemy access (since the battle engine
isn't driven through HTTP here).
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
async def wb_client():
    """Per-test DB reset, matching the ``ml_client`` fixture in
    ``test_mainline_api.py``."""
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
        yield c, AsyncSessionLocal
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await dispose_db()


async def _create_profile(client, user_name="alice"):
    r = await client.post("/progression/profiles", json={"user_name": user_name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _start_mainline(client, user_name="alice"):
    r = await client.post(
        "/mainlines/chapter_01_steel_rebellion/start",
        json={"user_name": user_name, "skip_intro": True},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _finish_battle(SessionLocal, game_id):
    from app.models import Game
    async with SessionLocal() as s:
        g = await s.get(Game, game_id)
        g.status = "finished"
        await s.commit()


def test_level_up_scales_hero_snapshot_not_equipment_bonus():
    """Level growth must use naked stats, preserving the equipment delta."""
    from types import SimpleNamespace

    from app.config import EXP_TO_LEVEL
    from app.game_logic import level_up_if_ready

    unit = SimpleNamespace(
        level=1,
        exp=EXP_TO_LEVEL,
        # Effective battle values: ruby ring already added HP +3.
        hp=53,
        max_hp=53,
        atk=20,
        def_=11,
        matk=27,
        mdef=12,
        campaign_base_stats={
            "hp": 50, "atk": 20, "def": 11,
            "matk": 27, "mdef": 12, "mov": 4, "mp": 8,
        },
    )

    result = level_up_if_ready(unit)

    assert result is not None
    assert unit.campaign_base_stats["hp"] == 52
    assert unit.max_hp == 55
    assert unit.hp == 55
    assert unit.campaign_base_stats["atk"] == 22
    assert unit.atk == 22


def test_magic_hero_level_up_grows_magic_lane_and_weak_physical_side():
    """Magic classes grow MATK/MDEF strongly while ATK/DEF grow as weak side."""
    from types import SimpleNamespace

    from app.config import EXP_TO_LEVEL
    from app.game_logic import level_up_if_ready

    unit = SimpleNamespace(
        unit_type="warlock",
        level=1,
        exp=EXP_TO_LEVEL,
        hp=53,
        max_hp=53,
        atk=20,
        def_=11,
        matk=27,
        mdef=12,
        campaign_base_stats={
            "hp": 50, "atk": 20, "def": 11,
            "matk": 27, "mdef": 12, "mov": 4, "mp": 8,
        },
    )

    result = level_up_if_ready(unit)

    assert result is not None
    assert unit.campaign_base_stats["hp"] == 52
    assert unit.campaign_base_stats["atk"] == 21
    assert unit.campaign_base_stats["def"] == 12
    assert unit.campaign_base_stats["matk"] == 29
    assert unit.campaign_base_stats["mdef"] == 14
    assert unit.atk == 21
    assert unit.def_ == 12
    assert unit.matk == 29
    assert unit.mdef == 14


def test_physical_hero_level_up_grows_physical_lane_and_weak_magic_side():
    """Physical classes grow ATK/DEF strongly while MATK/MDEF grow as weak side."""
    from types import SimpleNamespace

    from app.config import EXP_TO_LEVEL
    from app.game_logic import level_up_if_ready

    unit = SimpleNamespace(
        unit_type="swordsman",
        level=1,
        exp=EXP_TO_LEVEL,
        hp=45,
        max_hp=45,
        atk=18,
        def_=12,
        matk=4,
        mdef=4,
        campaign_base_stats={
            "hp": 45, "atk": 18, "def": 12,
            "matk": 4, "mdef": 4, "mov": 3, "mp": 5,
        },
    )

    result = level_up_if_ready(unit)

    assert result is not None
    assert unit.campaign_base_stats["hp"] == 47
    assert unit.campaign_base_stats["atk"] == 20
    assert unit.campaign_base_stats["def"] == 14
    assert unit.campaign_base_stats["matk"] == 5
    assert unit.campaign_base_stats["mdef"] == 5
    assert unit.matk == 5
    assert unit.mdef == 5


def test_battle_level_cap_is_20_and_exp_award_levels_immediately():
    """Combat EXP settlement should apply level-up before turn/chapter end."""
    from types import SimpleNamespace

    from app.config import EXP_PER_KILL, EXP_TO_LEVEL, MAX_LEVEL
    from app.game_logic import award_exp

    assert MAX_LEVEL == 20

    unit = SimpleNamespace(
        unit_type="warlock",
        level=19,
        exp=EXP_TO_LEVEL - EXP_PER_KILL,
        hp=53,
        max_hp=53,
        atk=20,
        def_=11,
        matk=27,
        mdef=12,
        morale=0,
        campaign_base_stats={
            "hp": 50, "atk": 20, "def": 11,
            "matk": 27, "mdef": 12, "mov": 4, "mp": 8,
        },
    )

    result = award_exp(unit, "kill")

    assert result is not None
    assert result.new_level == 20
    assert unit.level == 20
    assert unit.exp == 0
    assert unit.morale == 1
    assert unit.campaign_base_stats["matk"] == 29
    assert unit.campaign_base_stats["mdef"] == 14
    assert unit.campaign_base_stats["def"] == 12


def test_battle_exp_is_discarded_at_level_cap():
    """Lv20 is the hard battle cap; do not bank overflow EXP."""
    from types import SimpleNamespace

    from app.config import EXP_PER_KILL, EXP_TO_LEVEL
    from app.game_logic import award_exp

    unit = SimpleNamespace(
        unit_type="swordsman",
        level=19,
        exp=EXP_TO_LEVEL - EXP_PER_KILL + 5,
        hp=45,
        max_hp=45,
        atk=18,
        def_=12,
        matk=4,
        mdef=4,
        morale=0,
        campaign_base_stats={},
    )

    result = award_exp(unit, "kill")

    assert result is not None
    assert unit.level == 20
    assert unit.exp == 0

    result = award_exp(unit, "kill")

    assert result is None
    assert unit.level == 20
    assert unit.exp == 0


@pytest.mark.integration
async def test_immediate_hero_level_up_persists_only_after_mainline_advance(wb_client):
    """Live battle growth is formalized only by successful chapter advance."""
    client, SessionLocal = wb_client
    await _create_profile(client, "alice")
    body = await _start_mainline(client, "alice")
    game_id = body["game_id"]

    from app.config import EXP_PER_KILL, EXP_TO_LEVEL
    from app.game_logic import award_exp
    from app.models import Game, Player, Unit
    from app.progression.models import PlayerProfile

    async with SessionLocal() as s:
        profile = (await s.execute(
            select(PlayerProfile).where(PlayerProfile.user_name == "alice")
        )).scalar_one()
        baseline_level = profile.hero_campaign_states["yun"]["level"]
        baseline_exp = profile.hero_campaign_states["yun"]["exp"]

        human = (await s.execute(
            select(Player).where(Player.game_id == game_id, Player.user_name == "alice")
        )).scalar_one()
        yun = (await s.execute(
            select(Unit).where(Unit.player_id == human.id, Unit.hero_id == "yun")
        )).scalar_one()

        yun.level = baseline_level
        yun.exp = EXP_TO_LEVEL - EXP_PER_KILL
        result = award_exp(yun, "kill")
        assert result is not None
        assert yun.level == baseline_level + 1

        # Before chapter advance, formal profile state must not be mutated.
        await s.flush()
        await s.refresh(profile)
        assert profile.hero_campaign_states["yun"]["level"] == baseline_level
        assert profile.hero_campaign_states["yun"]["exp"] == baseline_exp

        game = await s.get(Game, game_id)
        game.status = "finished"
        await s.commit()

    r = await client.post(
        "/mainlines/chapter_01_steel_rebellion/advance",
        json={"user_name": "alice", "game_id": game_id},
    )
    assert r.status_code == 200, r.text

    async with SessionLocal() as s:
        profile = (await s.execute(
            select(PlayerProfile).where(PlayerProfile.user_name == "alice")
        )).scalar_one()
        saved = profile.hero_campaign_states["yun"]
        assert saved["level"] == baseline_level + 1
        assert saved["exp"] == 0

    # Auto-save is a formal snapshot; mutating the profile afterward should
    # prove the saved chapter-end copy already contains the leveled hero.
    async with SessionLocal() as s:
        profile = (await s.execute(
            select(PlayerProfile).where(PlayerProfile.user_name == "alice")
        )).scalar_one()
        mutated = dict(profile.hero_campaign_states)
        mutated["yun"] = dict(mutated["yun"])
        mutated["yun"]["level"] = 1
        profile.hero_campaign_states = mutated
        await s.commit()

    r = await client.post(
        "/saves/load",
        json={"user_name": "alice", "kind": "auto", "slot_index": 0},
    )
    assert r.status_code == 200, r.text

    async with SessionLocal() as s:
        profile = (await s.execute(
            select(PlayerProfile).where(PlayerProfile.user_name == "alice")
        )).scalar_one()
        assert profile.hero_campaign_states["yun"]["level"] == baseline_level + 1


# ============================================================
# Edge 1: hero died during battle
# ============================================================

@pytest.mark.integration
class TestDeadHeroWriteback:
    async def test_dead_hero_keeps_long_term_max_hp(self, wb_client):
        """If the hero's ``Unit.is_alive`` is False at end-of-battle, the
        persisted ``base_stats.hp`` must NOT collapse to 0 — the
        long-term pool is the pre-battle max, not the battle's
        depleted value."""
        client, SessionLocal = wb_client
        await _create_profile(client, "alice")
        body = await _start_mainline(client, "alice")
        game_id = body["game_id"]
        await _finish_battle(SessionLocal, game_id)

        from app.models import Game, Player, Unit
        from app.progression.models import PlayerProfile
        async with SessionLocal() as s:
            # Capture the pre-battle max_hp for yun from the hero_campaign_states
            profile = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            pre_hp = profile.hero_campaign_states["yun"]["base_stats"]["hp"]
            assert pre_hp > 0

            # Kill yun mid-battle
            human = (await s.execute(
                select(Player).where(Player.game_id == game_id, Player.user_name == "alice")
            )).scalar_one()
            yun = (await s.execute(
                select(Unit).where(Unit.player_id == human.id, Unit.hero_id == "yun")
            )).scalar_one()
            yun.hp = 0
            yun.is_alive = False
            await s.commit()

        r = await client.post(
            "/mainlines/chapter_01_steel_rebellion/advance",
            json={"user_name": "alice", "game_id": game_id},
        )
        assert r.status_code == 200, r.text

        async with SessionLocal() as s:
            profile = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            saved = profile.hero_campaign_states["yun"]
            # Long-term max_hp must NOT collapse to 0 just because the
            # unit is dead in this battle.
            assert saved["base_stats"]["hp"] == pre_hp, (
                f"dead hero lost long-term HP: pre={pre_hp} got={saved['base_stats']['hp']}"
            )


# ============================================================
# Edge 2: equipment slot in long-term storage untouched
# ============================================================

@pytest.mark.integration
class TestEquipmentSlot:
    async def test_equipment_bonus_is_not_written_into_campaign_base_stats(
        self, wb_client,
    ):
        """Battle equipment raises effective stats only for that battle."""
        client, SessionLocal = wb_client
        await _create_profile(client, "alice")
        body = await _start_mainline(client, "alice")
        game_id = body["game_id"]

        from app.models import Game, Player, Unit
        from app.progression.models import PlayerProfile
        async with SessionLocal() as s:
            profile = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            human = (await s.execute(
                select(Player).where(Player.game_id == game_id, Player.user_name == "alice")
            )).scalar_one()
            yun = (await s.execute(
                select(Unit).where(Unit.player_id == human.id, Unit.hero_id == "yun")
            )).scalar_one()
            # Yun's default ruby ring gives HP +3.  The Unit must carry the
            # effective 53 HP while its settlement snapshot remains 50.
            assert yun.max_hp == 53
            assert yun.campaign_base_stats["hp"] == 50
            assert profile.hero_campaign_states["yun"]["base_stats"]["hp"] == 50
            game = await s.get(Game, game_id)
            game.status = "finished"
            await s.commit()

        r = await client.post(
            "/mainlines/chapter_01_steel_rebellion/advance",
            json={"user_name": "alice", "game_id": game_id},
        )
        assert r.status_code == 200, r.text

        async with SessionLocal() as s:
            profile = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            saved = profile.hero_campaign_states["yun"]
            assert saved["base_stats"]["hp"] == 50
            assert saved["base_stats"]["matk"] == 27
            assert saved["base_stats"]["mdef"] == 12

    async def test_advance_does_not_overwrite_long_term_equipment(
        self, wb_client,
    ):
        """The long-term equipment on the profile must remain a
        *long-term* slot — the in-battle ``Unit.equipment`` (which the
        engine treats as a snapshot) must not bleed into the persisted
        hero state.
        """
        client, SessionLocal = wb_client
        await _create_profile(client, "alice")
        body = await _start_mainline(client, "alice")
        game_id = body["game_id"]

        from app.progression.models import PlayerProfile
        async with SessionLocal() as s:
            profile = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            # NOTE: SQLAlchemy's JSON column doesn't auto-track
            # in-place dict mutation. We must reassign the whole
            # column, mirroring how ``ProgressionService.set_*`` works.
            profile.hero_campaign_states = {
                "yun": {
                    "hero_id": "yun",
                    "class_id": "warlock",
                    "level": 5,
                    "exp": 0,
                    "base_stats": {
                        "hp": 50, "atk": 20, "def": 11,
                        "matk": 27, "mdef": 12, "mov": 4, "mp": 8,
                    },
                    "weapon_ranks": {},
                    "learned_skills": ["arcane_strike"],
                    "promoted": False,
                    "equipment": {"weapon": "oak_staff", "accessory": "iron_ring"},
                }
            }
            await s.commit()

        await _finish_battle(SessionLocal, game_id)
        # NOTE: Unit rows do NOT have a `weapon` column — the
        # long-term equipment slot is the *source of truth* and must
        # survive a battle unchanged. We don't need to mutate the
        # Unit row; we just check that advance doesn't blow it away.

        r = await client.post(
            "/mainlines/chapter_01_steel_rebellion/advance",
            json={"user_name": "alice", "game_id": game_id},
        )
        assert r.status_code == 200, r.text

        async with SessionLocal() as s:
            profile = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            saved = profile.hero_campaign_states["yun"]
            assert saved["equipment"] == {
                "weapon": "oak_staff", "accessory": "iron_ring",
            }, f"long-term equipment got clobbered: {saved['equipment']}"


# ============================================================
# Edge 3: promoted hero class stays promoted after the battle
# ============================================================

@pytest.mark.integration
class TestPromotedClassPersistence:
    async def test_tier2_unit_type_keeps_promoted_flag(
        self, wb_client,
    ):
        """If yun spawns as a ``sage`` (tier-2) and gains a level, the
        persisted state must still report ``promoted: True`` and the
        matching tier-2 class_id.
        """
        client, SessionLocal = wb_client
        await _create_profile(client, "alice")
        body = await _start_mainline(client, "alice")
        game_id = body["game_id"]
        await _finish_battle(SessionLocal, game_id)

        from app.models import Player, Unit
        from app.progression.models import PlayerProfile
        async with SessionLocal() as s:
            profile = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            profile.hero_campaign_states = {
                "yun": {
                    "hero_id": "yun",
                    "class_id": "sage",
                    "level": 3,
                    "exp": 30,
                    "base_stats": {
                        "hp": 54, "atk": 11, "def": 13,
                        "matk": 30, "mdef": 18, "mov": 4, "mp": 10,
                    },
                    "weapon_ranks": {},
                    "learned_skills": ["arcane_strike"],
                    "promoted": True,
                    "equipment": {},
                }
            }
            await s.commit()

            # yun promotes mid-battle (level 20 + crest) AND levels
            # up to 4. Simulate the in-battle state on the Unit row.
            human = (await s.execute(
                select(Player).where(Player.game_id == game_id, Player.user_name == "alice")
            )).scalar_one()
            yun = (await s.execute(
                select(Unit).where(Unit.player_id == human.id, Unit.hero_id == "yun")
            )).scalar_one()
            yun.unit_type = "sage"
            yun.level = 4
            yun.exp = 20
            yun.max_hp = 58
            yun.matk = 38
            yun.mdef = 19
            yun.mov = 5
            yun.mp = 12
            await s.commit()

        r = await client.post(
            "/mainlines/chapter_01_steel_rebellion/advance",
            json={"user_name": "alice", "game_id": game_id},
        )
        assert r.status_code == 200, r.text

        async with SessionLocal() as s:
            profile = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            saved = profile.hero_campaign_states["yun"]
            assert saved["class_id"] == "sage"
            assert saved["promoted"] is True
            assert saved["level"] == 4
            assert saved["exp"] == 20


# ============================================================
# Edge 4: no human player (e.g. game created by another process)
# ============================================================

@pytest.mark.integration
class TestMissingHumanPlayer:
    async def test_advance_skips_persist_when_no_human_player(
        self, wb_client,
    ):
        """If the Game has no human Player matching the profile (e.g. a
        dev tool finished a battle without spawning a human seat), the
        writeback must be a no-op — not crash, not corrupt, and the
        profile's prior hero state must stay intact.
        """
        client, SessionLocal = wb_client
        await _create_profile(client, "alice")

        from app.database import AsyncSessionLocal
        from app.models import Game, Player
        from app.progression.models import PlayerProfile

        async with SessionLocal() as s:
            profile = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            profile.hero_campaign_states = {
                "yun": {
                    "hero_id": "yun",
                    "class_id": "warlock",
                    "level": 5,
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
            prior_snapshot = dict(profile.hero_campaign_states["yun"])
            await s.commit()

            # Create a finished mainline game with NO human Player.
            g = Game(name="orphan:battle_01", status="finished", map_seed=1)
            s.add(g)
            await s.flush()
            game_id = g.id
            # Only an AI player, no human seat 0 with user_name="alice"
            ai = Player(
                game_id=game_id, seat=0, color="red", user_name="ai-bot",
                is_ai=True, is_spectator=False,
            )
            s.add(ai)
            await s.commit()

        r = await client.post(
            "/mainlines/chapter_01_steel_rebellion/advance",
            json={"user_name": "alice", "game_id": game_id},
        )
        # 409 because the mainline cursor doesn't match this game
        assert r.status_code in (200, 409), r.text

        async with SessionLocal() as s:
            profile = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            # Prior hero state must be untouched.
            assert profile.hero_campaign_states["yun"] == prior_snapshot
