"""Frozen experiment inputs around the same public memory evolution functions."""
from copy import deepcopy
from pathlib import Path
import re

from .engine import evolve
from .report import report, sampling_quality
from .sampling import sample_tasks
from .schemas import DomainError, digest, load_contracts, new_id, now_iso
from .store import Store
from .telemetry import measure_stage


MODES = ('online', 'frozen', 'frozen_microbatch')


def _require(value, message, **details):
    if not value:
        raise DomainError('experiment_contract', message, details)


def audit_splits(dataset, *, unseen_scope):
    """Audit the declared sources/families and public task content, without a model."""
    _require(unseen_scope in ('none', 'instance', 'family'), 'Declare none/instance/family unseen scope.')
    _require(isinstance(dataset.get('adaptation'), list) and isinstance(dataset.get('final'), list)
             and dataset['final'], 'Provide adaptation and nonempty final tasks.')
    selection = dataset.get('selection')
    _require(isinstance(selection, dict) and isinstance(selection.get('cases'), list), 'Provide the selection case set.')
    groups = {'adaptation': dataset['adaptation'], 'selection': [c['task'] for c in selection['cases']],
              'final': dataset['final']}
    rows = {}
    for split, tasks in groups.items():
        values = []
        for task in tasks:
            _require(isinstance(task, dict) and isinstance(task.get('task_id'), str)
                     and isinstance(task.get('revision'), str) and isinstance(task.get('description'), str),
                     'Each task requires its actual identity, revision and public description.', split=split)
            _require(all(task.get(key) is None or isinstance(task[key], str) for key in ('source_id', 'task_family')),
                     'Source and family identities must be text or unknown.', split=split)
            public = {k: v for k, v in task.items()
                      if k not in ('task_id', 'revision', 'project_id', 'source_id', 'criteria', 'private', 'task_family')}
            values.append({'task_id': task['task_id'], 'revision': task['revision'],
                           'source_id': task.get('source_id'), 'task_family': task.get('task_family'),
                           'public_content_hash': digest(public)})
        identities = [v['task_id'] for v in values]
        _require(len(identities) == len(set(identities)), 'Task IDs repeat within a split.', split=split)
        rows[split] = values
    overlaps = {}
    for other in ('adaptation', 'selection'):
        overlap = {}
        for field in ('task_id', 'source_id', 'task_family', 'public_content_hash'):
            left = {v[field] for v in rows[other] if v[field] is not None}
            right = {v[field] for v in rows['final'] if v[field] is not None}
            overlap[field] = sorted(left & right)
        overlaps[other + '_vs_final'] = overlap
    unknown = {split: [r['task_id'] for r in values if not r['source_id'] or not r['task_family']]
               for split, values in rows.items()}
    if unseen_scope != 'none':
        _require(not any(unknown.values()), 'Unseen claims need explicit source and family metadata.', missing=unknown)
        denied = ('task_id', 'source_id', 'public_content_hash') + (('task_family',) if unseen_scope == 'family' else ())
        _require(not any(row[key] for row in overlaps.values() for key in denied),
                 'Final materials overlap with adaptation or selection under the declared claim.', overlaps=overlaps)
    return {'rows': rows, 'overlaps': overlaps, 'missing_metadata': unknown, 'unseen_scope': unseen_scope,
            'claim_boundary': 'Unseen relative to this recorded adaptation/selection material; model pretraining exposure is unknown.'}


def _arm_tasks(tasks, project):
    return [{**deepcopy(task), 'project_id': project} for task in tasks]


def _quality(store, sampled):
    group = store.get('run_groups', sampled['plan_ids'][0]) if sampled['plan_ids'] else None
    view = sampling_quality(store, group['project_id'], sampled['plan_ids']) if group else None
    groups = [] if view is None else view['groups']
    rows = [row for group in groups for row in group['results']]
    planned = len(sampled['planned_run_ids'])
    counts = {state: sum(row['outcome'] == state for row in rows) for state in ('pass', 'fail', 'unknown')}
    counts['unknown'] += planned - len(rows)
    return {'planned_runs': planned, 'outcomes': counts,
            'mean_score': sum(row['score'] for row in rows) / planned
                if planned and len(rows) == planned and all(row['score'] is not None for row in rows) else None}


def run_experiment(root, dataset, execution_factory, model_factory, *, protocol, sampling_policy,
                   context_policy, learning_policy, comparison_protocol, verification=None, seed=None):
    """Run all declared arms; callbacks/teacher are supplied, evolution is not reimplemented.

    execution_factory(store) returns execute/evaluate and optionally execute_view,
    asset_runner. Every arm has a separate Store and the same initial contents.
    An experiment ID is immutable; a partial study is reported rather than silently replayed.
    Sampling/comparison recovery is available through their explicit original-plan APIs.
    """
    dataset, protocol = deepcopy(dataset), deepcopy(protocol)
    sampling_policy, context_policy, learning_policy, comparison_protocol, verification, seed = deepcopy(
        (sampling_policy, context_policy, learning_policy, comparison_protocol, verification, seed))
    modes = protocol.get('modes')
    _require(isinstance(modes, list) and modes and len(modes) == len(set(modes))
             and all(mode in MODES for mode in modes), 'Declare the experiment modes.')
    for name in ('max_learning_cycles_per_arm', 'max_model_calls_per_arm', 'microbatch_size'):
        _require(type(protocol.get(name)) is int and protocol[name] >= (1 if name == 'microbatch_size' else 0),
                 'Declare bounded cycles, model calls and a positive microbatch size.', field=name)
    identifier = protocol.get('id')
    _require(isinstance(identifier, str) and re.fullmatch(r'[A-Za-z0-9_-]+', identifier), 'Use a plain experiment ID.')
    project = protocol.get('project_id')
    _require(isinstance(project, str) and project, 'Declare the project identity shared by isolated arms.')
    _require(isinstance(protocol.get('model_config'), dict), 'Freeze the non-secret model configuration.')
    _require(not any(k.casefold() in ('api_key', 'authorization', 'password', 'secret') for k in protocol['model_config']),
             'Keep credentials outside frozen experiment artifacts.')
    split_audit = audit_splits(dataset, unseen_scope=protocol.get('unseen_scope'))
    control = Store(Path(root) / identifier / 'control')
    _require(not control.list('experiment_plans'), 'Experiment ID already exists; inspect or explicitly recover original plans.')
    source = load_contracts()['source']
    plan = {'experiment_id': identifier, 'project_id': project, 'created_at': now_iso(),
            'dataset_id': dataset.get('id'), 'dataset_version': dataset.get('version'), 'dataset_hash': digest(dataset),
            'dataset': dataset, 'protocol': protocol, 'sampling_policy': deepcopy(sampling_policy),
            'context_policy': deepcopy(context_policy), 'learning_policy': deepcopy(learning_policy),
            'comparison_protocol': deepcopy(comparison_protocol), 'verification': deepcopy(verification),
            'seed': deepcopy(seed), 'seed_hash': digest(seed), 'contract_source': source, 'split_audit': split_audit}
    control.put('experiment_plans', identifier, plan)
    arms, total_calls, cycles = [], 0, 0
    for mode in modes:
        arm_calls, arm_cycles = 0, 0
        store = Store(Path(root) / identifier / mode)
        with measure_stage(store, project, 'prepare', purpose='maintenance', subject_ref=identifier):
            store.initialize_project(project, seed=deepcopy(seed), source={'experiment_id': identifier, 'seed_hash': plan['seed_hash']})
            baseline = store.active(project)
            runtime = execution_factory(store)
            _require(isinstance(runtime, dict) and callable(runtime.get('execute')) and callable(runtime.get('evaluate')),
                     'Execution factory must provide real execute/evaluate functions.')
        selected_cases = deepcopy(dataset['selection'])
        for case in selected_cases['cases']:
            case['task']['project_id'] = project
        tasks = _arm_tasks(dataset['adaptation'], project)
        width = protocol['microbatch_size'] if mode == 'frozen_microbatch' else 1
        steps, stopped = [], None
        for offset in range(0, len(tasks), width):
            batch = tasks[offset:offset + width]
            live = mode != 'frozen'
            effective = {**deepcopy(sampling_policy), 'purpose': 'learning' if live else 'validation',
                         'update_mode': ('frozen_microbatch' if mode == 'frozen_microbatch' else 'task_barrier') if live else 'none'}
            sampled = sample_tasks(store, batch, runtime['execute'], runtime['evaluate'],
                                   policy=effective, context_policy=context_policy)
            # Persist pre-update performance before the same task can influence memory.
            step = {'step_id': new_id('experiment_step'), 'experiment_id': identifier, 'project_id': project,
                    'mode': mode, 'phase': 'adaptation', 'task_ids': [t['task_id'] for t in batch],
                    'sampling': {k: deepcopy(v) for k, v in sampled.items() if k != 'episodes'},
                    'pre_update_quality': _quality(store, sampled), 'snapshot_before': store.active(project),
                    'evolution': None, 'update_status': 'not_requested', 'created_at': now_iso()}
            control.put('experiment_steps', step['step_id'] + '_measured', step)
            if sampled['status'] == 'blocked':
                stopped = 'sampling_blocked'
                steps.append(step)
                break
            if live:
                remaining = protocol['max_model_calls_per_arm'] - arm_calls
                if arm_cycles >= protocol['max_learning_cycles_per_arm'] or remaining <= 0:
                    step['update_status'] = 'budget_exhausted'
                else:
                    teacher = model_factory(store)
                    _require(hasattr(teacher, 'limits') and hasattr(teacher, 'calls') and teacher.calls == 0,
                             'Return a fresh budgeted model for each learning cycle.')
                    _require(type(teacher.limits.get('max_calls')) is int and teacher.limits['max_calls'] > 0,
                             'The model must declare its positive per-cycle call budget.')
                    teacher.limits = {**teacher.limits, 'max_calls': min(teacher.limits['max_calls'], remaining)}
                    _require(load_contracts()['source'] == source, 'Contracts changed during the frozen experiment.')
                    before_calls = teacher.calls
                    result = evolve(store, [ep['episode_id'] for ep in sampled['episodes']], teacher,
                        learning_policy=learning_policy, case_set=selected_cases, protocol=comparison_protocol,
                        execute=runtime['execute'], evaluate=runtime['evaluate'], max_parallel=effective['max_parallel'],
                        verification=verification, execute_view=runtime.get('execute_view'), asset_runner=runtime.get('asset_runner'))
                    used_calls = teacher.calls - before_calls
                    total_calls += used_calls
                    arm_calls += used_calls
                    arm_cycles += 1
                    cycles += 1
                    step.update(evolution=result, update_status=result['status'])
            step['snapshot_after'] = store.active(project)
            control.put('experiment_steps', step['step_id'] + '_finished', step)
            steps.append(step)
        final_batches = []
        frozen_version = store.active(project)
        # Final cases cannot contribute experience, selection or relationship updates.
        if stopped is None:
            for task in _arm_tasks(dataset['final'], project):
                sampling = sample_tasks(store, [task], runtime['execute'], runtime['evaluate'],
                    policy={**deepcopy(sampling_policy), 'purpose': 'final', 'update_mode': 'none'}, context_policy=context_policy)
                _require(store.active(project) == frozen_version, 'Final evaluation changed the library.')
                final_batches.append({'task_id': task['task_id'], 'sampling': {k:v for k,v in sampling.items() if k != 'episodes'},
                                      'quality': _quality(store, sampling)})
                if sampling['status'] == 'blocked':
                    stopped = 'final_sampling_blocked'
                    break
        arm = {'mode': mode, 'store_root': str(store.root), 'baseline': baseline,
               'model_calls': arm_calls, 'learning_cycles': arm_cycles,
               'initial_seed_hash': plan['seed_hash'], 'adaptation_steps': steps, 'final_snapshot': frozen_version,
               'final': final_batches, 'planned_final_tasks': len(dataset['final']),
               'status': stopped or 'completed', 'report': report(store, project)}
        arms.append(arm)
    base = next((arm for arm in arms if arm['mode'] == 'frozen'), None)
    differences = []
    if base is not None:
        known = {row['task_id']: row['quality']['mean_score'] for row in base['final']}
        for arm in arms:
            if arm is base:
                continue
            rows = []
            for task in dataset['final']:
                actual = next((row['quality']['mean_score'] for row in arm['final'] if row['task_id'] == task['task_id']), None)
                baseline_score = known.get(task['task_id'])
                rows.append({'task_id': task['task_id'], 'baseline': baseline_score, 'candidate': actual,
                             'gain': actual - baseline_score if actual is not None and baseline_score is not None else None})
            differences.append({'mode': arm['mode'], 'cases': rows,
                                'mean_gain': sum(row['gain'] for row in rows) / len(rows)
                                    if rows and all(row['gain'] is not None for row in rows) else None})
    result = {'result_id': identifier, 'project_id': project, 'experiment_id': identifier,
              'plan_hash': digest(plan), 'arms': arms, 'differences_vs_frozen': differences,
              'model_calls': total_calls, 'learning_cycles': cycles, 'split_audit': split_audit,
              'evidence_kind': protocol.get('evidence_kind', 'caller-supplied tasks; generalization is limited to declared splits'),
              'created_at': now_iso()}
    control.put('experiment_results', identifier, result)
    return result
