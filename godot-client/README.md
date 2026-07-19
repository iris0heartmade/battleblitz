# BattleBlitz Godot Client

Godot 4.7 frontend for BattleBlitz. The Python backend stays unchanged;
this client replaces the old HTML/CSS/JS board renderer with a native
`TileMapLayer`-based tactics board.

See `../docs/路线/Godot移植方案.md` for the broader port context.

> **Status as of 2026-07-19:** the Godot client is now close to replacing
> the old Web UI for normal play. The old home-page "free play vs AI" entry
> has been removed; users enter through mainline or the online lobby. It
> covers room browsing and creation, lobby host controls, spectator
> join/convert, team switching, save management, movement/attack/skill/
> claim/recruit/wait/end-turn, CO HUD/power, BGM selection, commander
> selection, mainline lifecycle with auto-abandon retry, dialogue scenes,
> portrait assets, and a basic map editor. Remaining gaps are mostly
> advanced parity and release polish: editor undo/fill/line/select,
> help/reference panels, AI commentary UI,
> phase-aware polling/diagnostics, and export-safe asset loading.

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

Verify the two critical GUI entry flows against a running backend:

```bash
"<godot_exe>" --headless --path godot-client res://tools/entry_flow_e2e.tscn
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
    ├── smoke_test.gd
    └── entry_flow_e2e.gd
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
      help/reference panels, commentary UI, diagnostics, and full integration/e2e coverage against
      a running backend.
- [ ] **M4 - Touch + mobile export.** Android + iOS input remap, gesture camera.
- [ ] **M5 - Backend deploy + Web export.** WSS on a public host, HTML5 export.

For the current gap list, see
`../docs/WebUI-vs-GodotClient-差异与计划.md`.

For the backend contract used by this client, see
`../docs/参考/Godot客户端后端接口.md`.
