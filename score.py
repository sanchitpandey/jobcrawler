"""
score.py  —  provider-agnostic via providers.py
─────────────────────────────────────────────────
Switch provider by setting LLM_PROVIDER env var. Zero code changes needed.
"""

import json
import os
import re
import time
import pandas as pd

from logger    import get_logger
from providers import chat
from config    import FILTERED_CSV, SCORED_CSV, BATCH_SIZE
from utils import _precompute_flags

log = get_logger(__name__)
_BATCH_SIZE = min(BATCH_SIZE, 5)

SCORE_PROMPT = """\
You are a strict recruiter scoring job listings for an ML/NLP candidate.
 
CANDIDATE SUMMARY:
- First-author ACL ARR 2026 paper on RAG utilization failure in sub-7B LLMs (arXiv:2603.11513)
- Skills: PyTorch, HuggingFace TRL, Dual-PPO RLHF, FAISS+BM25 RAG pipelines, FastAPI, LangChain
- Education: BITS Pilani B.E. E&I, CGPA 7.15, graduating May 2026
- Experience: Genpact AI intern (Dual-PPO self-play, HF TRL internals, ~30% perf gain)
- FRESHER — 0 years full-time. Available July 2026. Min 12 LPA, target 15-18 LPA.
 
MANDATORY PENALTIES (apply these FIRST, before anything else):
 
1. SENIORITY PENALTY — if the job title contains ANY of these words/phrases,
   the score MUST be below 35, regardless of company or tech stack:
   "Sr. Staff", "Staff Engineer", "Principal", "Senior Staff", "Distinguished",
   "Director", "VP of", "Head of", "Lead Engineer" (when Lead implies 5+ yr exp).
   Reason: a fresher cannot pass these interviews. Do not waste application slots.
 
2. PROMPT ENGINEERING PENALTY — if the primary role is "Prompt Engineer",
   "Prompt Engineering", or "Prompt Specialist", score MUST be below 50.
   Reason: this does not use the candidate's RLHF/RAG/NLP research depth.
 
3. STAFFING / BODY SHOP PENALTY — if the company is a staffing agency,
   placement firm, or recruiter (e.g. Uplers, TeamLease, Hireginie, JForce,
   or any company whose JD is actually for a client role):
   score MUST be below 30.
 
4. DOMAIN COMPANY PENALTY — if the company's core business is NOT technology
   (agriculture/food/FMCG like Cargill, auto parts like Advance Auto,
   pharma, telecom infrastructure, beer/beverages):
   score MUST be below 45, however many ML keywords appear in the JD.

5. INTERNSHIP / UNPAID PENALTY — if flags.is_internship is true OR the description
   mentions "stipend", "unpaid first month", or "training period":
   score MUST be below 35.
   Reason: candidate is seeking full-time employment from July 2026.

6. SHORT CONTRACT PENALTY — if flags.is_short_contract is true (contract ending
   before September 2026):
   score MUST be below 45.
   Reason: a 2-3 month engagement is not a job — it is barely an extension.

7. INFRA/DEVOPS PENALTY — if flags.is_infra_role_not_ml is true (primary skills
   are Kubernetes, Terraform, Helm, CI/CD with ML as secondary):
   score MUST be below 40.
   Reason: candidate has zero DevOps/Platform Engineering background.

8. EXPERIENCE GAP PENALTY — if flags.min_exp_years >= 4:
   cap the score at 55, regardless of tech stack alignment.
   If flags.min_exp_years >= 6: cap at 35.
   Reason: fresher will not clear HR filters at these companies.
 
SCORING RUBRIC (apply after the penalties above):
85-100: AI-first company (LLM startup, research lab, AI product co.)
        + role directly involves LLMs/RAG/NLP/RL training
        + 0-2 years experience required OR explicitly says fresher/new grad
65-84 : Good AI role at non-AI company (GCC of a tech firm, fintech product co.)
        OR AI-first company but 2-3yr exp bar
        OR adjacent role (MLOps, DS) at strong company
40-64 : DS/analytics at domain company
        OR AI role at legacy enterprise (Ericsson, Teradata, TCS GCC)
        OR experience requirement is 3+ years
0-39  : Domain company with no AI research culture
        OR staffing / body shopping company
        OR pure analytics / BI / Tableau with no ML
 
CALIBRATION (use these to anchor your scale):
  Sarvam AI Research Residency → 95
  Cohere Research Engineer → 92
  Glean Data Scientist (AI search startup) → 88
  LinkedIn Sr. Staff ML Engineer → 20  (seniority penalty — auto below 35)
  Amazon Applied Scientist (analytics team) → 68
  Ericsson Gen AI Engineer → 52
  Getege EdTech Prompt Engineering → 48  (prompt eng penalty)
  AB InBev Data Scientist → 28
  Cargill ML Engineer → 35  (domain company penalty)
  Advance Auto Parts Data Scientist → 15
  Uplers (staffing) any role → 20  (staffing penalty)
 
verdict mapping:
  strong_apply = fit_score >= 80
  apply        = fit_score 60-79
  borderline   = fit_score 40-59
  skip         = fit_score < 40
 
OUTPUT: Return ONLY a valid JSON array — no markdown fences, no text before or after.
[
  {{
    "id": "<copy id field exactly as given>",
    "fit_score": <integer 0-100>,
    "comp_estimate": "<e.g. 14-18 LPA>",
    "verdict": "strong_apply|apply|borderline|skip",
    "gaps": ["specific missing requirement 1", "up to 3 total"],
    "why": "<one sentence — strongest reason to apply or skip, mention if a penalty was applied>"
  }}
]

Jobs to score:
{jobs_json}"""

def _extract_jd_fields(desc: str) -> str:
    """Extract the highest-signal sections from a JD."""
    full = desc[:4000]  # work with more raw text
    
    # Key signal patterns to surface explicitly
    lines = full.split('\n')
    requirements_lines = []
    in_req_section = False
    
    for line in lines:
        lower = line.lower()
        # Detect requirements sections
        if any(k in lower for k in ['required', 'qualification', 'must have', 
                                      'minimum', 'you bring', 'what we need']):
            in_req_section = True
        if any(k in lower for k in ['what we offer', 'benefit', 'why join', 
                                      'about us', 'perks']):
            in_req_section = False
        if in_req_section or any(k in lower for k in 
                                  ['years of exp', 'yrs exp', 'year experience',
                                   'internship', 'contract', 'full-time',
                                   'stipend', 'unpaid', 'fresher', 'entry level']):
            requirements_lines.append(line)
    
    # Always include first 400 chars (role overview) + extracted requirements
    overview = desc[:400]
    reqs = '\n'.join(requirements_lines[:40])  # up to 40 requirement lines
    return f"{overview}\n---REQUIREMENTS---\n{reqs}"[:2500]

def _format_batch(batch: list[dict]) -> str:
    return json.dumps([
        {
            "id":          str(j.get("id", "")),
            "company":     str(j.get("company", "")),
            "title":       str(j.get("title", "")),
            "location":    str(j.get("location", "")),
            "flags":       _precompute_flags(j),
            "description": _extract_jd_fields(str(j.get("description", ""))),
        }
        for j in batch
    ], indent=1)
 
 
def _parse_response(raw: str, expected_ids: set) -> list[dict]:
    # Strip <think>...</think> blocks from reasoning models (Gemini 2.5, DeepSeek R1)
    text = re.sub(r"<think>.*?</think>", "", raw.strip(), flags=re.DOTALL)
    text = re.sub(r"^```(?:json)?\s*\n?", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text, flags=re.MULTILINE).strip()
 
    if text.startswith("{"):
        try:
            obj = json.loads(text)
            for v in obj.values():
                if isinstance(v, list):
                    return _validate(v, expected_ids)
        except json.JSONDecodeError:
            pass
 
    start = text.find("[")
    end   = text.rfind("]")
    if start == -1:
        raise ValueError(f"No JSON array in response: {text[:150]!r}")
 
    arr = text[start: end + 1] if end > start else text[start:]
    try:
        return _validate(json.loads(arr), expected_ids)
    except json.JSONDecodeError:
        return _validate(json.loads(arr + "]"), expected_ids)
 
 
def _validate(items: list, expected_ids: set) -> list[dict]:
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("id", "")) not in expected_ids:
            continue
        if "fit_score" not in item:
            continue
        try:
            item["fit_score"] = int(item["fit_score"])
        except (ValueError, TypeError):
            continue
        out.append(item)
    return out
 
 
def run() -> pd.DataFrame:
    log.info("=== SCORING START ===")
 
    if not os.path.exists(FILTERED_CSV):
        log.error("Filtered CSV not found: %s", FILTERED_CSV)
        raise FileNotFoundError(FILTERED_CSV)
 
    df = pd.read_csv(FILTERED_CSV)
    log.info("Loaded %d jobs from %s", len(df), FILTERED_CSV)
 
    if "fit_score" in df.columns:
        mask           = df["fit_score"].isna()
        to_score       = df[mask].copy()
        already_scored = df[~mask].copy()
        log.info("To score: %d | Already scored (skipping): %d",
                 len(to_score), len(already_scored))
    else:
        to_score       = df.copy()
        already_scored = pd.DataFrame()
 
    if to_score.empty:
        log.info("Nothing new to score.")
        return df
 
    records       = to_score.to_dict(orient="records")
    total_batches = (len(records) + _BATCH_SIZE - 1) // _BATCH_SIZE
    log.info("Scoring %d jobs in %d batches", len(records), total_batches)
 
    all_scores: list[dict] = []
    failed_batches = 0
 
    for i in range(0, len(records), _BATCH_SIZE):
        batch     = records[i: i + _BATCH_SIZE]
        batch_num = i // _BATCH_SIZE + 1
        companies = " | ".join(str(j.get("company", "?")) for j in batch)
        log.info("Batch %d/%d — %s", batch_num, total_batches, companies)
 
        expected_ids = {str(j["id"]) for j in batch}
        prompt = SCORE_PROMPT.format(jobs_json=_format_batch(batch))
 
        try:
            raw    = chat(prompt)
            scores = _parse_response(raw, expected_ids)
 
            if not scores:
                log.error("Batch %d — 0 valid scores. Raw: %.200s", batch_num, raw)
                failed_batches += 1
            else:
                all_scores.extend(scores)
                summary = " | ".join(
                    f"{s.get('fit_score','?')}={s.get('verdict','?')}"
                    for s in scores
                )
                log.info("Batch %d — OK (%d/%d): %s",
                         batch_num, len(scores), len(batch), summary)
                missing = expected_ids - {str(s["id"]) for s in scores}
                if missing:
                    log.warning("Batch %d — no score for %d job(s)", batch_num, len(missing))
 
        except RuntimeError as e:
            log.error("Batch %d — provider exhausted: %s", batch_num, e)
            failed_batches += 1
            log.warning(
                "Stopping at batch %d/%d. Scored %d jobs so far. "
                "Re-run with --no-scrape or switch provider (LLM_PROVIDER=openrouter).",
                batch_num, total_batches, len(all_scores)
            )
            break
 
        except Exception as e:
            failed_batches += 1
            log.error("Batch %d FAILED: %s", batch_num, e, exc_info=True)
 
        time.sleep(3)
 
    if failed_batches:
        log.warning(
            "%d batch(es) failed. Run `python main.py --no-scrape` to retry only unscored jobs.",
            failed_batches
        )
 
    if not all_scores:
        log.error("No scores generated at all. Check pipeline.log.")
        return df
 
    scores_df       = pd.DataFrame(all_scores)
    scores_df["id"] = scores_df["id"].astype(str)
    to_score["id"]  = to_score["id"].astype(str)
    merged_new      = to_score.merge(scores_df, on="id", how="left")
 
    if not already_scored.empty:
        already_scored["id"] = already_scored["id"].astype(str)
        merged = pd.concat([merged_new, already_scored], ignore_index=True)
    else:
        merged = merged_new
 
    merged = merged.sort_values("fit_score", ascending=False)
    merged.to_csv(SCORED_CSV, index=False)
    log.info("Written %d rows to %s", len(merged), SCORED_CSV)
 
    bins = [(80,101,"strong_apply"),(60,80,"apply"),(40,60,"borderline"),(0,40,"skip")]
    dist = {l: len(merged[(merged["fit_score"]>=lo)&(merged["fit_score"]<hi)])
            for lo,hi,l in bins}
    log.info("Distribution — %s", "  ".join(f"{k}: {v}" for k,v in dist.items()))
 
    top = merged[merged["verdict"].isin(["strong_apply","apply"])].head(10)
    if not top.empty:
        log.info("Top matches:")
        for _, r in top.iterrows():
            sc = int(r["fit_score"]) if not pd.isna(r.get("fit_score")) else 0
            log.info("  [%3d] %-28s %s", sc,
                     str(r.get("company",""))[:28], str(r.get("title",""))[:35])
 
    log.info("=== SCORING DONE ===")
    return merged