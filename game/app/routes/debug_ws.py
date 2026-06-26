"""
Debug WebSocket endpoints — **not for production clients**.

These let a developer connect to a game's event stream via WebSocket to
verify the event bus is working end-to-end. Useful with `wscat`,
`websocat`, or a browser console:

    wscat -c "ws://localhost:8000/debug/ws/games/1"

    # or in browser console:
    ws = new WebSocket("ws://localhost:8000/debug/ws/games/1")
    ws.onmessage = (e) => console.log(JSON.parse(e.data));

This is intentionally minimal — the production WebSocket gateway will
use the same protocol (app.protocol.v1) but add auth, rate limiting,
and per-client state snapshots.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.events import bus
from app.protocol import EVENT_DELTA, PROTOCOL_VERSION, WSMessage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/debug/ws", tags=["debug"])


@router.websocket("/games/{game_id}")
async def debug_event_stream(ws: WebSocket, game_id: int) -> None:
    """Stream all GameEvents for the given game_id as JSON.

    Connection lifecycle:
      1. Server accepts the WebSocket
      2. Server sends a `server.hello` message
      3. Server forwards every published GameEvent as `event.delta`
      4. Client may send `ping`; server replies with `pong` (TODO if needed)
      5. On client disconnect, server cleans up the subscription
    """
    await ws.accept()
    logger.info("Debug WS connected: game_id=%d client=%s",
                game_id, ws.client)

    # Subscribe BEFORE sending hello, so no event is missed.
    queue = bus.subscribe(game_id)
    try:
        # Send hello envelope
        await ws.send_json(WSMessage(
            v=PROTOCOL_VERSION,
            type="server.hello",
            payload={
                "server_version": "0.1.0-debug",
                "protocol_version": PROTOCOL_VERSION,
                "subscribed_game_id": game_id,
                "message": "Debug event stream connected. You'll receive event.delta messages as they happen.",
            },
        ).to_wire())

        # Forward events until the client disconnects.
        while True:
            event = await queue.get()
            await ws.send_json(WSMessage(
                v=PROTOCOL_VERSION,
                type=EVENT_DELTA,
                payload={
                    "game_id": event.game_id,
                    "turn": event.turn,
                    "event_type": event.type,
                    "actor_unit_id": event.actor_unit_id,
                    "actor_name": event.actor_name,
                    "target_unit_id": event.target_unit_id,
                    "target_name": event.target_name,
                    "context": event.context,
                    "importance": event.importance,
                    "original_timestamp_ms": event.timestamp_ms,
                },
            ).to_wire())
    except WebSocketDisconnect:
        logger.info("Debug WS disconnected: game_id=%d", game_id)
    except Exception:  # noqa: BLE001
        logger.exception("Debug WS error: game_id=%d", game_id)
    finally:
        bus.unsubscribe(game_id, queue)
        try:
            await ws.close()
        except Exception:  # noqa: BLE001
            pass
