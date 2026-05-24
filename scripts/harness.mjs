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
const sourcePath = path.join(vaultRoot, "source.md");
const sessionSummaryPath = path.join(vaultRoot, "session-summary.md");
const transcriptPath = path.join(vaultRoot, "session-transcript.md");
const mockAgentOutput = path.join(vaultRoot, "mock-agent-env.json");
await writeFile(sourcePath, "Evidence source for the harness.\n", "utf8");
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

await run("node", [cliPath, "init-project", "--project", "harness-project"], {
  env: cliEnv,
  cwd: harnessProjectRoot
});
const harnessProjectStatus = JSON.parse(await run("node", [cliPath, "status"], {
  env: cliEnv,
  cwd: harnessProjectRoot
}));
assert(harnessProjectStatus.project === "harness-project", "Expected project-local config to bind harness project.");

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
assert(sessionEnd.reportPath?.includes("reports"), "Expected session-end to write a maintenance report.");

const inferredContext = JSON.parse(
  await run("node", [cliPath, "context", "--task", "harness task"], projectOptions)
);
assert(
  inferredContext.contextPack.includes("project=harness-project"),
  "Expected context to infer project without explicit --project."
);
assert(
  inferredContext.contextPack.includes("Project context packs must include concise verified project memory."),
  "Expected context to include inline verified project memory."
);
assert(
  !inferredContext.contextPack.includes("Low priority filler memory 4."),
  "Expected context to omit low-priority filler memory."
);
const memoryEntries = inferredContext.contextPack.match(/^memory:/gm) ?? [];
assert(memoryEntries.length <= 3, "Expected context to limit inline memory entries.");

const ingestedSessionContext = JSON.parse(
  await run("node", [cliPath, "context", "--task", "session summaries"], projectOptions)
);
assert(
  ingestedSessionContext.contextPack.includes("Session ingest should capture end-of-session summaries"),
  "Expected task-matched context to include ingested session summaries."
);
const ingestedSessionMemoryEntries = ingestedSessionContext.contextPack.match(/^memory:/gm) ?? [];
assert(ingestedSessionMemoryEntries.length <= 3, "Expected ingested session context to keep inline memory bounded.");

const ephemeralSessionContext = JSON.parse(
  await run("node", [cliPath, "context", "--task", "ephemeral session memory"], projectOptions)
);
assert(
  ephemeralSessionContext.contextPack.includes("Session memory should stay ephemeral"),
  "Expected task-matched context to include inline session memory without promotion."
);
const ephemeralSessionMemoryEntries = ephemeralSessionContext.contextPack.match(/^memory:/gm) ?? [];
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
const transcriptMemoryEntries = transcriptContext.contextPack.match(/^memory:/gm) ?? [];
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

const uiProcess = spawn("node", [cliPath, "ui", "--port", "0"], {
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
assert(uiHome.includes("Add Knowledge Base"), "Expected UI homepage to include KB configuration form.");
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
