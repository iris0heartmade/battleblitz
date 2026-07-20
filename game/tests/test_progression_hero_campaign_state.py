from __future__ import annotations

import pytest

from app.progression.models import PlayerProfile
from app.progression.service import ProgressionService


@pytest.mark.unit
async def test_player_profile_has_hero_campaign_states_json(db_session):
    profile = PlayerProfile(user_name="tester")
    db_session.add(profile)
    await db_session.flush()
    await db_session.refresh(profile)
    assert isinstance(profile.hero_campaign_states, dict)
    assert isinstance(profile.mercenary_roster_state, dict)


@pytest.mark.unit
async def test_progression_service_exposes_hero_campaign_state_accessors(db_session):
    db_session.add(PlayerProfile(user_name="svc-hero"))
    await db_session.flush()

    svc = ProgressionService(db_session)
    payload = {"class_id": "warlock", "level": 3, "exp": 20}
    stored = await svc.set_hero_campaign_state("svc-hero", "yun", payload)
    fetched = await svc.get_hero_campaign_state("svc-hero", "yun")

    assert stored == payload
    assert fetched == payload
