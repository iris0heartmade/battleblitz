# BattleBlitz Godot Client

Godot 4.7 frontend for BattleBlitz. The Python backend stays unchanged;
this client replaces the old HTML/CSS/JS board renderer with a native
`TileMapLayer`-based tactics board.

See `../docs/路线/Godot移植方案.md` for the broader port context.

> **Status:** 48x48 map presentation baseline complete. The client now
> renders existing BattleBlitz map JSONs through dedicated ground /
> structure / decor placeholder layers, highlight overlays, static unit
> markers, and a board-bounded camera. Multiplayer / unit interaction
> arrives in M2.

---

## First-run setup

Tile pixel art lives in `../game/app/web/assets/tiles/`. Sync it once into
the Godot project before opening the editor:

```bash
python godot-client/tools/sync_assets.py
```

Then open
`D:\PyCharm Community Edition 2024.3.3\PycharmProjects\Godot_v4.7-stable_win64\Godot_v4.7-stable_win64.exe`,
choose `Import`, and point it at `godot-client/`.

---

## Headless sanity check

Import assets without opening the editor:

```bash
"<godot_exe>" --headless --path godot-client --import --quit
```

Run the smoke test:

```bash
"<godot_exe>" --headless --path godot-client res://tools/smoke_test.tscn
```

Launch the demo board scene:

```bash
"<godot_exe>" --path godot-client
```

---

## Project layout

```text
godot-client/
├── project.godot
├── README.md
├── assets/
│   └── tiles/                 # synced from game/app/web/assets/tiles/
├── scripts/
│   ├── autoload/              # Config, GameState, InputState, NetworkClient, UserSettings
│   ├── core/                  # map_metrics, map_theme, tile_set_builder, map_loader, map_logic, types
│   ├── board/                 # board, board_camera, highlights, unit_node
│   └── main.gd
├── scenes/
│   ├── main.tscn
│   └── board.tscn
└── tools/
    ├── sync_assets.py
    └── smoke_test.gd
```

---

## Milestones

- [x] **M0 - Skeleton.** `project.godot`, autoloads, config mirrors, and shared types.
- [x] **M1 - 48x48 map presentation baseline.** `MapMetrics` owns board scale,
      `MapTheme` routes terrain into ground / structure / decor layers,
      `MapLoader` reads `game/maps/*.json`, and `Board` renders tiles,
      highlights, static units, and camera bounds.
- [ ] **M2 - Online play.** WebSocket subscription, REST actions, full move/attack/claim loop.
- [ ] **M3 - Full features.** Lobby / HUD / combat preview / CO meter / dialogue / mainline.
- [ ] **M4 - Touch + mobile export.** Android + iOS input remap, gesture camera.
- [ ] **M5 - Backend deploy + Web export.** WSS on a public host, HTML5 export.
