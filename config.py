# config.py
import os
from dotenv import load_dotenv
load_dotenv()
# ── Job search settings ────────────────────────────────────────────────────
SEARCH_TERMS = [
    "ML Engineer LLM",
    "NLP Engineer",
    "AI Engineer RAG",
    "Machine Learning Engineer NLP",
]
LOCATION = "India"
RESULTS_PER_QUERY = 50
HOURS_OLD = 72  # only jobs posted in last 3 days
SITES = ["linkedin", "indeed", "glassdoor"]

# ── Your profile ───────────────────────────────────────────────────────────
MIN_COMP_LPA = 10          # never show jobs below this
TARGET_COMP_LPA = 14       # what you're aiming for
RELOCATION_OK = True       # show jobs outside Hyderabad
BLACKLIST_CITIES = []      # e.g. ["Chennai"] if you won't go

# ── Blacklist — companies/terms to auto-reject ─────────────────────────────
BLACKLIST_COMPANIES = [
    "recro", "ksolves", "cogent", "infosys", "wipro", "cognizant",
    "tcs", "hcl", "tech mahindra", "mphasis", "ltimindtree",
    "accenture", "capgemini", "hexaware", "mindteck",
    "quess", "teamlease", "manpower", "randstad", "adecco",
    "viraaj", "lmj innovations", "golden opportunities", "whitefield careers",
    "uplers",
    "jforce",
    "hireginie",
    "canorous",
    "techs to suit",
    "manuscriptpedia",        # content mill, not tech
    "iConsultera",
 
    # Body shops / consulting farms already in your list but adding variants
    "ascendion",              # appeared 3x in batch 12 — IT staffing
    "bristlecone",            
]
BLACKLIST_KEYWORDS = [
    "1 week", "2 week", "short term contract", "staffing",
    "body shop", "c2h", "contract to hire",
    "prompt engineer",        # catches "Prompt Engineer" titles — too junior/wrong fit
    "prompt engineering",
    "senior staff",           # Sr. Staff / Staff+ roles require 7-10+ yrs
    "principal engineer",
    "staff engineer",
    "distinguished engineer",
]

# ── Scoring weights ────────────────────────────────────────────────────────
WEIGHT_FIT   = 0.5   # technical skill match
WEIGHT_COMP  = 0.3   # estimated compensation
WEIGHT_BRAND = 0.2   # company quality / growth stage

# ── Paths ──────────────────────────────────────────────────────────────────
RAW_CSV      = "output/jobs_raw.csv"
FILTERED_CSV = "output/jobs_filtered.csv"
SCORED_CSV   = "output/jobs_scored.csv"
DB_PATH      = "output/tracker.db"
COVER_DIR    = "output/cover_letters"

# ── Gemini CLI ─────────────────────────────────────────────────────────────
GEMINI_CMD = r"C:/Program Files/nodejs/gemini.cmd"
BATCH_SIZE   = 8         # JDs per Gemini call (stay under context limits)

LINKEDIN_EMAIL    = "sanchitpandey72@gmail.com"
LINKEDIN_PASSWORD = os.environ.get("LINKEDIN_PASS")
 
INDEED_EMAIL      = "your@email.com"
INDEED_PASSWORD   = "your_indeed_password"
 
# ── Resume path (PDF recommended) ──────────────────────────────────────────────
RESUME_PATH = "resume/resume.pdf"   # create a /resume folder and place your PDF here
 
# ── Apply rate limiting ─────────────────────────────────────────────────────────
AUTO_APPLY_DELAY    = (8, 20)    # random seconds to wait between applications
MAX_APPLIES_PER_RUN = 25         # safety cap per session
 
# ── Review server ───────────────────────────────────────────────────────────────
REVIEW_SERVER_PORT = 5055
MIN_REVIEW_SCORE   = 55