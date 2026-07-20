# Godot Mainline Preparation Stage 2 UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add concrete Godot selectors and hero battlefield presentation to the existing mainline preparation center.

**Architecture:** Extend `MainlineView` with one selector row and wire it from `main.gd`; update `UnitNode` with a small hero badge. Keep the UI data-driven from existing prepare/shop/mercenary payloads.

**Tech Stack:** Godot 4.7 GDScript, existing smoke test, pytest static contract tests.

## Global Constraints

- Keep Web UI untouched.
- Use existing Godot assets under `godot-client/assets`.
- Write smoke/contract tests before production code.
- Preserve existing mainline preparation start flow.

---

### Task 1: Selector Nodes and Red Tests

- [ ] Extend `godot-client/tools/smoke_test.gd` with failing assertions for selector nodes and hero badge behavior.
- [ ] Run Godot smoke and confirm the new assertions fail for missing nodes/methods.

### Task 2: Scene and State

- [ ] Add selector row nodes to `godot-client/scenes/main.tscn`.
- [ ] Add onready references and selection state to `godot-client/scripts/main.gd`.
- [ ] Populate selectors from prepare, shop, and mercenary payloads.

### Task 3: Actions Use Selected Values

- [ ] Change hero, equipment, shop, and mercenary actions to use selected OptionButton values.
- [ ] Update rendering to reflect selected hero/item/unit/stat.

### Task 4: Battle Hero Presentation

- [ ] Add hero badge rendering to `godot-client/scripts/board/unit_node.gd`.
- [ ] Add hero identity to `main.gd` unit info text.

### Task 5: Verification and Commit

- [ ] Run Godot smoke.
- [ ] Run pytest contract tests.
- [ ] Run compileall, diff check, conflict scan.
- [ ] Commit with `feat: add godot preparation selectors and hero battle cues`.
