export interface ApiField {
  name: string;
  label: string;
  type: string;
  options?: string[];
}

export interface FillRequest {
  fields: ApiField[];
  jobDescription: string;
}

export interface FillResponse {
  answers: Record<string, string>;
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
  | { type: "GET_AUTH_TOKEN" }
  | { type: "AUTH_TOKEN_RESULT"; payload: AuthToken | null }
  | { type: "CLEAR_AUTH_TOKEN" }
  | { type: "ERROR"; payload: { message: string } };

export type MessageType = Message["type"];
