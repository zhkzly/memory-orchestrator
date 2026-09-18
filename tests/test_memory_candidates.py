"""Restricted edits, derived from the blueprint's existing PATCH example."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch as mock_patch

from memory_orchestrator.candidates import apply_candidate, skill_view
from memory_orchestrator.schemas import DomainError, digest
from memory_orchestrator.store import Store


def examples():
    c = json.loads((Path(__file__).parents[1] / 'docs/blueprint/project-contract.json').read_text())
    return {x['id']: copy.deepcopy(x['value']) for x in c['examples']}


def content():
    e = examples()['experience']
    return {'title': e['title'], 'scope': e['scope'], 'triggers': ['csv'], 'preconditions': e['conditions'],
            'steps': e['guidance']['steps'] or ['retain input', 'check output'],
            'checks': e['guidance']['checks'] or ['compare fields'], 'exceptions': [],
            'depends_on': [], 'declared_conflicts': [], 'evidence_refs': e['supporting_refs']}


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.base = self.store.ensure_project('p')
        self.patch = examples()['patch']
        self.patch['operations'] = [{'op': 'ADD', 'proposed_slug': 'csv-preserve', 'content': content()}]
        self.refs = set(self.patch['evidence_refs']) | set(content()['evidence_refs'])
        self.kw = {'base_digest': self.base['snapshot_id'], 'expected_generation': 0,
                   'allowed_evidence_refs': self.refs, 'allowed_skill_ids': [],
                   'max_operations': 8, 'max_skills': 10, 'max_asset_bytes': 10000}

    def apply(self, patch=None, **kwargs):
        return apply_candidate(self.store, 'p', patch or self.patch, **{**self.kw, **kwargs})

    def test_add_creates_hidden_candidate_with_content_identity(self):
        candidate = self.apply()
        self.assertEqual(candidate['base_digest'], self.base['snapshot_id'])
        self.assertEqual(self.store.active('p'), self.base)
        self.assertEqual(self.store.get('candidates', candidate['proposal_id']), candidate)
        snapshot = self.store.snapshot(candidate['candidate_digest'])
        skill = next(iter(snapshot['skills'].values()))
        self.assertEqual(skill['content'], content())
        self.assertEqual(skill_view(snapshot)[skill['skill_id']]['rules'][0]['rule_id'], 'R1')

    def test_dependency_new_references_and_assets_are_resolved_together(self):
        patch = copy.deepcopy(self.patch)
        other = content()
        patch['operations'].append({'op': 'ADD', 'proposed_slug': 'csv-check', 'content': other})
        patch['operations'][0]['content']['depends_on'] = ['new:csv-check']
        patch['asset_edits'] = [{'op': 'UPSERT', 'owner_skill_ref': 'new:csv-check',
                                'relative_path': 'scripts/check.py', 'expected_hash': None, 'content': 'print(1)'}]
        candidate = self.apply(patch)
        snapshot = self.store.snapshot(candidate['candidate_digest'])
        dependent = next(x for x in snapshot['skills'].values() if x['content']['depends_on'])
        target = dependent['content']['depends_on'][0]
        self.assertIn(target, snapshot['skills'])
        self.assertIn(target + '/scripts/check.py', snapshot['assets'])

    def test_evidence_and_operation_limits_are_enforced(self):
        patch = copy.deepcopy(self.patch)
        patch['operations'][0]['content']['evidence_refs'] = ['invented']
        with self.assertRaises(DomainError):
            self.apply(patch)
        with self.assertRaises(DomainError):
            self.apply(max_operations=0)
        with self.assertRaises(DomainError):
            self.apply(max_skills=0)

    def test_paths_assets_and_owner_limits(self):
        patch = copy.deepcopy(self.patch)
        edit = {'op': 'UPSERT', 'owner_skill_ref': 'new:csv-preserve',
                'relative_path': 'scripts/../../escape.py', 'expected_hash': None, 'content': 'bad'}
        patch['asset_edits'] = [edit]
        with self.assertRaises(DomainError):
            self.apply(patch)
        edit['relative_path'] = 'scripts/good.py'
        with self.assertRaises(DomainError):
            self.apply(patch, max_asset_bytes=1)
        edit['expected_hash'] = digest('missing old content')
        with self.assertRaises(DomainError):
            self.apply(patch)

    def test_noop_has_no_candidate_or_snapshot_side_effect(self):
        before = self.store.active('p')
        self.assertIsNone(self.apply(examples()['noop']))
        self.assertEqual(before, self.store.active('p'))
        self.assertEqual(self.store.list('candidates'), [])

    def test_cycles_and_unknown_dependencies_are_rejected(self):
        for ref in ('new:csv-preserve', 'missing-skill'):
            patch = copy.deepcopy(self.patch)
            patch['operations'][0]['content']['depends_on'] = [ref]
            with self.assertRaises(DomainError):
                self.apply(patch)

    def test_stale_base_and_generation_rejected(self):
        with self.assertRaises(DomainError):
            self.apply(expected_generation=1)
        other = self.store.ensure_project('other')
        with self.assertRaises(DomainError):
            self.apply(base_digest=other['snapshot_id'])

    def test_duplicate_new_names_rejected_before_persist(self):
        patch = copy.deepcopy(self.patch)
        patch['operations'].append(copy.deepcopy(patch['operations'][0]))
        with self.assertRaises(DomainError):
            self.apply(patch)
        self.assertEqual(self.store.list('candidates'), [])

    def test_existing_patch_preserves_original_rule_anchors_and_revision(self):
        original = content()
        original['steps'] = ['first', 'second', 'third']
        seed = self.store.save_snapshot('p', {'csv-schema-preservation': {
            'skill_id': 'csv-schema-preservation', 'revision': 'r1', 'project_id': 'p',
            'content': original, 'asset_refs': []}}, {})
        patch = examples()['patch']
        patch['operations'][0]['edits'] = [{'kind': 'REMOVE_RULE', 'rule_id': 'R1'},
                                         {'kind': 'REPLACE_RULE', 'rule_id': 'R2', 'text': 'revised second'}]
        # Isolate the edit operation's already-published-base precondition.
        # Actual acceptance/publication is covered by the release/flow tests.
        active = {**self.base, 'snapshot_id': seed['snapshot_id']}
        with mock_patch.object(self.store, 'active', return_value=active):
            result = self.apply(patch, base_digest=seed['snapshot_id'], allowed_skill_ids=['csv-schema-preservation'])
            actual = self.store.snapshot(result['candidate_digest'])['skills']['csv-schema-preservation']
            self.assertEqual(actual['content']['steps'], ['revised second', 'third'])
            self.assertNotEqual(actual['revision'], 'r1')
            with self.assertRaises(DomainError):
                self.apply(patch, base_digest=seed['snapshot_id'])
            patch['operations'][0]['expected_revision'] = 'r2'
            with self.assertRaises(DomainError):
                self.apply(patch, base_digest=seed['snapshot_id'], allowed_skill_ids=['csv-schema-preservation'])

    def test_retirement_requires_remaining_dependencies_to_be_fixed(self):
        first = {'skill_id': 'a', 'revision': 'r1', 'project_id': 'p', 'content': content(), 'asset_refs': []}
        second = {**copy.deepcopy(first), 'skill_id': 'b'}
        first['content']['depends_on'] = ['b']
        seed = self.store.save_snapshot('p', {'a': first, 'b': second}, {})
        patch = examples()['patch']
        patch['operations'] = [{'op': 'RETIRE', 'target_skill_id': 'b', 'expected_revision': 'r1',
                                'replacement_skill_id': None, 'reason': 'obsolete'}]
        with mock_patch.object(self.store, 'active', return_value={**self.base, 'snapshot_id': seed['snapshot_id']}):
            with self.assertRaises(DomainError):
                self.apply(patch, base_digest=seed['snapshot_id'], allowed_skill_ids=['a', 'b'])
            patch['operations'].append({'op': 'PATCH', 'target_skill_id': 'a', 'expected_revision': 'r1',
                                       'edits': [{'kind': 'SET_FIELD', 'field': 'depends_on', 'value': []}]})
            result = self.apply(patch, base_digest=seed['snapshot_id'], allowed_skill_ids=['a', 'b'])
            self.assertEqual(set(self.store.snapshot(result['candidate_digest'])['skills']), {'a'})


if __name__ == '__main__':
    unittest.main()
