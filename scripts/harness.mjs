import { execFile } from "node:child_process";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
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
const sourcePath = path.join(vaultRoot, "source.md");
await writeFile(sourcePath, "Evidence source for the harness.\n", "utf8");

await run("npm", ["run", "build"]);

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

const now = new Date().toISOString();
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
  { env: { ...process.env, MEMORY_ORCHESTRATOR_ROOT: vaultRoot } }
);
const promoted = JSON.parse(promoteOutput);
assert(promoted.path.endsWith("notes/harness-evidence.md"), "Expected evidence item to be written under notes.");

const cleanOutput = await run(
  "node",
  ["dist/cli.js", "clean", "--scope", "memory"],
  { env: { ...process.env, MEMORY_ORCHESTRATOR_ROOT: vaultRoot } }
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
