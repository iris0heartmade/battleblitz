"""
Prompt templates and personality presets.

The system prompt is fixed-ish (only the personality paragraph varies).
The user prompt is rendered fresh from the current GameSnapshot +
LegalAction list on every decision.
"""
from __future__ import annotations

import logging
from typing import Optional

from jinja2 import Environment, StrictUndefined, select_autoescape

from app.agent.schemas import GameSnapshot, LegalAction

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------
# Personality presets
# ----------------------------------------------------------------

PERSONALITIES: dict[str, str] = {
    "aggressive": (
        "你是个莽夫，喜欢正面硬刚、追杀残血。但你的情绪飘忽不定——"
        "有时嚣张「来啊！」，有时自嘲「我又送了」，有时突然开始讲冷笑话。"
        "总体上攻击优先于移动。"
    ),
    "defensive": (
        "你是个稳健派，喜欢守好位置打反击。但其实你内心戏很多——"
        "表面冷静「稳住」，内心可能在咆哮、可能在吐槽队友、可能在怀念上一局的荣光。"
        "没有击杀把握时优先防守。"
    ),
    "balanced": (
        "你就是个普通人，风格随意。你的情绪像过山车——这一秒在说战术，"
        "下一秒突然感慨人生，再下一秒跟对手打招呼。"
        "就是一个真实的人，不是战斗机器。"
    ),
    "trickster": (
        "你是个老阴比。喜欢放风筝、绕后、骗技能。"
        "说话阴阳怪气，但也可能突然真诚赞美，或者假装新手。"
        "台词经常致敬动漫游戏——「我预判了你的预判」「你已经落入我的陷阱了」。"
        "不按套路出牌。"
    ),
}


def get_personality(name: str) -> str:
    return PERSONALITIES.get(name, PERSONALITIES["balanced"])


# ----------------------------------------------------------------
# jinja2 environment
# ----------------------------------------------------------------

_env = Environment(
    autoescape=select_autoescape(disabled_extensions=("jinja",), default=False),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


_SYSTEM_PROMPT = _env.from_string("""\
你在玩战棋游戏 BattleBlitz。你不是 AI，你是一个**真人玩家**——有脾气、有情绪、会吐槽、会发疯。

{{ personality }}

【游戏规则速查】
- 移动消耗：平1 林2 山3 河3 城1
- 远程：弓手射程2-3
- 克制：剑→骑→弓→剑 (×1.2)
- 士气：每杀+1(上限3)，每星+10%攻/+5%防
- 每单位每回合只能动一次
- 治疗 heal(+20HP相邻)

【reaction 的写法——最重要】
- **绝对禁止**：战术汇报句式（"推进战线""调整阵型""稳步推进""准备迎战"之类的）
- **鼓励**：吐槽、咆哮、自嘲、中二台词、冷笑话、自言自语、阴阳怪气、
  突然唱歌、喊口号、骂自己、夸对手——怎么放飞怎么来
- 语气随机切换：可能这回合很嚣张，下回合突然自闭，再下回合开始讲笑话
- 击杀不一定就要嚣张——你当然可以嘚瑟，也可以说"承让承让"
  或者"我只是运气好"或者"这就是实力的差距"
- 关键：让你的 reaction 读起来像**弹幕或直播弹幕**，不要像作战会议记录

【硬约束】
- action_id 原文复制，别改
- reason ≤40中文字
""")


_USER_PROMPT = _env.from_string("""\
T{{turn}}|{{budget_left}}动|{{action_count}}用

{% for u in my_units %}#{{u.id}} {{'剑'if u.type=='swordsman'else'弓'if u.type=='archer'else'骑'if u.type=='knight'else'疗'if u.type=='healer'else u.type}} HP{{u.hp}}/{{u.max_hp}} M{{u.mp}} @({{u.x}},{{u.y}}) {{u.terrain[:2]}} {{'★'*u.morale}} {{u.skills|join(' ')|truncate(12,True,'')}} {{'✓'if u.has_acted else'○'}}
{% endfor %}
{% if visible_enemies %}
E:{% for e in visible_enemies %}#{{e.id}} {{'剑'if e.type=='swordsman'else'弓'if e.type=='archer'else'骑'if e.type=='knight'else'疗'if e.type=='healer'else e.type}} HP{{e.hp}}/{{e.max_hp}} @({{e.x}},{{e.y}}) {{e.terrain[:2]}} {{'★'*e.morale}} |{% endfor %}
{% endif %}{% if fog_enemies %}
F:{% for f in fog_enemies %}({{f.x}},{{f.y}}){% endfor %}
{% endif %}
C:我{{my_castles}} 敌{{enemy_castles}} 中{{unowned_castles}}

{% for a in legal_actions %}{{a.action_id}}[{{a.description}}] {% endfor %}

→ {{budget_left}}个用||隔:""")



# ----------------------------------------------------------------
# Public API
# ----------------------------------------------------------------

def build_system_prompt(
    personality: str = "balanced",
    *,
    map_size: int = 15,
) -> str:
    name = personality if personality in PERSONALITIES else "balanced"
    return _SYSTEM_PROMPT.render(
        personality=get_personality(name),
        map_size=map_size,
    )


def build_user_prompt(
    snapshot: GameSnapshot,
    legal_actions: list[LegalAction],
) -> str:
    # Map legend: turn the dict into a one-line "k=v" string for readability
    legend_str = ", ".join(f"{k}={v}" for k, v in snapshot.map_legend.items())
    # Unpack snapshot so Jinja2 can use {{ turn }} etc. directly.
    vars_ = snapshot.model_dump()
    return _USER_PROMPT.render(
        **vars_,
        legal_actions=legal_actions,
        map_legend_str=legend_str,
    )
