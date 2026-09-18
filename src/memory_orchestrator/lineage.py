"""Known local source facts and their two consumers: binding and learning admission.

No records are synthesized. Feedback can precede RunBundle/receipt persistence;
learning additionally requires the actual known group or microbatch to close.
"""
from .schemas import DomainError, digest
from .outcomes import TERMINAL_STATUSES


def _optional(store, kind, identifier):
    if identifier is None:
        return None
    try:
        return store.get(kind, identifier)
    except DomainError as exc:
        if exc.code != 'NOT_FOUND':
            raise
        return None


def _agree(name, values):
    known = [value for value in values if value is not None]
    if known and any(value != known[0] for value in known[1:]):
        raise DomainError('PROJECT_MISMATCH' if name == 'project_id' else 'REFERENCE_MISMATCH',
                          f'Known source records disagree on {name}.', {'field': name, 'values': known})
    return known[0] if known else None


def resolve_episode_source(store, episode):
    """Read and compare known facts, without requiring a lifecycle receipt."""
    reference = episode['source']['reference']
    run = _optional(store, 'runs', reference)
    execution = _optional(store, 'executions', reference)
    if execution is None and run is not None:
        execution = _optional(store, 'executions', run.get('raw_events_ref'))
    known = run is not None or execution is not None
    run_data, execution_data = run or {}, execution or {}
    request = execution_data.get('request') or {}
    if not isinstance(request, dict):
        raise DomainError('REFERENCE_MISMATCH', 'Known execution request is malformed.')
    sampling_input = _optional(store, 'sampling_inputs', request.get('input_ref'))
    input_data = sampling_input or {}
    group_id = _agree('group_id', [run_data.get('group_id'), input_data.get('group_id')])
    group = _optional(store, 'run_groups', group_id)
    group_data = group or {}
    if known:
        _agree('project_id', [episode['project_id'], run_data.get('project_id'), execution_data.get('project_id'),
                             input_data.get('project_id'), group_data.get('project_id')])
    run_id = _agree('run_id', [reference if known else None, run_data.get('run_id'),
                              execution_data.get('run_id'), request.get('request_id')])
    revision = _agree('task_revision', [run_data.get('task_revision'), request.get('task_revision'), group_data.get('task_revision')])
    snapshot = _agree('snapshot_digest', [run_data.get('snapshot_digest'), request.get('snapshot_digest'),
                                         input_data.get('snapshot_digest'), group_data.get('snapshot_digest'),
                                         episode['source_snapshot_ref'] if known else None])
    if known and revision is not None and episode['task']['revision'] is not None:
        _agree('task_revision', [episode['task']['revision'], revision])
    output = execution_data.get('output')
    binding_error = execution_data.get('binding_error', execution_data.get('error'))
    # Older sampling records used error for a normally returned terminal state.
    if ('binding_error' not in execution_data and isinstance(binding_error, dict)
            and isinstance(output, dict) and binding_error.get('type') is None
            and binding_error.get('code') == output.get('execution_status')
            and output.get('execution_status') in ('timeout', 'cancelled', 'budget_exhausted')):
        binding_error = None
    artifact = digest(output['artifact']) if isinstance(output, dict) and 'artifact' in output and binding_error is None else None
    artifact = _agree('artifact_digest', [run_data.get('artifact_digest'), artifact])
    batch = _optional(store, 'sampling_batches', group_data.get('batch_ref'))
    if batch is not None:
        _agree('project_id', [episode['project_id'], batch.get('project_id')])
        _agree('snapshot_digest', [snapshot, batch.get('snapshot_digest')])
    return {'known': known, 'run_id': run_id, 'project_id': episode['project_id'],
            'task_revision': revision, 'snapshot_digest': snapshot, 'artifact_digest': artifact,
            'run': run, 'group': group, 'execution': execution, 'batch': batch,
            'binding_error': binding_error}


def check_feedback_binding(store, feedback, episode):
    """Reject known contradictions when claiming bound; retain unbound reports."""
    _agree('project_id', [feedback['project_id'], episode['project_id']])
    _agree('subject_ref', [feedback['subject_ref'], episode['episode_id']])
    source = resolve_episode_source(store, episode)
    if feedback['binding_status'] != 'bound':
        return source
    declared_run = feedback.get('run_id')
    if source['known']:
        _agree('run_id', [source['run_id'], declared_run])
    claimed_run = _optional(store, 'runs', declared_run)
    claimed_execution = _optional(store, 'executions', declared_run)
    for record in (claimed_run, claimed_execution):
        if record is not None:
            _agree('project_id', [episode['project_id'], record.get('project_id')])
    checked_source = source
    if not source['known'] and (claimed_run is not None or claimed_execution is not None):
        # Verify the explicitly claimed run without inventing that the imported
        # episode itself has a locally observed execution source.
        checked_source = resolve_episode_source(store, {**episode,
            'source': {**episode['source'], 'reference': declared_run}})
    known_revisions = {episode['task']['revision'], *(e.get('task_revision') for e in episode['events'])} - {None}
    if feedback['task_revision'] is not None and known_revisions and feedback['task_revision'] not in known_revisions:
        raise DomainError('REFERENCE_MISMATCH', 'Bound feedback refers to another observed task revision.',
                          {'known_revisions': sorted(known_revisions), 'actual': feedback['task_revision']})
    if checked_source['known']:
        _agree('task_revision', [feedback['task_revision'], checked_source['task_revision']])
        _agree('artifact_digest', [feedback['evaluated_state_digest'], checked_source['artifact_digest']])
        if checked_source['binding_error'] is not None:
            raise DomainError('REFERENCE_MISMATCH', 'Execution identity/format error prevents a bound feedback claim.')
    return source


def _require(condition, message, **details):
    if not condition:
        raise DomainError('learning_not_permitted', message, details)


def _closed_group(store, group):
    _require(group is not None, 'Known local source has no group plan.')
    _require(group.get('purpose') == 'learning' and group.get('learning_enabled') is True
             and group.get('update_mode') != 'none', 'Frozen or learning-disabled groups cannot train memory.',
             group_id=group.get('group_id'))
    slots = group.get('slots', [])
    run_ids = [slot.get('run_id') for slot in slots]
    slot_ids = [slot.get('slot_id') for slot in slots]
    _require(bool(slots) and all(isinstance(ref, str) and ref for ref in run_ids + slot_ids)
             and len(slots) == group.get('k') and len(set(run_ids)) == len(slots)
             and len(set(slot_ids)) == len(slots), 'Group slot identities are incomplete or duplicated.')
    runs = []
    for slot in slots:
        run = _optional(store, 'runs', slot['run_id'])
        _require(run is not None, 'A planned run has not produced a terminal RunBundle.', run_id=slot['run_id'])
        expected = {'run_id': slot['run_id'], 'slot_id': slot['slot_id'], 'group_id': group['group_id'],
                    'project_id': group['project_id'], 'task_revision': group['task_revision'],
                    'snapshot_digest': group['snapshot_digest'], 'context_digest': group['context_digest'],
                    'executor_ref': group['executor_ref']}
        _require(all(run.get(key) == value for key, value in expected.items()),
                 'RunBundle does not match its frozen planned slot.', run_id=slot['run_id'])
        _require(run.get('execution_status') in TERMINAL_STATUSES, 'Run is not terminal.', run_id=slot['run_id'])
        runs.append(run)
    receipts = [r for r in store.list('group_receipts', project_id=group['project_id']) if r.get('group_id') == group['group_id']]
    _require(len(receipts) == 1, 'Group needs one unambiguous completion receipt.', group_id=group['group_id'])
    receipt = receipts[0]
    statuses = {state: sum(r['execution_status'] == state for r in runs) for state in TERMINAL_STATUSES}
    actual_ids = receipt.get('run_ids', [])
    _require(isinstance(actual_ids, list) and all(isinstance(ref, str) and ref for ref in actual_ids)
             and len(actual_ids) == len(set(actual_ids))
             and set(actual_ids) == set(run_ids) and receipt.get('all_slots_accounted') is True
             and receipt.get('planned') == len(slots) and receipt.get('recorded') == len(runs)
             and receipt.get('completed') == statuses['completed'] and receipt.get('terminal_status_counts') == statuses,
             'Receipt does not describe the actual complete planned run set.', group_id=group['group_id'])
    return receipt


def require_learning_source(store, episode):
    """Require actual local lifecycle closure; unknown external imports stay legal."""
    visited, checked_groups = set(), {}

    def check(current):
        if current['episode_id'] in visited:
            return resolve_episode_source(store, current)
        visited.add(current['episode_id'])
        source = resolve_episode_source(store, current)
        if source['known']:
            _require(source['run'] is not None, 'Local execution has no terminal RunBundle.', episode_id=current['episode_id'])
            group = source['group']
            _require(group is not None, 'Local execution has no frozen group plan.', episode_id=current['episode_id'])
            groups = [group]
            if group['update_mode'] == 'frozen_microbatch':
                batch = source['batch']
                _require(batch is not None, 'Frozen microbatch membership is unknown; no batch is fabricated.')
                ids = batch.get('group_ids', [])
                _require(isinstance(ids, list) and bool(ids) and all(isinstance(ref, str) and ref for ref in ids)
                         and len(ids) == len(set(ids)) and group['group_id'] in ids
                         and batch.get('update_mode') == 'frozen_microbatch', 'Microbatch membership is invalid.')
                groups = [_optional(store, 'run_groups', identifier) for identifier in ids]
                _require(all(g is not None and g.get('batch_ref') == batch['batch_id']
                             and g.get('project_id') == batch['project_id'] and g.get('snapshot_digest') == batch['snapshot_digest']
                             and g.get('update_mode') == 'frozen_microbatch' for g in groups),
                         'Microbatch member plan is missing or contradicts its batch.')
            for member in groups:
                if member['group_id'] not in checked_groups:
                    checked_groups[member['group_id']] = _closed_group(store, member)
            source['receipt'] = checked_groups[group['group_id']]
        for parent_id in dict.fromkeys(e.get('parent_episode_id') for e in current['events']
                                       if e.get('parent_episode_id') and e['parent_episode_id'] != current['episode_id']):
            parent = store.get('episodes', parent_id)
            _agree('project_id', [current['project_id'], parent['project_id']])
            check(parent)
        return source

    return check(episode)
