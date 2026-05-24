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

`doctor` verifies the vault root, context generation, agent harness entrypoint, and `session-end` hook readiness. A project-local config is optional, not required. If a checkout is not pinned yet, it still works and will suggest `init-project` only as a later convenience.

Inspect the memory type policy:

```bash
memory-orchestrator memory-policy
```

This returns the machine-readable meaning, load policy, write policy, retrieval policy, and safe-apply boundary for `personal`, `project`, `evidence`, and `session` memory.

Query one memory layer through that policy:

```bash
memory-orchestrator memory-query --kind personal
memory-orchestrator memory-query --kind project --task "current task"
memory-orchestrator memory-query --kind session --task "current task"
memory-orchestrator memory-query --kind evidence --task "LLM Wiki"
```

`memory-query` returns bounded JSON with the selected kind's policy metadata plus matching excerpts. Durable `personal`, `project`, and `evidence` queries return verified items; `session` queries can return candidate scratchpad items.

## Layered Context

`context` returns a layered context pack rather than one undifferentiated search result:

```bash
memory-orchestrator context --task "current task"
```

The sections have different memory semantics:

- `always_loaded`: verified personal/user model memory. This is loaded across projects and should stay compact.
- `project_core`: verified current-project memory. This carries project rules, decisions, and stable status.
- `retrieved`: task-matched durable project/evidence memory, ranked by lexical task matches, verified status, confidence, and recency.
- `session_memory`: task-matched ephemeral session memory. This is useful scratchpad context, not permanent truth.
- `evidence_memory`: task-matched evidence records and source-backed facts.
- `knowledge_bases`: concise linked external KB excerpts added by the knowledge-base bridge.

This split is intentional: long-term user/profile memory is loaded directly, while session memory is retrieved by relevance and age.

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
- `kb doctor --name <name> [--query <text>]`
- `kb search --name <name> --query <text>`
- `kb read --name <name> --page <path>`
- `agent codex|claude [project-dir] [--task <text>]`
- `maintain [--task <text>] [--session <scope>] [--project <scope>] [--scope <scope>] [--write-report]`
- `review [--scope <scope>] [--days <n>] [--session <scope>] [--project <scope>]`
- `memory-policy`
- `memory-query --kind personal|project|evidence|session [--task <text>] [--limit <n>] [--session <scope>] [--project <scope>]`
- `harness [--task <text>] [--scope <scope>] [--days <n>] [--write-report]`
- `controller [--trigger scheduled|event|manual] [--policy <file>] [--write-report] [--write-review-artifacts] [--write-feedback] [--write-reinforcement] [--write-proposals] [--apply-safe]`
- `controller-apply --proposal <id>`
- `controller-feedback [--limit <n>] [--min-score <n>]`
- `controller-policy init|show [--force] [--model-provider <name>] [--model-name <name>]`
- `controller-reflection [--limit <n>] [--write-report]`
- `controller-review ingest|show [--file <path>] [--reviewer <name>] [--limit <n>]`
- `controller-schedule [--format cron|systemd|launchd|windows-task] [--time HH:MM] [--policy <file>] [--write-report] [--write-review-artifacts] [--write-feedback] [--write-reinforcement] [--apply-safe]`
- `ui [--host <host>] [--port <port>]`
- `ingest-session --file <path> [--session <scope>] [--project <scope>]`
- `summarize-session --file <path> [--out <path>] [--ingest] [--session <scope>] [--project <scope>]`
- `session-end (--transcript <path> | --summary <path>) [--task <text>] [--write-report] [--controller-event] [--controller-policy <file>] [--controller-report] [--controller-review-artifacts] [--controller-feedback] [--controller-reinforcement] [--controller-apply-safe]`
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
- Codex workflow integration

Use them as instructions for models or wrappers. The CLI remains the source of behavior. The `memory-orchestrator-codex` skill is the recommended cross-project instruction layer: it tells Codex to load layered context at the start of work, use `kb search/read` for external knowledge, and run `session-end --controller-event` at the end of work.

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

Use `review` a few days later to list session memories, session items nearing expiry, and matching maintenance reports for a scope:

```bash
node dist/cli.js review --scope memory-orchestrator --days 7
```

This command is intentionally read-only. It is the CLI path for post-hoc human review: inspect the listed session files and reports in Obsidian, then edit or promote only what still deserves to become durable project/evidence memory.

Start a local review UI:

```bash
node dist/cli.js ui --cwd /path/to/project
```

The UI binds to `127.0.0.1` by default and exposes status, project initialization, knowledge-base registry, maintenance reports, and safe knowledge-base add/link actions. It is a review/configuration aid, not the policy owner.

Use `harness` when an external scheduler, Codex workflow, Claude workflow, or shell wrapper needs one stable memory-system health and context entrypoint:

```bash
node dist/cli.js harness --task "daily memory maintenance" --scope memory-orchestrator --days 7 --write-report
```

The harness command composes `doctor`, `maintain`, `review`, and `controller`. It reports readiness, task-aware context, cleanup markers, registered knowledge bases, vault-level controller signals, expiring session memory, and optional report paths in one JSON response. It is still read/report-first; it does not turn the memory system into an autonomous background agent.

It also includes a structure score from `evaluation/structure-rubric.json`, which keeps memory-architecture quality separate from daily usability scoring.

Use `controller` as the vault-level governance surface when you want an independent pass over the whole vault:

```bash
node dist/cli.js controller --trigger scheduled --write-report
```

The controller is intentionally vault-scoped rather than project-scoped. It scans memory items across the vault, reports time-based expiry, reinforcement/decay, length-budget pressure, near-duplicates, deterministic contradiction markers, cleanup markers, and structure-rubric feedback, then writes a vault-level report when requested. It also classifies findings into `keep`, `decay`, `consolidate`, `review`, and `expire` recommendations. Codex may trigger it, especially after `session-end`, promotion, or knowledge-base link events, but it should be treated as an independent maintenance pass, not as the current task's memory policy.

Use `--policy <file>` to give the controller its own deterministic maintenance policy:

```json
{
  "staleDays": 30,
  "expiringSoonDays": 7,
  "duplicateThreshold": 0.72,
  "ttlDays": {
    "personal": 3650,
    "project": 365,
    "evidence": 1825,
    "session": 7
  },
  "lengthBudgets": {
    "personal": 12000,
    "project": 16000,
    "evidence": 20000,
    "session": 8000
  },
  "fileLengthBudgets": {
    "people": 20000,
    "projects": 24000,
    "notes": 20000,
    "sessions": 12000
  },
  "model": { "provider": "none", "name": "deterministic-only" }
}
```

The `model` block is recorded as controller configuration for later LLM review support. The current controller does not call a model.

Use `controller-policy init` to create the vault-owned default policy at `agent/controller-policy.json`:

```bash
node dist/cli.js controller-policy init --model-provider none --model-name deterministic-only
node dist/cli.js controller-policy show
```

When `controller` runs without `--policy`, it checks this vault-owned policy file before falling back to built-in defaults. This makes controller thresholds and model-review metadata part of the vault maintenance system rather than project-local Codex configuration.

`ttlDays` is a per-layer time policy. It lets the controller flag memory that has exceeded its expected lifetime even when a file does not have an explicit `expires_at`.

`lengthBudgets` applies to structured memory item content.
`fileLengthBudgets` applies to actual Markdown files in vault layers such as `people/`, `projects/`, `notes/`, and `sessions/`.
Oversized Markdown files are reported under `budgets.oversizedFiles` and become structured `budget` review items with reason `file-length-budget`.

Add `--apply-safe` only when the controller should perform bounded deterministic maintenance. The first safe action marks expired session memory as `outdated` with a traceable controller rationale. It does not rewrite personal, project, or evidence memory.

The controller also emits a deterministic feedback score plus a review prompt. That prompt is meant for an external model or human reviewer to inspect, not for the controller itself to execute.

Add `--write-feedback` to append a compact JSONL record to `agent/controller-feedback.jsonl`:

```bash
node dist/cli.js controller --trigger scheduled --write-feedback
```

Each line records trigger, mode, policy source, deterministic score, structure score, item count, recommendation counts, and report/review artifact paths. This creates a vault-owned feedback history for trend review and policy tuning without making an LLM the hidden evaluator.

Add `--write-reinforcement` to append reinforce/decay candidates to `agent/controller-reinforcement.jsonl`:

```bash
node dist/cli.js controller --trigger scheduled --write-reinforcement
```

This is review-only. It records frequently retrieved verified memory and decay candidates for later human or model review, but it does not automatically rewrite durable memory or promote a claim.

Use `controller-feedback` to summarize that JSONL history:

```bash
node dist/cli.js controller-feedback --limit 20 --min-score 0.7
```

It reports the latest run, average deterministic and structure scores, score deltas across the selected window, and threshold alerts such as `below_min_score`. This is the hard-code feedback path for trend checks; model review can consume the same log later, but is not required for basic evaluation.

Use `controller-reflection` to combine feedback and reinforcement history into a review-only reflection packet:

```bash
node dist/cli.js controller-reflection --limit 20 --write-report
```

It produces a reflection prompt, review questions, feedback trend summary, reinforcement summary, and an optional `reports/controller-reflection-*.md` file. This is the controller's periodic reflection surface; it prepares review material but still does not execute model rewrites.

Use `controller-review ingest` to record an external human or model review result:

```bash
node dist/cli.js controller-review ingest --file /path/to/review.json --reviewer external-model
node dist/cli.js controller-review show --limit 20
```

The review JSON can include fields such as `decision`, `confidence`, `findings`, and `actions`. The command appends the record to `agent/controller-review-feedback.jsonl` with `safety: "record-only"`. It does not execute suggested actions.

Use `--write-review-artifacts` to write a focused Markdown artifact under `reports/` for human or external-model review of `consolidate`, `review`, `decay`, and `expire` recommendations. This artifact is an input for later curation; it is not an auto-merge or auto-rewrite plan.

Use `--write-proposals` when controller findings should become evaluated optimization proposals:

```bash
memory-orchestrator controller --trigger scheduled --write-report --write-proposals
```

This appends machine-readable entries to:

- `agent/controller-proposals.jsonl`
- `agent/controller-evaluations.jsonl`

Each proposal has a risk level, targets, sources, rationale, action, review requirement, and reversibility flag. Each evaluation uses the built-in `memory-optimization-safety` rubric. Low-risk reversible session maintenance can be applied automatically after evaluation; durable memory changes remain review-first.

Apply a safe evaluated proposal explicitly:

```bash
memory-orchestrator controller-apply --proposal <proposal-id>
```

Current safe apply scope is narrow: evaluated expired-session proposals can mark session memory `outdated`. Durable `people/`, `projects/`, and `notes/` rewrites are proposed and evaluated, but not silently applied.

The controller also emits structured `consolidationCandidates` with the candidate ids, similarity score when available, reason, and `review-merge` action. These candidates make consolidation inspectable without allowing automatic durable memory merges.

The controller also emits structured `reviewItems` for issues such as references, source integrity, rubric scores, budget pressure, stale items, and decay candidates. Each item includes a type, target, reason, and `inspect` or `review` action.

Cleanup also includes a conservative `direct_contradiction:` marker for matching `must/should ...` versus `must not/should not ...` claims inside the same kind, scope, and semantic tag. These become `direct-contradiction-marker` consolidation candidates for review. This is deterministic and intentionally narrow; it does not replace model or human contradiction review.

Use `controller-schedule` to generate an installable daily scheduler snippet without letting a project-local agent own the schedule:

```bash
memory-orchestrator controller-schedule --format cron --time 03:30 --policy /path/to/controller-policy.json --write-report --write-feedback --write-reinforcement
memory-orchestrator controller-schedule --format systemd --time 03:30 --write-report
memory-orchestrator controller-schedule --format launchd --time 03:30 --write-report
memory-orchestrator controller-schedule --format windows-task --time 03:30 --write-report
```

This command only prints scheduler configuration and shell commands. It does not install anything by itself. The generated output includes a stable `scheduleId`, an `installCommand`, and an `uninstallCommand`, so a scheduled controller pass can be added, replaced, or removed deliberately.

Supported scheduler formats:

- `cron` for Unix/Linux cron.
- `systemd` for Linux user systemd timers.
- `launchd` for macOS LaunchAgents.
- `windows-task` for Windows Task Scheduler through `schtasks`.

The generated command pins `MEMORY_ORCHESTRATOR_ROOT` to the resolved vault root and runs `controller --trigger scheduled`, so scheduled maintenance remains vault-scoped and independent of whichever project happens to be active.

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

If you want that same hook to trigger the vault-level controller, add `--controller-event`:

```bash
node dist/cli.js session-end --transcript /path/to/transcript.md --controller-event --controller-report
```

That path triggers the independent vault maintenance loop after the session is captured. It is still a vault-level pass, not a project-local memory policy override. Optional controller flags let wrappers forward a policy file or request review artifacts without moving the policy owner into the session workflow.

Session memory is intentionally short-lived: ingest and session-end outputs currently expire after 7 days so scratchpad material does not silently become permanent project history.

## Knowledge Bases

LLM Wiki projects should be registered as external professional knowledge bases, not imported into the memory vault:

```bash
export LLM_WIKI_API_TOKEN=<token-from-llm-wiki>
node dist/cli.js kb add --name memory-research --root /path/to/llm-wiki --type llm_wiki --api http://127.0.0.1:19828
node dist/cli.js kb link --name memory-research --project memory-orchestrator
node dist/cli.js kb doctor --name memory-research --query "agent memory"
node dist/cli.js kb search --name memory-research --query "agent memory"
```

When `--api` is configured, `kb search` and `kb read` try the LLM Wiki local HTTP API first:

- `POST /api/v1/projects/current/search`
- `GET /api/v1/projects/current/files/content?path=<page>`

If `LLM_WIKI_API_TOKEN` is set, the CLI sends it as a bearer token. If the API is unavailable, commands fall back to local Markdown files under the registered root.

Use `kb doctor` to verify whether the API is reachable, whether the token is present, and whether local Markdown fallback can return results.

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

The harness builds the TypeScript project, runs structure and usability score reports, promotes a verified evidence item into a temporary vault, and verifies cleanup markers.

Run the usability rubric directly:

```bash
node dist/cli.js score --rubric evaluation/usability-rubric.json --evidence evaluation/usability-evidence.json --out usability-score-report.json
```

Run the structure rubric directly:

```bash
node dist/cli.js score --rubric evaluation/structure-rubric.json --evidence evaluation/structure-evidence.json --out structure-score-report.json
```

## Repository Policy

- Do not commit `node_modules/` or `dist/`.
- Keep durable memory data outside this repository.
- Keep vault-specific AGENTS instructions in the vault, not in this package.
- Add licenses and npm publishing metadata only after the repository owner decides the distribution model.
