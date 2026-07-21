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

    Optional file logger: when ``set_file_logger(path)`` is called, every
    published event is appended as one JSON line to that file. This is
    the primary evidence stream used by the chapter_06 event verifier
    (see ``godot-client/tools/chapter_06_event_log_verify.gd``).
    """

    QUEUE_MAX_SIZE: int = 100

    def __init__(self) -> None:
        self._subscribers: dict[int, list[asyncio.Queue["GameEvent"]]] = \
            defaultdict(list)
        self._lock = asyncio.Lock()
        # File logger state. When ``_log_path`` is set, every published
        # event is appended as one JSON line.
        self._log_path: str | None = None
        self._log_file = None  # open file handle

    def set_file_logger(self, log_path: str) -> None:
        """Enable file-based event logging. Each event → one JSON line.

        Used by ``godot-client/tools/chapter_06_event_log_verify.gd``
        to verify that the chapter_06 design triggers the expected
        sequence of move / attack / trap / boss / victory events.
        """
        if self._log_file is not None:
            self._log_file.close()
        self._log_path = log_path
        # Write a header so the file is self-describing.
        self._log_file = open(log_path, "a", encoding="utf-8")
        if self._log_file is not None:
            self._log_file.write("=== chapter_06 event log started ===\n")
            self._log_file.flush()

    def close_file_logger(self) -> None:
        if self._log_file is not None:
            self._log_file.write("=== chapter_06 event log closed ===\n")
            self._log_file.close()
            self._log_file = None
            self._log_path = None

    def _write_log_line(self, event: "GameEvent") -> None:
        if self._log_file is None:
            return
        # Compact one-line JSON for grep-friendly verification
        import json as _json
        line = _json.dumps({
            "t": event.timestamp_ms,
            "turn": event.turn,
            "type": event.type,
            "game": event.game_id,
            "actor": [event.actor_player_id, event.actor_unit_id, event.actor_name],
            "target": [event.target_player_id, event.target_unit_id, event.target_name],
            "ctx": event.context,
        }, ensure_ascii=False, separators=(",", ":"))
        self._log_file.write(line + "\n")
        self._log_file.flush()

    async def publish(self, event: "GameEvent") -> None:
        """Fan out an event to all subscribers of its game_id.

        Non-blocking from the publisher's perspective: a slow subscriber
        cannot back-pressure the publisher.
        """
        # Always log to file if enabled (even with 0 subscribers)
        self._write_log_line(event)
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


# ============================================================
# Module-level singleton
# ============================================================
# Importing this gives you a shared bus for the whole process. Tests can
# create their own GameEventBus() and monkey-patch `bus` if they need
# isolation.

bus = GameEventBus()


__all__ = ["GameEventBus", "bus"]
