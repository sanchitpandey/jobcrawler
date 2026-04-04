/**
 * ats-detector.ts
 *
 * Client-side port of api/services/ats_router.py → classify_job().
 * Regex patterns copied exactly from _RULES; order preserved (first match wins).
 */

export interface ATSMatch {
  platform: string;
  difficulty: "auto" | "hybrid" | "manual";
}

type Rule = [RegExp, string, "auto" | "hybrid" | "manual"];

// Translated directly from _RULES in ats_router.py.
// Python re.compile(pattern, re.I) → JS /pattern/i
const RULES: Rule[] = [
  // ── LinkedIn ────────────────────────────────────────────────────────────────
  [/linkedin\.com\/jobs\//i,  "linkedin", "auto"],
  [/linkedin\.com\/apply\//i, "linkedin", "auto"],

  // ── Indeed ──────────────────────────────────────────────────────────────────
  [/indeed\.com\//i,          "indeed", "auto"],
  [/indeed\.co\./i,           "indeed", "auto"],   // indeed.co.uk, indeed.co.in …

  // ── Greenhouse ──────────────────────────────────────────────────────────────
  [/(boards\.)?greenhouse\.io\//i, "greenhouse", "hybrid"],
  [/grnh\.se\//i,                  "greenhouse", "hybrid"],  // short-links

  // ── Lever ───────────────────────────────────────────────────────────────────
  [/(jobs\.)?lever\.co\//i,   "lever", "hybrid"],

  // ── Ashby ───────────────────────────────────────────────────────────────────
  [/ashbyhq\.com\//i,         "ashby", "hybrid"],
  [/jobs\.ashbyhq\.com\//i,   "ashby", "hybrid"],

  // ── Workday ─────────────────────────────────────────────────────────────────
  [/myworkdayjobs\.com\//i,          "workday", "manual"],
  [/workday\.com\//i,                "workday", "manual"],
  [/wd\d+\.myworkdayjobs\.com\//i,   "workday", "manual"],

  // ── iCIMS ───────────────────────────────────────────────────────────────────
  [/icims\.com\//i,           "icims", "manual"],
  [/careers\.icims\.com\//i,  "icims", "manual"],
];

/**
 * Classify a job-posting URL by ATS platform and automation difficulty.
 * Returns null when no rule matches (unknown / non-job page).
 */
export function detectATS(url: string): ATSMatch | null {
  if (!url) return null;
  for (const [pattern, platform, difficulty] of RULES) {
    if (pattern.test(url)) return { platform, difficulty };
  }
  return null;
}
