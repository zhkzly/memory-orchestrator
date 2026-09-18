"""Frozen criterion feedback, auditable aggregation and recorded callback recovery.

These functions check identities and complete accounting. They do not establish
that a human or model judgement is semantically correct.
"""
from copy import deepcopy
from contextlib import contextmanager
import fcntl
import math
import os
import time

from .schemas import DomainError, digest, json_bytes, load_contracts, new_id, normalize_usage_measurements, now_iso, validate
from .outcomes import parse_execution, resolve_scoring_policy
from .telemetry import measure_stage


@contextmanager
def recovery_lock(store, scope):
    """Local mutual exclusion for the two existing resumable consumers."""
    path = store._path('sampling-locks', digest(scope) + '.lock', create_parent=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _require(ok, code, message, **details):
    if not ok:
        raise DomainError(code, message, details)


def _get(store, kind, ref):
    try:
        return store.get(kind, ref)
    except DomainError as exc:
        if exc.code == 'NOT_FOUND':
            return None
        raise


def _error(exc):
    return {'type': type(exc).__name__, 'code': getattr(exc, 'code', None),
            'message': str(exc), 'details': deepcopy(getattr(exc, 'details', {}))}


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _criteria(plan):
    criteria, aggregation = plan['criteria'], plan['aggregation']
    ids = [c['criterion_id'] for c in criteria]
    _require(bool(ids) and len(ids) == len(set(ids)), 'feedback_protocol', 'Criterion IDs must be nonempty and unique.')
    kind = aggregation['kind']
    _require(kind in ('single_task_outcome', 'binary_all', 'weighted_sum'), 'feedback_protocol', 'Unknown aggregation rule.')
    if kind == 'single_task_outcome':
        _require(ids == ['task_outcome'], 'feedback_protocol', 'Single outcome uses exactly task_outcome.')
    if kind == 'weighted_sum':
        weights = [c.get('weight') for c in criteria]
        _require(all(_number(w) and w >= 0 for w in weights) and sum(weights) > 0,
                 'feedback_protocol', 'Every weight must be explicit, finite and nonnegative, with positive total.')
        threshold = aggregation.get('threshold')
        _require(_number(threshold) and 0 <= threshold <= 1, 'feedback_protocol', 'Weighted aggregation requires an explicit [0,1] threshold.')
    return ids


def aggregate(plan, feedbacks):
    """Aggregate all frozen criteria. Missing weighted terms never shrink W."""
    ids = _criteria(plan)
    found = {}
    for item in feedbacks:
        cid = item['criterion_id']
        _require(cid in ids and cid not in found, 'feedback_criteria', 'Foreign or duplicate criterion feedback.', criterion_id=cid)
        found[cid] = item
    known = {cid: item for cid, item in found.items() if item['binding_status'] == 'bound'
             and item['evaluator_status'] == 'ok' and item['outcome'] in ('pass', 'fail')
             and _number(item['score']) and 0 <= item['score'] <= 1 and item['evidence_refs']}
    missing = [cid for cid in ids if cid not in known]
    kind = plan['aggregation']['kind']
    bounds, outcome, score = [0.0, 1.0], 'unknown', None
    if kind == 'weighted_sum':
        total = sum(c['weight'] for c in plan['criteria'])
        measured = sum(c['weight'] * known[c['criterion_id']]['score'] for c in plan['criteria'] if c['criterion_id'] in known)
        absent = sum(c['weight'] for c in plan['criteria'] if c['criterion_id'] not in known)
        bounds = [measured / total, (measured + absent) / total]
        if not missing:
            score = measured / total
            outcome = 'pass' if score >= plan['aggregation']['threshold'] else 'fail'
    elif kind == 'binary_all':
        if any(item['outcome'] == 'fail' for item in known.values()):
            score, outcome, bounds = 0.0, 'fail', [0.0, 0.0]
        elif not missing:
            score, outcome, bounds = 1.0, 'pass', [1.0, 1.0]
    elif not missing:
        item = known['task_outcome']
        score, outcome, bounds = item['score'], item['outcome'], [item['score'], item['score']]
    return {'outcome': outcome, 'score': score, 'aggregation_rule': kind,
            'expected_criterion_ids': ids, 'missing_criterion_ids': missing,
            'criterion_coverage': len(known) / len(ids), 'score_bounds': bounds,
            'feedback_sources': sorted({item['source'] for item in found.values()}),
            'unknown_reasons': ['Missing or unbound criterion: ' + cid for cid in missing]}


def freeze_feedback_plan(store, subject, protocol):
    """Freeze effective rubric and stable request IDs before any evaluator call."""
    subject, protocol = deepcopy(subject), deepcopy(protocol)
    selected = protocol.get('feedback') or protocol
    criteria = selected.get('criteria')
    if not isinstance(criteria, list):
        criteria = [{'criterion_id': 'task_outcome', 'rule': subject.get('criteria')}]
    aggregation = selected.get('aggregation', {'kind': 'single_task_outcome'})
    _criteria({'criteria': criteria, 'aggregation': aggregation})
    pid = subject.get('feedback_plan_id') or new_id('feedback_plan')
    requests = [{'request_id': pid + ':' + cid['criterion_id'], 'criterion_id': cid['criterion_id'],
                 'feedback_id': pid + ':feedback:' + cid['criterion_id']} for cid in criteria]
    request = subject.get('request', {})
    proxy = deepcopy(selected.get('proxy'))
    if proxy is not None:
        _require(proxy.get('enabled') is True and isinstance(proxy.get('limits'), dict)
                 and isinstance(proxy.get('packet_limits'), dict), 'feedback_protocol', 'Proxy requires explicit model and packet budgets.')
        prompt = load_contracts()['prompts']['proxy_judge_v1']
        proxy.update(prompt_id='proxy_judge_v1', prompt_digest=digest(prompt))
    plan = validate('FeedbackPlan', {'feedback_plan_id': pid, 'project_id': subject['project_id'],
        'subject': {k: subject.get(k) for k in ('kind', 'ref', 'authority_ref', 'execution_ref')},
        'run_id': subject.get('run_id'), 'task_revision': subject.get('task_revision', request.get('task_revision')),
        'evaluated_state_digest': subject.get('evaluated_state_digest'),
        'protocol_id': protocol.get('protocol_id', protocol.get('id')), 'protocol_hash': digest(protocol),
        'criteria': criteria, 'aggregation': aggregation,
        'scoring_policy': resolve_scoring_policy(protocol.get('scoring_policy'), default='completed_only'),
        'visibility': protocol.get('visibility', 'selection_only'), 'evaluator': protocol.get('evaluator'), 'proxy': proxy,
        'requests': requests, 'assessment_id': subject.get('assessment_id') or pid + ':assessment',
        'created_at': now_iso(), 'request': request, 'batch_id': subject.get('batch_id'),
        'purpose': protocol.get('purpose', {'adaptation': 'learning', 'selection_only': 'validation', 'final_only': 'final'}[protocol.get('visibility', 'selection_only')])})
    existing = _get(store, 'feedback_plans', pid)
    if existing is not None:
        plan['created_at'] = existing['created_at']
    store.put('feedback_plans', pid, plan)
    return plan


def _callback_usage(store, attempt, returned, purpose, subject):
    with measure_stage(store, attempt['project_id'], 'recover', purpose=purpose, subject_ref=attempt['attempt_id']):
        return _save_callback_usage(store, attempt, returned, purpose, subject)


def _save_callback_usage(store, attempt, returned, purpose, subject):
    raw = returned['raw_output']
    model_entries = raw.get('usage') if attempt['stage'] == 'proxy' and isinstance(raw, dict) else None
    if attempt['stage'] == 'proxy' and returned['error']:
        model_entries = returned['error'].get('details', {}).get('usage')
    entries = model_entries if isinstance(model_entries, list) else [None]
    refs = []
    for i, entry in enumerate(entries):
        uid = attempt['attempt_id'] + ':usage:' + str(i)
        if isinstance(entry, dict):
            supplied = {'tokens': {key: entry.get(key) for key in ('input_tokens', 'output_tokens', 'total_tokens')},
                        **{key: entry.get(key) for key in ('monetary_cost', 'currency', 'price_version')}}
            elapsed = entry.get('elapsed_seconds')
        else:
            supplied, elapsed = returned.get('measured_usage'), returned['elapsed_seconds']
        measurements = normalize_usage_measurements(supplied)
        record = {'usage_id': uid, 'project_id': attempt['project_id'],
            'exclusive_stage': 'evaluate' if attempt['stage'] == 'proxy' else attempt['stage'],
            'purpose': purpose, 'request_id': subject, 'run_or_proposal_id': subject,
            'attempt_ref': attempt['attempt_id'], **measurements, 'time': elapsed,
            'status': 'reported' if supplied and not measurements['diagnostics'] else 'missing',
            'price_version': supplied.get('price_version') if isinstance(supplied, dict) else None,
            'raw': entry if entry is not None else supplied}
        store.put('usage', uid, record)
        refs.append(uid)
    return refs


def call_recorded(store, *, project_id, batch_id, run_id, request_ref, stage, config,
                  purpose, subject_ref, callback, args, resolutions=None):
    """One exact recorded callback. Unknown prior side effects need explicit evidence."""
    attempts = sorted((item for item in store.list('callback_attempts', project_id)
                       if item['request_ref'] == request_ref and item['stage'] == stage), key=lambda item: (item['started_at'], item['attempt_id']))
    latest = attempts[-1] if attempts else None
    if latest is not None:
        _require(latest['config_hash'] == digest(config) and latest['run_id'] == run_id and latest['batch_id'] == batch_id,
                 'recovery_binding', 'Stored attempt differs from the frozen request.')
    existing = _get(store, 'callback_returns', latest['attempt_id']) if latest else None
    recovery_ref = None
    if latest is not None and existing is None:
        decision = (resolutions or {}).get(request_ref)
        _require(isinstance(decision, dict), 'recovery_blocked', 'Started callback has no saved return; no automatic retry.',
                 request_ref=request_ref, attempt_ref=latest['attempt_id'], stage=stage)
        row = deepcopy(decision)
        row.update(resolution_id=decision.get('resolution_id') or 'recovery_' + digest([latest['attempt_id'], decision]),
                   project_id=project_id, request_ref=request_ref, created_at=decision.get('created_at') or now_iso())
        row = validate('RecoveryResolution', row)
        _require(bool(row['source']) and bool(row['evidence']), 'recovery_evidence', 'Explicit recovery source and evidence are required.')
        prior_resolution = _get(store, 'recovery_resolutions', row['resolution_id'])
        if prior_resolution is not None:
            row['created_at'] = prior_resolution['created_at']
        store.put('recovery_resolutions', row['resolution_id'], row)
        recovery_ref = row['resolution_id']
        if row['action'] != 'confirmed_not_executed':
            if row['action'] == 'attach_result':
                _require('raw_output' in row, 'recovery_evidence', 'attach_result needs the original callback output.')
                output, error = row['raw_output'], row.get('error')
            else:
                output, error = None, {'code': 'execution_unknown', 'message': 'Explicitly closed without knowing original termination or side effects.', 'recovery_ref': recovery_ref}
            existing = validate('CallbackReturn', {'attempt_id': latest['attempt_id'], 'project_id': project_id,
                'request_ref': request_ref, 'stage': stage, 'returned_at': row['created_at'],
                'raw_output': output, 'error': error, 'measured_usage': row.get('measured_usage'),
                'elapsed_seconds': row.get('elapsed_seconds')})
            store.put('callback_returns', latest['attempt_id'], existing)
    if existing is None:
        aid = 'attempt_' + digest([project_id, request_ref, stage, recovery_ref])
        attempt = validate('CallbackAttempt', {'attempt_id': aid, 'project_id': project_id,
            'batch_id': batch_id, 'run_id': run_id, 'stage': stage, 'request_ref': request_ref,
            'started_at': now_iso(), 'config_hash': digest(config), 'recovery_ref': recovery_ref})
        with measure_stage(store, project_id, 'execute' if stage == 'execute' else 'evaluate', purpose=purpose, subject_ref=aid):
            store.put('callback_attempts', aid, attempt)
        start, output, error = time.monotonic(), None, None
        copied = deepcopy(args)
        before = json_bytes(copied)
        try:
            output = callback(*copied)
            _require(json_bytes(copied) == before, 'callback_mutated_input', 'Callback changed a frozen input.')
            json_bytes(output)
        except Exception as exc:
            error = _error(exc)
        elapsed = time.monotonic() - start
        try:
            json_bytes(output)
        except DomainError:
            output = {'unserializable_repr': repr(output)}
        existing = validate('CallbackReturn', {'attempt_id': aid, 'project_id': project_id,
            'request_ref': request_ref, 'stage': stage, 'returned_at': now_iso(), 'raw_output': output,
            'error': error, 'measured_usage': output.get('usage') if isinstance(output, dict) and stage != 'proxy' else None,
            'elapsed_seconds': elapsed})
        with measure_stage(store, project_id, 'execute' if stage == 'execute' else 'evaluate', purpose=purpose, subject_ref=aid):
            store.put('callback_returns', aid, existing)
        latest = attempt
    _require(existing['attempt_id'] == latest['attempt_id'] and existing['request_ref'] == request_ref
             and existing['project_id'] == project_id and existing['stage'] == stage,
             'recovery_binding', 'Return does not belong to the saved attempt.')
    return {**existing, 'usage_refs': _callback_usage(store, latest, existing, purpose, subject_ref)}


def _check_return(value, request, criterion_id):
    _require(isinstance(value, dict), 'feedback', 'Evaluator must return an object.')
    for key in ('request_id', 'case_id', 'case_ref', 'snapshot_digest', 'task_revision'):
        if key in value:
            _require(value[key] == request.get(key), 'feedback_binding', 'Wrong returned ' + key, expected=request.get(key), actual=value[key])
    if 'criterion_id' in value:
        _require(value['criterion_id'] == criterion_id, 'feedback_binding', 'Wrong returned criterion.')
    _require(value.get('outcome') in ('pass', 'fail', 'unknown'), 'feedback', 'Invalid outcome.')
    _require(value.get('score') is None if value['outcome'] == 'unknown' else
             _number(value.get('score')) and 0 <= value['score'] <= 1, 'feedback', 'Outcome and score disagree.')
    _require(value.get('source') in ('executable', 'human', 'llm_proxy') and bool(value.get('evidence')),
             'feedback', 'Feedback needs source and observable evidence.')


def _execution_source(store, plan, execution_ref):
    if plan['subject']['kind'] == 'episode':
        from .lineage import resolve_episode_source
        episode = store.get('episodes', plan['subject']['ref'])
        _require(episode['project_id'] == plan['project_id'], 'feedback_binding', 'Episode project differs.')
        source = resolve_episode_source(store, episode)
        if source['known']:
            _require(plan['run_id'] == source['run_id'] and plan['task_revision'] == source['task_revision'],
                     'feedback_binding', 'Frozen feedback plan contradicts the known run/revision.')
            if source['group'] is not None:
                _require(plan['protocol_id'] == source['group']['protocol_id']
                         and plan['subject']['authority_ref'] in (None, source['group']['group_id']),
                         'feedback_binding', 'Feedback authority/protocol differs from the known run.')
        raw = source.get('execution')
        if raw is None:
            return None, None
        _require(execution_ref in (None, raw['run_id']), 'feedback_binding', 'Execution reference differs from the episode source.')
        return raw.get('output'), raw.get('binding_error')
    authority = _get(store, 'evaluation_plans', plan['subject']['authority_ref'])
    if authority is None:
        authority = store.get('contrast_plans', plan['subject']['authority_ref'])
    request = next((r for r in authority['requests'] if r['request_id'] == plan['subject']['ref']), None)
    _require(authority['project_id'] == plan['project_id'] and request is not None,
             'feedback_binding', 'Feedback subject is not in its comparison plan.')
    _require(request == plan['request'], 'feedback_binding', 'Feedback request differs from frozen authority.')
    if 'protocol_hash' in authority:
        _require(authority['protocol_hash'] == plan['protocol_hash'], 'feedback_binding', 'Feedback protocol differs from frozen authority.')
    if execution_ref is None:
        return None, None
    raw = store.get('evaluation_returns', execution_ref)
    _require(raw.get('project_id') == plan['project_id'] and raw.get('stage') == 'execute'
             and raw.get('request') == request, 'feedback_binding', 'Comparison execution does not bind its original request.')
    return raw.get('returned'), raw.get('error')


def check_planned_feedback(store, plan, item):
    item = validate('Feedback', item)
    expected = next((r for r in plan['requests'] if r['criterion_id'] == item['criterion_id']), None)
    _require(expected is not None and item.get('feedback_plan_ref') == plan['feedback_plan_id']
             and item['check_id'] == expected['feedback_id'] and item.get('request_ref') == expected['request_id']
             and item['subject_ref'] == plan['subject']['ref'] and item['project_id'] == plan['project_id']
             and item.get('run_id') == plan['run_id'] and item['task_revision'] == plan['task_revision']
             and item['visibility'] == plan['visibility'], 'feedback_binding', 'Criterion feedback differs from its frozen plan.')
    output, error = _execution_source(store, plan, item.get('execution_ref'))
    if item['binding_status'] == 'bound':
        _require(isinstance(output, dict) and 'artifact' in output and error is None
                 and digest(output['artifact']) == item['evaluated_state_digest'], 'feedback_binding', 'Feedback state is not the actual saved artifact.')
    if item.get('attempt_ref') is not None:
        returned = store.get('callback_returns', item['attempt_ref'])
        _require(returned['project_id'] == plan['project_id'] and item['attempt_ref'] in item['evidence_refs'],
                 'feedback_binding', 'Feedback does not cite the saved raw callback.')
        if item['evaluator_status'] == 'ok':
            _require(returned['error'] is None, 'feedback_binding', 'An errored original callback cannot become a successful check.')
            if returned['stage'] == 'proxy':
                _require(item['source'] == 'llm_proxy', 'feedback_source', 'Proxy feedback cannot be promoted to external evidence.')
                values = returned['raw_output']['value']['criterion_findings']
                matched = [v for v in values if v['criterion_id'] == item['criterion_id']]
                _require(len(matched) == 1 and all(item[k] == matched[0][k] for k in ('outcome', 'score')),
                         'feedback_binding', 'Proxy feedback differs from raw judgement.')
            else:
                value = returned['raw_output']
                _check_return(value, plan['request'], item['criterion_id'])
                _require(returned['request_ref'] == expected['request_id'] and returned['error'] is None
                         and all(item[k] == value[k] for k in ('outcome', 'score'))
                         and item['source'] == ('external' if value['source'] == 'executable' else value['source']),
                         'feedback_binding', 'Criterion result differs from original callback.')
    else:
        _require(item['outcome'] == 'unknown' and item['evaluator_status'] != 'ok', 'feedback_binding', 'No callback cannot provide a known assessment.')
    return item


def _correction_source(store, plan, supersedes):
    if supersedes is None:
        return
    _require(supersedes != plan['assessment_id'], 'assessment_binding', 'Assessment cannot supersede itself.')
    previous = store.get('assessments', supersedes)
    _require(previous.get('project_id') == plan['project_id'] and previous['subject_ref'] == plan['subject']['ref']
             and previous['protocol_id'] == plan['protocol_id'], 'assessment_binding', 'Correction refers to another subject or protocol.')
    if previous.get('feedback_plan_ref') is not None:
        original_plan = store.get('feedback_plans', previous['feedback_plan_ref'])
        _require(original_plan['protocol_hash'] == plan['protocol_hash'], 'assessment_binding', 'A correction cannot silently change the original rubric.')


def verify_assessment(store, assessment_or_id, *, expected_subject=None, expected_protocol=None):
    assessment = store.get('assessments', assessment_or_id) if isinstance(assessment_or_id, str) else deepcopy(assessment_or_id)
    assessment = validate('TaskAssessment', assessment)
    plan = validate('FeedbackPlan', store.get('feedback_plans', assessment['feedback_plan_ref']))
    _require(assessment.get('assessment_id') == plan['assessment_id'] and assessment['subject_ref'] == plan['subject']['ref']
             and assessment.get('project_id') == plan['project_id'] and assessment.get('run_id') == plan['run_id']
             and assessment['protocol_id'] == plan['protocol_id'], 'assessment_binding', 'Assessment identity differs from frozen plan.')
    if expected_subject is not None:
        _require(expected_subject == plan['subject'] or expected_subject == plan['subject']['ref'], 'assessment_binding', 'Unexpected assessment subject.')
    if expected_protocol is not None:
        _require(expected_protocol in (plan['protocol_id'], plan['protocol_hash']), 'assessment_binding', 'Unexpected assessment protocol.')
    _correction_source(store, plan, assessment.get('supersedes'))
    feedbacks = [store.get('feedback', ref) for ref in assessment['criterion_feedback_ids']]
    _require(len(assessment['criterion_feedback_ids']) == len(set(assessment['criterion_feedback_ids'])), 'assessment_binding', 'Duplicate criterion references.')
    for item in feedbacks:
        check_planned_feedback(store, plan, item)
        _require(item.get('execution_ref') == assessment.get('execution_ref'), 'assessment_binding', 'Assessment and feedback describe different executions.')
    actual = aggregate(plan, feedbacks)
    for key, value in actual.items():
        _require(assessment.get(key) == value, 'assessment_binding', 'Assessment aggregate differs from original criteria.', field=key)
    return {'plan': plan, 'assessment': assessment, 'feedbacks': feedbacks, 'aggregate': actual}


def _proxy_call(store, plan, execution, case, proxy_model, resolutions):
    cfg = plan['proxy']
    if plan['subject']['kind'] == 'episode':
        from .evidence import index_episodes, build_packet, validate_citations
        packet = build_packet(index_episodes([store.get('episodes', plan['subject']['ref'])], store=store,
                                            trace_limits=cfg.get('trace_limits')), limits=cfg['packet_limits'])
        def citations(value):
            return validate_citations(value, packet)
    else:
        # Comparison has a real callback result, not a fabricated Episode.
        limits = cfg['packet_limits']
        from .evidence import _limits
        _limits(limits)
        text = json_bytes({'artifact': execution.get('artifact'), 'execution_status': execution.get('execution_status')}).decode('utf-8')
        packet = {'fragments': [{'ref_id': plan['subject']['ref'] + ':execution', 'source_hash': digest(text),
            'text': text[:limits['max_fragment_chars']], 'truncated': len(text) > limits['max_fragment_chars']}],
            'limits': limits, 'gaps': ['Only the provided artifact snippet is visible; omitted execution events are not read evidence.',
                'Token estimate = ceil(UTF-8 JSON bytes / 3), not a tokenizer measurement.']}
        while len(json_bytes(packet).decode('utf-8')) > limits['max_chars'] or math.ceil(len(json_bytes(packet)) / 3) > limits['token_budget']:
            fragment = packet['fragments'][0]
            _require(bool(fragment['text']), 'proxy_budget', 'Comparison evidence metadata exceeds packet budget.')
            fragment['text'] = fragment['text'][:len(fragment['text']) // 2]
            fragment['truncated'] = True
        def citations(value):
            allowed = {item['ref_id'] for item in packet['fragments']}
            _require(all(ref in allowed for item in value['criterion_findings'] for ref in item['evidence_refs']),
                     'unsupported_evidence', 'Proxy references unseen evidence.')
    def check(value):
        citations(value)
        ids = [item['criterion_id'] for item in value['criterion_findings']]
        _require(len(ids) == len(set(ids)) and set(ids) <= set(_criteria(plan)), 'feedback_criteria', 'Proxy returned duplicate or foreign criteria.')
        for item in value['criterion_findings']:
            _require(item['outcome'] == 'unknown' or bool(item['evidence_refs']), 'feedback', 'Known proxy judgement needs visible evidence.')
    inputs = {'public_requirements': case.get('task', {}), 'allowed_evidence_packet': packet,
              'permitted_criteria': plan['criteria']}
    def generate():
        _require(callable(getattr(proxy_model, 'generate', None)) and proxy_model.limits == cfg['limits'],
                 'proxy_budget', 'Proxy model must use exactly the frozen finite limits.')
        _require(digest(load_contracts()['prompts']['proxy_judge_v1']) == cfg['prompt_digest'],
                 'proxy_prompt', 'Frozen proxy prompt changed; make a new plan.')
        with recovery_lock(store, 'proxy-model:' + digest(cfg)):
            with measure_stage(store, plan['project_id'], 'evaluate', purpose=plan['purpose'], subject_ref=plan['feedback_plan_id']) as meter:
                details = {}
                try:
                    details = proxy_model.generate('proxy_judge_v1', inputs, check=check)
                    return details
                except DomainError as exc:
                    details = exc.details
                    raise
                finally:
                    for entry in details.get('usage', []):
                        seconds = entry.get('elapsed_seconds')
                        if _number(seconds) and seconds >= 0:
                            meter.exclude(seconds)
    returned = call_recorded(store, project_id=plan['project_id'], batch_id=plan['batch_id'], run_id=plan['run_id'],
        request_ref=plan['feedback_plan_id'] + ':proxy', stage='proxy', config=cfg,
        purpose=plan['purpose'], subject_ref=plan['request'].get('request_id', plan['subject']['ref']),
        callback=generate, args=(), resolutions=resolutions)
    if returned['error'] is None:
        try:
            raw = returned['raw_output']
            _require(isinstance(raw, dict) and isinstance(raw.get('value'), dict), 'feedback', 'Saved proxy return has no structured value.')
            value = validate('ProxyJudgement', raw['value'])
            check(value)
        except DomainError as exc:
            returned = {**returned, 'error': _error(exc)}
    return returned


def assess(store, plan_id, execution, case, *, evaluate=None, proxy_model=None,
           execution_ref=None, request=None, binding_error=None, resolutions=None, supersedes=None):
    plan = validate('FeedbackPlan', store.get('feedback_plans', plan_id))
    _correction_source(store, plan, supersedes)
    if request is not None:
        _require(request == plan['request'], 'feedback_binding', 'Evaluation request differs from frozen plan.')
    existing = _get(store, 'assessments', plan['assessment_id'])
    if existing is not None:
        if supersedes is not None:
            _require(existing.get('supersedes') == supersedes, 'assessment_binding', 'Saved assessment has another correction predecessor.')
        verified = verify_assessment(store, existing)
        return {**verified, 'usage_refs': _assessment_usage(store, verified['feedbacks']), 'blocked': []}
    output, original_error = _execution_source(store, plan, execution_ref)
    _require(output is None or output == execution, 'feedback_binding', 'Supplied execution differs from saved source.')
    disposition = parse_execution(execution, binding_error or original_error, plan['scoring_policy'])
    state = digest(execution['artifact']) if disposition['eligible'] and output is not None else None
    if plan['evaluated_state_digest'] is not None:
        _require(state == plan['evaluated_state_digest'], 'feedback_binding', 'Actual artifact differs from frozen state.')
    proxy, proxy_error = None, None
    if evaluate is None and plan['proxy'] is not None and disposition['eligible']:
        try:
            proxy = _proxy_call(store, plan, execution, case, proxy_model, resolutions)
        except DomainError as exc:
            if exc.code == 'recovery_blocked':
                raise
            if exc.code == 'needs_index':
                raise DomainError('recovery_blocked', 'Another bounded local indexing step is required before proxy evaluation.',
                                  {'request_ref': plan_id + ':proxy_index', 'attempt_ref': None, 'stage': 'proxy_index', **exc.details}) from exc
            proxy_error = _error(exc)
    feedbacks, usages = [], []
    if proxy is not None:
        usages.extend(proxy['usage_refs'])
    for criterion, planned in zip(plan['criteria'], plan['requests']):
        prior = _get(store, 'feedback', planned['feedback_id'])
        if prior is not None:
            check_planned_feedback(store, plan, prior)
            feedbacks.append(prior)
            continue
        value, error, returned = None, None, None
        if evaluate is not None and disposition['eligible']:
            criterion_request = {**plan['request'], 'criterion_id': criterion['criterion_id']}
            criterion_case = {**deepcopy(case), 'criteria': criterion['rule']}
            returned = call_recorded(store, project_id=plan['project_id'], batch_id=plan['batch_id'], run_id=plan['run_id'],
                request_ref=planned['request_id'], stage='evaluate', config=plan['evaluator'], purpose=plan['purpose'],
                subject_ref=plan['request'].get('request_id', plan['subject']['ref']), callback=evaluate,
                args=(criterion_request, execution, criterion_case), resolutions=resolutions)
            usages.extend(returned['usage_refs'])
            value, error = returned['raw_output'], returned['error']
            if error is None:
                try:
                    _check_return(value, plan['request'], criterion['criterion_id'])
                except DomainError as exc:
                    error = _error(exc)
        elif proxy is not None:
            returned, error = proxy, proxy['error']
            if error is None:
                findings = proxy['raw_output']['value']['criterion_findings']
                value = next((item for item in findings if item['criterion_id'] == criterion['criterion_id']), None)
                if value is not None:
                    value = {**value, 'source': 'llm_proxy', 'evidence': value['evidence_refs'], 'reason': value['finding']}
                else:
                    error = {'code': 'missing_criterion', 'message': 'Proxy did not judge this criterion.'}
        else:
            error = proxy_error or {'code': 'not_evaluated', 'message': disposition['reason'] or 'No evaluation function or permitted proxy.'}
        with measure_stage(store, plan['project_id'], 'evaluate', purpose=plan['purpose'], subject_ref=plan_id):
            source = 'llm_proxy' if proxy is not None or proxy_error is not None else 'external'
            if not error:
                source = 'external' if value['source'] == 'executable' else value['source']
            entry = validate('Feedback', {'check_id': planned['feedback_id'], 'project_id': plan['project_id'],
                'run_id': plan['run_id'], 'criterion_id': criterion['criterion_id'], 'task_revision': plan['task_revision'],
                'evaluated_state_digest': state, 'evaluator_status': ('error' if returned else 'missing') if error else 'ok',
                'outcome': 'unknown' if error else value['outcome'], 'score': None if error else value['score'],
                'source': source, 'visibility': plan['visibility'], 'evidence_refs': [returned['attempt_id']] if returned else [],
                'reason': json_bytes(error or {'message': value.get('reason', ''), 'evidence': value.get('evidence', [])}).decode('utf-8'),
                'checked_at': None if error else returned['returned_at'], 'received_at': returned['returned_at'] if returned else plan['created_at'],
                'subject_ref': plan['subject']['ref'], 'binding_status': 'bound' if state is not None else 'partial',
                'feedback_plan_ref': plan_id, 'request_ref': planned['request_id'],
                'attempt_ref': returned['attempt_id'] if returned else None, 'execution_ref': execution_ref})
            store.add_feedback(entry)
            feedbacks.append(entry)
    with measure_stage(store, plan['project_id'], 'evaluate', purpose=plan['purpose'], subject_ref=plan_id):
        assessment = validate('TaskAssessment', {'assessment_id': plan['assessment_id'], 'project_id': plan['project_id'],
            'run_id': plan['run_id'], 'subject_ref': plan['subject']['ref'], 'protocol_id': plan['protocol_id'],
            'criterion_feedback_ids': [item['check_id'] for item in feedbacks], **aggregate(plan, feedbacks),
            'feedback_plan_ref': plan_id, 'execution_ref': execution_ref, 'supersedes': supersedes})
        store.put('assessments', assessment['assessment_id'], assessment)
    return {'plan': plan, 'assessment': assessment, 'feedbacks': feedbacks,
            'aggregate': aggregate(plan, feedbacks), 'usage_refs': sorted(set(usages + _assessment_usage(store, feedbacks))), 'blocked': []}


def _assessment_usage(store, feedbacks):
    attempts = {item.get('attempt_ref') for item in feedbacks} - {None}
    return [item['usage_id'] for item in store.list('usage') if item.get('attempt_ref') in attempts]
