"""Score filtered jobs with the configured LLM provider."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import pandas as pd

from config import BATCH_SIZE, FILTERED_CSV, SCORED_CSV
from core.profile import load_profile_text
from logger import get_logger
from providers import chat, get_session
from utils import _precompute_flags

log = get_logger(__name__)
_BATCH_SIZE = min(BATCH_SIZE, 3)
PROFILE_FILE = Path("APPLY_PROFILE.md")

SCORING_RULES = """You are a strict recruiter scoring job listings for a candidate.

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
  {{
    "id": "<copy id field exactly>",
    "fit_score": 0,
    "comp_estimate": "candidate-aligned compensation estimate",
    "verdict": "strong_apply|apply|borderline|skip",
    "gaps": ["specific missing requirement", "up to 3 total"],
    "why": "one sentence summary"
  }}
]
"""


def _load_candidate_profile() -> str:
    if not PROFILE_FILE.exists():
        raise FileNotFoundError("APPLY_PROFILE.md not found. Fill in your profile before scoring jobs.")
    return load_profile_text(PROFILE_FILE)


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


def _format_batch(batch: list[dict]) -> str:
    payload = []
    for job in batch:
        payload.append(
            {
                "id": str(job.get("id", "")),
                "company": str(job.get("company", "")),
                "title": str(job.get("title", "")),
                "location": str(job.get("location", "")),
                "flags": _precompute_flags(job),
                "description": _extract_jd_fields(str(job.get("description", ""))),
            }
        )
    return json.dumps(payload, indent=1)


def _build_prompt(profile_text: str, batch: list[dict]) -> str:
    jobs_json = _format_batch(batch)
    return (
        f"{SCORING_RULES}\n\n"
        f"CANDIDATE PROFILE:\n{profile_text}\n\n"
        f"Jobs to score:\n{jobs_json}\n"
    )


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


def run(rescore_model: str | None = None) -> pd.DataFrame:
    log.info("=== SCORING START ===")
    if not os.path.exists(FILTERED_CSV):
        raise FileNotFoundError(FILTERED_CSV)

    profile_text = _load_candidate_profile()
    df = pd.read_csv(FILTERED_CSV)
    log.info("Loaded %d jobs from %s", len(df), FILTERED_CSV)

    if rescore_model and "scored_model" in df.columns:
        bad = df["scored_model"] == rescore_model
        df.loc[bad, "fit_score"] = float("nan")
        log.info("Cleared scores for %d job(s) previously scored by %s", bad.sum(), rescore_model)

    if "fit_score" in df.columns:
        to_score = df[df["fit_score"].isna()].copy()
        already_scored = df[~df["fit_score"].isna()].copy()
        log.info("To score: %d | Already scored: %d", len(to_score), len(already_scored))
    else:
        to_score = df.copy()
        already_scored = pd.DataFrame()

    if to_score.empty:
        log.info("Nothing new to score.")
        return df

    records = to_score.to_dict(orient="records")
    total_batches = (len(records) + _BATCH_SIZE - 1) // _BATCH_SIZE
    log.info("Scoring %d jobs in %d batches", len(records), total_batches)

    all_scores: list[dict] = []
    failed_batches = 0

    for index in range(0, len(records), _BATCH_SIZE):
        batch = records[index:index + _BATCH_SIZE]
        batch_num = index // _BATCH_SIZE + 1
        companies = " | ".join(str(job.get("company", "?")) for job in batch)
        log.info("Batch %d/%d - %s", batch_num, total_batches, companies)

        expected_ids = {str(job["id"]) for job in batch}
        prompt = _build_prompt(profile_text, batch)

        try:
            raw = chat(prompt, max_tokens=8192)
            scores = _parse_response(raw, expected_ids)
            if not scores:
                log.error("Batch %d - 0 valid scores. Raw: %.200s", batch_num, raw)
                failed_batches += 1
            else:
                all_scores.extend(scores)
                summary = " | ".join(f"{score.get('fit_score', '?')}={score.get('verdict', '?')}" for score in scores)
                log.info("Batch %d - OK (%d/%d): %s", batch_num, len(scores), len(batch), summary)
                missing = expected_ids - {str(score["id"]) for score in scores}
                if missing:
                    log.warning("Batch %d - no score for %d job(s)", batch_num, len(missing))
        except RuntimeError as exc:
            failed_batches += 1
            log.error("Batch %d - provider exhausted: %s", batch_num, exc)
            break
        except Exception as exc:
            failed_batches += 1
            log.error("Batch %d failed: %s", batch_num, exc, exc_info=True)

        time.sleep(6)

    if failed_batches:
        log.warning("%d batch(es) failed. Re-run with --no-scrape to retry only unscored jobs.", failed_batches)

    if not all_scores:
        log.error("No scores generated at all. Check pipeline.log.")
        return df

    scores_df = pd.DataFrame(all_scores)
    scores_df["scored_model"] = get_session().current_model
    scores_df["id"] = scores_df["id"].astype(str)
    to_score["id"] = to_score["id"].astype(str)
    merged_new = to_score.merge(scores_df, on="id", how="left")

    if not already_scored.empty:
        already_scored["id"] = already_scored["id"].astype(str)
        merged = pd.concat([merged_new, already_scored], ignore_index=True)
    else:
        merged = merged_new

    merged = merged.sort_values("fit_score", ascending=False)
    merged.to_csv(SCORED_CSV, index=False)
    log.info("Written %d rows to %s", len(merged), SCORED_CSV)

    bins = [(80, 101, "strong_apply"), (60, 80, "apply"), (40, 60, "borderline"), (0, 40, "skip")]
    distribution = {label: len(merged[(merged["fit_score"] >= low) & (merged["fit_score"] < high)]) for low, high, label in bins}
    log.info("Distribution - %s", "  ".join(f"{label}: {count}" for label, count in distribution.items()))

    top = merged[merged["verdict"].isin(["strong_apply", "apply"])].head(10)
    if not top.empty:
        log.info("Top matches:")
        for _, row in top.iterrows():
            score_value = int(row["fit_score"]) if not pd.isna(row.get("fit_score")) else 0
            log.info("  [%3d] %-28s %s", score_value, str(row.get("company", ""))[:28], str(row.get("title", ""))[:35])

    log.info("=== SCORING DONE ===")
    return merged
