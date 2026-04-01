from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return int(raw)


def _env_tuple(name: str, default: tuple[int, int]) -> tuple[int, int]:
    raw = os.environ.get(name)
    if not raw:
        return default
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 2:
        return default
    return int(parts[0]), int(parts[1])


@dataclass(frozen=True)
class SearchSettings:
    terms: list[str]
    location: str
    results_per_query: int
    hours_old: int
    sites: list[str]


@dataclass(frozen=True)
class CandidatePreferences:
    min_comp_lpa: int
    target_comp_lpa: int
    relocation_ok: bool
    blacklist_cities: list[str]
    blacklist_companies: list[str]
    blacklist_keywords: list[str]


@dataclass(frozen=True)
class ScoringSettings:
    weight_fit: float
    weight_comp: float
    weight_brand: float
    batch_size: int


@dataclass(frozen=True)
class ReviewSettings:
    port: int
    min_review_score: int


@dataclass(frozen=True)
class ApplySettings:
    linkedin_email: str
    linkedin_password: str | None
    indeed_email: str
    indeed_password: str | None
    resume_path: str
    auto_apply_delay: tuple[int, int]
    max_applies_per_run: int


@dataclass(frozen=True)
class PathSettings:
    raw_csv: str
    filtered_csv: str
    scored_csv: str
    db_path: str
    cover_dir: str
    output_dir: str = "output"
    resume_dir: str = "resume"


@dataclass(frozen=True)
class LLMSettings:
    gemini_cmd: str
    provider_name: str


@dataclass(frozen=True)
class Settings:
    search: SearchSettings
    candidate: CandidatePreferences
    scoring: ScoringSettings
    review: ReviewSettings
    apply: ApplySettings
    paths: PathSettings
    llm: LLMSettings

    @property
    def root_dir(self) -> Path:
        return Path.cwd()


def _default_search_terms() -> list[str]:
    env_terms = _split_csv(os.environ.get("JOB_SEARCH_TERMS"))
    if env_terms:
        return env_terms
    return [
        # Tier 1 — high relevance
        "AI ML Engineer",
        "Machine Learning Engineer",
        "NLP Engineer",
        "LLM Engineer",
        "Applied Scientist ML",
        "AI Engineer",
        # Tier 2 — adjacent roles
        "MLOps Engineer",
        "Deep Learning Engineer",
        "Data Scientist NLP",
        "Research Engineer ML",
        "AI Platform Engineer",
        "Gen AI Engineer",
    ]


def _default_sites() -> list[str]:
    env_sites = _split_csv(os.environ.get("JOB_SITES"))
    return env_sites or ["linkedin", "indeed"]


def _default_blacklist_companies() -> list[str]:
    env_companies = _split_csv(os.environ.get("BLACKLIST_COMPANIES"))
    if env_companies:
        return env_companies
    return [
        "recro", "ksolves", "cogent", "infosys", "wipro", "cognizant",
        "tcs", "hcl", "tech mahindra", "mphasis", "ltimindtree",
        "accenture", "capgemini", "hexaware", "mindteck",
        "quess", "teamlease", "manpower", "randstad", "adecco",
        "viraaj", "lmj innovations", "golden opportunities", "whitefield careers",
        "uplers", "jforce", "hireginie", "canorous", "techs to suit",
        "manuscriptpedia", "iConsultera", "ascendion", "bristlecone",
    ]


def _default_blacklist_keywords() -> list[str]:
    env_keywords = _split_csv(os.environ.get("BLACKLIST_KEYWORDS"))
    if env_keywords:
        return env_keywords
    return [
        "1 week", "2 week", "short term contract", "staffing",
        "body shop", "c2h", "contract to hire", "prompt engineer",
        "prompt engineering", "senior staff", "principal engineer",
        "staff engineer", "distinguished engineer",
        "data analyst", "business analyst", "bi developer",
        "power bi", "tableau developer", "etl developer",
        "data entry", "annotation", "labeling", "labelling",
        "android developer", "ios developer", "flutter",
        "react native", "frontend developer", "ui developer",
        "network engineer", "system administrator", "dba",
        "manual testing", "qa engineer", "test engineer",
        "technical writer", "scrum master", "project manager",
        "sales engineer", "solutions architect", "pre-sales",
        "customer success", "account manager",
    ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        search=SearchSettings(
            terms=_default_search_terms(),
            location=os.environ.get("JOB_LOCATION", "India"),
            results_per_query=_env_int("RESULTS_PER_QUERY", 80),
            hours_old=_env_int("HOURS_OLD", 72),
            sites=_default_sites(),
        ),
        candidate=CandidatePreferences(
            min_comp_lpa=_env_int("MIN_COMP_LPA", 10),
            target_comp_lpa=_env_int("TARGET_COMP_LPA", 14),
            relocation_ok=_env_bool("RELOCATION_OK", True),
            blacklist_cities=_split_csv(os.environ.get("BLACKLIST_CITIES")),
            blacklist_companies=_default_blacklist_companies(),
            blacklist_keywords=_default_blacklist_keywords(),
        ),
        scoring=ScoringSettings(
            weight_fit=float(os.environ.get("WEIGHT_FIT", 0.5)),
            weight_comp=float(os.environ.get("WEIGHT_COMP", 0.3)),
            weight_brand=float(os.environ.get("WEIGHT_BRAND", 0.2)),
            batch_size=_env_int("BATCH_SIZE", 8),
        ),
        review=ReviewSettings(
            port=_env_int("REVIEW_SERVER_PORT", 5055),
            min_review_score=_env_int("MIN_REVIEW_SCORE", 55),
        ),
        apply=ApplySettings(
            linkedin_email=os.environ.get("LINKEDIN_EMAIL", ""),
            linkedin_password=os.environ.get("LINKEDIN_PASSWORD", ""),
            indeed_email=os.environ.get("INDEED_EMAIL", ""),
            indeed_password=os.environ.get("INDEED_PASSWORD", ""),
            resume_path=os.environ.get("RESUME_PATH", "resume/resume.pdf"),
            auto_apply_delay=_env_tuple("AUTO_APPLY_DELAY", (8, 20)),
            max_applies_per_run=_env_int("MAX_APPLIES_PER_RUN", 25),
        ),
        paths=PathSettings(
            raw_csv=os.environ.get("RAW_CSV", "output/jobs_raw.csv"),
            filtered_csv=os.environ.get("FILTERED_CSV", "output/jobs_filtered.csv"),
            scored_csv=os.environ.get("SCORED_CSV", "output/jobs_scored.csv"),
            db_path=os.environ.get("DB_PATH", "output/tracker.db"),
            cover_dir=os.environ.get("COVER_DIR", "output/cover_letters"),
        ),
        llm=LLMSettings(
            gemini_cmd=os.environ.get("GEMINI_CMD", r"C:/Program Files/nodejs/gemini.cmd"),
            provider_name=os.environ.get("LLM_PROVIDER", "auto"),
        ),
    )


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()
