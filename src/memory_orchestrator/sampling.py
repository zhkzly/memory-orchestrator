"""N03/N05: explicit, frozen sampling plans and evidence-bearing feedback."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import math
import time
from itertools import combinations

from .context import select_context
from .outcomes import parse_execution, resolve_scoring_policy
from .schemas import DomainError, digest, json_bytes, new_id, normalize_usage_measurements, now_iso, validate


def _identity(output, request):
    if not isinstance(output, dict):
        raise DomainError('callback_shape', 'Callback must return a JSON object')
    json_bytes(output)
    for field in ('request_id', 'case_id', 'snapshot_digest', 'task_revision'):
        if field in output and output[field] != request[field]:
            raise DomainError('callback_identity', f'Callback returned wrong {field}',
                              {'expected': request[field], 'actual': output[field]})


def _error(exc):
    return {'type': type(exc).__name__, 'code': getattr(exc, 'code', None),
            'message': str(exc), 'details': getattr(exc, 'details', {})}


def record_usage(store, project, stage, purpose, subject, supplied, elapsed):
    """Missing measurements stay missing; elapsed time is measured locally."""
    measurements = normalize_usage_measurements(supplied)
    record = {'usage_id': new_id('usage'), 'project_id': project, 'exclusive_stage': stage,
              'purpose': purpose, 'run_or_proposal_id': subject, **measurements, 'time': elapsed,
              'status': 'reported' if supplied and not measurements['diagnostics'] else 'missing',
              'price_version': supplied.get('price_version') if isinstance(supplied, dict) else None,
              'raw_usage': supplied}
    store.put('usage', record['usage_id'], record)
    return record['usage_id']


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


def sample_tasks(store, tasks, execute, evaluate, *, policy, context_policy):
    """A task or microbatch finishes all assigned slots before learning can start.

    execute(request, snapshot, public_case) and evaluate(request, execution, case)
    are caller-owned functions. Their reported trace/environment observations are
    retained; a successful callback alone never establishes independent resets.
    """
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
    jobs, plans = [], []
    batch_id = new_id('sampling_batch')
    for task in tasks:
        if not all(isinstance(task.get(k), str) and task[k] for k in ('task_id', 'revision', 'description')):
            raise DomainError('sampling_tasks', 'New execution requires task identity, revision and description')
        manifest = select_context(store, task, context_policy, explicit_snapshot=snapshot['snapshot_id'])
        slots = [{'slot_id': new_id('slot'), 'run_id': new_id('run'), 'seed': None,
                  'seed_support': 'unconfirmed'} for _ in range(policy['repeat_count'])]
        plan = validate('RunGroupPlan', {'group_id': new_id('group'), 'project_id': project,
            'task_revision': task['revision'], 'initial_state_digest': task.get('initial_state_digest'),
            'snapshot_digest': snapshot['snapshot_id'], 'active_generation': active['generation'],
            'context_digest': digest(manifest), 'protocol_id': policy['protocol_id'],
            'purpose': purpose, 'update_mode': mode, 'k': len(slots), 'slots': slots,
            'max_parallel': policy['max_parallel'], 'learning_enabled': purpose == 'learning' and mode != 'none',
            'scoring_policy': policy['scoring_policy'], 'batch_ref': batch_id,
            'executor_ref': executor_config['id'], 'executor_config_hash': digest(executor_config['config']),
            'limitations': ['Reset independence and seed support require observations from the execution function.']})
        store.put('run_groups', plan['group_id'], plan)
        public_task = {k: v for k, v in task.items() if k not in ('criteria', 'private')}
        public_case = {'id': task['task_id'], 'split': 'target', 'task': public_task}
        input_ref = new_id('sampling_input')
        store.put('sampling_inputs', input_ref, {'input_id': input_ref, 'project_id': project,
                  'group_id': plan['group_id'], 'task': task, 'policy': policy, 'public_case': public_case,
                  'context_ref': manifest['manifest_id'], 'snapshot_digest': snapshot['snapshot_id'],
                  'visibility': {'public_case': 'executor', 'task.criteria': 'evaluator_only'}})
        plans.append(plan)
        for i, slot in enumerate(slots):
            jobs.append((task, manifest, plan, slot, i, input_ref, public_case))
    batch = validate('SamplingBatchPlan', {'batch_id': batch_id, 'project_id': project,
        'group_ids': [plan['group_id'] for plan in plans], 'update_mode': mode,
        'snapshot_digest': snapshot['snapshot_id']})
    store.put('sampling_batches', batch_id, batch)

    def run(job):
        task, manifest, plan, slot, i, input_ref, public_case = job
        run_id = slot['run_id']
        request = {'request_id': run_id, 'case_id': task['task_id'], 'task_revision': task['revision'],
                   'repeat_index': i, 'snapshot_digest': snapshot['snapshot_id'],
                   'context_manifest': manifest, 'purpose': purpose, 'input_ref': input_ref,
                   'scoring_policy': policy['scoring_policy']}
        started, output, error, binding_error = time.monotonic(), None, None, None
        status = 'completed'
        try:
            output = execute(deepcopy(request), deepcopy(snapshot), deepcopy(public_case))
            _identity(output, request)
            disposition = parse_execution(output, None, policy['scoring_policy'])
            status = disposition['execution_status']
            if status == 'adapter_error':
                raise DomainError('callback_shape', disposition['reason'])
            if status != 'completed':
                error = {'code': status, 'message': 'Execution function reported a non-completed attempt',
                         'details': output.get('error')}
        except Exception as exc:
            error = binding_error = _error(exc)
            status = parse_execution(output, binding_error, policy['scoring_policy'])['execution_status']
        elapsed = time.monotonic() - started
        try:
            json_bytes(output)
        except DomainError:
            output = {'unserializable_repr': repr(output)}
        raw_output = output
        output = output if isinstance(output, dict) else {}
        usage_refs = []
        try:
            usage_refs.append(record_usage(store, project, 'execute', purpose, run_id,
                                            (output or {}).get('usage'), elapsed))
        except DomainError as exc:
            error, binding_error, status = _error(exc), _error(exc), 'adapter_error'
            usage_refs.append(record_usage(store, project, 'execute', purpose, run_id, None, elapsed))
        initial = output.get('initial_state_digest')
        environment_id = output.get('environment_instance_id')
        if initial is not None and (not isinstance(initial, str) or len(initial) != 64 or any(c not in '0123456789abcdef' for c in initial)):
            error, status, initial = {'code': 'invalid_initial_state', 'message': 'Invalid reported initial-state digest'}, 'adapter_error', None
            binding_error = error
        if environment_id is not None and (not isinstance(environment_id, str) or not environment_id):
            error, status, environment_id = {'code': 'invalid_environment', 'message': 'Invalid reported environment identity'}, 'adapter_error', None
            binding_error = error
        gaps = []
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
                for key in ('task_id', 'goal_id', 'source_role', 'parent_event_id', 'parent_episode_id'):
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
        else:
            gaps.append('Detailed execution events were not supplied; result material alone is available.')
        events.append({'event_id': 'result', 'kind': 'result', 'text': json.dumps({'artifact': output.get('artifact'), 'error': error}, ensure_ascii=False),
                       'source_ref': run_id, 'call_id': None, 'task_revision': task['revision'], 'source_role': 'environment'})
        episode = {'episode_id': new_id('episode'), 'project_id': project,
                   'task': {'description': task['description'], 'task_id': task['task_id'], 'revision': task['revision']},
                   'source': {'kind': 'execution_function', 'reference': run_id}, 'events': events,
                   'source_snapshot_ref': snapshot['snapshot_id'], 'context_ref': manifest['manifest_id'],
                   'feedback_refs': [], 'gaps': gaps, 'created_at': now_iso()}
        try:
            validate('EpisodeRecord', episode)
            store._check_episode(episode)
        except DomainError as exc:
            episode['events'] = [events[0], events[-1]]
            episode['gaps'].append('Malformed reported trace omitted from derived index; raw output retained.')
            error, binding_error, status = _error(exc), _error(exc), 'adapter_error'
        disposition = parse_execution(output, binding_error, policy['scoring_policy'])
        status = disposition['execution_status']
        artifact_hash = digest(output['artifact']) if 'artifact' in output and binding_error is None else None
        episode['events'][-1]['text'] = json.dumps({'artifact': output.get('artifact'), 'error': error}, ensure_ascii=False)
        store.put('executions', run_id, {'run_id': run_id, 'project_id': project,
                                        'request': request, 'output': raw_output, 'error': error,
                                        'binding_error': binding_error})
        store.add_episode(episode)
        judged, feedback_error = None, None
        feedback_started = time.monotonic()
        if evaluate is not None and disposition['eligible']:
            try:
                case = {**public_case, 'criteria': task.get('criteria')}
                judged = evaluate(deepcopy(request), deepcopy(output), deepcopy(case))
                _identity(judged, request)
                value = judged.get('score')
                if judged.get('outcome') not in ('pass', 'fail', 'unknown'):
                    raise DomainError('feedback', 'Invalid outcome')
                if judged['outcome'] == 'unknown':
                    if value is not None:
                        raise DomainError('feedback', 'Unknown outcome must have null score')
                elif type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                    raise DomainError('feedback', 'Known outcome requires finite numeric score within [0,1]')
                if judged.get('source') not in ('executable', 'human', 'llm_proxy') or not judged.get('evidence'):
                    raise DomainError('feedback', 'Feedback requires source and observable evidence')
            except Exception as exc:
                feedback_error = _error(exc)
        elif evaluate is None:
            feedback_error = {'code': 'missing_evaluator', 'message': 'No evaluation function provided'}
        else:
            feedback_error = {'code': 'not_evaluated', 'message': disposition['reason'],
                              'execution_status': status, 'scoring_policy': policy['scoring_policy']}
        feedback_raw_id = new_id('feedback_return')
        try:
            json_bytes(judged)
        except DomainError:
            judged = {'unserializable_repr': repr(judged)}
        store.put('evaluation_returns', feedback_raw_id, {'return_id': feedback_raw_id, 'project_id': project,
                  'run_id': run_id, 'output': judged, 'error': feedback_error})
        judged = judged if isinstance(judged, dict) else {}
        try:
            usage_refs.append(record_usage(store, project, 'evaluate', purpose, run_id,
                                            (judged or {}).get('usage'), time.monotonic() - feedback_started))
        except DomainError as exc:
            feedback_error = _error(exc)
            usage_refs.append(record_usage(store, project, 'evaluate', purpose, run_id, None,
                                            time.monotonic() - feedback_started))
        feedback = validate('Feedback', {'check_id': new_id('check'), 'project_id': project,
            'run_id': run_id, 'criterion_id': 'task_outcome', 'task_revision': task['revision'],
            'evaluated_state_digest': artifact_hash, 'evaluator_status': 'error' if feedback_error else 'ok',
            'outcome': 'unknown' if feedback_error else judged['outcome'],
            'score': None if feedback_error else judged['score'],
            'source': 'external' if feedback_error or judged['source'] == 'executable' else judged['source'],
            'visibility': {'learning': 'adaptation', 'validation': 'selection_only', 'final': 'final_only'}[purpose],
            'evidence_refs': [feedback_raw_id], 'reason': json.dumps(feedback_error or {
                'message': judged.get('reason', ''), 'evidence': judged.get('evidence', [])}, ensure_ascii=False),
            'checked_at': None if feedback_error else now_iso(), 'received_at': now_iso(),
            'subject_ref': episode['episode_id'], 'binding_status': 'bound' if artifact_hash else 'partial'})
        store.add_feedback(feedback)
        assessment = validate('TaskAssessment', {'assessment_id': new_id('assessment'), 'project_id': project,
            'run_id': run_id, 'subject_ref': episode['episode_id'], 'protocol_id': plan['protocol_id'],
            'criterion_feedback_ids': [feedback['check_id']], 'outcome': feedback['outcome'], 'score': feedback['score'],
            'aggregation_rule': 'single_task_outcome',
            'unknown_reasons': [f"Feedback {feedback['check_id']} is unknown; inspect its source and evaluator status."]
                               if feedback['outcome'] == 'unknown' else []})
        store.put('assessments', assessment['assessment_id'], assessment)
        error_ref = None
        if error:
            error_ref = new_id('error')
            store.put('errors', error_ref, {'error_id': error_ref, 'project_id': project, 'error': error, 'run_id': run_id})
        consumption, consumption_gaps = _record_consumption(store, project, manifest, output, run_id, learn_relations=plan['learning_enabled']) if binding_error is None else ([], [])
        bundle = validate('RunBundle', {'run_id': run_id, 'slot_id': slot['slot_id'], 'group_id': plan['group_id'],
            'task_revision': task['revision'], 'snapshot_digest': snapshot['snapshot_id'], 'context_digest': digest(manifest),
            'environment_instance_id': environment_id, 'initial_state_digest': initial, 'artifact_digest': artifact_hash,
            'initial_state_binding': initial_binding, 'assessment_ref': assessment['assessment_id'],
            'raw_events_ref': run_id, 'execution_status': status, 'capture_gaps': episode['gaps'] + consumption_gaps,
            'consumption_events': consumption, 'consumption_observability': 'observed' if consumption else 'unknown', 'comparability': False,
            'usage_refs': usage_refs, 'error_ref': error_ref, 'project_id': project, 'executor_ref': executor_config['id']})
        store.put('runs', run_id, bundle)
        return episode, bundle

    with ThreadPoolExecutor(max_workers=min(policy['max_parallel'], len(jobs))) as pool:
        results = list(pool.map(run, jobs))
    receipts = []
    for plan in plans:
        group_runs = [bundle for _, bundle in results if bundle['group_id'] == plan['group_id']]
        receipt = {'receipt_id': new_id('receipt'), 'project_id': project, 'group_id': plan['group_id'],
                   'planned': len(plan['slots']), 'recorded': len(group_runs),
                   'run_ids': [r['run_id'] for r in group_runs],
                   'all_slots_accounted': len(group_runs) == len(plan['slots']),
                   'completed': sum(r['execution_status'] == 'completed' for r in group_runs),
                   'terminal_status_counts': {state: sum(r['execution_status'] == state for r in group_runs)
                                              for state in ('completed', 'cancelled', 'timeout', 'budget_exhausted', 'adapter_error')},
                   'independent_environment_comparability': 'not_verified'}
        store.put('group_receipts', receipt['receipt_id'], receipt)
        receipts.append(receipt['receipt_id'])
    return {'plan_ids': [p['group_id'] for p in plans], 'run_ids': [r['run_id'] for _, r in results],
            'receipt_ids': receipts, 'episodes': [e for e, _ in results]}
