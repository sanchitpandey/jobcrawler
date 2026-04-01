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

# Matches labels that expect a pure integer answer (years / months of experience).
_YEARS_EXP_LABEL_PATTERN = re.compile(r"\byrs?\b.*exp|\byears?\b.*exp|years? of exp", re.I)

MANUAL_REVIEW_PATTERNS = re.compile(
    r"describe (a time|an experience|when|how)|tell us about|cover letter|"
    r"why do you want|what motivates|greatest (strength|weakness)|"
    r"where do you see yourself|what are your long.term",
    re.I,
)

# TODO: Migrate to Redis cache keyed by (user_id, normalized_question)
_answer_cache: dict[tuple[str, str], dict] = {}

CACHE_TTL_DAYS = 30
_CACHE_MAX_SIZE = 10_000   # evict oldest 10% when exceeded


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
    entry = _answer_cache.get(key)
    if entry is None:
        return None
    if datetime.now() - datetime.fromisoformat(entry["cached_at"]) > timedelta(days=CACHE_TTL_DAYS):
        del _answer_cache[key]
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
    if len(_answer_cache) >= _CACHE_MAX_SIZE:
        # Evict the oldest 10% (insertion-order guaranteed in Python 3.7+)
        evict_count = _CACHE_MAX_SIZE // 10
        for old_key in list(_answer_cache.keys())[:evict_count]:
            del _answer_cache[old_key]
    key = _cache_key(user_id, question)
    _answer_cache[key] = {
        "value": answer.value,
        "source": answer.source,
        "is_manual_review": answer.is_manual_review,
        "raw_question": answer.raw_question,
        "confidence": answer.confidence,
        "cached_at": datetime.now().isoformat(),
    }


def _ctc_fallback(raw: str, candidate: dict) -> str:
    """Return raw if it's a parseable positive number; else fall back to target_comp_lpa × 100000."""
    try:
        val = float(re.sub(r"[^\d.]", "", raw))
        if val > 0:
            return raw
    except (ValueError, TypeError):
        pass
    target = candidate.get("target_comp_lpa", 0)
    return str(int(target) * 100_000)


def build_standard_patterns(candidate: dict) -> list[tuple[re.Pattern[str], callable]]:
    """Build the STANDARD_PATTERNS list bound to the given candidate dict."""
    return [
        (re.compile(r"\bemail\b", re.I), lambda: candidate["email"]),
        (re.compile(r"\bphone|mobile|contact\b", re.I), lambda: candidate["phone"]),
        (re.compile(r"\blinkedin\b", re.I), lambda: candidate["linkedin"]),
        (re.compile(r"\bgithub|portfolio\b", re.I), lambda: candidate["github"]),
        (re.compile(r"current.*(ctc|salary|comp)|present.*(ctc|salary)", re.I), lambda: candidate["current_ctc"]),
        (re.compile(r"expected.*(ctc|salary|comp)|desired.*(ctc|salary)", re.I), lambda: _ctc_fallback(candidate["expected_ctc"], candidate)),
        (re.compile(r"notice period|joining period", re.I), lambda: candidate["notice_period"]),
        (re.compile(r"(when|available).*(start|join)|start date|availability", re.I), lambda: candidate["start_date"]),
        (re.compile(r"cgpa|gpa|percentage|aggregate", re.I), lambda: candidate["cgpa"]),
        (re.compile(r"\b(college|university)\b|educational institution|alma mater", re.I), lambda: candidate["college"]),
        (re.compile(r"graduation year|passing year|batch", re.I), lambda: candidate.get("graduation_year", candidate.get("graduation_month_year", ""))),
        (re.compile(r"degree|qualification", re.I), lambda: candidate["degree"]),
        # Exact-match guard prevents "Python experience" / "GCP experience" from hitting this
        (re.compile(r"^(?:how many )?(?:years of )?(?:total )?(?:work )?experience(?: do you have)?\??$", re.I), lambda: candidate["total_experience"]),
        (re.compile(r"python.*(?:years?|exp)", re.I), lambda: candidate["python_years"]),
        (re.compile(r"(?:pytorch|tensorflow).*(?:years?|exp)", re.I), lambda: candidate["pytorch_years"]),
        (re.compile(r"(?:hugging\s?face|hf|transformers).*(?:years?|exp)", re.I), lambda: candidate["huggingface_years"]),
        (re.compile(r"(?:llm|rag|nlp|nlu|bert|gpt).*(?:years?|exp)", re.I), lambda: candidate.get("llm_nlp_rag_years", candidate.get("llm_years", ""))),
        (re.compile(r"(?:machine learning|ml).*(?:years?|exp)", re.I), lambda: candidate["ml_years"]),
        (re.compile(r"work auth|authorized to work|eligible to work", re.I), lambda: candidate["work_authorization"]),
        (re.compile(r"(?:visa|sponsorship).*(?:require|need|sponsor)", re.I), lambda: candidate["sponsorship_required"]),
        (re.compile(r"(?:willing|open).*(?:relocat)|can you relocat", re.I), lambda: candidate["willing_to_relocate"]),
        (re.compile(r"\bgender\b", re.I), lambda: candidate["gender"]),
        (re.compile(r"veteran", re.I), lambda: candidate["veteran_status"]),
        (re.compile(r"disability|disabled", re.I), lambda: candidate["disability"]),
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
        " For fields asking years of experience (e.g. 'years of experience', 'yrs of exp'),"
        " answer with ONLY a number (e.g., '1' or '2')."
        " Never include text like 'years' or parenthetical explanations."
    ) if _YEARS_EXP_LABEL_PATTERN.search(question) else ""

    _numeric_error = bool(
        validation_error and re.search(
            r"decimal|number|numerical|\d+\s*(or\s*)?larger|greater than", validation_error, re.I
        )
    )
    if validation_error:
        if _numeric_error:
            error_hint = (
                f"\nIMPORTANT — The previous answer was rejected: \"{validation_error}\". "
                "The field requires a NUMBER. "
                "Output ONLY a single number (digits and optional decimal point, nothing else). "
                "Example valid answers: 0.5  1  2  3.5"
            )
        else:
            error_hint = (
                f"\nIMPORTANT — The previous answer was rejected: \"{validation_error}\". "
                "Your new answer MUST satisfy this constraint."
            )
    else:
        error_hint = ""

    prompt = (
        "You fill job application forms for a candidate. "
        "Answer only the question asked. "
        "For dropdowns and radio buttons, output exactly one listed option. "
        "For text answers, keep the answer concise. "
        "If a truthful answer requires a personal anecdote or unknown detail, output MANUAL_REVIEW."
        + numeric_hint
        + error_hint
        + f"\n\nCandidate profile:\n{profile_text}\n\n"
        f"Applying to: {company} - {job_title}\n\n"
        f'Question: "{question}"\n'
        f"Field type: {field_type}{options_str}\n\nAnswer:"
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
