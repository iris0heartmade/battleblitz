# BattleBlitz Godot Client

Godot 4.7 frontend for BattleBlitz. The Python backend stays unchanged;
this client replaces the old HTML/CSS/JS board renderer with a native
`TileMapLayer`-based tactics board.

See `../docs/路线/Godot移植方案.md` for the broader port context.

> **Status as of 2026-07-16:** the Godot client has moved past the map
> presentation baseline into playable parity slices: online room browsing
> and creation, lobby AI controls, team switching, save management, attack
> confirmation, recruit feedback, CO HUD/power, BGM selection, commander
> selection, and mainline start/advance/abandon/next-battle flows. The
> remaining gaps are mostly advanced Web UI parity: the map editor, richer
> spectator/host controls, AI commander assignment, and deeper end-to-end
> interaction coverage.

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
- [x] **M2 - Online play core.** WebSocket subscription, REST action wrappers,
      move/attack/claim/recruit/end-turn paths, action log, HUD refresh, and
      reconnect/resume hooks are present.
- [x] **M3 - Main feature parity slices.** Lobby room browsing, create/join,
      spectator join option, team switching, add/remove AI, AI personality,
      BGM selection, commander selection, save manager, combat confirmation,
      CO meter/power, dialogue, and mainline lifecycle controls are present.
- [ ] **M3.5 - Web UI parity polish.** Remaining work: full map editor,
      richer spectator conversion/add-spectator UX, host row-level controls,
      per-AI commander assignment, better room-row interaction, and full
      integration/e2e coverage against a running backend.
- [ ] **M4 - Touch + mobile export.** Android + iOS input remap, gesture camera.
- [ ] **M5 - Backend deploy + Web export.** WSS on a public host, HTML5 export.

For the current gap list, see
`../docs/superpowers/specs/2026-07-16-godot-client-parity-audit.md`.
