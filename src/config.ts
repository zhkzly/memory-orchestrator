import { promises as fs } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";

export interface KnowledgeBaseConfig {
  name: string;
  type: "llm_wiki" | "folder";
  root: string;
  api?: string;
  description?: string;
  linkedProjects?: string[];
}

export interface MemoryConfig {
  vaultRoot?: string;
  defaultProject?: string;
  knowledgeBases?: KnowledgeBaseConfig[];
}

const CONFIG_DIR = path.join(homedir(), ".config", "memory-orchestrator");
const CONFIG_PATH = path.join(CONFIG_DIR, "config.json");
const PROJECT_CONFIG = ".memory-orchestrator.json";

async function readJsonFile<T>(filePath: string): Promise<T | null> {
  try {
    return JSON.parse(await fs.readFile(filePath, "utf8")) as T;
  } catch {
    return null;
  }
}

async function findUp(startDir: string, fileName: string): Promise<string | null> {
  let current = path.resolve(startDir);
  while (true) {
    const candidate = path.join(current, fileName);
    try {
      await fs.access(candidate);
      return candidate;
    } catch {
      const parent = path.dirname(current);
      if (parent === current) {
        return null;
      }
      current = parent;
    }
  }
}

export async function readGlobalConfig(): Promise<MemoryConfig> {
  return (await readJsonFile<MemoryConfig>(CONFIG_PATH)) ?? {};
}

export async function writeGlobalConfig(config: MemoryConfig): Promise<string> {
  await fs.mkdir(CONFIG_DIR, { recursive: true });
  await fs.writeFile(CONFIG_PATH, `${JSON.stringify(config, null, 2)}\n`, "utf8");
  return CONFIG_PATH;
}

export async function readProjectConfig(cwd = process.cwd()): Promise<MemoryConfig> {
  const projectConfigPath = await findUp(cwd, PROJECT_CONFIG);
  return projectConfigPath ? ((await readJsonFile<MemoryConfig>(projectConfigPath)) ?? {}) : {};
}

export async function resolveConfig(cwd = process.cwd()): Promise<MemoryConfig> {
  const globalConfig = await readGlobalConfig();
  const projectConfig = await readProjectConfig(cwd);
  return {
    ...globalConfig,
    ...projectConfig,
    knowledgeBases: [...(globalConfig.knowledgeBases ?? []), ...(projectConfig.knowledgeBases ?? [])]
  };
}

export function resolveVaultRoot(config: MemoryConfig, cwd = process.cwd()): string {
  const root = process.env.MEMORY_ORCHESTRATOR_ROOT ?? config.vaultRoot ?? cwd;
  return path.resolve(root);
}

export async function initConfig(input: { vaultRoot: string; defaultProject?: string }): Promise<{ path: string; config: MemoryConfig }> {
  const previous = await readGlobalConfig();
  const config: MemoryConfig = {
    ...previous,
    vaultRoot: path.resolve(input.vaultRoot),
    defaultProject: input.defaultProject ?? previous.defaultProject
  };
  return { path: await writeGlobalConfig(config), config };
}

export async function addKnowledgeBase(input: KnowledgeBaseConfig): Promise<{ path: string; config: MemoryConfig }> {
  const previous = await readGlobalConfig();
  const existing = previous.knowledgeBases ?? [];
  const next = existing.filter((kb) => kb.name !== input.name);
  next.push({
    ...input,
    root: path.resolve(input.root),
    linkedProjects: input.linkedProjects ?? []
  });
  const config: MemoryConfig = { ...previous, knowledgeBases: next };
  return { path: await writeGlobalConfig(config), config };
}

export async function linkKnowledgeBase(input: { name: string; project: string }): Promise<{ path: string; config: MemoryConfig }> {
  const previous = await readGlobalConfig();
  const knowledgeBases = (previous.knowledgeBases ?? []).map((kb) =>
    kb.name === input.name
      ? { ...kb, linkedProjects: [...new Set([...(kb.linkedProjects ?? []), input.project])] }
      : kb
  );
  const config: MemoryConfig = { ...previous, knowledgeBases };
  return { path: await writeGlobalConfig(config), config };
}
