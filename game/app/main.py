"""
FastAPI application entrypoint.

Run with:
    cd game
    source venv/Scripts/activate     # Windows
    # source venv/bin/activate       # Linux/Raspberry Pi
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import APP_TITLE, APP_VERSION
from app.database import dispose_db, init_db
from app.routes import actions as actions_routes
from app.routes import game as game_routes
from app.routes import turns as turns_routes


WEB_DIR = Path(__file__).resolve().parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables + start turn scheduler. Shutdown: stop + dispose."""
    await init_db()
    turns_routes.start_scheduler()
    try:
        yield
    finally:
        turns_routes.stop_scheduler()
        await dispose_db()


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