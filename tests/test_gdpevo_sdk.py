"""A pilot's physical calls stay recorded across faults and repeated openings."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest


class LedgerTests(unittest.TestCase):
    def test_full_real_messages_and_tools_count_before_dispatch(self):
        from examples.gdpevo_pilot.sdk import CallLedger
        payload = json.loads((Path(__file__).parent / 'fixtures/gdpevo_actor_first_request.json').read_text())['payload']
        seen = []
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: seen.append(kw))))
        config = {'model': 'fixture', 'base_url': 'http://localhost:8317/v1', 'timeout': 30,
                  'max_calls': 2, 'max_total_input_chars': 1000, 'max_output_tokens': 8192}
        with tempfile.TemporaryDirectory() as root:
            ledger = CallLedger(root, config=config, client=client)
            with self.assertRaisesRegex(Exception, 'budget'):
                ledger(payload, stage='execute', subject='train_001')
            self.assertEqual(seen, [])
            self.assertEqual(ledger.summary()['calls'], 0)

    def test_actual_call_envelope_is_saved_and_budget_is_shared_after_reopen(self):
        from examples.gdpevo_pilot.sdk import CallLedger
        seen = []
        def create(**payload):
            seen.append(payload)
            return {'id': 'recorded-provider-response', 'model': 'fixture',
                    'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': '{}',
                                 'reasoning_content': 'PRIVATE-HIDDEN-REASONING'}}],
                    'usage': {'prompt_tokens': 10, 'completion_tokens': 2, 'total_tokens': 12}}
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        config = {'model': 'fixture', 'base_url': 'http://localhost:8317/v1', 'timeout': 30,
                  'max_calls': 1, 'max_total_input_chars': 5000, 'max_output_tokens': 100}
        with tempfile.TemporaryDirectory() as root:
            ledger = CallLedger(root, config=config, client=client)
            payload = {'messages': [{'role': 'user', 'content': 'Read public business orders.'}],
                       'max_completion_tokens': 50}
            result = ledger(payload, stage='execute', subject='task001')
            self.assertEqual(result['usage']['total_tokens'], 12)
            self.assertNotIn('PRIVATE-HIDDEN-REASONING', json.dumps(result))
            self.assertEqual(ledger.summary()['calls'], 1)
            reopened = CallLedger(root, config=config, client=client)
            with self.assertRaisesRegex(Exception, 'budget'):
                reopened(payload, stage='execute', subject='task002')
            self.assertEqual(len(seen), 1)
            text = '\n'.join(p.read_text() for p in Path(root).rglob('*.json'))
            self.assertIn('Read public business orders.', text)
            self.assertNotIn('PRIVATE-HIDDEN-REASONING', text)

    def test_interrupted_and_failed_transports_remain_unknown_attempts(self):
        from examples.gdpevo_pilot.sdk import CallLedger
        for error in (RuntimeError('Bearer DO_NOT_SAVE'), KeyboardInterrupt('interrupted')):
            def create(**payload):
                raise error
            client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
            config = {'model': 'fixture', 'base_url': 'http://localhost:8317/v1', 'timeout': 30,
                      'max_calls': 2, 'max_total_input_chars': 5000, 'max_output_tokens': 100}
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as root:
                ledger = CallLedger(root, config=config, client=client)
                with self.assertRaises(type(error)):
                    ledger({'messages': [{'role': 'user', 'content': 'task'}], 'max_completion_tokens': 10},
                           stage='extract_v1', subject='development')
                summary = ledger.summary()
                self.assertEqual(summary['calls'], 1)
                self.assertEqual(summary['unknown_usage_calls'], 1)
                self.assertIsNone(summary['complete_token_totals'])
                self.assertNotIn('DO_NOT_SAVE', '\n'.join(p.read_text() for p in Path(root).rglob('*.json')))


if __name__ == '__main__':
    unittest.main()
