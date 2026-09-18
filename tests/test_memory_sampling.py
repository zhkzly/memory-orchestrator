"""Actual local callback execution; constructed tasks are not benchmark evidence."""
import tempfile
import threading
import unittest
from concurrent.futures import CancelledError

from memory_orchestrator.sampling import sample_tasks
from memory_orchestrator.schemas import DomainError
from memory_orchestrator.store import Store
from memory_orchestrator.report import report
from memory_orchestrator.evidence import build_packet, index_episodes
import json


class SamplingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.tasks = [{'project_id': 'p', 'task_id': 'csv', 'revision': '1',
                       'description': 'csv identifiers', 'input': '001,2', 'criteria': {'expected': '001'}}]
        self.policy = {'repeat_count': 3, 'max_parallel': 2, 'purpose': 'learning',
                       'update_mode': 'frozen_microbatch', 'protocol_id': 'local/v1',
                       'executor': {'id': 'csv/v1', 'config': {}}}
        self.context_policy = {'max_roots': 2, 'max_context_chars': 5000, 'relation_weight': 0.0}

    def run_samples(self, execute, evaluate=None, **overrides):
        return sample_tasks(self.store, self.tasks, execute, evaluate,
                            policy={**self.policy, **overrides}, context_policy=self.context_policy)

    def test_plan_precedes_calls_every_attempt_survives_and_criteria_hidden(self):
        observed = []
        lock = threading.Lock()
        def execute(request, snapshot, case):
            self.assertTrue(self.store.list('run_groups', project_id='p'))
            self.assertNotIn('criteria', case['task'])
            self.assertEqual(request['snapshot_digest'], snapshot['snapshot_id'])
            with lock:
                observed.append(request['request_id'])
            if request['repeat_index'] == 1:
                raise RuntimeError('intentional second-slot failure')
            return {'artifact': case['task']['input'].split(',')[0]}
        def evaluate(request, execution, case):
            return {'outcome': 'pass', 'score': 1.0, 'source': 'executable',
                    'evidence': [execution['artifact'] == case['criteria']['expected']]}
        result = self.run_samples(execute, evaluate)
        self.assertEqual(len(observed), 3)
        self.assertEqual(len(result['episodes']), 3)
        runs = self.store.list('runs', project_id='p')
        self.assertEqual(sum(r['execution_status'] == 'adapter_error' for r in runs), 1)
        self.assertEqual(len({r['snapshot_digest'] for r in runs}), 1)
        self.assertTrue(all(not r['comparability'] for r in runs))
        outcomes = [f['outcome'] for e in result['episodes'] for f in self.store.feedback_for(e['episode_id'])]
        self.assertCountEqual(outcomes, ['pass', 'unknown', 'pass'])

    def test_wrong_callback_identity_becomes_unknown_with_raw_evidence(self):
        result = self.run_samples(lambda *args: {'artifact': '001', 'request_id': 'wrong'}, repeat_count=1)
        run = self.store.get('runs', result['run_ids'][0])
        self.assertEqual(run['execution_status'], 'adapter_error')
        raw = self.store.get('executions', result['run_ids'][0])
        self.assertEqual(raw['output']['request_id'], 'wrong')
        feedback = self.store.feedback_for(result['episodes'][0]['episode_id'])[0]
        self.assertEqual(feedback['outcome'], 'unknown')

    def test_final_samples_cannot_enable_learning(self):
        with self.assertRaises(DomainError):
            self.run_samples(lambda *args: {}, purpose='final', update_mode='frozen_microbatch')
        result = self.run_samples(lambda *args: {'artifact': '001'}, purpose='final', update_mode='none')
        plan = self.store.get('run_groups', result['plan_ids'][0])
        self.assertFalse(plan['learning_enabled'])
        self.assertTrue(all(self.store.feedback_for(e['episode_id'])[0]['visibility'] == 'final_only'
                            for e in result['episodes']))

    def test_partial_events_survive_noncompleted_terminal_results(self):
        for terminal in ('timeout', 'cancelled', 'budget_exhausted'):
            with self.subTest(terminal=terminal):
                output = {'execution_status': terminal, 'artifact': 'partial', 'events': [
                    {'event_id': 'read', 'kind': 'action', 'text': 'read before interruption', 'call_id': 'c1'},
                    {'event_id': 'seen', 'kind': 'observation', 'text': 'partial original evidence',
                     'call_id': 'c1', 'parent_event_id': 'read'}]}
                result = self.run_samples(lambda *args: output, repeat_count=1)
                ep = result['episodes'][0]
                self.assertTrue(any(e['text'] == 'partial original evidence' for e in ep['events']))
                self.assertFalse(any('events were not supplied' in gap for gap in ep['gaps']))
                child = next(e for e in ep['events'] if e['text'] == 'partial original evidence')
                self.assertEqual(child['parent_event_id'], 'observation_0')
                self.assertEqual(self.store.get('runs', result['run_ids'][0])['execution_status'], terminal)

    def test_known_initial_state_mismatch_is_explicit_not_missing(self):
        from memory_orchestrator.schemas import digest
        self.tasks[0]['initial_state_digest'] = digest('planned')
        result = self.run_samples(lambda *args: {'artifact': '001',
            'initial_state_digest': digest('observed'), 'environment_instance_id': 'env'}, repeat_count=1)
        run = self.store.get('runs', result['run_ids'][0])
        self.assertEqual(run['execution_status'], 'completed')
        self.assertEqual(run['initial_state_binding'], {'expected': digest('planned'),
            'reported': digest('observed'), 'status': 'mismatched'})
        self.assertTrue(any('initial-state mismatch' in gap.lower() for gap in run['capture_gaps']))
        self.assertFalse(any('did not report both' in gap for gap in run['capture_gaps']))

    def test_scoring_policy_is_frozen_and_terminal_status_is_not_outcome(self):
        calls = []
        def execute(*args):
            plans = self.store.list('run_groups', project_id='p')
            self.assertTrue(all('scoring_policy' in plan for plan in plans))
            return {'execution_status': 'cancelled', 'artifact': '001'}
        def evaluate(*args):
            calls.append('evaluated')
            return {'outcome': 'pass', 'score': 1.0, 'source': 'executable', 'evidence': ['checked partial artifact']}
        default = self.run_samples(execute, evaluate, repeat_count=1)
        self.assertEqual(calls, [])
        assessed = self.run_samples(execute, evaluate, repeat_count=1, scoring_policy='available_artifact')
        self.assertEqual(calls, ['evaluated'])
        run = self.store.get('runs', assessed['run_ids'][0])
        self.assertEqual(run['execution_status'], 'cancelled')
        assessment = self.store.get('assessments', run['assessment_ref'])
        self.assertEqual(assessment['run_id'], run['run_id'])
        self.assertEqual(assessment['outcome'], 'pass')
        feedback = self.store.get('feedback', assessment['criterion_feedback_ids'][0])
        self.assertEqual(feedback['subject_ref'], assessed['episodes'][0]['episode_id'])
        self.assertEqual(assessment['subject_ref'], feedback['subject_ref'])
        self.assertEqual(assessment['aggregation_rule'], 'single_task_outcome')
        unknown = self.store.get('assessments', self.store.get('runs', default['run_ids'][0])['assessment_ref'])
        self.assertEqual(unknown['outcome'], 'unknown')

    def test_available_artifact_never_bypasses_wrong_identity(self):
        called = []
        result = self.run_samples(lambda *args: {'artifact': '001', 'execution_status': 'timeout', 'request_id': 'wrong'},
                                 lambda *args: called.append(args), repeat_count=1, scoring_policy='available_artifact')
        self.assertEqual(called, [])
        self.assertEqual(self.store.get('runs', result['run_ids'][0])['execution_status'], 'adapter_error')

    def test_closed_source_checks_actual_slots_runs_and_receipt(self):
        from memory_orchestrator.lineage import require_learning_source
        result = self.run_samples(lambda *args: {'artifact': '001'}, repeat_count=2)
        ep = result['episodes'][0]
        self.assertTrue(require_learning_source(self.store, ep)['known'])
        receipt_id = result['receipt_ids'][0]
        path = self.store._record_path('group_receipts', receipt_id)
        original = path.read_bytes()
        path.unlink()
        with self.assertRaises(DomainError) as raised: require_learning_source(self.store, ep)
        self.assertEqual(raised.exception.code, 'learning_not_permitted')
        path.write_bytes(original)
        missing_run = self.store._record_path('runs', result['run_ids'][1])
        run_bytes = missing_run.read_bytes(); missing_run.unlink()
        with self.assertRaises(DomainError): require_learning_source(self.store, ep)
        missing_run.write_bytes(run_bytes)
        receipt = self.store.get('group_receipts', receipt_id)
        path.unlink()
        self.store.put('group_receipts', receipt_id, {**receipt, 'run_ids': [result['run_ids'][0]], 'all_slots_accounted': True})
        with self.assertRaises(DomainError): require_learning_source(self.store, ep)
        path.write_bytes(original)
        self.assertTrue(require_learning_source(self.store, ep)['known'])

    def test_frozen_microbatch_requires_every_member_group_to_close(self):
        from memory_orchestrator.lineage import require_learning_source
        self.tasks.append({**self.tasks[0], 'task_id': 'csv-second'})
        result = self.run_samples(lambda *args: {'artifact': '001'}, repeat_count=1, update_mode='frozen_microbatch')
        first = self.store.get('run_groups', result['plan_ids'][0])
        batch = self.store.get('sampling_batches', first['batch_ref'])
        self.assertCountEqual(batch['group_ids'], result['plan_ids'])
        self.assertTrue(require_learning_source(self.store, result['episodes'][0])['known'])
        other_receipt = self.store._record_path('group_receipts', result['receipt_ids'][1])
        original = other_receipt.read_bytes(); other_receipt.unlink()
        with self.assertRaises(DomainError): require_learning_source(self.store, result['episodes'][0])
        other_receipt.write_bytes(original)
        self.assertTrue(require_learning_source(self.store, result['episodes'][0])['known'])

    def test_invalid_or_unbounded_sampling_rejected_before_any_call(self):
        calls = []
        for count in (0, True, -1):
            with self.assertRaises(DomainError):
                self.run_samples(lambda *args: calls.append(args), repeat_count=count)
        self.assertEqual(calls, [])

    def test_non_object_callback_returns_are_retained_as_unknown(self):
        result = self.run_samples(lambda *args: ['invalid', 'execution'], repeat_count=1)
        self.assertEqual(self.store.get('executions', result['run_ids'][0])['output'], ['invalid', 'execution'])
        self.assertEqual(self.store.feedback_for(result['episodes'][0]['episode_id'])[0]['outcome'], 'unknown')

    def test_native_parent_event_ids_are_mapped_and_bad_links_terminalize(self):
        def execute(*args):
            return {'artifact': '001', 'events': [
                {'event_id': 'read-1', 'kind': 'action', 'text': 'read csv'},
                {'event_id': 'result-1', 'kind': 'result', 'text': '001', 'parent_event_id': 'read-1'}]}
        result = self.run_samples(execute, repeat_count=2)
        self.assertEqual(len(result['run_ids']), 2)
        for ep in result['episodes']:
            parent = next(e for e in ep['events'] if e['text'] == 'read csv')
            child = next(e for e in ep['events'] if e['text'] == '001')
            self.assertEqual(child['parent_event_id'], parent['event_id'])
        bad = self.run_samples(lambda *args: {'artifact': None, 'events': [
            {'event_id': 'child', 'kind': 'result', 'text': 'bad link', 'parent_event_id': 'absent'}]}, repeat_count=1)
        self.assertEqual(self.store.get('runs', bad['run_ids'][0])['execution_status'], 'adapter_error')
        self.assertTrue(self.store.get('group_receipts', bad['receipt_ids'][0])['all_slots_accounted'])

    def test_cancelled_and_budget_exhausted_are_not_completed_or_task_failure(self):
        for status in ('cancelled', 'budget_exhausted', 'timeout'):
            result = self.run_samples(lambda *args: {'execution_status': status}, repeat_count=1)
            self.assertEqual(self.store.get('runs', result['run_ids'][0])['execution_status'], status)
            self.assertEqual(self.store.get('group_receipts', result['receipt_ids'][0])['completed'], 0)
            self.assertEqual(self.store.feedback_for(result['episodes'][0]['episode_id'])[0]['outcome'], 'unknown')
        def cancelled(*args):
            raise CancelledError('cancelled by caller')
        result = self.run_samples(cancelled, repeat_count=1)
        self.assertEqual(self.store.get('runs', result['run_ids'][0])['execution_status'], 'cancelled')

    def test_actual_inputs_and_private_criteria_are_persisted_before_execution(self):
        def execute(request, snapshot, case):
            inputs = self.store.get('sampling_inputs', request['input_ref'])
            self.assertEqual(inputs['task'], self.tasks[0])
            self.assertEqual(inputs['policy']['executor'], self.policy['executor'])
            self.assertEqual(inputs['public_case'], case)
            self.assertNotIn('criteria', case['task'])
            return {'artifact': '001'}
        result = self.run_samples(execute, repeat_count=1)
        self.assertEqual(self.store.get('runs', result['run_ids'][0])['execution_status'], 'completed')
        first = result['episodes'][0]['events'][0]
        self.assertIn('sampling_input_', first['source_ref'])

    def test_absent_or_cyclic_raw_parents_cannot_bind_host_event_ids(self):
        for parent in ('instruction', 'result', 'observation_0', 'child'):
            events = [{'event_id': 'child', 'kind': 'result', 'text': 'orphan', 'parent_event_id': parent}]
            result = self.run_samples(lambda *args: {'artifact': None, 'events': events}, repeat_count=1)
            self.assertEqual(self.store.get('runs', result['run_ids'][0])['execution_status'], 'adapter_error')
            self.assertEqual(self.store.get('executions', result['run_ids'][0])['output']['events'], events)
        events = [{'event_id': 'a', 'kind': 'action', 'text': 'a', 'parent_event_id': 'b'},
                  {'event_id': 'b', 'kind': 'result', 'text': 'b', 'parent_event_id': 'a'}]
        result = self.run_samples(lambda *args: {'artifact': None, 'events': events}, repeat_count=1)
        self.assertEqual(self.store.get('runs', result['run_ids'][0])['execution_status'], 'adapter_error')

    def test_malformed_optional_trace_fields_do_not_lose_attempts(self):
        outputs = [{'artifact': None, 'events': None},
                   {'artifact': None, 'events': [{'event_id': 'a', 'kind': 'action', 'text': 'x', 'parent_event_id': {}}]},
                   {'artifact': None, 'events': [], 'consumption_events': [{'skill_id': [], 'event_id': []}]}]
        for output in outputs:
            result = self.run_samples(lambda *args: output, repeat_count=1)
            self.assertEqual(len(result['run_ids']), 1)
            self.assertTrue(self.store.get('group_receipts', result['receipt_ids'][0])['all_slots_accounted'])

    def test_invalid_callback_usage_remains_missing_and_does_not_break_report(self):
        value = {'tokens': {'input_tokens': 1.5, 'output_tokens': True, 'total_tokens': 9},
                 'currency': [], 'monetary_cost': -2}
        result = self.run_samples(lambda *args: {'artifact': '001', 'usage': value}, repeat_count=1)
        run = self.store.get('runs', result['run_ids'][0])
        usage = self.store.get('usage', run['usage_refs'][0])
        self.assertEqual(usage['raw_usage'], value)
        self.assertEqual(usage['tokens'], {'input_tokens': None, 'output_tokens': None, 'total_tokens': 9})
        self.assertEqual(len(usage['diagnostics']), 4)
        self.assertIsNone(report(self.store, 'p')['usage']['complete_cost_totals'])

    def test_rich_inputs_and_checker_evidence_are_available_to_extraction(self):
        self.tasks[0]['input'] = 'PUBLIC_INPUT_SENTINEL_001'
        self.tasks[0]['private'] = {'secret_answer': 'PRIVATE_CRITERIA_SENTINEL'}
        result = self.run_samples(lambda *args: {'artifact': 'wrong-output'},
            lambda *args: {'outcome': 'fail', 'score': 0.0, 'source': 'executable',
                          'evidence': [{'expected': 'EXPECTED_EVIDENCE_SENTINEL', 'actual': 'wrong-output'}],
                          'reason': 'Typed comparison mismatch'}, repeat_count=1)
        episode = result['episodes'][0]
        feedback = self.store.feedback_for(episode['episode_id'])
        index = index_episodes([episode], feedback=feedback,
                              contexts={episode['context_ref']: self.store.get('contexts', episode['context_ref'])})
        packet = build_packet(index, limits={'max_chars': 12000, 'max_fragment_chars': 3000,
                                              'max_catalog_refs': 8, 'token_budget': 10000})
        visible = json.dumps(packet, ensure_ascii=False)
        self.assertIn('PUBLIC_INPUT_SENTINEL_001', visible)
        self.assertIn('EXPECTED_EVIDENCE_SENTINEL', visible)
        self.assertNotIn('PRIVATE_CRITERIA_SENTINEL', visible)
        result = self.run_samples(lambda *args: {'artifact': '001'}, lambda *args: ['invalid', 'score'], repeat_count=1)
        self.assertEqual(self.store.feedback_for(result['episodes'][0]['episode_id'])[0]['outcome'], 'unknown')


if __name__ == '__main__':
    unittest.main()
