"""Thin Actor checks; public fixtures copied from GDPevo group_007/train_001.

Only prompt/template/queue input text is copied. Scripted SDK responses and the
intentionally incomplete answer test protocol behavior, not benchmark success.
"""
from copy import deepcopy
import json
import tempfile
import unittest

from examples.gdpevo_pilot.actor import make_executor
from memory_orchestrator.context import select_context
from memory_orchestrator.schemas import DomainError
from memory_orchestrator.store import Store

PUBLIC_FILES = {
  "prompt.txt": "Northwind Components operations has an expedite queue for wave TRAIN_EXPEDITE_A. Use the local queue memo in input/payloads/expedite_queue_memo.json and the shared Northwind ERP API to prepare the dispatch-control answer.\n\nShared API entry point: `<TASK_ENV_BASE_URL>`\n\nFor each order in the memo, classify the inventory status, customer exception, final fulfillment decision, next action, SKU exception lists, and shipping quote. Use the live API records for orders, products, customers, inventory, warehouses, and shipping quotes. Return only JSON matching input/payloads/answer_template.json.\n\nKeep records sorted by order_id. Currency must be rounded to two decimals.\n",
  "payloads/answer_template.json": "{\n  \"description\": \"Required JSON output shape for the TRAIN_EXPEDITE_A expedite queue decision task.\",\n  \"required_top_level_keys\": [\n    \"wave_id\",\n    \"records\",\n    \"summary\"\n  ],\n  \"fields\": {\n    \"wave_id\": {\n      \"type\": \"string\",\n      \"required_value\": \"TRAIN_EXPEDITE_A\"\n    },\n    \"records\": {\n      \"type\": \"list\",\n      \"ordering\": \"sort ascending by order_id\",\n      \"item_required_keys\": [\n        \"order_id\",\n        \"inventory_status\",\n        \"customer_exception\",\n        \"final_decision\",\n        \"next_action\",\n        \"shortage_skus\",\n        \"inactive_skus\",\n        \"low_stock_skus\",\n        \"shipping_quote\"\n      ],\n      \"item_fields\": {\n        \"order_id\": {\n          \"type\": \"string\",\n          \"source\": \"queue memo order_id\"\n        },\n        \"inventory_status\": {\n          \"type\": \"enum\",\n          \"allowed_values\": [\n            \"ready\",\n            \"low_stock\",\n            \"shortage\",\n            \"inactive_sku\",\n            \"inactive_and_shortage\"\n          ]\n        },\n        \"customer_exception\": {\n          \"type\": \"enum\",\n          \"allowed_values\": [\n            \"none\",\n            \"review_required\",\n            \"account_blocked\",\n            \"fraud_watch\",\n            \"credit_watch\"\n          ]\n        },\n        \"final_decision\": {\n          \"type\": \"enum\",\n          \"allowed_values\": [\n            \"ship_now\",\n            \"delayed_release\",\n            \"manual_review\",\n            \"backorder\",\n            \"reject_hold\"\n          ]\n        },\n        \"next_action\": {\n          \"type\": \"enum\",\n          \"allowed_values\": [\n            \"release_to_pick\",\n            \"delay_and_monitor\",\n            \"send_account_review\",\n            \"create_backorder\",\n            \"hold_credit_or_fraud\",\n            \"escalate_product_master\"\n          ]\n        },\n        \"shortage_skus\": {\n          \"type\": \"list[string]\",\n          \"ordering\": \"sort ascending by SKU\"\n        },\n        \"inactive_skus\": {\n          \"type\": \"list[string]\",\n          \"ordering\": \"sort ascending by SKU\"\n        },\n        \"low_stock_skus\": {\n          \"type\": \"list[string]\",\n          \"ordering\": \"sort ascending by SKU\"\n        },\n        \"shipping_quote\": {\n          \"type\": \"object\",\n          \"required_keys\": [\n            \"zone_distance\",\n            \"service_days\",\n            \"total_cost_usd\"\n          ],\n          \"fields\": {\n            \"zone_distance\": {\n              \"type\": \"integer\"\n            },\n            \"service_days\": {\n              \"type\": \"integer\"\n            },\n            \"total_cost_usd\": {\n              \"type\": \"number\",\n              \"precision\": \"2 decimal places\",\n              \"unit\": \"USD\"\n            }\n          }\n        }\n      }\n    },\n    \"summary\": {\n      \"type\": \"object\",\n      \"required_keys\": [\n        \"order_count\",\n        \"decision_counts\",\n        \"total_shipping_cost_usd\",\n        \"blocked_order_ids\",\n        \"manual_review_order_ids\",\n        \"backorder_order_ids\",\n        \"inactive_sku_order_ids\"\n      ],\n      \"fields\": {\n        \"order_count\": {\n          \"type\": \"integer\"\n        },\n        \"decision_counts\": {\n          \"type\": \"object\",\n          \"required_keys\": [\n            \"ship_now\",\n            \"delayed_release\",\n            \"manual_review\",\n            \"backorder\",\n            \"reject_hold\"\n          ],\n          \"value_type\": \"integer\"\n        },\n        \"total_shipping_cost_usd\": {\n          \"type\": \"number\",\n          \"precision\": \"2 decimal places\",\n          \"unit\": \"USD\"\n        },\n        \"blocked_order_ids\": {\n          \"type\": \"list[string]\",\n          \"ordering\": \"sort ascending\"\n        },\n        \"manual_review_order_ids\": {\n          \"type\": \"list[string]\",\n          \"ordering\": \"sort ascending\"\n        },\n        \"backorder_order_ids\": {\n          \"type\": \"list[string]\",\n          \"ordering\": \"sort ascending\"\n        },\n        \"inactive_sku_order_ids\": {\n          \"type\": \"list[string]\",\n          \"ordering\": \"sort ascending\"\n        }\n      }\n    }\n  }\n}\n",
  "payloads/expedite_queue_memo.json": "{\n  \"memo_id\": \"EXPEDITE-MEMO-2026-06-01-A\",\n  \"wave_id\": \"TRAIN_EXPEDITE_A\",\n  \"requester\": \"Northwind Components Dispatch Control\",\n  \"as_of_date\": \"2026-06-01\",\n  \"queue_note\": \"Expedite desk needs a release, hold, review, or backorder decision for the listed live ERP orders. Use current ERP records for account, inventory, product, and parcel quote checks.\",\n  \"order_ids\": [\n    \"SO-70000\",\n    \"SO-70007\",\n    \"SO-70014\",\n    \"SO-70028\",\n    \"SO-70035\",\n    \"SO-70049\",\n    \"SO-70070\",\n    \"SO-70077\"\n  ],\n  \"operator_notes\": [\n    {\n      \"order_id\": \"SO-70000\",\n      \"note\": \"Strategic customer asked whether any line can be expedited today.\"\n    },\n    {\n      \"order_id\": \"SO-70007\",\n      \"note\": \"Single-line order; dispatch wants account clearance confirmed before pick release.\"\n    },\n    {\n      \"order_id\": \"SO-70014\",\n      \"note\": \"Multiple maintenance items requested from WH_NORTH.\"\n    },\n    {\n      \"order_id\": \"SO-70028\",\n      \"note\": \"Customer has asked for a same-week exception despite account flags.\"\n    },\n    {\n      \"order_id\": \"SO-70035\",\n      \"note\": \"Desk flagged product-master risk on one line and needs the account disposition too.\"\n    },\n    {\n      \"order_id\": \"SO-70049\",\n      \"note\": \"Overnight shipment quote is needed even if the queue decision is not release.\"\n    },\n    {\n      \"order_id\": \"SO-70070\",\n      \"note\": \"High-priority request from WH_NORTH.\"\n    },\n    {\n      \"order_id\": \"SO-70077\",\n      \"note\": \"Critical order from WH_CENTRAL; quote using the order's requested shipping speed.\"\n    }\n  ]\n}\n"
}

def limits(**changes):
    result = {"max_model_calls": 6, "max_input_chars": 100000,
              "max_tool_output_chars": 20000, "max_completion_tokens": 8192, "max_tool_calls": 128,
              "context_policy": {"max_roots": 3, "max_context_chars": 16000, "relation_weight": 0.0}}
    result.update(changes)
    return result


def call(name, args, identifier):
    return {"id": identifier, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def reply(calls=(), *, content=None, finish="tool_calls"):
    return {"id": "chatcmpl-fixture", "model": "scripted-envelope", "call_ref": "physical-call-fixture",
            "elapsed_seconds": 0.01, "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            "choices": [{"index": 0, "finish_reason": finish,
                         "message": {"role": "assistant", "content": content, "tool_calls": list(calls)}}]}


class Dataset:
    business_docs = "GET /orders/<order_id>; GET /inventory?warehouse_id=&sku=; GET /shipping/quote?warehouse_id=&destination_zip=&weight_lb=&speed=. Only business GET endpoints."
    def __init__(self): self.reads = []; self.gets = []
    def public_files(self, task_id):
        if task_id != "train_001": raise AssertionError(task_id)
        return {name: len(text.encode()) for name, text in PUBLIC_FILES.items()}
    def read_input(self, task_id, path):
        self.reads.append((task_id, path))
        return PUBLIC_FILES[path]
    def business_get(self, path, query):
        self.gets.append((path, deepcopy(query)))
        return {"path": path, "query": query, "fixture": "business response only"}


class Invoke:
    def __init__(self, replies): self.replies = list(replies); self.calls = []
    def __call__(self, payload, *, stage, subject):
        self.calls.append({"payload": deepcopy(payload), "stage": stage, "subject": subject})
        result = self.replies.pop(0)
        if isinstance(result, BaseException): raise result
        return result


class ActorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name); active = self.store.ensure_project("pilot")
        self.snapshot = self.store.snapshot(active["snapshot_id"])
        self.task = {"project_id": "pilot", "task_id": "train_001", "revision": "public-fixture",
                     "description": PUBLIC_FILES["prompt.txt"], "task_family": "northwind_erp"}
        self.dataset = Dataset()
        self.request = {"request_id": "run-public-1", "case_id": "train_001", "task_revision": "public-fixture",
                        "snapshot_digest": self.snapshot["snapshot_id"], "purpose": "learning"}
        template = json.loads(PUBLIC_FILES["payloads/answer_template.json"])
        self.answer = {key: (template["fields"]["wave_id"]["required_value"] if key == "wave_id"
                             else [] if key == "records" else {}) for key in template["required_top_level_keys"]}

    def execute(self, invoke, **changes):
        return make_executor(self.store, self.dataset, invoke, limits=limits(**changes))(
            self.request, self.snapshot, {"task": self.task})

    def test_real_public_prompt_and_parallel_tool_pairs_reach_the_next_sdk_call(self):
        first = reply([call("read_input", {"path": "input/payloads/answer_template.json"}, "schema"),
                       call("read_input", {"path": "payloads/expedite_queue_memo.json"}, "memo"),
                       call("business_get", {"path": "/orders/SO-70000", "query": {}}, "order")])
        invoke = Invoke([first, reply([call("submit_answer", {"answer": self.answer}, "submit")])])
        result = self.execute(invoke)
        self.assertEqual(result["execution_status"], "completed")
        self.assertEqual(result["artifact"], self.answer)
        initial = invoke.calls[0]["payload"]
        self.assertIn(PUBLIC_FILES["prompt.txt"], initial["messages"][1]["content"])
        self.assertIn("payloads/answer_template.json", str(initial))
        self.assertIn(self.dataset.business_docs, str(initial))
        messages = invoke.calls[1]["payload"]["messages"]
        outputs = [m for m in messages if m["role"] == "tool"]
        self.assertEqual({m["tool_call_id"] for m in outputs}, {"schema", "memo", "order"})
        self.assertTrue(all(isinstance(json.loads(m["content"]), dict) for m in outputs))
        self.assertEqual(len([e for e in result["events"] if e["kind"] == "action"]), 4)
        self.assertEqual(len([e for e in result["events"] if e["kind"] == "result"]), 4)
        self.assertEqual(result["usage"]["tokens"]["input_tokens"], 22)
        self.assertEqual(result["usage"]["tokens"]["output_tokens"], 14)
        self.assertEqual([c["subject"] for c in invoke.calls], ["run-public-1", "run-public-1"])
        self.assertTrue(all(c["stage"] == "execute" for c in invoke.calls))
        self.assertEqual(len(result["actor_calls"]), 2)
        self.assertEqual(result["consumption_events"], [])

    def test_gold_unknown_tool_and_judge_are_rejected_without_dispatch(self):
        invoke = Invoke([reply([
            call("read_input", {"path": "../eval/gold.json"}, "gold"),
            call("business_get", {"path": "/api/judge", "query": {}}, "judge"),
            call("python", {"code": "print(1)"}, "python")]),
            reply([call("submit_answer", {"answer": self.answer}, "submit")])])
        result = self.execute(invoke)
        self.assertEqual(result["execution_status"], "completed")
        self.assertEqual(self.dataset.reads, [])
        self.assertEqual(self.dataset.gets, [])
        errors = [json.loads(m["content"]) for m in invoke.calls[1]["payload"]["messages"] if m["role"] == "tool"]
        self.assertTrue(all(row["status"] == "error" for row in errors))
        self.assertEqual({row["error"]["code"] for row in errors}, {"input_not_public", "business_endpoint", "unknown_tool"})

    def test_normal_stop_preserves_non_json_without_host_repair(self):
        text = 'Here is the answer: ```json\n{"wave_id": "wrong"}\n```'
        result = self.execute(Invoke([reply(content=text, finish="stop")]))
        self.assertEqual(result["execution_status"], "completed")
        self.assertEqual(result["artifact"], text)
        self.assertTrue(result["gaps"])

    def test_call_budget_and_global_budget_do_not_fabricate_success(self):
        invoke = Invoke([])
        result = self.execute(invoke, max_model_calls=0)
        self.assertEqual(result["execution_status"], "budget_exhausted")
        self.assertNotIn("artifact", result)
        self.assertEqual(invoke.calls, [])
        denied = self.execute(Invoke([DomainError("pilot_budget", "Global limit reached")]))
        self.assertEqual(denied["execution_status"], "budget_exhausted")
        self.assertNotIn("artifact", denied)
        self.assertIsNone(denied["usage"]["tokens"]["input_tokens"])

    def test_oversized_tool_json_is_rejected_whole_not_silently_cut(self):
        self.dataset.business_get = lambda *args: {"large": "x" * 10000}
        invoke = Invoke([reply([call("business_get", {"path": "/products", "query": {}}, "large")]),
                         reply(content="Insufficient visible data", finish="stop")])
        result = self.execute(invoke, max_tool_output_chars=500)
        tool = next(m for m in invoke.calls[1]["payload"]["messages"] if m["role"] == "tool")
        parsed = json.loads(tool["content"])
        self.assertEqual(parsed["error"]["code"], "tool_output_budget")
        self.assertNotIn("large", parsed.get("data", {}))
        self.assertLessEqual(len(tool["content"]), 500)
        self.assertEqual(result["artifact"], "Insufficient visible data")

    def test_timeout_length_and_malformed_sdk_envelope_keep_terminal_state(self):
        for returned, expected in [(TimeoutError("local fixture"), "timeout"),
                                   (reply(content='{"partial":', finish="length"), "budget_exhausted"),
                                   ({"choices": []}, "adapter_error")]:
            with self.subTest(expected=expected):
                result = self.execute(Invoke([returned]))
                self.assertEqual(result["execution_status"], expected)
                if expected == "budget_exhausted": self.assertEqual(result["artifact"], '{"partial":')

    def test_malformed_list_tool_id_keeps_partial_trace_without_dispatch(self):
        malformed = reply([call("business_get", {"path": "/orders/SO-70000", "query": {}}, "unused")],
                          content="Visible partial plan")
        malformed["choices"][0]["message"]["tool_calls"][0]["id"] = ["not-a-string-id"]
        result = self.execute(Invoke([malformed]))
        self.assertEqual(result["execution_status"], "adapter_error")
        self.assertEqual(self.dataset.gets, [])
        self.assertEqual(len(result["actor_calls"]), 1)
        self.assertIn("Visible partial plan", [row["text"] for row in result["events"]])

    def test_final_context_is_pinned_and_cross_version_manifest_is_rejected(self):
        self.request["purpose"] = "final"
        manifest = select_context(self.store, self.task, limits()["context_policy"],
                                  explicit_snapshot=self.snapshot["snapshot_id"], purpose="final")
        self.request["context_manifest"] = manifest
        before = len(self.store.list("contexts"))
        invoke = Invoke([reply(content="raw answer", finish="stop")])
        result = self.execute(invoke)
        self.assertEqual(result["context_manifest_ref"], manifest["manifest_id"])
        self.assertEqual(len(self.store.list("contexts")), before)
        wrong = deepcopy(manifest); wrong["snapshot_digest"] = "foreign"
        self.request["context_manifest"] = wrong
        with self.assertRaises(DomainError): self.execute(Invoke([]))

    def test_only_an_actual_selected_asset_read_records_consumption(self):
        from test_memory_context import skill
        selected, excluded = skill("erp"), skill("unrelated")
        for row in (selected, excluded): row["project_id"] = "pilot"
        selected["content"]["scope"]["task_family"] = "northwind_erp"
        selected["content"]["triggers"] = ["Northwind", "ERP"]
        excluded["content"]["scope"]["task_family"] = "astronomy"
        excluded["content"]["triggers"] = ["astronomy"]
        selected["asset_refs"] = ["erp/references/ordering.txt"]
        excluded["asset_refs"] = ["unrelated/references/private.txt"]
        self.snapshot = self.store.save_snapshot("pilot", {"erp": selected, "unrelated": excluded},
            {selected["asset_refs"][0]: "BODY_ONLY_ON_READ: inspect public inventory fields",
             excluded["asset_refs"][0]: "UNSELECTED_BODY"})
        self.request["snapshot_digest"] = self.snapshot["snapshot_id"]
        invoke = Invoke([reply([call("load_skill_asset", {"path": selected["asset_refs"][0]}, "read-selected"),
                                call("load_skill_asset", {"path": excluded["asset_refs"][0]}, "read-excluded")]),
                         reply([call("submit_answer", {"answer": self.answer}, "submit")])])
        result = self.execute(invoke)
        self.assertNotIn("BODY_ONLY_ON_READ", str(invoke.calls[0]["payload"]))
        self.assertIn("BODY_ONLY_ON_READ", str(invoke.calls[1]["payload"]))
        self.assertNotIn("UNSELECTED_BODY", str(invoke.calls))
        self.assertEqual(len(result["consumption_events"]), 1)
        consumed = result["consumption_events"][0]
        self.assertEqual((consumed["skill_id"], consumed["level"]), ("erp", "read"))
        witness = next(e for e in result["events"] if e["event_id"] == consumed["event_id"])
        self.assertEqual(witness["source_role"], "tool")
        self.assertIn("BODY_ONLY_ON_READ", witness["text"])

    def test_sixty_gets_in_one_sdk_reply_are_allowed_and_paired(self):
        many = [call("business_get", {"path": "/orders/SO-70000", "query": {}}, "get-" + str(i)) for i in range(60)]
        invoke = Invoke([reply(many), reply([call("submit_answer", {"answer": self.answer}, "submit")])])
        result = self.execute(invoke)
        self.assertEqual(result["execution_status"], "completed")
        self.assertEqual(len(self.dataset.gets), 60)
        messages = [m for m in invoke.calls[1]["payload"]["messages"] if m["role"] == "tool"]
        self.assertEqual({m["tool_call_id"] for m in messages}, {"get-" + str(i) for i in range(60)})

    def test_tool_batch_over_budget_executes_none_and_keeps_attempts(self):
        many = [call("business_get", {"path": "/health", "query": {}}, "get-" + str(i)) for i in range(129)]
        result = self.execute(Invoke([reply(many)]))
        self.assertEqual(result["execution_status"], "budget_exhausted")
        self.assertEqual(self.dataset.gets, [])
        self.assertEqual(len([e for e in result["events"] if e["kind"] == "result"]), 129)
        self.assertNotIn("artifact", result)

    def test_complete_payload_budget_blocks_dispatch_without_removing_context(self):
        invoke = Invoke([])
        result = self.execute(invoke, max_input_chars=400)
        self.assertEqual(result["execution_status"], "budget_exhausted")
        self.assertEqual(invoke.calls, [])
        self.assertEqual(result["actor_calls"], [])

    def test_recorded_six_round_pattern_discloses_remaining_budget_without_inventing_answer(self):
        # Derived from actual continued call_0005..0010 payloads for train_001:
        # input chars 4592,13466,18984,30935,40307,45236; prior tool results
        # 0,3,11,38,59,67. Its last SDK reply still requested two business GETs.
        # The captured original first-two-message hash was unchanged all rounds:
        # 1ba8112222eb128c2c9ec7740238e8d89f5d4cf1a4ef2aa60eba5865cf50c2f6.
        counts = [3, 8, 27, 21, 8, 2]
        replies = [reply([call("business_get", {"path": "/orders/SO-70000", "query": {}},
                                    f"recorded-{turn}-{index}") for index in range(count)])
                   for turn, count in enumerate(counts)]
        invoke = Invoke(replies)
        result = self.execute(invoke)
        self.assertEqual(len(invoke.calls), 6)
        self.assertEqual(result["execution_status"], "budget_exhausted")
        self.assertNotIn("artifact", result)  # A budget reminder cannot synthesize an answer.
        for turn, used in enumerate((0, 3, 11, 38, 59, 67)):
            messages = invoke.calls[turn]["payload"]["messages"]
            host = [m for m in messages if m["role"] == "system"
                    and m["content"].startswith("HOST_EXECUTION_STATE\n")]
            self.assertEqual(len(host), 1, "One current host state must be visible; stale states must not accumulate")
            state = json.loads(host[0]["content"].split("\n", 1)[1])
            self.assertEqual(state["model_call_number"], turn + 1)
            self.assertEqual(state["model_calls_remaining_after_this"], 5 - turn)
            self.assertEqual(state["tool_calls_used"], used)
            self.assertEqual(state["tool_calls_remaining"], 128 - used)
            self.assertEqual(state["final_model_call"], turn == 5)
            if turn == 5:
                self.assertIn("no further model call", host[0]["content"].lower())
                self.assertIn("do not invent", host[0]["content"].lower())
            self.assertEqual(sum(m["content"].startswith("PUBLIC TASK") for m in messages if isinstance(m.get("content"), str)), 1)

    def test_recorded_five_round_submission_keeps_one_unused_model_call_visible(self):
        # Original train_001 call_0001..0005 used batches 3,8,27,28,submit(1),
        # and submitted with one model call left. This is Actor control evidence,
        # not a replay of its business answer or a memory-improvement claim.
        replies = [reply([call("business_get", {"path": "/orders/SO-70000", "query": {}},
                                   f"original-{turn}-{index}") for index in range(count)])
                   for turn, count in enumerate((3, 8, 27, 28))]
        replies.append(reply([call("submit_answer", {"answer": self.answer}, "submit")]))
        invoke = Invoke(replies)
        result = self.execute(invoke)
        self.assertEqual(result["artifact"], self.answer)
        self.assertEqual(len(invoke.calls), 5)
        host = [m for m in invoke.calls[-1]["payload"]["messages"] if m["role"] == "system"
                and m["content"].startswith("HOST_EXECUTION_STATE\n")]
        self.assertEqual(len(host), 1)
        state = json.loads(host[0]["content"].split("\n", 1)[1])
        self.assertEqual((state["model_call_number"], state["model_calls_remaining_after_this"]), (5, 1))
        self.assertEqual((state["tool_calls_used"], state["tool_calls_remaining"]), (66, 62))
        self.assertFalse(state["final_model_call"])

    def test_dynamic_host_state_is_included_in_the_complete_input_budget(self):
        observed = Invoke([reply(content="Unmodified answer", finish="stop")])
        self.execute(observed)
        complete = observed.calls[0]["payload"]
        without_state = deepcopy(complete)
        without_state["messages"] = [m for m in without_state["messages"]
            if not (m["role"] == "system" and m["content"].startswith("HOST_EXECUTION_STATE\n"))]
        def size(value): return len(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        self.assertGreater(size(complete), size(without_state))
        # Between the exact payload sizes, allowing for the shorter visible cap digits.
        cap = (size(complete) + size(without_state)) // 2
        denied = Invoke([])
        result = self.execute(denied, max_input_chars=cap)
        self.assertEqual(result["execution_status"], "budget_exhausted")
        self.assertEqual(denied.calls, [])


if __name__ == "__main__": unittest.main()
