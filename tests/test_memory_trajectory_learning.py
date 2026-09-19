"""Learning-input checks derived from the real GDPevo train001 event fixture.

Transport replies are scripted to inspect the actual host data path; they are
not measurements of summary accuracy or model learning gains.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from memory_orchestrator.learning import learn, _summary_excerpts
from memory_orchestrator.evidence import index_episodes, build_packet
from memory_orchestrator.schemas import DomainError, load_contracts
from memory_orchestrator.model import StructuredModel
from memory_orchestrator.store import Store
from test_memory_learning import policy
from test_memory_model import EXAMPLES, limits, response


FIXTURE = json.loads((Path(__file__).parent / 'fixtures/gdpevo_context_train001.json').read_text())


def processing(**changes):
    result = {
        'direct_max_input_tokens': 0,
        'plan': {'max_scan_events': 512, 'max_segments': 2, 'max_groups_per_segment': 4,
                 'packet': {'max_chars': 15000, 'max_fragment_chars': 900,
                            'max_catalog_refs': 4, 'token_budget': 12000},
                 'role_max_chars': {'user': 900, 'action': 900, 'note': 400,
                                    'result': 500, 'feedback': 900, 'unknown': 300}},
        'summary_limits': {'max_observations': 3, 'max_quote_chars': 240},
    }
    result.update(changes)
    return result


def request_packet(request):
    text = request['messages'][1]['content']
    for position, character in enumerate(text):
        if character != '{':
            continue
        try:
            value, _ = json.JSONDecoder().raw_decode(text[position:])
        except ValueError:
            continue
        if isinstance(value, dict) and 'fragments' in value and 'packet_id' in value:
            return value
    raise AssertionError('Actual rendered request has no evidence packet')


class RecordingTeacher:
    def __init__(self, *, fail_local=None, local_abstain=False, report_usage=True):
        self.calls = []
        self.fail_local = fail_local
        self.local_abstain = local_abstain
        self.report_usage = report_usage

    def __call__(self, request):
        self.calls.append(copy.deepcopy(request))
        if request['prompt_id'] == 'summarize_trace_v1':
            local_count = sum(c['prompt_id'] == 'summarize_trace_v1' for c in self.calls)
            if local_count == self.fail_local:
                return response('not valid JSON', usage=self.report_usage)
            if self.local_abstain:
                return response({'status': 'abstained', 'observations': [], 'unknowns': ['Insufficient local evidence.'], 'reason': 'No supported observation.'}, usage=self.report_usage)
            packet = request_packet(request)
            source = next((f for f in packet['fragments'] if f['kind'] == 'action'), packet['fragments'][0])
            return response({'status': 'completed', 'observations': [{
                'kind': 'action' if source['kind'] == 'action' else 'task',
                'text': 'Recorded source content; downstream effectiveness is not established.',
                'excerpts': [{'ref_id': source['ref_id'], 'quote': source['text'][:100]}],
            }], 'unknowns': ['Selected ranges do not establish the full task cause.'], 'reason': 'Local evidence only.'}, usage=self.report_usage)
        return response(EXAMPLES['abstain'], usage=self.report_usage)


class TrajectoryLearningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.episode = copy.deepcopy(FIXTURE['episode'])
        self.store.ensure_project(self.episode['project_id'])
        self.store.put('contexts', FIXTURE['context']['manifest_id'], FIXTURE['context'])
        # The saved feedback names an original frozen plan outside this fixture.
        # Import only the real trace here; do not forge a legacy/unbound scorer.
        self.store.add_episode(self.episode)

    def run_learning(self, config=None, *, transport=None, summary_calls=10, extract_calls=10, dependency_lookup=None):
        transport = transport or RecordingTeacher()
        budget = {'max_input_tokens': 50000, 'max_total_input_tokens': 200000,
                  'max_total_output_tokens': 30000, 'stages': {name: {
                    'max_calls': 10, 'max_input_tokens': 50000, 'max_output_tokens': 3000,
                    'max_total_input_tokens': 200000, 'max_total_output_tokens': 30000,
                  } for name in load_contracts()['prompts']}}
        budget['stages']['summarize_trace_v1']['max_calls'] = summary_calls
        budget['stages']['extract_v1']['max_calls'] = extract_calls
        model = StructuredModel(transport, limits=limits(max_calls=10, max_input_chars=150000,
            max_total_input_chars=500000, max_format_repairs=0, token_budget=budget))
        options = {'trajectory_processing': config or processing()}
        if dependency_lookup is not None:
            options['dependency_lookup'] = dependency_lookup
        result = learn(self.store, [self.episode['episode_id']], model, policy=policy(**options))
        return result, transport

    def test_long_real_trace_is_summarized_before_extraction(self):
        original = copy.deepcopy(self.episode)
        result, transport = self.run_learning()
        self.assertEqual(transport.calls[0]['prompt_id'], 'summarize_trace_v1')
        self.assertEqual(transport.calls[-1]['prompt_id'], 'extract_v1')
        final = request_packet(transport.calls[-1])
        self.assertTrue(final['trajectory_summaries'])
        visible = {f['ref_id'] for f in final['fragments']}
        for summary in final['trajectory_summaries']:
            for observation in summary['observations']:
                self.assertTrue(set(observation['quote_refs']) <= visible)
        self.assertEqual(result['status'], 'abstained')
        self.assertEqual(self.store.get('episodes', original['episode_id'])['events'], original['events'])
        self.assertEqual(len(self.store.release_history(original['project_id'])), 0)
        self.assertTrue(any(f.get('structure', {}).get('source_kind') in ('result', 'observation')
                            for f in final['fragments']), 'Action quotes retain matching result context.')

    def test_later_local_failure_keeps_prior_summary_and_actual_failed_usage(self):
        config = processing()
        config['plan']['max_segments'] = 3
        result, transport = self.run_learning(config, transport=RecordingTeacher(fail_local=2))
        self.assertEqual(transport.calls[-1]['prompt_id'], 'extract_v1')
        state = result['trajectory_processing']
        self.assertEqual(state['mode'], 'partial')
        self.assertEqual(state['summary_count'], 1)
        self.assertEqual([r['status'] for r in state['segments']],
                         ['completed', 'failed', 'not_analyzed_after_stop'])
        self.assertTrue(state['segments'][1]['report_ref'])
        self.assertEqual(len(self.store.list('usage', self.episode['project_id'])), 3)
        self.assertEqual(result['status'], 'abstained')

    def test_stage_limit_leaves_unanalyzed_segments_and_extractor_can_use_prior_work(self):
        result, transport = self.run_learning(summary_calls=1)
        self.assertEqual([r['prompt_id'] for r in transport.calls], ['summarize_trace_v1', 'extract_v1'])
        state = result['trajectory_processing']
        self.assertEqual(state['summary_count'], 1)
        self.assertEqual(state['segments'][1]['status'], 'not_analyzed_budget')
        self.assertLess(state['analyzed_event_count'], state['planned_coverage']['total_events'])

    def test_all_local_abstentions_are_not_an_error_or_a_skill(self):
        result, transport = self.run_learning(transport=RecordingTeacher(local_abstain=True))
        self.assertEqual(result['status'], 'abstained')
        self.assertFalse(any(r['prompt_id'] == 'extract_v1' for r in transport.calls))
        self.assertEqual(result['experience_ids'], [])
        self.assertEqual(result['candidate_ids'], [])

    def test_impossible_extraction_budget_does_not_spend_on_local_summaries(self):
        result, transport = self.run_learning(extract_calls=0)
        self.assertEqual(result['status'], 'abstained')
        self.assertEqual(transport.calls, [])
        self.assertIn('blocking_reason', result['trajectory_processing'])

    def test_null_strategy_cannot_disable_the_unified_input_path(self):
        transport = RecordingTeacher()
        model = StructuredModel(transport, limits=limits())
        with self.assertRaises(DomainError) as caught:
            learn(self.store, [self.episode['episode_id']], model, policy=policy(trajectory_processing=None))
        self.assertEqual(caught.exception.code, 'learning_policy')
        self.assertEqual(transport.calls, [])

    def test_pilot_profile_enables_budgeted_processing_of_its_real_trace(self):
        from examples.gdpevo_pilot.run import MODEL, LEARNING
        self.assertIn('token_budget', MODEL)
        self.assertIn('trajectory_processing', LEARNING)
        transport = RecordingTeacher(report_usage=False)
        model = StructuredModel(transport, limits=MODEL)
        result = learn(self.store, [self.episode['episode_id']], model, policy=LEARNING)
        self.assertTrue(transport.calls)
        self.assertEqual(transport.calls[0]['prompt_id'], 'summarize_trace_v1')
        self.assertEqual(transport.calls[-1]['prompt_id'], 'extract_v1')
        self.assertGreater(result['trajectory_processing']['summary_count'], 0)
        self.assertLessEqual(len(transport.calls), MODEL['max_calls'])

    def test_real_feedback_and_prompt_overhead_fit_the_reference_input_cap(self):
        # Preflight the full rendered request using the unchanged real feedback.
        # This does not import a missing historical FeedbackPlan or invoke a model.
        from examples.gdpevo_pilot.run import MODEL, LEARNING
        from memory_orchestrator.evidence import build_trajectory_plan
        from memory_orchestrator.learning import _packet_union, _extraction_inputs
        index = index_episodes([FIXTURE['episode']], feedback=[FIXTURE['feedback']],
            contexts={FIXTURE['context']['manifest_id']: FIXTURE['context']})
        plan = build_trajectory_plan(index, limits=LEARNING['trajectory_processing']['plan'])
        anchors = _packet_union(index, plan['segments'], LEARNING['packet'], anchors_only=True)
        transport = RecordingTeacher()
        model = StructuredModel(transport, limits=MODEL)
        supplied = _extraction_inputs([FIXTURE['episode']], index, anchors, [], LEARNING)
        self.assertTrue(supplied['available_feedback'])
        preview = model.preview('extract_v1', supplied)
        self.assertTrue(preview['fits'], preview['blocking_reason'])
        self.assertLessEqual(preview['estimated_input_tokens'], MODEL['token_budget']['stages']['extract_v1']['max_input_tokens'])
        self.assertEqual(transport.calls, [])

    def test_project_report_exposes_partial_analysis_without_counting_reserves_as_usage(self):
        from memory_orchestrator.report import report
        result, transport = self.run_learning(summary_calls=1)
        summary = report(self.store, self.episode['project_id'])
        rows = summary['memory_progress']['trajectory_processing']
        row = next(r for r in rows if r['cycle_id'] == result['cycle_id'])
        self.assertEqual(row['mode'], 'partial')
        self.assertEqual(row['summary_count'], 1)
        self.assertEqual(row['segment_status_counts'].get('not_analyzed_budget'), 1)
        self.assertEqual(summary['usage']['tokens']['known_subtotals']['input_tokens'], 11 * len(transport.calls))

    def test_short_projected_trace_keeps_continuation_catalog_without_summary_calls(self):
        short = copy.deepcopy(self.episode)
        short['episode_id'] += '-short'
        short['events'] = short['events'][:3]
        self.store.add_episode(short)
        self.episode = short
        config = processing(direct_max_input_tokens=50000)
        result, transport = self.run_learning(config)
        self.assertEqual([r['prompt_id'] for r in transport.calls], ['extract_v1'])
        packet = request_packet(transport.calls[0])
        self.assertTrue(packet['readable_ref_catalog'])
        self.assertFalse(result['trajectory_processing']['planned_coverage']['raw_body_complete'])
        self.assertTrue(packet['coverage']['incomplete_reasons'])

    def test_local_excerpts_are_original_byte_ranges_not_relabelled_summaries(self):
        # Same real event shape with a multilingual prefix exercises byte/char
        # separation; this constructed boundary is not original pilot content.
        variant = copy.deepcopy(self.episode)
        variant['events'][0]['text'] = '中文🙂' + variant['events'][0]['text']
        index = index_episodes([variant], contexts={FIXTURE['context']['manifest_id']: FIXTURE['context']})
        packet = build_packet(index, limits=FIXTURE['packet_limits'])
        original = next(f for f in packet['fragments'] if f['event_id'] == variant['events'][0]['event_id'])
        quote = original['text'][7:55]
        draft = {'status': 'completed', 'observations': [{'kind': 'task',
            'text': 'A derived interpretation, not original text.',
            'excerpts': [{'ref_id': original['ref_id'], 'quote': quote}]}], 'unknowns': [], 'reason': 'Selected evidence.'}
        notes, fragments = _summary_excerpts(draft, packet, processing()['summary_limits'])
        self.assertEqual(fragments[0]['text'], quote)
        self.assertNotEqual(fragments[0]['text'], notes[0]['text'])
        self.assertEqual(fragments[0]['raw_hash'], original['raw_hash'])
        self.assertEqual(fragments[0]['range']['start_byte'], original['range']['start_byte'] + len(original['text'][:7].encode('utf-8')))
        self.assertEqual(notes[0]['quote_refs'], [fragments[0]['ref_id']])

    def test_unread_or_paraphrased_quotes_are_rejected_together(self):
        index = index_episodes([self.episode], contexts={FIXTURE['context']['manifest_id']: FIXTURE['context']})
        packet = build_packet(index, limits=FIXTURE['packet_limits'])
        original = packet['fragments'][0]
        draft = {'status': 'completed', 'observations': [{'kind': 'task', 'text': 'Unsupported.', 'excerpts': [
            {'ref_id': original['ref_id'], 'quote': 'UNOBSERVED_SENTINEL_64322'},
            {'ref_id': 'unread-reference', 'quote': 'not supplied'},
        ]}], 'unknowns': [], 'reason': 'Invalid quotes.'}
        with self.assertRaises(DomainError) as caught:
            _summary_excerpts(draft, packet, processing()['summary_limits'])
        self.assertEqual(caught.exception.code, 'summary_evidence')
        self.assertEqual(len(caught.exception.details['errors']), 2)

    def test_visible_assistant_claim_is_not_retyped_as_a_verified_outcome(self):
        # Legal-shape adversarial variant of a recorded event, not a claim that
        # this note or hidden reasoning existed in the original pilot.
        variant = copy.deepcopy(self.episode)
        note = copy.deepcopy(variant['events'][1])
        note.update(event_id='visible-self-report', kind='note', source_role='agent', call_id=None,
                    text='I believe the submitted answer is correct.')
        variant['events'] = [note]
        packet = build_packet(index_episodes([variant], contexts={FIXTURE['context']['manifest_id']: FIXTURE['context']}),
                              limits=FIXTURE['packet_limits'])
        source = next(f for f in packet['fragments'] if f['event_id'] == note['event_id'])
        draft = {'status': 'completed', 'observations': [{'kind': 'outcome', 'text': 'Correct answer.',
            'excerpts': [{'ref_id': source['ref_id'], 'quote': source['text']}]}], 'unknowns': [], 'reason': 'Self-report only.'}
        with self.assertRaises(DomainError) as caught:
            _summary_excerpts(draft, packet, processing()['summary_limits'])
        self.assertEqual(caught.exception.code, 'summary_evidence')
        draft['observations'][0]['kind'] = 'intention'
        self.assertTrue(_summary_excerpts(draft, packet, processing()['summary_limits'])[0])

    def test_quote_cannot_borrow_identical_text_from_an_unprovided_reference(self):
        packet = build_packet(index_episodes([self.episode], contexts={FIXTURE['context']['manifest_id']: FIXTURE['context']}),
                              limits=FIXTURE['packet_limits'])
        draft = {'status': 'completed', 'observations': [{'kind': 'task', 'text': 'Unsupported source identity.',
            'excerpts': [{'ref_id': 'not-provided', 'quote': packet['fragments'][0]['text'][:20]}]}],
            'unknowns': [], 'reason': 'Same words are not the same source.'}
        with self.assertRaises(DomainError):
            _summary_excerpts(draft, packet, processing()['summary_limits'])

    def test_all_local_count_and_quote_limits_are_enforced_with_field_paths(self):
        packet = build_packet(index_episodes([self.episode], contexts={FIXTURE['context']['manifest_id']: FIXTURE['context']}),
                              limits=FIXTURE['packet_limits'])
        source = packet['fragments'][0]
        observation = {'kind': 'task', 'text': 'A source excerpt.',
                       'excerpts': [{'ref_id': source['ref_id'], 'quote': source['text'][:30]}]}
        draft = {'status': 'completed', 'observations': [observation, copy.deepcopy(observation)],
                 'unknowns': [], 'reason': 'Legal schema, exceeded declared local limits.'}
        with self.assertRaises(DomainError) as caught:
            _summary_excerpts(draft, packet, {'max_observations': 1, 'max_quote_chars': 10})
        self.assertEqual(len(caught.exception.details['errors']), 3)
        self.assertTrue(all(row['path'].startswith('$.observations') for row in caught.exception.details['errors']))

    def test_dependency_lookup_reaches_actual_local_and_extraction_inputs(self):
        # Resource annotations and failure text are deliberate legal variants of
        # nine real events. They are not claimed as measurements of the ERP run.
        base = copy.deepcopy(self.episode)
        base['events'] = base['events'][:9]
        base['events'][2]['resources'] = [{'kind': 'file', 'ref': 'input.csv', 'access': 'write', 'version_ref': 'v1'}]
        base['events'][8]['resources'] = [{'kind': 'file', 'ref': 'input.csv', 'access': 'check', 'version_ref': 'v1'}]
        base['events'][8]['text'] = 'ERROR: consumer needs prior input.csv evidence\n' + base['events'][8]['text']
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                variant = copy.deepcopy(base)
                variant['episode_id'] += '-dependency-' + str(enabled)
                self.store.add_episode(variant)
                self.episode = variant
                config = processing()
                config['plan'].update(max_segments=1, max_groups_per_segment=1)
                result, transport = self.run_learning(config, dependency_lookup={
                    'max_hops': 2 if enabled else 0, 'max_events': 4 if enabled else 0})
                self.assertEqual(result['status'], 'abstained')
                self.assertEqual([r['prompt_id'] for r in transport.calls], ['summarize_trace_v1', 'extract_v1'])
                for request in transport.calls:
                    packet = request_packet(request)
                    positions = {f['structure']['source_position'] for f in packet['fragments'] + packet['readable_ref_catalog']
                                 if f['structure']['namespace'] == 'event'}
                    self.assertEqual(2 in positions, enabled,
                                     'Declared lookup must reach the actual learner, not only an unused packet utility.')


if __name__ == '__main__':
    unittest.main()
