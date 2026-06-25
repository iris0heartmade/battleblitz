# BattleBlitz LLM Agent — 接口规范

> 版本：v0.1.0 · 适用代码：`game/app/agent/` · `game/app/classes/units/`
>
> 本文档定义 LLM 对手层的全部公共接口：Python API、HTTP 端点变更、数据契约、配置项。
> 目标读者：希望集成、扩展或测试该模块的开发者。
>
> **v0.1.0 → 实施记录**：
> - ✅ 双协议支持（`LLM_PROTOCOL=anthropic|openai`），可走 llama.cpp 本地
> - ✅ 随机性格切换（每回合选一种）
> - ✅ 模板库扩到 80+ 条，覆盖所有动作类型
> - ✅ 详细耗时日志（snapshot / prompt / LLM / execute 各阶段）
> - 🆕 **新加** `GET /games/units` `GET /games/skills` 端点（前端不再硬编码）

---

## 1. 模块结构

```
game/app/agent/
├── schemas.py        # 数据契约（Pydantic 模型 + 错误类型）
├── snapshot.py       # DB → GameSnapshot（含战争迷雾）
├── legal_actions.py  # 枚举合法动作（含伤害预估）
├── llm_client.py     # Anthropic SDK 封装（tool_use 强制）
├── prompt.py         # jinja2 模板 + 性格预设
├── reactions.py      # 情感反应系统（模板库 + 事件检测）
├── agent.py          # LLMAgent 编排器（含反应检测）
├── integration.py    # dispatch_ai_turn 分发器（含 ActionLog 落库）
└── __init__.py       # 公开 API
```

`__init__.py` 暴露两个名字：

```python
from app.agent import LLMAgent, dispatch_ai_turn
```

---

## 2. Python 公共 API

### 2.1 `LLMAgent`（`game.app.agent.agent`）

主入口。一个 `LLMAgent` 实例 = 一个 AI 玩家；可在多个回合间复用。

#### 构造

```python
LLMAgent(
    llm_client: LLMClient,
    personality: str = "balanced",
    *,
    max_retries: int = 2,
    max_decisions_per_turn: int = AI_MAX_ACTIONS_PER_TURN,  # 5
    think_delay: float = 0.0,
    max_reactions_per_turn: int = 3,
    reaction_rng_seed: int | None = None,
)
```

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `llm_client` | `LLMClient` | 必填 | 复用同一 client（一般是 `get_default_llm_client()`）|
| `personality` | `str` | `"balanced"` | 见 §2.6 性格预设 |
| `max_retries` | `int` | 2 | 单次决策失败最多重试次数（实际尝试 = `max_retries + 1`）|
| `max_decisions_per_turn` | `int` | 5 | 硬性行动上限（防 bug 卡死）|
| `think_delay` | `float` | 0.0 | 每次决策间隔秒数；生产环境填 `AI_THINK_DELAY_SECONDS = 1.2` |
| `max_reactions_per_turn` | `int` | 3 | 一次回合最多输出几条被动反应（"被打/被击杀"）|
| `reaction_rng_seed` | `int \| None` | `None` | 模板随机种子；测试时可固定 |

#### `await take_turn(session, game, player, *, budget_left) -> TurnMetrics`

走完一个 AI 玩家的整个回合。**会自动执行**每一步决策（落库 + 写 `ActionLog`）。

```python
metrics = await agent.take_turn(
    session, game, player, budget_left=2,
)
# metrics.actions_taken, .llm_calls, .llm_retries,
# .fallback_used, .input_tokens, .output_tokens,
# .decisions, .reactions
```

| 异常 | 触发条件 |
|------|----------|
| `sqlalchemy.exc.SQLAlchemyError` | DB 写入失败 |
| 任意被 LLM 客户端抛出的异常 | 已被内部 try/except 捕获并降级为回退动作 |

**降级保证**：当 LLM 三次都失败时，会自动切换到 `_rules_ai_pick` 选出的动作，并把 `plan.fallback = True`、`plan.reason` 以 `[兜底]` 开头。

#### `await decide_one(session, game, player, *, budget_left, action_count=0) -> ActionPlan`

只决策、不执行。便于单测和 prompt 调试。

#### 内部方法（被单测用到，不建议外部直接调用）

| 方法 | 用途 |
|------|------|
| `_parse_response(response: LLMResponse) -> AgentAction` | 解析 LLM 的 `tool_use` 块 |
| `_validate_action_id(action: AgentAction, legal: list[LegalAction]) -> None` | 检查 `action_id` 在合法列表中 |
| `_ask_llm_with_retry(system, user, legal) -> ActionPlan` | 含重试 + 兜底 |

---

### 2.2 `dispatch_ai_turn(session, game, player) -> int`

`game_logic.ai_take_turn` 的 drop-in 替代品。按 `player.agent_kind` 分发：

| `agent_kind` | 行为 |
|--------------|------|
| `"rules"` | 调原 `ai_take_turn`（规则 AI）|
| `"llm"` | 构造 `LLMAgent` 并跑一整个回合；**同时把情感反应写入 `ActionLog`**；异常时回退到规则 AI |
| 其他 / 缺省 | 走规则 AI + warning 日志 |

```python
# game/app/routes/turns.py 已经这样用
from app.agent.integration import dispatch_ai_turn
actions = await dispatch_ai_turn(session, game, current_player)
```

返回执行的步数（与原 `ai_take_turn` 一致）。

---

### 2.3 `LLMClient`（`game.app.agent.llm_client`）

Anthropic 兼容 API 客户端。**支持自定义 base URL**，可对接 minimaxi、OpenRouter、本地 llama.cpp server 等。

#### 构造

```python
LLMClient(
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    *,
    timeout: float = 30.0,
    max_retries: int = 2,
)
```

参数缺省时从环境变量读（见 §4 配置）。

#### `await chat(system, user, *, tool=None, max_tokens=1024, temperature=0.7) -> LLMResponse`

单次对话。强制 `tool_choice={"type": "any"}` —— 模型必须调工具（默认 `choose_action`）。

```python
resp = await client.chat(
    system="你是战棋指挥官...",
    user="[回合 1 · 剩余行动 2] ...",
)
if resp.tool_name == "choose_action":
    action_id = resp.tool_input["action_id"]
    reason = resp.tool_input["reason"]
```

#### `LLMResponse` 数据类

| 字段 | 类型 | 说明 |
|------|------|------|
| `text` | `str` | 模型返回的自由文本（通常为空，因为强制 tool_use）|
| `tool_name` | `str \| None` | 调用的工具名；非空 = 成功结构化输出 |
| `tool_input` | `dict` | 工具参数（`{"action_id": "...", "reason": "..."}`）|
| `stop_reason` | `str` | 原始 stop_reason（`tool_use` / `end_turn` 等）|
| `usage` | `TokenUsage` | token 消耗 |
| `raw` | `Any` | 原始 SDK response，调试用 |

#### `await health_check() -> bool`

轻量 liveness 探测（发 8 token 的 ping）。

---

### 2.4 数据契约（`game.app.agent.schemas`）

#### `GameSnapshot`

发给 LLM 的完整局面。

| 字段 | 类型 | 说明 |
|------|------|------|
| `turn` | `int ≥ 1` | 当前回合数 |
| `budget_left` | `int ≥ 0` | 剩余行动数 |
| `action_count` | `int` | 本回合已用行动数 |
| `my_units` | `list[UnitView]` | 我方所有存活单位 |
| `visible_enemies` | `list[UnitView]` | 视野内敌人 |
| `fog_enemies` | `list[FogUnit]` | 已知存在但不可见（仅坐标）|
| `my_castles` | `list[(x, y)]` | 我方城堡坐标 |
| `enemy_castles` | `list[(x, y)]` | 敌方城堡坐标 |
| `unowned_castles` | `list[(x, y)]` | 无主城堡坐标 |
| `map_size` | `int` | 地图边长（默认 15）|
| `map_ascii` | `str` | 15×15 ASCII 地图（含单位标记）|
| `map_legend` | `dict` | 地图字符图例 |

#### `UnitView`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `int` | 单位 ID |
| `type` | `swordsman` / `archer` / `knight` / `healer` | 单位类型 |
| `name` | `str` | 展示名（默认 `"Unit"`）|
| `hp` / `max_hp` | `int` | 当前 / 最大 HP |
| `mp` | `int ≥ 0` | 本回合剩余 MP |
| `x` / `y` | `int ≥ 0` | 坐标 |
| `terrain` | `plain` / `forest` / `mountain` / `river` / `castle` | 脚下地形 |
| `skills` | `list[str]` | 技能列表 |
| `morale` | `0..3` | 士气星数 |
| `has_acted` | `bool` | 是否本回合已行动 |

#### `LegalAction`

引擎预生成的合法选项之一。

| 字段 | 类型 | 说明 |
|------|------|------|
| `action_id` | `str` | LLM 必须原文复制此 ID |
| `kind` | `move` / `attack` / `skill` / `wait` / `end_turn` | 动作类型 |
| `unit_id` | `int \| None` | 哪个单位行动 |
| `params` | `dict` | 动作参数（`{"to": [x, y]}` / `{"target_id": 9}` / `{"skill": "heal"}` 等）|
| `description` | `str` | 人类可读描述（"Knight 攻击 Swordsman (预计 14 伤害)"）|
| `dmg_estimate` | `int \| None` | 攻击/技能的预期伤害（attack/skill 才有）|

**`action_id` 命名规范**：
- `move_{unit_id}_{x}_{y}` — 移动
- `attack_{unit_id}_{target_id}` — 攻击
- `skill_{skill}_{unit_id}[_{target_id}]` — 技能
- `wait_{unit_id}` — 待命
- `end_turn` — 结束回合

#### `AgentAction`

LLM 的回复（`tool_input` 解析后的形态）。

| 字段 | 约束 |
|------|------|
| `action_id` | 1-64 字符，只允许 `[a-zA-Z0-9_-.]` |
| `reason` | 自动截断到 120 字符（≤40 中文字）|

#### 错误类型

| 类 | 触发场景 | 携带字段 |
|----|----------|----------|
| `AgentError` | 基类 | — |
| `ParseError` | 工具名错 / 缺 `action_id` | — |
| `InvalidActionError` | `action_id` 不在合法列表 | `.action_id` |

---

### 2.5 工具函数

#### `build_snapshot(session, game, player, *, budget_left, action_count=0) -> GameSnapshot`

从 DB 加载状态并应用战争迷雾。**迷雾规则**：4 格（`AI_AGGRO_RANGE`）内的敌人完整可见；更远的只报坐标。

#### `enumerate_legal_actions(session, game, player) -> list[LegalAction]`

枚举该玩家所有合法动作。**包含 `end_turn`**（永远存在）。move 目标最多 8 个（按距离最近敌人排序）。

#### `build_system_prompt(personality, *, map_size=15) -> str`

返回系统提示词（性格变体仅在 personality 段落不同）。

#### `build_user_prompt(snapshot, legal_actions) -> str`

返回用户提示词（jinja2 渲染）。

#### `get_default_llm_client() -> LLMClient` / `set_default_llm_client(client)`

全局 LLM 客户端单例。测试时可以 `set_default_llm_client(fake)` 注入 mock。

#### `get_personality(name) -> str`

读 `PERSONALITIES` 字典；未知名字 fallback 到 `"balanced"`。

---

### 2.6 性格预设（`prompt.PERSONALITIES`）

| key | 中文 | 风格 |
|-----|------|------|
| `aggressive` | 激进 | 主动进攻、追杀残血、抢城堡 |
| `defensive` | 谨慎 | 保护弓手治疗者、占森林/山地/城堡 |
| `balanced` | 均衡 | 灵活攻守 |
| `trickster` | 狡猾 | 弓手风筝、骑士绕后、敢换命 |

---

### 2.7 情感反应系统（`game.app.agent.reactions`）

LLM 对手会根据游戏事件**自动发言**——击杀时嚣张、被击杀时恼怒、被攻击时烦躁、占城堡时得意。发言是模板化生成的（**零 LLM 调用**，~0ms），按 personality × event 选一句。

#### 事件分类（`Event`）

| Event | 触发时机 | 典型情绪 |
|-------|---------|---------|
| `kill` | 我们的攻击击杀敌方单位 | `joy` / `smug` |
| `killed` | 我们的一个单位在对手回合被击杀 | `anger` / `disappointed` |
| `damaged` | 我们的单位受伤但未死 | `frustrated` |
| `castled` | 我们移动到无主/敌方城堡 | `joy` / `smug` |
| `victory` | 我们赢了整局 | `joy` / `smug` |
| `defeat` | 我们输了整局 | `anger` / `disappointed` |
| `skill_use` | 我们使用了技能 | `neutral` / `smug` |

#### `Reaction` 数据类

```python
@dataclass(frozen=True)
class Reaction:
    event: Event          # 触发的事件
    mood: Mood            # 情绪: joy / anger / frustrated / smug /
                          #        disappointed / neutral / relieved
    text: str             # ≤40 中文字，自动截断
```

#### `generate_reaction(personality, event, *, rng=None) -> Reaction`

从模板库随机选一句。**三级 fallback**：

1. `(personality, event)` 特定模板（如 `("aggressive", "kill")`）
2. `("balanced", event)` 通用模板
3. `_NEUTRAL_FALLBACK[event]` 中性默认
4. 完全未知事件：返回 `Reaction(event, "neutral", "……")`

```python
from app.agent.reactions import generate_reaction

r = generate_reaction("aggressive", "kill")
# Reaction(event='kill', mood='joy', text='哈！又一个！')
```

#### 性格示例（同事件不同台词）

| 性格 | `kill` 台词样例 |
|------|---------------|
| aggressive | 哈！又一个！ / 爽！杀得痛快！ / 就这？ |
| defensive | 终于解决了一个威胁。 / 稳妥拿下。 |
| balanced | 干得漂亮。 / 又拿下一城。 |
| trickster | 上钩了吧？ / 哈哈，正中下怀！ / 感谢送头！ |

#### 自动事件检测

`LLMAgent` 内部检测两类事件：

1. **被动事件**（在回合开始时检测）—— 通过 `state["last_turn_hp"]` 与当前 HP 对比，识别 "killed" / "damaged"（反映对手回合对我方造成的伤害）
2. **行动事件**（在每个 action 执行后检测）—— 检查 target 是否 HP=0 (kill)、目标格是否为敌方 castle (castled)、是否使用了 skill

**单回合反应上限** = `max_reactions_per_turn` (默认 3)，避免对手一回合打我三个人时刷屏。

#### 反应存储

`dispatch_ai_turn` 把 `metrics.reactions` 全部写入 `ActionLog`：

```python
ActionLog(
    action_type="ai_commentary",
    description=f"[{reaction.event}/{reaction.mood}] {reaction.text}",
)
```

前端通过现有的 `GET /games/{id}/state`（含 `logs`）即可读到，**无需新接口**。

---

### 2.8 度量（`TurnMetrics`）

```python
@dataclass
class TurnMetrics:
    actions_taken: int = 0
    llm_calls: int = 0          # 总调用次数（含失败重试）
    llm_retries: int = 0        # 失败重试次数
    fallback_used: int = 0      # 兜底次数
    input_tokens: int = 0       # prompt 输入 token
    output_tokens: int = 0      # 回复输出 token
    decisions: list[ActionPlan] = field(default_factory=list)
    reactions: list[Reaction] = field(default_factory=list)  # 本回合全部反应
```

`ActionPlan` 也含 `reactions: list[Reaction]`，是该 action 触发的反应（通常 0 或 1 条）。

---

## 3. HTTP 接口变更

### 3.1 `POST /games/{game_id}/add-ai`

**新增**（向后兼容；不传则走规则 AI）：

```jsonc
{
  "difficulty": "normal",             // 已存在
  "agent_kind": "llm",                // 新增: "rules" | "llm"
  "personality": "aggressive"         // 新增: 仅 agent_kind=llm 时使用
}
```

| 字段 | 类型 | 默认 | 取值 |
|------|------|------|------|
| `agent_kind` | `str` | `"rules"` | `"rules"` 或 `"llm"`（Pydantic 强制）|
| `personality` | `str` | `"balanced"` | `"aggressive"` / `"defensive"` / `"balanced"` / `"trickster"` |

**响应** (`PlayerOut`) 新增字段：

```jsonc
{
  "id": 3,
  "user_name": "电脑-1-normal-llm",
  "color": "green",
  "is_alive": true,
  "has_ended_turn": false,
  "seat": 2,
  "is_ai": true,
  "agent_kind": "llm",              // 新增
  "agent_personality": "aggressive", // 新增
  "units": []
}
```

### 3.2 `GET /games/{id}` (GameStateOut)

`PlayerOut` 内嵌在 `players` 数组中，自动包含新增字段。**无需前端额外改动**，但前端可以选择在 UI 上展示 `agent_kind` 让玩家知道对手是 LLM 还是规则 AI。

### 3.3 内部改动

`POST /games/{id}/end-turn` 行为不变。但当下一个玩家是 AI 时，**自动用 `dispatch_ai_turn`** 替代原来的 `ai_take_turn`（一个 import 替换）：

```python
# game/app/routes/turns.py
from app.agent.integration import dispatch_ai_turn  # 新增
# ...
actions = await dispatch_ai_turn(session, game, current)  # 替换原 ai_take_turn
```

---

## 4. 配置（环境变量）

通过 `agent/.env` 加载，缺省值见下表。

| 变量 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `ANTHROPIC_API_KEY` | ✓ | — | 任意 Anthropic 兼容 token（minimaxi、OpenRouter、本地 mock 都行）|
| `ANTHROPIC_BASE_URL` | ✗ | `https://api.anthropic.com` | 代理端点（minimaxi 填 `https://api.minimaxi.com/anthropic`）|
| `ANTHROPIC_MODEL` | ✗ | `claude-sonnet-4-6` | 模型名（minimaxi 填 `MiniMax-M3`）|
| `AI_THINK_DELAY_SECONDS` | ✗ | `1.2` | 两次 AI 决策间隔（来自 `app.config`）|
| `AI_AGGRO_RANGE` | ✗ | `4` | 战争迷雾可见距离（来自 `app.config`）|
| `AI_MAX_ACTIONS_PER_TURN` | ✗ | `5` | 单回合最大行动数（来自 `app.config`）|

**端点示例**：

| 提供方 | `ANTHROPIC_BASE_URL` | `ANTHROPIC_MODEL` |
|--------|----------------------|--------------------|
| Anthropic 官方 | `https://api.anthropic.com` | `claude-sonnet-4-6` |
| Minimax coding plan | `https://api.minimaxi.com/anthropic` | `MiniMax-M3` |
| OpenRouter | `https://openrouter.ai/api/v1` | `anthropic/claude-sonnet-4-6` |
| 本地 llama.cpp server | `http://127.0.0.1:8080` | 任意（需兼容 Anthropic schema）|

---

## 5. 数据流

```
[路由]  routes/turns.py
   │  end_turn 后 → 下一个玩家是 AI？
   │  是 → asyncio.create_task(_run_ai_turn_chain)
   ▼
[分发]  dispatch_ai_turn(session, game, player)
   │  按 player.agent_kind 分发
   │
   ├─ "rules"  →  rules_ai_take_turn       (原有逻辑)
   │
   └─ "llm"    →  LLMAgent.take_turn
                     │
                     │  0. _detect_passive_reactions()   # 上回合被打/被击杀
                     │
                     │  while budget_left > 0:
                     │     1. snapshot = build_snapshot(...)
                     │     2. legal    = enumerate_legal_actions(...)
                     │     3. prompt   = build_*_prompt(snapshot, legal, personality)
                     │     4. response = await LLMClient.chat(...)
                     │     5. action   = AgentAction(...)
                     │     6. validate action_id ∈ legal
                     │     7. execute via _ai_move / _ai_attack / _ai_use_skill
                     │     8. _detect_action_outcomes()   # 击杀/占城堡反应
                     │     9. 失败 → 重试 (max 3 次) → 兜底规则 AI
                     │
                     ▼
                  metrics (含 reactions)
                     │
                     ▼
              ActionLog entries with action_type="ai_commentary"
                     │
                     ▼
              前端通过 GET /games/{id} 读到
```

---

## 6. 错误处理策略

| 失败点 | 行为 |
|--------|------|
| LLM 返回非 tool_use | warning 日志，parse 失败，触发重试 |
| LLM 返回幻觉 `action_id` | 重试时附加错误信息；3 次后兜底 |
| LLM API 超时/5xx | tenacity 退避重试；3 次后兜底 |
| 行动执行失败（单位已死）| 跳过该动作，下一动作重新快照 |
| 整轮异常 | dispatcher 捕获并 fallback 到 `rules_ai_take_turn` |

**绝不停摆**：上述任何失败都不会导致游戏卡住，最多表现就是 LLM 退化为规则 AI。

---

## 7. 完整示例

### 7.0 前端读取 AI 反应

`ActionLog.action_type = "ai_commentary"` 的记录就是 AI 发言。Description 格式：`[event/mood] text`。

```jsonc
// GET /games/{id} → response.logs
[
  {"turn_number": 3, "player_id": 2, "action_type": "attack",
   "description": "Knight 攻击 Swordsman", "created_at": "..."},
  {"turn_number": 3, "player_id": 2, "action_type": "ai_commentary",
   "description": "[kill/joy] 哈！又一个！", "created_at": "..."},
  {"turn_number": 4, "player_id": 2, "action_type": "ai_commentary",
   "description": "[damaged/frustrated] 这点伤算什么！", "created_at": "..."},
]
```

前端推荐按 `player_id` 过滤 + 解析 `[event/mood]` 前缀做表情图标（joy→😄, anger→😠, frustrated→😤, smug→😏, disappointed→😞, relieved→😅, neutral→💬）。

### 7.1 启动 + 加 LLM AI

```bash
# 配置
cat > agent/.env << 'EOF'
ANTHROPIC_API_KEY=sk-cp-...
ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic
ANTHROPIC_MODEL=MiniMax-M3
EOF

# 重置 DB（Player 表加了字段）
rm -f game/battleblitz.db

# 启动
cd game && uvicorn app.main:app --reload
```

```bash
# 创建游戏 + 加 LLM AI
curl -X POST http://localhost:8000/games \
  -H 'Content-Type: application/json' \
  -d '{"name":"Test","max_players":2}'

curl -X POST http://localhost:8000/games/1/add-ai \
  -H 'Content-Type: application/json' \
  -d '{"difficulty":"normal","agent_kind":"llm","personality":"aggressive"}'
```

### 7.2 Python 直接调用

```python
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.agent import LLMAgent, dispatch_ai_turn
from app.agent.integration import get_default_llm_client
from app.models import Game, Player

async def run_one_turn(session: AsyncSession, game: Game, player: Player):
    # 方式 A: 走 dispatcher（推荐）
    n = await dispatch_ai_turn(session, game, player)
    print(f"AI 行动了 {n} 步")

    # 方式 B: 自己控制
    client = get_default_llm_client()
    agent = LLMAgent(client, personality="aggressive", think_delay=0.5)
    metrics = await agent.take_turn(session, game, player, budget_left=2)
    print(f"LLM 调用 {metrics.llm_calls} 次, "
          f"token {metrics.input_tokens}+{metrics.output_tokens}, "
          f"兜底 {metrics.fallback_used} 次")
    for d in metrics.decisions:
        print(f"  - {d.legal_action.description}  ({d.reason})")
```

### 7.3 测试用 mock client

```python
from unittest.mock import AsyncMock
from app.agent.llm_client import LLMClient, LLMResponse, TokenUsage

class FakeLLM(LLMClient):
    def __init__(self, action_id="attack_1_9", reason="测试"):
        self.action_id = action_id
        self.reason = reason
        self.calls = []

    async def chat(self, *, system, user, **kwargs):
        self.calls.append((system, user))
        return LLMResponse(
            tool_name="choose_action",
            tool_input={"action_id": self.action_id, "reason": self.reason},
            stop_reason="tool_use",
            usage=TokenUsage(input_tokens=100, output_tokens=20),
        )

# 注入到全局
from app.agent.integration import set_default_llm_client
set_default_llm_client(FakeLLM(action_id="end_turn"))
```

---

## 8. 扩展指南

### 8.1 加新性格

```python
# game/app/agent/prompt.py
PERSONALITIES["berserker"] = "你是一位狂暴指挥官，无视防御只追击杀。"

# game/app/schemas.py
class AddAIRequest(BaseModel):
    personality: str = Field(
        default="balanced",
        pattern="^(aggressive|defensive|balanced|trickster|berserker)$",
    )
```

### 8.2 切换后端到 OpenAI 兼容 API

**已实现**（`app/agent/openai_client.py`）。无需自己写——`.env` 设 `LLM_PROTOCOL=openai` 即可：

```bash
# .env
LLM_PROTOCOL=openai
OPENAI_API_KEY=not-needed             # llama.cpp 不需要
OPENAI_BASE_URL=http://127.0.0.1:8080/v1
OPENAI_MODEL=local-model
```

实现细节见 `app/agent/openai_client.py`（Anthropic → OpenAI 工具 schema 转换、function calling 解析）。

### 8.3 加 ReAct 工具（沙盘推演）

参考 `~/battleblitz-llm-agent.md` §7。最小改动：
1. `LLM_TOOL_SCHEMA` 加第二个工具 `simulate_move`
2. `llm_client.chat` 改循环，每轮检查 `tool_use` 是否为 `simulate`，是则本地计算后 `messages.append({"role":"user","content": result})` 再发
3. `LLMAgent.decide_one` 终止条件改为收到 `choose_action` 而非首次响应

---

## 9. 版本与兼容

| 版本 | 兼容范围 |
|------|----------|
| 0.1.x | 第一版（当前）。单步决策 + 兜底 |
| 0.2.x | 计划：ReAct 沙盘推演、行动级 reason SSE 推送 |
| 1.0 | 计划：本地 llama.cpp 后端、多模型投票 |

向后兼容原则：所有 HTTP 新字段都有默认值；`Player.agent_kind` 缺省 `"rules"` 等于老行为；`LLMClient` 构造参数全部可选。
