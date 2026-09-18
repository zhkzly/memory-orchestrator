"""Counts include missing planned requests and all unique stage costs."""
import copy
import unittest
from unittest.mock import patch
from memory_orchestrator.schemas import DomainError
from memory_orchestrator.report import aggregate_usage, report
from test_memory_evaluation import MemoryFixture, execute_csv


class MemoryReportTests(MemoryFixture,unittest.TestCase):
    def test_complete_and_failed_candidate_costs_are_counted_once(self):
        bad=self.make_candidate("bad",preserve=False)
        self.compare(candidates=[self.candidate,bad])
        output=report(self.store,self.project)
        self.assertEqual(output["evaluation_requests"],16)
        self.assertEqual(output["candidate_counts"],{"accepted":1,"rejected":1,"unknown":0})
        self.assertEqual(output["usage"]["unique_calls"],32)
        self.assertAlmostEqual(output["usage"]["complete_cost_totals"]["test-unit"],0.48)
        self.assertEqual(output["usage"]["by_stage"],{"execute":16,"evaluate":16})

    def test_missing_usage_stays_unknown(self):
        def missing(*args):
            out=execute_csv(*args); out.pop("usage"); return out
        self.compare(execute_fn=missing)
        output=report(self.store,self.project)
        self.assertEqual(output["usage"]["missing_cost_calls"],8)
        self.assertIsNone(output["usage"]["complete_cost_totals"])
        self.assertAlmostEqual(output["usage"]["known_cost_subtotals"]["test-unit"],0.16)

    def test_usage_deduplication_conflict_and_currencies(self):
        one={"usage_id":"u1","exclusive_stage":"execute","monetary_cost":1,"currency":"USD","time":1}
        two={"usage_id":"u2","exclusive_stage":"evaluate","monetary_cost":2,"currency":"EUR","time":2}
        out=aggregate_usage([one,copy.deepcopy(one),two])
        self.assertEqual(out["unique_calls"],2)
        self.assertEqual(out["complete_cost_totals"],{"USD":1,"EUR":2})
        conflicting=copy.deepcopy(one); conflicting["monetary_cost"]=100
        with self.assertRaises(DomainError): aggregate_usage([one,conflicting])

    def test_entire_unfinished_plan_remains_in_denominator(self):
        result=self.compare()
        old=self.store.get("evaluation_plans",result["plan_ids"][0])
        pending=copy.deepcopy(old); pending["plan_id"]="not-executed"
        for r in pending["requests"]:r["request_id"]="pending-"+r["request_id"]
        self.store.put("evaluation_plans",pending["plan_id"],pending)
        output=report(self.store,self.project)
        self.assertEqual(output["evaluation_requests"],16)
        self.assertEqual(output["outcomes"]["unknown"],8)
        self.assertEqual(output["coverage"],0.5)
        self.assertEqual(output["identification_bounds"],[6/16,14/16])
        self.assertIsNone(output["usage"]["complete_cost_totals"])
        self.assertEqual(output["usage"]["unaccounted_evaluation_requests"],8)
        self.assertEqual(output["unique_case_identity_count"],2)

    def test_invalid_cost_and_missing_time_do_not_become_known_zero(self):
        for invalid in [True,float("nan"),-1]:
            with self.assertRaises(DomainError):
                aggregate_usage([{"usage_id":"bad","exclusive_stage":"extract","monetary_cost":invalid,"currency":"USD"}])
        out=aggregate_usage([{"usage_id":"u1","exclusive_stage":"extract","monetary_cost":None,"currency":None}])
        self.assertIsNone(out["sum_run_time"])
        self.assertIsNone(out["complete_cost_totals"])

    def test_scheduling_unknowns_are_not_zero_cost_evidence(self):
        with patch("memory_orchestrator.evaluation.ThreadPoolExecutor",side_effect=RuntimeError("pool unavailable")):
            self.compare()
        output=report(self.store,self.project)
        self.assertEqual(output["outcomes"],{"pass":0,"fail":0,"unknown":8})
        self.assertIsNone(output["usage"]["complete_cost_totals"])
        self.assertEqual(output["usage"]["unaccounted_evaluation_requests"],8)

    def test_token_measures_have_independent_subtotals_and_missing_counts(self):
        def row(uid,tokens):
            return {"usage_id":uid,"exclusive_stage":"extract","tokens":tokens,"monetary_cost":None,"currency":None}
        one=row("one",{"input_tokens":10,"output_tokens":3,"total_tokens":None})
        two=row("two",{"input_tokens":4,"output_tokens":None,"total_tokens":7})
        out=aggregate_usage([one,copy.deepcopy(one),two,row("three",None)])
        self.assertEqual(out["tokens"]["known_subtotals"],{"input_tokens":14,"output_tokens":3,"total_tokens":7})
        self.assertEqual(out["tokens"]["known_calls"],{"input_tokens":2,"output_tokens":1,"total_tokens":1})
        self.assertEqual(out["tokens"]["missing_calls"],{"input_tokens":1,"output_tokens":2,"total_tokens":2})
        self.assertEqual(out["tokens"]["complete_totals"],{"input_tokens":None,"output_tokens":None,"total_tokens":None})
        complete=aggregate_usage([row("four",{"input_tokens":10,"output_tokens":3,"total_tokens":13})])
        self.assertEqual(complete["tokens"]["complete_totals"],{"input_tokens":10,"output_tokens":3,"total_tokens":13})

    def test_invalid_tokens_rejected_and_all_unknowns_not_zero(self):
        for tokens in [True,{"input_tokens":True},{"total_tokens":-1},{"output_tokens":2.5}]:
            with self.assertRaises(DomainError):
                aggregate_usage([{"usage_id":"bad","exclusive_stage":"propose","tokens":tokens}])
        out=aggregate_usage([{"usage_id":"unknown","exclusive_stage":"propose","tokens":None}])
        self.assertEqual(out["tokens"]["known_subtotals"],{"input_tokens":None,"output_tokens":None,"total_tokens":None})

    def test_unfinished_sampling_slots_prevent_complete_cost_claim(self):
        # Schema-derived RunGroupPlan with real project/base identity; no execution invented.
        from memory_orchestrator.schemas import digest
        plan={"group_id":"pending-sampling","project_id":self.project,"task_revision":"csv@1",
              "initial_state_digest":None,"snapshot_digest":self.active["snapshot_id"],
              "active_generation":self.active["generation"],"context_digest":digest({"provided":[]}),
              "executor_ref":"csv-executor/v1","executor_config_hash":digest({}),"protocol_id":"explicit-demo",
              "purpose":"learning","update_mode":"task_barrier","k":2,"max_parallel":1,
              "learning_enabled":True,"limitations":["Constructed pending plan; no execution."],
              "slots":[{"slot_id":"slot-a","run_id":"run-a","seed":None,"seed_support":"unsupported"},
                       {"slot_id":"slot-b","run_id":"run-b","seed":None,"seed_support":"unsupported"}]}
        self.store.put("run_groups",plan["group_id"],plan)
        output=report(self.store,self.project)
        self.assertEqual(output["sampling_slots"],2)
        self.assertEqual(output["usage"]["unaccounted_sampling_slots"],2)
        self.assertIsNone(output["usage"]["complete_cost_totals"])
        self.assertEqual(output["usage"]["tokens"]["complete_totals"],{"input_tokens":None,"output_tokens":None,"total_tokens":None})

    def test_comparison_reports_quality_regression_and_stability_by_case(self):
        result=self.compare()
        output=report(self.store,self.project)
        comparison=output["comparisons"][0]
        self.assertEqual(comparison["plan_id"],result["plan_ids"][0])
        self.assertEqual(comparison["validation_id"],result["validation_ids"][0])
        self.assertEqual(comparison["base_digest"],self.active["snapshot_id"])
        self.assertEqual(comparison["candidate_digest"],self.candidate["candidate_digest"])
        self.assertEqual(comparison["acceptance_scope"],"local repair")
        self.assertEqual(comparison["repeat_count"],2)
        target=comparison["by_split"]["target"][0]
        self.assertEqual((target["base"],target["candidate"],target["gain"]),(0,1,1))
        self.assertEqual((target["base_range"],target["candidate_range"]),(0,0))
        self.assertEqual((target["base_known_repeats"],target["candidate_known_repeats"]),(2,2))
        self.assertEqual(target["observed_change"],"improved")
        regression=comparison["by_split"]["regression"][0]
        self.assertEqual((regression["base"],regression["candidate"],regression["gain"]),(1,1,0))
        self.assertEqual(regression["observed_change"],"unchanged")
        self.assertEqual(comparison["by_split"]["transfer"],[])
        self.assertEqual(comparison["missing_request_ids"],[])

    def test_historical_comparison_status_not_recomputed_after_publication(self):
        from memory_orchestrator.release import publish
        result=self.compare()
        before=report(self.store,self.project)["comparisons"]
        publish(self.store,self.project,self.candidate["proposal_id"],result["validation_ids"][0],result["selection_id"],
                expected_active_digest=self.active["snapshot_id"],expected_generation=0)
        after=report(self.store,self.project)["comparisons"]
        self.assertEqual(before,after)
        self.assertEqual(after[0]["validation_status"],"accepted")

    def test_missing_comparison_results_stay_missing_per_split(self):
        result=self.compare()
        old=self.store.get("evaluation_plans",result["plan_ids"][0])
        pending=copy.deepcopy(old);pending["plan_id"]="pending-comparison"
        for row in pending["requests"]:row["request_id"]="later-"+row["request_id"]
        self.store.put("evaluation_plans",pending["plan_id"],pending)
        output=report(self.store,self.project)
        item=next(c for c in output["comparisons"] if c["plan_id"]==pending["plan_id"])
        self.assertEqual(item["validation_status"],"missing")
        self.assertEqual(len(item["missing_request_ids"]),8)
        for split in ("target","regression"):
            row=item["by_split"][split][0]
            self.assertIsNone(row["base"])
            self.assertIsNone(row["gain"])
            self.assertEqual(row["base_known_repeats"],0)
            self.assertEqual(row["observed_change"],"unknown")


if __name__=="__main__":unittest.main()
