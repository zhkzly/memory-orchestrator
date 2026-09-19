"""Feedback field-view checks derived from recorded GDPevo train001 material.

Boundary cases change only visibility, field text, or packet size. Scripted
summary drafts test exact evidence transport, not semantic learning quality.
"""
import copy
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from memory_orchestrator import evidence
from memory_orchestrator.learning import _summary_excerpts
from memory_orchestrator.schemas import DomainError, digest
from memory_orchestrator.store import Store
from memory_orchestrator.trace import import_trace


FIXTURE = json.loads((Path(__file__).parent / 'fixtures/gdpevo_context_train001.json').read_text())
REPAIR = json.loads((Path(__file__).parent / 'fixtures/gdpevo_summary_repair_train001.json').read_text())


def limits(max_chars=50000, max_fragment_chars=10000, max_catalog_refs=6):
    return {'max_chars': max_chars, 'max_fragment_chars': max_fragment_chars,
            'max_catalog_refs': max_catalog_refs, 'token_budget': 20000}


def summary(ref, quote):
    return {'status': 'completed', 'observations': [{'kind': 'outcome',
        'text': 'The supplied feedback reports this scoring result.',
        'excerpts': [{'ref_id': ref, 'quote': quote}]}],
        'unknowns': ['A scoring observation does not establish its cause.'],
        'reason': 'Original feedback quotation only.'}


class FeedbackTextTests(unittest.TestCase):
    def setUp(self):
        self.episode = copy.deepcopy(FIXTURE['episode'])
        self.episode['events'] = self.episode['events'][:3]
        self.feedback = copy.deepcopy(FIXTURE['feedback'])
        self.contexts = {FIXTURE['context']['manifest_id']: FIXTURE['context']}
        self.summary_limits = {'max_observations': 3, 'max_quote_chars': 240}

    def index(self):
        return evidence.index_episodes([self.episode], feedback=[self.feedback], contexts=self.contexts)

    def raw_ref(self):
        return f"feedback:{self.feedback['check_id']}#/reason"

    def reason_row(self, index):
        matches = [row for row in index['records'].values() if row['raw_ref'] == self.raw_ref()]
        self.assertEqual(len(matches), 1, 'The original reason must have one independently addressed text view.')
        return matches[0]

    def legacy_index(self, index):
        return {**index, 'records': {ref: row for ref, row in index['records'].items()
            if row['raw_ref'] != self.raw_ref()}}

    def test_real_reason_has_an_independent_exact_field_identity(self):
        original = copy.deepcopy(self.feedback)
        index = self.index()
        field = self.reason_row(index)
        expected = 'ev:' + digest([self.episode['project_id'], self.episode['episode_id'],
                                  'feedback', self.feedback['check_id'], 'reason-text-v1'])[:24]
        self.assertEqual(field['base_ref'], expected)
        self.assertEqual(field['text'], self.feedback['reason'])
        self.assertEqual(field['raw_hash'], digest(self.feedback['reason']))
        self.assertEqual(field['namespace'], 'feedback')
        self.assertEqual(field['event_id'], self.feedback['check_id'])
        self.assertFalse(field['source_event'])
        self.assertEqual(self.feedback, original)
        self.assertEqual(index['feedback'], [original])

    def test_old_full_feedback_bytes_and_identity_are_unchanged(self):
        index = self.index()
        base = 'ev:' + digest([self.episode['project_id'], self.episode['episode_id'],
                              'feedback', self.feedback['check_id']])[:24]
        _, full = evidence._resolve(index, base)
        expected = json.dumps(self.feedback, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
        self.assertEqual(full['text'], expected)
        self.assertEqual(full['raw_ref'], f"feedback:{self.feedback['check_id']}")
        self.assertEqual(full['raw_hash'], digest(expected))
        self.assertEqual(full['range'], {'start_byte': 0, 'end_byte_exclusive': len(expected.encode('utf-8'))})
        self.assertNotEqual(self.reason_row(index)['base_ref'], base)

    def test_exact_reason_quote_works_only_with_its_own_provided_ref(self):
        index = self.index()
        field = self.reason_row(index)
        packet = evidence.build_packet(index, limits=limits())
        reason = next(f for f in packet['fragments'] if f['raw_ref'] == field['raw_ref'])
        full = next(f for f in packet['fragments'] if f['raw_ref'] == f"feedback:{self.feedback['check_id']}")
        quote = re.search(r'"id":"[^"]+","matched":(?:true|false)', self.feedback['reason']).group()
        _, fragments = _summary_excerpts(summary(reason['ref_id'], quote), packet, self.summary_limits)
        self.assertEqual(evidence._resolve(index, fragments[0]['ref_id'])[1], fragments[0])
        for wrong_ref, wrong_quote in ((full['ref_id'], quote), (reason['ref_id'], quote + ' invented'),
                                       ('ev:unprovided:0:1', quote)):
            with self.subTest(ref=wrong_ref, quote=wrong_quote):
                with self.assertRaises(DomainError) as caught:
                    _summary_excerpts(summary(wrong_ref, wrong_quote), packet, self.summary_limits)
                self.assertEqual(caught.exception.code, 'summary_evidence')

    def test_real_rejected_summary_quotes_need_the_new_field_ref(self):
        rejected = json.loads(REPAIR['response']['text'])
        with self.assertRaises(DomainError) as caught:
            _summary_excerpts(rejected, REPAIR['inputs']['evidence_packet'], REPAIR['inputs']['summary_limits'])
        self.assertEqual(caught.exception.code, 'summary_evidence')
        self.assertEqual(caught.exception.details['errors'], REPAIR['diagnostics']['errors'])
        # Compose the exact recorded feedback with an existing train001 source
        # fixture for reference validation, not as a new execution trajectory.
        self.feedback = copy.deepcopy(REPAIR['feedback'])
        self.episode['episode_id'] = self.feedback['subject_ref']
        index = self.index()
        field = self.reason_row(index)
        packet = evidence.build_packet(index, limits=limits(max_fragment_chars=1600),
            allowed_refs={row['base_ref'] for row in index['records'].values() if row['namespace'] == 'feedback'})
        reason = next(f for f in packet['fragments'] if f['raw_ref'] == field['raw_ref'])
        full = next(f for f in packet['fragments'] if f['raw_ref'] == f"feedback:{self.feedback['check_id']}")
        original_excerpts = rejected['observations'][-1]['excerpts']
        quotes = [excerpt['quote'] for excerpt in original_excerpts]
        self.assertEqual(len(quotes), 5)
        self.assertIn(quotes[0], full['text'])
        for quote in quotes[1:]: self.assertIn(quote, reason['text'])
        corrected = {**rejected, 'observations': [copy.deepcopy(rejected['observations'][-1])]}
        for i, excerpt in enumerate(corrected['observations'][0]['excerpts']):
            excerpt['ref_id'] = full['ref_id'] if i == 0 else reason['ref_id']
        _, fragments = _summary_excerpts(corrected, packet, self.summary_limits)
        self.assertEqual([f['text'] for f in fragments], quotes)
        for fragment in fragments:
            self.assertEqual(evidence._resolve(index, fragment['ref_id'])[1], fragment)

    def test_multilingual_reason_is_unparsed_and_uses_original_utf8_offsets(self):
        self.feedback['reason'] = ' \t前缀🌱\n { "数量" : 3, "path" : "C:\\tmp", "ok" : true }\n原文尾部  \n'
        index = self.index()
        field = self.reason_row(index)
        self.assertEqual(field['text'], self.feedback['reason'])
        packet = evidence.build_packet(index, limits=limits())
        source = next(f for f in packet['fragments'] if f['raw_ref'] == self.raw_ref())
        quote = '"数量" : 3, "path" : "C:\\tmp"'
        _, fragments = _summary_excerpts(summary(source['ref_id'], quote), packet, self.summary_limits)
        fragment = fragments[0]
        start = len(self.feedback['reason'].split(quote)[0].encode('utf-8'))
        self.assertEqual(fragment['range'], {'start_byte': start, 'end_byte_exclusive': start + len(quote.encode('utf-8'))})
        self.assertEqual(evidence._resolve(index, fragment['ref_id'])[1]['text'], quote)

    def test_json_reason_keeps_original_spacing_and_key_order(self):
        self.feedback['reason'] = ' { "结果" : "保留🌱", "a" : true, "z" : 3 } \n'
        index = self.index()
        row = self.reason_row(index)
        self.assertEqual(row['text'], self.feedback['reason'])
        self.assertNotEqual(row['text'], evidence._json(json.loads(self.feedback['reason'])))
        packet = evidence.build_packet(index, limits=limits())
        fragment = next(f for f in packet['fragments'] if f['raw_ref'] == self.raw_ref())
        self.assertEqual(fragment['text'], self.feedback['reason'])

    def test_tampered_field_text_hash_range_and_origin_are_rejected(self):
        index = self.index()
        field = self.reason_row(index)
        packet = evidence.build_packet(index, limits=limits())
        position = next(i for i, f in enumerate(packet['fragments']) if f['raw_ref'] == field['raw_ref'])
        source = packet['fragments'][position]
        mutations = {'text': source['text'] + ' changed', 'raw_hash': '0' * 64,
                     'range': {**source['range'], 'end_byte_exclusive': source['range']['end_byte_exclusive'] - 1},
                     'raw_ref': f"feedback:{self.feedback['check_id']}",
                     'event_id': 'other-feedback',
                     'structure': {**source['structure'], 'namespace': 'event'}}
        for key, value in mutations.items():
            with self.subTest(field=key):
                changed = copy.deepcopy(packet)
                changed['fragments'][position][key] = value
                with self.assertRaises(DomainError): evidence.validate_packet(changed, index)
        index['records'][field['base_ref']]['text'] += ' changed'
        with self.assertRaises(DomainError): evidence._resolve(index, field['base_ref'])

    def test_field_continuation_must_be_read_and_counts_against_budget(self):
        index = self.index()
        field = self.reason_row(index)
        packet = evidence.build_packet(index, limits=limits(9000, 160, 4), allowed_refs={field['base_ref']})
        self.assertLessEqual(len(evidence._json(packet)), 9000)
        self.assertTrue(all(len(f['text']) <= 160 for f in packet['fragments']))
        locator = next(r for r in packet['readable_ref_catalog'] if r['raw_ref'] == self.raw_ref())
        quote = evidence._resolve(index, locator['ref_id'])[1]['text'][:60]
        with self.assertRaises(DomainError):
            _summary_excerpts(summary(locator['ref_id'], quote), packet, self.summary_limits)
        with self.assertRaises(DomainError) as caught:
            evidence.expand_packet(index, packet, [{'ref_id': locator['ref_id'], 'purpose': 'Read feedback continuation'}],
                                   limits=limits(100, 160, 4))
        self.assertEqual(caught.exception.code, 'evidence_budget_exhausted')
        expanded = evidence.expand_packet(index, packet,
            [{'ref_id': locator['ref_id'], 'purpose': 'Read feedback continuation'}], limits=limits(12000, 160, 4))
        _, fragments = _summary_excerpts(summary(locator['ref_id'], quote), expanded, self.summary_limits)
        self.assertEqual(evidence._resolve(index, fragments[0]['ref_id'])[1], fragments[0])
        self.assertNotIn(locator['ref_id'], {f['ref_id'] for f in packet['fragments']})

    def test_old_complete_packet_stays_readable_and_complete(self):
        index = self.index()
        self.reason_row(index)
        legacy = evidence.build_packet(self.legacy_index(index), limits=limits())
        self.assertEqual(legacy['coverage']['incomplete_reasons'], [])
        self.assertEqual(evidence.validate_packet(legacy, index), legacy)
        partial = evidence.build_packet(self.legacy_index(index), limits=limits(16000, 400, 4))
        locator = next(r for r in partial['readable_ref_catalog']
                       if r['raw_ref'] == f"feedback:{self.feedback['check_id']}")
        expanded = evidence.expand_packet(index, partial,
            [{'ref_id': locator['ref_id'], 'purpose': 'Read original full feedback'}], limits=limits())
        self.assertIn(locator['ref_id'], {f['ref_id'] for f in expanded['fragments']})

    def test_reason_view_cannot_replace_unread_full_feedback_or_an_event(self):
        index = self.index()
        field = self.reason_row(index)
        legacy_refs = set(self.legacy_index(index)['records'])
        full = next(ref for ref in legacy_refs if index['records'][ref]['namespace'] == 'feedback')
        event = next(ref for ref in legacy_refs if index['records'][ref]['source_event'])
        for omitted in (full, event):
            with self.subTest(omitted=omitted):
                packet = evidence.build_packet(index, limits=limits(),
                    allowed_refs=(legacy_refs - {omitted}) | {field['base_ref']})
                self.assertTrue(packet['coverage']['incomplete_reasons'])
        # A short optional field range must not invalidate complete original records.
        packet = evidence.build_packet(index, limits=limits(), allowed_refs=legacy_refs)
        short = evidence._resolve(index, field['base_ref'] + ':0:10')[1]
        packet['fragments'].append(short)
        evidence._refresh(packet, index)
        self.assertEqual(packet['coverage']['incomplete_reasons'], [])
        evidence.validate_packet(packet, index)

    def test_feedback_metadata_and_event_counts_are_not_duplicated(self):
        index = self.index()
        self.reason_row(index)
        packet = evidence.build_packet(index, limits=limits())
        visible = evidence.feedback_view(index, packet)
        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0]['check_id'], self.feedback['check_id'])
        self.assertEqual(packet['feedback_ids'], [self.feedback['check_id']])
        self.assertEqual(len(visible[0]['provided_refs']), 2)
        self.assertNotIn('reason', visible[0])
        self.assertEqual(packet['coverage']['selected_event_count'], len(self.episode['events']))
        self.assertEqual(packet['coverage']['total_event_count'], len(self.episode['events']))

    def test_reference_trajectory_keeps_field_bodies_within_role_and_packet_caps(self):
        from examples.gdpevo_pilot.run import LEARNING
        self.episode = copy.deepcopy(FIXTURE['episode'])
        index = self.index()
        config = LEARNING['trajectory_processing']['plan']
        plan = evidence.build_trajectory_plan(index, limits=config)
        self.assertEqual(plan['coverage']['total_events'], len(self.episode['events']))
        self.assertLessEqual(plan['coverage']['projected_events'], len(self.episode['events']))
        self.assertTrue(plan['segments'])
        for packet in plan['segments']:
            evidence.validate_packet(packet, index)
            self.assertLessEqual(len(evidence._json(packet)), config['packet']['max_chars'])
            fields = [f for f in packet['fragments'] if f['raw_ref'] == self.raw_ref()]
            self.assertTrue(fields)
            self.assertTrue(all(len(f['text']) <= config['role_max_chars']['feedback'] for f in fields))
            self.assertEqual(len(evidence.feedback_view(index, packet)), 1)

    def test_disk_index_keeps_legacy_coverage_and_field_read_without_full_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'store')
            store.ensure_project(self.episode['project_id'])
            store.put('contexts', FIXTURE['context']['manifest_id'], FIXTURE['context'])
            source = Path(directory) / 'trace.jsonl'
            source.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in self.episode['events']))
            header = copy.deepcopy(self.episode)
            header['events'] = []
            trace_limits = {'max_events': 20, 'max_bytes': 30000, 'max_event_bytes': 10000}
            header = import_trace(store, header, source, limits=trace_limits)
            index = evidence.index_episodes([header], feedback=[self.feedback], contexts=self.contexts,
                                           store=store, trace_limits=trace_limits)
            field = self.reason_row(index)
            # Build the historical complete packet without the new optional view.
            registry = index['records']
            saved = registry.memory.pop(field['base_ref'])
            try:
                legacy = evidence.build_packet(index, limits=limits())
            finally:
                registry.memory[field['base_ref']] = saved
            self.assertEqual(legacy['coverage']['incomplete_reasons'], [])
            with patch.object(type(registry), '__iter__', side_effect=AssertionError('unbounded disk metadata scan')):
                self.assertEqual(evidence.validate_packet(legacy, index), legacy)
                self.assertEqual(evidence._resolve(index, field['base_ref'])[1]['text'], self.feedback['reason'])

    def test_final_and_selection_feedback_have_neither_view(self):
        for visibility in ('selection_only', 'final_only'):
            with self.subTest(visibility=visibility):
                self.feedback['visibility'] = visibility
                index = self.index()
                packet = evidence.build_packet(index, limits=limits())
                self.assertEqual(index['feedback'], [])
                self.assertFalse(any(row['namespace'] == 'feedback' for row in index['records'].values()))
                self.assertEqual(packet['feedback_ids'], [])
                self.assertEqual(evidence.feedback_view(index, packet), [])
                base = 'ev:' + digest([self.episode['project_id'], self.episode['episode_id'],
                    'feedback', self.feedback['check_id'], 'reason-text-v1'])[:24]
                with self.assertRaises(DomainError): evidence._resolve(index, base + ':0:1')

    def test_empty_reason_keeps_only_the_original_record(self):
        self.feedback['reason'] = ''
        index = self.index()
        feedback_rows = [row for row in index['records'].values() if row['namespace'] == 'feedback']
        self.assertEqual(len(feedback_rows), 1)
        self.assertEqual(feedback_rows[0]['raw_ref'], f"feedback:{self.feedback['check_id']}")

    def test_two_views_share_one_selection_unit_and_body_allowance(self):
        index = self.index()
        candidates = list(index['records'].values())
        units = evidence._selection_units(index, candidates, set(), len(candidates))
        feedback_units = [u for u in units if any(r['namespace'] == 'feedback' for r in u['members'])]
        self.assertEqual(len(feedback_units), 1)
        self.assertEqual(len(feedback_units[0]['members']), 2)
        packet = evidence.build_packet(index, limits=limits(max_fragment_chars=1800))
        fragments = [f for f in packet['fragments'] if f['structure']['namespace'] == 'feedback']
        self.assertEqual(len(fragments), 2)
        self.assertLessEqual(sum(len(f['text']) for f in fragments), 1800)
        full = next(f for f in fragments if f['raw_ref'] != self.raw_ref())
        expected = evidence._json(self.feedback).split(',"reason":')[0]
        self.assertEqual(full['text'], expected)
        self.assertIn('"outcome":"fail"', full['text'])
        old = next(r for r in packet['readable_ref_catalog'] if r['raw_ref'] == full['raw_ref'])
        expanded = evidence.expand_packet(index, packet, [{'ref_id': old['ref_id'], 'purpose': 'Read original full feedback'}],
                                           limits=limits())
        self.assertIn(old['ref_id'], {f['ref_id'] for f in expanded['fragments']})

    def test_role_cap_is_shared_even_when_fragment_cap_is_larger(self):
        index = self.index()
        caps = {'user': 4000, 'action': 2000, 'note': 600, 'result': 1800,
                'feedback': 300, 'unknown': 300}
        packet = evidence.build_packet(index, limits=limits(), role_max_chars=caps)
        fragments = [f for f in packet['fragments'] if f['structure']['namespace'] == 'feedback']
        self.assertEqual(len(fragments), 2)
        self.assertLessEqual(sum(len(f['text']) for f in fragments), 300)
        self.assertTrue(any(f['raw_ref'] == self.raw_ref() for f in fragments))

    def test_long_metadata_uses_exact_outcome_range_and_preserves_reason_budget(self):
        self.feedback['evidence_refs'] = ['长元数据🌱' * 500]
        index = self.index()
        packet = evidence.build_packet(index, limits=limits(max_fragment_chars=1600))
        full = next(f for f in packet['fragments'] if f['raw_ref'] == f"feedback:{self.feedback['check_id']}")
        reason = next(f for f in packet['fragments'] if f['raw_ref'] == self.raw_ref())
        self.assertEqual(full['text'], '"outcome":"fail"')
        self.assertGreater(full['range']['start_byte'], 1600)
        self.assertEqual(evidence._resolve(index, full['ref_id'])[1], full)
        self.assertGreaterEqual(len(reason['text']), 800)
        self.assertLessEqual(len(full['text']) + len(reason['text']), 1600)

    def test_metadata_over_half_uses_outcome_without_starving_reason(self):
        index = self.index()
        packet = evidence.build_packet(index, limits=limits(max_fragment_chars=1000))
        full = next(f for f in packet['fragments'] if f['raw_ref'] == f"feedback:{self.feedback['check_id']}")
        reason = next(f for f in packet['fragments'] if f['raw_ref'] == self.raw_ref())
        self.assertEqual(full['text'], '"outcome":"fail"')
        self.assertGreaterEqual(len(reason['text']), 500)
        self.assertLessEqual(len(full['text']) + len(reason['text']), 1000)

    def test_tiny_feedback_allowance_prefers_reason_and_keeps_full_locator(self):
        index = self.index()
        allowed = {r['base_ref'] for r in index['records'].values() if r['namespace'] == 'feedback'}
        for catalog_cap in (0, 6):
            with self.subTest(catalog_cap=catalog_cap):
                packet = evidence.build_packet(index, limits=limits(max_fragment_chars=1, max_catalog_refs=catalog_cap), allowed_refs=allowed)
                self.assertEqual(len(packet['fragments']), 1)
                self.assertEqual(packet['fragments'][0]['raw_ref'], self.raw_ref())
                self.assertEqual(packet['fragments'][0]['text'], self.feedback['reason'][:1])
                self.assertEqual(any(r['raw_ref'] == f"feedback:{self.feedback['check_id']}" for r in packet['readable_ref_catalog']), bool(catalog_cap))
                self.assertTrue(packet['coverage']['incomplete_reasons'])

    def test_explicit_single_view_selection_does_not_pull_in_sibling(self):
        index = self.index()
        rows = [r for r in index['records'].values() if r['namespace'] == 'feedback']
        self.assertEqual(len(rows), 2)
        for row in rows:
            with self.subTest(source=row['raw_ref']):
                packet = evidence.build_packet(index, limits=limits(max_fragment_chars=300), allowed_refs={row['base_ref']})
                expected = next(evidence._pieces(row, 300, 0))
                self.assertEqual(packet['fragments'], [expected])
                self.assertTrue(all(item['raw_ref'] == row['raw_ref']
                    for item in packet['fragments'] + packet['readable_ref_catalog']))


if __name__ == '__main__': unittest.main()
