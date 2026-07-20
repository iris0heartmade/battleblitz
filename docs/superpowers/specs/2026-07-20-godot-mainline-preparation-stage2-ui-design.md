# Godot Mainline Preparation Stage 2 UI Design

## Goal

Upgrade the Godot mainline preparation center from a text-rich first pass into a tactical RPG preparation UI with concrete selectors, hero detail sheets, equipment warehouse interaction, mercenary allocation controls, shop item selection, and clear hero identity in battle.

## Visual Direction

The layout continues to reference Fire Emblem: Three Houses preparation flow: a compact command hub, character list/detail paper sheet, inventory convoy, class/promotion focus, market stock list, and explicit battle start. Assets stay local to the Godot client; no external art or copied game UI assets are introduced.

## Scope

- Add selector row under preparation tabs:
  - hero selector
  - equipment selector
  - mercenary unit selector
  - mercenary stat selector
  - shop item selector
- Render hero detail as a paper-sheet style text panel with selected hero stats, skills, equipment, promotion options, and inventory context.
- Equipment actions operate on the selected equipment item and selected hero.
- Mercenary allocation operates on selected unit type and selected stat.
- Shop purchase operates on selected shop item.
- Battle map units with `hero_id` display a small hero badge and expose testable hero identity.
- Unit info panel highlights hero name/class when a selected battlefield unit has `hero_id`.

## Constraints

- Preserve Web UI unchanged.
- Preserve existing Godot scene structure and smoke test harness.
- Keep first implementation inside existing `MainlineView` and `UnitNode` rather than introducing multiple new scenes.
- Do not add plugins or new generated art.

## Acceptance Criteria

- Smoke test can find all preparation selector nodes.
- Loading a prepare payload populates hero and equipment selectors.
- Selecting a different hero changes hero detail content.
- Loading shop data populates the shop selector, and purchase action uses the selected item.
- Loading mercenary config populates unit/stat selectors, and allocation action uses selected values.
- UnitNode renders a visible hero badge for data containing `hero_id`.
- Unit info text includes hero identity for battlefield hero units.
