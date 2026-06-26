# BattleBlitz — Database Migrations

The project does not use Alembic. Schema changes are applied either by
`Base.metadata.create_all` (on a fresh DB) or via the one-off migration
scripts under `tools/`. Each script is **idempotent** — running it
twice is a no-op.

---

## Step 2 — `player_profiles` mainline progress columns

**Date:** 2026-06-26
**Script:** `tools/migrate_add_mainline_progress.py`
**Reason:** enable the mainline (campaign) mode. Each player profile
now stores which campaign is active and where the cursor is in the
battle + dialogue sequence.

### Columns added

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `active_mainline` | `VARCHAR(64)` | YES | `NULL` | The id of the mainline JSON currently in play (matches `Mainline.id`). `NULL` = no campaign active. |
| `mainline_progress` | `JSON` | NO | `'{}'` | In-campaign cursor. See the JSON contract below. |

### JSON contract — `mainline_progress`

```json
{
  "battle_index": 0,
  "scene_id": "intro",
  "started_at": "2026-06-26T12:34:56.789012+00:00"
}
```

| Key | Type | Notes |
|-----|------|-------|
| `battle_index` | int | 0-based index into `Mainline.battles` (the next battle to play). When `>= len(battles)` the mainline is auto-cleared. |
| `scene_id` | str | A key in the active `Mainline.dialogues` map (e.g. `"intro"`, `"battle_01_after"`, `"victory"`). |
| `started_at` | str \| null | ISO-8601 UTC timestamp of when the campaign started. `null` when no mainline is active. |

### How to run

From the project root (with the project's Python env on `PATH`):

```bash
# Uses DATABASE_URL (same env var the FastAPI app uses)
python tools/migrate_add_mainline_progress.py

# Or point at a specific file:
python tools/migrate_add_mainline_progress.py --db /path/to/game.db
```

### Fresh-DB behaviour

If you are starting from an empty DB you do **not** need to run the
script — `Base.metadata.create_all` (called by `app.database.init_db`
on FastAPI startup) now creates the columns alongside the rest of the
table.

### Rollback (manual)

```sql
ALTER TABLE player_profiles DROP COLUMN mainline_progress;
ALTER TABLE player_profiles DROP COLUMN active_mainline;
```

The application will still run, but `/profile/...` endpoints will
return 500s because the ORM expects the columns to exist.
