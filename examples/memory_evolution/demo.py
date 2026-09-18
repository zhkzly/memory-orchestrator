"""Offline integration example: real CSV callbacks, deliberately scripted teacher.

This is a mechanism demonstration, not a benchmark or evidence of LLM gains.
Pass a StructuredModel to run_demo(..., model=...) to replace the teacher.
"""
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
import tempfile
import time

from memory_orchestrator.context import select_context
from memory_orchestrator.engine import evolve
from memory_orchestrator.release import rollback
from memory_orchestrator.report import report
from memory_orchestrator.sampling import sample_tasks
from memory_orchestrator.schemas import digest, load_contracts, new_id, validate
from memory_orchestrator.store import Store


CONTEXT = {'max_roots': 2, 'max_context_chars': 12000, 'relation_weight': 0.5}
MODEL_LIMITS = {'max_input_chars': 100000, 'max_output_chars': 16000, 'max_output_tokens': 4000,
                'max_total_input_chars': 500000, 'max_calls': 12, 'max_format_repairs': 1}
LEARNING = {'packet': {'max_chars': 28000, 'max_fragment_chars': 1200, 'max_catalog_refs': 8, 'token_budget': 16000},
            'expanded_packet': {'max_chars': 38000, 'max_fragment_chars': 1200, 'max_catalog_refs': 8, 'token_budget': 24000},
            'max_expansions': 2, 'max_experiences': 3, 'max_read_requests': 4,
            'max_related_experiences': 4, 'max_related_episodes': 8, 'max_related_chars': 16000,
            'candidate_count': 1, 'max_operations': 3, 'max_skills': 20, 'max_asset_bytes': 20000,
            'evaluation_scope': 'local CSV repair; target and regression, no transfer claim'}


def protocol(label):
    return {'id': label, 'comparison_scope': 'local repair', 'repeat_count': 2,
            'required_gates': ['complete_results', 'target_gain', 'regression_non_decrease',
                               'call_budget', 'scope_bound', 'versions_unchanged'],
            'criteria': {'target_mean_gain_must_exceed': 0.0, 'maximum_per_case_regression': 0.0,
                         'maximum_evaluation_calls': 8, 'transfer_claim': False},
            'selection_rule': {'id': 'quality-cost-id/v1', 'order': ['accepted quality gain descending',
                               'evaluation cost ascending', 'candidate digest ascending'], 'missing_cost': 'last'},
            'executor': {'id': 'local-csv/v1', 'config': {}}, 'evaluator': {'id': 'typed-row-check/v1', 'config': {}},
            'allowed_sources': ['executable']}


def task(identifier, rows, expected):
    return {'project_id': 'csv-demo', 'task_id': identifier, 'revision': 'v1', 'task_family': 'csv',
            'description': 'Transform CSV using declared column types. String IDs retain leading zeros; '
                           'empty numeric cells become null. The local executor reads selected Skills asset '
                           'references/csv-policy.json with preserve_string_columns and empty_numeric_as_null booleans.',
            'csv': rows, 'column_types': {'id': 'string', 'amount': 'number'}, 'criteria': {'expected_rows': expected}}


def callbacks(store):
    def execute(request, snapshot, case):
        task_data = case['task']
        manifest = request.get('context_manifest') or select_context(
            store, task_data, CONTEXT, explicit_snapshot=snapshot['snapshot_id'])
        settings, events, consumption = {}, [], []
        for selected in manifest['selected_skills']:
            sid = selected['skill_id']
            ref = sid + '/references/csv-policy.json'
            if ref in snapshot['assets']:
                settings.update(json.loads(snapshot['assets'][ref]))
                events.append({'event_id': 'read_' + sid, 'kind': 'action', 'text': 'Read CSV policy ' + ref,
                               'call_id': ref, 'task_revision': task_data['revision'], 'source_role': 'tool'})
                consumption.append({'skill_id': sid, 'event_id': 'read_' + sid})
        transformed = []
        for row in csv.DictReader(io.StringIO(task_data['csv'])):
            converted = {}
            for key, value in row.items():
                if task_data['column_types'][key] == 'string' and settings.get('preserve_string_columns'):
                    converted[key] = value
                elif value == '' and task_data['column_types'][key] == 'number' and settings.get('empty_numeric_as_null'):
                    converted[key] = None
                else:
                    try:
                        converted[key] = float(value)
                    except ValueError:
                        converted[key] = value
            transformed.append(converted)
        return {'artifact': transformed, 'events': events, 'consumption_events': consumption}

    def evaluate(request, execution, case):
        actual, expected = execution['artifact'], case['criteria']['expected_rows']
        passed = actual == expected
        return {'outcome': 'pass' if passed else 'fail', 'score': float(passed), 'source': 'executable',
                'evidence': [{'actual_rows': actual, 'expected_rows': expected, 'equal': passed}],
                'reason': 'Independent exact comparison against the declared typed-row criterion.'}
    return execute, evaluate


class ScriptedTeacher:
    """Test double for the teacher only; it does not simulate task execution."""
    limits = MODEL_LIMITS

    def __init__(self):
        self.calls = 0

    def generate(self, prompt_id, inputs, *, check=None):
        started = time.monotonic()
        self.calls += 1
        if self.calls > self.limits['max_calls']:
            raise RuntimeError('Scripted demonstration exceeded its explicit call budget')
        if prompt_id == 'extract_v1':
            packet = inputs['evidence_packet']
            refs = [f['ref_id'] for f in packet['fragments']]
            exp = {'kind': 'procedure', 'title': 'Preserve declared CSV column types',
                   'conditions': ['CSV declares string and numeric column types'],
                   'scope': {'task_family': 'csv', 'applies_when': ['CSV has declared types'], 'exclusions': []},
                   'observed_facts': [{'claim': 'A local CSV execution and its checker result are available.', 'evidence_refs': refs}],
                   'guidance': {'steps': ['Use the declared type for each column.', 'Handle empty numeric values explicitly.'],
                                'checks': ['Compare typed rows with the expected result.']},
                   'supporting_refs': refs, 'counterevidence_refs': [], 'alternatives': ['Executor configuration may be wrong.'],
                   'unknowns': ['This constructed local example does not establish generalization.'],
                   'reuse_level': 'task_family', 'boundary_refs': []}
            value = {'status': 'completed', 'experiences': [exp], 'read_requests': [], 'missing_evidence': [], 'reason': ''}
        elif prompt_id == 'diagnose_v1':
            refs = [f['ref_id'] for p in inputs['evidence_packets'] for f in p['fragments']]
            snapshot = inputs['target_snapshot']
            skills = snapshot['skills']
            targets = [{'skill_id': sid, 'revision': skill['revision'], 'rule_id': 'R2'} for sid, skill in skills.items()]
            value = {'route': 'skill_patch', 'hypotheses': [{'claim': 'The CSV policy is absent or incomplete.',
                     'supporting_refs': refs, 'counterevidence_refs': [], 'alternatives': ['An executor defect could require code changes.']}],
                     'targets': targets, 'expected_behavior': 'Preserve declared string IDs and numeric conversion.',
                     'check_plan': [{'purpose': 'target', 'behavior': 'Repair the observed typed-row mismatch.', 'required_evidence': 'Exact output check'},
                                    {'purpose': 'regression', 'behavior': 'Keep ordinary numeric conversion.', 'required_evidence': 'Independent numeric-row check'}],
                     'evidence_refs': refs, 'abstain_reason': ''}
        elif prompt_id == 'propose_v1':
            intent = inputs['change_intent']
            refs = intent['evidence_refs']
            skills = inputs['allowed_skill_contents']
            if not skills:
                owner = 'new:csv-types'
                content = {'title': 'CSV typed conversion', 'scope': {'task_family': 'csv', 'applies_when': ['CSV types declared'], 'exclusions': []},
                           'triggers': ['CSV'], 'preconditions': ['Column schema is supplied'],
                           'steps': ['Load references/csv-policy.json.', 'Preserve declared string columns.'],
                           'exceptions': [], 'checks': ['Check output row values and types.'],
                           'depends_on': [], 'declared_conflicts': [], 'evidence_refs': refs}
                operations = [{'op': 'ADD', 'proposed_slug': 'csv-types', 'content': content}]
                previous = None
                empty = False
            else:
                owner, skill = next(iter(skills.items()))
                operations = [{'op': 'PATCH', 'target_skill_id': owner, 'expected_revision': skill['revision'],
                               'edits': [{'kind': 'REPLACE_RULE', 'rule_id': 'R2',
                                          'text': 'Preserve declared strings; convert empty numeric cells to null.'}]}]
                previous = digest(json.dumps({'preserve_string_columns': True, 'empty_numeric_as_null': False}, sort_keys=True))
                empty = True
            value = {'operations': operations,
                     'asset_edits': [{'op': 'UPSERT', 'owner_skill_ref': owner, 'relative_path': 'references/csv-policy.json',
                                      'expected_hash': previous, 'content': json.dumps({'preserve_string_columns': True, 'empty_numeric_as_null': empty}, sort_keys=True)}],
                     'reason': 'Constructed fixture proposes a narrow CSV policy update.', 'evidence_refs': refs,
                     'expected_behavior': intent['expected_behavior'], 'check_plan': intent['check_plan']}
        else:
            raise ValueError(prompt_id)
        schema = load_contracts()['prompts'][prompt_id]['output_schema']
        value = validate(schema, value)
        if check is not None:
            check(value)
        usage = {'usage_id': new_id('demo_call'), 'prompt_id': prompt_id, 'input_tokens': None,
                 'output_tokens': None, 'total_tokens': None, 'measurement': 'missing',
                 'elapsed_seconds': time.monotonic() - started, 'status': 'scripted', 'model': 'scripted-test-double'}
        return {'value': value, 'usage': [usage], 'attempts': [], 'raw_response': value}


def run_demo(root, *, model=None, rounds=2):
    if rounds not in (1, 2):
        raise ValueError('This bounded demonstration has one or two specified rounds')
    store = Store(root)
    store.remember('user', 'Explain outcomes in Chinese.', 'explicit demonstration input')
    execute, evaluate = callbacks(store)
    first = task('leading-zeros', 'id,amount\n001,10\n', [{'id': '001', 'amount': 10.0}])
    empty = task('empty-numeric', 'id,amount\n009,\n', [{'id': '009', 'amount': None}])
    numeric = task('numeric-regression', 'id,amount\na,2.5\n', [{'id': 'a', 'amount': 2.5}])
    releases, learning_records, after = [], [], []
    teacher_mode = 'scripted' if model is None else 'provided'
    model = model or ScriptedTeacher()
    for i, current in enumerate((first, empty)[:rounds]):
        sampled = sample_tasks(store, [current], execute, evaluate,
            policy={'repeat_count': 2, 'max_parallel': 2, 'purpose': 'learning', 'update_mode': 'task_barrier',
                    'protocol_id': f'csv-learning-{i}', 'executor': {'id': 'local-csv/v1', 'config': {}}},
            context_policy=CONTEXT)
        cases = {'id': f'csv-cases-{i}', 'version': '1', 'cases': [
            {'id': current['task_id'], 'split': 'target', 'task': {k:v for k,v in current.items() if k != 'criteria'}, 'criteria': current['criteria']},
            {'id': numeric['task_id'], 'split': 'regression', 'task': {k:v for k,v in numeric.items() if k != 'criteria'}, 'criteria': numeric['criteria']}]}
        cycle = evolve(store, [ep['episode_id'] for ep in sampled['episodes']], model,
                       learning_policy=LEARNING, case_set=cases, protocol=protocol(f'csv-eval-{i}'),
                       execute=execute, evaluate=evaluate, max_parallel=2)
        learning_records.append(cycle['learning'])
        if cycle['release'] is None:
            continue
        release = cycle['release']
        releases.append(release)
        reused = sample_tasks(store, [current], execute, evaluate,
            policy={'repeat_count': 1, 'max_parallel': 1, 'purpose': 'validation', 'update_mode': 'none',
                    'protocol_id': f'csv-reuse-{i}', 'executor': {'id': 'local-csv/v1', 'config': {}}},
            context_policy=CONTEXT)
        after.append({'snapshot_digest': reused['episodes'][0]['source_snapshot_ref'],
                      'outcome': store.feedback_for(reused['episodes'][0]['episode_id'])[0]['outcome']})
    rolled_back = None
    if len(releases) == 2:
        active = store.active('csv-demo')
        rolled_back = rollback(store, 'csv-demo', releases[0]['release_id'],
                               expected_active_digest=active['snapshot_id'], expected_generation=active['generation'],
                               reason='Demonstrate explicit return to an earlier committed library.')
    return {'evidence_kind': 'constructed local integration; not a benchmark or generalization claim',
            'teacher_mode': teacher_mode,
            'learning_statuses': [r['status'] for r in learning_records], 'release_count': len(releases),
            'after_release': after, 'rollback': rolled_back, 'report': report(store, 'csv-demo')}


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='memory-evolution-') as root:
        print(json.dumps(run_demo(root), ensure_ascii=False, indent=2))
