import type { MemoryItem, MemoryKind, RubricProxy } from "./types.js";

export interface CaptureCandidateInput {
  rawObservation: string;
  source: string;
  session: string;
  project: string;
}

export interface ClassifyCandidateInput {
  candidate: MemoryItem;
}

export interface VerifyCandidateInput {
  candidate: MemoryItem;
  evidence: string[];
}

export interface PromoteItemInput {
  item: MemoryItem;
}

export interface BuildContextPackInput {
  taskContext: string;
  sessionScope: string;
  projectScope: string;
}

export interface EvaluateRubricInput {
  rubricDefinition: string;
  evidenceSet: string[];
  candidateSystem: string;
  proxies: RubricProxy[];
}

export interface CleanMemoryInput {
  targetScope: string;
}

export interface ToolResult<T> {
  ok: boolean;
  data?: T;
  message?: string;
}

export interface MemoryToolset {
  captureCandidate(input: CaptureCandidateInput): Promise<ToolResult<MemoryItem>>;
  classifyCandidate(input: ClassifyCandidateInput): Promise<ToolResult<{ kind: MemoryKind }>>;
  verifyCandidate(input: VerifyCandidateInput): Promise<ToolResult<{ status: "verified" | "rejected" | "needs_more_evidence" }>>;
  promoteItem(input: PromoteItemInput): Promise<ToolResult<{ path: string }>>;
  buildContextPack(input: BuildContextPackInput): Promise<ToolResult<{ contextPack: string }>>;
  evaluateRubric(input: EvaluateRubricInput): Promise<ToolResult<{ proxyScores: RubricProxy[]; criterionScores: Record<string, number>; recommendation: string }>>;
  cleanMemory(input: CleanMemoryInput): Promise<ToolResult<{ markers: string[] }>>;
}
