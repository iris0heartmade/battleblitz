"""
Turn-management routes: end-turn + background scheduler.

After every player in a game calls end-turn, the server resolves end-of-turn
effects (level up, dead-unit cleanup, win check) and advances to the next
player's seat.

A background asyncio task polls every `TURNS_CHECK_INTERVAL_SECONDS` for
players who haven't ended their turn within `TURN_TIMEOUT_HOURS` and
auto-skips them. It also emits periodic `HEALTH |` lines per the project's
logging standard.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    ABANDONED_FINISHED_HOURS,
    ABANDONED_LOBBY_MINUTES,
    AI_THINK_DELAY_SECONDS,
    INCOME_PER_TURN,
    INCOME_TERRAINS,
    LOBBY_CLEANUP_INTERVAL_SECONDS,
    TERRAIN_BARRACKS,
    TERRAIN_VILLAGE,
    CASTLE_VAULT,
    TURN_TIMEOUT_HOURS,
    TURNS_CHECK_INTERVAL_SECONDS,
)
from app.database import AsyncSessionLocal, get_session
from app.game_logic import ai_take_turn, ai_take_one_action, apply_end_of_turn, check_pending_claims
from app.logging_config import (
    collect_health_metrics,
    format_health_line,
    get_audit_logger,
    get_health_logger,
)
from app.models import ActionLog, Game, Player, Tile, Unit
from app.schemas import EndTurnRequest, EndTurnResult
from app.log_format import fmt_end_turn

logger = logging.getLogger(__name__)
audit = get_audit_logger()
health = get_health_logger()

router = APIRouter(prefix="/games", tags=["turns"])


# ============================================================
# Per-turn income (P0.4 economy)
# ============================================================

async def _collect_income_for_player(
    session: AsyncSession,
    game: Game,
    player: Player,
) -> Dict[str, int]:
    """Award gold to `player` for every tile they own that yields income.

    Called at the start of every player turn (not end-of-turn) so income
    fires once per round per player, regardless of how many turn-end calls
    happen between rounds. Returns a {terrain_id: count} breakdown for the
    ActionLog entry and the front-end toast.
    """
    rows = (
        await session.execute(
            select(Tile).where(
                Tile.game_id == game.id,
                Tile.owner_id == player.id,
            )
        )
    ).scalars().all()

    breakdown: Dict[str, int] = {}
    for tile in rows:
        if tile.terrain in INCOME_TERRAINS:
            breakdown[tile.terrain] = breakdown.get(tile.terrain, 0) + 1

    gold_gain = sum(
        INCOME_PER_TURN[t] * count for t, count in breakdown.items()
    )
    if gold_gain > 0:
        player.gold = (player.gold or 0) + gold_gain
        # Chinese description: "玩家 X 获得 +N 金币（来源：村落×2 + 金库×1）"
        source_str = " + ".join(
            f"{INCOME_TERRAIN_CN.get(t, t)}×{n}" for t, n in breakdown.items()
        )
        session.add(ActionLog(
            game_id=game.id,
            turn_number=game.turn_number,
            player_id=player.id,
            action_type="income",
            description=f"{player.user_name} 获得 +{gold_gain} 金币（{source_str}）",
        ))
    return breakdown


# Display names for income terrains in ActionLog descriptions.
INCOME_TERRAIN_CN: Dict[str, str] = {
    TERRAIN_VILLAGE:  "村落",
    TERRAIN_BARRACKS: "佣兵站",
    CASTLE_VAULT:     "金库",
}


# ============================================================
# End turn
# ============================================================

@router.post("/{game_id}/end-turn", response_model=EndTurnResult)
async def end_turn(
    game_id: int,
    body: EndTurnRequest,
    session: AsyncSession = Depends(get_session),
) -> EndTurnResult:
    game = await session.get(Game, game_id)
    if game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "游戏不存在")
    if game.status != "playing":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"游戏状态不是进行中（当前：{game.status}）")

    players = (
        await session.execute(select(Player).where(Player.game_id == game_id))
    ).scalars().all()
    if not players:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "此游戏没有玩家")

    player = next((p for p in players if p.id == body.player_id), None)
    if player is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "玩家不在此游戏中")
    if not player.is_alive:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "你已被淘汰")

    alive_seats = sorted(p.seat for p in players if p.is_alive)
    if not alive_seats:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "场上没有存活玩家")

    # Locate the expected current player
    expected_seat = next(
        (s for s in alive_seats if s >= game.current_player_index),
        alive_seats[0],
    )
    expected_player = next(p for p in players if p.seat == expected_seat)
    if player.id != expected_player.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "现在不是你的回合")

    # Count units that have acted (for the action log message)
    player_units = (
        await session.execute(
            select(Unit).where(Unit.player_id == player.id)
        )
    ).scalars().all()
    acted_count = sum(1 for u in player_units if u.has_acted)

    # Lock in the first-player handicap after they end their first turn.
    if player.seat == 0 and not game.first_player_done_first_turn:
        game.first_player_done_first_turn = True

    player.has_ended_turn = True
    session.add(
        ActionLog(
            game_id=game.id,
            turn_number=game.turn_number,
            player_id=player.id,
            action_type="end_turn",
            description=fmt_end_turn(player, acted_count),
        )
    )

    # P0.4: resolve any claim sessions whose completes_turn has arrived.
    # Runs at every end_turn; only sessions whose timer expired will flip.
    await check_pending_claims(session, game)
    audit.info(
        "USER_ACTION | user=player_%d | game=%d | action=END_TURN | result=SUCCESS | "
        "seat=%d | acted_count=%d | turn=%d",
        player.id, game_id, player.seat, acted_count, game.turn_number,
    )

    # Find next alive seat after the current one (with wrap-around).
    idx = alive_seats.index(expected_seat)
    next_seat = alive_seats[(idx + 1) % len(alive_seats)]
    next_player = next(p for p in players if p.seat == next_seat)

    # P0.4 income: collect gold for the NEXT player at the start of their
    # turn. Done here (right before we hand control to next_player) so the
    # income ActionLog and the gold field are both flushed in the same
    # transaction as the end_turn action.
    await _collect_income_for_player(session, game, next_player)

    # If the next player has already ended, we've wrapped around -> resolve round.
    if next_player.has_ended_turn:
        eot = await apply_end_of_turn(session, game)
        leveled_ids = [uid for uid, _ in eot.leveled_units]
        eliminated = [p.id for p in players if not p.is_alive]
        for p in players:
            p.has_ended_turn = False
        all_units = (
            await session.execute(
                select(Unit).where(Unit.player_id.in_([p.id for p in players]))
            )
        ).scalars().all()
        for u in all_units:
            u.has_acted = False
            u.has_moved = False
            u.mp = u.mov  # refill MP pool for the next round

        if game.status == "playing":
            game.turn_number += 1
            alive_seats = sorted(p.seat for p in players if p.is_alive)
            if alive_seats:
                game.current_player_index = alive_seats[0]
                # If the new round starts with an AI, keep it in 'ai' phase;
                # otherwise mark as 'player' so the human can act.
                first_player = next(p for p in players if p.seat == alive_seats[0])
                game.phase = "ai" if first_player.is_ai else "player"
            else:
                game.status = "finished"
                game.phase = "player"

        next_id = (
            next((p.id for p in players if p.seat == game.current_player_index), None)
            if game.status == "playing" else None
        )
        return EndTurnResult(
            next_player_id=next_id,
            turn_number=game.turn_number,
            game_status=game.status,
            leveled_units=leveled_ids,
            eliminated_players=eliminated,
            actions_taken=acted_count,
            actions_required=5,
            description=(
                f"第 {game.turn_number - 1} 回合结算完毕。"
                + (f" 升级单位：{len(leveled_ids)}。" if leveled_ids else "")
            ),
        )

    # Otherwise, just advance to the next alive player (within the same round).
    game.current_player_index = next_seat

    # If the next player is AI, schedule it to play automatically in the
    # background so the human user can watch without doing anything.
    if next_player.is_ai and game.status == "playing":
        game.phase = "ai"
        asyncio.create_task(_run_ai_turn_chain(game.id))
    else:
        game.phase = "player"

    return EndTurnResult(
        next_player_id=next_player.id,
        turn_number=game.turn_number,
        game_status=game.status,
        actions_taken=acted_count,
        actions_required=5,
        description=f"{player.user_name} 结束回合。下一位：{next_player.user_name}。",
    )


async def _run_ai_turn_chain(game_id: int) -> None:
    """Run AI turns one action at a time, sleeping between each.

    Plays out the AI's actions slowly so the human can watch. After the AI
    finishes, advances to the next player. If the next player is also AI,
    recursively runs them. Stops when the current player is human or the
    game ends.
    """
    try:
        # Step 1: wait for the "AI thinking" pause before the first action.
        await asyncio.sleep(AI_THINK_DELAY_SECONDS)
        async with AsyncSessionLocal() as session:
            game = await session.get(Game, game_id)
            if game is None or game.status != "playing":
                return
            players = (
                await session.execute(
                    select(Player).where(Player.game_id == game_id)
                )
            ).scalars().all()
            alive_seats = sorted(p.seat for p in players if p.is_alive)
            if not alive_seats:
                return
            idx = next(
                (i for i, s in enumerate(alive_seats)
                 if s >= game.current_player_index),
                0,
            )
            expected_seat = alive_seats[idx % len(alive_seats)]
            current = next((p for p in players if p.seat == expected_seat), None)
            if current is None or not current.is_ai:
                # Reached a human player — hand control back.
                game.phase = "player"
                await session.commit()
                return

            # Step 2: take ONE action (rules AI path; LLM uses its own
            # dispatch_ai_turn which still runs the whole turn in one shot).
            try:
                acted = await ai_take_one_action(session, game, current)
            except Exception:
                logger.exception("AI step failed; aborting chain for game %d", game_id)
                return

            if not acted:
                # No more actions — end this AI's turn and advance.
                current.has_ended_turn = True
                session.add(ActionLog(
                    game_id=game.id,
                    turn_number=game.turn_number,
                    player_id=current.id,
                    action_type="end_turn",
                    description=fmt_end_turn(current, 0),
                ))
                # Advance to the next player. If everyone has ended, resolve.
                next_idx = (idx + 1) % len(alive_seats)
                next_seat = alive_seats[next_idx]
                next_player = next(p for p in players if p.seat == next_seat)
                if next_player.has_ended_turn:
                    # Round wrap -> resolve end-of-turn
                    await apply_end_of_turn(session, game)
                    for p in players:
                        p.has_ended_turn = False
                    all_units = (
                        await session.execute(
                            select(Unit).where(Unit.player_id.in_([p.id for p in players]))
                        )
                    ).scalars().all()
                    for u in all_units:
                        u.has_acted = False
                        u.has_moved = False
                        u.mp = u.mov
                    if game.status == "playing":
                        new_alive = sorted(p.seat for p in players if p.is_alive)
                        if new_alive:
                            game.current_player_index = new_alive[0]
                            game.turn_number += 1
                            first_p = next(p for p in players if p.seat == new_alive[0])
                            game.phase = "ai" if first_p.is_ai else "player"
                        else:
                            game.status = "finished"
                            game.phase = "player"
                else:
                    game.current_player_index = next_seat
                    # Phase decision: if next is AI, keep phase=ai; else player
                    game.phase = "ai" if next_player.is_ai else "player"
                await session.commit()
                # If next player is still AI, continue the chain.
                if game.status == "playing":
                    is_next_ai = next(
                        (p.is_ai for p in players if p.seat == game.current_player_index),
                        False,
                    )
                    if is_next_ai:
                        asyncio.create_task(_run_ai_turn_chain(game_id))
                return

            # AI still has more actions — commit and recurse to take the next.
            await session.commit()
            asyncio.create_task(_run_ai_turn_chain(game_id))
    except Exception:  # noqa: BLE001
        logger.exception("AI turn chain error in game %d", game_id)


# ============================================================
# Background scheduler
# ============================================================

_scheduler_task: Optional[asyncio.Task] = None


async def _auto_skip_loop(stop_event: asyncio.Event) -> None:
    """Poll for stale turns every TURNS_CHECK_INTERVAL_SECONDS.

    Also runs abandoned-room cleanup on a slower cadence (LOBBY_CLEANUP_INTERVAL_SECONDS),
    and emits a HEALTH line every ~30-60s so operators can
    see liveness + memory growth at a glance.
    """
    loop_count = 0
    health_interval = max(TURNS_CHECK_INTERVAL_SECONDS, 30)  # never more often than 30s
    health_every = max(1, health_interval // TURNS_CHECK_INTERVAL_SECONDS)
    prev_rss_mb: Optional[float] = None
    logger.info("Turn scheduler started: poll_interval=%ds health_interval=%ds",
                TURNS_CHECK_INTERVAL_SECONDS, health_interval)
    try:
        while not stop_event.is_set():
            try:
                await _check_stale_turns()
                if loop_count % max(1, LOBBY_CLEANUP_INTERVAL_SECONDS // TURNS_CHECK_INTERVAL_SECONDS) == 0:
                    await cleanup_abandoned_games()
            except Exception:  # noqa: BLE001
                # Log but never kill the scheduler
                logger.exception("Turn scheduler loop error")
            # Periodic HEALTH line (per the Agent Logging Standard §4.2 / §16)
            if loop_count > 0 and loop_count % health_every == 0:
                try:
                    playing, waiting = await _count_games_by_status()
                    metrics = collect_health_metrics(prev_rss_mb=prev_rss_mb)
                    prev_rss_mb = metrics["rss_mb"]
                    health.info(format_health_line(
                        metrics, playing_games=playing, waiting_games=waiting,
                    ))
                except Exception:  # noqa: BLE001
                    logger.exception("HEALTH collection failed")
            loop_count += 1
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=TURNS_CHECK_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                pass
    finally:
        # Final HEALTH line on shutdown
        try:
            playing, waiting = await _count_games_by_status()
            metrics = collect_health_metrics(prev_rss_mb=prev_rss_mb)
            health.info(format_health_line(
                metrics, playing_games=playing, waiting_games=waiting, final=True,
            ))
        except Exception:  # noqa: BLE001
            logger.exception("Final HEALTH line failed")
        logger.info("Turn scheduler stopped")


async def _count_games_by_status() -> tuple:
    """Return (playing_count, waiting_count). Lightweight — no joins."""
    from sqlalchemy import func

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Game.status, func.count(Game.id)).group_by(Game.status)
            )
        ).all()
    playing = waiting = 0
    for status, count in rows:
        if status == "playing":
            playing = count
        elif status == "waiting":
            waiting = count
    return playing, waiting


async def cleanup_abandoned_games() -> None:
    """Delete games that have been abandoned.

    - waiting games with 0 players, older than ABANDONED_LOBBY_MINUTES -> deleted
    - finished games older than ABANDONED_FINISHED_HOURS -> deleted (housekeeping)
    """
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        # 1. Empty lobbies
        lobby_cutoff = now - timedelta(minutes=ABANDONED_LOBBY_MINUTES)
        empty_lobbies = (
            await session.execute(
                select(Game).where(Game.status == "waiting", Game.created_at < lobby_cutoff)
            )
        ).scalars().all()
        abandoned_ids: List[int] = []
        for g in empty_lobbies:
            player_count = (
                await session.execute(
                    select(Player).where(Player.game_id == g.id)
                )
            ).scalars().all()
            if len(player_count) == 0:
                abandoned_ids.append(g.id)

        # 2. Finished games (housekeeping)
        finished_cutoff = now - timedelta(hours=ABANDONED_FINISHED_HOURS)
        old_finished = (
            await session.execute(
                select(Game).where(Game.status == "finished", Game.created_at < finished_cutoff)
            )
        ).scalars().all()
        for g in old_finished:
            abandoned_ids.append(g.id)

        if abandoned_ids:
            from sqlalchemy import delete
            # Delete each game; cascades on tiles/logs/players/units clean up the rest
            for gid in abandoned_ids:
                g = await session.get(Game, gid)
                if g is not None:
                    await session.delete(g)
            logger.info(
                "Abandoned games cleaned up: count=%d ids=%s", len(abandoned_ids), abandoned_ids
            )
        await session.commit()


async def _check_stale_turns() -> None:
    """Mark players who exceeded TURN_TIMEOUT_HOURS as ended (auto-skip)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=TURN_TIMEOUT_HOURS)
    async with AsyncSessionLocal() as session:
        games = (
            await session.execute(select(Game).where(Game.status == "playing"))
        ).scalars().all()
        for game in games:
            players = (
                await session.execute(select(Player).where(Player.game_id == game.id))
            ).scalars().all()
            alive_seats = sorted(p.seat for p in players if p.is_alive)
            if not alive_seats:
                continue
            expected_seat = next(
                (s for s in alive_seats if s >= game.current_player_index),
                alive_seats[0],
            )
            current = next((p for p in players if p.seat == expected_seat), None)
            if current is None:
                continue
            if current.has_ended_turn:
                continue
            # Look at the latest turn_end log to find when this player started their turn
            last_log = (
                await session.execute(
                    select(ActionLog)
                    .where(ActionLog.game_id == game.id, ActionLog.turn_number == game.turn_number)
                    .order_by(ActionLog.id.desc())
                )
            ).scalars().first()
            # Use game.turn_number and last_log.created_at as a proxy
            started = last_log.created_at if last_log else game.created_at
            if started is None or started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc) if started else None
            if started and datetime.now(timezone.utc) - started >= timedelta(hours=TURN_TIMEOUT_HOURS):
                current.has_ended_turn = True
                session.add(
                    ActionLog(
                        game_id=game.id,
                        turn_number=game.turn_number,
                        player_id=current.id,
                        action_type="auto_skip",
                        description=f"{current.user_name} 因超时自动跳过",
                    )
                )
                audit.warning(
                    "USER_ACTION | user=player_%d | game=%d | action=AUTO_SKIP | "
                    "result=SUCCESS | reason=timeout | user_name=%s | seat=%d",
                    current.id, game.id, current.user_name, current.seat,
                )
                # If everyone has ended, resolve the turn
                if all(p.has_ended_turn or not p.is_alive for p in players):
                    await apply_end_of_turn(session, game)
                    for p in players:
                        p.has_ended_turn = False
                    all_units = (
                        await session.execute(
                            select(Unit).where(Unit.player_id.in_([p.id for p in players]))
                        )
                    ).scalars().all()
                    for u in all_units:
                        u.has_acted = False
                        u.has_moved = False
                        u.mp = u.mov
                    if game.status == "playing":
                        new_alive = sorted(p.seat for p in players if p.is_alive)
                        if new_alive:
                            game.current_player_index = new_alive[0]
                            game.turn_number += 1
        await session.commit()


def start_scheduler() -> asyncio.Task:
    """Start the background turn scheduler. Idempotent."""
    global _scheduler_task
    if _scheduler_task is not None and not _scheduler_task.done():
        return _scheduler_task
    stop_event = asyncio.Event()
    task = asyncio.create_task(_auto_skip_loop(stop_event))
    _scheduler_task = task
    return task


def stop_scheduler() -> None:
    """Best-effort cancel of the background task."""
    global _scheduler_task
    if _scheduler_task is not None and not _scheduler_task.done():
        _scheduler_task.cancel()
    _scheduler_task = None