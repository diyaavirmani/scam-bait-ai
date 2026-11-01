export interface Ev {
  id: number | null;
  ts: string;
  case_id: string | null;
  channel: string;
  type: string;
  data: any;
}
export interface Case {
  id: string;
  channel: string;
  external_id: string;
  status: string;
  scam_type: string;
  verdict: string;
  summary: string;
  created_at: string;
  updated_at: string;
  turns?: number;
}
export interface Msg { id: number; case_id: string; role: 'scammer' | 'persona'; text: string; ts: string; }
export interface Intel { case_id?: string; kind: string; value: string; message_id?: number | null; first_seen?: string; source?: string | null; }
export interface Evidence { kind: string; path: string; sha256: string; created_at: string; }
export interface CaseData {
  case: Case;
  messages: Msg[];
  intel: Intel[];
  events: Ev[];
  evidence: Evidence[];
  partial: Record<string, string>;
}
export interface SharedId { field: string; value: string; case_count: number; }
export interface Network {
  network_id: string;
  case_ids: string[];
  shared: SharedId[];
  first_seen?: string;
  last_seen?: string;
  scam_types?: string[];
}
export interface Health {
  status: string;
  checks: {
    database: boolean;
    models: { ok: boolean; detail: string; models?: string[] };
    decisions: { available: boolean; reason: string };
  };
}
