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
    unit_composition: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # Fairness: the first player (seat 0) is limited to 1 action on their first
    # turn; once they've ended it, everyone gets 2 actions per turn going forward.
    first_player_done_first_turn: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
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

    # JSON array of skill strings, e.g. ["snipe", "rally"].
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
    owner_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("players.id", ondelete="SET NULL"), nullable=True
    )
    occupied_unit_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("units.id", ondelete="SET NULL"), nullable=True
    )

    game: Mapped["Game"] = relationship("Game", back_populates="tiles")

    __table_args__ = (
        UniqueConstraint("game_id", "x", "y", name="uq_tile_coord_per_game"),
        Index("ix_tile_game_coord", "game_id", "x", "y"),
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