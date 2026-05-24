import { execFile } from "node:child_process";
import { chmod, mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const repoRoot = process.cwd();

async function run(command, args, options = {}) {
  const result = await execFileAsync(command, args, {
    cwd: repoRoot,
    maxBuffer: 1024 * 1024,
    ...options
  });
  return result.stdout.trim();
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
const sourcePath = path.join(vaultRoot, "source.md");
const sessionSummaryPath = path.join(vaultRoot, "session-summary.md");
const mockAgentOutput = path.join(vaultRoot, "mock-agent-env.json");
await writeFile(sourcePath, "Evidence source for the harness.\n", "utf8");
await writeFile(
  sessionSummaryPath,
  "Session ingest should capture end-of-session summaries for the next context pack.\n",
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
await new Promise((resolve) => apiServer.listen(0, "127.0.0.1", resolve));
const apiAddress = apiServer.address();
const apiBase =
  typeof apiAddress === "object" && apiAddress ? `http://127.0.0.1:${apiAddress.port}` : "http://127.0.0.1:0";

const cliEnv = { ...process.env, HOME: homeRoot };
const agentEnv = {
  ...cliEnv,
  PATH: `${binRoot}${path.delimiter}${process.env.PATH ?? ""}`,
  MOCK_AGENT_OUTPUT: mockAgentOutput
};

await run("node", ["dist/cli.js", "init", "--vault", vaultRoot, "--project", "harness-project"], { env: cliEnv });

const status = JSON.parse(await run("node", ["dist/cli.js", "status"], { env: cliEnv }));
assert(status.vaultRoot === vaultRoot, "Expected status to resolve configured vault root.");
assert(status.project === "harness-project", "Expected status to use configured default project.");

await run("node", ["dist/cli.js", "kb", "add", "--name", "memory-research", "--root", wikiRoot, "--api", apiBase], {
  env: cliEnv
});
await run("node", ["dist/cli.js", "kb", "link", "--name", "memory-research", "--project", "harness-project"], {
  env: cliEnv
});
await run(
  "node",
  ["dist/cli.js", "kb", "add", "--name", "fallback-research", "--root", wikiRoot, "--api", "http://127.0.0.1:1"],
  { env: cliEnv }
);
const knowledgeBases = JSON.parse(await run("node", ["dist/cli.js", "kb", "list"], { env: cliEnv }));
assert(knowledgeBases.length === 2, "Expected two registered knowledge bases.");
assert(
  knowledgeBases[0].linkedProjects.includes("harness-project"),
  "Expected knowledge base to link to harness-project."
);
const searchResults = JSON.parse(
  await run("node", ["dist/cli.js", "kb", "search", "--name", "memory-research", "--query", "LLM Wiki"], {
    env: cliEnv
  })
);
assert(searchResults[0]?.path === "wiki/api-memory.md", "Expected kb search to prefer the API adapter.");
const fallbackResults = JSON.parse(
  await run("node", ["dist/cli.js", "kb", "search", "--name", "fallback-research", "--query", "LLM Wiki"], {
    env: cliEnv
  })
);
assert(fallbackResults[0]?.path === "wiki/agent-memory.md", "Expected kb search to fall back to local files.");
const wikiPage = JSON.parse(
  await run("node", ["dist/cli.js", "kb", "read", "--name", "memory-research", "--page", "wiki/api-memory.md"], {
    env: cliEnv
  })
);
assert(wikiPage.content.includes("Read through LLM Wiki API"), "Expected kb read to prefer the API adapter.");

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

await run("node", ["dist/cli.js", "promote", "--item", JSON.stringify(projectItem)], { env: cliEnv });
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

await run("node", ["dist/cli.js", "write", "--item", JSON.stringify(sessionItem)], { env: cliEnv });

for (let index = 1; index <= 4; index += 1) {
  await run(
    "node",
    [
      "dist/cli.js",
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
    { env: cliEnv }
  );
}

const ingestedSession = JSON.parse(
  await run("node", ["dist/cli.js", "ingest-session", "--file", sessionSummaryPath], { env: cliEnv })
);
assert(ingestedSession.item.kind === "session", "Expected ingest-session to create a session memory item.");
assert(ingestedSession.item.status === "candidate", "Expected ingest-session to write a candidate item.");
assert(ingestedSession.path.includes("sessions"), "Expected ingest-session to write under sessions.");
const sessionMarkdown = await readFile(ingestedSession.path, "utf8");
assert(sessionMarkdown.includes("# Session Memory:"), "Expected ingested session memory to have a readable title.");
assert(sessionMarkdown.includes("## Suggested Maintenance"), "Expected ingested session memory to have maintenance guidance.");

const inferredContext = JSON.parse(
  await run("node", ["dist/cli.js", "context", "--task", "harness task"], { env: cliEnv })
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
  inferredContext.contextPack.includes("Session memory should stay ephemeral"),
  "Expected context to include inline session memory without promotion."
);
assert(
  inferredContext.contextPack.includes("Session ingest should capture end-of-session summaries"),
  "Expected context to include ingested session summaries."
);
const memoryEntries = inferredContext.contextPack.match(/^memory:/gm) ?? [];
assert(memoryEntries.length <= 3, "Expected context to limit inline memory entries.");
assert(
  !inferredContext.contextPack.includes("Low priority filler memory 4."),
  "Expected context to omit low-priority filler memory."
);

const knowledgeContext = JSON.parse(
  await run("node", ["dist/cli.js", "context", "--task", "LLM Wiki"], { env: cliEnv })
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
  await run("node", ["dist/cli.js", "maintain", "--task", "harness task"], { env: cliEnv })
);
assert(maintenanceReport.project === "harness-project", "Expected maintain to infer project.");
assert(
  maintenanceReport.context.contextPack.includes("task=harness task"),
  "Expected maintain to include a task-aware context pack."
);
assert(Array.isArray(maintenanceReport.cleanup.markers), "Expected maintain to include cleanup markers.");
assert(maintenanceReport.knowledgeBases.length === 2, "Expected maintain to include registered knowledge bases.");
const writtenMaintenanceReport = JSON.parse(
  await run("node", ["dist/cli.js", "maintain", "--task", "harness task", "--write-report"], { env: cliEnv })
);
assert(writtenMaintenanceReport.reportPath?.includes("reports"), "Expected maintain to write a report under reports.");
const maintenanceMarkdown = await readFile(writtenMaintenanceReport.reportPath, "utf8");
assert(maintenanceMarkdown.includes("# Maintenance Report"), "Expected maintenance report to have a readable title.");
assert(maintenanceMarkdown.includes("## Scope"), "Expected maintenance report to include scope.");
assert(maintenanceMarkdown.includes("## Cleanup Markers"), "Expected maintenance report to include cleanup markers.");
assert(maintenanceMarkdown.includes("## Knowledge Bases"), "Expected maintenance report to include knowledge bases.");
assert(maintenanceMarkdown.includes("## Next Actions"), "Expected maintenance report to include next actions.");

await run("node", ["dist/cli.js", "agent", "codex", repoRoot, "--task", "LLM Wiki"], { env: agentEnv });
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
  "dist/cli.js",
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
  ["dist/cli.js", "promote", "--item", JSON.stringify(item)],
  { env: cliEnv }
);
const promoted = JSON.parse(promoteOutput);
assert(promoted.path.endsWith("notes/harness-evidence.md"), "Expected evidence item to be written under notes.");

const cleanOutput = await run(
  "node",
  ["dist/cli.js", "clean", "--scope", "memory"],
  { env: cliEnv }
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
