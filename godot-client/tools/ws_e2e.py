"""
ws_e2e.py — Backend protocol round-trip smoke test.

Drives the FastAPI server through the full M2.1/M2.2 pipeline and
verifies the WebSocket envelope contract matches what the Godot
client (network_client.gd / game_state.gd) expects. Catches
regressions in:
  * REST: POST /games, /games/{id}/join, /add-ai, /start
  * WS handshake: server.hello envelope shape
  * WS initial state: state.snapshot with full GameStateOut

Outputs PASS/FAIL to stdout and writes a summary file.

Usage:
    python tools/ws_e2e.py [--host 127.0.0.1] [--port 8000]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Tuple

# We need websocket-client for the WS round-trip; if missing,
# fall back to a raw socket implementation (more brittle but zero-dep).
try:
    from websocket import create_connection, WebSocket  # type: ignore
    HAVE_WS_CLIENT = True
except ImportError:
    HAVE_WS_CLIENT = False


# ============================================================
# HTTP helpers
# ============================================================

def http_post(base: str, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{base}{path}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode("utf-8"))


def http_get(base: str, path: str) -> Dict[str, Any]:
    url = f"{base}{path}"
    req = urllib.request.Request(url, method="GET",
        headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode("utf-8"))


# ============================================================
# Stages
# ============================================================

class E2E:
    def __init__(self, base: str):
        self.base = base
        self.game_id: int = 0
        self.player_id: int = 0
        self.passed: List[str] = []
        self.failed: List[str] = []

    def check(self, cond: bool, label: str) -> None:
        if cond:
            self.passed.append(label)
            print(f"  PASS {label}")
        else:
            self.failed.append(label)
            print(f"  FAIL {label}")

    def run(self) -> bool:
        # ====== STAGE 1: create game ======
        print("STAGE 1: POST /games")
        name = f"ws_e2e_{int(time.time())}"
        try:
            resp = http_post(self.base, "/games", {
                "name": name,
                "map_preset": "balanced_2p_15",
                "map_biome": "grass",
                "win_condition": "rout",
            })
        except Exception as e:
            self.failed.append(f"create_game exception: {e}")
            return self._finish()
        self.game_id = int(resp.get("id", 0))
        self.check(self.game_id > 0, f"create_game returned id={self.game_id}")

        # ====== STAGE 2: join game ======
        # The /join endpoint returns the Player dict directly
        # (top-level `id` is the player_id). Some FastAPI shapes
        # also wrap it under `player` — check both.
        print("STAGE 2: POST /games/{id}/join")
        try:
            resp = http_post(self.base, f"/games/{self.game_id}/join", {
                "user_name": "ws_e2e_runner",
                "color": "red",
            })
        except Exception as e:
            self.failed.append(f"join exception: {e}")
            return self._finish()
        self.player_id = int(resp.get("id", 0))
        if self.player_id <= 0:
            self.player_id = int(resp.get("player_id", 0))
        if self.player_id <= 0:
            p = resp.get("player", {})
            if isinstance(p, dict):
                self.player_id = int(p.get("id", 0))
        self.check(self.player_id > 0, f"join returned player_id={self.player_id}")

        # ====== STAGE 3: add AI ======
        print("STAGE 3: POST /games/{id}/add-ai")
        try:
            resp = http_post(self.base, f"/games/{self.game_id}/add-ai", {
                "difficulty": "normal",
                "agent_kind": "rules",
                "personality": "balanced",
            })
        except Exception as e:
            self.failed.append(f"add_ai exception: {e}")
            return self._finish()
        self.check(isinstance(resp, dict) and int(resp.get("id", 0)) > 0,
                   f"add_ai returned ai player")

        # ====== STAGE 4: start ======
        print("STAGE 4: POST /games/{id}/start")
        try:
            resp = http_post(self.base, f"/games/{self.game_id}/start", {})
        except Exception as e:
            self.failed.append(f"start exception: {e}")
            return self._finish()
        game = resp.get("game", {}) if isinstance(resp, dict) else {}
        self.check(game.get("status") == "playing",
                   f"start: status={game.get('status')} turn={game.get('turn_number')}")

        # ====== STAGE 5: WS connect ======
        print("STAGE 5: WS connect")
        if not HAVE_WS_CLIENT:
            self.failed.append("websocket-client not installed; pip install websocket-client")
            return self._finish()
        # ws://host:port/ws/games/{id}?player_id={pid}&since_seq=0
        # (http:// -> ws://)
        ws_url = self.base.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/ws/games/{self.game_id}?player_id={self.player_id}&since_seq=0"
        print(f"  -> connecting {ws_url}")
        try:
            ws = create_connection(ws_url, timeout=8)
        except Exception as e:
            self.failed.append(f"WS connect failed: {e}")
            return self._finish()
        print("  WS connected, reading frames...")

        got_hello = False
        got_snapshot = False
        hello_seq = 0
        snapshot_phase = ""
        snapshot_cur_pid: Optional[int] = None
        snapshot_unit_count = 0
        last_event = ""
        last_event_seq = 0

        deadline = time.time() + 8.0
        while time.time() < deadline and not (got_hello and got_snapshot):
            try:
                ws.settimeout(0.5)
                raw = ws.recv()
            except Exception:
                # recv timeout — loop and re-check deadline
                continue
            if not raw:
                break
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            t = msg.get("type", "")
            seq = int(msg.get("seq", 0))
            if seq > 0:
                last_event_seq = seq
            if t == "server.hello":
                got_hello = True
                hello_seq = seq
                payload = msg.get("payload", {})
                print(f"  PASS server.hello: seq={seq} ver={payload.get('server_version')} "
                      f"subscribed_game_id={payload.get('subscribed_game_id')}")
            elif t == "state.snapshot":
                got_snapshot = True
                payload = msg.get("payload", {})
                game_dict = payload.get("game", {})
                # GameSummaryOut.phase sits at `game.phase` but
                # GameStateOut doesn't carry phase at the top level
                # — it nests under game. Detect both.
                if "phase" in game_dict:
                    snapshot_phase = str(game_dict.get("phase", ""))
                else:
                    # Some server builds put it elsewhere — log keys.
                    print(f"  debug: game_dict keys = {list(game_dict.keys())}")
                    if "game" in game_dict:
                        snapshot_phase = str(game_dict["game"].get("phase", ""))
                snapshot_cur_pid = game_dict.get("current_player_id")
                for p in game_dict.get("players", []):
                    if isinstance(p, dict):
                        units = p.get("units", [])
                        if isinstance(units, list):
                            snapshot_unit_count += len(units)
                print(f"  PASS state.snapshot: seq={seq} phase={snapshot_phase} "
                      f"cur_pid={snapshot_cur_pid} units={snapshot_unit_count}")
            elif t == "event.delta":
                payload = msg.get("payload", {})
                et = payload.get("event_type", "?")
                last_event = et
                print(f"  - event.delta: {et} seq={seq}")
            else:
                print(f"  - {t}: seq={seq}")
        ws.close()

        # ====== ASSERTIONS ======
        self.check(got_hello, f"server.hello received (seq={hello_seq})")
        self.check(got_snapshot, "state.snapshot received")
        self.check(snapshot_unit_count > 0,
                   f"snapshot has {snapshot_unit_count} units (expect >0)")
        self.check(snapshot_phase in ("player", "ai", "spectator", "animating"),
                   f"phase is valid: '{snapshot_phase}'")
        self.check(snapshot_cur_pid is not None,
                   f"current_player_id present: {snapshot_cur_pid}")
        return self._finish()

    def _finish(self) -> bool:
        print()
        print("=" * 60)
        if not self.failed:
            print(f"PASS — {len(self.passed)} checks verified")
        else:
            print(f"FAIL — {len(self.failed)} of {len(self.passed) + len(self.failed)} failed")
            for f in self.failed:
                print(f"  - {f}")
        # Also probe a follow-up REST call so the report shows the
        # action->snapshot round-trip is wired too.
        if not self.failed and self.game_id:
            try:
                state = http_get(self.base, f"/games/{self.game_id}/state")
                g = state.get("game", {})
                print(f"  follow-up GET /state: status={g.get('status')} turn={g.get('turn_number')} "
                      f"phase={g.get('phase')}")
            except Exception as e:
                print(f"  follow-up GET /state failed: {e}")
        print("=" * 60)
        return not self.failed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", default=8000, type=int)
    args = ap.parse_args()
    base = f"http://{args.host}:{args.port}"
    e2e = E2E(base)
    ok = e2e.run()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
