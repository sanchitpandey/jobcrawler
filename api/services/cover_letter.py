"""Cover letter generation — ported from legacy/cover.py.

Public API
----------
generate_cover(job_dict, profile_text) → str
"""

from __future__ import annotations

import textwrap

from api.services.llm import chat_with_tokens

COVER_PROMPT = textwrap.dedent("""
Using the candidate profile below, write a professional cover letter for this job.

Candidate profile:
{profile}

Rules:
- 4 paragraphs, max 350 words total
- Paragraph 1: hook with the most relevant project, internship, or publication for this role
- Paragraph 2: strongest technical proof point that maps to the requirements
- Paragraph 3: why this company specifically
- Paragraph 4: close with availability and any notable differentiator from the profile
- No generic opening sentence like "I am writing to apply"
- No bullet points
- Output only the letter text

Job details:
Company: {company}
Title: {title}
Location: {location}
Description:
{description}
""")


async def generate_cover(job_dict: dict, profile_text: str) -> tuple[str, int]:
    """Generate a cover letter for a job.

    Parameters
    ----------
    job_dict:
        Dict with at minimum ``title``, ``company``, ``location``, ``description``.
    profile_text:
        Full profile markdown text (from Profile.to_text()).

    Returns
    -------
    Cover letter as a plain text string.
    """
    prompt = COVER_PROMPT.format(
        profile=profile_text,
        company=job_dict.get("company", ""),
        title=job_dict.get("title", ""),
        location=job_dict.get("location", ""),
        description=str(job_dict.get("description", ""))[:2000],
    )
    return await chat_with_tokens(prompt, max_tokens=600, temperature=0.3)
