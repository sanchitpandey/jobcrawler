"""Stateless job scoring service — ported from legacy/score.py."""

from __future__ import annotations

import json
import logging
import re
from string import Template

from api.services.llm import chat

log = logging.getLogger("crawler.scorer")

# ── Prompt ─────────────────────────────────────────────────────────────────────
# Preserved exactly from legacy/score.py (PROMPT_TEMPLATE).

SCORING_RULES = Template("""You are a strict recruiter scoring job listings for a candidate.

Use the candidate profile below as the only source of truth for background, strengths, preferences, constraints, seniority, compensation expectations, and target roles.

MANDATORY PENALTIES (apply these first):
1. Seniority penalty: if the title implies Staff, Principal, Director, VP, or similar seniority, score must be below 35.
2. Prompt engineering penalty: if the role is mainly prompt engineering, score must be below 50.
3. Staffing/body shop penalty: if the company is a staffing agency or recruiter, score must be below 30.
4. Domain company penalty: if the company is not primarily a technology company, score must be below 45 unless the candidate profile explicitly targets that domain.
5. Internship or unpaid penalty: if the role is an internship or unpaid, score must be below 35 unless the candidate profile explicitly says internships are acceptable.
6. Short contract penalty: if the contract ends before the candidate's stated availability or job search preference window, score must be below 45.
7. Infra/devops penalty: if the role is mainly infra/devops instead of ML, score must be below 40 unless the profile explicitly targets platform roles.
8. Experience gap penalty: if minimum experience is materially above the candidate's full-time experience, cap aggressively.
$mandatory_boosts
SCORING RUBRIC:
85-100: excellent match to candidate goals, stack, seniority, and constraints
65-84: strong match with manageable gaps
40-64: partial fit, adjacent role, or notable mismatch
0-39: poor fit based on seniority, domain, role type, or hard constraints

VERDICT MAPPING:
- strong_apply = fit_score >= 80
- apply = fit_score 60-79
- borderline = fit_score 40-59
- skip = fit_score < 40

OUTPUT: Return only a valid JSON array.
[
  {
    "id": "<copy id field exactly>",
    "fit_score": 0,
    "comp_estimate": "candidate-aligned compensation estimate",
    "verdict": "strong_apply|apply|borderline|skip",
    "gaps": ["specific missing requirement", "up to 3 total"],
    "why": "one sentence summary"
  }
]
""")

# ── Policy constants ───────────────────────────────────────────────────────────

_DEFAULT_JUNIOR_SIGNALS = [
    "foundational hire",
    "how you think",
    "curiosity",
    "early-stage",
    "welcomes junior candidates",
]
_POINT_DEFAULTS = {
    "niche": 15,
    "trending": 15,
    "junior": 10,
}
_POINT_MAX = 30
_NICHE_HINT_KEYWORDS = [
    ("RAG", "rag"),
    ("FAISS", "faiss"),
    ("RLHF", "rlhf"),
    ("PPO", "ppo"),
    ("HuggingFace", "huggingface"),
    ("BM25", "bm25"),
    ("retrieval", "retrieval"),
    ("reranking", "reranking"),
    ("reranker", "reranker"),
    ("transformers", "transformers"),
    ("PyTorch", "pytorch"),
    ("LLMs", "llm"),
    ("NLP", "nlp"),
]
_PROFILE_DERIVATION_FIELDS = (
    "must_have_preferences",
    "preferred_roles",
    "candidate_summary",
    "experience_highlights",
)
_TECHNICAL_EXPERIENCE_KEYS = (
    "python_years",
    "ml_years",
    "llm_nlp_rag_years",
    "pytorch_years",
    "huggingface_years",
)


# ── Helper functions (preserved from legacy) ───────────────────────────────────

def _safe_text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _precompute_flags(job: dict) -> dict:
    """Extract structured signals via regex without relying on fragile raw types."""
    desc = _safe_text(job.get("description", "")).lower()
    location = _safe_text(job.get("location", "")).lower()

    exp_matches = re.findall(
        r'(\d+)\s*[\+\-to]*\s*(?:\d+)?\s*years?\s*(?:of\s*)?(?:experience|exp)',
        desc,
    )
    min_exp = min((int(match) for match in exp_matches), default=0)

    is_internship = any(token in desc for token in [
        'internship', 'intern ', 'stipend', 'unpaid', 'first month is unpaid', 'training period'
    ])
    is_contract = any(token in desc for token in [
        'contract-based', 'contract role', 'initial contract', 'consultant', 'freelance'
    ])
    short_contract = bool(re.search(r'(?:through|until|till|ending)\s+(?:jun|july|aug)\s*202[56]', desc))

    infra_primary = sum(desc.count(token) for token in [
        'kubernetes', 'helm', 'terraform', 'ci/cd pipeline', 'devops', 'platform engineering', 'sre '
    ])
    ml_primary = sum(desc.count(token) for token in [
        'llm', 'transformer', 'pytorch', 'fine-tun', 'rag', 'nlp', 'machine learning model', 'training'
    ])
    is_infra_role = infra_primary > ml_primary and infra_primary >= 3

    is_bangalore_office_only = (
        'bengaluru' in location
        and not bool(job.get('is_remote'))
        and ('in-office' in desc or 'work from office' in desc)
    )

    return {
        'min_exp_years': min_exp,
        'is_internship': is_internship,
        'is_short_contract': is_contract and short_contract,
        'is_infra_role_not_ml': is_infra_role,
        'is_bangalore_office_only': is_bangalore_office_only,
    }


def _extract_jd_fields(desc: str) -> str:
    full = desc[:4000]
    lines = full.splitlines()
    requirements_lines: list[str] = []
    in_requirements = False

    for line in lines:
        lower = line.lower()
        if any(token in lower for token in ["required", "qualification", "must have", "minimum", "you bring", "what we need"]):
            in_requirements = True
        if any(token in lower for token in ["what we offer", "benefit", "why join", "about us", "perks"]):
            in_requirements = False
        if in_requirements or any(token in lower for token in [
            "years of exp",
            "yrs exp",
            "year experience",
            "internship",
            "contract",
            "full-time",
            "stipend",
            "unpaid",
            "fresher",
            "entry level",
        ]):
            requirements_lines.append(line)

    overview = desc[:400]
    requirements = "\n".join(requirements_lines[:40])
    return f"{overview}\n---REQUIREMENTS---\n{requirements}"[:2500]


def _sanitize_json(text: str) -> str:
    """Aggressively clean LLM output to make it valid JSON."""
    # Strip <think> blocks
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Strip markdown fences anywhere in the string
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    # Remove single-line comments
    text = re.sub(r"//[^\n]*", "", text)
    # Remove trailing commas before } or ]
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return text.strip()


def _parse_response(raw: str, expected_ids: set[str]) -> list[dict]:
    text = _sanitize_json(raw)

    # Try parsing as a bare object wrapping an array
    if text.startswith("{"):
        try:
            obj = json.loads(text)
            for value in obj.values():
                if isinstance(value, list):
                    return _validate(value, expected_ids)
        except json.JSONDecodeError:
            pass

    start = text.find("[")
    end = text.rfind("]")
    if start == -1:
        raise ValueError(f"No JSON array in response: {text[:150]!r}")

    array_text = text[start:end + 1] if end > start else text[start:]

    # Attempt 1: parse as-is
    try:
        return _validate(json.loads(array_text), expected_ids)
    except json.JSONDecodeError:
        pass

    # Attempt 2: try appending a closing bracket (truncated response)
    try:
        return _validate(json.loads(array_text + "]"), expected_ids)
    except json.JSONDecodeError:
        pass

    # Attempt 3: per-object extraction — salvage whatever parses
    objects = re.findall(r"\{[^{}]+\}", array_text, re.DOTALL)
    salvaged: list[dict] = []
    for obj_str in objects:
        try:
            salvaged.append(json.loads(obj_str))
        except json.JSONDecodeError:
            pass
    if salvaged:
        log.warning("Full array parse failed — salvaged %d/%d objects", len(salvaged), len(objects))
        return _validate(salvaged, expected_ids)

    raise ValueError(f"Could not parse JSON from response: {text[:200]!r}")


def _validate(items: list, expected_ids: set[str]) -> list[dict]:
    validated: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("id", "")) not in expected_ids:
            continue
        try:
            item["fit_score"] = int(item["fit_score"])
        except (KeyError, TypeError, ValueError):
            continue
        validated.append(item)
    return validated


# ── Scoring policy helpers ─────────────────────────────────────────────────────

def _clamp_points(raw_value: str | None, default: int) -> int:
    try:
        value = int(str(raw_value).strip())
    except (TypeError, ValueError, AttributeError):
        value = default
    return max(0, min(_POINT_MAX, value))


def _split_keywords(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    parts = re.split(r"[\n,;|]+", raw_value)
    seen: set[str] = set()
    cleaned: list[str] = []
    for part in parts:
        item = re.sub(r"^\s*[-*]\s*", "", part).strip().strip('"')
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(item)
    return cleaned


def _profile_blob(profile_kv: dict[str, str], fields: tuple[str, ...]) -> str:
    return "\n".join(profile_kv.get(field, "") for field in fields if profile_kv.get(field, "")).lower()


def _derive_niche_keywords(profile_kv: dict[str, str]) -> list[str]:
    derived: list[str] = []
    blob = _profile_blob(profile_kv, _PROFILE_DERIVATION_FIELDS)
    for rendered, hint in _NICHE_HINT_KEYWORDS:
        if hint in blob:
            derived.append(rendered)

    for key in _TECHNICAL_EXPERIENCE_KEYS:
        raw = profile_kv.get(key, "")
        if not raw:
            continue
        try:
            years = float(re.sub(r"[^\d.]", "", str(raw)))
        except ValueError:
            years = 0.0
        if years <= 0:
            continue
        if key == "huggingface_years":
            derived.append("HuggingFace")
        elif key == "llm_nlp_rag_years":
            derived.extend(["LLMs", "NLP", "RAG"])
        elif key == "pytorch_years":
            derived.append("PyTorch")
        elif key == "ml_years":
            derived.append("Machine Learning")

    deduped: list[str] = []
    seen: set[str] = set()
    for item in derived:
        norm = item.lower()
        if norm in seen:
            continue
        seen.add(norm)
        deduped.append(item)
    return deduped


def _derive_trending_keywords(profile_kv: dict[str, str]) -> list[str]:
    blob = _profile_blob(profile_kv, _PROFILE_DERIVATION_FIELDS)
    choices = []
    keyword_map = {
        "AI agents": ("ai agents", "agent"),
        "agentic": ("agentic",),
        "LangChain": ("langchain",),
    }
    for rendered, hints in keyword_map.items():
        if any(hint in blob for hint in hints):
            choices.append(rendered)
    return choices


def _is_junior_profile(profile_kv: dict[str, str], profile_text: str) -> bool:
    combined = " ".join(
        filter(
            None,
            [
                profile_kv.get("total_experience", ""),
                profile_kv.get("graduation_year", ""),
                profile_kv.get("candidate_summary", ""),
                profile_kv.get("must_have_preferences", ""),
                profile_text,
            ],
        )
    ).lower()
    junior_markers = [
        "fresher",
        "junior",
        "entry-level",
        "entry level",
        "graduating",
        "graduation",
        "no full-time",
        "internship experience",
    ]
    return any(marker in combined for marker in junior_markers)


def _load_scoring_policy(profile_kv: dict[str, str], profile_text: str) -> dict[str, object]:
    explicit_niche = _split_keywords(profile_kv.get("scoring_boost_niche_keywords"))
    explicit_trending = _split_keywords(profile_kv.get("scoring_boost_trending_keywords"))
    explicit_junior = _split_keywords(profile_kv.get("scoring_boost_junior_signals"))

    junior_profile = _is_junior_profile(profile_kv, profile_text)

    niche_keywords = explicit_niche or _derive_niche_keywords(profile_kv)
    trending_keywords = explicit_trending or _derive_trending_keywords(profile_kv)
    junior_signals = explicit_junior or (_DEFAULT_JUNIOR_SIGNALS if junior_profile else [])

    return {
        "niche_keywords": niche_keywords,
        "trending_keywords": trending_keywords,
        "junior_signals": junior_signals,
        "niche_points": _clamp_points(profile_kv.get("scoring_boost_niche_points"), _POINT_DEFAULTS["niche"]),
        "trending_points": _clamp_points(profile_kv.get("scoring_boost_trending_points"), _POINT_DEFAULTS["trending"]),
        "junior_points": _clamp_points(profile_kv.get("scoring_boost_junior_points"), _POINT_DEFAULTS["junior"]),
        "enable_junior_boosts": bool(junior_signals),
    }


def _render_mandatory_boosts(policy: dict[str, object]) -> str:
    lines: list[str] = []
    if policy["niche_keywords"]:
        keywords = ", ".join(policy["niche_keywords"])  # type: ignore[arg-type]
        lines.append(
            f"1. Niche Skill Match: +{policy['niche_points']} points if the JD explicitly mentions or strongly aligns with profile-differentiating skills such as {keywords}."
        )
    if policy["trending_keywords"]:
        keywords = ", ".join(policy["trending_keywords"])  # type: ignore[arg-type]
        lines.append(
            f"{len(lines) + 1}. Agentic/Trending Match: +{policy['trending_points']} points if the JD mentions or strongly aligns with profile-relevant trending themes such as {keywords}."
        )
    if policy["junior_signals"]:
        signals = ", ".join(f'"{signal}"' for signal in policy["junior_signals"])  # type: ignore[union-attr]
        lines.append(
            f"{len(lines) + 1}. Junior-Friendly Language: +{policy['junior_points']} points if the JD includes signals such as {signals}."
        )
    if not lines:
        return ""
    return "MANDATORY BOOSTS (apply these to raise the score after penalties):\n" + "\n".join(lines) + "\n\n"


def _build_prompt(profile_text: str, policy: dict[str, object], job: dict) -> str:
    payload = {
        "id": str(job.get("id", "")),
        "company": str(job.get("company", "")),
        "title": str(job.get("title", "")),
        "location": str(job.get("location", "")),
        "flags": _precompute_flags(job),
        "description": _extract_jd_fields(str(job.get("description", ""))),
    }
    jobs_json = json.dumps([payload], indent=1)
    scoring_rules = SCORING_RULES.substitute(
        mandatory_boosts=_render_mandatory_boosts(policy),
    ).strip()
    return f"{scoring_rules}\n\nCANDIDATE PROFILE:\n{profile_text}\n\nJobs to score:\n{jobs_json}\n"


# ── Public API ─────────────────────────────────────────────────────────────────

async def score_job(
    job_dict: dict,
    profile_text: str,
    profile_kv: dict | None = None,
) -> dict:
    """Score a single job against a candidate profile.

    Args:
        job_dict: Job fields (id, title, company, location, description, ...).
        profile_text: Full profile markdown text (from Profile.to_text()).
        profile_kv: Key-value profile dict (from Profile.to_dict()). Used to
                    derive the scoring policy. Falls back to empty dict if omitted.

    Returns:
        A dict with keys: id, fit_score, comp_estimate, verdict, gaps, why.
    """
    kv = profile_kv or {}
    policy = _load_scoring_policy(kv, profile_text)
    prompt = _build_prompt(profile_text, policy, job_dict)

    job_id = str(job_dict.get("id", ""))
    raw = await chat(prompt, max_tokens=8192)
    results = _parse_response(raw, {job_id})

    if not results:
        raise ValueError(f"LLM returned no valid score for job id={job_id!r}. Raw: {raw[:200]!r}")

    return results[0]
