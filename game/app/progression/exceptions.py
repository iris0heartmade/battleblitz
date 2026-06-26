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
