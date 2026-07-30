# Unit Portraits Transparent Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add generic unit portrait assets and make the in-game portrait area transparent and borderless.

**Architecture:** Keep board sprites separate from large portraits. Heroes continue to use `assets/heroes/portrait_<hero_id>.png`; non-hero units use `assets/unit_portraits/portrait_<unit_type>.png`. The existing Godot portrait slot becomes a generic selected-unit portrait slot with no visible frame.

**Tech Stack:** Godot GDScript, PNG assets, Python static tests for client contract checks.

## Global Constraints

- Generated unit portraits are `800x1400` PNGs.
- Portraits must not show visible eyes for non-hero NPC units.
- T2 unit portraits use richer armor, cloth layers, lighting, and pose detail than T1 units.
- Do not overwrite existing classic board sprites.

---

### Task 1: Selected Unit Portrait Path Resolution

**Files:**
- Modify: `godot-client/scripts/main.gd`
- Test: `game/tests/test_godot_unit_portrait_paths.py`

**Interfaces:**
- Produces: `_unit_portrait_path_for(unit: Dictionary) -> String`
- Consumes: selected unit dictionaries containing `hero_id` and `unit_type`

- [ ] Add a failing static test proving hero and generic unit portrait paths are both supported.
- [ ] Run the targeted test and confirm it fails before implementation.
- [ ] Implement `_unit_portrait_path_for` and update `_set_unit_info_portrait` to accept a unit dictionary.
- [ ] Run the targeted test and confirm it passes.

### Task 2: Transparent Borderless Portrait Slot

**Files:**
- Modify: `godot-client/scripts/main.gd`
- Modify: `game/app/web/style.css`
- Test: `game/tests/test_godot_unit_portrait_paths.py`

**Interfaces:**
- Produces: borderless transparent selected-unit portrait panel styling.

- [ ] Add a failing static test for transparent panel styling in Godot.
- [ ] Remove Godot panel background and border styling for the selected-unit portrait slot.
- [ ] Remove Web dialog portrait card chrome while preserving layout.
- [ ] Run the targeted test and confirm it passes.

### Task 3: Unit Portrait Assets

**Files:**
- Create: `godot-client/assets/unit_portraits/portrait_<unit_type>.png`
- Create: `game/app/web/assets/unit_portraits/portrait_<unit_type>.png`
- Modify: `godot-client/CHANGELOG.md`
- Modify: `docs/维护/2026-07-28-unit-portraits-transparent-panel.md`

**Interfaces:**
- Consumes: `_unit_portrait_path_for` from Task 1.
- Produces: project-local PNG assets for every current unit type.

- [ ] Generate portraits for all 15 registered unit types with hidden eyes and tier-aware detail.
- [ ] Save PNGs into Godot and Web asset directories.
- [ ] Validate image dimensions and alpha channels.
- [ ] Update changelog and maintenance note.
