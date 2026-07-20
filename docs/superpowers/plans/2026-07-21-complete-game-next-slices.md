# Complete Game Next Slices Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current BattleBlitz Godot + FastAPI build into a more complete, reliable tactics game loop with sequential mainline progression, stronger preparation UX, stable automation, and release-ready client/backend checks.

**Architecture:** Keep the backend authoritative for progression, combat, saves, AI, and map contracts. Keep the Godot client as the primary playable UI, using focused vertical slices that each add tests first, implement one visible behavior, and end with a Godot or backend verification command.

**Tech Stack:** FastAPI, SQLAlchemy async, pytest/httpx, Godot 4.7 GDScript, existing `NetworkClient` REST/WS layer, existing Godot smoke/e2e test scenes.

## Global Constraints

- Do not reintroduce the removed solo free-play entry as a primary UI route.
- Mainline test chapters must unlock sequentially through formal save evidence: chapter 1, then chapter 2, then chapter 3.
- Godot UI text should stay Chinese for user-facing controls.
- Backend remains authoritative for seat uniqueness, chapter gates, battle actions, save mutation, and reward persistence.
- Prefer adding focused tests to existing `game/tests/` and `godot-client/tools/smoke_test.gd` instead of creating a parallel test harness.
- Do not touch the unrelated untracked branch report file.

---

## File Structure

- `godot-client/tools/smoke_test.gd`
  - Fix the headless autoload entry issue and keep UI shape assertions for lobby, mainline, editor, saves, and combat panels.
- `godot-client/tools/smoke_test.tscn`
  - Use this scene as the canonical Godot smoke entry instead of direct `--script` execution when autoloads are required.
- `godot-client/tools/entry_flow_e2e.gd`
  - Verify playable entry paths against a running backend: mainline chapter start and online lobby create/start.
- `godot-client/scripts/main.gd`
  - Implement the remaining Godot UX slices: mainline chapter page polish, preparation page polish, battle presentation, diagnostics, and help/reference panels.
- `godot-client/scripts/autoload/network_client.gd`
  - Add or expose REST/WS diagnostics and any missing backend route wrapper needed by the UX slices.
- `game/app/routes/mainline.py`
  - Extend mainline chain behavior when real chapters are added beyond the temporary test chain.
- `game/mainlines/*.json`
  - Add production mainline chapters with battle ids, story hooks, required classes, rewards, and preparation metadata.
- `game/stories/**`
  - Add story scenes used by those chapters.
- `game/tests/test_test_mainline_chapters.py`
  - Keep sequential unlock regression coverage as chapters expand.
- `game/tests/test_mainline_full_campaign.py`
  - Create when the production chapter chain is added; verifies start, clear, reward, save, next unlock.
- `docs/路线/项目状态.md`
  - Update after each completed slice with the current playable status.

---

### Task 1: Stabilize Godot Headless Automation

**Files:**
- Modify: `godot-client/tools/smoke_test.gd`
- Modify: `godot-client/README.md`

**Interfaces:**
- Consumes: Godot autoloads `GameState`, `InputState`, `NetworkClient`, `UserSettings`.
- Produces: a documented smoke command that compiles and runs through `smoke_test.tscn`.

- [ ] **Step 1: Run the scene-based smoke command and capture the real failure**

Run:

```powershell
& "D:\Python\godot\Godot_v4.7-stable_win64_console.exe" --headless --path godot-client res://tools/smoke_test.tscn
```

Expected: either the smoke test runs and reports assertion results, or it fails at the first compile/runtime blocker.

- [ ] **Step 2: If direct autoload identifiers still fail, replace compile-time singleton references in `smoke_test.gd` with root lookups**

Use this pattern at the top of checks that currently reference autoload names directly:

```gdscript
var game_state := get_node_or_null("/root/GameState")
var input_state := get_node_or_null("/root/InputState")
var network_client := get_node_or_null("/root/NetworkClient")
var user_settings := get_node_or_null("/root/UserSettings")
_assert_true("GameState autoload", game_state != null, "GameState autoload not registered")
```

Then replace local direct references inside that test block, for example:

```gdscript
var prev_tiles: Array = game_state.tiles
game_state.tiles = mock_tiles
```

- [ ] **Step 3: Re-run smoke and keep only actionable failures**

Run:

```powershell
& "D:\Python\godot\Godot_v4.7-stable_win64_console.exe" --headless --path godot-client res://tools/smoke_test.tscn
```

Expected: no `Identifier not found: GameState` compile error. Any remaining failures should name real UI or behavior gaps.

- [ ] **Step 4: Update `godot-client/README.md`**

Document the canonical command:

```markdown
"<godot_exe>" --headless --path godot-client res://tools/smoke_test.tscn
```

- [ ] **Step 5: Commit**

```powershell
git add godot-client/tools/smoke_test.gd godot-client/README.md
git commit -m "test: stabilize godot smoke autoload entry"
```

---

### Task 2: Promote Sequential Mainline From Test Chain To Campaign Chain

**Files:**
- Modify: `game/app/routes/mainline.py`
- Create: `game/tests/test_mainline_full_campaign.py`
- Modify: `game/mainlines/*.json`

**Interfaces:**
- Consumes: `GameSaveSlot.user_name`, `GameSaveSlot.mainline_id`, `GameSaveSlot.chapter_index`.
- Produces: `GET /mainlines?user_name=...` returns only the current campaign chapter for configured chains.

- [ ] **Step 1: Write campaign chain tests**

Create `game/tests/test_mainline_full_campaign.py`:

```python
import pytest

pytestmark = pytest.mark.asyncio


async def test_campaign_chain_starts_at_first_chapter(client):
    await client.post("/profiles", json={"user_name": "campaigner"})
    r = await client.get("/mainlines", params={"user_name": "campaigner"})
    assert r.status_code == 200
    ids = [item["id"] for item in r.json()]
    assert "chapter_test_01" in ids
    assert "chapter_test_02" not in ids


async def test_locked_campaign_chapter_rejects_direct_start(client):
    await client.post("/profiles", json={"user_name": "campaigner"})
    r = await client.post(
        "/mainlines/chapter_test_02/start",
        json={"user_name": "campaigner", "skip_intro": True},
    )
    assert r.status_code == 403
```

- [ ] **Step 2: Extract chain configuration from hard-coded temporary ids**

In `game/app/routes/mainline.py`, replace the fixed temporary tuple with a helper that can later read metadata:

```python
CAMPAIGN_CHAINS = {
    "test": ("chapter_test_01", "chapter_test_02", "chapter_test_03"),
}
```

Keep `TEST_MAINLINE_CHAIN` as an alias only if existing tests still import or assert it.

- [ ] **Step 3: Run targeted backend tests**

Run:

```powershell
cd game
..\game\venv\Scripts\python.exe -m pytest tests/test_test_mainline_chapters.py tests/test_mainline_full_campaign.py -q
```

Expected: all campaign chain tests pass.

- [ ] **Step 4: Commit**

```powershell
git add game/app/routes/mainline.py game/tests/test_mainline_full_campaign.py game/mainlines
git commit -m "feat: generalize sequential mainline campaign gates"
```

---

### Task 3: Make Mainline Preparation Feel Like A Real Strategy Screen

**Files:**
- Modify: `godot-client/scripts/main.gd`
- Modify: `godot-client/tools/smoke_test.gd`

**Interfaces:**
- Consumes: existing `_mainline_prepare_payload`, hero list, inventory, shop, mercenary, commander state.
- Produces: two-page mainline flow: chapter page -> preparation page -> battle.

- [ ] **Step 1: Add smoke assertions for page separation**

In `smoke_test.gd`, after invoking `_on_mainline_pressed`, assert list controls are visible and preparation controls are hidden. After `_on_mainline_prepare_response`, assert the inverse:

```gdscript
_assert_true("Mainline chapter list visible before prepare", main_check.get_node("MainlineView/MainlineFrame/MainlineList").visible, "chapter list should be visible before preparation")
_assert_true("Mainline prep content hidden before prepare", not main_check.get_node("MainlineView/MainlineFrame/PrepContent").visible, "preparation content should be hidden before selecting a chapter")
```

- [ ] **Step 2: Polish preparation page controls**

In `main.gd`, keep the existing `_set_mainline_page(page: String)` entry point and make these states explicit:

```gdscript
func _set_mainline_page(page: String) -> void:
	_mainline_page = page
	var showing_prepare := page == "prepare"
	_set_node_visible(ml_list_container, not showing_prepare)
	_set_node_visible(ml_slots_container, not showing_prepare)
	_set_node_visible(ml_prep_summary, showing_prepare)
	_set_node_visible(ml_prep_tabs, showing_prepare)
	_set_node_visible(ml_prep_content, showing_prepare)
	_set_node_visible(ml_prep_start_btn, showing_prepare)
```

- [ ] **Step 3: Verify with Godot headless startup and smoke**

Run:

```powershell
& "D:\Python\godot\Godot_v4.7-stable_win64_console.exe" --headless --path godot-client --quit
& "D:\Python\godot\Godot_v4.7-stable_win64_console.exe" --headless --path godot-client res://tools/smoke_test.tscn
```

Expected: startup exits 0, smoke reaches preparation assertions.

- [ ] **Step 4: Commit**

```powershell
git add godot-client/scripts/main.gd godot-client/tools/smoke_test.gd
git commit -m "ui: polish mainline preparation page flow"
```

---

### Task 4: Add Real Chapter Content Loop

**Files:**
- Create: `game/mainlines/chapter_02_*.json`
- Create: `game/mainlines/chapter_03_*.json`
- Create: `game/stories/chapter_02/*.json`
- Create: `game/stories/chapter_03/*.json`
- Modify: `game/tests/test_mainline_full_campaign.py`

**Interfaces:**
- Consumes: existing mainline loader schema and `/mainlines/{id}/start`, `/advance`, `/next-battle`.
- Produces: at least three production-feeling chapters with intro, battle, result, reward, and next unlock.

- [ ] **Step 1: Add loader tests for all production chapter files**

```python
def test_production_mainlines_load():
    from app.mainline import load_mainline

    for mainline_id in [
        "chapter_01_steel_rebellion",
        "chapter_02_border_flame",
        "chapter_03_crown_shadow",
    ]:
        ml = load_mainline(mainline_id)
        assert ml.id == mainline_id
        assert len(ml.battles) >= 1
        assert ml.title
```

- [ ] **Step 2: Create chapter JSON files**

Each chapter should include:

```json
{
  "id": "chapter_02_border_flame",
  "title": "第二章 边境烽火",
  "synopsis": "敌军推进至边境要塞，玩家需要守住补给线。",
  "battles": [
    {
      "id": "battle_01",
      "map_id": "balanced_2p_15",
      "intro_story": "chapter_02/intro",
      "victory_story": "chapter_02/victory"
    }
  ]
}
```

- [ ] **Step 3: Create story JSON files**

Use the existing story schema from `game/stories/chapter_01` and keep each scene short enough to read before battle.

- [ ] **Step 4: Run loader and mainline tests**

```powershell
cd game
..\game\venv\Scripts\python.exe -m pytest tests/test_mainline_loader.py tests/test_mainline_full_campaign.py -q
```

Expected: all new chapter files load and campaign tests pass.

- [ ] **Step 5: Commit**

```powershell
git add game/mainlines game/stories game/tests/test_mainline_full_campaign.py
git commit -m "content: add next mainline campaign chapters"
```

---

### Task 5: Improve Battle Feedback And AI Readability

**Files:**
- Modify: `godot-client/scripts/main.gd`
- Modify: `godot-client/scripts/autoload/network_client.gd`
- Modify: `godot-client/tools/smoke_test.gd`

**Interfaces:**
- Consumes: existing action log, combat forecast, `ai_thinking`, and future `commentary.text` WS events.
- Produces: visible AI state, clearer combat result feedback, and optional commentary panel.

- [ ] **Step 1: Add smoke checks for AI state UI**

Assert the battle HUD exposes a visible node for AI thinking or commentary:

```gdscript
_assert_true("Battle HUD exposes AI status", main_check.get_node_or_null("GameView/HUD/AiStatusLabel") != null, "AI turns should have a visible status label")
```

- [ ] **Step 2: Wire `commentary.text` through `NetworkClient`**

Add a signal:

```gdscript
signal commentary_received(payload: Dictionary)
```

When a WS envelope type is `commentary.text`, emit:

```gdscript
commentary_received.emit(payload)
```

- [ ] **Step 3: Render commentary in the war report/action log area**

Append a concise line:

```gdscript
_append_log("战况解说：%s" % str(payload.get("text", "")))
```

- [ ] **Step 4: Verify**

```powershell
& "D:\Python\godot\Godot_v4.7-stable_win64_console.exe" --headless --path godot-client res://tools/smoke_test.tscn
```

Expected: smoke passes the new AI status/commentary assertions.

- [ ] **Step 5: Commit**

```powershell
git add godot-client/scripts/main.gd godot-client/scripts/autoload/network_client.gd godot-client/tools/smoke_test.gd
git commit -m "ui: improve battle ai feedback"
```

---

### Task 6: Release Readiness Gate

**Files:**
- Modify: `docs/路线/项目状态.md`
- Modify: `godot-client/README.md`
- Modify: `.github/workflows/*` only if workflows already exist.

**Interfaces:**
- Consumes: backend pytest, Godot headless startup, Godot smoke, entry-flow e2e.
- Produces: a repeatable release checklist for local and CI verification.

- [ ] **Step 1: Run backend target suite**

```powershell
cd game
..\game\venv\Scripts\python.exe -m pytest -q
```

Expected: the backend suite passes or failures are documented with exact failing tests.

- [ ] **Step 2: Run Godot startup and smoke**

```powershell
& "D:\Python\godot\Godot_v4.7-stable_win64_console.exe" --headless --path godot-client --quit
& "D:\Python\godot\Godot_v4.7-stable_win64_console.exe" --headless --path godot-client res://tools/smoke_test.tscn
```

Expected: both commands exit 0.

- [ ] **Step 3: Run entry-flow e2e with backend running**

Start backend:

```powershell
cd game
..\game\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another shell:

```powershell
& "D:\Python\godot\Godot_v4.7-stable_win64_console.exe" --headless --path godot-client res://tools/entry_flow_e2e.tscn
```

Expected: both mainline and lobby flows enter `GameView` with a populated `GameState`.

- [ ] **Step 4: Update status docs**

Record:

```markdown
- Backend pytest: PASS/FAIL with command and date.
- Godot startup: PASS/FAIL with command and date.
- Godot smoke: PASS/FAIL with command and date.
- Entry-flow e2e: PASS/FAIL with command and date.
```

- [ ] **Step 5: Commit**

```powershell
git add docs/路线/项目状态.md godot-client/README.md
git commit -m "docs: add release readiness checklist"
```

---

## Execution Order

1. Task 1: Stabilize Godot Headless Automation.
2. Task 2: Promote Sequential Mainline From Test Chain To Campaign Chain.
3. Task 3: Make Mainline Preparation Feel Like A Real Strategy Screen.
4. Task 4: Add Real Chapter Content Loop.
5. Task 5: Improve Battle Feedback And AI Readability.
6. Task 6: Release Readiness Gate.

## Self-Review

- Spec coverage: covers current client/backend checks, sequential mainline progression, preparation UX, richer chapter content, AI/battle readability, and release verification.
- Placeholder scan: clear.
- Type consistency: referenced Godot methods and backend route names match the current project conventions observed in `main.gd`, `network_client.gd`, and `mainline.py`.
