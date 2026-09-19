"""N03/N05: explicit, frozen sampling plans and evidence-bearing feedback."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
import json
import os
import tempfile
import time
from itertools import combinations

from .context import select_context
from .feedback import assess, call_recorded, freeze_feedback_plan, recovery_lock, _get
from .lineage import verify_group_completion
from .outcomes import parse_execution, resolve_scoring_policy
from .schemas import DomainError, digest, json_bytes, new_id, now_iso, validate
from .telemetry import measure_stage


def _identity(output, request):
    if not isinstance(output, dict):
        raise DomainError('callback_shape', 'Callback must return a JSON object')
    json_bytes(output)
    for field in ('request_id', 'case_id', 'snapshot_digest', 'task_revision', 'episode_id'):
        if field in output and output[field] != request[field]:
            raise DomainError('callback_identity', f'Callback returned wrong {field}',
                              {'expected': request[field], 'actual': output[field]})


def _error(exc):
    return {'type': type(exc).__name__, 'code': getattr(exc, 'code', None),
            'message': str(exc), 'details': getattr(exc, 'details', {})}




def _record_consumption(store, project, manifest, output, run_id, *, learn_relations):
    """Only explicit, trace-linked tool observations can support co-use counts."""
    declarations = output.get('consumption_events', [])
    raw_events = output.get('events')
    events = {e['event_id']: e for e in (raw_events if isinstance(raw_events, list) else [])
              if isinstance(e, dict) and isinstance(e.get('event_id'), str)}
    supplied = {s['skill_id'] for s in manifest['selected_skills']}
    consumed, refs, gaps = set(), [], []
    if not isinstance(declarations, list):
        return [], ['Malformed consumption declarations; use remains unknown.']
    for index, item in enumerate(declarations):
        if not isinstance(item, dict):
            gaps.append('Malformed consumption item; use remains unknown.')
            continue
        sid, event_id = item.get('skill_id'), item.get('event_id')
        event = events.get(event_id) if isinstance(event_id, str) else None
        if (not isinstance(sid, str) or sid not in supplied or event is None or event.get('source_role') not in ('tool', 'environment')
                or event.get('kind') not in ('action', 'result', 'observation')):
            gaps.append('Consumption declaration lacks a supplied Skill and an observed tool event.')
            continue
        consumed.add(sid)
        refs.append(f'{run_id}#/output/consumption_events/{index}')
    for first, second in combinations(sorted(consumed) if learn_relations else [], 2):
        identity = 'relation_' + digest([project, run_id, first, second])
        store.put('relations', identity, {'relation_id': identity, 'project_id': project,
                  'from': first, 'to': second, 'kind': 'co_used', 'value': 1,
                  'supporting_refs': refs, 'snapshot_digest': manifest['snapshot_digest'],
                  'evidence_level': 'reported_by_execution_function', 'applicable_context': manifest['task_ref']})
    return refs, gaps


def _request(task, manifest, plan, slot, index):
    return {'request_id': slot['run_id'], 'case_id': task['task_id'], 'task_revision': task['revision'],
            'repeat_index': index, 'snapshot_digest': plan['snapshot_digest'], 'context_manifest': manifest,
            'purpose': plan['purpose'], 'input_ref': plan['input_ref'], 'scoring_policy': plan['scoring_policy'],
            **({'episode_id': slot['episode_id']} if slot.get('episode_id') else {})}


def _archive_episode_trace(store, episode, output, policy):
    """Freeze a local callback trace plus truthful host input/result observations."""
    prior = _get(store, 'episodes', episode['episode_id'])
    if prior is not None:
        store._check_episode(prior)
        if (prior['source'] != episode['source'] or prior['task'] != episode['task'] or prior['events']
                or not prior.get('trace_ref') or output.get('trace_ref') not in (None, prior['trace_ref'])):
            raise DomainError('trace_mismatch', 'Archived Episode differs from this planned execution.')
        manifest = store.get('trace_manifests', prior['trace_ref'])
        if manifest['episode_id'] != episode['episode_id'] or manifest['project_id'] != episode['project_id']:
            raise DomainError('trace_mismatch', 'Trace manifest belongs to another Episode.')
        return prior
    if output.get('trace_ref') is not None:
        raise DomainError('trace_mismatch', 'A trace_ref must already have its exact planned Episode header.')
    from .trace import import_trace
    from pathlib import Path
    if not isinstance(output.get('trace_path'), str) or not output['trace_path']:
        raise DomainError('trace_source', 'trace_path must be an explicit local JSONL path.')
    source = Path(output['trace_path']).absolute()
    store._no_symlinks(source)
    temporary_parent = store._path('traces', '.capture', create_parent=True).parent
    fd, name = tempfile.mkstemp(prefix='.host-trace-', suffix='.jsonl', dir=temporary_parent)
    try:
        try:
            source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
        except BaseException:
            os.close(fd)
            raise
        with os.fdopen(fd, 'wb') as target, os.fdopen(source_fd, 'rb') as original:
            first = {**episode['events'][0], 'event_id': 'host:' + episode['source']['reference'] + ':instruction'}
            last = {**episode['events'][-1], 'event_id': 'host:' + episode['source']['reference'] + ':result'}
            target.write(json_bytes(first) + b'\n')
            final_byte = b'\n'
            while chunk := original.read(65536):
                target.write(chunk)
                final_byte = chunk[-1:]
            if final_byte != b'\n':
                target.write(b'\n')
            target.write(json_bytes(last) + b'\n')
            target.flush(); os.fsync(target.fileno())
        header = {**episode, 'events': [], 'gaps': [*episode['gaps'],
            'Trace raw ranges refer to the composite archive: truthful host input/result lines surround unchanged callback JSONL lines; they are not offsets in the original callback file.']}
        return import_trace(store, header, name, limits=policy.get('trace_limits', {}))
    finally:
        if os.path.exists(name):
            os.unlink(name)


def prepare_sampling(store, tasks, *, policy, context_policy):
    """Freeze all slots, inputs and criterion requests before calling an executor."""
    if not tasks or not isinstance(tasks[0], dict) or not tasks[0].get('project_id'):
        raise DomainError('sampling_tasks', 'Provide a nonempty same-project task batch')
    purpose = policy.get('purpose')
    if purpose not in ('learning', 'validation', 'final'):
        raise DomainError('sampling_policy', 'Explicit purpose is required')
    with measure_stage(store, tasks[0]['project_id'], 'prepare', purpose=purpose) as meter:
        return _prepare_sampling(store, tasks, policy=policy, context_policy=context_policy, meter=meter)


def _prepare_sampling(store, tasks, *, policy, context_policy, meter):
    policy, context_policy, tasks = deepcopy(policy), deepcopy(context_policy), deepcopy(tasks)
    policy['scoring_policy'] = resolve_scoring_policy(policy.get('scoring_policy'), default='completed_only')
    for name in ('repeat_count', 'max_parallel'):
        if type(policy.get(name)) is not int or policy[name] < 1:
            raise DomainError('sampling_policy', f'{name} must be an explicit positive integer')
    purpose, mode = policy.get('purpose'), policy.get('update_mode')
    if purpose not in ('learning', 'validation', 'final') or mode not in ('task_barrier', 'frozen_microbatch', 'none'):
        raise DomainError('sampling_policy', 'Explicit purpose and update_mode are required')
    if purpose != 'learning' and mode != 'none':
        raise DomainError('sampling_policy', 'Validation/final sampling cannot enable learning')
    if not tasks or len({t['project_id'] for t in tasks}) != 1:
        raise DomainError('sampling_tasks', 'Provide a nonempty same-project task batch')
    if mode == 'task_barrier' and len(tasks) != 1:
        raise DomainError('sampling_policy', 'task_barrier takes one task; use frozen_microbatch for a batch')
    if len({(t['task_id'], t['revision']) for t in tasks}) != len(tasks):
        raise DomainError('sampling_tasks', 'Duplicate task/revision in batch')
    executor_config = policy['executor']
    project = tasks[0]['project_id']
    active = store.ensure_project(project)
    snapshot = store.snapshot(active['snapshot_id'])
    plans = []
    batch_id = new_id('sampling_batch')
    for task in tasks:
        if not all(isinstance(task.get(k), str) and task[k] for k in ('task_id', 'revision', 'description')):
            raise DomainError('sampling_tasks', 'New execution requires task identity, revision and description')
        selection_started = time.monotonic()
        manifest = select_context(store, task, context_policy, explicit_snapshot=snapshot['snapshot_id'], purpose=purpose)
        meter.exclude(time.monotonic() - selection_started)
        slots = [{'slot_id': new_id('slot'), 'run_id': new_id('run'), 'seed': None,
                  'episode_id': new_id('episode'), 'feedback_plan_id': new_id('feedback_plan'), 'assessment_id': new_id('assessment'),
                  'seed_support': 'unconfirmed'} for _ in range(policy['repeat_count'])]
        input_ref = new_id('sampling_input')
        plan = validate('RunGroupPlan', {'group_id': new_id('group'), 'project_id': project,
            'task_revision': task['revision'], 'initial_state_digest': task.get('initial_state_digest'),
            'snapshot_digest': snapshot['snapshot_id'], 'active_generation': active['generation'],
            'context_digest': digest(manifest), 'protocol_id': policy['protocol_id'],
            'purpose': purpose, 'update_mode': mode, 'k': len(slots), 'slots': slots,
            'max_parallel': policy['max_parallel'], 'learning_enabled': purpose == 'learning' and mode != 'none',
            'scoring_policy': policy['scoring_policy'], 'batch_ref': batch_id,
            'recovery_version': 1, 'input_ref': input_ref,
            'executor_ref': executor_config['id'], 'executor_config_hash': digest(executor_config['config']),
            'limitations': ['Reset independence and seed support require observations from the execution function.']})
        store.put('run_groups', plan['group_id'], plan)
        public_task = {k: v for k, v in task.items() if k not in ('criteria', 'private')}
        public_case = {'id': task['task_id'], 'split': 'target', 'task': public_task}
        store.put('sampling_inputs', input_ref, {'input_id': input_ref, 'project_id': project,
                  'group_id': plan['group_id'], 'task': task, 'policy': policy, 'public_case': public_case,
                  'context_ref': manifest['manifest_id'], 'snapshot_digest': snapshot['snapshot_id'],
                  'visibility': {'public_case': 'executor', 'task.criteria': 'evaluator_only'}})
        plans.append(plan)
        for i, slot in enumerate(slots):
            request = _request(task, manifest, plan, slot, i)
            protocol = {'protocol_id': policy['protocol_id'], 'purpose': purpose,
                'scoring_policy': policy['scoring_policy'], 'evaluator': policy.get('evaluator'),
                'visibility': {'learning': 'adaptation', 'validation': 'selection_only', 'final': 'final_only'}[purpose]}
            if 'feedback' in policy:
                protocol['feedback'] = policy['feedback']
            freeze_feedback_plan(store, {'kind': 'episode', 'ref': slot['episode_id'], 'project_id': project,
                'authority_ref': plan['group_id'], 'execution_ref': None, 'run_id': slot['run_id'],
                'task_revision': task['revision'], 'request': request, 'criteria': task.get('criteria'),
                'feedback_plan_id': slot['feedback_plan_id'], 'assessment_id': slot['assessment_id'], 'batch_id': batch_id}, protocol)
    batch = validate('SamplingBatchPlan', {'batch_id': batch_id, 'project_id': project,
        'group_ids': [plan['group_id'] for plan in plans], 'update_mode': mode,
        'snapshot_digest': snapshot['snapshot_id'], 'recovery_version': 1, 'created_at': now_iso()})
    store.put('sampling_batches', batch_id, batch)
    return {'batch_id': batch_id, 'plan_ids': batch['group_ids'],
            'planned_run_ids': [slot['run_id'] for plan in plans for slot in plan['slots']],
            'run_ids': [], 'episodes': [], 'receipt_ids': [], 'blocked': [], 'status': 'prepared'}




def resume_sampling(store, batch_id, execute, evaluate, *, resolutions=None, proxy_model=None):
    """Resume exact saved stages; an unreturned attempt is never an implicit retry."""
    with recovery_lock(store, batch_id):
        batch = store.get('sampling_batches', batch_id)
        project = batch['project_id']
        plans = [store.get('run_groups', gid) for gid in batch['group_ids']]
        completed = _get(store, 'sampling_batch_receipts', batch_id + ':receipt')
        if completed is not None:
            with measure_stage(store, project, 'recover', purpose=plans[0]['purpose'], subject_ref=batch_id):
                validate('SamplingBatchReceipt', completed)
                if completed['batch_id'] != batch_id or completed['project_id'] != project or completed['group_ids'] != batch['group_ids']:
                    raise DomainError('recovery_binding', 'Batch receipt differs from frozen membership.')
                result = _result(store, batch, plans, [], completed['receipt_id'])
                if completed['receipt_refs'] != result['receipt_ids']:
                    raise DomainError('recovery_binding', 'Batch receipt does not refer to the actual group receipts.')
                return result
        segment_id = new_id('sampling_segment')
        start, started_at = time.monotonic(), now_iso()
        before = {x['attempt_id'] for x in store.list('callback_attempts', project)}
        segment = {'record_id': segment_id + ':start', 'segment_id': segment_id, 'project_id': project,
                   'batch_id': batch_id, 'started_at': started_at, 'finished_at': None, 'elapsed_seconds': None,
                   'status': 'started', 'started_attempt_ids': [], 'completed_attempt_ids': []}
        store.put('sampling_segments', segment['record_id'], segment)
        result, raised = None, None
        try:
            result = _resume(store, batch, plans, execute, evaluate, resolutions, proxy_model)
        except BaseException as exc:
            raised = exc
        attempts = [x['attempt_id'] for x in store.list('callback_attempts', project)
                    if x['batch_id'] == batch_id and x['attempt_id'] not in before]
        finished = {**segment, 'record_id': segment_id + ':end', 'finished_at': now_iso(),
            'elapsed_seconds': time.monotonic() - start, 'status': 'error' if raised else result['status'],
            'started_attempt_ids': attempts,
            'completed_attempt_ids': [ref for ref in attempts if _get(store, 'callback_returns', ref) is not None]}
        store.put('sampling_segments', finished['record_id'], finished)
        if raised is not None:
            raise raised
        if not result['blocked']:
            result['batch_receipt_id'] = _batch_receipt(store, batch, result['receipt_ids'])
        return result


def _resume(store, batch, plans, execute, evaluate, resolutions, proxy_model):
    project, jobs = batch['project_id'], []
    snapshot = store.snapshot(batch['snapshot_digest'])
    with measure_stage(store, project, 'recover', purpose=plans[0]['purpose'], subject_ref=batch['batch_id']):
        for plan in plans:
            inputs = [item for item in store.list('sampling_inputs', project) if item['group_id'] == plan['group_id']]
            if (len(inputs) != 1 or plan['snapshot_digest'] != batch['snapshot_digest']
                    or plan['project_id'] != project or plan.get('batch_ref') != batch['batch_id']
                    or plan['update_mode'] != batch['update_mode']):
                raise DomainError('recovery_binding', 'Sampling inputs or batch membership cannot be uniquely restored.')
            item = inputs[0]
            manifest = store.get('contexts', item['context_ref'])
            if digest(manifest) != plan['context_digest'] or item['snapshot_digest'] != plan['snapshot_digest']:
                raise DomainError('recovery_binding', 'Stored context/input differs from original plan.')
            for index, slot in enumerate(plan['slots']):
                jobs.append((item['task'], manifest, plan, slot, index, item['input_id'], item['public_case'], item['policy']))

    def run(job):
        task, manifest, plan, slot, i, input_ref, public_case, policy = job
        run_id = slot['run_id']
        purpose, executor_config = plan['purpose'], policy['executor']
        request = _request(task, manifest, {**plan, 'input_ref': input_ref}, slot, i)
        existing = _get(store, 'runs', run_id)
        if existing is not None:
            episodes = ([store.get('episodes', slot['episode_id'])] if slot.get('episode_id') else
                        [e for e in store.list('episodes', project) if e['source']['reference'] == run_id])
            if len(episodes) != 1 or existing['group_id'] != plan['group_id']:
                raise DomainError('recovery_binding', 'Completed run/episode cannot be uniquely restored.')
            if episodes[0]['source']['reference'] != run_id:
                raise DomainError('recovery_binding', 'Planned Episode does not describe this run.')
            return episodes[0], existing
        legacy = batch.get('recovery_version') != 1
        raw = _get(store, 'executions', run_id) if legacy else None
        if legacy:
            if raw is None or raw['request'] != request:
                raise DomainError('recovery_blocked', 'Legacy slot has no proven original return.', {'request_ref': run_id, 'attempt_ref': None, 'stage': 'execute'})
            previous_episodes = [e for e in store.list('episodes', project) if e['source']['reference'] == run_id]
            if len(previous_episodes) > 1:
                raise DomainError('recovery_binding', 'Legacy execution has ambiguous episodes.')
            slot = {**slot, 'episode_id': previous_episodes[0]['episode_id'] if previous_episodes else run_id + ':episode',
                    'feedback_plan_id': run_id + ':feedback_plan', 'assessment_id': run_id + ':assessment'}
            returned = {'raw_output': raw['output'], 'error': raw.get('binding_error'), 'attempt_id': None,
                'returned_at': previous_episodes[0]['created_at'] if previous_episodes else now_iso(),
                'usage_refs': [u['usage_id'] for u in store.list('usage', project) if u.get('run_or_proposal_id') == run_id and u['exclusive_stage'] == 'execute']}
        else:
            returned = call_recorded(store, project_id=project, batch_id=batch['batch_id'], run_id=run_id,
                request_ref=run_id, stage='execute', config=executor_config, purpose=purpose, subject_ref=run_id,
                callback=execute, args=(request, snapshot, public_case), resolutions=resolutions)
        with measure_stage(store, project, 'execute', purpose=purpose, subject_ref=run_id):
            output, error, binding_error = returned['raw_output'], returned['error'], returned['error']
            status = 'completed'
            try:
                if binding_error is not None:
                    raise DomainError(binding_error.get('code') or 'callback_error', binding_error.get('message', 'Callback failed'), binding_error)
                _identity(output, request)
                disposition = parse_execution(output, None, policy['scoring_policy'])
                status = disposition['execution_status']
                if status == 'adapter_error':
                    raise DomainError('callback_shape', disposition['reason'])
                if status != 'completed':
                    error = {'code': status, 'message': 'Execution function reported a non-completed attempt',
                             'details': output.get('error')}
            except Exception as exc:
                error = binding_error = binding_error or _error(exc)
                status = parse_execution(output, binding_error, policy['scoring_policy'])['execution_status']
            try:
                json_bytes(output)
            except DomainError:
                output = {'unserializable_repr': repr(output)}
            raw_output = output
            output = output if isinstance(output, dict) else {}
            usage_refs = list(returned['usage_refs'])
            initial = output.get('initial_state_digest')
            environment_id = output.get('environment_instance_id')
            if initial is not None and (not isinstance(initial, str) or len(initial) != 64 or any(c not in '0123456789abcdef' for c in initial)):
                error, status, initial = {'code': 'invalid_initial_state', 'message': 'Invalid reported initial-state digest'}, 'adapter_error', None
                binding_error = error
            if environment_id is not None and (not isinstance(environment_id, str) or not environment_id):
                error, status, environment_id = {'code': 'invalid_environment', 'message': 'Invalid reported environment identity'}, 'adapter_error', None
                binding_error = error
            gaps = []
            if isinstance(binding_error, dict) and binding_error.get('code') == 'execution_unknown':
                gaps.append('Underlying termination and side effects remain unknown after explicit recovery closure.')
            if initial is None or environment_id is None:
                gaps.append('Execution did not report both reset-state and environment identity; independent comparability unknown.')
            expected_initial = plan['initial_state_digest']
            initial_binding = {'expected': expected_initial, 'reported': initial,
                               'status': 'unknown' if expected_initial is None or initial is None else
                                         'matched' if expected_initial == initial else 'mismatched'}
            if initial_binding['status'] == 'mismatched':
                gaps.append(f'Known initial-state mismatch: planned {expected_initial}, reported {initial}; reset comparability is not established.')
            events = [{'event_id': 'instruction', 'kind': 'instruction', 'text': json_bytes(public_case['task']).decode('utf-8'),
                       'source_ref': f'{input_ref}#/public_case/task', 'call_id': None, 'task_revision': task['revision'],
                       'source_role': 'user', 'task_id': task['task_id']}]
            reported_events = (output or {}).get('events')
            if binding_error is None and isinstance(reported_events, list):
                event_mapping = {}
                duplicate_events = False
                invalid_parents = False
                parent_graph = {}
                for j, event in enumerate(reported_events):
                    if isinstance(event, dict) and isinstance(event.get('event_id'), str):
                        duplicate_events |= event['event_id'] in event_mapping
                        event_mapping[event['event_id']] = f'observation_{j}'
                        if event.get('parent_episode_id') is None and event.get('parent_event_id') is not None:
                            if isinstance(event['parent_event_id'], str):
                                parent_graph[event['event_id']] = event['parent_event_id']
                            else:
                                invalid_parents = True
                for node in parent_graph:
                    seen, current = set(), node
                    while current in parent_graph:
                        if current in seen:
                            invalid_parents = True
                            break
                        seen.add(current)
                        current = parent_graph[current]
                for j, event in enumerate(reported_events):
                    if not isinstance(event, dict):
                        gaps.append(f'Reported event {j} is not an object; original retained in executions.')
                        continue
                    # Host assigns an index; all optional identities remain explicitly unknown.
                    item = {'event_id': f'observation_{j}', 'kind': event.get('kind', 'observation'),
                            'text': event.get('text', ''), 'source_ref': f'{run_id}:events:{j}',
                            'call_id': event.get('call_id'), 'task_revision': event.get('task_revision')}
                    for key in ('task_id', 'goal_id', 'source_role', 'parent_event_id', 'parent_episode_id', 'resources'):
                        if key in event:
                            item[key] = event[key]
                    if item.get('parent_event_id') is not None and item.get('parent_episode_id') is None:
                        if not isinstance(item['parent_event_id'], str) or item['parent_event_id'] not in event_mapping:
                            invalid_parents = True
                            item['parent_event_id'] = None
                        else:
                            item['parent_event_id'] = event_mapping[item['parent_event_id']]
                    events.append(item)
                if duplicate_events or invalid_parents:
                    error, status = {'code': 'event_relations', 'message': 'Raw event identities or parent graph are invalid'}, 'adapter_error'
                    binding_error = error
                    gaps.append('Raw event identities/parents cannot be bound unambiguously; original output retained.')
                    events = events[:1]
            elif isinstance(reported_events, list):
                gaps.append('Detailed events were supplied but cannot be bound because execution metadata is invalid; raw output is retained.')
            elif not output.get('trace_path') and not output.get('trace_ref'):
                gaps.append('Detailed execution events were not supplied; result material alone is available.')
            events.append({'event_id': 'result', 'kind': 'result', 'text': json.dumps({'artifact': output.get('artifact'), 'error': error}, ensure_ascii=False),
                           'source_ref': run_id, 'call_id': None, 'task_revision': task['revision'], 'source_role': 'environment'})
            episode = {'episode_id': slot['episode_id'], 'project_id': project,
                       'task': {'description': task['description'], 'task_id': task['task_id'], 'revision': task['revision']},
                       'source': {'kind': 'execution_function', 'reference': run_id}, 'events': events,
                       'source_snapshot_ref': snapshot['snapshot_id'], 'context_ref': manifest['manifest_id'],
                       'feedback_refs': [], 'gaps': gaps, 'created_at': returned['returned_at']}
            try:
                validate('EpisodeRecord', episode)
                store._check_episode(episode)
            except DomainError as exc:
                episode['events'] = [events[0], events[-1]]
                episode['gaps'].append('Malformed reported trace omitted from derived index; raw output retained.')
                error, binding_error, status = _error(exc), _error(exc), 'adapter_error'
            episode['events'][-1]['text'] = json.dumps({'artifact': output.get('artifact'), 'error': error}, ensure_ascii=False)
            artifact_hash = digest(output['artifact']) if 'artifact' in output and binding_error is None else None
            if artifact_hash is not None:
                episode['events'][-1]['resources'] = [{
                    'kind': 'artifact', 'ref': 'evaluated-state:' + artifact_hash,
                    'access': 'check', 'version_ref': artifact_hash,
                }]
            if binding_error is None and (output.get('trace_path') is not None or output.get('trace_ref') is not None):
                try:
                    if output.get('events') or output.get('trace_path') is not None and output.get('trace_ref') is not None:
                        raise DomainError('trace_source', 'Provide exactly one event source.')
                    episode = _archive_episode_trace(store, episode, output, policy)
                except (DomainError, OSError) as exc:
                    error = binding_error = _error(exc)
                    episode['gaps'].append('Trace archive could not be bound: ' + str(exc))
            if binding_error is not None:
                artifact_hash = None
                if episode.get('events'):
                    episode['events'][-1].pop('resources', None)
            disposition = parse_execution(output, binding_error, policy['scoring_policy'])
            status = disposition['execution_status']
            if legacy and previous_episodes:
                episode = previous_episodes[0]
            if not legacy:
                store.put('executions', run_id, {'run_id': run_id, 'project_id': project,
                                            'request': request, 'output': raw_output, 'error': error,
                                            'binding_error': binding_error})
            store.add_episode(episode)
        if legacy:
            prior = [item for item in store.list('assessments', project) if item.get('run_id') == run_id
                     and item['subject_ref'] == episode['episode_id'] and item['protocol_id'] == plan['protocol_id']]
            if len(prior) != 1:
                raise DomainError('recovery_blocked', 'Legacy evaluator stage is unknown; preserve it or create an explicitly new plan.',
                                  {'request_ref': run_id + ':evaluate', 'attempt_ref': None, 'stage': 'evaluate'})
            store._check_assessment(prior[0])
            assessed = {'assessment': prior[0], 'usage_refs': [u['usage_id'] for u in store.list('usage', project)
                if u.get('run_or_proposal_id') == run_id and u['exclusive_stage'] == 'evaluate']}
        else:
            assessed = assess(store, slot['feedback_plan_id'], raw_output, {**public_case, 'criteria': task.get('criteria')},
                          evaluate=evaluate, proxy_model=proxy_model, execution_ref=run_id, request=request,
                          binding_error=binding_error, resolutions=resolutions)
        with measure_stage(store, project, 'execute', purpose=purpose, subject_ref=run_id):
            assessment = assessed['assessment']
            usage_refs.extend(assessed['usage_refs'])
            error_ref = None
            if error:
                error_ref = run_id + ':error'
                store.put('errors', error_ref, {'error_id': error_ref, 'project_id': project, 'error': error, 'run_id': run_id})
            consumption, consumption_gaps = _record_consumption(store, project, manifest, output, run_id, learn_relations=plan['learning_enabled']) if binding_error is None else ([], [])
            bundle = validate('RunBundle', {'run_id': run_id, 'slot_id': slot['slot_id'], 'group_id': plan['group_id'],
                'task_revision': task['revision'], 'snapshot_digest': snapshot['snapshot_id'], 'context_digest': digest(manifest),
                'environment_instance_id': environment_id, 'initial_state_digest': initial, 'artifact_digest': artifact_hash,
                'initial_state_binding': initial_binding, 'assessment_ref': assessment['assessment_id'],
                'chosen_attempt_ref': returned['attempt_id'],
                'raw_events_ref': run_id, 'execution_status': status, 'capture_gaps': episode['gaps'] + consumption_gaps,
                'consumption_events': consumption, 'consumption_observability': 'observed' if consumption else 'unknown', 'comparability': False,
                'usage_refs': usage_refs, 'error_ref': error_ref, 'project_id': project, 'executor_ref': executor_config['id']})
            store.put('runs', run_id, bundle)
            return episode, bundle

    blocked = []
    def guarded(job):
        try:
            return run(job)
        except DomainError as exc:
            if exc.code != 'recovery_blocked':
                raise
            blocked.append({'code': exc.code, 'message': exc.message, **exc.details})
            return None
    with ThreadPoolExecutor(max_workers=min(plans[0]['max_parallel'], len(jobs))) as pool:
        results = [item for item in pool.map(guarded, jobs) if item is not None]
    for plan in plans:
        group_runs = [bundle for _, bundle in results if bundle['group_id'] == plan['group_id']]
        if len(group_runs) != len(plan['slots']):
            continue
        existing = [r for r in store.list('group_receipts', project) if r['group_id'] == plan['group_id']]
        if existing:
            if len(existing) != 1 or set(existing[0]['run_ids']) != {r['run_id'] for r in group_runs}:
                raise DomainError('recovery_binding', 'Saved group receipt disagrees with actual slots.')
            continue
        receipt = {'receipt_id': plan['group_id'] + ':receipt', 'project_id': project, 'group_id': plan['group_id'],
                   'planned': len(plan['slots']), 'recorded': len(group_runs),
                   'run_ids': [r['run_id'] for r in group_runs],
                   'all_slots_accounted': len(group_runs) == len(plan['slots']),
                   'completed': sum(r['execution_status'] == 'completed' for r in group_runs),
                   'terminal_status_counts': {state: sum(r['execution_status'] == state for r in group_runs)
                                              for state in ('completed', 'cancelled', 'timeout', 'budget_exhausted', 'adapter_error')},
                   'independent_environment_comparability': 'not_verified'}
        store.put('group_receipts', receipt['receipt_id'], receipt)
    return _result(store, batch, plans, blocked, None)


def _result(store, batch, plans, blocked, batch_receipt_id):
    planned = [slot['run_id'] for plan in plans for slot in plan['slots']]
    runs = [ref for ref in planned if _get(store, 'runs', ref) is not None]
    by_run = {}
    expected = {slot['run_id']: slot.get('episode_id') for plan in plans for slot in plan['slots']}
    for ref in runs:
        matches = ([store.get('episodes', expected[ref])] if expected[ref] else
                   [e for e in store.list('episodes', batch['project_id']) if e['source']['reference'] == ref])
        if len(matches) != 1 or matches[0]['source']['reference'] != ref:
            raise DomainError('recovery_binding', 'Run has no unambiguous planned Episode.')
        by_run[ref] = matches[0]
        store._check_episode(matches[0])
    if set(by_run) != set(runs):
        raise DomainError('recovery_binding', 'A recorded run is missing its exact Episode.')
    if not blocked:
        for plan in plans:
            verify_group_completion(store, plan)
    receipts = [r['receipt_id'] for p in plans for r in store.list('group_receipts', batch['project_id']) if r['group_id'] == p['group_id']]
    return {'batch_id': batch['batch_id'], 'plan_ids': batch['group_ids'], 'planned_run_ids': planned,
            'run_ids': runs, 'episodes': [by_run[ref] for ref in runs], 'receipt_ids': receipts,
            'batch_receipt_id': batch_receipt_id, 'blocked': sorted(blocked, key=lambda row: row['request_ref']),
            'status': 'blocked' if blocked else 'completed'}


def _batch_receipt(store, batch, receipt_refs):
    records = [s for s in store.list('sampling_segments', batch['project_id']) if s['batch_id'] == batch['batch_id']]
    starts = {s['segment_id']: s for s in records if s['status'] == 'started'}
    ends = {s['segment_id']: s for s in records if s['status'] != 'started'}
    first = min((s['started_at'] for s in starts.values()), default=None)
    finished = now_iso()
    span = (datetime.fromisoformat(finished.replace('Z', '+00:00')) - datetime.fromisoformat(first.replace('Z', '+00:00'))).total_seconds() if first else None
    receipt = validate('SamplingBatchReceipt', {'receipt_id': batch['batch_id'] + ':receipt',
        'project_id': batch['project_id'], 'batch_id': batch['batch_id'], 'group_ids': batch['group_ids'],
        'receipt_refs': receipt_refs, 'segment_ids': sorted(starts), 'first_started_at': first, 'finished_at': finished,
        'end_to_end_seconds': span, 'known_segment_seconds': sum(s['elapsed_seconds'] for s in ends.values() if s['elapsed_seconds'] is not None),
        'missing_segment_count': sum(ref not in ends or ends[ref]['elapsed_seconds'] is None for ref in starts)})
    store.put('sampling_batch_receipts', receipt['receipt_id'], receipt)
    return receipt['receipt_id']


def sample_tasks(store, tasks, execute, evaluate, *, policy, context_policy, proxy_model=None):
    prepared = prepare_sampling(store, tasks, policy=policy, context_policy=context_policy)
    return resume_sampling(store, prepared['batch_id'], execute, evaluate, proxy_model=proxy_model)
