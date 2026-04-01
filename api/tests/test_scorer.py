"""Tests for api/services/scorer.py"""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from api.services.scorer import (
    _extract_jd_fields,
    _precompute_flags,
    _sanitize_json,
    _parse_response,
    _load_scoring_policy,
    _render_mandatory_boosts,
    _build_prompt,
    SCORING_RULES,
)


# ── _extract_jd_fields ────────────────────────────────────────────────────────

def test_extract_jd_fields_returns_overview_and_requirements():
    # Build a desc long enough that the benefits line falls outside the 400-char overview.
    padding = "A" * 450 + "\n"
    desc = (
        padding
        + "Required: 3 years of experience in Python.\n"
        + "Must have: PyTorch knowledge.\n"
        + "What we offer: great salary.\n"
        + "Benefit: health insurance.\n"
    )
    result = _extract_jd_fields(desc)
    assert "---REQUIREMENTS---" in result
    assert "3 years of experience" in result
    # "what we offer" stops requirements collection — these should NOT appear
    # in the requirements block (they could appear in the 400-char overview only
    # if the desc were short, but here padding pushes them past it)
    assert "great salary" not in result
    assert "health insurance" not in result


def test_extract_jd_fields_truncates_at_2500():
    long_desc = "x" * 5000
    assert len(_extract_jd_fields(long_desc)) <= 2500


# ── _precompute_flags ─────────────────────────────────────────────────────────

def test_precompute_flags_internship():
    job = {"description": "This is an internship role with a stipend.", "location": ""}
    flags = _precompute_flags(job)
    assert flags["is_internship"] is True
    assert flags["is_infra_role_not_ml"] is False


def test_precompute_flags_min_exp():
    job = {"description": "Minimum 5 years of experience in ML required.", "location": ""}
    flags = _precompute_flags(job)
    assert flags["min_exp_years"] == 5


def test_precompute_flags_infra_role():
    job = {
        "description": "kubernetes helm terraform devops devops sre  ci/cd pipeline platform engineering",
        "location": "",
    }
    flags = _precompute_flags(job)
    assert flags["is_infra_role_not_ml"] is True


def test_precompute_flags_no_internship():
    job = {"description": "Full-time ML engineer role at a product company.", "location": ""}
    flags = _precompute_flags(job)
    assert flags["is_internship"] is False


# ── _sanitize_json ────────────────────────────────────────────────────────────

def test_sanitize_json_strips_think_blocks():
    raw = "<think>some reasoning</think>[{\"id\": \"1\"}]"
    result = _sanitize_json(raw)
    assert "<think>" not in result
    assert "[{" in result


def test_sanitize_json_strips_markdown_fences():
    raw = "```json\n[{\"id\": \"1\"}]\n```"
    result = _sanitize_json(raw)
    assert "```" not in result
    assert "[{" in result


def test_sanitize_json_removes_trailing_commas():
    raw = '[{"id": "1", "score": 75,}]'
    result = _sanitize_json(raw)
    assert result == '[{"id": "1", "score": 75}]'


# ── _parse_response ───────────────────────────────────────────────────────────

def test_parse_response_valid_array():
    raw = json.dumps([{"id": "42", "fit_score": 80, "verdict": "apply", "gaps": [], "why": "good", "comp_estimate": "20 LPA"}])
    results = _parse_response(raw, {"42"})
    assert len(results) == 1
    assert results[0]["fit_score"] == 80


def test_parse_response_filters_unknown_ids():
    raw = json.dumps([{"id": "99", "fit_score": 70, "verdict": "apply", "gaps": [], "why": "ok", "comp_estimate": ""}])
    results = _parse_response(raw, {"42"})
    assert results == []


def test_parse_response_wrapped_object():
    raw = json.dumps({"results": [{"id": "1", "fit_score": 60, "verdict": "borderline", "gaps": [], "why": "meh", "comp_estimate": ""}]})
    results = _parse_response(raw, {"1"})
    assert len(results) == 1


def test_parse_response_with_markdown_fence():
    payload = [{"id": "5", "fit_score": 90, "verdict": "strong_apply", "gaps": [], "why": "great", "comp_estimate": "25 LPA"}]
    raw = f"```json\n{json.dumps(payload)}\n```"
    results = _parse_response(raw, {"5"})
    assert results[0]["fit_score"] == 90


def test_parse_response_no_array_raises():
    with pytest.raises(ValueError, match="No JSON array"):
        _parse_response("just some text", {"1"})


# ── Scoring policy ────────────────────────────────────────────────────────────

def test_load_scoring_policy_derives_niche_from_skills():
    kv = {"llm_nlp_rag_years": "2", "pytorch_years": "1"}
    policy = _load_scoring_policy(kv, "")
    assert "LLMs" in policy["niche_keywords"]
    assert "PyTorch" in policy["niche_keywords"]


def test_load_scoring_policy_junior_profile_detected():
    kv = {"candidate_summary": "I am a fresher looking for entry-level ML roles."}
    policy = _load_scoring_policy(kv, "")
    assert policy["enable_junior_boosts"] is True


def test_render_mandatory_boosts_empty_when_no_keywords():
    policy = {
        "niche_keywords": [],
        "trending_keywords": [],
        "junior_signals": [],
        "niche_points": 15,
        "trending_points": 15,
        "junior_points": 10,
    }
    assert _render_mandatory_boosts(policy) == ""


def test_render_mandatory_boosts_includes_niche():
    policy = {
        "niche_keywords": ["RAG", "PyTorch"],
        "trending_keywords": [],
        "junior_signals": [],
        "niche_points": 15,
        "trending_points": 15,
        "junior_points": 10,
    }
    result = _render_mandatory_boosts(policy)
    assert "RAG" in result
    assert "Niche Skill Match" in result


# ── _build_prompt ─────────────────────────────────────────────────────────────

def test_build_prompt_contains_profile_and_job():
    job = {"id": "10", "title": "ML Engineer", "company": "Acme", "location": "Remote", "description": "Build LLM pipelines."}
    kv = {"llm_nlp_rag_years": "2"}
    policy = _load_scoring_policy(kv, "experienced ML engineer")
    prompt = _build_prompt("experienced ML engineer", policy, job)
    assert "ML Engineer" in prompt
    assert "Acme" in prompt
    assert "CANDIDATE PROFILE:" in prompt
    assert "Jobs to score:" in prompt


# ── SCORING_RULES template ────────────────────────────────────────────────────

def test_scoring_rules_substitution():
    rendered = SCORING_RULES.substitute(mandatory_boosts="")
    assert "MANDATORY PENALTIES" in rendered
    assert "VERDICT MAPPING" in rendered
    assert "SCORING RUBRIC" in rendered
    assert "strong_apply" in rendered


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
