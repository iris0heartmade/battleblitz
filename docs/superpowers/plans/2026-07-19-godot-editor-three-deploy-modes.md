# Godot Editor Three Deploy Modes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the Godot map editor into terrain, surface/building, and unit deployment modes, with four-team ownership support for units and owned surface buildings.

**Architecture:** Keep the existing single-character `layout` grid for terrain and building tile type. Add a new optional custom-map field `tile_owners: [{x, y, color}]` for owned buildings; backend save/load validates it and game start maps colors to actual player ids.

**Tech Stack:** Godot 4.7 GDScript scenes/tests, FastAPI/Pydantic editor route, existing SQLAlchemy game start flow, existing headless smoke test.

## Global Constraints

- Godot visible UI text must remain Chinese.
- `tile_owners` uses color ids `red`, `blue`, `green`, `yellow`; no player ids are stored in map JSON.
- Backend remains authoritative during game start by resolving colors to joined players.
- Existing custom maps without `tile_owners` must keep working.
- TDD: write failing tests before production edits.

---

### Task 1: Godot Editor UI And Local Map Shape

**Files:**
- Modify: `godot-client/scenes/main.tscn`
- Modify: `godot-client/scripts/main.gd`
- Test: `godot-client/tools/smoke_test.gd`

**Interfaces:**
- Produces: `_selected_editor_mode() -> String`, returning `terrain`, `surface`, or `unit`.
- Produces: `tile_owners` inside `_editor_map`, as an array of dictionaries with `x`, `y`, `color`.

- [x] **Step 1: Write failing smoke assertions**
- [x] **Step 2: Run smoke test and confirm it fails on missing three-mode/surface owner behavior**
- [x] **Step 3: Implement Godot scene controls and editor mode branching**
- [x] **Step 4: Run smoke test and confirm Godot editor assertions pass**

### Task 2: Backend Custom Map Schema And Game Start Ownership

**Files:**
- Modify: `game/app/routes/editor.py`
- Modify: `game/app/routes/game.py`
- Test: existing backend tests or focused pytest tests

**Interfaces:**
- Consumes: custom map JSON optional field `tile_owners`.
- Produces: saved/loaded custom map JSON retaining `tile_owners`.
- Produces: game-start tile `owner_id` resolved from `tile_owners[].color`.

- [x] **Step 1: Write failing backend tests for saving `tile_owners` and applying ownership at start**
- [x] **Step 2: Run focused pytest and confirm failures**
- [x] **Step 3: Extend Pydantic schema, validation, JSON persistence, and game start application**
- [x] **Step 4: Run focused pytest and confirm pass**

### Task 3: Verification And Docs

**Files:**
- Modify: `godot-client/README.md`
- Modify: `docs/WebUI-vs-GodotClient-差异与计划.md`
- Modify: `docs/参考/Godot客户端后端接口.md`

- [x] **Step 1: Update docs for three deploy modes and `tile_owners`**
- [x] **Step 2: Run `python godot-client/tools/check_chinese_ui.py`**
- [x] **Step 3: Run Godot headless import**
- [x] **Step 4: Run Godot smoke test**
- [x] **Step 5: Run focused backend tests**
- [x] **Step 6: Commit and push**
