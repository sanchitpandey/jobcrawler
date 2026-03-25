# Apply Profile
Fill in this single file with your own background, target roles, preferences, and application details. The pipeline uses it for scoring, cover letters, and form filling.
Notes:
- Keep the field names unchanged.
- Replace the example values with your own truthful information.
- Indented lines under a field are treated as part of that answer.
- You can leave optional fields blank if they do not apply.
## Personal
name: "Sanchit Pandey"
email: "sanchitpandey72@gmail.com"
phone: "+91-8527104455"
linkedin: "https://www.linkedin.com/in/sanchitpandey"
github: "https://github.com/sanchitpandey"
portfolio: "https://sanchitpandey.github.io/"
location_current: "Hyderabad, India"
## Availability And Compensation
notice_period: "Available immediately"
current_ctc: "0"
expected_ctc: "Enter your expected compensation range"
expected_ctc_min_lpa: "0"
start_date: "2026-05"
## Education
degree: "B.E., Electronics & Instrumentation Engineering"
college: "Birla Institute of Technology and Science (BITS), Pilani"
graduation_month_year: "May 2026"
graduation_year: "2026"
cgpa: "7.15"
## Experience And Authorization
total_experience: "~1 year internship experience (no full-time); graduating May 2026"
work_authorization: "Authorized to work in India without sponsorship: Yes"
willing_to_relocate: "Yes — Bengaluru, Hyderabad, Pune, Mumbai, Delhi NCR"
willing_to_travel: "Yes"
sponsorship_required: "No"
## Technical Experience
python_years: "3"
ml_years: "2"
llm_nlp_rag_years: "2"
pytorch_years: "2"
huggingface_years: "1"
sql_years: "1"
docker_years: "1"
react_years: "1"
## Diversity Or EEO
gender: "male"
ethnicity: "asian"
veteran_status: "no"
disability: "no"
## Job Search Preferences
preferred_roles: >
  Machine Learning Engineer, Applied Scientist, NLP Engineer, LLM Engineer,
  AI/ML Engineer, Research Engineer, Backend Engineer (Go / Python).
target_locations: >
  Bengaluru, Hyderabad, Pune, Delhi NCR, Mumbai, remote within India.
avoid_roles: >
  Pure prompt engineering, QA automation, support roles, sales engineering,
  data-entry or pure BI/reporting analyst roles.
avoid_companies: >
  Staffing agencies, unpaid internships, companies requiring immediate 1+ year
  bond/service agreement.
minimum_compensation: >
  Open to discussion for the right role; targeting market-rate for a 2026
  fresher with published research and production ML internship experience.
## Candidate Summary
candidate_summary: >
  Final-year B.E. (Electronics & Instrumentation) student at BITS Pilani with
  a strong focus on LLMs, NLP, and production ML systems. First-author paper
  under review at ACL ARR 2026 studying RAG utilization failure in sub-7B
  models. Hands-on experience building Dual-PPO RLHF systems by modifying TRL
  internals, hybrid retrieval pipelines (FAISS + BM25 + LightGBM reranking),
  and full-stack backend services in Go and FastAPI. Qualified ZCO and INOI
  (2020). Seeking full-time roles in ML/AI engineering or applied NLP.
experience_highlights: >
  - First-author ACL ARR 2026 submission: empirical study of RAG utilization
    failure across 5 models (360M–8B), classifying 2,588 oracle failures into
    6 error categories; introduced parametric knowledge split methodology.
  - Genpact AI/ML Intern: adapted Absolute Zero Reasoner to NLP tasks via
    LLM-as-a-judge; achieved ~30% relative improvement in 8 self-play
    iterations; redesigned to Dual-PPO with custom reward injection by
    modifying TRL internals.
  - Busy InfoTech (Indiamart) Software Intern: delivered Go + PostgreSQL
    backend endpoints; reduced API latency by 15%.
  - IndiaAI MSME project: end-to-end multimodal matching engine with hybrid
    retrieval (FAISS + BM25), Whisper ASR, DeepSeek OCR, and LightGBM
    LambdaRank re-ranking for the Ministry of MSME's TEAM initiative.
  - Hospital Visitor Management System: full-stack (Node.js, React, MongoDB,
    Firebase); reduced check-in time by 70% and errors by 90%.
  - Deepfake detection pipeline: CNN + ResNet50 + ELA preprocessing; 80.12%
    test accuracy.
  - IRCS Data Analyst: Python ETL pipelines over 7 years of financial data;
    improved allocation efficiency by 25%.
must_have_preferences: >
  Roles involving LLMs, RAG systems, RLHF/alignment, NLP model training, or
  production ML infrastructure. Ideally at a company building AI-native
  products or conducting applied research. Technologies: Python, PyTorch,
  HuggingFace, FastAPI, or Go backends. Fresher/junior to mid-level seniority.
deal_breakers: >
  Roles with no ML/AI component, pure frontend or mobile development, manual
  QA, sales or support engineering, unpaid positions, mandatory relocation
  outside India without compensation, or roles requiring 2+ years of full-time
  experience as a hard filter.
## Short Answers
why_ml_engineering: >
  I have been drawn to the intersection of research and engineering since
  working on my RAG utilization study, where I found that even well-retrieved
  context fails to help small models generate correct answers. That gap between
  what a model retrieves and what it can actually use is a real-world problem
  with immediate product impact. ML engineering lets me close that gap —
  building systems that are not just theoretically sound but reliably useful in
  production.
describe_challenging_project: >
  The most technically demanding project was adapting the Absolute Zero
  Reasoner for NLP tasks at Genpact. AZR was designed for code with
  deterministic correctness checks; replacing that with an LLM-as-a-judge for
  sarcasm detection and NER required careful reward shaping to avoid reward
  hacking. I had to modify TRL's PPO internals to inject custom rewards into a
  Dual-PPO setup, track collapse signals across iterations, and validate that
  the ~30% relative improvement at iteration 8 was genuine and not an artifact
  of the judge's bias.
what_do_you_know_about_us: >
  [Fill in a company-specific answer when applying. Describe what the company
  builds, why their work is interesting to you, and how your background aligns
  with their mission.]
salary_expectation_justification: >
  As a 2026 fresher with a first-author publication, two ML internships, and
  production experience in RLHF and hybrid retrieval systems, I am targeting
  compensation in line with the market rate for AI/ML roles at companies of
  similar size and stage. I am flexible for the right role and growth
  opportunity.