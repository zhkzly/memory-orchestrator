"""Actual local scripts and CSV checks; constructed behavior, not effect claims."""
import copy
import unittest

from memory_orchestrator.schemas import DomainError, digest, new_id
from memory_orchestrator.release import publish
from test_memory_evaluation import MemoryFixture, case_set, protocol, execute_csv, evaluate_csv


class VerificationTests(MemoryFixture, unittest.TestCase):
    def promote(self,result):
        return publish(self.store,self.project,self.candidate['proposal_id'],result['validation_ids'][0],
            result['selection_id'],expected_active_digest=self.active['snapshot_id'],expected_generation=self.active['generation'])
    def replace_candidate(self, *, checks=(), script=None, extra_skills=None):
        old = self.store.snapshot(self.candidate['candidate_digest'])
        skills, assets = copy.deepcopy(old['skills']), copy.deepcopy(old['assets'])
        sid = next(iter(skills))
        if script is not None:
            path = sid + '/scripts/convert.py'
            assets[path] = script
            skills[sid]['asset_refs'] = [path]
        if extra_skills:
            skills.update(extra_skills)
        snapshot = self.store.save_snapshot(self.project, skills, assets, parent=self.active['snapshot_id'])
        candidate = {**self.candidate, 'proposal_id': new_id('proposal'),
                     'candidate_digest': snapshot['snapshot_id'], 'check_plan': list(checks),
                     'changed_skill_refs': list(skills)}
        self.store.put('candidates', candidate['proposal_id'], candidate)
        self.candidate = candidate
        return sid

    def test_unbound_check_cannot_pass_or_publish_and_alias_obligations_union(self):
        sibling = self.candidate
        self.replace_candidate(checks=[{'purpose':'distinguish','behavior':'Resolve cause',
            'required_evidence':'Independent separating case','check_ref':None}])
        result = self.compare(candidates=[sibling,self.candidate])
        val = self.validation(result)
        self.assertEqual(val['status'], 'unknown')
        self.assertEqual(len(result['plan_ids']), 1)
        self.assertFalse(next(g for g in val['gate_results'] if g['gate']=='verification_complete')['passed'])
        self.assertEqual(self.store.active(self.project), self.active)

    def test_alias_obligation_order_is_stable_for_publication(self):
        aliases=[]
        for identifier in ('z-proposal','a-proposal'):
            candidate={**self.candidate,'proposal_id':identifier,'check_plan':[{'purpose':'target',
                'behavior':'Keep identifier text','required_evidence':'Declared CSV exact check','check_ref':'case:identifiers'}]}
            self.store.put('candidates',identifier,candidate);aliases.append(candidate)
        self.candidate=aliases[0]
        result=self.compare(candidates=aliases)
        self.assertEqual(self.validation(result)['status'],'accepted')
        self.assertEqual(self.promote(result)['status'],'published')

    def test_requested_additional_material_changes_requests_and_catalog_hides_gold(self):
        from memory_orchestrator.verification import verification_catalog
        self.replace_candidate(checks=[{'purpose':'distinguish','behavior':'Preserve scientific identifiers',
            'required_evidence':'Leading zero fixture','check_ref':'check:extra'}])
        extra=copy.deepcopy(case_set()['cases'][0]);extra['id']='extra-case'
        material={'id':'extra','version':'v1','checks':[{'check_ref':'check:extra','purpose':'distinguish',
            'description':'Independent identifier case','evidence_kind':'task','case_ids':['extra-case'],
            'asset_test_ids':[]}],'cases':[extra]}
        catalog=verification_catalog(case_set(),material)
        self.assertNotIn('criteria',repr(catalog))
        result=self.compare(verification=material)
        plan=self.store.get('evaluation_plans',result['plan_ids'][0])
        self.assertEqual(len(plan['requests']),12)
        self.assertEqual(self.validation(result)['status'],'accepted')

    def test_reused_full_task_specs_do_not_leak_private_fields(self):
        from memory_orchestrator.verification import verification_catalog
        cases=case_set()
        for case in cases['cases']:
            case['task']['criteria']={'secret':'hidden answer'}
            case['task']['private']={'secret':'private checker implementation'}
        catalog=verification_catalog(cases)
        self.assertNotIn('hidden answer',repr(catalog))
        self.assertNotIn('private checker implementation',repr(catalog))
        def execute(request,snapshot,case):
            self.assertNotIn('criteria',case['task'])
            self.assertNotIn('private',case['task'])
            return execute_csv(request,snapshot,case)
        def evaluate(request,execution,case):
            self.assertIn('sum',case['criteria'])
            return evaluate_csv(request,execution,case)
        result=self.compare(case_set=cases,execute_fn=execute,evaluate_fn=evaluate)
        self.assertEqual(self.validation(result)['status'],'accepted')

    def test_material_catalog_is_stable_across_json_key_order(self):
        from memory_orchestrator.verification import verification_catalog
        left=case_set();right=copy.deepcopy(left)
        left['cases'][0]['task']={'csv':left['cases'][0]['task']['csv'],'format':'CSV'}
        right['cases'][0]['task']={'format':'CSV','csv':right['cases'][0]['task']['csv']}
        self.assertEqual(verification_catalog(left),verification_catalog(right))

    def test_optional_checks_cannot_dilute_the_original_quality_objective(self):
        protected=case_set();protected['cases'][0]['criteria']['codes']=['12','7']
        extra=[]
        for i,codes in enumerate((['0012','0007'],['0018','0005'])):
            row=copy.deepcopy(case_set()['cases'][0]);row['id']='optional-preserve-'+str(i)
            row['task']['csv']='code,amount\n'+codes[0]+',3\n'+codes[1]+',4\n';row['criteria']['codes']=codes
            extra.append(row)
        checks=[{'check_ref':'check:'+c['id'],'purpose':'target','description':'Optional preservation fixture',
            'evidence_kind':'task','case_ids':[c['id']],'asset_test_ids':[]} for c in extra]
        self.replace_candidate(checks=[{'purpose':'target','behavior':c['description'],
            'required_evidence':'Independent optional fixture','check_ref':c['check_ref']} for c in checks])
        result=self.compare(case_set=protected,verification={'id':'trusted-pool','version':'1','checks':checks,'cases':extra})
        validation=self.validation(result)
        self.assertEqual(validation['status'],'rejected')
        self.assertFalse(next(g for g in validation['gate_results'] if g['gate']=='target_gain')['passed'])
        plan=self.store.get('evaluation_plans',result['plan_ids'][0])
        self.assertEqual(plan['quality_case_refs'],['identifiers','sum'])
        self.assertEqual(len(plan['requests']),16)
        with self.assertRaises(DomainError):self.promote(result)

    def asset_material(self,sid):
        return {'id':'trusted-script-fixture','version':'v1','asset_tests':[{
            'test_id':'convert-functional','owner_skill_ref':sid,'entrypoint':'scripts/convert.py',
            'args':[],'stdin':'0012\n','input_files':{},'expected_stdout':'0012\n','expected_files':{},
            'timeout_seconds':1.0,'max_output_bytes':4096,'required_isolation':'process'}]}

    def test_compile_and_function_are_both_executed_and_wrong_function_rejected(self):
        for script,expected in [('if ???','rejected'),('print(12)','rejected'),
                                ('import sys\nprint(sys.stdin.read().strip())','accepted')]:
            with self.subTest(script=script):
                sid=self.replace_candidate(script=script)
                result=self.compare(verification=self.asset_material(sid))
                self.assertEqual(self.validation(result)['status'],expected)
                plan=self.store.get('evaluation_plans',result['plan_ids'][0])
                checks=[c for c in self.store.list('asset_checks',project_id=self.project)
                        if c['verification_plan_ref']==plan['verification_plan_ref']]
                self.assertCountEqual([c['kind'] for c in checks],['compile','function'])
                self.assertEqual(next(c['status'] for c in checks if c['kind']=='compile'),
                                 'fail' if script=='if ???' else 'pass')
                if expected=='accepted':
                    self.assertEqual(self.promote(result)['status'],'published')

    def test_missing_functional_material_and_unavailable_isolation_are_unknown(self):
        sid=self.replace_candidate(script='print("0012")')
        self.assertEqual(self.validation(self.compare())['status'],'unknown')
        material=self.asset_material(sid)
        material['asset_tests'][0]['required_isolation']='sandbox'
        self.assertEqual(self.validation(self.compare(verification=material))['status'],'unknown')

    def test_contrast_executes_distinct_dependency_complete_views(self):
        skill=copy.deepcopy(next(iter(self.store.snapshot(self.candidate['candidate_digest'])['skills'].values())))
        skill.update(skill_id='csv-two');skill['content']['title']='Other capability'
        sid=self.replace_candidate(extra_skills={'csv-two':skill})
        material={'id':'contrasts','version':'v1','relation_pairs':[{'from':sid,'to':'csv-two','required':True}]}
        seen=[]
        def execute_view(request,view,case):
            seen.append(sorted(view['skills']))
            self.assertNotIn('snapshot_id',view)
            return {'artifact':{'has_identifier_skill':sid in view['skills']}}
        def evaluator(request,execution,case):
            if request['arm'] in ('without','with'):
                score=int(execution['artifact']['has_identifier_skill'])
                return {'outcome':'pass' if score else 'fail','score':score,'source':'executable','evidence':[{'score':score}]}
            return evaluate_csv(request,execution,case)
        result=self.compare(verification=material,execute_view=execute_view,evaluate_fn=evaluator)
        self.assertEqual(self.validation(result)['status'],'accepted')
        self.assertIn(['csv-two'],seen)
        self.assertIn(sorted([sid,'csv-two']),seen)
        relations=[r for r in self.store.list('relations',project_id=self.project) if r['kind']=='measured_effect']
        self.assertEqual(len(relations),1)
        self.assertEqual(relations[0]['value'],1)
        self.assertEqual(relations[0]['skill_revisions'],{sid:'r1','csv-two':'r1'})
        self.assertEqual(self.promote(result)['status'],'published')

    def test_diagnosis_check_is_not_removed_by_empty_patch_plan(self):
        diagnosis={'diagnosis_id':new_id('diagnosis'),'project_id':self.project,
            'base_digest':self.active['snapshot_id'],'draft':{'check_plan':[{'purpose':'distinguish',
            'behavior':'Separate two failure explanations','required_evidence':'Independent case','check_ref':None}]}}
        self.store.put('diagnoses',diagnosis['diagnosis_id'],diagnosis)
        candidate={**self.candidate,'proposal_id':new_id('proposal'),'check_plan':[],
            'diagnosis_ref':diagnosis['diagnosis_id'],'diagnosis_hash':digest(diagnosis)}
        self.store.put('candidates',candidate['proposal_id'],candidate);self.candidate=candidate
        result=self.compare()
        self.assertEqual(self.validation(result)['status'],'unknown')
        with self.assertRaises(DomainError):self.promote(result)

    def test_timeout_output_limit_and_unknown_returns_never_pass_function_check(self):
        for script,reason in [('while True: pass','timeout'),('print("x"*10000)','output_limit')]:
            with self.subTest(reason=reason):
                sid=self.replace_candidate(script=script)
                materials=self.asset_material(sid);materials['asset_tests'][0]['timeout_seconds']=.1
                result=self.compare(verification=materials)
                self.assertEqual(self.validation(result)['status'],'unknown')
                vp=self.store.get('evaluation_plans',result['plan_ids'][0])['verification_plan_ref']
                records=[r for r in self.store.list('asset_checks',self.project)
                         if r['verification_plan_ref']==vp and r['kind']=='function']
                self.assertEqual(records[0]['raw']['interruption'],reason)
                self.assertEqual(len(records[0]['usage_refs']),1)

    def test_asset_revision_and_function_result_cannot_be_substituted(self):
        sid=self.replace_candidate(script='print("0012")')
        result=self.compare(verification=self.asset_material(sid))
        original=self.store.get
        def changed(kind,identifier):
            value=original(kind,identifier)
            if kind=='asset_checks' and value['kind']=='function':
                value['raw']['stdout']='wrong-but-status-still-pass'
            return value
        from unittest.mock import patch
        with patch.object(self.store,'get',side_effect=changed),self.assertRaises(DomainError):
            self.promote(result)
        def changed_original(kind,identifier):
            value=original(kind,identifier)
            if kind=='callback_returns' and value['request_ref'].endswith(':asset'):
                value['raw_output']['stdout']='different observed script output'
            return value
        with patch.object(self.store,'get',side_effect=changed_original),self.assertRaises(DomainError):
            self.promote(result)

    def test_engine_forwards_materials_through_default_verification(self):
        from memory_orchestrator.engine import evolve
        from unittest.mock import patch
        sid=self.replace_candidate(script='print("0012")')
        learning={'status':'proposed','candidate_ids':[self.candidate['proposal_id']],'cycle_id':'constructed-learning'}
        with patch('memory_orchestrator.engine.learn',return_value=learning) as learner:
            result=evolve(self.store,['constructed-episode'],None,learning_policy={},case_set=case_set(),
                protocol=protocol(),execute=execute_csv,evaluate=evaluate_csv,max_parallel=1,
                verification=self.asset_material(sid))
        self.assertEqual(result['status'],'published')
        self.assertTrue(learner.call_args.kwargs['verification_catalog'])

    def test_required_combination_with_identical_dependency_closures_is_unknown(self):
        snapshot=self.store.snapshot(self.candidate['candidate_digest'])
        sid=next(iter(snapshot['skills']))
        other=copy.deepcopy(snapshot['skills'][sid]);other['skill_id']='dependent'
        other['content']['depends_on']=[sid]
        self.replace_candidate(extra_skills={'dependent':other})
        material={'id':'dependent','version':'v1','relation_pairs':[{'from':sid,'to':'dependent','required':True}]}
        calls=[]
        result=self.compare(verification=material,execute_view=lambda *args:calls.append(args))
        self.assertEqual(self.validation(result)['status'],'unknown')
        plans=self.store.list('contrast_plans',self.project)
        required=next(p for p in plans if p['required'])
        self.assertEqual(required['state'],'not_identifiable')
        self.assertFalse(any(r.get('kind')=='measured_effect' for r in self.store.list('relations',self.project)))
        for plan in plans:
            for view_id in plan['arms'].values():
                if view_id:
                    view=self.store.get('execution_views',view_id)
                    if 'dependent' in view['skills']:self.assertIn(sid,view['skills'])

    def test_contrast_budget_includes_all_criterion_calls_before_execution(self):
        skill=copy.deepcopy(next(iter(self.store.snapshot(self.candidate['candidate_digest'])['skills'].values())))
        skill['skill_id']='other';sid=self.replace_candidate(extra_skills={'other':skill})
        material={'id':'budget','version':'v1','relation_pairs':[{'from':sid,'to':'other','required':True}]}
        p=protocol();p['criteria']['maximum_evaluation_calls']=8
        with self.assertRaises(DomainError):
            self.compare(protocol=p,verification=material,execute_view=lambda *_:self.fail('not before budget'),
                         execute_fn=lambda *_:self.fail('not before budget'))
        self.assertEqual(self.store.list('evaluation_returns',self.project),[])

    def test_multi_criterion_comparison_uses_fixed_denominator_and_original_feedback(self):
        p=protocol();p['feedback']={'criteria':[{'criterion_id':'csv','rule':{'kind':'csv'},'weight':3},
            {'criterion_id':'extra','rule':{'kind':'extra'},'weight':1}],
            'aggregation':{'kind':'weighted_sum','threshold':.75},'proxy':None}
        p['criteria']['maximum_evaluation_calls']=16
        def evaluator(request,execution,case):
            self.assertEqual(case['criteria']['kind'],request['criterion_id'])
            if request['criterion_id']=='extra' and request['arm']=='candidate':
                return {'outcome':'unknown','score':None,'source':'executable','evidence':['missing']}
            score=int(request['arm']=='candidate') if case['split']=='target' else 1
            return {'outcome':'pass' if score else 'fail','score':score,'source':'executable','evidence':['fixed']}
        result=self.compare(protocol=p,evaluate_fn=evaluator)
        self.assertEqual(self.validation(result)['status'],'unknown')
        records=[self.store.get('assessments',r['assessment_ref']) for r in self.validation(result)['results']]
        self.assertTrue(any(r['score_bounds']==[.75,1.0] and r['score'] is None for r in records))
        self.assertEqual(len([r for r in self.store.list('callback_returns',self.project) if r['stage']=='evaluate']),16)

    def test_measured_local_csv_effect_changes_real_selector_only_in_scope(self):
        from memory_orchestrator.context import select_context
        snapshot=self.store.snapshot(self.candidate['candidate_digest'])
        extra={}
        for identifier in ('a-anchor','b-distractor'):
            skill=copy.deepcopy(next(iter(snapshot['skills'].values())))
            skill.update(skill_id=identifier);skill['content']['steps']=['Infer numeric fields.']
            extra[identifier]=skill
        sid=self.replace_candidate(extra_skills=extra)
        material={'id':'real-csv-views','version':'v1','relation_pairs':[{'from':sid,'to':'a-anchor','required':True}],
            'relation_policy':{'max_pairs':1,'background_skill_ids':[],'task_family':'csv'}}
        result=self.compare(verification=material,execute_view=execute_csv)
        self.assertEqual(self.validation(result)['status'],'accepted')
        self.promote(result)
        policy={'max_roots':2,'max_context_chars':20000,'relation_weight':10}
        task={'project_id':self.project,'task_id':'new-csv-task','task_family':'csv','description':'csv conversion'}
        chosen=select_context(self.store,task,policy)
        self.assertEqual([r['skill_id'] for r in chosen['roots']],['a-anchor',sid])
        other=select_context(self.store,{**task,'task_family':'unrelated'},policy)
        self.assertEqual([r['skill_id'] for r in other['roots']],['a-anchor','b-distractor'])
        relation=next(r for r in self.store.list('relations',self.project) if r['kind']=='measured_effect')
        self.assertEqual(relation['value'],.5)

    def test_uncompleted_contrast_does_not_produce_a_numeric_relation(self):
        skill=copy.deepcopy(next(iter(self.store.snapshot(self.candidate['candidate_digest'])['skills'].values())))
        skill['skill_id']='anchor';sid=self.replace_candidate(extra_skills={'anchor':skill})
        material={'id':'missing-contrast','version':'v1','relation_pairs':[{'from':sid,'to':'anchor','required':True}]}
        def evaluator(request,execution,case):
            if request['arm']=='with' and request['repeat_index']==1:
                return {'outcome':'unknown','score':None,'source':'executable','evidence':['checker missing']}
            return evaluate_csv(request,execution,case)
        result=self.compare(verification=material,execute_view=execute_csv,evaluate_fn=evaluator)
        self.assertEqual(self.validation(result)['status'],'unknown')
        self.assertFalse(any(r['kind']=='measured_effect' for r in self.store.list('relations',self.project)))
        contrast=self.store.list('contrast_results',self.project)[0]
        self.assertEqual(len(contrast['result_refs']),8)
        self.assertIsNone(contrast['value'])

    def test_missing_view_provider_preserves_all_planned_unknown_slots(self):
        skill=copy.deepcopy(next(iter(self.store.snapshot(self.candidate['candidate_digest'])['skills'].values())))
        skill['skill_id']='anchor';sid=self.replace_candidate(extra_skills={'anchor':skill})
        material={'id':'no-view-provider','version':'v1','relation_pairs':[{'from':sid,'to':'anchor','required':True}]}
        result=self.compare(verification=material)
        self.assertEqual(self.validation(result)['status'],'unknown')
        plan=self.store.list('contrast_plans',self.project)[0]
        observed=self.store.list('contrast_results',self.project)[0]
        self.assertEqual(plan['state'],'missing_capability')
        self.assertEqual(len(plan['requests']),8)
        self.assertEqual(len(observed['result_refs']),8)
        self.assertTrue(all(self.store.get('evaluation_results',r)['outcome']=='unknown' for r in observed['result_refs']))
        self.assertTrue(all(self.store.get('evaluation_results',r)['execution_ref'] is None for r in observed['result_refs']))

    def test_asset_and_contrast_derived_records_resume_without_repeating_calls(self):
        from memory_orchestrator.evaluation import resume_comparison
        from unittest.mock import patch
        sid=self.replace_candidate(script='print("0012")')
        original=self.store.put;failed=[]
        def fail_asset(kind,identifier,row):
            if kind=='asset_checks' and row['kind']=='function' and not failed:
                failed.append(identifier);raise OSError('stop after actual functional return')
            return original(kind,identifier,row)
        with patch.object(self.store,'put',side_effect=fail_asset):
            result=self.compare(verification=self.asset_material(sid))
        self.assertEqual(result['status'],'blocked')
        before=len(self.store.list('callback_returns',self.project))
        with patch('memory_orchestrator.assets.python_asset_runner',side_effect=AssertionError('must reuse return')):
            resumed=resume_comparison(self.store,result['comparison_id'],execute_csv,evaluate_csv)
        self.assertEqual(self.validation(resumed)['status'],'accepted')
        self.assertEqual(len(self.store.list('callback_returns',self.project)),before)

    def test_explicit_non_python_compiler_and_function_provider_are_recorded(self):
        import subprocess
        import tempfile
        from pathlib import Path
        snapshot=self.store.snapshot(self.candidate['candidate_digest']);sid=next(iter(snapshot['skills']))
        path=sid+'/scripts/convert.sh'
        snapshot['assets']={path:'read value\nprintf "%s\\n" "$value"\n'}
        snapshot['skills'][sid]['asset_refs']=[path]
        saved=self.store.save_snapshot(self.project,snapshot['skills'],snapshot['assets'],parent=self.active['snapshot_id'])
        candidate={**self.candidate,'proposal_id':new_id('proposal'),'candidate_digest':saved['snapshot_id']}
        self.store.put('candidates',candidate['proposal_id'],candidate);self.candidate=candidate
        material=self.asset_material(sid);material['asset_tests'][0]['entrypoint']='scripts/convert.sh'
        material['asset_runner']={'id':'constructed-sh-runtime/v1','config':{},'isolation':'process'}
        called=[]
        def runner(request,snapshot,test):
            called.append(request['kind'])
            with tempfile.TemporaryDirectory() as directory:
                script=Path(directory)/'convert.sh';script.write_text(snapshot['assets'][request['asset_path']])
                argv=['/bin/sh',*( ['-n'] if request['kind']=='compile' else []),str(script)]
                actual=subprocess.run(argv,input=test['stdin'] if test else '',capture_output=True,text=True,timeout=1,cwd=directory)
                if request['kind']=='compile':return {'available':True,'compiled':actual.returncode==0,'stderr':actual.stderr}
                return {'available':True,'returncode':actual.returncode,'stdout':actual.stdout,'stderr':actual.stderr,'files':{},'interruption':None}
        result=self.compare(verification=material,asset_runner=runner)
        self.assertEqual(self.validation(result)['status'],'accepted')
        self.assertEqual(called,['compile','function'])
        self.assertEqual(self.promote(result)['status'],'published')

    def test_contrast_derived_record_resumes_without_repeating_calls(self):
        from memory_orchestrator.evaluation import resume_comparison
        from unittest.mock import patch
        skill=copy.deepcopy(next(iter(self.store.snapshot(self.candidate['candidate_digest'])['skills'].values())))
        skill['skill_id']='anchor';skill['asset_refs']=[]
        sid=self.replace_candidate(extra_skills={'anchor':skill})
        material={'id':'contrast-resume','version':'v1','relation_pairs':[{'from':sid,'to':'anchor','required':True}]}
        failed=[];original=self.store.put
        def fail_contrast(kind,identifier,row):
            if kind=='contrast_results' and not failed:
                failed.append(identifier);raise OSError('stop after actual controlled returns')
            return original(kind,identifier,row)
        with patch.object(self.store,'put',side_effect=fail_contrast):
            result=self.compare(verification=material,execute_view=execute_csv)
        self.assertEqual(result['status'],'blocked')
        before=len(self.store.list('callback_returns',self.project))
        resumed=resume_comparison(self.store,result['comparison_id'],execute_csv,evaluate_csv,
            execute_view=lambda *_:self.fail('must reuse controlled request results'))
        self.assertEqual(self.validation(resumed)['status'],'accepted')
        self.assertEqual(len(self.store.list('callback_returns',self.project)),before)


if __name__=='__main__':unittest.main()
