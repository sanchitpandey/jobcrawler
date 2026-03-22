from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class JobRecord:
    id: str = ""
    company: str = ""
    title: str = ""
    location: str = ""
    url: str = ""
    description: str = ""
    fit_score: float | None = None
    comp_est: str = ""
    verdict: str = ""
    gaps: str = ""
    status: str = "new"
    cover_letter: str = ""
    scraped_at: str = ""
    applied_at: str = ""


@dataclass
class ApplyResult:
    status: str
    job_url: str = ""
    company: str = ""
    title: str = ""
    manual_questions: list[str] = field(default_factory=list)
    error_message: str = ""
