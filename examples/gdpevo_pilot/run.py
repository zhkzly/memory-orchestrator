"""Fixed, small GDPevo diagnostic stages; all evolution uses the ordinary core.

Run development first, preserve the pre-learning store, then explicitly replay a
prompt revision with the same evidence. The final probe is a separate frozen step.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil

from examples.gdpevo_pilot.actor import make_executor
from examples.gdpevo_pilot.dataset import GDPevoDataset
from examples.gdpevo_pilot.sdk import CallLedger, save_json
from examples.memory_evolution.demo import protocol as base_protocol
from memory_orchestrator.engine import evolve
from memory_orchestrator.model import StructuredModel
from memory_orchestrator.report import report
from memory_orchestrator.sampling import sample_tasks
from memory_orchestrator.schemas import DomainError, digest, load_contracts, now_iso
from memory_orchestrator.store import Store


COMMIT = '56d60ae4ae5e067d1ec0ee1f850622e69f422179'
PROJECT = 'gdpevo-group007'
CONTEXT = {'max_roots': 3, 'max_context_chars': 18000, 'relation_weight': 0.5}
ACTOR = {'max_model_calls': 6, 'max_tool_calls': 128, 'max_input_chars': 100000,
         'max_tool_output_chars': 20000, 'max_completion_tokens': 8192, 'context_policy': CONTEXT}
MODEL = {'max_input_chars': 120000, 'max_output_chars': 30000, 'max_output_tokens': 6000,
         'max_total_input_chars': 480000, 'max_calls': 8, 'max_format_repairs': 1}
SDK = {'model': 'gpt-5.6-terra', 'base_url': 'http://localhost:8317/v1', 'timeout': 45,
       'max_calls': 96, 'max_total_input_chars': 3000000, 'max_output_tokens': 8192}
LEARNING = {
    'packet': {'max_chars': 42000, 'max_fragment_chars': 1800, 'max_catalog_refs': 24, 'token_budget': 24000},
    'expanded_packet': {'max_chars': 60000, 'max_fragment_chars': 3000, 'max_catalog_refs': 24, 'token_budget': 34000},
    'max_expansions': 1, 'max_experiences': 3, 'max_read_requests': 3,
    'max_related_experiences': 4, 'max_related_episodes': 6, 'max_related_chars': 12000,
    'candidate_count': 1, 'max_operations': 4, 'max_skills': 12, 'max_asset_bytes': 20000,
    'necessity': {'max_compared_skills': 12},
    'maintenance': {'max_chars': 18000, 'max_pairs': 6, 'max_actions': 4},
    'goal_binding': {'max_events': 6, 'max_bindings': 6, 'max_read_requests': 2, 'max_expansions': 1,
                     'max_catalog_goals': 12,
                     'packet': {'max_chars': 18000, 'max_fragment_chars': 1800, 'max_catalog_refs': 16, 'token_budget': 10000}},
    'evaluation_scope': 'Local procedural improvement for the observed GDPevo train_001 workflow; '
                        'train_004 is a regression check. No general transfer claim. The actor can query official '
                        'read-only business GET endpoints, read public input files and selected Skill assets, and '
                        'submit an answer. It cannot execute scripts or access grading materials. '
                        'Only the trusted checks in verification_catalog are supplied in this pilot.',
}


class ObservedTeacher(StructuredModel):
    def __init__(self, invoke, *, output):
        super().__init__(invoke, limits=MODEL)
        self.output = Path(output)
        self.sequence = 0

    def generate(self, prompt_id, inputs, *, check=None):
        self.sequence += 1
        blocks = {key: {'chars': len(json.dumps(value, ensure_ascii=False, sort_keys=True)),
                        'type': type(value).__name__, 'items': len(value) if isinstance(value, (dict, list)) else None}
                  for key, value in inputs.items()}
        record = {'prompt_id': prompt_id, 'sequence': self.sequence, 'inputs': deepcopy(inputs), 'blocks': blocks,
                  'prompt_digest': digest(load_contracts()['prompts'][prompt_id]), 'status': 'started'}
        path = self.output / f'{self.sequence:02d}-{prompt_id}.json'
        save_json(path, record)
        try:
            result = super().generate(prompt_id, inputs, check=check)
        except BaseException as exc:
            record.update(status='error', error_type=type(exc).__name__, code=getattr(exc, 'code', None))
            save_json(path, record)
            raise
        record.update(status='returned', result=result)
        save_json(path, record)
        return result


def task(dataset, split, number):
    return {**dataset.task(split, number), 'project_id': PROJECT}


def sampling_policy(purpose):
    return {'repeat_count': 1, 'max_parallel': 1, 'purpose': purpose,
            'update_mode': 'task_barrier' if purpose == 'learning' else 'none',
            'protocol_id': 'gdpevo-pilot-' + purpose,
            'executor': {'id': 'sdk-business-get/v2', 'config': {'model': SDK['model'], 'actor': ACTOR, 'dataset_commit': COMMIT,
                         'context_change': 'One current host budget state per model request; task and tools unchanged.'}},
            'evaluator': {'id': 'gdpevo-official-script/v1', 'config': {'commit': COMMIT}},
            'scoring_policy': 'available_artifact'}


def case_set(dataset):
    cases = []
    for number, split in [('001', 'target'), ('004', 'regression')]:
        value = task(dataset, 'train', number)
        cases.append({'id': value['task_id'], 'split': split,
                      'task': {key: val for key, val in value.items() if key not in ('criteria', 'private')},
                      'criteria': value.get('criteria', {'task_id': value['task_id']})})
    return {'id': 'gdpevo007-development', 'version': COMMIT, 'cases': cases}


def protocol():
    value = base_protocol('gdpevo-pilot-comparison/v1')
    value.update(repeat_count=1, comparison_scope='local development repair')
    value['criteria']['maximum_evaluation_calls'] = 4
    value['executor'] = sampling_policy('validation')['executor']
    value['evaluator'] = sampling_policy('validation')['evaluator']
    return value


def main(root, source, stage, *, budget=None):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    dataset = GDPevoDataset(source, group_id='task_group_007', commit=COMMIT)
    sdk_config, ledger_name = deepcopy(SDK), 'calls'
    continuation = None
    if budget is not None:
        continuation = json.loads(Path(budget).read_text())
        prior = CallLedger(root / continuation['previous_ledger'], config=SDK).summary()
        sdk_config = continuation['config']
        ledger_name = continuation['new_ledger']
        if (Path(ledger_name).name != ledger_name or sdk_config['model'] != SDK['model']
                or sdk_config['base_url'] != SDK['base_url']
                or prior['calls'] + sdk_config['max_calls'] > SDK['max_calls']
                or prior['input_chars'] + sdk_config['max_total_input_chars'] > SDK['max_total_input_chars']):
            raise DomainError('pilot_budget', 'Continuation must preserve the model and overall physical-call/input ceiling.')
    ledger = CallLedger(root / ledger_name, config=sdk_config)
    path = root / stage
    if path.exists():
        raise DomainError('pilot_immutable_stage', 'Stage already exists; inspect its original records instead of silently rerunning.')
    path.mkdir()
    repo = Path(__file__).resolve().parents[2]
    measured_sources = [*sorted((repo / 'src/memory_orchestrator').glob('*.py')),
                        *sorted((repo / 'examples/gdpevo_pilot').glob('*.py'))]
    plan = {'stage': stage, 'created_at': now_iso(), 'source_commit': COMMIT,
            'tasks': {'learning': 'train_001', 'regression': 'train_004', 'probe': 'test_001'},
            'actor': ACTOR, 'teacher': MODEL, 'global_sdk': sdk_config, 'continuation': continuation, 'learning': LEARNING,
            'contract_source': load_contracts()['source'], 'prompt_digests': {
                key: digest(value) for key, value in load_contracts()['prompts'].items()},
            'source_hashes': {str(file.relative_to(repo)): hashlib.sha256(file.read_bytes()).hexdigest()
                              for file in measured_sources},
            'seed_support': 'unsupported/unconfirmed; repeated outputs are not paired random seeds',
            'claim': 'Small diagnostic subset with project-specific selection protocol, not an official benchmark score.'}
    save_json(path / 'plan.json', plan)
    if stage == 'probe':
        selected = json.loads((root / 'revised' / 'result.json').read_text())
        if selected.get('status') != 'completed':
            raise DomainError('pilot_probe', 'Development stage must close before the frozen probe.')
        results = []
        for label, origin in [('base', root / 'prelearning-store'), ('memory', root / 'revised/store')]:
            shutil.copytree(origin, path / label)
            store = Store(path / label)
            before = store.active(PROJECT)
            execute = make_executor(store, dataset, ledger, limits=ACTOR)
            sampled = sample_tasks(store, [task(dataset, 'test', '001')], execute, dataset.evaluate,
                                   policy=sampling_policy('final'), context_policy=CONTEXT)
            if store.active(PROJECT) != before:
                raise DomainError('pilot_probe', 'Frozen probe changed the memory version.')
            results.append({'condition': label, 'snapshot': before, 'sampled': sampled, 'report': report(store, PROJECT)})
        result = {'status': 'completed', 'conditions': results, 'ledger': ledger.summary()}
        save_json(path / 'result.json', result)
        print(json.dumps({'stage': stage, 'status': result['status'], 'model_calls': result['ledger']['calls']}, ensure_ascii=False), flush=True)
        return result
    if stage == 'baseline':
        store = Store(path / 'store')
        store.initialize_project(PROJECT, source={'benchmark': 'GDPevo', 'commit': COMMIT, 'mode': 'empty'})
        execute = make_executor(store, dataset, ledger, limits=ACTOR)
        sampled = sample_tasks(store, [task(dataset, 'train', '001')], execute, dataset.evaluate,
                               policy=sampling_policy('learning'), context_policy=CONTEXT)
        save_json(root / 'learning-input.json', sampled)
        shutil.copytree(store.root, root / 'prelearning-store')
    else:
        shutil.copytree(root / 'prelearning-store', path / 'store')
        store = Store(path / 'store')
        execute = make_executor(store, dataset, ledger, limits=ACTOR)
        sampled = json.loads((root / 'learning-input.json').read_text())
    teacher = ObservedTeacher(ledger.teacher_invoke(stage + ':teacher'), output=path / 'teacher-inputs')
    try:
        evolution = evolve(store, [row['episode_id'] for row in sampled['episodes']], teacher,
            learning_policy=LEARNING, case_set=case_set(dataset), protocol=protocol(),
            execute=execute, evaluate=dataset.evaluate, max_parallel=1)
        result = {'status': 'completed', 'evolution': evolution, 'report': report(store, PROJECT), 'ledger': ledger.summary()}
    except BaseException as exc:
        save_json(path / 'interruption.json', {'type': type(exc).__name__, 'code': getattr(exc, 'code', None),
                                              'ledger': ledger.summary()})
        raise
    save_json(path / 'result.json', result)
    print(json.dumps({'stage': stage, 'status': result['status'], 'evolution': evolution['status'],
                      'model_calls': result['ledger']['calls']}, ensure_ascii=False), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--stage', choices=('baseline', 'continued', 'revised', 'probe'), required=True)
    parser.add_argument('--budget', help='Explicit remaining-budget manifest after a recorded transport change')
    args = parser.parse_args()
    main(args.root, args.source, args.stage, budget=args.budget)
