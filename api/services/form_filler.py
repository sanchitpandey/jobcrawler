"""Profile-driven helpers for auto-filling job application forms."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import api.services.llm as llm_service
from api.logger import get_logger

log = get_logger(__name__)

# Matches labels that generally expect a numeric or duration logic
_NUMERIC_HINT_PATTERN = re.compile(r"\byrs?\b.*exp|\byears?\b.*exp|duration|period|length|salary|ctc|expected|present|current", re.I)

MANUAL_REVIEW_PATTERNS = re.compile(
    r"describe (a time|an experience|when|how)|tell us about|cover letter|"
    r"why do you want|what motivates|greatest (strength|weakness)|"
    r"where do you see yourself|what are your long.term",
    re.I,
)

import os
from pathlib import Path

# TODO: Migrate to Redis cache in production
CACHE_DIR = Path("output/cache")
CACHE_TTL_DAYS = 30
_CACHE_MAX_SIZE = 10_000

_memory_cache: dict[tuple[str, str], dict] = None

def _load_cache() -> dict[tuple[str, str], dict]:
    global _memory_cache
    if _memory_cache is not None:
        return _memory_cache
    
    _memory_cache = {}
    if not CACHE_DIR.exists():
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        
    for cache_file in CACHE_DIR.glob("user_*.json"):
        user_id = cache_file.stem.split("_", 1)[1]
        try:
            user_data = json.loads(cache_file.read_text(encoding="utf-8"))
            for q, entry in user_data.items():
                _memory_cache[(user_id, q)] = entry
        except Exception:
            pass
    return _memory_cache

def _persist_cache_for_user(user_id: str) -> None:
    cache = _load_cache()
    user_data = {q: entry for (u, q), entry in cache.items() if u == user_id}
    if not CACHE_DIR.exists():
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
    file_path = CACHE_DIR / f"user_{user_id}.json"
    file_path.write_text(json.dumps(user_data, ensure_ascii=False, indent=2), encoding="utf-8")

@dataclass
class FilledAnswer:
    value: str
    source: str
    is_manual_review: bool = False
    raw_question: str = ""
    confidence: float = 1.0


def _cache_key(user_id: str, question: str) -> tuple[str, str]:
    normalized = re.sub(r"\s+", " ", question).strip().lower()
    return (user_id, normalized)


def _cache_get(user_id: str, question: str) -> FilledAnswer | None:
    key = _cache_key(user_id, question)
    cache = _load_cache()
    entry = cache.get(key)
    if entry is None:
        return None
    if datetime.now() - datetime.fromisoformat(entry["cached_at"]) > timedelta(days=CACHE_TTL_DAYS):
        del cache[key]
        _persist_cache_for_user(user_id)
        log.debug("Cache entry expired for key: %r", question[:60])
        return None
    log.debug("Cache hit: %r", question[:60])
    return FilledAnswer(
        value=entry["value"],
        source="cache",
        is_manual_review=entry["is_manual_review"],
        raw_question=entry["raw_question"],
        confidence=entry["confidence"],
    )


def _cache_put(user_id: str, question: str, answer: FilledAnswer) -> None:
    key = _cache_key(user_id, question)
    cache = _load_cache()
    
    if len(cache) >= _CACHE_MAX_SIZE:
        sorted_keys = sorted(cache.keys(), key=lambda k: cache[k]["cached_at"])
        evict_count = _CACHE_MAX_SIZE // 10
        for k in sorted_keys[:evict_count]:
            del cache[k]
            
    cache[key] = {
        "value": answer.value,
        "source": answer.source,
        "is_manual_review": answer.is_manual_review,
        "raw_question": answer.raw_question,
        "confidence": answer.confidence,
        "cached_at": datetime.now().isoformat(),
    }
    _persist_cache_for_user(user_id)


def _get_national_phone(phone: str) -> str:
    """If phone is '+91-8527104455', returns '8527104455' to avoid duplication."""
    phone = phone.strip()
    if phone.startswith("+"):
        if "-" in phone:
            return phone.split("-", 1)[1].strip()
        if " " in phone:
            return phone.split(" ", 1)[1].strip()
    return phone

def build_standard_patterns(candidate: dict) -> list[tuple[re.Pattern[str], callable]]:
    """Build the STANDARD_PATTERNS list bound to the given candidate dict.
    Note: We only map hardcoded patterns for absolute basic identifiers.
    For everything else, we let the LLM dynamically decide based on field type and error states.
    """
    return [
        (re.compile(r"^\s*email\s*$", re.I), lambda: candidate["email"]),
        (re.compile(r"phone|mobile|contact number", re.I), lambda: _get_national_phone(candidate.get("phone", ""))),
        (re.compile(r"\blinkedin\b", re.I), lambda: candidate["linkedin"]),
        (re.compile(r"\bgithub\b", re.I), lambda: candidate["github"]),
        (re.compile(r"\bportfolio\b", re.I), lambda: candidate["portfolio"]),
    ]


def _match_option(value: str, options: list[str]) -> str | None:
    candidate = value.lower().strip()
    # Exact match
    for option in options:
        if option.lower() == candidate:
            return option
    # Substring match
    for option in options:
        if candidate in option.lower() or option.lower() in candidate:
            return option
    # Boolean shorthands
    if candidate in {"yes", "true", "1"}:
        for option in options:
            if option.lower() in {"yes", "true"}:
                return option
    if candidate in {"no", "false", "0"}:
        for option in options:
            if option.lower() in {"no", "false"}:
                return option
    # Semantic: "available immediately" / "immediate" / "0 days" / "no notice" maps to
    # the shortest notice-period option (e.g. "Less than 15 Days", "Immediate", "0-15 days")
    if any(kw in candidate for kw in ("immediate", "0 day", "no notice", "available now")):
        # Find the option that represents the shortest / no wait period
        for option in options:
            opt_l = option.lower()
            if any(k in opt_l for k in ("immediate", "0", "less than 15", "< 15", "within 15")):
                return option
        # Fall back to the first non-placeholder option
        for option in options:
            if option.lower() not in ("select an option", "select", "please select", ""):
                return option
    return None


async def _ask_llm(
    question: str,
    field_type: str,
    options: list[str] | None,
    company: str,
    job_title: str,
    profile_text: str,
    validation_error: str = "",
) -> FilledAnswer:
    options_str = (
        f"\nAvailable options (pick exactly one verbatim): {json.dumps(options)}" if options else ""
    )
    numeric_hint = (
        " If the question asks for years of experience, a duration (like notice period), or compensation (CTC/salary), "
        "and the field type is a number or text, provide ONLY the raw numeric value (e.g. '0', '2', '1500000'). "
        "Never include text like 'years', 'days', or parenthetical explanations."
    ) if _NUMERIC_HINT_PATTERN.search(question) else ""

    _numeric_error = bool(
        validation_error and re.search(
            r"decimal|number|numerical|integer|\d+\s*(or\s*)?larger|greater than", validation_error, re.I
        )
    )
    if validation_error:
        if _numeric_error:
            error_hint = (
                f"\nIMPORTANT — The previous answer was rejected with error: \"{validation_error}\". "
                "The field explicitly requires a NUMBER. "
                "Output ONLY a single number (digits and optional decimal point, nothing else). "
                "Example valid answers: 0  15  1500000"
            )
        else:
            error_hint = (
                f"\nIMPORTANT — The previous answer was rejected with error: \"{validation_error}\". "
                "Your new answer MUST satisfy this constraint."
            )
    else:
        error_hint = ""

    prompt = (
        "You fill job application forms for a candidate. "
        "Answer only the question asked. "
        "For dropdowns, radio buttons, or checkbox options, output exactly one listed option verbatim. "
        "For text answers, keep the answer extremely concise and literal. "
        "If a truthful answer requires a personal anecdote or unknown detail, output MANUAL_REVIEW."
        + numeric_hint
        + error_hint
        + f"\n\nCandidate profile:\n{profile_text}\n\n"
        f"Applying to: {company} - {job_title}\n\n"
        f'Question: "{question}"\n'
        f"Input Field Type: {field_type}{options_str}\n\nAnswer:"
    )

    max_tok = 20 if (_numeric_error or field_type == "number") else 200

    try:
        answer, tokens = await llm_service.chat_with_tokens(prompt, max_tokens=max_tok, temperature=0.1)
    except Exception as exc:
        log.warning("LLM call failed during form fill: %s", str(exc)[:120])
        return FilledAnswer("", "manual_review", True, question), 0

    if not answer or answer == "MANUAL_REVIEW":
        return FilledAnswer("", "manual_review", True, question), tokens

    if options and answer not in options:
        matched = _match_option(answer, options)
        if matched:
            answer = matched
        else:
            return FilledAnswer("", "manual_review", True, question, 0.0), tokens

    return FilledAnswer(answer, "llm", raw_question=question, confidence=0.85), tokens


async def answer_question_for_user(
    question_text: str,
    field_type: str,
    options: list[str] | None,
    company: str,
    job_title: str,
    candidate: dict,
    profile_text: str,
    validation_error: str = "",
    user_id: str = "",
) -> FilledAnswer:
    question = question_text.strip()
    log.debug("Answering question: %r", question[:80])

    if MANUAL_REVIEW_PATTERNS.search(question):
        return FilledAnswer("", "manual_review", True, question), 0

    standard_patterns = build_standard_patterns(candidate)
    for pattern, answer_fn in standard_patterns:
        if pattern.search(question):
            raw_value = answer_fn()
            if options:
                matched = _match_option(raw_value, options)
                if matched:
                    return FilledAnswer(matched, "pattern", raw_question=question), 0
            else:
                return FilledAnswer(raw_value, "pattern", raw_question=question), 0

    # Bypass cache when a validation error is present so the LLM sees the error context
    if not validation_error:
        cached = _cache_get(user_id, question)
        if cached is not None:
            return cached, 0

    result, tokens = await _ask_llm(question, field_type, options, company, job_title, profile_text, validation_error)

    if not result.is_manual_review and not validation_error:
        _cache_put(user_id, question, result)

    return result, tokens
