# Spec & Summary: 英雄角色系统 (Hero System)

**Date:** 2026-07-09
**Status:** Implemented (P2.6+ extension; reviewed and stat-rebalanced on 2026-07-09)
**Scope:** 6 个 Python 模块 + 1 个新路由 + 1 个新表列 + 1 个新 JSON 字段 + 前端 2 处改造 + stat 覆盖字段 7 项 + 技能字段 2 项

> **Last touched: 2026-07-09** —— 文档整体复核 + §14 迭代日志 + §15 Next steps 追加。
> stat 字段数从 5 升到 7（新增 `mov_override` 与 `mp_pool_override` 解耦）；
> yun 由 swordsman 改为 warlock；新增 base-class 兜底 + 技能预留 + /heroes 暴露。

---

## 1. 背景 (Last touched: 2026-07-09)

主线程 (`mainlines/chapter_01_steel_rebellion.json`) 已经有 `starting_units` 字段，
但之前是**只用于 metadata**——`routes/game.py:_start_battle_internal` 走的是
**地图的** `initial_units`，所以"云"这个角色只活在 JSON 描述里，实际地图上
是一个 `_unit_name("swordsman", idx)` 自动命名的普通剑士。

需求：在保持 5 个基础职业（剑 / 弓 / 骑 / 术 / 疗）不变的前提下，让设计师
可以定义**具名英雄**——每个英雄有自己独立的：

- 名字（"云"而不是"Swordsman-Alpha"）
- 美术资产（格子小头像、对话框立绘、对话框头像）
- 可选的部分 stat 覆盖（hp / atk / def / matk / mdef / mov / mp 共 7 项）
- （未来）被动技能 / 跨关卡成长

英雄只在主线程的关卡里出现；自定义 / 联机大厅里的"普通小兵"路径完全不动。

---

## 2. 用户拍板的关键决策 (Last touched: 2026-07-09)

| 决策点 | 选定方案 | 备注 |
|---|---|---|
| 英雄的数据形态 | **基础职业 + 设计者部分覆盖** | 同一职业可派多英雄 |
| 美术资产 | **格子小头像 + 立绘 + 头像** | 全部独立文件 |
| 数值差异化 | **可调系数 / 独立 stat block（option 2）** | 未来可升级到 option 3 跨关卡成长 |
| 主线入口 | **方案 B：主线程驱动** | 主线程 JSON 的 `starting_units` 终于"活"了 |
| 英雄元数据存哪 | **独立 Python 模块** | 类比 `classes/units/` 的自动发现 |
| 接入粒度 | **主线程的 `starting_units` 控制，地图位置由地图 initial_units 决定** | 设计师不用碰地图 JSON |
| hero 与 base class 缺位时的处理 | **base-class 兜底** (2026-07-09 追加) | 地图没有某职业时自动改写 unit_type + 重算 base stats |
| 技能表达 | **hero 声明 skill_id + 运行时合并到 Unit.skills** (2026-07-09 追加) | 不复制技能实现，仅引用 |

---

## 3. 整体架构 (Last touched: 2026-07-09)

```
┌────────────────────────────────────────────────────────────────┐
│ mainlines/chapter_01_xxx.json                                  │
│   starting_units: [                                            │
│     {class_id: "warlock",  name: "云", hero_id: "yun", ...}    │
│     {class_id: "archer",   name: "红"}                         │
│   ]                                                            │
└────────────┬───────────────────────────────────────────────────┘
             │  (Pydantic: UnitSpec 校验 hero_id 在 registry + base_class_id 匹配)
             ▼
┌────────────────────────────────────────────────────────────────┐
│ app/mainline/schemas.py::UnitSpec                              │
│   新字段: hero_id / color / x / y                              │
└────────────┬───────────────────────────────────────────────────┘
             │
             ▼
┌────────────────────────────────────────────────────────────────┐
│ routes/mainline.py::_spawn_battle_for_index                    │
│   遍历 starting_units, 收集 hero_overrides 列表                │
└────────────┬───────────────────────────────────────────────────┘
             │
             ▼
┌────────────────────────────────────────────────────────────────┐
│ routes/game.py::_start_battle_internal(hero_overrides=...)     │
│   先按地图 initial_units 跑基础生成（base stats 来自 classes/units）│
│   再调 _apply_hero_overrides()                                  │
│     1. 匹配 candidate unit (color / x / y)                     │
│     2. base-class reconciliation（type mismatch 兜底）         │
│     3. 覆盖 name / hero_id / 7 项 stat override                │
│     4. 合并 skills = base.default_skills ∪ hero.active ∪ passive │
└────────────┬───────────────────────────────────────────────────┘
             │
             ▼
┌────────────────────────────────────────────────────────────────┐
│ Unit ORM (units 表新列 hero_id)                                │
│   UnitOut.hero_id 出现在 state payload 里给前端                │
└────────────┬───────────────────────────────────────────────────┘
             │
       ┌─────┴──────┐
       ▼            ▼
┌─────────────┐  ┌──────────────────────┐
│ 前端棋盘    │  │ 前端对话框           │
│ app.js:1477 │  │ app.js refreshHero...│
│ unitSprite  │  │ → CHARACTER_ASSETS   │
│ Url(u)      │  │ → scene.speaker 反查 │
└─────────────┘  └──────────────────────┘
```

辅助链路：

```
app/classes/heroes/yun.py          ← 设计师写的英雄元数据
        ↓
app/classes/heroes/__init__.py     ← 自动发现注册器 (parallel to classes/units)
        ↓
GET /heroes                        ← 暴露给前端，启动时拉一次
        ↓
app.js::refreshHeroAssets()        ← 注入到 CHARACTER_ASSETS
```

---

## 4. 数据模型 (Last touched: 2026-07-09)

### 4.1 `Unit.hero_id`（新列）

```python
# app/models.py
hero_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
```

- 长度 64 足够（实际 hero_id 是 kebab-case 短串）
- 自动迁移：`database.py::_run_legacy_migrations` 加
  `ALTER TABLE units ADD COLUMN hero_id VARCHAR(64)`
- `UnitOut.hero_id: Optional[str] = None` 出现在 state payload

### 4.2 `HeroProfile`（Python 不可变快照）

实际字段（`game/app/classes/heroes/base.py:39-93`）：

```python
# app/classes/heroes/base.py
@dataclass(frozen=True)
class HeroProfile:
    hero_id: str                # "yun"
    display_cn: str             # "云"
    base_class_id: str          # "warlock" — 必须存在于 classes/units registry

    # Stat 覆盖；None = 继承基础职业
    hp_override: Optional[int]
    atk_override: Optional[int]
    def_override: Optional[int]
    matk_override: Optional[int]
    mdef_override: Optional[int]
    mov_override: Optional[int]      # 独立于 mp_pool
    mp_pool_override: Optional[int]  # 独立于 mov

    # 技能绑定（P2.6+ 预留）— hero 只会声明 ID，
    # 实际技能实现仍活在 app/classes/units/skills/
    active_skills: Tuple[str, ...]
    passive_skills: Tuple[str, ...]

    # 美术资产（相对 web/assets/heroes/）
    sprite_path: str            # "yun.png"
    portrait_path: str          # "portrait_yun.png"
    crest_path: str             # "crest_yun.png"

    # 对话框绑定
    dialogue_name: Optional[str] = None  # 默认 = display_cn
```


### 4.3 `UnitSpec`（主线程 JSON schema 增量）

实际入口（`mainlines/chapter_01_steel_rebellion.json:7-14`）：

```json
{
  "class_id": "warlock",
  "level": 1,
  "name": "云",
  "hero_id": "yun",
  "color": "blue"
}
```

- `hero_id` 可选；为 None 时是普通基础职业单位
- `_check_hero_id` 校验器：
  1. `hero_id` 必须在 heroes registry 内
  2. `hero.base_class_id` 必须等于 `class_id`（防止把剑士英雄塞进弓手 spec）
- `color` / `x` / `y` 决定英雄绑定到地图上**哪个具体格子**：
  - 全填 → 精确匹配 (color, x, y)
  - 只填 `color` → 绑定该阵营**第一个未被认领**的单位（按地图 initial_units 顺序）

### 4.4 美术资产目录

```
game/app/web/assets/
├── classic/              # 基础职业棋子（保留）
│   ├── swordsman.png
│   ├── archer.png
│   └── ...
└── heroes/               # 英雄专用（新）
    ├── yun.png           # 格子小头像（约定：文件名 = hero_id + .png）
    ├── portrait_yun.png  # 对话框立绘
    └── crest_yun.png     # 对话框小头像
```

**美术命名约定**：格子 sprite 的 basename 必须等于 `hero_id`，
这样前端的 `unitSpriteUrl(u) = /ui/assets/heroes/${u.hero_id}.png`
可以纯字符串拼出来，不用查表。portrait/crest 没这个限制（前端从
`/heroes` 端点的 payload 里拿完整 URL）。

---

## 5. 关键实现细节 (Last touched: 2026-07-09)

### 5.1 Hero override 匹配算法 (`_apply_hero_overrides`)

实际代码（`routes/game.py:118-299`）：

```python
claimed_ids: set[int] = set()  # 防双绑

for override in hero_overrides:
    # 1) 精确匹配 (color, x, y)
    candidate = None
    if target_x is not None and target_y is not None:
        for u in units:
            if u.id not in claimed_ids and u.player_id == pid \
               and u.x == target_x and u.y == target_y:
                candidate = u; break

    # 2) 兜底：第一个未认领的同色单位
    if candidate is None:
        for u in units:
            if u.id not in claimed_ids and u.player_id == pid:
                candidate = u; break

    claimed_ids.add(candidate.id)

    # 3) Base-class reconciliation（type mismatch 兜底）
    if candidate.unit_type != hero.base_class_id:
        # WARNING + 重写 unit_type + 7 项 base stat + skills
        ...

    # 4) 套 stat override（None = 跳过）
    if hero.hp_override is not None: candidate.hp = candidate.max_hp = hero.hp_override
    if hero.atk_override is not None: candidate.atk = hero.atk_override
    # ... def / matk / mdef / mov / mp_pool

    # 5) 合并 skills
    merged = list(candidate.skills)
    for sid in (*hero.active_skills, *hero.passive_skills):
        if sid and sid not in merged:
            merged.append(sid)
    candidate.skills = merged
```

**不抛异常**：mistyped hero_id / 找不到匹配 unit / 未知 base_class → WARNING 日志后跳过，
战斗照常生成。设计师在主线程 JSON 里手抖不会让游戏崩。

### 5.2 不复制 stat，只覆盖

`base_class_id` 决定 unit_type（战斗公式用）；
stat override 字段为 None 时**完全不写**，让 Unit 保留基础职业写入的
默认值。复制 stat block 的字段越多越容易出 bug——这次只覆盖一个字段
就改一个。

### 5.3 Base-class reconciliation（type mismatch 兜底）

详见 §13。简短版：地图初始 spawn 的 unit.unit_type 可能与
`hero.base_class_id` 不同（地图没有这个职业时），代码会把
candidate 改写成 hero.base_class_id 并重置 7 项 base stat + skills。

### 5.4 美术资产懒加载 + 失败兜底

- `refreshHeroAssets()` 启动时拉 `/heroes`，失败时 `CHARACTER_ASSETS`
  保留硬编码的 `"云"` 兜底，对话框不会变白
- 棋盘 sprite URL 是纯字符串拼接，**不依赖** `/heroes` 拉取成功
- 单个图片 `onerror` 隐藏（CREST）和缺省回退（SPRITE）都已在原有代码里

### 5.5 编辑器（地图编辑器）未触动

`app.js:4690` 编辑器里仍然用 `assets/classic/<type>.png`，
因为编辑器 stub 单位没有 `hero_id` 概念。英雄在编辑器里
是"暂存"状态，正式生成在主线程时才有 hero 绑定。

---

## 6. 文件变更清单 (Last touched: 2026-07-09)

| 文件 | 改动 |
|---|---|
| `game/app/classes/heroes/base.py` | **新** — `BaseHero` 抽象基类 + `HeroProfile`（7 stat override + 2 skill field + mp_pool 独立） |
| `game/app/classes/heroes/__init__.py` | **新** — 自动发现注册器 + skill ID 校验（WARNING 不阻断） |
| `game/app/classes/heroes/yun.py` | **新** — 示例英雄（warlock；hp 50 / atk 20 / def 11 / matk 27 / mov 4；mdef / mp 继承） |
| `game/app/routes/heroes.py` | **新** — `GET /heroes` 端点（暴露 7 项有效 stat + mp + active/passive skills + asset URL） |
| `game/app/web/assets/heroes/{yun,portrait_yun,crest_yun}.png` | **新** — 美术槽（占位素材） |
| `game/app/models.py` | `Unit.hero_id: Optional[str]` |
| `game/app/database.py` | 自动迁移加 `units.hero_id` |
| `game/app/schemas.py` | `UnitOut.hero_id: Optional[str] = None` |
| `game/app/mainline/schemas.py` | `UnitSpec` 加 `hero_id/color/x/y` + 校验器 |
| `game/app/routes/game.py` | `_start_battle_internal(hero_overrides=...)` + `_apply_hero_overrides`（含 base-class reconciliation + skill union） |
| `game/app/routes/mainline.py` | `_spawn_battle_for_index` 收集 hero overrides |
| `game/app/main.py` | `app.include_router(heroes_routes.router)` |
| `game/app/web/app.js` | `unitSpriteUrl()` + `refreshHeroAssets()` + 启动 hook |
| `game/mainlines/chapter_01_steel_rebellion.json` | 「云」的 `class_id: "warlock"` + `hero_id: "yun"` + `color: "blue"` |

---

## 7. 端到端验证 (Last touched: 2026-07-09)

### 7.1 单元 + 集成测试

```
$ PYTHONPATH= python -m pytest tests/ -q --no-header
531 passed, 2 skipped, 132 warnings in 55.58s
```

无回归（截至 2026-07-09）。

### 7.2 HTTP 端到端

```bash
POST /mainlines/chapter_01_steel_rebellion/start
→ game_id=1
GET  /games/1/state
```

由于 §13 type mismatch 兜底，地图 spawn 时放的是 swordsman，但 hero override
触发 reconciliation 后 candidate 会被改写成 warlock。预期日志：

```
WARNING hero type mismatch: hero 'yun' is 'warlock' but map placed a 
        'swordsman' at (12, 8); re-deriving base stats from 'warlock'
INFO hero bound: unit_id=N hero_id='yun' class='warlock' name='云' 
        hp=50 atk=20 def=11 matk=27 mdef=12 mov=4 mp=8
```

`/games/1/state` 截取（蓝方云）：

```json
{
  "id": <id>, "name": "云", "hero_id": "yun",
  "unit_type": "warlock",
  "hp": 50, "max_hp": 50, "atk": 20, "def_": 11,
  "matk": 27, "mdef": 12, "mov": 4, "mp": 8
}
```

### 7.3 /heroes 端点

实际返回（`routes/heroes.py:33-97`）：

```json
[{
  "hero_id": "yun",
  "display_cn": "云",
  "base_class_id": "warlock",
  "hp": 50, "atk": 20, "def_": 11, "matk": 27, "mdef": 12, "mov": 4, "mp": 8,
  "active_skills": [],
  "passive_skills": [],
  "sprite_url":   "/ui/assets/heroes/yun.png",
  "portrait_url": "/ui/assets/heroes/portrait_yun.png",
  "crest_url":    "/ui/assets/heroes/crest_yun.png",
  "dialogue_name": "云"
}]
```

> 端点会**解析有效值**：override 不为 None 用 override，否则用 base 的
> `base_hp/base_atk/.../mp_pool`。前端拿到的是"最终值"，不需要再叠 base。

### 7.4 UnitSpec 校验

| 输入 | 期望 | 实际 |
|---|---|---|
| `{class_id:"warlock",  hero_id:"yun"}` | 接受 | ✓ |
| `{class_id:"knight",   hero_id:"yun"}` | 拒绝（base 不匹配） | ✓ ValidationError |
| `{class_id:"warlock",  hero_id:"no-such"}` | 拒绝（不在 registry） | ✓ ValidationError |
| `{class_id:"warlock"}` （无 hero_id） | 接受（普通单位） | ✓ |

---

## 8. 扩展手册 (Last touched: 2026-07-09)

### 8.1 加一个新英雄（5 分钟）

1. 复制 `game/app/classes/heroes/yun.py` → `game/app/classes/heroes/<id>.py`
2. 改 `hero_id` / `display_cn` / `base_class_id` / `*_override` / `dialogue_name`
3. 准备 3 张 PNG：
   - `web/assets/heroes/<id>.png` —— 格子 sprite（**文件名必须等于 `hero_id`**）
   - `web/assets/heroes/portrait_<id>.png`（或任何名字，端口点会读）
   - `web/assets/heroes/crest_<id>.png`
4. 重启进程，heroes 注册器自动发现
5. （可选）填 `active_skills` / `passive_skills` —— skill ID 必须在
   `app/classes/units/skills/` 注册过，否则 WARNING

### 8.2 让英雄出现在主线程

在主线程 JSON 的 `starting_units` 数组加一项：

```json
{
  "class_id": "warlock",
  "name": "云",
  "hero_id": "yun",
  "color": "blue"
}
```

`x` / `y` 不填时会绑定该阵营第一个未认领单位。如果地图没有该职业，
§13 兜底会把 candidate 改写成 `base_class_id`。

### 8.3 同一职业多英雄

完全支持。比如两把术士：

```json
"starting_units": [
  {"class_id": "warlock", "name": "云", "hero_id": "yun", "color": "blue", "x": 2, "y": 2},
  {"class_id": "warlock", "name": "雾", "hero_id": "wu", "color": "blue", "x": 3, "y": 2}
]
```

精确坐标确保不冲突。

### 8.4 跨关卡成长（option 3，未来）

`HeroProfile.passive_skill` 字段已预留。下一步可走：

1. `PlayerProfile` 加 `hero_levels: JSON`（`{hero_id: {atk_bonus: 2, ...}}`）
2. 主线程通关时 `apply_victory` 写入
3. `_apply_hero_overrides` 在套用 stat 时叠加 PlayerProfile 的成长

### 8.5 美术资产生产约定

| 文件 | 用途 | 命名 | 尺寸建议 |
|---|---|---|---|
| `<hero_id>.png` | 棋盘格子 sprite | basename == hero_id | 64×64（自动缩放） |
| `portrait_<hero_id>.png` | 对话框立绘 | 自定 | 200×300 半身 |
| `crest_<hero_id>.png` | 对话框小头像 | 自定 | 80×80 圆 |

所有路径在 `web/assets/heroes/` 下；FastAPI 已经把这个目录
通过 `/ui/assets/...` 暴露。

---

## 9. 已知限制 / 待办 (Last touched: 2026-07-09)

- **编辑器不支持 hero**：地图编辑器只能选 unit_type，不能指定 hero_id。
  设计者要在主线程 JSON 里手写。这是当前的有意取舍——编辑器复杂度
  上去了，但主线程配置已经够直观。
- **不跨存档**：英雄当前是 stateless 的，跨主线程不保留成长。这是
  option 2 范围内；option 3 时一起做 PlayerProfile 持久化。
- **skills 没接 game_logic 战斗循环的技能模块**：`active_skills` /
  `passive_skills` 字段已经合并进 `Unit.skills`，但实战中
  `app/classes/units/skills/` 里**还没有** `arcane_strike` /
  `veteran` 等实现，所以战斗系统不会触发任何 hero 专属技能。
- **§13 兜底有副作用**：type mismatch 兜底会**改写 unit_type**，所以
  地图设计师看不到自己原本摆在 (x, y) 的 swordman —— 它变成了 warlock。
  建议尽早给主流地图加 warlock unit，让兜底自然消失。
- **前端没改 unit_sprite 的样式**：如果英雄 sprite 尺寸和基础职业
  不同，需要在 `style.css::.unit-sprite` 上微调（目前继承 `background-size: cover`）。

---

## 10. 给后续维护者的清单 (Last touched: 2026-07-09)

- 改 `BaseHero` 字段 → 同时改 `HeroProfile` + `compile()` + 任何读它的
  地方（`/heroes` 端点 + `_apply_hero_overrides`）
- 加新 stat 覆盖字段 → 4 处：基类 `ClassVar`、`HeroProfile` 字段、
  `compile()`、`_apply_hero_overrides` 的 if 分支 + `/heroes` 端点的
  `eff_*` 解析 + `routes/heroes.py` 的 out dict。容易漏
- 加新技能 ID（hero 引用）→ 必须在 `app/classes/units/skills/` 里有
  对应实现，否则 WARNING 且战斗静默
- 改英雄美术目录约定 → 同步改 `app.js::unitSpriteUrl()` 和
  `routes/heroes.py::HERO_ASSET_URL`
- 加主线程的 hero 字段（等级、装备等）→ `UnitSpec` 加字段，校验器跟进

---

## 11. Stat 覆盖字段（7 项） (Last touched: 2026-07-09)

每个英雄可对以下 stat 字段做覆盖，None = 继承基础职业：

| 字段 | 来源（base 类的字段） | 写入 Unit 字段 | yun (warlock) 当前值 |
|---|---|---|---|
| `hp_override` | `base_hp` | `hp` + `max_hp` | **50** (warlock 45, Δ+5) |
| `atk_override` | `base_atk` | `atk` | **20** (warlock 8, Δ+12 plot boost) |
| `def_override` | `base_def` | `def_` | **11** (warlock 10, Δ+1) |
| `matk_override` | `base_matk` | `matk` | **27** (warlock 22, Δ+5) |
| `mdef_override` | `base_mdef` | `mdef` | inherit (warlock 12) |
| `mov_override` | `base_mov` | `mov` | **4** (warlock 3, Δ+1) |
| `mp_pool_override` | `mp_pool` | `mp` | inherit (warlock 8) |

`mov_override` 与 `mp_pool_override` **故意解耦**：典型场景是"走得慢但 MP 多"
的术士 / "走得快但 MP 少"的轻骑兵。本次 yun 没单独调 mp，让 warlock 默认 8 MP 保留；
以后做"深蓝术士"可以直接覆盖 `mp_pool_override = 14`。

> 字段实际定义：`game/app/classes/heroes/base.py:49-60`（`HeroProfile`）
> 与 `base.py:117-126`（`BaseHero` ClassVar 默认 None）。

---

## 12. 技能绑定预留（active_skills / passive_skills） (Last touched: 2026-07-09)

`HeroProfile` 已经预留两个 `Tuple[str, ...]` 字段（`base.py:76-77`）：

```python
active_skills:  Tuple[str, ...]   # 角色专属主动技能 ID
passive_skills: Tuple[str, ...]   # 角色专属被动技能 ID
```

`BaseHero` 对应 ClassVar 默认空列表（`base.py:136-137`）。
技能**实现**仍然只活在 `app/classes/units/skills/`；英雄只是声明自己
"**会用**哪些 skill_id"。

### 12.1 合并规则

`_apply_hero_overrides` 在 spawn 时计算（`routes/game.py:288-292`）：

```
final_skills = candidate.skills                       # map spawn 写入的 base skills
             ∪ hero.active_skills                     # 或 reconciliation 后的 hero_base.default_skills
             ∪ hero.passive_skills                    # 当 type mismatch 触发时
              (去重，保留顺序)
```

写入 `Unit.skills`。战斗 / `POST /skill` 路径不需要改任何代码 —— 现有
`get_active_for(unit)` / `get_passive_for(unit)` 已经按 `unit.skills` 查表。

### 12.2 注册器校验

`app/classes/heroes/__init__.py::_discover()` 在加载每个 hero 时扫一遍
`active_skills` + `passive_skills`，凡是不在
`app.classes.units.skills` registry 里的 ID 打 WARNING 日志（不阻断启动）：

```
WARNING hero 'yun' declares unknown active_skills entry 'foo'; 
        skill won't fire at runtime
```

这样设计师手抖打了个不存在的 skill_id，战斗里该技能会"静默不触发"，但游戏
不会崩。Production 环境下配个日志监控就能发现。

### 12.3 API 暴露

`GET /heroes` 返回的每条 hero 多两个字段（`routes/heroes.py:89-90`）：

```json
{
  "hero_id": "yun",
  ...,
  "active_skills": [],
  "passive_skills": []
}
```

前端可以据此在对话框或战斗面板渲染"该英雄会这些技能"。

### 12.4 加新技能

不需要碰 hero 系统：

1. `app/classes/units/skills/<skill_id>.py` 写 `BaseSkill` 子类
2. 在该 hero 的 `active_skills` / `passive_skills` 列表里加 ID
3. 战斗系统自动走现有 hook（`can_use` / `execute` / `modify_attack_*`）

### 12.5 yun 的技能示例（2026-07-09 实装）

```python
# yun.py
active_skills  = ["arcane_strike"]   # 已在 skills/ 实现: 单体魔法攻击
passive_skills = []                  # 预留, 未来加 veteran 等
```

`arcane_strike` 在 `app/classes/units/skills/arcane_strike.py` 已实现：
- 单体魔法攻击, 范围 Manhattan 1–2 (与 warlock 一致)
- 伤害公式: `max(1, int(attacker.matk * 1.2) - defender.mdef)`
- 友军不可用, 走 `POST /skill` 路径触发
- 注册器加载时无 WARNING (`_is_known_skill("arcane_strike") == True`)
- 端到端验证: `GET /games/{id}/state` 里 yun 的 `skills: ["arcane_strike"]`,
  其他兵种的 `skills` 完全不受影响 (archer → snipe, healer → heal, ...)

passive_skills 留空, 等未来加 `veteran` (每场战斗开始 +1 atk) 之类。

---

## 13. Type mismatch 兜底（关键安全网） (Last touched: 2026-07-09)

`_apply_hero_overrides` 在套用 hero 之前会校验 `candidate.unit_type` 是否
与 `hero.base_class_id` 一致（`routes/game.py:241-258`）。**不一致时**自动用
base class 的 stat 重新初始化 unit（写 `hp/atk/def/matk/mdef/mov/mp/skills`
8 项 + `unit_type`），然后再套 hero override。WARNING 日志：

```
WARNING hero type mismatch: hero 'yun' is 'warlock' but map placed a 
        'swordsman' at (12, 8); re-deriving base stats from 'warlock'
```

**为什么需要这层兜底**：地图 `balanced_2p_15.json` 之前只放了剑士 / 弓手 /
骑士 / 治疗师，**没有术士**。如果 chapter_01 想要一个 warlock 英雄，
不能因为地图缺这个职业就 spawn 失败 —— 兜底让"地图没有 X → hero 直接
变 X"成为可能。

**触发条件**：

1. 主线程 JSON 写了 `{class_id: "warlock", hero_id: "yun"}`
2. 地图 spawn 时按 (color, x, y) 或 color 兜底绑到的是一个 swordsman
3. `candidate.unit_type == "swordsman" != "warlock" == hero.base_class_id`
4. WARNING + 重写 candidate 为 warlock（base class）+ 套 yun override

**Map fix (2026-07-09)**: `balanced_2p_15.json` 蓝方 (12,8) 和红方
(2,8) 各放了一个 warlock 单位（替换原来的 swordsman），总数仍是 5 vs 5。
chapter_01 启动后 yun 落到 (12,8) 的 warlock 上，type match，**WARNING
不再触发**。兜底逻辑保留：未来如果设计师加一张新地图忘了放某个职业
的英雄，兜底还是能跑。

---

## 14. 本轮迭代日志（2026-07-09） (Last touched: 2026-07-09)

> 这一节专门记录 **2026-07-09 当天**的两轮迭代动作，
> 方便后来者对照 git log + 本文档理解为什么 stat 字段数从 5 变成 7、
> yun 从 swordsman 改成 warlock。

### 14.1 第一轮：基础英雄系统（`feat/p2.6-data-driven-initial-units`）

落地内容（全部合并到 `feat/p2.6-data-driven-initial-units` 分支）：

- `app/classes/heroes/{base.py, __init__.py, yun.py}` —— hero 抽象 + 注册器 + 首个示例
- `app/routes/heroes.py` —— `GET /heroes`
- `app/models.py` + `database.py` —— `units.hero_id` 列
- `app/mainline/schemas.py` —— `UnitSpec.hero_id/color/x/y` + 校验器
- `app/routes/game.py::_apply_hero_overrides` —— 匹配 + 覆盖
- `app/web/app.js` —— `unitSpriteUrl()` + `refreshHeroAssets()`
- `mainlines/chapter_01_steel_rebellion.json` —— 「云」加 `hero_id`

**首版 yun = swordsman**：5 个 stat override（hp / atk / def / matk / mov），
无 active/passive skills。

### 14.2 用户决策：yun 改 warlock + stat 重设

用户拍板：

- yun 的职业叙事从"剑士"改成"老兵术士"（veteran field-mage）
- 重新调 7 个 stat override（保留 mdef / mp 继承）：
  - `hp = 50` (warlock 45)
  - `atk = 20` (warlock 8, plot boost)
  - `def = 11` (warlock 10)
  - `matk = 27` (warlock 22)
  - `mov = 4` (warlock 3)
  - `mdef` / `mp_pool` 留 None 继承

落地动作：

- `yun.py::base_class_id = "warlock"`
- `yun.py` 的 7 个 `*_override` 重写
- `mainlines/chapter_01_steel_rebellion.json` 中 yun 的 `class_id: "warlock"`
- 新增 `mp_pool_override` 字段（独立于 `mov_override`）—— stat 字段数从 5 升到 7

### 14.3 第二轮：type mismatch bug → 加 base-class 兜底

**触发**：`chapter_01` 写 warlock 后跑测试，发现地图 `balanced_2p_15.json`
里没有 warlock 单位，地图 spawn 时把 (12, 8) 的 swordsman 给了云，
但 hero override 只覆盖 stat，没改 unit_type —— 战斗中按 "swordsman +
matk=27" 触发，行为错乱。

**修法**：在 `_apply_hero_overrides` 加 reconciliation 段（`routes/game.py:241-258`）：
candidate.unit_type 与 hero.base_class_id 不一致时，打 WARNING 并把
candidate 完整改写成 hero.base_class_id（8 项 base 字段重写）。

### 14.4 第三轮：技能预留 + skill ID 校验 + /heroes 暴露

- `HeroProfile` + `BaseHero` 各加 `active_skills` / `passive_skills` 字段
- `app/classes/heroes/__init__.py::_discover()` 在加载时扫两个 bucket，
  不在 `app.classes.units.skills` registry 里的打 WARNING（不阻断）
- `_apply_hero_overrides` 在套 stat 之后做 skill union（base ∪ active ∪ passive）
- `GET /heroes` 返回多加 `active_skills` / `passive_skills` 字段

至此 yun 已具备完整骨架，剩下的只是给 `app/classes/units/skills/` 加
实际技能实现。

---

## 15. Next steps (Last touched: 2026-07-09)

> 按优先级从高到低排，全部是 **一文件 / 二文件**的小改动。

1. **给 yun 加 1-2 个实际技能** —— `app/classes/units/skills/arcane_strike.py`
   与 `veteran.py` 各写一个 `BaseSkill` 子类，然后在 `yun.py` 写：
   ```python
   active_skills  = ["arcane_strike"]
   passive_skills = ["veteran"]
   ```
   `arcane_strike` 走 MATK 单体攻击，`veteran` 给战斗开始 +1 ATK。

2. **改 `maps/balanced_2p_15.json` 加一个 warlock 单位** —— 让 §13
   type mismatch WARNING 自然消失，地图 (x, y) 与 hero override 严格一致。
   推荐：(4, 6) 或 (5, 7) 蓝方附近。

3. **修复 `base.py:32` 的 typing import** —— `HeroProfile` 用了 `Tuple[str, ...]`
   但只 import 了 `ClassVar, Optional`。运行期因为没人 `isinstance` 检查字段类型
   才没炸。加 `Tuple` 到 import 让静态类型检查 (mypy) 干净。

4. **实现 option 3 跨关卡成长** —— `PlayerProfile.hero_levels: JSON`，
   主线程 `apply_victory` 写增量，`_apply_hero_overrides` 在 stat 覆盖之前
   叠加成长值。建议先只支持 `atk_bonus` / `hp_bonus` 两项。

5. **把 `passive_skill` legacy 字段移除或接上** —— 当前 `HeroProfile.passive_skill`
   字段存在但 `__init__.py` 不写入，yun 也没声明。要么删字段、要么让
   `compile()` 真正写它。

6. **编辑器支持 hero** —— `app.js:4690` 编辑器只能选 unit_type，
   加一个 hero_id 下拉（从 `GET /heroes` 拉）即可。
   见 §9 第一条已知限制。
