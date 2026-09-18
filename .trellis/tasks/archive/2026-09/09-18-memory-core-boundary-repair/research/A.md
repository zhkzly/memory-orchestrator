# A: source identity and lifecycle contract
Goal: use one known-source interpretation for feedback and learning admission; retain partial execution facts.
Invariant: early feedback needs no RunBundle/receipt, while learning requires real closed group/batch evidence.
Invariant: unknown imports remain unknown; known project/run/revision/state contradictions cannot be bound.
Invariant: execution termination and task judgement remain separate under a pre-recorded scoring_policy.
Owned: store.py, sampling.py, lineage.py, outcomes.py and the corresponding store/sampling tests.
Excluded: evidence/learning/evaluation/report, blueprint/packaged schemas, models/network/benchmarks, commits.
Gold: archived F02/F04/F06/F07 probes, current Store/RunGroupPlan records, normal sampling tests.

## Checks
1. Early correct feedback binds from executions; wrong known run/state/project/revision is rejected when bound.
2. Unknown external imports and explicitly unbound reports remain legal.
3. Learning requires actual slots, matching terminal RunBundles and receipt, not a boolean alone.
4. Frozen microbatch admission requires the actual immutable batch membership to close.
5. Valid partial events remain available after timeout/cancellation.
6. Expected/reported initial-state mismatch is visible without inventing an unprovided-state explanation.
7. completed_only/available_artifact are recorded before calls; malformed identity cannot be graded under either.
8. A run has an immutable single task_outcome assessment link; feedback may precede the RunBundle.
9. Pure shared helpers serve current consumers, without a lifecycle framework or rubric DSL.
10. Cross-boundary tests and official mutation checks prove rejection and legal continuation paths.

## Agreed interfaces
- outcomes.resolve_scoring_policy(value, *, default); parse_execution(output, error, policy).
- lineage.resolve_episode_source(store, episode); check_feedback_binding(store, feedback, episode); require_learning_source(store, episode).
- New sampling writes scoring_policy and batch_ref on RunGroupPlan, one SamplingBatchPlan per call, assessment_ref and initial_state_binding on RunBundle. Root owns the schema additions; B consumes closed-source admission and C consumes scoring/assessment records.

## Executed evidence

- Store 22 and Sampling 18 tests passed. The early-feedback test writes only an execution record before the episode/feedback/assessment; no RunBundle or receipt is fabricated. Wrong known run/state/revision are rejected; explicit unbound reports remain append-only.
- Timeout/cancelled/budget-exhausted returns retain actual partial event text and parent mapping. A reported initial-state mismatch remains visible as expected/reported/mismatched and as an episode gap, without silently changing task outcome.
- completed_only versus available_artifact is persisted before execution. Under available_artifact a cancelled run can have independently checked pass feedback, while its execution_status remains cancelled; wrong callback identity never becomes eligible.
- Closure tests remove an actual receipt/run and construct an inconsistent all_slots_accounted receipt, then restore the real record. A separate microbatch test withholds the other member's receipt. Learning admission rejects each open/contradictory state and accepts restored closure.
- Ten official mutation checks below killed the intended defect, restored the exact target bytes, and returned green. No model/network/benchmark or commit was performed.

### Raw official mutation output

```json
[
  {
    "name": "feedback shared binding",
    "file": "src/memory_orchestrator/store.py",
    "exit_code": 0,
    "output": "✅ 执照发放:src/memory_orchestrator/store.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n"
  },
  {
    "name": "known source project",
    "file": "src/memory_orchestrator/lineage.py",
    "exit_code": 0,
    "output": "✅ 执照发放:src/memory_orchestrator/lineage.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n"
  },
  {
    "name": "feedback artifact identity",
    "file": "src/memory_orchestrator/lineage.py",
    "exit_code": 0,
    "output": "✅ 执照发放:src/memory_orchestrator/lineage.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n"
  },
  {
    "name": "assessment source identity",
    "file": "src/memory_orchestrator/store.py",
    "exit_code": 0,
    "output": "✅ 执照发放:src/memory_orchestrator/store.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n"
  },
  {
    "name": "actual receipt run set",
    "file": "src/memory_orchestrator/lineage.py",
    "exit_code": 0,
    "output": "✅ 执照发放:src/memory_orchestrator/lineage.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n"
  },
  {
    "name": "microbatch member closure",
    "file": "src/memory_orchestrator/lineage.py",
    "exit_code": 0,
    "output": "✅ 执照发放:src/memory_orchestrator/lineage.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n"
  },
  {
    "name": "partial events retain",
    "file": "src/memory_orchestrator/sampling.py",
    "exit_code": 0,
    "output": "✅ 执照发放:src/memory_orchestrator/sampling.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n"
  },
  {
    "name": "known initial mismatch visible",
    "file": "src/memory_orchestrator/sampling.py",
    "exit_code": 0,
    "output": "✅ 执照发放:src/memory_orchestrator/sampling.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n"
  },
  {
    "name": "error blocks artifact evaluation",
    "file": "src/memory_orchestrator/outcomes.py",
    "exit_code": 0,
    "output": "✅ 执照发放:src/memory_orchestrator/outcomes.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n"
  },
  {
    "name": "available artifact policy",
    "file": "src/memory_orchestrator/outcomes.py",
    "exit_code": 0,
    "output": "✅ 执照发放:src/memory_orchestrator/outcomes.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n"
  }
]
```

## Independent read-only review of B

Reviewed B after its mutation window restored stable source: evidence.py SHA-256 `669ee5f121ac9ba251f52abe61c2d90c451ab45e7b162b10eea51260004be1ed`; learning.py `3a3337b80f606733d8316b3b960d493b506ae9684b61eb4c7e6f00c5e0f3928f`.

No new deterministic deviation was found in this repair scope. The same `_structure`/`_refresh` projection feeds fragments, read locators, relationship summaries, validation and expansion; all serialized metadata participates in the packet budget. Unread locator IDs remain uncitable as original facts, and unavailable goal-transition bases produce explicit partial/ambiguous coverage. Legacy archives are not overwritten; rereading creates a v2 packet. Requested sources, related retrieval/provenance and canonical-history merging all delegate to the shared learning admission rule, preventing frozen history from reentering through consolidation.

This review used stable source and the focused transport/budget/regression test definitions. No Python tests or mutations ran during C's window, no B file was edited, and final cross-module execution remains root's responsibility.
