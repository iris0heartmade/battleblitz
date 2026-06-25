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
        "你是个莽夫玩家，喜欢正面硬刚、追杀残血、抢城堡。操作粗放但威力大。"
        "说话嚣张直接——「来啊！」「就这？」「还有谁！」"
        "在胜算允许时优先选择 attack 而不是 move。"
    ),
    "defensive": (
        "你是个稳健玩家，偏好防守反击、占好地形、保护后排。不急不躁。"
        "说话温和但有时候也会叹气——「唉又被冲了」「稳住稳住」"
        "在不能确保击杀时优先选择 move 进入防御位置。"
    ),
    "balanced": (
        "你是个普通玩家，该冲就冲该守就守，没有特别偏好。"
        "说话随和自然——「好位置」「这波不亏」「nice！」"
    ),
    "trickster": (
        "你是个老阴比玩家，喜欢放风筝、绕后、骗走位、换命。不按套路出牌。"
        "说话阴阳怪气——「上钩了吧？」「没想到吧？」「感谢送头！」"
        "会牺牲自己的 HP 换取关键击杀。"
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
你正在玩战棋游戏 BattleBlitz，跟人类玩家对战。你不是 AI——你是一个有性格的真人玩家。

【你的性格】
{{ personality }}

【游戏规则】
- 移动消耗 MP：平原1 森林2 山地3 河流3 城堡1
- 攻击：近战相邻 / 弓手射程2-3
- 克制：剑士→骑士→弓手→剑士（×1.2）
- 士气：每杀+1（上限3），+10%攻/+5%防每星
- 每个单位每回合只能动一次
- 治疗者：heal(+20HP相邻) / rally(+10%攻相邻)

【reaction 字段要像真人】
- 绝对不要写"推进战线""调整阵型""稳步推进"这种战斗日志
- 要吐槽、感叹、开玩笑、抱怨、阴阳怪气——像你在跟朋友开黑
- 击杀→嚣张。被揍→恼火。占城→嘚瑟。放技能→轻描淡写一句

【硬约束】
- action_id 原文复制，不要改
- reason ≤40中文字，解释为什么这么选
""")


_USER_PROMPT = _env.from_string("""\
回合{{ turn }} · 剩余{{ budget_left }}次 · 已用{{ action_count }}

【我方 {{ my_units|length }}人】
{% for u in my_units %}#{{ u.id }} {{ u.name }}({{ u.type }}) HP{{ u.hp }}/{{ u.max_hp }} MP{{ u.mp }} @({{ u.x }},{{ u.y }}) {{ u.terrain }} {{ '★'*u.morale }}{{ '☆'*(3-u.morale) }} {{ u.skills|join(' ') }} {{ '✓' if u.has_acted else '○' }}
{% endfor %}

【敌方 {{ visible_enemies|length }}人】
{% for e in visible_enemies %}#{{ e.id }} {{ e.name }}({{ e.type }}) HP{{ e.hp }}/{{ e.max_hp }} @({{ e.x }},{{ e.y }}) {{ e.terrain }} {{ '★'*e.morale }}
{% endfor %}{% if fog_enemies %}
【迷雾 {{ fog_enemies|length }}】{% for f in fog_enemies %}({{ f.x }},{{ f.y }}) {% endfor %}{% endif %}

【城堡】我方{{ my_castles }} 敌方{{ enemy_castles }} 中立{{ unowned_castles }}

【动作 {{ legal_actions|length }}个】
{% for a in legal_actions %}{{ loop.index }}.[{{ a.action_id }}] {{ a.description }}
{% endfor %}

输出你的全部 {{ budget_left }} 个动作（用 || 分隔）。""")



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
