"""Authoritative rules for commander-point allocations.

This module intentionally has no HTTP or database dependencies.  Callers
provide an existing :class:`CommanderAllocation`; the rules calculate the
price and validate both the requested stat and the selected mercenary type.
Battle spawning will consume the resulting ``unit_type_upgrades`` in a later
phase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import AbstractSet, Mapping

from app.classes.units import type_ids
from app.mercenary_domain.state import CommanderAllocation


class MercenaryAllocationError(ValueError):
    """Base error for a commander allocation rejected by game rules."""


class UnknownMercenaryTypeError(MercenaryAllocationError):
    """The requested unit type is not available to this chapter."""


class InvalidMercenaryStatError(MercenaryAllocationError):
    """The requested stat has no commander-upgrade rule."""


class MercenaryUpgradeLimitError(MercenaryAllocationError):
    """The requested upgrade would exceed the configured stat cap."""


class MercenaryPointBudgetError(MercenaryAllocationError):
    """The requested upgrade would exceed the available commander points."""


@dataclass(frozen=True)
class UpgradeRule:
    """Cost and cap for one stat, expressed per mercenary unit type."""

    point_cost: int
    max_bonus: int

    def __post_init__(self) -> None:
        if self.point_cost < 1:
            raise ValueError("point_cost must be positive")
        if self.max_bonus < 1:
            raise ValueError("max_bonus must be positive")


DEFAULT_UPGRADE_RULES: Mapping[str, UpgradeRule] = {
    # HP has a lower price because its absolute values are larger than the
    # combat stats.  Mobility is deliberately scarce because it changes map
    # reachability rather than only combat efficiency.
    "hp": UpgradeRule(point_cost=2, max_bonus=20),
    "atk": UpgradeRule(point_cost=10, max_bonus=5),
    "def": UpgradeRule(point_cost=10, max_bonus=5),
    "matk": UpgradeRule(point_cost=10, max_bonus=5),
    "mdef": UpgradeRule(point_cost=10, max_bonus=5),
    "mov": UpgradeRule(point_cost=25, max_bonus=2),
}


@dataclass(frozen=True)
class MercenaryAllocationRules:
    """Declarative commander-allocation policy for a chapter.

    ``allowed_unit_types=None`` means every currently registered unit class is
    eligible.  A chapter can pass a finite set to restrict its roster without
    changing validation code.
    """

    stat_rules: Mapping[str, UpgradeRule] = field(
        default_factory=lambda: dict(DEFAULT_UPGRADE_RULES)
    )
    allowed_unit_types: AbstractSet[str] | None = None

    def available_unit_types(self) -> frozenset[str]:
        registered = frozenset(type_ids())
        if self.allowed_unit_types is None:
            return registered
        return frozenset(self.allowed_unit_types) & registered


DEFAULT_ALLOCATION_RULES = MercenaryAllocationRules()


def apply_allocation_to_unit(unit, upgrades: Mapping[str, Mapping[str, int]]) -> dict[str, int]:
    """Apply a validated generic-roster allocation to one battle unit.

    The caller chooses which units are mercenaries; heroes must remain on the
    separate campaign-progression path.  Returning the applied values keeps
    route-level audit logging deterministic and makes this helper usable for
    both map spawns and later barracks recruits.
    """
    applied = {
        stat: int(value)
        for stat, value in dict(upgrades.get(unit.unit_type, {})).items()
        if stat in DEFAULT_UPGRADE_RULES and int(value) > 0
    }
    hp = applied.get("hp", 0)
    if hp:
        unit.max_hp += hp
        unit.hp += hp
    unit.atk += applied.get("atk", 0)
    unit.def_ += applied.get("def", 0)
    unit.matk += applied.get("matk", 0)
    unit.mdef += applied.get("mdef", 0)
    mov = applied.get("mov", 0)
    if mov:
        # Clamp mov against STAT_CAPS["mov"] to prevent equipment / talent
        # exploits that would let a unit exceed the cap (spec §12).
        from app.progression.policies import STAT_CAPS
        new_mov = max(0, min(STAT_CAPS["mov"], unit.mov + mov))
        # Apply the same delta to mp (max-per-turn) so the runtime
        # `unit.mp` stays in sync.
        applied_delta = new_mov - unit.mov
        unit.mov = new_mov
        unit.mp = max(0, unit.mp + applied_delta)
    return applied


@dataclass(frozen=True)
class AllocationReceipt:
    """Server-calculated result returned to persistence or API layers."""

    unit_type: str
    stat: str
    value: int
    cost: int
    spent_points: int
    remaining_points: int


def apply_commander_upgrade(
    allocation: CommanderAllocation,
    *,
    unit_type: str,
    stat: str,
    value: int,
    rules: MercenaryAllocationRules = DEFAULT_ALLOCATION_RULES,
) -> AllocationReceipt:
    """Validate and apply one commander allocation with server-calculated cost.

    The caller must not supply a cost.  This prevents manipulated requests
    from turning one point of a high-impact stat into a cheap upgrade.
    """
    if value < 1:
        raise ValueError("upgrade value must be positive")
    if unit_type not in rules.available_unit_types():
        raise UnknownMercenaryTypeError(f"unknown or unavailable mercenary type: {unit_type}")

    stat_rule = rules.stat_rules.get(stat)
    if stat_rule is None:
        raise InvalidMercenaryStatError(f"unsupported mercenary upgrade stat: {stat}")

    current_value = int(allocation.unit_type_upgrades.get(unit_type, {}).get(stat, 0))
    if current_value + value > stat_rule.max_bonus:
        raise MercenaryUpgradeLimitError(
            f"{unit_type}.{stat} exceeds cap {stat_rule.max_bonus}"
        )

    cost = stat_rule.point_cost * value
    if allocation.spent_points + cost > allocation.total_points:
        raise MercenaryPointBudgetError(
            f"points exceeded: have {allocation.total_points - allocation.spent_points}, need {cost}"
        )

    allocation.add_upgrade(unit_type, stat, value, cost)
    return AllocationReceipt(
        unit_type=unit_type,
        stat=stat,
        value=value,
        cost=cost,
        spent_points=allocation.spent_points,
        remaining_points=allocation.total_points - allocation.spent_points,
    )
