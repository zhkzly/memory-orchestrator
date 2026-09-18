"""Three experiment arms using the ordinary core and actual local CSV execution.

All data and teacher decisions are constructed fixtures, not benchmark results.
Use run_study(path) to keep the complete plan, trajectory and result records.
"""
import json
import tempfile

from examples.memory_evolution.demo import (
    CONTEXT, LEARNING, ScriptedTeacher, callbacks, protocol as comparison_protocol, task,
)
from memory_orchestrator.experiments import run_experiment


def dataset():
    def item(name, data, expected):
        return {**task(name, data, expected), 'source_id': 'constructed:' + name}
    adaptation = [item('train-ids', 'id,amount\n001,10\n', [{'id': '001', 'amount': 10.0}]),
                  item('train-empty', 'id,amount\n002,\n', [{'id': '002', 'amount': None}])]
    selected = [item('select-ids', 'id,amount\n003,4\n', [{'id': '003', 'amount': 4.0}]),
                item('select-empty', 'id,amount\n004,\n', [{'id': '004', 'amount': None}]),
                item('select-regression', 'id,amount\nz,2\n', [{'id': 'z', 'amount': 2.0}])]
    final = [item('final-ids', 'id,amount\n005,6\n', [{'id': '005', 'amount': 6.0}]),
             item('final-empty', 'id,amount\n006,\n', [{'id': '006', 'amount': None}])]
    cases = [{'id': value['task_id'], 'split': 'regression' if i == 2 else 'target',
              'task': {k: v for k, v in value.items() if k not in ('criteria', 'private')},
              'criteria': value['criteria']} for i, value in enumerate(selected)]
    return {'id': 'csv-study', 'version': 'constructed-v1', 'adaptation': adaptation,
            'selection': {'id': 'csv-selection', 'version': 'v1', 'cases': cases}, 'final': final}


def run_study(root):
    config = {'id': 'study', 'project_id': 'csv-demo', 'modes': ['online', 'frozen', 'frozen_microbatch'],
              'microbatch_size': 2, 'max_learning_cycles_per_arm': 2, 'max_model_calls_per_arm': 24,
              'model_config': {'model': 'scripted-test-double'}, 'unseen_scope': 'instance',
              'evidence_kind': 'constructed CSV protocol integration'}
    sampling = {'repeat_count': 2, 'max_parallel': 2, 'protocol_id': 'csv-sampling',
                'executor': {'id': 'local-csv/v1', 'config': {}},
                'evaluator': {'id': 'typed-row-check/v1', 'config': {}}}
    comparison = comparison_protocol('csv-study-comparison')
    comparison['criteria']['maximum_evaluation_calls'] = 12
    def runtime(store):
        execute, evaluate = callbacks(store)
        return {'execute': execute, 'evaluate': evaluate}
    return run_experiment(root, dataset(), runtime, lambda store: ScriptedTeacher(), protocol=config,
        sampling_policy=sampling, context_policy=CONTEXT, learning_policy=LEARNING, comparison_protocol=comparison)


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='memory-study-') as root:
        result = run_study(root)
        print(json.dumps({'evidence_kind': result['evidence_kind'],
                          'arms': [{'mode': row['mode'], 'status': row['status'],
                                    'model_calls': row['model_calls'], 'learning_cycles': row['learning_cycles'],
                                    'final_generation': row['final_snapshot']['generation']} for row in result['arms']],
                          'differences_vs_frozen': result['differences_vs_frozen']}, ensure_ascii=False, indent=2))
