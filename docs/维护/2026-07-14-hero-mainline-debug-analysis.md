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

### 7. Clean local database showed save/profile 404 responses

**Root cause:** clearing `battleblitz.db` correctly removed the profile for
the nickname still stored in browser local storage. `/saves`, `/profile`, and
commander lookups then returned 404 before the first mainline start created a
new profile. The two save views rendered the save endpoint's 404 as a failure
instead of an empty new-player state.

**Fix:** both save views now treat `GET /saves` 404 as three empty manual
slots and no auto/suspend save. Starting a mainline continues to create the
profile automatically; other HTTP failures remain visible to the user.

### 8. Moving a cavalry unit onto an enemy castle returned 500

**Root cause:** the old immediate-capture block in `move_unit` still invoked
`claim_castle_if_present`, but that helper was no longer imported after the
HQ movement change. This produced the reported `NameError` after pathfinding
had already succeeded.

**Fix:** removed the obsolete immediate-capture call. A unit may enter the
castle, while ownership is changed only by the explicit two-turn claim
mechanic. This both removes the 500 and preserves seize-mode rules.

### 9. Spectators incorrectly hid the fourth player slot in a 4-player room

**Root cause:** the lobby UI compared total entries, including spectators,
against room capacity even though the backend already excludes spectators
from its capacity count.

**Fix:** lobby add-AI and start eligibility now use the non-spectator count.
Added `test_spectator_does_not_consume_an_ai_player_slot` to cover one host,
one spectator, and three valid AI additions in a four-player room.

### 10. Spectator still received a turn after a game started

**Root cause:** capacity logic excluded spectators, but turn progression,
timeout handling, game-state current-player selection, and CO-power selection
still included their seat. The spectator could therefore end a turn despite
having no units.

**Fix:** all turn-seat calculations now use alive non-spectator players.
`/end-turn` explicitly rejects spectators, so a spectator is independent of
both player capacity and the round cycle.

### 11. AI still captured an HQ immediately

**Root cause:** the human move route was changed to preserve the two-turn
claim rule, but the AI movement helper retained its old direct ownership
transfer.

**Fix:** AI movement now only enters the castle, matching human movement.
Ownership changes only through the claim workflow.

### 12. Bridge tile asset repeatedly returned 404

**Root cause:** procedural maps can emit `bridge` terrain but no
`bridge_v0.png` exists in the web assets directory.

**Fix:** the renderer uses the existing road sprite as a temporary bridge
fallback, preventing repeated failed requests until dedicated artwork is
added.

### 13. Test chapters 1-3 did not form a visible continuous campaign

**Root cause:** `chapter_test_01`, `chapter_test_02`, and
`chapter_test_03` were separate mainline files with no successor metadata.
The normal completion flow correctly cleared the completed chapter, but then
returned to the list without offering the intended next test chapter.

**Fix:** mainline content now supports optional `next_mainline_id`. The test
chain is `chapter_test_01 → chapter_test_02 → chapter_test_03`. On chapter
completion, the frontend plays that chapter's configured victory dialogue,
then explicitly asks whether to enter the linked next chapter. Confirming
opens its prepare screen; declining returns to the chapter list. Hero state,
inventory, and rewards persist through the shared player profile.

### 14. Attack-target selector could obscure map cells

**Root cause:** the compact "选择攻击目标" action bubble was fixed near the
selected unit, with no way for a desktop player to move it.

**Fix:** its title bar is now a mouse drag handle. The panel stays inside the
viewport and removes its old tile-pointer arrow once detached. Other action
buttons retain their normal click behaviour; touch input remains unchanged.

### 15. Mainline clear experience raised `MissingGreenlet`

**Root cause:** `MainlineEngine.apply_victory()` accessed the lazy
`profile.units` relationship from async request code after clearing the
campaign. SQLAlchemy attempted synchronous lazy I/O and raised
`MissingGreenlet`; gold, unlock, and clear state had already been persisted,
but the optional unit experience loop was skipped.

**Fix:** the reward path explicitly selects `UnitInstance.id` by `profile_id`
and awards experience by ID. A regression test makes `profile.units` fail on
access and verifies both queried unit IDs still receive `mainline_clear` XP.

### 16. Successor chapter could remain on the dialogue page after battle start

**Root cause:** the next chapter's battle was created before its pre-battle
dialogue played. If dialogue loading failed or the player closed it, the
frontend returned early and left the user on the mainline page instead of
entering the already-created game.

**Fix:** dialogue failure/closure now shows a short "剧情已跳过" notice and
continues into the battle map. The chapter 1 completion → chapter 2 prepare
→ chapter 2 start API chain was also verified against an isolated SQLite
database: start returned 201 and the new game returned 225 tiles in
`playing` state.

## Tests

- Passed: `node --check game/app/web/app.js`.
- Passed: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest game/tests/test_utils.py -q`
  (`26 passed`), including enemy-HQ passability.
- Passed: `python -m py_compile` for the changed Python modules.
- Added regression tests for the active-campaign prepare flag and UTC save
  serialization in `test_mainline_api.py` and `test_save_api.py`.
- Passed: `node --check game/app/web/app.js`, `python -m py_compile
  app/routes/actions.py`, and `git diff --check` after the follow-up fixes.
- The local mainline lifecycle was exercised against a newly created SQLite
  database: profile creation, prepare, start, state load (225 tiles), and
  rejoin all returned successful responses.
- Manual live verification also confirmed `POST /mainlines/.../start` (201),
  cavalry movement to an enemy HQ (200), and claim initiation (200).
- Passed: `test_test_chapters_define_an_ordered_campaign_chain` verifies the
  `chapter_test_01 → chapter_test_02 → chapter_test_03` linkage.

The async API test files could not run in this environment: normal pytest
startup fails because globally installed `launch_testing` implements an
incompatible pytest hook; disabling plugin autoload removes the async fixture
runner. Re-run them in the project test environment after correcting that
dependency, then manually verify: save in battle 1, load from both entry
points, start the restored battle, abandon once, and claim an enemy HQ for two
turns.
