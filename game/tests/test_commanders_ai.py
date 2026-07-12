import pytest
from sqlalchemy import select

from app.commanders.ai import ai_should_fire_co_power
from app.database import AsyncSessionLocal
from app.models import ActionLog, Game, Player
from app.routes.turns import _run_ai_turn_chain_locked


class FakePlayer:
    def __init__(self, commander_id, meter, active=False):
        self.commander_id = commander_id
        self.co_state = {"meter": meter, "threshold": 22,
                         "is_power_active": active}


@pytest.mark.parametrize("player, expected", [
    (FakePlayer("yun", 22), True),
    (FakePlayer("yun", 21), False),
    (FakePlayer(None, 100), False),
    (FakePlayer("yun", 22, True), False),
])
def test_ai_should_fire_co_power(player, expected):
    assert ai_should_fire_co_power(player) is expected


@pytest.mark.asyncio
async def test_ai_fires_only_on_its_turn_and_commits(monkeypatch, db_session):
    game = Game(name="ai-co", status="playing", current_player_index=0,
                turn_number=1, phase="ai", map_seed=1)
    db_session.add(game)
    await db_session.flush()
    ai = Player(game_id=game.id, user_name="cpu", color="red", seat=0,
                is_ai=True, commander_id="yun", co_state={"meter": 22,
                "threshold": 22, "is_power_active": False,
                "last_start_turn": 1})
    human = Player(game_id=game.id, user_name="human", color="blue", seat=1,
                   is_ai=False, commander_id="anna", co_state={"meter": 18,
                   "threshold": 18, "is_power_active": False,
                   "last_start_turn": 1})
    db_session.add_all([ai, human])
    await db_session.commit()

    async def no_sleep(_): pass
    async def no_action(session, battle, player): return False
    monkeypatch.setattr("app.routes.turns.asyncio.sleep", no_sleep)
    monkeypatch.setattr("app.routes.turns.ai_take_one_action", no_action)

    await _run_ai_turn_chain_locked(game.id)
    await _run_ai_turn_chain_locked(game.id)
    async with AsyncSessionLocal() as check:
        fired_ai = await check.get(Player, ai.id)
        untouched_human = await check.get(Player, human.id)
        logs = (await check.execute(select(ActionLog).where(
            ActionLog.game_id == game.id,
            ActionLog.action_type == "co_power_fired",
        ))).scalars().all()
        assert fired_ai.co_state["meter"] == 0
        assert fired_ai.co_state["is_power_active"] is True
        assert untouched_human.co_state["meter"] == 18
        assert len(logs) == 1
        assert "auto" in logs[0].description

    async with AsyncSessionLocal() as setup:
        battle = await setup.get(Game, game.id)
        battle.current_player_index = 1
        human_row = await setup.get(Player, human.id)
        human_row.is_ai = False
        human_row.co_state = {**human_row.co_state, "meter": 18,
                              "is_power_active": False}
        await setup.commit()
    await _run_ai_turn_chain_locked(game.id)
    async with AsyncSessionLocal() as check:
        human_row = await check.get(Player, human.id)
        assert human_row.co_state["meter"] == 18
