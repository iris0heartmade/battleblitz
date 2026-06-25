"""
LLM-powered agent opponent for BattleBlitz.

Public surface:
- LLMAgent: orchestrator that turns a game state into an action via LLM
- dispatch_ai_turn: drop-in replacement for `ai_take_turn` that picks
  rules vs LLM backend based on `Player.agent_kind`
"""
from app.agent.agent import LLMAgent
from app.agent.integration import dispatch_ai_turn

__all__ = ["LLMAgent", "dispatch_ai_turn"]
