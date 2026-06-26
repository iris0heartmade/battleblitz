"""
Service layer for progression — business orchestration on top of repos.

A service is a single class that holds the session and the repos it needs,
and exposes intent-named methods (create_profile, award_xp, promote).

Why a class instead of free functions:
  - One session injection point (we use FastAPI's Depends on the API layer)
  - Repos are constructed once, easy to mock in tests
  - Future "match-end hook" can live here: `apply_match_result(profile, snapshot)`
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional, Union

from sqlalchemy.ext.asyncio import AsyncSession

from app.progression.exceptions import (
    InvalidMainlineProgress,
    LevelCapReached,
    MainlineAlreadyActive,
    MainlineIdNotFound,
    NoActiveMainline,
    PromoteRequirementNotMet,
    TierCapReached,
)
from app.progression.leveling import (
    can_promote,
    can_level_up,
    award_exp as _award_exp,
    promote as _promote,
)
from app.progression.models import PlayerProfile, UnitInstance
from app.progression.repository import ProfileRepository, UnitRepository

logger = logging.getLogger(__name__)


# A validator raises MainlineIdNotFound if `mainline_id` is unknown.
# Default implementation lazily imports `app.mainline.loader` (avoiding
# the circular dependency that a top-level import would create). Tests
# can inject a mock via the ProgressionService constructor.
MainlineValidator = Callable[[str], None]


def _default_mainline_validator(mainline_id: str) -> None:
    """Default mainline id validator — delegates to app.mainline.loader.

    Imported lazily so `app.progression` does not hard-depend on
    `app.mainline` at import time. The loader's `load_mainline` raises
    `MainlineNotFound` (subclass of `MainlineError`); we translate it
    to `MainlineIdNotFound` so the progression namespace is self-contained.
    """
    from app.mainline.loader import MainlineNotFound, load_mainline
    try:
        load_mainline(mainline_id)
    except MainlineNotFound as exc:
        raise MainlineIdNotFound(
            f"mainline {mainline_id!r} not found in mainlines/"
        ) from exc


@dataclass(frozen=True)
class AwardXpSummary:
    unit_id: int
    levels_gained: int
    new_level: int
    new_exp: int
    talent_points_awarded: int
    capped: bool


@dataclass(frozen=True)
class PromoteSummary:
    unit_id: int
    old_tier: int
    new_tier: int
    new_level_cap: int


@dataclass(frozen=True)
class MainlineProgressSummary:
    """Returned by every mainline-progress service method.

    The HTTP layer renders this back to the client so it can show the
    new state (active id, current cursor, remaining battle count).
    """
    user_name: str
    active_mainline: Optional[str]
    mainline_progress: dict
    # True iff the operation finished the last battle and auto-cleared
    # the active mainline. Useful for the client to show a "VICTORY"
    # screen.
    cleared: bool = False


class ProgressionService:
    """Orchestrates profile + unit + leveling operations."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        mainline_validator: Optional[MainlineValidator] = None,
    ) -> None:
        self.session = session
        self.profiles = ProfileRepository(session)
        self.units = UnitRepository(session)
        # Resolve lazily so importing this module never touches mainline.
        self._mainline_validator: MainlineValidator = (
            mainline_validator or _default_mainline_validator
        )

    # ── Profiles ────────────────────────────────────────────

    async def create_profile(
        self, user_name: str, *, initial_rating: int | None = None
    ) -> PlayerProfile:
        profile = await self.profiles.create(
            user_name, initial_rating=initial_rating
        )
        await self.session.flush()
        logger.info(
            "Profile created: id=%d user=%r rating=%d",
            profile.id, profile.user_name, profile.rating,
        )
        return profile

    async def get_profile(self, profile_id: int) -> PlayerProfile:
        return await self.profiles.get(profile_id)

    async def list_profiles(self, limit: int = 100, offset: int = 0) -> list[PlayerProfile]:
        return list(await self.profiles.list_all(limit=limit, offset=offset))

    # ── Units ───────────────────────────────────────────────

    async def create_unit(
        self,
        profile_id: int,
        base_type: str,
        nickname: str,
        personality: str = "tactical",
    ) -> UnitInstance:
        # Confirm profile exists (will raise ProfileNotFound if not)
        await self.profiles.get(profile_id)
        unit = await self.units.create(
            profile_id=profile_id,
            base_type=base_type,
            nickname=nickname,
            personality=personality,
        )
        await self.session.flush()
        logger.info(
            "Unit created: id=%d profile=%d type=%s nick=%r",
            unit.id, unit.profile_id, unit.base_type, unit.nickname,
        )
        return unit

    async def get_unit(self, unit_id: int) -> UnitInstance:
        return await self.units.get(unit_id)

    async def list_units(self, profile_id: int) -> list[UnitInstance]:
        return list(await self.units.list_for_profile(profile_id))

    # ── Leveling ────────────────────────────────────────────

    async def award_xp(
        self, unit_id: int, amount: int, *, reason: str = "manual"
    ) -> AwardXpSummary:
        unit = await self.units.get(unit_id)
        was_at_cap = not can_level_up(unit)
        old_level = unit.level

        result = _award_exp(unit, amount)
        capped = was_at_cap or not can_level_up(unit) and result.levels_gained == 0

        await self.session.flush()
        logger.info(
            "XP awarded: unit=%d amount=%d reason=%s levels=%d new_lv=%d",
            unit_id, amount, reason, result.levels_gained, result.new_level,
        )
        return AwardXpSummary(
            unit_id=unit_id,
            levels_gained=result.levels_gained,
            new_level=result.new_level,
            new_exp=unit.exp,
            talent_points_awarded=result.talent_points_awarded,
            capped=capped,
        )

    async def promote(
        self, unit_id: int, *, force: bool = False
    ) -> PromoteSummary:
        unit = await self.units.get(unit_id)

        if unit.tier >= 3:
            raise TierCapReached(f"unit {unit_id} is already at max tier (3)")

        if not can_promote(unit) and not force:
            from app.progression.leveling import TIER_PROMO_LEVEL_REQ
            required = TIER_PROMO_LEVEL_REQ.get(unit.tier, 99)
            raise PromoteRequirementNotMet(
                f"unit {unit_id} needs level {required} to promote from tier {unit.tier} "
                f"(currently level {unit.level})"
            )

        old_tier = unit.tier
        if force:
            # Bypass the level check inside _promote (debug/admin only).
            unit.tier += 1
        else:
            _promote(unit)

        from app.progression.leveling import max_level_for_tier
        new_cap = max_level_for_tier(unit.tier)
        await self.session.flush()
        logger.info(
            "Unit promoted: id=%d %d -> %d new_cap=%d force=%s",
            unit_id, old_tier, unit.tier, new_cap, force,
        )
        return PromoteSummary(
            unit_id=unit_id,
            old_tier=old_tier,
            new_tier=unit.tier,
            new_level_cap=new_cap,
        )

    # ── Mainline (campaign) progress — Step 2 ────────────────
    #
    # JSON contract for `PlayerProfile.mainline_progress`:
    #   {
    #     "battle_index": int,    # 0-based; == len(battles) => cleared
    #     "scene_id": str,        # key into Mainline.dialogues
    #     "started_at": str|None  # ISO-8601 UTC; None iff no active mainline
    #   }
    #
    # The service never imports `app.mainline` directly — instead it
    # delegates id existence checks to `self._mainline_validator`,
    # which is injected by the API layer (or defaults to a lazy loader
    # call for production use). This keeps the dependency direction
    # `progression -> mainline` (one-way) and lets tests mock the
    # validator without monkey-patching modules.

    def _build_mainline_progress(
        self,
        battle_index: int,
        scene_id: str,
        started_at: Optional[str],
    ) -> dict:
        """Validate + serialise a progress row to its JSON shape."""
        if battle_index < 0:
            raise InvalidMainlineProgress(
                f"battle_index must be >= 0, got {battle_index}"
            )
        if not isinstance(scene_id, str) or not scene_id:
            raise InvalidMainlineProgress("scene_id must be a non-empty string")
        return {
            "battle_index": int(battle_index),
            "scene_id": scene_id,
            "started_at": started_at,
        }

    async def set_active_mainline(
        self,
        user_name: str,
        mainline_id: str,
        *,
        force: bool = False,
    ) -> MainlineProgressSummary:
        """Begin (or reset) a campaign for the given player.

        - Validates the mainline id exists (delegated to
          `self._mainline_validator`).
        - If the profile already has an active mainline and `force` is
          False, raises `MainlineAlreadyActive`.
        - Otherwise writes the initial progress row
          (battle_index=0, scene_id="intro", started_at=now).

        The engine (Step 3) will later use the loaded mainline's
        `dialogues["intro"]` path to fetch the first script.
        """
        # Verify the mainline id exists. Raises MainlineIdNotFound.
        self._mainline_validator(mainline_id)

        profile = await self.profiles.get_by_name(user_name)
        if profile is None:
            # Re-use the existing 404 path so route handlers stay uniform.
            from app.progression.exceptions import ProfileNotFound
            raise ProfileNotFound(f"profile {user_name!r} not found")

        if profile.active_mainline is not None and not force:
            raise MainlineAlreadyActive(
                f"profile {user_name!r} already has an active mainline "
                f"({profile.active_mainline!r}); abandon it first or pass force=True"
            )

        started_at = datetime.now(timezone.utc).isoformat()
        # Default opening: first battle, "intro" dialogue (or first key
        # in `Mainline.dialogues` if "intro" is absent — the engine can
        # override later).
        try:
            from app.mainline.loader import load_mainline
            ml = load_mainline(mainline_id)
            scene_id = "intro" if "intro" in ml.dialogues else (
                next(iter(ml.dialogues)) if ml.dialogues else "intro"
            )
        except Exception:  # pragma: no cover — defensive
            scene_id = "intro"

        profile.active_mainline = mainline_id
        profile.mainline_progress = self._build_mainline_progress(
            battle_index=0,
            scene_id=scene_id,
            started_at=started_at,
        )
        await self.session.flush()
        logger.info(
            "Mainline started: user=%r mainline=%r force=%s",
            user_name, mainline_id, force,
        )
        return MainlineProgressSummary(
            user_name=user_name,
            active_mainline=profile.active_mainline,
            mainline_progress=dict(profile.mainline_progress),
            cleared=False,
        )

    async def advance_mainline_progress(
        self,
        user_name: str,
        *,
        scene_id: Optional[str] = None,
        next_battle: bool = False,
    ) -> MainlineProgressSummary:
        """Move the campaign cursor forward.

        Behaviour:
          * If neither `scene_id` nor `next_battle` is set this is a
            no-op (returns the current state).
          * If the profile has no active mainline, raises
            `NoActiveMainline`.
          * If `next_battle` is True, increments `battle_index` by 1.
          * If `scene_id` is given, sets the dialogue cursor. The id
            is validated against the active mainline's `dialogues` map.
          * If the new `battle_index` equals `len(battles)`, the
            mainline is auto-cleared (`active_mainline` set to None,
            `mainline_progress` reset to an empty dict) and `cleared`
            is True on the response.
        """
        profile = await self.profiles.get_by_name(user_name)
        if profile is None:
            from app.progression.exceptions import ProfileNotFound
            raise ProfileNotFound(f"profile {user_name!r} not found")
        if profile.active_mainline is None:
            raise NoActiveMainline(
                f"profile {user_name!r} has no active mainline to advance"
            )

        # Load the mainline to know battle count + dialogue keys.
        from app.mainline.loader import MainlineNotFound, load_mainline
        try:
            ml = load_mainline(profile.active_mainline)
        except MainlineNotFound as exc:
            # Active mainline vanished from disk — treat as no-active
            # and surface to caller via the same exception type so the
            # route can return 409.
            raise NoActiveMainline(
                f"active mainline {profile.active_mainline!r} is no longer "
                f"available on disk"
            ) from exc

        current = dict(profile.mainline_progress or {})
        cur_index = int(current.get("battle_index", 0))
        cur_scene = current.get("scene_id", "intro")
        cur_started = current.get("started_at")

        # Apply updates.
        new_index = cur_index
        new_scene = cur_scene
        if next_battle:
            new_index = cur_index + 1
        if scene_id is not None:
            if scene_id not in ml.dialogues:
                raise InvalidMainlineProgress(
                    f"scene_id {scene_id!r} not in mainline "
                    f"{profile.active_mainline!r}.dialogues "
                    f"(have {sorted(ml.dialogues)})"
                )
            new_scene = scene_id

        # Auto-clear when the cursor walks off the end of the battle list.
        cleared = new_index >= len(ml.battles)
        if cleared:
            profile.active_mainline = None
            profile.mainline_progress = self._build_mainline_progress(
                battle_index=new_index,
                scene_id=new_scene,
                started_at=None,  # no campaign active
            )
            await self.session.flush()
            logger.info(
                "Mainline cleared: user=%r finished %d battles",
                user_name, len(ml.battles),
            )
        else:
            profile.active_mainline = profile.active_mainline
            profile.mainline_progress = self._build_mainline_progress(
                battle_index=new_index,
                scene_id=new_scene,
                started_at=cur_started,
            )
            await self.session.flush()
            logger.info(
                "Mainline advanced: user=%r mainline=%r index=%d scene=%r",
                user_name, profile.active_mainline, new_index, new_scene,
            )

        return MainlineProgressSummary(
            user_name=user_name,
            active_mainline=profile.active_mainline,
            mainline_progress=dict(profile.mainline_progress),
            cleared=cleared,
        )

    async def abandon_mainline(
        self, user_name: str
    ) -> MainlineProgressSummary:
        """Drop the active mainline (if any) without finishing it.

        Idempotent: returns the current state even when there is no
        active mainline. The route layer surfaces a 200 with the
        cleared payload in that case.
        """
        profile = await self.profiles.get_by_name(user_name)
        if profile is None:
            from app.progression.exceptions import ProfileNotFound
            raise ProfileNotFound(f"profile {user_name!r} not found")
        if profile.active_mainline is not None:
            old = profile.active_mainline
            profile.active_mainline = None
            profile.mainline_progress = self._build_mainline_progress(
                battle_index=0,
                scene_id="intro",
                started_at=None,
            )
            await self.session.flush()
            logger.info("Mainline abandoned: user=%r mainline=%r", user_name, old)
        return MainlineProgressSummary(
            user_name=user_name,
            active_mainline=profile.active_mainline,
            mainline_progress=dict(profile.mainline_progress or {}),
            cleared=profile.active_mainline is None,
        )


__all__ = [
    "ProgressionService",
    "AwardXpSummary",
    "PromoteSummary",
    "MainlineProgressSummary",
    "MainlineValidator",
]
