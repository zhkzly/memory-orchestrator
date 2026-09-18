"""C independently reviews A's real Store/feedback/recovery consumers; no network."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from memory_orchestrator.feedback import verify_assessment, check_planned_feedback
from memory_orchestrator.model import StructuredModel
from memory_orchestrator.sampling import prepare_sampling, resume_sampling, sample_tasks
from memory_orchestrator.schemas import DomainError, new_id
from memory_orchestrator.store import Store
from memory_orchestrator.evaluation import compare_candidates
from memory_orchestrator.release import publish
from test_memory_store import skill
from test_memory_model import limits, response
from test_memory_evaluation import case_set, protocol, execute_csv, evaluate_csv

CTX={'max_roots':2,'max_context_chars':8000,'relation_weight':0}
POLICY={'repeat_count':1,'max_parallel':1,'purpose':'learning','update_mode':'task_barrier',
        'protocol_id':'independent-review','executor':{'id':'local-csv','config':{}},'evaluator':{'id':'fixed-csv-check','config':{}}}
TASK={'project_id':'p','task_id':'csv','revision':'1','description':'CSV identifiers','criteria':{'expected':'001'}}
summary={}

def candidate(store,active):
    snapshot=store.snapshot(active['snapshot_id']); learned=skill('learned',project='p')
    learned['content']['steps']=['Preserve text identifiers.'];snapshot['skills']['learned']=learned
    created=store.save_snapshot('p',snapshot['skills'],{},parent=active['snapshot_id'])
    record={'proposal_id':new_id('proposal'),'project_id':'p','base_digest':active['snapshot_id'],
            'candidate_digest':created['snapshot_id'],'expected_generation':active['generation']}
    store.put('candidates',record['proposal_id'],record);return record

def seed_check(seed):
    with tempfile.TemporaryDirectory() as root:
        store=Store(root)
        if seed:
            initial=skill('seed');initial['content']['steps']=['Infer numeric fields.']
            active=store.initialize_project('p',seed={'skills':{'seed':initial},'assets':{}},source='independent fixed seed fixture')
        else:
            active=store.ensure_project('p');legacy={k:v for k,v in active.items() if k not in ('baseline_ref','bootstrap')}
            store._atomic_write(store._active_path('p'),legacy);active=store.active('p')
        assert active['generation']==0 and active['release_id'] is None and store.release_history('p')==[]
        proposed=candidate(store,active)
        comp=compare_candidates(store,'p',[proposed],case_set(),protocol(),execute_csv,evaluate_csv,max_parallel=1)
        release=publish(store,'p',proposed['proposal_id'],comp['validation_ids'][0],comp['selection_id'],
                        expected_active_digest=active['snapshot_id'],expected_generation=0)
        reopened=Store(root);history=reopened.release_history('p')
        assert len(history)==1 and history[0]['expected_active_digest']==active['snapshot_id']
        assert reopened.active('p')['generation']==1
        if seed:
            assert reopened.active('p')['baseline_ref']==active['baseline_ref']
            assert reopened.get('baselines',active['baseline_ref'])['kind']=='seed'
        return {'baseline':active,'actual_release':release,'history_count':len(history)}

summary['seed_chain']=seed_check(True)
summary['legacy_empty_chain']=seed_check(False)

with tempfile.TemporaryDirectory() as root:
    store=Store(root);active=store.ensure_project('p');proposed=candidate(store,active)
    p=protocol();p['feedback']={'criteria':[{'criterion_id':'external','rule':{},'weight':1},
        {'criterion_id':'proxy','rule':{},'weight':3}], 'aggregation':{'kind':'weighted_sum','threshold':.75}}
    cs=case_set();gold={c['id']:c for c in cs['cases']}
    def mixed(request,execution,case):
        out=evaluate_csv(request,execution,gold[case['id']]);out['source']='llm_proxy' if request['criterion_id']=='proxy' else 'executable';return out
    compared=compare_candidates(store,'p',[proposed],cs,p,execute_csv,mixed,max_parallel=1)
    validation=store.get('validations',compared['validation_ids'][0])
    assessments=[verify_assessment(store,row['assessment_ref'])['aggregate'] for row in validation['results']]
    assert all(row['feedback_sources']==['external','llm_proxy'] for row in assessments)
    assert validation['status']=='unknown' and store.release_history('p')==[]
    summary['mixed_sources']={'assessment_sources':assessments[0]['feedback_sources'],'validation_status':validation['status'],
                              'result_count':len(validation['results'])}

with tempfile.TemporaryDirectory() as root:
    store=Store(root);calls=[]
    def invoke(request):
        calls.append(request)
        packet,_=json.JSONDecoder().raw_decode(request['messages'][1]['content'].split('证据：',1)[1])
        return response({'outcome':'pass','criterion_findings':[{'criterion_id':'task_outcome','outcome':'pass','score':1,
            'finding':'Constructed independent review of proxy provenance','evidence_refs':[packet['fragments'][-1]['ref_id']]}],'unknowns':[]})
    budget=limits(max_calls=1,max_format_repairs=0)
    p={**POLICY,'feedback':{'criteria':[{'criterion_id':'task_outcome','rule':TASK['criteria']}],
        'aggregation':{'kind':'single_task_outcome'},'proxy':{'enabled':True,'limits':budget,
            'packet_limits':{'max_chars':6000,'max_fragment_chars':400,'max_catalog_refs':8,'token_budget':4000}}}}
    sampled=sample_tasks(store,[TASK],lambda *_:{'artifact':'001'},None,policy=p,context_policy=CTX,
                         proxy_model=StructuredModel(invoke,limits=budget))
    assessed=verify_assessment(store,store.get('runs',sampled['run_ids'][0])['assessment_ref'])
    assert len(calls)==1 and assessed['aggregate']['feedback_sources']==['llm_proxy']
    try:check_planned_feedback(store,assessed['plan'],{**assessed['feedbacks'][0],'source':'external'})
    except DomainError as exc:forged_code=exc.code
    else:raise AssertionError('proxy source relabel was accepted')
    summary['proxy']={'scripted_provider_calls':len(calls),'source':assessed['aggregate']['feedback_sources'],'forgery_rejected':forged_code}

for point in ('after_return','inside_execution'):
    with tempfile.TemporaryDirectory() as root:
        store=Store(root);batch=prepare_sampling(store,[TASK],policy=POLICY,context_policy=CTX)
        count=Path(root)/'physical-calls.txt'
        program='''import os,sys
from pathlib import Path
from memory_orchestrator.store import Store
from memory_orchestrator.sampling import resume_sampling
store=Store(sys.argv[1])
def execute(*args):
    with Path(sys.argv[3]).open('a') as stream:stream.write('called\\n')
    if sys.argv[4]=='inside_execution':os._exit(31)
    return {'artifact':'001'}
if sys.argv[4]=='after_return':store.add_episode=lambda *args,**kwargs:os._exit(29)
resume_sampling(store,sys.argv[2],execute,None)
'''
        child=subprocess.run([sys.executable,'-c',program,root,batch['batch_id'],str(count),point],capture_output=True,text=True,timeout=8)
        assert child.returncode==(29 if point=='after_return' else 31),child.stderr
        def forbidden(*_):raise AssertionError('saved/unknown execution was repeated')
        resumed=resume_sampling(Store(root),batch['batch_id'],forbidden,None)
        assert count.read_text().splitlines()==['called']
        if point=='inside_execution':
            assert resumed['status']=='blocked' and len(resumed['blocked'])==1
            reference=resumed['blocked'][0]['request_ref']
            resumed=resume_sampling(Store(root),batch['batch_id'],forbidden,None,resolutions={reference:{
                'action':'close_unknown','source':'independent review child process exit','evidence':[{'exit_code':31}]}})
            assessment=store.get('assessments',store.get('runs',resumed['run_ids'][0])['assessment_ref'])
            assert assessment['outcome']=='unknown' and assessment['score'] is None
        assert resumed['status']=='completed' and count.read_text().splitlines()==['called']
        receipt=store.get('sampling_batch_receipts',resumed['batch_receipt_id'])
        assert receipt['missing_segment_count']==1
        summary[point]={'child_exit':child.returncode,'physical_execution_calls':len(count.read_text().splitlines()),
            'status':resumed['status'],'missing_wall_segments':receipt['missing_segment_count'],
            'attempts':len(store.list('callback_attempts','p')),'returns':len(store.list('callback_returns','p'))}

summary['source_sha256']={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in
    map(Path,['src/memory_orchestrator/feedback.py','src/memory_orchestrator/sampling.py','src/memory_orchestrator/store.py'])}
Path('/tmp/memory-c-review-a-results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print(json.dumps(summary,ensure_ascii=False,indent=2))
