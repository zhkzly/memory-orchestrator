"""Release checks use real files, locks and local task results."""
import copy
import csv
import io
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from memory_orchestrator.schemas import DomainError, new_id, digest
from memory_orchestrator.evaluation import verify_validation
from memory_orchestrator.release import publish, rollback
from test_memory_evaluation import MemoryFixture, case_set, execute_csv


class MemoryReleaseTests(MemoryFixture, unittest.TestCase):
    def promote(self, result, candidate=None):
        candidate = candidate or self.candidate
        return publish(self.store, self.project, candidate["proposal_id"], result["validation_ids"][0],
                       result["selection_id"], expected_active_digest=candidate["base_digest"],
                       expected_generation=candidate["expected_generation"])

    def test_exact_selected_candidate_commits_and_retry_is_idempotent(self):
        result=self.compare()
        release=self.promote(result)
        self.assertEqual(release["new_generation"],1)
        self.assertEqual(self.store.active(self.project)["snapshot_id"],self.candidate["candidate_digest"])
        self.assertEqual(self.promote(result),release)
        self.assertEqual(len(self.store.release_history(self.project)),1)

    def test_unselected_candidate_cannot_publish_even_if_accepted(self):
        other=self.make_candidate("two")
        result=self.compare(candidates=[self.candidate,other])
        selection=self.store.get("selections",result["selection_id"])
        wrong=next(c for c in [self.candidate,other] if c["candidate_digest"] != selection["selected_candidate_digest"])
        wrong_val=next(v for v in [self.validation(result,0),self.validation(result,1)] if v["candidate_digest"]==wrong["candidate_digest"])
        with self.assertRaises(DomainError):
            publish(self.store,self.project,wrong["proposal_id"],wrong_val["validation_id"],result["selection_id"],
                    expected_active_digest=self.active["snapshot_id"],expected_generation=0)
        self.assertEqual(self.store.active(self.project),self.active)

    def test_selected_snapshot_allows_frozen_alias_but_not_later_alias(self):
        duplicate=copy.deepcopy(self.candidate);duplicate["proposal_id"]=new_id("proposal")
        self.store.put("candidates",duplicate["proposal_id"],duplicate)
        result=self.compare(candidates=[self.candidate,duplicate])
        release=self.promote(result,duplicate)
        self.assertEqual(self.promote(result,self.candidate),release)
        unconsidered=copy.deepcopy(self.candidate);unconsidered["proposal_id"]=new_id("proposal")
        self.store.put("candidates",unconsidered["proposal_id"],unconsidered)
        with self.assertRaises(DomainError):self.promote(result,unconsidered)

    def test_alias_mapping_cannot_be_forged_in_selection(self):
        result=self.compare()
        selection=self.store.get("selections",result["selection_id"])
        forged=copy.deepcopy(selection);forged["selection_id"]=new_id("forgedselection")
        forged["candidate_validations"][0]["proposal_ids"]=["not-a-frozen-proposal"]
        self.store.put("selections",forged["selection_id"],forged)
        with self.assertRaises(DomainError):
            publish(self.store,self.project,self.candidate["proposal_id"],result["validation_ids"][0],forged["selection_id"],
                    expected_active_digest=self.active["snapshot_id"],expected_generation=0)

    def test_noncompleted_but_verified_artifact_can_publish_under_frozen_policy(self):
        def cancelled(*args):
            out=execute_csv(*args);out["execution_status"]="cancelled";return out
        result=self.compare(execute_fn=cancelled)
        release=self.promote(result)
        self.assertEqual(release["status"],"published")
        self.assertTrue(all(row["execution_status"]=="cancelled" for row in self.validation(result)["results"]))

    def test_publication_recheck_enforces_recorded_scoring_policy(self):
        def cancelled(*args):
            out=execute_csv(*args);out["execution_status"]="cancelled";return out
        result=self.compare(execute_fn=cancelled)
        original=self.validation(result)
        old_plan=self.store.get("evaluation_plans",original["plan_id"])
        old_protocol=self.store.get("protocols",old_plan["protocol_ref"])
        strict=copy.deepcopy(old_protocol);strict["id"]=new_id("protocol")
        strict["value"]["scoring_policy"]="completed_only"
        self.store.put("protocols",strict["id"],strict)
        plan=copy.deepcopy(old_plan);plan.update(plan_id=new_id("plan"),protocol_ref=strict["id"],
            protocol_hash=digest(strict["value"]),scoring_policy="completed_only")
        self.store.put("evaluation_plans",plan["plan_id"],plan)
        forged=copy.deepcopy(original);forged.update(validation_id=new_id("validation"),plan_id=plan["plan_id"],
            plan_hash=digest(plan),protocol_hash=plan["protocol_hash"])
        self.store.put("validations",forged["validation_id"],forged)
        with self.assertRaises(DomainError):verify_validation(self.store,forged)

    def test_publication_checks_actual_snapshot_and_public_case_inputs(self):
        result=self.compare();original=self.store.get
        for index in (1,2):
            def changed(kind,identifier):
                row=original(kind,identifier)
                if kind=='evaluation_returns' and row['stage']=='execute':
                    row['inputs'][index]={'substituted':'not the actual planned input'}
                return row
            with self.subTest(index=index),patch.object(self.store,'get',side_effect=changed),self.assertRaises(DomainError):
                self.promote(result)

    def test_publication_rechecks_original_quality_scope(self):
        result=self.compare();original=self.store.get
        plan=original('evaluation_plans',result['plan_ids'][0]);changed_plan=copy.deepcopy(plan)
        changed_plan['quality_case_refs']=['sum']
        def changed(kind,identifier):
            value=original(kind,identifier)
            if kind=='evaluation_plans' and identifier==plan['plan_id']:return changed_plan
            if kind=='validations' and value['plan_id']==plan['plan_id']:value['plan_hash']=digest(changed_plan)
            return value
        with patch.object(self.store,'get',side_effect=changed),self.assertRaises(DomainError) as caught:
            self.promote(result)
        self.assertEqual(caught.exception.code,'quality_scope')

    def test_missing_or_duplicate_gates_cannot_be_forged_into_a_release(self):
        result=self.compare()
        val=self.validation(result)
        sel=self.store.get("selections",result["selection_id"])
        for defect in ["missing","duplicate","false_score","missing_result","duplicate_result"]:
            forged=copy.deepcopy(val); forged["validation_id"]=new_id("forged")
            if defect=="missing": forged["gate_results"].pop()
            if defect=="duplicate": forged["gate_results"][-1]=copy.deepcopy(forged["gate_results"][0])
            if defect=="false_score": forged["results"][0]["score"]=1
            if defect=="missing_result": forged["results"].pop()
            if defect=="duplicate_result": forged["results"][-1]=copy.deepcopy(forged["results"][0])
            self.store.put("validations",forged["validation_id"],forged)
            chosen=copy.deepcopy(sel); chosen["selection_id"]=new_id("forgedselection")
            chosen["selected_validation_ref"]=forged["validation_id"]
            chosen["candidate_validations"][0]["validation_ref"]=forged["validation_id"]
            self.store.put("selections",chosen["selection_id"],chosen)
            with self.subTest(defect=defect), self.assertRaises(DomainError):
                publish(self.store,self.project,self.candidate["proposal_id"],forged["validation_id"],chosen["selection_id"],
                        expected_active_digest=self.active["snapshot_id"],expected_generation=0)

    def test_foreign_project_and_wrong_generation_do_not_publish(self):
        result=self.compare()
        self.store.ensure_project("other")
        for project,generation in [("other",0),(self.project,1)]:
            with self.assertRaises(DomainError):
                publish(self.store,project,self.candidate["proposal_id"],result["validation_ids"][0],result["selection_id"],
                        expected_active_digest=self.active["snapshot_id"],expected_generation=generation)

    def test_failure_before_active_write_leaves_orphan_uncommitted_and_retry_works(self):
        result=self.compare()
        original=self.store._atomic_write
        def fail_active(path,value):
            if path.name=="active.json": raise OSError("constructed active-write failure")
            return original(path,value)
        with patch.object(self.store,"_atomic_write",side_effect=fail_active),self.assertRaises(OSError):
            self.promote(result)
        self.assertEqual(self.store.active(self.project),self.active)
        self.assertEqual(self.store.release_history(self.project),[])
        orphan=self.store.list("releases",project_id=self.project)[0]
        with self.assertRaises(DomainError):
            rollback(self.store,self.project,orphan["release_id"],expected_active_digest=self.active["snapshot_id"],
                     expected_generation=0,reason="Orphan is not history")
        release=self.promote(result)
        self.assertEqual(release["release_id"],orphan["release_id"])
        self.assertEqual(len(self.store.release_history(self.project)),1)

    def test_two_publishers_have_one_atomic_winner(self):
        other=self.make_candidate("two")
        first=self.compare()
        second=self.compare(candidates=[other])
        original=self.store._commit_release
        barrier=threading.Barrier(2)
        def at_commit(*args):
            barrier.wait(timeout=5)
            return original(*args)
        with patch.object(self.store,"_commit_release",side_effect=at_commit),ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(self.promote,first),pool.submit(self.promote,second,other)]
            results=[]
            for future in futures:
                try: results.append(future.result())
                except DomainError as exc: results.append(exc)
        self.assertEqual(sum(isinstance(r,dict) for r in results),1)
        self.assertEqual(self.store.active(self.project)["generation"],1)
        self.assertEqual(len(self.store.release_history(self.project)),1)

    def test_rollback_checks_history_and_aba_generation(self):
        first=self.promote(self.compare())
        self.active=self.store.active(self.project)
        next_candidate=self.make_candidate("uppercase",extra_steps=["Uppercase identifiers."])
        cs=case_set(); cs["cases"][0]["task"]["csv"]="code,amount\naa,3\nbb,4\n"
        cs["cases"][0]["criteria"]["codes"]=["AA","BB"]
        def uppercase(request,snapshot,case):
            out=execute_csv(request,snapshot,case)
            if any("Uppercase identifiers." in s["content"]["steps"] for s in snapshot["skills"].values()):
                rows=list(csv.DictReader(io.StringIO(out["artifact"]["csv"])))
                for row in rows: row["code"]=row["code"].upper()
                stream=io.StringIO(); writer=csv.DictWriter(stream,fieldnames=["code","amount"])
                writer.writeheader(); writer.writerows(rows); out["artifact"]["csv"]=stream.getvalue()
            return out
        next_result=self.compare(candidates=[next_candidate],case_set=cs,execute_fn=uppercase)
        second=self.promote(next_result,next_candidate)
        restored=rollback(self.store,self.project,first["release_id"],expected_active_digest=second["new_digest"],
                          expected_generation=2,reason="Restore earlier behavior")
        self.assertEqual(restored["new_generation"],3)
        self.assertEqual(self.store.active(self.project)["snapshot_id"],first["new_digest"])
        with self.assertRaises(DomainError):
            self.compare(candidates=[next_candidate],case_set=cs,execute_fn=uppercase)
        with self.assertRaises(DomainError):
            rollback(self.store,self.project,"not-published",expected_active_digest=first["new_digest"],
                     expected_generation=3,reason="Invalid target")


if __name__=="__main__": unittest.main()
