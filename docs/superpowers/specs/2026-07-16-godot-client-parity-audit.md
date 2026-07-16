# Godot Client Parity Audit

> Date: 2026-07-16
> Branch: `godot-map-port`
> Scope: compare the current Godot client against the original Web UI and identify remaining work.

## Current Status

The Godot client is no longer just a map-rendering prototype. Recent commits added the main WebUI parity slices needed for ordinary play:

- Map rendering with 48px `TileMapLayer` layers, highlights, units, and camera bounds.
- Online room list, room selection, create-and-join, join selected, and lobby polling.
- Lobby controls for join role, team selection, team update, add AI, remove AI, AI difficulty/backend/personality, AI commander preset, BGM selection, and host commander selection.
- Save management with open/mainline grouping, resume, delete, and refresh.
- Battle HUD with turn/player/gold panels, action bubble, action log, war report, attack confirmation, recruit modal/feedback, CO roster, CO meter, and CO Power trigger.
- Mainline list, pre/post dialogue fetch, start, advance, next battle, abandon, and pre-start commander selection.
- Map editor first slice: menu entry, dedicated editor view, board-backed 15x15 preview, terrain/biome controls, click-to-paint terrain, saved-map listing/loading/deletion, and `/editor/maps` network wrappers.
- NetworkClient wrappers for the main REST surfaces used by the Godot UI.
- Headless smoke coverage for the major scene nodes, typed API wrappers, and response handlers.

Latest verified smoke result during the recent development run:

```text
Passed: 162   Failed: 0
```

## Remaining Gaps

### P0 - Must Fix Before Calling It a Full Replacement

1. **Map editor is only partially ported.**
   Godot now has an editor entry, panel, board-backed preview, terrain/biome controls, click-to-paint terrain, saved-map listing/loading/deletion, and editor API wrappers. It still needs unit placement, resize, undo/redo, and richer WebUI-style editing workflows.

2. **Live backend e2e coverage is thin.**
   The Godot smoke test is good for scene/API wrapper regressions, but most checks are headless/unit-style. Add a scripted backend e2e that creates a game, joins, starts, performs one or two actions, tests spectator join, and resumes.

3. **Lobby spectator UX is simplified.**
   Godot can join as spectator, but WebUI also supports converting an existing player seat versus adding a fresh spectator slot, plus spectator-specific hints. Godot needs that richer flow.

### P1 - Important Parity/Polish

4. **Host row-level lobby controls are incomplete.**
   WebUI lets the host edit other players' teams inline and remove AI from player rows. Godot currently supports self team update plus an AI selector/removal button, but not full row-level host controls.

5. **Room list interaction is functional but not rich.**
   Godot uses a dropdown and a text marker. WebUI has richer room cards/actions. A future Godot pass should make room rows selectable/clickable with clearer status, capacity, map, and host information.

6. **Mainline commander selection lacks card-level context.**
   Godot exposes the unlocked commander dropdown and apply button. WebUI shows card-style choices, current status, lock reasons, and disabled reasons.

7. **Create-room advanced options are still narrower than WebUI.**
   Godot exposes map preset, commander, BGM, team, and room name. It does not yet expose every older WebUI option or explanatory metadata block, such as detailed BGM notes and map designer notes.

### P2 - Quality/Production Work

8. **Localization/encoding cleanup.**
   Several existing Godot and WebUI strings show mojibake in source views. The UI may still render acceptably in places, but the source should be normalized before larger localization work.

9. **Touch/mobile and export work remains.**
    Android/iOS input remap, gesture camera, and export-specific QA are still open.

10. **Backend deploy/Web export remains.**
    Public WSS configuration, HTML5 export validation, and deployment docs are still future work.

11. **Automated visual QA is limited.**
    The repository has screenshot tools, but the current parity gate is mostly smoke assertions. Add screenshot checks for lobby, mainline, battle HUD, save manager, and BGM/commander controls.

## Suggested Next Development Order

1. Finish the Godot map editor first slice: confirm saved `custom:{id}` maps appear in lobby presets, then add unit placement.
2. Add live backend e2e for create/join/start/action/resume so regressions are caught outside mocked response handlers.
3. Expand spectator UX to match WebUI's convert/add-spectator choices.
4. Upgrade room list rows from dropdown selection to clickable Godot controls.
5. Do an encoding/localization cleanup pass once the feature surface settles.

## Files To Watch

- `godot-client/scenes/main.tscn` - current single-screen UI surface for menu, lobby, saves, mainline, and HUD.
- `godot-client/scripts/main.gd` - most Godot UI orchestration and response handling lives here.
- `godot-client/scripts/autoload/network_client.gd` - typed REST/WebSocket API wrapper surface.
- `godot-client/tools/smoke_test.gd` - current headless regression gate.
- `game/app/web/index.html` and `game/app/web/app.js` - source of remaining WebUI parity reference, especially map editor and richer spectator flows.
