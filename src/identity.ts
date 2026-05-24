import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";
import type { MemoryConfig } from "./config.js";

const execFileAsync = promisify(execFile);

async function git(args: string[], cwd: string): Promise<string | null> {
  try {
    const { stdout } = await execFileAsync("git", args, { cwd });
    return stdout.trim() || null;
  } catch {
    return null;
  }
}

export function slug(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export async function inferProject(cwd: string, config: MemoryConfig, explicit?: string): Promise<string> {
  if (explicit?.trim()) {
    return slug(explicit);
  }
  if (config.projectConfigPath && config.defaultProject?.trim()) {
    return slug(config.defaultProject);
  }
  const repoRoot = await git(["rev-parse", "--show-toplevel"], cwd);
  if (repoRoot) {
    return slug(path.basename(repoRoot));
  }
  if (config.defaultProject?.trim() && config.vaultRoot && path.resolve(cwd) === path.resolve(config.vaultRoot)) {
    return slug(config.defaultProject);
  }
  return slug(path.basename(path.resolve(cwd))) || "default-project";
}

export async function inferSession(cwd: string, explicit?: string): Promise<string> {
  if (explicit?.trim()) {
    return slug(explicit);
  }
  const branch = await git(["branch", "--show-current"], cwd);
  const day = new Date().toISOString().slice(0, 10);
  return branch ? `${day}-${slug(branch)}` : day;
}
