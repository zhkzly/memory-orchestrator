"""Real failed Teacher output: reusable guidance needs an execution evidence chain."""
import copy
import json
from pathlib import Path
import unittest

from memory_orchestrator.learning import _check_necessity, _check_reusable_extraction
from memory_orchestrator.schemas import DomainError


FIXTURE = json.loads(
    (Path(__file__).parent / 'fixtures/gdpevo_bad_task_family_extraction.json').read_text())


def completed_chain_refs(packet):
    provided = {row['ref_id'] for row in packet['fragments']}
    call = next(row for row in packet['relations']['calls']
                if row['status'] == 'paired' and row['coverage'] == 'complete'
                and set(row['action_refs'] + row['result_refs']) <= provided)
    output = next(row['ref_id'] for row in packet['fragments']
                  if row['structure']['source_role'] == 'environment'
                  and row['structure']['source_kind'] == 'result')
    return [*call['action_refs'], *call['result_refs'], output]


def packet_with_state_link(packet):
    linked = copy.deepcopy(packet)
    output = next(row['ref_id'] for row in linked['fragments']
                  if row['structure']['source_role'] == 'environment'
                  and row['structure']['source_kind'] == 'result')
    feedback = next(row['ref_id'] for row in linked['fragments'] if row['kind'] == 'feedback')
    linked['resource_relations'] = [{
        'from_ref': output, 'to_ref': feedback,
        'resource_ref': 'evaluated-state:real-fixture',
        'relation': 'same_resource_candidate', 'version_match': True, 'coverage': 'complete',
    }]
    return linked


class GroundedLearningTests(unittest.TestCase):
    def test_real_task_family_extraction_is_rejected_when_it_cites_only_task_and_scores(self):
        with self.assertRaises(DomainError) as caught:
            _check_reusable_extraction(copy.deepcopy(FIXTURE['extraction']), FIXTURE['evidence_packet'])
        self.assertEqual(caught.exception.code, 'reusable_evidence_incomplete')
        error = caught.exception.details['errors'][0]
        self.assertEqual(error['reuse_level'], 'task_family')
        self.assertEqual(error['missing_roles'], ['action_result_pair', 'evaluated_output'])
        self.assertEqual(error['repair_options'], ['cite_provided_refs', 'needs_more_evidence',
                                                   'downgrade_to_instance', 'abstain'])

    def test_task_family_extraction_accepts_a_complete_provided_chain(self):
        packet = packet_with_state_link(FIXTURE['evidence_packet'])
        extraction = copy.deepcopy(FIXTURE['extraction'])
        extraction['experiences'][0]['supporting_refs'].extend(completed_chain_refs(packet))
        _check_reusable_extraction(extraction, packet)

    def test_complete_roles_without_artifact_feedback_link_remain_insufficient(self):
        extraction = copy.deepcopy(FIXTURE['extraction'])
        extraction['experiences'][0]['supporting_refs'].extend(completed_chain_refs(FIXTURE['evidence_packet']))
        with self.assertRaises(DomainError) as caught:
            _check_reusable_extraction(extraction, FIXTURE['evidence_packet'])
        self.assertEqual(caught.exception.details['errors'][0]['missing_roles'], ['evaluated_output'])

    def test_instance_experience_can_preserve_a_local_observation_without_full_chain(self):
        extraction = copy.deepcopy(FIXTURE['extraction'])
        extraction['experiences'][0]['reuse_level'] = 'instance'
        _check_reusable_extraction(extraction, FIXTURE['evidence_packet'])

    def test_real_proceed_diagnosis_is_rejected_without_the_same_chain(self):
        with self.assertRaises(DomainError) as caught:
            _check_necessity(copy.deepcopy(FIXTURE['diagnosis']), {}, FIXTURE['evidence_packet'],
                             {'max_compared_skills': 0})
        self.assertEqual(caught.exception.code, 'necessity_invalid')
        grounding = next(row for row in caught.exception.details['errors']
                         if row['path'] == '$.necessity.evidence_refs')
        self.assertEqual(grounding['missing_roles'], ['action_result_pair', 'evaluated_output'])
        self.assertEqual(grounding['repair_options'],
                         ['cite_provided_refs', 'necessity_needs_evidence', 'abstain'])

    def test_proceed_diagnosis_accepts_complete_chain(self):
        packet = packet_with_state_link(FIXTURE['evidence_packet'])
        diagnosis = copy.deepcopy(FIXTURE['diagnosis'])
        diagnosis['necessity']['evidence_refs'].extend(completed_chain_refs(packet))
        _check_necessity(diagnosis, {}, packet, {'max_compared_skills': 0})


if __name__ == '__main__':
    unittest.main()
