import { execFile, spawn } from "node:child_process";
import { chmod, mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const repoRoot = process.cwd();
const cliPath = path.join(repoRoot, "dist/cli.js");

async function run(command, args, options = {}) {
  const result = await execFileAsync(command, args, {
    cwd: repoRoot,
    maxBuffer: 1024 * 1024,
    ...options
  });
  return result.stdout.trim();
}

function waitForLine(child, pattern) {
  return new Promise((resolve, reject) => {
    let output = "";
    const timer = setTimeout(() => reject(new Error(`Timed out waiting for ${pattern}`)), 5000);
    child.stdout.on("data", (chunk) => {
      output += chunk.toString();
      const line = output.split("\n").find((candidate) => candidate.includes(pattern));
      if (line) {
        clearTimeout(timer);
        resolve(line);
      }
    });
    child.on("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on("exit", (code) => {
      if (code && code !== 0) {
        clearTimeout(timer);
        reject(new Error(`Process exited before ${pattern}: ${code}`));
      }
    });
  });
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

const vaultRoot = await mkdtemp(path.join(tmpdir(), "memory-orchestrator-vault."));
const homeRoot = await mkdtemp(path.join(tmpdir(), "memory-orchestrator-home."));
const wikiRoot = await mkdtemp(path.join(tmpdir(), "memory-orchestrator-wiki."));
const binRoot = await mkdtemp(path.join(tmpdir(), "memory-orchestrator-bin."));
const inferredProjectRoot = await mkdtemp(path.join(tmpdir(), "memory-orchestrator-inferred-project."));
const localProjectRoot = await mkdtemp(path.join(tmpdir(), "memory-orchestrator-local-project."));
const harnessProjectRoot = await mkdtemp(path.join(tmpdir(), "memory-orchestrator-harness-project."));
const uiProjectRoot = await mkdtemp(path.join(tmpdir(), "memory-orchestrator-ui-project."));
const sourcePath = path.join(vaultRoot, "source.md");
const sessionSummaryPath = path.join(vaultRoot, "session-summary.md");
const transcriptPath = path.join(vaultRoot, "session-transcript.md");
const oversizedVaultNotePath = path.join(vaultRoot, "notes", "oversized-vault-note.md");
const controllerPolicyPath = path.join(vaultRoot, "controller-policy.json");
const vaultControllerPolicyPath = path.join(vaultRoot, "agent", "controller-policy.json");
const controllerFeedbackPath = path.join(vaultRoot, "agent", "controller-feedback.jsonl");
const controllerReinforcementPath = path.join(vaultRoot, "agent", "controller-reinforcement.jsonl");
const controllerProposalsPath = path.join(vaultRoot, "agent", "controller-proposals.jsonl");
const controllerEvaluationsPath = path.join(vaultRoot, "agent", "controller-evaluations.jsonl");
const controllerExternalReviewPath = path.join(vaultRoot, "controller-external-review.json");
const controllerExternalReviewLogPath = path.join(vaultRoot, "agent", "controller-review-feedback.jsonl");
const mockAgentOutput = path.join(vaultRoot, "mock-agent-env.json");
await writeFile(sourcePath, "Evidence source for the harness.\n", "utf8");
await mkdir(path.dirname(oversizedVaultNotePath), { recursive: true });
await writeFile(oversizedVaultNotePath, `${"oversized vault note ".repeat(120)}\n`, "utf8");
await writeFile(
  controllerExternalReviewPath,
  JSON.stringify(
    {
      reviewer: "harness-model",
      source: "controller-reflection",
      decision: "needs-human-review",
      confidence: 0.8,
      findings: ["reinforce candidate should be reviewed before rewrite"],
      actions: ["inspect reinforcement log"]
    },
    null,
    2
  ),
  "utf8"
);
await writeFile(
  controllerPolicyPath,
  JSON.stringify(
    {
      staleDays: 10,
      expiringSoonDays: 2,
      duplicateThreshold: 0.2,
      ttlDays: { session: 1, project: 365, evidence: 730, personal: 3650 },
      lengthBudgets: { session: 20 },
      fileLengthBudgets: { notes: 120 },
      model: { provider: "none", name: "deterministic-only" }
    },
    null,
    2
  ),
  "utf8"
);
await writeFile(
  sessionSummaryPath,
  "Session ingest should capture end-of-session summaries for the next context pack.\n",
  "utf8"
);
await writeFile(
  transcriptPath,
  [
    "User: Need memory usability work.",
    "Decision: Keep CLI-first memory policy and use UI only as a review/config aid.",
    "TODO: Test transcript summarization for session-end workflow.",
    "Evidence: Harness should verify summarized transcripts enter future context."
  ].join("\n"),
  "utf8"
);
await mkdir(path.join(wikiRoot, "wiki"), { recursive: true });
await writeFile(
  path.join(wikiRoot, "wiki", "agent-memory.md"),
  "# Agent Memory\n\nLLM Wiki should stay separate from personal and project memory.\n",
  "utf8"
);
await writeFile(
  path.join(binRoot, "codex"),
  [
    "#!/usr/bin/env node",
    "const fs = require('node:fs');",
    "fs.writeFileSync(process.env.MOCK_AGENT_OUTPUT, JSON.stringify({",
    "  root: process.env.MEMORY_ORCHESTRATOR_ROOT,",
    "  project: process.env.MEMORY_ORCHESTRATOR_PROJECT,",
    "  session: process.env.MEMORY_ORCHESTRATOR_SESSION,",
    "  context: process.env.MEMORY_ORCHESTRATOR_CONTEXT,",
    "  argv: process.argv.slice(2)",
    "}, null, 2));"
  ].join("\n"),
  "utf8"
);
await chmod(path.join(binRoot, "codex"), 0o755);

await run("npm", ["run", "build"]);

const apiServer = createServer((request, response) => {
  const url = new URL(request.url ?? "/", "http://127.0.0.1");
  response.setHeader("content-type", "application/json");
  if (url.pathname === "/search") {
    response.end(
      JSON.stringify({
        results: [
          {
            path: "wiki/api-memory.md",
            title: "API Memory",
            excerpt: "API-backed LLM Wiki result should win over folder fallback."
          }
        ]
      })
    );
    return;
  }
  if (url.pathname === "/read") {
    response.end(JSON.stringify({ path: "wiki/api-memory.md", content: "# API Memory\n\nRead through LLM Wiki API.\n" }));
    return;
  }
  response.statusCode = 404;
  response.end(JSON.stringify({ error: "not found" }));
});
const llmWikiApiServer = createServer((request, response) => {
  const url = new URL(request.url ?? "/", "http://127.0.0.1");
  response.setHeader("content-type", "application/json");
  if (url.pathname === "/api/v1/projects/current/search" && request.method === "POST") {
    assert(request.headers.authorization === "Bearer harness-token", "Expected LLM Wiki API token header.");
    response.end(
      JSON.stringify({
        mode: "hybrid",
        tokenHits: [
          {
            path: "wiki/real-api-memory.md",
            title: "Real API Memory",
            snippet: "Real LLM Wiki API search result should win over folder fallback."
          }
        ],
        vectorHits: []
      })
    );
    return;
  }
  if (url.pathname === "/api/v1/projects/current/files/content") {
    assert(request.headers.authorization === "Bearer harness-token", "Expected LLM Wiki API token header.");
    assert(url.searchParams.get("path") === "wiki/real-api-memory.md", "Expected LLM Wiki read path query.");
    response.end(
      JSON.stringify({ path: "wiki/real-api-memory.md", content: "# Real API Memory\n\nRead through real LLM Wiki API shape.\n" })
    );
    return;
  }
  response.statusCode = 404;
  response.end(JSON.stringify({ error: "not found" }));
});
await new Promise((resolve) => apiServer.listen(0, "127.0.0.1", resolve));
await new Promise((resolve) => llmWikiApiServer.listen(0, "127.0.0.1", resolve));
const apiAddress = apiServer.address();
const apiBase =
  typeof apiAddress === "object" && apiAddress ? `http://127.0.0.1:${apiAddress.port}` : "http://127.0.0.1:0";
const llmWikiApiAddress = llmWikiApiServer.address();
const llmWikiApiBase =
  typeof llmWikiApiAddress === "object" && llmWikiApiAddress
    ? `http://127.0.0.1:${llmWikiApiAddress.port}`
    : "http://127.0.0.1:0";

const cliEnv = { ...process.env, HOME: homeRoot };
const agentEnv = {
  ...cliEnv,
  PATH: `${binRoot}${path.delimiter}${process.env.PATH ?? ""}`,
  LLM_WIKI_API_TOKEN: "harness-token",
  MOCK_AGENT_OUTPUT: mockAgentOutput
};
const projectOptions = { env: { ...cliEnv, LLM_WIKI_API_TOKEN: "harness-token" }, cwd: harnessProjectRoot };

await run("node", ["dist/cli.js", "init", "--vault", vaultRoot, "--project", "harness-project"], { env: cliEnv });

const status = JSON.parse(await run("node", ["dist/cli.js", "status"], { env: cliEnv }));
assert(status.vaultRoot === vaultRoot, "Expected status to resolve configured vault root.");
assert(status.project.includes("memory-orchestrator-publish"), "Expected status to infer the current repo project.");

const unconfiguredDoctor = JSON.parse(await run("node", [cliPath, "doctor"], {
  env: cliEnv,
  cwd: inferredProjectRoot
}));
assert(unconfiguredDoctor.ready === true, "Expected doctor to allow an unbound project to remain usable.");
assert(
  unconfiguredDoctor.nextActions.some((action) => action.includes("Pin a project-local config later")),
  "Expected doctor to treat project initialization as an optional later convenience."
);

await run("node", [cliPath, "init-project", "--project", "harness-project"], {
  env: cliEnv,
  cwd: harnessProjectRoot
});
const harnessProjectStatus = JSON.parse(await run("node", [cliPath, "status"], {
  env: cliEnv,
  cwd: harnessProjectRoot
}));
assert(harnessProjectStatus.project === "harness-project", "Expected project-local config to bind harness project.");
const configuredDoctor = JSON.parse(await run("node", [cliPath, "doctor"], projectOptions));
assert(configuredDoctor.ready === true, "Expected doctor to mark configured project as ready.");
assert(configuredDoctor.project === "harness-project", "Expected doctor to report inferred project.");
assert(configuredDoctor.checks.projectConfig.ok === true, "Expected doctor to detect project-local config.");
assert(configuredDoctor.checks.agentHarness.ok === true, "Expected doctor to report agent harness readiness.");
assert(configuredDoctor.checks.sessionEnd.ok === true, "Expected doctor to report session-end readiness.");

const inferredProjectStatus = JSON.parse(await run("node", [cliPath, "status"], {
  env: cliEnv,
  cwd: inferredProjectRoot
}));
assert(
  inferredProjectStatus.project.includes("memory-orchestrator-inferred-project"),
  "Expected project inference to prefer cwd over global default inside a project directory."
);

await run("node", [cliPath, "init-project", "--project", "Local Project"], {
  env: cliEnv,
  cwd: localProjectRoot
});
const localProjectStatus = JSON.parse(await run("node", [cliPath, "status"], {
  env: cliEnv,
  cwd: localProjectRoot
}));
assert(localProjectStatus.project === "local-project", "Expected project-local config to override inference.");

await run("node", [cliPath, "kb", "add", "--name", "memory-research", "--root", wikiRoot, "--api", apiBase], projectOptions);
await run("node", [cliPath, "kb", "link", "--name", "memory-research", "--project", "harness-project"], projectOptions);
await run(
  "node",
  [cliPath, "kb", "add", "--name", "fallback-research", "--root", wikiRoot, "--api", "http://127.0.0.1:1"],
  projectOptions
);
const knowledgeBases = JSON.parse(await run("node", [cliPath, "kb", "list"], projectOptions));
assert(knowledgeBases.length === 2, "Expected two registered knowledge bases.");
assert(
  knowledgeBases[0].linkedProjects.includes("harness-project"),
  "Expected knowledge base to link to harness-project."
);
const searchResults = JSON.parse(
  await run("node", [cliPath, "kb", "search", "--name", "memory-research", "--query", "LLM Wiki"], projectOptions)
);
assert(searchResults[0]?.path === "wiki/api-memory.md", "Expected kb search to prefer the API adapter.");
const fallbackResults = JSON.parse(
  await run("node", [cliPath, "kb", "search", "--name", "fallback-research", "--query", "LLM Wiki"], projectOptions)
);
assert(fallbackResults[0]?.path === "wiki/agent-memory.md", "Expected kb search to fall back to local files.");
const fallbackDoctor = JSON.parse(
  await run("node", [cliPath, "kb", "doctor", "--name", "fallback-research", "--query", "LLM Wiki"], projectOptions)
);
assert(fallbackDoctor.ready === true, "Expected kb doctor to accept local fallback when API is unavailable.");
assert(fallbackDoctor.checks.api.ok === false, "Expected kb doctor to report unavailable API.");
assert(fallbackDoctor.checks.localFallback.ok === true, "Expected kb doctor to report local fallback readiness.");
const wikiPage = JSON.parse(
  await run("node", [cliPath, "kb", "read", "--name", "memory-research", "--page", "wiki/api-memory.md"], projectOptions)
);
assert(wikiPage.content.includes("Read through LLM Wiki API"), "Expected kb read to prefer the API adapter.");

await run("node", [cliPath, "kb", "add", "--name", "real-llm-wiki", "--root", wikiRoot, "--api", llmWikiApiBase], projectOptions);
await run("node", [cliPath, "kb", "link", "--name", "real-llm-wiki", "--project", "harness-project"], projectOptions);
const realApiSearchResults = JSON.parse(
  await run("node", [cliPath, "kb", "search", "--name", "real-llm-wiki", "--query", "real api"], projectOptions)
);
assert(realApiSearchResults[0]?.path === "wiki/real-api-memory.md", "Expected kb search to support real LLM Wiki API.");
const realApiPage = JSON.parse(
  await run("node", [cliPath, "kb", "read", "--name", "real-llm-wiki", "--page", "wiki/real-api-memory.md"], projectOptions)
);
assert(realApiPage.content.includes("real LLM Wiki API shape"), "Expected kb read to support real LLM Wiki API.");
const realApiDoctor = JSON.parse(
  await run("node", [cliPath, "kb", "doctor", "--name", "real-llm-wiki", "--query", "real api"], projectOptions)
);
assert(realApiDoctor.ready === true, "Expected kb doctor to mark real LLM Wiki API as ready.");
assert(realApiDoctor.checks.api.ok === true, "Expected kb doctor to report API readiness.");
assert(realApiDoctor.checks.auth.ok === true, "Expected kb doctor to report token presence.");

const now = new Date().toISOString();
const projectItem = {
  id: "harness-project-rule",
  kind: "project",
  scope: "harness-project",
  source: sourcePath,
  confidence: 0.9,
  confidence_rationale: "harness project fixture",
  status: "verified",
  content: "Project context packs must include concise verified project memory.",
  created_at: now,
  updated_at: now,
  verified_at: now,
  retrieval_count: 0,
  cross_project_applicable: false,
  references: [],
  semantic_tags: ["context"],
  provenance: [{ type: "file", ref: sourcePath }]
};

await run("node", [cliPath, "promote", "--item", JSON.stringify(projectItem)], projectOptions);
const projectMarkdown = await readFile(path.join(vaultRoot, "projects", "harness-project-rule.md"), "utf8");
assert(projectMarkdown.includes("# Project Memory: harness-project-rule"), "Expected project memory to have a readable title.");
assert(projectMarkdown.includes("## Claim"), "Expected project memory to have a readable claim section.");
assert(projectMarkdown.includes("## Provenance"), "Expected project memory to have a readable provenance section.");

const personalItem = {
  ...projectItem,
  id: "harness-user-profile",
  kind: "personal",
  scope: "user",
  content: "The user prefers direct engineering answers with explicit tradeoffs and evidence.",
  semantic_tags: ["profile", "communication"]
};
await run("node", [cliPath, "promote", "--item", JSON.stringify(personalItem)], projectOptions);

const queryEvidenceItem = {
  ...projectItem,
  id: "harness-query-evidence",
  kind: "evidence",
  scope: "memory:harness",
  content: "LLM Wiki evidence should remain source-backed and retrievable through memory-query.",
  cross_project_applicable: true,
  semantic_tags: ["LLM", "Wiki", "evidence"]
};
await run("node", [cliPath, "promote", "--item", JSON.stringify(queryEvidenceItem)], projectOptions);

const contradictionPositiveItem = {
  ...projectItem,
  id: "harness-contradiction-positive",
  content: "Controller policy must archive transient scratchpad records.",
  semantic_tags: ["contradiction-fixture"]
};
const contradictionNegativeItem = {
  ...projectItem,
  id: "harness-contradiction-negative",
  content: "Controller policy must not archive transient scratchpad records.",
  semantic_tags: ["contradiction-fixture"]
};
await run("node", [cliPath, "promote", "--item", JSON.stringify(contradictionPositiveItem)], projectOptions);
await run("node", [cliPath, "promote", "--item", JSON.stringify(contradictionNegativeItem)], projectOptions);

const sessionItem = {
  id: "harness-session-note",
  kind: "session",
  scope: "harness-project",
  source: sourcePath,
  confidence: 0.6,
  confidence_rationale: "harness session fixture",
  status: "candidate",
  content: "Session memory should stay ephemeral but remain visible to current context.",
  created_at: now,
  updated_at: now,
  retrieval_count: 0,
  cross_project_applicable: false,
  references: [],
  semantic_tags: ["context"],
  provenance: [{ type: "session", ref: "harness" }]
};

await run("node", [cliPath, "write", "--item", JSON.stringify(sessionItem)], projectOptions);

const expiredSessionItem = {
  ...sessionItem,
  id: "expired-session-note",
  content: "Expired session memory should be safely marked outdated by the controller.",
  created_at: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
  updated_at: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
  expires_at: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString()
};
await run("node", [cliPath, "write", "--item", JSON.stringify(expiredSessionItem)], projectOptions);

const proposalExpiredSessionItem = {
  ...expiredSessionItem,
  id: "proposal-expired-session-note",
  content: "Expired session memory should become an evaluated optimization proposal before apply."
};
await run("node", [cliPath, "write", "--item", JSON.stringify(proposalExpiredSessionItem)], projectOptions);

for (let index = 1; index <= 4; index += 1) {
  await run(
    "node",
    [
      cliPath,
      "write",
      "--item",
      JSON.stringify({
        id: `low-priority-memory-${index}`,
        kind: "project",
        scope: "harness-project",
        source: sourcePath,
        confidence: 0.2,
        confidence_rationale: "low priority harness fixture",
        status: "candidate",
        content: `Low priority filler memory ${index}.`,
        created_at: now,
        updated_at: now,
        retrieval_count: 0,
        cross_project_applicable: false,
        references: [],
        semantic_tags: [],
        provenance: [{ type: "file", ref: sourcePath }]
      })
    ],
    projectOptions
  );
}

const ingestedSession = JSON.parse(
  await run("node", [cliPath, "ingest-session", "--file", sessionSummaryPath], projectOptions)
);
assert(ingestedSession.item.kind === "session", "Expected ingest-session to create a session memory item.");
assert(ingestedSession.item.status === "candidate", "Expected ingest-session to write a candidate item.");
assert(
  new Date(ingestedSession.item.expires_at).getTime() > Date.now(),
  "Expected ingested session memory to have a future expiration."
);
assert(ingestedSession.path.includes("sessions"), "Expected ingest-session to write under sessions.");
const sessionMarkdown = await readFile(ingestedSession.path, "utf8");
assert(sessionMarkdown.includes("# Session Memory:"), "Expected ingested session memory to have a readable title.");
assert(sessionMarkdown.includes("## Suggested Maintenance"), "Expected ingested session memory to have maintenance guidance.");
const summarizedSession = JSON.parse(
  await run("node", [cliPath, "summarize-session", "--file", transcriptPath, "--ingest"], projectOptions)
);
assert(summarizedSession.summaryPath?.includes("session-summary"), "Expected summarize-session to write a summary file.");
assert(summarizedSession.item?.kind === "session", "Expected summarize-session --ingest to create a session item.");
const transcriptSummary = await readFile(summarizedSession.summaryPath, "utf8");
assert(transcriptSummary.includes("## Decisions"), "Expected transcript summary to include decisions.");
assert(transcriptSummary.includes("Keep CLI-first memory policy"), "Expected transcript summary to preserve decisions.");
assert(transcriptSummary.includes("## TODOs"), "Expected transcript summary to include TODOs.");
const sessionEnd = JSON.parse(
  await run(
    "node",
    [cliPath, "session-end", "--transcript", transcriptPath, "--task", "session-end hook", "--write-report"],
    projectOptions
  )
);
assert(sessionEnd.project === "harness-project", "Expected session-end to infer project.");
assert(sessionEnd.ingest?.item?.kind === "session", "Expected session-end to ingest transcript summary.");
assert(
  new Date(sessionEnd.ingest.item.expires_at).getTime() > Date.now(),
  "Expected session-end memory to have a future expiration."
);
assert(sessionEnd.reportPath?.includes("reports"), "Expected session-end to write a maintenance report.");

const sessionEndController = JSON.parse(
  await run(
    "node",
    [
      cliPath,
      "session-end",
      "--transcript",
      transcriptPath,
      "--task",
      "session-end controller hook",
      "--controller-event",
      "--controller-report",
      "--controller-review-artifacts",
      "--controller-policy",
      controllerPolicyPath
    ],
    projectOptions
  )
);
assert(sessionEndController.controller?.scope === "vault", "Expected session-end to forward a vault controller event.");
assert(sessionEndController.controller?.trigger === "event", "Expected session-end controller trigger to be event-driven.");
assert(
  sessionEndController.controller?.policy.source === controllerPolicyPath,
  "Expected session-end controller event to accept a dedicated policy file."
);
assert(
  sessionEndController.controller?.reviewArtifacts?.length > 0,
  "Expected session-end controller event to be able to request review artifacts."
);
assert(
  sessionEndController.controller?.reportPath?.includes("controller-vault"),
  "Expected session-end controller event to write a vault controller report when requested."
);

const reviewReport = JSON.parse(
  await run("node", [cliPath, "review", "--scope", "harness-project", "--days", "8"], projectOptions)
);
assert(reviewReport.project === "harness-project", "Expected review to infer project.");
assert(reviewReport.scope === "harness-project", "Expected review to use the requested scope.");
assert(
  reviewReport.sessionItems.some((item) => item.id === sessionEnd.ingest.item.id),
  "Expected review to include session-end memory."
);
assert(
  reviewReport.expiringSessionItems.some((item) => item.id === sessionEnd.ingest.item.id),
  "Expected review to flag session-end memory inside the review window."
);
assert(
  reviewReport.reports.includes(sessionEnd.reportPath),
  "Expected review to include existing maintenance reports."
);
assert(
  reviewReport.nextActions.some((action) => action.includes("Review session memory")),
  "Expected review to recommend post-hoc human review."
);

const harnessReport = JSON.parse(
  await run(
    "node",
    [cliPath, "harness", "--task", "harness task", "--scope", "harness-project", "--days", "8", "--write-report"],
    projectOptions
  )
);
assert(harnessReport.ready === true, "Expected memory harness to report readiness.");
assert(harnessReport.doctor.ready === true, "Expected memory harness to include doctor readiness.");
assert(
  harnessReport.maintenance.context.contextPack.includes("task=harness task"),
  "Expected memory harness to include task-aware maintenance context."
);
assert(
  harnessReport.review.expiringSessionItems.some((item) => item.id === sessionEnd.ingest.item.id),
  "Expected memory harness to include post-hoc review data."
);
assert(harnessReport.controller.scope === "vault", "Expected memory harness to include vault-level controller data.");
assert(
  harnessReport.controller.mode === "read-report-first",
  "Expected memory harness controller pass to remain read/report-first."
);
assert(
  harnessReport.controller.reportPath?.includes("controller-vault"),
  "Expected memory harness to write a controller report when requested."
);
assert(
  harnessReport.reportPath?.includes("reports"),
  "Expected memory harness to write a maintenance report when requested."
);
assert(
  harnessReport.nextActions.some((action) => action.includes("agent codex|claude")),
  "Expected memory harness to point agents at the launcher surface."
);
assert(
  harnessReport.structure.overall_score >= 4,
  "Expected memory harness to include a credible structure score."
);
assert(
  harnessReport.structure.recommendation === "accept",
  "Expected memory harness structure score to accept the current architecture."
);
assert(
  harnessReport.structure.overall_score >= 4.4,
  "Expected memory harness structure score to stay above the acceptance threshold."
);

for (let index = 0; index < 3; index += 1) {
  await run("node", [cliPath, "context", "--task", "concise verified project memory"], projectOptions);
}

const controllerReport = JSON.parse(
  await run("node", [cliPath, "controller", "--write-report", "--trigger", "scheduled"], projectOptions)
);
assert(controllerReport.scope === "vault", "Expected controller to operate at vault scope.");
assert(controllerReport.mode === "read-report-first", "Expected controller to avoid automatic durable rewrites.");
assert(controllerReport.trigger === "scheduled", "Expected controller to record its trigger mode.");
assert(controllerReport.counts.items >= 2, "Expected controller to scan memory items across the vault.");
assert(
  controllerReport.cleanup.markers.some((marker) => marker.includes("never_retrieved") || marker.includes("semantic_conflict")),
  "Expected controller to reuse hard cleanup markers."
);
assert(
  controllerReport.cleanup.markers.some((marker) => marker.includes("direct_contradiction") && marker.includes("contradiction-fixture")),
  "Expected controller cleanup to detect explicit deterministic contradictions."
);
assert(controllerReport.time.expired.length >= 0, "Expected controller to include time-based expiry signals.");
assert(controllerReport.reinforcement.reinforce.length >= 0, "Expected controller to include reinforcement signals.");
assert(controllerReport.reinforcement.decay.length >= 0, "Expected controller to include decay signals.");
assert(
  controllerReport.reinforcement.reinforce.some((entry) => entry.includes("harness-project-rule")),
  "Expected frequently retrieved verified memory to be a reinforcement candidate."
);
assert(controllerReport.budgets.oversized.length >= 0, "Expected controller to include document length budget signals.");
assert(Array.isArray(controllerReport.budgets.oversizedFiles), "Expected controller to include vault Markdown file budget signals.");
assert(controllerReport.similarity.nearDuplicates.length >= 0, "Expected controller to include lexical similarity signals.");
assert(Array.isArray(controllerReport.recommendations.keep), "Expected controller to classify keep recommendations.");
assert(Array.isArray(controllerReport.recommendations.decay), "Expected controller to classify decay recommendations.");
assert(Array.isArray(controllerReport.recommendations.consolidate), "Expected controller to classify consolidate recommendations.");
assert(Array.isArray(controllerReport.consolidationCandidates), "Expected controller to expose structured consolidation candidates.");
assert(
  controllerReport.consolidationCandidates.every((candidate) => candidate.action === "review-merge"),
  "Expected consolidation candidates to require review before merge."
);
assert(
  controllerReport.consolidationCandidates.some((candidate) => candidate.reason === "direct-contradiction-marker"),
  "Expected direct contradictions to become structured consolidation candidates."
);
assert(Array.isArray(controllerReport.recommendations.review), "Expected controller to classify review recommendations.");
assert(Array.isArray(controllerReport.recommendations.expire), "Expected controller to classify expire recommendations.");
assert(
  controllerReport.recommendations.review.length > 0,
  "Expected controller to route cleanup and rubric feedback into review recommendations."
);
assert(controllerReport.structure.overall_score >= 4.4, "Expected controller to include rubric structure feedback.");
assert(
  controllerReport.nextActions.some((action) => action.includes("scheduler")),
  "Expected controller to recommend independent scheduling."
);
assert(controllerReport.reportPath?.includes("controller-vault"), "Expected controller to write a vault-level report.");

const reinforcementControllerReport = JSON.parse(
  await run("node", [cliPath, "controller", "--trigger", "scheduled", "--write-reinforcement"], projectOptions)
);
assert(
  reinforcementControllerReport.reinforcementLogPath === controllerReinforcementPath,
  "Expected controller --write-reinforcement to append to the vault-owned reinforcement log."
);
const reinforcementLines = (await readFile(controllerReinforcementPath, "utf8")).trim().split("\n");
assert(reinforcementLines.length >= 1, "Expected reinforcement log to contain at least one entry.");
const reinforcementEntry = JSON.parse(reinforcementLines.at(-1));
assert(reinforcementEntry.trigger === "scheduled", "Expected reinforcement log to record the trigger.");
assert(
  reinforcementEntry.reinforce.some((entry) => entry.includes("harness-project-rule")),
  "Expected reinforcement log to persist reinforcement candidates."
);
assert(
  reinforcementEntry.action === "review-reinforce",
  "Expected reinforcement log to remain a review action rather than an automatic rewrite."
);

const initializedControllerPolicy = JSON.parse(
  await run(
    "node",
    [
      cliPath,
      "controller-policy",
      "init",
      "--model-provider",
      "none",
      "--model-name",
      "vault-deterministic-only"
    ],
    projectOptions
  )
);
assert(
  initializedControllerPolicy.path === vaultControllerPolicyPath,
  "Expected controller-policy init to write a vault-owned policy file."
);
assert(
  initializedControllerPolicy.policy.model.name === "vault-deterministic-only",
  "Expected controller-policy init to persist model configuration metadata."
);
const shownControllerPolicy = JSON.parse(await run("node", [cliPath, "controller-policy", "show"], projectOptions));
assert(
  shownControllerPolicy.source === vaultControllerPolicyPath,
  "Expected controller-policy show to read the vault-owned policy file."
);
assert(
  shownControllerPolicy.model.name === "vault-deterministic-only",
  "Expected controller-policy show to include model metadata."
);
const defaultPolicyControllerReport = JSON.parse(await run("node", [cliPath, "controller"], projectOptions));
assert(
  defaultPolicyControllerReport.policy.source === vaultControllerPolicyPath,
  "Expected controller to use the vault-owned policy when --policy is omitted."
);

const cronSchedule = JSON.parse(
  await run(
    "node",
    [cliPath, "controller-schedule", "--format", "cron", "--time", "03:30", "--policy", controllerPolicyPath, "--write-report"],
    projectOptions
  )
);
assert(cronSchedule.format === "cron", "Expected controller-schedule to emit cron format.");
assert(cronSchedule.trigger === "scheduled", "Expected controller-schedule to target scheduled controller runs.");
assert(cronSchedule.scheduleId === "memory-orchestrator-controller", "Expected controller-schedule to emit a stable default schedule id.");
assert(
  cronSchedule.command.includes("controller --trigger scheduled"),
  "Expected controller-schedule command to run the vault controller in scheduled mode."
);
assert(cronSchedule.command.includes(controllerPolicyPath), "Expected controller-schedule to include the policy path.");
assert(cronSchedule.cron.includes("30 3 * * *"), "Expected controller-schedule to encode the requested daily time.");
assert(cronSchedule.cron.includes("# memory-orchestrator-controller"), "Expected cron output to include a removable schedule marker.");
assert(cronSchedule.installCommand.includes("crontab"), "Expected cron output to include an install command.");
assert(cronSchedule.uninstallCommand.includes("grep -v"), "Expected cron output to include a removal command.");
assert(
  !cronSchedule.command.includes("--project"),
  "Expected controller-schedule to avoid project-scoped policy flags."
);

const systemdSchedule = JSON.parse(
  await run("node", [cliPath, "controller-schedule", "--format", "systemd", "--time", "03:30"], projectOptions)
);
assert(systemdSchedule.format === "systemd", "Expected controller-schedule to emit systemd format.");
assert(systemdSchedule.service.includes("[Service]"), "Expected systemd schedule to include a service unit.");
assert(systemdSchedule.timer.includes("OnCalendar=*-*-* 03:30:00"), "Expected systemd schedule to encode the requested daily time.");
assert(systemdSchedule.installCommand.includes("systemctl --user enable --now"), "Expected systemd output to include an enable command.");
assert(systemdSchedule.uninstallCommand.includes("systemctl --user disable --now"), "Expected systemd output to include a disable command.");
assert(
  systemdSchedule.installHint.includes("systemctl --user"),
  "Expected systemd schedule to include a user-level install hint."
);

const launchdSchedule = JSON.parse(
  await run("node", [cliPath, "controller-schedule", "--format", "launchd", "--time", "03:30"], projectOptions)
);
assert(launchdSchedule.format === "launchd", "Expected controller-schedule to emit launchd format.");
assert(launchdSchedule.label === "local.memory-orchestrator-controller", "Expected launchd output to include a stable label.");
assert(launchdSchedule.plist.includes("<key>StartCalendarInterval</key>"), "Expected launchd plist to include daily scheduling.");
assert(launchdSchedule.plist.includes("<integer>3</integer>"), "Expected launchd plist to encode the requested hour.");
assert(launchdSchedule.installCommand.includes("launchctl bootstrap"), "Expected launchd output to include an install command.");
assert(launchdSchedule.uninstallCommand.includes("launchctl bootout"), "Expected launchd output to include an uninstall command.");

const windowsSchedule = JSON.parse(
  await run("node", [cliPath, "controller-schedule", "--format", "windows-task", "--time", "03:30"], projectOptions)
);
assert(windowsSchedule.format === "windows-task", "Expected controller-schedule to emit Windows Task Scheduler format.");
assert(windowsSchedule.taskName === "MemoryOrchestratorController", "Expected Windows output to include a stable task name.");
assert(windowsSchedule.installCommand.includes("schtasks /Create"), "Expected Windows output to include a schtasks create command.");
assert(windowsSchedule.installCommand.includes("/ST 03:30"), "Expected Windows install command to encode the requested time.");
assert(windowsSchedule.uninstallCommand.includes("schtasks /Delete"), "Expected Windows output to include a schtasks delete command.");
assert(windowsSchedule.command.includes("set MEMORY_ORCHESTRATOR_ROOT="), "Expected Windows command to set the vault root.");

const policyControllerReport = JSON.parse(
  await run("node", [cliPath, "controller", "--policy", controllerPolicyPath], projectOptions)
);
assert(policyControllerReport.policy.source === controllerPolicyPath, "Expected controller to load an explicit policy file.");
assert(policyControllerReport.policy.staleDays === 10, "Expected controller policy to override stale days.");
assert(policyControllerReport.policy.expiringSoonDays === 2, "Expected controller policy to override expiry window.");
assert(policyControllerReport.policy.duplicateThreshold === 0.2, "Expected controller policy to override duplicate threshold.");
assert(policyControllerReport.policy.ttlDays.session === 1, "Expected controller policy to override session TTL.");
assert(policyControllerReport.budgets.limits.session === 20, "Expected controller policy to override session length budget.");
assert(policyControllerReport.budgets.fileLimits.notes === 120, "Expected controller policy to override note file length budget.");
assert(
  policyControllerReport.budgets.oversizedFiles.some((entry) => entry.includes("oversized-vault-note.md")),
  "Expected controller to flag oversized vault Markdown notes."
);
assert(
  policyControllerReport.reviewItems.some(
    (item) => item.type === "budget" && item.target.includes("oversized-vault-note.md") && item.reason === "file-length-budget"
  ),
  "Expected oversized vault Markdown notes to become structured budget review items."
);
assert(policyControllerReport.time.ttlBreaches.length > 0, "Expected controller policy TTL to produce time breach signals.");
assert(
  policyControllerReport.policy.model.name === "deterministic-only",
  "Expected controller policy to expose model configuration without invoking a model."
);
assert(policyControllerReport.feedback.deterministicScore <= 1, "Expected controller feedback score to be normalized.");
assert(policyControllerReport.feedback.deterministicScore >= 0, "Expected controller feedback score to be normalized.");
assert(
  policyControllerReport.feedback.reviewPrompt.includes("Memory Controller Review"),
  "Expected controller to generate a model/human review prompt."
);
assert(
  policyControllerReport.feedback.reviewPrompt.includes("Recommendations"),
  "Expected review prompt to include recommendation buckets."
);
assert(
  policyControllerReport.feedback.reviewPrompt.includes("Do not rewrite durable memory"),
  "Expected review prompt to preserve safe write boundaries."
);

const feedbackControllerReport = JSON.parse(
  await run("node", [cliPath, "controller", "--policy", controllerPolicyPath, "--trigger", "scheduled", "--write-feedback"], projectOptions)
);
assert(
  feedbackControllerReport.feedbackLogPath === controllerFeedbackPath,
  "Expected controller --write-feedback to append to the vault-owned feedback log."
);
const feedbackLogLines = (await readFile(controllerFeedbackPath, "utf8")).trim().split("\n");
assert(feedbackLogLines.length >= 1, "Expected controller feedback log to contain at least one entry.");
const feedbackLogEntry = JSON.parse(feedbackLogLines.at(-1));
assert(feedbackLogEntry.trigger === "scheduled", "Expected feedback log to record the controller trigger.");
assert(feedbackLogEntry.policy === controllerPolicyPath, "Expected feedback log to record the policy source.");
assert(
  feedbackLogEntry.deterministicScore >= 0 && feedbackLogEntry.deterministicScore <= 1,
  "Expected feedback log to persist the normalized deterministic score."
);
assert(
  feedbackLogEntry.recommendations.review === feedbackControllerReport.recommendations.review.length,
  "Expected feedback log to persist recommendation counts for trend analysis."
);
const feedbackTrend = JSON.parse(await run("node", [cliPath, "controller-feedback", "--min-score", "1"], projectOptions));
assert(feedbackTrend.path === controllerFeedbackPath, "Expected controller-feedback to read the vault-owned feedback log.");
assert(feedbackTrend.count >= 1, "Expected controller-feedback to summarize feedback history entries.");
assert(
  feedbackTrend.latest.deterministicScore === feedbackLogEntry.deterministicScore,
  "Expected controller-feedback latest score to match the most recent log entry."
);
assert(
  feedbackTrend.averageDeterministicScore >= 0 && feedbackTrend.averageDeterministicScore <= 1,
  "Expected controller-feedback to compute a normalized average score."
);
assert(
  typeof feedbackTrend.trend.deterministicScoreDelta === "number",
  "Expected controller-feedback to compute a deterministic score trend delta."
);
assert(
  feedbackTrend.alerts.some((alert) => alert.includes("below_min_score")),
  "Expected controller-feedback to emit threshold alerts for low scores."
);
const reflectionReport = JSON.parse(
  await run("node", [cliPath, "controller-reflection", "--limit", "10", "--write-report"], projectOptions)
);
assert(reflectionReport.feedback.count >= 1, "Expected controller-reflection to include feedback history.");
assert(reflectionReport.reinforcement.count >= 1, "Expected controller-reflection to include reinforcement history.");
assert(
  reflectionReport.reflectionPrompt.includes("Memory Controller Reflection"),
  "Expected controller-reflection to generate a reflection prompt."
);
assert(
  reflectionReport.reviewQuestions.some((question) => question.includes("reinforce")),
  "Expected controller-reflection to surface reinforcement review questions."
);
assert(
  reflectionReport.reportPath?.includes("controller-reflection"),
  "Expected controller-reflection to write a report when requested."
);
const externalReviewIngest = JSON.parse(
  await run(
    "node",
    [cliPath, "controller-review", "ingest", "--file", controllerExternalReviewPath, "--reviewer", "external-model"],
    projectOptions
  )
);
assert(
  externalReviewIngest.path === controllerExternalReviewLogPath,
  "Expected controller-review ingest to append to the vault-owned external review log."
);
assert(externalReviewIngest.entry.reviewer === "external-model", "Expected controller-review ingest to record reviewer override.");
assert(
  externalReviewIngest.entry.decision === "needs-human-review",
  "Expected controller-review ingest to preserve external review decisions."
);
const externalReviewSummary = JSON.parse(await run("node", [cliPath, "controller-review", "show"], projectOptions));
assert(externalReviewSummary.count >= 1, "Expected controller-review show to summarize ingested reviews.");
assert(
  externalReviewSummary.latest.findings.some((finding) => finding.includes("reinforce")),
  "Expected controller-review show to expose latest external findings."
);

const artifactControllerReport = JSON.parse(
  await run(
    "node",
    [cliPath, "controller", "--policy", controllerPolicyPath, "--write-review-artifacts"],
    projectOptions
  )
);
assert(
  artifactControllerReport.reviewArtifacts.length > 0,
  "Expected controller to write review artifacts for human/model review."
);
assert(Array.isArray(artifactControllerReport.reviewItems), "Expected controller to expose structured review items.");
assert(
  artifactControllerReport.reviewItems.some((item) => item.action === "inspect" || item.action === "review"),
  "Expected controller to classify review findings as structured review items."
);
assert(
  artifactControllerReport.reviewItems.some((item) => item.type === "rubric" && item.action === "review"),
  "Expected controller to classify rubric feedback as review items."
);
const reviewArtifactPath = artifactControllerReport.reviewArtifacts[0];
assert(reviewArtifactPath.includes("controller-review"), "Expected review artifact path to be controller-scoped.");
const reviewArtifact = await readFile(reviewArtifactPath, "utf8");
assert(reviewArtifact.includes("# Memory Controller Review Artifact"), "Expected review artifact title.");
assert(reviewArtifact.includes("## Consolidate"), "Expected review artifact to include consolidate findings.");
assert(reviewArtifact.includes("## Consolidation Candidates"), "Expected review artifact to include structured consolidation candidates.");
assert(reviewArtifact.includes("## Review"), "Expected review artifact to include review findings.");
assert(reviewArtifact.includes("## Review Items"), "Expected review artifact to include structured review items.");
assert(reviewArtifact.includes("Do not rewrite durable memory"), "Expected review artifact to preserve safety boundary.");

const proposalControllerReport = JSON.parse(
  await run("node", [cliPath, "controller", "--policy", controllerPolicyPath, "--write-proposals"], projectOptions)
);
assert(
  proposalControllerReport.proposalLogPath === controllerProposalsPath,
  "Expected controller --write-proposals to append to the vault-owned proposal log."
);
assert(
  proposalControllerReport.evaluationLogPath === controllerEvaluationsPath,
  "Expected controller --write-proposals to append to the vault-owned evaluation log."
);
assert(
  proposalControllerReport.proposals.some(
    (proposal) => proposal.type === "mark-session-outdated" && proposal.targets.some((target) => target.includes("proposal-expired-session-note"))
  ),
  "Expected expired session memory to become an evaluated optimization proposal."
);
assert(
  proposalControllerReport.proposals.some((proposal) => proposal.requiresReview === true && proposal.risk !== "low"),
  "Expected durable consolidation or review proposals to require review."
);
const proposalLines = (await readFile(controllerProposalsPath, "utf8")).trim().split("\n");
assert(proposalLines.length >= 1, "Expected proposal log to contain at least one entry.");
const evaluationLines = (await readFile(controllerEvaluationsPath, "utf8")).trim().split("\n");
assert(evaluationLines.length >= 1, "Expected evaluation log to contain at least one rubric entry.");
const safeSessionProposal = proposalControllerReport.proposals.find(
  (proposal) => proposal.type === "mark-session-outdated" && proposal.targets.some((target) => target.includes("proposal-expired-session-note"))
);
const proposalApplyReport = JSON.parse(await run("node", [cliPath, "controller-apply", "--proposal", safeSessionProposal.id], projectOptions));
assert(
  proposalApplyReport.applied.some((entry) => entry.includes("proposal-expired-session-note")),
  "Expected controller-apply to apply a low-risk evaluated session proposal."
);
const proposalExpiredSessionMarkdown = await readFile(path.join(vaultRoot, "sessions", "proposal-expired-session-note.md"), "utf8");
assert(proposalExpiredSessionMarkdown.includes('"status": "outdated"'), "Expected controller-apply to mark proposal session memory outdated.");
assert(
  proposalExpiredSessionMarkdown.includes("controller proposal apply"),
  "Expected controller-apply update to be traceable to a proposal."
);

const appliedControllerReport = JSON.parse(
  await run("node", [cliPath, "controller", "--trigger", "scheduled", "--apply-safe"], projectOptions)
);
assert(
  appliedControllerReport.proposalLogPath === controllerProposalsPath,
  "Expected controller --apply-safe to write proposal history before applying safe changes."
);
assert(
  appliedControllerReport.evaluationLogPath === controllerEvaluationsPath,
  "Expected controller --apply-safe to write evaluation history before applying safe changes."
);
assert(
  appliedControllerReport.proposals.some(
    (proposal) => proposal.type === "mark-session-outdated" && proposal.targets.some((target) => target.includes("expired-session-note"))
  ),
  "Expected controller --apply-safe to evaluate expired session proposals before applying them."
);
assert(
  appliedControllerReport.applied.expiredSessionItems.some((item) => item.includes("expired-session-note")),
  "Expected controller --apply-safe to mark expired session memory."
);
const expiredSessionMarkdown = await readFile(path.join(vaultRoot, "sessions", "expired-session-note.md"), "utf8");
assert(expiredSessionMarkdown.includes('"status": "outdated"'), "Expected expired session memory to be marked outdated.");
assert(
  expiredSessionMarkdown.includes("controller proposal apply"),
  "Expected expired session memory update to be traceable to an evaluated controller proposal."
);

const inferredContext = JSON.parse(
  await run("node", [cliPath, "context", "--task", "harness task"], projectOptions)
);
const memoryPolicy = JSON.parse(await run("node", [cliPath, "memory-policy"], projectOptions));
assert(memoryPolicy.kinds.personal.load === "always_loaded", "Expected personal memory policy to be always-loaded.");
assert(memoryPolicy.kinds.personal.write === "verified_multi_evidence_or_user_confirmed", "Expected personal memory writes to require strong evidence.");
assert(memoryPolicy.kinds.project.load === "project_core_plus_retrieved", "Expected project memory policy to match layered context.");
assert(memoryPolicy.kinds.evidence.retrieval === "task_or_reference", "Expected evidence memory to prefer task/reference retrieval.");
assert(memoryPolicy.kinds.session.load === "session_memory", "Expected session memory policy to match session_memory context section.");
assert(memoryPolicy.kinds.session.autoApply.includes("mark_expired_outdated"), "Expected session memory to allow safe expiry apply.");
assert(memoryPolicy.contextSections.always_loaded.includes("personal"), "Expected policy to document always_loaded personal memory.");
assert(memoryPolicy.controller.safeApply.includes("session"), "Expected policy to document session-only safe apply.");

const personalQuery = JSON.parse(await run("node", [cliPath, "memory-query", "--kind", "personal"], projectOptions));
assert(personalQuery.kind === "personal", "Expected memory-query to return the requested kind.");
assert(personalQuery.load === "always_loaded", "Expected personal memory-query to be direct-load.");
assert(personalQuery.items.some((item) => item.id === "harness-user-profile"), "Expected personal memory-query to return the user profile memory.");
assert(personalQuery.items.length <= 5, "Expected personal memory-query to keep the result bounded.");

const projectQuery = JSON.parse(await run("node", [cliPath, "memory-query", "--kind", "project", "--task", "harness task"], projectOptions));
assert(projectQuery.kind === "project", "Expected project memory-query to return project kind.");
assert(projectQuery.load === "project_core_plus_retrieved", "Expected project memory-query to match layered policy.");
assert(projectQuery.items.some((item) => item.id === "harness-project-rule"), "Expected project memory-query to return verified project memory.");
assert(projectQuery.items.every((item) => typeof item.excerpt === "string"), "Expected memory-query to return excerpts.");

const sessionQuery = JSON.parse(await run("node", [cliPath, "memory-query", "--kind", "session", "--task", "ephemeral session memory"], projectOptions));
assert(sessionQuery.kind === "session", "Expected session memory-query to return session kind.");
assert(sessionQuery.load === "session_memory", "Expected session memory-query to match session_memory policy.");
assert(sessionQuery.items.some((item) => item.id === "harness-session-note"), "Expected session memory-query to return session memories.");

const evidenceQuery = JSON.parse(await run("node", [cliPath, "memory-query", "--kind", "evidence", "--task", "LLM Wiki"], projectOptions));
assert(evidenceQuery.kind === "evidence", "Expected evidence memory-query to return evidence kind.");
assert(evidenceQuery.retrieval === "task_or_reference", "Expected evidence memory-query to expose retrieval policy.");
assert(evidenceQuery.items.some((item) => item.kind === "evidence"), "Expected evidence memory-query to return evidence items.");
assert(evidenceQuery.items.length <= 5, "Expected evidence memory-query to keep the result bounded.");

assert(
  inferredContext.contextPack.includes("project=harness-project"),
  "Expected context to infer project without explicit --project."
);
assert(
  inferredContext.contextPack.includes("Project context packs must include concise verified project memory."),
  "Expected context to include inline verified project memory."
);
assert(
  inferredContext.contextPack.includes("always_loaded:"),
  "Expected context to distinguish always-loaded long-term memory."
);
assert(
  inferredContext.contextPack.includes("retrieved:"),
  "Expected context to distinguish task-retrieved memory."
);
assert(
  inferredContext.contextPack.includes("session_memory:"),
  "Expected context to distinguish session memory retrieval."
);
assert(
  inferredContext.contextPack.includes("evidence_memory:"),
  "Expected context to distinguish evidence retrieval."
);
assert(
  inferredContext.contextPack.includes("memory:personal:user:harness-user-profile"),
  "Expected context to always load user profile memory even when task terms do not match."
);
assert(
  !inferredContext.contextPack.includes("Low priority filler memory 4."),
  "Expected context to omit low-priority filler memory."
);
const retrievedSection = inferredContext.contextPack.match(/retrieved:\n([\s\S]*?)\nsession_memory:/)?.[1] ?? "";
const retrievedEntries = retrievedSection.match(/^memory:(project|evidence):/gm) ?? [];
assert(retrievedEntries.length <= 3, "Expected context to limit task-retrieved durable memory entries.");

const ingestedSessionContext = JSON.parse(
  await run("node", [cliPath, "context", "--task", "session summaries"], projectOptions)
);
assert(
  ingestedSessionContext.contextPack.includes("Session ingest should capture end-of-session summaries"),
  "Expected task-matched context to include ingested session summaries."
);
const ingestedSessionSection = ingestedSessionContext.contextPack.match(/session_memory:\n([\s\S]*?)\nevidence_memory:/)?.[1] ?? "";
const ingestedSessionMemoryEntries = ingestedSessionSection.match(/^memory:session:/gm) ?? [];
assert(ingestedSessionMemoryEntries.length <= 3, "Expected ingested session context to keep inline memory bounded.");

const ephemeralSessionContext = JSON.parse(
  await run("node", [cliPath, "context", "--task", "ephemeral session memory"], projectOptions)
);
assert(
  ephemeralSessionContext.contextPack.includes("Session memory should stay ephemeral"),
  "Expected task-matched context to include inline session memory without promotion."
);
const ephemeralSessionSection = ephemeralSessionContext.contextPack.match(/session_memory:\n([\s\S]*?)\nevidence_memory:/)?.[1] ?? "";
const ephemeralSessionMemoryEntries = ephemeralSessionSection.match(/^memory:session:/gm) ?? [];
assert(ephemeralSessionMemoryEntries.length <= 3, "Expected ephemeral session context to keep inline memory bounded.");

const transcriptContext = JSON.parse(
  await run("node", [cliPath, "context", "--task", "transcript summarization"], projectOptions)
);
assert(
  transcriptContext.contextPack.includes("Test transcript summarization"),
  "Expected task-matched context to include summarized transcript memory."
);
assert(
  transcriptContext.contextPack.includes("Keep CLI-first memory policy"),
  "Expected transcript context to include session-end ingested transcript summary."
);
const transcriptSessionSection = transcriptContext.contextPack.match(/session_memory:\n([\s\S]*?)\nevidence_memory:/)?.[1] ?? "";
const transcriptMemoryEntries = transcriptSessionSection.match(/^memory:session:/gm) ?? [];
assert(transcriptMemoryEntries.length <= 3, "Expected transcript context to keep inline memory bounded.");

const knowledgeContext = JSON.parse(
  await run("node", [cliPath, "context", "--task", "LLM Wiki"], projectOptions)
);
assert(
  knowledgeContext.contextPack.includes("kb:memory-research:wiki/api-memory.md"),
  "Expected context to include linked API knowledge-base matches."
);
assert(
  knowledgeContext.contextPack.includes("API-backed LLM Wiki result"),
  "Expected context to include a concise linked knowledge-base excerpt."
);

const maintenanceReport = JSON.parse(
  await run("node", [cliPath, "maintain", "--task", "harness task"], projectOptions)
);
assert(maintenanceReport.project === "harness-project", "Expected maintain to infer project.");
assert(
  maintenanceReport.context.contextPack.includes("task=harness task"),
  "Expected maintain to include a task-aware context pack."
);
assert(Array.isArray(maintenanceReport.cleanup.markers), "Expected maintain to include cleanup markers.");
assert(
  ["memory-research", "fallback-research", "real-llm-wiki"].every((name) =>
    maintenanceReport.knowledgeBases.some((kb) => kb.name === name)
  ),
  "Expected maintain to include registered knowledge bases."
);
const writtenMaintenanceReport = JSON.parse(
  await run("node", [cliPath, "maintain", "--task", "harness task", "--write-report"], projectOptions)
);
assert(writtenMaintenanceReport.reportPath?.includes("reports"), "Expected maintain to write a report under reports.");
const maintenanceMarkdown = await readFile(writtenMaintenanceReport.reportPath, "utf8");
assert(maintenanceMarkdown.includes("# Maintenance Report"), "Expected maintenance report to have a readable title.");
assert(maintenanceMarkdown.includes("## Scope"), "Expected maintenance report to include scope.");
assert(maintenanceMarkdown.includes("## Cleanup Markers"), "Expected maintenance report to include cleanup markers.");
assert(maintenanceMarkdown.includes("## Knowledge Bases"), "Expected maintenance report to include knowledge bases.");
assert(maintenanceMarkdown.includes("## Next Actions"), "Expected maintenance report to include next actions.");

const uiProcess = spawn("node", [cliPath, "ui", "--port", "0", "--cwd", uiProjectRoot], {
  ...projectOptions,
  stdio: ["ignore", "pipe", "pipe"]
});
const uiLine = await waitForLine(uiProcess, "memory-orchestrator ui");
const uiUrl = uiLine.match(/http:\/\/[^\s]+/)?.[0];
assert(uiUrl, "Expected ui command to print its local URL.");
const uiStatus = await fetch(`${uiUrl}/api/status`).then((response) => response.json());
assert(uiStatus.project === "harness-project", "Expected UI API to use project-local config.");
const uiHome = await fetch(uiUrl).then((response) => response.text());
assert(uiHome.includes("Memory Orchestrator"), "Expected UI homepage to render.");
assert(uiHome.includes("Project Init"), "Expected UI homepage to include project bootstrap form.");
assert(uiHome.includes("Add Knowledge Base"), "Expected UI homepage to include KB configuration form.");
const uiProjectInit = await fetch(`${uiUrl}/api/project/init`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ project: "ui-project", vaultRoot })
}).then((response) => response.json());
assert(uiProjectInit.ok === true, "Expected UI to initialize a project-local config.");
const uiProjectStatus = JSON.parse(
  await run("node", [cliPath, "status"], {
    env: cliEnv,
    cwd: uiProjectRoot
  })
);
assert(
  uiProjectStatus.project === "ui-project",
  "Expected UI project initialization to pin the new checkout."
);
const uiKbAdd = await fetch(`${uiUrl}/api/kb/add`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ name: "ui-research", root: wikiRoot, type: "llm_wiki" })
}).then((response) => response.json());
assert(uiKbAdd.ok === true, "Expected UI to add a knowledge base.");
const uiKbLink = await fetch(`${uiUrl}/api/kb/link`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ name: "ui-research", project: "harness-project" })
}).then((response) => response.json());
assert(uiKbLink.ok === true, "Expected UI to link a knowledge base.");
const uiKnowledgeBases = await fetch(`${uiUrl}/api/kb`).then((response) => response.json());
assert(
  uiKnowledgeBases.some((kb) => kb.name === "ui-research" && kb.linkedProjects.includes("harness-project")),
  "Expected UI-added knowledge base to appear in registry."
);
uiProcess.kill();

await run("node", [cliPath, "agent", "codex", harnessProjectRoot, "--task", "LLM Wiki"], { env: agentEnv });
const mockAgentEnv = JSON.parse(await readFile(mockAgentOutput, "utf8"));
assert(mockAgentEnv.root === vaultRoot, "Expected agent harness to inject configured vault root.");
assert(mockAgentEnv.project === "harness-project", "Expected agent harness to inject inferred project.");
assert(mockAgentEnv.context.includes("task=LLM Wiki"), "Expected agent harness to inject memory context.");
assert(
  mockAgentEnv.context.includes("kb:memory-research:wiki/api-memory.md"),
  "Expected agent harness context to include linked knowledge-base matches."
);
assert(mockAgentEnv.argv.includes("--add-dir"), "Expected codex harness to add explicit directories.");

await run("node", [
  cliPath,
  "score",
  "--rubric",
  "evaluation/cli-first-rubric.json",
  "--evidence",
  "evaluation/cli-first-evidence.json",
  "--out",
  path.join(vaultRoot, "score-report.json")
]);

const scoreReport = JSON.parse(await readFile(path.join(vaultRoot, "score-report.json"), "utf8"));
assert(scoreReport.recommendation === "accept", "Expected rubric recommendation to be accept.");
await run("node", [
  cliPath,
  "score",
  "--rubric",
  "evaluation/usability-rubric.json",
  "--evidence",
  "evaluation/usability-evidence.json",
  "--out",
  path.join(vaultRoot, "usability-score-report.json")
]);
const usabilityScoreReport = JSON.parse(await readFile(path.join(vaultRoot, "usability-score-report.json"), "utf8"));
assert(usabilityScoreReport.overall_score >= 4.5, "Expected usability rubric score to meet the acceptance threshold.");
assert(
  usabilityScoreReport.criteria.some((criterion) => criterion.name === "Zero-Friction Startup"),
  "Expected usability rubric to include startup readiness."
);

const item = {
  id: "harness-evidence",
  kind: "evidence",
  scope: "memory:harness",
  source: sourcePath,
  confidence: 0.9,
  confidence_rationale: "harness fixture",
  status: "verified",
  content: "Harness confirms evidence promotion works.",
  created_at: now,
  updated_at: now,
  verified_at: now,
  retrieval_count: 0,
  cross_project_applicable: true,
  references: ["missing-reference"],
  semantic_tags: ["harness"],
  provenance: [{ type: "file", ref: sourcePath }]
};

const promoteOutput = await run(
  "node",
  [cliPath, "promote", "--item", JSON.stringify(item)],
  projectOptions
);
const promoted = JSON.parse(promoteOutput);
assert(promoted.path.endsWith("notes/harness-evidence.md"), "Expected evidence item to be written under notes.");

const cleanOutput = await run(
  "node",
  [cliPath, "clean", "--scope", "memory"],
  projectOptions
);
const cleanReport = JSON.parse(cleanOutput);
assert(
  cleanReport.markers.some((marker) => marker.includes("never_retrieved")),
  "Expected cleanup to mark never_retrieved evidence."
);
assert(
  cleanReport.markers.some((marker) => marker.includes("dangling_reference")),
  "Expected cleanup to mark dangling references."
);

apiServer.close();
llmWikiApiServer.close();

console.log(
  JSON.stringify(
    {
      ok: true,
      vaultRoot,
      score: scoreReport.overall_score,
      markers: cleanReport.markers
    },
    null,
    2
  )
);
