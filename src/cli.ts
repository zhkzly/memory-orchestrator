import {
  captureCandidate,
  classifyCandidate,
  verifyCandidate,
  promoteItem,
  writeCandidateItem,
  ingestSessionFile,
  summarizeSessionTranscript,
  buildContextPack,
  evaluateRubric,
  cleanMemory
} from "./core.js";
import { addKnowledgeBase, initConfig, initProjectConfig, linkKnowledgeBase, resolveConfig, resolveVaultRoot } from "./config.js";
import { inferProject, inferSession } from "./identity.js";
import { listKnowledgeBases, readKnowledgeBasePage, searchKnowledgeBase } from "./kb.js";
import { memoryItemSchema, rubricProxySchema } from "./schemas.js";
import { spawn } from "node:child_process";
import { promises as fs } from "node:fs";
import { createServer } from "node:http";
import type { IncomingMessage } from "node:http";
import path from "node:path";
import type { MemoryConfig } from "./config.js";

function usage(): string {
  return [
    "memory-orchestrator CLI",
    "",
    "Commands:",
    "  init --vault <path> [--project <default-project>]",
    "  init-project [--project <project>] [--vault <path>]",
    "  status",
    "  kb list",
    "  kb add --name <name> --root <path> [--type llm_wiki|folder] [--api <url>] [--description <text>]",
    "  kb link --name <name> --project <project>",
    "  kb search --name <name> --query <text> [--limit <n>]",
    "  kb read --name <name> --page <path>",
    "  agent codex|claude [project-dir] [--task <text>]",
    "  maintain [--task <text>] [--session <scope>] [--project <scope>] [--scope <scope>] [--write-report]",
    "  ui [--host <host>] [--port <port>]",
    "  ingest-session --file <path> [--session <scope>] [--project <scope>]",
    "  summarize-session --file <path> [--out <path>] [--ingest] [--session <scope>] [--project <scope>]",
    "  capture --raw <text> --source <source> [--session <session>] [--project <project>]",
    "  classify --candidate <json>",
    "  verify --candidate <json> --evidence <json-array>",
    "  write --item <json>",
    "  promote --item <json>",
    "  context --task <text> [--session <scope>] [--project <scope>]",
    "  rubric --definition <text> --evidence <json-array> --system <text> --proxies <json-array>",
    "  score --rubric <file> --evidence <file> --out <file>",
    "  clean --scope <scope>"
  ].join("\n");
}

function value(args: string[], flag: string): string | undefined {
  const index = args.indexOf(flag);
  return index >= 0 ? args[index + 1] : undefined;
}

async function resolvedScopes(args: string[]): Promise<{ project: string; session: string }> {
  const config = await resolveConfig(process.cwd());
  return {
    project: await inferProject(process.cwd(), config, value(args, "--project")),
    session: await inferSession(process.cwd(), value(args, "--session"))
  };
}

async function contextWithLinkedKnowledgeBases(input: {
  config: MemoryConfig;
  contextPack: string;
  project: string;
  task: string;
}): Promise<string> {
  if (!input.task.trim()) {
    return input.contextPack;
  }
  const matches: string[] = [];
  for (const knowledgeBase of listKnowledgeBases(input.config)) {
    if (!(knowledgeBase.linkedProjects ?? []).includes(input.project)) {
      continue;
    }
    const results = await searchKnowledgeBase(input.config, knowledgeBase.name, input.task, 2);
    for (const result of results) {
      matches.push(`kb:${result.knowledgeBase}:${result.path}\ntitle=${result.title}\nexcerpt=${result.excerpt}`);
    }
  }
  return matches.length > 0 ? `${input.contextPack}\nknowledgeBases:\n${matches.join("\n---\n")}` : input.contextPack;
}

async function buildCliContext(input: {
  config: MemoryConfig;
  task: string;
  project: string;
  session: string;
}): Promise<{ contextPack: string }> {
  const context = await buildContextPack({
    taskContext: input.task,
    sessionScope: input.session,
    projectScope: input.project
  });
  context.contextPack = await contextWithLinkedKnowledgeBases({
    config: input.config,
    contextPack: context.contextPack,
    project: input.project,
    task: input.task
  });
  return context;
}

async function writeMaintenanceReport(input: {
  vaultRoot: string;
  project: string;
  session: string;
  scope: string;
  task: string;
  cleanup: { markers: string[] };
  knowledgeBases: ReturnType<typeof listKnowledgeBases>;
  nextActions: string[];
}): Promise<string> {
  const reportsDir = path.join(input.vaultRoot, "reports");
  await fs.mkdir(reportsDir, { recursive: true });
  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  const reportPath = path.join(reportsDir, `maintenance-${input.scope}-${timestamp}.md`);
  const knowledgeBases =
    input.knowledgeBases
      .map((kb) => `- ${kb.name} (${kb.type}) root=${kb.root}${kb.api ? ` api=${kb.api}` : ""}`)
      .join("\n") || "- none";
  const cleanupMarkers = input.cleanup.markers.map((marker) => `- ${marker}`).join("\n") || "- none";
  const nextActions = input.nextActions.map((action) => `- ${action}`).join("\n");
  await fs.writeFile(
    reportPath,
    [
      "# Maintenance Report",
      "",
      "## Scope",
      "",
      `- project: ${input.project}`,
      `- session: ${input.session}`,
      `- scope: ${input.scope}`,
      `- task: ${input.task}`,
      "",
      "## Cleanup Markers",
      "",
      cleanupMarkers,
      "",
      "## Knowledge Bases",
      "",
      knowledgeBases,
      "",
      "## Next Actions",
      "",
      nextActions,
      ""
    ].join("\n"),
    "utf8"
  );
  return reportPath;
}

function htmlPage(): string {
  return [
    "<!doctype html>",
    "<html>",
    "<head><meta charset=\"utf-8\"><title>Memory Orchestrator</title></head>",
    "<body>",
    "<h1>Memory Orchestrator</h1>",
    "<section><h2>Status</h2><pre id=\"status\">Loading...</pre></section>",
    "<section><h2>Knowledge Bases</h2><pre id=\"kb\">Loading...</pre></section>",
    "<section><h2>Add Knowledge Base</h2><form id=\"add-kb\"><input name=\"name\" placeholder=\"name\"><input name=\"root\" placeholder=\"root\"><input name=\"api\" placeholder=\"api optional\"><button>Add</button></form></section>",
    "<section><h2>Link Knowledge Base</h2><form id=\"link-kb\"><input name=\"name\" placeholder=\"name\"><input name=\"project\" placeholder=\"project\"><button>Link</button></form></section>",
    "<section><h2>Reports</h2><pre id=\"reports\">Loading...</pre></section>",
    "<script>",
    "for (const name of ['status','kb','reports']) fetch('/api/' + name).then(r => r.json()).then(j => document.getElementById(name).textContent = JSON.stringify(j, null, 2));",
    "async function postForm(id, url) { const form = document.getElementById(id); form.addEventListener('submit', async (event) => { event.preventDefault(); const body = Object.fromEntries(new FormData(form).entries()); await fetch(url, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) }); location.reload(); }); }",
    "postForm('add-kb', '/api/kb/add'); postForm('link-kb', '/api/kb/link');",
    "</script>",
    "</body>",
    "</html>"
  ].join("\n");
}

async function listReports(vaultRoot: string): Promise<string[]> {
  const reportsDir = path.join(vaultRoot, "reports");
  try {
    const entries = await fs.readdir(reportsDir, { withFileTypes: true });
    return entries.filter((entry) => entry.isFile() && entry.name.endsWith(".md")).map((entry) => path.join(reportsDir, entry.name));
  } catch {
    return [];
  }
}

async function readRequestJson<T>(request: IncomingMessage): Promise<T> {
  const chunks: Buffer[] = [];
  await new Promise<void>((resolve) => {
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", resolve);
  });
  return JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}") as T;
}

async function serveUi(args: string[]): Promise<void> {
  const host = value(args, "--host") ?? "127.0.0.1";
  const requestedPort = Number(value(args, "--port") ?? "8765");
  const server = createServer(async (request, response) => {
    const url = new URL(request.url ?? "/", `http://${host}`);
    const config = await resolveConfig(process.cwd());
    const vaultRoot = resolveVaultRoot(config);
    const scopes = await resolvedScopes(args);
    if (url.pathname === "/") {
      response.setHeader("content-type", "text/html; charset=utf-8");
      response.end(htmlPage());
      return;
    }
    if (url.pathname === "/api/status") {
      response.setHeader("content-type", "application/json");
      response.end(JSON.stringify({ vaultRoot, ...scopes }, null, 2));
      return;
    }
    if (url.pathname === "/api/kb") {
      response.setHeader("content-type", "application/json");
      response.end(JSON.stringify(listKnowledgeBases(config), null, 2));
      return;
    }
    if (url.pathname === "/api/kb/add" && request.method === "POST") {
      const body = await readRequestJson<{ name?: string; root?: string; type?: "llm_wiki" | "folder"; api?: string }>(request);
      if (!body.name || !body.root) {
        response.statusCode = 400;
        response.end(JSON.stringify({ ok: false, error: "name and root are required" }));
        return;
      }
      await addKnowledgeBase({
        name: body.name,
        root: body.root,
        type: body.type ?? "llm_wiki",
        api: body.api || undefined
      });
      response.setHeader("content-type", "application/json");
      response.end(JSON.stringify({ ok: true }));
      return;
    }
    if (url.pathname === "/api/kb/link" && request.method === "POST") {
      const body = await readRequestJson<{ name?: string; project?: string }>(request);
      if (!body.name || !body.project) {
        response.statusCode = 400;
        response.end(JSON.stringify({ ok: false, error: "name and project are required" }));
        return;
      }
      await linkKnowledgeBase({ name: body.name, project: body.project });
      response.setHeader("content-type", "application/json");
      response.end(JSON.stringify({ ok: true }));
      return;
    }
    if (url.pathname === "/api/reports") {
      response.setHeader("content-type", "application/json");
      response.end(JSON.stringify(await listReports(vaultRoot), null, 2));
      return;
    }
    response.statusCode = 404;
    response.end("not found");
  });
  await new Promise<void>((resolve) => server.listen(requestedPort, host, resolve));
  const address = server.address();
  const port = typeof address === "object" && address ? address.port : requestedPort;
  console.log(`memory-orchestrator ui http://${host}:${port}`);
}

function positional(args: string[]): string[] {
  const values: string[] = [];
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg.startsWith("--")) {
      index += 1;
    } else {
      values.push(arg);
    }
  }
  return values;
}

async function spawnAgent(agent: "codex" | "claude", args: string[]): Promise<void> {
  const projectDir = positional(args.slice(1))[0] ?? process.cwd();
  const config = await resolveConfig(projectDir);
  const vaultRoot = resolveVaultRoot(config, projectDir);
  const project = await inferProject(projectDir, config, value(args, "--project"));
  const session = await inferSession(projectDir, value(args, "--session"));
  const context = await buildCliContext({
    config,
    task: value(args, "--task") ?? "",
    project,
    session
  });
  const env = {
    ...process.env,
    MEMORY_ORCHESTRATOR_ROOT: vaultRoot,
    MEMORY_ORCHESTRATOR_PROJECT: project,
    MEMORY_ORCHESTRATOR_SESSION: session,
    MEMORY_ORCHESTRATOR_CONTEXT: context.contextPack
  };
  const commandArgs = agent === "codex" ? ["--add-dir", vaultRoot, "--add-dir", projectDir] : [];
  const child = spawn(agent, commandArgs, { cwd: projectDir, env, stdio: "inherit" });
  await new Promise<void>((resolve, reject) => {
    child.on("exit", (code) => {
      process.exitCode = code ?? 0;
      resolve();
    });
    child.on("error", reject);
  });
}

async function main(): Promise<void> {
  const [command, ...rest] = process.argv.slice(2);
  if (!command) {
    console.log(usage());
    return;
  }

  if (command === "init") {
    const vaultRoot = value(rest, "--vault");
    if (!vaultRoot) {
      throw new Error("init requires --vault <path>.");
    }
    console.log(JSON.stringify(await initConfig({ vaultRoot, defaultProject: value(rest, "--project") }), null, 2));
    return;
  }
  if (command === "init-project") {
    console.log(
      JSON.stringify(
        await initProjectConfig({
          cwd: process.cwd(),
          project: value(rest, "--project"),
          vaultRoot: value(rest, "--vault")
        }),
        null,
        2
      )
    );
    return;
  }
  if (command === "status") {
    const config = await resolveConfig(process.cwd());
    const scopes = await resolvedScopes(rest);
    console.log(
      JSON.stringify(
        {
          vaultRoot: resolveVaultRoot(config),
          project: scopes.project,
          session: scopes.session,
          knowledgeBases: config.knowledgeBases ?? []
        },
        null,
        2
      )
    );
    return;
  }
  if (command === "kb" && rest[0] === "list") {
    const config = await resolveConfig(process.cwd());
    console.log(JSON.stringify(listKnowledgeBases(config), null, 2));
    return;
  }
  if (command === "kb" && rest[0] === "add") {
    const name = value(rest, "--name");
    const root = value(rest, "--root");
    if (!name || !root) {
      throw new Error("kb add requires --name <name> and --root <path>.");
    }
    console.log(
      JSON.stringify(
        await addKnowledgeBase({
          name,
          root,
          type: (value(rest, "--type") as "llm_wiki" | "folder" | undefined) ?? "llm_wiki",
          api: value(rest, "--api"),
          description: value(rest, "--description")
        }),
        null,
        2
      )
    );
    return;
  }
  if (command === "kb" && rest[0] === "link") {
    const name = value(rest, "--name");
    const project = value(rest, "--project");
    if (!name || !project) {
      throw new Error("kb link requires --name <name> and --project <project>.");
    }
    console.log(JSON.stringify(await linkKnowledgeBase({ name, project }), null, 2));
    return;
  }
  if (command === "kb" && rest[0] === "search") {
    const name = value(rest, "--name");
    const query = value(rest, "--query");
    const limit = Number(value(rest, "--limit") ?? "5");
    if (!name || !query) {
      throw new Error("kb search requires --name <name> and --query <text>.");
    }
    const config = await resolveConfig(process.cwd());
    console.log(JSON.stringify(await searchKnowledgeBase(config, name, query, Number.isNaN(limit) ? 5 : limit), null, 2));
    return;
  }
  if (command === "kb" && rest[0] === "read") {
    const name = value(rest, "--name");
    const page = value(rest, "--page");
    if (!name || !page) {
      throw new Error("kb read requires --name <name> and --page <path>.");
    }
    const config = await resolveConfig(process.cwd());
    console.log(JSON.stringify(await readKnowledgeBasePage(config, name, page), null, 2));
    return;
  }
  if (command === "agent") {
    const agent = rest[0];
    if (agent !== "codex" && agent !== "claude") {
      throw new Error("agent requires codex or claude.");
    }
    await spawnAgent(agent, rest);
    return;
  }
  if (command === "ui") {
    await serveUi(rest);
    return;
  }
  if (command === "maintain") {
    const config = await resolveConfig(process.cwd());
    const vaultRoot = resolveVaultRoot(config);
    const { session, project } = await resolvedScopes(rest);
    const scope = value(rest, "--scope") ?? project;
    const task = value(rest, "--task") ?? "maintenance";
    const context = await buildCliContext({
      config,
      task,
      project,
      session
    });
    const cleanup = await cleanMemory(scope);
    const report = {
      vaultRoot,
      project,
      session,
      scope,
      context,
      cleanup,
      knowledgeBases: listKnowledgeBases(config),
      nextActions: [
        "Review cleanup markers before promoting or deleting memory.",
        "Use kb search/read for linked professional knowledge; do not import whole knowledge bases into memory.",
        "Use capture/promote for explicit writes; maintain is intentionally read/report-first."
      ]
    };
    const reportPath = rest.includes("--write-report")
      ? await writeMaintenanceReport({
          vaultRoot,
          project,
          session,
          scope,
          task,
          cleanup,
          knowledgeBases: report.knowledgeBases,
          nextActions: report.nextActions
        })
      : undefined;
    console.log(
      JSON.stringify(
        {
          ...report,
          ...(reportPath ? { reportPath } : {})
        },
        null,
        2
      )
    );
    return;
  }
  if (command === "capture") {
    const rawObservation = value(rest, "--raw") ?? "";
    const source = value(rest, "--source") ?? "";
    const { session, project } = await resolvedScopes(rest);
    console.log(JSON.stringify(await captureCandidate({ rawObservation, source, session, project }), null, 2));
    return;
  }
  if (command === "ingest-session") {
    const filePath = value(rest, "--file");
    if (!filePath) {
      throw new Error("ingest-session requires --file <path>.");
    }
    const { session, project } = await resolvedScopes(rest);
    console.log(JSON.stringify(await ingestSessionFile({ filePath, session, project }), null, 2));
    return;
  }
  if (command === "summarize-session") {
    const filePath = value(rest, "--file");
    if (!filePath) {
      throw new Error("summarize-session requires --file <path>.");
    }
    const summary = await summarizeSessionTranscript({
      filePath,
      outPath: value(rest, "--out")
    });
    if (rest.includes("--ingest")) {
      const { session, project } = await resolvedScopes(rest);
      const ingested = await ingestSessionFile({
        filePath: summary.summaryPath,
        session,
        project
      });
      console.log(JSON.stringify({ ...summary, path: ingested.path, item: ingested.item }, null, 2));
      return;
    }
    console.log(JSON.stringify(summary, null, 2));
    return;
  }
  if (command === "classify") {
    console.log(
      JSON.stringify(
        await classifyCandidate(memoryItemSchema.parse(JSON.parse(value(rest, "--candidate") ?? "{}"))),
        null,
        2
      )
    );
    return;
  }
  if (command === "verify") {
    const candidate = memoryItemSchema.parse(JSON.parse(value(rest, "--candidate") ?? "{}"));
    const evidence = JSON.parse(value(rest, "--evidence") ?? "[]");
    console.log(JSON.stringify(await verifyCandidate(candidate, evidence), null, 2));
    return;
  }
  if (command === "write") {
    console.log(
      JSON.stringify(await writeCandidateItem(memoryItemSchema.parse(JSON.parse(value(rest, "--item") ?? "{}"))), null, 2)
    );
    return;
  }
  if (command === "promote") {
    console.log(JSON.stringify(await promoteItem(memoryItemSchema.parse(JSON.parse(value(rest, "--item") ?? "{}"))), null, 2));
    return;
  }
  if (command === "context") {
    const config = await resolveConfig(process.cwd());
    const { session, project } = await resolvedScopes(rest);
    const task = value(rest, "--task") ?? "";
    const context = await buildCliContext({
      config,
      task,
      project,
      session
    });
    console.log(
      JSON.stringify(
        context,
        null,
        2
      )
    );
    return;
  }
  if (command === "rubric") {
    const proxies = JSON.parse(value(rest, "--proxies") ?? "[]").map((proxy: unknown) => rubricProxySchema.parse(proxy));
    console.log(
      JSON.stringify(
        await evaluateRubric({
          rubricDefinition: value(rest, "--definition") ?? "",
          evidenceSet: JSON.parse(value(rest, "--evidence") ?? "[]"),
          candidateSystem: value(rest, "--system") ?? "",
          proxies
        }),
        null,
        2
      )
    );
    return;
  }
  if (command === "score") {
    const rubricPath = value(rest, "--rubric") ?? "";
    const evidencePath = value(rest, "--evidence") ?? "";
    const outPath = value(rest, "--out") ?? "";
    const rubric = JSON.parse(await fs.readFile(rubricPath, "utf8"));
    const evidence = JSON.parse(await fs.readFile(evidencePath, "utf8"));
    const proxies = (rubric.proxies ?? []).map((proxy: unknown) => rubricProxySchema.parse(proxy));
    const result = await evaluateRubric({
      rubricDefinition: JSON.stringify(rubric, null, 2),
      evidenceSet: evidence.items ?? [],
      candidateSystem: rubric.candidate?.name ?? "unknown",
      proxies
    });
    const report = {
      candidate: rubric.candidate?.name ?? "",
      rubric: rubricPath,
      proxies: result.proxyScores.map((proxy) => ({
        id: proxy.id,
        score: proxy.score,
        evidence: proxy.evidence
      })),
      criteria: Object.entries(result.criterionScores).map(([name, score]) => ({
        name,
        score,
        risks: []
      })),
      overall_score:
        Object.values(result.criterionScores).reduce((sum, score) => sum + score, 0) /
        Math.max(Object.keys(result.criterionScores).length, 1),
      recommendation: result.recommendation,
      notes: []
    };
    if (outPath) {
      await fs.writeFile(outPath, JSON.stringify(report, null, 2), "utf8");
    }
    console.log(JSON.stringify(report, null, 2));
    return;
  }
  if (command === "clean") {
    const { project } = await resolvedScopes(rest);
    console.log(JSON.stringify(await cleanMemory(value(rest, "--scope") ?? project), null, 2));
    return;
  }

  console.error(usage());
  process.exitCode = 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
