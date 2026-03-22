import re


def _safe_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and str(value) == "nan":
        return ""
    return str(value)


def _precompute_flags(job: dict) -> dict:
    """Extract structured signals via regex without relying on fragile raw types."""
    desc = _safe_text(job.get("description", "")).lower()
    location = _safe_text(job.get("location", "")).lower()

    exp_matches = re.findall(
        r'(\d+)\s*[\+\-to]*\s*(?:\d+)?\s*years?\s*(?:of\s*)?(?:experience|exp)',
        desc,
    )
    min_exp = min((int(match) for match in exp_matches), default=0)

    is_internship = any(token in desc for token in [
        'internship', 'intern ', 'stipend', 'unpaid', 'first month is unpaid', 'training period'
    ])
    is_contract = any(token in desc for token in [
        'contract-based', 'contract role', 'initial contract', 'consultant', 'freelance'
    ])
    short_contract = bool(re.search(r'(?:through|until|till|ending)\s+(?:jun|july|aug)\s*202[56]', desc))

    infra_primary = sum(desc.count(token) for token in [
        'kubernetes', 'helm', 'terraform', 'ci/cd pipeline', 'devops', 'platform engineering', 'sre '
    ])
    ml_primary = sum(desc.count(token) for token in [
        'llm', 'transformer', 'pytorch', 'fine-tun', 'rag', 'nlp', 'machine learning model', 'training'
    ])
    is_infra_role = infra_primary > ml_primary and infra_primary >= 3

    is_bangalore_office_only = (
        'bengaluru' in location
        and not bool(job.get('is_remote'))
        and ('in-office' in desc or 'work from office' in desc)
    )

    return {
        'min_exp_years': min_exp,
        'is_internship': is_internship,
        'is_short_contract': is_contract and short_contract,
        'is_infra_role_not_ml': is_infra_role,
        'is_bangalore_office_only': is_bangalore_office_only,
    }
