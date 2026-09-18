"""Dependency-preserving, directional local comparisons of actual skill views."""
from __future__ import annotations

from copy import deepcopy

from .schemas import DomainError, digest, new_id, validate


def execution_view(snapshot, seeds, background):
    skills = snapshot['skills']
    selected, visiting = set(), set()
    def visit(sid):
        if sid in selected: return
        if sid not in skills or sid in visiting:
            raise DomainError('contrast_dependency', 'Missing or cyclic dependency')
        visiting.add(sid)
        for dependency in skills[sid]['content']['depends_on']: visit(dependency)
        visiting.remove(sid); selected.add(sid)
    for sid in sorted(set(seeds) | set(background)): visit(sid)
    for sid in selected:
        if set(skills[sid]['content']['declared_conflicts']) & selected:
            raise DomainError('contrast_conflict', 'Selected view contains declared conflicts')
    refs = lambda ids: [{'skill_id': sid, 'revision': skills[sid]['revision']} for sid in sorted(ids)]
    body = {'project_id': snapshot['project_id'], 'source_snapshot_digest': snapshot['snapshot_id'],
            'selected_skill_refs': refs(selected), 'skills': {sid: deepcopy(skills[sid]) for sid in sorted(selected)},
            'assets': {path: snapshot['assets'][path] for sid in sorted(selected) for path in skills[sid]['asset_refs']},
            'dependency_closure': sorted(selected - set(seeds) - set(background)),
            'background_skill_refs': refs(background)}
    return validate('ExecutionView', {'view_id': digest(body), **body})


def candidate_pairs(store, snapshot, candidates, materials, relation_refs=None):
    aliases = {key: value for c in candidates for key, value in c.get('skill_aliases', {}).items()}
    resolve = lambda ref: aliases.get(ref, ref)
    pairs = {(resolve(p['from']), resolve(p['to'])): p['required'] for p in materials['relation_pairs']}
    changed = {sid for c in candidates for sid in c.get('changed_skill_refs', []) if sid in snapshot['skills']}
    for sid in sorted(changed):
        for dependency in snapshot['skills'][sid]['content']['depends_on']:
            pairs.setdefault((sid, dependency), False)
    source_relations=(store.list('relations',snapshot['project_id']) if relation_refs is None
                      else [store.get('relations',ref) for ref in relation_refs])
    base=store.snapshot(snapshot['parent']) if snapshot['parent'] else snapshot
    for relation in source_relations:
        if relation.get('kind') != 'co_used': continue
        left, right = relation.get('from'), relation.get('to')
        if left not in snapshot['skills'] or right not in snapshot['skills'] or not ({left, right} & changed): continue
        try: source = store.snapshot(relation['snapshot_digest'])
        except (DomainError, KeyError): continue
        if any(sid not in source['skills'] or sid not in base['skills'] or source['skills'][sid]['revision'] != base['skills'][sid]['revision']
               for sid in (left, right)): continue
        for a, b in ((left, right), (right, left)):
            if a in changed: pairs.setdefault((a, b), False)
    required = sorted(pair for pair, needed in pairs.items() if needed)
    others = sorted(pair for pair, needed in pairs.items() if not needed)
    maximum = materials['relation_policy']['max_pairs']
    # Explicit obligations survive the budget; they become missing evidence if
    # the total execution budget cannot cover them, never silently disappear.
    return [(a, b, pairs[(a, b)]) for a, b in required + others[:max(0, maximum - len(required))]]


def prepare_contrasts(store, verification_id, snapshot, candidates, materials, case_set, case_ref,
                      protocol, protocol_ref, has_view_executor, relation_refs=None):
    plans = []
    selected_cases = materials['relation_case_ids'] or [c['id'] for c in case_set['cases']]
    cases = {c['id']: c for c in case_set['cases']}
    background = materials['relation_policy']['background_skill_ids']
    for left, right, required in candidate_pairs(store, snapshot, candidates, materials,relation_refs):
        state, gaps, views = 'ready', [], {}
        try:
            if left == right or left not in snapshot['skills'] or right not in snapshot['skills']:
                raise DomainError('contrast_pair', 'Distinct existing skills are required')
            if not selected_cases or any(cid not in cases for cid in selected_cases):
                raise DomainError('contrast_cases', 'Comparison cases are missing')
            views['without'] = execution_view(snapshot, [right], background)
            views['with'] = execution_view(snapshot, [left, right], background)
            # Compare provided content, not view labels/dependency bookkeeping.
            if views['without']['skills'] == views['with']['skills']:
                state = 'not_identifiable'; gaps.append('Dependency closure provides identical skill content in both arms.')
            elif not has_view_executor:
                state = 'missing_capability'; gaps.append('No execute_view function for controlled skill inputs.')
        except DomainError as exc:
            state = 'invalid'; gaps.append(exc.code + ': ' + exc.message)
        for view in views.values(): store.put('execution_views', view['view_id'], view)
        requests = []
        if state in ('ready','missing_capability'):
            requests = [{'request_id': new_id('contrast_request'), 'case_ref': cid, 'arm': arm,
                'snapshot_digest': views[arm]['view_id'], 'repeat_index': repeat}
                for cid in selected_cases for arm in ('without', 'with') for repeat in range(protocol['repeat_count'])]
        dependencies = {sid for view in views.values() for sid in view['dependency_closure']} - {left, right}
        family = materials['relation_policy']['task_family']
        task_ids = sorted({str(cases[cid]['task'].get('task_id', cid)) if isinstance(cases[cid]['task'], dict) else cid
                           for cid in selected_cases if cid in cases})
        plan = {'contrast_plan_id': new_id('contrast'), 'project_id': snapshot['project_id'],
                'verification_plan_ref': verification_id, 'source_snapshot_digest': snapshot['snapshot_id'],
                'from': left, 'to': right, 'required': required, 'case_set_ref': case_ref,
                'case_set_hash': digest(case_set), 'protocol_ref': protocol_ref, 'protocol_hash': digest(protocol),
                'repeat_count': protocol['repeat_count'], 'arms': {arm: views[arm]['view_id'] if arm in views else None for arm in ('without','with')},
                'requests': requests, 'state': state, 'gaps': gaps,
                'skill_revisions': {sid: snapshot['skills'][sid]['revision'] for sid in (left,right) if sid in snapshot['skills']},
                'dependency_revisions': {sid: snapshot['skills'][sid]['revision'] for sid in sorted(dependencies)},
                'background_skill_refs': [{'skill_id': sid, 'revision': snapshot['skills'][sid]['revision']} for sid in sorted(background) if sid in snapshot['skills']],
                'applicable_context': {'task_family': family, 'task_ids': [] if family else task_ids, 'case_set_hash': digest(case_set)}}
        validate('ContrastPlan', plan); store.put('contrast_plans', plan['contrast_plan_id'], plan); plans.append(plan)
    return plans


def summarize_contrast(plan, results):
    if plan['state'] != 'ready':
        return (plan['state'] if plan['state'] in ('invalid','not_identifiable') else 'unknown'), None
    requests = plan['requests']; by_id = {r['request_id']: r for r in results}
    if (not requests or len(results) != len(requests) or len(by_id) != len(requests)
            or set(by_id) != {r['request_id'] for r in requests}
            or any(by_id[r['request_id']]['outcome'] == 'unknown' or by_id[r['request_id']]['evaluator_status'] != 'ok'
                   or by_id[r['request_id']]['score'] is None for r in requests)):
        return 'unknown', None
    gains = []
    for case in sorted({r['case_ref'] for r in requests}):
        means = {arm: sum(by_id[r['request_id']]['score'] for r in requests if r['case_ref']==case and r['arm']==arm)
                      / plan['repeat_count'] for arm in ('without','with')}
        gains.append(means['with'] - means['without'])
    return 'measured', sum(gains) / len(gains)


def measure_contrasts(store, plans, execute_view, evaluate, feedback_plans, *, comparison_id, resolutions=None):
    from .evaluation import _one_request, _optional, _unknown, verify_result
    records = []
    for plan in plans:
        identifier='contrast_result_'+digest(plan)
        existing=_optional(store,'contrast_results',identifier)
        if existing is not None:
            verify_contrast(store,plan,existing);records.append(existing)
            _save_relation(store,plan,existing)
            continue
        cases = {c['id']:c for c in store.get('case_sets', plan['case_set_ref'])['value']['cases']}
        protocol = store.get('protocols', plan['protocol_ref'])['value']
        results = []
        for request in plan['requests']:
            row=_optional(store,'evaluation_results',request['request_id'])
            if row is not None:
                verify_result(store,plan,request,row,protocol)
            elif plan['state']=='missing_capability':
                row=_unknown(request,'Frozen plan lacks a controlled-view executor; this slot was not executed.')
            else:
                row = _one_request(store, plan['project_id'], request,
                    store.get('execution_views', request['snapshot_digest']), cases[request['case_ref']],
                    execute_view, evaluate, protocol['allowed_sources'], protocol['scoring_policy'],
                    feedback_plan=feedback_plans[request['request_id']],execution_config=protocol['executor'],
                    comparison_id=comparison_id,resolutions=resolutions)
                row['usage_refs']=sorted(u['usage_id'] for u in store.list('usage',plan['project_id']) if u.get('request_id')==request['request_id'])
            validate('EvaluationResult', row); store.put('evaluation_results', row['request_id'], row); results.append(row)
        status, value = summarize_contrast(plan, results)
        relation_ref = None
        if status == 'measured':
            relation_ref = 'relation_'+digest(plan)
        result = {'contrast_result_id': identifier, 'project_id': plan['project_id'],
                  'plan_ref': plan['contrast_plan_id'], 'plan_hash': digest(plan), 'status': status,
                  'result_refs': [r['request_id'] for r in results], 'value': value, 'relation_ref': relation_ref,
                  'usage_refs': sorted({uid for r in results for uid in r['usage_refs']}), 'gaps': plan['gaps'][:]}
        validate('ContrastResult', result); store.put('contrast_results', identifier, result)
        _save_relation(store,plan,result)
        records.append(result)
    return records


def _save_relation(store,plan,result):
    if result['relation_ref']:
        relation={key:deepcopy(plan[key]) for key in ('project_id','from','to','skill_revisions',
                    'dependency_revisions','background_skill_refs','applicable_context','source_snapshot_digest')}
        relation.update(relation_id=result['relation_ref'],kind='measured_effect',metric='conditional_marginal_gain',
            value=result['value'],contrast_plan_ref=plan['contrast_plan_id'],supporting_refs=[result['contrast_result_id']],
            known_task_count=len({r['case_ref'] for r in plan['requests']}),repeats=plan['repeat_count'],evidence_level='executed_local_contrast')
        validate('MeasuredEffect',relation);store.put('relations',relation['relation_id'],relation)


def verify_contrast(store, plan, result):
    from .evaluation import verify_result
    validate('ContrastPlan', plan); validate('ContrastResult', result)
    if (result['plan_ref'] != plan['contrast_plan_id'] or result['plan_hash'] != digest(plan)
            or result['project_id'] != plan['project_id']):
        raise DomainError('contrast_binding', 'Contrast result differs from frozen plan')
    snapshot = store.snapshot(plan['source_snapshot_digest'])
    background = [r['skill_id'] for r in plan['background_skill_refs']]
    if plan['state'] in ('ready', 'not_identifiable', 'missing_capability'):
        for arm, seeds in [('without',[plan['to']]),('with',[plan['from'],plan['to']])]:
            actual = store.get('execution_views', plan['arms'][arm])
            if actual != execution_view(snapshot, seeds, background):
                raise DomainError('contrast_view', 'Provided view does not preserve exact dependency closure')
    protocol = store.get('protocols', plan['protocol_ref'])['value']
    cases = store.get('case_sets', plan['case_set_ref'])['value']
    if digest(protocol) != plan['protocol_hash'] or digest(cases) != plan['case_set_hash']:
        raise DomainError('contrast_binding', 'Contrast protocol/cases changed')
    if plan['state'] in ('ready','missing_capability'):
        if (plan['repeat_count']!=protocol['repeat_count'] or not plan['requests']
                or len({r['request_id'] for r in plan['requests']})!=len(plan['requests'])):
            raise DomainError('contrast_coverage','Invalid or repeated controlled requests')
        case_ids={r['case_ref'] for r in plan['requests']}
        coordinates={(cid,arm,i) for cid in case_ids for arm in ('without','with') for i in range(plan['repeat_count'])}
        if (len(plan['requests'])!=len(coordinates)
                or {(r['case_ref'],r['arm'],r['repeat_index']) for r in plan['requests']}!=coordinates
                or any(r['snapshot_digest']!=plan['arms'][r['arm']] for r in plan['requests'])):
            raise DomainError('contrast_coverage','Controlled requests do not cover each case/view/repeat')
    results = [store.get('evaluation_results', ref) for ref in result['result_refs']]
    requests = {r['request_id']: r for r in plan['requests']}
    if len(results)!=len(requests) or {r['request_id'] for r in results}!=set(requests):
        raise DomainError('contrast_coverage','Every planned controlled slot needs an observed or explicit unknown result')
    for row in results:
        if row['request_id'] not in requests:
            raise DomainError('contrast_coverage', 'Unexpected contrast result')
        verify_result(store, plan, requests[row['request_id']], row, protocol)
    if (result['status'], result['value']) != summarize_contrast(plan, results):
        raise DomainError('contrast_result', 'Contrast conclusion differs from observed results')
    if set(result['usage_refs']) != {u for r in results for u in r['usage_refs']}:
        raise DomainError('contrast_usage', 'Contrast usage is incomplete')
    return result
