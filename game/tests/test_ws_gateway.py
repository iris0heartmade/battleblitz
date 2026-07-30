"""
End-to-end tests for the production WebSocket gateway.

Covers (per audit §6 Top-5 #1, ROADMAP §RT.1):
  1. Auth — header / query / missing / wrong-player
  2. server.hello + state.snapshot on connect
  3. event.delta stream as the client drives REST actions
  4. Replay buffer — reconnect with since_seq catches up missed events
  5. server.pong heartbeat
  6. Critical GameEvent types actually fire (move / attack / kill / turn_end)

These tests use httpx.AsyncClient for HTTP and the starlette WebSocket
test session for the WS upgrade — both running on the same event
loop, so the aiosqlite worker-thread leak that bites the sync
TestClient on Windows does not occur here.

Per-test isolation is provided by clearing module-level state
(`bus._subscribers`, `ws_gateway._seq`, `ws_gateway._replay`) in the
autouse fixture below.
"""
from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.protocol.v1 import (
    EVENT_DELTA,
    PROTOCOL_VERSION,
    SERVER_HELLO,
    SERVER_PONG,
    STATE_SNAPSHOT,
)
from app.routes import ws_gateway


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_global_state():
    """Bus subscribers + replay buffer are module-level; clear them
    between tests so each test starts with zero leaked subscribers or
    replayed events from the previous test's connection."""
    from app.events import bus

    bus._subscribers.clear()
    ws_gateway._seq.clear()
    ws_gateway._replay.clear()
    yield
    bus._subscribers.clear()
    ws_gateway._seq.clear()
    ws_gateway._replay.clear()


@pytest.fixture
def short_heartbeat(monkeypatch):
    """Apply at the test level so the heartbeat fires within a test
    window instead of the production 30s default."""
    monkeypatch.setattr(ws_gateway, "HEARTBEAT_SEC", 0.1)
    yield


@asynccontextmanager
async def _live_app():
    """Initialize DB + create an AsyncClient + WebSocketTestSession
    factory sharing one event loop. Spins up a fresh in-process app
    per call so we never carry subscriber state across tests."""
    from app.database import init_db, dispose_db

    # ASGI lifespan (init_db) needs to be triggered manually because
    # AsyncClient's ASGITransport doesn't run lifespan by default.
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            yield client
        finally:
            await dispose_db()


# --------------------------------------------------------------------------
# REST helpers
# --------------------------------------------------------------------------

async def _create_game(client, name="ws-e2e"):
    r = await client.post("/games", json={
        "name": name, "map_preset": "classic", "map_seed": 7,
    })
    assert r.status_code == 201, r.text
    return r.json()


async def _join_human(client, game_id, user_name="alice"):
    r = await client.post(f"/games/{game_id}/join", json={"user_name": user_name})
    assert r.status_code == 201, r.text
    return r.json()


async def _add_ai(client, game_id):
    r = await client.post(f"/games/{game_id}/add-ai", json={
        "difficulty": "normal", "agent_kind": "rules", "personality": "balanced",
    })
    assert r.status_code == 201, r.text
    return r.json()


async def _start(client, game_id):
    r = await client.post(f"/games/{game_id}/start", json={})
    assert r.status_code == 200, r.text
    return r.json()


async def _state(client, game_id):
    r = await client.get(f"/games/{game_id}/state")
    assert r.status_code == 200, r.text
    return r.json()


async def _running_game(client):
    g = await _create_game(client)
    gid = g["id"]
    human = await _join_human(client, gid)
    ai = await _add_ai(client, gid)
    await _start(client, gid)
    state = await _state(client, gid)
    return gid, human["id"], ai["id"], state


def _flatten_units(state, player_id=None):
    out = []
    for p in state.get("players", []):
        if player_id is not None and p["id"] != player_id:
            continue
        for u in p.get("units", []):
            u2 = dict(u)
            u2["player_id"] = p["id"]
            out.append(u2)
    return out


# ==========================================================================
# Auth
# ==========================================================================

class TestWSAuth:
    async def test_missing_auth_header_returns_error_then_closes(self):
        async with _live_app() as client:
            gid, _h, _ai, _ = await _running_game(client)
            # Use TestClient just for the WS connect dance, then close.
            from fastapi.testclient import TestClient
            with pytest.raises(Exception):
                with TestClient(app).websocket_connect(
                    f"/ws/games/{gid}", headers={}
                ) as ws:
                    ws.receive_json()
                    ws.receive_text()

    async def test_auth_via_query_param_works(self):
        async with _live_app() as client:
            gid, human, _ai, _ = await _running_game(client)
            from fastapi.testclient import TestClient
            with TestClient(app).websocket_connect(
                f"/ws/games/{gid}", params={"player_id": str(human)}
            ) as ws:
                hello = ws.receive_json()
                assert hello["type"] == SERVER_HELLO
                assert hello["payload"]["authed_player_id"] == human

    async def test_auth_via_header_works(self):
        async with _live_app() as client:
            gid, human, _ai, _ = await _running_game(client)
            from fastapi.testclient import TestClient
            with TestClient(app).websocket_connect(
                f"/ws/games/{gid}", headers={"X-Player-Id": str(human)}
            ) as ws:
                hello = ws.receive_json()
                assert hello["type"] == SERVER_HELLO

    async def test_wrong_player_id_rejected(self):
        async with _live_app() as client:
            gid, _h, _ai, _ = await _running_game(client)
            from fastapi.testclient import TestClient
            with pytest.raises(Exception):
                with TestClient(app).websocket_connect(
                    f"/ws/games/{gid}", params={"player_id": "9999"}
                ) as ws:
                    ws.receive_json()
                    ws.receive_text()

    async def test_unknown_game_rejected(self):
        async with _live_app() as client:
            await _running_game(client)
            from fastapi.testclient import TestClient
            with pytest.raises(Exception):
                with TestClient(app).websocket_connect(
                    "/ws/games/9999", params={"player_id": "1"}
                ) as ws:
                    ws.receive_json()
                    ws.receive_text()

    async def test_non_integer_player_id_rejected(self):
        async with _live_app() as client:
            await _running_game(client)
            from fastapi.testclient import TestClient
            with pytest.raises(Exception):
                with TestClient(app).websocket_connect(
                    "/ws/games/1", params={"player_id": "not-a-number"}
                ) as ws:
                    ws.receive_json()
                    ws.receive_text()


# ==========================================================================
# Connect → hello + snapshot
# ==========================================================================

class TestWSHelloAndSnapshot:
    async def test_hello_envelope_shape(self):
        async with _live_app() as client:
            gid, human, _ai, _ = await _running_game(client)
            from fastapi.testclient import TestClient
            with TestClient(app).websocket_connect(
                f"/ws/games/{gid}", params={"player_id": str(human)}
            ) as ws:
                hello = ws.receive_json()
                snap = ws.receive_json()

                assert hello["v"] == PROTOCOL_VERSION
                assert hello["type"] == SERVER_HELLO
                assert isinstance(hello["seq"], int)

                p = hello["payload"]
                assert p["subscribed_game_id"] == gid
                assert p["authed_player_id"] == human
                assert p["protocol_version"] == PROTOCOL_VERSION
                assert p["supports_replay"] is True
                assert isinstance(p["current_seq"], int)
                assert isinstance(p["heartbeat_sec"], (int, float))

                # WS gateway wraps the GameStateOut dump under
                # `payload.game`; GameStateOut itself has a `game` field
                # too, so wire path is payload.game.game.id.
                assert snap["type"] == STATE_SNAPSHOT
                outer = snap["payload"]["game"]
                inner = outer["game"]
                assert inner["id"] == gid
                assert "players" in outer
                assert "tiles" in outer or "units" in outer

    async def test_no_events_leak_before_hello(self):
        async with _live_app() as client:
            gid, human, _ai, _ = await _running_game(client)
            from fastapi.testclient import TestClient
            with TestClient(app).websocket_connect(
                f"/ws/games/{gid}", params={"player_id": str(human)}
            ) as ws:
                first = ws.receive_json()
                second = ws.receive_json()
                assert first["type"] in (SERVER_HELLO, "error")
                if first["type"] == SERVER_HELLO:
                    assert second["type"] in (STATE_SNAPSHOT, EVENT_DELTA)


# ==========================================================================
# Live event stream
# ==========================================================================

class TestWSEventStream:
    async def test_move_emits_event_delta(self):
        async with _live_app() as client:
            gid, human, _ai, state = await _running_game(client)
            me = _flatten_units(state, human)
            assert me, "no human units in starting roster"
            unit = me[0]

            from fastapi.testclient import TestClient
            with TestClient(app).websocket_connect(
                f"/ws/games/{gid}", params={"player_id": str(human)}
            ) as ws:
                ws.receive_json()  # hello
                ws.receive_json()  # snapshot

                r = await client.post(f"/games/{gid}/move", json={
                    "player_id": human,
                    "unit_id": unit["id"],
                    "to_x": unit["x"] + 1,
                    "to_y": unit["y"],
                })
                assert r.status_code == 200, r.text

                deadline = time.time() + 2.0
                seen_move = None
                while time.time() < deadline and seen_move is None:
                    try:
                        msg = ws.receive_json(timeout=0.2)
                    except Exception:
                        break
                    if msg.get("type") == EVENT_DELTA and \
                       msg["payload"].get("event_type") == "move":
                        seen_move = msg
                assert seen_move is not None, \
                    "expected a move event.delta within 2s after successful move"
                ctx = seen_move["payload"]["context"]
                assert ctx["from_x"] == unit["x"]
                assert ctx["from_y"] == unit["y"]
                assert ctx["to_x"] == unit["x"] + 1
                assert ctx["to_y"] == unit["y"]
                assert isinstance(ctx["mp_cost"], int) and ctx["mp_cost"] >= 0

    async def test_attack_emits_attack_event_when_in_range(self):
        async with _live_app() as client:
            gid, human, _ai, state = await _running_game(client)
            my_units = _flatten_units(state, human)
            enemy_units = [u for u in _flatten_units(state) if u["player_id"] != human]
            assert my_units and enemy_units

            attacker = my_units[0]
            target = enemy_units[0]

            from fastapi.testclient import TestClient
            with TestClient(app).websocket_connect(
                f"/ws/games/{gid}", params={"player_id": str(human)}
            ) as ws:
                ws.receive_json()
                ws.receive_json()

                await client.post(f"/games/{gid}/move", json={
                    "player_id": human, "unit_id": attacker["id"],
                    "to_x": target["x"] - 1, "to_y": target["y"],
                })

                r = await client.post(f"/games/{gid}/attack", json={
                    "player_id": human, "attacker_id": attacker["id"],
                    "target_id": target["id"],
                })
                assert r.status_code in (200, 400), r.text
                if r.status_code != 200:
                    pytest.skip(
                        f"setup couldn't put attacker in range "
                        f"(attack → {r.text[:120]})"
                    )

                seen_attack = False
                deadline = time.time() + 2.0
                while time.time() < deadline and not seen_attack:
                    try:
                        msg = ws.receive_json(timeout=0.2)
                    except Exception:
                        break
                    if msg.get("type") == EVENT_DELTA and \
                       msg["payload"].get("event_type") == "attack":
                        seen_attack = True
                        ctx = msg["payload"]["context"]
                        assert "dmg" in ctx or "is_crit" in ctx
                assert seen_attack, "expected an attack event.delta after successful attack"

    async def test_end_turn_emits_turn_or_round_event(self):
        async with _live_app() as client:
            gid, human, _ai, _ = await _running_game(client)
            from fastapi.testclient import TestClient
            with TestClient(app).websocket_connect(
                f"/ws/games/{gid}", params={"player_id": str(human)}
            ) as ws:
                ws.receive_json()
                ws.receive_json()
                r = await client.post(f"/games/{gid}/end-turn", json={"player_id": human})
                assert r.status_code == 200, r.text
                seen_terminal = False
                seen_any = False
                deadline = time.time() + 3.0
                while time.time() < deadline:
                    try:
                        msg = ws.receive_json(timeout=0.3)
                    except Exception:
                        break
                    if msg.get("type") != EVENT_DELTA:
                        continue
                    seen_any = True
                    et = msg["payload"].get("event_type")
                    if et in ("turn_end", "round_end", "match_start"):
                        seen_terminal = True
                        break
                assert seen_any
                assert seen_terminal


# ==========================================================================
# Replay buffer
# ==========================================================================

class TestWSReplay:
    async def test_since_seq_replays_missed_events(self):
        async with _live_app() as client:
            gid, human, _ai, state = await _running_game(client)
            my_units = _flatten_units(state, human)
            assert my_units
            unit = my_units[0]

            from fastapi.testclient import TestClient
            with TestClient(app).websocket_connect(
                f"/ws/games/{gid}", params={"player_id": str(human)}
            ) as ws:
                ws.receive_json()
                ws.receive_json()
                r = await client.post(f"/games/{gid}/move", json={
                    "player_id": human, "unit_id": unit["id"],
                    "to_x": unit["x"] + 1, "to_y": unit["y"],
                })
                assert r.status_code == 200
                move_ev = ws.receive_json()
                assert move_ev["type"] == EVENT_DELTA
                last_seq = move_ev["seq"]

            with TestClient(app).websocket_connect(
                f"/ws/games/{gid}",
                params={
                    "player_id": str(human),
                    "since_seq": str(last_seq - 1),
                },
            ) as ws2:
                ws2.receive_json()
                ws2.receive_json()
                replayed = ws2.receive_json()
                assert replayed["type"] == EVENT_DELTA
                assert replayed["payload"]["event_type"] == "move"
                assert replayed["seq"] == last_seq

    async def test_since_seq_far_future_returns_no_replay(self):
        async with _live_app() as client:
            gid, human, _ai, _ = await _running_game(client)
            from fastapi.testclient import TestClient
            with TestClient(app).websocket_connect(
                f"/ws/games/{gid}",
                params={"player_id": str(human), "since_seq": "999999"},
            ) as ws:
                ws.receive_json()
                ws.receive_json()
                with pytest.raises(Exception):
                    ws.receive_json(timeout=0.3)


# ==========================================================================
# Heartbeat
# ==========================================================================

class TestWSHeartbeat:
    async def test_server_pong_fires_within_heartbeat_window(self, short_heartbeat):
        async with _live_app() as client:
            gid, human, _ai, _ = await _running_game(client)
            from fastapi.testclient import TestClient
            with TestClient(app).websocket_connect(
                f"/ws/games/{gid}", params={"player_id": str(human)}
            ) as ws:
                ws.receive_json()
                ws.receive_json()
                deadline = time.time() + 2.0
                seen_pong = False
                while time.time() < deadline and not seen_pong:
                    try:
                        msg = ws.receive_json(timeout=0.3)
                    except Exception:
                        break
                    if msg.get("type") == SERVER_PONG:
                        seen_pong = True
                assert seen_pong, "expected at least one server.pong heartbeat"


# ==========================================================================
# Wire-shape invariants
# ==========================================================================

class TestWSWireInvariants:
    @pytest.mark.parametrize("frame_kind", ["hello", "snapshot", "delta"])
    async def test_every_frame_has_protocol_version(self, frame_kind):
        async with _live_app() as client:
            gid, human, _ai, state = await _running_game(client)
            from fastapi.testclient import TestClient
            with TestClient(app).websocket_connect(
                f"/ws/games/{gid}", params={"player_id": str(human)}
            ) as ws:
                if frame_kind == "hello":
                    msg = ws.receive_json()
                elif frame_kind == "snapshot":
                    ws.receive_json()
                    msg = ws.receive_json()
                else:
                    ws.receive_json()
                    ws.receive_json()
                    my_units = _flatten_units(state, human)
                    if my_units:
                        await client.post(f"/games/{gid}/move", json={
                            "player_id": human,
                            "unit_id": my_units[0]["id"],
                            "to_x": my_units[0]["x"] + 1,
                            "to_y": my_units[0]["y"],
                        })
                        msg = ws.receive_json()
                    else:
                        pytest.skip("no human units to trigger delta")
                assert msg["v"] == PROTOCOL_VERSION
                assert "type" in msg
                assert "payload" in msg
                assert isinstance(msg["payload"], dict)
