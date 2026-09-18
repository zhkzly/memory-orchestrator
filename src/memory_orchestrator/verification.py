"""Bind diagnosis obligations to caller-owned materials and actual check records."""
from __future__ import annotations

from copy import deepcopy

from .schemas import DomainError, digest, json_bytes, new_id, validate
from .telemetry import measure_stage


def public_task(task):
    """Match the known TaskSpec visibility fields; do not classify prose by guess."""
    if isinstance(task,dict):
        return {key:deepcopy(value) for key,value in task.items() if key not in ('criteria','private')}
    return deepcopy(task)


def public_case(case):
    return {'id':case['id'],'split':case['split'],'task':public_task(case['task'])}


def normalize_materials(case_set, verification=None):
    value = deepcopy(verification or {})
    allowed = {'id','version','checks','cases','asset_tests','bindings','relation_case_ids','relation_pairs',
               'relation_policy','asset_runner'}
    if set(value) - allowed:
        raise DomainError('verification_materials', 'Unsupported verification material fields')
    value.setdefault('id', case_set['id'] + ':verification'); value.setdefault('version', case_set['version'])
    for key in ('checks','cases','asset_tests','relation_case_ids','relation_pairs'): value.setdefault(key, [])
    value.setdefault('bindings', {})
    value.setdefault('relation_policy', {'max_pairs':8, 'background_skill_ids':[], 'task_family':None})
    value.setdefault('asset_runner', {'id':'python-process/v1','config':{},'isolation':'process'})
    cases = {c['id']: c for c in case_set['cases']}
    for case in value['cases']:
        if case['id'] in cases:
            raise DomainError('duplicate_case', 'Additional check cases cannot replace protected cases')
        cases[case['id']] = case
    builtins = [{'check_ref':'case:' + c['id'], 'purpose':c['split'],
                 'description':c.get('check_description') or 'Check the public task: ' + json_bytes(public_task(c['task'])).decode('utf-8'),
                 'evidence_kind':'task','case_ids':[c['id']], 'asset_test_ids':[]} for c in cases.values()]
    explicit = value['checks']
    names = [c['check_ref'] for c in explicit + builtins]
    if len(names) != len(set(names)):
        raise DomainError('duplicate_check', 'Check references must be unique, including case:<id>')
    value['checks'] = builtins + explicit
    validate('VerificationMaterials', {'materials_id':'shape-check', 'project_id':'shape-check','value':value})
    test_ids = [t['test_id'] for t in value['asset_tests']]
    if len(test_ids) != len(set(test_ids)):
        raise DomainError('duplicate_asset_test', 'Functional test IDs must be unique')
    from .assets import safe_path
    for test in value['asset_tests']:
        for path in [test['entrypoint'], *test['input_files'], *test['expected_files']]: safe_path(path)
        if not test['entrypoint'].startswith('scripts/'):
            raise DomainError('asset_fixture', 'Fixture entrypoint must name an owned script')
    return value


def verification_catalog(case_set, verification=None):
    """Only descriptions and references are visible to the learner, never gold."""
    return deepcopy(normalize_materials(case_set, verification)['checks'])


def requirements_for(store, candidates, materials):
    checks = {c['check_ref']: c for c in materials['checks']}
    rows, seen = [], set()
    for candidate in candidates:
        sources = [(candidate['proposal_id'], candidate, candidate.get('check_plan', []))]
        ref = candidate.get('diagnosis_ref')
        if ref is not None:
            diagnosis = store.get('diagnoses', ref)
            if (digest(diagnosis) != candidate.get('diagnosis_hash') or diagnosis['project_id'] != candidate['project_id']
                    or diagnosis['base_digest'] != candidate['base_digest']):
                raise DomainError('diagnosis_binding', 'Candidate diagnosis differs from its exact source')
            sources.append((ref, diagnosis, diagnosis['draft']['check_plan']))
        if candidate.get('patch') is not None and candidate.get('check_plan') != candidate['patch']['check_plan']:
            raise DomainError('check_plan_binding', 'Candidate lost its patch check obligations')
        for source_ref, source, obligations in sources:
            for index, item in enumerate(obligations):
                identity = 'requirement_' + digest([source_ref, digest(source), index, item])
                if identity in seen: continue
                seen.add(identity)
                selected = materials['bindings'].get(identity, item.get('check_ref'))
                material, gaps = checks.get(selected), []
                if material is None:
                    gaps.append('No explicit trusted check material reference.')
                elif material['purpose'] != item['purpose']:
                    gaps.append('Check purpose differs from the required obligation.')
                elif not material['case_ids'] and not material['asset_test_ids'] and material['evidence_kind'] != 'combination':
                    gaps.append('Trusted check has no executable material.')
                rows.append({'requirement_id':identity,'source_ref':source_ref,'source_hash':digest(source),
                    'check':deepcopy(item),'check_ref':selected,
                    'case_ids':material['case_ids'][:] if material else [],
                    'asset_test_ids':material['asset_test_ids'][:] if material else [],
                    'status':'missing' if gaps else 'bound','gaps':gaps})
    return sorted(rows,key=lambda row:row['requirement_id'])


def freeze_materials(store, project_id, case_set, verification, candidates):
    materials = normalize_materials(case_set, verification)
    obligations = requirements_for(store, candidates, materials)
    required = {cid for item in obligations for cid in item['case_ids']}
    selected = deepcopy(case_set)
    selected['cases'].extend(deepcopy(c) for c in materials['cases'] if c['id'] in required or c['id'] in materials['relation_case_ids'])
    record = {'materials_id':new_id('materials'),'project_id':project_id,'value':materials}
    validate('VerificationMaterials', record); store.put('verification_materials',record['materials_id'],record)
    return record, selected


def asset_jobs(snapshot, candidates, materials):
    aliases = {k:v for candidate in candidates for k,v in candidate.get('skill_aliases', {}).items()}
    jobs = []
    for path in sorted(snapshot['assets']):
        if len(path.split('/')) < 3 or path.split('/')[1] != 'scripts': continue
        jobs.append({'job_id':new_id('asset_job'),'kind':'compile','asset_path':path,'test_id':None})
        tests = [t for t in materials['asset_tests'] if aliases.get(t['owner_skill_ref'],t['owner_skill_ref']) + '/' + t['entrypoint'] == path]
        for test in tests or [None]:
            jobs.append({'job_id':new_id('asset_job'),'kind':'function','asset_path':path,'test_id':test['test_id'] if test else None})
    return jobs


def prepare_verification(store, evaluation_plan, candidates, material_record, case_set, protocol, has_view_executor):
    from .relations import prepare_contrasts
    identifier = new_id('verification_plan')
    with measure_stage(store, evaluation_plan['project_id'], 'validate_overhead', purpose='validation', subject_ref=identifier):
        materials = material_record['value']
        snapshot = store.snapshot(evaluation_plan['candidate_digest'])
        relation_sources=sorted(r['relation_id'] for r in store.list('relations',evaluation_plan['project_id']) if r.get('kind')=='co_used')
        contrast_plans = prepare_contrasts(store, identifier, snapshot, candidates, materials, case_set,
                        evaluation_plan['case_set_ref'], protocol, evaluation_plan['protocol_ref'], has_view_executor,relation_sources)
        plan = {'verification_plan_id':identifier,'project_id':evaluation_plan['project_id'],
            'evaluation_plan_id':evaluation_plan['plan_id'],'base_digest':evaluation_plan['base_digest'],
            'candidate_digest':evaluation_plan['candidate_digest'],'expected_generation':evaluation_plan['expected_generation'],
            'proposal_hashes':{c['proposal_id']:digest(c) for c in candidates},
            'materials_ref':material_record['materials_id'],'materials_hash':digest(material_record),
            'requirements':requirements_for(store,candidates,materials),
            'asset_jobs':asset_jobs(snapshot,candidates,materials),
            'contrast_plan_refs':[p['contrast_plan_id'] for p in contrast_plans],
            'relation_source_refs':relation_sources,'recovery_version':1}
        validate('VerificationPlan',plan);store.put('verification_plans',identifier,plan)
    return plan, contrast_plans


def _coverage(store, plan, evaluation_plan, results, assets, contrasts, materials):
    checks = {c['check_ref']:c for c in materials['checks']}
    by_request = {r['request_id']:r for r in results}
    rows, gaps = [], []
    for requirement in plan['requirements']:
        states, refs, reasons = [], [], requirement['gaps'][:]
        check = checks.get(requirement['check_ref'])
        if requirement['status'] != 'bound': states.append('unknown')
        for case in requirement['case_ids']:
            planned = [r for r in evaluation_plan['requests'] if r['case_ref']==case and r['arm']=='candidate']
            observed = [by_request.get(r['request_id']) for r in planned]
            if len(planned) != evaluation_plan['repeat_count'] or any(r is None or r['evaluator_status']!='ok' or r['outcome']=='unknown' for r in observed):
                states.append('unknown'); reasons.append('Missing complete independent case evidence: ' + case)
            else:
                states.append('pass' if all(r['outcome']=='pass' for r in observed) else 'fail')
                refs.extend(r['request_id'] for r in observed)
        for test in requirement['asset_test_ids']:
            observed = [r for r in assets if r['kind']=='function' and r['test_id']==test]
            if not observed: states.append('unknown'); reasons.append('Required functional test did not execute: ' + test)
            else: states.extend(r['status'] for r in observed); refs.extend(r['asset_check_id'] for r in observed)
        if check and check['evidence_kind']=='combination':
            states.extend('pass' if r['status']=='measured' else 'unknown' for r in contrasts)
            refs.extend(r['contrast_result_id'] for r in contrasts)
            if not contrasts: states.append('unknown'); reasons.append('No applicable controlled combination comparison.')
        status = 'fail' if 'fail' in states else ('unknown' if not states or 'unknown' in states else 'pass')
        rows.append({'requirement_id':requirement['requirement_id'],'status':status,'evidence_refs':sorted(set(refs)),'gaps':reasons})
    states = [r['status'] for r in rows] + [a['status'] for a in assets]
    for result in contrasts:
        contrast_plan=store.get('contrast_plans',result['plan_ref'])
        if result['status']=='measured': states.append('pass')
        elif result['status']=='not_identifiable' and not contrast_plan['required']: pass
        else: states.append('unknown'); gaps.extend(result['gaps'] or ['Incomplete controlled comparison.'])
    status = 'fail' if 'fail' in states else ('unknown' if 'unknown' in states else 'pass')
    return rows, status, gaps


def finish_verification(store, plan, evaluation_plan, results, assets, contrasts):
    materials=store.get('verification_materials',plan['materials_ref'])['value']
    rows,status,gaps=_coverage(store,plan,evaluation_plan,results,assets,contrasts,materials)
    record={'verification_id':'verification_'+digest(plan),'project_id':plan['project_id'],'plan_ref':plan['verification_plan_id'],
        'plan_hash':digest(plan),'requirements':rows,'asset_check_refs':[r['asset_check_id'] for r in assets],
        'contrast_result_refs':[r['contrast_result_id'] for r in contrasts],'status':status,
        'usage_refs':sorted({u for r in assets+contrasts for u in r['usage_refs']}),'gaps':gaps}
    validate('VerificationRecord',record);store.put('verification_records',record['verification_id'],record)
    return record


def verify_verification(store, evaluation_plan, record):
    from .assets import verify_assets
    from .relations import verify_contrast, candidate_pairs
    validate('VerificationRecord',record)
    plan=store.get('verification_plans',evaluation_plan['verification_plan_ref']);validate('VerificationPlan',plan)
    if (record['plan_ref']!=plan['verification_plan_id'] or record['plan_hash']!=digest(plan)
            or evaluation_plan['verification_plan_hash']!=digest(plan)
            or any(plan[k]!=evaluation_plan[k] for k in ('project_id','base_digest','candidate_digest','expected_generation'))
            or plan['evaluation_plan_id']!=evaluation_plan['plan_id']):
        raise DomainError('verification_binding','Verification does not bind the frozen comparison and candidate')
    candidates=[store.get('candidates',ref) for ref in evaluation_plan['proposal_ids']]
    if plan['proposal_hashes']!={c['proposal_id']:digest(c) for c in candidates}:
        raise DomainError('verification_aliases','Verification did not include every exact proposal attempt')
    material=store.get('verification_materials',plan['materials_ref']);validate('VerificationMaterials',material)
    if material['project_id']!=plan['project_id'] or digest(material)!=plan['materials_hash']:
        raise DomainError('verification_materials','Trusted material record changed')
    materials=material['value']
    if plan['requirements']!=requirements_for(store,candidates,materials):
        raise DomainError('verification_obligations','Diagnosis or proposal requirements were omitted')
    snapshot=store.snapshot(plan['candidate_digest'])
    shape=lambda jobs:sorted((j['kind'],j['asset_path'],j['test_id'] or '') for j in jobs)
    if shape(plan['asset_jobs'])!=shape(asset_jobs(snapshot,candidates,materials)):
        raise DomainError('asset_coverage','Frozen job plan does not cover every candidate script/fixture')
    assets=[store.get('asset_checks',ref) for ref in record['asset_check_refs']]
    verify_assets(store,plan,materials,assets)
    contrasts=[store.get('contrast_results',ref) for ref in record['contrast_result_refs']]
    if len(contrasts)!=len(plan['contrast_plan_refs']) or {r['plan_ref'] for r in contrasts}!=set(plan['contrast_plan_refs']):
        raise DomainError('contrast_coverage','Controlled comparison results missing or duplicated')
    contrast_plans=[store.get('contrast_plans',ref) for ref in plan['contrast_plan_refs']]
    expected_pairs=candidate_pairs(store,snapshot,candidates,materials,plan['relation_source_refs'])
    if [(p['from'],p['to'],p['required']) for p in contrast_plans]!=expected_pairs:
        raise DomainError('contrast_coverage','Required local comparisons missing from frozen plan')
    for result in contrasts:
        cp=store.get('contrast_plans',result['plan_ref'])
        if cp['verification_plan_ref']!=plan['verification_plan_id'] or cp['source_snapshot_digest']!=plan['candidate_digest']:
            raise DomainError('contrast_binding','Contrast belongs to another candidate or verification')
        verify_contrast(store,cp,result)
    results=[store.get('evaluation_results',r['request_id']) for r in evaluation_plan['requests']]
    rows,status,gaps=_coverage(store,plan,evaluation_plan,results,assets,contrasts,materials)
    if (record['requirements']!=rows or record['status']!=status or record['gaps']!=gaps
            or record['usage_refs']!=sorted({u for r in assets+contrasts for u in r['usage_refs']})):
        raise DomainError('verification_result','Verification conclusion differs from actual executed coverage')
    return record
