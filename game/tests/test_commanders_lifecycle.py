from app.commanders.effects import (
    bake_passive_into_units, fire_co_power, on_player_turn_start,
)


class FakeUnit:
    def __init__(self, atk=10):
        self.atk, self.max_hp, self.hp = atk, 20, 20
        self.def_, self.matk, self.mdef = 5, 2, 1
        self.mov, self.mp, self.attack_range = 4, 4, 1


class FakePlayer:
    def __init__(self, commander_id, units=None, last=-1, meter=0, threshold=22):
        self.commander_id, self.units = commander_id, units or []
        self.co_state = {"commander_id": commander_id, "meter": meter,
                         "threshold": threshold, "is_power_active": False,
                         "last_start_turn": last}


def test_first_recorded_turn_does_not_expire():
    player = FakePlayer("yun", [FakeUnit()], meter=22)
    bake_passive_into_units(player)
    fire_co_power(player)
    on_player_turn_start(player, 1)
    assert player.co_state["is_power_active"] is True
    assert player.co_state["last_start_turn"] == 1


def test_next_self_start_expires_and_resets_meter():
    player = FakePlayer("yun", [FakeUnit()], last=1, meter=22)
    bake_passive_into_units(player)
    fire_co_power(player)
    on_player_turn_start(player, 5)
    assert player.co_state["is_power_active"] is False
    assert player.co_state["meter"] == 0
    assert player.co_state["last_start_turn"] == 5


def test_next_start_resets_meter_without_power():
    player = FakePlayer("yun", last=1, meter=15)
    on_player_turn_start(player, 5)
    assert player.co_state["meter"] == 0


def test_players_expire_independently():
    red = FakePlayer("yun", [FakeUnit()], last=1, meter=22)
    blue = FakePlayer("anna", [FakeUnit()], last=2, meter=18, threshold=18)
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

    old = player.co_state
    on_player_turn_start(player, 5)
    assert player.co_state is not old
    assert player.co_state["meter"] == 0
