"""Actual CSV tasks across three protocols; no benchmark/LLM gain claim."""
from copy import deepcopy
import tempfile
import unittest

from examples.memory_evolution.demo import task, callbacks, ScriptedTeacher, CONTEXT, LEARNING, protocol as compare_protocol
from memory_orchestrator.experiments import audit_splits, run_experiment
from memory_orchestrator.schemas import DomainError
from memory_orchestrator.store import Store
from examples.memory_evolution.study import dataset




class ExperimentTests(unittest.TestCase):
    def test_retained_caller_config_cannot_change_frozen_arm_execution(self):
        with tempfile.TemporaryDirectory() as root:
            config = {'id': 'freeze-inputs', 'project_id': 'csv-demo', 'modes': ['online', 'frozen'],
                      'microbatch_size': 2, 'max_learning_cycles_per_arm': 0, 'max_model_calls_per_arm': 0,
                      'model_config': {}, 'unseen_scope': 'instance'}
            sampling = {'repeat_count': 2, 'max_parallel': 2, 'protocol_id': 'csv-sampling',
                        'executor': {'id': 'local-csv/v1', 'config': {}}}
            context = deepcopy(CONTEXT)
            seed = {'skills': {}, 'assets': {}}
            def runtime(store):
                # Mutation occurs after the immutable experiment plan was written.
                sampling['repeat_count'] = 3
                context['max_roots'] = 0
                seed['assets']['unowned/references/data'] = 'changed initial contents'
                execute, evaluate = callbacks(store)
                return {'execute': execute, 'evaluate': evaluate}
            result = run_experiment(root, dataset(), runtime, lambda _: self.fail('No learning budget'),
                protocol=config, sampling_policy=sampling, context_policy=context, learning_policy=LEARNING,
                comparison_protocol=compare_protocol('fixed'), seed=seed)
            self.assertEqual(len({arm['baseline']['snapshot_id'] for arm in result['arms']}), 1)
            control = Store(root + '/freeze-inputs/control')
            self.assertEqual(control.get('experiment_plans', 'freeze-inputs')['sampling_policy']['repeat_count'], 2)
            for arm in result['arms']:
                store = Store(arm['store_root'])
                self.assertTrue(all(group['k'] == 2 for group in store.list('run_groups')))

    def test_real_same_core_runs_all_modes_with_frozen_final_and_equal_budgets(self):
        with tempfile.TemporaryDirectory() as root:
            config = {'id': 'study', 'project_id': 'csv-demo', 'modes': ['online','frozen','frozen_microbatch'],
                      'microbatch_size': 2, 'max_learning_cycles_per_arm': 2, 'max_model_calls_per_arm': 24,
                      'model_config': {'model': 'scripted-test-double'}, 'unseen_scope': 'instance',
                      'evidence_kind': 'constructed CSV protocol integration'}
            sampling = {'repeat_count': 2, 'max_parallel': 2, 'protocol_id': 'csv-sampling',
                        'executor': {'id': 'local-csv/v1', 'config': {}},
                        'evaluator': {'id': 'typed-row-check/v1', 'config': {}}}
            comparison = compare_protocol('csv-study-comparison')
            comparison['criteria']['maximum_evaluation_calls'] = 12
            def runtime(store):
                execute, evaluate = callbacks(store)
                return {'execute': execute, 'evaluate': evaluate}
            result = run_experiment(root, dataset(), runtime, lambda store: ScriptedTeacher(), protocol=config,
                sampling_policy=sampling, context_policy=CONTEXT, learning_policy=LEARNING, comparison_protocol=comparison)
            arms = {row['mode']: row for row in result['arms']}
            self.assertEqual(set(arms), set(config['modes']))
            self.assertEqual({row['baseline']['snapshot_id'] for row in arms.values()}, {arms['frozen']['baseline']['snapshot_id']})
            self.assertEqual(arms['frozen']['learning_cycles'], 0)
            self.assertEqual(arms['online']['learning_cycles'], 2)
            self.assertEqual(arms['frozen_microbatch']['learning_cycles'], 1)
            self.assertTrue(all(row['model_calls'] <= 24 for row in arms.values()))
            self.assertTrue(all(row['status'] == 'completed' for row in arms.values()))
            for mode, row in arms.items():
                store = Store(row['store_root'])
                final_groups = [g for g in store.list('run_groups') if g['purpose'] == 'final']
                self.assertEqual(len(final_groups), 2)
                self.assertTrue(all(g['update_mode'] == 'none' and not g['learning_enabled'] for g in final_groups))
                self.assertEqual({g['snapshot_digest'] for g in final_groups}, {row['final_snapshot']['snapshot_id']})
                if mode != 'frozen':
                    self.assertTrue(all(step['pre_update_quality']['planned_runs'] >= 2 for step in row['adaptation_steps']))
            self.assertEqual(len(result['differences_vs_frozen']), 2)
            self.assertTrue(all(len(row['cases']) == 2 for row in result['differences_vs_frozen']))
            self.assertGreater(arms['online']['final_snapshot']['generation'], 0)

    def test_split_audit_rejects_source_and_content_leakage_without_claiming_unknown_provenance(self):
        original = dataset()
        self.assertEqual(audit_splits(original, unseen_scope='instance')['unseen_scope'], 'instance')
        for field in ('source_id', 'task_id'):
            changed = deepcopy(original)
            changed['final'][0][field] = changed['adaptation'][0][field]
            with self.subTest(field=field), self.assertRaises(DomainError):
                audit_splits(changed, unseen_scope='instance')
        missing = deepcopy(original);del missing['final'][0]['source_id']
        with self.assertRaises(DomainError):
            audit_splits(missing, unseen_scope='instance')
        self.assertTrue(audit_splits(missing, unseen_scope='none')['missing_metadata']['final'])
        with self.assertRaises(DomainError):
            audit_splits(original, unseen_scope='family')


if __name__ == '__main__':
    unittest.main()
