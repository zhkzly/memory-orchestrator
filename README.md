# Memory Orchestrator

Memory Orchestrator is a CLI-first local memory system for agent workflows. It captures candidate memories, verifies them against evidence, promotes durable items into a Markdown vault, builds task context packs, scores memory-system quality with rubric proxies, and marks stale or unsafe memory records for cleanup.

The CLI is the canonical interface. Skills are included as optional instructions for agents that need a human-readable workflow layer, but they do not own policy.

## Status

This is an early implementation scaffold. It is useful for local experiments and agent workflow prototyping, but it is not yet a stable package API.

## Install

```bash
npm install
npm run build
```

Run commands from the repository root during development:

```bash
npm run dev -- capture --raw "Project prefers CLI-first memory updates" --source notes/source.md --session 2026-05-24 --project memory
```

After build, run the compiled CLI:

```bash
node dist/cli.js context --task "prepare next session" --session memory --project memory
```

## Vault Root

Memory files are written under `MEMORY_ORCHESTRATOR_ROOT` when set, otherwise under the current working directory.

```bash
MEMORY_ORCHESTRATOR_ROOT=/path/to/obsidian-vault node dist/cli.js context --task "next task" --session daily --project memory
```

## Commands

- `capture --raw <text> --source <source> --session <session> --project <project>`
- `classify --candidate <json>`
- `verify --candidate <json> --evidence <json-array>`
- `promote --item <json>`
- `context --task <text> --session <scope> --project <scope>`
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

`examples/codex-memory` shows the intended pattern:

```bash
MEMORY_ORCHESTRATOR_ROOT=/path/to/vault ./examples/codex-memory /path/to/vault
```

It starts Codex with the vault added as an explicit directory and points this CLI at the same vault.

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
