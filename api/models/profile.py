"""
Profile model — structured representation of legacy/APPLY_PROFILE.md.

Every field maps 1-to-1 to the keys in that file so that
Profile.to_dict() returns the same dict as load_key_value_profile().
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import Base

if TYPE_CHECKING:
    from api.models.user import User


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    # ── ## Personal ────────────────────────────────────────────────────────────
    name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    github_url: Mapped[str | None] = mapped_column(String(500))
    portfolio_url: Mapped[str | None] = mapped_column(String(500))
    location_current: Mapped[str | None] = mapped_column(String(255))
    resume_path: Mapped[str | None] = mapped_column(String(1000))

    # ── ## Availability And Compensation ───────────────────────────────────────
    notice_period: Mapped[str | None] = mapped_column(String(100))
    current_ctc: Mapped[str | None] = mapped_column(String(50))
    expected_ctc: Mapped[str | None] = mapped_column(String(50))
    expected_ctc_min_lpa: Mapped[str | None] = mapped_column(String(20))
    start_date: Mapped[str | None] = mapped_column(String(20))

    # ── ## Education ───────────────────────────────────────────────────────────
    degree: Mapped[str | None] = mapped_column(String(255))
    college: Mapped[str | None] = mapped_column(String(255))
    graduation_month_year: Mapped[str | None] = mapped_column(String(20))
    graduation_year: Mapped[str | None] = mapped_column(String(10))
    cgpa: Mapped[str | None] = mapped_column(String(10))

    # ── ## Experience And Authorization ────────────────────────────────────────
    total_experience: Mapped[str | None] = mapped_column(String(255))
    work_authorization: Mapped[str | None] = mapped_column(String(255))
    willing_to_relocate: Mapped[str | None] = mapped_column(String(255))
    willing_to_travel: Mapped[str | None] = mapped_column(String(10))
    sponsorship_required: Mapped[str | None] = mapped_column(String(10))

    # ── ## Technical Experience ────────────────────────────────────────────────
    # {"python_years": "3", "ml_years": "2", "llm_nlp_rag_years": "2", ...}
    skills_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)

    # ── ## Diversity Or EEO ────────────────────────────────────────────────────
    # {"gender": "male", "ethnicity": "asian", "veteran_status": "no", "disability": "no"}
    eeo_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)

    # ── ## Job Search Preferences ──────────────────────────────────────────────
    preferred_roles: Mapped[str | None] = mapped_column(Text)
    target_locations: Mapped[str | None] = mapped_column(Text)
    avoid_roles: Mapped[str | None] = mapped_column(Text)
    avoid_companies: Mapped[str | None] = mapped_column(Text)
    minimum_compensation: Mapped[str | None] = mapped_column(Text)
    must_have_preferences: Mapped[str | None] = mapped_column(Text)
    deal_breakers: Mapped[str | None] = mapped_column(Text)

    # ── ## Candidate Summary ───────────────────────────────────────────────────
    candidate_summary: Mapped[str | None] = mapped_column(Text)
    experience_highlights: Mapped[str | None] = mapped_column(Text)

    # ── ## Short Answers ───────────────────────────────────────────────────────
    # {"why_ml_engineering": "...", "describe_challenging_project": "...", ...}
    short_answers_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)

    # ── Filtering preferences (used by filter.py port) ─────────────────────────
    blacklist_companies: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    blacklist_keywords: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    min_comp_lpa: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    target_comp_lpa: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ── Timestamps ─────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="profile")

    # ── Helpers ────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Returns the same key/value structure as load_key_value_profile()."""
        d: dict[str, Any] = {
            # Personal
            "name": self.name or "",
            "email": self.email or "",
            "phone": self.phone or "",
            "linkedin": self.linkedin_url or "",
            "github": self.github_url or "",
            "portfolio": self.portfolio_url or "",
            "location_current": self.location_current or "",
            # Availability
            "notice_period": self.notice_period or "",
            "current_ctc": self.current_ctc or "",
            "expected_ctc": self.expected_ctc or "",
            "expected_ctc_min_lpa": self.expected_ctc_min_lpa or "",
            "start_date": self.start_date or "",
            # Education
            "degree": self.degree or "",
            "college": self.college or "",
            "graduation_month_year": self.graduation_month_year or "",
            "graduation_year": self.graduation_year or "",
            "cgpa": self.cgpa or "",
            # Experience
            "total_experience": self.total_experience or "",
            "work_authorization": self.work_authorization or "",
            "willing_to_relocate": self.willing_to_relocate or "",
            "willing_to_travel": self.willing_to_travel or "",
            "sponsorship_required": self.sponsorship_required or "",
            # Preferences
            "preferred_roles": self.preferred_roles or "",
            "target_locations": self.target_locations or "",
            "avoid_roles": self.avoid_roles or "",
            "avoid_companies": self.avoid_companies or "",
            "minimum_compensation": self.minimum_compensation or "",
            "must_have_preferences": self.must_have_preferences or "",
            "deal_breakers": self.deal_breakers or "",
            # Summary
            "candidate_summary": self.candidate_summary or "",
            "experience_highlights": self.experience_highlights or "",
            # Filtering
            "target_comp_lpa": self.target_comp_lpa,
            "min_comp_lpa": self.min_comp_lpa,
        }
        d.update(self.skills_json or {})
        d.update(self.eeo_json or {})
        d.update(self.short_answers_json or {})
        return d

    def to_text(self) -> str:
        """
        Reconstructs the APPLY_PROFILE.md markdown format that LLM prompts expect.
        Mirrors the output of load_profile_text(APPLY_PROFILE.md).
        """
        skills = self.skills_json or {}
        eeo = self.eeo_json or {}
        short = self.short_answers_json or {}

        skill_lines = "\n".join(f'{k}: "{v}"' for k, v in skills.items())
        eeo_lines = "\n".join(f'{k}: "{v}"' for k, v in eeo.items())
        short_lines = "\n".join(f"{k}: >\n  {v}" for k, v in short.items())

        return "\n\n".join(
            filter(
                None,
                [
                    "## Personal",
                    f'name: "{self.name}"\nemail: "{self.email}"\nphone: "{self.phone}"\n'
                    f'linkedin: "{self.linkedin_url}"\ngithub: "{self.github_url}"\n'
                    f'portfolio: "{self.portfolio_url}"\nlocation_current: "{self.location_current}"',
                    "## Availability And Compensation",
                    f'notice_period: "{self.notice_period}"\ncurrent_ctc: "{self.current_ctc}"\n'
                    f'expected_ctc: "{self.expected_ctc}"\nstart_date: "{self.start_date}"',
                    "## Education",
                    f'degree: "{self.degree}"\ncollege: "{self.college}"\n'
                    f'graduation_month_year: "{self.graduation_month_year}"\n'
                    f'graduation_year: "{self.graduation_year}"\ncgpa: "{self.cgpa}"',
                    "## Experience And Authorization",
                    f'total_experience: "{self.total_experience}"\n'
                    f'work_authorization: "{self.work_authorization}"\n'
                    f'willing_to_relocate: "{self.willing_to_relocate}"\n'
                    f'sponsorship_required: "{self.sponsorship_required}"',
                    "## Technical Experience",
                    skill_lines,
                    "## Diversity Or EEO",
                    eeo_lines,
                    "## Job Search Preferences",
                    f"preferred_roles: >\n  {self.preferred_roles}\n"
                    f"target_locations: >\n  {self.target_locations}",
                    "## Candidate Summary",
                    f"candidate_summary: >\n  {self.candidate_summary}\n"
                    f"experience_highlights: >\n  {self.experience_highlights}",
                    "## Short Answers",
                    short_lines,
                ],
            )
        )
