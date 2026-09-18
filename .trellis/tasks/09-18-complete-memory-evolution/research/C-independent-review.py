"""Read-only repository audit; every mutable record is under the given /tmp root."""
import copy
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

from memory_orchestrator.schemas import DomainError, digest, new_id
from memory_orchestrator.store import Store
from memory_orchestrator.release import publish
from memory_orchestrator.evaluation import verify_validation
from test_memory_evaluation import case_set, execute_csv, evaluate_csv
from test_memory_verification import VerificationTests


ROOT = Path(sys.argv[1])
ROOT.mkdir(parents=True, exist_ok=True)
evidence = {'source_sha256': {}, 'selection': [], 'publication': []}
for filename in ('verification.py', 'evaluation.py', 'release.py', 'assets.py', 'relations.py'):
    path = Path('src/memory_orchestrator') / filename
    evidence['source_sha256'][str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(name):
    obj = VerificationTests()
    obj.store = Store(ROOT / name)
    obj.project = 'csv-project'
    obj.active = obj.store.ensure_project(obj.project)
    obj.candidate = obj.make_candidate()
    return obj


materials = {'id': 'same-frozen-materials', 'version': 'audit-v1', 'cases': [], 'checks': []}
for name in ('left', 'right', 'unused'):
    case = copy.deepcopy(case_set()['cases'][0])
    case['id'] = 'optional-' + name
    materials['cases'].append(case)
    materials['checks'].append({'check_ref': 'check:' + name, 'purpose': 'distinguish',
        'description': 'Independent CSV case ' + name, 'evidence_kind': 'task',
        'case_ids': [case['id']], 'asset_test_ids': []})

for selected in ('left', 'right'):
    obj = fixture('selection-' + selected)
    diagnosis = {'diagnosis_id': 'diagnosis', 'project_id': obj.project,
        'base_digest': obj.active['snapshot_id'], 'draft': {'check_plan': [{
            'purpose': 'distinguish', 'behavior': 'Resolve a CSV failure explanation',
            'required_evidence': 'Independent exact CSV checker', 'check_ref': 'check:' + selected}]}}
    obj.store.put('diagnoses', diagnosis['diagnosis_id'], diagnosis)
    candidate = {**obj.candidate, 'proposal_id': 'audited-proposal', 'check_plan': [],
        'diagnosis_ref': diagnosis['diagnosis_id'], 'diagnosis_hash': digest(diagnosis)}
    obj.store.put('candidates', candidate['proposal_id'], candidate)
    obj.candidate = candidate
    actual = []
    def execute(request, snapshot, case):
        actual.append({'request_id': request['request_id'], 'case_id': case['id'], 'arm': request['arm']})
        return execute_csv(request, snapshot, case)
    result = obj.compare(verification=materials, execute_fn=execute)
    plan = obj.store.get('evaluation_plans', result['plan_ids'][0])
    assert {row['case_id'] for row in actual} == {'identifiers', 'sum', 'optional-' + selected}
    assert len(actual) == 12 and len({row['request_id'] for row in actual}) == 12
    assert {r['request_id'] for r in plan['requests']} == {r['request_id'] for r in actual}
    assert obj.validation(result)['status'] == 'accepted'
    evidence['selection'].append({'selected_check': 'check:' + selected, 'material_hash': digest(materials),
        'base_digest': obj.active['snapshot_id'], 'candidate_digest': obj.candidate['candidate_digest'],
        'requested_count': len(plan['requests']), 'actual_requests': actual,
        'case_ids': sorted({r['case_id'] for r in actual}), 'validation': 'accepted'})

left, right = evidence['selection']
assert left['candidate_digest'] == right['candidate_digest']
assert left['material_hash'] == right['material_hash']
assert left['case_ids'] != right['case_ids']

obj = fixture('asset-publication')
sid = obj.replace_candidate(script='print("0012")')
result = obj.compare(verification=obj.asset_material(sid))
assert obj.validation(result)['status'] == 'accepted'
verify_validation(obj.store, obj.validation(result))
original_get = obj.store.get
def wrong_asset(kind, identifier):
    value = original_get(kind, identifier)
    if kind == 'asset_checks' and value['kind'] == 'function':
        value['raw']['stdout'] = 'different result while status still says pass'
    return value
try:
    with patch.object(obj.store, 'get', side_effect=wrong_asset):
        obj.promote(result)
except DomainError as error:
    evidence['publication'].append({'probe': 'changed_asset_raw', 'rejected': True, 'code': error.code, 'message': str(error)})
else:
    raise AssertionError('Changed functional evidence was published')
unvalidated = obj.make_candidate('unvalidated')
try:
    publish(obj.store, obj.project, unvalidated['proposal_id'], result['validation_ids'][0], result['selection_id'],
            expected_active_digest=obj.active['snapshot_id'], expected_generation=obj.active['generation'])
except DomainError as error:
    evidence['publication'].append({'probe': 'unvalidated_candidate', 'rejected': True, 'code': error.code, 'message': str(error)})
else:
    raise AssertionError('Unvalidated candidate was published')
assert obj.promote(result)['status'] == 'published'

obj = fixture('contrast-publication')
skill = copy.deepcopy(next(iter(obj.store.snapshot(obj.candidate['candidate_digest'])['skills'].values())))
skill['skill_id'] = 'anchor'
skill['content']['steps'] = ['Infer numeric fields.']
sid = obj.replace_candidate(extra_skills={'anchor': skill})
result = obj.compare(verification={'id': 'actual-views', 'version': 'v1',
    'relation_pairs': [{'from': sid, 'to': 'anchor', 'required': True}]}, execute_view=execute_csv)
assert obj.validation(result)['status'] == 'accepted'
verify_validation(obj.store, obj.validation(result))
original_get = obj.store.get
def wrong_contrast(kind, identifier):
    value = original_get(kind, identifier)
    if kind == 'contrast_results' and value['status'] == 'measured':
        value['value'] += .125
    return value
try:
    with patch.object(obj.store, 'get', side_effect=wrong_contrast):
        obj.promote(result)
except DomainError as error:
    evidence['publication'].append({'probe': 'changed_contrast_value', 'rejected': True, 'code': error.code, 'message': str(error)})
else:
    raise AssertionError('Changed contrast result was published')
assert obj.promote(result)['status'] == 'published'
evidence['status'] = 'all_probes_passed'
(ROOT / 'results.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + '\n')
print(json.dumps({'status': evidence['status'], 'selection': [
    {'case_ids': row['case_ids'], 'request_count': row['requested_count']} for row in evidence['selection']],
    'publication': evidence['publication'], 'results_path': str(ROOT / 'results.json')}, ensure_ascii=False))
