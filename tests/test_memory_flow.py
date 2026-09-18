"""Whole local flow with an explicit scripted teacher, not a learning benchmark."""
import importlib.util
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from memory_orchestrator.context import select_context
from memory_orchestrator.store import Store


spec = importlib.util.spec_from_file_location('memory_demo', Path(__file__).parents[1] / 'examples/memory_evolution/demo.py')
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


class FlowTests(unittest.TestCase):
    def test_engine_uses_selected_snapshot_not_first_proposal(self):
        class TwoChoices(demo.ScriptedTeacher):
            proposed=0
            def generate(self,prompt_id,inputs,**kwargs):
                response=super().generate(prompt_id,inputs,**kwargs)
                if prompt_id=='propose_v1':
                    self.proposed+=1
                    if self.proposed==1:
                        response['value']['asset_edits'][0]['content']=json.dumps(
                            {'preserve_string_columns':False,'empty_numeric_as_null':False},sort_keys=True)
                return response
        learning=copy.deepcopy(demo.LEARNING);learning['candidate_count']=2
        comparison=demo.protocol('two-distinct/v1');comparison['criteria']['maximum_evaluation_calls']=16
        with tempfile.TemporaryDirectory() as root,patch.object(demo,'LEARNING',learning),patch.object(demo,'protocol',return_value=comparison):
            result=demo.run_demo(root,model=TwoChoices(),rounds=1)
            self.assertEqual(result['release_count'],1)
            self.assertEqual(result['report']['validation_attempt_counts'],{'accepted':1,'rejected':1,'unknown':0})
            store=Store(root);active=store.snapshot(store.active('csv-demo')['snapshot_id'])
            config=json.loads(next(iter(active['assets'].values())))
            self.assertTrue(config['preserve_string_columns'])

    def test_duplicate_generation_attempts_still_publish_one_snapshot(self):
        learning=copy.deepcopy(demo.LEARNING);learning['candidate_count']=2
        with tempfile.TemporaryDirectory() as root, patch.object(demo,'LEARNING',learning):
            result=demo.run_demo(root,rounds=1)
            store=Store(root)
            proposals=store.list('candidates',project_id='csv-demo')
            self.assertEqual(len(proposals),2)
            self.assertEqual(len({p['candidate_digest'] for p in proposals}),1)
            self.assertEqual(result['release_count'],1)
            self.assertEqual(result['report']['evaluation_requests'],8)
            self.assertEqual(result['report']['usage']['by_stage']['propose'],2)
            self.assertEqual(result['report']['proposal_attempts']['planned_slots'],2)
            self.assertEqual(result['report']['candidate_counts']['proposal_records'],2)
            self.assertEqual(result['report']['candidate_counts']['unique_snapshots'],1)

    def test_rejected_and_invalid_comparisons_cannot_publish(self):
        for invalid in (False, True):
            explicit = demo.protocol('refusal/v1')
            if invalid:
                explicit['required_gates'] = ['complete_results']
            else:
                explicit['criteria']['target_mean_gain_must_exceed'] = 1.0
            with tempfile.TemporaryDirectory() as root, patch.object(demo, 'protocol', return_value=explicit):
                result = demo.run_demo(root, rounds=1)
                self.assertEqual(result['release_count'], 0)
                self.assertEqual(Store(root).active('csv-demo')['generation'], 0)
                if invalid:
                    errors = Store(root).list('errors', project_id='csv-demo')
                    self.assertTrue(any(error.get('stage') == 'compare' for error in errors))
                else:
                    self.assertEqual(result['report']['validation_attempt_counts']['rejected'], 1)

    def test_generate_patch_publish_reuse_rollback_and_reopen(self):
        with tempfile.TemporaryDirectory() as root:
            result = demo.run_demo(root)
            self.assertEqual(result['learning_statuses'], ['proposed', 'proposed'])
            self.assertEqual(result['release_count'], 2)
            self.assertEqual([x['outcome'] for x in result['after_release']], ['pass', 'pass'])
            self.assertNotEqual(result['after_release'][0]['snapshot_digest'], result['after_release'][1]['snapshot_digest'])
            store = Store(root)
            candidates = store.list('candidates', project_id='csv-demo')
            self.assertCountEqual([p['patch']['operations'][0]['op'] for p in candidates], ['ADD', 'PATCH'])
            self.assertTrue(all(len(store.snapshot(p['candidate_digest'])['skills']) == 1 for p in candidates))
            self.assertEqual(store.active('csv-demo')['generation'], 3)
            self.assertEqual(store.active('csv-demo')['snapshot_id'], result['after_release'][0]['snapshot_digest'])
            current = select_context(store, {'project_id': 'csv-demo', 'description': 'CSV conversion'}, demo.CONTEXT)
            self.assertEqual(current['snapshot_digest'], result['rollback']['new_digest'])
            report = result['report']
            self.assertEqual(report['episode_count'], 6)
            self.assertEqual(report['distinct_known_task_count'], 2)
            self.assertEqual(report['evaluation_requests'], 16)
            self.assertEqual(report['usage']['by_stage']['execute'], 22)
            self.assertEqual(report['usage']['by_stage']['evaluate'], 22)
            self.assertEqual(report['usage']['by_stage']['propose'], 2)
            runs = store.list('runs', project_id='csv-demo')
            self.assertTrue(any(r['consumption_observability'] == 'observed' for r in runs))
            self.assertTrue(any(r['consumption_observability'] == 'unknown' for r in runs))
            diagnoses = [r for r in store.list('reports', project_id='csv-demo') if r.get('prompt_id') == 'diagnose_v1']
            observed = [source for r in diagnoses for source in r['inputs']['source_provenance']
                        if source['observed_consumption'] == 'observed']
            self.assertTrue(observed)
            self.assertTrue(all(source['consumption_event_refs'] for source in observed))
            self.assertTrue(all(source['consumption_evidence_level'] == 'reported_by_execution_function' for source in observed))
            self.assertIsNone(report['usage']['complete_cost_totals'])
            self.assertEqual(store.facts('csv-demo')['user'][0]['content'], 'Explain outcomes in Chinese.')


if __name__ == '__main__':
    unittest.main()
