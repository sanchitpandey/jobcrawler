# cover.py
import subprocess, os, textwrap
import pandas as pd
from config import SCORED_CSV, COVER_DIR, GEMINI_CMD
from providers import chat

COVER_PROMPT = textwrap.dedent("""
Using the candidate profile in GEMINI.md, write a professional cover letter 
for this job. 

Rules:
- 4 paragraphs, max 350 words total
- Para 1: hook with most relevant project/paper for THIS role specifically
- Para 2: strongest technical proof point that maps to their requirements  
- Para 3: why THIS company specifically (not generic)
- Para 4: clean close with availability (July 2026) and arXiv paper mention
- No "I am writing to apply" openers
- No bullet points
- Output only the letter text, no subject line, no address header

Job details:
Company: {company}
Title: {title}
Location: {location}
Description:
{description}
""")

def generate_cover(row: dict) -> str:
    prompt = COVER_PROMPT.format(
        company=row.get("company", ""),
        title=row.get("title", ""),
        location=row.get("location", ""),
        description=str(row.get("description", ""))[:2000],
    )
    return chat(prompt, max_tokens=600, temperature=0.3)

def run(top_n=5):
    df = pd.read_csv(SCORED_CSV)
    top = df[df["verdict"].isin(["strong_apply", "apply"])].head(top_n)

    os.makedirs(COVER_DIR, exist_ok=True)
    generated = []

    for _, row in top.iterrows():
        company_slug = str(row["company"]).lower().replace(" ", "_")[:20]
        fname = f"{COVER_DIR}/cover_{company_slug}.txt"

        if os.path.exists(fname):
            print(f"  Skipping {row['company']} (already exists)")
            continue

        print(f"  Generating for {row['company']}...", end=" ")
        try:
            letter = generate_cover(row.to_dict())
            with open(fname, "w", encoding="utf-8") as f:
                f.write(f"Company: {row['company']}\n")
                f.write(f"Role: {row['title']}\n")
                f.write(f"Fit Score: {row.get('fit_score', '?')}\n")
                f.write(f"URL: {row.get('job_url', row.get('url', ''))}\n")
                f.write("\n" + "─"*60 + "\n\n")
                f.write(letter)
            print(f"✓ → {fname}")
            generated.append(fname)
        except Exception as e:
            print(f"✗ {e}")

    return generated