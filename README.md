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

After that, commands infer project and session when possible:

```bash
node dist/cli.js context --task "prepare next session"
```

## Vault Root

Memory files are written under the configured vault root. `MEMORY_ORCHESTRATOR_ROOT` remains an override for scripts and tests.

```bash
node dist/cli.js status
```

## Commands

- `init --vault <path> [--project <default-project>]`
- `status`
- `kb list`
- `kb add --name <name> --root <path> [--type llm_wiki|folder] [--api <url>]`
- `kb link --name <name> --project <project>`
- `kb search --name <name> --query <text>`
- `kb read --name <name> --page <path>`
- `agent codex|claude [project-dir] [--task <text>]`
- `maintain [--task <text>] [--session <scope>] [--project <scope>] [--scope <scope>] [--write-report]`
- `ingest-session --file <path> [--session <scope>] [--project <scope>]`
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

It resolves config, infers project/session, builds a context pack, runs cleanup checks, and reports registered knowledge bases as JSON. It is intentionally read/report-first; use explicit write commands such as `capture` and `promote` for memory changes until transcript ingestion is implemented.

Add `--write-report` to also write a human-readable Markdown report under `reports/` for later Obsidian review.

Use `ingest-session` from a session-end hook or agent task to write a session summary file as an ephemeral candidate memory:

```bash
node dist/cli.js ingest-session --file /path/to/session-summary.md
```

This does not promote the summary into project or personal memory. Promotion remains explicit.

## Knowledge Bases

LLM Wiki projects should be registered as external professional knowledge bases, not imported into the memory vault:

```bash
node dist/cli.js kb add --name memory-research --root /path/to/llm-wiki --type llm_wiki --api http://127.0.0.1:19828
node dist/cli.js kb link --name memory-research --project memory-orchestrator
node dist/cli.js kb search --name memory-research --query "agent memory"
```

When `--api` is configured, `kb search` and `kb read` try the LLM Wiki-style HTTP API first, then fall back to local Markdown files under the registered root if the API is unavailable.

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
