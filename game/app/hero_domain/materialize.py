from __future__ import annotations

from dataclasses import dataclass

from app.hero_domain.state import HeroCampaignState


@dataclass
class HeroBattleState:
    hero_id: str
    class_id: str
    level: int
    exp: int
    current_hp: int
    current_mp: int
    x: int
    y: int
    player_id: int


def build_hero_battle_state(
    state: HeroCampaignState,
    *,
    x: int,
    y: int,
    player_id: int,
) -> HeroBattleState:
    return HeroBattleState(
        hero_id=state.hero_id,
        class_id=state.class_id,
        level=state.level,
        exp=state.exp,
        current_hp=state.base_stats["hp"],
        current_mp=state.base_stats["mp"],
        x=x,
        y=y,
        player_id=player_id,
    )
