# M1 storage evidence

Scope: only `store.py`, `schemas.py`, packaged `schemas.json`, and `test_memory_store.py`.
Direct source: blueprint v1.4 node contracts plus `src/store.ts` JSON frontmatter/Claim and `scripts/harness.mjs` project/personal fixture.
Current missing behavior: no importable Python store, immutable records, project-bound episodes/feedback, or snapshot persistence.
No CLI/MCP/native execution, publication bypass, old TS deletion, model calls, or edits outside this ownership.

Tests are constructed from current examples and actual serialization, not evidence of Agent effectiveness.
Initial red command: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_memory_store.py' -v`.

## Decisions

- `SkillRevision` uses `{skill_id,revision,project_id,content:SkillContent,asset_refs:[]}`. Relationships live only in `content.depends_on` / `content.declared_conflicts`; this shape was confirmed with main.
- A new project bootstraps an empty snapshot at generation 0. Saving arbitrary snapshots never changes active. N10 release remains a later consumer; M1 adds no public active setter.
- Incomplete imported metadata is retained, while known references must resolve within the same project. Unbound feedback can be retained without claiming it evaluates the current state.
- First RED: import failed with `ModuleNotFoundError: memory_orchestrator` (1 discovered loader error, not a passing behavior test).
- First implementation run: 12/13 passed. The one failure was a stale test expectation after main explicitly requested immutable release archiving for the M3 consumer; policy review found no code bug. Test now distinguishes raw release records from committed history and checks the private CAS primitive.
- Main approved `add_episode(..., feedback_records=())` for existing feedback imported with original references. All identities are checked before writes; records remain individually atomic and immutable. An IO-interrupted bundle can be completed by exact retry and missing referenced feedback is reported, not silently treated as absent.
- Main and release worker approved N10-only `_commit_release` and `release_history`. Active atomically contains commit metadata and committed IDs; orphan release files do not count as publication.
- Official mutation audit caught a test gap: bypassing `_put_unlocked` conflict did not fail because episode imports have an independent preflight. Added a direct generic usage-record append/idempotency/conflict test, without changing implementation. This distinguishes both immutable write paths.

## Executed checks

- Final focused run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_memory_store.py' -v` — 18/18 passed, exit 0.
- Python `compile()` succeeded for both source files and test file; `git diff --check` exited 0.
- Packaged schemas are exact copies of all 18 current blueprint schemas, source v1.4.1, SHA256 `10a9fa5076d4f31f5496a4b87614d452a7f2b08bea2c36ae4515888fc1d21ebc`. Prompts are owned separately by the learning worker; `load_contracts` verifies the two source identities match.
- Official `/home/kelong/ai-workbench/tools/mutation_license.py` completed 20/20 final mutations, each with green baseline, changed target + red test, exact-byte restore and green test. Mutations used the `apply_patch` command; restoration was performed only by the official tool.
- Mutation bindings: project scope, generic append immutability, record checksum, list project filter, fact project filter, legacy exact scope, episode/context snapshot, episode/context task, episode/context revision, feedback subject, feedback revision, asset inventory, safe asset path, dependency cycle, dependency conflict, snapshot checksum, CAS generation, orphan publication exclusion, schema rejection, packaged source identity.

## Final source identity

| File | SHA256 |
| --- | --- |
| store.py | d69e60fa07c7ae258c318986be8213eac798c9e05de2420bc8c8ae0ed610402e |
| schemas.py | ead64041118db97978ca60d83c3eaeedaa6c29a02e8de003996007ca060f49b5 |
| schemas.json | e03c6b74f0397356b6bdd6a0e704ca614d3e669f78b730d20a683f5dc34f07e7 |
| test_memory_store.py | 50003466752a7669306740047322e00534f8fd595b1320b52440edb4e367bd0c |

## Boundaries

The tests prove local persistence, namespace/binding checks, immutable bytes, dependency/asset integrity and the private mechanical CAS. They do not prove memory correctness or downstream task benefit. N10 owns validation/selection policy before `_commit_release`; archiving a release is not activation. Locking uses POSIX `flock`, not a distributed store. Individual imported records are atomic, while an interrupted multi-record import may require exact retry; missing declared feedback produces an error until completed. Legacy parse failures are returned with path/code and reads do not modify old files. No model call, native client, CLI/MCP, TS deletion, global configuration change or commit was performed by this worker.
