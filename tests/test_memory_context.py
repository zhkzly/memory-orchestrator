"""Constructed behavior cases derived from the existing blueprint experience."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from memory_orchestrator.context import select_context
from memory_orchestrator.schemas import DomainError
from memory_orchestrator.store import Store
from memory_orchestrator.sampling import _record_consumption


def skill(skill_id, deps=(), conflicts=()):
    contract = json.loads((Path(__file__).parents[1] / 'docs/blueprint/project-contract.json').read_text())
    experience = next(x['value'] for x in contract['examples'] if x['id'] == 'experience')
    return {'skill_id': skill_id, 'revision': 'r1', 'project_id': 'p', 'asset_refs': [],
            'content': {'title': experience['title'], 'scope': experience['scope'],
                        'triggers': ['csv'], 'preconditions': experience['conditions'],
                        'steps': experience['guidance']['steps'], 'checks': experience['guidance']['checks'],
                        'exceptions': [], 'depends_on': list(deps), 'declared_conflicts': list(conflicts),
                        'evidence_refs': experience['supporting_refs']}}


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.task = {'project_id': 'p', 'task_id': 't', 'revision': 'v1', 'description': 'csv transform'}
        self.policy = {'max_roots': 2, 'max_context_chars': 12000, 'relation_weight': 0.5}

    def test_default_uses_active_not_unpublished_candidate(self):
        base = self.store.ensure_project('p')
        candidate = self.store.save_snapshot('p', {'a': skill('a')}, {}, parent=base['snapshot_id'])
        result = select_context(self.store, self.task, self.policy)
        self.assertEqual(result['snapshot_digest'], base['snapshot_id'])
        self.assertEqual(result['selected_skills'], [])
        self.assertNotEqual(result['snapshot_digest'], candidate['snapshot_id'])
        self.assertEqual(Store(self.temp.name).get('contexts', result['manifest_id']), result)

    def test_dependencies_whole_and_snapshot_is_frozen(self):
        self.store.ensure_project('p')
        skills = {s: skill(s, ('b', 'c') if s == 'a' else ()) for s in ['a', 'b', 'c']}
        snapshot = self.store.save_snapshot('p', skills, {})
        result = select_context(self.store, self.task, self.policy, explicit_snapshot=snapshot['snapshot_id'])
        self.assertEqual(set(result['dependency_closure']), {'a', 'b', 'c'})
        snapshot['skills']['a']['content']['steps'] = ['tampered caller']
        self.assertNotIn('tampered caller', result['supplied_text'])
        self.assertEqual(result['snapshot_digest'], self.store.snapshot(result['snapshot_digest'])['snapshot_id'])

    def test_budget_does_not_partially_truncate_dependency_group(self):
        self.store.ensure_project('p')
        snapshot = self.store.save_snapshot('p', {'a': skill('a', ['b']), 'b': skill('b')}, {})
        result = select_context(self.store, self.task, {**self.policy, 'max_context_chars': 1},
                                explicit_snapshot=snapshot['snapshot_id'])
        self.assertEqual(result['selected_skills'], [])
        self.assertEqual(result['budget']['used'], 0)
        self.assertTrue(any(x['reason'] == 'budget' for x in result['exclusions']))

    def test_declared_conflicts_do_not_coexist(self):
        self.store.ensure_project('p')
        snapshot = self.store.save_snapshot('p', {'a': skill('a', conflicts=['b']), 'b': skill('b')}, {})
        result = select_context(self.store, self.task, self.policy, explicit_snapshot=snapshot['snapshot_id'])
        self.assertEqual(len(result['selected_skills']), 1)
        self.assertTrue(any(x['reason'] == 'declared_conflict' for x in result['exclusions']))

    def test_project_binding_and_policy_validation(self):
        other = self.store.ensure_project('other')
        with self.assertRaises(DomainError):
            select_context(self.store, self.task, self.policy, explicit_snapshot=other['snapshot_id'])
        with self.assertRaises(DomainError):
            select_context(self.store, self.task, {**self.policy, 'max_roots': True})

    def test_user_facts_are_read_only_and_provided_is_not_consumed(self):
        self.store.remember('user', 'reply in Chinese', 'explicit user instruction')
        self.store.remember('project', 'use JSON', 'explicit project instruction', project_id='p')
        self.store.remember('project', 'other fact', 'explicit project instruction', project_id='other')
        before = copy.deepcopy(self.store.facts('p'))
        result = select_context(self.store, self.task, self.policy)
        self.assertIn('reply in Chinese', result['supplied_text'])
        self.assertNotIn('other fact', result['supplied_text'])
        self.assertEqual(before, self.store.facts('p'))
        self.assertEqual(result['consumption_observability'], 'unknown')

    def test_trace_backed_co_use_can_affect_selection_but_delivery_alone_cannot(self):
        skills = {s: skill(s) for s in ['a', 'b', 'c']}
        snapshot = self.store.save_snapshot('p', skills, {})
        manifest = select_context(self.store, self.task, {**self.policy, 'max_roots': 3}, explicit_snapshot=snapshot['snapshot_id'])
        empty, _ = _record_consumption(self.store, 'p', manifest, {}, 'constructed_empty_run', learn_relations=True)
        self.assertEqual(empty, [])
        self.assertEqual(self.store.list('relations'), [])
        output = {'events': [{'event_id': 'read-a', 'source_role': 'tool', 'kind': 'action'},
                             {'event_id': 'read-c', 'source_role': 'tool', 'kind': 'action'}],
                  'consumption_events': [{'skill_id': 'a', 'event_id': 'read-a'},
                                         {'skill_id': 'c', 'event_id': 'read-c'}]}
        self.store.put('executions', 'constructed_run', {'project_id': 'p', 'run_id': 'constructed_run', 'output': output})
        observed, _ = _record_consumption(self.store, 'p', manifest, output, 'constructed_validation_run', learn_relations=False)
        self.assertEqual(len(observed), 2)
        self.assertEqual(self.store.list('relations'), [])
        refs, gaps = _record_consumption(self.store, 'p', manifest, output, 'constructed_run', learn_relations=True)
        self.assertEqual(len(refs), 2)
        self.assertEqual(gaps, [])
        result = select_context(self.store, self.task, self.policy, explicit_snapshot=snapshot['snapshot_id'])
        self.assertEqual([x['skill_id'] for x in result['roots']], ['a', 'c'])
        self.assertEqual(self.store.list('relations')[0]['evidence_level'], 'reported_by_execution_function')

    def test_natural_language_scope_and_triggers_are_not_opaque_ids(self):
        # Derived from live canary candidate 73cff8ff: valid model output that
        # used "local CSV repair" rather than the caller's short family label.
        generated = skill('csv')
        generated['content']['scope']['task_family'] = 'local CSV repair'
        generated['content']['triggers'] = ['A numeric-looking identifier in a declared string column must retain leading zeros.']
        unrelated = skill('vehicle')
        unrelated['content']['scope']['task_family'] = 'vehicle navigation'
        unrelated['content']['scope']['retrieval'] = {
            'require_any': ['navigate', 'destination'], 'exclude_any': []}
        unrelated['content']['triggers'] = ['navigate destination route']
        snapshot = self.store.save_snapshot('p', {'csv': generated, 'vehicle': unrelated}, {})
        result = select_context(self.store, {**self.task, 'task_family': 'csv'}, self.policy,
                                explicit_snapshot=snapshot['snapshot_id'])
        self.assertEqual([s['skill_id'] for s in result['selected_skills']], ['csv'])

    def test_machine_scope_selects_real_target_and_excludes_real_transfer_case(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/gdpevo_rejected_target_evaluation.json').read_text())
        actual = copy.deepcopy(next(iter(fixture['candidate_snapshot']['skills'].values())))
        actual['project_id'] = 'p'
        actual['content']['scope']['retrieval'] = {
            'require_any': ['expedite', 'dispatch-control'],
            'exclude_any': ['allocation desk', 'transfer'],
        }
        snapshot = self.store.save_snapshot('p', {actual['skill_id']: actual}, {})
        cases = {row['id']: {**row['task'], 'project_id': 'p'} for row in fixture['case_set']['value']['cases']}
        target = select_context(self.store, cases['train_001'], self.policy,
                                explicit_snapshot=snapshot['snapshot_id'])
        regression = select_context(self.store, cases['train_004'], self.policy,
                                    explicit_snapshot=snapshot['snapshot_id'])
        self.assertEqual([row['skill_id'] for row in target['selected_skills']], [actual['skill_id']])
        self.assertEqual(regression['selected_skills'], [])
        exclusion = next(row for row in regression['exclusions'] if row.get('skill_id') == actual['skill_id'])
        self.assertEqual(exclusion['reason'], 'scope_exclusion')
        self.assertEqual(exclusion['matched_terms'], ['allocation desk', 'transfer'])

    def test_machine_scope_requires_a_positive_phrase_before_ranking(self):
        generated = skill('csv')
        generated['content']['scope']['retrieval'] = {
            'require_any': ['csv', 'tabular conversion'], 'exclude_any': []}
        snapshot = self.store.save_snapshot('p', {'csv': generated}, {})
        result = select_context(self.store, {**self.task, 'description': 'unrelated schema review'},
                                self.policy, explicit_snapshot=snapshot['snapshot_id'])
        self.assertEqual(result['selected_skills'], [])
        self.assertTrue(any(row.get('skill_id') == 'csv' and row['reason'] == 'scope_requirement'
                            for row in result['exclusions']))


if __name__ == '__main__':
    unittest.main()
