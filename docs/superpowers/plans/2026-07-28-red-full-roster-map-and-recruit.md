# Red Full Roster Map And Recruit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 4-player free-mode map where red starts with every registered unit type, and make every registered unit recruitable from barracks.

**Architecture:** Add a data-driven map JSON under `game/maps`, then keep recruitment availability synchronized through backend `RECRUIT_COST`, Web `RECRUIT_UNIT_TYPES`, and Godot `_RECRUIT_OPTIONS`/`Config.RECRUIT_COST`. Use regression tests that compare map and UI lists against the backend unit registry.

**Tech Stack:** Python/FastAPI backend, JSON map presets, browser JavaScript UI, Godot GDScript client, pytest.

## Global Constraints

- Preserve existing map preset loading conventions.
- Do not change unit stats or class registration.
- Keep red full-roster units off the HQ tile so free-mode commander spawning does not remove one.
- Keep blue, green, and yellow to one HQ placeholder each.

---

### Task 1: Map Preset

**Files:**
- Create: `game/maps/red_full_roster_4p_20.json`
- Modify: `game/tests/test_data_driven_initial_units.py`

**Interfaces:**
- Consumes: `app.game_logic.MAP_PRESETS`, `app.classes.units.type_ids()`
- Produces: map preset id `red_full_roster_4p_20`

- [x] Write failing tests for map existence, 20x20 size, four-player capacity, red full roster, non-red single HQ placeholders, and red-side economy tiles.
- [x] Run the focused map tests and observe failure because the preset does not exist.
- [x] Add the map JSON with 20 rows of 20 cells and 18 initial units.
- [x] Re-run focused map tests and fix row width errors.

### Task 2: Barracks Recruit Roster

**Files:**
- Modify: `game/app/config.py`
- Modify: `game/app/web/app.js`
- Modify: `godot-client/scripts/main.gd`
- Modify: `godot-client/scripts/autoload/config.gd`
- Create: `game/tests/test_recruit_roster_sync.py`

**Interfaces:**
- Consumes: `app.classes.units.type_ids()`, backend `RECRUIT_COST`
- Produces: synchronized recruit availability for backend, Web, and Godot

- [x] Write failing tests asserting backend `RECRUIT_COST` covers every registered unit type.
- [x] Write failing tests asserting Web and Godot recruit lists contain every backend recruit type.
- [x] Expand backend recruit costs for new unit types.
- [x] Expand Web and Godot recruit lists.
- [x] Change Godot recruit button labels to reuse `_unit_type_cn(unit_type)`.
- [x] Re-run focused recruit roster tests.

### Task 3: Documentation And Verification

**Files:**
- Modify: `godot-client/CHANGELOG.md`
- Create: `docs/维护/2026-07-28-red-full-roster-map-and-recruit.md`

**Interfaces:**
- Produces: maintenance record and changelog entry

- [x] Add changelog bullets for the new map and recruit roster expansion.
- [x] Add maintenance record describing goals, files, and verification points.
- [x] Run targeted pytest coverage.
- [x] Run Godot contract verification and Godot headless smoke via `res://tools/smoke_test.tscn`.
