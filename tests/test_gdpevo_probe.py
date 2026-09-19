"""Keep the reserved task untouched when both deployable conditions are identical."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from examples.gdpevo_pilot.run import PROJECT, main
from examples.gdpevo_pilot.sdk import save_json
from memory_orchestrator.store import Store
from test_memory_context import skill


class ProbeTests(unittest.TestCase):
    def test_identical_deployable_states_skip_but_changed_state_reaches_probe(self):
        for changed in (False, True):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                base = Store(root / 'prelearning-store'); base.initialize_project(PROJECT)
                current = Store(root / 'revised/store')
                seed = None
                if changed:
                    row = deepcopy(skill('seed')); row['project_id'] = PROJECT
                    seed = {'skills': {'seed': row}, 'assets': {}}
                current.initialize_project(PROJECT, seed=seed, source={'kind': 'test_fixture', 'reference': 'test_memory_context.skill'})
                save_json(root / 'revised/result.json', {'status': 'completed'})
                reads = []
                def task(*args):
                    reads.append(args)
                    raise RuntimeError('Reached reserved task')
                dataset = SimpleNamespace(task=task)
                ledger = SimpleNamespace(summary=lambda: {'calls': 0})
                with patch('examples.gdpevo_pilot.run.GDPevoDataset', return_value=dataset), \
                     patch('examples.gdpevo_pilot.run.CallLedger', return_value=ledger):
                    if changed:
                        with self.assertRaisesRegex(RuntimeError, 'Reached reserved task'):
                            main(root, '/unused', 'probe')
                        self.assertEqual(reads, [('test', '001')])
                    else:
                        result = main(root, '/unused', 'probe')
                        self.assertEqual(result['status'], 'not_run')
                        self.assertEqual(result['reason'], 'identical_deployable_memory')
                        self.assertEqual(reads, [])
                        self.assertEqual(result['ledger']['calls'], 0)


if __name__ == '__main__':
    unittest.main()
