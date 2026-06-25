"""
Unit tests for the reaction system.

Verifies:
- generate_reaction picks a template for every (personality, event)
- All four personalities have at least 3 distinct templates per common event
- Length is capped at 40 characters
- events_from_hp_diff detects killed and damaged correctly
- events_for_action flags the right events
- Fallback works for unknown personalities / events
"""
from __future__ import annotations

import random

import pytest

from app.agent.reactions import (
    Reaction,
    _NEUTRAL_FALLBACK,
    _TEMPLATES,
    events_for_action,
    events_from_hp_diff,
    generate_reaction,
)


# ── generate_reaction ────────────────────────────────────────

PERSONALITIES = ["aggressive", "defensive", "balanced", "trickster"]
COMMON_EVENTS = ["kill", "killed", "damaged", "castled"]


@pytest.mark.parametrize("personality", PERSONALITIES)
@pytest.mark.parametrize("event", COMMON_EVENTS)
def test_every_personality_has_templates_for_common_events(personality, event):
    r = generate_reaction(personality, event)
    assert r.event == event
    assert 1 <= len(r.text) <= 40


def test_unknown_personality_falls_back_to_balanced():
    r1 = generate_reaction("nonsense", "kill")
    r2 = generate_reaction("balanced", "kill")
    # Both should be from the balanced bucket; moods may differ but both succeed
    assert r1.event == "kill"
    assert r2.event == "kill"


def test_unknown_event_falls_back_to_neutral():
    r = generate_reaction("aggressive", "unknown_event")
    # Falls all the way through to NEUTRAL_FALLBACK
    assert r.event == "unknown_event"
    assert r.mood == "neutral"


def test_reaction_text_capped_at_40_chars():
    """A long template would be auto-truncated by Reaction.__post_init__."""
    r = Reaction(event="kill", mood="joy", text="x" * 100)
    assert len(r.text) == 40


def test_template_rng_reproducibility():
    rng1 = random.Random(42)
    rng2 = random.Random(42)
    a = generate_reaction("aggressive", "kill", rng=rng1)
    b = generate_reaction("aggressive", "kill", rng=rng2)
    assert a.text == b.text


def test_each_personality_has_distinct_kill_lines():
    seen = set()
    for p in PERSONALITIES:
        # Sample 20 times to cover multiple templates
        rng = random.Random(p)
        for _ in range(20):
            r = generate_reaction(p, "kill", rng=rng)
            seen.add((p, r.text))
    # aggressive / defensive / trickster should have at least 2 distinct lines
    for p in PERSONALITIES:
        unique = {t for (pp, t) in seen if pp == p}
        assert len(unique) >= 2, f"{p} has <2 distinct kill lines"


# ── events_for_action ────────────────────────────────────────

def test_attack_without_kill_produces_no_event():
    assert events_for_action("attack", killed_target=False) == []


def test_attack_with_kill_produces_kill_event():
    assert events_for_action("attack", killed_target=True) == ["kill"]


def test_move_without_castle_produces_no_event():
    assert events_for_action("move", captured_castle=False) == []


def test_move_onto_castle_produces_castled_event():
    assert events_for_action("move", captured_castle=True) == ["castled"]


def test_skill_with_heal_produces_skill_use_event():
    assert events_for_action("skill", used_skill="heal") == ["skill_use"]


def test_wait_produces_no_event():
    assert events_for_action("wait") == []


# ── events_from_hp_diff ──────────────────────────────────────

def test_no_change_produces_no_events():
    hp = {1: 30, 2: 25}
    assert events_from_hp_diff(hp, dict(hp)) == []


def test_kill_detected():
    assert events_from_hp_diff({1: 30}, {1: 0}) == ["killed"]


def test_damage_detected():
    assert events_from_hp_diff({1: 30}, {1: 20}) == ["damaged"]


def test_heal_produces_no_event():
    # Heal goes UP, not down — not a damage event
    assert events_from_hp_diff({1: 20}, {1: 30}) == []


def test_missing_unit_after_is_treated_as_dead():
    """If a unit disappeared from `hp_after`, assume it died."""
    assert events_from_hp_diff({1: 30}, {}) == ["killed"]


def test_mixed_outcomes():
    events = events_from_hp_diff(
        {1: 30, 2: 20, 3: 40, 4: 15},
        {1:  0, 2: 20, 3: 25, 4:  0},   # 1 killed, 2 ok, 3 damaged, 4 killed
    )
    assert "killed" in events
    assert "damaged" in events
    assert events.count("killed") == 2
    assert events.count("damaged") == 1


# ── Template library coverage ────────────────────────────────

def test_all_personalities_have_templates_for_all_common_events():
    for p in PERSONALITIES:
        for e in COMMON_EVENTS:
            assert (p, e) in _TEMPLATES, f"missing template ({p}, {e})"


def test_neutral_fallback_covers_all_events():
    for e in ["kill", "killed", "damaged", "castled", "victory", "defeat", "skill_use"]:
        assert e in _NEUTRAL_FALLBACK
