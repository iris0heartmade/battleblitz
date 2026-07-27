# BattleBlitz Godot Client Changelog

## 2026-07-28

- Fixed rules-AI HQ targeting in team games: AI now excludes teammate HQs from enemy castle pull targets, so allied AI advances toward enemy HQs instead of the player's HQ.
- Added `red_full_roster_4p_20`, a 20x20 four-player free-mode map where red starts with one of every registered unit type and nearby village, barracks, and vault economy tiles.
- Expanded barracks recruitment across backend, Web, and Godot clients so every registered unit type is available from recruit UI paths.
- Fixed free-mode victory cleanup: the final kill now flushes dead units before rout evaluation, and match finish clears the player's suspend save so returning to menu cannot resume into the victory screen.

## 2026-07-27

- Changed the mainline entry to an FE8-style slot-first flow: players now choose one of the three formal save slots before the current chapter is resolved.
- Added `assets/tilesets/` as the preferred atlas-sheet home for map art.
- Wired the three new 48px-grid map sheets into `Config.TILESET_ATLAS_COORDS`.
- Updated `TileSetBuilder` so configured atlas sheets become shared runtime `TileSetAtlasSource` resources before legacy per-tile PNG fallback.
- Updated `MapLoader` to paint configured atlas coordinates directly.
- Routed transparent forest/mountain-style tiles through overlay layers so they render above biome-appropriate base ground.
- Added a focused `tileset_atlas_test` scene and smoke-test assertions for the new atlas mapping.
- Fixed Godot client movement previews so allied units are pass-through but not valid destinations; enemy units still fully block movement.
- Upgraded atlas rendering to parse sibling `.txt` label maps, grouping same-terrain variants by biome and selecting stable per-cell variants across each map.
