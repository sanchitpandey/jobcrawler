"""
form_filler.py  —  Groq edition with logging
──────────────────────────────────────────────
Free tier: 14,400 req/day, 500K tokens/day (console.groq.com)

Strategy:
  1. Pattern match against 24 common questions → instant, free, 0 API calls
  2. Groq API (Llama 3.3 70B) for anything unrecognised
  3. Flag as manual_review for behavioural / essay questions
"""

from __future__ import annotations
import re
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
load_dotenv()
from groq import Groq
from logger import get_logger

log = get_logger(__name__)

GROQ_MODEL = "llama-3.3-70b-versatile"
import yaml
from pathlib import Path

def _load_candidate() -> dict:
    p = Path("apply_profile.md")
    if not p.exists():
        raise FileNotFoundError("apply_profile.md not found — fill in your details first")
    # parse the YAML-like sections
    text = p.read_text(encoding="utf-8")
    # simplest approach: extract key: "value" pairs
    result = {}
    for line in text.splitlines():
        if ": " in line and not line.startswith("#"):
            k, _, v = line.partition(": ")
            result[k.strip()] = v.strip().strip('"')
    return result

CANDIDATE = _load_candidate()

STANDARD_PATTERNS: list[tuple[re.Pattern, callable]] = [
    (re.compile(r"\bemail\b",                            re.I), lambda: CANDIDATE["email"]),
    (re.compile(r"\bphone|mobile|contact\b",             re.I), lambda: CANDIDATE["phone"]),
    (re.compile(r"\blinkedin\b",                         re.I), lambda: CANDIDATE["linkedin"]),
    (re.compile(r"\bgithub|portfolio\b",                 re.I), lambda: CANDIDATE["github"]),
    (re.compile(r"current.*(ctc|salary|comp)|present.*(ctc|salary)", re.I),
                                                                lambda: CANDIDATE["current_ctc"]),
    (re.compile(r"expected.*(ctc|salary|comp)|desired.*(ctc|salary)", re.I),
                                                                lambda: CANDIDATE["expected_ctc"]),
    (re.compile(r"notice period|joining period",         re.I), lambda: CANDIDATE["notice_period"]),
    (re.compile(r"(when|available).*(start|join)|start date|availability", re.I),
                                                                lambda: CANDIDATE["start_date"]),
    (re.compile(r"cgpa|gpa|percentage|aggregate",        re.I), lambda: CANDIDATE["cgpa"]),
    (re.compile(r"college|university|institution",       re.I), lambda: CANDIDATE["college"]),
    (re.compile(r"graduation year|passing year|batch",   re.I), lambda: CANDIDATE["graduation_year"]),
    (re.compile(r"\bdegree|qualification\b",             re.I), lambda: CANDIDATE["degree"]),
    (re.compile(r"total.*(experience|exp)|years? of experience", re.I),
                                                                lambda: CANDIDATE["total_experience"]),
    (re.compile(r"python.*(years?|exp)",                 re.I), lambda: CANDIDATE["python_years"]),
    (re.compile(r"(pytorch|tensorflow).*(years?|exp)",   re.I), lambda: CANDIDATE["pytorch_years"]),
    (re.compile(r"(hugging\s?face|hf|transformers).*(years?|exp)", re.I),
                                                                lambda: CANDIDATE["huggingface_years"]),
    (re.compile(r"(llm|rag|nlp|nlu|bert|gpt).*(years?|exp)", re.I),
                                                                lambda: CANDIDATE["llm_years"]),
    (re.compile(r"(machine learning|ml).*(years?|exp)",  re.I), lambda: CANDIDATE["ml_years"]),
    (re.compile(r"work auth|authorized to work|eligible to work", re.I),
                                                                lambda: CANDIDATE["work_auth"]),
    (re.compile(r"(visa|sponsorship).*(require|need|sponsor)", re.I),
                                                                lambda: CANDIDATE["sponsorship"]),
    (re.compile(r"(willing|open).*(relocat)|can you relocat",  re.I),
                                                                lambda: CANDIDATE["relocate"]),
    (re.compile(r"\bgender\b",                           re.I), lambda: CANDIDATE["gender"]),
    (re.compile(r"veteran",                              re.I), lambda: CANDIDATE["veteran"]),
    (re.compile(r"disability|disabled",                  re.I), lambda: CANDIDATE["disability"]),
]

MANUAL_REVIEW_PATTERNS = re.compile(
    r"describe (a time|an experience|when|how)|tell us about|cover letter|"
    r"why do you want|what motivates|greatest (strength|weakness)|"
    r"where do you see yourself|what are your long.term",
    re.I,
)

_client: Optional[Groq] = None
_profile_text: Optional[str] = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GROQ_API_KEY not set. Get a free key at console.groq.com\n"
                "Windows: $env:GROQ_API_KEY = 'gsk_...'\n"
                "Linux/Mac: export GROQ_API_KEY=gsk_..."
            )
        _client = Groq(api_key=api_key)
        log.debug("Groq client ready (form_filler)")
    return _client


def _get_profile() -> str:
    global _profile_text
    if _profile_text is None:
        parts = []
        for fname in ["APPLY_PROFILE.md", "GEMINI.md"]:
            p = Path(fname)
            if p.exists():
                parts.append(p.read_text(encoding="utf-8"))
                log.debug("Loaded profile from %s", fname)
            else:
                log.debug("Profile file not found (optional): %s", fname)
        _profile_text = "\n\n".join(parts)
    return _profile_text


@dataclass
class FilledAnswer:
    value:            str
    source:           str    # "pattern" | "groq" | "manual_review"
    is_manual_review: bool   = False
    raw_question:     str    = ""
    confidence:       float  = 1.0


def _match_option(value: str, options: list[str]) -> str | None:
    val_lower = value.lower()
    for opt in options:
        if opt.lower() == val_lower:
            return opt
    for opt in options:
        if val_lower in opt.lower() or opt.lower() in val_lower:
            return opt
    if val_lower in ("yes", "true", "1"):
        for opt in options:
            if opt.lower() in ("yes", "true"):
                return opt
    if val_lower in ("no", "false", "0"):
        for opt in options:
            if opt.lower() in ("no", "false"):
                return opt
    return None


def answer_question(
    question_text: str,
    field_type:    str = "text",
    options:       list[str] | None = None,
    company:       str = "",
    job_title:     str = "",
) -> FilledAnswer:
    q = question_text.strip()
    log.debug("Answering question: %r (type=%s, options=%s)", q[:80], field_type,
              options[:4] if options else None)

    # 1. Behavioural / essay → always manual
    if MANUAL_REVIEW_PATTERNS.search(q):
        log.info("Question flagged as MANUAL_REVIEW (behavioural): %r", q[:80])
        return FilledAnswer("", "manual_review", True, q)

    # 2. Pattern match — zero API calls
    for pattern, answer_fn in STANDARD_PATTERNS:
        if pattern.search(q):
            raw_val = answer_fn()
            log.debug("Pattern match for %r → %r", q[:60], raw_val)
            if options:
                matched = _match_option(raw_val, options)
                if matched:
                    log.debug("Matched dropdown option: %r", matched)
                    return FilledAnswer(matched, "pattern", raw_question=q)
                log.debug("Pattern value %r not in options — falling through to Groq", raw_val)
            else:
                return FilledAnswer(raw_val, "pattern", raw_question=q)

    # 3. Groq API for anything else
    log.info("No pattern match for %r — sending to Groq", q[:80])
    return _ask_groq(q, field_type, options, company, job_title)


def _ask_groq(
    question:   str,
    field_type: str,
    options:    list[str] | None,
    company:    str,
    job_title:  str,
) -> FilledAnswer:
    profile     = _get_profile()
    options_str = (
        f"\nAvailable options (pick EXACTLY one, verbatim): {json.dumps(options)}"
        if options else ""
    )

    system = (
        "You fill job application forms for a candidate. "
        "Answer ONLY the question asked — no preamble, no explanation. "
        "Dropdowns/radio: output exactly one listed option, character-perfect. "
        "Text: max 2 sentences unless clearly more is needed. "
        "If you must fabricate a personal anecdote, output: MANUAL_REVIEW"
    )
    user = (
        f"Candidate profile:\n{profile}\n\n"
        f"Applying to: {company} — {job_title}\n\n"
        f'Question: "{question}"\n'
        f"Field type: {field_type}{options_str}\n\nAnswer:"
    )

    def _call():
        return _get_client().chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            max_tokens=200,
            temperature=0.1,
        )

    try:
        resp   = _call()
        answer = resp.choices[0].message.content.strip()
        log.debug("Groq answer for %r: %r", question[:60], answer[:100])
    except Exception as e:
        if "429" in str(e) or "rate_limit" in str(e).lower():
            log.warning("Groq rate limit hit on form question — waiting 62 s...")
            time.sleep(62)
            try:
                resp   = _call()
                answer = resp.choices[0].message.content.strip()
                log.info("Rate limit retry succeeded for question: %r", question[:60])
            except Exception as e2:
                log.error("Groq retry failed: %s — flagging as manual_review", e2)
                return FilledAnswer("", "manual_review", True, question)
        else:
            log.error("Groq API error for question %r: %s", question[:60], e)
            return FilledAnswer("", "manual_review", True, question)

    if not answer or answer == "MANUAL_REVIEW":
        log.info("Groq returned MANUAL_REVIEW for: %r", question[:80])
        return FilledAnswer("", "manual_review", True, question)

    if options and answer not in options:
        matched = _match_option(answer, options)
        if matched:
            log.debug("Groq answer %r fuzzy-matched to option %r", answer, matched)
            answer = matched
        else:
            log.warning("Groq answer %r doesn't match any option %s — flagging manual",
                        answer, options)
            return FilledAnswer("", "manual_review", True, question, 0.0)

    log.info("Groq answered %r → %r", question[:60], answer[:60])
    return FilledAnswer(answer, "groq", raw_question=question, confidence=0.85)


def answer_form(
    fields:    list[dict],
    company:   str = "",
    job_title: str = "",
) -> tuple[list[FilledAnswer], list[FilledAnswer]]:
    log.info("Filling %d form fields for %s — %s", len(fields), company, job_title)
    answered, manual = [], []
    for field in fields:
        result = answer_question(
            question_text=field.get("label", ""),
            field_type=field.get("type", "text"),
            options=field.get("options"),
            company=company,
            job_title=job_title,
        )
        (manual if result.is_manual_review else answered).append(result)
    log.info("Form fill complete — %d answered, %d manual review", len(answered), len(manual))
    return answered, manual