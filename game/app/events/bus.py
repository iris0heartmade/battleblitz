"""
In-process event bus for GameEvents.

Process-local pub/sub keyed by `game_id`. Subscribers get an asyncio.Queue
they can `await queue.get()` from. The bus is intentionally simple — when
we go multi-instance, swap this for Redis pub/sub behind the same API.

Usage:

    from app.events import bus, GameEvent

    # Publish (from action handlers, game logic, etc.)
    await bus.publish(GameEvent(
        type="kill", game_id=game.id, turn=game.turn_number,
        actor_player_id=..., actor_unit_id=..., actor_name=...,
        target_player_id=..., target_unit_id=..., target_name=...,
        context={"dmg": 18, "is_crit": True},
    ))

    # Subscribe (from AI, commentary, WebSocket gateway, etc.)
    queue = bus.subscribe(game_id)
    try:
        while True:
            event = await queue.get()
            ...
    finally:
        bus.unsubscribe(game_id, queue)
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.events.types import GameEvent


logger = logging.getLogger(__name__)


class GameEventBus:
    """In-process pub/sub for GameEvents, keyed by game_id.

    Each subscriber receives its own asyncio.Queue. If a subscriber is too
    slow and its queue fills up, events for that subscriber are dropped
    (a warning is logged) — other subscribers are unaffected.
    """

    QUEUE_MAX_SIZE: int = 100

    def __init__(self) -> None:
        self._subscribers: dict[int, list[asyncio.Queue["GameEvent"]]] = \
            defaultdict(list)
        self._lock = asyncio.Lock()

    async def publish(self, event: "GameEvent") -> None:
        """Fan out an event to all subscribers of its game_id.

        Non-blocking from the publisher's perspective: a slow subscriber
        cannot back-pressure the publisher.
        """
        queues = self._subscribers.get(event.game_id, [])
        if not queues:
            return
        for q in queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    "EventBus queue full for game %d, dropping %s",
                    event.game_id, event.type,
                )

    def subscribe(self, game_id: int) -> asyncio.Queue["GameEvent"]:
        """Register a new subscriber for `game_id`. Returns the queue."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=self.QUEUE_MAX_SIZE)
        self._subscribers[game_id].append(queue)
        logger.debug("EventBus: new subscriber for game %d (total=%d)",
                     game_id, len(self._subscribers[game_id]))
        return queue

    def unsubscribe(self, game_id: int, queue: asyncio.Queue) -> None:
        """Remove a subscriber. Safe to call multiple times."""
        subs = self._subscribers.get(game_id, [])
        if queue in subs:
            subs.remove(queue)
            if not subs:
                self._subscribers.pop(game_id, None)

    def subscriber_count(self, game_id: int) -> int:
        """How many subscribers are currently listening to this game."""
        return len(self._subscribers.get(game_id, []))

    def total_subscribers(self) -> int:
        """Sum of all subscribers across all games (for metrics)."""
        return sum(len(qs) for qs in self._subscribers.values())


# ============================================================
# Module-level singleton
# ============================================================
# Importing this gives you a shared bus for the whole process. Tests can
# create their own GameEventBus() and monkey-patch `bus` if they need
# isolation.

bus = GameEventBus()


__all__ = ["GameEventBus", "bus"]
