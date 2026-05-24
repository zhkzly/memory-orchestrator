export type MemoryKind = "personal" | "project" | "evidence" | "session";
export type MemoryStatus = "candidate" | "verified" | "rejected" | "outdated";

export interface ProvenanceItem {
  type: "prompt" | "file" | "diff" | "correction" | "session";
  ref: string;
}

export interface MemoryItem {
  id: string;
  kind: MemoryKind;
  scope: string;
  source: string;
  confidence: number;
  confidence_rationale?: string;
  status: MemoryStatus;
  content: string;
  created_at: string;
  updated_at: string;
  verified_at?: string;
  source_content_hash?: string;
  retrieval_count?: number;
  last_retrieved_at?: string;
  cross_project_applicable?: boolean;
  references?: string[];
  expires_at?: string;
  semantic_tags?: string[];
  provenance: ProvenanceItem[];
}

export interface RubricProxy {
  id: string;
  criterion: string;
  target: string;
  evidence: Array<{
    ref: string;
    type: "file" | "prompt" | "diff" | "test" | "session";
  }>;
  score: number;
}
