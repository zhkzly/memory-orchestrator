# B implementation handoff: O01/O02/O04/O05/O15

This is an implementation plan, not a completion claim. Existing raw records, source admission, v2 packet provenance, model limits and semantic-repair hooks stay authoritative. No product files changed in this planning pass.

## One actual learning path

`learn → source admission → ensure trace index → admit discovered parent sources → bind missing user goals → failure-aware related lookup → build/expand packet → extract → maintain experiences → diagnose necessity → propose allowed operations → existing checks/publication`.

Each step has a consumer below. No standalone background service, native adapter, workflow registry or independent truth judge is added. Existing in-memory episodes remain supported.

## O01: goal association enters learn

- Invoke `goal_binding_v1` only for known user instruction events whose goal/task identity or revision is missing; do not reinterpret agent plans as user requirements.
- `associate_goals(store, index, model, limits) -> annotated_index, binding_record_ids`. `learn` calls it before extraction. Process bounded user-event windows in source order with a bounded catalog of prior observed/derived goals; stop with explicit unresolved ranges when call/read budgets end.
- Keep `fragments.structure` observed values unchanged. Derived labels enter a separate `goal_annotations` projection, used by goal-aware evidence grouping and shown to extract/diagnose with `origin=model_proxy`.
- Existing `GoalBindingDraft.bindings` fields remain: `event_refs,goal_id,revision,relation,evidence_refs`. Add `anchor_user_ref:string` and `reason:string` to each binding.
- Add draft fields `status:completed|needs_more_evidence|abstained`, `read_requests:[{ref_id,purpose}]`, `reason:string`; retain `unknowns:string[]`.
- `goal_id` and `revision` may reference supplied known identifiers or `new:<local_slug>`. Host allocates **derived** IDs from project/episode/user-anchor/local-label; these never become observed task IDs or independent-task counts.
- `goal_binding_v1` inputs: `user_events,goal_catalog,indexed_event_refs,readable_ref_catalog,binding_limits,output_schema`. The catalog identifies whether each entry is observed or model-derived and supplies its grounding references.
- Pure check: references must be provided, anchors must be user instructions, event positions must not precede their anchor, known raw identities cannot be contradicted, resume targets must exist, local names must resolve within this draft/window. Catalog-only bodies are not evidence.
- Host record `goal_bindings`: `{record_id,project_id,episode_ids,index_ref,source_hashes,model_report_ref,draft,resolved_bindings:[{event_refs,goal_id,revision,relation,anchor_user_ref,evidence_refs,origin:'model_proxy'}],unresolved_refs,created_at}`.
- EvidencePacket additive `goal_annotations:[{binding_ref,event_ref,goal_id,revision,relation,anchor_user_ref,evidence_refs,origin:'model_proxy'}]`. Only exposed/readable endpoints are projected; no invisible source is smuggled into the packet. Raw and derived goal views remain distinguishable.

## O02: disk-backed source and dependency lookup

- Add `trace.py` for the **current** JSONL event source, not arbitrary storage backends. `import_trace(store, episode_header, source_path, limits)` freezes the source bytes and returns an episode with `events=[]` and `trace_ref`.
- Add optional `EpisodeRecord.trace_ref:string|null`. Ordinary array events keep their present path. Host-owned raw archive and manifest are immutable; resumption updates append-only indexing checkpoints, not raw bytes.
- `ensure_trace_index(store, trace_ref, limits) -> index_handle, progress`. Use stdlib SQLite for metadata/search tables and incremental JSONL reads. Memory is bounded by the largest input event plus the configured indexing batch, not the whole trace.
- Record raw-line byte locators separately from UTF-8 decoded text offsets. A derived text spool permits direct body-range reads; never label decoded-text offsets as offsets into escaped JSONL bytes.
- `TraceManifest`: `{trace_id,project_id,episode_id,format:'events-jsonl-v1',raw_path,raw_sha256,byte_length,text_path,index_path,index_version}`. Paths are host-generated relative paths under the explicit Store root.
- Index rows: `{base_ref,event_id,source_line_range,text_range,text_hash,kind,source_position,call_id,goal_id,task_id,task_revision,source_role,parent_refs,resource_refs,failure_terms}`. Bodies stay out of metadata query results.
- `TraceIndexCheckpoint`: `{checkpoint_id,trace_id,raw_sha256,index_version,next_raw_byte,event_count,index_complete,parent_episode_refs,bytes_processed,error,created_at}`. `learn` resumes indexing or returns `needs_index`; it must admit all discovered known parent sources before model work.
- The existing evidence functions use a narrow internal record-source interface: `select_metadata(query,limit)`, `get_metadata(ref)`, `read_range(ref,start,end)`, `neighbors(ref,kinds,limit)`. Both current in-memory indexes and the new disk index actually consume it; no backend registry.
- Refactor `build_packet` to select bounded metadata candidates **before** reading snippets. Do not materialize all text or build a `_pieces` dictionary for every event. `expand_packet` seeks only advertised ranges and verifies source identity/hash.
- Add optional event `resources:[{kind:file|artifact,ref:string,access:read|write|check|mention,version_ref:string|null}]`; existing events default to no declared resources. A must preserve this field when sampling/importing.
- Dependency lookup starts from feedback/action/file/artifact focus and follows declared parent/call links plus matching resource identities, with explicit hop/event/byte limits. Same-path text mentions are retrieval hints, not proven dependencies. Cross-episode file matches require explicit shared identity/version or parent linkage.
- Add EvidencePacket `resource_relations:[{from_ref,to_ref,resource_ref,relation:declared_parent|same_resource_candidate|text_mention,version_match:boolean|null,coverage:complete|partial}]` for the selected neighborhood only. Existing source roles and gaps retain uncertainty.
- Every fragment keeps existing decoded-body `range/raw_hash`; optional `source_record:{trace_ref,raw_range,raw_sha256}` records the original serialized-record locator. This prevents ambiguity about which bytes were read.
- Mutation or replacement of archived bytes invalidates the index/read. No silent reuse of a stale offset, no fake complete index after truncation; malformed records retain raw locators and diagnostics.

## O04: failure-aware retrieval and semantic maintenance

- Derive a bounded `failure_signature` from explicit failed criterion IDs, structured error codes, declared operation/tool/resource metadata and normalized textual symptoms. Missing values remain null; regex/model labels retain their origin, not external-verifier status.
- Experience host envelope gains `failure_signature:{criterion_ids:[],error_codes:[],operation:null|string,resource_kinds:[],symptom_terms:[],origin:observed_fields|text_pattern|model_proxy,evidence_refs:[]}`.
- `find_related(...,failure_signature,...)` actually ranks signature matches alongside existing task/scope terms, returning score components and preserving source eligibility. Newly stored experiences carry the signature; older records can still match by existing terms.
- Add `maintain_experience_v1` after extraction/storage of new experience and before diagnosis. Input only bounded new/related eligible records, their reference catalog, active maintenance links, and the maintenance limits.
- Exact prompt inputs: `new_experiences,related_experiences,comparison_evidence,existing_relations,maintenance_limits,output_schema`.
- New `ExperienceMaintenanceDraft`: `{actions:[MaintenanceAction],unknowns:string[]}`.
- `LINK_DUPLICATE`: `{op,record_ids:[string,string],preferred_record_id:string,reason:string,evidence_refs:string[]}`.
- `MARK_CONFLICT`: `{op,record_ids:[string,string],scope:string,reason:string,evidence_refs:string[]}`.
- `REVOKE`: `{op,relation_id:string,reason:string,evidence_refs:string[]}`. `NOOP`: `{op,reason:string}`.
- Pure checks bind actions to supplied record IDs/current revisions/project, actual provided comparison content and existing relation IDs; reject destructive/raw/fact writes, ambiguous targets and over-budget actions. A comparison may cite provided experience text as a **derived artifact**, but those refs never become raw observed-fact citations.
- `apply_maintenance` writes immutable `memory_relations` plus a `maintenance_reviews` receipt. It does not erase experiences or user/project facts; every judgment is labelled `model_proxy` and can be superseded/revoked.
- Actual consumers: `find_related` folds duplicate aliases into one representative while carrying the union of sources/boundaries; unresolved conflicting records are supplied together or excluded together if the pair cannot fit. `_save_experience` and maintenance reuse the shared source-admission rule for every member, including mixed-source history.
- `diagnose_v1` receives active conflicts/duplicate groups and can target a existing Skill accordingly. Conflicts are not marked factually resolved merely because a model prefers one side.

## O05: use the existing diagnosis call, not another vote

- Add `DiagnosisDraft.necessity:{verdict:proceed|noop|needs_evidence,repeatable:boolean|null,compared_skill_refs:[{skill_id,revision}],capability_gap:string,behavior_delta:string,allow_add:boolean,evidence_refs:string[],unknowns:string[]}`.
- Extend `diagnose_v1` input with `existing_capability_catalog` and `necessity_limits`; prompt explains exactly which Skill bodies were supplied and which remain unread. Existing `target_snapshot`, targets and expected_behavior stay in use.
- Pure check verifies comparison references/base revisions, supplied raw evidence and known targets. `proceed` requires a concrete behavior delta and repeatable applicability; `allow_add=true` needs a stated gap. An unread potentially relevant capability yields uncertainty, not a claim that the library contains no equivalent.
- `learn` consumes verdict before proposal: noop skips proposal, needs_evidence follows its bounded evidence path or stops unresolved; proceed restricts allowed operations. `allow_add=false` makes an emitted ADD a semantic error within the existing repair budget.
- Pass the decision into `propose_v1`; preserve coupled PATCH+RETIRE or ADD+PATCH packages when justified. Do not restrict an entire transaction to one atomic operation type.
- Store the decision in the existing diagnosis record with `decision_origin=model_proxy`. It is a necessity hypothesis, not a measured generalization claim. C's actual checks/publication remain required.

## O15: limits, errors, telemetry and reporting

- C handoff confirmed: `learn(...,verification_catalog=None)` passes a public catalog to diagnose/propose. Every check-plan item explicitly carries `check_ref:string|null`. `apply_candidate` accepts `diagnosis_ref=None,diagnosis_hash=None`; learned proposals pass the real persisted diagnosis ID and the digest of its entire record. C unions diagnosis and proposal obligations, so proposal cannot silently drop the original checks.

- Add explicit policy sections `goal_binding`, `trace_index`, `dependency_lookup`, `maintenance`, `necessity`; each contains only limits used by these consumers. Root's StructuredModel global calls/input/output/repair budget covers all new calls; no hidden retry or independent unmetered client.
- Goal/read failures retain unresolved/abstained records. Invalid maintenance decisions write a failed review and leave the current view unchanged. Every completed semantic action is derived and reversible; no partial application of a rejected action package.
- Reuse the existing model-call persistence path, extending its concrete prompt→stage mapping: `goal_binding_v1→index`, `maintain_experience_v1→extract`; necessity stays in `diagnose`. The same SDK call is charged once even when it has multiple responsibilities.
- Use root `telemetry.measure_stage(...)` around indexing, range reads, maintenance and local merging. Deduct separately counted synchronous SDK time via `meter.exclude(...)`; do not add model costs again as maintenance totals.
- Report event facts: goal calls/observed-vs-derived coverage/ambiguities; indexed bytes/events/completion/range-read bytes/dependency kinds; signature hits; duplicate/conflict/revocation actions actually applied; unresolved conflicts; necessity verdicts/compared bodies/ADD denied/NOOP. Distinguish attempted judgments from applied actions.
- Root/A additions required: schema/prompt fields above; Store collections `trace_manifests,trace_index_checkpoints,goal_bindings,memory_relations,maintenance_reviews`; retain old archives and known-source admission for trace parent refs. Root report consumes these receipts, not regenerated guesses from prompt wording.

## Acceptance and handoff

Tests must hit the actual learn/model path: missing labels → grounded derived annotation → changed extraction context; A→B→A and old feedback preserved; agent plans rejected as goal anchors; byte-exact multibyte reads/reopen/resume/stale-source rejection; failure-code retrieval over a lexical distractor; semantic duplicate folding and unresolved conflict co-return without lost counterexamples; identical-capability ADD blocked while a justified gap reaches the existing proposal/check pipeline.

Large JSONL tests prohibit whole-file text loads and check bounded metadata/body batches. Model substitutes exercise real prompt/schema/repair/usage paths; no real model or benchmark call is part of these tests. No implementation or independent-effect claim is made by this plan.

## Implementation checkpoint

- Root approved this plan and full B implementation. Product work is now underway in B-owned files; shared model/schema/prompt fields are supplied by root, Store collections by A, candidate verification by C.
- New `test_memory_maintenance.py` first failed on the absent module. `maintenance.py` now implements bounded comparison inputs, pure action checks, receipt-anchored links/revocation, conflict/duplicate retrieval views and failure-signature extraction; 4/4 focused tests passed. This is a data-layer checkpoint, not completed O04: the actual `learn` model path is the next consumer to connect.
- No network, live model, benchmark, commit or new agent has been invoked by B.

## Integrated implementation checkpoint (2026-09-19)

- `learning.learn` now invokes bounded missing-goal association before extraction, failure-aware retrieval, semantic maintenance when distinct eligible comparisons exist, explicit diagnosis necessity, constrained proposal operations and C's saved diagnosis hash/ref binding. Empty-library single-experience learning does not make a vacuous pair-comparison call.
- `goals.py` preserves raw identities and supplies derived annotations with `model_proxy` provenance. Earlier goal catalogs include source-backed excerpts, later user windows cannot justify earlier anchors, A→B→A resumes the previously derived ID. Invalid/ambiguous goal output is retained as unresolved; global model-budget exhaustion stops further windows.
- `trace.py` freezes original JSONL, incrementally commits SQLite metadata plus append-only checkpoints, and reads decoded UTF-8 text in verified byte chunks. Original serialized line locators are separate from decoded-body ranges. Reopening checks raw/index/spool digests; per-reader changes invalidate reads. One over-budget event remains unresolved and can resume under a larger explicit cap; malformed raw records retain their exact line range and do not become complete.
- `index_episodes(..., store=..., trace_limits=...)` is the shared trace consumer. A's proxy feedback path uses it and preserves `needs_index`; B's learning path returns `needs_index` before model calls. Complete archived parent references enter A's shared source-eligibility check, including historical memory reuse. B may load admitted parent episodes within the declared dependency hop/event budget.
- `build_packet` selects bounded metadata candidates before reading bodies. Calls, goals, parent pointers and file/artifact neighborhoods retain only visible or readable endpoints. Same-resource matches are explicitly candidate dependencies. Metadata, catalogs, relationships, derived annotations and source locators remain in the packet character/token budget.
- `maintenance.py` writes immutable relation actions and a final review receipt; unanchored relations do not affect retrieval. Duplicate folds preserve sources and historical adverse references. A conflicting pair (including one connected through a third duplicate) is returned together or excluded together if it cannot fit. `maintenance_summary(store, project_id)` and report share the same active/revoke/fold rules.
- Failure signatures have a declared character bound in the real learn path, explicit omitted-occurrence counts, and `text_pattern` origin for textual features. Saved signatures use the experience's cited source episodes. Pattern labels and semantic maintenance remain retrieval judgments, not external task truth.
- New model calls use existing StructuredModel limits/repairs and the unique usage ledger: goals=index, maintenance=extract, necessity=diagnose. Local index/select/merge/application measurements are separate; synchronous model time is excluded where already recorded.

### Actual checks so far

1. New maintenance module test initially RED: `ModuleNotFoundError: memory_orchestrator.maintenance`; first host action tests then 4/4 GREEN.
2. Real learning necessity NOOP / forbidden ADD / missing-goal consumer tests initially RED (two missing current prompt inputs, one actual transport still `extract_v1` instead of `goal_binding_v1`). They now pass through the same StructuredModel transport and pure repair checker used by production.
3. New trace tests initially RED: `ModuleNotFoundError: memory_orchestrator.trace`. Current trace cases include re-open/resume, multibyte byte ranges, tamper/symlink rejection, malformed line preservation, larger-budget continuation, dependency lookup, actual learn input and hidden frozen parent refusal.
4. Latest command: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_trace test_memory_learning test_memory_goals test_memory_maintenance test_memory_evidence -q` → **65 tests, exit 0**.
5. A is independently reviewing the now-stable B product source. No mutation window has been requested or used yet in this task. These are constructed behavior checks with actual files/model-boundary consumers; no real model/benchmark learning gain was measured.

### Concrete data/API handoff

- B host shapes are in `research/B-schemas.json`; model schemas/prompts remain root-owned canonical definitions. `FailureSignature.coverage` uses `complete`, `omitted_feature_occurrences`, `omitted_evidence_occurrences` (counts are occurrences, not invented unique counts).
- New learn policy: `necessity.max_compared_skills`; `maintenance.max_chars/max_pairs/max_actions` when comparisons exist; missing-user-goal policy `max_events/max_bindings/max_read_requests/max_expansions/max_catalog_goals/packet`; traces `max_events/max_bytes/max_event_bytes`; dependency lookup `max_hops/max_events`.
- `learn(..., verification_catalog=None)` passes only the supplied public check directory to diagnosis/proposal. New generated check items require `check_ref` or explicit null; no check obligation is removed to make a candidate pass.
- Learning cycles expose `goal_binding_ids`, `maintenance_review_ids`, `trace_checkpoint_ids`, failure retrieval component counts and `read_stats`. `body_bytes` counts bytes actually read from decoded text chunks, `range_reads` counts requests; integrity-hash passes and original JSONL processing are distinct local index work, not LLM context bytes.

### Final consumer checks before mutation

- Root imported all six host schemas. Their actual writer/read validators exposed two unclosed local `$defs` pointers; root fixed them by embedding the exact model Draft definitions. B handoff now copies that same self-contained shape, and real writer cases pass. No fallback generic object validator was added.
- The signature budget now derives from the explicit `packet.max_chars`, so `max_related_chars=0` remains a legitimate way to disable related lookup without disabling current-source learning. A direct consumer test covers this.
- The indexed reader shares a bounded cache between metadata and verified decoded chunks; its total cache bound is derived from the packet's declared character budget. A source stat/hash change still invalidates the reader; cache hits do not pretend to be physical reads.
- Newly generated diagnosis/proposal checks are validated while model repair is still available: `check_ref` must be null or a supplied public-directory entry of the same purpose. A real RED showed the previous path accepted an invented diagnosis check then entered proposal; the corrected path repairs the diagnosis before proposal. Private grading fields are not accepted as public catalog fields.
- Latest focused run is **70 tests, exit 0** with the same five-module command above. A's independent actual-consumer probe is archived under this task's `research/A-review-B.py` and JSON evidence; it verified disk→learn, hidden frozen parents and maintenance→next extraction before these bounded refinements.
- `research/B-mutations.py` contains 16 exact single-edge injection cases. They are prepared but not executed yet; the root coordinates the exclusive official mutation window.

### Source ancestry closure

- A aligned missing inline parent handling with archived parent handling: missing external material remains an explicit gap, while known foreign/final sources remain forbidden.
- A three-level public-input counterexample was then RED: an ordinary inline child pointed to an unindexed trace parent whose archived event pointed to a known final execution. A zero dependency-body budget previously allowed extraction before the hidden ancestor was admitted.
- `lineage.require_learning_source` now returns the shared `unindexed_trace_refs` across the entire known parent chain. B advances those source indexes under the explicit trace-index budget and rechecks admission before model work, independently of optional dependency-body retrieval. Historical experience reuse rejects unresolved ancestry; it does not invent a source verdict.
- The exact counterexample now passes with zero model calls and no extracted memory. Latest full B-focused result is **71 tests, exit 0**. The `archive_parent` mutation targets this active ancestry barrier, rather than a now-redundant later parent check.

### O12 normalized provider price preservation

- Root identified the existing normalized outer usage price fields being discarded by `learning.persist_call`. An actual StructuredModel → learn regression first failed with persisted `monetary_cost=None` despite transport `response.usage.monetary_cost=0.125`, USD, and an explicit provider price version.
- Root now normalizes only transport `response.usage` fields in model.py. B's narrow change copies `monetary_cost`, `currency`, and `price_version` from each normalized usage entry into the existing ledger. It never reads the model JSON body, and absent fields remain null.
- Three actual consumer regressions pass: priced invocation reaches `report()['usage']` intact; unpriced transport plus a forged model-body price remains unknown; rejected format attempts retain their cost while an explicitly reported zero stays zero. Latest `test_memory_learning` result: **35 tests, exit 0**.
- Three separate fee-binding injections were added to the prepared official mutation cases, now **19** total. No mutation has been executed yet; B source is frozen again pending the coordinator's exclusive window.

### Interrupted provider timing boundary

- Root's follow-up identified that an uncaught BaseException has no returned usage, so the entire model-call wait was previously counted as local maintenance. A controlled monotonic test advanced exactly 30 seconds inside the real StructuredModel transport, raised the same KeyboardInterrupt instance, and first failed at `delegated_seconds: 0.0 != 30.0`.
- The narrow `learning.call` branch now measures call-wall time and excludes it on non-DomainError exceptions before re-raising unchanged. It writes no invented usage/tokens/fee and does not finalize the learning cycle.
- The same regression now observes elapsed=30, delegated=30, local=0, stage=error, no usage records, a still-planned cycle, and the root report's unknown complete cost. `test_memory_learning` is **36 tests, exit 0**. One corresponding official injection was added, bringing the prepared B set to **20**; no mutation run has started yet.

## B final verification and window release

The root subsequently granted the exclusive window. All **20/20** official mutation calls exited 0 and restored exact target hashes; the runner's final `all_files_restored` was true. The restored five-module suite passed **75/75**, and B source/test `git diff --check` passed. Exact commands, official outputs and hashes are saved under `B-mutation-evidence/`; completion/limitations are consolidated in `B.md`. The window has been released and no further B product/schema edits or dependent Python checks are in progress.
