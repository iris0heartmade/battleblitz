# UI Rebuild Assets

This directory contains original, text-free raster assets for the Godot mainline preparation and battle HUD rebuild. They are deliberately small reusable pieces, not precomposed runtime screens.

## Nine-slice frame

| File | Size | Use |
| --- | --- | --- |
| `navy_gold_frame_overlay_9slice.png` | 1254 x 1254 RGBA | Preferred decorative overlay. Its middle is transparent, so place it over a native dark-blue `Panel` background. |
| `navy_gold_frame_9slice.png` | 1254 x 1254 RGB | Opaque fallback for a standalone dialogue or save-slot card. |

Use either frame in a Godot `NinePatchRect` with all four patch margins set to **128 px**. Keep the node's `draw_center` enabled only for the opaque fallback. For the overlay, use `draw_center = false`; never stretch it with `TextureRect`.

The `*_source.png` files keep the generated source for review. They are not runtime references.

## Equipment icons

These are independent 48 x 48 RGBA PNGs with transparent surroundings. Use `TextureRect` in `EXPAND_FIT_WIDTH_PROPORTIONAL` / `KEEP_ASPECT_CENTERED` mode.

- `equipment_sword_48.png`: weapon slot
- `equipment_armor_48.png`: armor slot
- `equipment_accessory_48.png`: accessory slot

## Attribute icons

These are independent 24 x 24 RGBA PNGs for stat rows or compact battle cards.

- `stat_heart_24.png`: HP / vitality
- `stat_sword_24.png`: physical attack
- `stat_shield_24.png`: defense

`icon_sheet.png` is the alpha-preserved source sheet from which the standalone icons were cropped. `icon_sheet_chromakey_source.png` is kept solely as the original chroma-key source.

## Art direction

Palette: ink navy, desaturated antique gold, and restrained steel highlights. The assets are original tactical-RPG decoration and must be combined with native Godot panels, labels, and layout containers. Do not use them as a full-screen background or recreate a third-party game's interface.
