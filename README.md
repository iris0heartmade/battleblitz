# BattleBlitz

Turn-based strategy game server (Fire Emblem / Advance Wars style).
Backend: Python + FastAPI + SQLAlchemy (async) + SQLite.
Frontend: vanilla HTML/CSS/JS served by FastAPI.

## Quick start

### Windows / macOS / Linux (development)

```bash
cd game
python -m venv venv

# Activate venv:
# Windows Git Bash:   source venv/Scripts/activate
# Windows PowerShell: venv\Scripts\Activate.ps1
 macOS/Linux:        source venv/bin/activate

pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open <http://localhost:8000/> for the web UI.

### Raspberry Pi (deployment)

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git
cd /home/pi
git clone <your-repo-url> BattleBlitz
cd BattleBlitz/game
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Run as a systemd service (auto-start on boot, auto-restart on crash):

```bash
sudo tee /etc/systemd/system/battleblitz.service > /dev/null <<EOF
[Unit]
Description=BattleBlitz Game Server
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/BattleBlitz/game
ExecStart=/home/pi/BattleBlitz/game/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now battleblitz
sudo systemctl status battleblitz
```

View logs with `sudo journalctl -u battleblitz -f`.

## Project layout

```
BattleBlitz/
├── .gitignore
├── README.md
└── game/
    ├── app/
    │   ├── __init__.py
    │   ├── main.py            # FastAPI app + lifespan
    │   ├── config.py          # All gameplay constants
    │   ├── database.py        # Async engine, sessionmaker, init_db
    │   ├── models.py          # Game / Player / Unit / Tile / ActionLog
    │   ├── schemas.py         # Pydantic request/response models
    │   ├── game_logic.py      # Map gen, damage, level-up, AI, end-of-turn
    │   ├── utils.py           # BFS pathfinding, LOS, distance
    │   └── routes/
    │       ├── game.py        # /games, /join, /start, /state, /presets, /add-ai
    │       ├── actions.py     # /move, /attack, /skill, /wait
    │       └── turns.py       # /end-turn + background timeout scheduler
    ├── web/
    │   ├── index.html         # SPA with menu/lobby/board/AI mgmt
    │   ├── style.css
    │   └── app.js
    ├── requirements.txt
    ├── start.bat              # Windows convenience launcher
    └── stop.bat               # Windows convenience shutdown
```

## API endpoints (highlights)

| Method | Path | Purpose |
|--------|------|---------|
| POST   | `/games`                       | Create a game |
| POST   | `/games/{id}/join`             | Join as a player |
| POST   | `/games/{id}/start`            | Begin play |
| GET    | `/games/{id}/state`            | Full state snapshot |
| POST   | `/games/{id}/move`             | Move a unit |
| POST   | `/games/{id}/attack`           | Attack |
| POST   | `/games/{id}/skill`            | Use a skill |
| POST   | `/games/{id}/wait`             | Skip a unit |
| POST   | `/games/{id}/end-turn`         | End your turn |
| POST   | `/games/{id}/add-ai`           | Add an AI player |
| DELETE | `/games/{id}/players/{pid}`    | Remove a player |
| POST   | `/games/{id}/rejoin`           | Resume via player_id |
| GET    | `/games/presets`               | Map & unit-composition presets |
| GET    | `/`                             | Redirects to the UI |
| GET    | `/docs`                         | OpenAPI / Swagger UI |

Full docs at <http://your-host:8000/docs>.

## Fairness rules

- The first player (seat 0) is limited to **1 action** on their first turn only.
  Every other player (and every later turn) requires **2 actions** per turn.
- Each unit can only **move once per turn**, but can still attack after moving.
- After moving / attacking / waiting / using a skill, the unit enters "standby"
  for the rest of the turn.

## AI players

- Built-in rule-based AI: prioritize low-HP targets, capture castles, stay
  near allies, use terrain defensively.
- Healers rally first, then melee units act.
- A chain of AI players will play sequentially without human intervention.

## License

MIT