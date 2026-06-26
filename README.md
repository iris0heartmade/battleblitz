# BattleBlitz · 战棋

> 类似《火焰纹章》和《高级战争》风格的回合制战棋游戏服务端。
> 后端：Python + FastAPI + SQLAlchemy（异步）+ SQLite
> 前端：原生 HTML / CSS / JS，由 FastAPI 静态托管

---

## ✨ 核心特性

- **15×15 棋盘**：随机生成 + 6 种手绘地图预设（经典 / 开阔 / 山地 / 河流 / 森林 / 四方水泽）
- **4 个兵种 × 4 种阵营组合**：经典 / 进攻 / 防御 / 远程火力
- **完整兵种类体系**：剑士、弓手、骑士、治疗师，可扩展
- **MP 移动点系统**：每回合按地形消耗 MP，可移动攻击 / 攻击后移动（仅骑弓）
- **士气系统**：每杀一人 +1 士气（最高 3 星），按星加成攻击/防御
- **反击系统**：被攻击方若存活且能打到攻击者 → 自动反击（50% 伤害，火纹式）
- **战斗预测面板**：攻击前显示预测伤害 / 暴击率 / 反击伤害 / 兵种克制
- **AI 对手**：5 档难度 + 多种人格，所有 AI 可自动连续行动
- **存档与重连**：localStorage 保留 session，自动恢复大厅 / 棋盘
- **房间与好友**：2-4 人局域网联机，加入 AI 电脑填补空位
- **回合横幅**：回合切换时滑入动画提示
- **悬浮路径预览**：移动时鼠标悬浮显示 A* 寻路绿点

---

## 🚀 快速开始

### Windows / 开发机

```bash
cd game
python -m venv venv
source venv/Scripts/activate        # Git Bash
# venv\Scripts\Activate.ps1         # PowerShell
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

打开 <http://localhost:8000/> 即可进入游戏。

### 树莓派 / Linux 部署

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git
cd /home/pi
git clone <仓库地址> BattleBlitz
cd BattleBlitz/game
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

部署后**同局域网的朋友**打开 `http://树莓派IP:8000/` 即可加入。

---

## 🎮 玩法规则

### 单位

| 单位 | 移动 | 攻击 | 生命 | 特性 |
|------|------|------|------|------|
| 剑士 | 5 MP | 1 格 | 45 | 均衡近战，可反击 |
| 弓手 | 5 MP | 2 格 | 35 | 远程（1 < 距离 ≤ 2），不可近战反击 |
| 骑士 | 8 MP | 1 格 | 55 | 高移动高攻，可反击 |
| 治疗师 | 5 MP | 0 | 40 | 治愈 / 集结技能 |

### 地形

| 地形 | 移动消耗 | 防御加成 | 特殊 |
|------|---------|---------|------|
| 平地 | 1 | 0 | - |
| 森林 | 2 | +2 | 阻挡远程视线 |
| 山地 | 3 | +3 | 阻挡远程视线 |
| 河流 | 3 | 0 | 阻挡远程视线 |
| 城堡 | 1 | +5 | 占满所有城堡即胜利 |

### 战斗

- 攻击公式：`伤害 = ATK × (ATK / (ATK + DEF + 地形)) × 兵种克制 × 暴击`
- 暴击：基础 5% + 每级 +1%，伤害 1.5 倍
- 兵种克制：剑 → 骑 (+20%)，骑 → 弓 (+20%)
- 士气加成：每颗星 +10% 攻击 / +5% 防御

### 回合流程

1. 当前玩家可移动 / 攻击 / 治疗 / 待机
2. 点「结束回合 →」切换到下一玩家
3. 所有玩家都结束后，AI 自动连续行动
4. 一整轮结算 → 进入下一回合

### 公平性规则

- 第一个玩家（座位 0）在**第一回合**只能操作 **1 个单位**
- 其他玩家，以及所有人后续回合，每回合需操作 **2 个单位**
- 每单位每回合只能移动一次，移动后仍可攻击

---

## 🗂️ 项目结构

```
BattleBlitz/
├── README.md
├── ARCHITECTURE_PLAN.md    # 详细路线图（P0-P3）
├── doc/                     # 设计文档
├── game/
│   ├── app/
│   │   ├── main.py          # FastAPI 入口
│   │   ├── config.py        # 全部游戏常量
│   │   ├── database.py      # 异步引擎 + session
│   │   ├── models.py        # ORM 模型
│   │   ├── schemas.py       # Pydantic 模型
│   │   ├── game_logic.py    # 地图 / 战斗 / 反击 / 士气
│   │   ├── utils.py         # 寻路 / 视线 / 距离
│   │   ├── events/          # 事件总线（pub/sub）
│   │   ├── llm/             # LLM 客户端抽象
│   │   ├── progression/     # 角色养成（未来）
│   │   ├── classes/units/   # 兵种类体系（弓手 / 剑士 / 骑 / 治疗）
│   │   ├── agent/           # LLM Agent 对手系统
│   │   ├── protocol/        # WebSocket v1 协议
│   │   ├── logging_config.py # 日志规范
│   │   ├── web/             # 前端
│   │   │   ├── index.html
│   │   │   ├── style.css
│   │   │   └── app.js
│   │   └── routes/
│   │       ├── game.py       # /games, /join, /start, /state, /presets, /add-ai
│   │       ├── actions.py    # /move, /attack, /skill, /wait
│   │       └── turns.py      # /end-turn + 后台超时
│   ├── tests/               # pytest 测试
│   ├── conftest.py
│   ├── pytest.ini
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── requirements-agent.txt
│   ├── start.bat
│   └── stop.bat
├── tests/                   # Agent 测试
└── tools/                   # 实用工具
```

---

## 📡 API 端点（精选）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/healthz` | 健康检查 |
| POST | `/games` | 创建游戏 `{name, max_players, map_preset, unit_composition}` |
| GET  | `/games` | 列出所有游戏 |
| GET  | `/games/presets` | 列出地图和兵种组合预设 |
| POST | `/games/{id}/join` | 加入游戏 `{user_name, color?}` |
| POST | `/games/{id}/rejoin` | 断线重连 `{player_id}` |
| POST | `/games/{id}/add-ai` | 添加 AI 电脑 `{difficulty}` |
| DELETE | `/games/{id}/players/{pid}` | 移除玩家（仅开始前）|
| POST | `/games/{id}/start` | 开始游戏 |
| GET  | `/games/{id}/state` | 完整状态快照 |
| POST | `/games/{id}/move` | 移动单位 `{player_id, unit_id, to_x, to_y}` |
| POST | `/games/{id}/attack` | 攻击目标 `{player_id, attacker_id, target_id}` |
| POST | `/games/{id}/skill` | 释放技能 |
| POST | `/games/{id}/wait` | 待机 |
| POST | `/games/{id}/end-turn` | 结束回合 `{player_id}` |
| GET  | `/` | 跳转到游戏 UI |
| GET  | `/docs` | OpenAPI Swagger 文档 |

---

## 🛠️ 配置常量（`app/config.py`）

| 常量 | 默认值 | 含义 |
|------|--------|------|
| `MAP_SIZE` | 15 | 棋盘大小 |
| `MORALE_MAX` | 3 | 最高士气星数 |
| `MORALE_ATK_PER_STAR` | 0.10 | 每星 +10% 攻击 |
| `MORALE_DEF_PER_STAR` | 0.05 | 每星 +5% 防御 |
| `COUNTER_DAMAGE_MULT` | 0.5 | 反击伤害乘数（0.5 = 火纹 50%）|
| `EXP_TO_LEVEL` | 60 | 升级所需经验（仅影响杀敌士气后）|
| `MAX_LEVEL` | 10 | 最高等级 |
| `TURN_TIMEOUT_HOURS` | 24 | 玩家超时自动跳过 |
| `AI_THINK_DELAY_SECONDS` | 1.2 | AI 行动间隔（人眼友好）|
| `ABANDONED_LOBBY_MINUTES` | 30 | 空房间多久后清理 |

---

## 🧪 测试

```bash
cd game
source venv/bin/activate
pytest tests/ -v
```

测试覆盖：
- 地图生成 / 寻路
- 战斗公式（士气 / 兵种克制 / 暴击）
- 反击触发条件
- API 端到端

---

## 🐛 常见问题

**端口 8000 被占用**
```bash
# Windows
netstat -ano | findstr ":8000"
taskkill /F /PID <pid>
```

**数据库结构变了导致 `no such column` 错误**
```bash
rm game/battleblitz.db   # 重启会自动建新表
```

**Pydantic aarch64 安装失败**
`pydantic==2.10.3` 已锁定兼容 aarch64 wheels

---

## 📜 许可

MIT
