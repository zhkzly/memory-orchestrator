<!-- TRELLIS:START -->
# Trellis Instructions

These instructions are for AI assistants working in this project.

This project is managed by Trellis. The working knowledge you need lives under `.trellis/`:

- `.trellis/workflow.md` — development phases, when to create tasks, skill routing
- `.trellis/spec/` — package- and layer-scoped coding guidelines (read before writing code in a given layer)
- `.trellis/workspace/` — per-developer journals and session traces
- `.trellis/tasks/` — active and archived tasks (PRDs, research, jsonl context)

If a Trellis command is available on your platform (e.g. `/trellis:finish-work`, `/trellis:continue`), prefer it over manual steps. Not every platform exposes every command.

If you're using Codex or another agent-capable tool, additional project-scoped helpers may live in:
- `.agents/skills/` — reusable Trellis skills
- `.codex/agents/` — optional custom subagents

Managed by Trellis. Edits outside this block are preserved; edits inside may be overwritten by a future `trellis update`.

<!-- TRELLIS:END -->

## Project Contract and Resume

- Target architecture authority: `docs/blueprint/project-contract.json`; its generated entry is `docs/blueprint/context.md`, with a human view in `docs/blueprint/index.html`.
- Before product implementation or resuming after interruption, read the current Trellis task's `resume.md`, identify the contract version, node IDs, allowed paths, last completed step, and next step.
- Read only relevant node contracts with `node docs/blueprint/build.mjs node Nxx`; historical research is background, not automatically active instructions.
- Record explicit user changes before changing shared boundaries. The user can revise the contract; do not use old documents to reject a clear new direction or silently reinterpret the request.
- Update the JSON source and regenerate views when the contract changes. Use `node docs/blueprint/build.mjs verify` to detect stale views.
