"""Real local storage plus constructed blueprint/callable evidence, not LLM gains."""
import copy
import json
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from memory_orchestrator.store import Store
from memory_orchestrator.schemas import DomainError
from memory_orchestrator.model import StructuredModel
from memory_orchestrator.report import report
from memory_orchestrator.learning import find_related, learn
from memory_orchestrator.sampling import sample_tasks
from memory_orchestrator.evidence import build_packet, index_episodes, validate_citations
from test_memory_evidence import EXAMPLES, csv_episodes, episode, event, limits as packet_limits
from test_memory_model import FakeCall, response, limits as model_limits


def policy(**changes):
    result = {"packet": packet_limits(), "expanded_packet": packet_limits(30000),
              "max_expansions": 2, "max_experiences": 3, "max_read_requests": 4,
              "max_related_experiences": 4, "max_related_episodes": 8, "max_related_chars": 16000,
              "candidate_count": 1, "max_operations": 3, "max_skills": 20,
              "max_asset_bytes": 20000, "evaluation_scope": "local repair, target and regression"}
    result.update(necessity={"max_compared_skills": 20},
                  maintenance={"max_chars": 20000, "max_pairs": 6, "max_actions": 3},
                  goal_binding={"max_events": 4, "max_bindings": 4, "max_read_requests": 2,
                                "max_expansions": 1, "max_catalog_goals": 12, "packet": packet_limits()})
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
    diagnosis["necessity"] = {"verdict": "proceed", "repeatable": True, "compared_skill_refs": [],
        "capability_gap": "No CSV schema-preserving procedure in the empty library",
        "behavior_delta": "Preserve explicit string identifiers before CSV conversion", "allow_add": True,
        "evidence_refs": extraction["experiences"][0]["supporting_refs"], "unknowns": ["Reuse remains unverified"]}
    exp = extraction["experiences"][0]
    content = {"title": exp["title"], "scope": exp["scope"], "triggers": ["CSV"],
               "preconditions": [], "steps": exp["guidance"]["steps"], "exceptions": [],
               "checks": exp["guidance"]["checks"], "depends_on": [], "declared_conflicts": [],
               "evidence_refs": exp["supporting_refs"]}
    patch = replace(EXAMPLES["patch"])
    patch["operations"] = [{"op": "ADD", "proposed_slug": "csv-schema", "content": content}]
    for draft in (diagnosis, patch):
        for check in draft["check_plan"]: check["check_ref"] = None
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

    def visible_packet(self, ep):
        """Decode the actual StructuredModel transport message, not the index."""
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            store.add_episode(ep)
            model, call = self.model([EXAMPLES["abstain"]])
            result = learn(store, [ep["episode_id"]], model, policy=policy())
            self.assertEqual(result["status"], "abstained")
            self.assertEqual(len(call.calls), 1)
            body = call.calls[0]["messages"][1]["content"]
            value, _ = json.JSONDecoder().raw_decode(body.split("证据包及缺口：", 1)[1].lstrip())
            value.pop("packet_id")
            return value

    def test_same_text_different_call_identity_changes_actual_model_input(self):
        # Directly derived from audit F03 call_metadata_loss, with identical text/IDs.
        first = episode()
        first["events"] = [
            {**event("a1", "launch process", "action"), "call_id": "c1"},
            {**event("a2", "launch process", "action"), "call_id": "c2"},
            {**event("r1", "result success", "result"), "call_id": "c1"},
            {**event("r2", "result failure", "result"), "call_id": "c2"},
        ]
        second = copy.deepcopy(first)
        second["events"][2]["call_id"], second["events"][3]["call_id"] = "c2", "c1"
        a, b = self.visible_packet(first), self.visible_packet(second)
        self.assertEqual([x["text"] for x in a["fragments"]], [x["text"] for x in b["fragments"]])
        self.assertNotEqual(a, b)
        self.assertNotEqual(a["relations"]["calls"], b["relations"]["calls"])

    def test_same_text_different_goal_identity_changes_actual_model_input(self):
        # Directly derived from audit F03 goal_metadata_loss.
        first = episode()
        first["events"] = [
            {**event("u1", "Continue task", "instruction", source_role="user", goal_id="A"), "task_revision": "r1"},
            {**event("u2", "Continue task", "instruction", source_role="user", goal_id="B"), "task_revision": "r1"},
        ]
        second = copy.deepcopy(first)
        second["events"][1]["goal_id"] = "A"
        a, b = self.visible_packet(first), self.visible_packet(second)
        self.assertEqual([x["text"] for x in a["fragments"]], [x["text"] for x in b["fragments"]])
        self.assertNotEqual(a, b)
        self.assertEqual([x["relation"] for x in a["relations"]["goals"]], ["continues", "switches"])
        self.assertEqual([x["relation"] for x in b["relations"]["goals"]], ["continues", "continues"])

    def test_open_local_group_cannot_call_model_or_write_learning_records(self):
        # Real callback scheduling from F04, with a bounded second-slot barrier.
        started, release = threading.Event(), threading.Event()
        def execute(request, *_):
            if request["repeat_index"] == 1:
                started.set()
                if not release.wait(timeout=5):
                    raise TimeoutError("test second-slot barrier")
            return {"artifact": "partial group material"}
        tasks = [{"project_id": "demo-project", "task_id": "barrier", "revision": "barrier@1", "description": "CSV local group"}]
        sampling = {"purpose": "learning", "update_mode": "frozen_microbatch", "repeat_count": 2,
                    "max_parallel": 2, "protocol_id": "barrier-test", "executor": {"id": "fixture", "config": {}}}
        context = {"max_roots": 1, "max_context_chars": 5000, "relation_weight": 0.0}
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(sample_tasks, self.store, tasks, execute, None,
                                 policy=sampling, context_policy=context)
            try:
                self.assertTrue(started.wait(timeout=2))
                deadline = time.monotonic() + 2
                sampled = []
                while time.monotonic() < deadline:
                    sampled = [x for x in self.store.list("episodes", "demo-project") if x["source"]["kind"] == "execution_function"]
                    if self.store.list("runs", "demo-project") and sampled:
                        break
                    time.sleep(0.01)
                self.assertTrue(sampled)
                self.assertFalse(future.done())
                self.assertEqual(self.store.list("group_receipts", "demo-project"), [])
                before = {path: path.read_bytes() for path in self.store.root.rglob("*.json")}
                model, call = self.model([EXAMPLES["abstain"]])
                with self.assertRaises(DomainError) as caught:
                    learn(self.store, [sampled[0]["episode_id"]], model, policy=policy())
                self.assertEqual(caught.exception.code, "learning_not_permitted")
                self.assertEqual(call.calls, [])
                self.assertEqual(before, {path: path.read_bytes() for path in self.store.root.rglob("*.json")})
            finally:
                release.set()
                result = future.result(timeout=5)
        model, call = self.model([EXAMPLES["abstain"]])
        after = learn(self.store, [result["episodes"][0]["episode_id"]], model, policy=policy())
        self.assertEqual(after["status"], "abstained")
        self.assertEqual(len(call.calls), 1)

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

    def test_necessity_noop_stops_proposal_and_persists_decision(self):
        extraction, diagnosis, patch = drafts(self.source)
        diagnosis["necessity"].update(verdict="noop", allow_add=False, behavior_delta="")
        model, call = self.model([extraction, diagnosis, patch])
        result = learn(self.store, self.ids, model, policy=policy())
        self.assertEqual(result["status"], "noop")
        self.assertEqual([c["prompt_id"] for c in call.calls], ["extract_v1", "diagnose_v1"])
        self.assertEqual(self.store.get("diagnoses", result["diagnosis_id"])["draft"]["necessity"]["verdict"], "noop")

    def test_add_denied_by_necessity_is_repaired_before_candidate_application(self):
        extraction, diagnosis, patch = drafts(self.source)
        diagnosis["necessity"]["allow_add"] = False
        noop = copy.deepcopy(patch); noop["operations"] = [{"op": "NOOP", "reason": "No permitted behavior change"}]
        model, call = self.model([extraction, diagnosis, patch, noop])
        result = learn(self.store, self.ids, model, policy=policy())
        self.assertEqual(result["status"], "noop")
        self.assertEqual(result["candidate_ids"], [])
        self.assertEqual(len(call.calls), 4)
        self.assertIn("allow_add", str(call.calls[-1]["messages"]))

    def test_invented_check_reference_is_repaired_at_diagnosis_before_proposal(self):
        extraction, diagnosis, patch = drafts(self.source)
        bad = copy.deepcopy(diagnosis); bad["check_plan"][0]["check_ref"] = "invented-check"
        model, call = self.model([extraction, bad, diagnosis, patch])
        result = learn(self.store, self.ids, model, policy=policy(), verification_catalog=[])
        self.assertEqual(result["status"], "proposed")
        self.assertEqual([c["prompt_id"] for c in call.calls], ["extract_v1", "diagnose_v1", "diagnose_v1", "propose_v1"])
        saved = self.store.get("diagnoses", result["diagnosis_id"])
        self.assertIsNone(saved["draft"]["check_plan"][0]["check_ref"])

    def test_missing_goals_reach_real_extraction_as_sidecar_not_observed_identity(self):
        ep = episode(); ep["events"] = [event("request", "Review CSV identifier handling", "instruction", source_role="user")]
        ep["episode_id"] = "missing-goal"
        self.store.add_episode(ep)
        packet = build_packet(index_episodes([ep]), limits=policy()["packet"])
        ref = next(f["ref_id"] for f in packet["fragments"] if f["event_id"] == "request")
        binding = {"status": "completed", "bindings": [{"event_refs": [ref], "goal_id": "new:csv",
            "revision": "new:initial", "relation": "continues", "anchor_user_ref": ref,
            "evidence_refs": [ref], "reason": "Explicit user CSV review request"}],
            "read_requests": [], "reason": "Anchored request", "unknowns": []}
        model, call = self.model([binding, EXAMPLES["abstain"]])
        result = learn(self.store, [ep["episode_id"]], model, policy=policy())
        self.assertEqual(result["status"], "abstained")
        self.assertEqual([c["prompt_id"] for c in call.calls], ["goal_binding_v1", "extract_v1"])
        body = call.calls[-1]["messages"][1]["content"]
        observed, _ = json.JSONDecoder().raw_decode(body.split("证据包及缺口：", 1)[1].lstrip())
        self.assertEqual(observed["goal_annotations"][0]["origin"], "model_proxy")
        self.assertTrue(observed["goal_annotations"][0]["goal_id"].startswith("derived-goal:"))
        self.assertIsNone(next(f for f in observed["fragments"] if f["event_id"] == "request")["structure"]["goal_id"])
        self.assertEqual(self.store.get("episodes", ep["episode_id"]), ep)

    def test_semantic_maintenance_runs_in_learn_and_next_retrieval_folds_real_records(self):
        extraction, diagnosis, _ = drafts(self.source)
        old_draft = copy.deepcopy(extraction["experiences"][0]); old_draft["title"] = "Older equivalent CSV procedure"
        old_draft["guidance"]["steps"].append("Retain identifiers as strings")
        old = {"record_id": "prior-equivalent", "project_id": "demo-project", "canonical_key": "separate-wording",
            "draft": old_draft, "packet_id": "prior-packet", "source_episode_ids": self.ids,
            "created_at": "2026-09-18T00:00:00Z"}
        self.store.put("experiences", old["record_id"], old)
        calls = []
        def teacher(request):
            calls.append(copy.deepcopy(request))
            if request["prompt_id"] == "extract_v1": return response(extraction)
            if request["prompt_id"] == "maintain_experience_v1":
                text = request["messages"][1]["content"]
                fresh, _ = json.JSONDecoder().raw_decode(text.split("新经验：", 1)[1])
                ids = [fresh[0]["record_id"], old["record_id"]]
                return response({"actions": [{"op": "LINK_DUPLICATE", "record_ids": ids,
                    "preferred_record_id": ids[0], "reason": "same scoped CSV method in different wording",
                    "evidence_refs": ["experience:" + ref for ref in ids]}], "unknowns": []})
            value = copy.deepcopy(diagnosis); value["necessity"].update(verdict="noop", allow_add=False)
            return response(value)
        result = learn(self.store, self.ids, StructuredModel(teacher, limits=model_limits(max_calls=6)), policy=policy())
        self.assertEqual(result["status"], "noop")
        self.assertEqual([c["prompt_id"] for c in calls], ["extract_v1", "maintain_experience_v1", "diagnose_v1"])
        self.assertIn("LINK_DUPLICATE", str(calls[-1]["messages"]))
        self.assertEqual(len(result["maintenance_review_ids"]), 1)
        from memory_orchestrator.maintenance import active_memory_relations
        selected = find_related(self.store.list("experiences"), "CSV", "demo-project", limit=4, max_chars=16000,
                                relations=active_memory_relations(self.store, "demo-project"))
        self.assertEqual(len(selected), 1)
        self.assertEqual(set(selected[0]["maintenance_member_ids"]), {old["record_id"], result["experience_ids"][0]})
        self.assertEqual(self.store.get("experiences", old["record_id"]), old)
        self.assertEqual(len(result["usage_ids"]), 3)

    def test_failure_signature_beats_unrelated_lexical_match(self):
        extraction, _, _ = drafts(self.source)
        records = []
        for identifier, title, signature in [("failure-match", "Preserve identifiers", {"criterion_ids": ["identifier-preservation"]}),
                                               ("a-lexical", "CSV transform parse export", {})]:
            draft = copy.deepcopy(extraction["experiences"][0]); draft["title"] = title
            records.append({"record_id": identifier, "project_id": "demo-project", "canonical_key": identifier,
                "draft": draft, "packet_id": "p", "created_at": "2026-09-18", "failure_signature": signature})
        result = find_related(records, "CSV", "demo-project", limit=1, max_chars=16000,
                              failure_signature={"criterion_ids": ["identifier-preservation"]})
        self.assertEqual(result[0]["record_id"], "failure-match")
        self.assertGreater(result[0]["retrieval_score"]["failure_signature"], 0)

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

    def test_disabling_related_lookup_does_not_disable_current_source_learning(self):
        model, call = self.model([EXAMPLES["abstain"]])
        result = learn(self.store, self.ids, model, policy=policy(max_related_chars=0, max_related_experiences=0))
        self.assertEqual(result["status"], "abstained")
        self.assertEqual(len(call.calls), 1)

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

    def _runtime_expansion_case(self, *, request_after_limit):
        """Request only locators actually delivered by the unified input pipeline."""
        from memory_orchestrator.schemas import load_contracts
        from memory_orchestrator.evidence import _resolve
        ep = copy.deepcopy(self.source[0]); ep["episode_id"] = "bounded-reads" if request_after_limit else "long-episode"
        template = ep["events"][-1]
        ep["events"] += [{**template, "event_id": f"extra{i}", "kind": "observation", "text": "ordinary details " * 150} for i in range(16)]
        self.store.add_episode(ep)
        processing = {"direct_max_input_tokens": 0,
            "plan": {"max_scan_events": 128, "max_segments": 2, "max_groups_per_segment": 4,
                "packet": packet_limits(15000, 400, 8),
                "role_max_chars": {"user": 400, "action": 400, "note": 200,
                                   "result": 300, "feedback": 400, "unknown": 200}},
            "summary_limits": {"max_observations": 3, "max_quote_chars": 120}}
        p = policy(packet=packet_limits(20000, 400, 8), expanded_packet=packet_limits(40000, 400, 8),
                   max_expansions=1, trajectory_processing=processing)
        calls, extracts, requested = [], [], []
        def visible_value(request, field):
            template = load_contracts()["prompts"][request["prompt_id"]]["user_template"]
            marker = template.split("{{" + field + "}}")[0].rsplit("\n", 1)[-1]
            return json.JSONDecoder().raw_decode(request["messages"][1]["content"].split(marker, 1)[1].lstrip())[0]
        def transport(request):
            calls.append(copy.deepcopy(request))
            packet = visible_value(request, "evidence_packet")
            if request["prompt_id"] == "summarize_trace_v1":
                source = packet["fragments"][0]
                return response({"status": "completed", "observations": [{"kind": "observation",
                    "text": "A quoted part of the supplied source; not a claim of task success.",
                    "excerpts": [{"ref_id": source["ref_id"], "quote": source["text"][:80]}]}],
                    "unknowns": ["Other original ranges remain unread."], "reason": "Local source only."})
            self.assertEqual(request["prompt_id"], "extract_v1")
            extracts.append(packet)
            if len(extracts) == 2:
                self.assertEqual(visible_value(request, "extraction_limits")["remaining_evidence_expansions"], 0)
            if len(extracts) == 1 or request_after_limit:
                provided = {f["ref_id"] for f in packet["fragments"]}
                unseen = [c for c in packet["readable_ref_catalog"] if c["available"] and c["ref_id"] not in provided]
                self.assertTrue(unseen, "The actual extraction request must offer an unread original range")
                requested.append(unseen[0]["ref_id"])
                return response({"status": "needs_more_evidence", "experiences": [],
                    "read_requests": [{"ref_id": requested[-1], "purpose": "Read the actual delivered original locator"}],
                    "missing_evidence": ["Unprovided original body"], "reason": "Need source before forming experience."})
            empty = copy.deepcopy(EXAMPLES["extraction"]); empty["experiences"] = []
            return response(empty)
        budget = {"max_input_tokens": 100000, "max_total_input_tokens": 500000, "max_total_output_tokens": 30000,
            "stages": {name: {"max_calls": 8, "max_input_tokens": 100000, "max_output_tokens": 3000,
                "max_total_input_tokens": 500000, "max_total_output_tokens": 30000} for name in load_contracts()["prompts"]}}
        model = StructuredModel(transport, limits=model_limits(max_calls=8, max_input_chars=200000,
            max_total_input_chars=1000000, max_format_repairs=0, token_budget=budget))
        result = learn(self.store, [ep["episode_id"]], model, policy=p)
        self.assertEqual(result["trajectory_processing"]["mode"], "partial")
        self.assertIn("segment_budget", result["trajectory_processing"]["planned_coverage"]["stop_reasons"])
        self.assertEqual(len(extracts), 2)
        summary_calls = sum(c["prompt_id"] == "summarize_trace_v1" for c in calls)
        self.assertGreater(summary_calls, 0)
        self.assertEqual(len(calls), summary_calls + 2)
        self.assertEqual(len(result["usage_ids"]), len(calls))
        self.assertEqual(self.store.get("episodes", ep["episode_id"])["events"], ep["events"])
        expanded = next(f for f in extracts[1]["fragments"] if f["ref_id"] == requested[0])
        _, original = _resolve(index_episodes([ep], contexts={}), requested[0])
        for key in ("text", "raw_ref", "raw_hash", "range"):
            self.assertEqual(expanded[key], original[key])
        self.assertNotIn(requested[0], {f["ref_id"] for f in extracts[0]["fragments"]})
        return result, extracts, requested

    def test_real_packet_expansion_is_finite_and_recorded(self):
        result, extracts, requested = self._runtime_expansion_case(request_after_limit=False)
        self.assertEqual(result["status"], "noop")
        self.assertEqual(len(requested), 1)
        stored = self.store.get("evidence_packets", extracts[1]["packet_id"])
        self.assertIn(requested[0], {f["ref_id"] for f in stored["fragments"]})

    def test_more_evidence_request_after_limit_abstains(self):
        result, extracts, requested = self._runtime_expansion_case(request_after_limit=True)
        self.assertEqual(result["status"], "abstained")
        self.assertEqual(result["candidate_ids"], [])
        self.assertEqual(len(requested), 2)
        self.assertNotEqual(requested[0], requested[1])
        self.assertNotIn(requested[1], {f["ref_id"] for f in extracts[1]["fragments"]})

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

    def test_canonical_merge_cannot_reintroduce_mixed_forbidden_history(self):
        extraction, diagnosis, _ = drafts(self.source)
        diagnosis["route"] = "external_issue"
        first = learn(self.store, self.ids, self.model([extraction, diagnosis])[0], policy=policy())
        valid = self.store.get("experiences", first["experience_ids"][0])
        frozen = sample_tasks(self.store,
            [{"project_id": "demo-project", "task_id": "held-out-canonical", "revision": "v1", "description": "CSV held-out"}],
            lambda *args: {"artifact": "PRIVATE CANONICAL MATERIAL"}, None,
            policy={"purpose": "final", "update_mode": "none", "repeat_count": 1, "max_parallel": 1,
                    "protocol_id": "frozen-canonical", "executor": {"id": "fixture", "config": {}}},
            context_policy={"max_roots": 1, "max_context_chars": 5000, "relation_weight": 0.0})["episodes"][0]
        # A historical pre-fix record mixes valid and forbidden sources. It
        # remains auditable, but neither retrieval nor consolidation may reuse it.
        polluted = copy.deepcopy(valid)
        polluted.update(record_id="mixed-historical", created_at="2027-01-01T00:00:00Z",
                        source_episode_ids=[*valid["source_episode_ids"], frozen["episode_id"]])
        polluted["retained_evidence"].append({"role": "boundary_refs", "ref_id": "PRIVATE_CANONICAL_BOUNDARY",
            "packet_id": "old-private-packet", "record_id": "mixed-historical", "status": "historical_reference_not_retracted"})
        self.store.put("experiences", polluted["record_id"], polluted)
        revised = copy.deepcopy(extraction)
        revised["experiences"][0]["unknowns"].append("Fresh lawful source observation remains limited.")
        model, call = self.model([revised, diagnosis])
        result = learn(self.store, self.ids, model, policy=policy())
        self.assertEqual(result["status"], "noop")
        fresh = self.store.get("experiences", result["experience_ids"][0])
        self.assertEqual(fresh["supersedes"], valid["record_id"])
        self.assertEqual(fresh["source_episode_ids"], valid["source_episode_ids"])
        self.assertNotIn("PRIVATE_CANONICAL_BOUNDARY", json.dumps(fresh))
        self.assertNotIn("PRIVATE CANONICAL MATERIAL", str(call.calls))
        self.assertNotIn("PRIVATE_CANONICAL_BOUNDARY", str(call.calls))
        self.assertEqual(self.store.get("experiences", polluted["record_id"]), polluted)

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

    def test_outer_transport_price_survives_actual_learn_and_call_usage_report(self):
        empty = copy.deepcopy(EXAMPLES["extraction"]); empty["experiences"] = []
        priced = response(empty)
        priced["usage"].update(monetary_cost=0.125, currency="USD", price_version="provider-test-v1")
        model = StructuredModel(FakeCall([priced]), limits=model_limits())
        result = learn(self.store, self.ids, model, policy=policy())
        self.assertEqual(result["status"], "noop")
        usage = self.store.get("usage", result["usage_ids"][0])
        self.assertEqual(usage["monetary_cost"], 0.125)
        self.assertEqual(usage["currency"], "USD")
        self.assertEqual(usage["price_version"], "provider-test-v1")
        self.assertEqual(usage["raw"]["monetary_cost"], 0.125)
        aggregate = report(self.store, "demo-project")["usage"]
        self.assertEqual(aggregate["known_cost_subtotals"], {"USD": 0.125})
        self.assertEqual(aggregate["missing_cost_calls"], 0)

    def test_unpriced_transport_stays_unknown_despite_a_model_body_price_claim(self):
        untrusted = {**copy.deepcopy(EXAMPLES["abstain"]), "monetary_cost": 99.0,
                     "currency": "USD", "price_version": "model-invented"}
        model = StructuredModel(FakeCall([response(untrusted)]), limits=model_limits(max_format_repairs=0))
        result = learn(self.store, self.ids, model, policy=policy())
        self.assertEqual(result["status"], "error")
        usage = self.store.get("usage", result["usage_ids"][0])
        for field in ("monetary_cost", "currency", "price_version"):
            self.assertIsNone(usage[field])
        aggregate = report(self.store, "demo-project")["usage"]
        self.assertIsNone(aggregate["complete_cost_totals"])
        self.assertEqual(aggregate["missing_cost_calls"], 1)

    def test_rejected_model_attempt_cost_is_preserved_and_zero_is_reported(self):
        empty = copy.deepcopy(EXAMPLES["extraction"]); empty["experiences"] = []
        replies = [response("not JSON"), response(empty)]
        for reply, cost in zip(replies, (0.125, 0.0)):
            reply["usage"].update(monetary_cost=cost, currency="USD", price_version="provider-test-v1")
        result = learn(self.store, self.ids, StructuredModel(FakeCall(replies), limits=model_limits()), policy=policy())
        self.assertEqual(result["status"], "noop")
        rows = [self.store.get("usage", ref) for ref in result["usage_ids"]]
        self.assertEqual([row["monetary_cost"] for row in rows], [0.125, 0.0])
        self.assertEqual(rows[0]["raw"]["status"], "invalid_output")
        aggregate = report(self.store, "demo-project")["usage"]
        self.assertEqual(aggregate["unique_calls"], 2)
        self.assertEqual(aggregate["complete_cost_totals"], {"USD": 0.125})

    def test_interrupted_provider_wait_is_not_charged_as_local_maintenance(self):
        clock = [10.0]
        interrupted = KeyboardInterrupt("provider operation interrupted")
        def invoke(_):
            clock[0] += 30.0
            raise interrupted
        model = StructuredModel(invoke, limits=model_limits())
        with patch("memory_orchestrator.telemetry.time.monotonic", side_effect=lambda: clock[0]):
            with self.assertRaises(KeyboardInterrupt) as caught:
                learn(self.store, self.ids, model, policy=policy())
        self.assertIs(caught.exception, interrupted)
        rows = [row for row in self.store.list("stage_measurements", "demo-project") if row["stage"] == "extract"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["elapsed_seconds"], 30.0)
        self.assertEqual(rows[0]["delegated_seconds"], 30.0)
        self.assertEqual(rows[0]["local_seconds"], 0.0)
        self.assertEqual(rows[0]["status"], "error")
        self.assertIsNone(rows[0]["monetary_cost"])
        self.assertEqual(self.store.list("usage", "demo-project"), [])
        self.assertEqual({r["status"] for r in self.store.list("learning_cycles", "demo-project")}, {"planned"})
        self.assertIsNone(report(self.store, "demo-project")["usage"]["complete_cost_totals"])


if __name__ == "__main__": unittest.main()
