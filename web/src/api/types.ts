export interface User {
  id: string
  email: string
  tier: 'free' | 'paid'
  is_active: boolean
  is_verified: boolean
  created_at: string
}

export interface Profile {
  id: string
  user_id: string
  // Personal
  name: string | null
  email: string | null
  phone: string | null
  linkedin_url: string | null
  github_url: string | null
  portfolio_url: string | null
  location_current: string | null
  // Availability
  notice_period: string | null
  current_ctc: string | null
  expected_ctc: string | null
  expected_ctc_min_lpa: string | null
  start_date: string | null
  // Education
  degree: string | null
  college: string | null
  graduation_month_year: string | null
  graduation_year: string | null
  cgpa: string | null
  // Experience
  total_experience: string | null
  work_authorization: string | null
  willing_to_relocate: string | null
  willing_to_travel: string | null
  sponsorship_required: string | null
  // JSON blobs
  skills_json: Record<string, string> | null
  eeo_json: Record<string, string> | null
  short_answers_json: Record<string, string> | null
  // Preferences
  preferred_roles: string | null
  target_locations: string | null
  avoid_roles: string | null
  avoid_companies: string | null
  minimum_compensation: string | null
  must_have_preferences: string | null
  deal_breakers: string | null
  // Summary
  candidate_summary: string | null
  experience_highlights: string | null
  // Filtering
  blacklist_companies: string[] | null
  blacklist_keywords: string[] | null
  min_comp_lpa: number
  target_comp_lpa: number
  // Timestamps
  created_at: string
  updated_at: string
}

export type ApplicationStatus =
  | 'discovered'
  | 'enriched'
  | 'scored'
  | 'approved'
  | 'applying'
  | 'applied'
  | 'rejected'
  | 'failed'
  | 'skipped'
  | 'interview'
  | 'offer'

export interface Application {
  id: string
  user_id: string
  external_id: string | null
  company: string | null
  title: string | null
  location: string | null
  url: string | null
  description: string | null
  fit_score: number | null
  comp_est: string | null
  verdict: 'strong_yes' | 'yes' | 'maybe' | 'no' | null
  gaps: string[] | null
  status: ApplicationStatus
  source: string
  discovery_batch_id: string | null
  ats_type: string | null
  difficulty: string | null
  filled_fields_json: Record<string, unknown> | null
  cover_letter: string | null
  applied_at: string | null
  scored_model: string | null
  llm_tokens_used: number
  scored_at: string
  updated_at: string
}

export interface SearchPreference {
  id: string
  user_id: string
  keywords: string[] | null
  location: string
  experience_levels: string
  remote_filter: string
  time_range: string
  auto_apply_threshold: number
  max_daily_applications: number
  skip_companies: string[] | null
  skip_title_keywords: string[] | null
  created_at: string
  updated_at: string
}

export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface ApiError {
  detail: string
}
