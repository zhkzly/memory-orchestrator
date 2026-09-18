"""Semantic-maintenance host actions using actual saved experience records."""
import copy
import tempfile
import unittest

from memory_orchestrator.maintenance import (
    failure_signature, maintenance_inputs, check_maintenance, apply_maintenance,
    active_memory_relations, fold_related,
    maintenance_summary,
)
from memory_orchestrator.evidence import index_episodes
from memory_orchestrator.schemas import DomainError
from memory_orchestrator.store import Store
from test_memory_evidence import episode, EXAMPLES


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.ep = episode(); self.store.add_episode(self.ep)
        self.project = self.ep["project_id"]
        self.records = []
        for identifier in ("left", "right"):
            draft = copy.deepcopy(EXAMPLES["experience"])
            draft["title"] = "CSV guidance " + identifier
            rec = {"record_id": identifier, "project_id": self.project, "canonical_key": identifier,
                   "draft": draft, "source_episode_ids": [self.ep["episode_id"]], "packet_id": "original-packet",
                   "retained_evidence": [{"role": "boundary_refs", "ref_id": identifier + ":boundary",
                      "packet_id": "original-packet", "record_id": identifier, "status": "historical_reference_not_retracted"}],
                   "created_at": "2026-09-18T00:00:00Z"}
            self.store.put("experiences", identifier, rec); self.records.append(rec)

    def test_duplicate_links_have_a_real_retrieval_consumer_and_keep_boundaries(self):
        inputs = maintenance_inputs(self.records, (), max_chars=10000, max_pairs=2)
        draft = {"actions": [{"op": "LINK_DUPLICATE", "record_ids": ["left", "right"],
                              "preferred_record_id": "left", "reason": "same scoped procedure",
                              "evidence_refs": inputs["comparison_refs"]}], "unknowns": []}
        check_maintenance(draft, inputs, max_actions=2)
        review = apply_maintenance(self.store, self.project, draft, inputs, cycle_id="cycle", model_report_ref="model-1")
        self.assertEqual(review["status"], "applied")
        selected = fold_related(self.records, active_memory_relations(self.store, self.project))
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["record_id"], "left")
        self.assertEqual(set(selected[0]["maintenance_member_ids"]), {"left", "right"})
        self.assertEqual({x["ref_id"] for x in selected[0]["retained_evidence"]}, {"left:boundary", "right:boundary"})
        self.assertEqual(self.store.get("experiences", "right"), self.records[1])

    def test_conflicts_are_exposed_together_and_can_be_revoked_without_erasure(self):
        inputs = maintenance_inputs(self.records, (), max_chars=10000, max_pairs=2)
        draft = {"actions": [{"op": "MARK_CONFLICT", "record_ids": ["left", "right"],
                              "scope": "same CSV fields", "reason": "incompatible procedures",
                              "evidence_refs": inputs["comparison_refs"]}], "unknowns": []}
        review = apply_maintenance(self.store, self.project, draft, inputs, cycle_id="cycle", model_report_ref="model-1")
        relations = active_memory_relations(self.store, self.project)
        grouped = fold_related(self.records, relations)
        self.assertEqual(len(grouped), 2)
        self.assertTrue(all(set(x["conflict_record_ids"]) == {"left", "right"} for x in grouped))
        updated = maintenance_inputs(self.records, relations, max_chars=10000, max_pairs=2)
        revoke = {"actions": [{"op": "REVOKE", "relation_id": review["relation_ids"][0],
                               "reason": "new scope evidence distinguishes the cases", "evidence_refs": updated["comparison_refs"]}], "unknowns": []}
        apply_maintenance(self.store, self.project, revoke, updated, cycle_id="later", model_report_ref="model-2")
        self.assertEqual(active_memory_relations(self.store, self.project), [])
        self.assertEqual(len(self.store.list("memory_relations", self.project)), 2)
        summary = maintenance_summary(self.store, self.project)
        self.assertEqual(summary["applied_revocations"], 1)
        self.assertEqual(summary["unresolved_conflict_groups"], [])

    def test_unknown_reference_or_foreign_project_cannot_partially_apply(self):
        inputs = maintenance_inputs(self.records, (), max_chars=10000, max_pairs=2)
        draft = {"actions": [{"op": "LINK_DUPLICATE", "record_ids": ["left", "foreign"],
                              "preferred_record_id": "left", "reason": "unsupported", "evidence_refs": ["not-provided"]}], "unknowns": []}
        with self.assertRaises(DomainError):
            apply_maintenance(self.store, self.project, draft, inputs, cycle_id="cycle", model_report_ref="model")
        self.assertEqual(self.store.list("memory_relations", self.project), [])

    def test_uncommitted_relation_has_no_retrieval_effect(self):
        self.store.put("memory_relations", "orphan", {"relation_id": "orphan", "project_id": self.project,
            "review_ref": "not-committed", "cycle_id": "interrupted", "origin": "model_proxy",
            "op": "LINK_DUPLICATE", "record_ids": ["left", "right"], "preferred_record_id": "left",
            "reason": "write occurred before receipt", "evidence_refs": ["experience:left", "experience:right"]})
        self.assertEqual(active_memory_relations(self.store, self.project), [])
        self.assertEqual(len(fold_related(self.records, active_memory_relations(self.store, self.project))), 2)

    def test_failure_signature_preserves_explicit_failed_criteria_as_a_query_feature(self):
        fb = copy.deepcopy(EXAMPLES["criterion-feedback"])
        fb.update(subject_ref=self.ep["episode_id"], project_id=self.project,
                  criterion_id="identifier-preservation", outcome="fail", score=0.0)
        signature = failure_signature(index_episodes([self.ep], feedback=[fb]))
        self.assertEqual(signature["criterion_ids"], ["identifier-preservation"])
        self.assertTrue(signature["evidence_refs"])
        self.assertEqual(signature["origin"], "observed_fields")

    def test_transitive_duplicates_cannot_hide_an_unresolved_contradiction(self):
        third = copy.deepcopy(self.records[0]); third.update(record_id="third", canonical_key="third")
        records = [*self.records, third]
        relations = [
            {"op": "LINK_DUPLICATE", "record_ids": ["left", "third"], "preferred_record_id": "left"},
            {"op": "LINK_DUPLICATE", "record_ids": ["third", "right"], "preferred_record_id": "right"},
            {"op": "MARK_CONFLICT", "record_ids": ["left", "right"]},
        ]
        view = fold_related(records, relations)
        self.assertEqual(len(view), 2)
        self.assertTrue(all(set(row["conflict_record_ids"]) == {"left", "right"} for row in view))
        from memory_orchestrator.learning import find_related
        self.assertEqual(find_related(records, "CSV", self.project, limit=1, max_chars=20000, relations=relations), [])
        self.assertEqual(len(find_related(records, "CSV", self.project, limit=2, max_chars=20000, relations=relations)), 2)

    def test_failure_features_are_bounded_and_pattern_origin_is_not_verifier_truth(self):
        from test_memory_evidence import event
        ep = copy.deepcopy(self.ep)
        ep["events"] = [event("failure", " ".join("Failure" + str(i) + "Error" for i in range(500)))]
        # Explicit index terms model the trace indexer's bounded per-event metadata.
        index = index_episodes([ep])
        for row in index["records"].values():
            if row["source_event"]: row["failure_terms"] = ["Failure" + str(i) + "Error" for i in range(500)]
        signature = failure_signature(index, max_chars=700)
        self.assertFalse(signature["coverage"]["complete"])
        self.assertGreater(signature["coverage"]["omitted_feature_occurrences"], 0)
        self.assertEqual(signature["origin"], "text_pattern")
        import json
        self.assertLessEqual(len(json.dumps(signature, ensure_ascii=False, separators=(",", ":"))), 700)


if __name__ == "__main__": unittest.main()
