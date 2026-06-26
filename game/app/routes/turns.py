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
    LOBBY_CLEANUP_INTERVAL_SECONDS,
    TURN_TIMEOUT_HOURS,
    TURNS_CHECK_INTERVAL_SECONDS,
)
from app.database import AsyncSessionLocal, get_session
from app.game_logic import ai_take_turn, apply_end_of_turn
from app.agent.integration import dispatch_ai_turn
from app.logging_config import (
    collect_health_metrics,
    format_health_line,
    get_audit_logger,
    get_health_logger,
)
from app.models import ActionLog, Game, Player, Unit
from app.schemas import EndTurnRequest, EndTurnResult, GameStateOut

logger = logging.getLogger(__name__)
audit = get_audit_logger()
health = get_health_logger()

router = APIRouter(prefix="/games", tags=["turns"])


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

    # Fairness rule: first player (seat 0) gets 1 action on first turn only;
    # everyone else (and first player on later turns) needs 2 actions per turn.
    required_actions = 5
    if player.seat == 0 and not game.first_player_done_first_turn:
        required_actions = 5

    # Count units that have already acted this turn
    player_units = (
        await session.execute(
            select(Unit).where(Unit.player_id == player.id)
        )
    ).scalars().all()
    acted_count = sum(1 for u in player_units if u.has_acted)
    # (No enforcement: any player can end their turn at any time, even
    # without acting. The action counter is now advisory only.)

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
            description=f"{player.user_name} ended their turn",
        )
    )
    audit.info(
        "USER_ACTION | user=player_%d | game=%d | action=END_TURN | result=SUCCESS | "
        "seat=%d | acted_count=%d | required=%d | turn=%d",
        player.id, game_id, player.seat, acted_count, required_actions, game.turn_number,
    )

    # Find next alive seat after the current one (with wrap-around).
    idx = alive_seats.index(expected_seat)
    next_seat = alive_seats[(idx + 1) % len(alive_seats)]
    next_player = next(p for p in players if p.seat == next_seat)

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
            else:
                game.status = "finished"

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
            actions_required=required_actions,
            description=(
                f"Turn {game.turn_number - 1} resolved."
                + (f" Leveled: {len(leveled_ids)}." if leveled_ids else "")
            ),
        )

    # Otherwise, just advance to the next alive player (within the same round).
    game.current_player_index = next_seat

    # If the next player is AI, schedule it to play automatically in the
    # background so the human user can watch without doing anything.
    if next_player.is_ai and game.status == "playing":
        asyncio.create_task(_run_ai_turn_chain(game.id))

    return EndTurnResult(
        next_player_id=next_player.id,
        turn_number=game.turn_number,
        game_status=game.status,
        actions_taken=acted_count,
        actions_required=required_actions,
        description=f"{player.user_name} ended turn. Next: {next_player.user_name}.",
    )


async def _run_ai_turn_chain(game_id: int) -> None:
    """Run AI turns in a loop until the current player is human or game ends."""
    try:
        while True:
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
                    return

                # Run the AI's turn (dispatcher picks rules vs LLM)
                actions = await dispatch_ai_turn(session, game, current)
                session.add(ActionLog(
                    game_id=game.id,
                    turn_number=game.turn_number,
                    player_id=current.id,
                    action_type="ai_turn",
                    description=f"{current.user_name} 行动了 {actions} 步",
                ))

                # Advance to the next player; check for round wrap
                next_idx = (idx + 1) % len(alive_seats)
                next_seat = alive_seats[next_idx]
                next_player = next(p for p in players if p.seat == next_seat)
                if next_player.has_ended_turn:
                    # Round wrap -> resolve
                    eot = await apply_end_of_turn(session, game)
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
                else:
                    game.current_player_index = next_seat
                await session.commit()
                # Loop continues if the next player is also AI
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
                        description=f"{current.user_name} auto-skipped (timeout)",
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