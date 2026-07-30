# FE8 Slot-First Mainline Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Godot mainline entry follow FE8-style save-slot flow: the player chooses one of three formal save slots first, and the selected slot's saved cursor decides the current chapter.

**Architecture:** Keep backend mainline data APIs intact for editor/debug and existing contracts. Change the Godot `MainlineView` controller from a chapter-list-first screen to a slot-first screen driven by `GET /saves`, reusing existing `load_save` and `start_mainline` flows. Existing chapter detail/prepare/start logic remains as the downstream path after a slot is selected.

**Tech Stack:** Godot 4 GDScript frontend; FastAPI/Python backend tests for source contracts; pytest for regression coverage.

## Global Constraints

- Formal player flow must not show all mainline chapters as the default mainline entry.
- Three manual slots are the authority for the player's chapter position.
- Empty slots start a new campaign at `chapter_01_steel_rebellion`.
- Existing save management remains available in `SavesView`.
- Backend `/mainlines` may remain available for tooling and internal detail loading.

---

### Task 1: Add Contract Test For Slot-First Mainline Entry

**Files:**
- Modify: `game/tests/test_godot_client_contract.py`

**Interfaces:**
- Consumes: `godot-client/scripts/mainline/mainline_controller.gd`
- Produces: a failing regression test that rejects chapter-list-first Godot entry.

- [ ] **Step 1: Write the failing test**

```python
def test_godot_mainline_entry_is_slot_first_not_chapter_list():
    src = _read(ROOT / "godot-client" / "scripts" / "mainline" / "mainline_controller.gd")
    open_start = src.index("func open() -> void:")
    open_end = src.index("func _set_node_visible(", open_start)
    open_body = src[open_start:open_end]
    assert 'NetworkClient.list_saves(_main._user_name, Callable(self, "_on_ml_slots_response"))' in open_body
    assert "NetworkClient.list_mainlines" not in open_body
    assert "NetworkClient.list_mainlines" in src
    assert "func _on_ml_slots_response(" in src
    assert "func _on_slot_continue_pressed(" in src
    assert "func _on_slot_new_game_pressed(" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd game; python -m pytest tests/test_godot_client_contract.py::test_godot_mainline_entry_is_slot_first_not_chapter_list -q`

Expected: FAIL because `open()` still calls `NetworkClient.list_mainlines(...)`.

- [ ] **Step 3: Implement minimal frontend change**

Update `mainline_controller.gd` so `open()` calls `NetworkClient.list_saves(... "_on_ml_slots_response")`, renders three slot rows in `MLListContainer`, and only calls `list_mainlines` from a debug/helper path outside `open()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd game; python -m pytest tests/test_godot_client_contract.py::test_godot_mainline_entry_is_slot_first_not_chapter_list -q`

Expected: PASS.

### Task 2: Wire Slot Actions To Existing Load/Start Flow

**Files:**
- Modify: `godot-client/scripts/mainline/mainline_controller.gd`
- Modify: `game/tests/test_godot_client_contract.py`

**Interfaces:**
- Consumes: `NetworkClient.load_save(user_name, kind, slot_index, callback)`
- Consumes: `NetworkClient.start_mainline(mainline_id, user_name, skip_intro, disabled_unit_indices, callback, force)`
- Produces: `_on_slot_continue_pressed(slot_index)`, `_on_slot_new_game_pressed(slot_index)`, `_on_slot_load_response(body, code, record)`.

- [ ] **Step 1: Write the failing test**

```python
def test_godot_mainline_slots_continue_and_new_game_use_save_cursor():
    src = _read(ROOT / "godot-client" / "scripts" / "mainline" / "mainline_controller.gd")
    assert 'NetworkClient.load_save(_main._user_name, "manual", slot_index' in src
    assert 'NetworkClient.start_mainline(_DEFAULT_MAINLINE_ID, _main._user_name, false, [], Callable(self, "_on_mainline_start_response"), true)' in src
    assert "_selected_mainline_id = str(body.get(\"mainline_id\"" in src
    assert "NetworkClient.get_mainline_detail(_main._selected_mainline_id" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd game; python -m pytest tests/test_godot_client_contract.py::test_godot_mainline_slots_continue_and_new_game_use_save_cursor -q`

Expected: FAIL because slot-specific handlers do not exist yet.

- [ ] **Step 3: Implement minimal frontend change**

Add slot handlers. Existing slot calls load the manual slot and then request that save's `mainline_id` detail/prepare payload. Empty slot calls `start_mainline` for `_DEFAULT_MAINLINE_ID` with `force=true`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd game; python -m pytest tests/test_godot_client_contract.py::test_godot_mainline_slots_continue_and_new_game_use_save_cursor -q`

Expected: PASS.

### Task 3: Update Docs And Run Focused Regression

**Files:**
- Modify: `docs/维护/2026-07-27-fe8-slot-first-mainline-entry.md`

**Interfaces:**
- Produces: maintenance changelog entry documenting FE8 slot-first entry.

- [ ] **Step 1: Add maintenance note**

Create a short Chinese note describing that Godot MainlineView now enters via three save slots and no longer exposes the full chapter list as the default player path.

- [ ] **Step 2: Run focused tests**

Run: `cd game; python -m pytest tests/test_godot_client_contract.py tests/test_save_slot_independence.py tests/test_mainline_chain_gates.py -q`

Expected: PASS.
