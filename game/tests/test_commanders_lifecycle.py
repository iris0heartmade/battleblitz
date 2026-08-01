from app.commanders.effects import (
    bake_passive_into_units, fire_co_power, on_player_turn_start,
)


class FakeUnit:
    def __init__(self, atk=10):
        self.atk, self.max_hp, self.hp = atk, 20, 20
        self.def_, self.matk, self.mdef = 5, 2, 1
        self.mov, self.mp, self.attack_range = 4, 4, 1


class FakePlayer:
    """新机制:stars 累计,每回合不重置。threshold=18 yun,power_cost=6。"""

    def __init__(self, commander_id, units=None, last=-1, stars=0,
                 threshold=18, power_cost=6, active=False):
        self.commander_id, self.units = commander_id, units or []
        self.co_state = {
            "commander_id": commander_id,
            "stars_earned_total": stars,
            "threshold": threshold,
            "power_cost": power_cost,
            "meter": 0,
            "is_power_active": active,
            "last_start_turn": last,
        }


def test_first_recorded_turn_does_not_expire():
    player = FakePlayer("yun", [FakeUnit()], stars=18)
    bake_passive_into_units(player)
    fire_co_power(player)
    on_player_turn_start(player, 1)
    assert player.co_state["is_power_active"] is True
    assert player.co_state["last_start_turn"] == 1


def test_next_self_start_expires_power_but_keeps_stars():
    """新机制:下个自己回合开始时,power 失效,但 stars 累计不重置。"""
    player = FakePlayer("yun", [FakeUnit()], last=1, stars=18)
    bake_passive_into_units(player)
    fire_co_power(player)
    # 放 power 后 stars = 12
    assert player.co_state["stars_earned_total"] == 12
    on_player_turn_start(player, 5)
    assert player.co_state["is_power_active"] is False
    # 不清零 stars(累计型)
    assert player.co_state["stars_earned_total"] == 12
    assert player.co_state["last_start_turn"] == 5


def test_next_start_keeps_stars_without_power():
    """新机制:每回合不重置 stars(无论 power 是否生效)。"""
    player = FakePlayer("yun", last=1, stars=15)
    on_player_turn_start(player, 5)
    assert player.co_state["stars_earned_total"] == 15  # 仍是 15,不清零


def test_players_expire_independently():
    red = FakePlayer("yun", [FakeUnit()], last=1, stars=18, threshold=18)
    blue = FakePlayer("anna", [FakeUnit()], last=2, stars=18, threshold=14)
    for player in (red, blue):
        bake_passive_into_units(player)
        fire_co_power(player)
    on_player_turn_start(red, 5)
    assert red.co_state["is_power_active"] is False
    assert blue.co_state["is_power_active"] is True
    on_player_turn_start(blue, 6)
    assert blue.co_state["is_power_active"] is False

    no_commander = FakePlayer(None, last=3)
    on_player_turn_start(no_commander, 7)
    assert no_commander.co_state["last_start_turn"] == 7


def test_lifecycle_initializes_missing_state_without_mutating_old_dict():
    player = FakePlayer("yun")
    player.co_state = None
    on_player_turn_start(player, 1)
    assert player.co_state["last_start_turn"] == 1
    # 新机制:下次 turn start 不会清零 stars(本测试 stars=0 仍是 0)
    old = player.co_state
    on_player_turn_start(player, 5)
    assert player.co_state is not old
    assert player.co_state["stars_earned_total"] == 0
