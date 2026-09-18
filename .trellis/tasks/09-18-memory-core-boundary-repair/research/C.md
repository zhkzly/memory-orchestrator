# C: attempts, snapshots, observations and admission

Goal: repair F05/F08/F09/F10 and consume the shared explicit F01 scoring policy.
Invariant: proposal attempts and fees remain; comparison executes each unique snapshot once per plan.
Invariant: observed result facts are reported without requiring a validation decision; publication still requires it.
Invariant: sampling/comparison/modes/terminal states retain original planned denominators and unknowns.
Owned: evaluation/release/report/engine and their four tests; this note.
Excluded: Store, sampling, evidence, schemas, model/network calls, commits and unrelated design additions.
Reference: frozen audit probes under implementation-coverage-audit-20260918/probes and current node contracts.

## Interface decisions

- A supplies outcomes.resolve_scoring_policy / parse_execution and lineage.check_feedback_binding. Comparison default is available_artifact, sampling default remains completed_only; effective choices are persisted before calls.
- Root owns Schema. New plans/results carry proposal aliases, purpose/mode/scoring_policy and execution_status. Selection is per unique content snapshot; aliases must match the frozen proposal records.
- Reports read evaluation_results by planned request ID. Validation metadata is a separate decision view, never the authority for whether observed results exist.

## Verification log

- RED reproduced: F05 charged two same-content proposals as sixteen evaluation requests instead of eight unique-snapshot requests; F08 reported eight unknowns despite eight saved results; F09 lacked sampling quality; F10 lacked unique snapshot/proposal counts. F01 effective scoring policy was not frozen.
- GREEN: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_evaluation test_memory_release test_memory_report test_memory_flow -q` passed 46 tests (13 evaluation, 11 release, 19 report, 3 full-flow).
- Explicit TaskAssessment producer/consumer and legacy unambiguous-feedback fallback are covered. Valid individual assessment records linked to the wrong run are reported unknown. An initially constructed internally inconsistent assessment was correctly rejected earlier by Store, so the report fixture was refined to the actual cross-reference boundary rather than weakening Store.
- Testing temporarily hit the stale inline ValidationRecord.results schema. Root synchronized the nested EvaluationResult shape; no product workaround discarded execution_status to bypass validation.
- Before the coordinated window, official mutations were pending. No tests or mutation ran while another worker mutated intersecting dependencies; final results are below.

## Final C verification

- Final owned suite: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_evaluation test_memory_release test_memory_report test_memory_flow -q` → **47 tests, OK** (13 comparison, 11 release, 19 report, 4 flow).
- Added whole-flow distinction: the first of two different valid proposals is ineffective, the second improves the local CSV task; engine publishes the frozen selected snapshot, not the first proposal. Duplicate same-snapshot attempts instead retain both records/fees but execute one comparison.
- Strict completed_only checks count actual evaluator invocations (zero when ineligible), rather than relying on an assertion that the callback boundary could correctly capture as an unknown result.
- A → B → C mutation windows were serialized. C completed **11/11 official mutation licenses**. Exact commands, injected text, raw stdout/stderr, return codes and before/after SHA-256 are in [C-mutations.json](C-mutations.json); every target was byte-identical after restoration.
- Covered mutation edges: unique-snapshot budget and execution, scoring eligibility and publication recheck, frozen selection aliases and retry membership, observations independent of validation, snapshots independent of validation count, ambiguous legacy outcome, unknown any-success, and engine's selected representative.
- No model/network/benchmark calls or commits. No C mutation/test process remains. Root owns final repository-wide verification and contract-view synchronization.

## Current behavior boundary

- Report views do not grant admission: raw known results remain visible with validation_status=missing after an interrupted comparison, while publish still requires accepted validation, frozen selection, exact aliases and CAS.
- Sampling report uses the explicit single task_outcome assessment and original feedback. Legacy reconstruction requires a unique provably related original feedback; contradictions/missing data remain unknown. This does not implement a multi-standard rubric.
- Terminal state and task outcome are separate. available_artifact can score a normally returned cancelled/timeout artifact; completed_only does not request that score. Effective choices are frozen in plans and repeated at publication checks.
- Unique snapshot/proposal-record counts, proposal-slot states, validation attempts, comparison observations and sampling purpose/update_mode/scoring_policy are separate statistics. Costs still come from unique usage records, never multiplied by proposal aliases or admission views.

## F09 same-cause interruption extension

- A final same-cause probe showed that Feedback/TaskAssessment persisted before RunBundle were still hidden by the run view. Root authorized the two current interruption points: before assessments, and before runs. Both first failed the new end-to-end assertion (known pass was reported unknown).
- Report now resolves an observed score through the frozen slot, actual episode/execution lineage and either one proven assessment or one original task_outcome feedback. RunBundle and receipt presence remain separate counts. It does not synthesize a Bundle/Assessment or relax the learning/publication gate.
- Reproducible artifacts: [probe](C-sampling-interruption-probe.py), [before](C-sampling-interruption-before.json), [after both points](C-sampling-interruption-after.json). Run with `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python .trellis/tasks/09-18-memory-core-boundary-repair/research/C-sampling-interruption-probe.py assessments` (or `runs`).
- After both interruptions: observed pass=1, RunBundles=0, recorded_runs=0, and learning_not_permitted. Existing fact bytes are unchanged by reconstruction; only the normal Report artifact is appended. Multiple competing assessments/feedback and contradicted execution identity remain unknown.
- Affected suite: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_report -q` → **20 tests, OK**. The four unchanged report mutation edges plus early-score visibility and early-assessment uniqueness all passed: **6/6**, exact restoration. Actual commands/injections/output/hashes: [C-report-interruption-mutations.json](C-report-interruption-mutations.json). No evaluation/release/engine mutation was unnecessarily repeated.
- Last combined C run before this extension was 47 tests; the extension adds one test with both interruption subcases, so current owned coverage is 13 evaluation + 11 release + 20 report + 4 flow. Root runs the final full suite. All C processes are stopped and products restored after mutation.

## Independent read-only A cross-check

Reproducible script: [C-independent-A-probe.py](C-independent-A-probe.py); output: [C-independent-A-result.json](C-independent-A-result.json).

Command from repository root: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python .trellis/tasks/09-18-memory-core-boundary-repair/research/C-independent-A-probe.py`.

- Correct early feedback saved with zero RunBundles and zero receipts. Wrong known run/state/revision each rejected as REFERENCE_MISMATCH.
- Unknown external import remains legal and resolves known=false; no synthetic run or receipt is required.
- For two microbatch task groups, the first group's actual completed run was given a matching local group receipt while the second task was held by a bounded Event. The first group alone passed _closed_group, but require_learning_source still rejected the open batch. Threads were released and joined.
- A fresh fully closed two-group microbatch allowed both source episodes. This distinguishes enforcing the batch boundary from blanket rejection.
- Temporary Stores only; no model/network calls and no A-source changes. The first temporary store intentionally exercises an early group receipt and is discarded after thread cleanup; the clean positive path uses a separate Store.
