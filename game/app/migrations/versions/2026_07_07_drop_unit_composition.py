"""drop game.unit_composition column

P2.6 — The `unit_composition` Game column is no longer used: the create-game
flow now derives the spawn roster from the chosen map's `initial_units`
data-driven schema. The unit_composition presets endpoint field and the
request field were also removed in this task; see commits 719bf36 +
follow-ups. This migration drops the now-dead column.

Revision ID: 2026_07_07_drop_ucomp
Revises: <head>  (project doesn't use Alembic; see _run_legacy_migrations in app/database.py for the actual DROP COLUMN)
Create Date: 2026-07-07

NOTE: The BattleBlitz project uses a hand-rolled migration runner inside
``app.database._run_legacy_migrations`` instead of Alembic. This file is
kept for parity with the broader SDD plan; the actual ALTER TABLE is
applied by the legacy runner on the next server start.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "2026_07_07_drop_ucomp"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("games", "unit_composition")


def downgrade() -> None:
    op.add_column(
        "games",
        sa.Column("unit_composition", sa.String(length=32), nullable=True),
    )
