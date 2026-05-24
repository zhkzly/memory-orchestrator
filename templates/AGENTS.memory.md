# Memory Orchestrator Agent Instructions

Use the `memory-orchestrator` CLI as the canonical memory interface.

## Startup

1. Read the vault's local `AGENTS.md`.
2. Build task context with:

   ```bash
   memory-orchestrator context --task "<current task>" --session "<session-scope>" --project "<project-scope>"
   ```

3. Treat the returned files as candidate context, not unquestioned truth.

## Writing Memory

Only promote memory after verification:

1. `capture` the candidate.
2. `verify` against source evidence.
3. `promote` only if status is `verified`.

Do not promote session scratchpads or unsupported personal facts.

## Cleanup

Run `clean` periodically and review markers before editing vault files:

```bash
memory-orchestrator clean --scope "<project-or-person-scope>"
```
