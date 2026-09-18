# B: bounded structural evidence and shared learning admission

Ownership: evidence.py, learning.py and their existing tests only. Main owns blueprint/packaged schemas; A owns the shared local lineage/admission rule. No native integration, model/network call, new scheduler or automatic goal inference.

Source: F03 call_metadata_loss/goal_metadata_loss and F04 open-group probes in the prior coverage audit. RED tests now assert actual StructuredModel transport content, rather than accepting that EpisodeIndex alone contains the relationships. A separate live-thread test checks zero model calls and zero learning writes while a known local group remains open, then normal learning after closure.

Root cause: text-only `_piece` erased available metadata before the model boundary. The repair will share one bounded projection across build/validate/expand and account for its serialized size. Old packet archives remain readable; new packets must preserve observed metadata without inventing missing identities.

F04: use A's `lineage.require_learning_source(store, episode)` for requested sources, explicit parent sources, related experience source admission and provenance. Do not keep another run/group-purpose interpretation in learning.py.

## RED evidence and shared decisions

- Before repair, all three new consumer tests failed: call-only and goal-only changes produced identical transport packets; open local group did not raise before model work.
- Root confirmed additive EvidencePacket `projection_version=2`, per-fragment/catalog `structure`, and local `relations` with call coverage, goal basis coverage and parent visibility. Legacy packets without the version remain readable; expansion reconstructs a new v2 packet from the source index. Schema/source packaging is owned by root.
- Initial integration errors were expected concurrent boundaries: source_position=-1 was awaiting the root's schema correction and evaluation imported A's not-yet-written outcomes.py. After schema synchronization, evidence tests passed 17/17 without increasing their existing packet budgets.
- Source eligibility must also guard canonical-history merging, not only prompt retrieval. Otherwise an old frozen/open-source experience can be silently reattached while saving a fresh valid experience. Both consumers now call the same `_eligible_experience`, which delegates to A's source rule.

## GREEN checkpoint

- With A's real batch producer connected, `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_evidence test_memory_learning -v` passed 42/42 (17 evidence, 25 learning).
- The open-group test runs real concurrent callback scheduling: before group/batch closure, `learn` raises `learning_not_permitted` with zero model calls and byte-identical stored JSON; after closure the same source can reach the model.
- The two F03 tests decode the actual StructuredModel transport message. Same-text call/goal changes now alter visible structure and corresponding relationship rows. Metadata, relationship summaries and catalog all fit the declared whole-packet budget. Original long-trace and bounded-expansion checks remain green without increasing their packet budgets.
- Canonical merge test preserves an old mixed valid/frozen-source record for audit while rejecting it from prompt retrieval and from merged source/counterexample history. Ordinary unknown imports remain eligible. Legacy packet fields remain readable; expansion reconstructs source-backed v2 metadata while leaving the old packet unchanged.
- Owned-path `git diff --check` passed. No model/network/benchmark invocation occurred.

## Independent C handoff review

Read-only inspection covered compare → selection → publish proposal aliases and terminal-scoring policy. Each proposal is checked against its stored canonical form/project/base/generation before snapshot deduplication. The frozen mapping, plan and selection retain aliases; publication rechecks them and rejects aliases created later. Scoring policy is persisted before execution and publication recomputes eligibility through the same `parse_execution` definition.

Five focused evaluation/release tests passed: duplicate proposal aliases share one comparison; non-completed scoring follows frozen policy; a frozen alias may publish while a later alias may not; forged selection aliases are rejected; publication rechecks recorded scoring policy. No new reproducible deviation was found in that bounded path. No C file was modified.

Official mutations were coordinated in a separate window after A; final evidence is recorded below. B is not running Python checks or mutations after releasing its window.

## Final official mutation evidence

Complete replayable test commands, exact injection scripts, official command lines and raw output are saved in [B-mutations.json](B-mutations.json). This is an audit artifact; executing it again requires a coordinated mutation window.

43/43 evidence+learning tests passed before the mutation window (18 evidence, 25 learning). The extra evidence case checks a legal cross-episode parent when both episodes use the same event_id.

Main granted an exclusive window. The official mutation tool completed 11/11 targeted semantic mutations, each with a green baseline, a failing mutated run, exact-byte restore and a green rerun. No additional changes were made while mutating.

Pre/post SHA256 output is identical:

```text
669ee5f121ac9ba251f52abe61c2d90c451ab45e7b162b10eea51260004be1ed  src/memory_orchestrator/evidence.py
3a3337b80f606733d8316b3b960d493b506ae9684b61eb4c7e6f00c5e0f3928f  src/memory_orchestrator/learning.py
```

Raw tool results (test commands, exit codes and complete tool output):

```json
[
  {
    "label": "observed-call-metadata",
    "target": "src/memory_orchestrator/evidence.py",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_evidence.EvidenceTests.test_packet_projects_observed_call_parent_role_and_source_order -q",
    "exit_code": 0,
    "raw_output": "✅ 执照发放:src/memory_orchestrator/evidence.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n"
  },
  {
    "label": "goal-to-model",
    "target": "src/memory_orchestrator/evidence.py",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_learning.LearningTests.test_same_text_different_goal_identity_changes_actual_model_input -q",
    "exit_code": 0,
    "raw_output": "✅ 执照发放:src/memory_orchestrator/evidence.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n"
  },
  {
    "label": "call-pair-endpoints",
    "target": "src/memory_orchestrator/evidence.py",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_evidence.EvidenceTests.test_packet_projects_observed_call_parent_role_and_source_order -q",
    "exit_code": 0,
    "raw_output": "✅ 执照发放:src/memory_orchestrator/evidence.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n"
  },
  {
    "label": "goal-visible-basis",
    "target": "src/memory_orchestrator/evidence.py",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_evidence.EvidenceTests.test_goal_transition_needs_its_visible_basis -q",
    "exit_code": 0,
    "raw_output": "✅ 执照发放:src/memory_orchestrator/evidence.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n"
  },
  {
    "label": "structural-budget",
    "target": "src/memory_orchestrator/evidence.py",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_evidence.EvidenceTests.test_relationship_metadata_is_bounded_and_undisclosed_endpoints_are_partial -q",
    "exit_code": 0,
    "raw_output": "✅ 执照发放:src/memory_orchestrator/evidence.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n"
  },
  {
    "label": "structure-validation",
    "target": "src/memory_orchestrator/evidence.py",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_evidence.EvidenceTests.test_structure_and_relationships_share_exact_source_validation -q",
    "exit_code": 0,
    "raw_output": "✅ 执照发放:src/memory_orchestrator/evidence.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n"
  },
  {
    "label": "relation-validation",
    "target": "src/memory_orchestrator/evidence.py",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_evidence.EvidenceTests.test_structure_and_relationships_share_exact_source_validation -q",
    "exit_code": 0,
    "raw_output": "✅ 执照发放:src/memory_orchestrator/evidence.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n"
  },
  {
    "label": "legacy-upgrade",
    "target": "src/memory_orchestrator/evidence.py",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_evidence.EvidenceTests.test_legacy_packet_remains_readable_and_expansion_upgrades_structure -q",
    "exit_code": 0,
    "raw_output": "✅ 执照发放:src/memory_orchestrator/evidence.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n"
  },
  {
    "label": "learning-entry-admission",
    "target": "src/memory_orchestrator/learning.py",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_learning.LearningTests.test_open_local_group_cannot_call_model_or_write_learning_records -q",
    "exit_code": 0,
    "raw_output": "✅ 执照发放:src/memory_orchestrator/learning.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n"
  },
  {
    "label": "related-experience-admission",
    "target": "src/memory_orchestrator/learning.py",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_learning.LearningTests.test_frozen_parent_and_polluted_related_memory_cannot_bypass_source_gate -q",
    "exit_code": 0,
    "raw_output": "✅ 执照发放:src/memory_orchestrator/learning.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n"
  },
  {
    "label": "canonical-history-admission",
    "target": "src/memory_orchestrator/learning.py",
    "test": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_learning.LearningTests.test_canonical_merge_cannot_reintroduce_mixed_forbidden_history -q",
    "exit_code": 0,
    "raw_output": "✅ 执照发放:src/memory_orchestrator/learning.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。\n"
  }
]
```

Window released to main and reviewers. Product effects remain unmeasured; these are source-bound local behavior checks, not real model or benchmark gains.
