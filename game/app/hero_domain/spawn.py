from __future__ import annotations

from app.hero_domain.state import HeroCampaignState


def build_campaign_spawn_payload(state: HeroCampaignState) -> dict:
    return {
        "hero_id": state.hero_id,
        "class_id": state.class_id,
        "level": state.level,
        "exp": state.exp,
        "base_stats": dict(state.base_stats),
        "learned_skills": list(state.learned_skills),
        "promoted": state.promoted,
        "equipment": dict(state.equipment),
    }
