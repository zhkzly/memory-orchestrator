import path from "node:path";
import { fileURLToPath } from "node:url";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import {
  buildContextPack,
  captureCandidate,
  classifyCandidate,
  cleanMemory,
  evaluateRubric,
  promoteItem,
  verifyCandidate
} from "./core.js";
import { memoryItemSchema, rubricProxySchema } from "./schemas.js";

const server = new McpServer({
  name: "memory-orchestrator",
  version: "0.1.0"
});

function asJsonText(data: unknown): Array<{ type: "text"; text: string }> {
  return [{ type: "text", text: JSON.stringify(data, null, 2) }];
}

server.tool(
  "capture_candidate",
  {
    rawObservation: z.string(),
    source: z.string(),
    session: z.string(),
    project: z.string()
  },
  async (input) => ({ content: asJsonText({ ok: true, data: await captureCandidate(input) }) })
);

server.tool("classify_candidate", { candidate: memoryItemSchema }, async ({ candidate }) => ({
  content: asJsonText({ ok: true, data: await classifyCandidate(candidate) })
}));

server.tool(
  "verify_candidate",
  {
    candidate: memoryItemSchema,
    evidence: z.array(z.string())
  },
  async ({ candidate, evidence }) => ({
    content: asJsonText({ ok: true, data: await verifyCandidate(candidate, evidence) })
  })
);

server.tool("promote_item", { item: memoryItemSchema }, async ({ item }) => ({
  content: asJsonText({ ok: true, data: await promoteItem(item) })
}));

server.tool(
  "build_context_pack",
  {
    taskContext: z.string(),
    sessionScope: z.string(),
    projectScope: z.string()
  },
  async (input) => ({ content: asJsonText({ ok: true, data: await buildContextPack(input) }) })
);

server.tool(
  "evaluate_rubric",
  {
    rubricDefinition: z.string(),
    evidenceSet: z.array(z.string()),
    candidateSystem: z.string(),
    proxies: z.array(rubricProxySchema)
  },
  async (input) => ({ content: asJsonText({ ok: true, data: await evaluateRubric(input) }) })
);

server.tool("clean_memory", { targetScope: z.string() }, async ({ targetScope }) => ({
  content: asJsonText({ ok: true, data: await cleanMemory(targetScope) })
}));

async function main(): Promise<void> {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

const isMainModule = fileURLToPath(import.meta.url) === path.resolve(process.argv[1] ?? "");
if (isMainModule) {
  main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}
