# Optional Skills

Each skill wraps one memory role around the CLI core.
These wrappers are optional compatibility helpers, not the canonical interface.

## Optional Skills

- `memory-extractor`
- `memory-verifier`
- `memory-writer`
- `memory-context-builder`
- `memory-rubric-scorer`
- `memory-cleaner`

## Rule

Skills should not implement memory policy themselves.
They should only:

1. collect the right inputs
2. call the CLI commands
3. format the result for the agent

If a runtime does not support this skills structure, use the CLI directly from `AGENTS.md`, shell scripts, or explicit agent instructions.
