"""Plumbing checks against the pinned, real GDPevo train_001 materials."""
import copy
import json
import os
from pathlib import Path
import unittest

from examples.gdpevo_pilot.dataset import GDPevoDataset, PINNED_COMMIT
from memory_orchestrator.schemas import DomainError


SOURCE=Path(os.environ.get('GDPEVO_SOURCE_ROOT','/tmp/gdpevo-memory-pilot/repo'))


@unittest.skipUnless((SOURCE/'LICENSE').is_file(),'Pinned GDPevo checkout is not present')
class GDPevoDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset=GDPevoDataset(SOURCE)
        cls.group=SOURCE/'data/task_groups/task_group_007'

    def test_task_preserves_full_public_prompt_without_private_paths(self):
        task=self.dataset.task('train','001')
        self.assertEqual(task['task_id'],'train_001')
        self.assertEqual(task['revision'],PINNED_COMMIT)
        self.assertEqual(task['description'],(self.group/'train_tasks/001/input/prompt.txt').read_text())
        self.assertFalse({'gold','eval','answer_path','evaluator_path'} & task.keys())
        self.assertNotIn('/output/',json.dumps(task))
        self.assertEqual(self.dataset.public_files(task['task_id']),{
            'prompt.txt':672,'payloads/answer_template.json':4000,'payloads/expedite_queue_memo.json':1562})

    def test_read_input_only_allows_current_public_files(self):
        expected=(self.group/'train_tasks/001/input/payloads/answer_template.json').read_text()
        self.assertEqual(self.dataset.read_input('train_001','payloads/answer_template.json'),expected)
        self.assertEqual(self.dataset.read_input('train_001','input/payloads/answer_template.json'),expected)
        for path in ('../output/answer.json','/etc/passwd','input/../eval/evaluate.py',
                     'payloads/../../notes/notes.md','../../env/judge_train_eval/train_001/output/answer.json',
                     'input/input/prompt.txt'):
            with self.subTest(path=path),self.assertRaises(DomainError):self.dataset.read_input('train_001',path)

    def test_business_get_matches_real_filtered_data_and_returns_copies(self):
        orders=json.loads((self.group/'env/data/orders.json').read_text())
        expected=[r for r in orders if r['wave']=='TRAIN_TRANSFER_B']
        observed=self.dataset.business_get('/orders',{'wave':'TRAIN_TRANSFER_B'})
        self.assertEqual(observed,expected)
        observed[0]['lines'].clear()
        self.assertEqual(self.dataset.business_get('/orders',{'wave':'TRAIN_TRANSFER_B'}),expected)
        order=self.dataset.business_get('/orders/SO-70000',{})
        self.assertEqual(order,next(r for r in orders if r['order_id']=='SO-70000'))
        inv=self.dataset.business_get('/inventory',{'sku':order['lines'][0]['sku']})
        self.assertEqual(len(inv),3)

    def test_judge_files_and_documented_but_unimplemented_routes_are_denied(self):
        for path in ('/api/judge','/manifest','/inventory/NW-1000','/warehouses/WH_WEST',
                     '/purchase_orders/PO-1','/../train_tasks/001/output/answer.json','https://example.com/orders'):
            with self.subTest(path=path),self.assertRaises(DomainError):self.dataset.business_get(path,{})
        with self.assertRaises(DomainError):self.dataset.business_get('/products',{'sku':'NW-1000'})
        self.assertNotIn('/api/judge',self.dataset.business_docs)
        self.assertNotIn('POST',self.dataset.business_docs)
        self.assertIn('/products/<sku>',self.dataset.business_docs)

    def test_source_commit_is_an_actual_precondition(self):
        with self.assertRaises(DomainError):GDPevoDataset(SOURCE,commit='0'*40)

    def evaluate(self,answer):
        task=self.dataset.task('train','001')
        return self.dataset.evaluate({'request_id':'plumbing-test','case_ref':task['task_id'],'snapshot_digest':'f'*64},
            {'artifact':answer},{'id':task['task_id'],'split':'target','task':task})

    def test_official_positive_and_missing_field_negative_keep_exact_score(self):
        # Private gold is used only in this host-side scorer plumbing test.
        gold=json.loads((self.group/'train_tasks/001/output/answer.json').read_text())
        accepted=self.evaluate(gold)
        self.assertEqual((accepted['outcome'],accepted['score'],accepted['source']),('pass',1.0,'executable'))
        self.assertEqual(len(accepted['evidence'][0]['result']['scoring_points']),8)
        changed=copy.deepcopy(gold);changed['records'][0].pop('shipping_quote')
        rejected=self.evaluate(changed)
        self.assertEqual(rejected['outcome'],'fail')
        self.assertEqual(rejected['score'],15/17)
        self.assertEqual(rejected['evidence'][0]['returncode'],0)

    def test_zero_and_invalid_json_are_not_success_because_exit_code_is_zero(self):
        for answer in ({},'not JSON'):
            scored=self.evaluate(answer)
            self.assertEqual((scored['outcome'],scored['score']),('fail',0.0))
            self.assertEqual(scored['evidence'][0]['returncode'],0)

    def test_request_case_identity_is_bound_before_scoring(self):
        task=self.dataset.task('train','001')
        with self.assertRaises(DomainError):
            self.dataset.evaluate({'request_id':'wrong','case_ref':'train_004'}, {'artifact':{}},
                {'id':'train_001','task':task})


if __name__=='__main__':unittest.main()
