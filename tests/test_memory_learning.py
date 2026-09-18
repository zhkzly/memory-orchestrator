"""Real local storage plus constructed blueprint/callable evidence, not LLM gains."""
import copy
import json
import tempfile
import unittest

from memory_orchestrator.store import Store
from memory_orchestrator.schemas import DomainError
from memory_orchestrator.model import StructuredModel
from memory_orchestrator.report import report
from memory_orchestrator.learning import find_related, learn
from memory_orchestrator.sampling import sample_tasks
from memory_orchestrator.evidence import build_packet, expand_packet, index_episodes, validate_citations
from test_memory_evidence import EXAMPLES, csv_episodes, limits as packet_limits
from test_memory_model import FakeCall, response, limits as model_limits


def policy(**changes):
    result = {"packet": packet_limits(), "expanded_packet": packet_limits(30000),
              "max_expansions": 2, "max_experiences": 3, "max_read_requests": 4,
              "max_related_experiences": 4, "max_related_episodes": 8, "max_related_chars": 16000,
              "candidate_count": 1, "max_operations": 3, "max_skills": 20,
              "max_asset_bytes": 20000, "evaluation_scope": "local repair, target and regression"}
    result.update(changes)
    return result


def drafts(source):
    packet = build_packet(index_episodes(source), limits=policy()["packet"])
    mapping = {f["event_id"]: f["ref_id"] for f in packet["fragments"]}
    def replace(value):
        if isinstance(value, dict): return {k: replace(v) for k, v in value.items()}
        if isinstance(value, list): return [replace(v) for v in value]
        return mapping.get(value, value) if isinstance(value, str) else value
    extraction = replace(EXAMPLES["extraction"])
    diagnosis = replace(EXAMPLES["diagnosis"]); diagnosis["targets"] = []
    exp = extraction["experiences"][0]
    content = {"title": exp["title"], "scope": exp["scope"], "triggers": ["CSV"],
               "preconditions": [], "steps": exp["guidance"]["steps"], "exceptions": [],
               "checks": exp["guidance"]["checks"], "depends_on": [], "declared_conflicts": [],
               "evidence_refs": exp["supporting_refs"]}
    patch = replace(EXAMPLES["patch"])
    patch["operations"] = [{"op": "ADD", "proposed_slug": "csv-schema", "content": content}]
    return extraction, diagnosis, patch


class LearningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.source = csv_episodes()
        for ep in self.source: self.store.add_episode(ep)
        self.ids = [ep["episode_id"] for ep in self.source]

    def model(self, values):
        call = FakeCall([response(v) if not isinstance(v, Exception) else v for v in values])
        return StructuredModel(call, limits=model_limits(max_calls=12)), call

    def test_generate_candidate_from_empty_library_and_keep_active(self):
        model, call = self.model(drafts(self.source))
        before = self.store.ensure_project("demo-project")
        result = learn(self.store, self.ids, model, policy=policy())
        self.assertEqual(result["status"], "proposed")
        self.assertEqual(len(result["candidate_ids"]), 1)
        self.assertEqual(len(result["experience_ids"]), 1)
        self.assertEqual(self.store.active("demo-project"), before)
        self.assertEqual([c["prompt_id"] for c in call.calls], ["extract_v1", "diagnose_v1", "propose_v1"])
        self.assertEqual(len(result["usage_ids"]), 3)
        self.assertEqual(len(self.store.list("reports", "demo-project")), 3)

    def test_non_skill_diagnosis_keeps_experience_without_proposal_or_fact_edit(self):
        fact = self.store.remember("user", "Chinese replies", "explicit user input")
        extraction, diagnosis, _ = drafts(self.source)
        diagnosis["route"] = "external_issue"
        model, call = self.model([extraction, diagnosis])
        result = learn(self.store, self.ids, model, policy=policy())
        self.assertEqual(result["status"], "noop")
        self.assertEqual(result["candidate_ids"], [])
        self.assertEqual(len(call.calls), 2)
        self.assertEqual(self.store.facts("demo-project")["user"], [fact])

    def test_unprovided_citation_is_rejected_after_raw_and_usage_saved(self):
        extraction, _, _ = drafts(self.source)
        extraction["experiences"][0]["supporting_refs"] = ["invented"]
        call = FakeCall([response(extraction)])
        model = StructuredModel(call, limits=model_limits(max_format_repairs=0))
        result = learn(self.store, self.ids, model, policy=policy())
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["experience_ids"], [])
        self.assertEqual(len(result["usage_ids"]), 1)
        self.assertIn("invented", json.dumps(self.store.list("reports")))
        self.assertEqual(len(call.calls), 1)

    def test_failed_candidate_does_not_hide_cost_or_block_next_same_base(self):
        extraction, diagnosis, patch = drafts(self.source)
        # Application-level duplicate ADD stays a slot failure, outside pure model repair.
        bad = copy.deepcopy(patch); bad["operations"].append(copy.deepcopy(bad["operations"][0]))
        model, call = self.model([extraction, diagnosis, bad, patch])
        result = learn(self.store, self.ids, model, policy=policy(candidate_count=2))
        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["candidate_ids"]), 1)
        self.assertEqual([slot["status"] for slot in result["candidate_slots"]], ["error", "candidate"])
        self.assertEqual(len(result["usage_ids"]), 4)
        inputs = [c["messages"][1]["content"] for c in call.calls if c["prompt_id"] == "propose_v1"]
        self.assertIn(result["base_digest"], inputs[0]); self.assertIn(result["base_digest"], inputs[1])

    def test_repeat_same_source_does_not_multiply_experience_support(self):
        extraction, diagnosis, _ = drafts(self.source); diagnosis["route"] = "external_issue"
        first = learn(self.store, self.ids, self.model([extraction, diagnosis])[0], policy=policy())
        second = learn(self.store, self.ids + self.ids, self.model([extraction, diagnosis])[0], policy=policy())
        self.assertEqual(first["experience_ids"], second["experience_ids"])
        records = self.store.list("experiences", "demo-project")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["source_episode_count"], len(self.ids))
        self.assertEqual(records[0]["known_task_count"], 2)

    def test_transport_failure_preserves_unknown_usage_and_plan(self):
        model, _ = self.model([RuntimeError("failed transport")])
        result = learn(self.store, self.ids, model, policy=policy(candidate_count=2))
        self.assertEqual(result["status"], "error")
        self.assertEqual(len(result["candidate_slots"]), 2)
        usage = self.store.get("usage", result["usage_ids"][0])
        self.assertIsNone(usage["tokens"]["input_tokens"])
        self.assertEqual(len(self.store.list("learning_cycles")), 2)

    def test_missing_policy_or_mixed_project_does_not_start_model(self):
        model, call = self.model([])
        with self.assertRaises(DomainError): learn(self.store, self.ids, model, policy={})
        other = copy.deepcopy(self.source[0]); other.update(episode_id="foreign", project_id="other")
        self.store.add_episode(other)
        with self.assertRaises(DomainError): learn(self.store, [self.ids[0], "foreign"], model, policy=policy())
        self.assertEqual(call.calls, [])

    def test_diagnosis_cannot_target_absent_base_skill(self):
        extraction, diagnosis, _ = drafts(self.source)
        diagnosis["targets"] = [{"skill_id": "absent", "revision": "r1", "rule_id": "R1"}]
        call = FakeCall([response(extraction), response(diagnosis)])
        model = StructuredModel(call, limits=model_limits(max_format_repairs=0))
        result = learn(self.store, self.ids, model, policy=policy())
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["errors"][0]["code"], "invalid_output")
        self.assertEqual(result["errors"][0]["details"]["diagnostics"]["code"], "stale_diagnosis_target")
        self.assertEqual(len(call.calls), 2)

    def test_real_canary_target_error_can_repair_to_add_and_continue(self):
        extraction, corrected, patch = drafts(self.source)
        bad = copy.deepcopy(corrected)
        # Actual target from live-learning-canary-route-v2.json's stored report
        # modelreport_772fefb1f00e4417b7d7f98dd69c8bd0; subsequent replies are synthetic.
        bad["targets"] = [{"skill_id": "csv-typed-transformation", "revision": "new", "rule_id": None}]
        model, call = self.model([extraction, bad, corrected, patch])
        result = learn(self.store, self.ids, model, policy=policy())
        self.assertEqual(result["status"], "proposed")
        self.assertEqual(len(call.calls), 4)
        self.assertEqual(len(result["usage_ids"]), 4)
        diagnosis_report = next(self.store.get("reports", rid) for rid in result["report_ids"]
                                if self.store.get("reports", rid)["prompt_id"] == "diagnose_v1")
        attempts = diagnosis_report["result"]["attempts"]
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0]["diagnostics"]["allowed_targets"], [])
        self.assertIn("targets=[]", attempts[0]["diagnostics"]["correction"])
        self.assertIn("csv-typed-transformation", str(call.calls[2]["messages"][-1]))
        self.assertEqual(self.store.active("demo-project")["generation"], 0)

    def test_semantic_repair_cannot_escape_shared_model_call_cap(self):
        extraction, bad, _ = drafts(self.source)
        bad["targets"] = [{"skill_id": "csv-typed-transformation", "revision": "new", "rule_id": None}]
        call = FakeCall([response(extraction), response(bad)])
        model = StructuredModel(call, limits=model_limits(max_calls=2, max_format_repairs=1))
        result = learn(self.store, self.ids, model, policy=policy())
        self.assertEqual(result["status"], "abstained")
        self.assertEqual(len(call.calls), 2)
        self.assertEqual(len(result["usage_ids"]), 2)
        self.assertEqual(result["candidate_ids"], [])
        self.assertIn("csv-typed-transformation", json.dumps(self.store.list("reports")))

    def test_model_costs_reach_project_report_without_zero_fill(self):
        model, _ = self.model(drafts(self.source))
        result = learn(self.store, self.ids, model, policy=policy())
        output = report(self.store, "demo-project")
        self.assertEqual(output["usage"]["unique_calls"], 3)
        self.assertEqual(output["usage"]["by_stage"], {"extract": 1, "diagnose": 1, "propose": 1})
        self.assertEqual(output["usage"]["missing_cost_calls"], 3)
        self.assertIsNone(output["usage"]["complete_cost_totals"])
        self.assertEqual(output["usage"]["tokens"]["known_subtotals"], {"input_tokens": 33, "output_tokens": 21, "total_tokens": None})
        self.assertEqual(output["usage"]["tokens"]["missing_calls"]["total_tokens"], 3)
        self.assertIsNone(output["usage"]["tokens"]["complete_totals"]["total_tokens"])
        for uid in result["usage_ids"]:
            usage = self.store.get("usage", uid)
            self.assertEqual(usage["tokens"], {"input_tokens": 11, "output_tokens": 7, "total_tokens": None})
            self.assertEqual(usage["purpose"], "learning")
            self.assertEqual(usage["run_or_proposal_id"], result["cycle_id"])
            self.assertEqual(usage["raw"]["input_tokens"], 11)

    def test_experience_revision_appends_and_does_not_inflate_support(self):
        extraction, diagnosis, _ = drafts(self.source); diagnosis["route"] = "external_issue"
        first = learn(self.store, self.ids, self.model([extraction, diagnosis])[0], policy=policy())
        original = self.store.get("experiences", first["experience_ids"][0])
        revised = copy.deepcopy(extraction)
        revised["experiences"][0]["unknowns"].append("Additional untested serialization path remains unknown.")
        second = learn(self.store, self.ids, self.model([revised, diagnosis])[0], policy=policy())
        updated = self.store.get("experiences", second["experience_ids"][0])
        self.assertEqual(updated["supersedes"], original["record_id"])
        self.assertEqual(updated["canonical_key"], original["canonical_key"])
        self.assertEqual(updated["source_episode_count"], original["source_episode_count"])
        self.assertEqual(self.store.get("experiences", original["record_id"]), original)

    def test_real_packet_expansion_is_finite_and_recorded(self):
        ep = copy.deepcopy(self.source[0]); ep["episode_id"] = "long-episode"
        template = ep["events"][-1]
        ep["events"] += [{**template, "event_id": f"extra{i}", "kind": "observation", "text": "ordinary details " * 150} for i in range(16)]
        self.store.add_episode(ep)
        p = policy(packet=packet_limits(6500, 200, 4), expanded_packet=packet_limits(18000, 200, 4), max_expansions=1)
        packet = build_packet(index_episodes([ep], contexts={}), limits=p["packet"])
        request = {"status": "needs_more_evidence", "experiences": [], "read_requests": [
            {"ref_id": packet["omitted_refs"][0], "purpose": "Read omitted original"}], "missing_evidence": ["details"], "reason": "Need source"}
        empty = copy.deepcopy(EXAMPLES["extraction"]); empty["experiences"] = []
        model, call = self.model([request, empty])
        result = learn(self.store, [ep["episode_id"]], model, policy=p)
        self.assertEqual(result["status"], "noop")
        self.assertEqual(len(call.calls), 2)
        packets = self.store.list("evidence_packets", "demo-project")
        self.assertEqual(len(packets), 2)
        self.assertTrue(any(request["read_requests"][0]["ref_id"] in {f["ref_id"] for f in x["fragments"]} for x in packets))

    def test_more_evidence_request_after_limit_abstains(self):
        ep = copy.deepcopy(self.source[0]); ep["episode_id"] = "bounded-reads"
        template = ep["events"][-1]
        ep["events"] += [{**template, "event_id": f"extra{i}", "kind": "observation", "text": "source details " * 200} for i in range(16)]
        self.store.add_episode(ep)
        p = policy(packet=packet_limits(6500, 200, 4), expanded_packet=packet_limits(18000, 200, 4), max_expansions=1)
        index = index_episodes([ep], contexts={})
        packet = build_packet(index, limits=p["packet"])
        def request(ref):
            return {"status": "needs_more_evidence", "experiences": [], "read_requests": [{"ref_id": ref, "purpose": "read"}],
                    "missing_evidence": ["detail"], "reason": "Need another range"}
        first = request(packet["omitted_refs"][0])
        expanded = expand_packet(index, packet, first["read_requests"], limits=p["expanded_packet"])
        second = request(expanded["omitted_refs"][0])
        model, call = self.model([first, second])
        result = learn(self.store, [ep["episode_id"]], model, policy=p)
        self.assertEqual(result["status"], "abstained")
        self.assertEqual(len(call.calls), 2)
        self.assertEqual(result["candidate_ids"], [])

    def test_related_experience_loads_bounded_original_sources(self):
        extraction, diagnosis, _ = drafts(self.source); diagnosis["route"] = "external_issue"
        initial = learn(self.store, self.ids, self.model([extraction, diagnosis])[0], policy=policy())
        new = copy.deepcopy(self.source[0]); new["episode_id"] = "new-csv-task"
        self.store.add_episode(new)
        empty = copy.deepcopy(extraction); empty["experiences"] = []
        result = learn(self.store, [new["episode_id"]], self.model([empty])[0], policy=policy(max_related_episodes=2))
        self.assertEqual(result["status"], "noop")
        self.assertEqual(len(result["source_episode_ids"]), 3)
        self.assertEqual(result["requested_episode_ids"], [new["episode_id"]])
        report_record = self.store.get("reports", result["report_ids"][0])
        self.assertEqual(report_record["inputs"]["related_experiences"][0]["record_id"], initial["experience_ids"][0])
        self.assertTrue(any("Additional related" in gap for gap in report_record["inputs"]["evidence_packet"]["gaps"]))

    def test_frozen_sample_episodes_are_rejected_before_model_or_memory_write(self):
        tasks = [{"project_id": "demo-project", "task_id": "held-out", "revision": "held-out@1", "description": "Frozen evaluation task"}]
        context = {"max_roots": 2, "max_context_chars": 5000, "relation_weight": 0.0}
        for purpose in ("final", "validation", "learning"):
            with self.subTest(purpose=purpose):
                sampled = sample_tasks(self.store, tasks, lambda *args: {"artifact": "FROZEN ANSWER"}, None,
                    policy={"purpose": purpose, "update_mode": "none", "repeat_count": 1, "max_parallel": 1,
                            "protocol_id": "frozen-test", "executor": {"id": "fixture", "config": {}}}, context_policy=context)
                model, call = self.model([EXAMPLES["abstain"]])
                before = self.store.list("experiences", "demo-project")
                with self.assertRaises(DomainError) as caught:
                    learn(self.store, [sampled["episodes"][0]["episode_id"]], model, policy=policy())
                self.assertEqual(caught.exception.code, "learning_not_permitted")
                self.assertEqual(call.calls, [])
                self.assertEqual(self.store.list("experiences", "demo-project"), before)

    def test_large_feedback_uses_only_packet_fragments_and_binding_metadata(self):
        fb = copy.deepcopy(EXAMPLES["criterion-feedback"])
        fb["subject_ref"] = self.ids[0]
        fb["reason"] = "Detailed verifier log: " + "X" * 180000
        self.store.add_feedback(fb)
        empty = copy.deepcopy(EXAMPLES["extraction"]); empty["experiences"] = []
        call = FakeCall([response(empty)])
        model = StructuredModel(call, limits=model_limits(max_input_chars=20000))
        result = learn(self.store, [self.ids[0]], model,
                       policy=policy(packet=packet_limits(6000, 350, 3)))
        self.assertEqual(result["status"], "noop")
        self.assertEqual(len(call.calls), 1)
        self.assertLessEqual(len(json.dumps(call.calls[0]["messages"], ensure_ascii=False, separators=(",", ":"))), 20000)
        record = self.store.get("reports", result["report_ids"][0])
        visible = record["inputs"]["available_feedback"][0]
        for key in ("subject_ref", "task_revision", "evaluated_state_digest", "binding_status", "source", "visibility"):
            self.assertEqual(visible[key], fb[key])
        self.assertNotIn("reason", visible)
        self.assertTrue(visible["provided_refs"])

    def test_new_canonical_revision_preserves_prior_boundaries_with_origin(self):
        extraction, diagnosis, _ = drafts(self.source); diagnosis["route"] = "external_issue"
        extraction["experiences"][0]["counterevidence_refs"] = [extraction["experiences"][0]["observed_facts"][1]["evidence_refs"][0]]
        first = learn(self.store, self.ids, self.model([extraction, diagnosis])[0], policy=policy())
        original = self.store.get("experiences", first["experience_ids"][0])
        revised = copy.deepcopy(extraction)
        revised["experiences"][0]["boundary_refs"] = []
        revised["experiences"][0]["counterevidence_refs"] = []
        second = learn(self.store, self.ids, self.model([revised, diagnosis])[0], policy=policy())
        latest = self.store.get("experiences", second["experience_ids"][0])
        retained = latest["retained_evidence"]
        for role in ("boundary_refs", "counterevidence_refs"):
            item = next(x for x in retained if x["role"] == role)
            self.assertEqual(item["packet_id"], original["packet_id"])
            self.assertEqual(item["record_id"], original["record_id"])
            self.assertEqual(item["ref_id"], original["draft"][role][0])
        related = find_related(self.store.list("experiences"), "CSV schema", "demo-project", limit=1, max_chars=16000)
        self.assertEqual(related[0]["record_id"], latest["record_id"])
        self.assertEqual(related[0]["retained_evidence"], retained)
        empty = copy.deepcopy(extraction); empty["experiences"] = []
        third = learn(self.store, [self.ids[0]], self.model([empty])[0], policy=policy(max_related_episodes=0))
        call_input = self.store.get("reports", third["report_ids"][0])["inputs"]
        boundary = next(x for x in call_input["related_experiences"][0]["retained_evidence"] if x["role"] == "boundary_refs")
        self.assertFalse(boundary["body_provided_in_current_packet"])
        with self.assertRaises(DomainError):
            validate_citations({"boundary_refs": [boundary["ref_id"]]}, call_input["evidence_packet"])

    def test_frozen_parent_and_polluted_related_memory_cannot_bypass_source_gate(self):
        sampled = sample_tasks(self.store,
            [{"project_id": "demo-project", "task_id": "frozen", "revision": "frozen@1", "description": "CSV frozen example"}],
            lambda *args: {"artifact": "FROZEN SECRET"}, None,
            policy={"purpose": "final", "update_mode": "none", "repeat_count": 1, "max_parallel": 1,
                    "protocol_id": "frozen-test", "executor": {"id": "fixture", "config": {}}},
            context_policy={"max_roots": 1, "max_context_chars": 5000, "relation_weight": 0.0})
        frozen = sampled["episodes"][0]
        child = copy.deepcopy(self.source[0]); child["episode_id"] = "child-of-frozen"
        child["events"][0].update(parent_episode_id=frozen["episode_id"], parent_event_id="instruction")
        self.store.add_episode(child)
        model, call = self.model([])
        with self.assertRaises(DomainError): learn(self.store, [child["episode_id"]], model, policy=policy())
        self.assertEqual(call.calls, [])
        # Simulate an already-stored record produced by the pre-fix bug; it stays
        # auditable but its frozen source must not enter a later learning prompt.
        draft = copy.deepcopy(EXAMPLES["experience"]); draft["title"] = "CSV FROZEN SECRET"
        self.store.put("experiences", "polluted", {"record_id": "polluted", "project_id": "demo-project",
            "canonical_key": "polluted", "draft": draft, "packet_id": "old-packet",
            "source_episode_ids": [frozen["episode_id"]], "created_at": "2026-09-18T00:00:00Z"})
        empty = copy.deepcopy(EXAMPLES["extraction"]); empty["experiences"] = []
        model, call = self.model([empty])
        result = learn(self.store, self.ids, model, policy=policy())
        self.assertEqual(result["status"], "noop")
        self.assertNotIn("FROZEN SECRET", str(call.calls))

    def test_enabled_learning_samples_and_unknown_import_sources_still_work(self):
        sampled = sample_tasks(self.store,
            [{"project_id": "demo-project", "task_id": "train", "revision": "train@1", "description": "Training task"}],
            lambda *args: {"artifact": "visible learning result"}, None,
            policy={"purpose": "learning", "update_mode": "task_barrier", "repeat_count": 1, "max_parallel": 1,
                    "protocol_id": "train-test", "executor": {"id": "fixture", "config": {}}},
            context_policy={"max_roots": 1, "max_context_chars": 5000, "relation_weight": 0.0})
        model, call = self.model([EXAMPLES["abstain"]])
        result = learn(self.store, [sampled["episodes"][0]["episode_id"]], model, policy=policy())
        self.assertEqual(result["status"], "abstained")
        self.assertEqual(len(call.calls), 1)
        imported = copy.deepcopy(self.source[0]); imported["episode_id"] = "external-untracked"
        imported["source"] = {"kind": "execution_function", "reference": "external:untracked"}
        self.store.add_episode(imported)
        result = learn(self.store, [imported["episode_id"]], self.model([EXAMPLES["abstain"]])[0], policy=policy())
        self.assertEqual(result["status"], "abstained")

    def test_fractional_model_usage_is_missing_without_breaking_project_report(self):
        empty = copy.deepcopy(EXAMPLES["extraction"]); empty["experiences"] = []
        invalid = response(empty); invalid["usage"] = {"input_tokens": 1.5, "output_tokens": 7, "total_tokens": True}
        call = FakeCall([invalid])
        result = learn(self.store, self.ids, StructuredModel(call, limits=model_limits()), policy=policy())
        self.assertEqual(result["status"], "noop")
        usage = self.store.get("usage", result["usage_ids"][0])
        self.assertIsNone(usage["tokens"]["input_tokens"])
        self.assertIsNone(usage["tokens"]["total_tokens"])
        self.assertTrue(usage["raw"]["usage_diagnostics"])
        aggregate = report(self.store, "demo-project")["usage"]["tokens"]
        self.assertEqual(aggregate["missing_calls"]["input_tokens"], 1)
        self.assertEqual(aggregate["known_subtotals"]["output_tokens"], 7)


if __name__ == "__main__": unittest.main()
