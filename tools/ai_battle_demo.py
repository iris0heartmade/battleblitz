"""AI vs AI 自动对战演示脚本

让 N 个 AI 在房间里互打，把引擎里所有的 debug 日志
(AISnapshot / ai_take_one_action / AI attack / AI move / claim_complete /
end_turn / apply_end_of_turn / ...) 实时输出到 stdout。

底层用的是 `app.routes.turns._run_ai_turn_chain`——朋友 P2.4 加的
"AI 慢慢打给人类看" 的链式异步循环。每个 AI 跑完一个动作就
sleep AI_THINK_DELAY_SECONDS 秒，下一个是 AI 就自动 recurse 继续打。

用法:
    cd game
    python ../tools/ai_battle_demo.py              # 4 个 AI
    python ../tools/ai_battle_demo.py --players 2  # 2 个 AI
    python ../tools/ai_battle_demo.py --seed 42    # 可复现
    python ../tools/ai_battle_demo.py --max-turns 50  # 最多 50 回合
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

# 让 Python 能 import app.*
ROOT = Path(__file__).resolve().parent.parent / "game"
sys.path.insert(0, str(ROOT))

from app.database import AsyncSessionLocal, dispose_db, init_db
from app.logging_config import setup_logging
from app.models import Game, Player
from app.routes.turns import _run_ai_turn_chain


# ============================================================
# Helpers
# ============================================================

async def _create_ai_game(num_players: int, seed: int) -> int:
    """Create a game with N AI players and return the game_id.

    First player is the host (joined via /join so they own a real seat).
    Remaining players come in via /add-ai so they get is_ai=True and
    friendly auto-generated names.
    """
    from app.routes.game import (
        create_game, join_game, add_ai_player, start_game,
    )
    from app.schemas import (
        CreateGameRequest, JoinGameRequest, AddAIRequest,
    )

    async with AsyncSessionLocal() as session:
        body = CreateGameRequest(
            name=f"AI battle ({num_players}p seed={seed})",
            map_preset="classic",
            capacity=num_players,
            map_seed=seed,
            win_condition="rout",
        )
        game = await create_game(body=body, session=session)
        game_id = game.id

        # Host is the first "real" player — but they're never going to
        # act (no UI), so they're effectively AI-shaped too. We don't
        # need to mark them is_ai=True for the chain to drive them:
        # the AI turn-chain skips humans and waits for them. To make
        # every seat an AI, use add_ai for ALL players.
        for _ in range(num_players):
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

        # Start the game (assigns castles, units, etc.)
        await start_game(game_id=game_id, session=session)
        await session.commit()
        return game_id


async def _wait_until_finished(game_id: int, max_turns: int, poll_interval: float = 1.0) -> dict:
    """Poll game state until status=='finished' or turn exceeds max_turns.

    Also kicks off `_run_ai_turn_chain` after the game starts so AI begins
    playing right away.
    """
    deadline = time.time() + 600  # 10-minute hard cap
    last_log = -1
    while True:
        async with AsyncSessionLocal() as session:
            game = await session.get(Game, game_id)
            if game is None:
                return {"status": "missing"}
            st = {
                "status": game.status,
                "turn": game.turn_number,
                "phase": game.phase,
                "winner": getattr(game, "_winner_team", None),
                "win_reason": game.win_reason,
            }

        # Show progress every few polls
        if st["turn"] != last_log:
            print(f"  [poll] T={st['turn']:>3} phase={st['phase']:<8} status={st['status']}",
                  flush=True)
            last_log = st["turn"]

        # Done?
        if st["status"] == "finished":
            return st
        if st["turn"] >= max_turns:
            return {**st, "status": "timeout"}

        # Still playing → if it's an AI's turn and phase='ai' but no chain
        # is running, kick one off. The chain self-recurse keeps it going.
        if st["phase"] == "ai" and not st.get("_chain_running"):
            st["_chain_running"] = True
            asyncio.create_task(_run_ai_turn_chain(game_id))
            print(f"  [spawn] AI chain (T={st['turn']})", flush=True)

        if time.time() > deadline:
            return {**st, "status": "wallclock_timeout"}

        await asyncio.sleep(poll_interval)


# ============================================================
# Main
# ============================================================

async def main_async(args: argparse.Namespace) -> int:
    # Configure logging FIRST so all engine modules pipe to stdout.
    setup_logging(console_level=logging.INFO)

    print("=" * 70, flush=True)
    print(f"AI Battle Demo · {args.players} players · seed={args.seed} · max-turns={args.max_turns}",
          flush=True)
    print("=" * 70, flush=True)

    await init_db()
    try:
        game_id = await _create_ai_game(args.players, args.seed)
        print(f"[setup] game #{game_id} created with {args.players} AI players", flush=True)

        # Pre-kick the first chain (game starts in phase='ai' for seat 0)
        asyncio.create_task(_run_ai_turn_chain(game_id))

        result = await _wait_until_finished(game_id, args.max_turns)
        print("=" * 70, flush=True)
        print(f"[done] status={result.get('status')} turn={result.get('turn')} "
              f"phase={result.get('phase')} winner={result.get('winner')} "
              f"reason={result.get('win_reason')}", flush=True)
        return 0 if result.get("status") == "finished" else 1
    finally:
        await dispose_db()


def main() -> int:
    p = argparse.ArgumentParser(description="AI vs AI auto-battle demo")
    p.add_argument("--players", type=int, default=4, choices=[2, 3, 4],
                   help="Number of AI players (default 4)")
    p.add_argument("--seed", type=int, default=42,
                   help="Map seed for reproducibility")
    p.add_argument("--max-turns", type=int, default=80,
                   help="Hard cap on turns before giving up")
    args = p.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())