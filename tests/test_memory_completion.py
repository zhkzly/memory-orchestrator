"""Consumers for the full contract, derived from the existing CSV fixtures."""
import tempfile
import unittest
from unittest.mock import patch

from memory_orchestrator.context import select_context
from memory_orchestrator.report import report
from memory_orchestrator.store import Store
from memory_orchestrator.sampling import _record_consumption, sample_tasks
from test_memory_context import skill


class CompletionConsumers(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.task = {'project_id': 'p', 'task_id': 'csv', 'revision': '1',
                     'description': 'csv identifiers', 'task_family': 'csv'}
        self.policy = {'max_roots': 2, 'max_context_chars': 5000, 'relation_weight': 0.5}

    def test_current_task_filters_unrelated_project_facts_before_budget(self):
        self.store.remember('user', 'reply in Chinese', 'explicit user preference')
        self.store.remember('project', 'GPU drivers require version 9', 'explicit fact', project_id='p')
        self.store.remember('project', 'CSV identifiers stay text', 'explicit fact', project_id='p')
        before = self.store.facts('p')
        selected = select_context(self.store, self.task, self.policy)
        self.assertIn('CSV identifiers stay text', selected['supplied_text'])
        self.assertNotIn('GPU drivers', selected['supplied_text'])
        self.assertIn('reply in Chinese', selected['supplied_text'])
        self.assertEqual(before, self.store.facts('p'))
        self.assertTrue(any(row.get('reason') == 'task_relevance' for row in selected['exclusions']))

    def test_selection_has_actual_maintenance_time_in_report(self):
        select_context(self.store, self.task, self.policy)
        result = report(self.store, 'p')
        measured = result['maintenance']['by_stage']['select']
        self.assertGreaterEqual(measured['local_seconds'], 0)
        self.assertGreaterEqual(measured['measurements'], 1)
        self.assertGreaterEqual(measured['unpriced_measurements'], 1)
        self.assertIsNone(result['maintenance']['complete_cost_totals'])

    def test_co_use_from_another_task_or_revision_does_not_change_selection(self):
        snapshot = self.store.save_snapshot('p', {key: skill(key) for key in ('a', 'b', 'c')}, {})
        manifest = select_context(self.store, self.task, {**self.policy, 'max_roots': 3},
                                  explicit_snapshot=snapshot['snapshot_id'])
        output = {'events': [{'event_id': key, 'source_role': 'tool', 'kind': 'action'} for key in ('a', 'c')],
                  'consumption_events': [{'skill_id': key, 'event_id': key} for key in ('a', 'c')]}
        self.store.put('executions', 'run', {'project_id': 'p', 'run_id': 'run', 'output': output})
        _record_consumption(self.store, 'p', manifest, output, 'run', learn_relations=True)
        same = select_context(self.store, self.task, self.policy, explicit_snapshot=snapshot['snapshot_id'])
        self.assertEqual([r['skill_id'] for r in same['roots']], ['a', 'c'])
        other = select_context(self.store, {**self.task, 'task_id': 'different'}, self.policy,
                               explicit_snapshot=snapshot['snapshot_id'])
        self.assertEqual([r['skill_id'] for r in other['roots']], ['a', 'b'])
        changed = self.store.snapshot(snapshot['snapshot_id'])['skills']
        changed['c']['revision'] = 'r2'
        changed['c']['content']['steps'].append('A new unrelated rule.')
        newer = self.store.save_snapshot('p', changed, {}, parent=snapshot['snapshot_id'])
        result = select_context(self.store, self.task, self.policy, explicit_snapshot=newer['snapshot_id'])
        self.assertEqual([r['skill_id'] for r in result['roots']], ['a', 'b'])
        self.assertIn('skill_revision', [r['reason'] for r in result['relation_filters'] if not r['eligible']])

    def test_multi_criterion_assessment_is_consumed_by_sampling_report(self):
        policy = {'repeat_count': 1, 'max_parallel': 1, 'purpose': 'learning', 'update_mode': 'task_barrier',
                  'protocol_id': 'multi-csv', 'executor': {'id': 'local-csv', 'config': {}},
                  'evaluator': {'id': 'local-check', 'config': {}}, 'feedback': {
                      'criteria': [{'criterion_id': 'identifier', 'rule': {'expected': '001'}, 'weight': 1},
                                   {'criterion_id': 'total', 'rule': {'expected': 3}, 'weight': 3}],
                      'aggregation': {'kind': 'weighted_sum', 'threshold': 0.75}}}
        def execute(*args):
            return {'artifact': {'identifier': '001', 'total': 0}}
        def evaluate(request, output, case):
            good = output['artifact'][request['criterion_id']] == case['criteria']['expected']
            return {'outcome': 'pass' if good else 'fail', 'score': float(good),
                    'source': 'executable', 'evidence': [{'actual': output['artifact'], 'expected': case['criteria']} ]}
        sampled = sample_tasks(self.store, [self.task], execute, evaluate, policy=policy, context_policy=self.policy)
        self.assertEqual(sampled['status'], 'completed')
        result = report(self.store, 'p')
        row = result['sampling']['groups'][0]['results'][0]
        self.assertEqual((row['outcome'], row['score']), ('fail', 0.25))
        self.assertEqual(row['criterion_coverage'], 1.0)
        self.assertEqual(set(row['criterion_ids']), {'identifier', 'total'})
        self.assertEqual(row['feedback_sources'], ['external'])

    def test_two_actual_releases_and_rollback_reach_longitudinal_report(self):
        from examples.memory_evolution.demo import run_demo
        result = run_demo(self.temp.name)['report']
        history = result['library_history']
        self.assertEqual([r['generation'] for r in history], [0, 1, 2, 3])
        self.assertEqual([r['skill_count'] for r in history], [0, 1, 1, 1])
        self.assertEqual(history[1]['snapshot_digest'], history[3]['snapshot_digest'])
        self.assertEqual(history[-1]['kind'], 'rollback')
        layers = result['consumption_layers']
        self.assertTrue(layers['provided_manifest_counts'])
        self.assertGreater(layers['observed_level_counts'].get('read', 0), 0)
        self.assertEqual(layers['observed_level_counts'].get('behavior', 0), 0)
        self.assertEqual(layers['effect_records'], [])
        walls = result['batch_wall_time']
        self.assertEqual(len(walls['sampling']), 4)
        self.assertEqual(len(walls['comparison']), 2)
        self.assertTrue(all(r['complete_active_wall_seconds'] is not None for r in walls['sampling']))
        self.assertEqual(result['memory_progress']['necessity_verdicts'], {'proceed': 2})
        self.assertIn('publish', result['maintenance']['by_stage'])
        own = self.store.get('stage_measurements', result['report_measurement_ref'])
        self.assertEqual(own['stage'], 'report')
        self.assertNotIn(own['measurement_id'], result['maintenance']['measurement_ids'])

    def test_a_later_priced_callback_does_not_erase_an_unreturned_attempt(self):
        from memory_orchestrator.feedback import call_recorded
        calls = []
        def execute():
            calls.append('executed')
            return {'artifact': 'done', 'usage': {'monetary_cost': 1, 'currency': 'test-unit',
                    'tokens': {'input_tokens': 2, 'output_tokens': 3, 'total_tokens': 5}}}
        original = self.store.put
        def interrupt_before_callback(kind, identifier, value):
            result = original(kind, identifier, value)
            if kind == 'callback_attempts':
                raise KeyboardInterrupt('Interruption before the callback was invoked')
            return result
        args = dict(project_id='p', batch_id=None, run_id='run', request_ref='request',
                    stage='execute', config={}, purpose='learning', subject_ref='run', callback=execute, args=())
        with patch.object(self.store, 'put', side_effect=interrupt_before_callback):
            with self.assertRaises(KeyboardInterrupt):
                call_recorded(self.store, **args)
        self.assertEqual(calls, [])
        call_recorded(self.store, **args, resolutions={'request': {
            'action': 'confirmed_not_executed', 'source': 'test callback invocation log',
            'evidence': ['Interruption occurred after started was saved and before callback invocation.']}})
        observed = report(self.store, 'p')['usage']
        self.assertEqual(calls, ['executed'])
        self.assertEqual(observed['callback_attempts'], 2)
        self.assertEqual(len(observed['unreturned_attempt_ids']), 1)
        self.assertEqual(observed['known_cost_subtotals'], {'test-unit': 1})
        self.assertIsNone(observed['complete_cost_totals'])
        self.assertTrue(all(value is None for value in observed['tokens']['complete_totals'].values()))

    def test_interrupted_model_learning_keeps_reported_costs_incomplete(self):
        from memory_orchestrator.learning import learn
        from memory_orchestrator.model import StructuredModel
        from test_memory_learning import policy
        from test_memory_evidence import episode
        from test_memory_model import limits
        source = episode()
        self.store.add_episode(source)
        entered = []
        def interrupted(request):
            entered.append(request['prompt_id'])
            raise KeyboardInterrupt('Interrupt during provider invocation')
        with self.assertRaises(KeyboardInterrupt):
            learn(self.store, [source['episode_id']], StructuredModel(interrupted, limits=limits()), policy=policy())
        self.assertEqual(len(entered), 1)
        reopened = Store(self.temp.name)
        observed = report(reopened, source['project_id'])['usage']
        self.assertIsNone(observed['complete_cost_totals'])
        self.assertEqual(len(observed['unfinished_learning_cycle_ids']), 1)
        self.assertTrue(all(value is None for value in observed['tokens']['complete_totals'].values()))


if __name__ == '__main__':
    unittest.main()
