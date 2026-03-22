import re

def _precompute_flags(job: dict) -> dict:
    """Extract structured signals via regex — no LLM needed."""
    desc  = (job.get("description", "") or "").lower()
    title = (job.get("title", "")       or "").lower()
    
    # Experience years — find the minimum requirement
    exp_matches = re.findall(
        r'(\d+)\s*[\+\-–to]*\s*(?:\d+)?\s*years?\s*(?:of\s*)?(?:experience|exp)', 
        desc
    )
    min_exp = min((int(x) for x in exp_matches), default=0)
    
    # Role type signals
    is_internship = any(k in desc for k in [
        'internship', 'intern ', 'stipend', 'unpaid', 
        'first month is unpaid', 'training period'
    ])
    is_contract   = any(k in desc for k in [
        'contract-based', 'contract role', 'initial contract', 
        'consultant', 'freelance'
    ])
    
    # Contract duration — flag very short ones
    short_contract = bool(re.search(
        r'(?:through|until|till|ending)\s+(?:jun|july|aug)\s*202[56]', desc
    ))
    
    # Primary skill mismatch — infra/devops with no ML core
    infra_primary  = sum(desc.count(k) for k in [
        'kubernetes', 'helm', 'terraform', 'ci/cd pipeline', 
        'devops', 'platform engineering', 'sre '
    ])
    ml_primary     = sum(desc.count(k) for k in [
        'llm', 'transformer', 'pytorch', 'fine-tun', 'rag', 
        'nlp', 'machine learning model', 'training'
    ])
    is_infra_role  = infra_primary > ml_primary and infra_primary >= 3
    
    # Location — candidate is in Delhi/can relocate, but flag very remote-hostile roles
    location = (job.get("location") or "").lower()
    is_bangalore_office_only = (
        "bengaluru" in location and 
        not job.get("is_remote") and
        "in-office" in desc or "work from office" in desc
    )
    
    return {
        "min_exp_years":           min_exp,
        "is_internship":           is_internship,
        "is_short_contract":       is_contract and short_contract,
        "is_infra_role_not_ml":    is_infra_role,
        "is_bangalore_office_only": is_bangalore_office_only,
    }