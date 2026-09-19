"""Finite, recorded comparisons. Callback correctness remains the caller's duty."""
from __future__ import annotations

import copy
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .schemas import DomainError, digest, new_id, now_iso, validate
from .outcomes import parse_execution, resolve_scoring_policy
from .telemetry import measure_stage


BASE_GATES = {"complete_results", "target_gain", "regression_non_decrease",
              "call_budget", "scope_bound", "versions_unchanged"}
OPTIONAL_GATES = {"transfer_gain", "transfer_non_decrease", "cost", "stability"}
ORDER = ["accepted quality gain descending", "evaluation cost ascending", "candidate digest ascending"]


def _require(condition, code, message):
    if not condition:
        raise DomainError(code, message)


def _number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _json(value):
    """Validate JSON without silently coercing keys, tuples or nonfinite numbers."""
    if value is None or type(value) in (str, bool, int):
        return copy.deepcopy(value)
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) is list:
        return [_json(v) for v in value]
    if type(value) is dict and all(type(k) is str for k in value):
        return {k: _json(v) for k, v in value.items()}
    raise DomainError("invalid_json", "Expected finite JSON values")


def _raw(value):
    """Preserve invalid callback values explicitly, instead of losing the return."""
    try:
        return _json(value)
    except (DomainError, ValueError, OverflowError):
        if type(value) is dict:
            return {str(k): _raw(v) for k, v in value.items()}
        if type(value) in (list, tuple):
            return [_raw(v) for v in value]
        return {"non_json_type": type(value).__name__, "representation": repr(value)}


def _error(exc):
    return {"type": type(exc).__name__, "message": str(exc),
            "code": getattr(exc, "code", None), "details": _raw(getattr(exc, "details", None))}


def _rejected_target_context(store, execution_ref):
    """Resolve one immutable rejected target execution without relabeling other validation material."""
    execution = store.get('evaluation_returns', execution_ref)
    results = [row for row in store.list('evaluation_results')
               if row.get('execution_ref') == execution_ref]
    _require(len(results) == 1, 'rejection_binding', 'Evaluation return needs one exact result')
    result = results[0]
    plans = [row for row in store.list('evaluation_plans', execution['project_id'])
             if any(req['request_id'] == result['request_id'] for req in row['requests'])]
    _require(len(plans) == 1, 'rejection_binding', 'Evaluation request needs one frozen plan')
    plan = plans[0]
    requests = [row for row in plan['requests'] if row['request_id'] == result['request_id']]
    _require(len(requests) == 1, 'rejection_binding', 'Evaluation request is absent or duplicated')
    request = requests[0]
    validations = [row for row in store.list('validations', execution['project_id'])
                   if row['plan_id'] == plan['plan_id']]
    _require(len(validations) == 1, 'rejection_binding', 'Rejected plan needs one ValidationRecord')
    validation = validations[0]
    selections = [row for row in store.list('selections', execution['project_id'])
                  if any(item['validation_ref'] == validation['validation_id']
                         for item in row['candidate_validations'])]
    _require(len(selections) == 1, 'rejection_binding', 'Rejected validation needs one SelectionRecord')
    selection = selections[0]
    candidate_rows = [row for row in selection['candidate_validations']
                      if row['validation_ref'] == validation['validation_id']]
    _require(len(candidate_rows) == 1, 'rejection_binding', 'Selection has an ambiguous validation binding')
    candidate_row = candidate_rows[0]
    cases_record = store.get('case_sets', plan['case_set_ref'])
    cases = cases_record['value']
    case_rows = [row for row in cases['cases'] if row['id'] == request['case_ref']]
    _require(len(case_rows) == 1, 'rejection_binding', 'Evaluation request needs one frozen public case')
    case = case_rows[0]
    _require(digest(plan) == validation['plan_hash'] and digest(cases) == plan['case_set_hash'],
             'rejection_binding', 'Plan or case set changed after validation')
    _require(validation['project_id'] == plan['project_id'] == execution['project_id']
             and selection['project_id'] == plan['project_id']
             and validation['candidate_digest'] == plan['candidate_digest']
             and candidate_row['candidate_digest'] == plan['candidate_digest']
             and validation['all_requests_accounted'] is True,
             'rejection_binding', 'Rejected records disagree on project or candidate')
    _require(validation['status'] == candidate_row['status'] == 'rejected'
             and selection['decision'] == 'keep_current'
             and selection['selected_candidate_digest'] is None
             and selection['selected_validation_ref'] is None,
             'rejection_ineligible', 'Only a rejected keep-current decision can create adaptation material')
    _require(selection['base_digest'] == plan['base_digest']
             and selection['expected_generation'] == plan['expected_generation'],
             'rejection_binding', 'Selection no longer describes the frozen plan base')
    active = store.active(plan['project_id'])
    _require(active['snapshot_id'] == selection['base_digest']
             and active['generation'] == selection['expected_generation'],
             'rejection_ineligible', 'A later active version prevents retrospective adaptation projection')
    _require(request['arm'] == 'candidate' and request['snapshot_digest'] == plan['candidate_digest']
             and case['split'] == 'target',
             'rejection_ineligible', 'Only rejected candidate target requests can enter the next learning cycle')
    stored_results = [row for row in validation['results'] if row['request_id'] == request['request_id']]
    _require(stored_results == [result], 'rejection_binding', 'Validation does not contain this exact result')
    target_failures = [row['gate'] for row in validation['gate_results']
                       if row['passed'] is not True and row['gate'] == 'target_gain']
    _require(target_failures == ['target_gain'], 'rejection_ineligible',
             'A regression-only or unrelated rejection cannot train from the target trace')
    _require(result['execution_status'] == 'completed' and result['evaluator_status'] == 'ok'
             and result['outcome'] != 'unknown' and result['score'] is not None
             and result['source'] in ('executable', 'human'),
             'rejection_ineligible', 'Incomplete or unknown evaluation results cannot train the next cycle')
    _require(execution['stage'] == 'execute' and execution['request'] == request and execution['error'] is None,
             'rejection_binding', 'Execution return is not the exact successful planned request')
    from .verification import public_case
    expected_inputs = [request, store.snapshot(request['snapshot_digest']), public_case(case)]
    _require(execution.get('inputs') == expected_inputs, 'rejection_binding',
             'Execution inputs differ from the frozen candidate and public target case')
    returned = execution.get('returned')
    _require(isinstance(returned, dict) and returned.get('execution_status') == 'completed'
             and isinstance(returned.get('events'), list) and 'artifact' in returned,
             'rejection_ineligible', 'Rejected target needs a completed event trace and artifact')
    source_assessment, source_feedback, assessment_gap = None, [], None
    assessment_ref = result.get('assessment_ref')
    if assessment_ref:
        try:
            store.get('assessments', assessment_ref)
        except DomainError as exc:
            if exc.code != 'NOT_FOUND':
                raise
            assessment_gap = 'The original criterion assessment is unavailable; only the aggregate EvaluationResult can be projected.'
        else:
            from .feedback import verify_assessment
            verified = verify_assessment(store, assessment_ref,
                expected_subject=request['request_id'], expected_protocol=plan['protocol_hash'])
            source_assessment = verified['assessment']
            source_feedback = verified['feedbacks']
            _require(source_assessment['project_id'] == plan['project_id']
                     and source_assessment['execution_ref'] == execution_ref
                     and source_assessment['subject_ref'] == request['request_id']
                     and source_assessment['outcome'] == result['outcome']
                     and source_assessment['score'] == result['score'],
                     'rejection_binding', 'Original criterion assessment differs from the selected EvaluationResult')
    return {'execution': execution, 'result': result, 'plan': plan, 'request': request,
            'validation': validation, 'selection': selection, 'case': case,
            'source_assessment': source_assessment, 'source_feedback': source_feedback,
            'assessment_gap': assessment_gap}


def _rejected_target_records(store, execution_ref):
    """Project a verified comparison return into one exact learning Episode and Feedback."""
    context = _rejected_target_context(store, execution_ref)
    execution, returned = context['execution'], context['execution']['returned']
    request, case = context['request'], context['case']
    validation, selection, result = context['validation'], context['selection'], context['result']
    episode_id = 'episode_' + digest(
        ['rejected_target_evaluation', selection['selection_id'], request['request_id']])[:32]
    raw_events = returned['events']
    raw_ids = [row.get('event_id') for row in raw_events if isinstance(row, dict)]
    _require(len(raw_ids) == len(raw_events) and all(isinstance(ref, str) and ref for ref in raw_ids)
             and len(raw_ids) == len(set(raw_ids)), 'rejection_trace',
             'Evaluation events need unique string IDs')
    mapping = {ref: f'evaluation_{index}' for index, ref in enumerate(raw_ids)}
    task = case['task']
    events = [{'event_id': 'instruction', 'kind': 'instruction',
        'text': json.dumps(task, ensure_ascii=False, sort_keys=True, separators=(',', ':')),
        'source_ref': f'{execution_ref}#/inputs/2/task', 'call_id': None,
        'task_revision': task['revision'], 'task_id': task['task_id'], 'source_role': 'user'}]
    optional = ('task_id', 'goal_id', 'source_role', 'parent_episode_id', 'resources')
    for index, raw in enumerate(raw_events):
        _require(isinstance(raw.get('text'), str), 'rejection_trace',
                 'Evaluation event text must be a string')
        item = {'event_id': mapping[raw['event_id']], 'kind': raw.get('kind', 'observation'),
                'text': raw['text'], 'source_ref': f'{execution_ref}#/returned/events/{index}',
                'call_id': raw.get('call_id'), 'task_revision': raw.get('task_revision')}
        for key in optional:
            if key in raw:
                item[key] = copy.deepcopy(raw[key])
        parent = raw.get('parent_event_id')
        if parent is not None:
            _require(parent in mapping, 'rejection_trace',
                     'Evaluation event parent is absent from the trace')
            item['parent_event_id'] = mapping[parent]
        events.append(item)
    state_digest = digest(returned['artifact'])
    state_resource = {'kind': 'artifact', 'ref': 'evaluated-state:' + state_digest,
                      'access': 'check', 'version_ref': state_digest}
    events.append({'event_id': 'result', 'kind': 'result',
        'text': json.dumps({'artifact': returned['artifact'], 'error': None}, ensure_ascii=False,
                           sort_keys=True, separators=(',', ':')),
        'source_ref': f'{execution_ref}#/returned/artifact', 'call_id': None,
        'task_revision': task['revision'], 'task_id': task['task_id'],
        'source_role': 'environment', 'resources': [state_resource]})
    check_id = 'feedback_' + digest(
        ['rejected_target_evaluation', selection['selection_id'], request['request_id']])[:32]
    failed_gates = [row['gate'] for row in validation['gate_results']
                    if row['passed'] is not True and row['gate'] == 'target_gain']
    source_fields = ('check_id', 'criterion_id', 'evaluator_status', 'outcome',
                     'score', 'source', 'evidence_refs', 'reason')
    source_feedback = [{key: row[key] for key in source_fields}
                       for row in context['source_feedback']]
    reason = {'kind': 'rejected_target_candidate', 'selection_id': selection['selection_id'],
              'validation_id': validation['validation_id'], 'validation_status': validation['status'],
              'failed_gates': failed_gates, 'request_id': request['request_id'],
              'score': result['score'], 'outcome': result['outcome'],
              'evaluation_gaps': result['gaps'],
              'source_assessment_ref': None if context['source_assessment'] is None
                  else context['source_assessment']['assessment_id'],
              'source_criterion_feedback': source_feedback,
              'source_feedback_gap': context['assessment_gap'],
              'scope_note': 'This target is now adaptation material; it is not unseen validation evidence.'}
    feedback = {'check_id': check_id, 'run_id': request['request_id'],
        'criterion_id': 'candidate_rejection', 'task_revision': task['revision'],
        'evaluated_state_digest': state_digest, 'evaluator_status': 'ok',
        'outcome': result['outcome'], 'score': result['score'],
        'source': 'external' if result['source'] == 'executable' else result['source'],
        'visibility': 'adaptation',
        'evidence_refs': [execution_ref, result['request_id'], validation['validation_id'],
                          selection['selection_id'], *([context['source_assessment']['assessment_id']]
                          if context['source_assessment'] else []),
                          *[row['check_id'] for row in context['source_feedback']]],
        'reason': json.dumps(reason, ensure_ascii=False, sort_keys=True, separators=(',', ':')),
        'checked_at': validation['evidence_cutoff'], 'received_at': validation['evidence_cutoff'],
        'subject_ref': episode_id, 'project_id': context['plan']['project_id'],
        'binding_status': 'bound', 'request_ref': request['request_id'],
        'attempt_ref': execution_ref, 'execution_ref': execution_ref}
    episode = {'episode_id': episode_id, 'project_id': context['plan']['project_id'],
        'task': {'description': task['description'], 'task_id': task['task_id'],
                 'revision': task['revision']},
        'source': {'kind': 'rejected_target_evaluation', 'reference': execution_ref},
        'events': events, 'source_snapshot_ref': request['snapshot_digest'], 'context_ref': None,
        'feedback_refs': [check_id],
        'gaps': ['Promoted from a rejected target candidate evaluation; no new task execution occurred.',
                 'The target is adaptation material after this handoff and cannot support an unseen-task claim.',
                 'Evaluation did not preserve a ContextManifest; exact Skill consumption remains unknown.'],
        'created_at': validation['evidence_cutoff']}
    return validate('EpisodeRecord', episode), validate('Feedback', feedback), context


def resolve_rejected_target_episode(store, episode):
    """Recheck a promoted Episode against its immutable evaluation source."""
    _require(episode.get('source', {}).get('kind') == 'rejected_target_evaluation',
             'rejection_binding', 'Expected a rejected-target evaluation Episode')
    expected, _, context = _rejected_target_records(store, episode['source']['reference'])
    _require(episode == expected, 'rejection_binding',
             'Promoted Episode differs from the exact evaluation projection')
    returned = context['execution']['returned']
    return {'known': True, 'run_id': context['request']['request_id'],
            'project_id': episode['project_id'], 'task_revision': context['case']['task']['revision'],
            'snapshot_digest': context['request']['snapshot_digest'],
            'artifact_digest': digest(returned['artifact']), 'run': None, 'group': None,
            'execution': context['execution'], 'batch': None, 'binding_error': None,
            'callback_attempt': None, 'source_reference': episode['source']['reference'],
            'evaluation_return': context['execution'], 'learning_authorized': True}


def capture_rejected_target_episodes(store, comparison):
    """Materialize exact rejected target traces for an explicit later learning cycle."""
    if comparison.get('status') != 'completed' or not comparison.get('selection_id'):
        return []
    selection = store.get('selections', comparison['selection_id'])
    if selection['decision'] != 'keep_current':
        return []
    _require(set(comparison.get('validation_ids', [])) == {
        item['validation_ref'] for item in selection['candidate_validations']},
        'rejection_binding', 'Comparison validations differ from the SelectionRecord')
    validation_ids = set(comparison['validation_ids'])
    plan_ids = set(comparison.get('plan_ids', []))
    expected_plan_ids = {store.get('validations', identifier)['plan_id'] for identifier in validation_ids}
    _require(plan_ids == expected_plan_ids, 'rejection_binding',
             'Comparison plan IDs differ from its exact ValidationRecords')
    episode_ids = []
    for validation_id in sorted(validation_ids):
        validation = store.get('validations', validation_id)
        if validation['status'] != 'rejected':
            continue
        if not any(row['gate'] == 'target_gain' and row['passed'] is not True
                   for row in validation['gate_results']):
            continue
        _require(validation['plan_id'] in plan_ids, 'rejection_binding',
                 'Comparison plan IDs omit a rejected validation')
        plan = store.get('evaluation_plans', validation['plan_id'])
        cases = store.get('case_sets', plan['case_set_ref'])['value']['cases']
        splits = {row['id']: row['split'] for row in cases}
        results = {row['request_id']: row for row in validation['results']}
        for request in plan['requests']:
            if request['arm'] != 'candidate' or splits.get(request['case_ref']) != 'target':
                continue
            result = results.get(request['request_id'])
            if (result is None or result.get('execution_status') != 'completed'
                    or result.get('evaluator_status') != 'ok' or result.get('outcome') == 'unknown'
                    or result.get('score') is None or not result.get('execution_ref')):
                continue
            episode, feedback, _ = _rejected_target_records(store, result['execution_ref'])
            store.add_episode(episode, [feedback])
            episode_ids.append(episode['episode_id'])
    return sorted(set(episode_ids))


def _check_protocol(protocol, case_set, candidate_count, max_parallel):
    p, cs = _json(protocol), _json(case_set)
    _require(set(p) <= {"id", "comparison_scope", "repeat_count", "required_gates", "criteria",
                       "selection_rule", "executor", "evaluator", "allowed_sources", "material_visibility", "note", "scoring_policy", "feedback"},
             "unsupported_protocol", "Unsupported protocol fields; no ignored policy switches")
    p["scoring_policy"] = resolve_scoring_policy(p.get("scoring_policy"), default="available_artifact")
    _require(type(max_parallel) is int and max_parallel > 0, "invalid_parallelism", "max_parallel must be positive")
    _require(type(p.get("repeat_count")) is int and p["repeat_count"] > 0,
             "invalid_protocol", "repeat_count must be explicit and positive")
    for key in ("id", "comparison_scope"):
        _require(isinstance(p.get(key), str) and p[key], "invalid_protocol", f"Missing {key}")
    gates = p.get("required_gates", [])
    _require(type(gates) is list and all(type(g) is str for g in gates)
             and len(gates) == len(set(gates)) and BASE_GATES <= set(gates)
             and set(gates) <= BASE_GATES | OPTIONAL_GATES,
             "unsupported_gates", "Declare all six basic gates and only supported optional gates")
    criteria = p.get("criteria", {})
    _require(isinstance(criteria, dict) and set(criteria) <= {
        "target_mean_gain_must_exceed", "maximum_per_case_regression", "maximum_evaluation_calls", "transfer_claim",
        "transfer_mean_gain_must_exceed", "maximum_per_case_transfer_regression", "maximum_score_range",
        "maximum_monetary_cost", "currency"}, "unsupported_protocol", "Unsupported criteria fields")
    thresholds = {"target_gain": "target_mean_gain_must_exceed",
                  "regression_non_decrease": "maximum_per_case_regression",
                  "transfer_gain": "transfer_mean_gain_must_exceed",
                  "transfer_non_decrease": "maximum_per_case_transfer_regression",
                  "stability": "maximum_score_range", "cost": "maximum_monetary_cost"}
    for gate, key in thresholds.items():
        if gate in gates:
            _require(_number(criteria.get(key)) and criteria[key] >= 0,
                     "invalid_threshold", f"{gate} requires explicit nonnegative {key}")
    if "cost" in gates:
        _require(isinstance(criteria.get("currency"), str) and criteria["currency"],
                 "invalid_threshold", "cost requires currency")
    _require(type(criteria.get("transfer_claim")) is bool, "invalid_protocol", "Declare transfer_claim")
    _require(criteria["transfer_claim"] == bool(set(gates) & {"transfer_gain", "transfer_non_decrease"}),
             "scope_mismatch", "Transfer claim must match an explicit transfer gate")
    selection = p.get("selection_rule", {})
    _require(selection.get("order") == ORDER and selection.get("missing_cost") == "last"
             and isinstance(selection.get("id"), str) and bool(selection["id"]),
             "unsupported_selection", "Use the declared quality/cost/digest order and missing_cost=last")
    for key in ("executor", "evaluator"):
        cfg = p.get(key, {})
        _require(isinstance(cfg, dict) and isinstance(cfg.get("id"), str) and bool(cfg["id"])
                 and isinstance(cfg.get("config"), dict), "invalid_protocol", f"Missing {key} identity/config")
    sources = p.get("allowed_sources")
    _require(isinstance(sources, list) and bool(sources) and set(sources) <= {"executable", "human"},
             "unsupported_source", "Published comparisons require declared executable/human evidence, not proxy alone")
    _require(isinstance(cs.get("id"), str) and bool(cs["id"]) and isinstance(cs.get("version"), str),
             "invalid_cases", "Case set needs id and version")
    cases = cs.get("cases", [])
    _require(isinstance(cases, list) and bool(cases), "invalid_cases", "At least target and regression cases required")
    ids = []
    for case in cases:
        _require(isinstance(case, dict) and isinstance(case.get("id"), str) and bool(case["id"])
                 and case.get("split") in {"target", "regression", "transfer"}
                 and "task" in case and "criteria" in case, "invalid_cases", "Case needs id/split/task/criteria")
        ids.append(case["id"])
    _require(len(ids) == len(set(ids)), "duplicate_case", "Case IDs must be unique")
    splits = {c["split"] for c in cases}
    _require({"target", "regression"} <= splits and (not criteria["transfer_claim"] or "transfer" in splits),
             "missing_split", "Missing case split required by the comparison scope")
    planned = candidate_count * len(cases) * 2 * p["repeat_count"] * criterion_count(p)
    limit = criteria.get("maximum_evaluation_calls")
    _require(type(limit) is int and limit >= planned, "call_budget", f"Plan requires {planned} evaluation requests")
    return p, cs


def criterion_count(protocol):
    criteria = protocol.get('feedback', {}).get('criteria', [{'criterion_id':'task_outcome'}])
    _require(isinstance(criteria,list) and bool(criteria),'feedback_protocol','At least one frozen criterion required')
    return len(criteria)


def comparison_call_budget(store, frozen, resolutions=None):
    """Every criterion attempt counts, including interrupted and superseded ones."""
    refs={r['request_id'] for ref in frozen['feedback_plan_refs'].values()
          for r in store.get('feedback_plans',ref)['requests']}
    attempts={ref:[] for ref in refs}
    for attempt in store.list('callback_attempts',frozen['project_id']):
        if attempt['stage']=='evaluate' and attempt['request_ref'] in attempts:
            attempts[attempt['request_ref']].append(attempt)
    count=len(refs)+sum(max(0,len(rows)-1) for rows in attempts.values())
    for ref,decision in (resolutions or {}).items():
        if ref in attempts and decision.get('action')=='confirmed_not_executed' and attempts[ref]:
            last=max(attempts[ref],key=lambda row:(row['started_at'],row['attempt_id']))
            if _optional(store,'callback_returns',last['attempt_id']) is None:count+=1
    return count


def _invoke(store, project, request, stage, callback, args, *, config, comparison_id, resolutions=None):
    from .feedback import call_recorded
    actual=call_recorded(store,project_id=project,batch_id=comparison_id,run_id=None,
        request_ref=request['request_id']+':'+stage,stage=stage,config=config,purpose='validation',
        subject_ref=request['request_id'],callback=callback,args=args,resolutions=resolutions)
    returned,error=actual['raw_output'],actual['error']
    if error is None:
        try:
            _require(isinstance(returned,dict),'invalid_return','Callback must return an object')
            for field in ('request_id','case_ref','snapshot_digest'):
                if field in returned:
                    _require(returned[field]==request[field],'return_binding_mismatch',f'Wrong returned {field}')
        except Exception as exc:error=_error(exc)
    rid=actual['attempt_id'];usage_id=actual['usage_refs'][0]
    record = {"id": rid, "project_id": project, "request": copy.deepcopy(request), "stage": stage,
              "inputs": _json(list(args)), "returned": _raw(returned), "error": error,
              "usage_ref": usage_id, "created_at": actual['returned_at']}
    store.put("evaluation_returns", rid, record)
    return record


def _unknown(request, reason, execution_ref=None, usage_refs=None, evidence_refs=None, execution_status="unknown"):
    return {"request_id": request["request_id"], "case_ref": request["case_ref"],
            "snapshot_digest": request["snapshot_digest"], "outcome": "unknown", "score": None,
            "evaluator_status": "error", "source": "executable",
            "evidence_refs": evidence_refs or [], "execution_ref": execution_ref,
            "usage_refs": usage_refs or [], "gaps": [reason], "execution_status": execution_status}


def _assessment_result(request, execution, assessed, sources, scoring_policy):
    terminal = parse_execution(execution['returned'], execution['error'], scoring_policy)
    aggregate = assessed['aggregate']; feedbacks = assessed['feedbacks']
    actual_sources = {'executable' if source == 'external' else source for source in aggregate['feedback_sources']}
    source = 'llm_proxy' if 'llm_proxy' in actual_sources else ('executable' if 'executable' in actual_sources else 'human')
    valid_source = bool(actual_sources) and actual_sources <= set(sources)
    known = terminal['eligible'] and valid_source and aggregate['score'] is not None
    return {'request_id':request['request_id'],'case_ref':request['case_ref'],'snapshot_digest':request['snapshot_digest'],
        'outcome':aggregate['outcome'] if known else 'unknown','score':aggregate['score'] if known else None,
        'evaluator_status':'ok' if known and not aggregate['missing_criterion_ids'] else 'error',
        'source':source,'evidence_refs':sorted({ref for f in feedbacks for ref in f['evidence_refs']}),
        'execution_ref':execution['id'],'usage_refs':sorted(set([execution['usage_ref'], *assessed['usage_refs']])),
        'gaps':aggregate['unknown_reasons'] + ([] if valid_source else ['Unpermitted or missing feedback source.'])
               + ([] if terminal['eligible'] else ['Execution ineligible: ' + str(terminal['reason'])]),
        'execution_status':terminal['execution_status'],'assessment_ref':assessed['assessment']['assessment_id']}


def freeze_request_feedback(store, plan, case_set, protocol, comparison_id=None):
    from .feedback import freeze_feedback_plan
    cases = {c['id']:c for c in case_set['cases']}
    authority = plan.get('plan_id', plan.get('contrast_plan_id'))
    return {r['request_id']: freeze_feedback_plan(store, {'kind':'evaluation_request','ref':r['request_id'],
        'authority_ref':authority,'execution_ref':None,'project_id':plan['project_id'],'request':r,
        'criteria':cases[r['case_ref']]['criteria'],'batch_id':comparison_id}, protocol)['feedback_plan_id'] for r in plan['requests']}


def _one_request(store, project, request, snapshot, case, execute_fn, evaluate_fn, sources, scoring_policy, *, feedback_plan,
                 execution_config, comparison_id, resolutions=None):
    from .feedback import assess
    from .verification import public_case
    execution = _invoke(store, project, request, "execute", execute_fn, (request, snapshot, public_case(case)),
                        config=execution_config,comparison_id=comparison_id,resolutions=resolutions)
    assessed = assess(store, feedback_plan, execution['returned'], case, evaluate=evaluate_fn,
                      execution_ref=execution['id'], request=request, binding_error=execution['error'],resolutions=resolutions)
    return _assessment_result(request, execution, assessed, sources, scoring_policy)


def proposal_aliases(candidates):
    """Content identities map to all distinct persisted proposal attempts."""
    aliases, seen = {}, {}
    for candidate in candidates:
        proposal, snapshot = candidate["proposal_id"], candidate["candidate_digest"]
        _require(proposal not in seen or seen[proposal] == snapshot, "proposal_binding", "Proposal names different snapshots")
        seen[proposal] = snapshot
        aliases.setdefault(snapshot, set()).add(proposal)
    return {snapshot: sorted(ids) for snapshot, ids in aliases.items()}


def _summaries(plan, results, case_set):
    rows = []
    by_request = {r["request_id"]: r for r in results}
    for case in case_set["cases"]:
        row = {"case_id": case["id"], "split": case["split"],
               "case_role":"quality" if case['id'] in plan.get('quality_case_refs',[c['id'] for c in case_set['cases']]) else "supplemental"}
        for arm in ("base", "candidate"):
            scores = [by_request[r["request_id"]]["score"] for r in plan["requests"]
                      if r["case_ref"] == case["id"] and r["arm"] == arm and r["request_id"] in by_request]
            known = len(scores) == plan["repeat_count"] and all(_number(v) for v in scores)
            row[arm] = sum(scores) / len(scores) if known else None
            row[arm + "_range"] = max(scores) - min(scores) if known else None
        row["gain"] = row["candidate"] - row["base"] if row["base"] is not None and row["candidate"] is not None else None
        rows.append(row)
    return rows


def _quality_rows(rows):
    return [row for row in rows if row.get('case_role','quality')=='quality']


def _cost(store, results, currency=None):
    usages = [store.get("usage", uid) for uid in sorted({uid for r in results for uid in r["usage_refs"]})]
    units = {u["currency"] for u in usages if u["monetary_cost"] is not None}
    known = bool(usages) and all(u["monetary_cost"] is not None for u in usages) and len(units) == 1
    if currency is not None:
        known = known and units == {currency}
    return sum(u["monetary_cost"] for u in usages) if known else None


def _gates(store, plan, results, case_set, protocol, planned_total, round_results=None, verification=None, auxiliary_usage=()):
    expected = {r["request_id"]: r for r in plan["requests"]}
    complete = len(results) == len(expected) and len({r["request_id"] for r in results}) == len(results)
    complete = complete and all(r["request_id"] in expected and all(r[k] == expected[r["request_id"]][k]
                               for k in ("case_ref", "snapshot_digest")) and r["evaluator_status"] == "ok"
                               and r["outcome"] in {"pass", "fail"} and _number(r["score"])
                               and 0 <= r["score"] <= 1 and bool(r["evidence_refs"]) for r in results)
    rows = _summaries(plan, results, case_set)
    criteria = protocol["criteria"]
    active = store.active(plan["project_id"])
    unchanged = (active["snapshot_id"] == plan["base_digest"] and active["generation"] == plan["expected_generation"])
    for sid in (plan["base_digest"], plan["candidate_digest"]):
        unchanged = unchanged and store.snapshot(sid)["project_id"] == plan["project_id"]
    quality_rows=_quality_rows(rows)
    target = [r["gain"] for r in quality_rows if r["split"] == "target"]
    regression = [r["gain"] for r in quality_rows if r["split"] == "regression"]
    transfer = [r["gain"] for r in quality_rows if r["split"] == "transfer"]
    all_known = complete and all(v is not None for v in target + regression + transfer)
    decisions = {"complete_results": complete,
                 "target_gain": sum(target) / len(target) > criteria["target_mean_gain_must_exceed"] if all_known else None,
                 "regression_non_decrease": all(v >= -criteria["maximum_per_case_regression"] for v in regression) if all_known else None,
                 "call_budget": planned_total <= criteria["maximum_evaluation_calls"],
                 "scope_bound": bool(target) and bool(regression) and (not criteria["transfer_claim"] or bool(transfer)),
                 "versions_unchanged": unchanged}
    for name in protocol["required_gates"]:
        if name == "transfer_gain":
            decisions[name] = sum(transfer) / len(transfer) > criteria["transfer_mean_gain_must_exceed"] if all_known and transfer else None
        elif name == "transfer_non_decrease":
            decisions[name] = all(v >= -criteria["maximum_per_case_transfer_regression"] for v in transfer) if all_known and transfer else None
        elif name == "stability":
            decisions[name] = all(r[arm + "_range"] <= criteria["maximum_score_range"] for r in rows for arm in ("base", "candidate")) if all_known else None
        elif name == "cost":
            cost = _cost(store, [*(round_results if round_results is not None else results),
                                {'usage_refs':list(auxiliary_usage)}], criteria["currency"])
            request_ids={row['request_id'] for row in (round_results if round_results is not None else results)}
            usage_ids={u for row in (round_results if round_results is not None else results) for u in row['usage_refs']} | set(auxiliary_usage)
            request_ids.update(store.get('usage',uid).get('request_id') for uid in usage_ids)
            criterion_refs={r['request_id'] for p in store.list('feedback_plans',plan['project_id'])
                            if p['subject']['ref'] in request_ids for r in p['requests']}
            relevant=[a for a in store.list('callback_attempts',plan['project_id'])
                      if a['request_ref'].split(':')[0] in request_ids
                      or a['request_ref'] in criterion_refs
                      or a['attempt_id'] in {store.get('usage',uid).get('attempt_ref') for uid in usage_ids}]
            if any(_optional(store,'callback_returns',a['attempt_id']) is None for a in relevant):cost=None
            decisions[name] = cost <= criteria["maximum_monetary_cost"] if cost is not None else None
    gates = [{"gate": name, "passed": decisions[name], "evidence_refs": [plan["plan_id"]],
              "detail": "Computed from the frozen plan and all recorded request results."} for name in protocol["required_gates"]]
    if plan.get('verification_plan_ref'):
        passed = None if verification is None or verification['status']=='unknown' else verification['status']=='pass'
        gates.append({'gate':'verification_complete','passed':passed,
            'evidence_refs':[verification['verification_id']] if verification else [],
            'detail':'Diagnosis obligations, candidate assets and controlled local comparisons must have actual evidence.'})
    status = "unknown" if not complete or any(g["passed"] is None for g in gates) else (
        "accepted" if all(g["passed"] is True for g in gates) else "rejected")
    return gates, status, rows


def _rank(store, validations, plans, case_set):
    """Never compare numeric costs across different currencies."""
    all_usage = {u for v in validations for u in v["usage_refs"]}
    currencies = {store.get("usage", u)["currency"] for u in all_usage
                  if store.get("usage", u)["monetary_cost"] is not None}
    ranked = []
    for val in validations:
        if val["status"] != "accepted":
            continue
        rows = _summaries(plans[val["plan_id"]], val["results"], case_set)
        gains = [r["gain"] for r in _quality_rows(rows) if r["split"] == "target"]
        cost = _cost(store, [{'usage_refs':val['usage_refs']}]) if len(currencies) == 1 else None
        ranked.append((-sum(gains)/len(gains), cost is None, cost or 0.0,
                       val["candidate_digest"], val["validation_id"]))
    return sorted(ranked)


def compare_candidates(store, project_id, candidates, case_set, protocol, execute_fn, evaluate_fn, *, max_parallel,
                       verification=None, execute_view=None, asset_runner=None):
    """Compare all candidates and select; does not learn or change active state.

    Callers provide request-local/resettable execution environments. Copying inputs
    here is not OS isolation. The cost gate covers all invocations in this comparison
    round; other learning/maintenance costs remain in the project report.
    """
    _require(callable(execute_fn) and callable(evaluate_fn), "missing_callback", "Actual execution and evaluation functions required")
    _require(isinstance(candidates, list) and bool(candidates), "missing_candidates", "Candidates required")
    active = copy.deepcopy(store.active(project_id))
    snapshots = {active["snapshot_id"]: store.snapshot(active["snapshot_id"])}
    candidates = _json(candidates)
    attempts = {}
    for candidate in candidates:
        canonical = store.get("candidates", candidate["proposal_id"])
        _require(canonical == candidate, "candidate_changed", "Use the stored immutable candidate")
        _require(candidate["project_id"] == project_id and candidate["base_digest"] == active["snapshot_id"]
                 and candidate["expected_generation"] == active["generation"], "stale_candidate", "Candidate project/base/generation mismatch")
        attempts[candidate["proposal_id"]] = candidate
        sid = candidate["candidate_digest"]
        snapshot = store.snapshot(sid)
        _require(snapshot["project_id"] == project_id and snapshot["parent"] == active["snapshot_id"],
                 "candidate_parent", "Candidate must belong to this project and base")
        snapshots[sid] = snapshot
    candidates = list(attempts.values())
    aliases = proposal_aliases(candidates)
    protocol,quality_case_set=_check_protocol(protocol,case_set,len(aliases),max_parallel)
    from .verification import freeze_materials, prepare_verification, finish_verification
    from .assets import run_assets
    from .relations import measure_contrasts
    with measure_stage(store,project_id,'validate_overhead',purpose='validation'):
        material_record, case_set = freeze_materials(store,project_id,quality_case_set,verification,candidates)
    protocol, case_set = _check_protocol(protocol, case_set, len(aliases), max_parallel)
    round_id = new_id("comparison")
    protocol_id, cases_id, quality_cases_id = new_id("protocol"), new_id("cases"), new_id('quality_cases')
    store.put("protocols", protocol_id, {"id": protocol_id, "project_id": project_id, "value": protocol})
    store.put("case_sets", cases_id, {"id": cases_id, "project_id": project_id, "value": case_set})
    store.put('case_sets',quality_cases_id,{'id':quality_cases_id,'project_id':project_id,'value':quality_case_set})
    plans, verification_plans, contrast_plans = [], {}, {}
    for snapshot_digest, proposal_ids in aliases.items():
        requests = [{"request_id": new_id("request"), "case_ref": case["id"], "arm": arm,
                     "snapshot_digest": active["snapshot_id"] if arm == "base" else snapshot_digest,
                     "repeat_index": i} for case in case_set["cases"] for arm in ("base", "candidate")
                    for i in range(protocol["repeat_count"])]
        plan = {"plan_id": new_id("plan"), "project_id": project_id, "base_digest": active["snapshot_id"],
                "candidate_digest": snapshot_digest, "expected_generation": active["generation"],
                "protocol_ref": protocol_id, "protocol_hash": digest(protocol), "case_set_ref": cases_id,
                "case_set_hash": digest(case_set), "evaluator_ref": protocol["evaluator"]["id"],
                "evaluator_config_hash": digest(protocol["evaluator"]["config"]),
                "repeat_count": protocol["repeat_count"], "acceptance_scope": protocol["comparison_scope"], "requests": requests,
                "proposal_ids": proposal_ids, "scoring_policy": protocol["scoring_policy"],
                "quality_case_refs":[c['id'] for c in quality_case_set['cases']],
                "purpose": "validation", "update_mode": "none", "recovery_version":1}
        vplan, local_plans = prepare_verification(store,plan,[c for c in candidates if c['proposal_id'] in proposal_ids],
                                                  material_record,case_set,protocol,callable(execute_view))
        plan.update(verification_plan_ref=vplan['verification_plan_id'],verification_plan_hash=digest(vplan))
        verification_plans[plan['plan_id']]=vplan;contrast_plans[plan['plan_id']]=local_plans
        validate("EvaluationPlan", plan)
        store.put("evaluation_plans", plan["plan_id"], plan)
        plans.append(plan)
    total_requests = sum(len(p['requests']) for p in plans) + sum(len(p['requests']) for rows in contrast_plans.values() for p in rows)
    planned_calls = total_requests * criterion_count(protocol)
    _require(planned_calls <= protocol['criteria']['maximum_evaluation_calls'],'call_budget',
             f'Protected cases and controlled contrasts require {planned_calls} criterion calls')
    feedback_plans = {}
    for plan in plans + [p for rows in contrast_plans.values() for p in rows]:
        feedback_plans.update(freeze_request_feedback(store,plan,case_set,protocol,round_id))
    frozen = {"id": round_id, "project_id": project_id, "base_digest": active["snapshot_id"],
              "expected_generation": active["generation"], "candidates": candidates, "protocol_ref": protocol_id,
              "case_set_ref": cases_id, "plan_ids": [p["plan_id"] for p in plans],
              "quality_case_set_ref":quality_cases_id,"quality_case_set_hash":digest(quality_case_set),
              "selection_rule": protocol["selection_rule"], "max_parallel": max_parallel,
              "verification_materials_ref":material_record['materials_id'],"verification_materials_hash":digest(material_record),
              "planned_evaluation_calls":planned_calls,"feedback_plan_refs":feedback_plans,
              "recovery_version":1,"validation_ids":{p['plan_id']:new_id('validation') for p in plans},
              "selection_id":new_id('selection'),
              "proposal_snapshots": [{"proposal_id": c["proposal_id"], "candidate_digest": c["candidate_digest"]} for c in candidates]}
    store.put("evaluation_inputs", round_id, frozen)
    return resume_comparison(store,round_id,execute_fn,evaluate_fn,execute_view=execute_view,asset_runner=asset_runner)


def _optional(store,kind,identifier):
    try:return store.get(kind,identifier)
    except DomainError as exc:
        if exc.code=='NOT_FOUND':return None
        raise


def resume_comparison(store, comparison_id, execute_fn, evaluate_fn, *, execute_view=None,asset_runner=None,resolutions=None):
    """Resume the frozen comparison; a started call with no return needs evidence."""
    from .feedback import recovery_lock
    with recovery_lock(store,'comparison:'+comparison_id):
        frozen=store.get('evaluation_inputs',comparison_id);project=frozen['project_id']
        _require(frozen.get('recovery_version')==1,'recovery_blocked','Legacy comparison has no proven started-call protocol')
        identifier=new_id('comparison_segment')
        start={'record_id':identifier+':start','segment_id':identifier,'project_id':project,'comparison_id':comparison_id,
               'started_at':now_iso(),'finished_at':None,'elapsed_seconds':None,'status':'running',
               'started_attempt_ids':[],'completed_attempt_ids':[]}
        validate('ComparisonSegment',start);store.put('comparison_segments',start['record_id'],start)
        before_attempts={r['attempt_id'] for r in store.list('callback_attempts',project) if r['batch_id']==comparison_id}
        before_returns={r['attempt_id'] for r in store.list('callback_returns',project)}
        started=time.monotonic();status='error'
        try:
            result=_resume_comparison(store,comparison_id,execute_fn,evaluate_fn,execute_view,asset_runner,resolutions)
            status=result['status'];return result
        finally:
            after_attempts={r['attempt_id'] for r in store.list('callback_attempts',project) if r['batch_id']==comparison_id}
            after_returns={r['attempt_id'] for r in store.list('callback_returns',project)}
            end={**start,'record_id':identifier+':end','finished_at':now_iso(),
                 'elapsed_seconds':time.monotonic()-started,'status':status,
                 'started_attempt_ids':sorted(after_attempts-before_attempts),
                 'completed_attempt_ids':sorted((after_returns-before_returns)&after_attempts)}
            validate('ComparisonSegment',end);store.put('comparison_segments',end['record_id'],end)


def _resume_comparison(store,round_id,execute_fn,evaluate_fn,execute_view,asset_runner,resolutions):
    from .verification import finish_verification
    from .assets import run_assets
    from .relations import measure_contrasts
    frozen=store.get('evaluation_inputs',round_id);project_id=frozen['project_id']
    _require(frozen.get('recovery_version')==1,'recovery_blocked','Legacy comparison has no proven started-call protocol')
    candidates=frozen['candidates'];aliases=proposal_aliases(candidates)
    for candidate in candidates:
        _require(store.get('candidates',candidate['proposal_id'])==candidate,'candidate_changed','Frozen candidate changed')
    protocol=store.get('protocols',frozen['protocol_ref'])['value']
    case_set=store.get('case_sets',frozen['case_set_ref'])['value']
    plans=[store.get('evaluation_plans',ref) for ref in frozen['plan_ids']]
    verification_plans={p['plan_id']:store.get('verification_plans',p['verification_plan_ref']) for p in plans}
    contrast_plans={pid:[store.get('contrast_plans',ref) for ref in vp['contrast_plan_refs']] for pid,vp in verification_plans.items()}
    material_record=store.get('verification_materials',frozen['verification_materials_ref'])
    _require(digest(material_record)==frozen['verification_materials_hash'],'verification_materials','Frozen materials changed')
    for plan in plans:
        _require(plan['protocol_hash']==digest(protocol) and plan['case_set_hash']==digest(case_set),
                 'protocol_changed','Frozen cases or protocol changed')
    max_parallel=frozen['max_parallel'];planned_calls=frozen['planned_evaluation_calls']
    _check_protocol(protocol,case_set,len(aliases),max_parallel)
    feedback_plans=frozen['feedback_plan_refs']
    counted_calls=comparison_call_budget(store,frozen,resolutions)
    if counted_calls>protocol['criteria']['maximum_evaluation_calls']:
        return {'comparison_id':round_id,'plan_ids':frozen['plan_ids'],'validation_ids':[],
                'selection_id':None,'usage_ids':[], 'status':'blocked',
                'blocked':[{'code':'call_budget','message':'Recovery would exceed frozen criterion attempt budget.'}]}
    active={'snapshot_id':frozen['base_digest'],'generation':frozen['expected_generation']}
    snapshots={sid:store.snapshot(sid) for p in plans for sid in (p['base_digest'],p['candidate_digest'])}
    by_case = {c["id"]: c for c in case_set["cases"]}
    requests = [r for p in plans for r in p["requests"]]
    owners={r['request_id']:p for p in plans for r in p['requests']}
    outcomes,blocked={},[]
    for request in requests:
        existing=_optional(store,'evaluation_results',request['request_id'])
        if existing is not None:
            verify_result(store,owners[request['request_id']],request,existing,protocol)
            outcomes[request['request_id']]=existing
    pending=[r for r in requests if r['request_id'] not in outcomes]
    try:
        with ThreadPoolExecutor(max_workers=max(1,min(max_parallel, len(pending)))) as pool:
            futures = {pool.submit(_one_request, store, project_id, r, snapshots[r["snapshot_digest"]], by_case[r["case_ref"]],
                                   execute_fn, evaluate_fn, protocol["allowed_sources"], protocol["scoring_policy"],
                                   feedback_plan=feedback_plans[r['request_id']],execution_config=protocol['executor'],
                                   comparison_id=round_id,resolutions=resolutions): r for r in pending}
            for future in as_completed(futures):
                request = futures[future]
                try:
                    outcomes[request["request_id"]] = future.result()
                except Exception as exc:
                    if isinstance(exc,DomainError) and exc.code=='recovery_blocked':
                        blocked.append({'request_id':request['request_id'],**_error(exc)})
                    else:
                        # Preserve an incomplete persistence boundary for resume;
                        # do not overwrite a potentially completed callback with
                        # a fabricated terminal unknown result.
                        blocked.append({'request_id':request['request_id'],**_error(exc)})
    except Exception as exc:
        for request in pending:
            outcomes.setdefault(request["request_id"], _unknown(request, f"Scheduling exception: {_error(exc)}"))
    # Keep usage written before a later persistence/scheduling failure as well.
    request_ids = {r["request_id"] for r in requests}
    used = [u for u in store.list("usage", project_id=project_id) if u.get("request_id") in request_ids]
    for request in requests:
        if request['request_id'] in outcomes:
            row=outcomes[request['request_id']]
            row["usage_refs"] = sorted(u["usage_id"] for u in used if u["request_id"] == request["request_id"])
    validations, verification_records = [], {}
    for row in outcomes.values():
        validate('EvaluationResult',row);store.put('evaluation_results',row['request_id'],row)
    if blocked:
        return {'comparison_id':round_id,'plan_ids':frozen['plan_ids'],'validation_ids':[],
                'selection_id':None,'usage_ids':sorted(u['usage_id'] for u in used),'status':'blocked','blocked':blocked}
    for plan in plans:
        vplan=verification_plans[plan['plan_id']]
        try:
            asset_records=run_assets(store,vplan,material_record['value'],asset_runner,resolutions=resolutions,comparison_id=round_id)
            contrast_records=measure_contrasts(store,contrast_plans[plan['plan_id']],execute_view,evaluate_fn,feedback_plans,
                                              comparison_id=round_id,resolutions=resolutions)
        except Exception as exc:
            return {'comparison_id':round_id,'plan_ids':frozen['plan_ids'],'validation_ids':[],
                    'selection_id':None,'usage_ids':sorted(u['usage_id'] for u in used),'status':'blocked','blocked':[_error(exc)]}
        verification_records[plan['plan_id']]=finish_verification(store,vplan,plan,
            [outcomes[r['request_id']] for r in plan['requests']],asset_records,contrast_records)
    auxiliary_usage=sorted({u for v in verification_records.values() for u in v['usage_refs']})
    for plan in plans:
        results = [outcomes.get(r["request_id"], _unknown(r, "Missing scheduled result")) for r in plan["requests"]]
        for result in results:
            validate("EvaluationResult", result)
            store.put("evaluation_results", result["request_id"], result)
        verification_record=verification_records[plan['plan_id']]
        with measure_stage(store,project_id,'validate_overhead',purpose='validation',subject_ref=plan['plan_id']):
            gates, status, rows = _gates(store, plan, results, case_set, protocol, comparison_call_budget(store,frozen), list(outcomes.values()),verification_record,auxiliary_usage)
        existing=_optional(store,'validations',frozen['validation_ids'][plan['plan_id']])
        if existing is not None:
            verify_validation(store,existing);validations.append(existing);continue
        validation = {"validation_id": frozen['validation_ids'][plan['plan_id']], "project_id": project_id, "plan_id": plan["plan_id"],
                      "plan_hash": digest(plan), "protocol_hash": plan["protocol_hash"], "base_digest": plan["base_digest"],
                      "candidate_digest": plan["candidate_digest"], "expected_active_generation": plan["expected_generation"],
                      "evaluator_ref": plan["evaluator_ref"], "evaluator_config_hash": plan["evaluator_config_hash"],
                      "case_set_hash": plan["case_set_hash"], "results": results, "all_requests_accounted": True,
                      "status": status, "gate_results": gates,
                      "usage_refs": sorted({u for r in results for u in r["usage_refs"]} | set(verification_record['usage_refs'])),
                      "verification_record_ref":verification_record['verification_id'],
                      "reasons": [g["gate"] for g in gates if g["passed"] is not True], "evidence_cutoff": now_iso()}
        validate("ValidationRecord", validation)
        store.put("validations", validation["validation_id"], validation)
        validations.append(validation)
    ranked = _rank(store, validations, {p["plan_id"]:p for p in plans}, case_set)
    selection = {"selection_id": frozen['selection_id'], "project_id": project_id, "base_digest": active["snapshot_id"],
                 "expected_generation": active["generation"], "selection_rule_ref": round_id,
                 "selection_rule_hash": digest(protocol["selection_rule"]),
                 "candidate_validations": [{"candidate_digest": v["candidate_digest"], "validation_ref": v["validation_id"], "status": v["status"],
                                            "proposal_ids": aliases[v["candidate_digest"]]} for v in validations],
                 "decision": "selected" if ranked else "keep_current",
                 "selected_candidate_digest": ranked[0][3] if ranked else None,
                 "selected_validation_ref": ranked[0][4] if ranked else None,
                 "reasons": ["Applied frozen quality/cost/digest order; unknown cost ranked last." if ranked else "No accepted candidate."]}
    validate("SelectionRecord", selection)
    store.put("selections", selection["selection_id"], selection)
    return {"comparison_id": round_id, "plan_ids": [p["plan_id"] for p in plans],
            "validation_ids": [v["validation_id"] for v in validations], "selection_id": selection["selection_id"],
            "usage_ids": sorted({u for v in validations for u in v["usage_refs"]}),"status":"completed","blocked":[]}


def verify_validation(store, validation):
    """Recheck stored evidence/plan binding, not just the status or JSON shape."""
    validate("ValidationRecord", validation)
    plan = store.get("evaluation_plans", validation["plan_id"])
    validate("EvaluationPlan", plan)
    _require(digest(plan) == validation["plan_hash"], "plan_changed", "Plan hash mismatch")
    protocol_record = store.get("protocols", plan["protocol_ref"])
    cases_record = store.get("case_sets", plan["case_set_ref"])
    _require(protocol_record["project_id"] == plan["project_id"] == cases_record["project_id"],
             "project_mismatch", "Protocol/cases belong to another project")
    protocol, cases = protocol_record["value"], cases_record["value"]
    _require(digest(protocol) == plan["protocol_hash"] and digest(cases) == plan["case_set_hash"],
             "protocol_changed", "Protocol or cases changed")
    for key in ("project_id", "base_digest", "candidate_digest", "protocol_hash", "case_set_hash", "evaluator_ref", "evaluator_config_hash"):
        _require(validation[key] == plan[key], "validation_binding", f"Mismatched {key}")
    _require(validation["expected_active_generation"] == plan["expected_generation"], "validation_binding", "Wrong generation")
    _require(plan["evaluator_ref"] == protocol["evaluator"]["id"] and plan["evaluator_config_hash"] == digest(protocol["evaluator"]["config"]),
             "validation_binding", "Evaluator identity/config changed")
    scoring_policy = resolve_scoring_policy(protocol.get("scoring_policy"), default="available_artifact")
    _require(plan.get("scoring_policy", scoring_policy) == scoring_policy, "scoring_policy_binding", "Plan scoring policy differs from its frozen protocol")
    expected = {r["request_id"]: r for r in plan["requests"]}
    expected_pairs = {(c["id"], arm, i) for c in cases["cases"] for arm in ("base", "candidate")
                      for i in range(protocol["repeat_count"])}
    actual_pairs = {(r["case_ref"], r["arm"], r["repeat_index"]) for r in plan["requests"]}
    _require(actual_pairs == expected_pairs and len(plan["requests"]) == len(expected_pairs)
             and plan["repeat_count"] == protocol["repeat_count"]
             and all(r["snapshot_digest"] == plan["base_digest" if r["arm"] == "base" else "candidate_digest"] for r in plan["requests"]),
             "plan_coverage", "Frozen plan does not cover every case/arm/repeat exactly once")
    results = validation["results"]
    _require(len(expected) == len(plan["requests"]) and len(results) == len(expected)
             and {r["request_id"] for r in results} == set(expected), "incomplete_results", "Requests missing or duplicated")
    for result in results:
        req = expected[result["request_id"]]
        verify_result(store,plan,req,result,protocol)
    # New publication requires the complete obligation/asset consumer. Old
    # archived comparisons remain readable but cannot bypass a new validation.
    _require(bool(plan.get('verification_plan_ref')) and bool(validation.get('verification_record_ref')),
             'verification_missing','Publication requires explicit obligation and asset verification')
    from .verification import verify_verification
    verification = verify_verification(store,plan,store.get('verification_records',validation['verification_record_ref']))
    _require(set(validation['usage_refs']) == {u for r in results for u in r['usage_refs']} | set(verification['usage_refs']),
             'usage_binding','Validation must include all case, script and combination usage')
    return plan, protocol, cases


def verify_result(store, plan, req, result, protocol):
    """The same evidence validation serves ordinary and controlled-view runs."""
    _require(result == store.get('evaluation_results',result['request_id']),'result_changed','Stored result changed')
    _require(all(result[k]==req[k] for k in ('request_id','case_ref','snapshot_digest')),
             'result_binding','Result belongs to another case/version')
    execution=store.get('evaluation_returns',result['execution_ref']) if result['execution_ref'] else None
    scoring=resolve_scoring_policy(protocol.get('scoring_policy'),default='available_artifact')
    terminal=parse_execution(execution['returned'],execution['error'],scoring) if execution else {'execution_status':'unknown','eligible':False}
    _require(result.get('execution_status',terminal['execution_status'])==terminal['execution_status'],
             'execution_status_binding','Recorded terminal state differs from execution evidence')
    if execution:
        _require(execution['project_id']==plan['project_id'] and execution['request']==req and execution['stage']=='execute',
                 'execution_binding','Execution does not belong to this exact planned slot')
        expected_input=(store.snapshot(req['snapshot_digest']) if 'plan_id' in plan
                        else store.get('execution_views',req['snapshot_digest']))
        cases=store.get('case_sets',plan['case_set_ref'])['value']['cases']
        case=next(c for c in cases if c['id']==req['case_ref'])
        from .verification import public_case
        _require(execution.get('inputs')==[req,expected_input,public_case(case)],
                 'execution_input_binding','Callback inputs differ from the exact frozen view and public case')
    if result.get('assessment_ref'):
        from .feedback import verify_assessment, _assessment_usage
        subject={'kind':'evaluation_request','ref':req['request_id'],
                 'authority_ref':plan.get('plan_id',plan.get('contrast_plan_id')),'execution_ref':None}
        verified=verify_assessment(store,result['assessment_ref'],expected_subject=subject,expected_protocol=digest(protocol))
        _require(verified['assessment'].get('execution_ref')==result['execution_ref'],
                 'assessment_binding','Assessment describes a different execution')
        verified['usage_refs']=_assessment_usage(store,verified['feedbacks'])
        actual=_assessment_result(req,execution,verified,protocol['allowed_sources'],scoring)
        actual['usage_refs']=sorted(u['usage_id'] for u in store.list('usage',plan['project_id']) if u.get('request_id')==req['request_id'])
        _require(result==actual,'assessment_result','Recorded result differs from original criterion aggregation')
        return
    if result['outcome']=='unknown':return
    _require(execution is not None and terminal['eligible'] and execution['error'] is None,
             'scoring_policy_binding','Execution is ineligible under frozen policy')
    _require(len(result['evidence_refs'])==1,'evidence_binding','Expected original evaluator return')
    evidence=store.get('evaluation_returns',result['evidence_refs'][0]);out=evidence['returned']
    _require(evidence['project_id']==plan['project_id'] and evidence['request']==req
             and evidence['stage']=='evaluate' and evidence['error'] is None and bool(out.get('evidence'))
             and out.get('source') in protocol['allowed_sources']
             and all(result[k]==out.get(k) for k in ('score','outcome','source')),
             'evidence_binding','Evaluator return does not support this result')
    _require(set(result['usage_refs'])=={execution['usage_ref'],evidence['usage_ref']},'usage_binding','Invocation usage incomplete')
