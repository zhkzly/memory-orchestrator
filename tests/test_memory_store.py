"""Constructed contract cases, derived from blueprint examples and TS store fixtures.

These tests exercise persistence and binding, not real Agent learning quality.
"""

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from memory_orchestrator.schemas import DomainError, digest, load_contracts, validate
from memory_orchestrator.store import Store


BLUEPRINT = Path(__file__).resolve().parents[1] / "docs/blueprint/project-contract.json"


def example(name):
    contract = json.loads(BLUEPRINT.read_text(encoding="utf-8"))
    return copy.deepcopy(next(item["value"] for item in contract["examples"] if item["id"] == name))


def episode(project="alpha", identifier="episode-1"):
    value = example("imported-episode")
    value.update(episode_id=identifier, project_id=project, context_ref=None,
                 source_snapshot_ref=None, feedback_refs=[])
    value["task"]["task_id"] = None
    value["task"]["revision"] = None
    return value


def skill(identifier, project="alpha", dependencies=(), conflicts=(), asset_refs=()):
    # The procedure content derives from the actual CSV experience example.
    exp = example("experience")
    return {
        "skill_id": identifier, "revision": "r1", "project_id": project,
        "content": {
            "title": exp["title"], "scope": exp["scope"], "triggers": ["CSV"],
            "preconditions": [], "steps": exp["guidance"]["steps"],
            "exceptions": [], "checks": exp["guidance"]["checks"],
            "depends_on": list(dependencies), "declared_conflicts": list(conflicts),
            "evidence_refs": exp["supporting_refs"],
        },
        "asset_refs": list(asset_refs),
    }


def feedback(subject="episode-1", project="alpha"):
    value = example("criterion-feedback")
    value.update(check_id="check-late", subject_ref=subject, project_id=project,
                 task_revision=None, evaluated_state_digest=None, run_id=None,
                 checked_at=None, binding_status="partial")
    return value


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "memory"
        self.store = Store(self.root)

    def assert_domain(self, code, fn, *args, **kwargs):
        with self.assertRaises(DomainError) as raised:
            fn(*args, **kwargs)
        self.assertEqual(code, raised.exception.code)
        return raised.exception

    def test_explicit_seed_is_generation_zero_and_cannot_replace_existing_baseline(self):
        seed = {"skills": {"csv": skill("csv", asset_refs=["csv/scripts/check.py"])},
                "assets": {"csv/scripts/check.py": "assert '001'.startswith('0')\n"}}
        active = self.store.initialize_project("seed-project", seed=seed, source="constructed CSV fixture")
        self.assertEqual(active["generation"], 0)
        self.assertIsNone(active["release_id"])
        self.assertEqual(self.store.release_history("seed-project"), [])
        snapshot = self.store.snapshot(active["snapshot_id"])
        self.assertEqual(snapshot["skills"]["csv"]["project_id"], "seed-project")
        baseline = self.store.get("baselines", active["baseline_ref"])
        self.assertEqual(baseline["kind"], "seed")
        self.assertEqual(self.store.ensure_project("seed-project"), active)
        self.assertEqual(self.store.initialize_project("seed-project", seed=seed, source="constructed CSV fixture"), active)
        self.assert_domain("BASELINE_CONFLICT", self.store.initialize_project, "seed-project")
        other = self.store.initialize_project("other-project", seed=seed, source="constructed CSV fixture")
        self.assertEqual(self.store.get("baselines", other["baseline_ref"])["seed_content_hash"], baseline["seed_content_hash"])

    def test_fact_applicability_is_preserved_and_not_reward_managed(self):
        applicability = {"task_ids": ["csv"], "task_families": ["tabular"], "query_terms": ["identifier"], "global": False}
        original = self.store.remember("project", "Preserve identifiers", "user", project_id="alpha", applicability=applicability)
        self.assertEqual(self.store.facts("alpha")["project"][0]["applicability"], applicability)
        correction = self.store.remember("project", "Preserve all identifiers", "user correction", project_id="alpha", memory_id=original["memory_id"])
        self.assertEqual(correction["applicability"], applicability)
        self.assert_domain("INVALID_ARGUMENT", self.store.remember, "user", "bad", "user", applicability={"global": "yes"})

    def test_unknown_external_parent_is_preserved_like_archived_parent_gap(self):
        from memory_orchestrator.lineage import require_learning_source
        value = episode()
        value['events'][0].update(parent_episode_id='external-unavailable', parent_event_id='earlier-observation')
        self.assertEqual(self.store.add_episode(value), value)
        proof = require_learning_source(self.store, value)
        self.assertEqual(proof['missing_parent_episode_refs'], ['external-unavailable'])
        self.assert_domain('NOT_FOUND', self.store.get, 'episodes', 'external-unavailable')
        self.assertEqual(self.store.get('episodes', value['episode_id']), value)
        bad_local = episode(identifier='bad-local-parent')
        bad_local['events'][0]['parent_event_id'] = 'does-not-exist-in-this-episode'
        self.assert_domain('REFERENCE_MISMATCH', self.store.add_episode, bad_local)

    def test_packaged_contracts_exactly_match_current_source(self):
        raw = BLUEPRINT.read_bytes()
        source = json.loads(raw)
        package = load_contracts()
        self.assertEqual(package["source"]["version"], source["meta"]["version"])
        self.assertEqual(package["source"]["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(package["schemas"], {x["id"]: x["json_schema"] for x in source["schemas"]})
        self.assertEqual(package["prompts"], {x["id"]: x for x in source["prompts"]})
        for fixture in source["examples"]:
            with self.subTest(example=fixture["id"]):
                self.assertEqual(validate(fixture["schema_id"], fixture["value"]), fixture["value"])

    def test_validation_returns_copy_and_all_errors(self):
        original = episode()
        valid = validate("EpisodeRecord", original)
        valid["task"]["description"] = "changed only in copy"
        self.assertNotEqual(original["task"]["description"], valid["task"]["description"])
        original["project_id"] = 123
        original["events"][0]["text"] = 123
        error = self.assert_domain("SCHEMA_INVALID", validate, "EpisodeRecord", original)
        paths = {x["path"] for x in error.details["errors"]}
        self.assertIn("$.project_id", paths)
        self.assertIn("$.events[0].text", paths)
        self.assert_domain("UNKNOWN_SCHEMA", validate, "NotARecord", {})

    def test_episode_roundtrip_unknowns_and_idempotent_import(self):
        value = episode()
        self.assertEqual(self.store.add_episode(value), value)
        before = {p: p.read_bytes() for p in self.root.rglob("*.json")}
        self.assertEqual(self.store.add_episode(value), value)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*.json")})
        self.assertEqual(Store(self.root).get("episodes", value["episode_id"]), value)
        value["task"]["description"] += " changed"
        self.assert_domain("IMMUTABLE_CONFLICT", self.store.add_episode, value)
        self.assertEqual(self.store.get("episodes", "episode-1")["source_snapshot_ref"], None)

    def test_generic_records_are_immutable_and_reads_are_independent(self):
        value = {"usage_id": "usage-1", "project_id": "alpha", "tokens": None}
        self.assertEqual(self.store.put("usage", "usage-1", value), value)
        self.assertEqual(self.store.put("usage", "usage-1", value), value)
        self.assert_domain("IMMUTABLE_CONFLICT", self.store.put, "usage", "usage-1", {**value, "tokens": 42})
        recalled = self.store.get("usage", "usage-1")
        recalled["tokens"] = 123
        self.assertIsNone(self.store.get("usage", "usage-1")["tokens"])

    def test_early_feedback_uses_known_execution_without_requiring_run_or_receipt(self):
        value = episode(identifier="early")
        value["task"].update(task_id="task", revision="v1")
        value["source"] = {"kind": "execution_function", "reference": "run-early"}
        self.store.put("executions", "run-early", {"run_id": "run-early", "project_id": "alpha",
            "request": {"request_id": "run-early", "case_id": "task", "task_revision": "v1"},
            "output": {"artifact": "first-state"}, "error": None})
        self.store.add_episode(value)
        correct = feedback(subject="early")
        correct.update(check_id="early-correct", run_id="run-early", task_revision="v1",
                       evaluated_state_digest=digest("first-state"), binding_status="bound")
        self.assertEqual(self.store.add_feedback(correct), correct)
        self.assertEqual(self.store.list("runs"), [])
        self.assertEqual(self.store.list("group_receipts"), [])
        for field, wrong in (("run_id", "other-run"), ("evaluated_state_digest", digest("other-state")),
                             ("task_revision", "v2")):
            bad = {**correct, "check_id": "wrong-" + field, field: wrong}
            self.assert_domain("REFERENCE_MISMATCH", self.store.add_feedback, bad)
            unbound = {**bad, "check_id": "unbound-" + field, "binding_status": "unbound"}
            self.assertEqual(self.store.add_feedback(unbound), unbound)

    def test_declared_known_run_constrains_feedback_even_for_unknown_import_source(self):
        value = episode()
        self.store.add_episode(value)
        self.store.put('executions', 'known-run', {'run_id': 'known-run', 'project_id': 'alpha',
            'request': {'request_id': 'known-run', 'task_revision': 'v1'},
            'output': {'artifact': 'known-state'}, 'error': None})
        item = feedback()
        item.update(run_id='known-run', evaluated_state_digest=digest('wrong-state'), binding_status='bound')
        self.assert_domain('REFERENCE_MISMATCH', self.store.add_feedback, item)
        item['evaluated_state_digest'] = digest('known-state')
        self.assertEqual(self.store.add_feedback(item), item)

    def test_single_assessment_is_bound_before_bundle_and_preserves_feedback_result(self):
        value = episode()
        value['source'] = {'kind': 'execution_function', 'reference': 'early-run'}
        self.store.put('executions', 'early-run', {'run_id': 'early-run', 'project_id': 'alpha',
            'request': {'request_id': 'early-run', 'task_revision': 'v1'},
            'output': {'artifact': 'state'}, 'error': None})
        self.store.add_episode(value)
        item = feedback()
        item.update(criterion_id='task_outcome', run_id=None, evaluated_state_digest=digest('state'), binding_status='bound')
        self.store.add_feedback(item)
        assessment = {'assessment_id': 'early-assessment', 'project_id': 'alpha', 'run_id': 'early-run',
            'subject_ref': value['episode_id'], 'protocol_id': 'external-explicit-protocol',
            'criterion_feedback_ids': [item['check_id']], 'outcome': item['outcome'], 'score': item['score'],
            'aggregation_rule': 'single_task_outcome', 'unknown_reasons': []}
        self.assertEqual(self.store.put('assessments', assessment['assessment_id'], assessment), assessment)
        self.assertEqual(self.store.list('runs'), [])
        self.assert_domain('REFERENCE_MISMATCH', self.store.put, 'assessments', 'wrong-result',
                           {**assessment, 'assessment_id': 'wrong-result', 'outcome': 'pass', 'score': 1})
        self.assert_domain('REFERENCE_MISMATCH', self.store.put, 'assessments', 'wrong-assessment-run',
                           {**assessment, 'assessment_id': 'wrong-assessment-run', 'run_id': 'other-run'})

    def test_known_execution_project_cannot_be_relabelled_by_episode(self):
        self.store.put("executions", "foreign-run", {"run_id": "foreign-run", "project_id": "beta",
            "request": {"request_id": "foreign-run", "task_revision": "v1"},
            "output": {"artifact": "other project"}, "error": None})
        value = episode()
        value["source"] = {"kind": "execution_function", "reference": "foreign-run"}
        self.assert_domain("PROJECT_MISMATCH", self.store.add_episode, value)

    def test_fact_corrections_keep_history_and_project_scope(self):
        user = self.store.remember("user", "中文回答", "explicit user input")
        first = self.store.remember("project", "SQLite", "project decision", project_id="alpha")
        correction = self.store.remember("project", "PostgreSQL", "explicit correction",
                                         project_id="alpha", memory_id=first["memory_id"])
        self.store.remember("project", "Redis", "other project", project_id="alpha-extra")
        self.assertEqual(correction["revision"], 2)
        self.assertEqual(correction["supersedes"], first["record_id"])
        before = {p: p.read_bytes() for p in self.root.rglob("*.json")}
        recalled = self.store.facts("alpha")
        self.assertEqual(recalled["user"], [user])
        self.assertEqual(recalled["project"], [correction])
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*.json")})
        self.assertEqual(self.store.get("facts", first["record_id"])["content"], "SQLite")
        self.assert_domain("PROJECT_MISMATCH", self.store.remember, "project", "bad", "input",
                           project_id="beta", memory_id=first["memory_id"])
        self.assert_domain("INVALID_ARGUMENT", self.store.remember, "user", "bad", "input", project_id="alpha")
        self.assert_domain("UNKNOWN_KIND", self.store.put, "facts", "model-fact", first)

    def test_legacy_json_frontmatter_claim_exact_scope_read_only(self):
        vault = Path(self.tmp.name) / "legacy"
        (vault / "projects").mkdir(parents=True)
        (vault / "people").mkdir()
        # Derived from scripts/harness.mjs projectItem/personalItem and src/store.ts.
        metadata = {"id": "harness-project-rule", "kind": "project", "scope": "alpha",
                    "status": "verified", "content": "stale metadata", "source": "fixture",
                    "confidence": 0.9, "retrieval_count": 0, "provenance": []}
        def write(name, item, body):
            path = vault / name
            path.write_text("---\n" + json.dumps(item) + "\n---\n\n# Memory\n\n## Claim\n\n"
                            + body + "\n\n## Metadata\n\n- kind: project\n", encoding="utf-8")
        write("projects/a.md", metadata, "Claim body wins")
        write("projects/b.md", {**metadata, "id": "b", "scope": "alpha-extra"}, "must not leak")
        write("projects/c.md", {**metadata, "id": "c", "status": "candidate"}, "not a fact")
        write("people/u.md", {**metadata, "id": "u", "kind": "personal", "scope": "user"}, "用户偏好")
        before = {p: p.read_bytes() for p in vault.rglob("*") if p.is_file()}
        result = self.store.facts("alpha", legacy_root=vault)
        self.assertEqual([x["content"] for x in result["project"]], ["Claim body wins"])
        self.assertEqual([x["content"] for x in result["user"]], ["用户偏好"])
        self.assertEqual(result["errors"], [])
        self.assertEqual(before, {p: p.read_bytes() for p in vault.rglob("*") if p.is_file()})
        (vault / "projects/broken.md").write_text("---\n{broken\n---\n\n", encoding="utf-8")
        errors = self.store.facts("alpha", legacy_root=vault)["errors"]
        self.assertEqual(len(errors), 1)
        self.assertIn("broken.md", errors[0]["path"])

    def test_bootstrap_is_empty_and_candidate_does_not_activate(self):
        active = self.store.ensure_project("alpha")
        self.assertEqual(active["generation"], 0)
        self.assertIsNone(active["release_id"])
        self.assertEqual(self.store.snapshot(active["snapshot_id"])["skills"], {})
        candidate = self.store.save_snapshot("alpha", {"csv": skill("csv")}, {}, parent=active["snapshot_id"])
        self.assertEqual(self.store.active("alpha"), active)
        self.assertEqual(Store(self.root).ensure_project("alpha"), active)
        self.assertNotEqual(candidate["snapshot_id"], active["snapshot_id"])
        self.assertNotEqual(self.store.active("beta")["snapshot_id"], active["snapshot_id"])
        self.assert_domain("UNKNOWN_KIND", self.store.put, "active", "alpha", candidate)
        self.assert_domain("UNKNOWN_KIND", self.store.put, "active_pointer", "alpha", candidate)

    def test_release_cas_orphans_and_stale_generation(self):
        # Mechanical N10 primitive only; policy validation is exercised by its consumer.
        active = self.store.ensure_project("alpha")
        candidate = self.store.save_snapshot("alpha", {"csv": skill("csv")}, {}, parent=active["snapshot_id"])
        release = {"release_id": "release-1", "project_id": "alpha", "kind": "promote",
                   "status": "published", "expected_active_digest": active["snapshot_id"],
                   "expected_generation": 0, "new_digest": candidate["snapshot_id"], "new_generation": 1,
                   "validation_ref": "provided-validation", "selection_ref": "provided-selection",
                   "rollback_target_release_ref": None, "reason": "constructed CAS fixture",
                   "timestamp": "2026-09-18T00:00:00Z"}
        self.store.put("releases", release["release_id"], release)
        self.assertEqual(self.store.active("alpha"), active)
        self.assertEqual(self.store.release_history("alpha"), [])
        write = self.store._atomic_write
        def fail_pointer(path, value):
            if path.name == "active.json":
                raise DomainError("STORAGE_ERROR", "injected pre-commit failure")
            return write(path, value)
        with patch.object(self.store, "_atomic_write", side_effect=fail_pointer):
            self.assert_domain("STORAGE_ERROR", self.store._commit_release, "alpha", active["snapshot_id"], 0, release)
        self.assertEqual(self.store.active("alpha"), active)
        self.assertEqual(self.store.release_history("alpha"), [])
        self.assertEqual(self.store._commit_release("alpha", active["snapshot_id"], 0, release), release)
        self.assertEqual(self.store._commit_release("alpha", active["snapshot_id"], 0, release), release)
        self.assertEqual(self.store.release_history("alpha"), [release])
        self.assert_domain("STALE_BASE", self.store._commit_release, "alpha", active["snapshot_id"], 0,
                           {**release, "release_id": "stale-other"})
        stale_generation = {**release, "release_id": "stale-generation",
                            "expected_active_digest": candidate["snapshot_id"]}
        self.assert_domain("STALE_BASE", self.store._commit_release, "alpha", candidate["snapshot_id"], 0, stale_generation)

    def test_snapshot_hash_covers_multiple_dependencies_and_assets(self):
        owned = "csv/scripts/read.py"
        skills = {"csv": skill("csv", dependencies=["parse", "check"], asset_refs=[owned]),
                  "parse": skill("parse"), "check": skill("check", dependencies=["parse"])}
        snap = self.store.save_snapshot("alpha", skills, {owned: "print('v1')"})
        self.assertEqual(snap["snapshot_id"], digest({k: v for k, v in snap.items() if k != "snapshot_id"}))
        self.assertEqual(self.store.save_snapshot("alpha", skills, {owned: "print('v1')"}), snap)
        changed = self.store.save_snapshot("alpha", skills, {owned: "print('v2')"})
        self.assertNotEqual(changed["snapshot_id"], snap["snapshot_id"])
        self.assertEqual(self.store.snapshot(snap["snapshot_id"])["assets"][owned], "print('v1')")
        invalid = copy.deepcopy(skills)
        invalid["check"]["content"]["depends_on"] = ["csv"]
        self.assert_domain("DEPENDENCY_CYCLE", self.store.save_snapshot, "alpha", invalid, {owned: "x"})
        invalid = copy.deepcopy(skills)
        invalid["check"]["content"]["declared_conflicts"] = ["parse"]
        self.assert_domain("DEPENDENCY_CONFLICT", self.store.save_snapshot, "alpha", invalid, {owned: "x"})
        invalid = copy.deepcopy(skills)
        invalid["parse"]["project_id"] = "beta"
        self.assert_domain("PROJECT_MISMATCH", self.store.save_snapshot, "alpha", invalid, {owned: "x"})
        self.assert_domain("ASSET_MISMATCH", self.store.save_snapshot, "alpha", skills, {})

    def test_wrong_snapshot_parent_and_asset_path_are_rejected(self):
        other = self.store.ensure_project("beta")
        self.assert_domain("PROJECT_MISMATCH", self.store.save_snapshot, "alpha", {}, {}, parent=other["snapshot_id"])
        for path in ["csv/scripts/../../escape", "csv/scripts//bad", "csv/scripts/./bad", "/absolute", "csv/scripts\\bad"]:
            with self.subTest(path=path):
                self.assert_domain("UNSAFE_PATH", self.store.save_snapshot, "alpha", {"csv": skill("csv", asset_refs=[path])}, {path: "x"})

    def test_context_and_snapshot_binding_do_not_allow_cross_project(self):
        a = self.store.ensure_project("alpha")
        b = self.store.ensure_project("beta")
        context = {"manifest_id": "ctx-1", "project_id": "alpha", "task_ref": None,
                   "snapshot_digest": a["snapshot_id"], "selected_skills": []}
        self.store.put("contexts", "ctx-1", context)
        value = episode()
        value["context_ref"] = "ctx-1"
        value["source_snapshot_ref"] = a["snapshot_id"]
        self.store.add_episode(value)
        foreign = episode("beta", "episode-beta")
        foreign["context_ref"] = "ctx-1"
        self.assert_domain("PROJECT_MISMATCH", self.store.add_episode, foreign)
        missing = episode(identifier="missing")
        missing["context_ref"] = "not-found"
        self.assert_domain("NOT_FOUND", self.store.add_episode, missing)
        foreign["context_ref"] = None
        foreign["source_snapshot_ref"] = a["snapshot_id"]
        self.assert_domain("PROJECT_MISMATCH", self.store.add_episode, foreign)
        context["snapshot_digest"] = b["snapshot_id"]
        self.assert_domain("PROJECT_MISMATCH", self.store.put, "contexts", "ctx-bad", {**context, "manifest_id": "ctx-bad"})

    def test_delayed_feedback_is_append_only_and_checks_subject(self):
        value = episode()
        value["task"]["revision"] = "revision-1"
        self.store.add_episode(value)
        original = self.store.get("episodes", value["episode_id"])
        late = feedback()
        self.store.add_feedback(late)
        self.assertEqual(self.store.feedback_for("episode-1"), [late])
        self.assertEqual(self.store.add_feedback(late), late)
        self.assertEqual(self.store.get("episodes", value["episode_id"]), original)
        self.assert_domain("PROJECT_MISMATCH", self.store.add_feedback, {**late, "check_id": "wrong-project", "project_id": "beta"})
        self.assert_domain("NOT_FOUND", self.store.add_feedback, {**late, "check_id": "missing", "subject_ref": "absent"})
        wrong = {**late, "check_id": "wrong-revision", "binding_status": "bound", "task_revision": "revision-2"}
        self.assert_domain("REFERENCE_MISMATCH", self.store.add_feedback, wrong)
        unbound = {**wrong, "check_id": "unbound", "binding_status": "unbound"}
        self.assertEqual(self.store.add_feedback(unbound), unbound)

    def test_context_known_task_and_revision_must_match(self):
        active = self.store.ensure_project("alpha")
        context = {"manifest_id": "ctx-known", "project_id": "alpha", "task_ref": "task-A",
                   "task_revision": "rev-A", "snapshot_digest": active["snapshot_id"]}
        self.store.put("contexts", "ctx-known", context)
        value = episode()
        value["context_ref"] = "ctx-known"
        value["task"].update(task_id="task-A", revision="rev-A")
        self.store.add_episode(value)
        for field, incorrect in [("task_id", "task-B"), ("revision", "rev-B")]:
            with self.subTest(field=field):
                bad = copy.deepcopy(value)
                bad["episode_id"] = "wrong-" + field
                bad["task"][field] = incorrect
                self.assert_domain("REFERENCE_MISMATCH", self.store.add_episode, bad)
        self.assert_domain("INVALID_ARGUMENT", self.store.put, "contexts", "bad-context",
                           {**context, "manifest_id": "bad-context", "task_revision": {"id": "rev-A"}})

    def test_existing_episode_feedback_import_retains_original_references(self):
        value = episode()
        supplied = feedback()
        value["feedback_refs"] = [supplied["check_id"]]
        self.assertEqual(self.store.add_episode(value, feedback_records=[supplied]), value)
        self.assertEqual(self.store.get("episodes", value["episode_id"]), value)
        self.assertEqual(self.store.feedback_for(value["episode_id"]), [supplied])
        self.assertEqual(self.store.add_episode(value, feedback_records=[supplied]), value)
        wrong = {**supplied, "project_id": "beta", "check_id": "bad"}
        fresh = episode(identifier="fresh")
        fresh["feedback_refs"] = ["bad"]
        self.assert_domain("PROJECT_MISMATCH", self.store.add_episode, fresh, feedback_records=[wrong])
        self.assert_domain("NOT_FOUND", self.store.get, "episodes", "fresh")
        wrong_subject = {**wrong, "project_id": "alpha"}
        self.assert_domain("REFERENCE_MISMATCH", self.store.add_episode, fresh, feedback_records=[wrong_subject])
        detached = episode(identifier="detached")
        self.assert_domain("REFERENCE_MISMATCH", self.store.add_episode, detached, feedback_records=[supplied])

    def test_bad_embedded_refs_and_parent_project_are_rejected(self):
        other = episode("beta", "parent")
        self.store.add_episode(other)
        value = episode()
        value["events"][0]["parent_episode_id"] = "parent"
        self.assert_domain("PROJECT_MISMATCH", self.store.add_episode, value)
        value["events"][0].pop("parent_episode_id")
        value["feedback_refs"] = ["absent-check"]
        self.assert_domain("NOT_FOUND", self.store.add_episode, value)
        first = episode()
        self.store.add_episode(first)
        self.assertEqual([x["episode_id"] for x in self.store.list("episodes", "alpha")], ["episode-1"])
        self.store.add_feedback(feedback())
        wrong_feedback = episode(identifier="wrong-feedback-subject")
        wrong_feedback["feedback_refs"] = ["check-late"]
        self.assert_domain("REFERENCE_MISMATCH", self.store.add_episode, wrong_feedback)

    def test_source_snapshot_must_match_known_context(self):
        active = self.store.ensure_project("alpha")
        candidate = self.store.save_snapshot("alpha", {"csv": skill("csv")}, {}, parent=active["snapshot_id"])
        self.store.put("contexts", "context-old", {"manifest_id": "context-old", "project_id": "alpha",
                                                    "snapshot_digest": active["snapshot_id"]})
        value = episode()
        value.update(context_ref="context-old", source_snapshot_ref=candidate["snapshot_id"])
        self.assert_domain("REFERENCE_MISMATCH", self.store.add_episode, value)

    def test_corruption_and_symlinks_are_explicit_errors(self):
        value = episode()
        self.store.add_episode(value)
        path = self.root / "records/episodes" / (digest(value["episode_id"]) + ".json")
        saved = json.loads(path.read_text(encoding="utf-8"))
        saved["record"]["task"]["description"] = "tampered"
        path.write_text(json.dumps(saved), encoding="utf-8")
        self.assert_domain("CORRUPT_RECORD", self.store.get, "episodes", value["episode_id"])
        self.assert_domain("CORRUPT_RECORD", self.store.list, "episodes")
        path.unlink()
        outside = Path(self.tmp.name) / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        path.symlink_to(outside)
        self.assert_domain("UNSAFE_PATH", self.store.get, "episodes", value["episode_id"])
        self.assertEqual(outside.read_text(encoding="utf-8"), "{}")

    def test_snapshot_tamper_and_replaced_root_are_rejected(self):
        snap = self.store.save_snapshot("alpha", {}, {})
        path = self.root / "snapshots" / (snap["snapshot_id"] + ".json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["project_id"] = "beta"
        path.write_text(json.dumps(payload), encoding="utf-8")
        self.assert_domain("CORRUPT_SNAPSHOT", self.store.snapshot, snap["snapshot_id"])
        old_root = self.root.with_name("old-memory")
        self.root.rename(old_root)
        self.root.mkdir()
        self.assert_domain("STALE_ROOT", self.store.list, "episodes")


if __name__ == "__main__":
    unittest.main()
