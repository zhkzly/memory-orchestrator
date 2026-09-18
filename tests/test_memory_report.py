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
        self.assertEqual(output["candidate_counts"],{"unique_snapshots":2,"proposal_records":2,"compared_snapshots":2})
        self.assertEqual(output["validation_attempt_counts"],{"accepted":1,"rejected":1,"unknown":0})
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

    def test_observed_results_survive_interruption_before_validation(self):
        original=self.store.put
        def stop_after_results(kind,identifier,value):
            if kind=="validations":raise OSError("constructed interruption after results")
            return original(kind,identifier,value)
        with patch.object(self.store,"put",side_effect=stop_after_results),self.assertRaises(OSError):
            self.compare()
        self.assertEqual(self.store.list("validations",project_id=self.project),[])
        output=report(self.store,self.project)
        self.assertEqual(output["outcomes"],{"pass":6,"fail":2,"unknown":0})
        comparison=output["comparisons"][0]
        self.assertEqual(comparison["recorded_results"],8)
        self.assertEqual(comparison["validation_status"],"missing")
        self.assertEqual(comparison["by_split"]["target"][0]["gain"],1)
        self.assertEqual(self.store.active(self.project),self.active)

    def test_revalidation_counts_attempts_not_additional_candidates(self):
        self.compare();self.compare()
        output=report(self.store,self.project)
        self.assertEqual(output["candidate_counts"]["unique_snapshots"],1)
        self.assertEqual(output["candidate_counts"]["proposal_records"],1)
        self.assertEqual(output["validation_attempt_counts"]["accepted"],2)
        self.assertEqual(output["comparison_summary"]["planned_requests"],16)

    def test_sampling_quality_modes_any_all_and_terminal_states(self):
        from memory_orchestrator.sampling import sample_tasks
        task={"project_id":self.project,"task_id":"sample-csv","revision":"1",
              "description":"CSV identifiers","input":"001","criteria":{"expected":"001"}}
        def execute(request,snapshot,case):
            return {"artifact":"002" if request["repeat_index"]==1 else "001"}
        def evaluate(request,execution,case):
            passed=execution["artifact"]==case["criteria"]["expected"]
            return {"outcome":"pass" if passed else "fail","score":int(passed),"source":"executable",
                    "evidence":[{"actual":execution["artifact"]}]}
        sample_tasks(self.store,[task],execute,evaluate,policy={"repeat_count":3,"max_parallel":2,
            "purpose":"learning","update_mode":"task_barrier","protocol_id":"sample/v1",
            "executor":{"id":"csv/v1","config":{}}},
            context_policy={"max_roots":2,"max_context_chars":5000,"relation_weight":0.0})
        output=report(self.store,self.project)
        self.assertEqual(output["evaluation_requests"],0)
        group=output["sampling"]["groups"][0]
        self.assertTrue(all(row["assessment_ref"] for row in group["results"]))
        self.assertTrue(all(row["assessment_source"]=="referenced" for row in group["results"]))
        self.assertEqual(group["outcomes"],{"pass":2,"fail":1,"unknown":0})
        self.assertEqual(group["execution_status_counts"]["completed"],3)
        self.assertTrue(group["any_success"]);self.assertFalse(group["all_success"])
        mode=output["sampling"]["by_mode"][0]
        self.assertEqual((mode["purpose"],mode["update_mode"]),("learning","task_barrier"))
        self.assertAlmostEqual(mode["observed_success_rate"],2/3)

    def test_partial_result_any_all_keep_missing_repeats_unknown(self):
        original=self.store.put;written=[]
        def stop_partway(kind,identifier,value):
            if kind=="evaluation_results":
                if len(written)==3:raise OSError("partial result persistence")
                written.append(identifier)
            return original(kind,identifier,value)
        with patch.object(self.store,"put",side_effect=stop_partway),self.assertRaises(OSError):self.compare()
        output=report(self.store,self.project)
        self.assertEqual(output["outcomes"],{"pass":1,"fail":2,"unknown":5})
        row=output["comparisons"][0]["by_split"]["target"][0]
        self.assertTrue(row["candidate_any_success"])
        self.assertIsNone(row["candidate_all_success"])
        self.assertFalse(row["base_any_success"])
        self.assertFalse(row["base_all_success"])
        missing=output["comparisons"][0]["by_split"]["regression"][0]
        self.assertIsNone(missing["base_any_success"])
        self.assertIsNone(missing["base_all_success"])

    def test_legacy_sampling_requires_unique_bound_feedback(self):
        from memory_orchestrator.sampling import sample_tasks
        from memory_orchestrator.schemas import new_id
        sampled=sample_tasks(self.store,[{"project_id":self.project,"task_id":"legacy","revision":"1",
            "description":"Legacy outcome","criteria":{}}],lambda *_:{"artifact":"ok"},
            lambda *_:{"outcome":"pass","score":1,"source":"executable","evidence":["checked"]},
            policy={"repeat_count":1,"max_parallel":1,"purpose":"learning","update_mode":"task_barrier",
                    "protocol_id":"legacy/v1","executor":{"id":"fixture","config":{}}},
            context_policy={"max_roots":2,"max_context_chars":5000,"relation_weight":0})
        original_list=self.store.list
        def legacy_list(kind,project_id=None):
            rows=original_list(kind,project_id=project_id)
            if kind=="runs":
                rows=copy.deepcopy(rows)
                for row in rows:row.pop("assessment_ref",None)
            return rows
        with patch.object(self.store,"list",side_effect=legacy_list):
            first=report(self.store,self.project)["sampling"]["groups"][0]
            self.assertEqual(first["outcomes"],{"pass":1,"fail":0,"unknown":0})
            self.assertEqual(first["results"][0]["assessment_source"],"unique_original_feedback")
            existing=self.store.feedback_for(sampled["episodes"][0]["episode_id"])[0]
            other=copy.deepcopy(existing);other.update(check_id=new_id("feedback"),outcome="fail",score=0)
            self.store.add_feedback(other)
            ambiguous=report(self.store,self.project)["sampling"]["groups"][0]
            self.assertEqual(ambiguous["outcomes"],{"pass":0,"fail":0,"unknown":1})
            self.assertIn("ambiguous_assessment",ambiguous["results"][0]["reason"])

    def test_comparison_terminal_states_are_separate_from_known_scores(self):
        def cancelled(*args):
            out=execute_csv(*args);out["execution_status"]="cancelled";return out
        self.compare(execute_fn=cancelled)
        output=report(self.store,self.project)
        self.assertEqual(output["outcomes"],{"pass":6,"fail":2,"unknown":0})
        self.assertEqual(output["execution_status_counts"]["cancelled"],8)
        candidate=output["comparisons"][0]["by_split"]["target"][0]
        self.assertTrue(candidate["candidate_all_success"])
        self.assertEqual(candidate["candidate_execution_status_counts"]["cancelled"],2)
        mode=output["comparison_summary"]["by_mode"][0]
        self.assertEqual((mode["purpose"],mode["update_mode"],mode["scoring_policy"]),
                         ("validation","none","available_artifact"))

    def test_explicit_assessment_cannot_borrow_other_runs_feedback(self):
        from memory_orchestrator.sampling import sample_tasks
        sampled=sample_tasks(self.store,[{"project_id":self.project,"task_id":"assessment","revision":"1",
            "description":"Bind score to run","criteria":{}}],lambda *_:{"artifact":"ok"},
            lambda *_:{"outcome":"pass","score":1,"source":"executable","evidence":["checked"]},
            policy={"repeat_count":2,"max_parallel":1,"purpose":"learning","update_mode":"task_barrier",
                    "protocol_id":"assessment/v1","executor":{"id":"fixture","config":{}}},
            context_policy={"max_roots":2,"max_context_chars":5000,"relation_weight":0})
        first=self.store.get("runs",sampled["run_ids"][0]);second=self.store.get("runs",sampled["run_ids"][1])
        original=self.store.list
        def mixed_pointer(kind,project_id=None):
            values=original(kind,project_id=project_id)
            if kind=="runs":
                values=copy.deepcopy(values)
                for row in values:
                    if row["run_id"]==first["run_id"]:row["assessment_ref"]=second["assessment_ref"]
            return values
        with patch.object(self.store,"list",side_effect=mixed_pointer):
            group=report(self.store,self.project)["sampling"]["groups"][0]
        self.assertEqual(group["outcomes"],{"pass":1,"fail":0,"unknown":1})
        bad=next(r for r in group["results"] if r["run_id"]==first["run_id"])
        self.assertEqual(bad["assessment_error"]["code"],"assessment_binding")

    def test_early_sampling_scores_survive_both_persistence_interruptions(self):
        from memory_orchestrator.sampling import sample_tasks
        from memory_orchestrator.lineage import require_learning_source
        from memory_orchestrator.schemas import new_id
        from pathlib import Path
        for stop_kind in ("assessments","runs"):
            with self.subTest(stop_kind=stop_kind):
                project="early-"+stop_kind
                original=self.store.put
                def interrupted(kind,identifier,value):
                    if kind==stop_kind:raise OSError("Interrupted before "+kind)
                    return original(kind,identifier,value)
                with patch.object(self.store,"put",side_effect=interrupted),self.assertRaises(OSError):
                    sample_tasks(self.store,[{"project_id":project,"task_id":"task","revision":"1",
                        "description":"Early observation","criteria":{}}],lambda *_:{"artifact":"ok"},
                        lambda *_:{"outcome":"pass","score":1,"source":"executable","evidence":["checked"]},
                        policy={"repeat_count":1,"max_parallel":1,"purpose":"learning","update_mode":"task_barrier",
                                "protocol_id":"early/v1","executor":{"id":"fixture","config":{}}},
                        context_policy={"max_roots":1,"max_context_chars":5000,"relation_weight":0})
                episode=self.store.list("episodes",project_id=project)[0]
                before={str(p):p.read_bytes() for p in Path(self.temp.name).rglob('*.json')}
                output=report(self.store,project)
                # report itself is appended; observations and missing lifecycle records are unchanged.
                for path,data in before.items():self.assertEqual(Path(path).read_bytes(),data)
                self.assertEqual(self.store.list("runs",project_id=project),[])
                self.assertEqual(self.store.list("group_receipts",project_id=project),[])
                group=output["sampling"]["groups"][0]
                self.assertEqual(group["recorded_runs"],0)
                self.assertEqual(group["recorded_receipts"],0)
                self.assertEqual(group["outcomes"],{"pass":1,"fail":0,"unknown":0})
                source=group["results"][0]["assessment_source"]
                self.assertEqual(source,"unique_original_feedback" if stop_kind=="assessments" else "recovered_assessment")
                with self.assertRaises(DomainError):require_learning_source(self.store,episode)
                original_get=self.store.get
                def contradictory_source(kind,identifier):
                    value=original_get(kind,identifier)
                    if kind=="executions" and identifier==episode["source"]["reference"]:
                        value=copy.deepcopy(value);value["request"]["request_id"]="another-known-run"
                    return value
                with patch.object(self.store,"get",side_effect=contradictory_source):
                    wrong=report(self.store,project)["sampling"]["groups"][0]
                self.assertEqual(wrong["outcomes"],{"pass":0,"fail":0,"unknown":1})
                if stop_kind=="assessments":
                    duplicate=copy.deepcopy(self.store.feedback_for(episode["episode_id"])[0])
                    duplicate.update(check_id=new_id("feedback"),outcome="fail",score=0)
                    self.store.add_feedback(duplicate)
                else:
                    duplicate=copy.deepcopy(self.store.list("assessments",project_id=project)[0])
                    duplicate["assessment_id"]=new_id("assessment")
                    self.store.put("assessments",duplicate["assessment_id"],duplicate)
                ambiguous=report(self.store,project)["sampling"]["groups"][0]
                self.assertEqual(ambiguous["outcomes"],{"pass":0,"fail":0,"unknown":1})
                self.assertIn("ambiguous_assessment",ambiguous["results"][0]["reason"])
                self.assertEqual(self.store.list("runs",project_id=project),[])
                with self.assertRaises(DomainError):require_learning_source(self.store,episode)


if __name__=="__main__":unittest.main()
