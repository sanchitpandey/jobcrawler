"""Tests for api/logger.py — no I/O, no network."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import json
import logging
import pytest

from api.logger import (
    ColourFormatter,
    JsonFormatter,
    get_logger,
    request_id_var,
    setup_logging,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_record(msg: str = "hello", level: int = logging.INFO, **kwargs) -> logging.LogRecord:
    record = logging.LogRecord(
        name="crawler.test",
        level=level,
        pathname="",
        lineno=0,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for key, value in kwargs.items():
        setattr(record, key, value)
    return record


# ── JsonFormatter ─────────────────────────────────────────────────────────────

def test_json_formatter_produces_valid_json():
    line = JsonFormatter().format(_make_record("hello"))
    payload = json.loads(line)  # must not raise
    assert isinstance(payload, dict)


def test_json_formatter_required_keys():
    payload = json.loads(JsonFormatter().format(_make_record("hello")))
    for key in ("ts", "level", "logger", "msg", "request_id"):
        assert key in payload, f"missing key: {key}"


def test_json_formatter_msg_content():
    payload = json.loads(JsonFormatter().format(_make_record("test message")))
    assert payload["msg"] == "test message"


def test_json_formatter_level_name():
    record = _make_record("x", level=logging.WARNING)
    payload = json.loads(JsonFormatter().format(record))
    assert payload["level"] == "WARNING"


def test_json_formatter_ts_format():
    payload = json.loads(JsonFormatter().format(_make_record()))
    # e.g. "2026-04-02T10:30:00.123Z"
    ts = payload["ts"]
    assert ts.endswith("Z")
    assert "T" in ts


def test_json_formatter_includes_extra_fields():
    record = _make_record("req")
    record.status = 200
    record.duration_ms = 42.5
    payload = json.loads(JsonFormatter().format(record))
    assert payload["status"] == 200
    assert payload["duration_ms"] == 42.5


def test_json_formatter_uses_request_id_contextvar():
    token = request_id_var.set("abc12345")
    try:
        payload = json.loads(JsonFormatter().format(_make_record()))
        assert payload["request_id"] == "abc12345"
    finally:
        request_id_var.reset(token)


def test_json_formatter_default_request_id_is_dash():
    # Ensure no leftover token from other tests
    token = request_id_var.set("-")
    try:
        payload = json.loads(JsonFormatter().format(_make_record()))
        assert payload["request_id"] == "-"
    finally:
        request_id_var.reset(token)


def test_json_formatter_does_not_leak_internal_fields():
    payload = json.loads(JsonFormatter().format(_make_record()))
    for key in ("args", "levelno", "lineno", "pathname", "msecs", "exc_info"):
        assert key not in payload, f"internal field leaked: {key}"


# ── ColourFormatter ───────────────────────────────────────────────────────────

def test_colour_formatter_produces_string():
    line = ColourFormatter().format(_make_record("colour test"))
    assert isinstance(line, str)
    assert "colour test" in line


def test_colour_formatter_contains_level():
    line = ColourFormatter().format(_make_record("x", level=logging.WARNING))
    assert "WARNING" in line


def test_colour_formatter_contains_ansi_escape():
    line = ColourFormatter().format(_make_record())
    assert "\033[" in line


# ── get_logger ────────────────────────────────────────────────────────────────

def test_get_logger_bare_name():
    logger = get_logger("scorer")
    assert logger.name == "crawler.scorer"


def test_get_logger_dotted_module_name():
    logger = get_logger("api.services.scorer")
    assert logger.name == "crawler.scorer"


def test_get_logger_already_prefixed():
    logger = get_logger("crawler.providers")
    assert logger.name == "crawler.providers"


def test_get_logger_returns_logging_logger():
    assert isinstance(get_logger("test"), logging.Logger)


# ── setup_logging ─────────────────────────────────────────────────────────────

def test_setup_logging_idempotent(monkeypatch):
    """Calling setup_logging twice must not add duplicate handlers."""
    import api.logger as _logger_mod
    # Reset the guard so we can call setup_logging fresh in this test
    monkeypatch.setattr(_logger_mod, "_configured", False)
    root = logging.getLogger()
    before = len(root.handlers)

    _logger_mod.setup_logging(app_env="development")
    after_first = len(root.handlers)

    _logger_mod.setup_logging(app_env="development")  # second call — no-op
    after_second = len(root.handlers)

    assert after_second == after_first  # idempotent
    # Restore so other tests are not affected
    monkeypatch.setattr(_logger_mod, "_configured", True)


def test_setup_logging_dev_uses_colour_formatter(monkeypatch):
    import api.logger as _logger_mod
    monkeypatch.setattr(_logger_mod, "_configured", False)
    root = logging.getLogger()
    root.handlers.clear()

    _logger_mod.setup_logging(app_env="development")
    assert any(isinstance(h.formatter, ColourFormatter) for h in root.handlers)
    monkeypatch.setattr(_logger_mod, "_configured", True)


def test_setup_logging_prod_uses_json_formatter(monkeypatch):
    import api.logger as _logger_mod
    monkeypatch.setattr(_logger_mod, "_configured", False)
    root = logging.getLogger()
    root.handlers.clear()

    _logger_mod.setup_logging(app_env="production")
    assert any(isinstance(h.formatter, JsonFormatter) for h in root.handlers)
    monkeypatch.setattr(_logger_mod, "_configured", True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
