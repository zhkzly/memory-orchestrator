"""Observed local work, provider time and unknown billing stay separate."""
import tempfile
import unittest
from unittest.mock import patch

from memory_orchestrator.schemas import DomainError
from memory_orchestrator.store import Store
from memory_orchestrator.telemetry import measure_stage, summarize_stages


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)

    def test_local_time_excludes_delegated_calls_and_deduplicates_price(self):
        with patch('memory_orchestrator.telemetry.time.monotonic', side_effect=[10, 15]):
            with measure_stage(self.store, 'p', 'extract', price_per_second=2, currency='test-unit') as meter:
                meter.exclude(3)
        row = self.store.get('stage_measurements', meter.measurement_id)
        self.assertEqual((row['elapsed_seconds'], row['local_seconds'], row['monetary_cost']), (5, 2, 4))
        result = summarize_stages([row, row])
        self.assertEqual(result['by_stage']['extract']['measurements'], 1)
        self.assertEqual(result['complete_cost_totals'], {'test-unit': 4})
        with self.assertRaises(DomainError):
            summarize_stages([row, {**row, 'local_seconds': 10}])

    def test_bad_exclusion_and_missing_prices_never_become_free_work(self):
        with patch('memory_orchestrator.telemetry.time.monotonic', side_effect=[10, 11]):
            with measure_stage(self.store, 'p', 'select', price_per_second=2, currency='test-unit') as meter:
                meter.exclude(2)
        row = self.store.get('stage_measurements', meter.measurement_id)
        self.assertIsNone(row['local_seconds'])
        self.assertIsNone(row['monetary_cost'])
        self.assertTrue(row['gaps'])
        self.assertIsNone(summarize_stages([row])['complete_cost_totals'])
        with measure_stage(self.store, 'p', 'prepare') as other:
            pass
        unknown = self.store.get('stage_measurements', other.measurement_id)
        self.assertIsNone(unknown['monetary_cost'])
        self.assertGreaterEqual(unknown['local_seconds'], 0)

    def test_failed_work_is_measured_and_storage_error_cannot_hide_original(self):
        original = DomainError('original_failure', 'Constructed failure')
        with self.assertRaises(DomainError) as caught:
            with measure_stage(self.store, 'p', 'propose'):
                raise original
        self.assertIs(caught.exception, original)
        row = self.store.list('stage_measurements', 'p')[0]
        self.assertEqual((row['status'], row['error_code']), ('error', 'original_failure'))
        with patch.object(self.store, 'put', side_effect=OSError('disk failure')):
            with self.assertRaises(DomainError) as caught:
                with measure_stage(self.store, 'p', 'propose'):
                    raise original
        self.assertIs(caught.exception, original)
        self.assertTrue(any('OSError' in note for note in original.__notes__))


if __name__ == '__main__':
    unittest.main()
