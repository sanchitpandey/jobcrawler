"""
logger.py
─────────
Centralised logging for the job crawler pipeline.

Every module imports like:
    from logger import get_logger
    log = get_logger(__name__)

Outputs to:
  - Console (INFO+, coloured)
  - output/pipeline.log (DEBUG+, full detail, rotates at 5 MB)
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# ── ANSI colours for terminal ──────────────────────────────────────────────────
_RESET  = "\033[0m"
_COLORS = {
    "DEBUG":    "\033[36m",   # cyan
    "INFO":     "\033[32m",   # green
    "WARNING":  "\033[33m",   # yellow
    "ERROR":    "\033[31m",   # red
    "CRITICAL": "\033[35m",   # magenta
}

class _ColourFormatter(logging.Formatter):
    FMT = "%(asctime)s  %(levelname)-8s  %(name)-18s  %(message)s"
    DATEFMT = "%H:%M:%S"

    def format(self, record: logging.LogRecord) -> str:
        colour = _COLORS.get(record.levelname, "")
        formatter = logging.Formatter(
            f"{colour}{self.FMT}{_RESET}", datefmt=self.DATEFMT
        )
        return formatter.format(record)

class _PlainFormatter(logging.Formatter):
    FMT    = "%(asctime)s  %(levelname)-8s  %(name)-18s  %(message)s"
    DATEFMT = "%Y-%m-%d %H:%M:%S"

    def format(self, record: logging.LogRecord) -> str:
        return logging.Formatter(self.FMT, datefmt=self.DATEFMT).format(record)


_configured = False

def _setup():
    global _configured
    if _configured:
        return
    _configured = True

    Path("output").mkdir(exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Console — INFO and above, coloured
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(_ColourFormatter())
    root.addHandler(ch)

    # Rotating file — DEBUG and above, plain text
    fh = RotatingFileHandler(
        "output/pipeline.log",
        maxBytes=5 * 1024 * 1024,   # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_PlainFormatter())
    root.addHandler(fh)

    # Silence noisy third-party loggers
    for noisy in ["urllib3", "httpx", "httpcore", "playwright", "asyncio"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    _setup()
    # Use short names: "jobcrawler.score" → strip leading package path
    short = name.split(".")[-1] if "." in name else name
    return logging.getLogger(f"crawler.{short}")