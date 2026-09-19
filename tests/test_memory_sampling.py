"""Actual local callback execution; constructed tasks are not benchmark evidence."""
import tempfile
import threading
import unittest
from concurrent.futures import CancelledError

from memory_orchestrator.sampling import sample_tasks
from memory_orchestrator.schemas import DomainError, digest
from memory_orchestrator.store import Store
from memory_orchestrator.report import report
from memory_orchestrator.evidence import build_packet, index_episodes
import json
import subprocess
import sys
from unittest.mock import patch


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

    def test_resume_rebuilds_from_saved_return_without_reexecution_or_double_usage(self):
        from memory_orchestrator.sampling import prepare_sampling, resume_sampling
        batch = prepare_sampling(self.store, self.tasks, policy={**self.policy, 'repeat_count': 1}, context_policy=self.context_policy)
        calls = []
        def execute(*args):
            calls.append('execute')
            return {'artifact': '001', 'usage': {'tokens': {'input_tokens': 4, 'output_tokens': 2, 'total_tokens': 6}}}
        with patch.object(self.store, 'add_episode', side_effect=KeyboardInterrupt('after original return')):
            with self.assertRaises(KeyboardInterrupt):
                resume_sampling(self.store, batch['batch_id'], execute, None)
        self.assertEqual(len(self.store.list('callback_returns', 'p')), 1)
        reopened = Store(self.temp.name)
        result = resume_sampling(reopened, batch['batch_id'], execute, None)
        self.assertEqual(calls, ['execute'])
        self.assertEqual(result['blocked'], [])
        before = reopened.list('usage', 'p')
        self.assertEqual(len(before), 1)
        self.assertEqual(before[0]['tokens']['total_tokens'], 6)
        again = resume_sampling(reopened, batch['batch_id'], execute, None)
        self.assertEqual(result, again)
        self.assertEqual(reopened.list('usage', 'p'), before)
        self.assertEqual(len(result['run_ids']), 1)

    def test_host_terminal_result_keeps_artifact_identity(self):
        result = self.run_samples(lambda *args: {'artifact': {'value': '001'}}, repeat_count=1)
        episode = result['episodes'][0]
        terminal = episode['events'][-1]
        self.assertEqual((terminal['event_id'], terminal['kind'], terminal['source_role']),
                         ('result', 'result', 'environment'))
        self.assertEqual(json.loads(terminal['text'])['artifact'], {'value': '001'})
        state = digest({'value': '001'})
        self.assertEqual(terminal['resources'], [{
            'kind': 'artifact', 'ref': 'evaluated-state:' + state,
            'access': 'check', 'version_ref': state,
        }])

    def test_started_without_return_blocks_until_explicit_original_result(self):
        from memory_orchestrator.sampling import prepare_sampling, resume_sampling
        batch = prepare_sampling(self.store, self.tasks, policy={**self.policy, 'repeat_count': 1}, context_policy=self.context_policy)
        calls = []
        def interrupted(*args):
            calls.append('maybe executed')
            raise KeyboardInterrupt('unknown result')
        with self.assertRaises(KeyboardInterrupt):
            resume_sampling(self.store, batch['batch_id'], interrupted, None)
        blocked = resume_sampling(self.store, batch['batch_id'], interrupted, None)
        self.assertEqual(len(blocked['blocked']), 1)
        self.assertEqual(calls, ['maybe executed'])
        request_ref = blocked['blocked'][0]['request_ref']
        final = resume_sampling(self.store, batch['batch_id'], interrupted, None, resolutions={request_ref: {
            'action': 'attach_result', 'source': 'local task capture', 'evidence': ['captured original output'],
            'raw_output': {'artifact': '001'}}})
        self.assertFalse(final['blocked'])
        self.assertEqual(calls, ['maybe executed'])
        self.assertEqual(self.store.get('executions', final['run_ids'][0])['output']['artifact'], '001')

    def test_multiple_criteria_are_called_separately_and_weighted_from_original_feedback(self):
        seen = []
        def evaluate(request, execution, case):
            seen.append((request['criterion_id'], case['criteria']))
            passed = request['criterion_id'] == 'identifier'
            return {'outcome': 'pass' if passed else 'fail', 'score': 1.0 if passed else 0.0,
                    'source': 'executable', 'evidence': [case['criteria']]}
        result = self.run_samples(lambda *args: {'artifact': '001'}, evaluate, repeat_count=1, feedback={
            'criteria': [{'criterion_id': 'identifier', 'rule': {'expected': '001'}, 'weight': 1},
                         {'criterion_id': 'total', 'rule': {'expected': 3}, 'weight': 3}],
            'aggregation': {'kind': 'weighted_sum', 'threshold': .75}})
        self.assertEqual([x[0] for x in seen], ['identifier', 'total'])
        assessment = self.store.get('assessments', self.store.get('runs', result['run_ids'][0])['assessment_ref'])
        self.assertEqual((assessment['score'], assessment['outcome']), (.25, 'fail'))
        self.assertEqual(len(assessment['criterion_feedback_ids']), 2)

    def test_proxy_uses_structured_model_budget_and_cannot_be_relabelled_external(self):
        from memory_orchestrator.model import StructuredModel
        from memory_orchestrator.feedback import verify_assessment, check_planned_feedback
        from tests.test_memory_model import limits, response
        calls = []
        def invoke(request):
            calls.append(request)
            text = request['messages'][1]['content'].split('证据：', 1)[1]
            packet, _ = json.JSONDecoder().raw_decode(text)
            ref = packet['fragments'][-1]['ref_id']
            return response({'outcome': 'pass', 'criterion_findings': [{'criterion_id': 'task_outcome',
                'outcome': 'pass', 'score': 1, 'finding': 'Constructed proxy sees result', 'evidence_refs': [ref]}], 'unknowns': []})
        model_limits = limits(max_calls=1, max_format_repairs=0)
        model = StructuredModel(invoke, limits=model_limits)
        result = sample_tasks(self.store, self.tasks, lambda *args: {'artifact': '001'}, None,
            policy={**self.policy, 'repeat_count': 1, 'feedback': {'criteria': [{'criterion_id': 'task_outcome', 'rule': self.tasks[0]['criteria']}],
                'aggregation': {'kind': 'single_task_outcome'}, 'proxy': {'enabled': True, 'model_config': {'model': 'synthetic'},
                    'limits': model_limits, 'packet_limits': {'max_chars': 6000, 'max_fragment_chars': 400, 'max_catalog_refs': 8, 'token_budget': 4000}}}},
            context_policy=self.context_policy, proxy_model=model)
        self.assertEqual(len(calls), 1)
        verified = verify_assessment(self.store, self.store.get('runs', result['run_ids'][0])['assessment_ref'])
        self.assertEqual(verified['aggregate']['feedback_sources'], ['llm_proxy'])
        self.assertEqual(verified['aggregate']['outcome'], 'pass')
        with self.assertRaises(DomainError):
            check_planned_feedback(self.store, verified['plan'], {**verified['feedbacks'][0], 'source': 'external'})
        proxy_usage = [u for u in self.store.list('usage', 'p') if u['exclusive_stage'] == 'evaluate']
        self.assertEqual(proxy_usage[0]['tokens']['input_tokens'], 11)

    def test_proxy_unseen_reference_repairs_inside_same_budget_and_keeps_both_costs(self):
        from memory_orchestrator.model import StructuredModel
        from tests.test_memory_model import limits, response
        calls = []
        def invoke(request):
            calls.append(request)
            packet, _ = json.JSONDecoder().raw_decode(request['messages'][1]['content'].split('证据：', 1)[1])
            reference = 'unseen-reference' if len(calls) == 1 else packet['fragments'][-1]['ref_id']
            return response({'outcome': 'pass', 'criterion_findings': [{'criterion_id': 'task_outcome',
                'outcome': 'pass', 'score': 1, 'finding': 'Constructed repair', 'evidence_refs': [reference]}], 'unknowns': []})
        budget = limits(max_calls=2, max_format_repairs=1)
        result = sample_tasks(self.store, self.tasks, lambda *args: {'artifact': '001'}, None,
            policy={**self.policy, 'repeat_count': 1, 'feedback': {'criteria': [{'criterion_id': 'task_outcome', 'rule': self.tasks[0]['criteria']}],
                'aggregation': {'kind': 'single_task_outcome'}, 'proxy': {'enabled': True, 'limits': budget,
                    'packet_limits': {'max_chars': 6000, 'max_fragment_chars': 400, 'max_catalog_refs': 8, 'token_budget': 4000}}}},
            context_policy=self.context_policy, proxy_model=StructuredModel(invoke, limits=budget))
        self.assertEqual(len(calls), 2)
        self.assertIn('unsupported_evidence', str(calls[1]['messages'][-1]))
        usage = [u for u in self.store.list('usage', 'p') if u['exclusive_stage'] == 'evaluate']
        self.assertEqual(len(usage), 2)
        self.assertEqual(sum(u['tokens']['input_tokens'] for u in usage), 22)
        self.assertEqual(self.store.get('assessments', self.store.get('runs', result['run_ids'][0])['assessment_ref'])['outcome'], 'pass')

    def test_proxy_input_budget_exhaustion_does_not_invent_provider_calls(self):
        from memory_orchestrator.model import StructuredModel
        from tests.test_memory_model import limits
        calls = []
        budget = limits(max_input_chars=1, max_calls=1, max_format_repairs=0)
        result = sample_tasks(self.store, self.tasks, lambda *args: {'artifact': '001'}, None,
            policy={**self.policy, 'repeat_count': 1, 'feedback': {'criteria': [{'criterion_id': 'task_outcome', 'rule': self.tasks[0]['criteria']}],
                'aggregation': {'kind': 'single_task_outcome'}, 'proxy': {'enabled': True, 'limits': budget,
                    'packet_limits': {'max_chars': 6000, 'max_fragment_chars': 400, 'max_catalog_refs': 8, 'token_budget': 4000}}}},
            context_policy=self.context_policy, proxy_model=StructuredModel(lambda req: calls.append(req), limits=budget))
        self.assertEqual(calls, [])
        self.assertEqual([u for u in self.store.list('usage', 'p') if u['exclusive_stage'] == 'evaluate'], [])
        assessed = self.store.get('assessments', self.store.get('runs', result['run_ids'][0])['assessment_ref'])
        self.assertEqual(assessed['outcome'], 'unknown')
        feedback = self.store.get('feedback', assessed['criterion_feedback_ids'][0])
        self.assertIn('model_budget_exhausted', feedback['reason'])

    def test_proxy_costs_follow_transport_usage_in_success_failure_and_missing_cases(self):
        from memory_orchestrator.model import StructuredModel
        from tests.test_memory_model import limits, response
        for supplied, malformed in ((True, False), (False, False), (True, True)):
            with self.subTest(supplied=supplied, malformed=malformed), tempfile.TemporaryDirectory() as directory:
                store = Store(directory)
                budget = limits(max_calls=1, max_format_repairs=0)
                def invoke(request):
                    packet, _ = json.JSONDecoder().raw_decode(request['messages'][1]['content'].split('证据：', 1)[1])
                    value = {'outcome': 'pass', 'criterion_findings': [{'criterion_id': 'task_outcome',
                        'outcome': 'pass', 'score': 1, 'finding': 'Generated prose says cost is 999 CNY; this is not measured usage.',
                        'evidence_refs': [packet['fragments'][-1]['ref_id']]}], 'unknowns': []}
                    returned = response('not JSON' if malformed else value)
                    if supplied:
                        returned['usage'].update(monetary_cost=.125, currency='test-unit', price_version='transport-price-v1')
                    return returned
                result = sample_tasks(store, self.tasks, lambda *args: {'artifact': '001'}, None,
                    policy={**self.policy, 'repeat_count': 1, 'feedback': {'criteria': [{'criterion_id': 'task_outcome', 'rule': self.tasks[0]['criteria']}],
                        'aggregation': {'kind': 'single_task_outcome'}, 'proxy': {'enabled': True, 'limits': budget,
                            'packet_limits': {'max_chars': 6000, 'max_fragment_chars': 400, 'max_catalog_refs': 8, 'token_budget': 4000}}}},
                    context_policy=self.context_policy, proxy_model=StructuredModel(invoke, limits=budget))
                usage = [u for u in store.list('usage', 'p') if u['exclusive_stage'] == 'evaluate']
                self.assertEqual(len(usage), 1)
                self.assertEqual(usage[0]['monetary_cost'], .125 if supplied else None)
                self.assertEqual(usage[0]['currency'], 'test-unit' if supplied else None)
                self.assertEqual(usage[0]['price_version'], 'transport-price-v1' if supplied else None)
                assessment = store.get('assessments', store.get('runs', result['run_ids'][0])['assessment_ref'])
                self.assertEqual(assessment['outcome'], 'unknown' if malformed else 'pass')

    def test_recovery_after_each_derived_stage_preserves_complete_inventory(self):
        from memory_orchestrator.sampling import prepare_sampling, resume_sampling
        stages = ('executions', 'feedback', 'assessments', 'runs', 'group_receipts', 'sampling_batch_receipts')
        for stage in stages:
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                store = Store(directory)
                batch = prepare_sampling(store, self.tasks, policy={**self.policy, 'repeat_count': 1}, context_policy=self.context_policy)
                calls, crashed = [], []
                def execute(*args):
                    calls.append('execute'); return {'artifact': '001'}
                def evaluate(*args):
                    calls.append('evaluate'); return {'outcome': 'pass', 'score': 1.0, 'source': 'executable', 'evidence': ['001']}
                put = store.put
                def crash(kind, identifier, record):
                    value = put(kind, identifier, record)
                    if kind == stage and not crashed:
                        crashed.append(stage)
                        raise KeyboardInterrupt('after saved ' + stage)
                    return value
                with patch.object(store, 'put', side_effect=crash):
                    with self.assertRaises(KeyboardInterrupt):
                        resume_sampling(store, batch['batch_id'], execute, evaluate)
                result = resume_sampling(Store(directory), batch['batch_id'], execute, evaluate)
                self.assertEqual(calls, ['execute', 'evaluate'])
                self.assertEqual(result['status'], 'completed')
                self.assertEqual(len(result['episodes']), 1)
                self.assertEqual(len(store.list('executions', 'p')), 1)
                self.assertEqual(len(store.list('runs', 'p')), 1)
                self.assertEqual(len(store.list('feedback', 'p')), 1)
                self.assertEqual(len(store.list('assessments', 'p')), 1)
                self.assertEqual(len(store.list('group_receipts', 'p')), 1)
                self.assertEqual(len(store.list('sampling_batch_receipts', 'p')), 1)
                self.assertEqual(len(store.list('usage', 'p')), 2)

    def test_confirmed_not_executed_and_close_unknown_preserve_original_attempts(self):
        from memory_orchestrator.sampling import prepare_sampling, resume_sampling
        for action in ('confirmed_not_executed', 'close_unknown'):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as directory:
                store = Store(directory)
                batch = prepare_sampling(store, self.tasks, policy={**self.policy, 'repeat_count': 1}, context_policy=self.context_policy)
                def lost(*args): raise KeyboardInterrupt('unknown')
                with self.assertRaises(KeyboardInterrupt): resume_sampling(store, batch['batch_id'], lost, None)
                request_ref = store.list('callback_attempts', 'p')[0]['request_ref']
                calls = []
                def execute(*args): calls.append('run'); return {'artifact': '001'}
                result = resume_sampling(store, batch['batch_id'], execute, None, resolutions={request_ref: {
                    'action': action, 'source': 'explicit executor confirmation', 'evidence': ['confirmed original side-effect status']}})
                self.assertEqual(calls, ['run'] if action == 'confirmed_not_executed' else [])
                self.assertEqual(len(store.list('callback_attempts', 'p')), 2 if action == 'confirmed_not_executed' else 1)
                if action == 'close_unknown':
                    assessment = store.get('assessments', store.get('runs', result['run_ids'][0])['assessment_ref'])
                    self.assertEqual(assessment['outcome'], 'unknown')
                    self.assertIsNone(store.list('usage', 'p')[0]['time'])

    def test_completed_recovery_rechecks_inventory_and_retains_resource_dependencies(self):
        from memory_orchestrator.sampling import resume_sampling
        resources = [{'kind': 'file', 'ref': 'source.csv', 'access': 'read', 'version_ref': None}]
        result = self.run_samples(lambda *args: {'artifact': '001', 'events': [
            {'event_id': 'read', 'kind': 'observation', 'text': 'Read CSV', 'resources': resources}]}, repeat_count=1)
        self.assertEqual(next(e for e in result['episodes'][0]['events'] if e['text'] == 'Read CSV')['resources'], resources)
        self.store._record_path('runs', result['run_ids'][0]).unlink()
        calls = []
        with self.assertRaises(DomainError):
            resume_sampling(self.store, result['batch_id'], lambda *args: calls.append(args), None)
        self.assertEqual(calls, [])

    def test_seed_library_uses_same_sampling_and_closed_learning_admission(self):
        from tests.test_memory_store import skill
        from memory_orchestrator.lineage import require_learning_source
        seeded = self.store.initialize_project('p', seed={'skills': {'csv': skill('csv')}, 'assets': {}}, source='CSV teaching seed')
        seen = []
        def execute(request, snapshot, case):
            seen.append(snapshot['snapshot_id'])
            self.assertIn('csv', snapshot['skills'])
            return {'artifact': '001'}
        result = self.run_samples(execute, repeat_count=1)
        self.assertEqual(seen, [seeded['snapshot_id']])
        self.assertTrue(require_learning_source(self.store, result['episodes'][0])['known'])
        self.assertEqual(self.store.active('p')['generation'], 0)

    def test_hard_exit_keeps_missing_wall_time_and_never_retries_execution(self):
        from memory_orchestrator.sampling import prepare_sampling, resume_sampling
        batch = prepare_sampling(self.store, self.tasks, policy={**self.policy, 'repeat_count': 1}, context_policy=self.context_policy)
        script = """import os, sys
from memory_orchestrator.store import Store
from memory_orchestrator.sampling import resume_sampling
def execute(*args): os._exit(19)
resume_sampling(Store(sys.argv[1]), sys.argv[2], execute, None)
"""
        completed = subprocess.run([sys.executable, '-c', script, self.temp.name, batch['batch_id']], capture_output=True, timeout=10)
        self.assertEqual(completed.returncode, 19, completed.stderr)
        calls = []
        blocked = resume_sampling(self.store, batch['batch_id'], lambda *args: calls.append(args), None)
        self.assertEqual(calls, [])
        request_ref = blocked['blocked'][0]['request_ref']
        result = resume_sampling(self.store, batch['batch_id'], lambda *args: calls.append(args), None,
            resolutions={request_ref: {'action': 'close_unknown', 'source': 'operator', 'evidence': ['original process exited with unknown side effects']}})
        receipt = self.store.get('sampling_batch_receipts', result['batch_receipt_id'])
        self.assertEqual(receipt['missing_segment_count'], 1)
        self.assertIsNotNone(receipt['end_to_end_seconds'])
        self.assertEqual(calls, [])

    def test_lost_evaluator_does_not_rerun_execute_or_silently_rejudge(self):
        from memory_orchestrator.sampling import prepare_sampling, resume_sampling
        batch = prepare_sampling(self.store, self.tasks, policy={**self.policy, 'repeat_count': 1}, context_policy=self.context_policy)
        counts = {'execute': 0, 'evaluate': 0}
        def execute(*args): counts['execute'] += 1; return {'artifact': '001'}
        def evaluate(*args): counts['evaluate'] += 1; raise KeyboardInterrupt('lost criterion return')
        with self.assertRaises(KeyboardInterrupt): resume_sampling(self.store, batch['batch_id'], execute, evaluate)
        blocked = resume_sampling(self.store, batch['batch_id'], execute, evaluate)
        self.assertEqual(counts, {'execute': 1, 'evaluate': 1})
        self.assertEqual(blocked['blocked'][0]['stage'], 'evaluate')
        result = resume_sampling(self.store, batch['batch_id'], execute, evaluate, resolutions={blocked['blocked'][0]['request_ref']: {
            'action': 'attach_result', 'source': 'checker log', 'evidence': ['original criterion result'],
            'raw_output': {'outcome': 'pass', 'score': 1, 'source': 'executable', 'evidence': ['001 equals expected']}}})
        self.assertEqual(counts, {'execute': 1, 'evaluate': 1})
        self.assertEqual(self.store.get('assessments', self.store.get('runs', result['run_ids'][0])['assessment_ref'])['outcome'], 'pass')

    def test_assessment_recomputation_rejects_score_and_raw_identity_changes(self):
        from memory_orchestrator.feedback import verify_assessment, check_planned_feedback
        result = self.run_samples(lambda *args: {'artifact': '001'}, lambda *args: {
            'outcome': 'pass', 'score': 1, 'source': 'executable', 'evidence': ['001']}, repeat_count=1)
        original = verify_assessment(self.store, self.store.get('runs', result['run_ids'][0])['assessment_ref'])
        with self.assertRaises(DomainError):
            verify_assessment(self.store, {**original['assessment'], 'score': .5})
        with self.assertRaises(DomainError):
            check_planned_feedback(self.store, original['plan'], {**original['feedbacks'][0], 'evaluated_state_digest': 'b' * 64})

    def test_prepared_local_run_cannot_be_disguised_as_unknown_import(self):
        from memory_orchestrator.sampling import prepare_sampling, resume_sampling
        from memory_orchestrator.lineage import require_learning_source
        from tests.test_memory_store import episode
        prepared = prepare_sampling(self.store, self.tasks, policy={**self.policy, 'purpose': 'final', 'update_mode': 'none'},
                                    context_policy=self.context_policy)
        imported = episode('p', 'import-before-return')
        imported['source']['reference'] = prepared['planned_run_ids'][0]
        self.store.add_episode(imported)
        with self.assertRaises(DomainError) as raised:
            require_learning_source(self.store, imported)
        self.assertEqual(raised.exception.code, 'learning_not_permitted')
        # A separately imported alias must not hide the actual planned Episode.
        completed = resume_sampling(self.store, prepared['batch_id'], lambda *args: {'artifact': '001'}, None)
        self.assertEqual(len(completed['episodes']), self.policy['repeat_count'])
        self.assertNotIn(imported['episode_id'], [e['episode_id'] for e in completed['episodes']])

    def test_known_comparison_request_and_return_cannot_reenter_as_unknown_training(self):
        from memory_orchestrator.lineage import require_learning_source
        from tests.test_memory_store import episode, example
        plan = example('comparison-plan')
        self.store.put('evaluation_plans', plan['plan_id'], plan)
        request = plan['requests'][0]
        self.store.put('evaluation_returns', 'original-validation-return', {'id': 'original-validation-return',
            'project_id': plan['project_id'], 'stage': 'execute', 'request': request,
            'returned': {'artifact': '001'}, 'error': None})
        from memory_orchestrator.schemas import digest, now_iso
        self.store.put('callback_attempts', 'validation-criterion-attempt', {'attempt_id': 'validation-criterion-attempt',
            'project_id': plan['project_id'], 'batch_id': None, 'run_id': None, 'stage': 'evaluate',
            'request_ref': 'actual-criterion', 'started_at': now_iso(), 'config_hash': digest({}), 'recovery_ref': None})
        for reference in (request['request_id'], 'original-validation-return', 'validation-criterion-attempt'):
            imported = episode(plan['project_id'], 'import-' + reference)
            imported['source']['reference'] = reference
            self.store.add_episode(imported)
            with self.assertRaises(DomainError) as raised:
                require_learning_source(self.store, imported)
            self.assertEqual(raised.exception.code, 'learning_not_permitted')

    def test_learning_callback_source_alias_keeps_actual_run_and_project_identity(self):
        from memory_orchestrator.lineage import require_learning_source
        from tests.test_memory_store import episode
        result = self.run_samples(lambda *args: {'artifact': '001'}, repeat_count=1)
        alias = self.store.list('callback_attempts', 'p')[0]['attempt_id']
        imported = episode('p', 'alias-import'); imported['source']['reference'] = alias
        self.store.add_episode(imported)
        self.assertEqual(require_learning_source(self.store, imported)['run_id'], result['run_ids'][0])
        wrong = {**imported, 'episode_id': 'wrong-project', 'project_id': 'foreign'}
        with self.assertRaises(DomainError): self.store.add_episode(wrong)

    def test_late_criterion_correction_appends_assessment_without_replacing_run_result(self):
        from memory_orchestrator.feedback import assess, freeze_feedback_plan, verify_assessment
        result = self.run_samples(lambda *args: {'artifact': '001'}, lambda *args: {
            'outcome': 'pass', 'score': 1, 'source': 'executable', 'evidence': ['initial checker']}, repeat_count=1)
        run = self.store.get('runs', result['run_ids'][0])
        previous = verify_assessment(self.store, run['assessment_ref'])
        plan = previous['plan']
        protocol = {'protocol_id': self.policy['protocol_id'], 'purpose': 'learning', 'scoring_policy': 'completed_only',
                    'evaluator': None, 'visibility': 'adaptation'}
        correction = freeze_feedback_plan(self.store, {**plan['subject'], 'project_id': 'p', 'run_id': run['run_id'],
            'task_revision': run['task_revision'], 'request': plan['request'], 'criteria': self.tasks[0]['criteria'],
            'batch_id': result['batch_id']}, protocol)
        actual = assess(self.store, correction['feedback_plan_id'], {'artifact': '001'},
            {'task': self.tasks[0], 'criteria': self.tasks[0]['criteria']}, execution_ref=run['run_id'],
            supersedes=previous['assessment']['assessment_id'], evaluate=lambda *args: {
                'outcome': 'fail', 'score': 0, 'source': 'human', 'evidence': ['corrected original criterion judgement']})
        self.assertEqual(actual['assessment']['outcome'], 'fail')
        self.assertEqual(verify_assessment(self.store, run['assessment_ref'])['assessment']['outcome'], 'pass')
        self.assertEqual(len(self.store.feedback_for(result['episodes'][0]['episode_id'])), 2)

    def test_concurrent_resumers_share_the_original_callback_and_receipt(self):
        from concurrent.futures import ThreadPoolExecutor
        from memory_orchestrator.sampling import prepare_sampling, resume_sampling
        batch = prepare_sampling(self.store, self.tasks, policy={**self.policy, 'repeat_count': 1}, context_policy=self.context_policy)
        calls = []
        def execute(*args): calls.append('executed'); return {'artifact': '001'}
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: resume_sampling(Store(self.temp.name), batch['batch_id'], execute, None), range(2)))
        self.assertEqual(calls, ['executed'])
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(self.store.list('sampling_batch_receipts', 'p')), 1)

    def test_trace_path_is_frozen_and_proxy_resumes_bounded_index_before_model(self):
        from pathlib import Path
        from memory_orchestrator.model import StructuredModel
        from memory_orchestrator.sampling import resume_sampling
        from tests.test_memory_evidence import event
        from tests.test_memory_model import limits, response
        path = Path(self.temp.name) / 'execution.jsonl'
        original = ''.join(json.dumps(event('e' + str(i), 'observed CSV step ' + str(i))) + '\n' for i in range(10))
        path.write_text(original)
        calls, model_calls = [], []
        def execute(request, *args):
            calls.append(request['request_id'])
            self.assertTrue(request['episode_id'])
            return {'artifact': '001', 'trace_path': str(path)}
        def invoke(request):
            model_calls.append(request)
            packet, _ = json.JSONDecoder().raw_decode(request['messages'][1]['content'].split('证据：', 1)[1])
            return response({'outcome': 'pass', 'criterion_findings': [{'criterion_id': 'task_outcome',
                'outcome': 'pass', 'score': 1, 'finding': 'Constructed archive check',
                'evidence_refs': [packet['fragments'][-1]['ref_id']]}], 'unknowns': []})
        budget = limits(max_calls=1, max_format_repairs=0)
        trace_limits = {'max_events': 3, 'max_bytes': 10000, 'max_event_bytes': 3000}
        proxy = {'enabled': True, 'limits': budget, 'trace_limits': trace_limits,
                 'packet_limits': {'max_chars': 12000, 'max_fragment_chars': 500, 'max_catalog_refs': 10, 'token_budget': 12000}}
        model = StructuredModel(invoke, limits=budget)
        result = sample_tasks(self.store, self.tasks, execute, None, policy={**self.policy, 'repeat_count': 1,
            'trace_limits': trace_limits, 'feedback': {'criteria': [{'criterion_id': 'task_outcome', 'rule': self.tasks[0]['criteria']}],
                'aggregation': {'kind': 'single_task_outcome'}, 'proxy': proxy}}, context_policy=self.context_policy, proxy_model=model)
        self.assertEqual(model_calls, [])
        self.assertEqual(result['blocked'][0]['stage'], 'proxy_index')
        for _ in range(10):
            result = resume_sampling(self.store, result['batch_id'], execute, None, proxy_model=model)
            if not result['blocked']: break
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(model_calls), 1)
        self.assertEqual(path.read_text(), original)
        ep = result['episodes'][0]
        self.assertEqual(ep['events'], [])
        manifest = self.store.get('trace_manifests', ep['trace_ref'])
        archived = (self.store.root / manifest['raw_path']).read_text()
        self.assertIn(original, archived)
        self.assertIn('host:' + result['run_ids'][0] + ':result', archived)
        host_result = json.loads(archived.splitlines()[-1])
        state = digest('001')
        self.assertEqual(host_result['resources'], [{
            'kind': 'artifact', 'ref': 'evaluated-state:' + state,
            'access': 'check', 'version_ref': state,
        }])

    def test_streamed_parent_source_is_checked_after_index_without_fabricating_missing_parent(self):
        from pathlib import Path
        from memory_orchestrator.trace import import_trace
        from memory_orchestrator.lineage import require_learning_source
        from tests.test_memory_store import episode
        from tests.test_memory_evidence import event
        final = self.run_samples(lambda *args: {'artifact': '001'}, repeat_count=1, purpose='final', update_mode='none')
        caps = {'max_events': 10, 'max_bytes': 10000, 'max_event_bytes': 5000}
        for parent_id in (final['episodes'][0]['episode_id'], 'unknown-parent'):
            header = episode('p', 'trace-child-' + parent_id); header['events'] = []
            path = Path(self.temp.name) / (header['episode_id'] + '.jsonl')
            path.write_text(json.dumps(event('child', 'Observed dependency', parent_episode_id=parent_id, parent_event_id='result')) + '\n')
            imported = import_trace(self.store, header, path, limits=caps)
            index_episodes([imported], store=self.store, trace_limits=caps)
            if parent_id == 'unknown-parent':
                proof = require_learning_source(self.store, imported)
                self.assertEqual(proof['missing_parent_episode_refs'], ['unknown-parent'])
            else:
                with self.assertRaises(DomainError) as raised: require_learning_source(self.store, imported)
                self.assertEqual(raised.exception.code, 'learning_not_permitted')

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
        self.assertEqual(usage['raw'], value)
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
