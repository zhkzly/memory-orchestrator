# Evaluation implementation boundary

Goal: compare immutable base/candidate snapshots through the caller's evaluator.
Invariants: freeze full plan before callbacks; unknown never accepted; exact snapshot and generation bind results.
Owned: `src/memory_orchestrator/evaluation.py`, `tests/test_evaluation.py`, this note.
Excluded: Agent adapters, processes, CLI/MCP, model calls, implicit learning/publication, shared modules.
Reference: current `interfaces.md` N09 callback contract; CSV PATCH example in the blueprint (constructed, not measured).

## Checks

- [ ] Real Store freezes every case/version/repeat slot before first callback.
- [ ] Stale/wrong-project candidates and over-budget/unsupported inputs invoke no callback.
- [ ] All callback exceptions, invalid scores, and explicit unknowns retain planned denominator.
- [ ] Scores aggregate per independent case; hidden per-case regression rejects; ceiling transfer permits acceptance.
- [ ] Callback input mutation cannot modify authoritative snapshots/cases or produce an accepted evaluation.
- [ ] Plan/records bind evaluator, policy, cases, candidate, base and exact generation; no implicit publish.
- [ ] Reported/missing usage retained once per slot; missing is null, not zero.
- [ ] Official mutation checks exercise missing-result, generation, regression, and mutable-input rejection.

## Append

- Store will persist proposals.expected_generation and a `validation_plans` collection. Five gate names agreed with main/store: complete_results, target_gain, regression_non_decrease, transfer_non_decrease, versions_unchanged.
- Current scope supersedes old blueprint runtime/actor mandatory fields. Caller callback correctness remains caller responsibility; this core does not claim independent truth or OS isolation.
