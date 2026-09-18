"""Recover real ledger interruption points without repeating external effects."""
import copy
import unittest
from unittest.mock import patch

from memory_orchestrator.evaluation import resume_comparison
from memory_orchestrator.schemas import DomainError, new_id
from test_memory_evaluation import MemoryFixture, execute_csv, evaluate_csv, protocol


class ComparisonRecoveryTests(MemoryFixture,unittest.TestCase):
    def callbacks(self):
        counts={'execute':0,'evaluate':0}
        def execute(*args):counts['execute']+=1;return execute_csv(*args)
        def evaluate(*args):counts['evaluate']+=1;return evaluate_csv(*args)
        return counts,execute,evaluate

    def test_saved_results_without_validation_resume_without_reexecuting(self):
        counts,execute,evaluate=self.callbacks();original=self.store.put
        def interrupt(kind,identifier,row):
            if kind=='validations':raise OSError('hard stop before validation')
            return original(kind,identifier,row)
        with patch.object(self.store,'put',side_effect=interrupt),self.assertRaises(OSError):
            self.compare(execute_fn=execute,evaluate_fn=evaluate)
        round_id=self.store.list('evaluation_inputs',self.project)[0]['id']
        before=copy.deepcopy(counts)
        result=resume_comparison(self.store,round_id,execute,evaluate)
        self.assertEqual(counts,before)
        self.assertEqual(self.validation(result)['status'],'accepted')
        self.assertEqual(result,resume_comparison(self.store,round_id,execute,evaluate))
        self.assertEqual(len(self.store.list('validations',self.project)),1)

    def test_feedback_and_assessment_interruption_reuses_original_returns(self):
        for kind in ('feedback','assessments','evaluation_results'):
            with self.subTest(kind=kind):
                counts,execute,evaluate=self.callbacks();original=self.store.put;failed=[]
                def interrupt(collection,identifier,row):
                    if collection==kind and not failed:
                        failed.append(identifier);raise OSError('single persistence stop')
                    return original(collection,identifier,row)
                try:
                    with patch.object(self.store,'put',side_effect=interrupt):
                        result=self.compare(execute_fn=execute,evaluate_fn=evaluate)
                except OSError:
                    result=None
                frozen=self.store.list('evaluation_inputs',self.project)[-1]
                before=copy.deepcopy(counts)
                resumed=resume_comparison(self.store,frozen['id'],execute,evaluate)
                self.assertEqual(counts,before)
                self.assertEqual(self.validation(resumed)['status'],'accepted')

    def test_started_execution_without_return_requires_explicit_resolution(self):
        counts,execute,evaluate=self.callbacks();original=self.store.put;failed=[]
        def interrupt(kind,identifier,row):
            if kind=='callback_returns' and row['stage']=='execute' and not failed:
                failed.append(copy.deepcopy(row));raise OSError('returned data lost before persistence')
            return original(kind,identifier,row)
        with patch.object(self.store,'put',side_effect=interrupt):
            result=self.compare(execute_fn=execute,evaluate_fn=evaluate)
        self.assertEqual(result['status'],'blocked')
        before=copy.deepcopy(counts)
        blocked=resume_comparison(self.store,result['comparison_id'],execute,evaluate)
        self.assertEqual(blocked['status'],'blocked');self.assertEqual(counts,before)
        old=failed[0]
        resolutions={old['request_ref']:{'action':'attach_result','source':'constructed retained callback boundary',
            'evidence':[{'attempt_id':old['attempt_id']}],'raw_output':old['raw_output'],'error':old['error'],
            'measured_usage':old['measured_usage'],'elapsed_seconds':old['elapsed_seconds']}}
        resumed=resume_comparison(self.store,result['comparison_id'],execute,evaluate,resolutions=resolutions)
        self.assertEqual(resumed['status'],'completed')
        self.assertEqual(counts['execute'],before['execute'])
        self.assertEqual(counts['evaluate'],before['evaluate']+1)
        self.assertEqual(self.validation(resumed)['status'],'accepted')

    def test_old_unmarked_comparison_never_guesses_unexecuted(self):
        result=self.compare();frozen=self.store.get('evaluation_inputs',result['comparison_id'])
        frozen.pop('recovery_version');frozen['id']=new_id('legacy_comparison')
        self.store.put('evaluation_inputs',frozen['id'],frozen)
        with self.assertRaises(DomainError):
            resume_comparison(self.store,frozen['id'],lambda *_:self.fail('must not execute'),lambda *_:self.fail('must not evaluate'))

    def test_retry_reservation_counts_interrupted_criterion_against_budget(self):
        p=protocol();p['criteria']['maximum_evaluation_calls']=8
        counts,execute,evaluate=self.callbacks();original=self.store.put;failed=[]
        def interrupt(kind,identifier,row):
            if kind=='callback_returns' and row['stage']=='evaluate' and not failed:
                failed.append(copy.deepcopy(row));raise OSError('unknown evaluation effect')
            return original(kind,identifier,row)
        with patch.object(self.store,'put',side_effect=interrupt):
            result=self.compare(protocol=p,execute_fn=execute,evaluate_fn=evaluate)
        before=copy.deepcopy(counts)
        decision={failed[0]['request_ref']:{'action':'confirmed_not_executed','source':'operator',
            'evidence':['constructed provider audit']}}
        blocked=resume_comparison(self.store,result['comparison_id'],execute,evaluate,resolutions=decision)
        self.assertEqual(blocked['status'],'blocked')
        self.assertEqual(blocked['blocked'][0]['code'],'call_budget')
        self.assertEqual(counts,before)


if __name__=='__main__':unittest.main()
