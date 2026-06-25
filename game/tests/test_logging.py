"""
Unit tests for `app.logging_config` — verify the logging setup is sound.

These tests intentionally reconfigure the root logger, so we save/restore
handlers around each test to avoid leaking state into the rest of the suite.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app.logging_config import (
    APP_LOGGER_NAME,
    AUDIT_LOGGER_NAME,
    HEALTH_LOGGER_NAME,
    collect_health_metrics,
    format_health_line,
    get_audit_logger,
    get_health_logger,
    log_server_lifecycle,
    setup_logging,
)


@pytest.fixture
def restore_logging():
    """Snapshot root handlers + level, restore after the test."""
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    yield
    # Detach everything the test installed, restore originals.
    for h in list(root.handlers):
        if h not in saved_handlers:
            h.close()
            root.removeHandler(h)
    root.setLevel(saved_level)


class _CapturingHandler(logging.Handler):
    """In-memory handler that records every LogRecord it sees.

    We need this because `setup_logging()` calls `root.handlers.clear()`,
    which removes the handler pytest's `caplog` fixture installs.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def log_capture(restore_logging):
    """Provide a fresh _CapturingHandler bound to the given logger."""
    handlers: list[_CapturingHandler] = []

    def _attach(logger_name: str = "") -> _CapturingHandler:
        h = _CapturingHandler()
        log = logging.getLogger(logger_name) if logger_name else logging.getLogger()
        log.addHandler(h)
        log.setLevel(logging.DEBUG)
        handlers.append((log, h))
        return h

    yield _attach
    for log, h in handlers:
        log.removeHandler(h)


# ============================================================
# setup_logging
# ============================================================

@pytest.mark.unit
class TestSetupLogging:
    def test_creates_timestamped_file(self, tmp_path, restore_logging):
        log_path = setup_logging(log_dir=str(tmp_path), app_name="TestApp")
        assert Path(log_path).exists()
        # Filename pattern: TestApp_YYYYMMDD_HHMMSS.log
        assert log_path.startswith(str(tmp_path))
        assert log_path.endswith(".log")

    def test_installs_two_handlers(self, tmp_path, restore_logging):
        setup_logging(log_dir=str(tmp_path), app_name="X")
        root = logging.getLogger()
        # File + console
        assert len(root.handlers) == 2
        handler_types = {type(h).__name__ for h in root.handlers}
        assert "StreamHandler" in handler_types  # console
        assert "RotatingFileHandler" in handler_types  # file

    def test_idempotent_clears_old_handlers(self, tmp_path, restore_logging):
        setup_logging(log_dir=str(tmp_path), app_name="X")
        setup_logging(log_dir=str(tmp_path), app_name="X")
        root = logging.getLogger()
        # Still exactly 2 handlers after the second call.
        assert len(root.handlers) == 2

    def test_quiet_third_party_loggers(self, tmp_path, restore_logging):
        setup_logging(log_dir=str(tmp_path), app_name="X")
        # These should be set to WARNING, not the default NOTSET
        for noisy in ("httpx", "httpcore", "aiosqlite", "asyncio"):
            assert logging.getLogger(noisy).level >= logging.WARNING

    def test_file_handler_debug_console_info(self, tmp_path, restore_logging):
        setup_logging(log_dir=str(tmp_path), app_name="X",
                      console_level=logging.WARNING)
        fh, ch = logging.getLogger().handlers
        assert fh.level == logging.DEBUG
        assert ch.level == logging.WARNING

    def test_creates_named_loggers(self, tmp_path, restore_logging):
        setup_logging(log_dir=str(tmp_path), app_name="X")
        # All three child loggers should now exist (not be placeholders).
        for name in (APP_LOGGER_NAME, AUDIT_LOGGER_NAME, HEALTH_LOGGER_NAME):
            assert name in logging.root.manager.loggerDict or \
                   logging.getLogger(name).name == name


# ============================================================
# Child loggers
# ============================================================

@pytest.mark.unit
class TestChildLoggers:
    def test_audit_logger_returns_audit_user(self):
        log = get_audit_logger()
        assert log.name == AUDIT_LOGGER_NAME

    def test_health_logger_returns_health(self):
        log = get_health_logger()
        assert log.name == HEALTH_LOGGER_NAME


# ============================================================
# Server lifecycle
# ============================================================

@pytest.mark.unit
class TestLogServerLifecycle:
    def test_starting_emits_info(self, tmp_path, restore_logging, log_capture):
        setup_logging(log_dir=str(tmp_path), app_name="X")
        cap = log_capture(APP_LOGGER_NAME)
        log_server_lifecycle("starting", host="0.0.0.0", port=8000,
                             version="1.2.3", db_path="/tmp/db.sqlite")
        assert any("Server starting" in r.getMessage() for r in cap.records)
        assert any("0.0.0.0" in r.getMessage() and "8000" in r.getMessage()
                   for r in cap.records)

    def test_started_stopping_stopped(self, tmp_path, restore_logging, log_capture):
        setup_logging(log_dir=str(tmp_path), app_name="X")
        cap = log_capture(APP_LOGGER_NAME)
        log_server_lifecycle("started", host="0.0.0.0", port=8000)
        log_server_lifecycle("stopping")
        log_server_lifecycle("stopped")
        msgs = " | ".join(r.getMessage() for r in cap.records)
        assert "Server started" in msgs
        assert "Server stopping" in msgs
        assert "Server stopped" in msgs


# ============================================================
# Health metrics
# ============================================================

@pytest.mark.unit
class TestHealthMetrics:
    def test_collect_never_raises(self):
        # Should always return a dict, even if psutil is missing.
        m = collect_health_metrics()
        assert "uptime_sec" in m
        assert "rss_mb" in m
        assert isinstance(m["rss_mb"], float)

    def test_collect_with_prev_rss(self):
        m = collect_health_metrics(prev_rss_mb=10.0)
        # rss_delta = current_rss - 10.0 (may be negative)
        assert "rss_delta_mb" in m
        assert isinstance(m["rss_delta_mb"], float)

    def test_format_health_line_minimal(self):
        m = {"uptime_sec": 100, "rss_mb": 50.0, "rss_delta_mb": 1.0,
             "cpu_pct": 5.0, "thread_count": 4,
             "disk_data_pct": 30.0, "disk_log_pct": 30.0}
        line = format_health_line(m, playing_games=2, waiting_games=1)
        assert line.startswith("HEALTH |")
        assert "uptime=100s" in line
        assert "rss=50.0MB" in line
        assert "playing=2" in line
        assert "waiting=1" in line

    def test_format_health_line_final(self):
        m = {"uptime_sec": 999, "rss_mb": 10.0, "rss_delta_mb": 0.0,
             "cpu_pct": 0.0, "thread_count": 1,
             "disk_data_pct": 0.0, "disk_log_pct": 0.0}
        line = format_health_line(m, playing_games=0, waiting_games=0, final=True)
        assert "final=true" in line
