# Save / Suspend 设计 (v2,2026-07-13) — 借鉴 FE8 + AW

> 上一版 (`2026-07-13-interrupt-save-design.md`) 走的是"我猜的"路线。
> 翻完 `refs/fireemblem8u` 和 `refs/Advance-Wars-v2` 后,基于真实参考重写。
> 等学长 review 批准后再实现。

---

## 0. 摘要(结论先行)

| 设计点 | 上一版(我猜) | 本版(借鉴) | 来源 |
|-------|--------------|------------|------|
| Save 类型 | 1 种 + 1 interrupt 列 | **2 类:Game save + Suspend save** | **FE8 `SAVEBLOCK_KIND_GAME` / `SAVEBLOCK_KIND_SUSPEND`** |
| Save 数量 | 1 个 | **3 个 Game slot + 1 个 Suspend slot** | **FE8 `SAVE_ID_GAME0/1/2 + SAVE_ID_SUSPEND`** |
| 触发时机 | 断线 / 离开 | **断线 / 离开 + 多个游戏循环点(phase 切换、行动中)** | **FE8 `SUSPEND_POINT_*`** |
| 存储位置 | DB 加列 | DB 单独表 + 现有 Game 表(可中断挂载) | FE8 SRam 分块 + 我方 DB 简化 |
| Hero 长期值 | 明确不动 | 明确不动(测试守门) | 不变 |

---

## 1. 参考项目调研笔记

### 1.1 FE8(`fireemblem8u/`,C 反编译)

#### 1.1.1 Save 架构

`fireemblem8u/include/bmsave.h:22-32`:
```c
enum save_chunk_index {
    SAVE_ID_GAME0,        // 正式存档 slot 0
    SAVE_ID_GAME1,        // 正式存档 slot 1
    SAVE_ID_GAME2,        // 正式存档 slot 2
    SAVE_ID_SUSPEND,      // 中断存档(战斗中)
    SAVE_ID_SUSPEND_ALT,  // 备用(联机/测试)
    SAVE_ID_ARENA,        // 竞技场
    SAVE_ID_XMAP,
    SAVE_ID_MAX
};

enum {
    SAVEBLOCK_KIND_GAME,     // 正式
    SAVEBLOCK_KIND_SUSPEND,  // 中断
    SAVEBLOCK_KIND_ARENA,
    SAVEBLOCK_KIND_XMAP,
    SAVEBLOCK_KIND_INVALID = -1
};
```

**关键事实**:
- FE8 有 **3 个 Game 存档 + 1 个 Suspend 中断存档**
- 两者在 SRam 里**分别存放在不同区域**:
  - `suspendSaveBlocks[2]` @ 0x00D4 (size 0x1F78 ≈ 8KB / 块)
  - `gameSaveBlocks[3]`   @ 0x3FC4 (size 0xDC8  ≈ 3.5KB / 块)

#### 1.1.2 Game vs Suspend 内容差异

`bmsave.h:350-385`:
```c
struct GameSaveBlock {        // 0xDC8 bytes — 关卡结束后存档
    PlaySt playSt;
    GameSavePackedUnit units[51];   // 只有 BLUE 一方(玩家已成型)
    supplyItems;
    pidStats;                       // BWL 数据(kills/deaths)
    chapterStats;                   // 战绩
    permanentFlags;
    bonusClaimFlags;
    wmStuff;                        // 大地图进度
    dungeons[2];
};

struct SuspendSaveBlock {     // 0x1F78 bytes — 战斗中断时存档
    PlaySt playSt;
    ActionData action;               // 当前正在进行的行动 ★
    SuspendSavePackedUnit blueUnits[51];
    SuspendSavePackedUnit wmMonsterUnit;
    SuspendSavePackedUnit redUnits[50];   // ★ 多了红/绿
    SuspendSavePackedUnit greenUnits[10];
    Trap traps[TRAP_MAX_COUNT];          // ★ 陷阱
    supplyItems;
    pidStats;
    chapterStats;
    menuOverride[0x10];                 // ★ 菜单禁用
    permanentFlags;
    chapterFlags[7];                    // ★ chapter 临时 flag
    wmStuff;
    dungeon;
    int eventSlotCnt;                   // ★ 事件计数器
};
```

**关键观察**:
- **Suspend 是 Game 的超集** + 行动中状态(action/traps/red+green units/chapter flags)
- Suspend **不存 BWL 战绩**(那是关卡结束才结算的)
- Suspend **不存 dungeons[2]**(只存当前 dungeon)

#### 1.1.3 Suspend ↔ Game 链接

`bmsave.h:73` + `bmsave.c:80-85`:
```c
struct GlobalSaveInfo {
    ...
    u8 last_game_save_id;      // 上次操作的 game slot
    u8 last_suspend_slot;      // 上次 suspend 关联的 game slot
};

struct PlaySt {  // 战斗/世界状态(同时被 Game 和 Suspend 存)
    ...
    u8 gameSaveSlot;           // ★ 这个 PlaySt 属于哪个 game slot
};
```

`bmsave.c:78-87` — 删除 game save 时级联失效 suspend:
```c
void InvalidateGameSave(int index) {
    struct SaveBlockInfo chunk;
    struct PlaySt play_st;

    if (IsValidSuspendSave(SAVE_ID_SUSPEND)) {
        ReadSuspendSavePlaySt(SAVE_ID_SUSPEND, &play_st);
        if (play_st.gameSaveSlot == index)   // ★ 检查链接
            InvalidateSuspendSave(SAVE_ID_SUSPEND);
    }
    chunk.kind = SAVEBLOCK_KIND_INVALID;
    WriteSaveBlockInfo(&chunk, index);
}
```

#### 1.1.4 Suspend 触发点(自动写)

`fireemblem8u/src/` 内 `WriteSuspendSave(SAVE_ID_SUSPEND)` 调用于:
- `bm.c:480` — `BmMain_SuspendBeforePhase` —— **phase 切换前** (SUSPEND_POINT_PHASECHANGE)
- `bmbattle.c:2221` —— **战斗结算后**
- `cp_decide.c:70` —— **enemy/player phase 开始** (SUSPEND_POINT_BSKPHASE / SUSPEND_POINT_CPPHASE)
- `playerphase.c:210` — `PlayerPhase_Suspend` —— **玩家回合开始,等待行动** (SUSPEND_POINT_PLAYERIDLE)
- `playerphase.c:793` —— **玩家单位行动中** (SUSPEND_POINT_DURINGACTION)
- `bmtrap.c:213`, `bmarena.c:655` —— trap / arena 触发

> **关键洞察**: FE8 **不是只在断线时存**。它在游戏的**每个自然停顿点**都存 suspend。玩家 B 键暂停时,最近的 suspend 已经在那里。

#### 1.1.5 玩家菜单

`include/savemenu.h:30-50`:
```c
enum {
    MAIN_MENU_RESUME     = 0,   // 续接(读 suspend)
    MAIN_MENU_RESTART    = 1,   // 重玩本关(读 game)
    MAIN_MENU_COPY       = 2,   // 复制 game slot
    MAIN_MENU_ERASE      = 3,   // 删除 game
    MAIN_MENU_NEW_GAME   = 4,   // 新游戏
    MAIN_MENU_EXTRAS     = 5,   // 额外(链接竞技场/音效室/支援/地图)
    MAIN_MENU_INVALID    = 6,   // 占位
    MAIN_MENU_7          = 7,   // 占位
    MAIN_MENU_EXIT       = 8,   // 退出
};
```

`src/savemenu.c:1326-1342` 关键 switch:
```c
} else if (proc->main_sel_bitfile & 1) {       // MAIN_MENU_OPTION_RESUME
    ReadSuspendSave(3);                          // 读 SUSPEND
    SetNextGameActionId(GAME_ACTION_4);
} else if (proc->main_sel_bitfile & 0x82) {     // RESTART or COPY
    ReadGameSave(proc->sus_slot);                // 读 GAME
    SetNextGameActionId(proc->sus_slot + 1);
} else if (proc->main_sel_bitfile & 0x10) {     // ERASE
    SetNextGameActionId(GAME_ACTION_EVENT_RETURN);
}
```

#### 1.1.6 FE8 关键不变量

1. **Suspend 总是关联到具体 game slot**(`play_st.gameSaveSlot`)
2. **删 game 时级联失效 suspend**
3. **Suspend 内容比 Game 大**(因为要存行动中状态)
4. **Suspend 在 phase 切换、行动中、玩家回合开始都自动写**(不需要玩家主动操作)
5. **RESUME 用 suspend,RESTART 用 game** —— 语义清晰

---

### 1.2 Advance-Wars-v2(`refs/Advance-Wars-v2`,Java)

#### 1.2.1 Save 架构

`src/engine/Save.java:32-44`:
```java
public class Save {
    final String path = "saves/";

    public void SaveGame() {
        // 写到 saves/savegame.properties
        FileWriter fstream = new FileWriter(path + "savegame.properties");
        ...
    }
    public void LoadGame() {
        // 读 saves/savegame.properties
        Properties configFile = new Properties();
        configFile.load(new FileInputStream(...));
        ...
    }
}
```

#### 1.2.2 Save 内容

`SavePlayerData` + `SaveCityData` + `SaveUnitData` 三块:

```
Map = Basic
CurrentPlayer = 0
Days = 2
Units = 3

# Player Data
Player0_Type = Andy
Player0_Defeated = false
Player0_Team = 1
Player0_Money = 200
...

# City Data
City0_Type = Barracks
City0_Owner = 1
City0_Health = 20
...

# Unit Data
Unit0_Type = Mechanic
Unit0_Owner = 0
Unit0_Health = 52
Unit0_Ammo = 10
Unit0_Fuel = 997
Unit0_X = 7
Unit0_Y = 7
Unit0_Acted = true
```

#### 1.2.3 AW 关键观察

1. **没有 Suspend / Game 区分** —— 只有一种 save
2. **单 slot** —— 一个 `savegame.properties`
3. **每个属性单独一行** —— 人类可读、可手动修改
4. **覆盖式写** —— 每次 SaveGame() 都覆盖
5. **不存 turn/phase 状态** —— 简化(每个回合结束自动存)
6. **属性化格式** —— 简化版 FE8(`PackedUnit` 的字段逐个展开)

#### 1.2.4 AW 关键不变量(弱)

- AW 完全没有 Suspend 概念 —— **缺中断存档**
- 玩家要"暂停"就保持窗口打开 —— 不关电脑
- 这是一个**设计缺陷**(对比 FE8)

---

### 1.3 其他参考项目

| 项目 | Save 机制 | 备注 |
|------|----------|------|
| `ice-emblem` | 无 | 简化到只有 ai/action/display 等核心 |
| `FreeWars` | 无 | 商业 FE8 复刻,源码是 Lua,没看到 save 模块 |
| `PyWars` | 无 | pygame AW 风格,无存档 |
| `AdvanceWarsClone` | 无 | 简化版,无 save 机制 |

> **结论**: Save 机制真正可借鉴的只有 **FE8** 和 **AW-v2**。FE8 是设计参考,AW-v2 是**反例**(说明不区分 Suspend/Game 的代价)。

---

## 2. BattleBlitz 设计(基于 FE8 风格)

### 2.1 存档种类

| 类型 | 数量 | 触发 | 内容 |
|------|------|------|------|
| **Game Save**(正式) | 3 slot | 玩家在菜单点 "SAVE" / 通关后 | 主线进度 + Hero 长期成长 |
| **Suspend Save**(中断) | 1 slot | 战斗 phase 切换 / 行动中 / 手动暂离 / 关闭浏览器 | 当前 Game 战斗态(完整快照) |

### 2.2 数据模型

#### 2.2.1 `GameSaveSlot` 表(新)

```python
class GameSaveSlot(Base):
    """A formal mainline save (one per slot)."""
    __tablename__ = "game_save_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    slot_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 0/1/2
    mainline_id: Mapped[str] = mapped_column(String(64), nullable=False)
    chapter_index: Mapped[int] = mapped_column(Integer, nullable=False)
    saved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    # 快照:战斗生成参数(不进 game_session 表,这样删 game 也能恢复)
    last_battle_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # ← snapshot 内容:{hero_campaign_states, mercenary_roster_state,
    #                   hero_inventory, gold, mainline_progress, ...}

    __table_args__ = (
        UniqueConstraint("user_name", "slot_index", name="uq_save_slot_per_user"),
    )
```

#### 2.2.2 `SuspendState` 表(新,单行)

```python
class SuspendState(Base):
    """The single mid-battle suspend slot. One row per user_name."""
    __tablename__ = "suspend_states"

    user_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    # 关联的 game_save_slot
    game_save_slot: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    game_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    battle_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    suspend_point: Mapped[str] = mapped_column(String(32), nullable=False)  # phase_change / player_idle / during_action / manual
    saved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    # 完整 Game 状态快照(Unit, Player, Tile, ActionLog, action_data)
    # 不存 hero_campaign_states —— suspend 与正式 hero 数值解耦
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
```

### 2.3 触发时机(参考 FE8 SUSPEND_POINT_*)

| 触发点 | FE8 对应 | 我方对应 | 调用 |
|-------|---------|---------|------|
| Phase 切换(player→enemy, enemy→ally) | `SUSPEND_POINT_PHASECHANGE` | `engine.end_turn()` | 自动 |
| 玩家回合开始,等待操作 | `SUSPEND_POINT_PLAYERIDLE` | `engine.begin_player_turn()` | 自动 |
| 单位行动中(moving/attacking) | `SUSPEND_POINT_DURINGACTION` | `engine.dispatch_action()` 提交后 | 自动 |
| 玩家手动"暂离" | (B-button suspend) | `POST /games/{id}/suspend` | 手动 |
| 浏览器关闭/WS 断开 | — | `WS onclose` / `beforeunload` | 隐式 |
| 战斗结束(胜利/失败) | — | `engine.set_status("finished")` | 清理 |

### 2.4 玩家菜单(模拟 FE8)

```
┌──────────────────────────────────────────────┐
│  Save Menu                                    │
│  ────────────────────────────────────────────│
│  Slot 0: chapter_01  (2026-07-13 20:38)     │
│  Slot 1: <empty>                              │
│  Slot 2: <empty>                              │
│                                                │
│  [RESUME]   ← 只在有 Suspend 时显示           │
│  [SAVE]                                        │
│  [RESTART]                                     │
│  [COPY]                                        │
│  [ERASE]                                       │
│  [NEW_GAME]                                    │
│  [EXIT]                                        │
└──────────────────────────────────────────────┘
```

### 2.5 不变量(测试守门)

```python
# 测试 1: Suspend 不污染 hero_campaign_states
def test_suspend_does_not_touch_hero_state():
    # /start → /suspend → /start
    # hero_campaign_states 与初始完全相同

# 测试 2: Game save 持久化 hero
def test_game_save_persists_hero_state():
    # 战斗胜利 → SAVE → 新设备 LOAD → hero_campaign_states 一致

# 测试 3: Save slot 3 满
def test_save_slot_overflow():
    # 写满 3 slot → 第 4 次提示"覆盖?"

# 测试 4: 删除 game 时级联 suspend
def test_erase_cascades_suspend():
    # Save 1 → Suspend → Erase 1 → Suspend 失效

# 测试 5: Suspend 触发点
@pytest.mark.parametrize("trigger", [...])
def test_suspend_writes_at_each_phase_point(trigger):
    ...
```

### 2.6 与现有系统的边界

| 不变量 | 强制方式 |
|-------|---------|
| `hero_campaign_states` 只在 `/advance` 写 | 测试 + 代码注释 + 不在 suspend 路径上写 |
| Game save 包含 hero 长期值 | 快照时读 `hero_campaign_states`,LOAD 时还原 |
| Suspend 包含游戏状态,**不**含 hero 长期值 | 快照时**不读** `hero_campaign_states` |
| Suspend 自动失效(玩家 `/advance` 成功) | `_persist_mainline_hero_results` 完成后清 `SuspendState.snapshot` |

---

## 3. 不在本次范围

- Save slot UI(由 FE 提需求,后端先出 API)
- 复制 Save(COPY)功能 —— 留 TODO
- 存档加密 / 校验和(FE8 有,我们不需要,SQLite 自带)
- 跨章节的 quick-save(不是中断存档语义)
- 多人观战 / 接力
- 7 天 cron 清理(留 TODO)

---

## 4. 实施顺序(批准后)

### Phase 1: 数据模型(小,无破坏性)
1. 新增 `GameSaveSlot` 表 + migration
2. 新增 `SuspendState` 表 + migration
3. Pydantic schema:`GameSaveSlotOut`, `SuspendStateOut`

### Phase 2: 自动 Suspend 触发(参考 FE8)
1. `engine.end_turn()` 末尾 → 写 SuspendState
2. `engine.begin_player_turn()` 末尾 → 写 SuspendState
3. `engine.dispatch_action()` 提交后 → 写 SuspendState
4. 每次写 Suspend 之前清旧 Suspend(避免堆积)

### Phase 3: API 端点
1. `GET  /saves?user_name=...` —— 列出 3 slot + Suspend
2. `POST /saves/save` —— 写入指定 slot
3. `POST /saves/load` —— 从 slot 还原
4. `POST /saves/erase` —— 删除 slot(级联 Suspend)
5. `POST /games/{id}/suspend` —— 手动 suspend

### Phase 4: 关键不变量测试
1. Suspend 不污染 hero
2. Save 持久化 hero
3. Suspend 触发点
4. 级联失效

预计 4-6 小时,改动多但每步独立可测。

---

## 5. 与上一版的差异

| 项 | 上一版 | 本版 |
|----|-------|------|
| 数据模型 | 加列(Game.interrupt_saved_at) | 新表(GameSaveSlot + SuspendState) |
| Save 数量 | 1 个 | 3 + 1 = 4 个 slot |
| 触发点 | 断线 / 离开 | 5+ 个游戏循环点 + 手动 + 断线 |
| 链接关系 | 隐式 | `SuspendState.game_save_slot` 显式 |
| 删除级联 | 不处理 | Suspend 失效 + Game save 级联 |
| Hero 数值 | 不动(对) | 不动(对)+ 测试守门 |
