#!/usr/bin/env python3
"""chapter_06 event-stream end-to-end verifier (07-21 F5C).

Runs the real backend, drives chapter_06 through apply_end_of_turn,
and verifies the event log contains the expected design-driven events.
No hand-written events — everything goes through F5B triggers.
"""
from __future__ import annotations
import argparse, asyncio, json, sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "game"))
from app.events.bus import bus


async def _drive(log_path):
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.database import init_db, dispose_db, AsyncSessionLocal
    from app.mainline import clear_cache
    from app.models import Game
    from app.game_logic import apply_end_of_turn as aet
    from app.events import bus

    bus.set_file_logger(str(log_path))
    try:
        await init_db()
        clear_cache()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            await c.post("/progression/profiles", json={"user_name": "v"})
            r = await c.post("/mainlines/chapter_06_iron_reckoning/start",
                             json={"user_name": "v", "skip_intro": True})
            gid = int(r.json()["game_id"])

            # Wave test (turn 3)
            async with AsyncSessionLocal() as s:
                g = await s.get(Game, gid)
                g.turn_number = 3; await s.commit()
            async with AsyncSessionLocal() as s:
                g = await s.get(Game, gid); await aet(s, g)

            # Trap test (move unit to 8,4; turn 9)
            async with AsyncSessionLocal() as s:
                from sqlalchemy import select
                from app.models import Player, Unit
                red = (await s.execute(
                    select(Player).where(Player.game_id == gid, Player.color == "red")
                )).scalars().first()
                if red:
                    u = (await s.execute(
                        select(Unit).where(Unit.player_id == red.id)
                    )).scalars().first()
                    if u:
                        u.x = 8; u.y = 4; await s.commit()
                g = await s.get(Game, gid)
                g.turn_number = 9; await s.commit()
            async with AsyncSessionLocal() as s:
                g = await s.get(Game, gid); await aet(s, g)

        await dispose_db()
    finally:
        bus.close_file_logger()


def _verify(log_path):
    results = []
    if not log_path.exists():
        return [("file.exists", False, "log missing")]
    raw = log_path.read_text(encoding="utf-8")
    lines = [json.loads(l) for l in raw.splitlines() if l.strip() and not l.startswith("===")]

    def he(t, **c):
        for o in lines:
            if o.get("type") == t and all(o.get(k) == v for k, v in c.items()):
                return (True, f"found {t}")
        return (False, f"no {t}")

    ok, d = he("match_start")
    results.append(("01.match_start", ok, d))
    ok, d = False, "no move with wave_turn=3"
    for o in lines:
        if o.get("type") == "move" and o.get("ctx", {}).get("wave_turn") == 3:
            ok, d = True, f"wave at ({o['ctx']['x']},{o['ctx']['y']})"; break
    results.append(("02.wave0.turn3", ok, d))
    ok, d = False, "no trap attack"
    for o in lines:
        if o.get("type") == "attack" and o.get("ctx", {}).get("trap") is True:
            ok, d = True, f"trap dmg={o['ctx'].get('dmg')}"; break
    results.append(("03.trap.8_4", ok, d))
    n = sum(1 for e in lines if e.get("type") == "move")
    results.append(("04.move_count_gt_0", n >= 1, f"got {n}"))
    n = sum(1 for e in lines if e.get("type") == "attack")
    results.append(("05.attack_count_gt_0", n >= 1, f"got {n}"))
    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--log", default=str(Path("game/.tmp/chapter_06_events.log")))
    args = p.parse_args()
    log_path = Path(args.log)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(_drive(log_path))
    print("=" * 50)
    results = _verify(log_path)
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"RESULT: {passed}/{len(results)}")
    for tid, ok, detail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {tid}: {detail}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
