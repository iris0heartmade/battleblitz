# Godot 48px Map Presentation Handoff

- Date: 2026-07-14
- Branch: `godot-map-port`
- Scope: Godot frontend only; no backend changes

## What Landed

The 48px map-presentation baseline is already implemented in commit `52a0129`.
This establishes the structural frontend foundation for BattleBlitz's tactics
map rendering without changing Python backend code or map JSON contracts.

Delivered baseline:

- `MapMetrics` centralizes the 48x48 board scale and coordinate math.
- `MapTheme` routes terrain and subtype data into layer-aware rendering logic.
- `Board` now coordinates a dedicated scene structure:
  - `GroundLayer`
  - `StructureLayer`
  - `DecorLayer`
  - `HighlightLayer`
  - `UnitLayer`
  - `EffectsLayer`
  - `BoardCamera`
- `MapLoader` reads existing `game/maps/*.json` and writes to the new layered
  presentation structure.
- Static unit presenters are spawned from `initial_units`.
- Camera fit and board bounds are separated into `board_camera.gd`.
- Headless smoke test coverage was extended for metrics, layers, units, and
  camera behavior.

## Verification Evidence

The structural baseline was verified with the Godot headless smoke test:

```powershell
"D:/PyCharm Community Edition 2024.3.3/PycharmProjects/Godot_v4.7-stable_win64/Godot_v4.7-stable_win64.exe" --headless --scene res://tools/smoke_test.tscn --path godot-client
```

Expected passing signal from the successful run:

```text
Passed: 61   Failed: 0
PASS
```

## What Was Added Today For Handoff

Two supporting docs were added so visual production can continue without
depending on chat history:

- `docs/superpowers/specs/2026-07-14-48px-tileset-image-prompts.md`
  - reusable image-generation prompts for a 48px tactics tileset reference set
  - includes one master prompt and four split prompts
- this handoff document

## Current Gap

The structural 48px frontend baseline is in place, but the visual result does
not yet clearly read as a new 48px art pass because current rendering still
leans on the older temporary FE-style assets.

In other words:

- structure is updated
- rendering contract is updated
- asset pipeline expectations are updated
- final visible 48px environment art is not yet produced

## Asset Generation Blocker

Built-in image generation in the current Codex environment repeatedly failed
before image creation started, returning a network error from the internal image
generation endpoint. Because of that, prompts were documented, but new atlas
reference images were not successfully generated inside this session.

This blocker affects visual asset ideation only. It does not invalidate the
code baseline already committed in `52a0129`.

## Recommended Next Steps

1. Generate reference boards externally using the prompts in
   `2026-07-14-48px-tileset-image-prompts.md`.
2. Convert the strongest outputs into a real 48px asset naming and slicing plan.
3. Replace FE-temporary visual priority with 48px-native assets in the Godot
   theme/tile pipeline.
4. Re-run the Godot smoke test.
5. Capture a fresh full-map screenshot that visibly proves the new 48px look.

## Files Most Relevant For The Next Person

- `godot-client/scripts/core/map_metrics.gd`
- `godot-client/scripts/core/map_theme.gd`
- `godot-client/scripts/core/map_loader.gd`
- `godot-client/scripts/core/tile_set_builder.gd`
- `godot-client/scripts/board/board.gd`
- `godot-client/scripts/board/board_camera.gd`
- `godot-client/scripts/board/highlights.gd`
- `godot-client/scripts/board/unit_node.gd`
- `godot-client/scenes/board.tscn`
- `godot-client/tools/smoke_test.gd`
- `godot-client/README.md`
- `docs/superpowers/specs/2026-07-14-godot-map-presentation-design.md`
- `docs/superpowers/plans/2026-07-14-godot-map-presentation-48px.md`
- `docs/superpowers/specs/2026-07-14-48px-tileset-image-prompts.md`

## Git Note

There is an existing modified `godot-client/project.godot` in the working tree
that was not included in this handoff commit because it is not part of the
documented deliverables above.
