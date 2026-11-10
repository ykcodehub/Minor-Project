export interface Provider {
  name: string;
  model: string;
  configured: boolean;
}
export type Language = "en" | "hi" | "hinglish";
export interface User {
  language?: Language;
  id: string;
  email: string;
  is_guest: boolean;
  guest: boolean;
  verified?: boolean;
  csrf_token: string;
  retention_days: number;
  preferred_provider?: string;
  authorized_providers?: string[] | null;
  providers: Provider[];
  settings?: Record<string, unknown>;
}
export interface Section {
  id: string;
  section_id?: string;
  text: string;
  page?: number | null;
  ordinal: number;
  heading?: string;
  locator?: Record<string, unknown>;
  locator_json?: Record<string, unknown>;
}
export interface Source {
  id: string;
  original_name: string;
  kind: string;
  captured_at: string;
  status: string;
  sha256: string;
  analysis_id?: string;
  analysis_status?: string;
  job_id?: string;
  job_state?: string;
  processing_error?: string | null;
  source_url?: string;
  sections?: Section[];
  metadata?: Record<string, unknown>;
  version?: string;
  coverage?: Record<string, unknown>;
  warnings?: string[];
}
export interface Citation {
  source_id: string;
  section_id: string;
  quote: string;
  page?: number | null;
  start: number;
  end: number;
  match_status: string;
  clause_label?: string;
}
export interface Finding {
  finding_id: string;
  category: string;
  statement: string;
  rationale: string;
  support_status: string;
  qualifications: string[];
  verification?: Record<string, unknown>;
  citations: Citation[];
  model?: string;
  provider?: string;
}
export interface Job {
  id: string;
  state: string;
  stage: string;
  progress: Record<string, unknown>;
  error?: string;
  error_code?: string;
  result?: Record<string, unknown>;
}
export interface Analysis {
  overview?: {
    summary: string;
    category_counts: Record<string, number>;
    document_cues: { label: string; method: string }[];
    explicit_party_labels: { text: string; method: string }[];
  };
  analysis_id: string;
  status: string;
  job_id: string;
  source_ids: string[];
  sources: Source[];
  coverage: Record<string, unknown>;
  findings_count: number;
  limitations: string[];
  model_calls?: Record<string, unknown>[];
}
export interface Candidate {
  url: string;
  title?: string;
  type?: string;
  kind?: string;
  category?: string;
  status: string;
  discovered_from?: string;
  captured_at?: string;
  reason?: string;
  error?: string;
}
export interface Discovery {
  candidates: Candidate[];
  missing_categories?: string[];
  missing?: string[];
  warnings?: string[];
  url?: string;
  state?: string;
  status?: string;
  job_id?: string;
}
export const active = (state?: string) =>
  !!state &&
  ![
    "COMPLETED",
    "PARTIAL",
    "PARTIAL_COMPLETION",
    "FAILED",
    "CANCELLED",
    "CANCELED",
  ].includes(state);
