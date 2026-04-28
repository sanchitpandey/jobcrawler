export interface DiscoveryConfig {
  keywords: string[];
  location: string;
  experienceLevels: string; // e.g. "2,3"
  remoteFilter: string;     // "" | "2" | "3"
  timeRange: string;        // e.g. "r86400"
}

export interface RawJob {
  linkedin_job_id: string;
  title: string;
  company: string;
  location: string;
  url: string;
  posted_text: string;
  is_easy_apply: boolean;
  applicant_count: string;
}

export interface DiscoveryStatus {
  phase: "discovering" | "filtering" | "enriching" | "scoring" | "complete" | "idle" | "error";
  progress?: number;
  total?: number;
  discovered?: number;
  filtered?: number;
  scored?: number;
  approved?: number;
  needsReview?: number;
  error?: string;
}

export interface ApiField {
  name: string;
  label: string;
  type: string;
  options?: string[];
  id?: string;
  error?: string;
}

export interface FillRequest {
  fields: ApiField[];
  company: string;
  jobTitle: string;
}

export interface AnswerItem {
  label: string;
  value: string;
  source: "pattern" | "cache" | "llm" | "manual_review";
  confidence: number;
  is_manual_review: boolean;
}

export interface FillResponse {
  answers: AnswerItem[];
}

export interface ScoreRequest {
  title: string;
  company: string;
  description: string;
  url: string;
}

export interface ScoreResponse {
  fit_score: number;
  verdict: string;
  comp_est: string | null;
  gaps: string[];
}

export interface AuthToken {
  access_token: string;
  refresh_token: string;
}

export interface TrackJobPayload {
  company: string;
  title: string;
  location: string;
  url: string;
  description: string;
  ats_type: string;
  difficulty: string;
  fit_score?: number;
  comp_est?: string;
  verdict?: string;
  gaps?: string[];
}

export interface TrackJobResponse {
  app_id: string;
}

export interface QueueItem {
  id: string;
  url: string;
  company: string;
  title: string;
  fit_score: number;
  ats_type: string;
}

export interface AutoApplyStatus {
  phase: "applying" | "paused" | "complete" | "stopped";
  current?: number;
  total?: number;
  applied?: number;
  skipped?: number;
  failed?: number;
  currentJob?: { company: string; title: string; score: number };
  stopReason?: string;
  lastError?: string;
}

export interface UpdateStatusPayload {
  app_id: string;
  status: string;
  filled_fields_json?: Record<string, string>;
  cover_letter?: string;
}

// Discriminated union for all chrome.runtime messages

export type Message =
  | { type: "LOGIN"; payload: { email: string; password: string } }
  | { type: "LOGIN_RESULT"; payload: AuthToken }
  | { type: "SCORE_JOB"; payload: ScoreRequest }
  | { type: "SCORE_JOB_RESULT"; payload: ScoreResponse }
  | { type: "ANSWER_FIELDS"; payload: FillRequest }
  | { type: "ANSWER_FIELDS_RESULT"; payload: FillResponse }
  | { type: "GENERATE_COVER"; payload: { jobDescription: string } }
  | { type: "GENERATE_COVER_RESULT"; payload: { cover_letter: string } }
  | { type: "TRACK_JOB"; payload: TrackJobPayload }
  | { type: "TRACK_JOB_RESULT"; payload: TrackJobResponse }
  | { type: "UPDATE_STATUS"; payload: UpdateStatusPayload }
  | { type: "UPDATE_STATUS_RESULT"; payload: { ok: boolean } }
  | { type: "SHOW_SCORE"; payload: ScoreResponse }
  | { type: "GET_AUTH_TOKEN" }
  | { type: "AUTH_TOKEN_RESULT"; payload: AuthToken | null }
  | { type: "CLEAR_AUTH_TOKEN" }
  // Discovery flow messages
  | { type: "start_discovery"; payload: DiscoveryConfig }
  | { type: "stop_discovery" }
  | { type: "discovery_page_complete"; jobs: RawJob[]; searchUrl: string; rateLimited?: boolean }
  | { type: "discovery_progress"; count: number }
  | { type: "discovery_status"; phase: DiscoveryStatus["phase"]; progress?: number; total?: number; discovered?: number; filtered?: number; scored?: number; approved?: number; needsReview?: number; error?: string }
  // Auto-apply flow messages
  | { type: "start_auto_apply"; payload?: { maxJobs?: number } }
  | { type: "stop_auto_apply" }
  | { type: "auto_apply_progress"; phase: AutoApplyStatus["phase"]; current?: number; total?: number; applied?: number; skipped?: number; failed?: number; currentJob?: { company: string; title: string; score: number }; stopReason?: string; lastError?: string }
  | { type: "batch_job_complete"; success: boolean; skipped?: boolean; filledFields?: Record<string, string> }
  | { type: "batch_job_failed"; error: string }
  | { type: "ERROR"; payload: { message: string } };

export type MessageType = Message["type"];
