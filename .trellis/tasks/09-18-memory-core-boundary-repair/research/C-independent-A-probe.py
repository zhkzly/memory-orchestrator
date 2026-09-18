"""Independent A boundary probes, temporary Stores only; no models/network."""
import copy
import json
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from memory_orchestrator.lineage import require_learning_source, _closed_group
from memory_orchestrator.sampling import sample_tasks
from memory_orchestrator.schemas import DomainError, digest, new_id
from memory_orchestrator.store import Store
from test_memory_store import episode, feedback

output = {}
with tempfile.TemporaryDirectory(dir='/tmp') as root:
    store = Store(root)
    early = episode(identifier='early')
    early['task'].update(task_id='task', revision='v1')
    early['source'] = {'kind':'execution_function', 'reference':'run-early'}
    store.put('executions','run-early',{'run_id':'run-early','project_id':'alpha',
        'request':{'request_id':'run-early','case_id':'task','task_revision':'v1'},
        'output':{'artifact':'observed-artifact'},'error':None})
    store.add_episode(early)
    correct = feedback(subject='early')
    correct.update(check_id='correct',run_id='run-early',task_revision='v1',
                   evaluated_state_digest=digest('observed-artifact'),binding_status='bound')
    store.add_feedback(correct)
    rejected = {}
    for field, value in [('run_id','other-run'),('evaluated_state_digest',digest('different')),('task_revision','v2')]:
        wrong={**correct,'check_id':'bad-'+field,field:value}
        try:store.add_feedback(wrong)
        except DomainError as exc:rejected[field]=exc.code
        else:raise AssertionError('accepted contradictory '+field)
    output['early_feedback']={'saved':True,'runs':len(store.list('runs')),
                             'receipts':len(store.list('group_receipts')),'rejections':rejected}
    unknown=episode(identifier='external')
    store.add_episode(unknown)
    output['unknown_import']={'known':require_learning_source(store,unknown)['known']}

context={'max_roots':2,'max_context_chars':5000,'relation_weight':0.0}
policy={'repeat_count':1,'max_parallel':2,'purpose':'learning','update_mode':'frozen_microbatch',
        'protocol_id':'batch/v1','executor':{'id':'local/v1','config':{}}}
tasks=[{'project_id':'p','task_id':name,'revision':name+'@1','description':name,'criteria':{}}
       for name in ('first','second')]
with tempfile.TemporaryDirectory(dir='/tmp') as root:
    store=Store(root);blocked=threading.Event();release=threading.Event()
    def execute(request,snapshot,case):
        if request['case_id']=='second':
            blocked.set()
            if not release.wait(10):raise TimeoutError('bounded audit barrier')
        return {'artifact':request['case_id']}
    with ThreadPoolExecutor(max_workers=1) as outer:
        pending=outer.submit(sample_tasks,store,tasks,execute,None,policy=policy,context_policy=context)
        try:
            assert blocked.wait(5)
            deadline=time.monotonic()+5
            while not store.list('runs',project_id='p') and time.monotonic()<deadline:time.sleep(.01)
            run=store.list('runs',project_id='p')[0]
            group=store.get('run_groups',run['group_id'])
            ep=next(e for e in store.list('episodes',project_id='p') if e['source']['reference']==run['run_id'])
            # Give the first task its own legitimate closed-group receipt. This
            # isolates whole-batch eligibility from the first group's own barrier.
            receipt={'receipt_id':new_id('audit_receipt'),'project_id':'p','group_id':group['group_id'],
                     'planned':1,'recorded':1,'run_ids':[run['run_id']],'all_slots_accounted':True,
                     'completed':1,'terminal_status_counts':{s:int(s=='completed') for s in
                         ('completed','cancelled','timeout','budget_exhausted','adapter_error')}}
            store.put('group_receipts',receipt['receipt_id'],receipt)
            assert _closed_group(store,group)['receipt_id']==receipt['receipt_id']
            try:require_learning_source(store,ep)
            except DomainError as exc:code=exc.code
            else:raise AssertionError('batch accepted with unfinished second task')
            output['open_microbatch']={'first_group_closed':True,'stored_runs':1,'batch_groups':2,
                                       'learning_rejection':code,'second_still_running':not pending.done()}
        finally:release.set()
        pending.result(timeout=15)
    output['open_microbatch']['threads_finished']=pending.done()

with tempfile.TemporaryDirectory(dir='/tmp') as root:
    store=Store(root)
    done=sample_tasks(store,tasks,lambda r,*_:{'artifact':r['case_id']},None,policy=policy,context_policy=context)
    accepted=[require_learning_source(store,ep)['known'] for ep in done['episodes']]
    output['closed_microbatch']={'learning_allowed':accepted,'runs':len(done['run_ids']),
                                'receipts':len(done['receipt_ids'])}

print(json.dumps(output,indent=2))
