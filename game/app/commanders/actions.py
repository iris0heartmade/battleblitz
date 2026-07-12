"""High-level authorization checks for commander actions."""


def can_player_fire_now(player, game, players=None) -> bool:
    """Use the battle action resolver's alive-seat/hole/wrap semantics."""
    players = list(players or [player])
    alive_seats = sorted(p.seat for p in players if p.is_alive or p.is_spectator)
    if not alive_seats:
        return False
    expected_seat = next(
        (seat for seat in alive_seats if seat >= game.current_player_index),
        alive_seats[0],
    )
    return bool(
        game.status == "playing"
        and player.is_alive
        and not player.is_ai
        and not player.is_spectator
        and player.seat == expected_seat
    )
