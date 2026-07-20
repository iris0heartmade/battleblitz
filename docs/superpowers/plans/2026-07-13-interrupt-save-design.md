# Interrupt-Save 设计 (2026-07-13)

> 学长要的"中断存档"设计提案 —— 等学长 review 后再实现
> 不影响正式存档(hero 长期数值),仅在战斗中保留"可以继续战局"的最小状态

---

## 1. 现状回顾

**目前的状态机**(基于代码 + 测试):

```
waiting  ──/start──>  playing  ──/advance(赢了)──>  finished
                            │
                            └──/abandon──>  finished(active_mainline=None)
```

**关键观察**:
- `Game.status` 只有 `waiting/playing/finished` 三态
- `Game` 行 + 全部 `Player/Unit/Tile/ActionLog` 行**已经是事务化持久**的(写到 SQLite)
- `hero_campaign_states` 是在 `/advance` 时由 `_persist_mainline_hero_results` 写回,**战斗中不会动**
- WS gateway 已有 200 事件 ring buffer (`_REPLAY_MAX = 200`) 支持重连回放
- **没有任何"暂停"或"中断存档"的概念**

**所以"中断存档"在事实层是空缺的** —— 玩家断网/关浏览器后,DB 里的 Game 仍然 `playing`,但 UI 没有"继续战局"入口。

---

## 2. 设计目标

| 目标 | 说明 |
|------|------|
| **可恢复** | 玩家断线/退出后,可以从中断处继续同一场战斗 |
| **不影响正式存档** | 中断存档**只动 WS 缓存 + Game.status**,绝不写 `hero_campaign_states` |
| **可识别** | 玩家下次回来能看见"上次有未完成战局" |
| **可清理** | 重新 `/start` 或 `/advance` 成功后,中断存档被自动丢弃 |
| **可调试** | 端到端测试 |

---

## 3. 数据流

### 3.1 触发时机

| 事件 | 触发什么 |
|------|---------|
| WS `onclose` | 标记该 game_id 对应的玩家 "disconnected" |
| `enterGame` 页面卸载 (`beforeunload`) | 调 `POST /games/{id}/interrupt-save` |
| 玩家 5 分钟没动 | 后端异步标记 "abandoned-in-progress" |
| 玩家主动点"暂离"按钮 | 立即调 `POST /games/{id}/interrupt-save` |

### 3.2 储存什么

**`hero_campaign_states` 不动**。Interrupt-save 只记:
- `Game.status` = `playing`(保持不变)
- `Game.battle_config` 不动
- `Player.is_connected` (新列) 标记断线状态
- `last_seen_at` (新列) 时间戳
- `interrupt_saved_at` (新列,Game 表上) 标记最后一次中断存档的时间

> **完全不需要"快照"**.DB 已经是权威状态。

### 3.3 怎么恢复

玩家重连/刷新页面时:
1. `GET /games?user_name=alice` 列出该用户所有 `status == "playing"` 的 game
2. 选一个,前端展示 "上次有未完成战局" + "继续" / "放弃"
3. 选继续 → `POST /games/{id}/rejoin`(已有)→ 拉 `/state` 渲染战场

---

## 4. Schema 改动

```python
# app/models.py — Player 表
class Player(Base):
    ...
    is_connected: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )

# app/models.py — Game 表
class Game(Base):
    ...
    interrupt_saved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
```

**不需要新表**,不加 JSON blob,所有列都是简单标量,迁移轻量。

---

## 5. API 端点

### 5.1 新增

| 端点 | 作用 |
|------|------|
| `POST /games/{id}/interrupt-save` | 标记 `interrupt_saved_at = now()`,`Player.is_connected = False` |
| `GET  /games/{id}/interrupt-status` | 返回该 game 的 `interrupt_saved_at` + 各 player 的 `is_connected/last_seen_at` |
| `GET  /games?status=playing&interrupted=true` | 列出"未完成且中断过"的游戏(给 FE 存档管理) |

### 5.2 复用已有

| 端点 | 复用方式 |
|------|---------|
| `POST /games/{id}/rejoin_by_name` | 玩家从中断恢复时调,reset `is_connected = True` |
| `POST /games/{id}/state` | 拉快照(已有,无需改) |
| WS `?since_seq=N` | 推送中断期间漏掉的事件(已有,无需改) |

---

## 6. 端到端测试 (设计)

`game/tests/test_interrupt_save.py`:

1. `test_disconnect_marks_player_disconnected`
   - 玩家连 WS,发心跳,断 WS → `is_connected == False`, `last_seen_at` 有值
2. `test_interrupt_save_endpoint_writes_timestamp`
   - `POST /games/{id}/interrupt-save` → `interrupt_saved_at` 不为空
3. `test_rejoin_resets_is_connected`
   - 中断 → 玩家 `rejoin_by_name` → `is_connected == True`
4. `test_interrupt_save_does_not_touch_hero_campaign_states`
   - 中断前后 `hero_campaign_states` 完全相同(关键不变量)
5. `test_list_interrupted_games`
   - 多个 game,只列 `status == playing` 且 `interrupt_saved_at != None`
6. `test_advance_clears_interrupt_marker`
   - 战斗胜利后 `/advance`,`interrupt_saved_at` 应当被置 None

---

## 7. 暂离 vs 战败 vs 战斗退出

| 场景 | 触发 | 处理 |
|------|------|------|
| **网络断 5 秒内重连** | WS 抖动 | 不标记 disconnected,`since_seq` 重传 |
| **网络断超过 30 秒** | 真的断线 | 标记 disconnected,游戏保持 playing |
| **玩家主动关浏览器** | `beforeunload` | POST `/interrupt-save` |
| **玩家在 mod UI 主动点"暂离"** | UI 按钮 | POST `/interrupt-save` |
| **玩家点了"放弃"** | `/abandon` | `active_mainline = None`,但 Game 行不删,保留 `status = finished` |
| **玩家战败** | engine 检测 | `Game.status = "finished"`,`/advance` 走 `victory/lost` 分支 |

---

## 8. 与现有系统的边界

| 不变量 | 强制方式 |
|-------|---------|
| `hero_campaign_states` 只在 `/advance` 写 | 现有代码已经如此,**新代码不引入写** |
| 中断存档**不能**被用于跨章节恢复 | `interrupt_saved_at` 校验:rejoin 时若 `Game.status == finished` 则返回 410 |
| 中断存档**不影响**正式存档 | 完全不动 `PlayerProfile.mercenary_roster_state/hero_inventory/hero_campaign_states` |
| 中断存档 7 天自动清理 | 单独的后台 cron(暂不实现,留 TODO) |

---

## 9. 不在本次范围

- 中断存档的 UI 弹窗(由 FE 单独提需求)
- 跨章节的快速继续(需要先打完整章节 → 不属于中断存档语义)
- 多人观战/接力(留到 P3+ 单独任务)
- 7 天 cron 清理(留 TODO)

---

## 10. 实施顺序(待批准后)

1. DB migration:`Player.is_connected`, `Player.last_seen_at`, `Game.interrupt_saved_at`
2. WS gateway 增强:on_disconnect 时异步更新 `is_connected = False`
3. 新端点 `POST /games/{id}/interrupt-save` 和 `GET /games/{id}/interrupt-status`
4. `/games` 列表端点扩展:`?interrupted=true` 过滤
5. `/rejoin_by_name` 增强:重置 `is_connected = True`
6. `_persist_mainline_hero_results` 在 `/advance` 时顺手清 `interrupt_saved_at`
7. 端到端测试 6 个
8. 跑全套测试

预计 1-2 小时工作量,无破坏性改动。
