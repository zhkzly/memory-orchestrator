import { captureCandidate, classifyCandidate, verifyCandidate, promoteItem, buildContextPack, evaluateRubric, cleanMemory } from "./core.js";
import { addKnowledgeBase, initConfig, linkKnowledgeBase, resolveConfig, resolveVaultRoot } from "./config.js";
import { inferProject, inferSession } from "./identity.js";
import { listKnowledgeBases, readKnowledgeBasePage, searchKnowledgeBase } from "./kb.js";
import { memoryItemSchema, rubricProxySchema } from "./schemas.js";
import { spawn } from "node:child_process";
import { promises as fs } from "node:fs";

function usage(): string {
  return [
    "memory-orchestrator CLI",
    "",
    "Commands:",
    "  init --vault <path> [--project <default-project>]",
    "  status",
    "  kb list",
    "  kb add --name <name> --root <path> [--type llm_wiki|folder] [--api <url>] [--description <text>]",
    "  kb link --name <name> --project <project>",
    "  kb search --name <name> --query <text> [--limit <n>]",
    "  kb read --name <name> --page <path>",
    "  agent codex|claude [project-dir] [--task <text>]",
    "  capture --raw <text> --source <source> [--session <session>] [--project <project>]",
    "  classify --candidate <json>",
    "  verify --candidate <json> --evidence <json-array>",
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
  const projectDir = positional(args.slice(1)).slice(1)[0] ?? process.cwd();
  const config = await resolveConfig(projectDir);
  const vaultRoot = resolveVaultRoot(config, projectDir);
  const project = await inferProject(projectDir, config, value(args, "--project"));
  const session = await inferSession(projectDir, value(args, "--session"));
  const context = await buildContextPack({
    taskContext: value(args, "--task") ?? "",
    projectScope: project,
    sessionScope: session
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
  if (command === "capture") {
    const rawObservation = value(rest, "--raw") ?? "";
    const source = value(rest, "--source") ?? "";
    const { session, project } = await resolvedScopes(rest);
    console.log(JSON.stringify(await captureCandidate({ rawObservation, source, session, project }), null, 2));
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
  if (command === "promote") {
    console.log(JSON.stringify(await promoteItem(memoryItemSchema.parse(JSON.parse(value(rest, "--item") ?? "{}"))), null, 2));
    return;
  }
  if (command === "context") {
    const { session, project } = await resolvedScopes(rest);
    console.log(
      JSON.stringify(
        await buildContextPack({
          taskContext: value(rest, "--task") ?? "",
          sessionScope: session,
          projectScope: project
        }),
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
