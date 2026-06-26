"""
Centralized logging configuration for the BattleBlitz server.

Implements the patterns described in
https://github.com/YoukoSaint/Logging_Standard_for_Agent :

  * Time-stamped per-run log files (`logs/BattleBlitz_YYYYMMDD_HHMMSS.log`).
  * Dual handlers: file = DEBUG with module:line, console = INFO concise.
  * `RotatingFileHandler` at 10 MiB x 7 backups so old runs age out cleanly.
  * Module loggers everywhere via `logging.getLogger(__name__)`.
  * Dedicated `audit.user` child logger for `USER_ACTION | ...` lines.
  * Optional `psutil`-based HEALTH line emitter for the scheduler.

Usage in `app.main`:

    from app.logging_config import setup_logging, log_server_lifecycle
    setup_logging()
    log_server_lifecycle("starting", host=host, port=port)

Per-module boilerplate:

    import logging
    logger = logging.getLogger(__name__)
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import time
from datetime import datetime
from typing import Optional


# ============================================================
# Constants
# ============================================================

APP_LOGGER_NAME: str = "battleblitz"      # child of root, for service-level lines
AUDIT_LOGGER_NAME: str = "audit.user"     # USER_ACTION lines live here
HEALTH_LOGGER_NAME: str = "battleblitz.health"  # HEALTH lines (not chatty)

DEFAULT_LOG_DIR: str = "logs"
DEFAULT_FILE_MAX_BYTES: int = 10 * 1024 * 1024   # 10 MiB
DEFAULT_FILE_BACKUP_COUNT: int = 7
DEFAULT_CONSOLE_LEVEL: int = logging.INFO

# Track process start so the HEALTH line can report `uptime=` without
# each module having to know the launch time.
_PROCESS_START_MONOTONIC: float = time.monotonic()
_PROCESS_START_WALL: datetime = datetime.now()


# ============================================================
# setup_logging()
# ============================================================

def setup_logging(
    app_name: str = "BattleBlitz",
    log_dir: str = DEFAULT_LOG_DIR,
    console_level: int = DEFAULT_CONSOLE_LEVEL,
    file_max_bytes: int = DEFAULT_FILE_MAX_BYTES,
    file_backup_count: int = DEFAULT_FILE_BACKUP_COUNT,
) -> str:
    """Configure root logger with dual handlers. Returns the log file path.

    Idempotent: clears any previously-installed handlers, so it's safe to call
    from test fixtures that may configure logging first.
    """
    os.makedirs(log_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f"{app_name}_{ts}.log")

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    # Important: clear existing handlers — pytest's caplog installs its own,
    # and uvicorn/loguru may also attach at import time.
    for h in list(root.handlers):
        root.removeHandler(h)

    # ── File: full DEBUG, with module:line for code navigation ──
    fh = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=file_max_bytes,
        backupCount=file_backup_count,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-7s] %(name)s:%(lineno)d - %(message)s"
    ))
    root.addHandler(fh)

    # ── Console: INFO concise (operators only) ──
    ch = logging.StreamHandler()
    ch.setLevel(console_level)
    ch.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-7s] %(message)s"
    ))
    root.addHandler(ch)

    # Quiet down a few noisy third-party loggers that we don't need at INFO.
    for noisy in ("httpx", "httpcore", "aiosqlite", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Touch the app-level child loggers so they appear in the file even before
    # their modules log anything (helps with `tail -f` of a freshly-started server).
    logging.getLogger(APP_LOGGER_NAME)
    logging.getLogger(AUDIT_LOGGER_NAME)
    logging.getLogger(HEALTH_LOGGER_NAME)

    logging.info("Logging initialized: %s", log_path)
    return log_path


# ============================================================
# Lifecycle helpers
# ============================================================

def log_server_lifecycle(
    phase: str,
    *,
    host: str = "?",
    port: int = 0,
    version: str = "?",
    db_path: str = "?",
) -> None:
    """Emit a server-lifecycle INFO line. `phase` is "starting" or "stopped"."""
    logger = logging.getLogger(APP_LOGGER_NAME)
    uptime = int(time.monotonic() - _PROCESS_START_MONOTONIC)
    if phase == "starting":
        logger.info(
            "Server starting: app=BattleBlitz version=%s host=%s port=%d db=%s",
            version, host, port, db_path,
        )
    elif phase == "started":
        logger.info(
            "Server started: listening on %s:%d (uptime=%ds)",
            host, port, uptime,
        )
    elif phase == "stopping":
        logger.info("Server stopping: uptime=%ds", uptime)
    elif phase == "stopped":
        logger.info("Server stopped: uptime=%ds", uptime)
    else:
        logger.info("Server lifecycle: phase=%s uptime=%ds", phase, uptime)


def get_audit_logger() -> logging.Logger:
    """Return the audit.user logger (USER_ACTION lines go here)."""
    return logging.getLogger(AUDIT_LOGGER_NAME)


def get_health_logger() -> logging.Logger:
    """Return the health logger (HEALTH lines)."""
    return logging.getLogger(HEALTH_LOGGER_NAME)


# ============================================================
# Health metrics
# ============================================================

def collect_health_metrics(prev_rss_mb: Optional[float] = None) -> dict:
    """Snapshot process + system metrics. Never raises (degraded on failure)."""
    out = {
        "uptime_sec": int(time.monotonic() - _PROCESS_START_MONOTONIC),
        "rss_mb": 0.0,
        "rss_delta_mb": 0.0,
        "cpu_pct": 0.0,
        "thread_count": 0,
        "disk_data_pct": 0.0,
        "disk_log_pct": 0.0,
    }
    try:
        import psutil  # local import: psutil is optional
        proc = psutil.Process()
        rss = proc.memory_info().rss / 1024 / 1024
        out["rss_mb"] = rss
        if prev_rss_mb is not None:
            out["rss_delta_mb"] = rss - prev_rss_mb
        out["cpu_pct"] = proc.cpu_percent(interval=None)
        out["thread_count"] = proc.num_threads()
        for mount, key in [(".", "disk_data_pct"), ("logs", "disk_log_pct")]:
            try:
                out[key] = psutil.disk_usage(mount).percent
            except (FileNotFoundError, OSError):
                pass
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(HEALTH_LOGGER_NAME).debug(
            "psutil metrics unavailable: %s", exc,
        )
    return out


def format_health_line(
    metrics: dict,
    *,
    playing_games: int = 0,
    waiting_games: int = 0,
    final: bool = False,
) -> str:
    """Render a HEALTH line per the standard. Grep-friendly: `HEALTH |`."""
    parts = [
        f"uptime={metrics['uptime_sec']}s",
        f"rss={metrics['rss_mb']:.1f}MB (Δ{metrics['rss_delta_mb']:+.1f})",
        f"cpu={metrics['cpu_pct']:.1f}%",
        f"thr={metrics['thread_count']}",
        f"games:playing={playing_games}|waiting={waiting_games}",
        f"disk:data={metrics['disk_data_pct']:.0f}%|log={metrics['disk_log_pct']:.0f}%",
    ]
    prefix = "HEALTH |"
    if final:
        prefix += " final=true |"
    return f"{prefix} " + " | ".join(parts)


__all__ = [
    "APP_LOGGER_NAME",
    "AUDIT_LOGGER_NAME",
    "HEALTH_LOGGER_NAME",
    "setup_logging",
    "log_server_lifecycle",
    "get_audit_logger",
    "get_health_logger",
    "collect_health_metrics",
    "format_health_line",
]
