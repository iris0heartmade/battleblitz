"""
MainlineEngine — pure orchestration over a loaded ``Mainline``.

The engine does NOT hold any combat logic. It only:

  1. Reads the active campaign from the loader (``app.mainline.loader``).
  2. Computes the next *frame* the client should render
     (dialogue / battle / victory) via ``next_step()``.
  3. Spawns the next ``Game`` row (delegating to
     ``routes.game._start_battle_internal``).
  4. Updates the player's profile via ``ProgressionService``.

Design notes:

  * ``next_step()`` is a **pure query**: it reads the profile but never
    mutates it. Side effects live on ``spawn_battle`` /
    ``apply_victory`` / ``mark_scene_done``.
  * The PlayerProfile contract used here is the post-Step-2 schema:
        - ``user_name``              : str
        - ``active_mainline``        : Optional[str]
        - ``mainline_progress``      : {"battle_index": int, "scene_id": str, "started_at": str|None}
    We fall back to safe defaults if any field is missing so the engine
    keeps working mid-migration.

This module is pure-Python + SQLAlchemy session; no FastAPI imports.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.mainline.loader import Mainline, MainlineNotFound, load_mainline
from app.mainline.schemas import (
    BattlePreview,
    BattleSpec,
    MainlineRewards,
    MainlineStepOut,
)

logger = logging.getLogger(__name__)


# ============================================================
# State enum
# ============================================================

class MainlineState(str, Enum):
    """The five logical states of a mainline playthrough.

    The orchestrator (routes/mainline.py) is responsible for the
    state-machine *transitions* — the engine just labels a frame.
    """
    MENU = "menu"           # lobby; no campaign active
    DIALOGUE = "dialogue"   # a scene is being played
    BATTLE = "battle"       # a battle is in progress
    VICTORY = "victory"     # campaign cleared
    ABANDONED = "abandoned" # player gave up


# ============================================================
# Profile attribute helpers (forward-compat shims)
# ============================================================

def _profile_active_mainline(profile: Any) -> Optional[str]:
    """``profile.active_mainline`` with a None default.

    Reads via ``getattr`` so a pre-Step-2 profile (no
    ``active_mainline`` column) returns None instead of raising
    AttributeError. Post-Step-2 profiles read the real value.
    """
    return getattr(profile, "active_mainline", None)


def _profile_progress(profile: Any) -> dict:
    """Return the ``mainline_progress`` JSON dict with a safe default.

    Default shape matches Step 2's contract:
        {"battle_index": 0, "scene_id": "intro", "started_at": None}

    If the column is missing OR is an empty dict we hand back a fresh
    default so callers can index into it without TypeError.
    """
    raw = getattr(profile, "mainline_progress", None)
    if not raw:
        return {"battle_index": 0, "scene_id": "intro", "started_at": None}
    # Defensive copy so callers can mutate without touching the ORM row.
    return dict(raw)


# ============================================================
# Game-name naming convention (the only Game↔Mainline association)
# ============================================================

def mainline_game_name(mainline_id: str, battle_id: str) -> str:
    """Canonical name for a Game row created by the mainline engine.

    Naming convention lets ``routes/mainline.py`` verify a game
    belongs to a campaign without needing a schema change on ``Game``.
    Example: ``mainline:chapter_01_steel_rebellion:battle_01``.
    """
    return f"mainline:{mainline_id}:{battle_id}"


def parse_mainline_game_name(game_name: str) -> Optional[tuple[str, str]]:
    """Inverse of ``mainline_game_name``. Returns (mainline_id, battle_id)
    or ``None`` if the name doesn't follow the convention.
    """
    parts = game_name.split(":")
    if len(parts) != 3 or parts[0] != "mainline":
        return None
    if not parts[1] or not parts[2]:
        return None
    return parts[1], parts[2]


# ============================================================
# MainlineEngine
# ============================================================

class MainlineEngine:
    """Stateful driver for one user's progress through one mainline.

    Holds NO combat logic — only orchestrates: load JSON → emit
    dialogue URL → request a battle → wait for ``game.status ==
    "finished"`` → emit next dialogue URL or VICTORY.

    The engine is created per-request by the route handler. It is
    cheap to construct (no IO beyond a ``load_mainline`` cache hit).
    """

    def __init__(
        self,
        session: AsyncSession,
        profile: Any,
        mainline: Mainline,
    ) -> None:
        self.session = session
        self.profile = profile
        self.mainline = mainline
        # Read-once state. Updates from the profile are pulled on demand
        # via the property accessors so the engine stays consistent with
        # any mutations the route handler applied earlier in the
        # request lifecycle.
        self._state: MainlineState = self._state_from_profile()
        logger.debug(
            "engine init: user=%s mainline=%s battles=%d dialogues=%d state=%s",
            getattr(profile, "user_name", "?"), mainline.id,
            len(mainline.battles), len(mainline.dialogues), self._state.value,
        )

    # ---------- State derivation ----------

    def _state_from_profile(self) -> MainlineState:
        active = _profile_active_mainline(self.profile)
        if active is None:
            return MainlineState.MENU
        if active != self.mainline.id:
            # Different campaign is active — treat as menu for this one.
            return MainlineState.MENU
        return MainlineState.DIALOGUE

    # ---------- Public read-only state ----------

    @property
    def state(self) -> MainlineState:
        logger.debug(
            "current state: user=%s mainline=%s state=%s battle_index=%d",
            getattr(self.profile, "user_name", "?"), self.mainline.id,
            self._state.value, self.current_battle_index,
        )
        return self._state

    @property
    def total_battles(self) -> int:
        return len(self.mainline.battles)

    @property
    def current_battle_index(self) -> int:
        """0-based index of the *next* battle the player must fight.

        Reads ``battle_index`` from ``profile.mainline_progress``; falls
        back to 0 when the column is missing or the dict is empty.
        """
        prog = _profile_progress(self.profile)
        try:
            return max(0, int(prog.get("battle_index", 0)))
        except (TypeError, ValueError):
            return 0

    @property
    def current_battle(self) -> Optional[BattleSpec]:
        idx = self.current_battle_index
        if 0 <= idx < self.total_battles:
            return self.mainline.battles[idx]
        return None

    @property
    def current_scene_id(self) -> str:
        """The current scene key (e.g. ``"intro"``)."""
        prog = _profile_progress(self.profile)
        return prog.get("scene_id", "intro") or "intro"

    # ---------- Pure query: next step ----------

    def next_step(self) -> MainlineStepOut:
        """Compute the next frame. PURE: no side effects.

        Returns:
            ``MainlineStepOut`` whose ``state`` is one of:
              - ``dialogue`` : show a scene next
              - ``battle``   : launch/continue the current battle
              - ``victory``  : campaign cleared, give rewards

            For ``dialogue`` frames, ``dialogue_url`` is the path
            relative to ``game/`` (e.g. ``stories/chapter_01/intro.json``)
            — the frontend calls ``GET /mainlines/dialogue?path=...``
            to fetch the scene list.
        """
        total = self.total_battles
        idx = self.current_battle_index

        # Past the last battle -> VICTORY already granted.
        if idx >= total:
            return MainlineStepOut(
                state=MainlineState.VICTORY.value,
                total_battles=total,
                battle_index=idx,
            )

        # No active campaign for this mainline -> first frame is DIALOGUE.
        active = _profile_active_mainline(self.profile)
        if active is None or active != self.mainline.id:
            battle = self.mainline.battles[idx]
            url = self.mainline.dialogues.get(battle.pre_battle_dialogue or "")
            return MainlineStepOut(
                state=MainlineState.DIALOGUE.value,
                dialogue_url=url,
                dialogue_key=battle.pre_battle_dialogue,
                battle_id=battle.id,
                battle_index=idx,
                total_battles=total,
            )

        # Mid-campaign: look at the scene the cursor points at. If it
        # matches a pre_battle_dialogue or post_battle_dialogue for the
        # current battle, render dialogue; otherwise the player should
        # be on the board.
        scene_id = self.current_scene_id
        battle = self.mainline.battles[idx]
        if battle.pre_battle_dialogue and scene_id == battle.pre_battle_dialogue:
            return MainlineStepOut(
                state=MainlineState.DIALOGUE.value,
                dialogue_url=self.mainline.dialogues.get(battle.pre_battle_dialogue),
                dialogue_key=battle.pre_battle_dialogue,
                battle_id=battle.id,
                battle_index=idx,
                total_battles=total,
            )
        if battle.post_battle_dialogue and scene_id == battle.post_battle_dialogue:
            return MainlineStepOut(
                state=MainlineState.DIALOGUE.value,
                dialogue_url=self.mainline.dialogues.get(battle.post_battle_dialogue),
                dialogue_key=battle.post_battle_dialogue,
                battle_id=battle.id,
                battle_index=idx,
                total_battles=total,
            )

        # Default: the player should be in the current battle.
        return MainlineStepOut(
            state=MainlineState.BATTLE.value,
            battle_id=battle.id,
            battle_index=idx,
            total_battles=total,
        )

    # ---------- Lifecycle helpers ----------

    async def mark_scene_done(
        self,
        scene_id: str,
        *,
        next_battle: bool = False,
    ) -> dict:
        """Update the profile's progress cursor.

        This is the ONLY place the engine writes to ``mainline_progress``
        (apart from ``apply_victory`` and ``abandon``). It is called by
        the route handler — never directly by the engine itself.

        Returns the new ``mainline_progress`` dict.
        """
        from app.progression.service import ProgressionService  # local import

        user_name = getattr(self.profile, "user_name", None)
        if not user_name:
            raise ValueError("profile has no user_name; cannot update progress")

        before_idx = self.current_battle_index
        logger.debug(
            "scene marking done: user=%s mainline=%s scene=%s next_battle=%s "
            "battle_index_before=%d",
            user_name, self.mainline.id, scene_id, next_battle, before_idx,
        )
        svc = ProgressionService(self.session)
        try:
            summary = await svc.advance_mainline_progress(
                user_name,
                scene_id=scene_id,
                next_battle=next_battle,
            )
        except Exception:
            logger.exception(
                "scene mark failed: user=%s mainline=%s scene=%s",
                user_name, self.mainline.id, scene_id,
            )
            raise
        # Reload profile so subsequent reads see the new values.
        await self.session.refresh(self.profile)
        after_idx = self.current_battle_index
        logger.debug(
            "scene marked done: %s → battle_index=%d (delta=%+d)",
            scene_id, after_idx, after_idx - before_idx,
        )
        return dict(summary.mainline_progress)

    async def apply_victory(self) -> MainlineRewards:
        """Called after the last battle is won.

        Awards ``mainline.rewards_on_clear`` to the profile (gold +
        unlocked_class) and clears the active mainline cursor. The
        engine returns the rewards object so the route layer can echo
        it back to the client.
        """
        from app.progression.service import ProgressionService

        user_name = getattr(self.profile, "user_name", None)
        if not user_name:
            raise ValueError("profile has no user_name; cannot grant rewards")

        rewards = self.mainline.rewards_on_clear
        logger.info(
            "victory START: user=%s mainline=%s gold=+%d unlock=%s exp_per_unit=+%d",
            user_name, self.mainline.id,
            rewards.gold or 0, rewards.unlock_class or "-",
            rewards.exp_per_unit or 0,
        )

        # Grant rewards onto the profile directly (no service-layer
        # helper exists for this yet — agent A's scope). Mutations are
        # flushed by the caller's commit.
        if rewards.gold:
            self.profile.gold = (self.profile.gold or 0) + int(rewards.gold)
        if rewards.unlock_class:
            unlocked = list(self.profile.unlocked_classes or [])
            if rewards.unlock_class not in unlocked:
                unlocked.append(rewards.unlock_class)
                self.profile.unlocked_classes = unlocked

        # Clear active mainline via the service (single source of truth).
        svc = ProgressionService(self.session)
        await svc.advance_mainline_progress(
            user_name, scene_id=None, next_battle=True,
        )
        await self.session.flush()

        # Award exp per owned unit (best-effort — does not fail victory).
        exp_units_awarded = 0
        if rewards.exp_per_unit:
            try:
                from app.progression.service import ProgressionService as _PS

                svc2 = _PS(self.session)
                units = list(getattr(self.profile, "units", []) or [])
                for u in units:
                    try:
                        await svc2.award_xp(u.id, int(rewards.exp_per_unit), reason="mainline_clear")
                        exp_units_awarded += 1
                    except Exception:  # pragma: no cover — defensive
                        logger.exception(
                            "Failed to award mainline exp to unit %s", getattr(u, "id", "?")
                        )
            except Exception:  # pragma: no cover — defensive
                logger.exception("Failed to award mainline clear exp")

        await self.session.refresh(self.profile)
        logger.info(
            "victory applied: user=%s mainline=%s gold=+%d unlocked=%s exp=+%d "
            "units_awarded=%d",
            user_name, self.mainline.id,
            rewards.gold or 0, rewards.unlock_class or "-",
            rewards.exp_per_unit or 0, exp_units_awarded,
        )
        return rewards

    async def abandon(self) -> Optional[str]:
        """Drop the active mainline without finishing it.

        Returns the abandoned mainline id (or None if nothing was
        active).
        """
        from app.progression.service import ProgressionService

        user_name = getattr(self.profile, "user_name", None)
        if not user_name:
            logger.debug("abandon: no user_name on profile; nothing to do")
            return None
        old = _profile_active_mainline(self.profile)
        logger.debug(
            "abandon: user=%s mainline=%s was_active=%s",
            user_name, self.mainline.id, old is not None,
        )
        svc = ProgressionService(self.session)
        try:
            await svc.abandon_mainline(user_name)
        except Exception:
            logger.exception(
                "mainline abandon failed: user=%s mainline=%s",
                user_name, self.mainline.id,
            )
            raise
        await self.session.refresh(self.profile)
        logger.info(
            "mainline abandoned: user=%s mainline=%s was_active=%s",
            user_name, self.mainline.id, old is not None,
        )
        return old

    # ---------- Dialogues ----------

    def get_dialogue_path(self, key: str) -> Optional[str]:
        """Resolve a scene key (e.g. ``"intro"``) to its file path.

        Returns ``None`` if the key isn't declared in this mainline's
        ``dialogues`` map.
        """
        return self.mainline.dialogues.get(key)

    def pre_battle_dialogue_for(self, battle_index: int) -> Optional[str]:
        if 0 <= battle_index < self.total_battles:
            return self.mainline.battles[battle_index].pre_battle_dialogue
        return None

    def post_battle_dialogue_for(self, battle_index: int) -> Optional[str]:
        if 0 <= battle_index < self.total_battles:
            return self.mainline.battles[battle_index].post_battle_dialogue
        return None

    # ---------- Battle spawning (used by the route handler) ----------

    def battle_pre_battle_dialogue_path(self, battle_index: int) -> Optional[str]:
        key = self.pre_battle_dialogue_for(battle_index)
        if not key:
            return None
        return self.get_dialogue_path(key)

    def battle_post_battle_dialogue_path(self, battle_index: int) -> Optional[str]:
        key = self.post_battle_dialogue_for(battle_index)
        if not key:
            return None
        return self.get_dialogue_path(key)


# ============================================================
# Convenience builders
# ============================================================

def utcnow_iso() -> str:
    """ISO-8601 UTC timestamp for ``abandoned_at`` etc."""
    return datetime.now(timezone.utc).isoformat()


def load_engine(
    session: AsyncSession, profile: Any, mainline_id: str
) -> MainlineEngine:
    """Build an engine for ``(profile, mainline_id)``.

    Raises ``MainlineNotFound`` if the id doesn't exist on disk (so
    the route handler can return a clean 404).
    """
    ml = load_mainline(mainline_id)
    return MainlineEngine(session, profile, ml)


__all__ = [
    "MainlineState",
    "MainlineEngine",
    "load_engine",
    "mainline_game_name",
    "parse_mainline_game_name",
    "utcnow_iso",
]
