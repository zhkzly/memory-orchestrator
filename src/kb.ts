import { promises as fs } from "node:fs";
import path from "node:path";
import type { KnowledgeBaseConfig, MemoryConfig } from "./config.js";

export interface KnowledgeBaseSearchResult {
  knowledgeBase: string;
  path: string;
  title: string;
  excerpt: string;
}

function findKnowledgeBase(config: MemoryConfig, name: string): KnowledgeBaseConfig {
  const knowledgeBase = (config.knowledgeBases ?? []).find((kb) => kb.name === name);
  if (!knowledgeBase) {
    throw new Error(`Knowledge base not found: ${name}`);
  }
  return knowledgeBase;
}

async function walkMarkdownFiles(root: string): Promise<string[]> {
  const entries = await fs.readdir(root, { withFileTypes: true });
  const files: string[] = [];
  for (const entry of entries) {
    const entryPath = path.join(root, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await walkMarkdownFiles(entryPath)));
    } else if (entry.isFile() && entry.name.endsWith(".md")) {
      files.push(entryPath);
    }
  }
  return files;
}

function titleFromMarkdown(filePath: string, markdown: string): string {
  const heading = markdown.match(/^#\s+(.+)$/m)?.[1];
  return heading ?? path.basename(filePath, ".md");
}

function excerpt(markdown: string, query: string): string {
  const normalized = markdown.replace(/\s+/g, " ").trim();
  const index = normalized.toLowerCase().indexOf(query.toLowerCase());
  if (index < 0) {
    return normalized.slice(0, 240);
  }
  return normalized.slice(Math.max(index - 80, 0), index + query.length + 160);
}

export function listKnowledgeBases(config: MemoryConfig): KnowledgeBaseConfig[] {
  return config.knowledgeBases ?? [];
}

export async function searchKnowledgeBase(
  config: MemoryConfig,
  name: string,
  query: string,
  limit = 5
): Promise<KnowledgeBaseSearchResult[]> {
  const knowledgeBase = findKnowledgeBase(config, name);
  const files = await walkMarkdownFiles(knowledgeBase.root);
  const results: KnowledgeBaseSearchResult[] = [];
  for (const filePath of files) {
    const markdown = await fs.readFile(filePath, "utf8");
    if (!markdown.toLowerCase().includes(query.toLowerCase())) {
      continue;
    }
    results.push({
      knowledgeBase: knowledgeBase.name,
      path: path.relative(knowledgeBase.root, filePath),
      title: titleFromMarkdown(filePath, markdown),
      excerpt: excerpt(markdown, query)
    });
    if (results.length >= limit) {
      break;
    }
  }
  return results;
}

export async function readKnowledgeBasePage(config: MemoryConfig, name: string, page: string): Promise<{
  knowledgeBase: string;
  path: string;
  content: string;
}> {
  const knowledgeBase = findKnowledgeBase(config, name);
  const root = path.resolve(knowledgeBase.root);
  const filePath = path.resolve(root, page);
  if (!filePath.startsWith(root)) {
    throw new Error("Cannot read a page outside the knowledge base root.");
  }
  return {
    knowledgeBase: knowledgeBase.name,
    path: path.relative(root, filePath),
    content: await fs.readFile(filePath, "utf8")
  };
}
