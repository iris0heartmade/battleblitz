# BattleBlitz Godot Client — UI Redesign Spec

**Date:** 2026-07-17
**Branch:** godot-map-port
**Status:** Draft (awaiting user review)
**Author:** Cat-girl Apprentice 🐱

---

## 1. Problem

The Godot client has ~7 top-level views (Menu / Connecting / Lobby /
SavesView / MainlineView / EditorView / GameView) and ~8 modal overlays
(SettingsPanel / PauseOverlay / DialogPanel / TutorialBubble /
WarReportPanel / BattleResultPanel / AttackConfirmPanel / RecruitPanel).
Pain points called out by the user:

- **Disorganized layout**: widgets in views are positioned ad-hoc;
  spacing and grouping are not consistent.
- **Emoji overload**: button / label texts carry decorative emoji
  (`⚔ 🛡 🎮 📁 📖 ⚙ ❌ ▶ 💤 👑 ✖ 🚶 ✨ 🆕 💰 🤖 👀 📜 ⚡ 💥 💀 🏆 🟢`)
  which clutters the UI and makes it feel cheap.
- **Inconsistent per-view chrome**: each view hand-rolls its own
  `FrameOuter + Border + Title` combo, with no shared definition.

## 2. Design Baseline

### 2.1 Color Palette (extends `MenuTheme` in `scripts/ui/menu_theme.gd`)

Keep existing FE-inspired palette, ADD new tokens:

```gdscript
const C_DIVIDER       := Color("#5a4426")   # thin section divider
const C_HOVER_HIGHLIGHT := Color("#e8c878") # same as C_GOLD_BRIGHT
const C_DISABLED      := Color("#5a5640")   # disabled state
```

Existing constants reused: `C_BG_DEEP`, `C_BG_PANEL`, `C_GOLD`,
`C_GOLD_BRIGHT`, `C_TEXT_WARM`, `C_TEXT_DIM`, `C_BTN_BLUE`,
`C_BTN_BLUE_HOVER`, `C_BTN_BLUE_PRESS`, `C_FIRE_RED`.

### 2.2 Font Scale (extends `MenuTheme`)

| Token     | Size | Use                                          |
|-----------|------|----------------------------------------------|
| `FS_HERO` | 56   | Main menu title only                         |
| `FS_TITLE`| 32   | Sub-screen titles (Lobby / Saves / Mainline) |
| `FS_SECTION` | 22 | Section header inside a view                 |
| `FS_BODY` | 16   | Default body / form row label                |
| `FS_BTN`  | 17   | Button text                                  |
| `FS_HINT` | 13   | Hint / dim subtitle                          |
| `FS_FOOT` | 12   | Footer / version                             |
| `FS_PILL` | 14   | HUD corner pill                              |

### 2.3 Spacing

| Token     | Value | Use                          |
|-----------|-------|------------------------------|
| `PAD_X`   | 24    | Outer panel padding         |
| `PAD_Y`   | 18    | Outer panel padding         |
| `GAP_SM`  | 6     | Tight (label ↔ helper text) |
| `GAP`     | 12    | Standard row gap             |
| `GAP_LG`  | 18    | Section separator           |
| `ROW_H`   | 36    | Default row height          |
| `BTN_H`   | 40    | Primary button height       |

All views sit on an **8-px baseline grid**.

### 2.4 Emoji Policy

| Where                         | Emoji rule                                   |
|-------------------------------|----------------------------------------------|
| Main menu / button labels      | **None** — use pure text                    |
| View titles                    | **None**                                     |
| HUD status pill                | Up to 1 per pill (e.g. 🟢/🤖/👀) — keep for fast scanning |
| Floating combat text           | 1 emoji max (💥/⚡/💀/💚) — already OK     |
| Toast / status line            | **None** — pure text                         |

Remove emoji from every Button / Label `text` in `main.tscn` except
floating combat text (in code) and HUD status pills.

### 2.5 View Chrome — Standard Layout

Every top-level view uses the same structure:

```
┌─────────────────────────────────────────────┐
│  TITLE              [Optional close/return] │   ← 44px title bar (FS_TITLE)
├─────────────────────────────────────────────┤
│                                             │
│            CONTENT (panels)                  │   ← anchor (left=24, right=-24, top=80, bottom=-72)
│                                             │
├─────────────────────────────────────────────┤
│  Footer  [Optional action buttons]          │   ← 48px
└─────────────────────────────────────────────┘
```

Implemented once as a reusable function `apply_view_chrome(view, title)`
in `menu_theme.gd` (or a new `view_chrome.gd`).

### 2.6 Widget Standards

- **Button height**: 40px (primary) / 32px (inline).
- **Input**: `LineEdit` height 36px, `OptionButton` matches.
- **RichTextLabel**: 16/14 line spacing; no font_color override (uses theme).
- **Section dividers**: 1px `HSeparator` colored `C_DIVIDER`, no emoji.

## 3. Implementation Rounds

Each round = `propose diffs → apply → auto-screenshot all changed views →
user reviews screenshots → next round`.

### Round 1 — Main Menu

- 8 buttons (currently `自由对局 / 联机大厅 / 继续上次 / 存档管理 / 主线章节 / Map Editor / 设置 / 退出`) → collapse to **2 group-cards**:
  ```
  ┌── SINGLE PLAYER ──┐
  │ ▶ 自由对局          │
  │ ▶ 主线章节          │
  └────────────────────┘
  ┌── MULTIPLAYER ─────┐
  │ ▶ 联机大厅          │
  │ ▶ 加入房间(代码入)  │
  └────────────────────┘
  [ 存档管理 ] [ Map Editor ] [ 设置 ] [ 退出 ]
  ```
- Replace `⚔ BATTLEBLITZ ⚔` title with single-color wordmark.
- Remove every emoji from Menu/Title/Button text.
- Keep footer 1 line.

### Round 2 — Container Views (`Lobby / SavesView / MainlineView / EditorView`)

- Replace per-view ad-hoc Frame with `apply_view_chrome()`.
- Each view = **two-column layout**:
  - Left col (60%): primary list / config
  - Right col (40%): secondary panel / preview / help
- Apply `RowVBoxContainer` helper (auto-height rows, uniform gap).
- Connect separated sections by 8-px gap + 1-px divider.

### Round 3 — In-Game HUD

- 4 HUD corners stay, but:
  - Bottom-left strip consolidated: `💰 gold [pill] · 指挥官徽章 [pill]`
  - Right-side `InfoPanel` width 360 (was 384).
  - Action Bubble: tighter (180px, 6 buttons incl. cancel) — already done in current session.
  - RecruitPanel / AttackConfirmPanel: list rows 36px.

### Round 4 — Modals & Overlays

- `SettingsPanel / PauseOverlay / DialogPanel / TutorialBubble /
  WarReportPanel / BattleResultPanel / RecruitPanel / AttackConfirmPanel`:
  Each = single column of rows, row height 36, `apply_view_chrome` with title.
- Standard button row at bottom: `[ Primary ]  [ Secondary ]` (right-aligned).
- Remove emojis from settings / pause / dialog titles.

## 4. Files Touched

- `godot-client/scripts/ui/menu_theme.gd` — add FS_*, GAP_*, ROW_H, C_*
- `godot-client/scripts/ui/view_chrome.gd` — new helper `apply_view_chrome(view, title)`
- `godot-client/scenes/main.tscn` — round-by-round rewrites of the listed views
- `godot-client/scripts/main.gd` — `_show_view`, `_on_X_pressed` text updates
- `godot-client/tools/views_screenshot.gd` — extend to capture modal overlays
- `docs/superpowers/specs/2026-07-17-godot-ui-redesign.md` — this doc

## 5. Test Method

For each round:

1. Apply tscn + gd diff.
2. Run `tools/views_screenshot.tscn` with `BB_AUTO_QUIT=20` → generates
   `diag_view_<name>.png` for every view AND modal.
3. Diff each PNG against its pre-round baseline (pixel diff via PIL).
4. User reviews screenshots in chat.

Smoke test (`tools/smoke_test.tscn`) must keep 184/0 PASS throughout.

## 6. Out of Scope (this spec)

- Logic changes (move / attack / WS / state polling) — already fixed in earlier session.
- Asset / pixel art changes.
- BGM / SFX selection UI polish (Round 4 may touch, but not redesign from scratch).
