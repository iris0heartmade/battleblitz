# Godot Mainline Preparation UI Design

## Goal

Build the first usable Godot presentation layer for the hero/mercenary backend design. The Godot client must stop auto-starting a mainline battle after fetching `prepare`; it should show a tactical RPG preparation center where the player can inspect heroes, roster, equipment, mercenary options, shop stock, and saves before starting battle.

## Reference Direction

The visual model is inspired by tactical RPG preparation screens such as Fire Emblem: Three Houses, without copying assets or layout exactly. The useful patterns are:

- A battle preparation hub before combat, not a direct launch.
- A strong primary action for battle start.
- Character-focused panes with list/detail structure.
- Equipment and shop screens that always show available gold and item effects.
- Promotion/class-change as a deliberate confirmation step.

## Scope

This first pass builds the Godot equivalent of Web UI's core hero preparation flow:

- Mainline preparation center inside `MainlineView`.
- Tabs for `英雄`, `部队`, `装备`, `佣兵`, `商店`, and `存档`.
- Hero list/detail display with stats, equipment, skills, promotion status.
- Equipment list and equip/unequip actions against selected hero.
- Mercenary config display and point allocation actions.
- Post-battle shop display and purchase action.
- Save slot panel remains visible and uses the new save API already wired in the previous phase.
- Start battle button calls the existing `start_mainline` flow only after the player confirms.

Out of scope for this pass:

- New hero combat animations.
- New art generation.
- Complex controller navigation polish.
- Full Web UI parity for every preparation sub-state.

## UI Architecture

The existing `MainlineView` remains the entry surface. It expands from a chapter list into a wider preparation frame:

- Left column: chapter list and mainline save slots.
- Right column: preparation panel for the selected chapter.
- Top of right column: preparation summary with battle index, total battles, gold, hero count, roster count.
- Tab row: `英雄`, `部队`, `装备`, `佣兵`, `商店`, `存档`.
- Content area: a RichTextLabel for readable tactical summaries in this first pass.
- Action row: `开始战斗`, `刷新整备`, `返回主菜单`, `放弃主线`.

This deliberately uses text-rich panels instead of a card-heavy mock UI because the current Godot client already has compact menu styling and smoke tests around node existence. Later passes can split the content area into custom scenes.

## Data Flow

1. Player opens mainline view.
2. Client loads mainlines, commanders, save slots, and hero registry as before.
3. Player selects a chapter.
4. Client fetches chapter detail and then `GET /mainlines/{id}/prepare`.
5. Client stores the response in `_mainline_prepare_payload`, sets the active tab to `heroes`, and renders the preparation panel.
6. Player can switch tabs locally.
7. Equipment, promotion, shop, and mercenary actions call their backend endpoint, then refresh `prepare` or shop/config data.
8. Player presses `开始战斗`; client calls `start_mainline` using disabled unit indices gathered from roster choices. First pass sends `[]` while showing the roster and preserving the API shape.

## Error Handling

- If `prepare` fails, keep the player in `MainlineView` and show the error in the preparation panel.
- If promotion/equipment/shop/mercenary calls fail, show a status message and do not change local state.
- If shop or mercenary config is unavailable, the related tab shows a readable empty/error state.
- If `start_mainline` returns `mainline_already_active`, keep the existing auto-abandon/retry behavior.

## Testing

- Extend Godot smoke tests to assert the new preparation nodes exist.
- Add smoke-level checks that `_on_mainline_prepare_response` renders the panel instead of auto-starting.
- Keep the backend Godot contract test covering endpoint wrappers.
- Run Godot headless smoke and targeted backend tests before completion.

## Acceptance Criteria

- Selecting a mainline chapter does not automatically enter battle.
- The player sees a preparation summary and tabs.
- Hero tab shows hero count, hero names, class, level, stats, equipment, and promotion status.
- Equipment tab can invoke equip/unequip wrapper for selected hero.
- Mercenary tab can fetch and display config, with allocation buttons when config contains spendable choices.
- Shop tab can fetch and display items, gold, and purchase buttons.
- Start battle remains possible and uses the existing battle entry flow.
