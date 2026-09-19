"""Replay a real rejected summary; scripted repair is not model-effect evidence."""
import copy
import json
from pathlib import Path
import unittest

from examples.gdpevo_pilot.run import MODEL
from memory_orchestrator.learning import _summary_excerpts
from memory_orchestrator.model import StructuredModel
from memory_orchestrator.schemas import DomainError


FIXTURE = json.loads((Path(__file__).parent / 'fixtures/gdpevo_summary_repair_train001.json').read_text())


def scripted_repair():
    """Produce a test response by copying literal supplied text, not by inference."""
    response = copy.deepcopy(FIXTURE['response'])
    draft = json.loads(response['text'])
    fragments = {f['ref_id']: f['text'] for f in FIXTURE['inputs']['evidence_packet']['fragments']}
    repaired = 0
    for observation in draft['observations']:
        for excerpt in observation['excerpts']:
            source = fragments[excerpt['ref_id']]
            if excerpt['quote'] not in source:
                literal = json.dumps(excerpt['quote'], ensure_ascii=False)[1:-1]
                assert literal in source, 'Only the observed nested-string mismatch may be corrected in this fixture.'
                excerpt['quote'] = literal
                repaired += 1
    assert repaired == 4
    response.update(text=json.dumps(draft, ensure_ascii=False), usage=None, request_id='scripted-repair-not-live')
    return response


class SummaryRepairTests(unittest.TestCase):
    def run_model(self, responses, config=None):
        requests = []
        def invoke(request):
            requests.append(copy.deepcopy(request))
            return copy.deepcopy(responses[len(requests) - 1])
        model = StructuredModel(invoke, limits=MODEL if config is None else config)
        supplied = copy.deepcopy(FIXTURE['inputs'])
        def generate():
            return model.generate('summarize_trace_v1', supplied, check=lambda value: _summary_excerpts(
                value, supplied['evidence_packet'], supplied['summary_limits']))
        return generate, requests

    def test_actual_rejected_draft_is_not_silently_unescaped(self):
        with self.assertRaises(DomainError) as caught:
            _summary_excerpts(json.loads(FIXTURE['response']['text']),
                FIXTURE['inputs']['evidence_packet'], FIXTURE['inputs']['summary_limits'])
        self.assertEqual(caught.exception.code, 'summary_evidence')
        self.assertEqual(caught.exception.details['errors'], FIXTURE['diagnostics']['errors'])

    def test_reference_profile_accepts_a_grounded_first_response(self):
        generate, requests = self.run_model([scripted_repair()])
        result = generate()
        self.assertEqual(result['value']['status'], 'completed')
        self.assertEqual(len(requests), 1)
        self.assertEqual(result['usage'][0]['status'], 'completed')

    def test_reference_profile_can_repair_the_recorded_rejection(self):
        generate, requests = self.run_model([FIXTURE['response'], scripted_repair()])
        result = generate()
        self.assertEqual(len(requests), 2)
        self.assertEqual([u['status'] for u in result['usage']], ['invalid_output', 'completed'])
        first, repair = requests
        self.assertEqual(repair['messages'][:2], first['messages'])
        self.assertEqual(repair['messages'][2], {'role': 'assistant', 'content': FIXTURE['response']['text']})
        self.assertIn('summary_evidence', repair['messages'][3]['content'])
        self.assertIn('Current enforced limits:', repair['messages'][3]['content'])
        self.assertGreater(result['usage'][1]['budget']['estimated_input_tokens'], 8000)
        self.assertLessEqual(result['usage'][1]['budget']['estimated_input_tokens'],
                            MODEL['token_budget']['stages']['summarize_trace_v1']['max_input_tokens'])
        self.assertEqual(result['usage'][1]['budget']['budget_status'], 'reserved_unknown')
        self.assertIsNone(result['usage'][1]['input_tokens'])

    def test_lower_request_limit_still_stops_before_second_dispatch(self):
        config = copy.deepcopy(MODEL)
        config['token_budget']['stages']['summarize_trace_v1']['max_input_tokens'] = 8000
        generate, requests = self.run_model([FIXTURE['response'], scripted_repair()], config)
        with self.assertRaises(DomainError) as caught:
            generate()
        self.assertEqual(caught.exception.code, 'model_budget_exhausted')
        self.assertEqual(len(requests), 1)
        inspected = caught.exception.details['preview']
        self.assertEqual(inspected['blocking_reason']['scope'], 'stage_request')
        self.assertGreater(inspected['estimated_input_tokens'], 8000)
        self.assertGreater(inspected['budget']['remaining']['input_tokens'], 100000)


if __name__ == '__main__':
    unittest.main()
