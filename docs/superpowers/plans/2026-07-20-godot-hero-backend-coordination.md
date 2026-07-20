# Godot Hero Backend Coordination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the `hero-mercenary-dual-track` backend/game design into `godot-map-port` while preserving Godot client completeness and first adapting Godot to the new mainline, hero, mercenary, shop, and save flows.

**Architecture:** Treat `hero-mercenary-dual-track` as the backend/game-design authority and `godot-map-port` as the target branch that owns `godot-client/` and Godot-specific backend affordances. Resolve conflicts by accepting hero-domain/save/mercenary/mainline business code from the hero branch, then reapply Godot-specific endpoints and client calls on top. Keep old Web UI present and loadable, but defer UI parity polishing until after Godot first-stage adaptation.

**Tech Stack:** Python FastAPI + SQLAlchemy backend, pytest test suite, Godot 4 GDScript client, existing Web UI in static HTML/CSS/JS.

## Global Constraints

- Base branch is `godot-map-port`; source branch is `hero-mercenary-dual-track`.
- Preserve all files under `godot-client/**`.
- Absorb hero branch backend/game design modules: `hero_domain`, `mercenary_domain`, `save`, items, shops, test chapters, stories, and related tests.
- Preserve Godot branch backend additions: map editor enhancements, `/games/{game_id}/forecast-attack`, BGM metadata, WS compatibility, and Godot client API expectations.
- Old Web UI must remain present and loadable, but first-stage implementation prioritizes Godot client adaptation.
- Do not remove tests to make the merge pass.

---

## File Structure

- `game/app/main.py`: router registration for both branches.
- `game/app/mainline/schemas.py`: shared mainline wire format; hero branch shape plus Godot metadata fields.
- `game/app/routes/mainline.py`: mainline prepare/start/advance/shop/mercenary flow; hero branch base plus Godot compatibility.
- `game/app/routes/actions.py`: combat actions; hero branch base plus Godot attack forecast endpoint.
- `game/app/routes/editor.py`: Godot map editor route enhancements.
- `game/app/routes/save.py`, `game/app/save/**`: hero branch save system.
- `game/app/hero_domain/**`, `game/app/mercenary_domain/**`, `game/app/item_catalog.py`: hero branch business modules.
- `game/app/web/**`: restored old Web UI and assets.
- `godot-client/scripts/autoload/network_client.gd`: new REST wrappers for prepare/shop/mercenary/save.
- `godot-client/scripts/main.gd`: first-stage Godot UI state wiring for prepare/shop/mercenary/save semantics.
- `game/tests/**`: merged backend tests from both branches.

### Task 1: Create Execution Branch and Baseline

**Files:**
- Modify: none
- Test: repository status and baseline targeted tests

**Interfaces:**
- Consumes: current `godot-map-port` branch with spec commit.
- Produces: branch `codex/godot-hero-backend-coordination` ready for merge work.

- [ ] **Step 1: Create implementation branch**

Run:

```powershell
git switch -c codex/godot-hero-backend-coordination
```

Expected: branch switches to `codex/godot-hero-backend-coordination`.

- [ ] **Step 2: Confirm only known untracked report remains**

Run:

```powershell
git status --short --branch
```

Expected: branch is `codex/godot-hero-backend-coordination`; only `branch-diff-report_godot-map-port_vs_hero-mercenary-dual-track.md` is untracked.

- [ ] **Step 3: Run focused baseline tests**

Run:

```powershell
pytest game/tests/test_mainline_api.py game/tests/test_player_vs_ai_full_game.py game/tests/test_map_capacity.py -q
```

Expected: current baseline result recorded before merge. If failures exist, keep going only after noting exact failures because they are pre-merge state.

### Task 2: Merge Backend/Game Design From Hero Branch

**Files:**
- Create/restore: `game/app/hero_domain/**`, `game/app/mercenary_domain/**`, `game/app/save/**`, `game/app/routes/save.py`, `game/app/item_catalog.py`, `game/items/**`, `game/shops/**`, `game/mainlines/chapter_test_*.json`, `game/stories/chapter_test_*`
- Modify: shared backend files listed in File Structure
- Test: conflict-free worktree after merge

**Interfaces:**
- Consumes: `hero-mercenary-dual-track` branch.
- Produces: merged source tree containing both Godot and hero backend surfaces.

- [ ] **Step 1: Start a no-commit merge**

Run:

```powershell
git merge --no-commit --no-ff hero-mercenary-dual-track
```

Expected: Git reports conflicts in shared backend/Web/test files.

- [ ] **Step 2: Accept hero-owned backend modules**

Run:

```powershell
git checkout --theirs -- game/app/hero_domain game/app/mercenary_domain game/app/save game/app/routes/save.py game/app/item_catalog.py game/items game/shops game/mainlines/chapter_test_01.json game/mainlines/chapter_test_02.json game/mainlines/chapter_test_03.json game/stories/chapter_test_01 game/stories/chapter_test_02 game/stories/chapter_test_03 game/requirements-e2e.txt game/pytest.ini
```

Expected: hero-owned modules are restored from the source branch.

- [ ] **Step 3: Preserve Godot-owned client tree**

Run:

```powershell
git checkout --ours -- godot-client
```

Expected: `godot-client/**` remains from `godot-map-port`.

- [ ] **Step 4: Resolve shared files manually**

Edit shared files using this rule:

```text
Use hero branch implementation as the base for business behavior.
Reapply Godot-specific endpoints/fields from godot-map-port:
- /games/{game_id}/forecast-attack in game/app/routes/actions.py
- custom map editor enhancements in game/app/routes/editor.py
- BGM metadata and battle_config fields in game/app/mainline/schemas.py and game/app/routes/mainline.py
- router registrations for save/audio/commanders/editor/ws/mainline/heroes/profile/progression in game/app/main.py
- WS gateway URL shape used by Godot: /ws/games/{game_id}?player_id={pid}&since_seq={N}
```

Expected: no conflict markers remain.

- [ ] **Step 5: Verify conflict markers**

Run:

```powershell
rg "<<<<<<<|=======|>>>>>>>" game README.md .gitignore
```

Expected: no matches.

- [ ] **Step 6: Stage backend merge**

Run:

```powershell
git add game README.md .gitignore docs
git status --short
```

Expected: merged files staged; `godot-client/**` preserved; untracked branch diff report remains untracked.

### Task 3: Restore Godot Backend Compatibility Tests

**Files:**
- Modify: `game/tests/test_mainline_api.py`
- Modify: `game/tests/test_castle_unit_placement.py`
- Modify: `game/tests/test_map_capacity.py`
- Modify: `game/tests/test_player_vs_ai_full_game.py`
- Create or preserve: tests from hero branch for hero, mercenary, save

**Interfaces:**
- Consumes: merged backend from Task 2.
- Produces: test suite asserting both hero backend design and Godot-specific compatibility.

- [ ] **Step 1: Add or preserve forecast endpoint assertion**

In `game/tests/test_mainline_api.py` or the existing action-route test file, ensure an async client test calls:

```python
resp = await client.get(f"/games/{game_id}/forecast-attack", params={
    "attacker_id": attacker_id,
    "target_id": target_id,
})
assert resp.status_code == 200
assert "damage" in resp.json()
```

Expected: test fails if `/forecast-attack` is lost during merge.

- [ ] **Step 2: Ensure save route smoke remains**

In `game/tests/test_save_api.py`, preserve tests for:

```python
GET /saves
POST /saves/save
POST /saves/load
POST /saves/load_suspend
POST /saves/erase
POST /games/{game_id}/suspend
```

Expected: tests fail if save router is not included.

- [ ] **Step 3: Run backend focused tests**

Run:

```powershell
pytest game/tests/test_mainline_api.py game/tests/test_mainline_engine.py game/tests/test_mainline_mercenary.py game/tests/test_hero_domain_models.py game/tests/test_hero_equipment.py game/tests/test_hero_promotion.py game/tests/test_save_api.py game/tests/test_save_resume_fixes.py game/tests/test_castle_unit_placement.py game/tests/test_player_vs_ai_full_game.py game/tests/test_map_capacity.py -q
```

Expected: failures identify remaining merge mistakes; fix code, not tests, unless test expectations contradict the approved spec.

### Task 4: Add Godot Network Wrappers

**Files:**
- Modify: `godot-client/scripts/autoload/network_client.gd`
- Test: Godot smoke script or text-level grep for function definitions

**Interfaces:**
- Consumes: backend endpoints from Task 2.
- Produces: GDScript methods used by Task 5 UI.

- [ ] **Step 1: Add mainline prepare wrappers**

Add methods with these signatures:

```gdscript
func get_mainline_prepare(mainline_id: String, user_name: String, callback: Callable = Callable()) -> void:
	request("GET", "/mainlines/%s/prepare?user_name=%s" % [mainline_id.uri_encode(), user_name.uri_encode()], {}, callback)

func complete_mainline_prepare(mainline_id: String, user_name: String, disabled_unit_indices: Array = [], callback: Callable = Callable()) -> void:
	request("POST", "/mainlines/%s/prepare/complete" % mainline_id.uri_encode(), {
		"user_name": user_name,
		"disabled_unit_indices": disabled_unit_indices,
	}, callback)
```

- [ ] **Step 2: Add hero/shop/mercenary wrappers**

Add methods:

```gdscript
func promote_mainline_hero(mainline_id: String, user_name: String, hero_id: String, target_class_id: String, callback: Callable = Callable()) -> void:
	request("POST", "/mainlines/%s/prepare/promote" % mainline_id.uri_encode(), {"user_name": user_name, "hero_id": hero_id, "target_class_id": target_class_id}, callback)

func equip_mainline_hero(mainline_id: String, user_name: String, hero_id: String, slot: String, equipment_id: Variant, callback: Callable = Callable()) -> void:
	request("POST", "/mainlines/%s/prepare/equipment" % mainline_id.uri_encode(), {"user_name": user_name, "hero_id": hero_id, "slot": slot, "equipment_id": equipment_id}, callback)

func get_post_battle_shop(mainline_id: String, user_name: String, callback: Callable = Callable()) -> void:
	request("GET", "/mainlines/%s/shop?user_name=%s" % [mainline_id.uri_encode(), user_name.uri_encode()], {}, callback)

func purchase_post_battle_shop_item(mainline_id: String, user_name: String, item_id: String, quantity: int = 1, callback: Callable = Callable()) -> void:
	request("POST", "/mainlines/%s/shop/purchase" % mainline_id.uri_encode(), {"user_name": user_name, "item_id": item_id, "quantity": quantity}, callback)

func get_mercenary_config(mainline_id: String, user_name: String, callback: Callable = Callable()) -> void:
	request("GET", "/mainlines/%s/mercenary/config?user_name=%s" % [mainline_id.uri_encode(), user_name.uri_encode()], {}, callback)

func allocate_mercenary_points(mainline_id: String, user_name: String, unit_type: String, stat: String, value: int, callback: Callable = Callable()) -> void:
	request("POST", "/mainlines/%s/mercenary/allocate" % mainline_id.uri_encode(), {"user_name": user_name, "unit_type": unit_type, "stat": stat, "value": value}, callback)
```

- [ ] **Step 3: Add save wrappers**

Add methods:

```gdscript
func list_saves(user_name: String, callback: Callable = Callable()) -> void:
	request("GET", "/saves?user_name=%s" % user_name.uri_encode(), {}, callback)

func load_save(user_name: String, save_id: int, callback: Callable = Callable()) -> void:
	request("POST", "/saves/load", {"user_name": user_name, "save_id": save_id}, callback)

func load_suspend(user_name: String, callback: Callable = Callable()) -> void:
	request("POST", "/saves/load_suspend", {"user_name": user_name}, callback)

func erase_save(user_name: String, save_id: int, callback: Callable = Callable()) -> void:
	request("POST", "/saves/erase", {"user_name": user_name, "save_id": save_id}, callback)

func capture_suspend(game_id: int, user_name: String, player_id: int, reason: String = "manual", callback: Callable = Callable()) -> void:
	request("POST", "/games/%d/suspend" % game_id, {"user_name": user_name, "player_id": player_id, "reason": reason}, callback)
```

- [ ] **Step 4: Check functions exist**

Run:

```powershell
rg "func (get_mainline_prepare|promote_mainline_hero|list_saves|load_save|erase_save|capture_suspend)" godot-client/scripts/autoload/network_client.gd
```

Expected: all new functions are listed.

### Task 5: Adapt Godot Mainline and Save UI Semantics

**Files:**
- Modify: `godot-client/scripts/main.gd`
- Modify if needed: `godot-client/scenes/main.tscn`
- Test: Godot smoke/e2e

**Interfaces:**
- Consumes: NetworkClient wrappers from Task 4.
- Produces: first-stage playable Godot flow for new backend design.

- [ ] **Step 1: Route saves view through save API**

Replace old save list/resume/delete calls with:

```gdscript
NetworkClient.list_saves(_user_name, Callable(self, "_on_saves_response"))
NetworkClient.load_save(_user_name, _selected_save_id, Callable(self, "_on_save_load_response"))
NetworkClient.erase_save(_user_name, _selected_save_id, Callable(self, "_on_save_delete_response").bind(_selected_save_id))
```

Expected: no call treats save id as game id.

- [ ] **Step 2: Add prepare fetch before mainline start**

When a mainline is selected, call:

```gdscript
NetworkClient.get_mainline_prepare(_selected_mainline_id, _user_name, Callable(self, "_on_mainline_prepare_response"))
```

Store the returned `heroes`, `roster_units`, `inventory`, `equipment_catalog`, `rewards_on_clear`, and `battle_index` dictionaries in main.gd state variables.

- [ ] **Step 3: Pass disabled unit indices on start and next battle**

Update calls to:

```gdscript
NetworkClient.start_mainline(_selected_mainline_id, _user_name, false, disabled_unit_indices, Callable(self, "_on_mainline_start_response"))
NetworkClient.next_battle_mainline(_active_mainline_id, _user_name, disabled_unit_indices, Callable(self, "_on_mainline_next_battle_response"))
```

Expected: backend receives `disabled_unit_indices` matching UI selection.

- [ ] **Step 4: Add minimal prepare rendering**

Render prepare payload into existing MainlineView labels or dynamic containers:

```gdscript
"战前准备: %s / 第 %d/%d 战\n英雄: %d\n可部署: %d\n金币: %d" % [
	body.get("battle_title", ""),
	int(body.get("battle_index", 0)) + 1,
	int(body.get("total_battles", 0)),
	(body.get("heroes", []) as Array).size(),
	(body.get("roster_units", []) as Array).size(),
	int((body.get("inventory", {}) as Dictionary).get("gold", 0)),
]
```

Expected: Godot player can see that prepare data loaded before starting.

- [ ] **Step 5: Wire suspend button only if existing UI control exists**

If a battle-exit or save button already exists in `main.gd`, call:

```gdscript
NetworkClient.capture_suspend(GameState.game_id, _user_name, GameState.player_id, "manual", Callable(self, "_on_suspend_response"))
```

Expected: no new scene layout is required for first stage if no suitable button exists.

### Task 6: Verification and Commit

**Files:**
- Modify: all files touched in Tasks 2-5
- Test: backend pytest and Godot smoke/e2e

**Interfaces:**
- Consumes: merged and adapted code.
- Produces: verified commit.

- [ ] **Step 1: Run conflict marker scan**

Run:

```powershell
rg "<<<<<<<|=======|>>>>>>>" .
```

Expected: no matches.

- [ ] **Step 2: Run backend targeted test suite**

Run:

```powershell
pytest game/tests/test_mainline_api.py game/tests/test_mainline_engine.py game/tests/test_mainline_mercenary.py game/tests/test_hero_domain_models.py game/tests/test_hero_equipment.py game/tests/test_hero_promotion.py game/tests/test_save_api.py game/tests/test_save_resume_fixes.py game/tests/test_castle_unit_placement.py game/tests/test_player_vs_ai_full_game.py game/tests/test_map_capacity.py -q
```

Expected: all selected tests pass, or failures are documented with exact file/test names if blocked by pre-existing environment constraints.

- [ ] **Step 3: Run Godot smoke/e2e if Godot executable is available**

Run the existing project command used by `godot-client/tools/smoke_test.gd` or the documented Godot smoke command in `godot-client/README.md`.

Expected: smoke passes. If Godot is not installed or not on PATH, record the missing executable.

- [ ] **Step 4: Check git status**

Run:

```powershell
git status --short --branch
```

Expected: only intended files changed; `branch-diff-report_godot-map-port_vs_hero-mercenary-dual-track.md` remains untracked unless explicitly staged later.

- [ ] **Step 5: Commit implementation**

Run:

```powershell
git add game godot-client docs/superpowers/plans/2026-07-20-godot-hero-backend-coordination.md
git commit -m "feat: coordinate godot client with hero backend"
```

Expected: implementation commit created on `codex/godot-hero-backend-coordination`.

## Self-Review

- Spec coverage: each approved spec area maps to a task: backend truth in Task 2, Godot wrappers in Task 4, Godot UI in Task 5, tests in Tasks 3 and 6, Web UI preservation in Task 2.
- Placeholder scan: no placeholder terms are intentionally left for implementers; every task has concrete commands or code signatures.
- Type consistency: Godot wrapper names in Task 4 are the names consumed by Task 5.
