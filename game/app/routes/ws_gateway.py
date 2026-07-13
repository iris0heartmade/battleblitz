"""
P0.1 — Production WebSocket gateway.

Replaces the browser's 3-second polling with a real-time push stream
of GameEvents. Same wire format as the debug endpoint (`debug_ws.py`)
but with auth, per-game ring buffer for rewind, heartbeat, and
proper disconnect cleanup.

Endpoint: ``ws://<host>/ws/games/{game_id}?since_seq=<N>``

Auth (dev-friendly): ``X-Player-Id: <int>`` header. Server verifies
the player_id is a participant in this game. Production should swap
``_check_auth`` for a JWT/session-token check; the rest of the loop
is identical.

Reconnect: client keeps ``last_seq``. On reconnect with
``?since_seq=N``, server replays every cached event with ``seq > N``
in order, then resumes live.

Heartbeat: server sends a no-op frame every ``HEARTBEAT_SEC``
seconds so a dead connection is detected within 2× that. Clients
should ignore unknown ``type`` fields silently.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import TYPE_CHECKING

from fastapi import APIRouter, Header, HTTPException, Query, WebSocket, WebSocketDisconnect, status

from app.events import bus
from app.protocol import (
    PROTOCOL_VERSION,
    SERVER_HELLO,
    STATE_SNAPSHOT,
    EVENT_DELTA,
    SERVER_PONG,
    WSMessage,
)
from app.models import Game, Player

if TYPE_CHECKING:
    from app.events.types import GameEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["ws-gateway"])


# Per-game state: a monotonic seq counter and a bounded ring buffer of
# recent events so a reconnecting client can ask "give me everything
# since seq=N" without us needing DB-backed history.
_seq: dict[int, int] = defaultdict(int)
_REPLAY_MAX = 200
_replay: dict[int, "list[tuple[int, GameEvent]]"] = defaultdict(list)


def _next_seq(game_id: int) -> int:
    _seq[game_id] += 1
    return _seq[game_id]


def _remember_event(game_id: int, seq: int, event: "GameEvent") -> None:
    buf = _replay[game_id]
    buf.append((seq, event))
    if len(buf) > _REPLAY_MAX:
        buf.pop(0)  # drop oldest


HEARTBEAT_SEC = 30.0


# ----- Auth -----

async def _check_auth(ws: WebSocket, game_id: int, x_player_id: str | None) -> Player:
    """Verify X-Player-Id header maps to a real participant in this game.

    Returns the matched Player on success; closes the WS with an error
    envelope on failure. Dev-only check — production would replace
    this with a session-token lookup.
    """
    if not x_player_id:
        await _send_error(ws, "AUTH_REQUIRED", "X-Player-Id header missing")
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing X-Player-Id")

    try:
        player_id = int(x_player_id)
    except ValueError:
        await _send_error(ws, "AUTH_REQUIRED", "X-Player-Id must be an integer")
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "X-Player-Id is not an integer")

    # Player must exist and be a participant in this game. We avoid
    # opening a DB session here — use a fresh short-lived one.
    from app.database import AsyncSessionLocal
    from sqlalchemy import select
    async with AsyncSessionLocal() as session:
        game = await session.get(Game, game_id)
        if game is None:
            await _send_error(ws, "GAME_NOT_FOUND", f"game {game_id} not found")
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            raise HTTPException(status.HTTP_404_NOT_FOUND, "game not found")
        result = await session.execute(
            select(Player).where(Player.id == player_id, Player.game_id == game_id)
        )
        player = result.scalar_one_or_none()
    if player is None:
        await _send_error(ws, "AUTH_REQUIRED", f"player {player_id} is not in game {game_id}")
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "player not in game")
    return player


async def _send_error(ws: WebSocket, code: str, message: str) -> None:
    """Best-effort error frame before close. If the socket is dead, ignore."""
    try:
        await ws.send_json(WSMessage(
            v=PROTOCOL_VERSION,
            type="error",
            payload={"code": code, "message": message},
        ).to_wire())
    except Exception:  # noqa: BLE001
        pass


# ----- Connection lifecycle -----

@router.websocket("/games/{game_id}")
async def production_event_stream(
    ws: WebSocket,
    game_id: int,
    since_seq: int = Query(default=0, ge=0, description="Replay events with seq > since_seq"),
    x_player_id: str | None = Header(default=None, alias="X-Player-Id"),
    player_id: int | None = Query(default=None, description="Auth via query param (browser WebSocket can't set custom headers)"),
) -> None:
    """Real-time GameEvent stream for production clients.

    Connection lifecycle:
      1. accept + auth (closes on failure)
      2. send server.hello with current_seq
      3. replay cached events with seq > since_seq
      4. forward every published GameEvent as event.delta
      5. heartbeat every HEARTBEAT_SEC (sends server.pong)
      6. on disconnect, unsubscribe + cleanup

    Auth: prefer ``X-Player-Id`` header. Falls back to ``?player_id=``
    query param so browser WebSocket clients (which can't set custom
    headers) can authenticate. Production should swap for a JWT or
    session cookie.
    """
    # Auth happens AFTER accept so we can send an `error` envelope
    # before closing with a structured status code.
    await ws.accept()
    auth_value = x_player_id if x_player_id else (str(player_id) if player_id else None)
    try:
        player = await _check_auth(ws, game_id, auth_value)
    except HTTPException:
        return  # _check_auth already closed the socket

    logger.info("WS gateway connected: game=%d player=%d (%s) since_seq=%d",
                game_id, player.id, player.user_name, since_seq)

    # Subscribe BEFORE sending hello, so no event is missed.
    queue = bus.subscribe(game_id)

    # Heartbeat task: sends a no-op frame every HEARTBEAT_SEC so dead
    # connections are detected by the client. Cancelled on disconnect.
    async def _heartbeat() -> None:
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_SEC)
                await ws.send_json(WSMessage(
                    v=PROTOCOL_VERSION,
                    type=SERVER_PONG,
                    payload={"echo_at_ms": 0},  # client uses local ping time
                ).to_wire())
        except (WebSocketDisconnect, asyncio.CancelledError):
            return
        except Exception:  # noqa: BLE001
            logger.debug("WS heartbeat failed (likely closed)", exc_info=False)
            return

    heartbeat_task = asyncio.create_task(_heartbeat())

    # Per-connection seq counter — this is the seq *for this client's
    # stream*, which may differ from the global per-game seq if the
    # client asked for since_seq > 0 (we resume numbering from there).
    client_seq = _seq[game_id]

    try:
        # 1. Hello with current global seq so the client knows where
        #    the stream is.
        await ws.send_json(WSMessage(
            v=PROTOCOL_VERSION,
            type=SERVER_HELLO,
            seq=client_seq,
            payload={
                "server_version": "0.1.0",
                "protocol_version": PROTOCOL_VERSION,
                "subscribed_game_id": game_id,
                "authed_player_id": player.id,
                "current_seq": client_seq,
                "heartbeat_sec": HEARTBEAT_SEC,
                "supports_replay": True,
            },
        ).to_wire())

        # 2. Initial state snapshot so the client has the full game to
        #    render. Reuse the same _build_state() helper the /state REST
        #    endpoint uses so the wire shape matches exactly. If the build
        #    fails (e.g. game was deleted between auth and snapshot) we
        #    close with a clean error rather than hang.
        try:
            from app.database import AsyncSessionLocal
            from app.routes.game import _build_state
            async with AsyncSessionLocal() as ss:
                game = await ss.get(Game, game_id)
                if game is None:
                    await _send_error(ws, "GAME_NOT_FOUND",
                                      f"game {game_id} disappeared")
                    return
                snapshot = await _build_state(ss, game)
            await ws.send_json(WSMessage(
                v=PROTOCOL_VERSION,
                type=STATE_SNAPSHOT,
                seq=client_seq,
                payload={"game": snapshot.model_dump(mode="json")},
            ).to_wire())
        except Exception:  # noqa: BLE001
            logger.exception("WS gateway: state.snapshot build failed for game=%d", game_id)
            await _send_error(ws, "INTERNAL", "failed to build initial snapshot")
            return

        # 3. Replay missed events from the ring buffer.
        replayed = 0
        for seq, ev in _replay.get(game_id, []):
            if seq > since_seq and ev.game_id == game_id:
                await ws.send_json(_event_to_message(ev, seq))
                replayed += 1
        if replayed:
            logger.info("WS gateway replayed %d events for game=%d player=%d",
                        replayed, game_id, player.id)

        # 3. Live stream until client disconnects.
        while True:
            ev = await queue.get()
            # Real seq is the global counter (only fire-and-store here
            # so the next reconnect can rewind from here).
            real_seq = _next_seq(game_id)
            _remember_event(game_id, real_seq, ev)
            await ws.send_json(_event_to_message(ev, real_seq))
    except WebSocketDisconnect:
        logger.info("WS gateway disconnected: game=%d player=%d", game_id, player.id)
    except Exception:  # noqa: BLE001
        logger.exception("WS gateway error: game=%d player=%d", game_id, player.id)
    finally:
        heartbeat_task.cancel()
        bus.unsubscribe(game_id, queue)
        # 2026-07-13: auto-capture suspend on WS disconnect.  When a
        # player's WS drops mid-battle (browser closed, network died,
        # tab crashed), we write a SuspendState so the player can
        # resume from where they left off.  See save-design-v2.md §2.3
        # and SuspendPoint.DISCONNECT.
        #
        # Awaits inline (rather than fire-and-forget): the WS test
        # harness runs the handler on a separate event loop from the
        # test's main loop, so a fire-and-forget task would never be
        # observable from the test.  In production the additional
        # ~5-20 ms before close is acceptable for the
        # "browser-closed-and-comes-back" UX guarantee.
        try:
            await _capture_disconnect_suspend(
                user_name=player.user_name, game_id=game_id,
            )
        except Exception:  # noqa: BLE001
            logger.exception("WS gateway: disconnect suspend handler failed")
        try:
            await ws.close()
        except Exception:  # noqa: BLE001
            pass


async def _capture_disconnect_suspend(*, user_name: str, game_id: int) -> None:
    """Write a SuspendState when a player's WS connection drops.

    Called from the WS gateway's finally block.  Opens a fresh DB
    session (the one in the WS handler is already closed) and:

      1. Re-loads the game; if it has been force-ended (status !=
         "playing") or deleted, skip — there's nothing to suspend.
      2. Captures only the *meta* snapshot (game_id, mainline_id,
         battle_id, suspend_point).  The full game state lives in
         the live Game/Player/Unit/Tile rows already; the suspend
         row is a pointer that tells the loader "go re-fetch this
         game" rather than a duplicate of the state.
      3. Calls ``SaveService.capture_suspend``.

    Critical invariant: this function does **not** touch
    ``hero_campaign_states`` or any other long-term profile column.
    See ``app.save.service.SaveService.capture_suspend`` for the
    snapshot shape and the FE8-style cascade rules.
    """
    try:
        from app.database import AsyncSessionLocal
        from app.models import Game
        from app.save import SaveService
        from app.save.models import SuspendPoint

        async with AsyncSessionLocal() as session:
            game = await session.get(Game, game_id)
            if game is None or game.status != "playing":
                logger.info(
                    "WS disconnect: skipping suspend — game=%d status=%s",
                    game_id, getattr(game, "status", "<missing>"),
                )
                return
            # Pull mainline_id + battle_id out of the name.  Mainline
            # games are named "mainline:<id>:<battle_id>"; for
            # non-mainline games we leave the fields empty.
            name = game.name or ""
            if name.startswith("mainline:"):
                parts = name.split(":")
                mainline_id = parts[1] if len(parts) > 1 else ""
                battle_id = parts[-1] if len(parts) > 2 else ""
            else:
                mainline_id = ""
                battle_id = name

            svc = SaveService(session)
            await svc.capture_suspend(
                user_name=user_name,
                game_id=game_id,
                mainline_id=mainline_id,
                battle_id=battle_id,
                suspend_point=SuspendPoint.DISCONNECT,
                # Snapshot is a meta pointer — see docstring.  The
                # actual game state is re-fetched on resume via
                # /games/{id}/state.
                game_state={
                    "kind": "live_state_pointer",
                    "game_id": game_id,
                    "note": (
                        "state re-fetched on resume from /games/{id}/state"
                    ),
                },
            )
            await session.commit()
            logger.info(
                "WS disconnect suspend ok: user=%s game=%d battle=%s",
                user_name, game_id, battle_id,
            )
    except Exception:  # noqa: BLE001
        # Suspend is best-effort.  A failure here means the player
        # can't auto-resume; they'll see the Game row still in
        # "playing" state and can rejoin via the existing
        # /rejoin_by_name endpoint.
        logger.exception(
            "WS disconnect suspend FAILED: user=%s game=%d",
            user_name, game_id,
        )


def _event_to_message(ev: "GameEvent", seq: int) -> dict:
    """Render a GameEvent as a WSMessage envelope for delivery."""
    return WSMessage(
        v=PROTOCOL_VERSION,
        type=EVENT_DELTA,
        seq=seq,
        payload={
            "game_id": ev.game_id,
            "turn": ev.turn,
            "event_type": ev.type,
            "actor_unit_id": ev.actor_unit_id,
            "actor_name": ev.actor_name,
            "target_unit_id": ev.target_unit_id,
            "target_name": ev.target_name,
            "context": ev.context,
            "importance": ev.importance,
            "original_timestamp_ms": ev.timestamp_ms,
        },
    ).to_wire()


__all__ = ["router"]
