"""Learning checks derived from blueprint examples; all model responses are synthetic."""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from memory_orchestrator.common import DomainError, digest, load_contracts
from memory_orchestrator.learning import (
    ModelClient, build_packet, expand_packet, find_related, learn_from_episodes,
)


BLUEPRINT = json.loads((Path(__file__).parents[1] / "docs/blueprint/project-contract.json").read_text())
EXAMPLES = {x["id"]: x["value"] for x in BLUEPRINT["examples"]}


def episodes():
    """Adapt the existing illustrative packet to the current caller-submission API."""
    result = {}
    for fragment in EXAMPLES["evidence-packet"]["fragments"]:
        episode = result.setdefault(fragment["run_id"], {
            "id": fragment["run_id"], "project": "csv-project",
            "task": EXAMPLES["evidence-packet"]["fragments"][0]["text"],
            "task_id": "csv-task" if fragment["run_id"] != "demo:run-c" else "amount-task",
            "task_revision": fragment["task_revision"],
            "snapshot_id": None, "context_id": None,
            "source": "illustrative_blueprint", "events": [], "feedback": [],
            "capture_gaps": ["No measured agent run; illustrative source only."],
        })
        episode["events"].append({"event_id": fragment["event_id"], "kind": fragment["kind"],
                                  "text": fragment["text"], "source": "illustrative_blueprint"})
    return list(result.values())


def remap_refs(value, packet):
    mapping = {fragment.get("event_id"): fragment["ref_id"] for fragment in packet["fragments"]}
    def visit(item):
        if isinstance(item, list):
            return [visit(x) for x in item]
        if isinstance(item, dict):
            return {k: visit(v) for k, v in item.items()}
        return mapping.get(item, item) if isinstance(item, str) else item
    return visit(copy.deepcopy(value))


def snapshot():
    experience = EXAMPLES["experience"]
    return {"snapshot_id": "a" * 64, "project": "csv-project", "parent": None,
            "skills": {"csv-schema-preservation": {
                "skill_id": "csv-schema-preservation", "revision": "r1", "project": "csv-project",
                "title": experience["title"], "scope": experience["scope"],
                "triggers": ["CSV"], "preconditions": [],
                "steps": [{"rule_id": "R1", "text": "Read schema."},
                          {"rule_id": "R2", "text": "Infer every field type automatically."}],
                "exceptions": [], "checks": ["Check output."],
                "depends_on": [], "declared_conflicts": [], "evidence_refs": []}}, "assets": {}}


class ScriptedModel:
    """Not a language model; returns explicit fixture output for data-flow checks."""
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def generate(self, prompt_id, inputs, output_schema):
        self.calls.append((prompt_id, copy.deepcopy(inputs), output_schema))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if callable(reply):
            reply = reply(inputs)
        return {"value": copy.deepcopy(reply), "usage": [{"id": f"fixture-call-{len(self.calls)}",
                "prompt_id": prompt_id, "input_tokens": 10, "output_tokens": 10,
                "measurement": "synthetic"}], "raw_response": "synthetic fixture"}


class MockSDK:
    """Imitates only the installed OpenAI SDK method used by ModelClient."""
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def response(value, finish="stop", usage=True):
    return {"id": "synthetic-response", "choices": [{"finish_reason": finish,
            "message": {"content": value if isinstance(value, str) else json.dumps(value, ensure_ascii=False),
                        "refusal": None}}],
            "usage": {"prompt_tokens": 17, "completion_tokens": 8, "total_tokens": 25} if usage else None}


def extract_inputs():
    prompt = load_contracts()["prompts"]["extract_v1"]
    return {field: None for field in prompt["input_fields"] if field != "output_schema"}


class PacketTests(unittest.TestCase):
    def test_pack_preserves_original_hashes_sources_and_unknown(self):
        source = episodes()
        before = copy.deepcopy(source)
        packet = build_packet(source)
        self.assertEqual(source, before)
        self.assertEqual(set(x["event_id"] for x in packet["fragments"] if x.get("event_id")),
                         {f"demo:E{i}" for i in range(1, 8)})
        self.assertTrue(packet["gaps"])
        for fragment in packet["fragments"]:
            if fragment.get("event_id"):
                event = next(e for ep in source for e in ep["events"] if e["event_id"] == fragment["event_id"])
                self.assertEqual(fragment["raw_hash"], digest(event["text"]))
                self.assertEqual(fragment["source"], "illustrative_blueprint")

    def test_long_trace_retains_start_failure_middle_and_recovery(self):
        source = episodes()[:1]
        original = source[0]["events"]
        noise = [{"event_id": f"noise-{i}", "kind": "observation", "text": "unchanged output " * 200}
                 for i in range(100)]
        source[0]["events"] = original[:1] + noise[:50] + original[2:] + noise[50:] + [
            {"event_id": "recovery", "kind": "recovery", "text": "Retry uses explicit string schema; check passed."}]
        packet = build_packet(source, max_chars=9000)
        self.assertLessEqual(len(json.dumps(packet, ensure_ascii=False, separators=(",", ":"))), 9000)
        kinds = {f["kind"] for f in packet["fragments"]}
        self.assertTrue({"requirement", "feedback", "recovery"}.issubset(kinds))
        self.assertTrue(packet["omitted_refs"])
        self.assertLess(packet["coverage"]["provided_count"], packet["coverage"]["total_count"])

    def test_single_long_event_provides_bounded_snippet(self):
        source = episodes()[:1]
        source[0]["events"] = [{"event_id": "long", "kind": "error", "text":
            "start " + "x" * 20000 + " ERROR missing schema " + "y" * 20000 + " end"}]
        packet = build_packet(source, max_chars=4500)
        fragment = next(f for f in packet["fragments"] if f.get("event_id") == "long")
        self.assertTrue(fragment["truncated"])
        self.assertTrue(fragment["segments"])
        self.assertIn("ERROR missing schema", fragment["text"])
        self.assertLessEqual(len(json.dumps(packet, ensure_ascii=False, separators=(",", ":"))), 4500)

    def test_expand_catalogued_ref_and_reject_fabrication_or_changed_raw(self):
        source = episodes()[:1]
        source[0]["events"].extend({"event_id": f"extra-{i}", "kind": "observation", "text": "details " * 60}
                                    for i in range(20))
        packet = build_packet(source, max_chars=4500)
        omitted = next(c["ref_id"] for c in packet["readable_ref_catalog"]
                       if c["ref_id"] not in {f["ref_id"] for f in packet["fragments"]})
        expanded = expand_packet(packet, source, [{"ref_id": omitted, "purpose": "inspect operation"}], 14000)
        self.assertIn(omitted, {f["ref_id"] for f in expanded["fragments"]})
        with self.assertRaises(DomainError):
            expand_packet(packet, source, [{"ref_id": "foreign", "purpose": "read"}], 14000)
        changed = copy.deepcopy(source)
        for event in changed[0]["events"]:
            event["text"] += " changed"
        with self.assertRaises(DomainError):
            expand_packet(packet, changed, [{"ref_id": omitted, "purpose": "read"}], 14000)

    def test_mixed_projects_rejected(self):
        source = episodes()
        source[-1]["project"] = "csv-project-other"
        with self.assertRaises(DomainError):
            build_packet(source)

    def test_related_exact_project_duplicate_sources_and_counterexamples(self):
        draft = copy.deepcopy(EXAMPLES["experience"])
        a = {"id": "a", "project": "csv-project", "draft": draft, "episode_ids": ["ep1"], "source_task_ids": ["task1"]}
        duplicate = dict(copy.deepcopy(a), id="duplicate")
        foreign = dict(copy.deepcopy(a), id="foreign", project="csv-project-other")
        boundary = dict(copy.deepcopy(a), id="boundary", episode_ids=["ep2"], source_task_ids=["task1"])
        boundary["draft"]["title"] = "CSV numeric conversion boundary"
        related = find_related([a, duplicate, foreign, boundary], "CSV schema", "csv-project")
        self.assertEqual(len(related), 2)
        self.assertNotIn("foreign", {x["id"] for x in related})
        self.assertTrue(any(x["draft"]["boundary_refs"] for x in related))


class ClientTests(unittest.TestCase):
    def test_sdk_prompt_schema_and_defaults(self):
        sdk = MockSDK([response(EXAMPLES["abstain"])])
        client = ModelClient(client=sdk)
        result = client.generate("extract_v1", extract_inputs(), "ExtractionDraft")
        self.assertEqual(result["value"], EXAMPLES["abstain"])
        call = sdk.calls[0]
        self.assertEqual(call["model"], "gpt-5.6-terra")
        self.assertEqual(call["response_format"], {"type": "json_object"})
        self.assertEqual(call["timeout"], 60)
        self.assertNotIn("{{", str(call["messages"]))
        self.assertIn("observed_facts", str(call["messages"]))
        self.assertEqual(result["usage"][0]["input_tokens"], 17)

    def test_one_format_repair_includes_original_rejected_and_errors(self):
        sdk = MockSDK([response({"status": "completed"}), response(EXAMPLES["abstain"])])
        result = ModelClient(client=sdk).generate("extract_v1", extract_inputs(), "ExtractionDraft")
        self.assertEqual(len(sdk.calls), 2)
        self.assertEqual(len(result["usage"]), 2)
        repair_messages = sdk.calls[1]["messages"]
        self.assertEqual(repair_messages[:2], sdk.calls[0]["messages"])
        self.assertIn("experiences", str(repair_messages[-1]))
        self.assertEqual(repair_messages[-2]["role"], "assistant")

    def test_second_invalid_output_preserves_both_attempt_costs(self):
        sdk = MockSDK([response("not-json"), response("still-not-json")])
        with self.assertRaises(DomainError) as caught:
            ModelClient(client=sdk).generate("extract_v1", extract_inputs(), "ExtractionDraft")
        self.assertEqual(len(sdk.calls), 2)
        self.assertEqual(len(caught.exception.details["usage"]), 2)
        self.assertEqual(caught.exception.code, "invalid_output")

    def test_truncation_not_silent_success_or_retry(self):
        sdk = MockSDK([response(EXAMPLES["abstain"], finish="length")])
        with self.assertRaises(DomainError) as caught:
            ModelClient(client=sdk).generate("extract_v1", extract_inputs(), "ExtractionDraft")
        self.assertEqual(len(sdk.calls), 1)
        self.assertEqual(caught.exception.code, "model_truncated")
        self.assertEqual(caught.exception.details["usage"][0]["output_tokens"], 8)

    def test_transport_unknown_usage_without_secret_exception_text(self):
        sdk = MockSDK([RuntimeError("Authorization: Bearer DO_NOT_STORE_THIS")])
        with self.assertRaises(DomainError) as caught:
            ModelClient(client=sdk).generate("extract_v1", extract_inputs(), "ExtractionDraft")
        self.assertNotIn("DO_NOT_STORE_THIS", str(caught.exception) + str(caught.exception.details))
        usage = caught.exception.details["usage"][0]
        self.assertIsNone(usage["input_tokens"])
        self.assertIsNone(usage["output_tokens"])
        self.assertEqual(len(sdk.calls), 1)

    def test_budget_repair_failure_retains_first_attempt(self):
        sdk = MockSDK([response("not-json")])
        with self.assertRaises(DomainError) as caught:
            ModelClient(client=sdk, max_calls=1).generate("extract_v1", extract_inputs(), "ExtractionDraft")
        self.assertEqual(caught.exception.code, "model_budget_exhausted")
        self.assertEqual(len(caught.exception.details["usage"]), 1)

    def test_missing_template_field_fails_before_call(self):
        sdk = MockSDK([])
        with self.assertRaises(DomainError):
            ModelClient(client=sdk).generate("extract_v1", {}, "ExtractionDraft")
        self.assertEqual(sdk.calls, [])


class LearningTests(unittest.TestCase):
    def prepared(self):
        source = episodes()
        packet = build_packet(source)
        return source, packet, [remap_refs(EXAMPLES[k], packet) for k in ("extraction", "diagnosis", "patch")]

    def test_three_stages_current_prompts_unknown_fields_and_no_source_mutation(self):
        source, packet, drafts = self.prepared()
        before = copy.deepcopy(source)
        model = ScriptedModel(drafts)
        result = learn_from_episodes(source, snapshot(), [], model)
        self.assertEqual(result["status"], "proposed")
        self.assertEqual(source, before)
        self.assertEqual([c[0] for c in model.calls], ["extract_v1", "diagnose_v1", "propose_v1"])
        self.assertEqual(len(result["usage"]), 3)
        self.assertEqual(result["source_episode_ids"], [ep["id"] for ep in source])
        self.assertEqual(result["allowed_targets"], ["csv-schema-preservation"])
        for prompt_id, inputs, _ in model.calls:
            required = set(load_contracts()["prompts"][prompt_id]["input_fields"]) - {"output_schema"}
            self.assertTrue(required.issubset(inputs))
        self.assertTrue(all(x["snapshot_id"] is None for x in model.calls[1][1]["source_run_snapshots"]))
        self.assertIn("unknown", json.dumps(model.calls[0][1]["task_assessments"]))

    def test_unknown_outcome_can_form_bounded_experience(self):
        source, packet, drafts = self.prepared()
        diagnosis = drafts[1]
        diagnosis.update(route="external_issue", targets=[])
        model = ScriptedModel([drafts[0], diagnosis])
        result = learn_from_episodes(source, snapshot(), [], model)
        self.assertEqual(result["status"], "noop")
        self.assertEqual(len(result["experiences"]), 1)
        self.assertIsNone(result["patch"])
        self.assertEqual(len(model.calls), 2)

    def test_unread_and_foreign_citations_rejected(self):
        source, _, drafts = self.prepared()
        drafts[0]["experiences"][0]["observed_facts"][0]["evidence_refs"] = ["not-provided"]
        model = ScriptedModel([drafts[0]])
        result = learn_from_episodes(source, snapshot(), [], model)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["errors"][0]["code"], "unsupported_evidence")
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(len(result["usage"]), 1)

    def test_stale_target_or_missing_rule_never_proposes(self):
        for field, value in (("revision", "r999"), ("rule_id", "not-a-rule")):
            with self.subTest(field=field):
                source, _, drafts = self.prepared()
                drafts[1]["targets"][0][field] = value
                model = ScriptedModel(drafts[:2])
                result = learn_from_episodes(source, snapshot(), [], model)
                self.assertEqual(result["status"], "error")
                self.assertIsNone(result["patch"])
                self.assertEqual(len(model.calls), 2)

    def test_proposal_cannot_edit_related_but_untargeted_skill(self):
        source, _, drafts = self.prepared()
        base = snapshot()
        base["skills"]["other"] = dict(copy.deepcopy(base["skills"]["csv-schema-preservation"]), skill_id="other")
        drafts[2]["operations"][0]["target_skill_id"] = "other"
        result = learn_from_episodes(source, base, [], ScriptedModel(drafts))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["errors"][0]["code"], "unauthorized_target")

    def test_expansion_is_bounded_and_successful_read_becomes_citable(self):
        source = episodes()[:1]
        source[0]["events"].extend({"event_id": f"extra-{i}", "kind": "observation", "text": "details " * 80}
                                    for i in range(20))
        def request(inputs):
            packet = inputs["evidence_packet"]
            omitted = next(c["ref_id"] for c in packet["readable_ref_catalog"]
                           if c["ref_id"] not in {f["ref_id"] for f in packet["fragments"]})
            return dict(copy.deepcopy(EXAMPLES["need-more"]), read_requests=[{"ref_id": omitted, "purpose": "inspect"}])
        model = ScriptedModel([request, EXAMPLES["abstain"]])
        result = learn_from_episodes(source, snapshot(), [], model,
                                     {"max_packet_chars": 4500, "max_expanded_packet_chars": 14000})
        self.assertEqual(result["status"], "abstained")
        self.assertEqual(len(model.calls), 2)
        self.assertGreater(len(model.calls[1][1]["evidence_packet"]["fragments"]),
                           len(model.calls[0][1]["evidence_packet"]["fragments"]))

    def test_zero_experiences_and_model_failure_keep_accounting(self):
        source = episodes()
        empty = dict(copy.deepcopy(EXAMPLES["extraction"]), experiences=[])
        self.assertEqual(learn_from_episodes(source, snapshot(), [], ScriptedModel([empty]))["status"], "noop")
        model = ScriptedModel([DomainError("model_transport_error", "failed", {"usage": [{"id": "failed", "input_tokens": None}]})])
        result = learn_from_episodes(source, snapshot(), [], model)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["usage"][0]["id"], "failed")


if __name__ == "__main__":
    unittest.main()
