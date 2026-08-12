# FE8 Keyboard Input Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add FE8-style keyboard bindings to the existing Godot input action system.

**Architecture:** Keep the current device-agnostic action routing. Extend `project.godot` action events and `InputHints` keyboard text only, so board/UI controllers keep consuming the same action names.

**Tech Stack:** Godot 4.7 project settings, GDScript autoload, Python pytest contract tests.

## Global Constraints

- Do not add a separate keyboard input router.
- Do not change board click/confirm/cancel business flow.
- Keep keyboard and gamepad mappings coexisting on the same actions.
- Update `godot-client/CHANGELOG.md` in Chinese with a user-facing entry.

---

### Task 1: FE8 Keyboard Bindings

**Files:**
- Modify: `game/tests/test_godot_client_contract.py`
- Modify: `godot-client/project.godot`
- Modify: `godot-client/scripts/autoload/input_hints.gd`
- Modify: `godot-client/CHANGELOG.md`

**Interfaces:**
- Consumes: existing Godot input actions `ui_accept`, `ui_cancel`, `ui_up`, `ui_down`, `ui_left`, `ui_right`, `board_cursor_up`, `board_cursor_down`, `board_cursor_left`, `board_cursor_right`, `board_confirm`, `board_cancel`, `board_zoom_in`, `board_zoom_out`.
- Produces: the same action names with added keyboard keycode events.

- [ ] **Step 1: Write the failing test**

Add a contract test that extracts input action blocks from `project.godot` and asserts:

```python
def test_godot_fe8_keyboard_bindings_are_mapped():
    project = _read(PROJECT_GODOT)
    hints = _read(ROOT / "godot-client" / "scripts" / "autoload" / "input_hints.gd")

    def block(action: str) -> str:
        start = project.index(f"{action}={{")
        end = project.index("\n}", start)
        return project[start:end]

    for action, keycodes in {
        "ui_up": ["4194320", "87"],
        "ui_down": ["4194322", "83"],
        "ui_left": ["4194319", "65"],
        "ui_right": ["4194321", "68"],
        "board_cursor_up": ["4194320", "87"],
        "board_cursor_down": ["4194322", "83"],
        "board_cursor_left": ["4194319", "65"],
        "board_cursor_right": ["4194321", "68"],
        "ui_accept": ["4194309", "4194310", "90", "32"],
        "board_confirm": ["4194309", "90", "32"],
        "ui_cancel": ["4194305", "4194308", "88"],
        "board_cancel": ["4194305", "4194308", "88"],
        "board_zoom_in": ["43", "61", "69"],
        "board_zoom_out": ["45", "95", "81"],
    }.items():
        body = block(action)
        for keycode in keycodes:
            assert f'"keycode":{keycode}' in body

    assert '"confirm": "Z/Enter"' in hints
    assert '"cancel":  "X/Esc"' in hints
    assert '"zoom_in": "E/+"' in hints
    assert '"zoom_out": "Q/-"' in hints
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest game/tests/test_godot_client_contract.py::test_godot_fe8_keyboard_bindings_are_mapped -q`

Expected: FAIL because keycode `90` / `88` / `87` / `65` / `83` / `68` / `69` / `81` are not all mapped yet, and hints still show Enter/Esc.

- [ ] **Step 3: Write minimal implementation**

Update `project.godot`:

- Add W/A/S/D key events to `ui_*` and `board_cursor_*`.
- Add Z and Space to `ui_accept` and `board_confirm`.
- Add X to `ui_cancel` and `board_cancel`.
- Add E to `board_zoom_in`.
- Add Q to `board_zoom_out`.

Update `input_hints.gd` keyboard table:

```gdscript
"confirm": "Z/Enter",
"cancel":  "X/Esc",
"zoom_in": "E/+",
"zoom_out": "Q/-",
```

Update `CHANGELOG.md` with a new dated Chinese section explaining the keyboard support.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest game/tests/test_godot_client_contract.py::test_godot_fe8_keyboard_bindings_are_mapped -q`

Expected: PASS.

- [ ] **Step 5: Run focused contract suite**

Run: `pytest game/tests/test_godot_client_contract.py -q`

Expected: PASS for the full Godot client contract test file.
