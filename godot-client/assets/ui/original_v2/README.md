# BattleBlitz Original UI Assets v2

This directory contains original UI candidates for the "Frontier War Council Archive" visual system.

## Clean-room rule

- Asset-generation agents did not inspect `docs/参考/fe_image`.
- Commercial screenshots are not generation inputs and are not distributed with the project.
- Prompts do not name or imitate an existing game, franchise, studio, character, or artist.
- Runtime candidates contain no baked text, characters, logos, coats of arms, royal crests, central gemstones, scrollwork borders, or circular command-dial motifs.

## Directory layout

- `base/`: scalable page frames, secondary panels, summary cards, and tiling materials.
- `controls/`: button, tab, row, focus, progress, scrollbar, hint, and generic function-icon candidates.
- `battle/`: battle status rail, side drawer, action menu, dialogue, nameplate, and result-title candidates.
- `sources/`: flat chroma-key outputs retained for provenance and reprocessing.
- `manifests/`: per-workstream prompt, tool, processing, and review records.

These files are candidate assets until their manifest entry has `review_status: approved`. Godot scenes must not reference an unreviewed source image directly.

## Integration requirements

- Use `NinePatchRect` or `StyleBoxTexture` for scalable frames; never stretch a decorative frame as a plain `TextureRect`.
- Keep all labels, values, shortcuts, and localized text in native Godot controls.
- Verify 1280 x 720, 1600 x 900, and 1920 x 1080 before approval.
- Do not modify map, terrain, unit, or board assets as part of this asset set.
