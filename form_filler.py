"""Profile-driven helpers for auto-filling job application forms."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from groq import Groq

from core.profile import load_key_value_profile, load_profile_text
from logger import get_logger

load_dotenv()
log = get_logger(__name__)

GROQ_MODEL = "llama-3.3-70b-versatile"
PROFILE_FILE = Path("APPLY_PROFILE.md")
PROFILE_CONTEXT_FILES = ["APPLY_PROFILE.md"]


def _load_candidate() -> dict[str, str]:
    if not PROFILE_FILE.exists():
        raise FileNotFoundError("APPLY_PROFILE.md not found. Fill in your candidate details before running apply automation.")
    return load_key_value_profile(PROFILE_FILE)


CANDIDATE = _load_candidate()

STANDARD_PATTERNS: list[tuple[re.Pattern[str], callable]] = [
    (re.compile(r"\bemail\b", re.I), lambda: CANDIDATE["email"]),
    (re.compile(r"\bphone|mobile|contact\b", re.I), lambda: CANDIDATE["phone"]),
    (re.compile(r"\blinkedin\b", re.I), lambda: CANDIDATE["linkedin"]),
    (re.compile(r"\bgithub|portfolio\b", re.I), lambda: CANDIDATE["github"]),
    (re.compile(r"current.*(ctc|salary|comp)|present.*(ctc|salary)", re.I), lambda: CANDIDATE["current_ctc"]),
    (re.compile(r"expected.*(ctc|salary|comp)|desired.*(ctc|salary)", re.I), lambda: CANDIDATE["expected_ctc"]),
    (re.compile(r"notice period|joining period", re.I), lambda: CANDIDATE["notice_period"]),
    (re.compile(r"(when|available).*(start|join)|start date|availability", re.I), lambda: CANDIDATE["start_date"]),
    (re.compile(r"cgpa|gpa|percentage|aggregate", re.I), lambda: CANDIDATE["cgpa"]),
    (re.compile(r"college|university|institution", re.I), lambda: CANDIDATE["college"]),
    (re.compile(r"graduation year|passing year|batch", re.I), lambda: CANDIDATE.get("graduation_year", CANDIDATE.get("graduation_month_year", ""))),
    (re.compile(r"\bdegree|qualification\b", re.I), lambda: CANDIDATE["degree"]),
    (re.compile(r"total.*(experience|exp)|years? of experience", re.I), lambda: CANDIDATE["total_experience"]),
    (re.compile(r"python.*(years?|exp)", re.I), lambda: CANDIDATE["python_years"]),
    (re.compile(r"(pytorch|tensorflow).*(years?|exp)", re.I), lambda: CANDIDATE["pytorch_years"]),
    (re.compile(r"(hugging\s?face|hf|transformers).*(years?|exp)", re.I), lambda: CANDIDATE["huggingface_years"]),
    (re.compile(r"(llm|rag|nlp|nlu|bert|gpt).*(years?|exp)", re.I), lambda: CANDIDATE.get("llm_nlp_rag_years", CANDIDATE.get("llm_years", ""))),
    (re.compile(r"(machine learning|ml).*(years?|exp)", re.I), lambda: CANDIDATE["ml_years"]),
    (re.compile(r"work auth|authorized to work|eligible to work", re.I), lambda: CANDIDATE["work_authorization"]),
    (re.compile(r"(visa|sponsorship).*(require|need|sponsor)", re.I), lambda: CANDIDATE["sponsorship_required"]),
    (re.compile(r"(willing|open).*(relocat)|can you relocat", re.I), lambda: CANDIDATE["willing_to_relocate"]),
    (re.compile(r"\bgender\b", re.I), lambda: CANDIDATE["gender"]),
    (re.compile(r"veteran", re.I), lambda: CANDIDATE["veteran_status"]),
    (re.compile(r"disability|disabled", re.I), lambda: CANDIDATE["disability"]),
]

MANUAL_REVIEW_PATTERNS = re.compile(
    r"describe (a time|an experience|when|how)|tell us about|cover letter|"
    r"why do you want|what motivates|greatest (strength|weakness)|"
    r"where do you see yourself|what are your long.term",
    re.I,
)

_client: Optional[Groq] = None
_profile_text: Optional[str] = None


@dataclass
class FilledAnswer:
    value: str
    source: str
    is_manual_review: bool = False
    raw_question: str = ""
    confidence: float = 1.0


def _get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GROQ_API_KEY not set. Get a free key at console.groq.com\n"
                "Windows: $env:GROQ_API_KEY = 'gsk_...'\n"
                "Linux/Mac: export GROQ_API_KEY=gsk_...'"
            )
        _client = Groq(api_key=api_key)
        log.debug("Groq client ready")
    return _client


def _get_profile() -> str:
    global _profile_text
    if _profile_text is None:
        _profile_text = load_profile_text(*PROFILE_CONTEXT_FILES)
    return _profile_text


def _match_option(value: str, options: list[str]) -> str | None:
    candidate = value.lower()
    for option in options:
        if option.lower() == candidate:
            return option
    for option in options:
        if candidate in option.lower() or option.lower() in candidate:
            return option
    if candidate in {"yes", "true", "1"}:
        for option in options:
            if option.lower() in {"yes", "true"}:
                return option
    if candidate in {"no", "false", "0"}:
        for option in options:
            if option.lower() in {"no", "false"}:
                return option
    return None


def answer_question(
    question_text: str,
    field_type: str = "text",
    options: list[str] | None = None,
    company: str = "",
    job_title: str = "",
) -> FilledAnswer:
    question = question_text.strip()
    log.debug("Answering question: %r", question[:80])

    if MANUAL_REVIEW_PATTERNS.search(question):
        return FilledAnswer("", "manual_review", True, question)

    for pattern, answer_fn in STANDARD_PATTERNS:
        if pattern.search(question):
            raw_value = answer_fn()
            if options:
                matched = _match_option(raw_value, options)
                if matched:
                    return FilledAnswer(matched, "pattern", raw_question=question)
            else:
                return FilledAnswer(raw_value, "pattern", raw_question=question)

    return _ask_groq(question, field_type, options, company, job_title)


def _ask_groq(
    question: str,
    field_type: str,
    options: list[str] | None,
    company: str,
    job_title: str,
) -> FilledAnswer:
    profile = _get_profile()
    options_str = (
        f"\nAvailable options (pick exactly one verbatim): {json.dumps(options)}" if options else ""
    )
    system = (
        "You fill job application forms for a candidate. "
        "Answer only the question asked. "
        "For dropdowns and radio buttons, output exactly one listed option. "
        "For text answers, keep the answer concise. "
        "If a truthful answer requires a personal anecdote or unknown detail, output MANUAL_REVIEW."
    )
    user = (
        f"Candidate profile:\n{profile}\n\n"
        f"Applying to: {company} - {job_title}\n\n"
        f'Question: "{question}"\n'
        f"Field type: {field_type}{options_str}\n\nAnswer:"
    )

    def _call():
        return _get_client().chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=200,
            temperature=0.1,
        )

    try:
        response = _call()
        answer = response.choices[0].message.content.strip()
    except Exception as exc:
        if "429" in str(exc) or "rate_limit" in str(exc).lower():
            log.warning("Groq rate limit hit during form fill. Waiting 62 seconds.")
            time.sleep(62)
            try:
                response = _call()
                answer = response.choices[0].message.content.strip()
            except Exception:
                return FilledAnswer("", "manual_review", True, question)
        else:
            return FilledAnswer("", "manual_review", True, question)

    if not answer or answer == "MANUAL_REVIEW":
        return FilledAnswer("", "manual_review", True, question)

    if options and answer not in options:
        matched = _match_option(answer, options)
        if matched:
            answer = matched
        else:
            return FilledAnswer("", "manual_review", True, question, 0.0)

    return FilledAnswer(answer, "groq", raw_question=question, confidence=0.85)


def answer_form(fields: list[dict], company: str = "", job_title: str = "") -> tuple[list[FilledAnswer], list[FilledAnswer]]:
    answered: list[FilledAnswer] = []
    manual: list[FilledAnswer] = []
    for field in fields:
        result = answer_question(
            question_text=field.get("label", ""),
            field_type=field.get("type", "text"),
            options=field.get("options"),
            company=company,
            job_title=job_title,
        )
        if result.is_manual_review:
            manual.append(result)
        else:
            answered.append(result)
    return answered, manual
