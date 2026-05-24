import { promises as fs } from "node:fs";
import { createHash } from "node:crypto";
import path from "node:path";
import { resolveConfig, resolveVaultRoot } from "./config.js";
import type { MemoryItem } from "./types.js";

async function rootDir(): Promise<string> {
  return resolveVaultRoot(await resolveConfig(process.cwd()));
}

async function memoryFilePath(item: MemoryItem): Promise<string> {
  const folder =
    item.kind === "personal"
      ? "people"
      : item.kind === "project"
        ? "projects"
        : item.kind === "evidence"
        ? "notes"
          : "sessions";
  return path.join(await rootDir(), folder, `${item.id}.md`);
}

function serializeItem(item: MemoryItem): string {
  const title = `${item.kind[0].toUpperCase()}${item.kind.slice(1)} Memory: ${item.id}`;
  const provenance = item.provenance.map((source) => `- ${source.type}: ${source.ref}`).join("\n") || "- none";
  const references = (item.references ?? []).map((reference) => `- ${reference}`).join("\n") || "- none";
  const maintenance =
    item.kind === "session"
      ? "Keep ephemeral unless a later review promotes a supported project or evidence item."
      : item.status === "candidate"
        ? "Review evidence and either promote, revise, or leave as candidate."
        : "Keep while accurate; mark outdated if the project direction or source changes.";
  return [
    "---",
    JSON.stringify(item, null, 2),
    "---",
    "",
    `# ${title}`,
    "",
    "## Claim",
    "",
    item.content,
    "",
    "## Metadata",
    "",
    `- kind: ${item.kind}`,
    `- scope: ${item.scope}`,
    `- status: ${item.status}`,
    `- confidence: ${item.confidence}`,
    item.confidence_rationale ? `- confidence rationale: ${item.confidence_rationale}` : "- confidence rationale: none",
    `- source: ${item.source}`,
    "",
    "## Provenance",
    "",
    provenance,
    "",
    "## References",
    "",
    references,
    "",
    "## Suggested Maintenance",
    "",
    maintenance,
    ""
  ].join("\n");
}

function parseItemFromMarkdown(markdown: string): MemoryItem | null {
  const match = markdown.match(/^---\n([\s\S]*?)\n---\n\n([\s\S]*)$/);
  if (!match) {
    return null;
  }
  try {
    const item = JSON.parse(match[1]) as MemoryItem;
    item.content = claimFromBody(match[2]) ?? item.content;
    return item;
  } catch {
    return null;
  }
}

function claimFromBody(body: string): string | null {
  const match = body.match(/## Claim\n\n([\s\S]*?)(?=\n## Metadata\n|\s*$)/);
  return match ? match[1].trim() : null;
}

async function ensureDir(filePath: string): Promise<void> {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
}

async function walkMarkdownFiles(dir: string): Promise<string[]> {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  const files: string[] = [];
  for (const entry of entries) {
    const entryPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await walkMarkdownFiles(entryPath)));
    } else if (entry.isFile() && entry.name.endsWith(".md")) {
      files.push(entryPath);
    }
  }
  return files;
}

export async function writeMemoryItem(item: MemoryItem): Promise<string> {
  const filePath = await memoryFilePath(item);
  await ensureDir(filePath);
  await fs.writeFile(filePath, serializeItem(item), "utf8");
  return filePath;
}

export async function readMemoryItem(pathname: string): Promise<string> {
  return fs.readFile(pathname, "utf8");
}

export async function listMemoryFiles(scope: string): Promise<string[]> {
  const root = await rootDir();
  const candidates = ["people", "projects", "notes", "sessions", "rubrics"].map((folder) =>
    path.join(root, folder, `${scope}.md`)
  );
  const existing = new Set<string>();
  for (const filePath of candidates) {
    try {
      await fs.access(filePath);
      existing.add(filePath);
    } catch {
      // ignore missing files
    }
  }
  for (const filePath of await listAllMemoryFiles()) {
    const item = await loadMemoryItem(filePath);
    if (item?.scope.includes(scope)) {
      existing.add(filePath);
    }
  }
  return [...existing];
}

export async function listAllMemoryFiles(): Promise<string[]> {
  const root = await rootDir();
  const roots = ["people", "projects", "notes", "sessions", "rubrics"].map((folder) => path.join(root, folder));
  const files: string[] = [];
  for (const root of roots) {
    try {
      files.push(...(await walkMarkdownFiles(root)));
    } catch {
      // ignore missing directories
    }
  }
  return files;
}

export async function listAllMemoryItems(): Promise<Array<{ filePath: string; item: MemoryItem }>> {
  const items: Array<{ filePath: string; item: MemoryItem }> = [];
  for (const filePath of await listAllMemoryFiles()) {
    const item = await loadMemoryItem(filePath);
    if (item) {
      items.push({ filePath, item });
    }
  }
  return items;
}

export async function loadMemoryItem(filePath: string): Promise<MemoryItem | null> {
  try {
    const markdown = await fs.readFile(filePath, "utf8");
    return parseItemFromMarkdown(markdown);
  } catch {
    return null;
  }
}

export async function saveMemoryItem(filePath: string, item: MemoryItem): Promise<void> {
  await fs.writeFile(filePath, serializeItem(item), "utf8");
}

export async function touchMemoryFiles(filePaths: string[]): Promise<void> {
  const seen = new Set(filePaths);
  for (const filePath of seen) {
    const item = await loadMemoryItem(filePath);
    if (!item) {
      continue;
    }
    item.retrieval_count = (item.retrieval_count ?? 0) + 1;
    item.last_retrieved_at = new Date().toISOString();
    item.updated_at = item.last_retrieved_at;
    await saveMemoryItem(filePath, item);
  }
}

export async function hashFileContents(relativeOrAbsolutePath: string): Promise<string | null> {
  const root = await rootDir();
  const filePath = path.isAbsolute(relativeOrAbsolutePath)
    ? relativeOrAbsolutePath
    : path.join(root, relativeOrAbsolutePath);
  try {
    const content = await fs.readFile(filePath);
    return createHash("sha256").update(content).digest("hex");
  } catch {
    return null;
  }
}
