import asyncio
import re
from sqlalchemy import update
from api.models.base import AsyncSessionLocal
from api.models.profile import Profile

def parse_profile(filepath: str) -> dict:
    profile = {}
    with open(filepath, 'r', encoding='utf-8') as f:
        buf_key = None
        buf_val = []
        for line in f:
            if line.startswith("#"):
                continue
            match = re.match(r'^([a-z_]+):\s*(.*)$', line)
            if match:
                if buf_key:
                    profile[buf_key] = "\n".join(buf_val).strip().strip('"')
                buf_key = match.group(1)
                val = match.group(2).strip()
                if val == '>':
                    buf_val = []
                else:
                    buf_val = [val]
            elif line.startswith("  ") and buf_key:
                buf_val.append(line.strip())
        if buf_key:
            profile[buf_key] = "\n".join(buf_val).strip().strip('"')
    return profile

async def run():
    async with AsyncSessionLocal() as db:
        p = parse_profile('legacy/APPLY_PROFILE.md')
        # update all profiles for now (assuming only the main user)
        # target_comp_lpa, min_comp_lpa might be strings, make sure they are ints
        if "target_comp_lpa" in p and isinstance(p["target_comp_lpa"], str) and not p["target_comp_lpa"].strip():
            p["target_comp_lpa"] = 0
        if "min_comp_lpa" in p and isinstance(p["min_comp_lpa"], str) and not p["min_comp_lpa"].strip():
            p["min_comp_lpa"] = 0
            
        await db.execute(update(Profile).values(**p))
        await db.commit()
        print("Updated profiles successfully!")

if __name__ == "__main__":
    asyncio.run(run())
