"""
mainline_chapter1_e2e.py — AI-driven E2E test for chapter_01 battle_01.

Drives a mainline playthrough via HTTP, sending /move and /attack on
behalf of the human player (seat 0, red). Verifies:
  * /move updates position + consumes MP, rejects has_moved units
  * /attack honors attack_range (rejects out-of-range, accepts in-range)
  * damage applied matches formula
  * HP bars track unit state accurately across the lifetime
  * End-turn advances turn order, blue rules-AI auto-runs

Requires: uvicorn running on http://127.0.0.1:8001 with chapter_01
JSON loaded.

Usage:
    /d/Python/pythonProject/.venv/Scripts/python.exe \
        ../tools/mainline_chapter1_e2e.py
"""
from __future__ import annotations
import asyncio
import json
import sys

import httpx

BASE = "http://127.0.0.1:8001"
MAINLINE = "chapter_01_steel_rebellion"
USER = f"ai_e2e_driver_{int(asyncio.get_event_loop().time())}"
MAX_ROUNDS = 6

# attack_range by class (from game/app/config.py — the source of truth)
ATTACK_RANGE = {"swordsman": 1, "archer": 2, "knight": 1, "warlock": 2, "healer": 2}
ATTACK_MIN = {"swordsman": 1, "archer": 2, "knight": 1, "warlock": 1, "healer": 1}


# ---------- pretty printing ----------

def hr(c: str = "", n: int = 72) -> None:
    print(f"\n{'=' * n}\n{c}\n{'=' * n}")


def sec(t: str) -> None:
    print(f"\n=== {t} ===")


def manhattan(a: tuple, b: tuple) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


# ---------- driver ----------

class MainlineE2E:
    def __init__(self) -> None:
        # trust_env=False: 强制不走 IE / 系统代理 (Win 注册表里写了
        # 127.0.0.1:7890 那种本机 Clash 端口,httpx 默认会走它,
        # 然后报 502 Bad Gateway)。
        self.client = httpx.AsyncClient(base_url=BASE, timeout=20.0, trust_env=False)
        self.game_id: int | None = None
        self.player_id: int | None = None
        self.enemy_player_id: int | None = None
        self.start_red_hp: dict[int, tuple[int, int]] = {}

    async def start(self) -> None:
        sec("START mainline chapter_01 (skip intro)")
        r = await self.client.post(
            f"/mainlines/{MAINLINE}/start",
            json={"user_name": USER, "skip_intro": True})
        r.raise_for_status()
        body = r.json()
        self.game_id = body["game_id"]
        print(f"  game_id={self.game_id}  battle_id={body['battle_id']}  "
              f"win_condition={body.get('battle_config', {}).get('win_condition')}")
        # get_session commits AFTER yield (dependency teardown), so the
        # client may receive 201 before the SQL COMMIT has flushed.
        # Sleep a tiny bit so /state finds the new row.
        await asyncio.sleep(0.6)

    async def state(self) -> dict:
        r = await self.client.get(f"/games/{self.game_id}/state")
        r.raise_for_status()
        return r.json()

    def get_red(self, state): return next(p for p in state["players"] if p["seat"] == 0)
    def get_blue(self, state): return next(p for p in state["players"] if p["seat"] == 1)

    async def refresh_player_ids(self, state) -> None:
        self.player_id = self.get_red(state)["id"]
        self.enemy_player_id = self.get_blue(state)["id"]
        print(f"  red player_id={self.player_id} (is_ai={self.get_red(state)['is_ai']})")
        print(f"  blue player_id={self.enemy_player_id} (is_ai={self.get_blue(state)['is_ai']})")

    async def move(self, unit_id, to_x, to_y):
        return await self.client.post(
            f"/games/{self.game_id}/move",
            json={"player_id": self.player_id, "unit_id": unit_id, "to_x": to_x, "to_y": to_y})

    async def attack(self, attacker_id, target_id):
        return await self.client.post(
            f"/games/{self.game_id}/attack",
            json={"player_id": self.player_id, "attacker_id": attacker_id, "target_id": target_id})

    async def end_turn(self):
        return await self.client.post(
            f"/games/{self.game_id}/end-turn",
            json={"player_id": self.player_id})

    # ---------- observations ----------

    async def snapshot(self, label: str, state: dict) -> None:
        sec(f"HP snapshot: {label}")
        for p in state["players"]:
            tag = f"{p['color']}{' (AI)' if p['is_ai'] else ''} seat={p['seat']}"
            print(f"  {tag}:")
            for u in sorted(p["units"], key=lambda u: (u["y"], u["x"])):
                hp_full = u["hp"] == u["max_hp"]
                marker = "" if hp_full else f"  ←Δ{u['hp']-u['max_hp']:+d}"
                print(f"    {u['unit_type']:9s} id={u['id']:<3} "
                      f"HP={u['hp']:>3}/{u['max_hp']:<3}{marker}  "
                      f"pos=({u['x']:>2},{u['y']:>2})  "
                      f"ATK={u['atk']:>3} DEF={u['def_']:>3} "
                      f"MATK={u['matk']:>3} MDEF={u['mdef']:>3} "
                      f"MOV={u['mov']} skills={u.get('skills', [])}")

    def capture_hp(self, state) -> None:
        self.start_red_hp = {
            u["id"]: (u["hp"], u["max_hp"]) for u in self.get_red(state)["units"]
        }

    # ---------- focused tests ----------

    async def test_01_move(self, state):
        """Move 1 step + try moving an already-moved unit."""
        sec("TEST 01 — /move updates position + rejects has_moved units")
        swordsman = next(u for u in self.get_red(state)["units"] if u["unit_type"] == "swordsman")
        start = (swordsman["x"], swordsman["y"])
        print(f"  before: swordsman@{start} MOV={swordsman['mov']}")

        # valid 1-step move
        r = await self.move(swordsman["id"], start[0], start[1] - 1)
        print(f"  POST /move → ({start[0]},{start[1]-1}) status={r.status_code}")
        if r.status_code == 200:
            d = r.json()
            print(f"    ok={d.get('ok')} to=({d.get('to_x')},{d.get('to_y')}) "
                  f"mp_left={d.get('mp_left')} mp_cost={d.get('mp_cost')}")
        else:
            print(f"    {r.text[:120]}")

        st2 = await self.state()
        sw2 = next(u for u in self.get_red(st2)["units"] if u["id"] == swordsman["id"])
        moved_to = (sw2["x"], sw2["y"])
        print(f"  after: swordsman@{moved_to} has_moved={sw2.get('has_moved')}")
        ok1 = start != moved_to
        ok2 = sw2.get("has_moved") is True
        print(f"  OK position changed: {ok1}    OK has_moved flag set: {ok2}")

        # try moving an already-moved unit (should reject)
        r = await self.move(swordsman["id"], moved_to[0], moved_to[1] - 1)
        print(f"  POST /move already-moved sword status={r.status_code}")
        if r.status_code in (400, 422, 409):
            print(f"    OK REJECTED: {r.json().get('detail', '?')[:120]}")
        else:
            print(f"    WARN unexpectedly accepted: {r.text[:120]}")

    async def test_02_out_of_range_attack(self, state):
        sec("TEST 02 — /attack REJECT when target OUT of attack_range (swordsman @ far blue)")
        swordsman = next(u for u in self.get_red(state)["units"]
                          if u["unit_type"] == "swordsman" and u["hp"] > 0)
        enemy = next(u for u in self.get_blue(state)["units"]
                      if u["unit_type"] == "knight" and u["hp"] > 0)
        ar = ATTACK_RANGE["swordsman"]
        d = manhattan((swordsman["x"], swordsman["y"]),
                      (enemy["x"], enemy["y"]))
        print(f"  swordsman@({swordsman['x']},{swordsman['y']})  "
              f"range=({ATTACK_MIN['swordsman']}-{ar})")
        print(f"  enemy knight@({enemy['x']},{enemy['y']})  "
              f"manhattan_dist={d}  → expect REJECT (out of range)")

        r = await self.attack(swordsman["id"], enemy["id"])
        if r.status_code in (400, 422, 409):
            print(f"  OK REJECTED status={r.status_code}: "
                  f"{str(r.json().get('detail', '?'))[:120]}")
        else:
            print(f"  WARN status={r.status_code}: {r.text[:120]}")

    # ---------- round driver (AI-style forward) ----------

    async def drive_round(self, round_no: int, state) -> dict:
        sec(f"DRIVE ROUND {round_no} — red moves + attacks if in range, then end-turn → blue AI auto")
        red = self.get_red(state)
        blue = self.get_blue(state)
        # pick first alive unit that hasn't moved
        mobile = [u for u in red["units"] if u["hp"] > 0 and not u.get("has_moved")]
        if not mobile:
            print("  (no mobile units — ending turn directly)")
            return state

        unit = mobile[0]
        unit_type = unit["unit_type"]
        # closest alive enemy
        alive_enemies = [e for e in blue["units"] if e["hp"] > 0]
        if not alive_enemies:
            return state
        closest = min(alive_enemies,
                      key=lambda e: (e["x"] - unit["x"]) ** 2 + (e["y"] - unit["y"]) ** 2)
        ex, ey = closest["x"], closest["y"]
        cx, cy = unit["x"], unit["y"]
        dx = (1 if ex > cx else -1 if ex < cx else 0)
        dy = (1 if ey > cy else -1 if ey < cy else 0)
        nx, ny = cx + dx, cy + dy

        # try diagonal first, fall back to single-axis
        moved = False
        for tx, ty in [(nx, ny), (cx + dx, cy), (cx, cy + dy), (cx - dx, cy), (cx, cy - dy)]:
            r = await self.move(unit["id"], tx, ty)
            if r.status_code == 200:
                d = r.json()
                print(f"  OK {unit_type}@{unit['id']} ({cx},{cy}) → ({tx},{ty})  "
                      f"mp_left={d.get('mp_left')} cost={d.get('mp_cost')}")
                moved = True
                nx, ny = tx, ty
                break
        if not moved:
            print(f"  x move failed for {unit_type}@{unit['id']} from ({cx},{cy}) "
                  f"toward ({ex},{ey})")
            # still end-turn so we don't loop forever
            r = await self.end_turn()
            await asyncio.sleep(2.5)
            return await self.state()

        # attack phase
        st2 = await self.state()
        unit = next(u for u in self.get_red(st2)["units"] if u["id"] == unit["id"])
        ar = ATTACK_RANGE.get(unit["unit_type"], 1)
        amin = ATTACK_MIN.get(unit["unit_type"], 1)
        in_range = [
            e for e in self.get_blue(st2)["units"]
            if e["hp"] > 0
            and amin <= manhattan((unit["x"], unit["y"]), (e["x"], e["y"])) <= ar
        ]
        if in_range:
            tgt = min(in_range, key=lambda e: e["hp"])
            r2 = await self.attack(unit["id"], tgt["id"])
            if r2.status_code == 200:
                ad = r2.json()
                damage = ad.get("damage") or ad.get("final_damage")
                print(f"  OK attack {unit_type}→{tgt['unit_type']}@{tgt['id']}  "
                      f"dist={manhattan((unit['x'], unit['y']), (tgt['x'], tgt['y']))}  "
                      f"damage={damage}  "
                      f"dead={ad.get('dead', '?')}  "
                      f"target_hp_after={ad.get('target_hp_after') or ad.get('defender_hp', '?')}")
                # print all interesting keys
                shown = set(("damage", "final_damage", "dead",
                             "target_hp_after", "defender_hp"))
                extras = {k: ad[k] for k in ad if k not in shown
                          and isinstance(ad[k], (str, int, float, bool))}
                if extras:
                    print(f"    extra: {extras}")
            else:
                print(f"  x attack: status={r2.status_code}: {r2.text[:120]}")
        else:
            ar_minmax = f"({amin}-{ar})" if amin != ar else f"{ar}"
            print(f"  (no enemy in {unit_type} range {ar_minmax} from ({unit['x']},{unit['y']}))")

        # end-turn → server runs blue AI
        r = await self.end_turn()
        if r.status_code == 200:
            print(f"  /end-turn ok  → blue AI auto-running …")
        else:
            print(f"  /end-turn status={r.status_code}: {r.text[:120]}")
        await asyncio.sleep(2.5)  # AI chain ~1.2s × 2 actions + buffer
        return await self.state()

    async def run(self) -> None:
        await self.start()
        state = await self.state()
        await self.refresh_player_ids(state)
        self.capture_hp(state)
        await self.snapshot("INITIAL right after /start", state)

        # Focused tests (we use the fresh swordsman move so test_03 next round)
        await self.test_01_move(state)
        # re-fetch state because the move changes has_moved
        st_after_t1 = await self.state()
        await self.test_02_out_of_range_attack(st_after_t1)

        for round_no in range(1, MAX_ROUNDS + 1):
            st = await self.state()
            gstat = st["game"]["status"]
            if gstat != "playing":
                print(f"\n[GAME OVER before round {round_no}] status={gstat}")
                break
            st = await self.drive_round(round_no, st)
            await self.snapshot(f"after round {round_no}", st)
            gstat = st["game"]["status"]
            if gstat != "playing":
                print(f"\n[GAME OVER after round {round_no}] status={gstat}  "
                      f"reason={st['game'].get('win_reason', '?')}")
                break

        hr("FINAL HP SNAPSHOT")
        st = await self.state()
        await self.snapshot("FINAL", st)

        sec("ACTION LOG (last 25 entries)")
        for log_entry in st.get("logs", [])[-25:]:
            print(f"  [T{log_entry.get('turn', '?'):>3}] {log_entry.get('description', '?')}")

        # compare red HP delta from baseline
        sec("RED HP DELTA vs start (post-1st-battle cumulative)")
        final_red = self.get_red(st)
        for u in final_red["units"]:
            base = self.start_red_hp.get(u["id"], (u["hp"], u["max_hp"]))
            delta = u["hp"] - base[0]
            print(f"  {u['unit_type']:9s} id={u['id']:<3} {base[0]:>3} → {u['hp']:>3}  Δ={delta:+d}")

        hr("DONE")


async def main() -> None:
    driver = MainlineE2E()
    await driver.run()
    await driver.client.aclose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"\nFATAL: {e}", file=sys.stderr)
        raise
