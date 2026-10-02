"""L3 — `add_effect` must not mutate effect dicts already held by callers.

The previous implementation would `eff["remaining_turns"] = ...` directly on
the existing dict. Any caller that did `old = find_effect(unit, "poison")`
and then later called `add_effect(unit, "poison", ...)` would see `old` get
silently updated. The fix: build a new dict, swap it into the list.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.status.effects import (
    add_effect,
    find_effect,
)


def _mk_unit(effects=None):
    return SimpleNamespace(status_effects=list(effects or []))


class TestAddEffectNoMutation:
    def test_preexisting_effect_dict_not_mutated(self):
        """L3 主场景:caller 提前拿到 effect 引用,后续 add 不应改它。"""
        u = _mk_unit()
        first = add_effect(u, "poison", applied_turn=1, remaining_turns=3)
        # Caller keeps a reference to the first dict.
        before_id = id(first)
        before_remaining = first["remaining_turns"]

        # Second add on the same type.
        second = add_effect(u, "poison", applied_turn=2, remaining_turns=2)

        # New effect is a *new* dict (different object), not the same one
        # mutated in place.
        assert id(first) != id(second)
        # Caller's reference is untouched.
        assert first["remaining_turns"] == before_remaining
        assert id(first) == before_id
        # And the unit's stored list points at the new one.
        assert find_effect(u, "poison") is second

    def test_preexisting_params_dict_not_mutated(self):
        """Same hazard for nested params dict — common bug surface."""
        u = _mk_unit()
        first = add_effect(u, "slow", applied_turn=1, params={"mov_mult": 0.5})
        # Capture the params dict identity.
        first_params_id = id(first["params"])

        add_effect(u, "slow", applied_turn=2, params={"mov_mult": 0.3, "extra": 1})
        # Old effect's params dict was not mutated.
        assert first["params"] == {"mov_mult": 0.5}
        assert id(first["params"]) == first_params_id

    def test_preexisting_applied_turn_not_overwritten_silently(self):
        """Caller keeps applied_turn reference; re-add must build new dict."""
        u = _mk_unit()
        first = add_effect(u, "blind", applied_turn=5, remaining_turns=2)
        assert first["applied_turn"] == 5

        add_effect(u, "blind", applied_turn=8, remaining_turns=4)
        # First ref still says 5 (not silently bumped to 8).
        assert first["applied_turn"] == 5
        # Stored one says 8.
        assert find_effect(u, "blind")["applied_turn"] == 8

    def test_preexisting_applied_by_preserved_when_new_is_none(self):
        """If new applied_by is None, keep the previous value (semantics
        preserved from the old implementation; explicit assertion so a
        refactor doesn't drop the rule)."""
        u = _mk_unit()
        first = add_effect(u, "paralyze", applied_turn=1, applied_by=42)

        # New add with applied_by=None — old 42 should remain on the new dict.
        second = add_effect(u, "paralyze", applied_turn=2, applied_by=None)
        assert second["applied_by"] == 42

    def test_preexisting_applied_by_overwritten_when_new_is_set(self):
        u = _mk_unit()
        add_effect(u, "paralyze", applied_turn=1, applied_by=42)
        second = add_effect(u, "paralyze", applied_turn=2, applied_by=99)
        assert second["applied_by"] == 99

    def test_new_effect_still_appended_normally(self):
        """First add still works as before — sanity check on the unchanged path."""
        u = _mk_unit()
        eff = add_effect(u, "poison", applied_turn=1)
        assert eff["type"] == "poison"
        assert eff["remaining_turns"] == 3  # EFFECT_DEFS["poison"] default
        assert eff["applied_turn"] == 1
        assert eff["applied_by"] is None
        assert eff["params"] == {"dmg_pct": 0.05}

    def test_list_replaced_not_extended_in_place_on_merge(self):
        """Sanity: when we replace an existing entry, the *list object*
        itself gets a new entry at the same index, not an extra one.
        Old impl extended by len-1; new impl preserves length."""
        u = _mk_unit()
        add_effect(u, "poison", applied_turn=1)
        assert len(u.status_effects) == 1
        add_effect(u, "poison", applied_turn=2)
        assert len(u.status_effects) == 1  # still one, just replaced
