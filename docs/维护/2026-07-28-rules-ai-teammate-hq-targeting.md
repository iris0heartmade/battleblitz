# 2026-07-28 规则 AI 队友 HQ 目标修复

## 问题

在团队模式中，规则 AI 队友经常向玩家自己的 HQ 前进，而不是向敌方 HQ 进攻。

## 根因

- `_load_ai_snapshot` 已经按 `_team_of(player)` 区分敌我，能正确排除队友单位和队友 HQ。
- 但移动打分使用的 `_load_enemy_castles_xy` 只排除了 AI 自己的 HQ，没有排除同队玩家的 HQ。
- 因此 `castle_pull` 会把队友 HQ 当成敌方 HQ，导致 AI 被错误吸引。

## 修改

- `_load_enemy_castles_xy` 先加载本局玩家，按 `_team_of` 找出同队玩家。
- 返回敌方 HQ 时同时排除自己和同队玩家。
- 新增回归测试：红/绿同队、蓝敌队时，绿方规则 AI 的敌方 HQ 目标只能是蓝方 HQ。

## 验证

- `python -m pytest tests/test_team_mode.py::test_rules_ai_enemy_castle_targets_exclude_teammate_hq -q`
