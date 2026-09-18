"""Whole local flow with an explicit scripted teacher, not a learning benchmark."""
import importlib.util
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
                    self.assertEqual(result['report']['candidate_counts']['rejected'], 1)

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
