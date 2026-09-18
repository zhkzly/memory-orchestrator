# B completion evidence — trace, goals, experience maintenance and learning

Implementation ownership stayed within `evidence.py`, `learning.py`, new `trace.py` / `goals.py` / `maintenance.py`, their focused tests, and this task's B research files. Shared schemas/prompts/model normalization and root report/experiments fixes were implemented by the designated owners. No live provider, benchmark, native client, CLI, MCP, new agent or commit was invoked by B.

## Actual behavior

- `learn` consumes imported array or immutable JSONL events through one evidence path. JSONL indexing advances by explicit batches and returns `needs_index` before model work when incomplete. Byte ranges, original line locators, source hashes, structural relationships and resource candidates enter bounded packets; tampering and malformed ranges are rejected.
- Missing user-goal labels enter the real StructuredModel call path. Anchors are user instructions, earlier windows exclude future instructions, previous goals have grounded catalog excerpts, A→B→A retains a derived resume identity, and raw identities remain unchanged. Ambiguous/failed output is retained without inventing successful associations.
- Known parent-source admission is independent of optional dependency-body retrieval. The three-level inline child → unindexed trace parent → known final ancestor counterexample is blocked with zero model calls. Unknown external parent references remain explicit gaps under A's shared lineage rules; incomplete ancestry cannot re-enter through old experience records.
- Failure signatures affect retrieval under an explicit character bound. Semantic duplicate/conflict/revoke decisions are validated against supplied records and become visible only through a committed maintenance review. Subsequent actual extraction sees the folded representation, preserving sources and adverse evidence; unresolved conflict groups stay together or are omitted together by budget.
- Diagnosis necessity controls NOOP and allowed ADD/PATCH/RETIRE operations. Existing capability identities, public check references and source citations are checked within model repair budgets. Candidate creation receives the exact saved diagnosis reference/hash for C's check scheduling.
- Model-call usage preserves normalized provider fee/currency/price version, including rejected attempts and explicit zero. Missing prices and model-body price claims remain unknown. Interrupted calls preserve their original exception, leave the learning cycle unfinished, and exclude provider call-wall time from local maintenance.

## Validation

- Focused final command:
  `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_trace test_memory_learning test_memory_goals test_memory_maintenance test_memory_evidence -q`
- Actual final output after all mutation restorations: **Ran 75 tests; OK; exit 0**.
- `git diff --check` over all B source/test files: **exit 0**.
- A independently exercised disk → goal association → actual extraction, zero-dependency-budget frozen-parent isolation, and maintenance → next extraction. Evidence is in `research/A-review-B.py` and its saved JSON. B's static review of root O12–O14 found two concrete issues; root reproduced and fixed both, retaining `root-review-red.txt` / `root-review-green.txt`.
- B's new-file RED, real consumer RED→GREEN, shared-schema reference closure, source ancestry and cost/timing regressions are recorded chronologically in `B-plan.md`. Tests use actual temporary storage and the real StructuredModel boundary with supplied synthetic responses; they do not establish model semantic accuracy or generalization gain.

## Official mutation evidence

The root granted an exclusive window after A finished. B ran only the existing official tool:
`/home/kelong/ai-workbench/tools/mutation_license.py`.

**20 / 20 licenses issued, every tool exit 0, every target restored to its exact pre-injection hash.** No weakened test, mutation retry or product change was needed during the window. The root was notified immediately when the window was released; B stopped dependent Python and source/schema edits.

- Exact injection definitions: `B-mutations.py`.
- Reproducible runner: `B-run-mutations.py --exclusive-window-granted` (requires coordinator scheduling).
- Every original official stdout, test command, injection command, target, exit code and restoration check: `B-mutation-evidence/` and `B-mutation-evidence/results.json`.
- Covered edges: cold/hot source integrity, batch limit, original byte range, user-only goal anchor, future-window exclusion, maintenance commit visibility, conflict preservation, necessity NOOP/ADD, failure ranking, real maintenance consumer, transitive source admission, derived/resource projections, check-directory binding, three independent fee fields, and interrupted-provider time exclusion.

Restored SHA-256 values:

| File | SHA-256 |
| --- | --- |
| evidence.py | 217ed01eacfc1b3667eeacdff08918af262a93b332c9d69649841bd99d58888d |
| learning.py | 2f2ce0f844b680ea6a1d2e6d61dffc39bf0b6872a5a16e8f717e453e808f6eca |
| trace.py | 89f439904756081ce57f4ed6faf5be05fe3564ca8c30be9c4e129f9906435975 |
| goals.py | 3f243124894a800a00f8c2c70b0b720aa32bffaf2786f94660d575babad1cd27 |
| maintenance.py | e3c5e86af3d72c1689fa849d4afd757ebcd410730e67a99e3dad0296a5dd3b80 |

## Handoff and evidence limits

No B implementation blocker remains. The coordinator still owns integrated full-suite verification, document/HTML evidence alignment and commits. The implemented source format is explicit JSONL Episode events, with array imports retained; this is not native Codex/Claude trace acquisition. Measured read counts and maintenance time are reported as observations, not claims of faster execution or positive net learning benefit. Real model/benchmark effectiveness remains unmeasured.
