"""
FastAPI application entrypoint.

Run with:
    cd game
    source venv/Scripts/activate     # Windows
    # source venv/bin/activate       # Linux/Raspberry Pi
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import APP_TITLE, APP_VERSION, DEFAULT_DB_PATH
from app.database import dispose_db, init_db
from app.logging_config import log_server_lifecycle, setup_logging
from app.routes import actions as actions_routes
from app.routes import debug_ws as debug_ws_routes
from app.routes import game as game_routes
from app.routes import turns as turns_routes
from app.progression import api as progression_api


WEB_DIR = Path(__file__).resolve().parent / "web"

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: configure logging + create tables + start scheduler.
    Shutdown: stop scheduler + dispose DB.
    """
    # Read host/port from uvicorn if available (we set them via CLI), else "?".
    host = os.environ.get("BB_HOST", "?")
    try:
        port = int(os.environ.get("BB_PORT", "0"))
    except ValueError:
        port = 0

    setup_logging()
    log_server_lifecycle("starting", host=host, port=port,
                         version=APP_VERSION, db_path=DEFAULT_DB_PATH)
    try:
        await init_db()
        turns_routes.start_scheduler()
    except Exception:
        logger.exception("Startup failed")
        raise
    log_server_lifecycle("started", host=host, port=port,
                         version=APP_VERSION, db_path=DEFAULT_DB_PATH)
    try:
        yield
    finally:
        log_server_lifecycle("stopping")
        turns_routes.stop_scheduler()
        await dispose_db()
        log_server_lifecycle("stopped")


app = FastAPI(
    title=APP_TITLE,
    version=APP_VERSION,
    description="Turn-based strategy game server (BattleBlitz).",
    lifespan=lifespan,
)


@app.get("/", tags=["meta"])
async def root():
    """Redirect root to the game client."""
    return RedirectResponse(url="/ui/")


@app.get("/ui", tags=["meta"])
async def ui_root():
    return RedirectResponse(url="/ui/")


@app.get("/ui/", response_class=FileResponse, tags=["meta"])
async def ui_index():
    return FileResponse(WEB_DIR / "index.html")


# Static asset mount MUST come after the API routes so its catch-all
# doesn't shadow them.
app.mount(
    "/ui",
    StaticFiles(directory=str(WEB_DIR), html=True),
    name="ui",
)


@app.get("/healthz", tags=["meta"])
async def healthz() -> dict:
    return {"status": "ok"}


# API routers
app.include_router(game_routes.router)
app.include_router(actions_routes.router)
app.include_router(turns_routes.router)
app.include_router(debug_ws_routes.router)
app.include_router(progression_api.router, prefix="/progression")