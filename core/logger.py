"""
Rotating logger writing to ~/.local/share/macfan-monitor/macfan-monitor.log.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path.home() / ".local/share/fresh-fan-manager"
LOG_FILE = LOG_DIR / "fresh-fan-manager.log"

_logger: logging.Logger | None = None


def get_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("fresh-fan-manager")
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(LOG_FILE, maxBytes=512_000, backupCount=3, encoding="utf-8")
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    # Also echo to stderr in dev
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    stream.setLevel(logging.WARNING)
    logger.addHandler(stream)
    _logger = logger
    return logger


def log_path() -> Path:
    return LOG_FILE
