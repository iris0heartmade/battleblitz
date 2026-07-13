# Hero Mainline Debug Analysis

Date: 2026-07-14

## Scope

This document records the investigation and fixes for six regressions reported
on `hero-mercenary-dual-track`. A helper agent performed read-only code
location; the final diagnosis, implementation, and verification were completed
in the primary workspace.

## Findings And Fixes

### 1. Manual saves displayed "第 ? 章"

**Root cause:** `app.js` used a truthiness check for `battle_index`. The valid
first-battle index (`0`) was treated as absent and rendered as `?`.

**Fix:** The label now uses an explicit null check and renders `第 1 战 - 手动`
for index zero. The text now says "战" because this field is the zero-based
battle cursor, not a narrative chapter number.

### 2. Mainline page and save manager showed different saves

**Root cause:** the mainline page queried `/games` and called any playing game
a save; the save manager queried `/saves`, where manual/auto/suspend snapshots
actually live. These are different data models.

**Fix:** `MainlineView.renderSlots()` now uses `/saves`, as does save
management. It renders the same three manual slots plus any auto and suspend
records, with the shared load/erase actions. A live `Game` is no longer
mislabelled as a persistent save.

### 3. Server timestamps shifted by timezone

**Root cause:** SQLite returns `DateTime` values without timezone metadata,
then the browser interprets an offset-free ISO timestamp as local time.
`POST /games/{id}/suspend` also returned naive `datetime.utcnow()`.

**Fix:** save API response projection restores a missing timezone as UTC and
normalizes aware timestamps to UTC. The suspend endpoint now uses
`datetime.now(timezone.utc)`. Save API responses therefore include a UTC
offset for browser `Date` parsing.

### 4. Starting a loaded mainline returned 409

**Root cause:** an active profile correctly makes `/start` return 409, but the
prepare screen always called `/start`, even after a formal save restore. The
frontend then attempted to auto-abandon the active campaign and retry, losing
the cursor it should resume.

**Fix:** the prepare response now exposes `is_active`. A loaded/active
campaign puts the frontend in `next-battle` mode, which spawns the battle at
the persisted `battle_index`; a fresh campaign still calls `/start`. The
unsafe automatic abandon-and-retry logic was removed.

### 5. Abandon confirmation repeated

**Root cause:** `MainlineView` declared two methods named `abandon`. The UI
method overwrote the HTTP wrapper and recursively called itself after every
confirmation.

**Fix:** the HTTP wrapper is now `abandonRequest`. The UI method calls it and
uses `mainlineAbandonPending` plus disabled abandon buttons to prevent a
second confirmation/request while the first is in flight.

### 6. Units could not enter or seize an enemy HQ

**Root cause:** both client path preview and server movement rejected an
owned enemy `castle`. Consequently the existing castle claim code could not
be reached.

**Fix:** enemy castles are passable in client pathfinding and server BFS/move
validation. `castle` is added to the client claimable terrain set. Moving onto
an HQ does not immediately flip ownership: the existing two-turn claim
workflow remains authoritative, and its completion triggers seize victory.

## Tests

- Passed: `node --check game/app/web/app.js`.
- Passed: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest game/tests/test_utils.py -q`
  (`26 passed`), including enemy-HQ passability.
- Passed: `python -m py_compile` for the changed Python modules.
- Added regression tests for the active-campaign prepare flag and UTC save
  serialization in `test_mainline_api.py` and `test_save_api.py`.

The async API test files could not run in this environment: normal pytest
startup fails because globally installed `launch_testing` implements an
incompatible pytest hook; disabling plugin autoload removes the async fixture
runner. Re-run them in the project test environment after correcting that
dependency, then manually verify: save in battle 1, load from both entry
points, start the restored battle, abandon once, and claim an enemy HQ for two
turns.
