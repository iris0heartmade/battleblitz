# BattleBlitz Godot Client

Godot 4.7 frontend for BattleBlitz. The Python backend (FastAPI + WebSocket)
stays unchanged — this client just replaces the existing HTML/CSS/JS board
renderer with a proper `TileMapLayer`-based scene.

See `../docs/路线/Godot移植方案.md` for the full port plan.

> **Status:** M0 (skeleton) + M1 (map prototype) — renders a map JSON as
> tile art with biome variants. Multiplayer / unit interaction arrives in M2.

---

## First-run setup

The tile pixel art lives in `../game/app/web/assets/tiles/`. Godot wants
PNGs inside the project root, so sync them once before opening the editor:

```bash
# From the repo root.
python godot-client/tools/sync_assets.py
```

That script copies the 70 tile PNGs into `godot-client/assets/tiles/`. The
files are committed to git so the editor can open the project without
network access.

Then open `D:\PyCharm Community Edition 2024.3.3\PycharmProjects\Godot_v4.7-stable_win64\Godot_v4.7-stable_win64.exe`,
"Import", point at `godot-client/`, and the editor will auto-generate
`.godot/` + `.import/` (gitignored).

---

## Headless sanity check

The project can be parsed and the asset import kicked off without the GUI:

```bash
"<godot_exe>" --headless --path godot-client --import --quit
```

To run the main scene without opening the editor:

```bash
"<godot_exe>" --path godot-client
```

---

## Project layout

```
godot-client/
├── project.godot          # Godot project config
├── icon.svg               # placeholder icon
├── README.md              # you are here
├── assets/
│   └── tiles/             # synced from game/app/web/assets/tiles/
├── resources/             # built TileSet / themes (.tres) — see tools/
├── scripts/
│   ├── autoload/          # Config, GameState, InputState, NetworkClient, UserSettings
│   ├── core/              # types, tile_set_builder, map_loader, map_logic
│   ├── board/             # board.gd, highlights.gd, unit_node.gd
│   └── main.gd            # entry point
├── scenes/
│   ├── main.tscn          # top-level: menu + game container
│   └── board.tscn         # the tile board
└── tools/
    ├── sync_assets.py     # copy tile PNGs from game/app/web/assets/tiles
    └── build_tileset.py   # (M1+) generate res://resources/terrain_tileset.tres
```

---

## Milestone checklist

- [x] **M0 — Skeleton.** `project.godot` + autoloads + Config constants + *Out type mirrors.
- [x] **M1 — Map prototype.** `TileSetAtlasSource` per (terrain, biome), `MapLoader` reads
      `game/maps/*.json`, `Board` scene renders tiles + highlights skeleton.
- [ ] **M2 — Online play.** WebSocket subscription, REST actions, full move/attack/claim loop.
- [ ] **M3 — Full features.** Lobby / HUD / combat preview / CO meter / dialogue / mainline.
- [ ] **M4 — Touch + mobile export.** Android + iOS input remap, gesture camera.
- [ ] **M5 — Backend deploy + Web export.** WSS on a public host, HTML5 export.

See `../docs/路线/Godot移植方案.md` for the contract this work follows.
