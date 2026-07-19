# Godot Client Next Work Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the Godot client from near-parity to reliable primary-client status by fixing the current entry-flow blockers, removing the obsolete solo free-play entry, and then closing the highest-impact Web UI gaps.

**Architecture:** Keep the Python backend authoritative for game rules and use Godot only for rendering, input, local previews, and UX. Add server-backed read APIs where prediction requires game logic, then wire Godot UI to existing `NetworkClient`/`GameState` patterns.

**Tech Stack:** Godot 4.7 GDScript, FastAPI/Pydantic backend, pytest, Godot headless checks via `D:\Python\godot\Godot_v4.7-stable_win64_console.exe`.

## Global Constraints

- Do not duplicate authoritative damage formulas in Godot.
- Player actions continue to use REST; WebSocket remains snapshot/delta/heartbeat until `ws_gateway.py` adds action dispatch.
- Preserve existing `UnitOut.def_` JSON field name.
- Keep Godot edits scoped to `godot-client/` unless a task explicitly requires a backend read-only endpoint.
- Verify Godot syntax with `--headless --path godot-client --import --quit` before claiming completion.

---

## File Structure

- `game/app/routes/actions.py`: add a read-only forecast endpoint that reuses server combat logic.
- `game/tests/test_godot_forecast_api.py`: backend tests for the forecast endpoint.
- `godot-client/tools/e2e_one_game.gd`: existing live backend game runner for automated play.
- `godot-client/tools/*screenshot*.gd`: existing screenshot scenes for menu/lobby/game visual verification.
- `godot-client/scripts/autoload/network_client.gd`: add `forecast_attack`.
- `godot-client/scripts/main.gd`: fix entry-flow blockers, remove solo free-play wiring, show forecast data in `AttackConfirmPanel`; add help/reference/commentary/editor handlers.
- `godot-client/scenes/main.tscn`: remove obsolete solo free-play entry and add/expose UI nodes when a task needs new controls.
- `godot-client/tools/smoke_test.gd`: keep scene-path smoke checks aligned with current scene tree.
- `docs/WebUI-vs-GodotClient-差异与计划.md`: update remaining-gap status after each completed task.
- `docs/参考/Godot客户端后端接口.md`: update endpoint docs when backend contract changes.

---

### Task 1: Fix Mainline and Lobby Create-to-Game Entry Blockers

**Files:**
- Modify: `godot-client/scripts/main.gd`
- Modify: `godot-client/tools/e2e_one_game.gd` if the existing runner needs a mainline/lobby mode flag
- Modify: `godot-client/tools/lobby_subview_screenshot.gd` only if screenshot automation needs path updates; preserve any existing uncommitted changes carefully
- Test: existing Godot headless import and live backend automation

**Interfaces:**
- Consumes: `NetworkClient.create_game`, `join_game`, `start_game`, `connect_to_game`, `start_mainline`, `fetch_mainline_dialogue`, `advance_mainline`, `next_battle_mainline`.
- Produces: reliable transitions from mainline start and lobby-created room into `GameView` with a populated `GameState`.

- [ ] **Step 1: Reproduce both blockers**

Start backend:

```powershell
cd game
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another shell run Godot automation:

```powershell
cd ..
& 'D:\Python\godot\Godot_v4.7-stable_win64_console.exe' --headless --path godot-client res://tools/e2e_one_game.tscn
```

Then run or extend a screenshot scene to click/drive:

- main menu -> mainline -> first chapter -> start;
- main menu -> lobby -> create room -> start.

Expected before fix: one or both flows fails to enter `GameView`, does not receive `state.snapshot`, or remains on connecting/lobby/mainline UI.

- [ ] **Step 2: Trace exact failing transition**

Inspect `godot-client/scripts/main.gd` handlers:

- `_on_mainline_start_response`
- `_on_mainline_dialogue_response`
- `_on_lobby_create_response`
- `_on_lobby_join_response`
- `_on_lobby_start_response`
- `_on_start_game_response`

Add temporary `print("[flow] ...")` statements only if the failing branch is not obvious; remove them before final verification.

- [ ] **Step 3: Fix mainline start flow**

Ensure successful mainline start stores `_game_id`, `_player_id`, `_entry_flow`, updates `UserSettings` session cache if applicable, calls `_show_view("game")`, starts WS via `NetworkClient.connect_to_game(_game_id, _player_id)`, and requests `NetworkClient.get_game_state(_game_id, Callable(self, "_on_state_response"))`.

- [ ] **Step 4: Fix lobby create/start flow**

Ensure create-room flow does not stop at lobby after `POST /start`: successful start must call `_show_view("game")`, connect WS, refresh state, and hide lobby-only panels. If create->join auto flow creates an AI before start, preserve that behavior.

- [ ] **Step 5: Add regression checks**

Update `godot-client/tools/e2e_one_game.gd` or add a small sibling tool so it can verify:

```text
mainline_start_reaches_game_view=true
lobby_create_start_reaches_game_view=true
state_updated_after_entry=true
```

Use existing screenshot helpers to save menu/lobby/game frames under `godot-client/logs/` or `user://`, so a reviewer can inspect the UI state.

- [ ] **Step 6: Verify**

Run:

```powershell
& 'D:\Python\godot\Godot_v4.7-stable_win64_console.exe' --headless --path godot-client --import --quit
& 'D:\Python\godot\Godot_v4.7-stable_win64_console.exe' --headless --path godot-client res://tools/e2e_one_game.tscn
```

Expected: import exits 0; live e2e enters game, receives state, can complete or at least advance turns without being stuck at entry.

---

### Task 2: Remove Obsolete Home Free-Play / Solo AI Entry

**Files:**
- Modify: `godot-client/scenes/main.tscn`
- Modify: `godot-client/scripts/main.gd`
- Modify: `godot-client/tools/smoke_test.gd`
- Modify: `godot-client/tools/menu_screenshot.gd` if it asserts menu buttons by index
- Modify: `godot-client/README.md`
- Modify: `docs/WebUI-vs-GodotClient-差异与计划.md`

**Interfaces:**
- Consumes: current menu node tree under `Menu/CenterContainer`.
- Produces: home page without “自由对局（人机）” and without solo-only handlers that are no longer reachable.

- [ ] **Step 1: Identify solo-only nodes and handlers**

Search:

```powershell
rg -n "FreePlay|free_play|自由|人机|SoloCard|_on_free_play_pressed|_entry_flow = \"free\"" godot-client
```

Classify each hit:

- remove if it only serves the old home free-play page/entry;
- keep if lobby/mainline/e2e still uses it for shared create/join/start behavior.

- [ ] **Step 2: Update menu scene**

Remove the visible `FreePlayButton` / “自由对局（人机）” option and any solo-only card container that becomes empty. Keep mainline, lobby, saves, settings, editor, resume, and exit entries.

- [ ] **Step 3: Remove or disconnect solo handlers**

In `main.gd`, remove `_on_free_play_pressed` and direct button connections if no other code calls it. Keep reusable lower-level helpers such as `_on_create_game_response`, `_on_join_game_response`, and `_on_start_game_response` only if Task 1 or test automation still uses them.

- [ ] **Step 4: Update smoke/menu screenshot expectations**

Change smoke assertions so the menu expects mainline/lobby/saves/settings/editor/resume/exit and explicitly asserts the removed free-play button is absent.

- [ ] **Step 5: Verify no orphan paths**

Run:

```powershell
rg -n "FreePlayButton|_on_free_play_pressed|自由对局|人机" godot-client
& 'D:\Python\godot\Godot_v4.7-stable_win64_console.exe' --headless --path godot-client --import --quit
```

Expected: only historical docs/logs mention the old label; Godot import exits 0.

---

### Task 3: Server-Authoritative Attack Forecast

**Files:**
- Modify: `game/app/routes/actions.py`
- Create: `game/tests/test_godot_forecast_api.py`
- Modify: `godot-client/scripts/autoload/network_client.gd`
- Modify: `godot-client/scripts/main.gd`
- Modify: `docs/参考/Godot客户端后端接口.md`

**Interfaces:**
- Consumes: `GET /games/{game_id}/state`, existing unit ids, existing server damage calculation path.
- Produces: `GET /games/{game_id}/forecast-attack?player_id={pid}&attacker_id={aid}&target_id={tid}` returning a JSON object with `damage`, `crit_rate`, `crit_damage`, `is_kill`, `counter_damage`, `attacker_hp_after_counter`, `type_multiplier`.

- [ ] **Step 1: Write failing backend API tests**

Create `game/tests/test_godot_forecast_api.py` with tests that create/start a small game, choose a valid attacker/target pair, call the endpoint, and assert the response has numeric forecast fields without mutating unit HP.

- [ ] **Step 2: Run the failing test**

Run:

```powershell
cd game
pytest tests/test_godot_forecast_api.py -v
```

Expected: fail with 404 because the endpoint does not exist.

- [ ] **Step 3: Add the read-only endpoint**

Add a route in `game/app/routes/actions.py` that loads game state, validates `player_id`, `attacker_id`, and `target_id`, calls the same server-side damage/attack forecast logic used by the real attack path, and returns forecast JSON without committing combat changes.

- [ ] **Step 4: Add Godot HTTP wrapper**

Add to `godot-client/scripts/autoload/network_client.gd`:

```gdscript
func forecast_attack(game_id: int, player_id: int, attacker_id: int, target_id: int, callback: Callable = Callable()) -> void:
	var path := "/games/%d/forecast-attack?player_id=%d&attacker_id=%d&target_id=%d" % [
		game_id, player_id, attacker_id, target_id
	]
	request("GET", path, {}, callback)
```

- [ ] **Step 5: Wire attack confirm panel**

In `godot-client/scripts/main.gd`, call `NetworkClient.forecast_attack` inside `_show_attack_confirm`, initially render attacker/target/distance, then update `attack_confirm_body.text` when forecast arrives.

- [ ] **Step 6: Verify**

Run:

```powershell
cd game
pytest tests/test_godot_forecast_api.py -v
cd ..
& 'D:\Python\godot\Godot_v4.7-stable_win64_console.exe' --headless --path godot-client --import --quit
```

Expected: pytest passes; Godot import exits 0.

---

### Task 4: Map Editor Advanced Tools

**Files:**
- Modify: `godot-client/scenes/main.tscn`
- Modify: `godot-client/scripts/main.gd`
- Modify: `godot-client/tools/smoke_test.gd`

**Interfaces:**
- Consumes: existing `_editor_map`, `_render_editor_map`, `_on_editor_tile_clicked`, `NetworkClient.save_editor_map`.
- Produces: editor tools `Paint`, `Fill`, `Line`, `Select`, `Place Unit`, `Erase Unit`, plus undo/redo stacks.

- [ ] **Step 1: Add smoke expectations**

Extend `smoke_test.gd` to assert editor UI exposes `EditorUndoBtn`, `EditorRedoBtn`, and an editor tool option containing `Fill`, `Line`, and `Select`.

- [ ] **Step 2: Run smoke to confirm failure**

Run:

```powershell
& 'D:\Python\godot\Godot_v4.7-stable_win64_console.exe' --headless --path godot-client res://tools/smoke_test.tscn
```

Expected: fails on missing editor advanced controls.

- [ ] **Step 3: Add UI nodes**

Add undo/redo buttons and tool choices to `EditorView/EditorPanel` in `main.tscn`, following the existing OptionButton/Button layout.

- [ ] **Step 4: Implement editor state helpers**

In `main.gd`, add `_editor_undo_stack`, `_editor_redo_stack`, `_push_editor_undo`, `_apply_editor_snapshot`, `_on_editor_undo_pressed`, `_on_editor_redo_pressed`.

- [ ] **Step 5: Implement tools**

Add flood fill over `layout`, Bresenham line paint between mouse down/up tiles, and select mode for moving/recoloring existing `initial_units`.

- [ ] **Step 6: Verify**

Run smoke and Godot import. Expected: editor smoke assertions pass or, if smoke still waits on network, Godot import exits 0 and editor path assertions pass before any network wait.

---

### Task 5: Help and Reference Panel

**Files:**
- Modify: `godot-client/scenes/main.tscn`
- Modify: `godot-client/scripts/main.gd`
- Modify: `godot-client/tools/smoke_test.gd`
- Modify: `docs/WebUI-vs-GodotClient-差异与计划.md`

**Interfaces:**
- Consumes: hardcoded `Config.gd` unit/terrain data initially; later can switch to `/games/units` and `/games/skills`.
- Produces: a visible Help/Reference panel reachable from menu or HUD.

- [ ] **Step 1: Add smoke check for Help panel and button**
- [ ] **Step 2: Add `HelpPanel`, close button, and `HelpButton`/menu entry in `main.tscn`**
- [ ] **Step 3: Implement `_on_help_pressed`, `_render_help_reference`, and `_on_help_close_pressed`**
- [ ] **Step 4: Render terrain, units, skills, turn flow, and combat formula summaries**
- [ ] **Step 5: Verify with Godot import and smoke path checks**

---

### Task 6: AI Commentary UI

**Files:**
- Modify: `godot-client/scripts/autoload/network_client.gd`
- Modify: `godot-client/scripts/autoload/game_state.gd`
- Modify: `godot-client/scripts/main.gd`
- Modify: `godot-client/scenes/main.tscn`

**Interfaces:**
- Consumes: WS `commentary.text` and future `commentary.audio`.
- Produces: signal `commentary_received(payload: Dictionary)` and a visible commentary/chat section in the war report panel.

- [ ] **Step 1: Add `commentary_received(payload: Dictionary)` signal**
- [ ] **Step 2: Emit the signal for `commentary.text` / `commentary.audio` instead of no-op**
- [ ] **Step 3: Add a commentary list node to the war report panel**
- [ ] **Step 4: Append commentary messages with timestamp and optional mood text**
- [ ] **Step 5: Verify by manually calling `_dispatch_ws_message` in smoke with a fake `commentary.text` envelope**

---

### Task 7: Network Diagnostics and Polling Safety Net

**Files:**
- Modify: `godot-client/scripts/autoload/network_client.gd`
- Modify: `godot-client/scripts/main.gd`
- Modify: `godot-client/scenes/main.tscn`

**Interfaces:**
- Consumes: existing WS signals and `_state_poll_timer`.
- Produces: connection status HUD, last seq, reconnect attempt count, last pong age, and a 15s safety poll while WS is connected.

- [ ] **Step 1: Add diagnostic fields to `NetworkClient`**
- [ ] **Step 2: Add HUD label for connection state**
- [ ] **Step 3: Make state polling interval phase-aware**
- [ ] **Step 4: Add 15s safety poll when WS is connected but no snapshot/delta has arrived**
- [ ] **Step 5: Verify with Godot import and a local backend free-play run**

---

### Task 8: Release-Polish Asset Loading

**Files:**
- Modify: `godot-client/scripts/board/unit_node.gd`
- Modify: `godot-client/scripts/autoload/audio_manager.gd`
- Modify: `godot-client/tools/smoke_test.gd`

**Interfaces:**
- Consumes: imported PNG/MP3 resources under `godot-client/assets/` and `godot-client/audio/`.
- Produces: export-safe asset loading without `Loaded resource as image file, this will not work on export` warnings.

- [ ] **Step 1: Replace direct `Image.load("res://assets/classic/*.png")` path with imported texture `load()`**
- [ ] **Step 2: Add fallback for missing imported texture**
- [ ] **Step 3: Add BGM crossfade in `AudioManager` using two `AudioStreamPlayer` nodes or a fade tween**
- [ ] **Step 4: Run smoke and confirm warning count is reduced**
- [ ] **Step 5: Run Godot import**

---

## Execution Order

1. Task 1: Fix mainline and lobby create-to-game entry blockers.
2. Task 2: Remove obsolete home free-play / solo AI entry.
3. Task 3: Attack forecast.
4. Task 4: Editor advanced tools.
5. Task 5: Help/reference panel.
6. Task 6: AI commentary UI.
7. Task 7: Network diagnostics.
8. Task 8: Release-polish asset loading.

## Self-Review

- Spec coverage: covers the current entry-flow blockers, requested home-menu cleanup, and P0/P1/P2 gaps from `docs/WebUI-vs-GodotClient-差异与计划.md`.
- Placeholder scan: no TBD/TODO placeholders; each task has named files and verification.
- Type consistency: endpoint and Godot wrapper names use `forecast_attack`; existing `NetworkClient` method style is preserved.
