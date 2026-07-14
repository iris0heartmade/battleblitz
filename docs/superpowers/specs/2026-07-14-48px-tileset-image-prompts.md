# BattleBlitz 48px Tileset Image Prompts

- Date: 2026-07-14
- Branch: `godot-map-port`
- Purpose: reusable image-generation prompts for a 48px tactical-RPG environment tileset reference set
- Style target: bright, high-contrast, GBA Fire Emblem-inspired, top-down with slight angled perspective, strong tactical readability

## Usage Notes

- Use the master prompt if the image tool can handle a dense single-sheet atlas.
- Use the split prompts if the tool struggles with long prompts or large boards.
- Prefer generation outputs that preserve a visible grid and atlas-like alignment.
- These prompts are for reference-board generation, not final production sprites.
- The target is a 48px ruleset, so the visual output should imply strict 48x48 cell logic even if the generator does not produce perfectly sliceable tiles.

## Global Style Add-On

Append this block to any prompt if the model starts drifting away from the intended look:

```text
Bright high-contrast GBA Fire Emblem-inspired tactics-RPG style. Pixel art. Top-down with slight angled perspective. Crisp borders, clear silhouettes, strong terrain separation, immediate strategic readability. Medieval fantasy palette. No characters, no UI, no labels, no watermark.
```

## Master Prompt

```text
Create a single large pixel-art tileset reference board for a turn-based tactics RPG.

This is a production-oriented master sheet, not a gameplay screenshot. Every tile cell is exactly 48x48 pixels in concept, arranged on a clean visible grid as a multi-section atlas. Use a top-down view with a slight angled perspective. Keep borders crisp, silhouettes clear, and tactical readability extremely strong. Use a cohesive medieval fantasy palette. No UI, no characters, no text labels, no watermark.

The image should look like a well-organized master tileset sheet divided into clear visual zones, suitable for later manual slicing into tile assets.

Natural terrain zone:
- grass plains base tiles with several subtle variants
- forest tiles with multiple canopy and ground variants
- mountain tiles and cliff-edge tiles with readable elevation
- dirt road tiles and stone road tiles
- river tiles: straight, corner, T-junction, cross, narrow bends
- bridge tiles over river
- ocean and sea tiles: deep water, shallow water, coast edges, inner corners, outer corners, wave variants, beach transitions, rocky coast transitions
- shoal and shallow coastal tactical tiles

Settlement and military building zone:
- village tiles with multiple roof, color, and layout variants
- mercenary post / hired swords outpost tiles, rugged but readable
- fortress tiles with a heavy military stone look
- castle exterior building tiles with a beautiful polished fantasy tactics-game look

Castle exterior structural zone:
- castle wall tiles, wall edges, corners, battlements
- gatehouse tiles and castle gate variants
- tower and turret variants
- courtyard entrance transition tiles
- stone plaza and exterior castle-ground tiles

Castle interior facility zone:
- noble castle interior floor tiles
- red carpet tiles, edges, turns, junctions
- throne dais and throne room centerpiece tiles
- barracks floor and furnishing tiles
- weapon rack and armory fixture tiles
- supply crate and storage detail tiles
- library and council chamber detail tiles
- iron bars, prison gate, and dungeon fixture tiles
- stair tiles, column tiles, decorative pillar tiles
- chapel or ceremonial hall floor variants

Variation requirements:
- each major terrain family should visibly include base, edge, corner, and connection variants
- important building groups should include orientation variants and visual variants
- keep all tiles aligned to a strict atlas presentation
- each tile should feel self-contained and grid aligned
- avoid excessive tiny noise that harms tactical readability
- emphasize bright color separation and crisp silhouettes over painterly detail

Composition requirements:
- show one complete atlas board view
- zoom out enough to show many tiles at once
- the board should feel like a serious tactics-RPG environment tileset proposal ready for 48px production planning
- use a neutral unobtrusive background outside the atlas if needed
```

## Split Prompt A: Natural Terrain

```text
Create a pixel-art tactical RPG terrain atlas board in a bright high-contrast GBA Fire Emblem-inspired style.

This is a production-oriented terrain reference sheet, not a gameplay screenshot. Every tile cell is exactly 48x48 pixels in concept, arranged on a strict visible grid. Top-down with slight angled perspective. Crisp borders, clear silhouettes, and strong terrain readability. Medieval fantasy palette. No characters, no UI, no labels, no watermark.

Show an organized atlas of natural terrain tiles with many variants:
- grass plains base tiles with subtle color and texture variants
- forest tiles with multiple canopy and forest-floor variants
- mountain tiles and cliff-edge tiles with readable height separation
- dirt roads and stone roads
- river tiles: straight, corners, T-junctions, cross-junctions, narrow bends
- bridge tiles crossing rivers
- ocean and sea tiles: deep water, shallow water, coast edges, inner corners, outer corners, beaches, rocky coasts, wave variations
- shoal and shallow coast tactical tiles

Requirements:
- each terrain family should include base, edge, corner, and connection variants
- keep tile boundaries visually regular for later slicing
- emphasize strong color separation and clean tactical silhouettes
- avoid noisy painterly detail
- the final board should look like a serious 48px tactics tileset planning sheet
```

## Split Prompt B: Settlements And Major Buildings

```text
Create a pixel-art tactical RPG building atlas board in a bright high-contrast GBA Fire Emblem-inspired style.

This is a production-oriented building reference sheet, not a gameplay screenshot. Every tile cell is exactly 48x48 pixels in concept, arranged on a strict visible grid. Top-down with slight angled perspective. Crisp borders, readable building silhouettes, strong tactical clarity. Medieval fantasy palette. No characters, no UI, no labels, no watermark.

Show an organized atlas of settlement and military building tiles:
- village tiles with several roof, color, and footprint variants
- mercenary post / hired swords outpost tiles, rugged but readable
- fortress tiles with heavy military stone construction
- beautiful castle exterior building tiles with polished fantasy war-game readability

Requirements:
- important buildings should include orientation variants and visible design variations
- keep the buildings readable as tactical map landmarks, not decorative paintings
- maintain strict grid alignment and atlas organization
- make the sheet feel ready to guide later manual slicing for a 48px tileset
```

## Split Prompt C: Castle Exterior Structures

```text
Create a pixel-art tactical RPG castle exterior atlas board in a bright high-contrast GBA Fire Emblem-inspired style.

This is a production-oriented castle structure reference sheet, not a gameplay screenshot. Every tile cell is exactly 48x48 pixels in concept, arranged on a strict visible grid. Top-down with slight angled perspective. Crisp borders, strong stone shape readability, clear tactical silhouettes. Medieval fantasy palette. No characters, no UI, no labels, no watermark.

Show an organized atlas of castle exterior structural tiles:
- castle walls
- wall edges
- wall corners
- battlements
- gatehouse tiles
- castle gate variants
- tower and turret variants
- courtyard entrance transition tiles
- stone plaza tiles
- exterior castle-ground tiles

Requirements:
- include base, edge, corner, and connection logic where relevant
- important structures should include orientation and visual variants
- prioritize strong map readability and clear wall logic over decorative excess
- keep everything aligned like a real production atlas for later slicing
```

## Split Prompt D: Castle Interior Facilities

```text
Create a pixel-art tactical RPG castle interior atlas board in a bright high-contrast GBA Fire Emblem-inspired style.

This is a production-oriented interior reference sheet, not a gameplay screenshot. Every tile cell is exactly 48x48 pixels in concept, arranged on a strict visible grid. Top-down with slight angled perspective. Crisp borders, readable furniture and floor logic, strong tactical clarity. Medieval fantasy palette. No characters, no UI, no labels, no watermark.

Show an organized atlas of castle interior facility tiles:
- noble castle floor tiles
- red carpet tiles with straight, corner, turn, and junction variants
- throne dais and throne room centerpiece tiles
- barracks floor and furnishing tiles
- armory and weapon rack fixture tiles
- supply crate and storage tiles
- library and council chamber detail tiles
- iron bars, prison gate, and dungeon fixture tiles
- stair tiles
- column tiles
- decorative pillar tiles
- chapel or ceremonial hall floor variants

Requirements:
- include orientation variants and layout-friendly connection variants
- keep every tile readable on a tactics map
- avoid overly tiny decorative noise
- align everything like a real atlas intended to support later 48px production
```

## Optional Reinforcement Lines

Use one or two of these if a model starts drifting:

```text
Make the grid spacing and tile boundaries extremely regular, as if prepared for an actual production tileset sheet.
```

```text
Use bright readable GBA-era tactical RPG color logic, with strong terrain separation and immediately recognizable strategic silhouettes.
```

```text
Do not make this look like a scene illustration; make it look like a real organized tile atlas board.
```

## Recommended Workflow

1. Try the master prompt first if the tool handles large atlases well.
2. If the tool collapses detail or ignores sections, generate the four split boards separately.
3. Pick the strongest outputs and use them as style references for later manual redraw or formal tileset production.
4. Do not assume generated sheets are directly slice-ready; treat them as structured visual concept sources unless manually cleaned.
