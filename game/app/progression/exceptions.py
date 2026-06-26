"""
Custom exceptions for the progression system.

Keep this small and specific — call sites should be able to catch the
exact failure mode and map it to an HTTP status.
"""
from __future__ import annotations


class ProgressionError(Exception):
    """Base for all progression-domain errors."""


class ProfileNotFound(ProgressionError):
    pass


class UnitNotFound(ProgressionError):
    pass


class ProfileAlreadyExists(ProgressionError):
    pass


class UnitAlreadyExists(ProgressionError):
    pass


class InvalidNickname(ProgressionError):
    """Nickname is empty, too long, or contains bad characters."""


class LevelCapReached(ProgressionError):
    """Unit is at its tier's max level."""


class TierCapReached(ProgressionError):
    """Unit is already at max tier (3)."""


class PromoteRequirementNotMet(ProgressionError):
    """Unit doesn't meet the level requirement for promotion."""


# ============================================================
# Mainline (campaign) errors — Step 2
# ============================================================

class MainlineIdNotFound(ProgressionError):
    """The requested mainline id has no JSON file on disk.

    Mirrors `app.mainline.loader.MainlineNotFound` but lives in the
    progression namespace so the service can raise it without depending
    on the mainline module (avoids circular import — see service.py).
    """


class MainlineAlreadyActive(ProgressionError):
    """A campaign is already active for this profile.

    Start a new mainline only after the current one is abandoned or
    cleared.
    """


class NoActiveMainline(ProgressionError):
    """Profile has no active campaign, but the operation needs one.

    Raised by advance_progress / abandon_mainline when `active_mainline`
    is NULL.
    """


class InvalidMainlineProgress(ProgressionError):
    """The supplied mainline_progress payload is malformed.

    E.g. missing keys, wrong types, battle_index out of range.
    """
