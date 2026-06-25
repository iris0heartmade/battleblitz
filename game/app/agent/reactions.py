"""
Emotional reaction system for the LLM agent.

When the LLM agent makes a move, it can also "speak" — a short Chinese
comment that reflects its personality and the in-game event. These are
pre-written templates (no extra LLM call) so they cost ~0ms.

Reactions are tied to *events*:

  kill       — our attack killed an enemy unit
  killed     — one of our units died (since the previous turn)
  damaged    — one of our units took damage but survived
  castled    — we moved onto an unowned / enemy castle
  victory    — we won the game
  defeat     — we lost the game
  skill_use  — we used a skill (heal / rally)

Each (personality, event) maps to a list of candidate templates; we pick
one at random so the same trigger doesn't always produce the same line.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Literal


# ----------------------------------------------------------------
# Event + mood enums
# ----------------------------------------------------------------

Event = Literal[
    "kill", "killed", "damaged", "castled", "victory", "defeat",
    "skill_use", "turn_start",
]
Mood = Literal["joy", "anger", "frustrated", "smug", "disappointed", "neutral", "relieved"]


# ----------------------------------------------------------------
# Reaction dataclass
# ----------------------------------------------------------------

@dataclass(frozen=True)
class Reaction:
    """One piece of AI commentary. Stored in ActionLog and shown to players."""
    event: Event
    mood: Mood
    text: str            # ≤40 Chinese chars, shown to player

    def __post_init__(self):
        if len(self.text) > 40:
            object.__setattr__(self, "text", self.text[:40])


# ----------------------------------------------------------------
# Template library
# ----------------------------------------------------------------
# Keys: (personality, event)  →  list of (mood, text) tuples.
# Falls back to ("balanced", event) if personality-specific templates
# are missing, and finally to a built-in neutral default.

_PERSONALITIES = ("aggressive", "defensive", "balanced", "trickster")

_TEMPLATES: dict[tuple[str, str], list[tuple[Mood, str]]] = {
    # ── aggressive ────────────────────────────────────────────
    ("aggressive", "kill"): [
        ("joy", "哈！又一个！"),
        ("joy", "爽！杀得痛快！"),
        ("joy", "倒下吧你！"),
        ("smug", "就这？"),
        ("joy", "再来十个都不够！"),
    ],
    ("aggressive", "killed"): [
        ("anger", "可恶！这笔账记下了！"),
        ("anger", "别让我再遇见你！"),
        ("anger", "哼，只是小失误！"),
        ("anger", "敢杀我的人？"),
    ],
    ("aggressive", "damaged"): [
        ("frustrated", "这点伤算什么！"),
        ("frustrated", "哼，无所谓！"),
        ("frustrated", "皮外伤！"),
    ],
    ("aggressive", "castled"): [
        ("joy", "地盘扩张！"),
        ("smug", "这座城是我的！"),
        ("joy", "抢下一城！"),
    ],
    ("aggressive", "victory"): [
        ("smug", "这就是差距！"),
        ("smug", "毫无悬念！"),
        ("joy", "碾压局！"),
    ],
    ("aggressive", "defeat"): [
        ("anger", "下次绝对赢回来！"),
        ("anger", "你们等着！"),
        ("frustrated", "这次不算！"),
    ],
    ("aggressive", "skill_use"): [
        ("smug", "给我上！"),
    ],

    # ── defensive ─────────────────────────────────────────────
    ("defensive", "kill"): [
        ("relieved", "终于解决了一个威胁。"),
        ("neutral", "稳妥拿下。"),
        ("joy", "这下稳了。"),
    ],
    ("defensive", "killed"): [
        ("disappointed", "唉，又损失了。"),
        ("frustrated", "这下麻烦大了。"),
        ("disappointed", "我太大意了。"),
    ],
    ("defensive", "damaged"): [
        ("frustrated", "这伤不轻。"),
        ("frustrated", "需要调整站位了。"),
        ("disappointed", "不该站在这。"),
    ],
    ("defensive", "castled"): [
        ("relieved", "多了一个据点。"),
        ("neutral", "城堡已占据。"),
    ],
    ("defensive", "victory"): [
        ("relieved", "守住了。"),
        ("neutral", "稳扎稳打的胜利。"),
    ],
    ("defensive", "defeat"): [
        ("disappointed", "防线还是被突破了。"),
        ("frustrated", "下次要更谨慎。"),
    ],
    ("defensive", "skill_use"): [
        ("neutral", "集结完毕。"),
    ],

    # ── balanced ──────────────────────────────────────────────
    ("balanced", "kill"): [
        ("joy", "干得漂亮。"),
        ("neutral", "又拿下一城。"),
        ("joy", "漂亮！"),
    ],
    ("balanced", "killed"): [
        ("disappointed", "唉，损失了。"),
        ("frustrated", "这下麻烦了。"),
    ],
    ("balanced", "damaged"): [
        ("frustrated", "被打了。"),
        ("neutral", "需要调整。"),
    ],
    ("balanced", "castled"): [
        ("neutral", "占领新据点。"),
        ("joy", "城堡到手。"),
    ],
    ("balanced", "victory"): [
        ("joy", "赢了。"),
    ],
    ("balanced", "defeat"): [
        ("disappointed", "这次失算了。"),
    ],
    ("balanced", "skill_use"): [
        ("neutral", "技能就绪。"),
    ],

    # ── trickster ─────────────────────────────────────────────
    ("trickster", "kill"): [
        ("smug", "上钩了吧？"),
        ("joy", "哈哈，正中下怀！"),
        ("smug", "感谢送头！"),
    ],
    ("trickster", "killed"): [
        ("anger", "谁在阴我！"),
        ("frustrated", "这次是意外。"),
        ("anger", "这笔账记下了！"),
    ],
    ("trickster", "damaged"): [
        ("frustrated", "怎么被发现了？"),
        ("frustrated", "这个位置被看穿了。"),
    ],
    ("trickster", "castled"): [
        ("smug", "城堡？不，是陷阱。"),
        ("joy", "请君入瓮。"),
    ],
    ("trickster", "victory"): [
        ("smug", "一切尽在掌握。"),
        ("smug", "你以为自己会赢？"),
    ],
    ("trickster", "defeat"): [
        ("anger", "哼，下一把让你看看真的。"),
        ("frustrated", "他们运气好。"),
    ],
    ("trickster", "skill_use"): [
        ("smug", "惊喜在后面。"),
    ],
    # ── turn_start (all personalities) ────────────────────────
    ("aggressive", "turn_start"): [
        ("joy", "好，轮到我了！"),
        ("neutral", "该动手了。"),
    ],
    ("defensive", "turn_start"): [
        ("neutral", "稳步推进…"),
    ],
    ("balanced", "turn_start"): [
        ("neutral", "到我的回合。"),
    ],
    ("trickster", "turn_start"): [
        ("smug", "让好戏开始吧。"),
    ],
}


# Neutral fallback when nothing else matches. Never empty.
_NEUTRAL_FALLBACK: dict[str, tuple[Mood, str]] = {
    "kill":      ("neutral", "击杀了敌方单位。"),
    "killed":    ("disappointed", "单位阵亡。"),
    "damaged":   ("frustrated", "单位受伤。"),
    "castled":   ("neutral", "占领了城堡。"),
    "victory":   ("joy", "胜利。"),
    "defeat":    ("disappointed", "战败。"),
    "skill_use":  ("neutral", "使用了技能。"),
    "turn_start": ("neutral", "轮到我了。"),
}


# ----------------------------------------------------------------
# Public API
# ----------------------------------------------------------------

def generate_reaction(
    personality: str,
    event: Event,
    *,
    rng: random.Random | None = None,
) -> Reaction:
    """Pick a random template matching (personality, event).

    Falls back through:
      1. (personality, event) specific templates
      2. ("balanced", event) generic templates
      3. _NEUTRAL_FALLBACK[event]
    """
    rng = rng or random.Random()

    # 1. Personality-specific
    options = _TEMPLATES.get((personality, event), [])
    # 2. Balanced generic
    if not options:
        options = _TEMPLATES.get(("balanced", event), [])
    # 3. Hard-coded neutral
    if not options:
        if event in _NEUTRAL_FALLBACK:
            mood, text = _NEUTRAL_FALLBACK[event]
            return Reaction(event=event, mood=mood, text=text)
        # Last resort: completely unknown event — return a default reaction
        return Reaction(event=event, mood="neutral", text="……")

    mood, text = rng.choice(options)
    return Reaction(event=event, mood=mood, text=text)


def events_for_action(
    legal_action_kind: str,
    *,
    killed_target: bool = False,
    captured_castle: bool = False,
    used_skill: str | None = None,
) -> List[Event]:
    """Given the outcome flags of an executed action, return the event(s) it should trigger.

    Most actions produce zero or one event. `attack` may produce `kill` (if
    the target died); `move` may produce `castled`; `skill` may produce
    `skill_use` (and the caller can pick a more specific event).
    """
    events: list[Event] = []
    if legal_action_kind == "attack" and killed_target:
        events.append("kill")
    if legal_action_kind == "move" and captured_castle:
        events.append("castled")
    if legal_action_kind == "skill" and used_skill:
        events.append("skill_use")
    return events


def events_from_hp_diff(
    hp_before: dict[int, int],
    hp_after: dict[int, int],
) -> List[Event]:
    """Given HP at end-of-last-turn vs HP at start-of-this-turn, return events.

    Returns:
      - "killed" for each unit that was alive before and is dead now
      - "damaged" for each unit whose HP dropped but is still alive
    """
    events: list[Event] = []
    for uid, before_hp in hp_before.items():
        after_hp = hp_after.get(uid, 0)
        if before_hp > 0 and after_hp == 0:
            events.append("killed")
        elif after_hp < before_hp and after_hp > 0:
            events.append("damaged")
    return events
