"""Constructed multi-criterion checks derived from the blueprint CSV feedback."""
from copy import deepcopy
import tempfile
import unittest

from memory_orchestrator.schemas import DomainError
from memory_orchestrator.store import Store
from tests.test_memory_store import feedback


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)

    def criterion(self, cid, outcome='pass', score=1.0):
        item = feedback()
        item.update(check_id='check-' + cid, criterion_id=cid, outcome=outcome, score=score,
                    binding_status='bound', evaluator_status='ok', evaluated_state_digest='a' * 64)
        return item

    def plan(self, kind='binary_all'):
        return {'criteria': [{'criterion_id': 'identifier', 'rule': {'expected': '001'}, 'weight': 1},
                             {'criterion_id': 'total', 'rule': {'expected': 3}, 'weight': 3}],
                'aggregation': {'kind': kind, **({'threshold': .75} if kind == 'weighted_sum' else {})}}

    def test_binary_failure_does_not_hide_missing_criteria_and_unknown_is_not_pass(self):
        from memory_orchestrator.feedback import aggregate
        failed = aggregate(self.plan(), [self.criterion('identifier', 'fail', 0)])
        self.assertEqual((failed['outcome'], failed['score']), ('fail', 0))
        self.assertEqual(failed['missing_criterion_ids'], ['total'])
        self.assertEqual(failed['criterion_coverage'], .5)
        unknown = aggregate(self.plan(), [self.criterion('identifier')])
        self.assertEqual((unknown['outcome'], unknown['score']), ('unknown', None))
        self.assertEqual(aggregate(self.plan(), [self.criterion('identifier'), self.criterion('total')])['outcome'], 'pass')

    def test_weighted_unknown_retains_original_denominator_and_mixed_sources(self):
        from memory_orchestrator.feedback import aggregate
        result = aggregate(self.plan('weighted_sum'), [self.criterion('identifier')])
        self.assertIsNone(result['score'])
        self.assertEqual(result['score_bounds'], [.25, 1.0])
        proxy = self.criterion('total', 'fail', 0)
        proxy['source'] = 'llm_proxy'
        full = aggregate(self.plan('weighted_sum'), [self.criterion('identifier'), proxy])
        self.assertEqual((full['score'], full['outcome']), (.25, 'fail'))
        self.assertEqual(set(full['feedback_sources']), {'external', 'llm_proxy'})

    def test_duplicate_unknown_criterion_and_unbound_success_never_become_best_score(self):
        from memory_orchestrator.feedback import aggregate
        with self.assertRaises(DomainError):
            aggregate(self.plan(), [self.criterion('identifier'), self.criterion('identifier', 'fail', 0)])
        with self.assertRaises(DomainError):
            aggregate(self.plan(), [self.criterion('foreign')])
        partial = self.criterion('total'); partial['binding_status'] = 'partial'
        self.assertEqual(aggregate(self.plan(), [self.criterion('identifier'), partial])['outcome'], 'unknown')


if __name__ == '__main__':
    unittest.main()
