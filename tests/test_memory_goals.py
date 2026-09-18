"""Derived goal decisions exercise the actual bounded structured-model path."""
import copy
import json
import tempfile
import unittest

from memory_orchestrator.store import Store
from memory_orchestrator.learning import learn
from memory_orchestrator.model import StructuredModel
from memory_orchestrator.evidence import build_packet, index_episodes, validate_packet
from memory_orchestrator.schemas import DomainError
from test_memory_evidence import episode, event, EXAMPLES, limits as packet_limits
from test_memory_learning import policy
from test_memory_model import response, limits as model_limits


class GoalTests(unittest.TestCase):
    def test_switch_resume_uses_prior_grounded_catalog_and_never_rewrites_raw(self):
        with tempfile.TemporaryDirectory() as path:
            store = Store(path); ep = episode()
            ep["events"] = [event("u1", "Inspect CSV parsing", "instruction", source_role="user"),
                            event("u2", "Switch to API auth", "instruction", source_role="user"),
                            event("u3", "Return to CSV parsing", "instruction", source_role="user")]
            store.add_episode(ep); calls = []
            def teacher(request):
                calls.append(copy.deepcopy(request))
                if request["prompt_id"] == "extract_v1": return response(EXAMPLES["abstain"])
                body = request["messages"][1]["content"]
                users, _ = json.JSONDecoder().raw_decode(body.split("用户事件正文：", 1)[1])
                cap, _ = json.JSONDecoder().raw_decode(body.split("本轮窗口和补读预算：", 1)[1])
                catalog, _ = json.JSONDecoder().raw_decode(body.split("已知或派生目标及依据：", 1)[1])
                ref = cap["target_user_refs"][0]
                target = next(x for x in users if x["ref_id"] == ref)
                if target["event_id"] == "u1":
                    self.assertNotIn("Return to CSV", json.dumps(users)); self.assertEqual(catalog, [])
                    goal, revision, relation = "new:csv", "new:initial", "continues"
                elif target["event_id"] == "u2":
                    goal, revision, relation = "new:api", "new:initial", "switches"
                else:
                    self.assertEqual(len(catalog), 2)
                    goal, revision, relation = catalog[0]["goal_id"], catalog[0]["revision"], "resumes"
                    self.assertIn("Inspect CSV", catalog[0]["anchor_excerpt"]["text"])
                return response({"status": "completed", "read_requests": [], "reason": "user-request boundary", "unknowns": [],
                    "bindings": [{"event_refs": [ref], "anchor_user_ref": ref, "goal_id": goal, "revision": revision,
                                  "relation": relation, "evidence_refs": [ref], "reason": "user explicitly names topic"}]})
            caps = policy(); caps["goal_binding"]["max_events"] = 1
            result = learn(store, [ep["episode_id"]], StructuredModel(teacher, limits=model_limits(max_calls=6)), policy=caps)
            self.assertEqual(result["status"], "abstained")
            self.assertEqual(len(result["goal_binding_ids"]), 3)
            bindings = [store.get("goal_bindings", rid)["resolved_bindings"][0] for rid in result["goal_binding_ids"]]
            self.assertEqual(bindings[0]["goal_id"], bindings[2]["goal_id"])
            self.assertNotEqual(bindings[0]["goal_id"], bindings[1]["goal_id"])
            self.assertEqual(store.get("episodes", ep["episode_id"]), ep)
            self.assertIn('"relation":"resumes"', calls[-1]["messages"][1]["content"].replace(" ", ""))

    def test_failed_association_is_retained_as_unknown_before_ordinary_extraction(self):
        with tempfile.TemporaryDirectory() as path:
            store = Store(path); ep = episode()
            ep["events"] = [event("u", "Unknown scope", "instruction", source_role="user")]
            store.add_episode(ep)
            def teacher(request):
                return response("not JSON" if request["prompt_id"] == "goal_binding_v1" else EXAMPLES["abstain"])
            result = learn(store, [ep["episode_id"]], StructuredModel(teacher, limits=model_limits(max_format_repairs=0)), policy=policy())
            self.assertEqual(result["status"], "abstained")
            record = store.get("goal_bindings", result["goal_binding_ids"][0])
            self.assertEqual(record["status"], "abstained"); self.assertTrue(record["unresolved_refs"])
            self.assertEqual(len(result["usage_ids"]), 2)

    def test_invented_derived_metadata_cannot_pass_source_validation(self):
        index = index_episodes([episode()]); packet = build_packet(index, limits=packet_limits())
        fragment = packet["fragments"][0]["ref_id"]
        packet["goal_annotations"] = [{"binding_ref": "invented", "event_ref": fragment, "anchor_user_ref": fragment,
            "goal_id": "made-up", "revision": "made-up", "relation": "continues", "evidence_refs": [fragment], "origin": "model_proxy"}]
        with self.assertRaises(DomainError): validate_packet(packet, index)

    def test_agent_instruction_is_not_a_user_anchor_even_if_its_text_says_switch(self):
        from memory_orchestrator.goals import check_goal_draft
        ep = episode(); ep["events"] = [event("plan", "Switch to rewriting authentication", "instruction", source_role="agent")]
        index = index_episodes([ep]); packet = build_packet(index, limits=packet_limits())
        ref = next(f["ref_id"] for f in packet["fragments"] if f["event_id"] == "plan")
        draft = {"status": "completed", "bindings": [{"event_refs": [ref], "goal_id": "new:auth", "revision": "new:initial",
            "relation": "switches", "anchor_user_ref": ref, "reason": "assistant plan", "evidence_refs": [ref]}],
            "read_requests": [], "reason": "plan", "unknowns": []}
        with self.assertRaises(DomainError) as caught:
            check_goal_draft(draft, index, packet, [], {"max_bindings": 2, "max_read_requests": 2, "target_user_refs": [ref]})
        self.assertEqual(caught.exception.code, "goal_binding")


if __name__ == "__main__": unittest.main()
