"""Budget mechanics over a real GDPevo trace; injected counters are not model evidence."""
import copy
import json
import math
from pathlib import Path
import unittest

from memory_orchestrator.evidence import build_packet, feedback_view, index_episodes
from memory_orchestrator.model import StructuredModel
from memory_orchestrator.schemas import DomainError, digest, load_contracts
from test_memory_model import EXAMPLES, FakeCall, inputs, limits, response


def caps(*, total_input=1000000, total_output=10000, stage_updates=None):
    stage = {"max_calls": 10, "max_input_tokens": 100000, "max_output_tokens": 50,
             "max_total_input_tokens": 1000000, "max_total_output_tokens": 10000}
    stages = {name: copy.deepcopy(stage) for name in load_contracts()["prompts"]}
    for name, changes in (stage_updates or {}).items():
        stages[name].update(changes)
    return limits(max_input_chars=2000000, max_total_input_chars=10000000,
                  max_calls=20, token_budget={
                      "counter_id": "utf8-json-bytes-div3-v1", "count_kind": "documented_estimate",
                      "max_input_tokens": 100000, "max_total_input_tokens": total_input,
                      "max_total_output_tokens": total_output, "stages": stages})


def reply(value=None, *, input_tokens=100, output_tokens=7, finish="stop"):
    result = response(EXAMPLES["abstain"] if value is None else value, finish=finish)
    result["usage"] = {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": None}
    return result


class ModelBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = json.loads((Path(__file__).parent / "fixtures/gdpevo_context_train001.json").read_text())
        ep = fixture["episode"]
        index = index_episodes([ep], feedback=[fixture["feedback"]],
                               contexts={fixture["context"]["manifest_id"]: fixture["context"]})
        packet = build_packet(index, limits=fixture["packet_limits"])
        cls.extract_inputs = {
            "task_requirements": [{"episode_id": ep["episode_id"], "task_id": ep["task"]["task_id"],
                "revision": ep["task"]["revision"], "provided_requirement_refs": [
                    row["ref_id"] for row in packet["fragments"] if row["kind"] == "task"]}],
            "evidence_packet": packet, "available_feedback": feedback_view(index, packet),
            "related_experiences": [], "readable_ref_catalog": packet["readable_ref_catalog"],
            "extraction_limits": {"max_experiences": 3, "max_read_requests": 2, "max_evidence_expansions": 1}}

    def make_model(self, replies, *, config=None, counter=None):
        config = caps() if config is None else config
        config["token_budget"].update(counter_id="injected-test-counter-v1", count_kind="documented_estimate")
        call = FakeCall(replies)
        model = StructuredModel(call, limits=config, token_counter=(lambda messages: 100) if counter is None else counter)
        return model, call

    def test_zero_input_token_quota_rejects_before_any_transport(self):
        call = FakeCall([reply()])
        model = StructuredModel(call, limits=caps(total_input=0))
        with self.assertRaises(DomainError) as caught:
            model.generate("extract_v1", self.extract_inputs)
        self.assertEqual(caught.exception.code, "model_budget_exhausted")
        self.assertEqual(call.calls, [])

    def test_zero_output_quota_rejects_before_any_transport(self):
        call = FakeCall([reply()])
        model = StructuredModel(call, limits=caps(total_output=0))
        with self.assertRaises(DomainError): model.generate("extract_v1", self.extract_inputs)
        self.assertEqual(call.calls, [])

    def test_preview_counts_exact_rendered_payload_without_consuming(self):
        seen = []
        def counter(messages):
            seen.append(copy.deepcopy(messages))
            messages[0]["content"] = "COUNTER_MUST_NOT_MUTATE_REQUEST"
            return 123
        model, call = self.make_model([reply()], counter=counter)
        preview = model.preview("extract_v1", self.extract_inputs)
        self.assertTrue(preview["fits"])
        self.assertEqual(preview["estimated_input_tokens"], 123)
        self.assertEqual(preview["effective_output_cap"], 50)
        self.assertEqual((model.calls, call.calls), (0, []))
        result = model.generate("extract_v1", self.extract_inputs)
        self.assertEqual(seen[0], call.calls[0]["messages"])
        self.assertEqual(seen[1], call.calls[0]["messages"])
        self.assertEqual(preview["messages_hash"], digest(call.calls[0]["messages"]))
        schema = load_contracts()["schemas"]["ExtractionDraft"]
        self.assertIn(json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":")), seen[0][1]["content"])
        self.assertIn(self.extract_inputs["task_requirements"][0]["task_id"], str(seen[0]))
        self.assertNotIn("COUNTER_MUST_NOT_MUTATE_REQUEST", str(call.calls))
        self.assertEqual(result["usage"][0]["budget"]["estimated_input_tokens"], 123)

    def test_default_estimate_is_declared_and_does_not_replace_provider_usage(self):
        call = FakeCall([reply(input_tokens=11)])
        model = StructuredModel(call, limits=caps())
        preview = model.preview("extract_v1", self.extract_inputs)
        result = model.generate("extract_v1", self.extract_inputs)
        serialized = json.dumps(call.calls[0]["messages"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertEqual(preview["estimated_input_tokens"], math.ceil(len(serialized.encode("utf-8")) / 3))
        entry = result["usage"][0]
        self.assertEqual(entry["input_tokens"], 11)
        self.assertEqual(entry["budget"]["input_debit"], 11)
        self.assertEqual(entry["budget"]["count_kind"], "documented_estimate")
        self.assertEqual(entry["budget"]["counter_id"], "utf8-json-bytes-div3-v1")

    def test_global_input_cumulative_limit_and_preview_are_rechecked(self):
        model, call = self.make_model([reply(), reply()], config=caps(total_input=150))
        self.assertTrue(model.preview("extract_v1", self.extract_inputs)["fits"])
        model.generate("extract_v1", self.extract_inputs)
        self.assertFalse(model.preview("extract_v1", self.extract_inputs)["fits"])
        with self.assertRaises(DomainError): model.generate("extract_v1", self.extract_inputs)
        self.assertEqual(len(call.calls), 1)

    def test_global_single_request_token_limit_includes_full_input(self):
        config = caps(); config["token_budget"]["max_input_tokens"] = 99
        model, call = self.make_model([reply()], config=config)
        self.assertFalse(model.preview("extract_v1", self.extract_inputs)["fits"])
        with self.assertRaises(DomainError): model.generate("extract_v1", self.extract_inputs)
        self.assertEqual(call.calls, [])

    def test_global_output_reservation_survives_unknown_usage(self):
        model, call = self.make_model([reply(output_tokens=None), reply()], config=caps(total_output=75))
        result = model.generate("extract_v1", self.extract_inputs)
        entry = result["usage"][0]
        self.assertIsNone(entry["output_tokens"])
        self.assertEqual(entry["budget"]["reserved_output_tokens"], 50)
        self.assertEqual(entry["budget"]["output_debit"], 50)
        with self.assertRaises(DomainError): model.generate("extract_v1", self.extract_inputs)
        self.assertEqual(len(call.calls), 1)

    def test_known_output_releases_only_unused_reservation(self):
        model, call = self.make_model([reply(output_tokens=5), reply(output_tokens=5)], config=caps(total_output=55))
        first = model.generate("extract_v1", self.extract_inputs)
        second = model.generate("extract_v1", self.extract_inputs)
        self.assertEqual([first["usage"][0]["budget"]["output_debit"], second["usage"][0]["budget"]["output_debit"]], [5, 5])
        self.assertEqual([r["max_output_tokens"] for r in call.calls], [50, 50])

    def test_stage_input_total_cannot_borrow_other_stage_allowance(self):
        config = caps(stage_updates={"extract_v1": {"max_total_input_tokens": 150}})
        model, call = self.make_model([reply(), reply(EXAMPLES["diagnosis"])], config=config)
        model.generate("extract_v1", self.extract_inputs)
        with self.assertRaises(DomainError): model.generate("extract_v1", self.extract_inputs)
        model.generate("diagnose_v1", inputs("diagnose_v1"))
        self.assertEqual([r["prompt_id"] for r in call.calls], ["extract_v1", "diagnose_v1"])

    def test_stage_call_limit_counts_repeated_generate(self):
        model, call = self.make_model([reply(), reply()], config=caps(stage_updates={"extract_v1": {"max_calls": 1}}))
        model.generate("extract_v1", self.extract_inputs)
        with self.assertRaises(DomainError): model.generate("extract_v1", self.extract_inputs)
        self.assertEqual(len(call.calls), 1)

    def test_stage_output_total_counts_unknown_completion(self):
        model, call = self.make_model([reply(output_tokens=None), reply()],
                                     config=caps(stage_updates={"extract_v1": {"max_total_output_tokens": 75}}))
        model.generate("extract_v1", self.extract_inputs)
        with self.assertRaises(DomainError): model.generate("extract_v1", self.extract_inputs)
        self.assertEqual(len(call.calls), 1)

    def test_repair_recounts_original_rejected_output_and_diagnostics(self):
        seen = []
        def counter(messages):
            seen.append(copy.deepcopy(messages))
            return 100 if len(messages) == 2 else 300
        model, call = self.make_model([reply("bad JSON"), reply()], counter=counter,
                                     config=caps(stage_updates={"extract_v1": {"max_input_tokens": 200}}))
        with self.assertRaises(DomainError) as caught: model.generate("extract_v1", self.extract_inputs)
        self.assertEqual(caught.exception.code, "model_budget_exhausted")
        self.assertEqual(len(call.calls), 1)
        self.assertEqual(len(caught.exception.details["usage"]), 1)
        self.assertEqual(seen[-1][-2]["content"], "bad JSON")
        self.assertIn("Diagnostics:", seen[-1][-1]["content"])
        self.assertEqual(seen[-1][:2], seen[0])

    def test_semantic_repair_uses_the_same_stage_calls(self):
        model, call = self.make_model([reply(), reply()], config=caps(stage_updates={"extract_v1": {"max_calls": 1}}))
        def reject(value): raise DomainError("rejected_evidence", "Known false citation")
        with self.assertRaises(DomainError) as caught: model.generate("extract_v1", self.extract_inputs, check=reject)
        self.assertEqual(caught.exception.code, "model_budget_exhausted")
        self.assertEqual(len(call.calls), 1)
        self.assertEqual(caught.exception.details["attempts"][0]["diagnostics"]["code"], "rejected_evidence")

    def test_transport_error_keeps_both_reservations_and_no_secret(self):
        model, call = self.make_model([RuntimeError("Bearer PRIVATE_CREDENTIAL"), reply()], config=caps(total_input=150))
        with self.assertRaises(DomainError) as caught: model.generate("extract_v1", self.extract_inputs)
        entry = caught.exception.details["usage"][0]
        self.assertEqual((entry["budget"]["input_debit"], entry["budget"]["output_debit"]), (100, 50))
        self.assertIsNone(entry["input_tokens"])
        self.assertNotIn("PRIVATE_CREDENTIAL", str(caught.exception.details))
        with self.assertRaises(DomainError): model.generate("extract_v1", self.extract_inputs)
        self.assertEqual(len(call.calls), 1)

    def test_partial_and_invalid_usage_cannot_refund_missing_dimensions(self):
        for tokens in ({"input_tokens": 1.5, "output_tokens": True, "total_tokens": 10},
                       {"total_tokens": 10}, {"output_tokens": 7}):
            with self.subTest(tokens=tokens):
                returned = reply(); returned["usage"] = tokens
                model, _ = self.make_model([returned])
                entry = model.generate("extract_v1", self.extract_inputs)["usage"][0]
                self.assertIsNone(entry["input_tokens"])
                self.assertEqual(entry["budget"]["input_debit"], 100)
                expected = 7 if tokens.get("output_tokens") == 7 else 50
                self.assertEqual(entry["budget"]["output_debit"], expected)

    def test_reported_usage_reconciles_underestimate_without_inventing_overrun(self):
        model, call = self.make_model([reply(input_tokens=120)], config=caps(total_input=150))
        entry = model.generate("extract_v1", self.extract_inputs)["usage"][0]
        self.assertEqual(entry["budget"]["input_debit"], 120)
        self.assertEqual(entry["status"], "completed")
        self.assertFalse(model.preview("extract_v1", self.extract_inputs)["fits"])
        self.assertEqual(len(call.calls), 1)

    def test_reported_overrun_keeps_actual_tokens_and_stops_later_calls(self):
        model, call = self.make_model([reply(input_tokens=160), reply()], config=caps(total_input=150))
        with self.assertRaises(DomainError) as caught: model.generate("extract_v1", self.extract_inputs)
        self.assertEqual(caught.exception.code, "model_budget_exhausted")
        entry = caught.exception.details["usage"][0]
        self.assertEqual(entry["input_tokens"], 160)
        self.assertEqual(entry["budget"]["input_debit"], 160)
        self.assertEqual(entry["budget"]["budget_status"], "overrun")
        with self.assertRaises(DomainError): model.generate("extract_v1", self.extract_inputs)
        self.assertEqual(len(call.calls), 1)

    def test_stage_output_cap_is_enforced_in_actual_transport(self):
        model, call = self.make_model([reply(output_tokens=7)])
        self.assertEqual(model.preview("extract_v1", self.extract_inputs)["effective_output_cap"], 50)
        model.generate("extract_v1", self.extract_inputs)
        self.assertEqual(call.calls[0]["max_output_tokens"], 50)

    def test_oversized_reported_stage_output_is_not_accepted(self):
        model, call = self.make_model([reply(output_tokens=51)])
        with self.assertRaises(DomainError) as caught: model.generate("extract_v1", self.extract_inputs)
        self.assertEqual(caught.exception.details["usage"][0]["output_tokens"], 51)
        self.assertEqual(len(call.calls), 1)

    def test_missing_stage_is_not_unlimited_and_config_is_copied(self):
        config = caps(); del config["token_budget"]["stages"]["extract_v1"]
        model, call = self.make_model([reply()], config=config)
        self.assertFalse(model.preview("extract_v1", self.extract_inputs)["fits"])
        config["token_budget"]["stages"]["extract_v1"] = caps()["token_budget"]["stages"]["extract_v1"]
        with self.assertRaises(DomainError): model.generate("extract_v1", self.extract_inputs)
        self.assertEqual(call.calls, [])

    def test_counter_failure_or_bad_count_never_dispatches_or_silently_falls_back(self):
        for bad in (True, -1, 1.5, "200", None):
            with self.subTest(bad=bad):
                model, call = self.make_model([reply()], counter=lambda messages: bad)
                with self.assertRaises(DomainError): model.generate("extract_v1", self.extract_inputs)
                self.assertEqual(call.calls, [])
        def explode(messages): raise RuntimeError("SECRET_FROM_COUNTER")
        model, call = self.make_model([reply()], counter=explode)
        with self.assertRaises(DomainError) as caught: model.generate("extract_v1", self.extract_inputs)
        self.assertNotIn("SECRET_FROM_COUNTER", str(caught.exception.details))
        self.assertEqual(call.calls, [])

    def test_counter_failure_during_repair_preserves_the_prior_attempt_usage(self):
        def counter(messages): return 100 if len(messages) == 2 else None
        model, call = self.make_model([reply("not JSON")], counter=counter)
        with self.assertRaises(DomainError) as caught: model.generate("extract_v1", self.extract_inputs)
        self.assertEqual(caught.exception.code, "invalid_model_counter")
        self.assertEqual(len(call.calls), 1)
        self.assertEqual(len(caught.exception.details["usage"]), 1)
        self.assertEqual(caught.exception.details["usage"][0]["input_tokens"], 100)
        self.assertEqual(caught.exception.details["attempts"][0]["raw_response"]["text"], "not JSON")

    def test_token_configuration_rejects_unknown_fields_and_ambiguous_counter_identity(self):
        for changed in ("max_total_ouput_tokens", "stagez"):
            config = caps(); config["token_budget"][changed] = 10
            with self.assertRaises(DomainError): StructuredModel(FakeCall([]), limits=config)
        config = caps(); config["token_budget"]["count_kind"] = "provider_reported"
        with self.assertRaises(DomainError): StructuredModel(FakeCall([]), limits=config)
        config = caps(); del config["token_budget"]["counter_id"]
        with self.assertRaises(DomainError): StructuredModel(FakeCall([]), limits=config, token_counter=lambda m: 10)

    def test_truncated_response_spending_is_preserved_before_error(self):
        model, call = self.make_model([reply(finish="length", output_tokens=40), reply()], config=caps(total_output=75))
        with self.assertRaises(DomainError) as caught: model.generate("extract_v1", self.extract_inputs)
        self.assertEqual(caught.exception.code, "model_truncated")
        self.assertEqual(caught.exception.details["usage"][0]["budget"]["output_debit"], 40)
        with self.assertRaises(DomainError): model.generate("extract_v1", self.extract_inputs)
        self.assertEqual(len(call.calls), 1)

    def test_legacy_short_path_keeps_one_call_and_original_output_cap(self):
        call = FakeCall([reply()])
        model = StructuredModel(call, limits=limits(max_input_chars=2000000, max_total_input_chars=4000000))
        result = model.generate("extract_v1", self.extract_inputs)
        self.assertEqual(result["value"], EXAMPLES["abstain"])
        self.assertEqual(len(call.calls), 1)
        self.assertEqual(call.calls[0]["max_output_tokens"], 3000)
        self.assertNotIn("budget", result["usage"][0])


if __name__ == "__main__": unittest.main()
