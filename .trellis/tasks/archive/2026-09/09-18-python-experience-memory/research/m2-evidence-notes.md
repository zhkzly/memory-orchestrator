# M2 evidence/model boundary
Goal: bounded, goal-aware evidence and schema-checked model handoffs, independent of storage.
Invariant: provided original ranges alone support facts; catalog-only refs require an explicit read.
Invariant: keep old target revisions, source gaps, feedback visibility and all attempted-call usage.
Invariant: explicit budgets match model-visible limits; no hidden SDK retry or native-agent work.
Owned: evidence.py, model.py, prompts.json, test_memory_evidence.py, test_memory_model.py.
Excluded: store/sampling/candidate/publish, source prompt rewriting, real model/network calls, installs.
Fixture: existing v1.4 CSV evidence/feedback/extraction examples and imported-episode; tests are constructed boundary evidence, not measured improvement.

## Checks
1. Preserve A → B → A event grouping, old revisions and unknown association.
2. Pair calls by episode/call identity, retain unmatched and parent gaps.
3. Packet stays within explicit character and estimated-token limits, including metadata.
4. Long events expose exact bounded UTF-8 ranges, not invented summaries.
5. Expansion rejects foreign/corrupt/unread sources; citation whitelist distinguishes catalog and body.
6. Private evaluation feedback stays out of adaptation input.
7. Model prompts match source byte-for-byte; template fields and active limits are visible.
8. Schema/format retries, input/output/cumulative limits and failure usage are finite and observable.
9. SDK injection uses the real OpenAI interface, no automatic retries or credential logging.
10. Red/green tests and official mutation checks before completion.

## Notes
- Token budget is an explicitly labelled estimate, not a tokenizer measurement. Character budgeting is exact JSON size; reported model usage is retained separately.
- Current user authorization supersedes the stale pause text being synchronized by main. No node behavior or parameter defaults are changed here.
- First GREEN: 12 evidence tests and 11 model tests. An initial shared-ID prefix mismatch was corrected against schemas.new_id's actual contract. No network calls occurred.
- Official mutation checks passed for original text, unread catalog citations, source metadata, feedback visibility, goal effective order, model call cap, no SDK retry, extraction count and reported output-token cap (9 bindings).

## Added ownership: learning orchestration

Main explicitly extended this worker to learning.py and test_memory_learning.py. `learn(store, episode_ids, model, *, policy)` fixes one active base/generation, records a plan, extracts once with finite reads, persists experience revisions, diagnoses once, then records every requested candidate slot. It never publishes or writes facts. `model` is the current StructuredModel boundary; no alternate model framework.

Policy fields are explicit: packet and expanded_packet (max_chars/max_fragment_chars/max_catalog_refs/token_budget), max_expansions, max_experiences, max_read_requests, max_related_experiences, max_related_episodes, max_related_chars, candidate_count, max_operations, max_skills, max_asset_bytes, evaluation_scope. Numeric values belong to each call; the module supplies no scientific/default thresholds.

Related memories are project-scoped and collapsed by canonical kind/scope/guidance. A bounded set of their actual source episodes is read for counterevidence; previous summaries alone are not new original facts. Revisions append, source episode/task counts deduplicate, unknown task identities remain unknown. Model reports and failed attempts are persisted before semantic rejection or candidate continuation.

## Current verification

- Evidence: 12 tests; model: 11 tests; learning/storage/report handoff: 13 tests, all green. Python compilation passed. These use blueprint-derived constructed episodes, synthetic model replies, and real temporary file storage.
- Official mutation licenses: 5 evidence bindings, 4 model bindings and 6 learning bindings (15 total), including finite expansion, source deduplication, non-Skill NOOP, current-base diagnosis target, cost retention and N11 stage classification. Each mutated source was restored by the official tool and its acceptance returned green.
- Learning usage now uses the shared ledger: exclusive_stage extract/diagnose/propose, purpose learning, cycle identity, independently reported input/output/total token fields, elapsed time, unknown monetary cost and original raw entry. The integrated report sees 3 calls and stages, input 33/output 21 for the synthetic fixture, and unknown total-token/currency cost rather than fabricated zeros.
- Existing feedback receives adaptation visibility filtering before model input. Related-memory source omissions are explicitly prioritized in packet gaps. Original requirements and events remain immutable.
- No SDK network/live model, native Agent, benchmark gain measurement, CLI/MCP, product publish or Git commit was performed by this worker.

## Independent-review corrections

Four reported failures were reproduced with new RED tests before fixes:

- Frozen final/validation trajectories bypassed feedback-only filtering. Learning now checks the stored run/group purpose and learning flag before model input; explicit parents are checked too, and previously polluted related memories are excluded. Imported material with no local run authority remains allowed with unknown provenance, rather than inventing a group.
- Full feedback logs bypassed the bounded packet via another prompt field. Model inputs now receive only provided-range references and compact feedback identity/state metadata; reason/log text stays in exact bounded fragments. Task requirements and source contexts also use references/metadata instead of duplicating long original text.
- A new canonical revision dropped prior counter/boundary references. Host-owned retained_evidence keeps original packet/record identity separately from the new model draft; retrieval preserves it and marks whether its body is currently provided. Unread historical references remain uncitable as new original facts.
- Fractional/bool/string/non-finite token measurements could poison the project report. Token fields now accept only nonnegative integers or null, preserving malformed-value diagnostics separately and marking the affected measurements missing. Time and monetary fields keep their distinct numeric contracts.

After fixes: evidence 12 + model 12 + learning 19 = 43 focused tests GREEN. Six additional official mutations (frozen lane, bounded feedback handoff, retained boundaries, integer token normalization, unread historical visibility, reason bypass) were killed and restored. Total licenses for this worker's implementation: 21. Independent reviewer was asked to rerun the original reproductions. No live model calls or commits during these fixes.

- The existing full local flow's 2 tests also passed after the fixes: scripted ADD/PATCH, accepted/rejected comparisons, temporary-store publication, reuse, rollback and reopen. These are isolated constructed executions, not changes to a user memory vault or evidence of general LLM improvement.
- Independent evaluation worker re-ran its original four reproductions without editing this worker's code: frozen final sources now produce 0 model calls/0 new experience; the 180k-character feedback input projects to 702 characters of metadata plus a 4002-character packet and completes one call; historical boundaries reach the related-memory input while unread citations remain rejected; fractional tokens become missing and the project report completes.

## Actual canary diagnosis handoff

- Read the saved v2 canary report `modelreport_772fefb1f00e4417b7d7f98dd69c8bd0`: its actual `skill_patch` diagnosis invented `csv-typed-transformation@new` in an empty base. Rejection was correct, but the error occurred after the model's finite repair opportunity and its diagnostics were empty.
- Added `StructuredModel.generate(..., check=None)`: a pure check runs after schema validation inside the existing format-repair/call budgets. It receives a copy, cannot transform the accepted value, and DomainError feedback preserves code/message/field diagnostics and every attempted usage. No second retry policy was added.
- Learning supplies citation checks and current-base target checks through that same boundary. Application-level `apply_candidate` stays outside retries; duplicate-ADD/static application rejection remains a candidate-slot failure. Target diagnostics now include actual targets, allowed IDs/revisions/rules and the concrete `targets=[]` correction for ADD.
- Regression starts with the actual canary target shape, then uses explicit synthetic corrected replies: extract → failed diagnosis → corrected empty targets → proposal consumes 4 calls with 4 usage records. Zero repair allowance still rejects; a two-call shared cap stops before the semantic retry. Format and semantic failures share the same repair allowance.
- Model 13 and learning 21 tests passed; existing 2 full local-flow tests and compilation passed. Three additional official mutations killed disabled semantic checking, exceeded shared repair allowance and omitted learning/check wiring, then restored the exact source. Total official mutations for this worker: 24. This establishes repair control flow, not a claim that the real model will necessarily produce a successful candidate.
