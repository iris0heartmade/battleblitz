# 2026-07-28 自由模式胜利与中断存档修复

## 问题

- 联机大厅自由模式房间胜利结算后返回主菜单，中断存档仍存在。
- 继续该中断存档会回到胜利结算画面。
- 消灭所有敌方 team 单位后，没有立刻胜利，需要等到后续回合流程再次触发判定。

## 根因

- `cleanup_dead_units` 在胜利判定前没有强制刷新删除队列，导致 `_alive_teams` 仍可能读到刚被击杀但尚未 flush 的单位。
- `_finish_game` 需要清理参与玩家的中断存档，但函数没有接收 `AsyncSession`，原清理逻辑落入异常保护后只写警告，不会真正清掉 suspend。

## 修改

- 死亡单位删除后立即 `flush`，让 rout 判定看到最新单位状态。
- 在删除前缓存死亡单位所属 `game_id`，避免从 deleted state 对象回溯对局。
- `_finish_game` 改为显式接收 `session`，胜利/平局/占领/到达收尾统一走同一清理路径。
- 新增 `test_free_mode_attack_rout_finishes_immediately_and_clears_suspend`，覆盖自由模式最后一击即时胜利和中断存档清理。

## 验证

- `python -m pytest tests/test_free_mode_victory_suspend.py -q`
