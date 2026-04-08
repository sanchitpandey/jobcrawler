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
  | { type: "ERROR"; payload: { message: string } };

export type MessageType = Message["type"];
