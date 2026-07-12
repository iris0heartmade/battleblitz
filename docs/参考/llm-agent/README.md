# BattleBlitz — LLM 对手集成设计

> **目标**：在现有 BattleBlitz (`game/app/`) 基础上，把本地 LLM 接入为可替换的对手。
> **硬件**：单卡 RTX 3080 10GB（vRAM 预算 9.5GB 上限）。
> **形态**：单步决策 agent（LLM 选动作 → 脚本校验执行）。
> **协议 / 端点 / 数据契约**：见 [`api.md`](api.md)
> **范围**：MVP 上 ReAct 升级是可选第二阶段，不在本文档硬性要求内。
>
> **更新记录**：
> - 2026-06-26: §4 加状态列；实施情况、prompt 优化、客户端双协议
> - 2026-06-27: 与 `api.md` 拆开；README 只留架构概览

---

## 1. 工具链依赖

### 1.1 LLM 推理服务（核心）

| 组件 | 选型 | 理由 | 备选 |
|------|------|------|------|
| **推理后端** | **llama.cpp** (`server` 模式) | 3080 10GB 兼容最好，OpenAI 兼容协议，结构化输出原生支持 | vLLM（吞吐高但起步 8GB+）、Ollama（封装死板）|
| **模型** | **Qwen2.5-7B-Instruct Q4_K_M (GGUF)** | 中文指令跟随强、JSON 输出稳定、4.5GB 显存 | GLM-4-9B Q4（中文微调更强但稍慢）、Llama-3.1-8B（英文为主）|
| **量化** | Q4_K_M | 质量/体积甜点；Q5 浪费 1.5GB 收益微弱，Q3 质量掉档 | Q5_K_M（显存紧时不用）|
| **下载** | `huggingface-cli download` | 官方通道 | `modelscope`（国内网络更快）|

**显存预估**：~6.5 GB（权重 4.5 + KV 1.5 + 框架 0.5），留 3GB 给系统。

**启动命令模板**（`scripts/run_llm_server.sh`）：

```bash
llama-server \
  -m models/qwen2.5-7b-instruct-q4_k_m.gguf \
  -ngl 999 -c 8192 \
  --port 8080 --host 127.0.0.1 \
  --json-schema /etc/llm/action_schema.json \
  --parallel 1
```

### 1.2 应用层新增依赖

写入 `requirements-agent.txt`：

```text
httpx>=0.27
tenacity>=9.0
jinja2>=3.1
orjson>=3.10
prometheus-client>=0.20
```

### 1.3 测试依赖

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
│  │  Game Engine (game_logic.py 已有)                  │
│  │    - 回合 / 行动点 / 战斗 / 士气 / 城堡            │
│  │    新增:                                            │
│  │    - snapshot_builder  (DB → JSON snapshot)        │
│  │    - legal_action_gen  (枚举合法动作 + 伤害预估)   │
│  │    - action_validator  (业务层校验)                │
│  │    - ai_dispatcher     (rules_ai | llm_ai 切换)   │
│  └────────────────────────────────────────────────────┘
│  ┌────────────────────────────────────────────────────┐  │
│  │  LLM Agent Layer (game/app/agent/ 新建)            │
│  │    - prompt.py        (jinja2 模板)                │
│  │    - llm_client.py    (httpx → llama.cpp)          │
│  │    - response_parser  (JSON → Action)              │
│  │    - retry.py         (3 次重试策略)               │
│  │    - agent.py         (编排器)                     │
│  │    - personality.py   (aggressive/defensive/...)   │
│  └────────────────────────────────────────────────────┘
│  ┌────────────────────────────────────────────────────┐  │
│  │  Observability (新增)                              │
│  │    - /metrics 暴露: 决策延迟、重试次数、非法动作率 │
│  └────────────────────────────────────────────────────┘
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
   ├──> legal = legal_action_gen.generate(snapshot)
   │        (move / attack / skill / wait / end_turn)
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
   ├──> executor.execute(action)  # 落库 + ActionLog
   ├──> sse.emit({type:"ai_reason", text: reason})   # 推前端
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

详见 [`api.md` §2.4](api.md#24-数据契约gameappagentschemas)。核心是 `LegalAction`（带 `dmg_estimate`）/ `Action`（强制 `action_id` ∈ legal）/ `GameSnapshot`（含战争迷雾与 ASCII 地图）。

### 2.5 三层校验防线

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
- 3 次全失败 → 走 `rules_ai_fallback`（reason 标 `[兜底]`）

### 2.6 与现有代码的集成点

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

## 3. 测试金字塔

```
       ┌────────────────────────┐
       │  50 局对战基准 (E2E)   │  ← LLM AI vs 规则 AI 胜率
       ├────────────────────────┤
       │  集成测试 (~10 个)     │  ← 真实 LLM 跑 1 回合
       ├────────────────────────┤
       │  单元测试 (~50 个)     │  ← snapshot / legal / parser / validator
       └────────────────────────┘
```

**回归 checklist**（每次改 prompt / 模型 / 校验逻辑必须重跑）：
- [ ] 50 局 LLM AI vs 规则 AI，胜率波动 ±10% 内
- [ ] P95 决策延迟 < 5s
- [ ] 显存峰值 < 9.5GB
- [ ] 非法动作率 < 1%
- [ ] JSON 解析失败率 < 5%
- [ ] VCR cassette 回放全部通过

---

## 4. 实施路线

| 阶段 | 任务 | 状态 (2026-06-26) |
|------|------|-------------------|
| **0. 准备** | 装 llama.cpp，下载 Q4_K_M | ✅ llama.cpp 已配，`.env` 设 `LLM_PROTOCOL=openai` |
| **1. 数据结构** | schemas / snapshot / legal_actions + 单测 | ✅ 完成 |
| **2. Prompt** | jinja 模板 + 真实 DB 渲染验证 | ✅ 完成（多次优化：精简模板、随机人格、行为自定义）|
| **3. LLM 客户端** | llm_client + retry + 三层校验 | ✅ 完成（双协议：Anthropic + OpenAI 兼容）|
| **4. 真实接入** | 跑通 1 完整回合（GPU）| ✅ 完成（实测 MiniMax M3 每次 ~1-3s）|
| **5. 前端 SSE** | reason 推前端 | 🚧 **部分**（用 3s 轮询替代 SSE，左下角 chat-float 浮层）|
| **6. 对战评估** | 50 局 LLM AI vs 规则 AI | ⬜ 未做 |
| **7. 性格预设** | aggressive / defensive / trickster | ✅ **部分**（后端每回合随机切人格，前端不能选）|
| **8. ReAct 升级 (可选)** | 加 simulate 工具 | ⬜ 未做 |

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
    --a llm-7b-aggressive --b rules --n 50 --output eval_report.json

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
**最后更新**：2026-06-27