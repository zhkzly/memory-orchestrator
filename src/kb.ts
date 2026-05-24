import { promises as fs } from "node:fs";
import path from "node:path";
import type { KnowledgeBaseConfig, MemoryConfig } from "./config.js";

export interface KnowledgeBaseSearchResult {
  knowledgeBase: string;
  path: string;
  title: string;
  excerpt: string;
}

export interface KnowledgeBaseDoctorReport {
  name: string;
  ready: boolean;
  checks: {
    registered: { ok: boolean; detail: string };
    root: { ok: boolean; detail: string };
    api: { ok: boolean; detail: string };
    auth: { ok: boolean; detail: string };
    localFallback: { ok: boolean; detail: string };
  };
  nextActions: string[];
}

interface ApiSearchResult {
  path?: string;
  file?: string;
  title?: string;
  excerpt?: string;
  content?: string;
  snippet?: string;
}

interface LlmWikiSearchPayload {
  tokenHits?: ApiSearchResult[];
  vectorHits?: ApiSearchResult[];
  results?: ApiSearchResult[];
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

export async function doctorKnowledgeBase(
  config: MemoryConfig,
  name: string,
  query = "memory"
): Promise<KnowledgeBaseDoctorReport> {
  const knowledgeBase = (config.knowledgeBases ?? []).find((kb) => kb.name === name);
  if (!knowledgeBase) {
    return {
      name,
      ready: false,
      checks: {
        registered: { ok: false, detail: `knowledge base not found: ${name}` },
        root: { ok: false, detail: "not checked" },
        api: { ok: false, detail: "not checked" },
        auth: { ok: false, detail: "not checked" },
        localFallback: { ok: false, detail: "not checked" }
      },
      nextActions: ["Run memory-orchestrator kb add --name <name> --root <path> [--api <url>]."]
    };
  }
  const rootOk = await directoryReadable(knowledgeBase.root);
  const apiResults = knowledgeBase.api ? await searchLlmWikiApi(knowledgeBase, query, 1) : null;
  const localResults = rootOk ? await searchKnowledgeBaseFiles(knowledgeBase, query, 1) : [];
  const apiOk = Boolean(apiResults?.length);
  const fallbackOk = localResults.length > 0;
  const nextActions: string[] = [];
  if (!rootOk) {
    nextActions.push("Fix the knowledge-base root path or run kb add with the correct --root.");
  }
  if (knowledgeBase.api && !apiOk) {
    nextActions.push("Start LLM Wiki, verify --api points at http://127.0.0.1:19828, and set LLM_WIKI_API_TOKEN if auth is enabled.");
  }
  if (!knowledgeBase.api && !fallbackOk) {
    nextActions.push("Add Markdown files under the knowledge-base root or configure --api.");
  }
  if (knowledgeBase.api && !apiOk && !fallbackOk) {
    nextActions.push("API and local fallback both failed; check the registered root and API configuration.");
  }
  const ready = rootOk && (apiOk || fallbackOk);
  return {
    name,
    ready,
    checks: {
      registered: { ok: true, detail: `${knowledgeBase.type}:${knowledgeBase.name}` },
      root: { ok: rootOk, detail: knowledgeBase.root },
      api: {
        ok: knowledgeBase.api ? apiOk : false,
        detail: knowledgeBase.api ? `${knowledgeBase.api}${apiOk ? " returned results" : " did not return results"}` : "no API configured"
      },
      auth: {
        ok: Boolean(process.env.LLM_WIKI_API_TOKEN),
        detail: process.env.LLM_WIKI_API_TOKEN ? "LLM_WIKI_API_TOKEN is set" : "LLM_WIKI_API_TOKEN is not set"
      },
      localFallback: {
        ok: fallbackOk,
        detail: fallbackOk ? "local Markdown fallback returned results" : "local Markdown fallback returned no results"
      }
    },
    nextActions: ready ? ["Knowledge base is ready for kb search/read and context integration."] : nextActions
  };
}

export async function searchKnowledgeBase(
  config: MemoryConfig,
  name: string,
  query: string,
  limit = 5
): Promise<KnowledgeBaseSearchResult[]> {
  const knowledgeBase = findKnowledgeBase(config, name);
  if (knowledgeBase.api) {
    const apiResults = await searchKnowledgeBaseApi(knowledgeBase, query, limit);
    if (apiResults) {
      return apiResults;
    }
  }
  return searchKnowledgeBaseFiles(knowledgeBase, query, limit);
}

async function directoryReadable(dirPath: string): Promise<boolean> {
  try {
    await fs.access(dirPath);
    return true;
  } catch {
    return false;
  }
}

async function searchKnowledgeBaseFiles(
  knowledgeBase: KnowledgeBaseConfig,
  query: string,
  limit = 5
): Promise<KnowledgeBaseSearchResult[]> {
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
  if (knowledgeBase.api) {
    const apiPage = await readKnowledgeBasePageApi(knowledgeBase, page);
    if (apiPage) {
      return apiPage;
    }
  }
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

async function searchKnowledgeBaseApi(
  knowledgeBase: KnowledgeBaseConfig,
  query: string,
  limit: number
): Promise<KnowledgeBaseSearchResult[] | null> {
  const llmWikiResults = await searchLlmWikiApi(knowledgeBase, query, limit);
  if (llmWikiResults) {
    return llmWikiResults;
  }
  try {
    const url = new URL("/search", knowledgeBase.api);
    url.searchParams.set("query", query);
    url.searchParams.set("limit", String(limit));
    const response = await fetch(url);
    if (!response.ok) {
      return null;
    }
    const payload = (await response.json()) as { results?: ApiSearchResult[] } | ApiSearchResult[];
    const rawResults = Array.isArray(payload) ? payload : payload.results;
    if (!rawResults) {
      return null;
    }
    return normalizeApiSearchResults(knowledgeBase, rawResults, limit);
  } catch {
    return null;
  }
}

async function searchLlmWikiApi(
  knowledgeBase: KnowledgeBaseConfig,
  query: string,
  limit: number
): Promise<KnowledgeBaseSearchResult[] | null> {
  try {
    const url = new URL("/api/v1/projects/current/search", knowledgeBase.api);
    const response = await fetch(url, {
      method: "POST",
      headers: apiHeaders(),
      body: JSON.stringify({ query, limit })
    });
    if (!response.ok) {
      return null;
    }
    const payload = (await response.json()) as LlmWikiSearchPayload | ApiSearchResult[];
    const rawResults = Array.isArray(payload)
      ? payload
      : [...(payload.tokenHits ?? []), ...(payload.vectorHits ?? []), ...(payload.results ?? [])];
    if (rawResults.length === 0) {
      return null;
    }
    return normalizeApiSearchResults(knowledgeBase, rawResults, limit);
  } catch {
    return null;
  }
}

function normalizeApiSearchResults(
  knowledgeBase: KnowledgeBaseConfig,
  rawResults: ApiSearchResult[],
  limit: number
): KnowledgeBaseSearchResult[] {
  return rawResults.slice(0, limit).map((result) => {
    const resultPath = result.path ?? result.file ?? "";
    const resultExcerpt = result.excerpt ?? result.snippet ?? result.content ?? "";
    return {
      knowledgeBase: knowledgeBase.name,
      path: resultPath,
      title: result.title ?? path.basename(resultPath, ".md"),
      excerpt: resultExcerpt.replace(/\s+/g, " ").trim().slice(0, 240)
    };
  });
}

async function readKnowledgeBasePageApi(
  knowledgeBase: KnowledgeBaseConfig,
  page: string
): Promise<{ knowledgeBase: string; path: string; content: string } | null> {
  const llmWikiPage = await readLlmWikiPageApi(knowledgeBase, page);
  if (llmWikiPage) {
    return llmWikiPage;
  }
  try {
    const url = new URL("/read", knowledgeBase.api);
    url.searchParams.set("page", page);
    const response = await fetch(url);
    if (!response.ok) {
      return null;
    }
    const payload = (await response.json()) as { path?: string; content?: string };
    if (!payload.content) {
      return null;
    }
    return {
      knowledgeBase: knowledgeBase.name,
      path: payload.path ?? page,
      content: payload.content
    };
  } catch {
    return null;
  }
}

async function readLlmWikiPageApi(
  knowledgeBase: KnowledgeBaseConfig,
  page: string
): Promise<{ knowledgeBase: string; path: string; content: string } | null> {
  try {
    const url = new URL("/api/v1/projects/current/files/content", knowledgeBase.api);
    url.searchParams.set("path", page);
    const response = await fetch(url, { headers: apiHeaders() });
    if (!response.ok) {
      return null;
    }
    const payload = (await response.json()) as { path?: string; content?: string };
    if (!payload.content) {
      return null;
    }
    return {
      knowledgeBase: knowledgeBase.name,
      path: payload.path ?? page,
      content: payload.content
    };
  } catch {
    return null;
  }
}

function apiHeaders(): HeadersInit {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (process.env.LLM_WIKI_API_TOKEN) {
    headers.authorization = `Bearer ${process.env.LLM_WIKI_API_TOKEN}`;
  }
  return headers;
}
