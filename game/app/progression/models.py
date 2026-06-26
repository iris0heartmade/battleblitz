"""
ORM models for the progression (character cultivation) system.

Tables:
  - player_profiles   : per-account cross-match persistent data
  - unit_instances    : per-hero persistent data (one profile → many heroes)
  - equipment_templates: static equipment definitions (read-mostly)
  - talent_definitions: static talent tree data (read-mostly)
  - match_records     : append-only log of past matches

Design notes:
  - `level` is 1..TIER_LEVEL_CAP[tier]; `tier` is 1..3.
  - All JSON columns store as TEXT under SQLite (SQLAlchemy `JSON` type).
  - All FKs have explicit indexes for join performance.
  - Use `_utcnow()` from app.models for tz-aware timestamps.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models import _utcnow  # reuse the existing tz-aware helper


# ============================================================
# PlayerProfile
# ============================================================

class PlayerProfile(Base):
    """A player's persistent account data, cross-match.

    Created once when a player first joins. Owns many UnitInstance rows.
    """
    __tablename__ = "player_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    gold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unlock_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unlocked_classes: Mapped[list] = mapped_column(
        JSON, nullable=False, default=lambda: ["swordsman", "archer", "knight", "healer"]
    )
    unlocked_cosmetics: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict
    )
    current_season: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    rating: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    # ── Mainline (campaign) progress — Step 2 ─────────────────
    # `active_mainline` is the id of the campaign the player is currently
    # playing (matches `Mainline.id` in `game/mainlines/*.json`). NULL
    # means no campaign is active.
    # `mainline_progress` is the in-campaign cursor. Shape:
    #   {"battle_index": int, "scene_id": str, "started_at": str|None}
    # - `battle_index`  : 0-based index into Mainline.battles (next battle
    #                     to play). When == len(battles) the mainline is
    #                     cleared.
    # - `scene_id`      : current dialogue key in Mainline.dialogues
    #                     (e.g. "intro", "battle_01_after", "victory").
    #                     The frontend looks this up to render the next
    #                     script.
    # - `started_at`    : ISO-8601 UTC timestamp of the campaign start
    #                     (or NULL if no campaign is active).
    active_mainline: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, default=None
    )
    mainline_progress: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )

    units: Mapped[list["UnitInstance"]] = relationship(
        "UnitInstance",
        back_populates="profile",
        cascade="all, delete-orphan",
        order_by="UnitInstance.id",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<PlayerProfile id={self.id} user={self.user_name!r} "
            f"rating={self.rating} active_mainline={self.active_mainline!r}>"
        )


# ============================================================
# UnitInstance
# ============================================================

class UnitInstance(Base):
    """A single owned hero (persistent across matches).

    Connection to match-time Unit (app.models.Unit):
        At match start, the system materialises a Unit row from a UnitInstance
        (copying base stats + applying talents/equipment). At match end, the
        system writes back career_stats, levels, and any unlocks.

    During this initial release, the materialisation is a TODO; the model
    here is fully functional on its own (you can create, level, promote
    via the API without ever entering a match).
    """
    __tablename__ = "unit_instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("player_profiles.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    base_type: Mapped[str] = mapped_column(String(16), nullable=False)
    nickname: Mapped[str] = mapped_column(String(32), nullable=False)
    tier: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    exp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    personality: Mapped[str] = mapped_column(
        String(16), nullable=False, default="tactical"
    )
    talent_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    talents: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # {"weapon": int|None, "armor": int|None, "accessory": int|None}
    equipment: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # {"matches":0,"kills":0,"deaths":0,"mvps":0,"wins":0}
    career_stats: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )

    profile: Mapped["PlayerProfile"] = relationship("PlayerProfile", back_populates="units")

    __table_args__ = (
        # A profile can't have two units with the same nickname
        UniqueConstraint("profile_id", "nickname", name="uq_unit_nickname_per_profile"),
        Index("ix_unit_profile_level", "profile_id", "level"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<UnitInstance id={self.id} type={self.base_type} "
            f"nick={self.nickname!r} tier={self.tier} lv={self.level}>"
        )


# ============================================================
# EquipmentTemplate
# ============================================================

class EquipmentTemplate(Base):
    """Static equipment definition (admin / config data).

    In a full game these would be seed-loaded; for now they're created on
    demand by tests / the dev seeder.
    """
    __tablename__ = "equipment_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slot: Mapped[str] = mapped_column(String(16), nullable=False)  # weapon/armor/accessory
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    rarity: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    # e.g. {"atk": 5, "def": 2, "max_hp": 10}
    stat_bonuses: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    set_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # "shop" / "gacha" / "match_reward" / "starter"
    drop_source: Mapped[str] = mapped_column(String(32), nullable=False, default="shop")

    __table_args__ = (
        Index("ix_equipment_slot_rarity", "slot", "rarity"),
    )


# ============================================================
# TalentDefinition
# ============================================================

class TalentDefinition(Base):
    """Static talent tree node definition (admin / config data)."""
    __tablename__ = "talent_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    class_id: Mapped[str] = mapped_column(String(16), nullable=False)
    node_id: Mapped[str] = mapped_column(String(32), nullable=False)
    tier_required: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    level_required: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # {"x": 1, "y": 2} for tree rendering (UI concern)
    position: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    max_rank: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # e.g. {"stat": "atk_pct", "value": 10}
    effect: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    prereq_nodes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    cost: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("class_id", "node_id", name="uq_talent_class_node"),
    )


# ============================================================
# MatchRecord
# ============================================================

class MatchRecord(Base):
    """Append-only log of completed matches for replay / season stats.

    `unit_snapshots` is the JSON of all UnitInstance states at match end
    (so we can render "this hero was the MVP" later without replaying).
    """
    __tablename__ = "match_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    season: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    winner_profile_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("player_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    unit_snapshots: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    events_url: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)


__all__ = [
    "PlayerProfile",
    "UnitInstance",
    "EquipmentTemplate",
    "TalentDefinition",
    "MatchRecord",
]
