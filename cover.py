import os
import textwrap
from pathlib import Path

import pandas as pd

from config import COVER_DIR, SCORED_CSV
from core.profile import load_profile_text
from providers import chat

PROFILE_FILE = Path("APPLY_PROFILE.md")

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


def _load_profile() -> str:
    if not PROFILE_FILE.exists():
        raise FileNotFoundError("APPLY_PROFILE.md not found. Fill in your profile before generating cover letters.")
    return load_profile_text(PROFILE_FILE)


def generate_cover(row: dict, profile_text: str) -> str:
    prompt = COVER_PROMPT.format(
        profile=profile_text,
        company=row.get("company", ""),
        title=row.get("title", ""),
        location=row.get("location", ""),
        description=str(row.get("description", ""))[:2000],
    )
    return chat(prompt, max_tokens=600, temperature=0.3)


def run(top_n: int = 5) -> list[str]:
    df = pd.read_csv(SCORED_CSV)
    top = df[df["verdict"].isin(["strong_apply", "apply"])].head(top_n)
    profile_text = _load_profile()

    os.makedirs(COVER_DIR, exist_ok=True)
    generated: list[str] = []

    for _, row in top.iterrows():
        company_slug = str(row["company"]).lower().replace(" ", "_")[:20]
        filename = f"{COVER_DIR}/cover_{company_slug}.txt"

        if os.path.exists(filename):
            print(f"  Skipping {row['company']} (already exists)")
            continue

        print(f"  Generating for {row['company']}...", end=" ")
        try:
            letter = generate_cover(row.to_dict(), profile_text)
            with open(filename, "w", encoding="utf-8") as handle:
                handle.write(f"Company: {row['company']}\n")
                handle.write(f"Role: {row['title']}\n")
                handle.write(f"Fit Score: {row.get('fit_score', '?')}\n")
                handle.write(f"URL: {row.get('job_url', row.get('url', ''))}\n")
                handle.write("\n" + "-" * 60 + "\n\n")
                handle.write(letter)
            print(f"[OK] -> {filename}")
            generated.append(filename)
        except Exception as exc:
            print(f"[X] {exc}")

    return generated
