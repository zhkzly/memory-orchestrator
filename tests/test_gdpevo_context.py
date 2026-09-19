"""Evidence-quality regression from the unmodified real train_001 pilot trace.

The saved actions/results are copied from the baseline artifact, not reconstructed
ideal trajectories. These checks neither call a model nor score a benchmark.
"""
import copy
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from memory_orchestrator.evidence import index_episodes, build_packet, validate_packet, expand_packet, validate_citations
from memory_orchestrator.schemas import DomainError


FIXTURE = json.loads((Path(__file__).parent / 'fixtures/gdpevo_context_train001.json').read_text())


class GDPevoContextTests(unittest.TestCase):
    def setUp(self):
        self.original = copy.deepcopy(FIXTURE)
        episode, feedback, context = (self.original[key] for key in ('episode', 'feedback', 'context'))
        self.index = index_episodes([episode], feedback=[feedback], contexts={context['manifest_id']: context})
        self.index['gaps'].insert(0, 'Related-memory lookup found no in-budget matches; this does not establish absence of counterexamples.')
        self.packet = build_packet(self.index, limits=self.original['packet_limits'])
        self.actions = {}
        for event in episode['events']:
            if event['kind'] != 'action': continue
            body = json.loads(event['text'])
            args = json.loads(body['arguments'])
            self.actions[event['call_id']] = {'tool': body['tool'], 'path': args.get('path'), 'event_id': event['event_id']}

    def original_row(self, item):
        return self.index['records'][item['ref_id'].rsplit(':', 2)[0]]

    def test_failed_business_categories_have_actual_return_evidence(self):
        families = set()
        for fragment in self.packet['fragments']:
            row = self.original_row(fragment)
            action = self.actions.get(row['call_id'])
            if row['source_role'] == 'tool' and row['source_kind'] in ('result', 'observation') and action and action['tool'] == 'business_get':
                families.add(action['path'].strip('/').split('/')[0])
        # Official SP002/SP003 failed. Both source data categories were actually
        # retrieved; neither may disappear behind a list of GET request bodies.
        self.assertIn('products', families)
        self.assertIn('inventory', families)
        self.assertIn('orders', families)

    def test_selected_business_requests_keep_their_actual_return_reachable(self):
        visible = self.packet['fragments'] + self.packet['readable_ref_catalog']
        rows = [self.original_row(item) for item in visible]
        missing = []
        for fragment in self.packet['fragments']:
            row = self.original_row(fragment); action = self.actions.get(row['call_id'])
            if row['source_kind'] == 'action' and action and action['tool'] == 'business_get':
                if not any(other['call_id'] == row['call_id'] and other['source_kind'] in ('result', 'observation') for other in rows):
                    missing.append(action['path'])
        self.assertEqual(missing, [], 'Selected GETs need exact returned evidence or an authorized read locator.')

    def test_catalog_offers_returns_and_selected_template_continuation(self):
        catalog = self.packet['readable_ref_catalog']
        self.assertTrue(any(self.original_row(item)['source_kind'] in ('result', 'observation') for item in catalog))
        template = next(event for event in self.original['episode']['events'] if event['call_id'] in self.actions
                        and self.actions[event['call_id']]['path'] == 'input/payloads/answer_template.json'
                        and event['kind'] == 'result')
        continuations = [item for item in catalog if self.original_row(item)['event_id'] == template['event_id']]
        self.assertTrue(continuations, 'A truncated required output template must remain readable.')
        selected = continuations[0]
        with self.assertRaises(DomainError): validate_citations({'evidence_refs': [selected['ref_id']]}, self.packet)
        expanded = expand_packet(self.index, self.packet,
            [{'ref_id': selected['ref_id'], 'purpose': 'Read the omitted required template fields'}],
            limits=self.original['expanded_packet_limits'])
        validate_citations({'evidence_refs': [selected['ref_id']]}, expanded)
        self.assertIn(selected['ref_id'], {item['ref_id'] for item in expanded['fragments']})

    def test_actual_budget_raw_ranges_and_all_scoring_points_remain_intact(self):
        validate_packet(self.packet, self.index)
        compact = json.dumps(self.packet, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        self.assertLessEqual(len(compact), self.original['packet_limits']['max_chars'])
        self.assertLess(self.packet['coverage']['selected_event_count'], len(self.original['episode']['events']))
        self.assertEqual(self.original, FIXTURE)
        feedback_text = ''.join(f['text'] for f in self.packet['fragments'] if f['kind'] == 'feedback')
        for number in range(1, 9): self.assertIn(f'SP{number:03d}_', feedback_text)
        self.assertEqual(self.packet['source_snapshot_refs'], [self.original['episode']['source_snapshot_ref']])
        for fragment in self.packet['fragments']:
            original = self.original_row(fragment)['text'].encode('utf-8')
            start, end = fragment['range']['start_byte'], fragment['range']['end_byte_exclusive']
            self.assertEqual(fragment['text'].encode('utf-8'), original[start:end])

    def test_real_trajectory_disk_index_keeps_the_same_useful_call_categories(self):
        from memory_orchestrator.store import Store
        from memory_orchestrator.trace import import_trace, ensure_trace_index
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'store')
            header = copy.deepcopy(self.original['episode'])
            events = header['events']; header['events'] = []
            active = store.ensure_project(header['project_id'])
            self.assertEqual(active['snapshot_id'], header['source_snapshot_ref'])
            context = self.original['context']; store.put('contexts', context['manifest_id'], context)
            path = Path(directory) / 'original-events.jsonl'
            path.write_text(''.join(json.dumps(event, ensure_ascii=False) + '\n' for event in events))
            caps = {'max_events': len(events) + 1, 'max_bytes': 200000, 'max_event_bytes': 100000}
            disk = import_trace(store, header, path, limits=caps)
            # Build the completed index using the exact earlier broad signal
            # policy. Reopening must not keep its customer_exception anchor.
            def old_signal(text):
                found = re.search(r'error|fail(?:ed|ure)?|exception|错误|失败|丢失|不通过', text, re.I)
                return found.start() if found else None
            with patch('memory_orchestrator.evidence._failure_position', side_effect=old_signal):
                reader, checkpoint = ensure_trace_index(store, disk['trace_ref'], caps)
            self.assertTrue(checkpoint['index_complete'])
            self.assertTrue(any(row['event_id'] == 'observation_1' and row['failure_byte'] is not None for row in reader.rows()))
            original_bytes = path.read_bytes()
            checkpoint_count = len(store.list('trace_index_checkpoints'))
            reopened = Store(store.root)
            index = index_episodes([disk], feedback=[self.original['feedback']],
                contexts={context['manifest_id']: context}, store=reopened, trace_limits=caps)
            # A smaller candidate window exercises the disk prefilter itself;
            # the main packet below still uses the original 42000-char budget.
            metadata = index['records'].select_metadata({}, 12)
            self.assertLessEqual(len(metadata), 12)
            self.assertTrue(any(row['source_event'] and row['position'] >= len(events) // 2 for row in metadata))
            self.assertTrue(any(row['source_kind'] in ('result', 'observation')
                and self.actions.get(row['call_id'], {}).get('tool') == 'business_get'
                and self.actions[row['call_id']]['path'].strip('/').split('/')[0] in ('products', 'inventory')
                for row in metadata))
            packet = build_packet(index, limits=self.original['packet_limits'])
            families = {self.actions[f['structure']['call_id']]['path'].strip('/').split('/')[0]
                for f in packet['fragments'] if f['structure']['source_kind'] in ('result', 'observation')
                and f['structure']['call_id'] in self.actions and self.actions[f['structure']['call_id']]['tool'] == 'business_get'}
            self.assertTrue({'orders', 'products', 'inventory'} <= families, families)
            self.assertTrue(any(item['structure']['source_kind'] in ('result', 'observation') for item in packet['readable_ref_catalog']))
            template = next(f for f in packet['fragments'] if f['event_id'] == 'observation_1')
            self.assertEqual(template['range']['start_byte'], 0)
            self.assertEqual(path.read_bytes(), original_bytes)
            self.assertEqual(len(reopened.list('trace_index_checkpoints')), checkpoint_count)
            validate_packet(packet, index)
            self.assertLessEqual(len(json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(',', ':'))), self.original['packet_limits']['max_chars'])


if __name__ == '__main__': unittest.main()
