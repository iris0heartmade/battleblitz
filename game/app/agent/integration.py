"""
Drop-in dispatcher for `ai_take_turn`.

The routes layer still calls `ai_take_turn(session, game, player)`; this
function checks the player's `agent_kind` column and either:
  - delegates to the original rules AI (default), or
  - runs the LLM agent and reports its actions

We deliberately don't modify `game_logic.ai_take_turn` to keep blast radius
small. Instead, `routes/turns.py` should import `dispatch_ai_turn` from
this module instead of the original.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.agent import LLMAgent, TurnMetrics
from app.agent.llm_client import LLMClient
from app.config import AI_MAX_ACTIONS_PER_TURN
from app.models import ActionLog, Game, Player

logger = logging.getLogger(__name__)

# Load agent/.env so API keys are available via os.environ.
# Resolve relative to the game/ directory (this file is game/app/agent/integration.py).
import os as _os
from pathlib import Path as _Path
_env_path = _Path(__file__).resolve().parent.parent.parent / "agent" / ".env"
if _env_path.exists():
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(_env_path)
    logger.info("Loaded agent/.env")
else:
    logger.info("agent/.env not found — LLM agent will fall back to rules AI")


# ----------------------------------------------------------------
# Shared LLM client (one per process is enough)
# ----------------------------------------------------------------

_default_client: Optional[LLMClient] = None


def get_default_llm_client() -> LLMClient:
    """Lazy singleton. Tests can monkey-patch `agent.llm_client._default_client`."""
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client


def set_default_llm_client(client: LLMClient) -> None:
    """Test hook: replace the global LLM client with a fake."""
    global _default_client
    _default_client = client


# ----------------------------------------------------------------
# Dispatcher
# ----------------------------------------------------------------

async def dispatch_ai_turn(
    session: AsyncSession,
    game: Game,
    player: Player,
) -> int:
    """Choose between rules AI and LLM AI based on `player.agent_kind`.

    Returns the number of actions taken. Falls back to the rules AI if the
    LLM agent is unconfigured or raises an unrecoverable error.
    """
    # Lazy import to avoid a circular dependency at module load.
    from app.game_logic import ai_take_turn as rules_ai_take_turn

    kind = getattr(player, "agent_kind", "rules") or "rules"

    if kind == "rules":
        return await rules_ai_take_turn(session, game, player)

    if kind != "llm":
        logger.warning("Unknown agent_kind=%r; falling back to rules AI", kind)
        return await rules_ai_take_turn(session, game, player)

    # LLM agent
    try:
        client = get_default_llm_client()
        personality = getattr(player, "agent_personality", "balanced") or "balanced"
        agent = LLMAgent(
            llm_client=client,
            personality=personality,
            max_decisions_per_turn=AI_MAX_ACTIONS_PER_TURN,
        )

        # Determine budget: 2 actions per turn (first player 1 on turn 1)
        from app.routes.actions import _actions_per_turn
        budget = _actions_per_turn(player, game)

        metrics: TurnMetrics = await agent.take_turn(
            session, game, player, budget_left=budget,
        )

        # ── Persist reactions to ActionLog so the frontend can display them ──
        for reaction in metrics.reactions:
            session.add(ActionLog(
                game_id=game.id,
                turn_number=game.turn_number,
                player_id=player.id,
                action_type="ai_commentary",
                description=f"[{reaction.event}/{reaction.mood}] {reaction.text}",
            ))

        logger.info(
            "LLM agent %s turn %d: %d actions, %d LLM calls, %d retries, "
            "%d fallback, %d/%d tokens, %d reactions",
            player.user_name, game.turn_number,
            metrics.actions_taken, metrics.llm_calls, metrics.llm_retries,
            metrics.fallback_used,
            metrics.input_tokens, metrics.output_tokens,
            len(metrics.reactions),
        )
        return metrics.actions_taken

    except Exception:
        logger.exception("LLM agent crashed; falling back to rules AI")
        return await rules_ai_take_turn(session, game, player)
