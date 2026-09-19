"""Rejected target handoff derived from one real GDPevo comparison; no model gain claim."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from memory_orchestrator.engine import evolve
from memory_orchestrator.evidence import build_packet, index_episodes
from memory_orchestrator.evaluation import capture_rejected_target_episodes
from memory_orchestrator.learning import learn
from memory_orchestrator.lineage import require_learning_source
from memory_orchestrator.model import StructuredModel
from memory_orchestrator.schemas import DomainError, load_contracts
from memory_orchestrator.store import Store
from test_memory_model import EXAMPLES, FakeCall, limits as model_limits, response


FIXTURE = json.loads((Path(__file__).parent / 'fixtures/gdpevo_rejected_target_evaluation.json').read_text())
ORIGINAL_FEEDBACK = json.loads(
    (Path(__file__).parent / 'fixtures/gdpevo_original_criterion_feedback.json').read_text())


class RejectedTargetLearningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.data = copy.deepcopy(FIXTURE)
        self._load()

    def _load(self):
        data, store = self.data, self.store
        plan, snapshot = data['plan'], data['candidate_snapshot']
        active = store.initialize_project(plan['project_id'], source={'fixture': 'real-gdpevo-rejection'})
        self.assertEqual(active['snapshot_id'], plan['base_digest'])
        saved = store.save_snapshot(plan['project_id'], snapshot['skills'], snapshot['assets'], parent=snapshot['parent'])
        self.assertEqual(saved['snapshot_id'], plan['candidate_digest'])
        store.put('candidates', data['candidate']['proposal_id'], data['candidate'])
        store.put('case_sets', data['case_set']['id'], data['case_set'])
        store.put('evaluation_plans', plan['plan_id'], plan)
        for label in ('target_candidate', 'regression_candidate'):
            row = data[label]
            store.put('evaluation_returns', row['evaluation_return']['id'], row['evaluation_return'])
            result = row['evaluation_result']
            store.put('evaluation_results', result['request_id'], result)
        store.put('validations', data['validation']['validation_id'], data['validation'])
        store.put('selections', data['selection']['selection_id'], data['selection'])

    def capture(self):
        return capture_rejected_target_episodes(self.store, copy.deepcopy(self.data['comparison']))

    def load_original_criterion_feedback(self):
        feedback = copy.deepcopy(ORIGINAL_FEEDBACK['feedback'])
        assessment = copy.deepcopy(ORIGINAL_FEEDBACK['assessment'])
        plan = copy.deepcopy(ORIGINAL_FEEDBACK['feedback_plan'])
        returned = copy.deepcopy(ORIGINAL_FEEDBACK['callback_return'])
        self.store.put('feedback_plans', plan['feedback_plan_id'], plan)
        self.store.put('callback_returns', returned['attempt_id'], returned)
        self.store.put('feedback', feedback['check_id'], feedback)
        self.store.put('assessments', assessment['assessment_id'], assessment)
        return feedback, assessment

    def test_rejected_target_preserves_bound_original_criterion_feedback(self):
        source, assessment = self.load_original_criterion_feedback()
        episode_id = self.capture()[0]
        adaptation = self.store.feedback_for(episode_id)[0]
        reason = json.loads(adaptation['reason'])
        self.assertEqual(reason['source_assessment_ref'], assessment['assessment_id'])
        self.assertEqual(reason['source_criterion_feedback'], [{
            key: source[key] for key in ('check_id', 'criterion_id', 'evaluator_status', 'outcome',
                                         'score', 'source', 'evidence_refs', 'reason')
        }])
        detail = json.loads(reason['source_criterion_feedback'][0]['reason'])
        points = detail['evidence'][0]['result']['scoring_points']
        self.assertEqual([row['id'] for row in points if not row['matched']], [
            'SP002_inventory_statuses_and_shortages',
            'SP003_inactive_and_low_stock_sku_sets',
            'SP005_final_decisions',
            'SP006_next_actions',
            'SP008_summary_rollups',
        ])

    def test_rejected_target_binds_evaluated_artifact_to_adaptation_feedback(self):
        self.load_original_criterion_feedback()
        episode_id = self.capture()[0]
        episode = self.store.get('episodes', episode_id)
        feedback = self.store.feedback_for(episode_id)
        index = index_episodes([episode], feedback=feedback)
        result = next(row for row in index['records'].values()
                      if row['source_event'] and row['event_id'] == 'result')
        projected = next(row for row in index['records'].values()
                         if not row['source_event'] and row['event_id'] == feedback[0]['check_id'])
        self.assertEqual(result['resources'], projected['resources'])
        self.assertEqual(result['resources'], [{
            'kind': 'artifact',
            'ref': 'evaluated-state:' + feedback[0]['evaluated_state_digest'],
            'access': 'check',
            'version_ref': feedback[0]['evaluated_state_digest'],
        }])
        packet = build_packet(index, limits={
            'max_chars': 1000000, 'max_fragment_chars': 200000,
            'max_catalog_refs': 256, 'token_budget': 1000000,
        }, allowed_refs=set(index['records']))
        self.assertTrue(any(link['resource_ref'] == result['resources'][0]['ref']
                            and link['version_match'] is True
                            for link in packet['resource_relations']))

    def test_tampered_original_criterion_feedback_blocks_rejection_projection(self):
        source, _ = self.load_original_criterion_feedback()
        changed = copy.deepcopy(source)
        changed['score'] = 1.0
        original = self.store.get
        def tampered(kind, identifier):
            if kind == 'feedback' and identifier == source['check_id']:
                return changed
            return original(kind, identifier)
        with patch.object(self.store, 'get', side_effect=tampered), \
             self.assertRaises(DomainError) as caught:
            self.capture()
        self.assertEqual(caught.exception.code, 'feedback_binding')

    def test_rejected_target_candidate_becomes_one_grounded_adaptation_episode(self):
        before = self.store.active(self.data['plan']['project_id'])
        episode_ids = self.capture()
        self.assertEqual(len(episode_ids), 1)
        episode = self.store.get('episodes', episode_ids[0])
        returned = self.data['target_candidate']['evaluation_return']['returned']
        request = self.data['target_candidate']['evaluation_return']['request']
        self.assertEqual(episode['source'], {
            'kind': 'rejected_target_evaluation',
            'reference': self.data['target_candidate']['evaluation_return']['id'],
        })
        self.assertEqual(episode['task']['task_id'], request['case_ref'])
        self.assertEqual(episode['source_snapshot_ref'], request['snapshot_digest'])
        self.assertEqual(len(episode['events']), len(returned['events']) + 2)
        self.assertEqual([event['text'] for event in episode['events'][1:-1]],
                         [event['text'] for event in returned['events']])
        self.assertEqual(json.loads(episode['events'][-1]['text'])['artifact'], returned['artifact'])
        feedback = self.store.feedback_for(episode['episode_id'])
        self.assertEqual(len(feedback), 1)
        self.assertEqual((feedback[0]['visibility'], feedback[0]['score'], feedback[0]['outcome']),
                         ('adaptation', self.data['target_candidate']['evaluation_result']['score'], 'fail'))
        reason = json.loads(feedback[0]['reason'])
        self.assertEqual(reason['selection_id'], self.data['selection']['selection_id'])
        self.assertEqual(reason['validation_status'], 'rejected')
        self.assertEqual(reason['failed_gates'], ['target_gain'])
        self.assertNotIn('regression', json.dumps(reason))
        self.assertNotIn('criteria', json.dumps(reason))
        source = require_learning_source(self.store, episode)
        self.assertEqual(source['evaluation_return']['id'], episode['source']['reference'])
        self.assertEqual(self.store.active(self.data['plan']['project_id']), before)

    def test_base_and_regression_requests_never_enter_next_learning_ids(self):
        episode_ids = self.capture()
        episode = self.store.get('episodes', episode_ids[0])
        self.assertEqual(episode['task']['task_id'], 'train_001')
        self.assertNotIn(self.data['regression_candidate']['evaluation_return']['id'], str(episode))
        self.assertFalse(any(e['task']['task_id'] == 'train_004' for e in self.store.list('episodes')))

    def test_handoff_is_idempotent_and_does_not_repeat_execution(self):
        first = self.capture()
        counts = {kind: len(self.store.list(kind)) for kind in ('episodes', 'feedback', 'evaluation_returns')}
        second = self.capture()
        self.assertEqual(second, first)
        self.assertEqual({kind: len(self.store.list(kind)) for kind in counts}, counts)

    def test_unknown_or_selected_validation_does_not_create_adaptation(self):
        for mode in ('unknown', 'selected'):
            with self.subTest(mode=mode):
                original = self.store.get
                if mode == 'unknown':
                    validation = copy.deepcopy(self.data['validation'])
                    validation['status'] = 'unknown'
                    def changed(kind, identifier):
                        return validation if kind == 'validations' and identifier == validation['validation_id'] else original(kind, identifier)
                else:
                    selection = copy.deepcopy(self.data['selection'])
                    selection.update(decision='selected',
                        selected_candidate_digest=self.data['plan']['candidate_digest'],
                        selected_validation_ref=self.data['validation']['validation_id'])
                    def changed(kind, identifier):
                        return selection if kind == 'selections' and identifier == selection['selection_id'] else original(kind, identifier)
                with patch.object(self.store, 'get', side_effect=changed):
                    self.assertEqual(capture_rejected_target_episodes(self.store, self.data['comparison']), [])
                self.assertEqual(self.store.list('episodes'), [])

    def test_regression_only_rejection_does_not_leak_back_into_target_learning(self):
        original = self.store.get
        validation = copy.deepcopy(self.data['validation'])
        for gate in validation['gate_results']:
            if gate['gate'] == 'target_gain':
                gate['passed'] = True
        validation['reasons'] = [reason for reason in validation['reasons'] if reason != 'target_gain']
        def changed(kind, identifier):
            return validation if kind == 'validations' and identifier == validation['validation_id'] else original(kind, identifier)
        with patch.object(self.store, 'get', side_effect=changed):
            self.assertEqual(capture_rejected_target_episodes(self.store, self.data['comparison']), [])
        self.assertEqual(self.store.list('episodes'), [])

    def test_unknown_target_result_does_not_create_adaptation(self):
        original = self.store.get
        validation = copy.deepcopy(self.data['validation'])
        result = next(row for row in validation['results'] if row['request_id'] ==
                      self.data['target_candidate']['evaluation_result']['request_id'])
        result.update(outcome='unknown', score=None, evaluator_status='error', execution_status='unknown')
        def changed(kind, identifier):
            return validation if kind == 'validations' and identifier == validation['validation_id'] else original(kind, identifier)
        with patch.object(self.store, 'get', side_effect=changed):
            self.assertEqual(capture_rejected_target_episodes(self.store, self.data['comparison']), [])
        self.assertEqual(self.store.list('episodes'), [])

    def test_blocked_comparison_has_no_handoff(self):
        comparison = {**self.data['comparison'], 'status': 'blocked', 'selection_id': None}
        self.assertEqual(capture_rejected_target_episodes(self.store, comparison), [])

    def test_tampered_projection_and_legacy_relabelling_are_rejected(self):
        episode_id = self.capture()[0]
        original = self.store.get('episodes', episode_id)
        tampered = copy.deepcopy(original)
        tampered['episode_id'] += '-tampered'
        tampered['events'][1]['text'] += ' changed'
        tampered['feedback_refs'] = []
        with self.assertRaises(DomainError):
            self.store.add_episode(tampered)
        relabelled = copy.deepcopy(original)
        relabelled['episode_id'] += '-legacy'
        relabelled['source']['kind'] = 'provided_material'
        relabelled['feedback_refs'] = []
        self.store.add_episode(relabelled)
        with self.assertRaises(DomainError) as caught:
            require_learning_source(self.store, relabelled)
        self.assertEqual(caught.exception.code, 'learning_not_permitted')

    def test_existing_learn_entrypoint_consumes_returned_episode_id(self):
        episode_id = self.capture()[0]
        packet = {'max_chars': 500000, 'max_fragment_chars': 200000,
                  'max_catalog_refs': 64, 'token_budget': 200000}
        policy = {
            'packet': packet, 'expanded_packet': packet,
            'max_expansions': 0, 'max_experiences': 1, 'max_read_requests': 0,
            'max_related_experiences': 0, 'max_related_episodes': 0, 'max_related_chars': 1,
            'candidate_count': 1, 'max_operations': 1, 'max_skills': 4, 'max_asset_bytes': 1000,
            'evaluation_scope': 'scripted admission check only',
            'necessity': {'max_compared_skills': 4},
            'maintenance': {'max_chars': 1000, 'max_pairs': 1, 'max_actions': 1},
            'goal_binding': {'max_events': 1, 'max_bindings': 1, 'max_read_requests': 0,
                'max_expansions': 0, 'max_catalog_goals': 1, 'packet': packet},
            'trajectory_processing': {
                'direct_max_input_tokens': 300000,
                'plan': {'max_scan_events': 512, 'max_segments': 2, 'max_groups_per_segment': 256,
                    'packet': packet,
                    'role_max_chars': {'user': 200000, 'action': 200000, 'note': 200000,
                                       'result': 200000, 'feedback': 200000, 'unknown': 200000}},
                'summary_limits': {'max_observations': 1, 'max_quote_chars': 120},
            },
        }
        call = FakeCall([response(EXAMPLES['abstain'])])
        model = StructuredModel(call, limits=model_limits(max_input_chars=1000000,
            max_total_input_chars=2000000, max_calls=2))
        result = learn(self.store, [episode_id], model, policy=policy)
        self.assertEqual(result['status'], 'abstained')
        self.assertEqual(result['requested_episode_ids'], [episode_id])
        self.assertEqual(len(call.calls), 1)

    def test_evolve_returns_next_episode_ids_without_automatic_second_model_cycle(self):
        candidate = self.data['candidate']
        learning = {'status': 'proposed', 'candidate_ids': [candidate['proposal_id']],
                    'cycle_id': 'scripted-cycle'}
        with patch('memory_orchestrator.engine.learn', return_value=learning) as learner, \
             patch('memory_orchestrator.engine.compare_candidates', return_value=self.data['comparison']):
            result = evolve(self.store, ['source-episode'], None, learning_policy={},
                case_set=self.data['case_set']['value'], protocol={}, execute=None, evaluate=None, max_parallel=1)
        self.assertEqual(result['status'], 'not_selected')
        self.assertEqual(len(result['next_episode_ids']), 1)
        self.assertEqual(learner.call_count, 1)
        self.assertIsNone(result['release'])
        self.assertEqual(self.store.active(self.data['plan']['project_id'])['generation'], 0)


if __name__ == '__main__':
    unittest.main()
