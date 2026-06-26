"""
One-off migration: add mainline progress columns to `player_profiles`.

Step 2 of the mainline (campaign) rollout. Adds:
  * `active_mainline`     VARCHAR(64)  NULL
  * `mainline_progress`    JSON         NOT NULL DEFAULT '{}'

Idempotent: re-running on an already-migrated DB is a no-op. Targets
SQLite (the project's default) — no Alembic / no async engine.

Usage
-----
    # from the project root, with the project's Python env on PATH:
    python tools/migrate_add_mainline_progress.py

    # Or against a specific DB file:
    python tools/migrate_add_mainline_progress.py --db /path/to/game.db

The script reads `DATABASE_URL` from the environment (same env var the
FastAPI app uses) and falls back to the project's default DB path when
unset.
"""
from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
from pathlib import Path

# Make `app.*` importable when run from anywhere.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_GAME_ROOT = _PROJECT_ROOT / "game"
if str(_GAME_ROOT) not in sys.path:
    sys.path.insert(0, str(_GAME_ROOT))


logger = logging.getLogger("migrate.mainline_progress")


# SQL fragments. Kept as constants so a future re-run on a
# half-migrated DB can be inspected at a glance.
SQL_ADD_ACTIVE_MAINLINE = (
    "ALTER TABLE player_profiles "
    "ADD COLUMN active_mainline VARCHAR(64) NULL"
)
SQL_ADD_MAINLINE_PROGRESS = (
    "ALTER TABLE player_profiles "
    "ADD COLUMN mainline_progress JSON NOT NULL DEFAULT '{}'"
)


def _resolve_sqlite_path(db_url: str | None) -> Path:
    """Convert a `sqlite+aiosqlite:///...` URL to a filesystem path.

    Falls back to `app.config.DEFAULT_DB_PATH` when no URL is given.
    """
    if db_url is None or db_url == "":
        from app.config import DEFAULT_DB_PATH
        return Path(DEFAULT_DB_PATH)

    prefix = "sqlite+aiosqlite:///"
    if db_url.startswith(prefix):
        return Path(db_url[len(prefix):])
    if db_url.startswith("sqlite:///"):
        return Path(db_url[len("sqlite:///"):])
    # Non-sqlite URLs (Postgres etc.) — bail out, this script only
    # supports the project's default SQLite DB.
    raise SystemExit(
        f"migrate_add_mainline_progress: non-SQLite URL {db_url!r} "
        f"is not supported by this script; write a SQL variant for "
        f"your target dialect."
    )


def _column_exists(cur: sqlite3.Cursor, table: str, column: str) -> bool:
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def migrate(db_path: Path) -> int:
    """Apply both ALTER TABLE statements. Returns count of columns added."""
    if not db_path.exists():
        logger.error("SQLite file does not exist: %s", db_path)
        return 0
    added = 0
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        if not _column_exists(cur, "player_profiles", "active_mainline"):
            logger.info("Adding column player_profiles.active_mainline")
            cur.execute(SQL_ADD_ACTIVE_MAINLINE)
            added += 1
        else:
            logger.info("Column player_profiles.active_mainline already present")
        if not _column_exists(cur, "player_profiles", "mainline_progress"):
            logger.info("Adding column player_profiles.mainline_progress")
            cur.execute(SQL_ADD_MAINLINE_PROGRESS)
            added += 1
        else:
            logger.info("Column player_profiles.mainline_progress already present")
        conn.commit()
    finally:
        conn.close()
    return added


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Explicit path to the SQLite DB file. Overrides DATABASE_URL.",
    )
    args = parser.parse_args()

    if args.db is not None:
        db_path = args.db
    else:
        db_path = _resolve_sqlite_path(os.getenv("DATABASE_URL"))

    logger.info("Migrating SQLite DB at: %s", db_path)
    added = migrate(db_path)
    if added:
        logger.info("Migration complete (%d column(s) added).", added)
    else:
        logger.info("Migration complete (DB already up-to-date).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
