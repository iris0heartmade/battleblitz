"""Focused verification of economy mechanics: claim / recruit / income.

The high-level `verify_map_spawn.py` exercises natural AI play, which is
too slow for economy events (claim takes 2 turns, income starts at turn
3, recruit needs gold accumulation). This script instead drives the
mechanics directly through the route functions, then asserts that:

  1. CLAIM:  Move unit onto an enemy-owned claimable tile, /claim
              twice (with a turn advance between), tile.owner_id
              flips to claiming player.
  2. RECRUIT: At an owned barracks, /recruit spawns a new Unit and
              deducts gold.
  3. GOLD:    Income accrues per turn based on owned tiles ×
              BUILDING_INCOME[*].amount.

Uses test_arena_10x10_2v2 — has 4 villages, 5 barracks, 4 vaults.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "game"
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.database import AsyncSessionLocal, dispose_db, init_db  # noqa: E402
from app.logging_config import setup_logging  # noqa: E402
from app.models import Game, Player, Tile, Unit  # noqa: E402
from app.routes.actions import (  # noqa: E402
    claim_tile, move_unit, recruit_unit,
)
from app.routes.game import (  # noqa: E402
    add_ai_player, create_game, join_game, start_game,
)
from app.routes.turns import _collect_income_for_player  # noqa: E402
from app.schemas import (  # noqa: E402
    AddAIRequest, ClaimRequest, CreateGameRequest, JoinGameRequest,
    MoveRequest, RecruitRequest,
)


async def _setup_game() -> int:
    async with AsyncSessionLocal() as session:
        body = CreateGameRequest(
            name="Economy verify",
            map_preset="test_arena_10x10_2v2",
            capacity=2,
            map_seed=42,
            win_condition="rout",
        )
        game = await create_game(body=body, session=session)
        game_id = game.id
        # Seat 0 = "verify_human" (is_ai=False so /move etc accept)
        await join_game(
            game_id=game_id,
            body=JoinGameRequest(user_name="verify_human", color="red"),
            session=session,
        )
        # Seat 1 = AI opponent
        await add_ai_player(
            game_id=game_id,
            body=AddAIRequest(
                difficulty="normal", agent_kind="rules",
                personality="balanced",
            ),
            session=session,
        )
        await session.commit()
        await start_game(game_id=game_id, session=session)
        # Force phase=player so the seat-0 action routes accept moves
        game = await session.get(Game, game_id)
        game.phase = "player"
        game.current_player_index = 0
        await session.commit()
        return game_id


async def _player_at(game_id: int, seat: int) -> Player | None:
    async with AsyncSessionLocal() as session:
        return (await session.execute(
            select(Player).where(
                Player.game_id == game_id, Player.seat == seat,
            ).options(selectinload(Player.units))
        )).scalars().first()


async def _tile_at(game_id: int, x: int, y: int) -> Tile | None:
    async with AsyncSessionLocal() as session:
        return (await session.execute(
            select(Tile).where(
                Tile.game_id == game_id, Tile.x == x, Tile.y == y,
            )
        )).scalars().first()


async def _all_units_for(game_id: int, player_id: int) -> list[Unit]:
    async with AsyncSessionLocal() as session:
        return list((await session.execute(
            select(Unit).join(Player, Unit.player_id == Player.id).where(
                Player.game_id == game_id, Unit.player_id == player_id,
            )
        )).scalars().all())


async def _move_onto(
    game_id: int, player_id: int, unit_id: int, tx: int, ty: int,
) -> str | None:
    """Move a unit; return None on success or error message on failure."""
    async with AsyncSessionLocal() as session:
        body = MoveRequest(
            player_id=player_id, unit_id=unit_id, to_x=tx, to_y=ty,
        )
        try:
            await move_unit(game_id=game_id, body=body, session=session)
            await session.commit()
            return None
        except Exception as e:
            await session.rollback()
            return str(e.detail) if hasattr(e, "detail") else str(e)


async def _advance_turn(game_id: int) -> None:
    """Bump current player + collect income + resolve pending claims."""
    from app.game_logic import check_pending_claims
    async with AsyncSessionLocal() as session:
        game = await session.get(Game, game_id)
        players = (await session.execute(
            select(Player).where(Player.game_id == game_id)
        )).scalars().all()
        game.current_player_index = (
            (game.current_player_index + 1) % len(players)
        )
        if game.current_player_index == 0:
            game.turn_number += 1
        current = next(
            p for p in players if p.seat == game.current_player_index
        )
        await _collect_income_for_player(session, game, current)
        # Also flip any claim sessions whose completes_turn has passed
        await check_pending_claims(session, game)
        await session.commit()


async def _ensure_player_phase(game_id: int, seat: int) -> None:
    """Force phase=player and current_player_index=seat for direct control."""
    async with AsyncSessionLocal() as session:
        game = await session.get(Game, game_id)
        game.phase = "player"
        game.current_player_index = seat
        await session.commit()


def _sep(title: str) -> None:
    print("\n" + "=" * 70, flush=True)
    print(f"  {title}", flush=True)
    print("=" * 70, flush=True)


async def main_async(args: argparse.Namespace) -> int:
    setup_logging(console_level=logging.WARNING)
    print(f"VERIFY ECONOMY · map=test_arena_10x10_2v2 · 2 players",
          flush=True)

    await init_db()
    errors: list[str] = []
    try:
        game_id = await _setup_game()
        seat0 = await _player_at(game_id, 0)
        seat1 = await _player_at(game_id, 1)
        assert seat0 is not None and seat1 is not None
        print(f"[setup] game #{game_id}, seat 0 = player {seat0.id}, "
              f"seat 1 = player {seat1.id}, starting gold = "
              f"{seat0.gold or 0}/{seat1.gold or 0}", flush=True)

        # Snapshot seat 0's owned claimable tiles (pre-assigned at start)
        async with AsyncSessionLocal() as session:
            all_tiles = (await session.execute(
                select(Tile).where(Tile.game_id == game_id)
            )).scalars().all()
        from app.config import BUILDING_INCOME
        seat0_owned = {
            t.terrain: sum(
                1 for x in all_tiles
                if x.owner_id == seat0.id and x.terrain == t.terrain
            )
            for t in all_tiles
            if t.owner_id == seat0.id and t.terrain in BUILDING_INCOME
        }
        seat0_rate = sum(
            BUILDING_INCOME[ter]["amount"] * count
            for ter, count in seat0_owned.items()
        )
        print(f"[snapshot] seat 0 owns: {seat0_owned}", flush=True)
        print(f"[snapshot] seat 0 income rate: {seat0_rate} gold/turn",
              flush=True)

        # ============================================================
        # STEP 1: CLAIM — take a tile from seat 1
        # ============================================================
        _sep("STEP 1: CLAIM (seat 0 takes a tile from seat 1)")
        # Find a barracks owned by seat 1
        target = next(
            (t for t in all_tiles
             if t.terrain == "barracks" and t.owner_id == seat1.id),
            None,
        )
        if target is None:
            errors.append("CLAIM: no enemy barracks to test capture against")
        else:
            tx, ty = target.x, target.y
            print(f"  target: enemy barracks at ({tx},{ty})", flush=True)
            # Pick seat 0's nearest unit (Manhattan distance)
            units = sorted(
                seat0.units, key=lambda u: u.id,
            )
            mover = min(
                units, key=lambda u: abs(u.x - tx) + abs(u.y - ty),
            )
            print(f"  mover: {mover.name} at ({mover.x},{mover.y}), "
                  f"mp={mover.mov}", flush=True)

            # Walk the unit toward target by 1 tile per step.
            # Each step: pick the adjacent tile that's closest to (tx, ty).
            for step in range(20):
                # Re-fetch mover from DB so we see the latest position
                units = await _all_units_for(game_id, seat0.id)
                mover = next(u for u in units if u.id == mover.id)
                if (mover.x, mover.y) == (tx, ty):
                    break
                # Find best adjacent direction
                best = None
                best_dist = abs(mover.x - tx) + abs(mover.y - ty)
                for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                    nx, ny = mover.x + dx, mover.y + dy
                    d = abs(nx - tx) + abs(ny - ty)
                    if d < best_dist:
                        best_dist = d
                        best = (nx, ny)
                if best is None:
                    print(f"  step {step}: stuck at "
                          f"({mover.x},{mover.y}), no improvement",
                          flush=True)
                    break
                err = await _move_onto(game_id, seat0.id, mover.id, *best)
                if err:
                    print(f"  step {step}: move to {best} failed: {err}",
                          flush=True)
                    break
                print(f"  step {step}: moved to {best}", flush=True)
            # Refresh mover position
            units = await _all_units_for(game_id, seat0.id)
            mover = next(u for u in units if u.id == mover.id)
            print(f"  mover now at ({mover.x},{mover.y})", flush=True)

            if (mover.x, mover.y) != (tx, ty):
                errors.append(
                    f"CLAIM: mover stopped at ({mover.x},{mover.y}) — "
                    f"can't reach ({tx},{ty})"
                )
            else:
                # CLAIM TURN 1: start session
                async with AsyncSessionLocal() as session:
                    body = ClaimRequest(
                        player_id=seat0.id, unit_id=mover.id,
                    )
                    try:
                        r1 = await claim_tile(
                            game_id=game_id, body=body, session=session,
                        )
                        await session.commit()
                        print(f"  claim-1: completed={r1.completed}",
                              flush=True)
                    except Exception as e:
                        await session.rollback()
                        errors.append(f"CLAIM-1: {e}")
                        r1 = None

                # Advance turn + claim-2 to flip ownership
                flipped = False
                for attempt in range(5):
                    await _advance_turn(game_id)
                    async with AsyncSessionLocal() as session:
                        body = ClaimRequest(
                            player_id=seat0.id, unit_id=mover.id,
                        )
                        try:
                            r2 = await claim_tile(
                                game_id=game_id, body=body,
                                session=session,
                            )
                            await session.commit()
                            if r2.completed:
                                print(f"  claim-2: completed=True "
                                      f"(attempt {attempt + 1})",
                                      flush=True)
                                flipped = True
                                break
                        except Exception:
                            await session.rollback()
                tnow = await _tile_at(game_id, tx, ty)
                print(f"  tile owner now: {tnow.owner_id}", flush=True)
                if tnow.owner_id == seat0.id:
                    print(f"  [OK] CLAIM worked — barracks now owned by seat 0",
                          flush=True)
                else:
                    errors.append(
                        f"CLAIM: tile.owner_id={tnow.owner_id}, "
                        f"expected {seat0.id}"
                    )

        # ============================================================
        # STEP 2: GOLD — income accrues per turn
        # ============================================================
        _sep("STEP 2: GOLD (income)")
        # Advance 3 turns, count gold gained.
        # Re-snapshot rate (seat 0 now owns the claimed barracks too)
        async with AsyncSessionLocal() as session:
            all_tiles = (await session.execute(
                select(Tile).where(Tile.game_id == game_id)
            )).scalars().all()
        seat0_owned_v2 = {
            t.terrain: sum(
                1 for x in all_tiles
                if x.owner_id == seat0.id and x.terrain == t.terrain
            )
            for t in all_tiles
            if t.owner_id == seat0.id and t.terrain in BUILDING_INCOME
        }
        rate = sum(
            BUILDING_INCOME[ter]["amount"] * count
            for ter, count in seat0_owned_v2.items()
        )
        print(f"  seat 0 owns: {seat0_owned_v2}, rate = {rate} gold/turn",
              flush=True)

        # Gold before/after 4 turn cycles (4 because each player gets 1 turn)
        seat0 = await _player_at(game_id, 0)
        gold_before = seat0.gold or 0
        print(f"  gold before cycles: {gold_before}", flush=True)
        for _ in range(4):
            await _advance_turn(game_id)
        seat0 = await _player_at(game_id, 0)
        gold_after = seat0.gold or 0
        print(f"  gold after 4 cycles: {gold_after}", flush=True)
        delta = gold_after - gold_before
        print(f"  delta: {delta:+d} (expected ~{rate * 2} since 2 of 4 "
              f"advances land on seat 0's turn)", flush=True)
        if rate == 0:
            errors.append("GOLD: seat 0 has no income tiles — setup issue")
        elif delta < rate:
            errors.append(
                f"GOLD: expected at least +{rate} over 2 of seat 0's turns, "
                f"got +{delta}"
            )
        else:
            print(f"  [OK] GOLD income works", flush=True)

        # ============================================================
        # STEP 3: RECRUIT — spend gold at owned barracks
        # ============================================================
        _sep("STEP 3: RECRUIT")
        # Find a barracks owned by seat 0
        async with AsyncSessionLocal() as session:
            own_barracks = (await session.execute(
                select(Tile).where(
                    Tile.game_id == game_id,
                    Tile.terrain == "barracks",
                    Tile.owner_id == seat0.id,
                )
            )).scalars().all()
        print(f"  barracks owned by seat 0: "
              f"{[(b.x, b.y) for b in own_barracks]}", flush=True)
        if not own_barracks:
            errors.append("RECRUIT: no owned barracks — can't test")
        else:
            recruit_b = own_barracks[0]
            # Move any occupant off the barracks
            async with AsyncSessionLocal() as session:
                occ = (await session.execute(
                    select(Unit).join(Player, Unit.player_id == Player.id).where(
                        Player.game_id == game_id,
                        Unit.x == recruit_b.x,
                        Unit.y == recruit_b.y,
                    )
                )).scalars().first()
            if occ is not None:
                for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                    err = await _move_onto(
                        game_id, seat0.id, occ.id,
                        recruit_b.x + dx, recruit_b.y + dy,
                    )
                    if err is None:
                        break

            from app.config import RECRUIT_COST
            # Pick cheapest unit
            unit_type, cost = min(RECRUIT_COST.items(), key=lambda kv: kv[1])
            seat0 = await _player_at(game_id, 0)
            gold_now = seat0.gold or 0
            # Force phase=player so the recruit action is accepted
            await _ensure_player_phase(game_id, 0)
            print(f"  cheapest recruit: {unit_type} cost={cost}, "
                  f"player gold={gold_now}", flush=True)
            if gold_now < cost:
                print(f"  gold insufficient — auto-granting 500 for test",
                      flush=True)
                async with AsyncSessionLocal() as session:
                    p = await session.get(Player, seat0.id)
                    p.gold = (p.gold or 0) + 500
                    await session.commit()

            units_before = await _all_units_for(game_id, seat0.id)
            count_before = sum(1 for u in units_before if u.hp > 0)

            async with AsyncSessionLocal() as session:
                body = RecruitRequest(
                    player_id=seat0.id,
                    tile_x=recruit_b.x,
                    tile_y=recruit_b.y,
                    unit_type=unit_type,
                )
                try:
                    res = await recruit_unit(
                        game_id=game_id, body=body, session=session,
                    )
                    await session.commit()
                    print(f"  recruit result: new_unit_id={res.new_unit_id}, "
                          f"gold_remaining={res.gold_remaining}",
                          flush=True)
                    units_after = await _all_units_for(game_id, seat0.id)
                    count_after = sum(1 for u in units_after if u.hp > 0)
                    expected_gold = (seat0.gold or 0) - cost
                    if count_after != count_before + 1:
                        errors.append(
                            f"RECRUIT: unit count {count_before}→{count_after},"
                            f" expected +1"
                        )
                    elif res.gold_remaining != expected_gold:
                        errors.append(
                            f"RECRUIT: gold deducted wrong — "
                            f"reported {res.gold_remaining}, expected "
                            f"{expected_gold} (player.gold {seat0.gold} - "
                            f"cost {cost})"
                        )
                    else:
                        print(f"  [OK] RECRUIT worked — "
                              f"+1 unit, -{cost} gold", flush=True)
                except Exception as e:
                    await session.rollback()
                    errors.append(f"RECRUIT: {e}")

        # ============================================================
        # RESULT
        # ============================================================
        _sep("RESULT")
        if errors:
            print(f"[FAIL] {len(errors)} error(s):", flush=True)
            for e in errors:
                print(f"  - {e}", flush=True)
        else:
            print("[OK] all 3 economy mechanics verified", flush=True)
        return 1 if errors else 0
    finally:
        await dispose_db()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--timeout", type=int, default=120)
    args = p.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())