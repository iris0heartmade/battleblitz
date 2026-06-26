"""
Event bus for BattleBlitz.

Public API:
    from app.events import bus, GameEvent

    await bus.publish(GameEvent(type="kill", game_id=1, ...))
    queue = bus.subscribe(game_id=1)
    event = await queue.get()
    bus.unsubscribe(game_id, queue)
"""
from app.events.bus import GameEventBus, bus
from app.events.types import (
    CRITICAL_EVENTS,
    IMPORTANT_EVENTS,
    EventType,
    GameEvent,
)

__all__ = [
    "GameEventBus",
    "bus",
    "GameEvent",
    "EventType",
    "CRITICAL_EVENTS",
    "IMPORTANT_EVENTS",
]
