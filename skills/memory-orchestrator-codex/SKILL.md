---
name: memory-orchestrator-codex
description: Use when Codex is working in a project that should use the local Memory Orchestrator CLI for layered context, session capture, vault controller maintenance, or external knowledge-base lookup.
---

# Memory Orchestrator for Codex

Use this skill when a project relies on `memory-orchestrator` for long-term memory.

## Start Of Work

1. Resolve the vault:
   - Prefer `MEMORY_ORCHESTRATOR_ROOT` if set.
   - Otherwise run `memory-orchestrator status`.
   - If unconfigured, ask the user for the vault path and run `memory-orchestrator init --vault <path>`.
2. Get task context:
   - Run `memory-orchestrator memory-policy` if you need to confirm each memory type's load/write/retrieval rules.
   - Run `memory-orchestrator context --task "<current task>"`.
   - Read the returned sections by type:
     - `always_loaded`: long-term user profile and stable preferences; treat as always relevant unless contradicted.
     - `project_core`: current project facts and rules; load before task-specific memories.
     - `retrieved`: task-matched durable project/evidence items.
     - `session_memory`: recent or task-matched ephemeral session material; do not treat as permanent truth.
     - `evidence_memory`: source-backed facts or citations; prefer these over unsourced memories.
     - `knowledge_bases`: external KB excerpts such as LLM Wiki; do not import the whole KB.

## During Work

- Use `memory-orchestrator kb search/read` for linked professional knowledge bases.
- Use `memory-orchestrator capture` or `write` only for candidate/session material.
- Do not directly promote personal or project memory from a single observation.
- Treat session memory as scratchpad unless later verified.

## End Of Work

If a transcript or summary file exists, run:

```bash
memory-orchestrator session-end --transcript <path> --controller-event --controller-report
```

If only a prepared summary exists, use:

```bash
memory-orchestrator session-end --summary <path> --controller-event --controller-report
```

## Maintenance

- Use `memory-orchestrator controller --trigger manual --write-report` for an explicit vault pass.
- Use `memory-orchestrator controller-feedback` to inspect recent deterministic feedback.
- Use controller recommendations as review inputs, not as permission to rewrite durable memory silently.

## Safety

- Never store secrets, API keys, passwords, or recovery codes.
- Never rewrite durable `people/`, `projects/`, or `notes/` memory without evidence or explicit user approval.
- LLM Wiki is an external professional knowledge source, not the personal/project memory store.
