# BattleBlitz — LLM 对手集成设计

> **目标**：在现有 BattleBlitz (`game/app/`) 基础上，把本地 LLM 接入为可替换的对手。
> **硬件**：单卡 RTX 3080 10GB（vRAM 预算 9.5GB 上限）。
> **形态**：单步决策 agent（LLM 选动作 → 脚本校验执行）。
> **范围**：MVP 上 ReAct 升级是可选第二阶段，不在本文档硬性要求内。

---

## 1. 工具链依赖

### 1.1 LLM 推理服务（核心）

| 组件 | 选型 | 理由 | 备选 |
|------|------|------|------|
| **推理后端** | **llama.cpp** (`server` 模式) | 3080 10GB 兼容最好，OpenAI 兼容协议，结构化输出原生支持 | vLLM（吞吐高但起步 8GB+）、Ollama（封装死板）|
| **模型** | **Qwen2.5-7B-Instruct Q4_K_M (GGUF)** | 中文指令跟随强、JSON 输出稳定、4.5GB 显存 | GLM-4-9B Q4（中文微调更强但稍慢）、Llama-3.1-8B（英文为主）|
| **量化** | Q4_K_M | 质量/体积甜点；Q5 浪费 1.5GB 收益微弱，Q3 质量掉档 | Q5_K_M（显存紧时不用）|
| **下载** | `huggingface-cli download` | 官方通道 | `modelscope`（国内网络更快）|

**显存预估**：
- 模型权重 ~4.5 GB
- KV cache (8K ctx) ~1.5 GB
- 框架开销 ~0.5 GB
- **合计 ~6.5 GB**，留 3GB 给系统

**启动命令模板**（`scripts/run_llm_server.sh`）：

```bash
llama-server \
  -m models/qwen2.5-7b-instruct-q4_k_m.gguf \
  -ngl 999 \                       # 全部层卸载到 GPU
  -c 8192 \                        # 上下文长度
  --port 8080 \
  --host 127.0.0.1 \
  --json-schema /etc/llm/action_schema.json \   # 硬约束输出
  --parallel 1                     # 单并发，节省显存
```

### 1.2 应用层新增依赖

| 包 | 版本约束 | 用途 |
|----|---------|------|
| `httpx` | `>=0.27` | 异步调 llama.cpp `/v1/chat/completions` |
| `tenacity` | `>=9.0` | LLM 调用重试（指数退避）|
| `pydantic` | `>=2.5`（已有）| 快照 / 动作 / reason schema |
| `jinja2` | `>=3.1` | Prompt 模板渲染 |
| `orjson` | `>=3.10` | 快照序列化加速（vs 标准 json ~2x）|
| `prometheus-client` | `>=0.20` | 决策延迟、token 消耗、重试计数 |
| `tenacity` | `>=9.0` | 重试 |

写入 `requirements-agent.txt`：

```text
httpx>=0.27
tenacity>=9.0
jinja2>=3.1
orjson>=3.10
prometheus-client>=0.20
```

### 1.3 测试依赖

| 包 | 用途 |
|----|------|
| `pytest` | 测试框架（已有）|
| `pytest-asyncio` `>=0.23` | 异步测试 |
| `pytest-mock` `>=3.14` | mock LLM client |
| `vcrpy` `>=6.0` | 录制真实 LLM 响应，离线回放 |
| `pytest-benchmark`（可选）| 决策延迟基准 |

```text
# requirements-agent-dev.txt
pytest-asyncio>=0.23
pytest-mock>=3.14
vcrpy>=6.0
pytest-benchmark>=4.0
```

### 1.4 不需要的东西

- ❌ LangChain / LlamaIndex（过重，自己写 100 行 LLM client 就够）
- ❌ 向量数据库（不需要 RAG）
- ❌ vLLM（10GB 卡跑不动 7B FP16）
- ❌ 微调脚本（MVP 不需要，先 prompt 工程）

---

## 2. 架构

### 2.1 分层

```
┌──────────────────────────────────────────────────────────┐
│  Frontend (已有 web/)                                     │
│    SSE 推送：状态更新 / 行动日志 / ai_reason 气泡         │
└────────────────────┬─────────────────────────────────────┘
                     │  HTTP / WebSocket
┌────────────────────▼─────────────────────────────────────┐
│  FastAPI Backend (game/app/ 已有)                         │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Game Engine (game_logic.py 已有)                  │  │
│  │    - 回合 / 行动点 / 战斗 / 士气 / 城堡            │  │
│  │    新增:                                            │  │
│  │    - snapshot_builder  (DB → JSON snapshot)        │  │
│  │    - legal_action_gen  (枚举合法动作 + 伤害预估)   │  │
│  │    - action_validator  (业务层校验)                │  │
│  │    - ai_dispatcher     (rules_ai | llm_ai 切换)   │  │
│  └────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────┐  │
│  │  LLM Agent Layer (game/app/agent/ 新建)            │  │
│  │    - prompt.py        (jinja2 模板)                │  │
│  │    - llm_client.py    (httpx → llama.cpp)          │  │
│  │    - response_parser  (JSON → Action)              │  │
│  │    - retry.py         (3 次重试策略)               │  │
│  │    - agent.py         (编排器)                     │  │
│  │    - personality.py   (aggressive/defensive/...)   │  │
│  └────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Observability (新增)                              │  │
│  │    - /metrics 暴露: 决策延迟、重试次数、非法动作率 │  │
│  └────────────────────────────────────────────────────┘  │
└────────────────────┬─────────────────────────────────────┘
                     │  HTTP (OpenAI-compatible)
┌────────────────────▼─────────────────────────────────────┐
│  llama.cpp server  (localhost:8080)                       │
│    Qwen2.5-7B-Instruct Q4_K_M  ·  ~5GB VRAM              │
│    --json-schema 约束输出                                 │
└──────────────────────────────────────────────────────────┘
```

### 2.2 数据流（一次 LLM 决策）

```
ai_take_turn() 触发
   │
   ├──> snapshot = snapshot_builder.build(player, game)
   │
   ├──> legal = legal_action_gen.generate(snapshot)
   │        (move / attack / skill / wait / end_turn)
   │
   ├──> prompt = prompt_builder.render(snapshot, legal, personality)
   │
   ├──> for attempt in 1..3:
   │        response = await llm_client.chat(prompt, json_schema=ActionSchema)
   │        try:
   │            parsed = response_parser.parse(response)      # Pydantic
   │            action = action_validator.check(parsed, legal) # 业务校验
   │            break
   │        except (ParseError, InvalidActionError):
   │            log.warn(attempt)
   │            continue
   │      else:
   │        action = rules_ai_fallback(snapshot)  # 三次都失败兜底
   │
   ├──> reason = parsed.reason
   │
   ├──> executor.execute(action)  # 落库 + ActionLog
   │
   ├──> sse.emit({type:"ai_reason", text: reason})   # 推前端
   │
   └──> 继续下一个 action (直到 budget 用完或 end_turn)
```

### 2.3 新增文件清单

| 路径 | 职责 | 估行数 |
|------|------|--------|
| `game/app/agent/__init__.py` | 公开 `LLMAgent` | 20 |
| `game/app/agent/schemas.py` | Pydantic: `GameSnapshot`, `LegalAction`, `Action`, `Reason` | 120 |
| `game/app/agent/snapshot.py` | DB → snapshot，序列化 + 迷雾过滤 | 100 |
| `game/app/agent/legal_actions.py` | 枚举所有合法动作，附带 `dmg_estimate` | 180 |
| `game/app/agent/prompt.py` | jinja2 系统提示 + 用户提示模板 | 150 |
| `game/app/agent/llm_client.py` | httpx 异步 client、timeout、health check | 80 |
| `game/app/agent/response_parser.py` | JSON → `Action`，错误分类 | 60 |
| `game/app/agent/retry.py` | tenacity 装饰器 + 兜底策略 | 40 |
| `game/app/agent/agent.py` | `LLMAgent.take_turn()` 编排 | 100 |
| `game/app/agent/personality.py` | 性格预设 (system prompt 片段) | 50 |
| `game/app/agent/observability.py` | prometheus 指标 | 40 |
| `game/app/agent/integration.py` | 挂到 `ai_take_turn` 的分发器 | 60 |
| `scripts/run_llm_server.sh` | llama.cpp server 启动 | 30 |
| `scripts/download_model.py` | 模型下载 + SHA256 校验 | 50 |
| `tests/agent/` | 单元 + 集成测试 | 600+ |

**总计新增 ~1000 行应用代码 + 测试**，不修改 `game_logic.py` 核心逻辑（仅在 `ai_take_turn` 增加一行分发判断）。

### 2.4 关键数据结构

```python
# schemas.py
class LegalAction(BaseModel):
    action_id: str                  # "move_1_to_5,5"
    kind: Literal["move", "attack", "skill", "wait", "end_turn"]
    unit_id: int
    params: dict                    # {to:[5,5]} or {target_id:9} or {kind:"heal"}
    description: str                # 人类可读: "骑士攻击弓手 (预计 12 伤害)"
    dmg_estimate: int | None        # 攻击/技能才有


class Action(BaseModel):
    action_id: str                  # 必须匹配 LegalAction.action_id
    reason: str                     # ≤40 字，推前端显示


class GameSnapshot(BaseModel):
    turn: int
    budget_left: int
    my_units: list[UnitView]
    visible_enemies: list[UnitView]  # 视野内 + 已知存在
    fog_enemies: list[Position]      # 仅坐标
    unowned_castles: list[Position]
    enemy_castles: list[Position]
    map_ascii: str                   # ~30x20 字符画
    map_legend: dict[str, str]
```

### 2.5 Prompt 模板骨架

**System prompt**（固定，性格变体只改尾部）：

```
你是战棋游戏 BattleBlitz 的指挥官，指挥 [我方] 与 [敌方] 对战。

游戏规则 (简明版):
  - 移动: 消耗 MP (平原 1, 森林 2, 山 3, 城堡 1)
  - 攻击: 相邻 (近战) 或 2-3 格远程 (snipe 弓手 +1 射程)
  - 类型克制: 剑士>骑士>弓手>剑士 (1.2x)
  - 士气: 每杀 +1 (上限 3), 每颗 +10% 攻击 / +5% 防御
  - 行动预算: 每回合固定 N 次
  - 行动结束后该单位本回合不能再动 (除非双击)

你的任务: 从 [合法动作列表] 中选一个执行。
输出格式 (严格 JSON, 不要任何额外文字):
  {
    "action_id": "从合法动作列表复制",
    "reason": "≤40 字中文，说明你的意图"
  }

硬约束:
  - action_id 必须出现在合法动作列表中
  - 不要输出列表外的动作
  - 不要解释规则, 不要问问题, 只输出 JSON
```

**User prompt**（jinja 渲染）：

```
[回合 {{ turn }} · 剩余行动 {{ budget_left }}]

{{ map_ascii }}
图例: {{ map_legend|join(', ') }}

【我方单位】
{% for u in my_units %}
  #{{ u.id }} {{ u.type_zh }}  HP {{ u.hp }}/{{ u.max_hp }}  MP {{ u.mp }}
  位置 ({{ u.x }},{{ u.y }})  地形: {{ u.terrain_zh }}
  技能: {{ u.skills|default('无') }}  士气: {{ '★' * u.morale }}
{% endfor %}

【可见敌方】
{% for e in visible_enemies %}
  #{{ e.id }} {{ e.type_zh }}  HP {{ e.hp_estimate or '?' }}  @ ({{ e.x }},{{ e.y }})
{% endfor %}
{% if fog_enemies %}
【迷雾 (仅坐标)】
{% for p in fog_enemies %}  ? @ ({{ p.x }},{{ p.y }}){% endfor %}
{% endif %}

【合法动作 ({{ legal_actions|length }} 个)】
{% for a in legal_actions %}
  {{ loop.index }}. [{{ a.action_id }}] {{ a.description }}{% if a.dmg_estimate %} (预计伤害 {{ a.dmg_estimate }}){% endif %}
{% endfor %}

请选择并输出 JSON:
```

### 2.6 三层校验防线

```
Layer 1  llama.cpp server  --json-schema
            └─ 服务端硬约束，token 层面拒绝非法字段
Layer 2  Pydantic schemas.Action
            └─ 类型 / 必填字段 / action_id 存在
Layer 3  action_validator.check()
            └─ 业务校验: 距离、MP、行动点、单位存活、士气状态
```

**降级策略**：
- Layer 1/2 失败 → 同一 prompt 重试（换温度 + 错误信息回灌）
- Layer 3 失败 → 提示 LLM "此动作不合法，请从合法列表重新选择"
- 3 次全失败 → 走 `rules_ai_fallback`（用现有 `_ai_pick_attack_target` 处理这一回合，reason 标 `[兜底]`）

### 2.7 与现有代码的集成点

**最小侵入**：不改 `ai_take_turn` 核心，只在分发处切换：

```python
# game/app/agent/integration.py
async def ai_take_turn(session, game, ai_player):
    if ai_player.llm_config is None:
        return await rules_ai_take_turn(session, game, ai_player)  # 已有

    agent = LLMAgent(
        personality=ai_player.llm_config.personality,
        llm_endpoint=ai_player.llm_config.endpoint,
    )
    return await agent.take_turn(session, game, ai_player)
```

`Player` 表加一列 `llm_config` (JSON, nullable)：`null` → 规则 AI，否则 LLM AI。

---

## 3. 测试方法

### 3.1 测试金字塔

```
       ┌────────────────────────┐
       │  50 局对战基准 (E2E)   │  ← LLM AI vs 规则 AI 胜率
       ├────────────────────────┤
       │  集成测试 (~10 个)     │  ← 真实 LLM 跑 1 回合
       ├────────────────────────┤
       │  单元测试 (~50 个)     │  ← snapshot / legal / parser / validator
       └────────────────────────┘
```

### 3.2 单元测试（mock LLM，无 GPU 也跑）

**A. snapshot 生成**

```python
# tests/agent/test_snapshot.py
def test_snapshot_excludes_fog_enemies(game_with_fog):
    snap = snapshot_builder.build(player_pov, game_with_fog)
    assert all(e.hp_estimate is None for e in snap.visible_enemies)
    assert (3, 3) in [p for p in snap.fog_enemies]  # 已知存在但不可见

def test_snapshot_includes_action_budget(game_n_turn_3):
    snap = snapshot_builder.build(...)
    assert snap.budget_left == 2  # 假设本回合 2 次行动
```

**B. legal_action 枚举**

```python
# tests/agent/test_legal_actions.py
def test_legal_actions_excludes_blocked_by_mp(swordsman_with_mp_0):
    actions = legal_action_gen.generate(snap_with(swordsman_with_mp_0))
    assert not any(a.kind == "move" and a.unit_id == swordsman_with_mp_0.id
                   for a in actions)

def test_legal_attack_includes_dmg_estimate(archer_vs_swordsman):
    actions = legal_action_gen.generate(snap)
    atk = next(a for a in actions if a.kind == "attack")
    assert atk.dmg_estimate == expected_dmg(archer, swordsman)
```

**C. parser**

```python
# tests/agent/test_response_parser.py
def test_parses_well_formed_response():
    raw = '{"action_id": "attack_1_9", "reason": "抢先击杀"}'
    a = ResponseParser().parse(raw)
    assert a.action_id == "attack_1_9"

def test_rejects_json_with_extra_fields():
    raw = '{"action_id": "...", "reason": "...", "secret": "..."}'
    with pytest.raises(ValidationError):
        ResponseParser().parse(raw)

def test_rejects_markdown_fenced_json():
    raw = '```json\n{"action_id": "..."}\n```'
    with pytest.raises(ParseError):
        ResponseParser(strict=True).parse(raw)
```

**D. validator**

```python
# tests/agent/test_validator.py
def test_rejects_attack_on_dead_unit(snap_with_dead_enemy):
    action = Action(action_id="attack_1_99", reason="x")
    with pytest.raises(InvalidActionError):
        ActionValidator().check(action, snap_with_dead_enemy)
```

### 3.3 集成测试（mock llama.cpp server，不需 GPU）

```python
# tests/agent/test_agent_integration.py
async def test_full_turn_with_mock_llm(monkeypatch, simple_scenario):
    async def fake_chat(prompt, schema):
        return '{"action_id": "attack_1_2", "reason": "测试"}'

    monkeypatch.setattr(llm_client, "chat", fake_chat)
    agent = LLMAgent(personality="aggressive")
    n = await agent.take_turn(simple_scenario)
    assert n == 1
    assert simple_scenario.units[1].has_acted is True


async def test_retry_on_invalid_action(monkeypatch, caplog):
    responses = iter([
        '{"action_id": "ILLEGAL", "reason": "..."}',  # 第 1 次: 无效
        '{"action_id": "attack_1_2", "reason": "..."}',  # 第 2 次: 有效
    ])
    async def fake_chat(prompt, schema):
        return next(responses)
    monkeypatch.setattr(llm_client, "chat", fake_chat)

    agent = LLMAgent()
    await agent.take_turn(simple_scenario)
    assert "attempt 1 failed" in caplog.text
    assert "attempt 2 succeeded" in caplog.text


async def test_fallback_after_3_failures(monkeypatch):
    monkeypatch.setattr(llm_client, "chat", always_returns_garbage)
    agent = LLMAgent(fallback=rules_ai_fallback)
    n = await agent.take_turn(simple_scenario)
    # 兜底走规则 AI，至少执行 1 步
    assert n >= 1
```

### 3.4 真实 LLM 烟囱测试（需要 GPU，CI 跳过）

```python
# tests/agent/test_llm_smoke.py
import pytest

@pytest.mark.requires_gpu
@pytest.mark.skipif(not has_gpu(), reason="无 GPU 跳过")
async def test_llm_returns_parseable_action():
    """真实跑一次 LLM，验证 JSON 可解析 + 动作合法。"""
    snap, legal = make_simple_scenario()  # 1v1 简化场景
    agent = LLMAgent(personality="aggressive")
    action = await agent.decide(snap, legal)
    assert action_validator.check(action, legal) is not None


@pytest.mark.requires_gpu
async def test_llm_falls_back_under_high_temperature(promote_higher_temp):
    """高温度下重试策略仍能在 3 次内找到合法动作。"""
    agent = LLMAgent(temperature=1.5)
    success = 0
    for _ in range(10):
        try:
            await agent.decide(snap, legal)
            success += 1
        except AllAttemptsFailed:
            pass
    assert success >= 7  # ≥70% 一次成功
```

### 3.5 VCR 录播（真实 LLM 离线回放）

```python
# tests/agent/cassettes/aggressive_attack_turn3.json
# 录制: 真实 LLM 对某局第 3 回合的完整 HTTP 响应

@pytest.mark.vcr
async def test_prompt_changes_dont_break_replay(cassette_dir):
    """prompt 改版后，cassette 仍能离线回放历史决策。"""
    agent = LLMAgent()
    action = await agent.decide(snap, legal)
    assert action == expected_action_from_cassette
```

> VCR 价值：CI 不需要 GPU 也能跑真实 LLM 回归。模型升级或 prompt 改版前，重放 cassette 确认行为不漂移。

### 3.6 对战评估（核心！）

**`scripts/eval/head_to_head.py`**：

```python
async def evaluate(ai_a_kind, ai_b_kind, n_games=50, max_turns=100):
    results = {
        "a_wins": 0, "b_wins": 0, "draws": 0,
        "turn_counts": [], "latencies": [],
    }
    for i in range(n_games):
        game = await create_game(seed=i)
        await run_game_with_seeded_rng(game, ai_a_kind, ai_b_kind, max_turns)
        winner = game.winner
        results["turn_counts"].append(game.turn_number)
        results["latencies"].extend(game.metrics.decision_latencies)
        ...
    report = {
        "a_win_rate": results["a_wins"] / n_games,
        "avg_turns": statistics.mean(results["turn_counts"]),
        "p50_decision_ms": percentile(results["latencies"], 50),
        "p95_decision_ms": percentile(results["latencies"], 95),
    }
    return report
```

**报告指标**：

| 指标 | 目标 | 警戒线 |
|------|------|--------|
| LLM AI 胜率 (vs 规则 AI) | ≥ 50% | < 30% 需调 prompt |
| P50 决策延迟 | < 2.5s | > 5s 需减 prompt 长度 |
| P95 决策延迟 | < 5s | > 10s 需排查 |
| 非法动作率 | < 1% | > 5% 需重写 prompt |
| JSON 解析失败率 | < 5% | > 10% prompt 有歧义 |
| 平均重试次数 | < 1.3 | > 2 prompt 没说清约束 |

### 3.7 资源 / 性能基准

```bash
# 监控 llama.cpp server 显存
nvidia-smi dmon -s u -d 1

# 监控应用层
curl http://localhost:8000/metrics | grep agent_
# 输出:
# agent_decision_seconds_bucket{le="1.0"} 12
# agent_decision_seconds_bucket{le="2.5"} 38
# agent_decision_seconds_bucket{le="5.0"} 49
# agent_decision_seconds_bucket{le="10.0"} 50
# agent_retry_total{result="success"} 47
# agent_retry_total{result="fallback"} 3
# agent_invalid_action_total{kind="out_of_range"} 2
```

### 3.8 回归 checklist

每次改 prompt / 模型 / 校验逻辑，**必须**重跑：

- [ ] 50 局 LLM AI vs 规则 AI，胜率波动 ±10% 内
- [ ] P95 决策延迟 < 5s
- [ ] 显存峰值 < 9.5GB
- [ ] 非法动作率 < 1%
- [ ] JSON 解析失败率 < 5%
- [ ] VCR cassette 回放全部通过

---

## 4. 实施路线

| 阶段 | 任务 | 验收 |
|------|------|------|
| **0. 准备** | 装 llama.cpp，下载 Q4_K_M，curl 测试通 | 1 分钟内首 token 出来 |
| **1. 数据结构** | schemas.py + snapshot.py + legal_actions.py + 单元测试 | 覆盖率 > 90% |
| **2. Prompt** | prompt.py + jinja 模板 + 用真实 DB 数据肉眼检查渲染 | 100 局回放，reason 文本无乱码 |
| **3. LLM 客户端** | llm_client.py + retry.py + 三层校验 | mock server 集成测试 100% |
| **4. 真实接入** | 跑通 1 完整回合（GPU）| 烟囱测试通过 |
| **5. 前端 SSE** | reason 推前端 | 前端能看到 AI 内心独白 |
| **6. 对战评估** | 50 局 LLM AI vs 规则 AI | 胜率 ≥ 30%（先稳）→ 调 prompt → ≥ 50% |
| **7. 性格预设** | aggressive / defensive / trickster | 前端可切换 |
| **8. ReAct 升级 (可选)** | 加 simulate 工具 | 胜率提升 > 10% 才保留 |

**预估工时**：
- 阶段 0-3：~3-5 天（纯写代码 + 单测）
- 阶段 4-5：~1-2 天（GPU 调试 + 前端）
- 阶段 6-7：~2-3 天（评估 + 调 prompt）
- 阶段 8：可选，1-2 周

---

## 5. 风险与对策

| 风险 | 概率 | 影响 | 对策 |
|------|------|------|------|
| LLM 输出幻觉（不存在的 unit_id）| 高 | 中 | 三层校验 + 兜底规则 AI |
| llama.cpp 启动慢（~10s）| 高 | 低 | 启动时 prewarm，状态机持久化 |
| 显存溢出 | 中 | 高 | 监控 + 启动时 model load 校验 + 熔断 |
| 长游戏 N 回合后 prompt 超出 8K | 中 | 中 | 早期回合压缩历史，只保留最近 3 回合 + 关键事件 |
| LLM 太弱（< 规则 AI）| 中 | 中 | prompt 调优 + 性格预设 + 后期 ReAct 升级 |
| LLM 太强（玩家打不动）| 低 | 高 | 性格预设给"马虎"选项 + 故意 miss 概率化 |

---

## 6. 一键启动 checklist

```bash
# 1. 模型
huggingface-cli download Qwen/Qwen2.5-7B-Instruct-GGUF \
    qwen2.5-7b-instruct-q4_k_m.gguf --local-dir models/
sha256sum models/qwen2.5-7b-instruct-q4_k_m.gguf  # 校验

# 2. 启动 LLM 服务
bash scripts/run_llm_server.sh
curl http://127.0.0.1:8080/health  # 应返回 ok

# 3. 安装 Python 依赖
pip install -r requirements-agent.txt
pip install -r requirements-agent-dev.txt

# 4. 跑测试
pytest tests/agent/ -v                          # 单元 + 集成（无 GPU）
pytest tests/agent/ -v -m requires_gpu          # 烟囱（需 GPU）
pytest tests/agent/ -v --benchmark-only          # 性能基准

# 5. 跑对战评估
python scripts/eval/head_to_head.py \
    --a llm-7b-aggressive \
    --b rules \
    --n 50 \
    --output eval_report.json

# 6. 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## 7. 后续可扩展点（不在 MVP 范围）

- **多模型投票**：同一局面调 3 次 LLM，少数服从多数 → 提升稳定性
- **ReAct 沙盘推演**：加 `simulate` 工具，LLM 主动 lookahead
- **记忆系统**：保存历史决策，玩家行为画像
- **风格迁移 LoRA**：用对战数据微调 7B，让 LLM 学到项目专属"性格"
- **多 LLM 对战**：两个本地模型对打，研究 prompt 技巧
- **Spectator 模式**：旁观别人 LLM AI 对战，reason 流式播报

---

**维护者**：YoukoSaint
**最后更新**：2026-06-25
