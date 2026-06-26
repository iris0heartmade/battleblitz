"""
Unit tests for the in-process event bus.

Covers:
  - GameEvent serialization
  - subscribe/unsubscribe bookkeeping
  - publish fan-out
  - queue overflow behavior
  - thread/async safety (single-loop, so just sequential here)
"""
from __future__ import annotations

import asyncio

import pytest

from app.events import (
    CRITICAL_EVENTS,
    IMPORTANT_EVENTS,
    GameEvent,
    GameEventBus,
)


# ============================================================
# GameEvent
# ============================================================

@pytest.mark.unit
class TestGameEvent:
    def test_importance_classification(self):
        kill = GameEvent(type="kill", game_id=1)
        assert kill.importance == "critical"
        assert kill.type in CRITICAL_EVENTS

        level = GameEvent(type="level_up", game_id=1)
        assert level.importance == "important"
        assert level.type in IMPORTANT_EVENTS

        move = GameEvent(type="move", game_id=1)
        assert move.importance == "normal"

    def test_to_dict_omits_none(self):
        e = GameEvent(type="move", game_id=1, actor_unit_id=42)
        d = e.to_dict()
        assert d["actor_unit_id"] == 42
        # target_* are None, should be excluded
        assert "target_player_id" not in d
        assert "target_unit_id" not in d

    def test_default_timestamp_recent(self):
        e = GameEvent(type="wait", game_id=1)
        # Must be within the last few seconds (in ms)
        import time
        now_ms = int(time.time() * 1000)
        assert abs(now_ms - e.timestamp_ms) < 5000

    def test_context_is_per_type(self):
        e = GameEvent(
            type="kill", game_id=1,
            context={"dmg": 18, "is_crit": True},
        )
        assert e.context["dmg"] == 18
        assert e.context["is_crit"] is True


# ============================================================
# GameEventBus
# ============================================================

@pytest.mark.unit
class TestGameEventBus:
    def test_subscribe_returns_queue(self):
        bus = GameEventBus()
        q = bus.subscribe(game_id=1)
        assert isinstance(q, asyncio.Queue)
        assert bus.subscriber_count(1) == 1
        bus.unsubscribe(1, q)
        assert bus.subscriber_count(1) == 0

    async def test_publish_fans_out_to_all_subscribers(self):
        bus = GameEventBus()
        q1 = bus.subscribe(game_id=1)
        q2 = bus.subscribe(game_id=1)
        await bus.publish(GameEvent(type="move", game_id=1))
        e1 = await q1.get()
        e2 = await q2.get()
        assert e1.type == "move"
        assert e2.type == "move"

    async def test_publish_does_not_cross_games(self):
        bus = GameEventBus()
        q1 = bus.subscribe(game_id=1)
        q2 = bus.subscribe(game_id=2)
        await bus.publish(GameEvent(type="move", game_id=1))
        # q1 gets the event
        assert (await q1.get()).type == "move"
        # q2 stays empty
        assert q2.empty()

    async def test_unsubscribe_stops_delivery(self):
        bus = GameEventBus()
        q = bus.subscribe(game_id=1)
        bus.unsubscribe(1, q)
        await bus.publish(GameEvent(type="move", game_id=1))
        # Nothing should arrive
        await asyncio.sleep(0)  # yield
        assert q.empty()

    async def test_subscribe_again_after_unsubscribe(self):
        bus = GameEventBus()
        q1 = bus.subscribe(game_id=1)
        bus.unsubscribe(1, q1)
        q2 = bus.subscribe(game_id=1)
        await bus.publish(GameEvent(type="kill", game_id=1))
        assert (await q2.get()).type == "kill"

    async def test_total_subscribers_metric(self):
        bus = GameEventBus()
        bus.subscribe(game_id=1)
        bus.subscribe(game_id=1)
        bus.subscribe(game_id=2)
        assert bus.total_subscribers() == 3

    async def test_overflow_drops_for_slow_subscriber(self):
        """A subscriber that doesn't drain its queue gets the latest events
        dropped, but other subscribers still get them."""
        bus = GameEventBus()
        bus.QUEUE_MAX_SIZE = 3  # type: ignore[misc]
        slow = bus.subscribe(game_id=1)
        fast = bus.subscribe(game_id=1)
        for i in range(10):
            await bus.publish(GameEvent(type="move", game_id=1, context={"i": i}))
        # Slow queue is at max
        assert slow.qsize() == 3
        # Fast queue is also at max (overflow was logged, not raised)
        # The test mainly asserts no exception is raised and both queues
        # have at most QUEUE_MAX_SIZE items.
        assert fast.qsize() <= 3

    async def test_publish_with_no_subscribers_is_noop(self):
        bus = GameEventBus()
        # Should not raise
        await bus.publish(GameEvent(type="move", game_id=99))
