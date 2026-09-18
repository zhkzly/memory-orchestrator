"""Synthetic callable/SDK responses exercise contracts; they do not measure an LLM."""
import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from memory_orchestrator.schemas import DomainError, load_contracts
from memory_orchestrator.model import StructuredModel, make_openai_call

C = json.loads((Path(__file__).parents[1] / "docs/blueprint/project-contract.json").read_text())
EXAMPLES = {x["id"]: x["value"] for x in C["examples"]}


def limits(**updates):
    value = dict(max_input_chars=50000, max_output_chars=10000, max_output_tokens=3000,
                 max_total_input_chars=150000, max_calls=6, max_format_repairs=1)
    value.update(updates)
    return value


def inputs(prompt_id="extract_v1"):
    value = {key: None for key in load_contracts()["prompts"][prompt_id]["input_fields"] if key != "output_schema"}
    if "extraction_limits" in value: value["extraction_limits"] = {"max_experiences": 3, "max_read_requests": 2, "max_evidence_expansions": 2}
    if "learning_limits" in value: value["learning_limits"] = {}
    return value


def response(value, finish="stop", usage=True):
    return {"text": value if isinstance(value, str) else json.dumps(value, ensure_ascii=False),
            "finish_reason": finish, "model": "synthetic-model",
            "usage": {"input_tokens": 11, "output_tokens": 7} if usage else None,
            "request_id": "synthetic-request"}


class FakeCall:
    def __init__(self, responses): self.responses = list(responses); self.calls = []
    def __call__(self, request):
        self.calls.append(copy.deepcopy(request))
        reply = self.responses.pop(0)
        if isinstance(reply, Exception): raise reply
        return reply


class ModelTests(unittest.TestCase):
    def test_packaged_prompts_match_source_exactly(self):
        self.assertEqual(load_contracts()["prompts"], {p["id"]: p for p in C["prompts"]})

    def test_valid_output_uses_exact_prompt_and_visible_actual_limits(self):
        call = FakeCall([response(EXAMPLES["abstain"])])
        model = StructuredModel(call, limits=limits())
        result = model.generate("extract_v1", inputs())
        self.assertEqual(result["value"], EXAMPLES["abstain"])
        self.assertEqual(call.calls[0]["messages"][0]["content"], load_contracts()["prompts"]["extract_v1"]["system"])
        self.assertNotIn("{{", str(call.calls[0]["messages"]))
        self.assertIn("max_input_chars", str(call.calls[0]["messages"]))
        self.assertEqual(result["usage"][0]["input_tokens"], 11)

    def test_format_repair_retains_original_input_rejected_output_and_usage(self):
        call = FakeCall([response({"status": "completed"}), response(EXAMPLES["abstain"])])
        result = StructuredModel(call, limits=limits()).generate("extract_v1", inputs())
        self.assertEqual(len(call.calls), 2)
        self.assertEqual(len(result["usage"]), 2)
        self.assertEqual(call.calls[1]["messages"][:2], call.calls[0]["messages"])
        self.assertIn("experiences", str(call.calls[1]["messages"][-1]))
        self.assertEqual(call.calls[1]["messages"][-2]["role"], "assistant")

    def test_no_implicit_format_retry(self):
        call = FakeCall([response("bad JSON")])
        with self.assertRaises(DomainError) as caught:
            StructuredModel(call, limits=limits(max_format_repairs=0)).generate("extract_v1", inputs())
        self.assertEqual(caught.exception.code, "invalid_output")
        self.assertEqual(len(call.calls), 1)
        self.assertEqual(len(caught.exception.details["usage"]), 1)

    def test_truncation_and_output_budget_keep_reported_usage(self):
        for reply, caps in [(response(EXAMPLES["abstain"], finish="length"), limits()),
                            (response("x" * 200), limits(max_output_chars=100))]:
            with self.subTest(reply=reply["finish_reason"]):
                call = FakeCall([reply])
                with self.assertRaises(DomainError) as caught:
                    StructuredModel(call, limits=caps).generate("extract_v1", inputs())
                self.assertEqual(len(call.calls), 1)
                self.assertEqual(caught.exception.details["usage"][0]["output_tokens"], 7)

    def test_total_call_budget_counts_repair_and_no_credential_exception_dump(self):
        call = FakeCall([response("bad JSON")])
        with self.assertRaises(DomainError) as caught:
            StructuredModel(call, limits=limits(max_calls=1)).generate("extract_v1", inputs())
        self.assertEqual(caught.exception.code, "model_budget_exhausted")
        self.assertEqual(len(caught.exception.details["usage"]), 1)
        call = FakeCall([RuntimeError("Bearer SECRET_DO_NOT_RECORD")])
        with self.assertRaises(DomainError) as caught:
            StructuredModel(call, limits=limits()).generate("extract_v1", inputs())
        self.assertNotIn("SECRET_DO_NOT_RECORD", str(caught.exception) + str(caught.exception.details))
        self.assertIsNone(caught.exception.details["usage"][0]["input_tokens"])

    def test_cumulative_budget_and_missing_fields_fail_before_network(self):
        call = FakeCall([response(EXAMPLES["abstain"])])
        model = StructuredModel(call, limits=limits())
        with self.assertRaises(DomainError): model.generate("extract_v1", {})
        self.assertEqual(call.calls, [])
        model = StructuredModel(call, limits=limits(max_total_input_chars=10))
        with self.assertRaises(DomainError) as caught: model.generate("extract_v1", inputs())
        self.assertEqual(caught.exception.code, "model_budget_exhausted")
        self.assertEqual(call.calls, [])

    def test_runtime_extraction_limit_enforced_and_not_hidden(self):
        extraction = copy.deepcopy(EXAMPLES["extraction"])
        call = FakeCall([response(extraction)])
        data = inputs(); data["extraction_limits"]["max_experiences"] = 0
        with self.assertRaises(DomainError):
            StructuredModel(call, limits=limits(max_format_repairs=0)).generate("extract_v1", data)
        self.assertIn('"max_experiences":0', call.calls[0]["messages"][1]["content"])

    def test_openai_sdk_callable_disables_retry_and_excludes_hidden_reasoning(self):
        calls = []; configured = []
        def create(**kwargs):
            calls.append(kwargs)
            return {"id": "mock-id", "model": "gpt-5.6-terra", "choices": [{"finish_reason": "stop", "message": {
                "content": json.dumps(EXAMPLES["abstain"]), "reasoning_content": "NOT_VISIBLE"}}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 2}}
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        client.with_options = lambda **kw: configured.append(kw) or client
        invoke = make_openai_call(timeout=17, client=client)
        result = invoke({"messages": [], "max_output_tokens": 321})
        self.assertEqual(configured[0]["max_retries"], 0)
        self.assertEqual(calls[0]["model"], "gpt-5.6-terra")
        self.assertEqual(calls[0]["response_format"], {"type": "json_object"})
        self.assertEqual(calls[0]["max_completion_tokens"], 321)
        self.assertEqual(calls[0]["timeout"], 17)
        self.assertNotIn("NOT_VISIBLE", str(result))
        self.assertEqual(result["usage"], {"input_tokens": 4, "output_tokens": 2, "total_tokens": None})

    def test_reported_output_token_overrun_is_not_success(self):
        reply = response(EXAMPLES["abstain"])
        reply["usage"]["output_tokens"] = 4000
        call = FakeCall([reply])
        with self.assertRaises(DomainError) as caught:
            StructuredModel(call, limits=limits(max_output_tokens=3000)).generate("extract_v1", inputs())
        self.assertEqual(caught.exception.details["usage"][0]["output_tokens"], 4000)
        self.assertEqual(len(call.calls), 1)

    def test_error_record_keeps_only_bounded_text_and_public_envelope(self):
        reply = response("x" * 300)
        reply["hidden_reasoning"] = "DO_NOT_COLLECT"
        call = FakeCall([reply])
        with self.assertRaises(DomainError) as caught:
            StructuredModel(call, limits=limits(max_output_chars=100)).generate("extract_v1", inputs())
        raw = caught.exception.details["attempts"][0]["raw_response"]
        self.assertLessEqual(len(raw["text"]), 100)
        self.assertNotIn("DO_NOT_COLLECT", str(caught.exception.details))
        self.assertTrue(caught.exception.details["attempts"][0]["raw_response_truncated"])

    def test_only_nonnegative_integer_token_counts_enter_usage(self):
        for bad in (1.5, -1, True, "5", float("nan")):
            with self.subTest(value=repr(bad)):
                reply = response(EXAMPLES["abstain"]); reply["usage"]["input_tokens"] = bad
                result = StructuredModel(FakeCall([reply]), limits=limits()).generate("extract_v1", inputs())
                self.assertIsNone(result["usage"][0]["input_tokens"])
                self.assertEqual(result["usage"][0]["output_tokens"], 7)
                self.assertTrue(result["usage"][0]["usage_diagnostics"])
                json.dumps(result, allow_nan=False)

    def test_semantic_check_shares_format_repair_and_call_budgets(self):
        bad = copy.deepcopy(EXAMPLES["diagnosis"])
        bad["targets"] = [{"skill_id": "csv-typed-transformation", "revision": "new", "rule_id": None}]
        corrected = copy.deepcopy(bad); corrected["targets"] = []
        def check(value):
            if value["targets"]:
                raise DomainError("nonexistent_target", "Empty base: ADD uses targets=[]", {
                    "errors": [{"path": "$.targets", "actual": value["targets"], "expected": []}]})
        call = FakeCall([response(bad), response(corrected)])
        result = StructuredModel(call, limits=limits()).generate("diagnose_v1", inputs("diagnose_v1"), check=check)
        self.assertEqual(result["value"]["targets"], [])
        self.assertEqual(len(result["usage"]), 2)
        self.assertEqual(result["attempts"][0]["diagnostics"]["code"], "nonexistent_target")
        self.assertIn("csv-typed-transformation", str(call.calls[1]["messages"][-1]))
        # A format error and semantic error share one repair; no third attempt.
        call = FakeCall([response("not-json"), response(bad), response(corrected)])
        with self.assertRaises(DomainError) as caught:
            StructuredModel(call, limits=limits(max_format_repairs=1)).generate("diagnose_v1", inputs("diagnose_v1"), check=check)
        self.assertEqual(caught.exception.code, "invalid_output")
        self.assertEqual(len(call.calls), 2)
        self.assertEqual(len(caught.exception.details["usage"]), 2)
        self.assertEqual(caught.exception.details["diagnostics"]["code"], "nonexistent_target")
        call = FakeCall([response(bad), response(corrected)])
        with self.assertRaises(DomainError) as caught:
            StructuredModel(call, limits=limits(max_calls=1)).generate("diagnose_v1", inputs("diagnose_v1"), check=check)
        self.assertEqual(caught.exception.code, "model_budget_exhausted")
        self.assertEqual(len(call.calls), 1)
        self.assertEqual(len(caught.exception.details["usage"]), 1)


if __name__ == "__main__": unittest.main()
