"""Existing interrupted sampler boundary, only temporary Store and local callbacks."""
import json
import sys
import tempfile
from unittest.mock import patch

from memory_orchestrator.lineage import require_learning_source
from memory_orchestrator.report import report
from memory_orchestrator.sampling import sample_tasks
from memory_orchestrator.schemas import DomainError
from memory_orchestrator.store import Store

with tempfile.TemporaryDirectory(dir='/tmp') as root:
    store=Store(root)
    stop_kind=sys.argv[1] if len(sys.argv)>1 else 'runs'
    original=store.put
    def interrupt(kind,identifier,value):
        if kind==stop_kind:raise OSError('constructed interruption before '+stop_kind)
        return original(kind,identifier,value)
    try:
        with patch.object(store,'put',side_effect=interrupt):
            sample_tasks(store,[{'project_id':'p','task_id':'task','revision':'1','description':'Check an artifact','criteria':{'expected':'ok'}}],
                lambda *_:{'artifact':'ok'},
                lambda request,execution,case:{'outcome':'pass','score':1,'source':'executable',
                                              'evidence':[execution['artifact']==case['criteria']['expected']]},
                policy={'repeat_count':1,'max_parallel':1,'purpose':'learning','update_mode':'task_barrier',
                        'protocol_id':'fixture/v1','executor':{'id':'local/v1','config':{}}},
                context_policy={'max_roots':1,'max_context_chars':5000,'relation_weight':0})
    except OSError:
        pass
    episode=store.list('episodes',project_id='p')[0]
    try:require_learning_source(store,episode);learning='allowed'
    except DomainError as exc:learning=exc.code
    observed=report(store,'p')['sampling']['groups'][0]
    print(json.dumps({'interrupted_before':stop_kind,'raw_feedback':[f['outcome'] for f in store.list('feedback',project_id='p')],
                      'assessments':[a['outcome'] for a in store.list('assessments',project_id='p')],
                      'run_bundles':len(store.list('runs',project_id='p')),
                      'reported_outcomes':observed['outcomes'],
                      'recorded_runs':observed['recorded_runs'],
                      'learning_gate':learning},indent=2))
