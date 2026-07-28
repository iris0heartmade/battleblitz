# Godot Path Step Movement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Godot units move along the selected tile path instead of tweening directly to the destination, while preserving sub-500ms input feedback.

**Architecture:** Keep server-authoritative movement. The client caches the same path it already computes for hover dots, uses it for immediate local path preview, and the server move event additionally exposes the authoritative path for replays/spectators.

**Tech Stack:** Godot 4.7 GDScript, Python FastAPI backend, existing Godot headless tool tests.

## Global Constraints

- Do not change movement legality, MP cost, terrain passability, or action semantics.
- Local feedback must begin within 500ms after command submission.
- Multi-tile movement must visually traverse path cells, not a single diagonal/straight tween to the endpoint.
- Server remains authoritative; client preview must reconcile to later snapshots.
- Keep edits scoped to movement path playback and move event metadata.

---

### Task 1: Board Path Preview Player

**Files:**
- Modify: `godot-client/scripts/board/board.gd`
- Test: `godot-client/tools/action_latency_test.gd`

**Interfaces:**
- Produces: `func preview_unit_path(unit_id: int, path_cells: Array, max_total_sec: float = 0.45) -> void`
- Consumes: existing `metrics.cell_to_local(cell)` and `_unit_nodes_by_id`

- [ ] **Step 1: Write the failing test**

Add a test case in `godot-client/tools/action_latency_test.gd` that calls:

```gdscript
board.preview_unit_path(101, [
	Vector2i(1, 1),
	Vector2i(2, 1),
	Vector2i(2, 2),
	Vector2i(3, 2),
], 0.45)
await get_tree().create_timer(0.16).timeout
var mid_pos: Vector2 = unit_node.position
assert_true(mid_pos.distance_to(board.metrics.cell_to_local(Vector2i(3, 2))) > 8.0, "path preview should not jump directly to destination")
await get_tree().create_timer(0.40).timeout
assert_true(unit_node.position.distance_to(board.metrics.cell_to_local(Vector2i(3, 2))) <= 1.0, "path preview should finish at destination")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
D:\Python\godot\Godot_v4.7-stable_win64_console.exe --headless --path godot-client res://tools/action_latency_test.tscn
```

Expected: FAIL because `preview_unit_path` does not exist.

- [ ] **Step 3: Implement minimal path player**

In `board.gd`, add:

```gdscript
func preview_unit_path(unit_id: int, path_cells: Array, max_total_sec: float = 0.45) -> void:
	if path_cells.is_empty():
		return
	if path_cells.size() <= 2:
		preview_unit_move(unit_id, Vector2i(path_cells[-1]), min(max_total_sec, 0.28))
		return
	if metrics == null:
		return
	var existing: Node2D = _unit_nodes_by_id.get(unit_id) as Node2D
	if existing == null or not is_instance_valid(existing):
		return
	var old_tween: Tween = existing.get_meta("move_tween") if existing.has_meta("move_tween") else null
	if old_tween != null and old_tween.is_running():
		old_tween.kill()
	var steps: Array = path_cells.slice(1)
	var step_sec: float = min(0.10, max_total_sec / float(max(1, steps.size())))
	var t: Tween = create_tween()
	existing.set_meta("move_tween", t)
	t.set_trans(Tween.TRANS_LINEAR)
	t.set_ease(Tween.EASE_IN_OUT)
	for cell in steps:
		t.tween_property(existing, "position", metrics.cell_to_local(Vector2i(cell)), step_sec)
```

- [ ] **Step 4: Run test to verify it passes**

Run the same Godot headless command.

Expected: `action_latency_test.gd` passes with zero failures.

---

### Task 2: Cache Hover Path And Use It On Click

**Files:**
- Modify: `godot-client/scripts/main.gd`
- Test: `godot-client/tools/action_latency_test.gd`

**Interfaces:**
- Consumes: `Board.preview_unit_path(unit_id, path_cells, max_total_sec)`
- Produces: `_move_preview_path: Array` and `_move_preview_target: Vector2i`

- [ ] **Step 1: Write failing test**

Extend the Godot tool test to simulate or directly call the new move feedback helper with a multi-cell path:

```gdscript
main._apply_immediate_move_feedback(101, Vector2i(3, 2), [
	Vector2i(1, 1),
	Vector2i(2, 1),
	Vector2i(2, 2),
	Vector2i(3, 2),
])
await get_tree().create_timer(0.16).timeout
assert_true(unit_node.position.distance_to(board.metrics.cell_to_local(Vector2i(3, 2))) > 8.0, "move feedback should consume path when provided")
```

Expected old signature failure or endpoint-jump failure.

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
D:\Python\godot\Godot_v4.7-stable_win64_console.exe --headless --path godot-client res://tools/action_latency_test.tscn
```

- [ ] **Step 3: Add path state fields**

Near `_path_hover_last`, add:

```gdscript
var _move_preview_path: Array = []
var _move_preview_target: Vector2i = Vector2i(-1, -1)
```

- [ ] **Step 4: Cache hover path**

In `_update_path_dots_on_hover()`, after `var path: Array = MapLogic.pathfind(...)`, set:

```gdscript
_move_preview_path = path.duplicate()
_move_preview_target = target_cell
```

When hover leaves reachable tiles, clear only the target path:

```gdscript
_move_preview_path = []
_move_preview_target = Vector2i(-1, -1)
```

- [ ] **Step 5: Feed path to move feedback**

Change helper signature to:

```gdscript
func _apply_immediate_move_feedback(unit_id: int, to_cell: Vector2i, path_cells: Array = []) -> void:
```

Inside it:

```gdscript
if board != null:
	if path_cells.size() >= 2 and board.has_method("preview_unit_path"):
		board.preview_unit_path(unit_id, path_cells, 0.45)
	elif board.has_method("preview_unit_move"):
		board.preview_unit_move(unit_id, to_cell, 0.28)
	board.clear_selection_marks()
```

- [ ] **Step 6: Resolve path on click**

In `_move_unit_to()`, before calling `_apply_immediate_move_feedback`, choose:

```gdscript
var to_cell := Vector2i(to_x, to_y)
var path_cells: Array = []
if _move_preview_target == to_cell and _move_preview_path.size() >= 2:
	path_cells = _move_preview_path.duplicate()
_apply_immediate_move_feedback(unit_id, to_cell, path_cells)
```

- [ ] **Step 7: Clear cache on cancel/submit**

In `_cancel_move_mode()` and `_apply_immediate_move_feedback()`, set:

```gdscript
_move_preview_path = []
_move_preview_target = Vector2i(-1, -1)
```

- [ ] **Step 8: Run test to verify it passes**

Run the Godot headless test command again.

Expected: action latency and path preview assertions pass.

---

### Task 3: Server Move Event Carries Authoritative Path

**Files:**
- Modify: `game/app/routes/actions.py`
- Test: existing backend move test if available; otherwise add focused route/unit test under existing test style

**Interfaces:**
- Produces: move `GameEvent.context["path"]` as `list[{"x": int, "y": int}]`

- [ ] **Step 1: Write failing assertion**

Locate the existing test that exercises `POST /games/{id}/move` and event publication. Add:

```python
assert event.context["path"][0] == {"x": from_x, "y": from_y}
assert event.context["path"][-1] == {"x": to_x, "y": to_y}
```

If no event assertion test exists, add the smallest test around the move route’s bus publish capture using the repository’s existing test fixtures.

- [ ] **Step 2: Run backend test to verify it fails**

Run the narrow pytest command for the selected test file.

Expected: FAIL because `context["path"]` is missing.

- [ ] **Step 3: Add path to move event context**

In `actions.py`, update the move event context:

```python
"path": [{"x": x, "y": y} for x, y in path],
```

- [ ] **Step 4: Run backend test to verify it passes**

Run the same pytest command.

Expected: PASS.

---

### Task 4: Documentation And Regression Verification

**Files:**
- Modify: `docs/维护/2026-07-26-godot-action-latency.md`
- Modify or create: `docs/维护/2026-07-26-godot-path-step-movement.md`

**Interfaces:**
- Consumes: implementation behavior from Tasks 1-3
- Produces: maintenance note for future developers

- [ ] **Step 1: Update maintenance changelog**

Record:

```markdown
## 逐格路径移动

- Godot 点击移动时优先复用 hover 期间计算出的 `MapLogic.pathfind()` 路径。
- `Board.preview_unit_path()` 负责把 `[start, ..., goal]` 播成逐格 Tween。
- 服务端 move event context 增加 `path`,供回放/旁观者使用。
- 保持 500ms 内反馈目标;路径总动画时长封顶 0.45s。
```

- [ ] **Step 2: Run Godot regression tests**

Run:

```powershell
D:\Python\godot\Godot_v4.7-stable_win64_console.exe --headless --path godot-client res://tools/action_latency_test.tscn
D:\Python\godot\Godot_v4.7-stable_win64_console.exe --headless --path godot-client res://tools/view_position_reset_test.tscn
```

Expected: both pass with zero failures.

- [ ] **Step 3: Run backend focused test**

Run the pytest command selected in Task 3.

Expected: pass.

- [ ] **Step 4: Inspect diff**

Run:

```powershell
git diff -- godot-client/scripts/board/board.gd godot-client/scripts/main.gd game/app/routes/actions.py godot-client/tools/action_latency_test.gd docs
```

Expected: diff only touches path movement, event metadata, tests, and docs.

