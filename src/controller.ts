import { cleanMemory, evaluateRubric } from "./core.js";
import { resolveConfig, resolveVaultRoot } from "./config.js";
import { listAllMemoryItems, saveMemoryItem } from "./store.js";
import { promises as fs } from "node:fs";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function value(args: string[], flag: string): string | undefined {
  const index = args.indexOf(flag);
  return index >= 0 ? args[index + 1] : undefined;
}

function dayDelta(timestamp?: string): number | null {
  if (!timestamp) {
    return null;
  }
  const value = new Date(timestamp).getTime();
  return Number.isFinite(value) ? Math.floor((Date.now() - value) / (24 * 60 * 60 * 1000)) : null;
}

function tokenSet(text: string): Set<string> {
  return new Set(
    text
      .toLowerCase()
      .split(/[^a-z0-9]+/)
      .filter((term) => term.length >= 4)
  );
}

function jaccard(left: string, right: string): number {
  const leftTerms = tokenSet(left);
  const rightTerms = tokenSet(right);
  if (leftTerms.size === 0 || rightTerms.size === 0) {
    return 0;
  }
  let intersection = 0;
  for (const term of leftTerms) {
    if (rightTerms.has(term)) {
      intersection += 1;
    }
  }
  return intersection / new Set([...leftTerms, ...rightTerms]).size;
}

interface ControllerPolicy {
  source: string;
  staleDays: number;
  expiringSoonDays: number;
  duplicateThreshold: number;
  ttlDays: Record<string, number>;
  lengthBudgets: Record<string, number>;
  fileLengthBudgets: Record<string, number>;
  model?: {
    provider?: string;
    name?: string;
  };
}

type ControllerReviewItem = {
  type: "reference" | "source" | "rubric" | "budget" | "stale" | "decay" | "integrity" | "retrieval";
  target: string;
  reason: string;
  action: "inspect" | "review";
};

function defaultControllerPolicy(source = "default"): ControllerPolicy {
  return {
    source,
    staleDays: 30,
    expiringSoonDays: 7,
    duplicateThreshold: 0.72,
    ttlDays: {
      personal: 3650,
      project: 365,
      evidence: 1825,
      session: 7
    },
    lengthBudgets: {
      personal: 12000,
      project: 16000,
      evidence: 20000,
      session: 8000
    },
    fileLengthBudgets: {
      people: 20000,
      projects: 24000,
      notes: 20000,
      sessions: 12000
    }
  };
}

function vaultControllerPolicyPath(vaultRoot: string): string {
  return path.join(vaultRoot, "agent", "controller-policy.json");
}

function policyForWrite(policy: ControllerPolicy): Omit<ControllerPolicy, "source"> {
  const { source: _source, ...rest } = policy;
  return rest;
}

async function listMarkdownFiles(root: string): Promise<string[]> {
  const output: string[] = [];
  async function visit(dirPath: string): Promise<void> {
    let entries;
    try {
      entries = await fs.readdir(dirPath, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      const fullPath = path.join(dirPath, entry.name);
      const relativePath = path.relative(root, fullPath);
      const firstSegment = relativePath.split(path.sep)[0];
      if (["agent", "reports", ".git", "node_modules"].includes(firstSegment)) {
        continue;
      }
      if (entry.isDirectory()) {
        await visit(fullPath);
      } else if (entry.isFile() && fullPath.endsWith(".md")) {
        output.push(fullPath);
      }
    }
  }
  await visit(root);
  return output;
}

function fileBudgetKey(vaultRoot: string, filePath: string): string {
  const relativePath = path.relative(vaultRoot, filePath);
  return relativePath.split(path.sep)[0] || "root";
}

async function readControllerPolicyFile(policyPath: string): Promise<ControllerPolicy> {
  const defaults = defaultControllerPolicy(path.resolve(policyPath));
  const policy = JSON.parse(await fs.readFile(policyPath, "utf8")) as Partial<ControllerPolicy>;
  return {
    ...defaults,
    ...policy,
    source: path.resolve(policyPath),
    ttlDays: {
      ...defaults.ttlDays,
      ...(policy.ttlDays ?? {})
    },
    lengthBudgets: {
      ...defaults.lengthBudgets,
      ...(policy.lengthBudgets ?? {})
    },
    fileLengthBudgets: {
      ...defaults.fileLengthBudgets,
      ...(policy.fileLengthBudgets ?? {})
    }
  };
}

async function loadControllerPolicy(args: string[], vaultRoot: string): Promise<ControllerPolicy> {
  const policyPath = value(args, "--policy");
  if (policyPath) {
    return readControllerPolicyFile(policyPath);
  }
  const vaultPolicyPath = vaultControllerPolicyPath(vaultRoot);
  try {
    await fs.access(vaultPolicyPath);
    return readControllerPolicyFile(vaultPolicyPath);
  } catch {
    return defaultControllerPolicy();
  }
}

export async function runControllerPolicy(args: string[]): Promise<{ path: string; created: true; policy: ControllerPolicy } | ControllerPolicy> {
  const config = await resolveConfig(process.cwd());
  const vaultRoot = resolveVaultRoot(config);
  const policyPath = vaultControllerPolicyPath(vaultRoot);
  const subcommand = args[0] ?? "show";
  if (subcommand === "init") {
    const policy = {
      ...defaultControllerPolicy(policyPath),
      model: {
        provider: value(args, "--model-provider") ?? "none",
        name: value(args, "--model-name") ?? "deterministic-only"
      }
    };
    try {
      await fs.access(policyPath);
      if (!args.includes("--force")) {
        throw new Error(`controller policy already exists at ${policyPath}; pass --force to overwrite.`);
      }
    } catch (error) {
      if (error instanceof Error && error.message.includes("already exists")) {
        throw error;
      }
    }
    await fs.mkdir(path.dirname(policyPath), { recursive: true });
    await fs.writeFile(policyPath, `${JSON.stringify(policyForWrite(policy), null, 2)}\n`, "utf8");
    return { path: policyPath, created: true, policy };
  }
  if (subcommand !== "show") {
    throw new Error("controller-policy requires init or show.");
  }
  return loadControllerPolicy([], vaultRoot);
}

async function scoreStructure(): Promise<{
  candidate: { name: string; scope: string; version: string };
  overall_score: number;
  criterionScores: Record<string, number>;
  recommendation: string;
}> {
  const rubric = JSON.parse(await readFile(path.join(packageRoot, "evaluation/structure-rubric.json"), "utf8"));
  const evidence = JSON.parse(await readFile(path.join(packageRoot, "evaluation/structure-evidence.json"), "utf8"));
  const result = await evaluateRubric({
    proxies: rubric.proxies,
    rubricDefinition: JSON.stringify(rubric, null, 2),
    evidenceSet: evidence.items,
    candidateSystem: rubric.candidate.name
  });
  return {
    candidate: rubric.candidate,
    overall_score:
      Object.values(result.criterionScores).reduce((sum, score) => sum + score, 0) /
      Math.max(Object.values(result.criterionScores).length, 1),
    criterionScores: result.criterionScores,
    recommendation: result.recommendation
  };
}

async function writeControllerReport(input: Awaited<ReturnType<typeof runController>>): Promise<string> {
  const reportsDir = path.join(input.vaultRoot, "reports");
  await fs.mkdir(reportsDir, { recursive: true });
  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  const reportPath = path.join(reportsDir, `controller-vault-${timestamp}.md`);
  const bullets = (items: string[]) => (items.length > 0 ? items.map((item) => `- ${item}`).join("\n") : "- none");
  await fs.writeFile(
    reportPath,
    [
      "# Vault Controller Report",
      "",
      "## Scope",
      "",
      `- vaultRoot: ${input.vaultRoot}`,
      `- mode: ${input.mode}`,
      `- trigger: ${input.trigger}`,
      `- policy: ${input.policy.source}`,
      input.policy.model?.name ? `- model: ${input.policy.model.name}` : "- model: none",
      "",
      "## Counts",
      "",
      `- items: ${input.counts.items}`,
      `- files: ${input.counts.files}`,
      "",
      "## Applied",
      "",
      bullets(input.applied.expiredSessionItems),
      "",
      "## Cleanup",
      "",
      bullets(input.cleanup.markers),
      "",
      "## Time",
      "",
      bullets(input.time.expired),
      "",
      "### TTL Breaches",
      "",
      bullets(input.time.ttlBreaches),
      "",
      "## Reinforcement",
      "",
      "### Reinforce",
      "",
      bullets(input.reinforcement.reinforce),
      "",
      "### Decay",
      "",
      bullets(input.reinforcement.decay),
      "",
      "## Budgets",
      "",
      bullets(input.budgets.oversized),
      "",
      "## Similarity",
      "",
      bullets(input.similarity.nearDuplicates.map((item) => `${item.left} <-> ${item.right} score=${item.score}`)),
      "",
      "## Recommendations",
      "",
      "### Keep",
      "",
      bullets(input.recommendations.keep),
      "",
      "### Decay",
      "",
      bullets(input.recommendations.decay),
      "",
      "### Consolidate",
      "",
      bullets(input.recommendations.consolidate),
      "",
      "### Review",
      "",
      bullets(input.recommendations.review),
      "",
      "### Expire",
      "",
      bullets(input.recommendations.expire),
      "",
      "## Structure",
      "",
      `- score: ${input.structure.overall_score}`,
      `- recommendation: ${input.structure.recommendation}`,
      "",
      "## Feedback",
      "",
      `- deterministicScore: ${input.feedback.deterministicScore}`,
      `- model: ${input.feedback.model.provider ?? "none"}:${input.feedback.model.name ?? "none"}`,
      "",
      "### Review Prompt",
      "",
      input.feedback.reviewPrompt,
      "",
      "## Next Actions",
      "",
      bullets(input.nextActions),
      ""
    ].join("\n"),
    "utf8"
  );
  return reportPath;
}

async function writeControllerReviewArtifact(input: {
  vaultRoot: string;
  feedback: { reviewPrompt: string };
  recommendations: { consolidate: string[]; review: string[]; decay: string[]; expire: string[] };
  consolidationCandidates: Array<{ left: string; right?: string; score?: number; reason: string; action: "review-merge" }>;
  reviewItems: ControllerReviewItem[];
}): Promise<string> {
  const reportsDir = path.join(input.vaultRoot, "reports");
  await fs.mkdir(reportsDir, { recursive: true });
  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  const artifactPath = path.join(reportsDir, `controller-review-${timestamp}.md`);
  const bullets = (items: string[]) => (items.length > 0 ? items.map((item) => `- ${item}`).join("\n") : "- none");
  await fs.writeFile(
    artifactPath,
    [
      "# Memory Controller Review Artifact",
      "",
      "## Safety Boundary",
      "",
      "- Do not rewrite durable memory automatically.",
      "- Treat this artifact as a review input, not an execution plan.",
      "- LLM Wiki remains an external knowledge source.",
      "",
      "## Feedback Prompt",
      "",
      input.feedback.reviewPrompt,
      "",
      "## Consolidate",
      "",
      bullets(input.recommendations.consolidate),
      "",
      "## Consolidation Candidates",
      "",
      bullets(
        input.consolidationCandidates.map((candidate) =>
          `${candidate.left}${candidate.right ? ` <-> ${candidate.right}` : ""} reason=${candidate.reason}${
            candidate.score !== undefined ? ` score=${candidate.score}` : ""
          } action=${candidate.action}`
        )
      ),
      "",
      "## Review",
      "",
      bullets(input.recommendations.review),
      "",
      "## Review Items",
      "",
      bullets(input.reviewItems.map((item) => `${item.type}:${item.target} reason=${item.reason} action=${item.action}`)),
      "",
      "## Decay",
      "",
      bullets(input.recommendations.decay),
      "",
      "## Expire",
      "",
      bullets(input.recommendations.expire),
      ""
    ].join("\n"),
    "utf8"
  );
  return artifactPath;
}

async function appendControllerFeedback(input: Awaited<ReturnType<typeof runController>>): Promise<string> {
  const feedbackPath = path.join(input.vaultRoot, "agent", "controller-feedback.jsonl");
  await fs.mkdir(path.dirname(feedbackPath), { recursive: true });
  const recommendationCounts = Object.fromEntries(
    Object.entries(input.recommendations).map(([key, value]) => [key, value.length])
  );
  const entry = {
    timestamp: new Date().toISOString(),
    trigger: input.trigger,
    mode: input.mode,
    policy: input.policy.source,
    deterministicScore: input.feedback.deterministicScore,
    structureScore: input.structure.overall_score,
    items: input.counts.items,
    recommendations: recommendationCounts,
    reportPath: input.reportPath,
    reviewArtifacts: input.reviewArtifacts
  };
  await fs.appendFile(feedbackPath, `${JSON.stringify(entry)}\n`, "utf8");
  return feedbackPath;
}

async function appendControllerReinforcement(input: Awaited<ReturnType<typeof runController>>): Promise<string> {
  const reinforcementPath = path.join(input.vaultRoot, "agent", "controller-reinforcement.jsonl");
  await fs.mkdir(path.dirname(reinforcementPath), { recursive: true });
  const entry = {
    timestamp: new Date().toISOString(),
    trigger: input.trigger,
    policy: input.policy.source,
    reinforce: input.reinforcement.reinforce,
    decay: input.reinforcement.decay,
    action: "review-reinforce",
    safety: "review-only"
  };
  await fs.appendFile(reinforcementPath, `${JSON.stringify(entry)}\n`, "utf8");
  return reinforcementPath;
}

type ControllerFeedbackEntry = {
  timestamp?: string;
  trigger?: string;
  mode?: string;
  policy?: string;
  deterministicScore?: number;
  structureScore?: number;
  items?: number;
  recommendations?: Record<string, number>;
  reportPath?: string;
  reviewArtifacts?: string[];
};

type ControllerReinforcementEntry = {
  timestamp?: string;
  trigger?: string;
  policy?: string;
  reinforce?: string[];
  decay?: string[];
  action?: string;
  safety?: string;
};

type ControllerExternalReviewEntry = {
  timestamp?: string;
  reviewer?: string;
  source?: string;
  sourceFile?: string;
  decision?: string;
  confidence?: number;
  findings?: string[];
  actions?: string[];
  safety?: string;
};

function average(values: number[]): number {
  if (values.length === 0) {
    return 0;
  }
  return Number((values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(3));
}

async function readJsonl<T>(filePath: string): Promise<T[]> {
  let raw = "";
  try {
    raw = await fs.readFile(filePath, "utf8");
  } catch {
    return [];
  }
  return raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line) as T);
}

function numericArg(args: string[], flag: string, fallback: number): number {
  const raw = value(args, flag);
  if (!raw) {
    return fallback;
  }
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export async function readControllerFeedback(args: string[]): Promise<{
  path: string;
  count: number;
  entries: ControllerFeedbackEntry[];
  latest: ControllerFeedbackEntry;
  averageDeterministicScore: number;
  averageStructureScore: number;
  trend: { deterministicScoreDelta: number; structureScoreDelta: number };
  alerts: string[];
}> {
  const config = await resolveConfig(process.cwd());
  const vaultRoot = resolveVaultRoot(config);
  const feedbackPath = path.join(vaultRoot, "agent", "controller-feedback.jsonl");
  const limit = Math.max(1, Math.floor(numericArg(args, "--limit", 20)));
  const minScore = numericArg(args, "--min-score", 0);
  const allEntries = await readJsonl<ControllerFeedbackEntry>(feedbackPath);
  const entries = allEntries.slice(-limit);
  const latest = entries.at(-1) ?? {};
  const first = entries[0] ?? {};
  const deterministicScores = entries
    .map((entry) => entry.deterministicScore)
    .filter((score): score is number => typeof score === "number");
  const structureScores = entries
    .map((entry) => entry.structureScore)
    .filter((score): score is number => typeof score === "number");
  const latestDeterministic = latest.deterministicScore ?? 0;
  const latestStructure = latest.structureScore ?? 0;
  const alerts: string[] = [];
  if (latest.deterministicScore !== undefined && latest.deterministicScore < minScore) {
    alerts.push(`below_min_score:${latest.deterministicScore}/${minScore}`);
  }
  if (entries.length === 0) {
    alerts.push("no_feedback_history");
  }
  return {
    path: feedbackPath,
    count: allEntries.length,
    entries,
    latest,
    averageDeterministicScore: average(deterministicScores),
    averageStructureScore: average(structureScores),
    trend: {
      deterministicScoreDelta: Number((latestDeterministic - (first.deterministicScore ?? latestDeterministic)).toFixed(3)),
      structureScoreDelta: Number((latestStructure - (first.structureScore ?? latestStructure)).toFixed(3))
    },
    alerts
  };
}

async function writeControllerReflectionReport(input: {
  vaultRoot: string;
  feedback: Awaited<ReturnType<typeof readControllerFeedback>>;
  reinforcement: { path: string; count: number; entries: ControllerReinforcementEntry[]; latest: ControllerReinforcementEntry };
  reflectionPrompt: string;
  reviewQuestions: string[];
}): Promise<string> {
  const reportsDir = path.join(input.vaultRoot, "reports");
  await fs.mkdir(reportsDir, { recursive: true });
  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  const reportPath = path.join(reportsDir, `controller-reflection-${timestamp}.md`);
  await fs.writeFile(
    reportPath,
    [
      "# Memory Controller Reflection",
      "",
      "## Feedback",
      "",
      `- count: ${input.feedback.count}`,
      `- averageDeterministicScore: ${input.feedback.averageDeterministicScore}`,
      `- deterministicScoreDelta: ${input.feedback.trend.deterministicScoreDelta}`,
      "",
      "## Reinforcement",
      "",
      `- count: ${input.reinforcement.count}`,
      `- latest reinforce: ${(input.reinforcement.latest.reinforce ?? []).length}`,
      `- latest decay: ${(input.reinforcement.latest.decay ?? []).length}`,
      "",
      "## Review Questions",
      "",
      input.reviewQuestions.map((question) => `- ${question}`).join("\n"),
      "",
      "## Reflection Prompt",
      "",
      input.reflectionPrompt,
      ""
    ].join("\n"),
    "utf8"
  );
  return reportPath;
}

export async function buildControllerReflection(args: string[]): Promise<{
  vaultRoot: string;
  feedback: Awaited<ReturnType<typeof readControllerFeedback>>;
  reinforcement: { path: string; count: number; entries: ControllerReinforcementEntry[]; latest: ControllerReinforcementEntry };
  reviewQuestions: string[];
  reflectionPrompt: string;
  reportPath?: string;
}> {
  const config = await resolveConfig(process.cwd());
  const vaultRoot = resolveVaultRoot(config);
  const limit = Math.max(1, Math.floor(numericArg(args, "--limit", 20)));
  const feedback = await readControllerFeedback(["--limit", String(limit)]);
  const reinforcementPath = path.join(vaultRoot, "agent", "controller-reinforcement.jsonl");
  const allReinforcement = await readJsonl<ControllerReinforcementEntry>(reinforcementPath);
  const reinforcementEntries = allReinforcement.slice(-limit);
  const latestReinforcement = reinforcementEntries.at(-1) ?? {};
  const reviewQuestions = [
    "Which reinforce candidates should be promoted into clearer durable memory, and which should remain unchanged?",
    "Which decay candidates are obsolete versus merely underused?",
    "Did deterministic score or structure score trend down enough to require policy changes?",
    "Which review artifacts need human confirmation before any rewrite?"
  ];
  const reflectionPrompt = [
    "# Memory Controller Reflection",
    "",
    "Review vault memory health using deterministic history first.",
    "",
    "## Feedback Trend",
    "",
    `- runs: ${feedback.count}`,
    `- average deterministic score: ${feedback.averageDeterministicScore}`,
    `- deterministic delta: ${feedback.trend.deterministicScoreDelta}`,
    `- alerts: ${feedback.alerts.join(", ") || "none"}`,
    "",
    "## Reinforcement",
    "",
    `- runs: ${allReinforcement.length}`,
    `- latest reinforce candidates: ${(latestReinforcement.reinforce ?? []).length}`,
    `- latest decay candidates: ${(latestReinforcement.decay ?? []).length}`,
    "",
    "## Safety",
    "",
    "- Treat this as review input only.",
    "- Do not rewrite durable memory automatically.",
    "- Keep LLM Wiki as an external knowledge source.",
    "",
    "## Questions",
    "",
    ...reviewQuestions.map((question) => `- ${question}`)
  ].join("\n");
  const result = {
    vaultRoot,
    feedback,
    reinforcement: {
      path: reinforcementPath,
      count: allReinforcement.length,
      entries: reinforcementEntries,
      latest: latestReinforcement
    },
    reviewQuestions,
    reflectionPrompt
  };
  const reportPath = args.includes("--write-report") ? await writeControllerReflectionReport(result) : undefined;
  return {
    ...result,
    ...(reportPath ? { reportPath } : {})
  };
}

export async function runControllerReview(args: string[]): Promise<
  | { path: string; entry: ControllerExternalReviewEntry }
  | { path: string; count: number; entries: ControllerExternalReviewEntry[]; latest: ControllerExternalReviewEntry }
> {
  const config = await resolveConfig(process.cwd());
  const vaultRoot = resolveVaultRoot(config);
  const reviewPath = path.join(vaultRoot, "agent", "controller-review-feedback.jsonl");
  const subcommand = args[0] ?? "show";
  if (subcommand === "ingest") {
    const filePath = value(args, "--file");
    if (!filePath) {
      throw new Error("controller-review ingest requires --file <path>.");
    }
    const review = JSON.parse(await fs.readFile(filePath, "utf8")) as ControllerExternalReviewEntry;
    const entry = {
      timestamp: new Date().toISOString(),
      ...review,
      reviewer: value(args, "--reviewer") ?? review.reviewer ?? "external-reviewer",
      sourceFile: path.resolve(filePath),
      safety: "record-only"
    };
    await fs.mkdir(path.dirname(reviewPath), { recursive: true });
    await fs.appendFile(reviewPath, `${JSON.stringify(entry)}\n`, "utf8");
    return { path: reviewPath, entry };
  }
  if (subcommand !== "show") {
    throw new Error("controller-review requires ingest or show.");
  }
  const limit = Math.max(1, Math.floor(numericArg(args, "--limit", 20)));
  const allEntries = await readJsonl<ControllerExternalReviewEntry>(reviewPath);
  const entries = allEntries.slice(-limit);
  return {
    path: reviewPath,
    count: allEntries.length,
    entries,
    latest: entries.at(-1) ?? {}
  };
}

export async function runController(args: string[]): Promise<{
  vaultRoot: string;
  scope: "vault";
  mode: "read-report-first" | "safe-apply";
  trigger: "scheduled" | "event" | "manual";
  policy: ControllerPolicy;
  counts: { items: number; files: number };
  cleanup: Awaited<ReturnType<typeof cleanMemory>>;
  time: { expired: string[]; expiringSoon: string[]; stale: string[]; ttlBreaches: string[] };
  reinforcement: { reinforce: string[]; decay: string[] };
  budgets: { limits: Record<string, number>; fileLimits: Record<string, number>; oversized: string[]; oversizedFiles: string[] };
  similarity: { threshold: number; nearDuplicates: Array<{ left: string; right: string; score: number }> };
  recommendations: { keep: string[]; decay: string[]; consolidate: string[]; review: string[]; expire: string[] };
  consolidationCandidates: Array<{ left: string; right?: string; score?: number; reason: string; action: "review-merge" }>;
  reviewItems: ControllerReviewItem[];
  applied: { expiredSessionItems: string[] };
  structure: Awaited<ReturnType<typeof scoreStructure>>;
  feedback: {
    deterministicScore: number;
    model: NonNullable<ControllerPolicy["model"]>;
    reviewPrompt: string;
  };
  reviewArtifacts: string[];
  feedbackLogPath?: string;
  reinforcementLogPath?: string;
  nextActions: string[];
  reportPath?: string;
}> {
  const config = await resolveConfig(process.cwd());
  const vaultRoot = resolveVaultRoot(config);
  const rawTrigger = value(args, "--trigger");
  const trigger = rawTrigger === "scheduled" || rawTrigger === "event" || rawTrigger === "manual" ? rawTrigger : "manual";
  const applySafe = args.includes("--apply-safe");
  const policy = await loadControllerPolicy(args, vaultRoot);
  const items = await listAllMemoryItems();
  const cleanup = await cleanMemory("");
  const expired: string[] = [];
  const expiringSoon: string[] = [];
  const stale: string[] = [];
  const ttlBreaches: string[] = [];
  const reinforce: string[] = [];
  const decay: string[] = [];
  const limits = policy.lengthBudgets;
  const fileLimits = policy.fileLengthBudgets;
  const oversized: string[] = [];
  const oversizedFiles: string[] = [];
  const keep: string[] = [];
  const review: string[] = [];
  const appliedExpiredSessionItems: string[] = [];
  for (const { filePath, item } of items) {
    const expiresAt = item.expires_at ? new Date(item.expires_at).getTime() : null;
    const ageDays = dayDelta(item.created_at) ?? dayDelta(item.updated_at) ?? 0;
    const ttlDays = policy.ttlDays[item.kind];
    const ttlBreached = Number.isFinite(ttlDays) && ttlDays > 0 && ageDays >= ttlDays;
    if (ttlBreached) {
      ttlBreaches.push(`${item.id}:${ageDays}/${ttlDays}:${filePath}`);
    }
    if (expiresAt !== null && expiresAt <= Date.now()) {
      expired.push(`${item.id}:${filePath}`);
      if (applySafe && item.kind === "session" && item.status !== "outdated") {
        await saveMemoryItem(filePath, {
          ...item,
          status: "outdated",
          updated_at: new Date().toISOString(),
          confidence_rationale: `${item.confidence_rationale ?? "none"}; controller safe expiry`
        });
        appliedExpiredSessionItems.push(`${item.id}:${filePath}`);
      }
    } else if (ttlBreached && applySafe && item.kind === "session" && item.status !== "outdated") {
      await saveMemoryItem(filePath, {
        ...item,
        status: "outdated",
        updated_at: new Date().toISOString(),
        confidence_rationale: `${item.confidence_rationale ?? "none"}; controller safe ttl expiry`
      });
      appliedExpiredSessionItems.push(`${item.id}:${filePath}`);
    } else if (expiresAt !== null && expiresAt - Date.now() <= policy.expiringSoonDays * 24 * 60 * 60 * 1000) {
      expiringSoon.push(`${item.id}:${filePath}`);
    }
    const lastRetrievedDays = dayDelta(item.last_retrieved_at);
    const updatedDays = dayDelta(item.updated_at);
    if (item.kind !== "session" && (lastRetrievedDays ?? updatedDays ?? 0) >= policy.staleDays) {
      stale.push(`${item.id}:${lastRetrievedDays ?? updatedDays}d`);
    }
    if ((item.retrieval_count ?? 0) >= 3 && item.status === "verified") {
      reinforce.push(`${item.id}:retrieval_count=${item.retrieval_count}`);
    }
    if (item.kind !== "session" && (item.retrieval_count ?? 0) === 0 && (updatedDays ?? 0) >= 14) {
      decay.push(`${item.id}:unretrieved_for=${updatedDays}d`);
    }
    const limit = limits[item.kind] ?? 12000;
    if (item.content.length > limit) {
      oversized.push(`${item.id}:${item.content.length}/${limit}:${filePath}`);
    }
    if (
      item.status === "verified" &&
      (item.retrieval_count ?? 0) > 0 &&
      (lastRetrievedDays ?? updatedDays ?? 0) < 30 &&
      item.content.length <= limit
    ) {
      keep.push(`${item.id}:${filePath}`);
    }
  }
  for (const filePath of await listMarkdownFiles(vaultRoot)) {
    const budgetKey = fileBudgetKey(vaultRoot, filePath);
    const limit = fileLimits[budgetKey] ?? fileLimits.root ?? 20000;
    const content = await fs.readFile(filePath, "utf8");
    if (content.length > limit) {
      oversizedFiles.push(`${budgetKey}:${content.length}/${limit}:${filePath}`);
    }
  }
  const nearDuplicates: Array<{ left: string; right: string; score: number }> = [];
  const threshold = policy.duplicateThreshold;
  for (let leftIndex = 0; leftIndex < items.length; leftIndex += 1) {
    for (let rightIndex = leftIndex + 1; rightIndex < items.length; rightIndex += 1) {
      const left = items[leftIndex].item;
      const right = items[rightIndex].item;
      if (left.kind !== right.kind) {
        continue;
      }
      const score = jaccard(left.content, right.content);
      if (score >= threshold) {
        nearDuplicates.push({ left: left.id, right: right.id, score: Number(score.toFixed(3)) });
      }
    }
  }
  const consolidate = [
    ...new Set([
      ...nearDuplicates.map((pair) => `${pair.left}<->${pair.right}`),
      ...cleanup.markers.filter((marker) => marker.startsWith("semantic_conflict:") || marker.startsWith("direct_contradiction:"))
    ])
  ];
  const consolidationCandidates = [
    ...nearDuplicates.map((pair) => ({
      left: pair.left,
      right: pair.right,
      score: pair.score,
      reason: "lexical-near-duplicate",
      action: "review-merge" as const
    })),
    ...cleanup.markers
      .filter((marker) => marker.startsWith("semantic_conflict:"))
      .map((marker) => ({
        left: marker,
        reason: "semantic-conflict-marker",
        action: "review-merge" as const
      })),
    ...cleanup.markers
      .filter((marker) => marker.startsWith("direct_contradiction:"))
      .map((marker) => ({
        left: marker,
        reason: "direct-contradiction-marker",
        action: "review-merge" as const
      }))
  ];
  review.push(
    ...cleanup.markers.filter((marker) =>
      [
        "dangling_reference:",
        "source_drift:",
        "missing_source_hash:",
        "missing_verified_at:",
        "never_retrieved:",
        "unreadable:",
        "circular_reference:"
      ].some((prefix) => marker.startsWith(prefix))
    )
  );
  review.push(...oversized);
  review.push(...oversizedFiles);
  review.push(...stale.map((entry) => `stale:${entry}`));
  review.push(...decay.map((entry) => `decay:${entry}`));
  const structure = await scoreStructure();
  if (structure.overall_score < 5) {
    review.push(`structure_score:${structure.overall_score}:${structure.recommendation}`);
  }
  const reviewItems: ControllerReviewItem[] = [
    ...cleanup.markers
      .filter((marker) => marker.startsWith("dangling_reference:"))
      .map((marker) => ({ type: "reference" as const, target: marker, reason: "dangling-reference", action: "inspect" as const })),
    ...cleanup.markers
      .filter((marker) => marker.startsWith("source_drift:") || marker.startsWith("missing_source_hash:"))
      .map((marker) => ({ type: "source" as const, target: marker, reason: "source-integrity", action: "inspect" as const })),
    ...cleanup.markers
      .filter((marker) => marker.startsWith("missing_verified_at:") || marker.startsWith("never_retrieved:") || marker.startsWith("unreadable:"))
      .map((marker) => ({ type: "integrity" as const, target: marker, reason: "item-integrity", action: "inspect" as const })),
    ...stale.map((entry) => ({ type: "stale" as const, target: entry, reason: "stale-age", action: "review" as const })),
    ...decay.map((entry) => ({ type: "decay" as const, target: entry, reason: "unretrieved-durable-memory", action: "review" as const })),
    ...oversized.map((entry) => ({ type: "budget" as const, target: entry, reason: "length-budget", action: "review" as const })),
    ...oversizedFiles.map((entry) => ({ type: "budget" as const, target: entry, reason: "file-length-budget", action: "review" as const })),
    ...(structure.overall_score < 5
      ? [{ type: "rubric" as const, target: "structure-rubric", reason: `structure-score:${structure.overall_score}`, action: "review" as const }]
      : []),
    ...cleanup.markers
      .filter((marker) => marker.startsWith("circular_reference:"))
      .map((marker) => ({ type: "retrieval" as const, target: marker, reason: "circular-reference", action: "inspect" as const }))
  ];
  const recommendations = {
    keep,
    decay,
    consolidate,
    review,
    expire: [...expired, ...expiringSoon, ...ttlBreaches]
  };
  const issueCount =
    recommendations.decay.length +
    recommendations.consolidate.length +
    recommendations.review.length +
    recommendations.expire.length;
  const deterministicScore = Number(Math.max(0, Math.min(1, 1 - issueCount / Math.max(items.length * 2, 1))).toFixed(3));
  const model = policy.model ?? { provider: "none", name: "deterministic-only" };
  const feedback = {
    deterministicScore,
    model,
    reviewPrompt: [
      "# Memory Controller Review",
      "",
      "Review the vault-level memory maintenance report.",
      "",
      "## Safety Boundary",
      "",
      "- Do not rewrite durable memory automatically.",
      "- Only expired session memory may be marked outdated through apply-safe.",
      "- Treat LLM Wiki as an external knowledge source, not as memory policy.",
      "",
      "## Rubric Feedback",
      "",
      `- structure score: ${structure.overall_score}`,
      `- recommendation: ${structure.recommendation}`,
      "",
      "## Recommendations",
      "",
      `- keep: ${recommendations.keep.length}`,
      `- decay: ${recommendations.decay.length}`,
      `- consolidate: ${recommendations.consolidate.length}`,
      `- review: ${recommendations.review.length}`,
      `- expire: ${recommendations.expire.length}`,
      "",
      "## Requested Review",
      "",
      "Identify which review items need human confirmation, which consolidate items are safe to merge later, and which decay items should remain untouched."
    ].join("\n")
  };
  const report = {
    vaultRoot,
    scope: "vault" as const,
    mode: applySafe ? ("safe-apply" as const) : ("read-report-first" as const),
    trigger: trigger as "scheduled" | "event" | "manual",
    policy,
    counts: { items: items.length, files: items.length },
    cleanup,
    time: { expired, expiringSoon, stale, ttlBreaches },
    reinforcement: { reinforce, decay },
    budgets: { limits, fileLimits, oversized, oversizedFiles },
    similarity: { threshold, nearDuplicates },
    recommendations,
    consolidationCandidates,
    reviewItems,
    applied: { expiredSessionItems: appliedExpiredSessionItems },
    structure,
    feedback,
    nextActions: [
      "Run this controller from an independent scheduler so vault health is not biased by the current project.",
      "Use event triggers after session-end, promotion, or knowledge-base link changes for narrower follow-up checks.",
      "Review keep/decay/consolidate/review/expire recommendations before editing durable memory.",
      "Keep LLM Wiki registered as an external knowledge base rather than importing it into core memory."
    ]
  };
  const reviewArtifacts = args.includes("--write-review-artifacts") ? [await writeControllerReviewArtifact(report)] : [];
  const reportWithArtifacts = {
    ...report,
    reviewArtifacts
  };
  const reportPath = args.includes("--write-report") ? await writeControllerReport(reportWithArtifacts) : undefined;
  const result = {
    ...reportWithArtifacts,
    ...(reportPath ? { reportPath } : {})
  };
  const feedbackLogPath = args.includes("--write-feedback") ? await appendControllerFeedback(result) : undefined;
  const reinforcementLogPath = args.includes("--write-reinforcement") ? await appendControllerReinforcement(result) : undefined;
  return {
    ...result,
    ...(feedbackLogPath ? { feedbackLogPath } : {}),
    ...(reinforcementLogPath ? { reinforcementLogPath } : {})
  };
}

function parseDailyTime(raw: string | undefined): { hour: number; minute: number; value: string } {
  const value = raw ?? "03:00";
  const match = /^(\d{1,2}):(\d{2})$/.exec(value);
  if (!match) {
    throw new Error("controller-schedule --time must use HH:MM format.");
  }
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (!Number.isInteger(hour) || !Number.isInteger(minute) || hour < 0 || hour > 23 || minute < 0 || minute > 59) {
    throw new Error("controller-schedule --time must be a valid 24-hour time.");
  }
  return { hour, minute, value: `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}` };
}

function shellQuote(value: string): string {
  return `'${value.replace(/'/g, "'\\''")}'`;
}

function scheduleId(args: string[]): string {
  const raw = value(args, "--name") ?? "memory-orchestrator-controller";
  return raw
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80) || "memory-orchestrator-controller";
}

function windowsTaskName(id: string): string {
  return id
    .split(/[^a-z0-9]+/i)
    .filter(Boolean)
    .map((part) => part.slice(0, 1).toUpperCase() + part.slice(1))
    .join("") || "MemoryOrchestratorController";
}

function controllerArgs(args: string[]): string[] {
  const commandArgs = ["controller", "--trigger", "scheduled"];
  const policyPath = value(args, "--policy");
  if (policyPath) {
    commandArgs.push("--policy", path.resolve(policyPath));
  }
  if (args.includes("--write-report")) {
    commandArgs.push("--write-report");
  }
  if (args.includes("--write-review-artifacts")) {
    commandArgs.push("--write-review-artifacts");
  }
  if (args.includes("--write-feedback")) {
    commandArgs.push("--write-feedback");
  }
  if (args.includes("--write-reinforcement")) {
    commandArgs.push("--write-reinforcement");
  }
  if (args.includes("--apply-safe")) {
    commandArgs.push("--apply-safe");
  }
  return commandArgs;
}

function shellArg(value: string): string {
  return /^(--?)?[a-z0-9-]+$/i.test(value) ? value : shellQuote(value);
}

function controllerCommand(args: string[], vaultRoot: string): string {
  return `MEMORY_ORCHESTRATOR_ROOT=${shellQuote(vaultRoot)} memory-orchestrator ${controllerArgs(args).map(shellArg).join(" ")}`;
}

function controllerExecStart(args: string[]): string {
  return `memory-orchestrator ${controllerArgs(args).map(shellArg).join(" ")}`;
}

function xmlEscape(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function launchdPlist(args: string[], vaultRoot: string, label: string, time: { hour: number; minute: number }): string {
  const programArguments = ["memory-orchestrator", ...controllerArgs(args)]
    .map((argument) => ["\t\t<string>", xmlEscape(argument), "</string>"].join(""))
    .join("\n");
  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
    '<plist version="1.0">',
    '<dict>',
    "\t<key>Label</key>",
    `\t<string>${xmlEscape(label)}</string>`,
    "\t<key>EnvironmentVariables</key>",
    "\t<dict>",
    "\t\t<key>MEMORY_ORCHESTRATOR_ROOT</key>",
    `\t\t<string>${xmlEscape(vaultRoot)}</string>`,
    "\t</dict>",
    "\t<key>ProgramArguments</key>",
    "\t<array>",
    programArguments,
    "\t</array>",
    "\t<key>StartCalendarInterval</key>",
    "\t<dict>",
    "\t\t<key>Hour</key>",
    `\t\t<integer>${time.hour}</integer>`,
    "\t\t<key>Minute</key>",
    `\t\t<integer>${time.minute}</integer>`,
    "\t</dict>",
    "\t<key>RunAtLoad</key>",
    "\t<false/>",
    "</dict>",
    "</plist>"
  ].join("\n");
}

function windowsCommand(args: string[], vaultRoot: string): string {
  const command = ["memory-orchestrator", ...controllerArgs(args)].join(" ");
  return `cmd.exe /c "set MEMORY_ORCHESTRATOR_ROOT=${vaultRoot}&& ${command}"`;
}

function windowsQuote(value: string): string {
  return `"${value.replace(/"/g, '\\"')}"`;
}

export async function buildControllerSchedule(args: string[]): Promise<{
  format: "cron" | "systemd" | "launchd" | "windows-task";
  trigger: "scheduled";
  vaultRoot: string;
  scheduleId: string;
  command: string;
  installCommand: string;
  uninstallCommand: string;
  cron?: string;
  service?: string;
  timer?: string;
  label?: string;
  plist?: string;
  taskName?: string;
  installHint: string;
  uninstallHint: string;
}> {
  const config = await resolveConfig(process.cwd());
  const vaultRoot = resolveVaultRoot(config);
  const rawFormat = value(args, "--format") ?? "cron";
  const format =
    rawFormat === "systemd" || rawFormat === "launchd" || rawFormat === "windows-task" || rawFormat === "cron" ? rawFormat : "cron";
  const time = parseDailyTime(value(args, "--time"));
  const id = scheduleId(args);
  const command = controllerCommand(args, vaultRoot);
  if (format === "cron") {
    const marker = `# ${id}`;
    const cron = `${time.minute} ${time.hour} * * * ${command} ${marker}`;
    return {
      format,
      trigger: "scheduled",
      vaultRoot,
      scheduleId: id,
      command,
      cron,
      installCommand: `(crontab -l 2>/dev/null | grep -v ${shellQuote(id)}; printf '%s\\n' ${shellQuote(cron)}) | crontab -`,
      uninstallCommand: `crontab -l 2>/dev/null | grep -v ${shellQuote(id)} | crontab -`,
      installHint: "Review installCommand, then run it to add or replace the cron entry.",
      uninstallHint: "Run uninstallCommand to remove the cron entry with this schedule id."
    };
  }
  if (format === "systemd") {
    const unitBase = id;
    return {
      format,
      trigger: "scheduled",
      vaultRoot,
      scheduleId: id,
      command,
      installCommand: `systemctl --user daemon-reload && systemctl --user enable --now ${unitBase}.timer`,
      uninstallCommand: `systemctl --user disable --now ${unitBase}.timer; rm -f ~/.config/systemd/user/${unitBase}.service ~/.config/systemd/user/${unitBase}.timer; systemctl --user daemon-reload`,
      service: [
        "[Unit]",
        "Description=Memory Orchestrator vault controller",
        "",
        "[Service]",
        "Type=oneshot",
        `Environment=MEMORY_ORCHESTRATOR_ROOT=${vaultRoot}`,
        `ExecStart=${controllerExecStart(args)}`
      ].join("\n"),
      timer: [
        "[Unit]",
        "Description=Run Memory Orchestrator vault controller daily",
        "",
        "[Timer]",
        `OnCalendar=*-*-* ${time.value}:00`,
        "Persistent=true",
        "",
        "[Install]",
        "WantedBy=timers.target"
      ].join("\n"),
      installHint: `Review, save service/timer as ~/.config/systemd/user/${unitBase}.{service,timer}, then run installCommand with systemctl --user.`,
      uninstallHint: "Run uninstallCommand to disable and remove the user service and timer."
    };
  }
  if (format === "launchd") {
    const label = `local.${id}`;
    const plistPath = `~/Library/LaunchAgents/${label}.plist`;
    return {
      format,
      trigger: "scheduled",
      vaultRoot,
      scheduleId: id,
      command,
      label,
      plist: launchdPlist(args, vaultRoot, label, time),
      installCommand: `mkdir -p ~/Library/LaunchAgents && launchctl bootstrap gui/$(id -u) ${plistPath} && launchctl enable gui/$(id -u)/${label}`,
      uninstallCommand: `launchctl bootout gui/$(id -u)/${label} 2>/dev/null; rm -f ${plistPath}`,
      installHint: `Review plist, save it as ${plistPath}, then run installCommand.`,
      uninstallHint: "Run uninstallCommand to unload and remove the LaunchAgent."
    };
  }
  const taskName = windowsTaskName(id);
  const winCommand = windowsCommand(args, vaultRoot);
  return {
    format,
    trigger: "scheduled",
    vaultRoot,
    scheduleId: id,
    command: winCommand,
    taskName,
    installCommand: `schtasks /Create /TN ${windowsQuote(taskName)} /SC DAILY /ST ${time.value} /TR ${windowsQuote(winCommand)} /F`,
    uninstallCommand: `schtasks /Delete /TN ${windowsQuote(taskName)} /F`,
    installHint: "Run installCommand from PowerShell or cmd.exe to create or replace the scheduled task.",
    uninstallHint: "Run uninstallCommand from PowerShell or cmd.exe to delete the scheduled task."
  };
}
