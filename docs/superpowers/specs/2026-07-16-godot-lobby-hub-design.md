# Godot Lobby Hub Design

> Date: 2026-07-16
> Scope: Godot client basic create/join/lobby flow

## Goal

Bring the Godot client closer to the original Web UI's free-play room flow while keeping the current Godot GBA-style single-panel design. The delivered slice should let a player open the online lobby, refresh waiting rooms, create a room with a name and map preset, join a selected waiting room, add an AI, and start the game.

## Web UI Reference

The Web UI splits this flow across create-game, join-list, and lobby views:

- `renderJoinList` lists rooms and lets the user join or spectate.
- `createGame` gathers room name, map preset, BGM, commander, and related settings.
- `renderLobby` shows players, teams, spectators, AI controls, and the start button.

Godot should not copy the DOM layout. It should reuse the existing `Lobby` view as a dense tactical command panel:

- Left: waiting room list with refresh and join controls.
- Right: compact create-room controls.
- Bottom/current room: player list, add AI, and start.

## Godot UI

The existing `Lobby` scene remains the entry point. It gains these stable nodes:

- `RoomList`: `RichTextLabel` listing waiting games from `GET /games`.
- `RefreshRoomsBtn`: refreshes `RoomList`.
- `JoinSelectedBtn`: joins the selected waiting room.
- `CreateNameInput`: room name, defaulting to `<player name> 的房间`.
- `MapPresetOption`: map preset dropdown from `GET /games/presets`.
- `CreateRoomBtn`: creates and joins a room.

The first waiting room is selected by default for this slice. That keeps the implementation small and testable without introducing a custom clickable list control. The list copy makes the selected room explicit.

## Data Flow

Entering the lobby no longer auto-creates a room. Instead it:

1. Shows the lobby view.
2. Loads presets with `NetworkClient.list_presets`.
3. Loads room summaries with `NetworkClient.list_games`.

Creating a room calls `NetworkClient.create_game(name, preset_id, biome, "rout")`, then `NetworkClient.join_game`. Joining a room calls `NetworkClient.join_game` for the selected game id. After joining, the existing lobby polling uses `NetworkClient.get_lobby`; Add AI and Start continue to use the existing endpoints.

## Non-Goals

This slice does not implement spectator join, team switching, AI personality selection, BGM selection, commander selection, deleting saves, or full clickable room rows. Those remain WebUI parity work for later.

## Acceptance

- Headless smoke test verifies the lobby hub nodes exist.
- Opening the lobby does not create a room automatically.
- The room list can render waiting games and select the first one.
- Creating a room joins it and begins the current-room polling flow.
- Joining the selected room joins it and begins the current-room polling flow.
- Existing free-play auto-create flow remains available.
