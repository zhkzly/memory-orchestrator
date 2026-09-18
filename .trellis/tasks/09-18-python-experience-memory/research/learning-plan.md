# Learning implementation contract
Goal: implement bounded evidence learning through the current Python memory API.
Invariant: facts cite provided original fragments; catalog entries alone are not evidence.
Invariant: preserve missing feedback/context, source identity and every attempted model call.
Invariant: only explicit current Skill targets can be proposed for editing; no automatic publish.
Files: src/memory_orchestrator/learning.py and tests/test_learning.py.
Excluded: storage/engine ownership, native agents, CLI/MCP, live calls, installs, blueprint changes.
Fixture source: docs/blueprint/project-contract.json illustrative CSV packet and model drafts; all SDK responses are explicitly synthetic, not measured results.

## Acceptance checklist
1. Bounded packets retain requirement, failure and recovery evidence with source/hash/ranges.
2. Long individual events provide useful truncated fragments; expansion only reads catalogued, unmodified sources.
3. Unknown feedback/context is preserved without fabricated runner records.
4. Foreign/unread citations and invalid current Skill targets are rejected.
5. Related lookup matches exact project and does not multiply duplicated sources.
6. SDK calls use actual prompt templates/schema, no hidden retry, explicit timeout and finite budgets.
7. Invalid output gets at most one format repair; truncation/transport/budget errors retain attempted usage.
8. Extraction expansion is finite, allows abstention and zero experiences; non-Skill routes never propose.
9. Three-stage scripted learning returns sourced drafts with no store writes.
10. Meaningful tests and mutation rejection run before reporting implementation complete.

## Evidence and decisions
- Current task interfaces override stale runner references in the macro blueprint. Draft schemas remain packaged and unchanged.
- SDK source inspected: installed openai 2.54.0 supports chat.completions.create response_format=json_object and max_completion_tokens; OpenAI max_retries defaults to 2, so the implementation must set 0 explicitly.
