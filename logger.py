"""Centralised logging for the job crawler pipeline."""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from core.settings import get_settings

_RESET = "\033[0m"
_COLORS = {
    "DEBUG": "\033[36m",
    "INFO": "\033[32m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[35m",
}


class _ColourFormatter(logging.Formatter):
    FMT = "%(asctime)s  %(levelname)-8s  %(name)-18s  %(message)s"
    DATEFMT = "%H:%M:%S"

    def format(self, record: logging.LogRecord) -> str:
        colour = _COLORS.get(record.levelname, "")
        formatter = logging.Formatter(f"{colour}{self.FMT}{_RESET}", datefmt=self.DATEFMT)
        return formatter.format(record)


class _PlainFormatter(logging.Formatter):
    FMT = "%(asctime)s  %(levelname)-8s  %(name)-18s  %(message)s"
    DATEFMT = "%Y-%m-%d %H:%M:%S"

    def format(self, record: logging.LogRecord) -> str:
        return logging.Formatter(self.FMT, datefmt=self.DATEFMT).format(record)


_configured = False


def _setup():
    global _configured
    if _configured:
        return
    _configured = True

    settings = get_settings()
    Path(settings.paths.output_dir).mkdir(exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(_ColourFormatter())
    root.addHandler(ch)

    fh = RotatingFileHandler(
        str(Path(settings.paths.output_dir) / "pipeline.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_PlainFormatter())
    root.addHandler(fh)

    for noisy in ["urllib3", "httpx", "httpcore", "playwright", "asyncio"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    _setup()
    short = name.split(".")[-1] if "." in name else name
    return logging.getLogger(f"crawler.{short}")
