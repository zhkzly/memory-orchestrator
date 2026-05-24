import { promises as fs } from "node:fs";
import { createHash } from "node:crypto";
import path from "node:path";
import type { MemoryItem } from "./types.js";

const ROOT_DIR = process.env.MEMORY_ORCHESTRATOR_ROOT ?? process.cwd();

function memoryFilePath(item: MemoryItem): string {
  const folder =
    item.kind === "personal"
      ? "people"
      : item.kind === "project"
        ? "projects"
        : item.kind === "evidence"
          ? "notes"
          : "sessions";
  return path.join(ROOT_DIR, folder, `${item.id}.md`);
}

function serializeItem(item: MemoryItem): string {
  return `---\n${JSON.stringify(item, null, 2)}\n---\n\n${item.content}\n`;
}

function parseItemFromMarkdown(markdown: string): MemoryItem | null {
  const match = markdown.match(/^---\n([\s\S]*?)\n---\n\n([\s\S]*)$/);
  if (!match) {
    return null;
  }
  try {
    const item = JSON.parse(match[1]) as MemoryItem;
    item.content = match[2].replace(/\n$/, "");
    return item;
  } catch {
    return null;
  }
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
  const filePath = memoryFilePath(item);
  await ensureDir(filePath);
  await fs.writeFile(filePath, serializeItem(item), "utf8");
  return filePath;
}

export async function readMemoryItem(pathname: string): Promise<string> {
  return fs.readFile(pathname, "utf8");
}

export async function listMemoryFiles(scope: string): Promise<string[]> {
  const candidates = ["people", "projects", "notes", "sessions", "rubrics"].map((folder) =>
    path.join(ROOT_DIR, folder, `${scope}.md`)
  );
  const existing: string[] = [];
  for (const filePath of candidates) {
    try {
      await fs.access(filePath);
      existing.push(filePath);
    } catch {
      // ignore missing files
    }
  }
  return existing;
}

export async function listAllMemoryFiles(): Promise<string[]> {
  const roots = ["people", "projects", "notes", "sessions", "rubrics"].map((folder) => path.join(ROOT_DIR, folder));
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
  const filePath = path.isAbsolute(relativeOrAbsolutePath)
    ? relativeOrAbsolutePath
    : path.join(ROOT_DIR, relativeOrAbsolutePath);
  try {
    const content = await fs.readFile(filePath);
    return createHash("sha256").update(content).digest("hex");
  } catch {
    return null;
  }
}
