# B static cross-review of root-owned O12–O14 consumers

Date: 2026-09-19. Scope: experiments.py, telemetry.py, report.py and their root-owned tests. A held the exclusive mutation window. **No dependent Python code, test, probe, model or benchmark was executed for this review; no product/schema file was changed.** Findings below are static causal paths with concrete triggering inputs, not claimed runtime reproductions.

## Findings

### P2 — Frozen experiment policy copies are recorded but not used by execution

- Locations: `experiments.py:93`, `:111–116`, `:123`, `:137–140`, `:165–168`, `:183–184`.
- The function copies only `dataset` and `protocol` into private working variables. It records deep copies of sampling/context/learning/comparison policies, verification and seed in the immutable plan, but all arms continue to read the caller's original objects. The saved plan therefore does not constrain the actual configuration used by later arms/cycles.
- Concrete trigger using the existing experiment fixture: retain a mutable `sampling` dict with `repeat_count=2`; an `execution_factory(store)` closure changes it to `repeat_count=3` when `store.root.name == 'frozen'`. The plan still records 2 while frozen and subsequent arms receive 3. Likewise an externally mutated mutable seed can change a later arm's initial snapshot while `initial_seed_hash` continues to name the original seed.
- Impact: arm execution counts/costs or starting libraries can differ from the frozen study plan without a rejection. This directly contradicts the function's documented same-initial-contents property and O14's frozen protocol basis; it is not an assertion about whether a caller-provided executor tells the truth.
- Existing test `test_real_same_core_runs_all_modes_with_frozen_final_and_equal_budgets` supplies constant objects and checks call ceilings and baseline equality; it does not mutate a retained caller configuration during the run.
- Minimal correction: capture the full configuration before invoking either factory and execute only from the frozen copies, passing isolated copies where a downstream API could mutate a container. Add a mutation-of-original-input regression which compares actual persisted run plans/seed snapshots with the saved experiment plan.

### P2 — An interrupted model learning call can leave the report's call-cost total marked complete

- Report location: `report.py:454–472`; producer boundary: `learning.py:286`, `:324–339`, `:565–568`; `model.py:101–119`.
- The report marks totals incomplete for unreturned callback attempts and missing sampling/comparison work, but does not consider a persisted `learning_cycles` plan without a terminal record. StructuredModel's in-flight usage entry exists only in memory; `persist_call` runs after return or DomainError. A `KeyboardInterrupt` from an actual started model transport is not caught by `except Exception` in model.py or by the DomainError-only learn path.
- Concrete trigger: use an ordinary imported Episode and StructuredModel transport which records that it entered the provider operation and then raises `KeyboardInterrupt`; catch the interrupt outside `learn`, reopen the Store, and call `report`. The persisted cycle remains `planned`; there is no usage record/callback-attempt record for that model attempt. With no other work, `aggregate_usage([])` returns `complete_cost_totals={}`, and the report's current guard does not turn it unknown. If earlier fully priced calls exist, their partial total can similarly remain labelled complete.
- Impact: an interrupted provider call with unknown billing is represented as no missing call cost. The report already conservatively handles the analogous unreturned execute/evaluate callback, so model learning should not silently fall outside that completeness boundary. Local error timing is not the missing provider bill.
- Existing telemetry tests cover timing exceptions and storage-error preservation; completion tests cover unreturned ordinary callbacks; learning tests cover returned/DomainError model usage. None covers this model-interruption-to-report path.
- Minimal correction: at least expose unfinished learning cycle IDs and clear complete cost/token totals when a persisted learning plan has no terminal outcome. A durable model-attempt record can make attribution more precise, but the immediate report must not infer that absent usage means a free attempt.

## Paths that are implemented and have direct consumers

- **Three modes and bounded learning:** experiments resets per-arm counters (`:119–120`), uses one same-core `sample_tasks`/`evolve` path (`:139`, `:165`), blocks teacher creation once cycle/call budgets are exhausted (`:153–161`), and caps each fresh teacher's max_calls by the arm remainder (`:162`). Frozen mode does not invoke evolution (`:136`, `:152`). Actual transport/callback honesty remains explicitly caller-owned.
- **Final-stage non-learning:** final sampling overwrites purpose/update mode to final/none (`experiments.py:180–185`), never invokes evolve on those episodes, and checks the active version after every final batch. Existing experiment tests inspect the persisted final groups' `learning_enabled`, mode and snapshot, rather than merely checking a local boolean.
- **Pre-update and final comparisons are real consumers:** the controller stores a measured adaptation step before evolve (`:141–147`), records snapshot_after and the evolution result (`:174–177`), and aligns final mean gains by task ID with null propagation (`:199–212`). It does not call a held-out success rate a pre-update gain.
- **Split audit:** adaptation/final and selection/final ID, source and public-content overlaps are computed; family separation is additionally enforced for a family-level claim (`:48–64`). Unknown source/family metadata prevents an unseen claim. Selection material is kept distinct from final material; model pretraining exposure is explicitly unknown.
- **Provider versus local costs:** unique usage IDs are deduplicated with conflicting contents rejected (`report.py:16–34`); token/time missingness is kept separate. `telemetry.py:18–22`, `:42–56` excludes declared separately recorded synchronous work and records null cost without a price. Excessive exclusion becomes unknown, not negative/free work. Tests cover successful, failed and unpriced local work.
- **Wall clock:** report groups start/end records by segment ID, keeps the completed record over its start marker, and exposes incomplete active-wall totals when an end is absent (`report.py:344–359`). Sampling batch receipts are returned separately (`:488–490`), preserving end-to-end span versus active segment time; summed per-call time is not silently renamed wall time.
- **Longitudinal output:** `_library_history` reads committed release generations/snapshots, including rollback (`:363–377`); `_memory_progress` consumes actual goal/checkpoint/learning/maintenance records (`:407–428`); `_consumption_layers` separates provided, reported read, reported behavior and conditional contrast results (`:380–404`). The real two-publish-plus-rollback fixture in `test_memory_completion.py:86–107` reaches these report fields. No missing native adapter is treated as an O12–O14 defect, and no semantic accuracy or net maintenance benefit is inferred from these structural counts.

## Evidence boundary

This is a static review during another worker's mutation window. The two findings need bounded executable regressions in the root's subsequent safe window. No broad redesign, extra native client, new benchmark, or future feature is proposed.

## Follow-up status

The coordinator subsequently reproduced both findings as real RED cases and fixed the root-owned consumers; the original output is retained in `research/root-review-red.txt`. B did not take ownership of report/experiments. B's later controlled-interruption learning regression now also directly verifies that an unfinished model cycle yields unknown complete cost in the fixed report, while its provider wait is excluded from local maintenance. The original static findings above are retained as the audit record rather than rewritten as new defects.

## Targeted closure review after root mutation restoration

The root explicitly released its exclusive window after **12/12** official variants were detected and every target hash restored. B then read only the restored source and the stable existing test/log evidence. **No Python/test/model command was run in this closure review, no product/schema file was changed, and no new issue was added.**

1. **Frozen experiment configuration: CLOSED.** `experiments.py:93–95` now copies dataset/protocol and the full sampling/context/learning/comparison/verification/seed tuple before the plan is stored or either factory is invoked. The loop consumes these private copies; seed initialization at `:125` occurs from the copied seed before `execution_factory` at `:127`, and later sampling/evolution use the copied policies (`:139–142`, `:167–170`, `:185–186`). The actual regression `test_memory_experiments.py:16–40` mutates retained original sampling, context and seed inside the factory, then checks identical arm baselines, the saved repeat count 2, and actual persisted run-group repeat count 2. `root-review-red.txt` retains the pre-fix second-arm seed failure; `root-review-green.txt` includes the passing regression in its **10-test GREEN** run.

2. **Interrupted model call cost completeness: CLOSED.** `report.py:462–463` explicitly collects still-planned learning cycle IDs as `unfinished_learning_cycle_ids`. Their presence is included in the completeness guard at `:472`, which leaves complete monetary totals and every complete token total null (`:473–474`) while preserving observed subtotals. The actual regression `test_memory_completion.py:140–158` starts a real StructuredModel invocation, interrupts it, reopens the Store and checks all three behaviors. Its original RED was `{}` rather than null; the same test is present in the **10-test GREEN** log.

3. **Related provider-wait boundary: CLOSED and separately verified.** `learning.py:329` starts call-wall timing; its non-DomainError branch at `:338–342` excludes that elapsed time before re-raising unchanged. `test_memory_learning.py:662–682` advances a controlled monotonic clock by 30 seconds inside the transport and observes elapsed=30, delegated=30, local=0, no fabricated usage, a planned cycle, and unknown complete cost. B executed this regression and the **36-test learning module GREEN** before its own official window. `B-mutation-evidence/interrupted_wait.log` and `results.json` record the corresponding official mutant detection and exact restoration as one of **20/20** B licenses; the restored B suite subsequently passed **75/75**. The timing fix does not stand in for the report fix: they close distinct local-time versus missing-provider-cost boundaries.

Restored source hashes inspected during closure:

- experiments.py: `bdbad3b5d605e4d20b19b682aae0f411ac532068d5f370774d77c5494b96a7d5`
- report.py: `cf482e5be5f4cf2f59195123b782ce5a72211ba8f651ef99cad05aa2c68fba6d`
- learning.py: `2f2ce0f844b680ea6a1d2e6d61dffc39bf0b6872a5a16e8f717e453e808f6eca`

Both original static findings are closed for these concrete paths. This closure adds no claim about live model semantic performance, benchmark gain or unseen-task generalization.
