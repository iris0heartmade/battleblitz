# Godot Action Latency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make movement and attack commands provide visible feedback within 500ms.

**Architecture:** Keep the server authoritative, but add client-side immediate feedback at the command boundary. `Board` owns visual previews, while `main.gd` invokes those previews before waiting for REST/WS confirmation.

**Tech Stack:** Godot 4.7, GDScript, existing headless diagnostic scenes.

## Global Constraints

- Do not predict damage or final combat results on the client.
- Do not change backend APIs or gameplay rules.
- Visual feedback for move/attack command submission must appear within 500ms.
- Server snapshots/events remain the source of truth and may correct local previews.

---

### Task 1: Regression Test

**Files:**
- Create: `godot-client/tools/action_latency_test.gd`
- Create: `godot-client/tools/action_latency_test.tscn`

**Interfaces:**
- Consumes: `Board.preview_unit_move(unit_id: int, to_cell: Vector2i, duration_sec: float)`.
- Consumes: `main._apply_immediate_move_feedback(unit_id: int, to_cell: Vector2i)`.
- Consumes: `main._apply_immediate_attack_feedback(attacker_id: int, target_id: int)`.

- [ ] Write a headless test that loads `main.tscn`, seeds `GameState`, loads a map, and asserts immediate move/attack feedback appears before 500ms.
- [ ] Run it before implementation and confirm it fails because the new helper methods do not exist.

### Task 2: Board Visual Preview

**Files:**
- Modify: `godot-client/scripts/board/board.gd`

**Interfaces:**
- Produces: `preview_unit_move(unit_id: int, to_cell: Vector2i, duration_sec: float = 0.28) -> void`.

- [ ] Add a board method that moves the existing unit presenter toward `to_cell` using a short tween.
- [ ] Kill any previous movement tween for the same unit before starting the preview.
- [ ] Keep authoritative correction through existing `GameState.units_changed` flow.

### Task 3: Command Boundary Feedback

**Files:**
- Modify: `godot-client/scripts/main.gd`

**Interfaces:**
- Produces: `_apply_immediate_move_feedback(unit_id: int, to_cell: Vector2i) -> void`.
- Produces: `_apply_immediate_attack_feedback(attacker_id: int, target_id: int) -> void`.

- [ ] Call immediate move feedback before `NetworkClient.action_move`.
- [ ] Call immediate attack feedback before `NetworkClient.action_attack`.
- [ ] Hide modal/highlights immediately and update status text immediately.

### Task 4: Verify And Archive

**Files:**
- Create: `docs/维护/2026-07-26-godot-action-latency.md`

- [ ] Run `action_latency_test.tscn`.
- [ ] Run the existing `view_position_reset_test.tscn`.
- [ ] Archive root cause, files, and verification results.
