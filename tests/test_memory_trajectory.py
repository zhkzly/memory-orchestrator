"""Role/chunk acceptance derived from the saved real GDPevo train_001 trace.

Extra boundary rows alter only the named size/role/binding condition; they are
constructed evidence, not fresh benchmark runs or measured learning outcomes.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from memory_orchestrator import evidence
from memory_orchestrator.schemas import DomainError
from memory_orchestrator.store import Store
from memory_orchestrator.trace import import_trace


FIXTURE = json.loads((Path(__file__).parent / 'fixtures/gdpevo_context_train001.json').read_text())


def trajectory_limits(**overrides):
    value = {'max_scan_events': 512, 'max_segments': 24, 'max_groups_per_segment': 6,
        'packet': {'max_chars': 42000, 'max_fragment_chars': 6000,
                   'max_catalog_refs': 24, 'token_budget': 24000},
        'role_max_chars': {'user': 4500, 'action': 2400, 'note': 600,
                           'result': 1800, 'feedback': 5000, 'unknown': 800}}
    value.update(overrides)
    return value


def indexed(ep=None):
    ep = copy.deepcopy(ep or FIXTURE['episode'])
    context = FIXTURE['context']
    return evidence.index_episodes([ep], feedback=[FIXTURE['feedback']],
        contexts={context['manifest_id']: context})


def source_bases(packet):
    return {f['ref_id'].rsplit(':', 2)[0] for f in packet['fragments'] + packet['readable_ref_catalog']}


class TrajectoryTests(unittest.TestCase):
    def plan(self, index, **overrides):
        return evidence.build_trajectory_plan(index, limits=trajectory_limits(**overrides))

    def assert_original(self, plan, index):
        for packet in plan['segments']:
            evidence.validate_packet(packet, index)
            self.assertLessEqual(len(evidence._json(packet)), 42000)
            for fragment in packet['fragments']:
                row, expected = evidence._resolve(index, fragment['ref_id'])
                self.assertEqual(fragment['text'], expected['text'])
                self.assertEqual(fragment['raw_hash'], row['raw_hash'])

    def test_allowed_refs_is_a_strict_boundary_including_empty_set(self):
        index = indexed()
        one = next(r['base_ref'] for r in index['records'].values() if r['source_kind'] == 'action')
        packet = evidence.build_packet(index, limits=trajectory_limits()['packet'], allowed_refs={one})
        self.assertEqual(source_bases(packet), {one})
        with self.assertRaises(DomainError):
            evidence.build_packet(index, limits=trajectory_limits()['packet'], allowed_refs=set())

    def test_real_trace_is_covered_by_multiple_bounded_call_groups(self):
        index = indexed(); plan = self.plan(index)
        self.assertGreater(len(plan['segments']), 1)
        self.assertTrue(plan['coverage']['scan_complete'])
        self.assertEqual(plan['coverage']['total_events'], 136)
        self.assertEqual(plan['coverage']['omitted_events'], 0)
        self.assert_original(plan, index)
        seen = set().union(*(source_bases(p) for p in plan['segments']))
        for row in index['records'].values():
            if row['source_event']:
                self.assertIn(row['base_ref'], seen)
        for packet in plan['segments']:
            self.assertLessEqual(len(packet['relations']['calls']), 6)
            positions = [f['structure']['source_position'] for f in packet['fragments']
                         if f['structure']['namespace'] == 'event']
            self.assertEqual(positions, sorted(positions))
            for pair in packet['relations']['calls']:
                if pair['status'] == 'paired':
                    self.assertTrue(pair['action_refs'])
                    self.assertTrue(pair['result_refs'])
                    self.assertEqual(pair['coverage'], 'complete')

    def test_user_paste_and_visible_analysis_have_distinct_source_caps(self):
        ep = copy.deepcopy(FIXTURE['episode'])
        ep['events'][0]['text'] += '\nUser supplied material: ' + '材料' * 9000
        note = copy.deepcopy(ep['events'][1])
        note.update(event_id='visible-analysis', kind='note', call_id=None,
                    text='Hypothesis, not tool evidence: ' + 'consider this path ' * 600)
        ep['events'].insert(1, note)
        index = indexed(ep); plan = self.plan(index)
        rows = [f for p in plan['segments'] for f in p['fragments']]
        notes = [f for f in rows if f['event_id'] == 'visible-analysis']
        users = [f for f in rows if f['event_id'] == ep['events'][0]['event_id'] and f['structure']['namespace'] == 'event']
        self.assertTrue(notes); self.assertTrue(users)
        self.assertTrue(all(len(f['text']) <= 600 for f in notes))
        self.assertTrue(all(len(f['text']) <= 4500 for f in users))
        self.assertTrue(all(f['structure']['source_role'] == 'agent' for f in notes))
        self.assertGreater(plan['coverage']['truncated_events'], 0)
        self.assertFalse(plan['coverage']['raw_body_complete'])
        self.assert_original(plan, index)

    def test_user_control_prefix_is_not_displaced_by_quoted_error_material(self):
        ep = copy.deepcopy(FIXTURE['episode']); ep['events'] = ep['events'][:3]
        control = 'USER_CONTROL_KEEP: keep only Q3 rows and never modify the original CSV.'
        ep['events'][0]['text'] = (control + '\n<quoted_business_log>\n' + 'row,ok,0\n' * 1800
            + 'ERROR: this is quoted historical material\n' + 'row,ok,0\n' * 100 + '\n</quoted_business_log>')
        plan = self.plan(indexed(ep))
        supplied = [f for p in plan['segments'] for f in p['fragments']
                    if f['event_id'] == ep['events'][0]['event_id'] and f['structure']['namespace'] == 'event']
        self.assertTrue(any(control in f['text'] for f in supplied))
        self.assertEqual(supplied[0]['range']['start_byte'], 0)

    def test_goal_revision_chunks_do_not_inherit_final_requirement(self):
        ep = copy.deepcopy(FIXTURE['episode'])
        ep['events'] = ep['events'][:7]
        for position, row in enumerate(ep['events']):
            goal, revision = ('A', 'A@1') if position < 3 else ('B', 'B@1') if position < 5 else ('A', 'A@2')
            row.update(task_id=goal, goal_id=goal, task_revision=revision)
        # Paired actions/results in this saved prefix occupy (1,2),(3,4),(5,6).
        index = indexed(ep); plan = self.plan(index)
        self.assertGreaterEqual(len(plan['segments']), 3)
        for packet in plan['segments']:
            bindings = {(f['structure']['task_id'], f['structure']['goal_id'], f['task_revision'])
                for f in packet['fragments'] if f['structure']['namespace'] == 'event'}
            self.assertLessEqual(len(bindings), 1)
        self.assert_original(plan, index)

    def test_cross_revision_call_is_explicitly_ambiguous(self):
        ep = copy.deepcopy(FIXTURE['episode']); ep['events'] = ep['events'][1:3]
        ep['events'][0].update(task_id='A', goal_id='A', task_revision='A@1')
        ep['events'][1].update(task_id='B', goal_id='B', task_revision='B@1')
        plan = self.plan(indexed(ep))
        self.assertEqual(plan['segment_scopes'][0]['binding_status'], 'ambiguous')
        self.assertIn('binding_conflict', plan['coverage']['stop_reasons'])

    def test_missing_binding_does_not_inherit_episode_final_revision(self):
        ep = copy.deepcopy(FIXTURE['episode']); ep['events'] = ep['events'][1:3]
        for row in ep['events']: row.update(task_id=None, goal_id=None, task_revision=None)
        plan = self.plan(indexed(ep))
        self.assertEqual(plan['segment_scopes'][0]['binding_status'], 'unknown')
        self.assertIsNone(plan['segment_scopes'][0]['task_revision'])

    def test_conflicting_derived_bindings_are_not_last_write_wins(self):
        ep = copy.deepcopy(FIXTURE['episode']); ep['events'] = ep['events'][1:3]
        for row in ep['events']: row.update(task_id=None, goal_id=None, task_revision=None)
        index = indexed(ep)
        base = next(r['base_ref'] for r in index['records'].values() if r['source_event'])
        index['goal_annotations'] = [{'event_ref': base, 'goal_id': value, 'revision': value + '@1',
            'relation': 'continues', 'anchor_user_ref': base, 'evidence_refs': [],
            'binding_ref': 'constructed-contradiction', 'origin': 'model_proxy'} for value in ('A', 'B')]
        plan = self.plan(index)
        self.assertEqual(plan['segment_scopes'][0]['binding_status'], 'ambiguous')

    def test_scan_and_segment_caps_report_unprocessed_events(self):
        index = indexed()
        for caps in ({'max_scan_events': 7}, {'max_segments': 1}):
            plan = self.plan(index, **caps)
            self.assertGreater(plan['coverage']['omitted_events'], 0)
            self.assertFalse(plan['coverage']['raw_body_complete'])
            self.assertTrue(plan['coverage']['stop_reasons'])
            self.assertLessEqual(len(plan['segments']), caps.get('max_segments', 24))

    def test_late_verifier_failure_is_prioritized_before_early_routine_groups(self):
        ep = copy.deepcopy(FIXTURE['episode'])
        ep['events'][-1]['text'] = 'ERROR: late verification\n' + FIXTURE['feedback']['reason']
        index = indexed(ep)
        plan = self.plan(index, max_segments=1)
        self.assertTrue(any(f['event_id'] == ep['events'][-1]['event_id']
                            and f['structure']['namespace'] == 'event'
                            for f in plan['segments'][0]['fragments']))
        self.assertGreater(plan['coverage']['omitted_events'], 0)
        self.assertIn('segment_budget', plan['coverage']['stop_reasons'])

    def test_repeated_results_fold_but_failure_remains_source_evidence(self):
        ep = copy.deepcopy(FIXTURE['episode']); ep['events'] = ep['events'][:1]
        template_action, template_result = FIXTURE['episode']['events'][1:3]
        for i, text in enumerate(['{"status":"ok"}', '{"status":"ok"}',
                                  'ValueError: missing required field', 'ValueError: missing required field']):
            action, result = copy.deepcopy(template_action), copy.deepcopy(template_result)
            action.update(event_id=f'action-{i}', call_id=f'call-{i}')
            result.update(event_id=f'result-{i}', call_id=f'call-{i}', text=text)
            ep['events'].extend([action, result])
        index = indexed(ep); plan = self.plan(index)
        self.assertGreater(plan['coverage']['folded_events'], 0)
        failures = [f for p in plan['segments'] for f in p['fragments'] if f['event_id'] in ('result-2', 'result-3')]
        self.assertEqual({f['event_id'] for f in failures}, {'result-2', 'result-3'})
        self.assertIn('ValueError', failures[0]['text'])
        self.assert_original(plan, index)

    def test_failure_result_uses_protected_diagnostic_cap(self):
        ep = copy.deepcopy(FIXTURE['episode']); ep['events'] = ep['events'][:3]
        ep['events'][2]['text'] = 'ValueError: validation trace\n' + 'diagnostic context ' * 140 + 'ACTUAL_DIAGNOSTIC_END'
        index = indexed(ep); plan = self.plan(index)
        text = '\n'.join(f['text'] for p in plan['segments'] for f in p['fragments']
                         if f['event_id'] == ep['events'][2]['event_id'])
        self.assertIn('ACTUAL_DIAGNOSTIC_END', text)
        self.assert_original(plan, index)

    def test_disk_and_inline_group_projections_match_without_whole_text_load(self):
        expected = self.plan(indexed())
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'store')
            ep = copy.deepcopy(FIXTURE['episode']); events = ep['events']; ep['events'] = []
            store.ensure_project(ep['project_id'])
            store.put('contexts', FIXTURE['context']['manifest_id'], FIXTURE['context'])
            source = Path(directory) / 'source.jsonl'
            source.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in events))
            caps = {'max_events': 200, 'max_bytes': 300000, 'max_event_bytes': 100000}
            ep = import_trace(store, ep, source, limits=caps)
            original = Path.read_text
            def guarded(path, *args, **kwargs):
                if path.suffix in ('.jsonl', '.text'): raise AssertionError('whole source text loaded')
                return original(path, *args, **kwargs)
            with patch.object(Path, 'read_text', guarded):
                index = evidence.index_episodes([ep], feedback=[FIXTURE['feedback']],
                    contexts={FIXTURE['context']['manifest_id']: FIXTURE['context']}, store=store, trace_limits=caps)
                actual = self.plan(index)
            def view(plan):
                return [[(f['event_id'], f['range'], f['text']) for f in p['fragments']] for p in plan['segments']]
            self.assertEqual(view(actual), view(expected))
            self.assertEqual(actual['coverage'], expected['coverage'])
            limited = self.plan(index, max_scan_events=3)
            self.assertEqual(limited['coverage']['scanned_events'], 3)
            self.assertGreater(limited['read_stats']['metadata_rows'], 3)
            self.assertEqual(limited['coverage']['scan_limit_scope'], 'selection_events')

    def test_missing_limits_and_unprovided_citations_still_rejected(self):
        index = indexed()
        with self.assertRaises(DomainError): evidence.build_trajectory_plan(index, limits={})
        packet = self.plan(index)['segments'][0]
        locator = packet['readable_ref_catalog'][0]
        with self.assertRaises(DomainError):
            evidence.validate_citations({'evidence_refs': [locator['ref_id']]}, packet)

    def test_missing_execution_events_still_preserves_supplied_feedback_and_requirement(self):
        ep = copy.deepcopy(FIXTURE['episode']); ep['events'] = []
        plan = self.plan(indexed(ep))
        self.assertTrue(plan['segments'])
        kinds = {f['kind'] for p in plan['segments'] for f in p['fragments']}
        self.assertTrue({'task', 'feedback'} <= kinds)
        self.assertEqual(plan['coverage']['total_events'], 0)

    def dependency_case(self, *, two_resources=False):
        ep = copy.deepcopy(FIXTURE['episode']); ep['events'] = ep['events'][:9]
        for producer, consumer, resource in ([(2, 6, 'a.csv'), (4, 8, 'b.csv')] if two_resources else [(2, 8, 'input.csv')]):
            ep['events'][producer]['resources'] = [{'kind': 'file', 'ref': resource, 'access': 'write', 'version_ref': 'v1'}]
            ep['events'][consumer]['resources'] = [{'kind': 'file', 'ref': resource, 'access': 'check', 'version_ref': 'v1'}]
            ep['events'][consumer]['text'] = 'ERROR: dependent input check failed\n' + ep['events'][consumer]['text']
        return ep

    def test_selected_span_retrieves_its_resource_producer_under_dependency_budget(self):
        ep = self.dependency_case(); index = indexed(ep)
        config = trajectory_limits(max_segments=1, max_groups_per_segment=1)
        off = evidence.build_trajectory_plan(index, limits=config,
            dependency_limits={'max_hops': 0, 'max_events': 0})
        on = evidence.build_trajectory_plan(index, limits=config,
            dependency_limits={'max_hops': 2, 'max_events': 4})
        def visible(plan): return set().union(*(source_bases(p) for p in plan['segments']))
        producer = next(r['base_ref'] for r in index['records'].values() if r['event_id'] == ep['events'][2]['event_id'])
        self.assertNotIn(producer, visible(off))
        self.assertIn(producer, visible(on))
        self.assertGreater(on['coverage']['dependency_provided_events'], 0)
        self.assertTrue(on['segment_scopes'][0]['dependency_support'])
        self.assertTrue(any(link['resource_ref'] == 'input.csv' for link in on['segments'][0].get('resource_relations', [])))
        self.assert_original(on, index)

    def test_dependency_new_events_share_one_plan_balance_and_keep_chain_depth(self):
        ep = self.dependency_case(two_resources=True); index = indexed(ep)
        config = trajectory_limits(max_segments=2, max_groups_per_segment=1)
        plan = evidence.build_trajectory_plan(index, limits=config,
            dependency_limits={'max_hops': 2, 'max_events': 1})
        self.assertEqual(plan['coverage']['dependency_discovered_events'], 1)
        self.assertLessEqual(plan['coverage']['dependency_provided_events'], 1)
        self.assertIn('dependency_budget', plan['coverage']['stop_reasons'])
        producer_ids = {ep['events'][2]['event_id'], ep['events'][4]['event_id']}
        used = {index['records'][r]['event_id'] for p in plan['segments'] for r in source_bases(p)}
        self.assertEqual(len(producer_ids & used), 1)

    def test_dependency_other_revision_and_resource_version_remains_candidate_context(self):
        ep = self.dependency_case()
        ep['events'][2].update(task_id='previous-task', goal_id='previous-goal', task_revision='old@1')
        ep['events'][2]['resources'][0]['version_ref'] = 'v0'
        index = indexed(ep)
        plan = evidence.build_trajectory_plan(index, limits=trajectory_limits(max_segments=1, max_groups_per_segment=1),
            dependency_limits={'max_hops': 1, 'max_events': 3})
        support = next(row for row in plan['segment_scopes'][0]['dependency_support']
                       if row['event_id'] == ep['events'][2]['event_id'])
        self.assertEqual(support['source_scope']['task_revision'], 'old@1')
        self.assertEqual(support['scope_relation'], 'different_scope')
        self.assertEqual(support['resources'][0]['version_ref'], 'v0')
        self.assertIn('different_scope', plan['segments'][0]['gaps'][-1])
        self.assertTrue(any(link['version_match'] is False for link in plan['segments'][0].get('resource_relations', [])))
        self.assert_original(plan, index)

    def test_dependency_depth_limit_controls_second_hop_call_context(self):
        ep = self.dependency_case(); index = indexed(ep)
        config = trajectory_limits(max_segments=1, max_groups_per_segment=1)
        def event_ids(hops):
            plan = evidence.build_trajectory_plan(index, limits=config,
                dependency_limits={'max_hops': hops, 'max_events': 4})
            return {index['records'][ref]['event_id'] for p in plan['segments'] for ref in source_bases(p)}
        self.assertNotIn(ep['events'][1]['event_id'], event_ids(1))
        self.assertIn(ep['events'][1]['event_id'], event_ids(2))

    def test_dependency_already_counted_producer_is_reused_without_new_charge(self):
        ep = self.dependency_case()
        ep['events'][6]['resources'] = copy.deepcopy(ep['events'][8]['resources'])
        ep['events'][6]['text'] = 'ERROR: earlier check\n' + ep['events'][6]['text']
        index = indexed(ep)
        plan = evidence.build_trajectory_plan(index, limits=trajectory_limits(max_segments=2, max_groups_per_segment=1),
            dependency_limits={'max_hops': 1, 'max_events': 1})
        producer = next(r['base_ref'] for r in index['records'].values() if r['event_id'] == ep['events'][2]['event_id'])
        self.assertEqual(len(plan['segments']), 2)
        self.assertTrue(all(producer in source_bases(p) for p in plan['segments']))
        self.assertEqual(plan['coverage']['dependency_discovered_events'], 1)

    def test_dependency_declared_parent_is_selected_without_a_resource_match(self):
        ep = self.dependency_case()
        ep['events'][2]['resources'] = []; ep['events'][8]['resources'] = []
        ep['events'][8].update(parent_episode_id=ep['episode_id'], parent_event_id=ep['events'][2]['event_id'])
        index = indexed(ep)
        plan = evidence.build_trajectory_plan(index, limits=trajectory_limits(max_segments=1, max_groups_per_segment=1),
            dependency_limits={'max_hops': 1, 'max_events': 1})
        self.assertTrue(any(r['event_id'] == ep['events'][2]['event_id']
                            for r in plan['segment_scopes'][0]['dependency_support']))
        self.assertTrue(any(r['status'] in ('provided', 'readable') for r in plan['segments'][0]['relations']['parents']))

    def test_dependency_unknown_binding_is_not_inherited_from_primary_span(self):
        ep = self.dependency_case()
        ep['events'][2].update(task_id=None, goal_id=None, task_revision=None)
        index = indexed(ep)
        plan = evidence.build_trajectory_plan(index, limits=trajectory_limits(max_segments=1, max_groups_per_segment=1),
            dependency_limits={'max_hops': 1, 'max_events': 2})
        row = next(r for r in plan['segment_scopes'][0]['dependency_support'] if r['event_id'] == ep['events'][2]['event_id'])
        self.assertEqual(row['scope_relation'], 'unknown_scope')
        self.assertIsNone(row['source_scope']['task_revision'])

    def test_dependency_that_cannot_fit_has_an_explicit_gap(self):
        index = indexed(self.dependency_case())
        config = trajectory_limits(max_segments=1, max_groups_per_segment=1)
        config['packet']['max_chars'] = 3500
        plan = evidence.build_trajectory_plan(index, limits=config,
            dependency_limits={'max_hops': 2, 'max_events': 4})
        self.assertGreater(plan['coverage']['dependency_omitted_events'], 0)
        self.assertIn('dependency_packet_budget', plan['coverage']['stop_reasons'])
        self.assertIn('dependency_packet_budget', plan['segment_scopes'][0]['dependency_gaps'])


if __name__ == '__main__': unittest.main()
