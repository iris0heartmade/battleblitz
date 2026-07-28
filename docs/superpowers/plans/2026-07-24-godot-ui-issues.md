# Godot UI Issues Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 5 张截图标注的 Godot UI 问题，并用合约测试与真实客户端流程验证修复不回归。

**Architecture:** 保持 `main.gd` 作为大厅/游戏流程协调器，`mainline_controller.gd` 作为主线页面控制器，`saves_controller.gd` 作为存档页面控制器。状态文本从服务端玩家/存档数据渲染，页面控件由单一页面切换函数管理，动态内容继续由现有 VBox/HBox 容器生成。

**Tech Stack:** Godot 4 GDScript, `.tscn` 场景布局, pytest source-contract tests, existing Godot screenshot/flow scripts.

## Global Constraints

- 不改变服务端座位、AI、存档和主线 API 语义。
- NetworkClient callback 必须保持 `(body, code)` 两参数兼容。
- 立绘原始纹理不得缩放；只调整承载容器、裁剪和对齐。
- 不复用状态弹窗替代真实页面布局；继续使用现有页面节点和主题。
- 每项修复先写可失败的合约测试，再改最小实现。

---

### Task 1: 锁定五项 UI 回归条件

**Files:**
- Modify: `game/tests/test_godot_client_contract.py`
- Read: `godot-client/scripts/main.gd`, `godot-client/scripts/mainline/mainline_controller.gd`, `godot-client/scripts/ui/saves_controller.gd`, `godot-client/scenes/main.tscn`

**Interfaces:**
- Consumes: current GDScript source and scene text.
- Produces: source-level regression tests for AI seat wording, mainline visibility, save layout, launch routing, and portrait container geometry.

- [ ] **Step 1: Write failing assertions**

Add tests that extract the relevant function/node blocks and assert:

```python
def test_lobby_ai_replacement_has_distinct_occupant_rendering():
    src = _read(MAIN_GD)
    start = src.index("func _build_lobby_seat_card(")
    end = src.index("func _lobby_team_index_for_seat(", start)
    body = src[start:end]
    assert "AI替补" in body
    assert "等待玩家入座" in body
    assert "入座中" in body
    assert "is_ai" in body or "ai_replacement" in body


def test_mainline_page_hides_all_prepare_controls_on_chapter_list():
    src = _read(ROOT / "godot-client/scripts/mainline/mainline_controller.gd")
    start = src.index("func _set_mainline_page(")
    end = src.index("func _on_ml_list_response(", start)
    body = src[start:end]
    for name in ["ml_prep_start_btn", "ml_prep_complete_btn", "ml_prep_refresh_btn", "ml_prep_action_btn", "ml_prep_alt_action_btn"]:
        assert name in body


def test_saves_view_uses_non_overlapping_vertical_sections():
    src = _read(ROOT / "godot-client/scenes/main.tscn")
    for node in ["SaveSlotsContainer", "SaveAutoRow", "SaveSuspendRow", "SaveRefreshBtn", "SaveBackBtn"]:
        assert node in src


def test_lobby_start_response_enters_game_directly():
    src = _read(MAIN_GD)
    start = src.index("func _on_lobby_start_response(")
    end = src.index("func ", start + len("func "))
    body = src[start:end]
    assert "_show_view(\"game\")" in body or "_on_start_game_response" in body


def test_portrait_panel_keeps_original_texture_scale():
    src = _read(MAIN_GD)
    scene = _read(ROOT / "godot-client/scenes/main.tscn")
    assert "HeroPortraitPanel" in scene
    assert "STRETCH_KEEP" in src or "EXPAND_IGNORE_SIZE" in src
```

Adjust the launch function boundary to the actual callback block if the current callback has a different ending.

- [ ] **Step 2: Run the focused tests and verify they fail for missing behavior**

Run:

```bash
python -m pytest game/tests/test_godot_client_contract.py -k "ai_replacement or mainline_page or saves_view or lobby_start or portrait_panel" -q
```

Expected: at least the new assertions fail against the current source, while existing unrelated contract tests remain unchanged.

- [ ] **Step 3: Commit the regression tests**

```bash
git add game/tests/test_godot_client_contract.py
git commit -m "test(godot): cover screenshot UI regressions"
```

### Task 2: Fix lobby AI seat status and launch transition

**Files:**
- Modify: `godot-client/scripts/main.gd`
- Test: `game/tests/test_godot_client_contract.py`

**Interfaces:**
- Consumes: `_lobby_seat_ai_replacements`, `_lobby_seat_occupants`, `_lobby_last_players`, `NetworkClient.start_game()` callbacks.
- Produces: deterministic seat label rendering and direct successful start-to-game routing.

- [ ] **Step 1: Add a single seat occupant display helper**

Implement a helper near `_lobby_seat_occupant_name()`:

```gdscript
func _lobby_seat_display_name(seat_index: int) -> String:
    var occupant_name := _lobby_seat_occupant_name(seat_index)
    if occupant_name != "":
        return occupant_name
    if _lobby_ai_replacement_for_seat(seat_index):
        return "电脑-%d（入座中…）" % (seat_index + 1)
    return ""
```

Use this helper in `_build_lobby_seat_card()` so the empty label is only used when AI replacement is false. In the player refresh path, preserve `is_ai` player names when rebuilding `_lobby_seat_occupants`; do not clear the local AI placeholder before the server response has been applied.

- [ ] **Step 2: Make successful lobby start skip redundant waiting view**

In the successful start response path, call the existing `_show_view("game")`, `NetworkClient.connect_to_game(_game_id, _player_id)`, and initial `get_game_state()` sequence directly. Keep `_show_view("connecting")` only for create/join/reconnect operations that still need a network wait. Preserve failure handling in the lobby and preserve `_trigger_first_tutorial()` only after entering game view.

- [ ] **Step 3: Run focused tests**

```bash
python -m pytest game/tests/test_godot_client_contract.py -k "ai_replacement or lobby_start" -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add godot-client/scripts/main.gd game/tests/test_godot_client_contract.py
git commit -m "fix(godot): show AI seat names and streamline lobby start"
```

### Task 3: Fix mainline page visibility and overlapping controls

**Files:**
- Modify: `godot-client/scripts/mainline/mainline_controller.gd`
- Modify: `godot-client/scenes/main.tscn`
- Test: `game/tests/test_godot_client_contract.py`

**Interfaces:**
- Consumes: `_set_mainline_page(page: String)` and existing button signals.
- Produces: mutually exclusive chapter-list/prepare controls with no overlapping fixed-position nodes.

- [ ] **Step 1: Extend `_set_mainline_page()` to include every prepare control**

Add `ml_prep_complete_btn` to the same `showing_prepare` visibility group as the other preparation buttons. Ensure chapter-list-only controls remain visible and prepare-only controls are hidden when `_main._mainline_page == "chapter_list"`.

- [ ] **Step 2: Make the two same-position controls mutually exclusive in prepare mode**

In `_update_prepare_action_buttons()`, set `ml_prep_complete_btn.visible` to the state intended by the preparation flow, and never leave both `MLPrepCompleteBtn` and `MLPrepRefreshBtn` visible at the same fixed coordinates. If both actions are needed, move them into the existing bottom action row or give each a distinct anchor/offset block in `main.tscn`; retain their existing signal connections.

- [ ] **Step 3: Run focused tests and parse-check the scene**

```bash
python -m pytest game/tests/test_godot_client_contract.py -k "mainline_page" -q
cd godot-client && godot --headless --path . --editor --quit
```

Expected: focused tests PASS; Godot exits without parse errors.

- [ ] **Step 4: Commit**

```bash
git add godot-client/scripts/mainline/mainline_controller.gd godot-client/scenes/main.tscn game/tests/test_godot_client_contract.py
git commit -m "fix(godot): isolate mainline chapter and prepare controls"
```

### Task 4: Reflow saves management sections

**Files:**
- Modify: `godot-client/scenes/main.tscn`
- Modify: `godot-client/scripts/ui/saves_controller.gd`
- Test: `game/tests/test_godot_client_contract.py`

**Interfaces:**
- Consumes: existing `SaveSlotsContainer`, `SaveAutoRow`, `SaveSuspendRow` dynamic renderers.
- Produces: non-overlapping vertical save sections and stable delete-suspend action location.

- [ ] **Step 1: Capture the current layout as a failing geometry test**

Parse the `SavesView/SaveFrame` blocks in the contract test and assert that the manual, auto, suspend and footer areas have monotonic vertical bounds, or assert the presence of a dedicated `SaveContentScroll`/`SaveSections` container with the three sections as children.

- [ ] **Step 2: Move dynamic rows under one vertical content container**

Use a `VBoxContainer`/`ScrollContainer` hierarchy for the title/status, manual slots, auto row, suspend row, and footer. Remove fixed offsets that place section labels over dynamic rows. Keep the existing controller node paths (`$SaveFrame/SaveSlotsContainer`, `$SaveFrame/SaveAutoRow`, `$SaveFrame/SaveSuspendRow`) valid, or update only the corresponding `@onready` paths in the same change.

- [ ] **Step 3: Keep suspend deletion attached to the suspend row**

Verify `_render_suspend_row()` creates the delete/continue controls inside `SaveSuspendRow`; do not route deletion through a manual-slot button or generic game deletion endpoint.

- [ ] **Step 4: Run tests**

```bash
python -m pytest game/tests/test_godot_client_contract.py -k "saves_view" -q
cd godot-client && godot --headless --path . --editor --quit
```

Expected: PASS and no scene parse errors.

- [ ] **Step 5: Commit**

```bash
git add godot-client/scenes/main.tscn godot-client/scripts/ui/saves_controller.gd game/tests/test_godot_client_contract.py
git commit -m "fix(godot): reflow saves management sections"
```

### Task 5: Correct portrait presentation without texture scaling

**Files:**
- Modify: `godot-client/scripts/main.gd`
- Modify: `godot-client/scenes/main.tscn`
- Possibly modify: `godot-client/scripts/ui/menu_theme.gd` only if the existing panel theme cannot express the target frame
- Test: `game/tests/test_godot_client_contract.py`

**Interfaces:**
- Consumes: `_set_unit_info_portrait()`, `HeroPortraitPanel`, existing `TextureRect` setup and hero texture loader.
- Produces: portrait placed inside the red-box target region without changing source texture scale.

- [ ] **Step 1: Identify the target panel from the screenshot and current scene**

Confirm whether the red box corresponds to `GameView/HUD/HeroPortraitPanel` or `DialogPanel/DialogBody/Portrait`. Use the existing node path and screenshot dimensions; do not modify both components by assumption.

- [ ] **Step 2: Write the geometry contract**

Assert the selected panel is anchored to the intended HUD region, has explicit minimum size, and its `TextureRect` uses `STRETCH_KEEP_ASPECT_CENTERED` or an equivalent no-resize mode. Assert no old `InfoPanel` hard-coded portrait offset remains.

- [ ] **Step 3: Adjust only container geometry and clipping**

Set the target panel's anchors/offsets and `clip_contents` as needed. Keep the texture's native dimensions and use centered alignment; if the native portrait exceeds the red box, clip the overflow rather than scaling the texture.

- [ ] **Step 4: Run focused tests and the Godot headless parse check**

```bash
python -m pytest game/tests/test_godot_client_contract.py -k "portrait_panel" -q
cd godot-client && godot --headless --path . --editor --quit
```

Expected: PASS and no parse errors.

- [ ] **Step 5: Commit**

```bash
git add godot-client/scripts/main.gd godot-client/scenes/main.tscn game/tests/test_godot_client_contract.py
# include menu_theme.gd only if it was actually changed
git commit -m "fix(godot): place hero portraits in target frame"
```

### Task 6: Full verification and screenshot comparison

**Files:**
- Modify: none unless verification exposes a regression
- Test: `game/tests/test_godot_client_contract.py`, existing Godot screenshot/flow harness

- [ ] **Step 1: Run the complete Godot contract suite**

```bash
python -m pytest game/tests/test_godot_client_contract.py -q
```

Expected: all tests PASS.

- [ ] **Step 2: Launch the real Godot flow**

Use the repository's existing Godot run/screenshot command or `godot --path godot-client --editor`. Exercise: lobby AI replacement, lobby start, saves view, mainline chapter list/prepare, and a battle with a hero portrait.

- [ ] **Step 3: Compare screenshots against all five issue images**

Verify: AI seat has an AI name, no redundant start waiting screen, save headings do not overlap, chapter controls do not overlap or swallow clicks, and the portrait occupies the red-box region without texture scaling.

- [ ] **Step 4: Run the broader relevant test set**

```bash
python -m pytest game/tests/test_godot_client_contract.py game/tests/test_commanders_ai.py game/tests/test_commanders_integration.py -q
```

Expected: PASS. Report any environment-only Godot launch limitation instead of claiming visual verification.

- [ ] **Step 5: Commit verification notes if needed**

If screenshots or documentation were updated, commit only those artifacts with a focused message; otherwise leave the working tree limited to implementation commits.

## Self-review checklist

- Spec coverage: Tasks 2–5 map one-to-one to the five screenshot issues; Task 1 and Task 6 cover regression and end-to-end verification.
- Placeholder scan: no task depends on an undefined future function; the only conditional item is the already-existing portrait theme file, which is explicitly limited to a demonstrated need.
- Type consistency: callbacks remain `(body, code)`, `_set_mainline_page(page: String)` remains the page interface, and existing node paths are preserved unless the controller paths are updated together.
