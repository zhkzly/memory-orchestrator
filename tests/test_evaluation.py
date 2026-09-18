"""Constructed callback checks against real local Store, not Agent effect evidence."""

from __future__ import annotations

import copy
import threading
import time
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from memory_orchestrator.common import DomainError, digest
from memory_orchestrator.evaluation import validate_candidate
from memory_orchestrator.store import Store


def skill_patch(slug="csv-schema"):
    """ADD derived from the blueprint's CSV PATCH behavior and PatchDraft schema."""
    return {
        "operations": [{
            "op": "ADD", "proposed_slug": slug,
            "content": {
                "title": "Preserve CSV identifiers", "scope": {
                    "task_family": "csv", "applies_when": ["CSV identifiers"],
                    "exclusions": [],
                },
                "triggers": ["CSV"], "preconditions": [],
                "steps": ["Use the target schema to preserve text identifiers."],
                "exceptions": [], "checks": ["Check identifiers and numeric sums."],
                "depends_on": [], "declared_conflicts": [],
                "evidence_refs": ["constructed:csv-leading-zero"],
            },
        }],
        "asset_edits": [], "reason": "Derived CSV example for callback tests.",
        "evidence_refs": ["constructed:csv-leading-zero"],
        "expected_behavior": "Preserve identifiers and numeric operations.",
        "check_plan": [{"purpose": "target", "behavior": "Preserve zero prefix.",
                        "required_evidence": "Caller supplied test output."}],
    }


def cases():
    return [
        {"id": "identifier", "split": "target", "data": {"base": 0.0, "candidate": 1.0}},
        {"id": "sum", "split": "regression", "data": {"base": 1.0, "candidate": 1.0}},
    ]


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.project = "constructed-csv"
        self.store.ensure_project(self.project)
        self.base = self.store.active(self.project)
        self.candidate = self.store.create_candidate(
            self.project, self.base["snapshot_id"], skill_patch()
        )

    def evaluate(self, callback=None, **kwargs):
        return validate_candidate(
            self.store, self.project, self.candidate["id"], kwargs.pop("cases", cases()),
            callback or self.score, "constructed-score/v1", **kwargs,
        )

    def score(self, snapshot, case):
        role = "base" if snapshot["snapshot_id"] == self.base["snapshot_id"] else "candidate"
        value = case["data"][role]
        return {"outcome": "pass" if value > 0 else "fail", "score": value,
                "evidence_refs": ["caller-result:" + case["id"]],
                "usage": {"input_tokens": 3, "output_tokens": 2, "cost": 0.25}}

    def test_plan_frozen_before_callbacks_and_all_repeats_persisted(self):
        observed_plans = []

        def evaluate(snapshot, case):
            plans = self.store.list("validation_plans", project=self.project)
            self.assertEqual(len(plans), 1)
            self.assertEqual(len(plans[0]["slots"]), 12)
            observed_plans.append(plans[0])
            return self.score(snapshot, case)

        result = self.evaluate(evaluate, repeats=3, max_parallel=2)
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(len(observed_plans), 12)
        plan = self.store.get("validation_plans", result["plan_id"])
        self.assertEqual(plan["cases"], cases())
        self.assertEqual(plan["cases_hash"], digest(cases()))
        self.assertEqual(plan["evaluator_id"], "constructed-score/v1")
        self.assertEqual(plan["expected_generation"], self.base["generation"])
        self.assertEqual(plan["policy"], result["policy"])
        self.assertEqual(plan["validation_id"], result["id"])
        self.assertEqual({s["slot_id"] for s in plan["slots"]},
                         {s["slot_id"] for s in result["results"]})
        self.assertEqual(result["metrics"]["case_count"], 2)
        self.assertEqual(result["metrics"]["planned_calls"], 12)
        self.assertEqual(result["metrics"]["completed_calls"], 12)
        self.assertEqual(self.store.get("validations", result["id"]), result)
        self.assertEqual(self.store.active(self.project), self.base)
        self.assertTrue(all(row["source"] == "caller_evaluator" for row in result["results"]))

    def test_transfer_at_ceiling_does_not_require_strict_improvement(self):
        inputs = cases() + [{"id": "alternate-id", "split": "transfer",
                            "data": {"base": 1.0, "candidate": 1.0}}]
        result = self.evaluate(cases=inputs, repeats=2)
        self.assertEqual(result["status"], "accepted")

    def test_regression_is_checked_per_case_not_hidden_by_average(self):
        inputs = cases() + [{"id": "average", "split": "regression",
                            "data": {"base": 0.0, "candidate": 1.0}}]
        inputs[1]["data"] = {"base": 1.0, "candidate": 0.0}
        result = self.evaluate(cases=inputs, repeats=2)
        self.assertEqual(result["status"], "rejected")
        gate = next(g for g in result["gates"] if g["name"] == "regression_non_decrease")
        self.assertFalse(gate["passed"])

    def test_target_needs_gain_and_absent_transfer_is_not_applicable(self):
        inputs = cases()
        inputs[0]["data"]["base"] = 1.0
        result = self.evaluate(cases=inputs)
        self.assertEqual(result["status"], "rejected")
        transfer = next(g for g in result["gates"] if g["name"] == "transfer_non_decrease")
        self.assertTrue(transfer["passed"])
        self.assertEqual(transfer["reason"], "not_applicable")

    def test_invalid_callback_scores_and_null_are_unknown(self):
        for invalid in [None, float("nan"), float("inf"), True, "1"]:
            with self.subTest(score=invalid):
                def callback(snapshot, case):
                    feedback = self.score(snapshot, case)
                    if snapshot["snapshot_id"] != self.base["snapshot_id"]:
                        feedback["score"] = invalid
                    return feedback

                result = self.evaluate(callback)
                self.assertEqual(result["status"], "unknown")
                self.assertEqual(len(result["results"]), 4)
                unknowns = [r for r in result["results"] if r["outcome"] == "unknown"]
                self.assertEqual(len(unknowns), 2)
                self.assertTrue(all(r["score"] is None for r in unknowns))
                self.assertTrue(all(r["usage"]["cost"] == 0.25 for r in unknowns))

    def test_callback_exception_preserves_error_and_full_denominator(self):
        def callback(snapshot, case):
            if snapshot["snapshot_id"] == self.candidate["snapshot_id"]:
                raise DomainError("upstream_failure", "rubric unavailable", {"code": 503})
            return self.score(snapshot, case)

        result = self.evaluate(callback, repeats=2, max_parallel=2)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(len(result["results"]), 8)
        failures = [r for r in result["results"] if r["error"]]
        self.assertEqual(len(failures), 4)
        self.assertEqual(failures[0]["error"]["cause_code"], "upstream_failure")
        self.assertEqual(failures[0]["error"]["details"], {"code": 503})
        self.assertIsNone(failures[0]["usage"])

    def test_usage_retained_once_and_unknown_not_zero(self):
        def callback(snapshot, case):
            feedback = self.score(snapshot, case)
            if case["id"] == "sum":
                feedback.pop("usage")
            return feedback

        result = self.evaluate(callback, repeats=2)
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(len(result["usage"]), 8)
        self.assertEqual(len({r["slot_id"] for r in result["usage"]}), 8)
        self.assertEqual(sum(r["usage"]["cost"] for r in result["usage"] if r["usage"]), 1.0)
        self.assertEqual(sum(r["usage"] is None for r in result["usage"]), 4)
        self.assertEqual(result["metrics"]["missing_usage_calls"], 4)

    def test_callback_cannot_mutate_evaluated_inputs(self):
        inputs = cases()
        original = copy.deepcopy(inputs)
        snapshot_before = self.store.snapshot(self.candidate["snapshot_id"])

        def callback(snapshot, case):
            feedback = self.score(snapshot, case)
            snapshot["assets"]["injected"] = "change what is supposedly evaluated"
            case["data"]["candidate"] = 100
            return feedback

        result = self.evaluate(callback, cases=inputs, repeats=2, max_parallel=2)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(inputs, original)
        self.assertEqual(self.store.snapshot(self.candidate["snapshot_id"]), snapshot_before)
        self.assertTrue(all(r["error"]["code"] == "callback_mutated_input" for r in result["results"]))

    def test_callback_mutating_original_cases_does_not_change_frozen_plan(self):
        inputs = cases()

        def callback(snapshot, case):
            inputs[0]["data"]["base"] = 100
            return self.score(snapshot, case)

        result = self.evaluate(callback, cases=inputs)
        self.assertEqual(result["status"], "accepted")
        plan = self.store.get("validation_plans", result["plan_id"])
        self.assertEqual(plan["cases"], cases())

    def test_invalid_inputs_budget_and_unsupported_policy_fail_before_calls(self):
        called = []

        def callback(snapshot, case):
            called.append(1)
            return self.score(snapshot, case)

        for kwargs in [
            {"repeats": 0}, {"repeats": True}, {"max_parallel": 0},
            {"policy": {"max_calls": 3}}, {"policy": {"max_calls": False}},
            {"policy": {"future_plugin": "none"}}, {"policy": {"min_gain": float("nan")}},
            {"policy": {"max_regression": -1}}, {"cases": cases()[:1]},
            {"cases": [cases()[0], cases()[0]]},
        ]:
            with self.subTest(kwargs=kwargs), self.assertRaises(DomainError):
                self.evaluate(callback, **kwargs)
        self.assertEqual(called, [])
        self.assertEqual(self.store.list("validation_plans", project=self.project), [])

    def test_wrong_project_rejects_without_calls(self):
        self.store.ensure_project("another-project")
        called = []
        with self.assertRaises(DomainError):
            validate_candidate(self.store, "another-project", self.candidate["id"], cases(),
                               lambda *args: called.append(1), "constructed/v1")
        self.assertEqual(called, [])

    def test_callback_parallelism_is_bounded(self):
        lock = threading.Lock()
        concurrent = 0
        peak = 0

        def callback(snapshot, case):
            nonlocal concurrent, peak
            with lock:
                concurrent += 1
                peak = max(peak, concurrent)
            time.sleep(0.01)
            with lock:
                concurrent -= 1
            return self.score(snapshot, case)

        result = self.evaluate(callback, repeats=3, max_parallel=2)
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(peak, 2)

    def test_stale_base_rejects_before_callbacks(self):
        validation = self.evaluate()
        self.store.publish(validation["id"], self.base["generation"])
        with self.assertRaises(DomainError):
            self.evaluate(lambda *_: self.fail("stale candidate executed"))

    def test_generation_changes_during_validation_prevent_acceptance(self):
        prepared = self.evaluate()
        changed = False

        def callback(snapshot, case):
            nonlocal changed
            if not changed:
                changed = True
                self.store.publish(prepared["id"], self.base["generation"])
            return self.score(snapshot, case)

        result = self.evaluate(callback)
        self.assertEqual(result["status"], "rejected")
        self.assertFalse(next(g for g in result["gates"] if g["name"] == "versions_unchanged")["passed"])

    def test_missing_scheduled_results_are_retained_as_unknown(self):
        # A scheduler failure is separate from a caller's evaluator failure.
        with patch("memory_orchestrator.evaluation.ThreadPoolExecutor", side_effect=RuntimeError("pool unavailable")):
            result = self.evaluate(max_parallel=2)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(len(result["results"]), 4)
        self.assertTrue(all(r["outcome"] == "unknown" for r in result["results"]))
        self.assertEqual(result["metrics"]["completed_calls"], 0)


if __name__ == "__main__":
    unittest.main()
