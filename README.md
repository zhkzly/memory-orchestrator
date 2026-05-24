# Memory Orchestrator

Memory Orchestrator is a CLI-first local memory system for agent workflows. It captures candidate memories, verifies them against evidence, promotes durable items into a Markdown vault, builds task context packs, scores memory-system quality with rubric proxies, and marks stale or unsafe memory records for cleanup.

The CLI is the canonical interface. Harnesses, agent wrappers, cron jobs, and session hooks should call the same commands instead of owning memory policy. Skills are included as optional instructions for agents that need a human-readable workflow layer, but they do not own policy.

## Status

This is an early implementation scaffold. It is useful for local experiments and agent workflow prototyping, but it is not yet a stable package API.

## Install

```bash
npm install
npm run build
```

Configure the memory vault once:

```bash
npm run dev -- init --vault /path/to/obsidian-vault --project memory-orchestrator
```

Optionally bind a repository to a stable project name once:

```bash
node dist/cli.js init-project --project current-project
```

After that, commands infer project and session when possible:

```bash
node dist/cli.js context --task "prepare next session"
```

Check whether the current project is ready for agent use:

```bash
node dist/cli.js doctor
```

`doctor` verifies the vault root, project-local config, context generation, agent harness entrypoint, and `session-end` hook readiness. If a project is not bound yet, it returns the exact `init-project` action to run.

## Vault Root

Memory files are written under the configured vault root. `MEMORY_ORCHESTRATOR_ROOT` remains an override for scripts and tests.

```bash
node dist/cli.js status
```

## Commands

- `init --vault <path> [--project <default-project>]`
- `init-project [--project <project>] [--vault <path>]`
- `status`
- `doctor [--task <text>] [--session <scope>] [--project <scope>]`
- `kb list`
- `kb add --name <name> --root <path> [--type llm_wiki|folder] [--api <url>]`
- `kb link --name <name> --project <project>`
- `kb search --name <name> --query <text>`
- `kb read --name <name> --page <path>`
- `agent codex|claude [project-dir] [--task <text>]`
- `maintain [--task <text>] [--session <scope>] [--project <scope>] [--scope <scope>] [--write-report]`
- `ui [--host <host>] [--port <port>]`
- `ingest-session --file <path> [--session <scope>] [--project <scope>]`
- `summarize-session --file <path> [--out <path>] [--ingest] [--session <scope>] [--project <scope>]`
- `session-end (--transcript <path> | --summary <path>) [--task <text>] [--write-report]`
- `capture --raw <text> --source <source> [--session <session>] [--project <project>]`
- `classify --candidate <json>`
- `verify --candidate <json> --evidence <json-array>`
- `write --item <json>`
- `promote --item <json>`
- `context --task <text> [--session <scope>] [--project <scope>]`
- `rubric --definition <text> --evidence <json-array> --system <text> --proxies <json-array>`
- `score --rubric <file> --evidence <file> --out <file>`
- `clean --scope <scope>`

## Skills

The `skills/` directory describes suggested agent roles:

- extractor
- verifier
- writer
- context builder
- rubric scorer
- cleaner

Use them as instructions for models or wrappers. The CLI remains the source of behavior.

## Codex Wrapper

`examples/codex-memory` shows the intended pattern after one-time config:

```bash
memory-orchestrator init --vault /path/to/vault --project memory-orchestrator
./examples/codex-memory /path/to/project
```

It starts Codex with the configured vault and project directory added explicitly.

`examples/claude-memory` uses the same config but launches Claude Code:

```bash
./examples/claude-memory /path/to/project
```

Both wrappers call `memory-orchestrator agent`, which injects `MEMORY_ORCHESTRATOR_ROOT`, `MEMORY_ORCHESTRATOR_PROJECT`, `MEMORY_ORCHESTRATOR_SESSION`, and `MEMORY_ORCHESTRATOR_CONTEXT` into the agent environment.

Wrappers are optional. Codex and Claude can also call `memory-orchestrator` commands directly during a session.

## Maintenance Automation

Use `maintain` as the first schedulable automation surface:

```bash
node dist/cli.js maintain --task "daily memory maintenance"
```

It resolves config, infers project/session, builds a context pack, runs cleanup checks, and reports registered knowledge bases as JSON. It is intentionally read/report-first; use explicit write commands such as `capture`, `promote`, `ingest-session`, or `summarize-session --ingest` for memory changes.

Add `--write-report` to also write a human-readable Markdown report under `reports/` for later Obsidian review.

Start a local review UI:

```bash
node dist/cli.js ui
```

The UI binds to `127.0.0.1` by default and exposes status, knowledge-base registry, maintenance reports, and safe knowledge-base add/link actions. It is a review/configuration aid, not the policy owner.

Use `ingest-session` from a session-end hook or agent task to write a session summary file as an ephemeral candidate memory:

```bash
node dist/cli.js ingest-session --file /path/to/session-summary.md
```

This does not promote the summary into project or personal memory. Promotion remains explicit.

Use `summarize-session` when a session hook has a transcript rather than a prepared summary:

```bash
node dist/cli.js summarize-session --file /path/to/transcript.md --ingest
```

The first-pass summarizer is deterministic. It extracts only explicit `Decision:`, `TODO:`, `Evidence:`, `Open Question:`, and `Note:` lines into a Markdown session summary, then `--ingest` stores that summary as ephemeral session memory. It does not call an LLM or infer durable project facts on its own.

Use `session-end` as the preferred hook command when an agent or wrapper finishes a session:

```bash
node dist/cli.js session-end --transcript /path/to/transcript.md --task "session-end" --write-report
```

It infers the project/session, summarizes a transcript or ingests a prepared summary, writes ephemeral session memory, runs cleanup checks, and optionally writes a maintenance report. This is the intended place for Codex, Claude, cron, or shell hooks to integrate without owning memory policy.

## Knowledge Bases

LLM Wiki projects should be registered as external professional knowledge bases, not imported into the memory vault:

```bash
export LLM_WIKI_API_TOKEN=<token-from-llm-wiki>
node dist/cli.js kb add --name memory-research --root /path/to/llm-wiki --type llm_wiki --api http://127.0.0.1:19828
node dist/cli.js kb link --name memory-research --project memory-orchestrator
node dist/cli.js kb search --name memory-research --query "agent memory"
```

When `--api` is configured, `kb search` and `kb read` try the LLM Wiki local HTTP API first:

- `POST /api/v1/projects/current/search`
- `GET /api/v1/projects/current/files/content?path=<page>`

If `LLM_WIKI_API_TOKEN` is set, the CLI sends it as a bearer token. If the API is unavailable, commands fall back to local Markdown files under the registered root.

When a knowledge base is linked to the active project, `context`, `maintain`, and `agent` include concise task-matching knowledge-base excerpts in the generated context pack. They do not import the whole wiki.

Context packs also include concise inline excerpts from matching memory items. Inline memory is ranked by task term matches, verified status, confidence, and recency, then limited to three entries to keep context bounded. Use `write` for candidate or session memory that should remain visible without being promoted, and use `promote` only for verified durable memory.

Generated memory files keep machine-readable frontmatter, then include human-readable sections such as `## Claim`, `## Metadata`, `## Provenance`, and `## Suggested Maintenance` so the vault can be reviewed and edited directly.

## MCP

The MCP adapter wraps the same core operations:

```bash
npm run mcp
```

Use MCP only when the client needs it. Do not make MCP the policy owner.

## Verification

Run the full local check:

```bash
npm run harness
```

The harness builds the TypeScript project, runs a score report, promotes a verified evidence item into a temporary vault, and verifies cleanup markers.

## Repository Policy

- Do not commit `node_modules/` or `dist/`.
- Keep durable memory data outside this repository.
- Keep vault-specific AGENTS instructions in the vault, not in this package.
- Add licenses and npm publishing metadata only after the repository owner decides the distribution model.
