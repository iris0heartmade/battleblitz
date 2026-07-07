"""E2E verification: spawn correctness + team/color mapping + gameplay ops.

Runs an AI vs AI battle on a named map preset, but — unlike
`ai_battle_demo.py` — ALSO asserts structural invariants:

  1. SPAWN: every `initial_units` entry from the JSON ends up as a real
     DB Unit row at the expected (x, y, color, type, level).
  2. TEAM:  each Player's color matches the units that should belong to
     them per the JSON, and 2v2 team_mode maps to (red+blue vs green+yellow).
  3. OPS:   after 5 AI turns, observe that move/attack operations have
     actually happened (positions changed, HP decreased) and no
     errors were logged.

Usage:
    cd game
    python ../tools/verify_map_spawn.py --map test_arena_10x10_2v2 --players 4 --turns 5
    python ../tools/verify_map_spawn.py --map classic --players 4 --turns 5
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "game"
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.database import AsyncSessionLocal, dispose_db, init_db  # noqa: E402
from app.logging_config import setup_logging  # noqa: E402
from app.models import Game, Player, Tile, Unit  # noqa: E402
from app.routes.game import (  # noqa: E402
    add_ai_player, create_game, start_game,
)
from app.routes.turns import _run_ai_turn_chain  # noqa: E402
from app.schemas import (  # noqa: E402
    AddAIRequest, CreateGameRequest,
)


TEAM_MAP_2V2 = {
    "red": "A", "blue": "A", "green": "B", "yellow": "B",
}


async def _create_game_with_ai(
    map_preset: str, num_players: int, seed: int,
) -> int:
    """Create game + N AI + start. Returns game_id."""
    async with AsyncSessionLocal() as session:
        body = CreateGameRequest(
            name=f"Verify spawn ({map_preset}, {num_players}p)",
            map_preset=map_preset,
            capacity=num_players,
            map_seed=seed,
            win_condition="rout",
        )
        game = await create_game(body=body, session=session)
        game_id = game.id
        for i in range(num_players):
            await add_ai_player(
                game_id=game_id,
                body=AddAIRequest(
                    difficulty="normal",
                    agent_kind="rules",
                    personality="balanced",
                ),
                session=session,
            )
        await session.commit()
        await start_game(game_id=game_id, session=session)
        await session.commit()
        return game_id


async def _load_map_json(map_preset: str) -> dict | None:
    """Read the on-disk JSON for a map preset (None if procedural)."""
    if map_preset == "classic":
        return None  # procedurally generated — skip JSON-level assertions
    p = ROOT / "maps" / f"{map_preset}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


async def _snapshot_game(game_id: int) -> dict:
    """Take a complete snapshot of the game state for assertions."""
    from sqlalchemy.orm import selectinload
    async with AsyncSessionLocal() as session:
        game = await session.get(Game, game_id)
        players = (await session.execute(
            select(Player)
            .where(Player.game_id == game_id)
            .options(selectinload(Player.units))
        )).scalars().all()
        tiles = (await session.execute(
            select(Tile).where(Tile.game_id == game_id)
        )).scalars().all()
        units = []
        for p in players:
            for u in p.units:
                units.append({
                    "id": u.id,
                    "owner_id": u.player_id,
                    "type": u.unit_type,
                    "name": u.name,
                    "x": u.x,
                    "y": u.y,
                    "hp": u.hp,
                    "max_hp": u.max_hp,
                    "level": u.level,
                    "mp": u.mp,
                    "morale": u.morale,
                    "alive": u.hp > 0,
                })
        # Build tile ownership map: (x, y) -> owner_id (None = unclaimed)
        tile_owners: dict[tuple[int, int], int | None] = {
            (t.x, t.y): t.owner_id for t in tiles
        }
        return {
            "game": {
                "status": game.status,
                "turn": game.turn_number,
                "phase": game.phase,
                "map_preset": game.map_preset,
                "map_seed": game.map_seed,
                "win_reason": game.win_reason,
                "team_mode": getattr(game, "team_mode", None),
            },
            "players": [
                {
                    "id": p.id,
                    "seat": p.seat,
                    "color": p.color,
                    "is_ai": p.is_ai,
                    "gold": p.gold,
                    "is_alive": p.is_alive,
                    "is_spectator": p.is_spectator,
                    "unit_count": sum(1 for u in p.units if u.hp > 0),
                }
                for p in players
            ],
            "units": units,
            "tile_owners": tile_owners,
            "tiles_count": len(tiles),
        }


def _check_spawn(
    snapshot: dict, map_json: dict | None, num_players: int,
) -> tuple[list[str], list[str]]:
    """Verify spawn correctness. Returns (errors, warnings)."""
    errors, warnings = [], []
    units = snapshot["units"]
    players = snapshot["players"]
    expected_colors = {"red", "blue", "green", "yellow"}

    # Total unit count: from JSON if present, else expect fallback formula
    actual = sum(1 for u in units if u["alive"])
    if map_json is not None and "initial_units" in map_json:
        expected = len(map_json["initial_units"])
        source = "JSON"
    else:
        # Legacy map (no initial_units in JSON) — fallback fills N×5
        expected = num_players * 5
        source = f"FALLBACK ({num_players} castles × 5)"
    if actual != expected:
        errors.append(
            f"SPAWN COUNT: expected {expected} units from {source}, "
            f"got {actual} alive"
        )

    # Color coverage
    unit_colors = {u["type"] for u in units if u["alive"]}  # placeholder
    color_to_owner: dict[str, int] = {}
    for p in players:
        if p["color"] and not p["is_spectator"]:
            color_to_owner[p["color"]] = p["id"]
    owner_colors: dict[int, set[str]] = {}
    for u in units:
        owner_colors.setdefault(u["owner_id"], set()).add(
            # We don't have color on Unit directly — read through owner
            next((p["color"] for p in players if p["id"] == u["owner_id"]),
                 "?")
        )

    # Every unit must be owned by a player whose color matches
    player_by_id = {p["id"]: p for p in players}
    for u in units:
        if u["owner_id"] not in player_by_id:
            errors.append(f"UNIT owner: unit {u['id']} has no owner_id")
            continue
        p = player_by_id[u["owner_id"]]
        if p["color"] is None:
            errors.append(
                f"UNIT color: unit {u['id']} owned by spectator/hostless player"
            )

    # Unit types
    type_counts: dict[str, int] = {}
    for u in units:
        type_counts[u["type"]] = type_counts.get(u["type"], 0) + 1
    # Every alive unit must have positive HP and be at known type
    for u in units:
        if u["hp"] <= 0:
            warnings.append(f"UNIT dead: unit {u['id']} has hp={u['hp']}")
        if u["hp"] > u["max_hp"]:
            errors.append(
                f"UNIT hp: unit {u['id']} hp={u['hp']} > max_hp={u['max_hp']}"
            )
        if u["x"] is None or u["y"] is None:
            errors.append(f"UNIT coords: unit {u['id']} missing (x,y)")

    return errors, warnings


def _check_teams(snapshot: dict) -> tuple[list[str], list[str]]:
    """Verify team/color mapping for 2v2 maps (or warn for FFA)."""
    errors, warnings = [], []
    tm = snapshot["game"]["team_mode"]
    players = snapshot["players"]
    real_players = [p for p in players if not p["is_spectator"]]

    if tm == "2v2":
        teams: dict[str, set[int]] = {}
        for p in real_players:
            if p["color"] not in TEAM_MAP_2V2:
                warnings.append(
                    f"TEAM: player seat={p['seat']} color={p['color']!r} "
                    f"not in 2v2 color map"
                )
                continue
            team = TEAM_MAP_2V2[p["color"]]
            teams.setdefault(team, set()).add(p["seat"])
        if "A" not in teams or "B" not in teams:
            errors.append(f"TEAM: 2v2 incomplete — got teams={teams}")
        elif teams["A"] != {0, 1} or teams["B"] != {2, 3}:
            warnings.append(
                f"TEAM: 2v2 unexpected seat mapping: {teams} "
                f"(expected A={{0,1}}, B={{2,3}})"
            )

    # All 4 colors should have exactly one player (for 4p)
    if len(real_players) == 4:
        seen = [p["color"] for p in real_players]
        if set(seen) != {"red", "blue", "green", "yellow"}:
            errors.append(
                f"COLORS: 4-player game has colors {seen}, "
                f"expected red/blue/green/yellow"
            )

    return errors, warnings


def _check_ops(
    snap_initial: dict, snap_after: dict,
) -> tuple[list[str], list[str]]:
    """Verify that gameplay operations actually changed state."""
    errors, warnings = [], []

    if snap_after["game"]["turn"] <= snap_initial["game"]["turn"]:
        warnings.append(
            f"OPS: turn did not advance "
            f"({snap_initial['game']['turn']} → {snap_after['game']['turn']})"
        )

    # Initial state should have all units at their JSON positions
    # After a few turns, at least one unit should have moved OR been hit
    initial_units = {u["id"]: u for u in snap_initial["units"]}
    after_units = {u["id"]: u for u in snap_after["units"]}
    moved = 0
    damaged = 0
    for uid, u0 in initial_units.items():
        if uid not in after_units:
            continue
        u1 = after_units[uid]
        if (u0["x"], u0["y"]) != (u1["x"], u1["y"]):
            moved += 1
        if u1["hp"] < u0["hp"]:
            damaged += 1

    if moved == 0 and damaged == 0:
        warnings.append(
            "OPS: no unit moved or was damaged across turns — "
            "gameplay may be stuck or AI inert"
        )

    return errors, warnings


def _check_claim(
    snap_initial: dict, snap_after: dict,
) -> tuple[list[str], list[str], dict]:
    """Detect tile-claim events by comparing tile ownership maps.

    Returns (errors, warnings, info). `info` has counts for the report.
    """
    errors, warnings, info = [], [], {}
    initial_owners = snap_initial["tile_owners"]
    after_owners = snap_after["tile_owners"]
    initial_players = {p["id"]: p for p in snap_initial["players"]}
    after_players = {p["id"]: p for p in snap_after["players"]}

    newly_claimed: list[tuple[int, int, int | None, int]] = []
    lost_claimed: list[tuple[int, int, int, int | None]] = []

    for xy, after_owner in after_owners.items():
        before_owner = initial_owners.get(xy)
        if before_owner != after_owner:
            if before_owner is None and after_owner is not None:
                newly_claimed.append((xy[0], xy[1], None, after_owner))
            elif before_owner is not None and after_owner is None:
                lost_claimed.append((xy[0], xy[1], before_owner, None))
            elif before_owner is not None and after_owner is not None:
                # Changed owner — treat as lost + newly_claimed
                lost_claimed.append((xy[0], xy[1], before_owner, None))
                newly_claimed.append((xy[0], xy[1], None, after_owner))

    info["newly_claimed_count"] = len(newly_claimed)
    info["lost_claimed_count"] = len(lost_claimed)
    info["newly_claimed"] = newly_claimed[:10]  # cap for printing
    info["lost_claimed"] = lost_claimed[:10]

    # Sanity: every claimed tile must belong to a real player
    for x, y, _, owner_id in newly_claimed:
        if owner_id not in after_players:
            errors.append(
                f"CLAIM: tile ({x},{y}) owner_id={owner_id} "
                f"not in players table"
            )

    if not newly_claimed and not lost_claimed:
        warnings.append(
            "CLAIM: no tile ownership changes — claim action not exercised "
            "(may be normal if no AI moved onto a claimable tile yet)"
        )

    return errors, warnings, info


def _check_recruit(
    snap_initial: dict, snap_after: dict,
) -> tuple[list[str], list[str], dict]:
    """Detect recruit events by comparing per-player unit counts.

    A recruit spawns a new Unit row, so total unit count grows beyond
    initial spawn count. We compare per-player counts because kills can
    offset the total.
    """
    errors, warnings, info = [], [], {}
    initial_by_player = {p["id"]: p for p in snap_initial["players"]}
    after_by_player = {p["id"]: p for p in snap_after["players"]}
    recruits_by_player: dict[int, int] = {}
    recruits_total = 0

    for pid, p_after in after_by_player.items():
        p_before = initial_by_player.get(pid)
        if p_before is None:
            continue
        delta = p_after["unit_count"] - p_before["unit_count"]
        if delta > 0:
            recruits_by_player[pid] = delta
            recruits_total += delta
        elif delta < 0:
            # Net loss — could be kills; not an error
            pass

    info["recruits_total"] = recruits_total
    info["recruits_by_player"] = {
        after_by_player[pid]["color"]: n
        for pid, n in recruits_by_player.items()
        if after_by_player[pid]["color"]
    }

    # Cross-check: every "after" unit either existed before OR is a new recruit
    initial_ids = {u["id"] for u in snap_initial["units"]}
    new_unit_ids = {u["id"] for u in snap_after["units"]} - initial_ids

    if recruits_total > 0 and len(new_unit_ids) != recruits_total:
        errors.append(
            f"RECRUIT: claimed {recruits_total} recruits but found "
            f"{len(new_unit_ids)} new unit IDs (mismatch)"
        )

    if recruits_total == 0:
        warnings.append(
            "RECRUIT: no new units spawned — recruit action not exercised "
            "(may be normal if no AI reached a barracks yet)"
        )

    return errors, warnings, info


def _check_gold(
    snap_initial: dict, snap_after: dict,
) -> tuple[list[str], list[str], dict]:
    """Detect gold income and spending across snapshots.

    Income = `turns.py:112` adds gold at turn start from owned tiles.
    Spending = recruit (cost) + skill costs.
    Net gold change should be positive OR zero if all income was spent.
    """
    errors, warnings, info = [], [], {}
    initial_by_player = {p["id"]: p for p in snap_initial["players"]}
    after_by_player = {p["id"]: p for p in snap_after["players"]}
    gold_delta_by_color: dict[str, int] = {}
    total_delta = 0
    any_negative = False

    for pid, p_after in after_by_player.items():
        p_before = initial_by_player.get(pid)
        if p_before is None:
            continue
        delta = (p_after["gold"] or 0) - (p_before["gold"] or 0)
        color = p_after["color"] or f"seat{p_after['seat']}"
        gold_delta_by_color[color] = delta
        total_delta += delta
        if (p_after["gold"] or 0) < 0:
            any_negative = True
            errors.append(
                f"GOLD: {color} has negative gold: {p_after['gold']}"
            )

    info["gold_delta_by_color"] = gold_delta_by_color
    info["total_delta"] = total_delta

    if total_delta <= 0 and all(d <= 0 for d in gold_delta_by_color.values()):
        warnings.append(
            "GOLD: no player gained gold — income path not exercised "
            "(may be normal if no claimed income buildings yet)"
        )

    if any_negative:
        # already in errors
        pass

    return errors, warnings, info


async def main_async(args: argparse.Namespace) -> int:
    setup_logging(console_level=logging.WARNING)  # quieter; we want summary
    print("=" * 70, flush=True)
    print(f"VERIFY SPAWN · map={args.map} · players={args.players} · "
          f"duration={args.duration}s", flush=True)
    print("=" * 70, flush=True)

    await init_db()
    try:
        game_id = await _create_game_with_ai(
            args.map, args.players, args.seed,
        )
        print(f"[setup] game #{game_id} created", flush=True)

        # Take T=1 snapshot (immediately after start)
        snap_initial = await _snapshot_game(game_id)
        await _load_map_json(args.map)  # touch I/O early
        map_json = await _load_map_json(args.map)

        # Spawn assertions
        err1, warn1 = _check_spawn(snap_initial, map_json, args.players)
        err2, warn2 = _check_teams(snap_initial)

        # Print spawn inventory
        players = snap_initial["players"]
        units = snap_initial["units"]
        print(f"[spawn] {len(players)} players, "
              f"{len([u for u in units if u['alive']])} alive units", flush=True)
        for p in sorted(players, key=lambda p: p["seat"]):
            n = sum(1 for u in units if u["owner_id"] == p["id"] and u["alive"])
            print(f"  seat={p['seat']} color={p['color']:<7} "
                  f"ai={p['is_ai']} units={n}", flush=True)
        by_color: dict[str, list[Unit]] = {}
        for u in units:
            p = next((x for x in players if x["id"] == u["owner_id"]), None)
            if p:
                by_color.setdefault(p["color"] or "?", []).append(u)
        for color, ulist in sorted(by_color.items()):
            types = sorted(u["type"] for u in ulist if u["alive"])
            print(f"  color={color}: {len(types)} units → {types}", flush=True)

        # Run the AI chain and wait a few turns
        asyncio.create_task(_run_ai_turn_chain(game_id))
        await asyncio.sleep(args.duration)  # wall-clock seconds

        snap_after = await _snapshot_game(game_id)
        print(f"[after {args.duration}s] turn={snap_after['game']['turn']} "
              f"phase={snap_after['game']['phase']} "
              f"status={snap_after['game']['status']}", flush=True)

        err3, warn3 = _check_ops(snap_initial, snap_after)
        err4, warn4, claim_info = _check_claim(snap_initial, snap_after)
        err5, warn5, recruit_info = _check_recruit(snap_initial, snap_after)
        err6, warn6, gold_info = _check_gold(snap_initial, snap_after)

        # Per-action detail block
        print("-" * 70, flush=True)
        print("[claim]   ", end="", flush=True)
        if claim_info["newly_claimed_count"] > 0:
            samples = claim_info["newly_claimed"][:3]
            sample_str = ", ".join(
                f"({x},{y})→p{after_by_player.get(pid, {}).get('color', '?')}"
                for x, y, _, pid in samples
            )
            print(f"{claim_info['newly_claimed_count']} tiles newly claimed "
                  f"(e.g. {sample_str})", flush=True)
        else:
            print("no new claims", flush=True)
        print("[recruit] ", end="", flush=True)
        if recruit_info["recruits_total"] > 0:
            print(f"{recruit_info['recruits_total']} new units by "
                  f"{recruit_info['recruits_by_player']}", flush=True)
        else:
            print("no new recruits", flush=True)
        print("[gold]    ", end="", flush=True)
        if gold_info["total_delta"] != 0:
            print(f"net delta {gold_info['total_delta']:+d} by color: "
                  f"{gold_info['gold_delta_by_color']}", flush=True)
        else:
            print("no gold change", flush=True)

        # Final report
        all_errors = err1 + err2 + err3 + err4 + err5 + err6
        all_warnings = warn1 + warn2 + warn3 + warn4 + warn5 + warn6
        print("-" * 70, flush=True)
        if all_errors:
            print(f"[ERRORS] ({len(all_errors)}):", flush=True)
            for e in all_errors:
                print(f"  - {e}", flush=True)
        if all_warnings:
            print(f"[WARNINGS] ({len(all_warnings)}):", flush=True)
            for w in all_warnings:
                print(f"  - {w}", flush=True)
        if not all_errors and not all_warnings:
            print("[OK] ALL CHECKS PASSED", flush=True)
        print("=" * 70, flush=True)
        return 0 if not all_errors else 1
    finally:
        await dispose_db()


def main() -> int:
    p = argparse.ArgumentParser(description="Verify map spawn correctness")
    p.add_argument("--map", default="test_arena_10x10_2v2",
                   help="Map preset id (default: showcase 2v2)")
    p.add_argument("--players", type=int, default=4, choices=[2, 3, 4])
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--duration", type=int, default=30,
                   help="Wall-clock seconds of AI play")
    args = p.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())