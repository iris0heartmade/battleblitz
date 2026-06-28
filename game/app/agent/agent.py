"""
LLMAgent: the orchestrator that turns a game state into an executed action.

Workflow per call to `decide_one`:
  1. snapshot = build_snapshot(...)              # DB → GameSnapshot
  2. legal    = enumerate_legal_actions(...)     # pre-validated options
  3. system, user = build_*_prompt(snapshot, legal, personality)
  4. response = await llm_client.chat(...)       # tool_use
  5. action   = AgentAction(action_id=..., reason=...)
  6. check action.action_id is in legal          # 业务校验
  7. return ActionPlan(legal_action=..., reason=...)

`take_turn` loops this until budget is exhausted, an end_turn is chosen,
or the engine tells us every unit has acted.

Failures (parse error, invalid id, API timeout) are retried up to N times
with a corrective user-message appended; on the last failure we fall back
to a rules-AI action so the turn is never stuck.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.legal_actions import enumerate_legal_actions
from app.agent.llm_client import LLMClient, LLMResponse, TokenUsage
from app.agent.prompt import build_system_prompt, build_user_prompt
from app.agent.reactions import (
    Reaction,
    events_from_hp_diff,
    generate_reaction,
)
from app.agent.schemas import (
    AgentAction,
    GameSnapshot,
    InvalidActionError,
    LegalAction,
    ParseError,
)
from app.agent.snapshot import build_snapshot
from app.config import AI_MAX_ACTIONS_PER_TURN, AI_THINK_DELAY_SECONDS
from app.models import Game, Player, Unit

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------
# Result types
# ----------------------------------------------------------------

@dataclass
class ActionPlan:
    """What the agent decided; the engine turns this into DB writes."""
    legal_action: LegalAction
    reason: str = ""
    fallback: bool = False  # True if rules AI produced this after LLM failed
    llm_calls: int = 0
    llm_retries: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    # Short emotional commentary triggered by the action's outcome
    # (e.g. kill, castle capture). May be empty.
    reactions: list[Reaction] = field(default_factory=list)


@dataclass
class TurnMetrics:
    actions_taken: int = 0
    llm_calls: int = 0
    llm_retries: int = 0
    fallback_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    decisions: list[ActionPlan] = field(default_factory=list)
    # All reactions emitted during this turn, including the passive
    # "killed" / "damaged" reactions from opponent's previous turn.
    reactions: list[Reaction] = field(default_factory=list)


# ----------------------------------------------------------------
# Agent
# ----------------------------------------------------------------

class LLMAgent:
    """Per-player LLM agent. One instance per AI player; safe to reuse across turns.

    Maintains a small persistent state dict (e.g. `last_turn_hp`) so that
    reactions like "I was hit last turn!" can be generated from HP diffs.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        personality: str = "balanced",
        *,
        max_retries: int = 2,
        max_decisions_per_turn: int = AI_MAX_ACTIONS_PER_TURN,
        think_delay: float = 0.0,             # 0 for tests; AI_THINK_DELAY for production
        max_reactions_per_turn: int = 3,      # cap passive reactions to avoid spam
        reaction_rng_seed: int | None = None,
    ):
        self.llm = llm_client
        self.personality = personality
        self.max_retries = max_retries
        self.max_decisions_per_turn = max_decisions_per_turn
        self.think_delay = think_delay
        self.max_reactions_per_turn = max_reactions_per_turn
        self._reaction_rng = random.Random(reaction_rng_seed)

        # Persistent state across turns. Keyed by whatever the engine needs.
        # `last_turn_hp` is {unit_id: hp} captured at the END of the agent's
        # own previous turn. On the next turn, we compare against current HP
        # to detect "damaged" / "killed" events from the opponent's turn.
        self.state: dict = {"last_turn_hp": {}}

    # ── Public: one full turn ─────────────────────────────────

    async def take_turn(
        self,
        session: AsyncSession,
        game: Game,
        player: Player,
        *,
        budget_left: int,
    ) -> TurnMetrics:
        """Decide up to `budget_left` actions for `player`, executing as we go."""
        metrics = TurnMetrics()
        actions_taken = 0

        # ── 0. Passive reactions: detect what happened to us on the
        # opponent's turn (HP diffs vs end-of-our-last-turn). Emitted
        # before we make any decision, so they appear at the top of the
        # turn's commentary.
        metrics.reactions.extend(
            await self._detect_passive_reactions(session, player)
        )

        # Snapshot unit state right before we act (used for castle-capture
        # detection and for last_turn_hp bookkeeping at the end).
        my_units_pre = await _load_my_units(session, player)

        # Turn-opening speech: the agent says something at the start of
        # every turn (like a real player thinking out loud).
        if self.think_delay > 0:
            await asyncio.sleep(self.think_delay)
        try:
            unit_count = len(my_units_pre)
            alive = sum(1 for u in my_units_pre if u.hp > 0)
            opener = self._speak("turn_start")
            metrics.reactions.append(opener)
        except Exception:  # noqa: BLE001
            pass

        # ── Batch decision: one LLM call for the whole turn ──
        t1 = time.perf_counter()
        snapshot = await build_snapshot(
            session, game, player,
            budget_left=budget_left, action_count=0,
        )
        legal = await enumerate_legal_actions(session, game, player)
        t2 = time.perf_counter()
        logger.info(
            "Phase [snapshot+legal]: %dms, %d legal actions, %d visible enemies",
            int((t2 - t1) * 1000), len(legal), len(snapshot.visible_enemies),
        )
        if not legal:
            metrics.actions_taken = 0
            return metrics

        system = build_system_prompt(self.personality, map_size=snapshot.map_size)
        user = build_user_prompt(snapshot, legal)
        t3 = time.perf_counter()
        logger.info(
            "Phase [prompt build]: %dms, system=%d chars, user=%d chars",
            int((t3 - t2) * 1000), len(system), len(user),
        )

        # Inject passive hits so the LLM can react to them
        hits = self.state.get("passive_hits", [])
        if hits:
            user += "\n\n【上回合你挨打了】" + "；".join(hits) + "\n请在 reaction 中表达你的情绪。"

        plans = await self._ask_llm_with_retry(system=system, user=user, legal=legal)

        for plan in plans:
            if actions_taken >= budget_left:
                break
            if self.think_delay > 0:
                await asyncio.sleep(self.think_delay)

            t_exec = time.perf_counter()
            enemy_hp_pre = await _load_enemy_hp(session, game, player)

            metrics.decisions.append(plan)
            executed = await self._execute_plan(session, game, player, plan)
            metrics.llm_calls += plan.llm_calls
            metrics.llm_retries += plan.llm_retries
            if plan.fallback:
                metrics.fallback_used += 1
            metrics.input_tokens += plan.input_tokens
            metrics.output_tokens += plan.output_tokens

            if not executed:
                continue

            actions_taken += 1

            outcome_reactions = await self._detect_action_outcomes(
                session, game, player, plan, enemy_hp_pre,
            )
            plan.reactions.extend(outcome_reactions)
            metrics.reactions.extend(plan.reactions)

            exec_ms = int((time.perf_counter() - t_exec) * 1000)
            logger.info(
                "Action #%d/%d: %s %s (%s) → %dms",
                actions_taken, budget_left,
                plan.legal_action.kind,
                plan.reason[:40] if plan.reason else "",
                "fallback" if plan.fallback else "llm",
                exec_ms,
            )

            if plan.legal_action.kind == "end_turn":
                break

        # Save current HP for next turn's diff
        my_units_post = await _load_my_units(session, player)
        self.state["last_turn_hp"] = {u.id: u.hp for u in my_units_post}

        metrics.actions_taken = actions_taken
        return metrics

    # ── Public: one decision (testable in isolation) ──────────

    async def decide_one(
        self,
        session: AsyncSession,
        game: Game,
        player: Player,
        *,
        budget_left: int,
        action_count: int = 0,
    ) -> ActionPlan:
        """Make ONE decision; do not execute."""
        snapshot = await build_snapshot(
            session, game, player,
            budget_left=budget_left, action_count=action_count,
        )
        legal = await enumerate_legal_actions(session, game, player)

        if not legal:
            return ActionPlan(
                legal_action=LegalAction(
                    action_id="end_turn", kind="end_turn",
                    description="无可用动作",
                ),
                reason="无可用动作",
                fallback=True,
            )

        system = build_system_prompt(self.personality, map_size=snapshot.map_size)
        user = build_user_prompt(snapshot, legal)

        # If we took damage last turn, tell the LLM so it can react
        # naturally in its `reaction` field.
        hits = self.state.get("passive_hits", [])
        if hits:
            user += "\n\n【上回合你挨打了】" + "；".join(hits) + "\n请在 reaction 中表达你的情绪。"

        plans = await self._ask_llm_with_retry(
            system=system,
            user=user,
            legal=legal,
        )
        if not plans:
            la = _rules_ai_pick(legal)
            return ActionPlan(legal_action=la, reason="[兜底] 无可用计划", fallback=True)
        return plans[0]

    # ── Internals ─────────────────────────────────────────────

    async def _ask_llm_with_retry(
        self,
        system: str,
        user: str,
        legal: List[LegalAction],
    ) -> list[ActionPlan]:
        """Call the LLM once; return 1-2 ActionPlans (batch decision).

        The LLM's `action_id` may contain pipe-separated IDs like
        'move_6_4_6 || attack_7_9'. Each gets its own ActionPlan with the
        same reason/reaction.
        """
        last_error: Optional[Exception] = None
        last_response: Optional[LLMResponse] = None
        retries = 0

        for attempt in range(self.max_retries + 1):
            try:
                # On retry, append a corrective user note
                if attempt == 0:
                    user_msg = user
                else:
                    user_msg = (
                        user
                        + "\n\n[系统提示] 上次调用出错: "
                        + (str(last_error) if last_error else "未知")
                        + "。请只输出一个 action_id（必须从合法动作列表原文复制）和 reason。"
                    )

                t_llm = time.perf_counter()
                response = await self.llm.chat(system=system, user=user_msg)
                logger.info(
                    "LLM chat round-trip (attempt %d/%d): %dms",
                    attempt + 1, self.max_retries + 1,
                    int((time.perf_counter() - t_llm) * 1000),
                )
                last_response = response

                action = self._parse_response(response)
                # action_id may be pipe-separated: "move_6_4_6 || attack_7_9"
                raw_ids = action.action_id or ""
                ids = [i.strip() for i in raw_ids.split("||") if i.strip()]

                reason = action.reason or ""
                reaction_text = (response.tool_input or {}).get("reaction", "").strip()

                plans: list[ActionPlan] = []
                for idx, aid in enumerate(ids):
                    try:
                        self._validate_action_id_by_string(aid, legal)
                    except (ParseError, InvalidActionError):
                        continue  # skip hallucinated / stale action
                    legal_action = next(a for a in legal if a.action_id == aid)
                    plan = ActionPlan(
                        legal_action=legal_action,
                        reason=reason if idx == 0 else "",
                        fallback=False,
                        llm_calls=attempt + 1,
                        llm_retries=retries,
                        input_tokens=response.usage.input_tokens if idx == 0 else 0,
                        output_tokens=response.usage.output_tokens if idx == 0 else 0,
                    )
                    # Attach reaction only to first action
                    if idx == 0 and reaction_text:
                        plan.reactions.append(Reaction(
                            event="turn_start",
                            mood="neutral",
                            text=reaction_text[:40],
                        ))
                    plans.append(plan)

                if not plans:
                    raise ParseError(f"no valid action_ids in {raw_ids!r}")
                return plans

            except (ParseError, InvalidActionError) as exc:
                last_error = exc
                retries += 1
                logger.warning(
                    "LLM agent attempt %d/%d failed: %s",
                    attempt + 1, self.max_retries + 1, exc,
                )
                continue
            except Exception as exc:                          # noqa: BLE001
                # API errors, timeouts, etc. — back off briefly and retry
                last_error = exc
                retries += 1
                logger.warning(
                    "LLM API attempt %d/%d failed: %s",
                    attempt + 1, self.max_retries + 1, exc,
                )
                await asyncio.sleep(0.5 * (attempt + 1))
                continue

        # All attempts failed — fall back to rules AI
        logger.error(
            "LLM agent failed after %d attempts; falling back to rules AI",
            self.max_retries + 1,
        )
        legal_action = _rules_ai_pick(legal)
        return [ActionPlan(
            legal_action=legal_action,
            reason=f"[兜底] LLM 调用失败 ({last_error})",
            fallback=True,
            llm_calls=self.max_retries + 1,
            llm_retries=retries,
            input_tokens=last_response.usage.input_tokens if last_response else 0,
            output_tokens=last_response.usage.output_tokens if last_response else 0,
        )]

    def _parse_response(self, response: LLMResponse) -> AgentAction:
        """Turn the LLM's tool_use block into a typed AgentAction."""
        if response.tool_name != "choose_action":
            raise ParseError(f"expected tool 'choose_action', got {response.tool_name!r}")
        inp = response.tool_input
        action_id = inp.get("action_id", "")
        if not isinstance(action_id, str) or not action_id:
            raise ParseError("tool_input.action_id is missing or empty")
        reason = inp.get("reason", "")
        if not isinstance(reason, str):
            reason = str(reason)
        return AgentAction(action_id=action_id, reason=reason[:120])

    def _validate_action_id(self, action: AgentAction, legal: List[LegalAction]) -> None:
        if not any(a.action_id == action.action_id for a in legal):
            sample = ", ".join(a.action_id for a in legal[:3])
            raise InvalidActionError(
                action.action_id,
                f"{action.action_id!r} not in legal_actions (first 3: {sample}...)",
            )

    def _validate_action_id_by_string(self, action_id: str, legal: List[LegalAction]) -> None:
        if not any(a.action_id == action_id for a in legal):
            sample = ", ".join(a.action_id for a in legal[:3])
            raise InvalidActionError(
                action_id,
                f"{action_id!r} not in legal_actions (first 3: {sample}...)",
            )

    async def _execute_plan(
        self,
        session: AsyncSession,
        game: Game,
        player: Player,
        plan: ActionPlan,
    ) -> bool:
        """Translate the plan into the engine's move/attack/skill/wait calls.

        We re-use the same low-level helpers the rules AI uses (`_ai_move`,
        `_ai_attack`, `_ai_use_skill`) so the LLM-driven and rules-driven
        paths share the exact same execution semantics. Returns True if the
        action was successfully applied, False otherwise (e.g. unit died).
        """
        from app.game_logic import _ai_attack, _ai_move, _ai_use_skill

        t0 = time.perf_counter()
        a = plan.legal_action
        if a.kind == "end_turn":
            return True
        if a.kind == "wait":
            unit_id = a.unit_id
            if unit_id is None:
                return False
            unit = await session.get(Unit, unit_id)
            if unit is None or unit.has_acted:
                return False
            unit.has_acted = True
            unit.mp = 0
            logger.info("  execute wait: unit_id=%d → %dms", unit_id,
                        int((time.perf_counter() - t0) * 1000))
            return True
        if a.kind == "move":
            unit = await session.get(Unit, a.unit_id) if a.unit_id else None
            if unit is None or unit.has_acted or unit.mp <= 0:
                return False
            tx, ty = a.params["to"]
            ok = await _ai_move(session, game, unit, (int(tx), int(ty)))
            logger.info("  execute move: unit_id=%d to=(%d,%d) ok=%s → %dms",
                        a.unit_id, int(tx), int(ty), ok,
                        int((time.perf_counter() - t0) * 1000))
            return bool(ok)
        if a.kind == "attack":
            unit = await session.get(Unit, a.unit_id) if a.unit_id else None
            target = await session.get(Unit, a.params.get("target_id", -1)) \
                if a.params.get("target_id") is not None else None
            if unit is None or target is None or unit.has_acted:
                return False
            ok = await _ai_attack(session, unit, target)
            logger.info("  execute attack: unit_id=%d target=%d ok=%s → %dms",
                        a.unit_id, a.params.get("target_id"), ok,
                        int((time.perf_counter() - t0) * 1000))
            return bool(ok)
        if a.kind == "skill":
            unit = await session.get(Unit, a.unit_id) if a.unit_id else None
            if unit is None or unit.has_acted:
                return False
            # Build a minimal snap for _ai_use_skill
            from app.game_logic import _load_ai_snapshot
            snap = await _load_ai_snapshot(session, game, player)
            ok = await _ai_use_skill(session, game, unit, snap)
            logger.info("  execute skill: unit_id=%d skill=%s ok=%s → %dms",
                        a.unit_id, a.params.get("skill"), ok,
                        int((time.perf_counter() - t0) * 1000))
            return bool(ok)
        return False

    # ── Reaction helpers ────────────────────────────────────────

    def _speak(self, event: str, *, ctx: dict | None = None) -> Reaction:
        """Pick a template reaction with context-filled placeholders."""
        return generate_reaction(
            self.personality, event, ctx=ctx, rng=self._reaction_rng
        )

    async def _detect_passive_reactions(
        self,
        session: AsyncSession,
        player: Player,
    ) -> list[Reaction]:
        """Detect HP diffs from opponent's turn; store in state so the
        first LLM decision this turn knows to react to them.

        Returns template reactions for immediate display; the LLM-produced
        reactions (which sound more natural) will come from the first
        decision's `reaction` field.
        """
        last_turn_hp: dict = self.state.get("last_turn_hp", {})
        self.state["passive_hits"] = []   # reset each turn
        if not last_turn_hp:
            return []  # first turn; nothing to compare

        my_units = await _load_my_units(session, player)
        current_hp = {u.id: u.hp for u in my_units}
        events = events_from_hp_diff(last_turn_hp, current_hp)

        if not events:
            return []

        # Store for the decision prompt so the LLM can react naturally
        for uid, (old_hp, new_hp) in current_hp.items():
            prev = last_turn_hp.get(uid)
            if prev is not None and new_hp < prev:
                unit_name = next((u.name for u in my_units if u.id == uid), f"#{uid}")
                self.state["passive_hits"].append(
                    f"{unit_name} 从 {prev} HP 被打到 {new_hp} HP"
                )
            elif prev is not None and new_hp <= 0 and prev > 0:
                unit_name = next((u.name for u in my_units if u.id == uid), f"#{uid}")
                self.state["passive_hits"].append(f"{unit_name} 被击杀")

        # Cap
        self.state["passive_hits"] = self.state["passive_hits"][:self.max_reactions_per_turn]

        # Still emit template reactions for the chat box (LLM ones will be
        # richer and come from the next decision call)
        killed = [e for e in events if e == "killed"]
        damaged = [e for e in events if e == "damaged"]
        ordered = (killed + damaged)[:self.max_reactions_per_turn]
        return [self._speak(e) for e in ordered]

    async def _detect_action_outcomes(
        self,
        session: AsyncSession,
        game: Game,
        player: Player,
        plan: ActionPlan,
        enemy_hp_pre: dict[int, int],
    ) -> list[Reaction]:
        """Detect reactions triggered by the action we just executed — every
        action gets at least one reaction so the agent never goes silent."""
        a = plan.legal_action
        reactions: list[Reaction] = []
        my_unit = await session.get(Unit, a.unit_id) if a.unit_id else None
        u_name = (my_unit.name if my_unit else "")[:6]

        if a.kind == "attack" and a.params.get("target_id") is not None:
            target = await session.get(Unit, a.params["target_id"])
            e_name = (target.name if target else "?")[:6]
            target_hp = target.hp if target else 0
            prev_hp = enemy_hp_pre.get(a.params["target_id"], 0)
            dmg_dealt = prev_hp - target_hp if target else 0

            if target is not None and target_hp <= 0 and prev_hp > 0:
                reactions.append(self._speak(
                    "kill", ctx={"u": u_name, "e": e_name, "dmg": str(prev_hp)},
                ))
            elif target is not None and 0 < target_hp <= 5:
                reactions.append(self._speak(
                    "near_miss", ctx={"e": e_name, "hp": str(target_hp)},
                ))
            else:
                reactions.append(self._speak(
                    "attack_hit", ctx={"u": u_name, "e": e_name, "dmg": str(dmg_dealt)},
                ))

        elif a.kind == "move" and a.params.get("to"):
            tx, ty = int(a.params["to"][0]), int(a.params["to"][1])
            from sqlalchemy import select
            from app.models import Tile
            tile = (await session.execute(
                select(Tile).where(
                    Tile.game_id == game.id, Tile.x == tx, Tile.y == ty,
                )
            )).scalars().first()
            if tile and tile.terrain == "castle" and tile.owner_id != player.id:
                reactions.append(self._speak(
                    "castled", ctx={"u": u_name},
                ))
            else:
                reactions.append(self._speak(
                    "move", ctx={"u": u_name},
                ))

        elif a.kind == "skill":
            skill = a.params.get("skill", "")
            if skill == "heal":
                reactions.append(self._speak("heal", ctx={"u": u_name}))
            else:
                reactions.append(self._speak("skill_use", ctx={"u": u_name}))

        elif a.kind == "wait":
            reactions.append(self._speak("wait", ctx={"u": u_name}))

        return reactions


# ----------------------------------------------------------------
# Fallback: a simple rules-based pick from the legal actions
# ----------------------------------------------------------------

def _rules_ai_pick(legal: List[LegalAction]) -> LegalAction:
    """Pick the best legal action using the same heuristics as the rules AI.

    Used only when the LLM is unavailable. Keeps the game moving.
    """
    # 1. Prefer attack actions with the highest expected damage / kill chance
    attacks = [a for a in legal if a.kind == "attack" and a.unit_id is not None]
    if attacks:
        attacks.sort(
            key=lambda a: (
                a.dmg_estimate or 0,                   # prefer high damage
                -int(a.params.get("target_id", 0)),    # tie-break on target id
            ),
            reverse=True,
        )
        return attacks[0]

    # 2. Then skills (heal preferred over rally)
    heals = [a for a in legal if a.kind == "skill" and a.params.get("skill") == "heal"]
    if heals:
        return heals[0]
    rallies = [a for a in legal if a.kind == "skill"]
    if rallies:
        return rallies[0]

    # 3. Then moves (any non-end_turn move)
    moves = [a for a in legal if a.kind == "move"]
    if moves:
        return moves[0]

    # 4. Wait or end_turn
    waits = [a for a in legal if a.kind == "wait"]
    if waits:
        return waits[0]
    end = [a for a in legal if a.kind == "end_turn"]
    if end:
        return end[0]

    # Should be unreachable (we always emit at least end_turn)
    return legal[0]


# ----------------------------------------------------------------
# Type-only imports to keep top-level clean
# ----------------------------------------------------------------

from app.models import Unit  # noqa: E402


# ----------------------------------------------------------------
# Module-level helpers
# ----------------------------------------------------------------

async def _load_my_units(session: AsyncSession, player: Player) -> list[Unit]:
    """Return all live units owned by `player` (any HP, including dead)."""
    from sqlalchemy import select
    rows = (await session.execute(
        select(Unit).where(Unit.player_id == player.id)
    )).scalars().all()
    return list(rows)


async def _load_enemy_hp(
    session: AsyncSession,
    game: Game,
    player: Player,
) -> dict[int, int]:
    """Return {unit_id: hp} for all enemy units (used to detect kills)."""
    from sqlalchemy import select
    rows = (await session.execute(
        select(Unit).where(Unit.player_id != player.id, Unit.hp > 0)
    )).scalars().all()
    return {u.id: u.hp for u in rows}
