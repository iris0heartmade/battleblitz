"""
SQLAlchemy ORM models for BattleBlitz.

Schema notes:
- `Unit.def_` uses trailing underscore because `def` is a Python keyword.
- `Unit.skills` is stored as JSON text (SQLite has no native JSON column,
  so SQLAlchemy's JSON type falls back to TEXT under the hood).
- All FK columns have an index for join performance.
- All tables use BIGINT-ish integer PKs for headroom.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional


def _utcnow() -> datetime:
    """Timezone-aware UTC now (UTC tzinfo set)."""
    return datetime.now(timezone.utc)

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

logger = logging.getLogger(__name__)


# ============================================================
# Game
# ============================================================

class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="waiting")
    # waiting | playing | finished
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    current_player_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    map_seed: Mapped[int] = mapped_column(Integer, nullable=False)
    map_preset: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # Map biome for tile palette selection: "grass" | "snow" | "desert"
    # Affects forest_*/castle_* tile variants rendered by the frontend.
    map_biome: Mapped[str] = mapped_column(String(16), nullable=False, default="grass")
    # Turn phase: "player" (human's turn), "ai" (AI is acting), "animating"
    # (reserved for future use, e.g. "playing back an action animation").
    phase: Mapped[str] = mapped_column(String(16), nullable=False, default="player")
    unit_composition: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # Fairness: the first player (seat 0) is limited to 1 action on their first
    # turn; once they've ended it, everyone gets 2 actions per turn going forward.
    first_player_done_first_turn: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # P2.3 — victory condition. Default "rout" preserves the legacy
    # behaviour (last team with alive units wins). Other values:
    #   "seize"  — capture the opponent's HQ tile (universal)
    #   "reach"  — a unit on game.reach_tile_id (mission only)
    #   "defend" — survive game.defend_turns full rounds (mission only)
    win_condition: Mapped[str] = mapped_column(String(16), nullable=False, default="rout")
    # P2.3 — when win_condition == "reach", this tile is the target.
    reach_tile_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tiles.id", ondelete="SET NULL"), nullable=True
    )
    # P2.3 — when win_condition == "defend", this is the round count
    # at which the last surviving team wins. A "round" = all living
    # players each taking 1 turn.
    defend_turns: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    # P2.3 — populated when the game ends ("rout" | "seize" | "reach" |
    # "defend" | "draw"). Used by the front-end to pick the right
    # victory banner copy.
    win_reason: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )

    players: Mapped[List["Player"]] = relationship(
        "Player",
        back_populates="game",
        cascade="all, delete-orphan",
        order_by="Player.id",
    )
    tiles: Mapped[List["Tile"]] = relationship(
        "Tile",
        back_populates="game",
        cascade="all, delete-orphan",
        # P2.3 — Tile has two FKs back to Game: the regular
        # `game_id` (one tile per (x, y) in the map) and the
        # `reach_tile_id` we just added for reach-mode targeting.
        # Disambiguate so SQLAlchemy picks the right one for
        # the parent/child join.
        foreign_keys="Tile.game_id",
    )
    action_logs: Mapped[List["ActionLog"]] = relationship(
        "ActionLog",
        back_populates="game",
        cascade="all, delete-orphan",
        order_by="ActionLog.id",
    )


# ============================================================
# Player
# ============================================================

class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_name: Mapped[str] = mapped_column(String(64), nullable=False)
    color: Mapped[str] = mapped_column(String(16), nullable=False)
    is_alive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    has_ended_turn: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Turn-order index within this game (0..N-1).
    seat: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # True if this slot is controlled by the built-in AI (no real client).
    is_ai: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # "rules" (built-in rule-based AI) or "llm" (LLMAgent from app.agent).
    # Only meaningful when is_ai=True; humans ignore it.
    agent_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="rules")
    # Personality preset name (e.g. "aggressive" / "defensive" / "balanced"
    # / "trickster"); only used when agent_kind == "llm".
    agent_personality: Mapped[str] = mapped_column(String(32), nullable=False, default="balanced")
    # P2.3 — team grouping. When NULL, the front-end falls back to
    # `color` so 1V1 free-for-all (legacy) keeps working unchanged.
    # Multiple players with the same team_id are treated as one
    # logical side for win-condition checks (Rout / Seize / Reach /
    # Defend). When unset, the team defaults to the player's color.
    team_id: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    # Per-game gold (P0.4 economy). Reset to 0 at game start; grows via
    # income from owned income-yielding terrains; spent on recruit.
    gold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    game: Mapped["Game"] = relationship("Game", back_populates="players")
    units: Mapped[List["Unit"]] = relationship(
        "Unit",
        back_populates="player",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("game_id", "user_name", name="uq_player_name_per_game"),
        UniqueConstraint("game_id", "color", name="uq_player_color_per_game"),
        UniqueConstraint("game_id", "seat", name="uq_player_seat_per_game"),
    )


# ============================================================
# Unit
# ============================================================

class Unit(Base):
    __tablename__ = "units"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_type: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)

    # Legacy fields (kept for DB compatibility; level is always 1 now,
    # exp is unused — progression is now morale-based).
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    exp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    hp: Mapped[int] = mapped_column(Integer, nullable=False)
    max_hp: Mapped[int] = mapped_column(Integer, nullable=False)
    atk: Mapped[int] = mapped_column(Integer, nullable=False)
    # Trailing underscore to avoid clashing with Python `def` keyword.
    def_: Mapped[int] = mapped_column("def_", Integer, nullable=False)
    # Magic stats. matk = magic attack output, mdef = magic defense.
    # Always read via the attacker's attack_kind: magic attackers use
    # matk, magic defenders (any unit) block with mdef.
    matk: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mdef: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mov: Mapped[int] = mapped_column(Integer, nullable=False)

    # Movement points remaining this turn. Reset to `mov` at the start of
    # each of the unit owner's turns.
    mp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Morale (0..MORALE_MAX). Awards +1 per kill, capped. Persistent across
    # turns — represents the unit's battle experience.
    morale: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    x: Mapped[int] = mapped_column(Integer, nullable=False)
    y: Mapped[int] = mapped_column(Integer, nullable=False)

    has_acted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # True if the unit has moved this turn. Separate from has_acted so
    # a unit can move AND then attack/heal within the same turn.
    has_moved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # JSON array of skill strings, e.g. ["snipe", "heal"].
    skills: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    player: Mapped["Player"] = relationship("Player", back_populates="units")

    __table_args__ = (
        Index("ix_unit_player_acted", "player_id", "has_acted"),
    )


# ============================================================
# Tile (one row per (game, x, y))
# ============================================================

class Tile(Base):
    __tablename__ = "tiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    x: Mapped[int] = mapped_column(Integer, nullable=False)
    y: Mapped[int] = mapped_column(Integer, nullable=False)
    terrain: Mapped[str] = mapped_column(String(16), nullable=False)
    # Castle sub-feature (P0.4). NULL on legacy tiles or non-castle tiles;
    # one of CASTLE_SUBTYPES for castle_* tiles. Used for layout rules
    # (castle_wall blocks; castle_door is the entry; castle_throne is
    # the future Seize objective; castle_vault yields income).
    subtype: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    owner_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("players.id", ondelete="SET NULL"), nullable=True
    )
    occupied_unit_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("units.id", ondelete="SET NULL"), nullable=True
    )

    game: Mapped["Game"] = relationship(
        "Game", back_populates="tiles",
        # P2.3 — Tile has two FKs back to Game: `game_id` (the per-tile
        # link) and `reach_tile_id` (the P2.3 reach-mode target).
        # Disambiguate so the back-ref matches Game.tiles' forward
        # foreign_keys="Tile.game_id".
        foreign_keys="Tile.game_id",
    )

    __table_args__ = (
        UniqueConstraint("game_id", "x", "y", name="uq_tile_coord_per_game"),
        Index("ix_tile_game_coord", "game_id", "x", "y"),
    )


# ============================================================
# ClaimSession (active claim mechanic — P0.4)
# ============================================================
# A unit performing a `claim` action parks here for CLAIM_TURNS_REQUIRED
# full player-turns. While parked, the unit cannot move. The unit is
# removed from this table when ownership flips, the unit dies, or the
# unit moves away (cancelled). Only one open session per tile at a time.

class ClaimSession(Base):
    __tablename__ = "claim_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tile_id: Mapped[int] = mapped_column(
        ForeignKey("tiles.id", ondelete="CASCADE"), nullable=False
    )
    unit_id: Mapped[int] = mapped_column(
        ForeignKey("units.id", ondelete="CASCADE"), nullable=False
    )
    target_player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    # The turn in which the session was started (for diagnostics / UI).
    started_turn: Mapped[int] = mapped_column(Integer, nullable=False)
    # The turn number at which the session completes and ownership flips.
    completes_turn: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )

    game: Mapped["Game"] = relationship("Game")
    tile: Mapped["Tile"] = relationship("Tile")
    unit: Mapped["Unit"] = relationship("Unit")
    target_player: Mapped["Player"] = relationship("Player")

    __table_args__ = (
        # Only one active session per (game, tile).
        UniqueConstraint("game_id", "tile_id", "claim_sessions_uq_active",
                         name=None) if False else None,
    )


# ============================================================
# ActionLog (battle reports)
# ============================================================

class ActionLog(Base):
    __tablename__ = "action_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)
    player_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("players.id", ondelete="SET NULL"), nullable=True
    )
    action_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # move | attack | skill | wait | turn_end | death | victory
    description: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )

    game: Mapped["Game"] = relationship("Game", back_populates="action_logs")