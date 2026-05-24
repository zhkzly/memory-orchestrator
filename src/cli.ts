import { captureCandidate, classifyCandidate, verifyCandidate, promoteItem, buildContextPack, evaluateRubric, cleanMemory } from "./core.js";
import { memoryItemSchema, rubricProxySchema } from "./schemas.js";
import { promises as fs } from "node:fs";

function usage(): string {
  return [
    "memory-orchestrator CLI",
    "",
    "Commands:",
    "  capture --raw <text> --source <source> --session <session> --project <project>",
    "  classify --candidate <json>",
    "  verify --candidate <json> --evidence <json-array>",
    "  promote --item <json>",
    "  context --task <text> --session <scope> --project <scope>",
    "  rubric --definition <text> --evidence <json-array> --system <text> --proxies <json-array>",
    "  score --rubric <file> --evidence <file> --out <file>",
    "  clean --scope <scope>"
  ].join("\n");
}

function value(args: string[], flag: string): string | undefined {
  const index = args.indexOf(flag);
  return index >= 0 ? args[index + 1] : undefined;
}

async function main(): Promise<void> {
  const [command, ...rest] = process.argv.slice(2);
  if (!command) {
    console.log(usage());
    return;
  }

  if (command === "capture") {
    const rawObservation = value(rest, "--raw") ?? "";
    const source = value(rest, "--source") ?? "";
    const session = value(rest, "--session") ?? "";
    const project = value(rest, "--project") ?? "";
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
    console.log(
      JSON.stringify(
        await buildContextPack({
          taskContext: value(rest, "--task") ?? "",
          sessionScope: value(rest, "--session") ?? "",
          projectScope: value(rest, "--project") ?? ""
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
    console.log(JSON.stringify(await cleanMemory(value(rest, "--scope") ?? ""), null, 2));
    return;
  }

  console.error(usage());
  process.exitCode = 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
