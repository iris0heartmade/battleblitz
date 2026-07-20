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

---

## 现状审计(2026-07-21 同步)

> 本章节由代码审计回填,**不是**原计划的执行步骤。它记录每一项 Task 在当前仓库里的落地情况,以及连带查到的历史计划残项。后续 agent 实施时应**先读本章节**,再决定是否需要按原计划 Task 全做、跳过、还是仅补缺口。

**审计方法**:
- 通读 `docs/superpowers/plans/` 下全部 14 份计划文档
- `git log --oneline -20` + `git diff --stat origin/master..master` 看代码增量
- 对每一个 plan 中点名的关键文件、函数、节点做 `grep` 验证是否存在
- 比对 `main.gd` / `network_client.gd` / `mainline.py` / `smoke_test.gd` / `save.py` 等核心文件的实际行号

### 一、本计划 6 个 Task 的现状

| Task | 计划要求 | 实际落地 | 缺口 |
|---|---|---|---|
| **Task 1** smoke autoload | 改 `smoke_test.gd` 用 `get_node_or_null("/root/GameState")` 取代编译期 singleton 引用 | ❌ **未做**:`smoke_test.gd` 头部 `extends Node`,第 459-472 / 600 行直接用 `GameState.tiles` / `GameState.unit_recruited.connect` 等编译期引用,grep `get_node_or_null.*GameState` 0 命中 | 把所有 `GameState.*` / `NetworkClient.*` / `InputState.*` / `UserSettings.*` 调用前先 `var xxx := get_node_or_null("/root/xxx")`,加 `xxx != null` 守门 |
| **Task 2** sequential chain | 新增 `CAMPAIGN_CHAINS` dict 抽象 + `test_mainline_full_campaign.py` | 🟡 **部分完成**:`_has_cleared_mainline` / `_current_test_mainline_for_user` / `_ensure_test_mainline_unlocked` 已在 `game/app/routes/mainline.py:141-189` 实现,`list_mainlines_endpoint` 已按 user 通关状态过滤,但**仍用 `TEST_MAINLINE_CHAIN` tuple**(line 138 / 165 / 168 / 176 / 809) | 1) 引入 `CAMPAIGN_CHAINS = {"test": (...)}` dict,逻辑改读 dict;2) 新建 `game/tests/test_mainline_full_campaign.py` 覆盖"未通关不可跳关 403" + "全通关后回归末章";3) 决定 production chain 命名空间(plan 里写 `chapter_test_*`,但 chapter_01 已经并入生产链,需要命名协调) |
| **Task 3** prep UX | `_set_mainline_page(page)` + smoke 断言两态互斥 | ✅ **完成**:`main.gd:5612` `_set_mainline_page` 函数完整,`ml_list_container` / `ml_slots_container` / `ml_prep_summary` / `ml_prep_tabs` / `ml_prep_content` / `ml_prep_start_btn` 等 13 个控件已 `showing_prepare` 互斥切换;`smoke_test.gd:233-261` 已有节点存在性断言 | (可选)补"页面切换前后可见性互斥"运行时断言,plan Step 1 要求的是动态断言,现有是静态节点存在性 |
| **Task 4** chapter content | chapter_02_border_flame + chapter_03_crown_shadow + stories | ❌ **完全没做**:`game/mainlines/` 只有 `chapter_01_steel_rebellion.json` + 3 个 test 章节;`game/stories/chapter_01/` 有 intro/battle_01_after/battle_02_after/victory.json;**chapter_02 / chapter_03 全缺**(连测试章节都没有对应的生产版本) | 1) `chapter_02_border_flame.json`:至少 2 battle,map_id 复用 `balanced_2p_15` 或 `balanced_3p_15`,intro/victory story 钩到 `stories/chapter_02/`;2) `chapter_03_crown_shadow.json`:3 battle,可引入 boss 战;3) 对应 stories JSON 文件;4) `test_mainline_loader.py` 加 production 三章节加载测试 |
| **Task 5** AI commentary | `commentary_received` signal + `AiStatusLabel` HUD + `_append_log("战况解说:...")` | ❌ **完全没做**:`network_client.gd:327-328` 显式注释 `# Reserved for future AI commentary. No-op for now.`;`main.gd` grep `AiStatusLabel\|AiStatus\|commentary` 0 命中 | 1) `network_client.gd` 加 `signal commentary_received(payload: Dictionary)`,在 `_dispatch_ws_message` 收到 `commentary.text` 时 `emit`;2) `main.tscn` GameView/HUD 加 `AiStatusLabel`(节点 + onready);3) `main.gd` 连接 `commentary_received` → `_on_commentary_received`,追加到 war report `RichTextLabel`;4) smoke 断言 `AiStatusLabel` 存在 |
| **Task 6** release gate | `docs/路线/项目状态.md` 加 PASS/FAIL + 命令 + 日期 模板 | 🟡 **部分完成**:`godot-client/README.md` 已经文档化 `--headless ... res://tools/smoke_test.tscn` 和 `res://tools/entry_flow_e2e.tscn` 命令(line 95 / 101);但 `docs/路线/项目状态.md` 最后更新停留在 **2026-07-13**,顶部还写"Current Branch: feat/p2.6-data-driven-initial-units" + "Latest pushed commits: b0df415..." 这种陈旧描述 | 1) 跑 `pytest -q` / `godot --headless --quit` / `smoke_test.tscn` / `entry_flow_e2e.tscn` 四件套,记录实际结果;2) 改写 `项目状态.md` 顶部,加入 release checklist 模板(后端 pytest / Godot startup / Godot smoke / Entry-flow e2e 各自的 PASS/FAIL + 命令 + 日期) |

### 二、历史计划的细粒度残项

为了避免重复盘点,把这次顺手查到的其他 13 份计划残项也一并列出,按计划日期排序:

#### 2026-07-10 commander-co-power(95%)
- 残项 1: "deeper AI commander decision tuning"(plan 自陈)
- 残项 2: "shared combat resolver cleanup"(plan 自陈)
- 残项 3: `test_commanders_e2e.py` 仍是单回合 lifecycle 测试,缺多玩家多回合完整 e2e

#### 2026-07-13 save-design-v2(~70%)
- ✅ 端点全部在 `game/app/routes/save.py`:`GET /saves`(117)、`POST /saves/save`(140)、`POST /saves/load`(167)、`POST /saves/load_suspend`(212)、`POST /saves/erase`(305)、`POST /games/{game_id}/suspend`(340)
- ✅ `test_save_api.py` + `test_save_resume_fixes.py` 存在
- ❌ plan 自陈 "Suspend 不污染 hero_campaign_states" 测试守门 + "Save slot 满 3 个" 测试**无专门文件**(可能需要补 `test_save_invariants.py`)
- ❌ Save slot UI 弹窗 + COPY 功能未做(plan §3 标"不在范围",可接受)
- ❌ 7 天 cron 清理未做(plan §3 标"不在范围",可接受)

#### 2026-07-13 interrupt-save-design v1(0%)
- ⚪ **已被 2026-07-13 save-design-v2 取代**,整份可视为 superseded,不必实施

#### 2026-07-13 hero-mercenary-dual-track(100%)
- ✅ 6 task 全部落地(commit `9b76ec5`),并入后续 godot-hero-backend-coordination plan
- 残项: "Hero 域与 command 系统整合" 是 plan Self-Review 列的 p3.0 commander 通过 `is_commander` class var 复用 hero,无 domain-level 集成 spec — 属远期

#### 2026-07-14 godot-map-presentation-48px(100%)
- ✅ commit `52a0129`,smoke 61 passed

#### 2026-07-14 godot-map-presentation-handoff(交付文档)
- ⚪ 48px 原生美术资源因 Codex 图像 endpoint 失败留 TODO — 属外部生成,可接受

#### 2026-07-19 godot-client-next-work(30% 落地)

| Task | 状态 | 证据 |
|---|---|---|
| Task 1 entry blockers | 🟡 部分 | 6 个 handlers 全部存在(`_on_start_game_response` 841、`_on_lobby_create_response` 4174、`_on_lobby_join_response` 4191、`_on_lobby_start_response` 5447、`_on_mainline_start_response` 6503、`_on_mainline_dialogue_response` 6570);**缺** plan Step 5 的 regression assertions(`mainline_start_reaches_game_view=true` 等) |
| Task 2 remove solo free-play | ✅ | `smoke_test.gd:179` 显式断言 `Menu/CenterContainer/GroupRow/SoloCard/FreePlayButton == null` |
| Task 3 server-authoritative forecast | 🟡 部分 | 后端 endpoint 在 `actions.py:402`,`AttackForecastOut` schema 在 `schemas.py:438`,`network_client.gd:508` 有 `forecast_attack()`,`main.gd:6948` 调用;**缺** `test_godot_forecast_api.py` 专门测试文件(可能合入 `test_godot_client_contract.py`) |
| Task 4 editor Fill/Line/Select | 🟡 部分 | undo/redo ✅(`_editor_undo_stack` 在 `main.gd:256` + 完整 push/pop/clear 链路 3455-3511);Fill/Line/Select 工具 ❌(grep `editor_fill\|fill_flood\|bresenham\|flood_fill\|paint_line\|select_tool` 0 命中) |
| Task 5 Help/Reference panel | ❌ | `HelpPanel` / `HelpButton` grep 0 命中 |
| Task 6 AI commentary UI | ❌ | 与 07-21 Task 5 重叠,等同 |
| Task 7 Network diagnostics HUD | ❌ | `connection_status` / `last_seq` / `last_pong` / `safety_poll` grep 0 命中;`reconnect_button` + `ws_reconnecting` 信号已有但属"重连基础设施",不是"诊断 HUD" |
| Task 8 release polish | ❌ | `unit_node.gd:81` 还有 `Image.load(path)` 直接调用注释;`tile_set_builder.gd:284` 还在用 `Image.load_from_file(path)`;BGM crossfade grep 0 命中 |

#### 2026-07-19 godot-editor-three-deploy-modes(100%)
- ✅ 所有 [x],commit 已落地

#### 2026-07-20 godot-hero-backend-coordination(100%)
- ✅ commits `df2ad26` + `2af3e42`

#### 2026-07-20 godot-mainline-preparation-ui(80%)

| Task | 状态 | 证据 |
|---|---|---|
| Task 1 prep nodes + smoke | ✅ | `main.gd:180-196` 全部 `ml_prep_*` @onready 声明;`smoke_test.gd:233-261` 12 个节点存在性断言 |
| Task 2 state + render | ✅ | `_mainline_prepare_tab` (358) / `_selected_prepare_hero_id` (359) / `_render_mainline_prepare` (5852) / `_build_prepare_heroes_text` (6154) / `_build_prepare_roster_text` (6208) / `_build_prepare_equipment_text` (6228) |
| Task 3 backend actions | 🟡 部分 | 找到 3/6 回调:`_on_prepare_start_pressed` (5830) / `_on_prepare_refresh_pressed` (5842) / `_on_prepare_mercenary_response` (6324);**缺** `_on_prepare_promote_pressed` / `_on_prepare_equip_pressed` / `_on_prepare_shop_refresh_response` |
| Task 4 verification | ✅ | commit `544f407` |

#### 2026-07-20 godot-mainline-preparation-stage2-ui(90%)

| Task | 状态 | 证据 |
|---|---|---|
| Task 1 smoke selector + hero badge | ✅ | `smoke_test.gd:253-261` 5 个 selector 节点 + line 354 `has_hero_badge()` 断言 |
| Task 2 scene + state | ✅ | `main.gd:187-191` 5 个 selector @onready |
| Task 3 actions use selected values | ✅(推断) | 与 Task 2 selectors 配合 |
| Task 4 hero badge | ✅ | `unit_node.gd:60-62` `_hero_badge` + `_hero_badge_label` 字段;line 215-230 完整绘制逻辑 |
| Task 5 verification | ✅ | commit `6dc8bea` |

### 三、按"对玩家可玩性 + 实施依赖"排序的待办清单

#### 🔴 高优先级(直接卡玩家体验,且不依赖其他 Task)

1. **07-21 Task 4** — 加 chapter_02 / chapter_03 + stories
   - 玩家进入主线后立刻能感受到"游戏不只 1 章"
   - 无代码依赖,纯数据 + JSON
   - 关键文件:`game/mainlines/chapter_02_border_flame.json`、`game/mainlines/chapter_03_crown_shadow.json`、`game/stories/chapter_02/{intro,victory}.json`、`game/stories/chapter_03/{intro,victory}.json`
   - 验证:`pytest tests/test_mainline_loader.py -q`

2. **07-21 Task 5** — AI commentary signal + HUD
   - 玩家战斗时能看到 AI 思考状态 / 战况解说
   - 依赖 `network_client.gd` 改 1 处 + `main.gd` 加 onready + `main.tscn` 加节点
   - 关键文件:`godot-client/scripts/autoload/network_client.gd`(line 327-328)、`godot-client/scripts/main.gd`、`godot-client/scenes/main.tscn`
   - 验证:`smoke_test.gd` 加 `AiStatusLabel` 断言;`godot --headless ... res://tools/smoke_test.tscn` 通过

3. **07-21 Task 6** — release gate 文档化
   - 把 release 流程固化成 4 条 PASS/FAIL 记录,后续不会"忘跑哪一步"
   - 关键文件:`docs/路线/项目状态.md`(顶部重写 + 加 checklist 章节)
   - 验证:运行 4 条命令各一次,把日期 + 结果填进表格

#### 🟡 中优先级(基础设施,被多个 Task 依赖)

4. **07-21 Task 2** — sequential chain 抽象 + campaign 测试
   - 不补这块,后续 chapter_02 / chapter_03 没法"按存档证据顺序解锁"
   - 关键文件:`game/app/routes/mainline.py`(line 138 改 `CAMPAIGN_CHAINS` dict)、`game/tests/test_mainline_full_campaign.py`(新建)
   - 验证:`pytest tests/test_test_mainline_chapters.py tests/test_mainline_full_campaign.py -q`

5. **07-21 Task 1** — smoke autoload 修复
   - 修复后,smoke 在 autoload 缺失或加载顺序异常时不会硬崩;这是后续补 HUD / commentary smoke 断言的**前置依赖**
   - 关键文件:`godot-client/tools/smoke_test.gd`(line 459-472 / 600 改 `get_node_or_null` 模式)
   - 验证:`godot --headless ... res://tools/smoke_test.tscn` 跑通

6. **07-19 Task 4 残项** — editor Fill/Line/Select 工具
   - undo/redo 已做,补剩下三个工具
   - 关键文件:`godot-client/scripts/main.gd`、`godot-client/scenes/main.tscn`、`godot-client/tools/smoke_test.gd`
   - 验证:smoke 加 Fill/Line/Select 工具选项断言

7. **07-19 Task 3 残项** — `test_godot_forecast_api.py`
   - 后端 + 客户端都通了,补一份专门测试守门,免得未来回归
   - 关键文件:`game/tests/test_godot_forecast_api.py`(新建)
   - 验证:`pytest tests/test_godot_forecast_api.py -v`

#### 🟢 低优先级(可选增强,不影响主流程)

8. **07-19 Task 1 残项** — `e2e_one_game.gd` 加回归断言
9. **07-20 prep UI Task 3 残项** — `_on_prepare_promote_pressed` / `_on_prepare_equip_pressed` / `_on_prepare_shop_refresh_response` 三个回调补全
10. **07-13 save-v2 残项** — "Suspend 不污染 hero_campaign_states" + "3 槽满" 专门测试
11. **07-10 commander-co-power 残项** — deeper AI decision tuning + shared combat resolver cleanup
12. **07-19 Task 5** — Help/Reference 面板
13. **07-19 Task 7** — Network diagnostics HUD
14. **07-19 Task 8** — Release polish asset loading(`Image.load` → import texture)+ BGM crossfade

### 四、建议执行顺序

如果由单 agent 顺序执行,推荐路径(兼顾依赖关系 + 用户可感知价值):

```
Step A: 07-21 Task 4 (内容,无依赖,1-2h)
Step B: 07-21 Task 1 (smoke 修复,作为后续 smoke 断言的安全网,30min)
Step C: 07-21 Task 2 (chain 抽象 + 测试,1h)
Step D: 07-21 Task 5 (AI commentary,半天,可在 C 完成后并行)
Step E: 07-19 Task 4 残项 (Fill/Line/Select,2h)
Step F: 07-21 Task 6 (release gate 文档化,30min,所有代码完成后做)
Step G: 07-19 Task 3 残项 (forecast 专门测试,30min)
```

每完成一步,跑对应验证命令并把 PASS/FAIL 写入 `docs/路线/项目状态.md`(即 Task 6 的产出),形成"边开发边记录"的循环,避免最后一天才补文档。

### 五、不能动的全局约束(继承自原计划 + 项目历史)

- 不要把已废弃的 solo free-play 入口复活作为主 UI 路径(`smoke_test.gd:179` 已经守住)
- 主线测试章节必须按存档证据顺序解锁(chapter_01_steel_rebellion → 待 chapter_02 → 待 chapter_03)
- Godot UI 文本保持中文
- 后端对 seat 唯一性 / chapter gate / battle action / save 写入 / reward 持久化保持权威
- 测试一律加到现有 `game/tests/` 和 `godot-client/tools/smoke_test.gd`,不另起 harness
- **不要碰**那个无关的未跟踪 branch report 文件(`branch-diff-report_godot-map-port_vs_hero-mercenary-dual-track.md`)
