import { randomUUID } from "node:crypto";
import { promises as fs } from "node:fs";
import {
  hashFileContents,
  loadMemoryItem,
  listAllMemoryItems,
  listMemoryFiles,
  touchMemoryFiles,
  writeMemoryItem
} from "./store.js";
import type { MemoryItem, MemoryKind, RubricProxy } from "./types.js";

export interface CaptureCandidateInput {
  rawObservation: string;
  source: string;
  session: string;
  project: string;
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

export interface IngestSessionInput {
  filePath: string;
  session: string;
  project: string;
}

export interface SummarizeSessionInput {
  filePath: string;
  outPath?: string;
}

export interface SessionTranscriptSummary {
  summaryPath: string;
  content: string;
  decisions: string[];
  todos: string[];
  evidence: string[];
  openQuestions: string[];
  notes: string[];
}

function now(): string {
  return new Date().toISOString();
}

function expiresInDays(days: number): string {
  return new Date(Date.now() + days * 24 * 60 * 60 * 1000).toISOString();
}

export function inferKind(content: string): MemoryKind {
  const text = content.toLowerCase();
  if (text.includes("preference") || text.includes("prefrence") || text.includes("user")) {
    return "personal";
  }
  if (text.includes("evidence") || text.includes("test") || text.includes("citation")) {
    return "evidence";
  }
  if (text.includes("session") || text.includes("scratchpad")) {
    return "session";
  }
  return "project";
}

export async function captureCandidate(input: CaptureCandidateInput): Promise<MemoryItem> {
  const kind = inferKind(input.rawObservation);
  return {
    id: `candidate:${randomUUID()}`,
    kind,
    scope: `${input.project}:${input.session}`,
    source: input.source,
    confidence: 0.5,
    confidence_rationale: "single-session capture",
    status: "candidate",
    content: input.rawObservation,
    created_at: now(),
    updated_at: now(),
    verified_at: undefined,
    retrieval_count: 0,
    cross_project_applicable: kind === "evidence",
    expires_at: kind === "session" ? expiresInDays(7) : undefined,
    semantic_tags: [],
    provenance: [{ type: "session", ref: input.session }]
  };
}

export async function classifyCandidate(candidate: MemoryItem): Promise<{ kind: MemoryKind }> {
  return { kind: candidate.kind };
}

export async function verifyCandidate(
  candidate: MemoryItem,
  evidence: string[]
): Promise<{ status: "verified" | "rejected" | "needs_more_evidence"; candidateId: string; evidenceCount: number }> {
  if (candidate.kind === "session") {
    return { status: "rejected", candidateId: candidate.id, evidenceCount: evidence.length };
  }
  if (candidate.kind === "personal" && evidence.length < 2) {
    return { status: "needs_more_evidence", candidateId: candidate.id, evidenceCount: evidence.length };
  }
  const status = evidence.length > 0 ? "verified" : "needs_more_evidence";
  return { status, candidateId: candidate.id, evidenceCount: evidence.length };
}

export async function promoteItem(item: MemoryItem): Promise<{ path: string }> {
  if (!item.scope.trim()) {
    throw new Error("Cannot promote memory item without a scope.");
  }
  if (item.status !== "verified") {
    throw new Error(`Cannot promote memory item with status ${item.status}.`);
  }
  if (item.kind === "session") {
    throw new Error("Session items are ephemeral and cannot be promoted to durable storage.");
  }
  item = {
    ...item,
    verified_at: item.verified_at ?? now(),
    references: item.references ?? []
  };
  if (item.kind === "evidence" && !item.source_content_hash) {
    const sourceHash = await hashFileContents(item.source);
    if (!sourceHash) {
      throw new Error(`Evidence item requires an existing source file: ${item.source}`);
    }
    item = { ...item, source_content_hash: sourceHash };
  }
  const filePath = await writeMemoryItem(item);
  return { path: filePath };
}

export async function writeCandidateItem(item: MemoryItem): Promise<{ path: string }> {
  if (!item.scope.trim()) {
    throw new Error("Cannot write memory item without a scope.");
  }
  if (item.status === "verified" && item.kind !== "session") {
    throw new Error("Use promote for verified durable memory items.");
  }
  const filePath = await writeMemoryItem(item);
  return { path: filePath };
}

export async function ingestSessionFile(input: IngestSessionInput): Promise<{ path: string; item: MemoryItem }> {
  const content = (await fs.readFile(input.filePath, "utf8")).trim();
  const item: MemoryItem = {
    id: `session:${randomUUID()}`,
    kind: "session",
    scope: `${input.project}:${input.session}`,
    source: input.filePath,
    confidence: 0.6,
    confidence_rationale: "session file ingest",
    status: "candidate",
    content,
    created_at: now(),
    updated_at: now(),
    retrieval_count: 0,
    cross_project_applicable: false,
    expires_at: expiresInDays(7),
    semantic_tags: ["session-ingest"],
    provenance: [{ type: "file", ref: input.filePath }]
  };
  const { path } = await writeCandidateItem(item);
  return { path, item };
}

export async function summarizeSessionTranscript(input: SummarizeSessionInput): Promise<SessionTranscriptSummary> {
  const content = await fs.readFile(input.filePath, "utf8");
  const sections = extractSessionSections(content);
  const summaryPath =
    input.outPath ??
    `${input.filePath.replace(/\.[^/.]+$/, "")}-session-summary.md`;
  const markdown = renderSessionSummary(input.filePath, sections);
  await fs.writeFile(summaryPath, markdown, "utf8");
  return {
    summaryPath,
    content: markdown,
    ...sections
  };
}

function extractSessionSections(content: string): Omit<SessionTranscriptSummary, "summaryPath" | "content"> {
  const sections = {
    decisions: [] as string[],
    todos: [] as string[],
    evidence: [] as string[],
    openQuestions: [] as string[],
    notes: [] as string[]
  };
  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) {
      continue;
    }
    const match = line.match(/^(decision|decisions|todo|todos|task|evidence|source|open question|question|note|notes)\s*:\s*(.+)$/i);
    if (!match) {
      continue;
    }
    const label = match[1].toLowerCase();
    const value = match[2].trim();
    if (!value) {
      continue;
    }
    if (label === "decision" || label === "decisions") {
      sections.decisions.push(value);
    } else if (label === "todo" || label === "todos" || label === "task") {
      sections.todos.push(value);
    } else if (label === "evidence" || label === "source") {
      sections.evidence.push(value);
    } else if (label === "open question" || label === "question") {
      sections.openQuestions.push(value);
    } else {
      sections.notes.push(value);
    }
  }
  if (
    sections.decisions.length === 0 &&
    sections.todos.length === 0 &&
    sections.evidence.length === 0 &&
    sections.openQuestions.length === 0 &&
    sections.notes.length === 0
  ) {
    sections.notes.push("No explicit Decision/TODO/Evidence markers were found in this transcript.");
  }
  return sections;
}

function renderSessionSummary(
  sourcePath: string,
  sections: Omit<SessionTranscriptSummary, "summaryPath" | "content">
): string {
  const bullets = (items: string[]) => (items.length > 0 ? items.map((item) => `- ${item}`).join("\n") : "- none");
  return [
    "# Session Summary",
    "",
    "## Source",
    "",
    `- ${sourcePath}`,
    "",
    "## Decisions",
    "",
    bullets(sections.decisions),
    "",
    "## TODOs",
    "",
    bullets(sections.todos),
    "",
    "## Evidence",
    "",
    bullets(sections.evidence),
    "",
    "## Open Questions",
    "",
    bullets(sections.openQuestions),
    "",
    "## Notes",
    "",
    bullets(sections.notes),
    ""
  ].join("\n");
}

export async function buildContextPack(input: BuildContextPackInput): Promise<{ contextPack: string }> {
  const files = await listMemoryFiles(input.projectScope || input.sessionScope);
  await touchMemoryFiles(files);
  const memoryItems: MemoryItem[] = [];
  for (const filePath of files) {
    const item = await loadMemoryItem(filePath);
    if (!item || item.status === "rejected" || item.status === "outdated") {
      continue;
    }
    memoryItems.push(item);
  }
  const memoryLines = rankMemoryItems(memoryItems, input.taskContext)
    .slice(0, 3)
    .map((item) => {
      const excerpt = item.content.replace(/\s+/g, " ").trim().slice(0, 500);
      return `memory:${item.kind}:${item.scope}:${item.id}\n${excerpt}`;
    });
  return {
    contextPack: [
      `task=${input.taskContext}`,
      `session=${input.sessionScope}`,
      `project=${input.projectScope}`,
      `files=${files.join(",")}`,
      memoryLines.length > 0 ? `memories:\n${memoryLines.join("\n---\n")}` : "memories="
    ].join("\n")
  };
}

function rankMemoryItems(items: MemoryItem[], taskContext: string): MemoryItem[] {
  const terms = taskContext
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((term) => term.length >= 3);
  const score = (item: MemoryItem): number => {
    const text = `${item.id} ${item.kind} ${item.scope} ${item.content} ${(item.semantic_tags ?? []).join(" ")}`.toLowerCase();
    const termScore = terms.reduce((sum, term) => sum + (text.includes(term) ? 3 : 0), 0);
    const statusScore = item.status === "verified" ? 2 : 0;
    const kindScore = item.kind === "session" ? 1 : 0;
    return termScore + statusScore + kindScore + item.confidence;
  };
  return [...items].sort((left, right) => {
    const scoreDelta = score(right) - score(left);
    if (scoreDelta !== 0) {
      return scoreDelta;
    }
    return new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime();
  });
}

export async function evaluateRubric(input: EvaluateRubricInput): Promise<{
  proxyScores: RubricProxy[];
  criterionScores: Record<string, number>;
  recommendation: string;
  source: string;
  rubricDefinition: string;
}> {
  const grouped = new Map<string, number[]>();
  for (const proxy of input.proxies) {
    grouped.set(proxy.criterion, [...(grouped.get(proxy.criterion) ?? []), proxy.score]);
  }
  const criterionScores = Object.fromEntries(
    [...grouped.entries()].map(([criterion, scores]) => [
      criterion,
      scores.reduce((sum, score) => sum + score, 0) / scores.length
    ])
  );
  const average =
    input.proxies.length > 0 ? input.proxies.reduce((sum, proxy) => sum + proxy.score, 0) / input.proxies.length : 0;
  return {
    proxyScores: input.proxies,
    criterionScores,
    recommendation: average >= 4 ? "accept" : input.evidenceSet.length > 0 ? "needs review" : "needs evidence",
    source: input.candidateSystem,
    rubricDefinition: input.rubricDefinition
  };
}

function contradictionKey(content: string): { polarity: "positive" | "negative"; key: string } | null {
  const normalized = content.toLowerCase().replace(/[^a-z0-9\s]/g, " ").replace(/\s+/g, " ").trim();
  const negative = normalized.match(/\b(must|should)\s+not\s+(.+)/);
  if (negative) {
    return { polarity: "negative", key: `${negative[1]} ${negative[2]}`.trim() };
  }
  const positive = normalized.match(/\b(must|should)\s+(.+)/);
  if (positive) {
    return { polarity: "positive", key: `${positive[1]} ${positive[2]}`.trim() };
  }
  return null;
}

export async function cleanMemory(targetScope: string): Promise<{ markers: string[] }> {
  const files = await listMemoryFiles(targetScope);
  const markers: string[] = [];
  const allItems = await listAllMemoryItems();
  const idSet = new Set(allItems.map(({ item }) => item.id));
  const itemById = new Map(allItems.map(({ item }) => [item.id, item]));
  const scopeBuckets = new Map<string, MemoryItem[]>();
  for (const filePath of files) {
    const content = await hashFileContents(filePath);
    if (!content) {
      markers.push(`unreadable:${filePath}`);
    }
  }
  for (const { filePath, item } of allItems) {
    if (targetScope && !item.scope.includes(targetScope) && !filePath.includes(targetScope)) {
      continue;
    }
    const bucketKey = `${item.kind}:${item.scope}`;
    scopeBuckets.set(bucketKey, [...(scopeBuckets.get(bucketKey) ?? []), item]);
    if ((item.status === "verified" || item.status === "outdated") && !item.verified_at) {
      markers.push(`missing_verified_at:${filePath}`);
    }
    if (item.expires_at && new Date(item.expires_at).getTime() <= Date.now()) {
      markers.push(`expired:${filePath}`);
    }
    if ((item.kind === "evidence" || item.kind === "project") && (item.retrieval_count ?? 0) === 0) {
      markers.push(`never_retrieved:${filePath}`);
    }
    if (item.kind === "evidence" && item.source_content_hash) {
      const currentSourceHash = await hashFileContents(item.source);
      if (currentSourceHash && currentSourceHash !== item.source_content_hash) {
        markers.push(`source_drift:${filePath}`);
      }
    }
    for (const reference of item.references ?? []) {
      if (!idSet.has(reference)) {
        markers.push(`dangling_reference:${filePath}->${reference}`);
      }
    }
    if (item.kind === "evidence" && !item.source_content_hash) {
      markers.push(`missing_source_hash:${filePath}`);
    }
  }
  for (const [bucketKey, bucketItems] of scopeBuckets.entries()) {
    const byTag = new Map<string, MemoryItem[]>();
    for (const item of bucketItems) {
      for (const tag of item.semantic_tags ?? []) {
        byTag.set(tag, [...(byTag.get(tag) ?? []), item]);
      }
    }
    for (const [tag, items] of byTag.entries()) {
      const contents = new Set(items.map((item) => item.content));
      if (contents.size > 1) {
        markers.push(`semantic_conflict:${bucketKey}:${tag}`);
      }
      const byClaim = new Map<string, { positive: string[]; negative: string[] }>();
      for (const item of items) {
        const claim = contradictionKey(item.content);
        if (!claim) {
          continue;
        }
        const bucket = byClaim.get(claim.key) ?? { positive: [], negative: [] };
        bucket[claim.polarity].push(item.id);
        byClaim.set(claim.key, bucket);
      }
      for (const [claimKey, polarity] of byClaim.entries()) {
        if (polarity.positive.length > 0 && polarity.negative.length > 0) {
          markers.push(`direct_contradiction:${bucketKey}:${tag}:${claimKey}:${polarity.positive.join(",")}<>${polarity.negative.join(",")}`);
        }
      }
    }
  }
  for (const { item } of allItems) {
    const stack: string[] = [];
    const visit = (itemId: string): boolean => {
      if (stack.includes(itemId)) {
        markers.push(`circular_reference:${[...stack, itemId].join("->")}`);
        return true;
      }
      const current = itemById.get(itemId);
      if (!current) {
        return false;
      }
      stack.push(itemId);
      for (const reference of current.references ?? []) {
        if (visit(reference)) {
          return true;
        }
      }
      stack.pop();
      return false;
    };
    visit(item.id);
  }
  if (files.length === 0 && markers.length === 0) {
    markers.push("no matching items found");
  }
  return { markers: markers.length > 0 ? markers : files };
}
