# Godot Mainline Preparation UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first usable Godot preparation center for hero, equipment, mercenary, shop, and save presentation before mainline battles.

**Architecture:** Extend the existing `MainlineView` scene with a preparation panel and implement rendering/actions inside `godot-client/scripts/main.gd`. Reuse existing `NetworkClient` wrappers from the backend coordination phase.

**Tech Stack:** Godot 4.7 GDScript, existing `main.tscn`, existing headless smoke test, pytest backend contract tests.

## Global Constraints

- Keep old Web UI intact.
- Do not introduce new external Godot plugins.
- Preserve existing Godot map/editor/lobby behavior and smoke checks.
- The first pass may use text-rich panels; no new art generation is required.
- Mainline battle must start only after an explicit player action from the preparation panel.

---

### Task 1: Preparation Scene Surface

**Files:**
- Modify: `godot-client/scenes/main.tscn`
- Modify: `godot-client/tools/smoke_test.gd`

**Interfaces:**
- Produces node paths consumed by `main.gd`:
  - `MainlineView/MLFrame/MLPrepSummary`
  - `MainlineView/MLFrame/MLPrepTabs`
  - `MainlineView/MLFrame/MLPrepContent`
  - `MainlineView/MLFrame/MLPrepStartBtn`
  - `MainlineView/MLFrame/MLPrepRefreshBtn`

- [ ] Add the preparation summary, tab row, content label, and action buttons to `MainlineView`.
- [ ] Update smoke test to assert these nodes exist.
- [ ] Run `Godot_v4.7-stable_win64_console.exe --headless --path godot-client res://tools/smoke_test.tscn`.

### Task 2: Preparation State and Rendering

**Files:**
- Modify: `godot-client/scripts/main.gd`
- Test: `godot-client/tools/smoke_test.gd`

**Interfaces:**
- Adds `_mainline_prepare_tab: String`
- Adds `_selected_prepare_hero_id: String`
- Adds `_render_mainline_prepare() -> void`
- Adds `_build_prepare_heroes_text(payload: Dictionary) -> String`
- Adds `_build_prepare_roster_text(payload: Dictionary) -> String`
- Adds `_build_prepare_equipment_text(payload: Dictionary) -> String`

- [ ] Connect tab buttons and action buttons in `_ready`.
- [ ] Change `_on_mainline_prepare_response` so it renders preparation instead of calling `start_mainline`.
- [ ] Add smoke assertion that invoking `_on_mainline_prepare_response` fills the content panel and leaves the view on `mainline`.
- [ ] Run the Godot smoke test.

### Task 3: Backend Actions From Preparation

**Files:**
- Modify: `godot-client/scripts/main.gd`
- Modify: `game/tests/test_godot_client_contract.py`

**Interfaces:**
- Adds `_on_prepare_start_pressed() -> void`
- Adds `_on_prepare_refresh_pressed() -> void`
- Adds `_on_prepare_promote_pressed() -> void`
- Adds `_on_prepare_equip_pressed(slot: String, equipment_id: Variant) -> void`
- Adds `_on_prepare_shop_refresh_response(body: Variant, code: int) -> void`
- Adds `_on_prepare_mercenary_response(body: Variant, code: int) -> void`

- [ ] Start button calls `NetworkClient.start_mainline`.
- [ ] Refresh button refetches `prepare`.
- [ ] Hero promotion uses the first available promotion option for the selected hero.
- [ ] Equipment buttons equip the first compatible item or unequip occupied slots.
- [ ] Shop tab fetches and renders `GET /shop`; purchase buttons call `/shop/purchase`.
- [ ] Mercenary tab fetches config and can call allocate for the first listed option.
- [ ] Extend contract test for use sites, not only wrapper definitions.

### Task 4: Verification and Commit

**Files:**
- Modify: changed files only.

**Verification commands:**
- `pytest game/tests/test_godot_client_contract.py game/tests/test_mainline_api.py game/tests/test_save_api.py -q`
- `python -m compileall -q game/app`
- `git diff --check`
- `rg -n "^(<<<<<<<|=======|>>>>>>>)" .`
- `D:\Python\godot\Godot_v4.7-stable_win64_console.exe --headless --path godot-client res://tools/smoke_test.tscn`

- [ ] Run every command above and read the output.
- [ ] Fix failures.
- [ ] Commit with `feat: add godot mainline preparation ui`.
