"""Commander metadata views backed by the hero registry."""

def _get_hero(commander_id: str):
    # Hero profiles import commander value objects while their registry is
    # initialising, so resolve the registry lazily to avoid that cycle.
    from app.classes.heroes import get

    return get(commander_id)


def get_commander_passive(commander_id: str | None):
    if commander_id is None:
        return None
    return getattr(_get_hero(commander_id), "commander_passive", None)


def get_commander_power(commander_id: str | None):
    if commander_id is None:
        return None
    return getattr(_get_hero(commander_id), "commander_power", None)


def get_power_threshold(commander_id: str | None) -> int:
    if commander_id is None:
        return 20
    return getattr(_get_hero(commander_id), "power_threshold", 20)
