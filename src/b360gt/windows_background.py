"""Silent Windows launcher for the local B360GT control panel."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .web_ui import run_ui


def log_path() -> Path:
    """Return the per-user background log path."""
    base = os.environ.get("LOCALAPPDATA")
    if base:
        root = Path(base)
    else:
        root = Path.home() / "AppData" / "Local"
    return root / "b360gt" / "logs" / "background.log"


def main() -> int:
    """Run the control panel without opening a browser or console window."""
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("b360gt.background")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = RotatingFileHandler(
        path,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )
    logger.addHandler(handler)
    try:
        logger.info("Starting B360GT background control panel on 127.0.0.1:8765")
        run_ui(port=8765, open_browser=False, quiet=True)
        logger.info("B360GT background control panel stopped")
        return 0
    except Exception:
        logger.exception("B360GT background control panel failed")
        return 1
    finally:
        logger.removeHandler(handler)
        handler.close()
