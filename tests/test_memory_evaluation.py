"""Constructed local CSV tasks; these checks are not benchmark effect evidence."""
from __future__ import annotations

import copy
import csv
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory_orchestrator.schemas import DomainError, new_id
from memory_orchestrator.store import Store
from memory_orchestrator.evaluation import compare_candidates


def protocol():
    return {
        "id": "csv-local/v1", "comparison_scope": "local repair", "repeat_count": 2,
        "required_gates": ["complete_results", "target_gain", "regression_non_decrease",
                           "call_budget", "scope_bound", "versions_unchanged"],
        "criteria": {"target_mean_gain_must_exceed": 0.0, "maximum_per_case_regression": 0.0,
                     "maximum_evaluation_calls": 64, "transfer_claim": False},
        "selection_rule": {"id": "quality-cost-id/v1", "order": [
            "accepted quality gain descending", "evaluation cost ascending",
            "candidate digest ascending"], "missing_cost": "last"},
        "executor": {"id": "csv-executor/v1", "config": {}},
        "evaluator": {"id": "csv-check/v1", "config": {}}, "allowed_sources": ["executable"],
    }


def case_set():
    return {"id": "csv-cases", "version": "constructed-v1", "cases": [
        {"id": "identifiers", "split": "target", "task": {"csv": "code,amount\n0012,3\n0007,4\n"},
         "criteria": {"codes": ["0012", "0007"], "sum": 7}},
        {"id": "sum", "split": "regression", "task": {"csv": "code,amount\n12,3\n7,4\n"},
         "criteria": {"sum": 7}},
    ]}


def execute_csv(request, snapshot, case):
    assert "criteria" not in case, "Private criteria leaked into execution."
    # Real local file IO and CSV conversion; the constructed executor interprets
    # the provided Skill as the switch for the behavior under test.
    with tempfile.TemporaryDirectory() as root:
        source = Path(root) / "input.csv"
        source.write_text(case["task"]["csv"], encoding="utf-8")
        with source.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        preserve = any("preserve" in step.lower() for skill in snapshot["skills"].values()
                       for step in skill["content"]["steps"])
        if not preserve:
            for row in rows:
                row["code"] = str(int(row["code"]))
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=["code", "amount"])
        writer.writeheader()
        writer.writerows(rows)
        artifact = {"csv": output.getvalue()}
    return {"artifact": artifact, "observations": ["CSV conversion completed"],
            "usage": {"monetary_cost": 0.01, "currency": "test-unit", "tokens": None}}


def evaluate_csv(request, execution, case):
    rows = list(csv.DictReader(io.StringIO(execution["artifact"]["csv"])))
    criteria = case["criteria"]
    checks = [sum(int(row["amount"]) for row in rows) == criteria["sum"]]
    if "codes" in criteria:
        checks.append([row["code"] for row in rows] == criteria["codes"])
    passed = all(checks)
    return {"outcome": "pass" if passed else "fail", "score": int(passed),
            "source": "executable", "evidence": [{"checks": checks, "rows": rows}],
            "usage": {"monetary_cost": 0.02, "currency": "test-unit", "tokens": None}}


class MemoryFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.project = "csv-project"
        self.active = self.store.ensure_project(self.project)
        self.candidate = self.make_candidate()

    def make_candidate(self, suffix="one", preserve=True, extra_steps=()):
        content = {"title": "CSV schema " + suffix, "scope": {
            "task_family": "csv", "applies_when": ["CSV conversion"], "exclusions": []},
            "triggers": ["csv"], "preconditions": [],
            "steps": ["Preserve text identifiers." if preserve else "Infer all fields.", *extra_steps],
            "exceptions": [], "checks": ["Check identifiers and sums."], "depends_on": [],
            "declared_conflicts": [], "evidence_refs": ["constructed:csv"]}
        sid = "csv-" + suffix
        snapshot = self.store.save_snapshot(self.project, {sid: {
            "skill_id": sid, "revision": "r1", "project_id": self.project,
            "content": content, "asset_refs": []}}, {}, parent=self.active["snapshot_id"])
        proposal = {"proposal_id": new_id("proposal"), "project_id": self.project,
                    "base_digest": self.active["snapshot_id"],
                    "candidate_digest": snapshot["snapshot_id"],
                    "expected_generation": self.active["generation"]}
        self.store.put("candidates", proposal["proposal_id"], proposal)
        return proposal

    def compare(self, **kwargs):
        return compare_candidates(self.store, self.project, kwargs.pop("candidates", [self.candidate]),
                                  kwargs.pop("case_set", case_set()), kwargs.pop("protocol", protocol()),
                                  kwargs.pop("execute_fn", execute_csv),
                                  kwargs.pop("evaluate_fn", evaluate_csv),
                                  max_parallel=kwargs.pop("max_parallel", 1), **kwargs)

    def validation(self, result, index=0):
        return self.store.get("validations", result["validation_ids"][index])


class MemoryEvaluationTests(MemoryFixture, unittest.TestCase):

    def test_complete_plan_precedes_real_callbacks_and_preserves_raw(self):
        def execute(request, snapshot, case):
            plans = self.store.list("evaluation_plans", project_id=self.project)
            self.assertEqual(len(plans), 1)
            self.assertEqual(len(plans[0]["requests"]), 8)
            return execute_csv(request, snapshot, case)
        result = self.compare(execute_fn=execute, max_parallel=2)
        val = self.validation(result)
        self.assertEqual(val["status"], "accepted")
        self.assertEqual(len(val["results"]), 8)
        self.assertEqual(len(self.store.list("evaluation_returns", project_id=self.project)), 16)
        self.assertEqual(self.store.active(self.project), self.active)
        selection = self.store.get("selections", result["selection_id"])
        self.assertEqual(selection["selected_candidate_digest"], self.candidate["candidate_digest"])

    def test_exception_invalid_score_and_wrong_identity_keep_all_requests(self):
        for defect in ["exception", "nan", "boolean", "wrong_id", "no_evidence"]:
            with self.subTest(defect=defect):
                def evaluator(request, execution, case):
                    out = evaluate_csv(request, execution, case)
                    if request["arm"] == "candidate":
                        if defect == "exception": raise RuntimeError("checker unavailable")
                        if defect == "nan": out["score"] = float("nan")
                        if defect == "boolean": out["score"] = True
                        if defect == "wrong_id": out["request_id"] = "another-request"
                        if defect == "no_evidence": out["evidence"] = []
                    return out
                val = self.validation(self.compare(evaluate_fn=evaluator))
                self.assertEqual(val["status"], "unknown")
                self.assertEqual(len(val["results"]), 8)
                self.assertEqual(sum(x["outcome"] == "unknown" for x in val["results"]), 4)

    def test_parameters_and_budget_fail_before_any_call(self):
        for mutate in [lambda p:p.pop("repeat_count"), lambda p:p["criteria"].update(maximum_evaluation_calls=7),
                       lambda p:p["required_gates"].remove("complete_results"),
                       lambda p:p["required_gates"].append("future_gate"), lambda p:p.update(unused_extension=True)]:
            p = protocol(); mutate(p)
            with self.assertRaises(DomainError):
                self.compare(protocol=p, execute_fn=lambda *_: self.fail("should not execute"))

    def test_callback_mutation_cannot_change_snapshots_or_evaluation_subject(self):
        before = self.store.snapshot(self.candidate["candidate_digest"])
        def execute(request, snapshot, case):
            out = execute_csv(request, snapshot, case)
            snapshot["assets"]["unvalidated"] = "mutated"
            return out
        val = self.validation(self.compare(execute_fn=execute))
        self.assertEqual(val["status"], "unknown")
        self.assertEqual(self.store.snapshot(self.candidate["candidate_digest"]), before)

    def test_each_regression_case_protected_even_when_mean_hides_loss(self):
        cs = case_set()
        cs["cases"].append({"id":"extra", "split":"regression", "task":{}, "criteria":{}})
        def execute(*_): return {"artifact": {}}
        def evaluate(request, execution, case):
            scores = {"identifiers": (0, 1), "sum": (1, 0), "extra": (0, 1)}
            score = scores[case["id"]][request["arm"] == "candidate"]
            return {"score":score,"outcome":"pass" if score else "fail", "source":"executable",
                    "evidence":[{"score":score}]}
        val = self.validation(self.compare(case_set=cs, execute_fn=execute, evaluate_fn=evaluate))
        self.assertEqual(val["status"], "rejected")
        self.assertFalse(next(g for g in val["gate_results"] if g["gate"] == "regression_non_decrease")["passed"])

    def test_transfer_threshold_is_explicit_and_ceiling_non_decrease_passes(self):
        cs = case_set(); transfer = copy.deepcopy(cs["cases"][1])
        transfer.update(id="transfer", split="transfer"); cs["cases"].append(transfer)
        p = protocol(); p["criteria"].update(transfer_claim=True,maximum_per_case_transfer_regression=0)
        p["required_gates"].append("transfer_non_decrease")
        self.assertEqual(self.validation(self.compare(case_set=cs,protocol=p))["status"],"accepted")
        p["required_gates"][-1] = "transfer_gain"
        p["criteria"]["transfer_mean_gain_must_exceed"] = 0
        self.assertEqual(self.validation(self.compare(case_set=cs,protocol=p))["status"],"rejected")

    def test_cost_and_stability_missing_parameters_or_evidence_do_not_pass(self):
        p=protocol(); p["required_gates"].extend(["cost","stability"])
        with self.assertRaises(DomainError): self.compare(protocol=p)
        p["criteria"].update(maximum_monetary_cost=1.0,currency="test-unit",maximum_score_range=0.0)
        self.assertEqual(self.validation(self.compare(protocol=p))["status"],"accepted")
        def no_usage(*args):
            out=execute_csv(*args); out.pop("usage"); return out
        val=self.validation(self.compare(protocol=p,execute_fn=no_usage))
        self.assertEqual(val["status"],"unknown")

    def test_all_candidates_are_compared_and_only_qualified_selected(self):
        bad=self.make_candidate("two",preserve=False)
        result=self.compare(candidates=[bad,self.candidate],max_parallel=2)
        vals=[self.validation(result,i) for i in range(2)]
        self.assertEqual([v["status"] for v in vals],["rejected","accepted"])
        self.assertEqual(len(result["usage_ids"]),32)
        selection=self.store.get("selections",result["selection_id"])
        self.assertEqual(len(selection["candidate_validations"]),2)
        self.assertEqual(selection["selected_candidate_digest"],self.candidate["candidate_digest"])

    def test_scheduler_failure_preserves_every_unknown_slot(self):
        with patch("memory_orchestrator.evaluation.ThreadPoolExecutor",side_effect=RuntimeError("pool unavailable")):
            result=self.compare()
        val=self.validation(result)
        self.assertEqual(val["status"],"unknown")
        self.assertEqual(len(val["results"]),8)
        self.assertTrue(all(r["outcome"]=="unknown" for r in val["results"]))

    def test_stability_gate_uses_all_repeats_not_best_run(self):
        p=protocol();p["required_gates"].append("stability");p["criteria"]["maximum_score_range"]=0
        def sometimes_wrong(request,execution,case):
            out=evaluate_csv(request,execution,case)
            if request["arm"]=="candidate" and request["repeat_index"]==1 and case["split"]=="target":
                out.update(outcome="fail",score=0,evidence=[{"constructed_repeated_failure":True}])
            return out
        val=self.validation(self.compare(protocol=p,evaluate_fn=sometimes_wrong))
        self.assertEqual(val["status"],"rejected")
        self.assertTrue(next(g for g in val["gate_results"] if g["gate"]=="target_gain")["passed"])
        self.assertFalse(next(g for g in val["gate_results"] if g["gate"]=="stability")["passed"])

    def test_invalid_callback_usage_is_unknown_without_changing_task_scores(self):
        from memory_orchestrator.report import report
        bad_usage={"tokens":{"input_tokens":1.5,"output_tokens":True,"total_tokens":None},
                   "monetary_cost":-2,"currency":[]}
        def execute(*args):
            out=execute_csv(*args);out["usage"]=copy.deepcopy(bad_usage);return out
        def evaluate(*args):
            out=evaluate_csv(*args);out["usage"]=copy.deepcopy(bad_usage);return out
        result=self.compare(execute_fn=execute,evaluate_fn=evaluate)
        self.assertEqual(self.validation(result)["status"],"accepted")
        output=report(self.store,self.project)
        self.assertIsNone(output["usage"]["complete_cost_totals"])
        self.assertEqual(output["usage"]["tokens"]["missing_calls"],
                         {"input_tokens":16,"output_tokens":16,"total_tokens":16})
        for uid in result["usage_ids"]:
            usage=self.store.get("usage",uid)
            self.assertEqual(usage["raw"],bad_usage)
            self.assertEqual(usage["tokens"],{"input_tokens":None,"output_tokens":None,"total_tokens":None})
            self.assertEqual(len(usage["diagnostics"]),4)


if __name__ == "__main__": unittest.main()
