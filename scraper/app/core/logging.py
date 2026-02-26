# scraper/app/core/logging.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional


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
    logger.setLevel(logging.DEBUG)  # păstrăm debug în fișier

    # IMPORTANT: evităm handler-e duplicate dacă setup_logging e chemat de mai multe ori
    if logger.handlers:
        return logger

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # File handler (DEBUG)
    fh = logging.FileHandler(log_dir / "scraper.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    # Console handler (INFO)
    ch = logging.StreamHandler()
    ch.setLevel(level_console)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)

    # Nu dubla logurile prin root logger
    logger.propagate = False
    return logger