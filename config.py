"""Central configuration for the job crawler."""

from core.settings import get_settings


_settings = get_settings()

SEARCH_TERMS = _settings.search.terms
LOCATION = _settings.search.location
RESULTS_PER_QUERY = _settings.search.results_per_query
HOURS_OLD = _settings.search.hours_old
SITES = _settings.search.sites

MIN_COMP_LPA = _settings.candidate.min_comp_lpa
TARGET_COMP_LPA = _settings.candidate.target_comp_lpa
RELOCATION_OK = _settings.candidate.relocation_ok
BLACKLIST_CITIES = _settings.candidate.blacklist_cities
BLACKLIST_COMPANIES = _settings.candidate.blacklist_companies
BLACKLIST_KEYWORDS = _settings.candidate.blacklist_keywords

WEIGHT_FIT = _settings.scoring.weight_fit
WEIGHT_COMP = _settings.scoring.weight_comp
WEIGHT_BRAND = _settings.scoring.weight_brand

RAW_CSV = _settings.paths.raw_csv
FILTERED_CSV = _settings.paths.filtered_csv
SCORED_CSV = _settings.paths.scored_csv
DB_PATH = _settings.paths.db_path
COVER_DIR = _settings.paths.cover_dir

GEMINI_CMD = _settings.llm.gemini_cmd
BATCH_SIZE = _settings.scoring.batch_size

LINKEDIN_EMAIL = _settings.apply.linkedin_email
LINKEDIN_PASSWORD = _settings.apply.linkedin_password
INDEED_EMAIL = _settings.apply.indeed_email
INDEED_PASSWORD = _settings.apply.indeed_password

RESUME_PATH = _settings.apply.resume_path
AUTO_APPLY_DELAY = _settings.apply.auto_apply_delay
MAX_APPLIES_PER_RUN = _settings.apply.max_applies_per_run

REVIEW_SERVER_PORT = _settings.review.port
MIN_REVIEW_SCORE = _settings.review.min_review_score
