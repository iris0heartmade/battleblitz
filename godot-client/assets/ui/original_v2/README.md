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

## Runtime integration (2026-07-31)

The single runtime entry point is `godot-client/scripts/ui/skin_assets.gd`. Scenes
and theme scripts must not `load()` original_v2 textures directly.

### Measured slice geometry (alpha edges, 2026-07-31)

Every value below was measured from the transparent PNG (alpha > 12 content bbox).
Use these as NinePatch/StyleBoxTexture margins; do not guess.

| Asset | Source size | Content bbox | Patch margins (L/T/R/B) |
|---|---:|---:|---:|
| `base/primary_page_frame_9slice` | 1024x768 | (38,36)-(984,733) | 56 / 56 / 56 / 56 |
| `base/secondary_panel_frame_9slice` | 1024x768 | (40,44)-(984,720) | 52 / 52 / 52 / 52 |
| `base/character_summary_card` | 512x640 | (24,24)-(488,617) | 48 / 48 / 48 / 48 |
| `base/item_value_summary_card` | 512x240 | (14,13)-(498,224) | 40 / 40 / 40 / 40 |

### Control spritesheet cell regions (region_rect)

- `controls/button_states.png` — 5 cells @ 426px: neutral (56,275,370,179), hover (426,275,423,179), pressed (882,275,369,179), disabled (1292,275,370,179), selected (1705,275,372,180). StyleBoxTexture margins 48.
- `controls/tab_states.png` — 4 cells @ 543px: inactive (28,232,484,233), hover (571,232,484,233), active (1114,232,485,233), disabled (1658,232,484,233). Margins 36/28/64/48.
- `controls/list_row_states.png` — 4 cells @ 543px: neutral (24,286,498,127), hover (565,286,499,127), selected (1104,286,502,127), disabled (1651,286,498,127). Margins 24.
- `controls/title_nameplates.png` — wide plate (17,329,861,216), narrow (896,348,860,192). Margins 48/40.
- `controls/section_divider.png` — section title bar (75,285,946,150), divider line (1141,354,968,26).
- `controls/status_frames.png` — focus (60,132,630,434), error (773,132,629,434), success (1484,132,629,434). Margins 56.
- `controls/bar_components.png` — trough (23,293,498,139), ink/brass/oxblood fills at 566/1109/1651. Margins 20/24.
- `controls/scrollbar_components.png` — track (215,0,328,724), thumb (543,0,543,724), up/down chevrons.
- `controls/function_icons.png` — 7 icons @ 310px: equipment (16,170,294,384), troops (310,170,310,384), shop (620,170,310,384), save (930,170,310,384), back (1240,170,310,383), confirm (1550,170,310,384), warning (1860,170,294,383).
- `controls/input_hint_capsules.png` — short (84,267,640,193), medium (724,267,724,193), long (1448,267,648,193).

### Battle panels (safe areas from manifests/battle.yaml)

| Asset | Size | StyleBoxTexture margins |
|---|---:|---:|
| `battle/top_battle_status_bar` | 1200x112 | 150 / 18 / 200 / 18 (TextureRect full-stretch) |
| `battle/battle_sidebar_drawer` | 384x720 | 72 / 72 / 82 / 88 |
| `battle/action_menu_panel` | 320x420 | 54 / 54 / 61 / 81 |
| `battle/dialogue_panel` | 1200x300 | 115 / 70 / 155 / 75 |
| `battle/nameplate` | 260x64 | 42 / 18 / 48 / 18 |
| `battle/compact_status_plate` | 240x80 | 48 / 20 / 50 / 22 |
| `battle/chapter_result_title` | 900x180 | 145 / 48 / 200 / 54 |

### Ownership rules (single style owner per component)

- Page-level frames: `mainline_theme.gd apply_page_frame()` (frame stylebox + tiled
  navy weave background child).
- Section panels: `mainline_theme.gd apply_section_panel()` (secondary frame + navy/paper/steel tile).
- Mainline buttons/tabs/rows: `skin_assets.button_style/tab_style/row_style`.
- Battle modal panels (`settings/pause/battle_result/war_report`): `hud_theme.apply_theme()`.
- Battle info panel / action menu / dialogue: `battle_theme.apply_floating_panel /
  apply_action_menu`, `dialog_manager.gd _apply_self_theme()`.
- No theme function `queue_free`s an approved art node; `ArtSkin` cleanup was removed.
