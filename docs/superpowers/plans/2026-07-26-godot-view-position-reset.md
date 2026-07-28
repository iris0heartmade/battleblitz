# Godot View Position Reset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix view-position drift when switching between gameplay and lobby/room views.

**Architecture:** Treat page transitions as state boundaries. Board camera pan/zoom state is reset when a new map/game is loaded, and lobby layout mutations are restored to their original anchors before leaving room-specific mode.

**Tech Stack:** Godot 4.7, GDScript, existing headless diagnostic scenes.

## Global Constraints

- Keep changes scoped to Godot client view state.
- Do not alter backend contracts or gameplay rules.
- Preserve user camera pan/zoom during the same loaded battle, but reset between new game/map sessions.
- Update maintenance changelog.

---

### Task 1: Add Regression Diagnostics

**Files:**
- Create: `godot-client/tools/view_position_reset_test.gd`
- Create: `godot-client/tools/view_position_reset_test.tscn`

**Interfaces:**
- Consumes: `Board.load_map(map_json: Dictionary)`, `BoardCamera.reset_to_fit()`, `main._show_view(name: String)`.
- Produces: a headless test scene that exits `0` on stable view state and `1` on drift.

- [ ] Write a failing test that:
  - Loads `main.tscn`.
  - Loads a map into `GameView/Board`.
  - Manually offsets/zooms the board camera and marks it user-positioned.
  - Loads the same map again as a new session and expects fit position/zoom to be restored.
  - Switches lobby to in-room layout, then choose layout, and expects `BottomBar` anchors to return to right-bottom anchoring.

- [ ] Run: `godot --headless --path godot-client res://tools/view_position_reset_test.tscn`
  - Expected before fix: FAIL on camera reset and/or lobby bottom bar anchors.

### Task 2: Reset Board Camera At New Map Boundary

**Files:**
- Modify: `godot-client/scripts/board/board_camera.gd`
- Modify: `godot-client/scripts/board/board.gd`

**Interfaces:**
- Produces: `BoardCamera.begin_new_map(metrics)` or equivalent method that clears user-positioned state before fit.

- [ ] Implement a minimal method on `BoardCamera` to accept new metrics and force fit.
- [ ] Call it from `Board.load_map()` so every new map load starts from deterministic camera position/zoom.
- [ ] Preserve `apply_metrics()` behavior for viewport resize or same-session refreshes if needed.

### Task 3: Restore Lobby Layout Anchors Correctly

**Files:**
- Modify: `godot-client/scripts/main.gd`

**Interfaces:**
- Produces: `_restore_lobby_default_layout()` with correct `BottomBar` right-bottom anchors.

- [ ] Change `BottomBar` anchor restore to `anchor_left/right/top/bottom = 1.0`.
- [ ] Ensure `_show_lobby_choose()` invokes the restore path before showing default lobby selection state.

### Task 4: Verify And Archive

**Files:**
- Create: `docs/维护/2026-07-26-godot-view-position-reset.md`

**Interfaces:**
- Produces: maintenance record for future readers.

- [ ] Run the new headless regression scene until PASS.
- [ ] Run a relevant existing Godot flow if available without backend dependency.
- [ ] Update maintenance changelog with root cause, files changed, and verification command.
