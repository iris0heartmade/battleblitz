"""
Emotional reaction system for the LLM agent — colloquial, in-the-moment,
like a real gamer reacting to events as they happen.

Design goals:
- Sound like a human player on voice chat / in-game chat, not a narrator.
- Reactions reference specific context (unit names, damage numbers) via
  `{var}` placeholders filled by the caller.
- Multiple variants per (personality, event) so the same trigger rarely
  repeats the same line.
- Events like crit, near-miss, and multi-kill chain tell a mini-story.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Literal


Event = Literal[
    "kill", "killed", "damaged", "castled", "victory", "defeat",
    "skill_use", "turn_start", "crit_kill", "near_miss",
    "move", "attack_hit", "wait", "heal",
]
Mood = Literal["joy", "anger", "frustrated", "smug", "disappointed", "neutral", "relieved", "panic"]


@dataclass(frozen=True)
class Reaction:
    event: Event
    mood: Mood
    text: str

    def __post_init__(self):
        if len(self.text) > 60:
            object.__setattr__(self, "text", self.text[:60])


# Placeholder docs for callers:
#   {u}   = my unit name (short)
#   {e}   = enemy unit name (short)
#   {dmg} = damage dealt / received
#   {hp}  = remaining HP
#   {x},{y}= coordinates
#   {n}   = number (how many units rallied, etc.)


_TEMPLATES: dict[tuple[str, str], list[tuple[Mood, str]]] = {

    # ── aggressive ────────────────────────────────────────────
    ("aggressive", "kill"): [
        ("joy", "卧槽秒了！"),
        ("joy", "{e}给我倒！"),
        ("smug", "就这？{e}就这？"),
        ("joy", "哈哈哈哈爽"),
        ("joy", "一刀一个"),
        ("smug", "还需要练练"),
        ("joy", "下一个谁？"),
        ("smug", "看到没看到没"),
        ("joy", "别跑啊{还没有跑}"),
        ("joy", "这{dmg}伤害你顶得住？"),
        ("smug", "早说你站位不行"),
    ],
    ("aggressive", "crit_kill"): [
        ("joy", "暴击！！"),
        ("joy", "卧槽暴击{dmg}！！"),
        ("joy", "天选之人"),
        ("smug", "这一刀暴击就问谁顶得住"),
        ("joy", "天命在我这边！"),
    ],
    ("aggressive", "near_miss"): [
        ("frustrated", "差{hp}滴血！！！"),
        ("frustrated", "不是就差{hp}血吗"),
        ("anger", "{hp}血跑了？？"),
        ("frustrated", "你是属泥鳅的吗"),
        ("frustrated", "啊？？这没死？？"),
    ],
    ("aggressive", "killed"): [
        ("anger", "{u}！！不！！"),
        ("anger", "你敢杀{u}？你等着"),
        ("frustrated", "啧，{u}没了"),
        ("anger", "好，你完了，下一个杀你"),
        ("frustrated", "这个走位出问题了"),
        ("anger", "记仇了记仇了"),
    ],
    ("aggressive", "damaged"): [
        ("frustrated", "挠痒痒呢？"),
        ("smug", "就掉{dmg}血也敢报"),
        ("neutral", "不疼"),
        ("smug", "打人不疼就别打"),
        ("frustrated", "{u}扛住"),
        ("neutral", "继续冲别怂"),
    ],
    ("aggressive", "castled"): [
        ("joy", "城拿下了！"),
        ("smug", "这城现在姓{u}了"),
        ("joy", "扩张扩张扩张"),
        ("joy", "地盘+1"),
        ("smug", "不好意思占了"),
        ("joy", "nice！卡住位置了"),
    ],
    ("aggressive", "victory"): [
        ("smug", "GG EZ"),
        ("joy", "碾压局有什么好说的"),
        ("smug", "我还没发力呢"),
        ("joy", "结束了？这么快"),
        ("smug", "下次找点厉害的来"),
    ],
    ("aggressive", "defeat"): [
        ("anger", "不服！再来！"),
        ("anger", "这把是意外"),
        ("frustrated", "运气你赢的"),
        ("anger", "给我等着"),
    ],
    ("aggressive", "skill_use"): [
        ("joy", "吃我一招！"),
        ("smug", "这你没想到吧"),
        ("joy", "好！"),
    ],

    # ── defensive ─────────────────────────────────────────────
    ("defensive", "kill"): [
        ("relieved", "好，解决了"),
        ("joy", "不错不错"),
        ("neutral", "稳的，不着急"),
        ("relieved", "这个位置终于拿回来了"),
        ("neutral", "好，{e}没了"),
        ("joy", "守住了这一波"),
    ],
    ("defensive", "crit_kill"): [
        ("joy", "暴击立功了！"),
        ("relieved", "好暴击！"),
    ],
    ("defensive", "near_miss"): [
        ("frustrated", "{hp}血溜了……"),
        ("disappointed", "就差一点"),
        ("frustrated", "唉被跑了"),
    ],
    ("defensive", "killed"): [
        ("disappointed", "啊{u}倒了"),
        ("frustrated", "这个站位是我的锅"),
        ("disappointed", "阵型要调了"),
        ("panic", "不好，{u}没了要补位"),
        ("frustrated", "他的站位太好了"),
    ],
    ("defensive", "damaged"): [
        ("frustrated", "{u}被{伤害}{dmg}"),
        ("neutral", "小伤，还能站"),
        ("frustrated", "这个位置不舒服了"),
        ("neutral", "还行不致命"),
    ],
    ("defensive", "castled"): [
        ("relieved", "多点一个据点了"),
        ("neutral", "好，城堡是我们的了"),
        ("joy", "稳住的奖励"),
    ],
    ("defensive", "victory"): [
        ("relieved", "守住了"),
        ("joy", "防御才是王道"),
        ("neutral", "滴水不漏"),
    ],
    ("defensive", "defeat"): [
        ("disappointed", "还是没守住"),
        ("frustrated", "下次换个阵型"),
    ],
    ("defensive", "skill_use"): [
        ("neutral", "好了"),
    ],

    # ── balanced ──────────────────────────────────────────────
    ("balanced", "kill"): [
        ("joy", "nice"),
        ("joy", "漂亮"),
        ("joy", "稳的"),
        ("neutral", "好，{e}没了"),
        ("joy", "可以可以"),
        ("joy", "收割"),
        ("joy", "拿捏了"),
        ("neutral", "中规中矩的一刀"),
        ("joy", "不亏不亏"),
    ],
    ("balanced", "crit_kill"): [
        ("joy", "暴击！nice！"),
        ("joy", "人品爆发"),
    ],
    ("balanced", "near_miss"): [
        ("frustrated", "啊{hp}血跑了"),
        ("frustrated", "差一丢丢"),
        ("disappointed", "可惜了"),
    ],
    ("balanced", "killed"): [
        ("disappointed", "啊{u}没了"),
        ("frustrated", "好伤"),
        ("neutral", "没事调整一下"),
        ("disappointed", "亏了亏了"),
    ],
    ("balanced", "damaged"): [
        ("neutral", "小伤"),
        ("neutral", "还行"),
        ("frustrated", "挨了一下"),
    ],
    ("balanced", "castled"): [
        ("joy", "城堡到手"),
        ("joy", "nice"),
        ("neutral", "占下来了"),
    ],
    ("balanced", "victory"): [
        ("joy", "赢了"),
        ("joy", "GG"),
        ("joy", "拿下了"),
    ],
    ("balanced", "defeat"): [
        ("disappointed", "输了"),
        ("neutral", "技不如人甘拜下风"),
    ],
    ("balanced", "skill_use"): [
        ("neutral", "ok"),
    ],

    # ── trickster ─────────────────────────────────────────────
    ("trickster", "kill"): [
        ("smug", "上当了吧？"),
        ("joy", "哈哈哈哈中计了"),
        ("smug", "我就知道{e}会站那"),
        ("smug", "感谢{e}送的人头"),
        ("joy", "没想到吧？？"),
        ("smug", "诶嘿"),
        ("smug", "这也在计算之中"),
    ],
    ("trickster", "crit_kill"): [
        ("smug", "暴击了，不用谢"),
        ("joy", "暴击就是最好的惊喜"),
    ],
    ("trickster", "near_miss"): [
        ("frustrated", "啧跑了"),
        ("smug", "下次你可没这么好运"),
    ],
    ("trickster", "killed"): [
        ("frustrated", "被蹲了"),
        ("anger", "好家伙，你也是老阴比"),
        ("frustrated", "翻车了翻车了"),
    ],
    ("trickster", "damaged"): [
        ("frustrated", "被发现了"),
        ("neutral", "没事他们猜不到我想干嘛"),
    ],
    ("trickster", "castled"): [
        ("smug", "偷到了"),
        ("smug", "声东击西"),
        ("smug", "顺手牵羊属于是"),
    ],
    ("trickster", "victory"): [
        ("smug", "全在计划之中"),
        ("smug", "你们从头到尾都在我的剧本里"),
    ],
    ("trickster", "defeat"): [
        ("frustrated", "被反套路了"),
        ("frustrated", "下次换个剧本"),
    ],
    ("trickster", "skill_use"): [
        ("smug", "好戏在后面"),
    ],

    # ── common actions (all personalities) ─────────────────────
    ("aggressive", "move"): [
        ("neutral", "冲了"),
        ("neutral", "压过去"),
        ("joy", "跟上跟上"),
        ("neutral", "{u}往前顶"),
        ("neutral", "往前压"),
    ],
    ("defensive", "move"): [
        ("neutral", "{u}调整一下"),
        ("neutral", "往后收"),
        ("neutral", "这个位置好"),
        ("neutral", "站好位"),
    ],
    ("balanced", "move"): [
        ("neutral", "{u}走这边"),
        ("neutral", "挪一下"),
        ("neutral", "好"),
    ],
    ("trickster", "move"): [
        ("smug", "{u}就蹲这"),
        ("neutral", "绕一下"),
        ("smug", "这个位置他们想不到"),
    ],
    ("aggressive", "attack_hit"): [
        ("frustrated", "没死？"),
        ("neutral", "刮一刀"),
        ("joy", "蹭一蹭血"),
        ("frustrated", "皮真厚"),
        ("neutral", "先削你{dmg}血"),
        ("smug", "疼不疼？"),
    ],
    ("defensive", "attack_hit"): [
        ("neutral", "打{dmg}"),
        ("neutral", "蹭你一下"),
        ("neutral", "不着急"),
    ],
    ("balanced", "attack_hit"): [
        ("neutral", "打{dmg}血"),
        ("neutral", "还行"),
        ("frustrated", "没杀掉"),
        ("neutral", "压制一波"),
    ],
    ("trickster", "attack_hit"): [
        ("smug", "先逗你一下"),
        ("neutral", "这是在铺垫"),
        ("smug", "马上你就知道了"),
    ],
    ("aggressive", "wait"): [
        ("neutral", "{u}等一下"),
        ("neutral", "{u}这回合不用"),
    ],
    ("defensive", "wait"): [
        ("neutral", "{u}先不动"),
    ],
    ("balanced", "wait"): [
        ("neutral", "{u}待命"),
        ("neutral", "这个不管"),
    ],
    ("trickster", "wait"): [
        ("smug", "{u}先藏着"),
    ],
    ("aggressive", "heal"): [
        ("joy", "奶一口{u}"),
        ("neutral", "{u}回血了"),
        ("joy", "治疗跟上"),
    ],
    ("defensive", "heal"): [
        ("relieved", "奶住{u}"),
        ("neutral", "好，回血了"),
    ],
    ("balanced", "heal"): [
        ("neutral", "奶一口"),
        ("neutral", "{u}+血"),
    ],
    ("trickster", "heal"): [
        ("smug", "想不到我还有奶吧"),
    ],

    # ── turn_start ─────────────────────────────────────────────
    ("aggressive", "turn_start"): [
        ("joy", "来！轮到我了！"),
        ("neutral", "该开干了"),
        ("smug", "坐稳了"),
        ("joy", "看我的"),
    ],
    ("defensive", "turn_start"): [
        ("neutral", "稳住别浪"),
        ("neutral", "我要调整一下"),
        ("neutral", "守好阵型"),
    ],
    ("balanced", "turn_start"): [
        ("neutral", "到我"),
        ("neutral", "我看看局面"),
        ("neutral", "好到我了"),
    ],
    ("trickster", "turn_start"): [
        ("smug", "准备搞事了"),
        ("smug", "让我看看谁会上当"),
        ("smug", "开始你们的表演"),
    ],
}

# Neutral fallback
_NEUTRAL_FALLBACK: dict[str, tuple[Mood, str]] = {
    "kill":       ("neutral", "击杀"),
    "killed":     ("disappointed", "阵亡"),
    "damaged":    ("frustrated", "受伤"),
    "castled":    ("neutral", "占城"),
    "victory":    ("joy", "胜利"),
    "defeat":     ("disappointed", "战败"),
    "skill_use":  ("neutral", "用了技能"),
    "turn_start": ("neutral", "到我了"),
    "crit_kill":  ("joy", "暴击击杀"),
    "near_miss":  ("frustrated", "差一点"),
    "move":       ("neutral", "走位"),
    "attack_hit": ("neutral", "打了一下"),
    "wait":       ("neutral", "待命"),
    "heal":       ("neutral", "治疗"),
}


# ── Public API ────────────────────────────────────────────

def generate_reaction(
    personality: str,
    event: Event,
    *,
    ctx: dict[str, str] | None = None,
    rng: random.Random | None = None,
) -> Reaction:
    """Pick a random template and fill `{var}` placeholders with context."""
    rng = rng or random.Random()

    options = _TEMPLATES.get((personality, event), [])
    if not options:
        options = _TEMPLATES.get(("balanced", event), [])
    if not options:
        mood, text = _NEUTRAL_FALLBACK.get(event, ("neutral", "…"))
        return Reaction(event=event, mood=mood, text=text)

    mood, template = rng.choice(options)

    # Fill placeholders
    ctx = ctx or {}
    text = template
    for key, val in ctx.items():
        text = text.replace("{" + key + "}", str(val))

    # Clean up unmatched placeholders (like "{还没有跑}" which is a
    # sneaky way to increase variety — if ctx doesn't have the key it
    # reads as natural Chinese)
    import re as _re
    text = _re.sub(r"\{[^}]*\}", "", text)
    if not text.strip():
        text = template  # never return empty

    return Reaction(event=event, mood=mood, text=text)


def events_for_action(
    legal_action_kind: str,
    *,
    killed_target: bool = False,
    captured_castle: bool = False,
    used_skill: str | None = None,
    is_crit: bool = False,
    target_hp_left: int = -1,
) -> List[Event]:
    events: list[Event] = []
    if legal_action_kind == "attack" and killed_target:
        events.append("crit_kill" if is_crit else "kill")
    elif legal_action_kind == "attack" and target_hp_left > 0 and target_hp_left <= 5:
        events.append("near_miss")
    if legal_action_kind == "move" and captured_castle:
        events.append("castled")
    if legal_action_kind == "skill" and used_skill:
        events.append("skill_use")
    return events


def events_from_hp_diff(
    hp_before: dict[int, int],
    hp_after: dict[int, int],
) -> List[Event]:
    events: list[Event] = []
    for uid, before_hp in hp_before.items():
        after_hp = hp_after.get(uid, 0)
        if before_hp > 0 and after_hp == 0:
            events.append("killed")
        elif after_hp < before_hp and after_hp > 0:
            events.append("damaged")
    return events
