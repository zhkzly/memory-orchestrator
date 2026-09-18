# M3 evaluation, selection, release and report

Goal: implement N09–N11 with ordinary Python execution/evaluation functions.
Invariant: persist every request before execution; bind exact cases, snapshots and protocol.
Invariant: unknown or incomplete evidence is never accepted; publication additionally requires selection and CAS.
Invariant: raw responses and unique usage remain auditable; no claimed benchmark/generalization gain.
Owned files: evaluation.py, release.py, report.py and their three test_memory_* files.
Excluded: CLI/MCP/native adapters, models, shared Store/schema edits, commits.
Reference: blueprint v1.4.1 schemas and CSV worked example; tests are constructed local function checks.

## Evidence log

- API agreed with main: candidate uses proposal_id/project_id/base_digest/candidate_digest/expected_generation; cases separate public task from private criteria. Protocol parameters and missing-cost selection behavior are explicit.
- Each candidate has a full old/new request plan; all candidate plans and frozen inputs precede callbacks. Evaluation does not publish or learn.
- RED: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_memory_evaluation.py -v` failed on unavailable Python package/schema before implementation.
- First integrated GREEN: evaluation 10, release 7, report 5 = 22 tests passed against real Store, temporary files, CSV task/evaluator functions and actual filesystem CAS. Additional report missing-scheduler-cost check added afterward, pending next coordinated test window.
- Storage/locking is Store._commit_release and release_history. Release module performs actual protocol/evidence/selection checks before calling it; orphan release records are never accepted as committed history.
- Cost gate covers the entire comparison round; project report separately includes all stored maintenance stages. Call-budget gate counts planned evaluations, not total model requests or monetary cost. Ordinary callbacks must terminate and supply request-local/resettable environments; there is no OS isolation or hard timeout claim.
- Test/mutation coordination: root requested pause while Store worker mutates dependencies; no further tests or mutations until the coordinated window opens.

## Official mutation checks
- `evaluation.py` / `return_identity`: exit 0; ✅ 执照发放:src/memory_orchestrator/evaluation.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。
- `evaluation.py` / `input_immutable`: exit 0; ✅ 执照发放:src/memory_orchestrator/evaluation.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。
- `evaluation.py` / `score_type`: exit 0; ✅ 执照发放:src/memory_orchestrator/evaluation.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。
- `evaluation.py` / `per_case_regression`: exit 0; ✅ 执照发放:src/memory_orchestrator/evaluation.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。
- `evaluation.py` / `unknown_cost`: exit 0; ✅ 执照发放:src/memory_orchestrator/evaluation.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。
- `evaluation.py` / `plan_before_execution`: exit 0; ✅ 执照发放:src/memory_orchestrator/evaluation.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。
- `release.py` / `revalidate_gates`: exit 0; ✅ 执照发放:src/memory_orchestrator/release.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。
- `release.py` / `selected_binding`: exit 0; ✅ 执照发放:src/memory_orchestrator/release.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。
- `release.py` / `orphan_history`: exit 0; ✅ 执照发放:src/memory_orchestrator/release.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。
- `report.py` / `unique_cost`: exit 0; ✅ 执照发放:src/memory_orchestrator/report.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。
- `report.py` / `planned_denominator`: exit 0; ✅ 执照发放:src/memory_orchestrator/report.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。
- `report.py` / `unknown_cost`: exit 0; ✅ 执照发放:src/memory_orchestrator/report.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。

## Token/sampling report follow-up
- RED: 3 new token/sampling tests failed (missing keys/invalid tokens accepted); GREEN: report 9 tests passed.
- report.py / token_total_not_double_counted: exit 0; ✅ 执照发放:src/memory_orchestrator/report.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。
- report.py / unknown_token_totals: exit 0; ✅ 执照发放:src/memory_orchestrator/report.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。
- report.py / sampling_completeness: exit 0; ✅ 执照发放:src/memory_orchestrator/report.py 注入错误时变红、按快照还原后回绿——该验收有资格存在。

## Per-case reporting and malformed usage follow-up

- RED: three report comparisons tests failed on absent `comparisons`; GREEN: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_memory_report.py -v` passed 12 tests.
- `report.comparisons` reuses evaluation._summaries for each frozen plan and historical validation. It separates target/regression/transfer, per-case means/ranges/gains/repeat coverage, exact scope and missing requests. It does not re-evaluate historical gates against current active.
- Official report mutations `per_case_gain`, `split_separation`, `historical_status`: 3/3 killed and restored.
- RED: a callback returning tokens 1.5/True, cost -2 and currency [] made the project report fail. `evaluation._usage` now consumes shared normalize_usage_measurements, preserving raw and four diagnostics; task scoring remains unchanged, malformed measurements are unknown.
- GREEN and official mutation: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_memory_evaluation.py -v` passed 11 tests; bypassing token normalization was killed and restored. M3 owned tests now total 11 evaluation + 7 release + 12 report = 30; owned official mutations cumulative 19.

## Independent read-only review of learning fixes

Command form: `PYTHONPATH=src:tests .venv/bin/python - <<'PY'` using actual temporary Store, sample_tasks and learn, with existing EXAMPLES/csv_episodes fixtures and StructuredModel(FakeCall). No source mutation, external model request or benchmark execution.

- Frozen source probe: sample_tasks with purpose=final, update_mode=none, repeat_count=1, then learn(returned episode). Original result was 2 scripted calls and 1 experience write. Recheck: learning_not_permitted, 0 calls and 0 experience writes.
- Long feedback probe: imported episode plus adaptation feedback reason=`'ERROR ' + 'long-result ' * 15000`; packet limits 6000 chars/300 fragment chars/3 catalog refs. Original duplicated 180539 feedback chars and made 0 calls due to model_budget_exhausted. Recheck: feedback view 702 chars, packet 4002 chars, one scripted call and no budget error; returned abstained was the supplied valid model answer.
- Boundary probe: learn CSV experience, then same kind/scope/guidance with empty boundary_refs/counterevidence_refs, then recall with max_related_episodes=0. Recheck: retained boundary count 1, included in the actual model related_experiences input with body_provided_in_current_packet=false; validate_citations rejects using that unread historical ref as current evidence.
- Token probe: scripted model response usage.input_tokens=1.5 followed by learn then report. Recheck: stored input_tokens=None, output_tokens=7, report succeeds with missing input measurement count 1.
- All four original causal failures are closed in the independently re-run inputs. This is bounded implementation evidence, not actual model learning gain.
