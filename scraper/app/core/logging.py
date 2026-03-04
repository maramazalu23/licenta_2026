# scraper/app/core/logging.py
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_dir: str | Path = "logs", level_console: int = logging.INFO) -> logging.Logger:
    """
    Configurează logging pentru proiect.
    - Console: INFO (default)
    - File: DEBUG
    Returnează logger-ul root al proiectului: "scraper"
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("scraper")
    logger.setLevel(logging.DEBUG)

    # evită handler-e duplicate
    if logger.handlers:
        return logger

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # File handler (DEBUG) cu rotație
    fh = RotatingFileHandler(
        log_dir / "scraper.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    # Console handler (INFO)
    ch = logging.StreamHandler()
    ch.setLevel(level_console)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)

    logger.propagate = False
    return logger