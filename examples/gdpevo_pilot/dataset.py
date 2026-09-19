"""Pinned GDPevo public business tools and a separate official scoring boundary.

The Actor receives input files and the official ERP router's GET results. It
never receives filesystem/evaluator access. No business decision is implemented
here; the model must obtain relevant records and produce its own answer.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import threading
import types
from urllib.parse import parse_qsl, unquote, urlsplit

from memory_orchestrator.schemas import DomainError


PINNED_COMMIT='56d60ae4ae5e067d1ec0ee1f850622e69f422179'
_IMPORT_LOCK=threading.Lock()
_COLLECTION_QUERIES={
    '/':set(),'/health':set(),'/products':set(),'/customers':set(),'/warehouses':set(),
    '/suppliers':set(),'/boms':set(),
    '/inventory':{'warehouse_id','sku'},
    '/purchase_orders':{'supplier_id','sku','status'},
    '/orders':{'wave','required_date','customer_id'},
    '/shipping/quote':{'warehouse_id','destination_zip','weight_lb','speed'},
    '/incidents':{'start','end','supplier_id','sku','incident_type','status'},
}
_ITEM_COLLECTIONS={'products','customers','orders','boms'}


def _require(condition,code,message):
    if not condition:raise DomainError(code,message)


def _module(path,name):
    """Load only the exact pinned file, without writing checkout bytecode."""
    module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),module.__dict__)
    return module


class GDPevoDataset:
    def __init__(self,source_root,group_id='task_group_007',commit=PINNED_COMMIT):
        self.source_root=Path(source_root).resolve()
        _require(re.fullmatch(r'task_group_\d{3}',group_id) is not None,
                 'benchmark_group','Use an exact official task_group_NNN identifier.')
        observed=subprocess.run(['git','-C',str(self.source_root),'rev-parse','HEAD'],
                                capture_output=True,text=True,timeout=10,check=False)
        _require(observed.returncode==0 and observed.stdout.strip()==commit,
                 'benchmark_commit','GDPevo checkout does not match the declared immutable commit.')
        self.group_id,self.commit=group_id,commit
        self.group_root=self.source_root/'data/task_groups'/group_id
        env=self.group_root/'env'
        _require((env/'server.py').is_file(),'benchmark_environment','Official ERP environment is missing.')
        readme=(env/'README.md').read_text(encoding='utf-8')
        _require('## Domain Endpoints' in readme,'benchmark_environment','Official public endpoint documentation is missing.')
        # endpoints.txt contains routes not implemented in this commit; the
        # README Domain Endpoints section agrees with the actual server router.
        self.business_docs='## Domain Endpoints'+readme.split('## Domain Endpoints',1)[1]
        _require('/api/judge' not in self.business_docs and 'POST' not in self.business_docs,
                 'benchmark_visibility','The Actor endpoint description must contain business GETs only.')
        with _IMPORT_LOCK:
            previous=sys.modules.get('judge_api')
            try:
                # server.py imports this helper, but loading it calls no judge
                # and opens no answers. Only ERPHandler.route is exposed below.
                sys.modules['judge_api']=_module(env/'judge_api.py','judge_api')
                server=_module(env/'server.py','_gdpevo_pinned_erp')
            finally:
                if previous is None:sys.modules.pop('judge_api',None)
                else:sys.modules['judge_api']=previous
        self._handler=server.ERPHandler.__new__(server.ERPHandler)
        self._handler.data=server.load_data()
        self.shared_environment_id=f'gdpevo:{commit}:{group_id}:env'

    def _task_dir(self,task_id):
        match=re.fullmatch(r'(train|test)_(\d{3})',task_id or '')
        _require(match is not None,'benchmark_task','Use a fixed task identifier such as train_001.')
        split,identifier=match.groups()
        path=self.group_root/(split+'_tasks')/identifier
        _require(path.is_dir(),'benchmark_task','Requested benchmark task does not exist.')
        return path

    def task(self,split,identifier):
        _require(split in ('train','test'),'benchmark_task','Split must be train or test.')
        _require(type(identifier) in (str,int) and str(identifier).isdigit(),
                 'benchmark_task','Task number must be a numeric official identifier.')
        task_id=f'{split}_{int(identifier):03d}'
        self._task_dir(task_id)
        return {'project_id':f'gdpevo-{self.group_id}','task_id':task_id,'revision':self.commit,
                'task_family':'northwind_erp','description':self.read_input(task_id,'prompt.txt'),
                'source_id':f'gdpevo:{self.commit}:{self.group_id}:{task_id}:input',
                'shared_environment_id':self.shared_environment_id,
                'input_files':self.public_files(task_id)}

    def public_files(self,task_id):
        directory=(self._task_dir(task_id)/'input').resolve()
        result={}
        for path in sorted(directory.rglob('*')):
            if path.is_file():
                _require(not path.is_symlink() and path.resolve().is_relative_to(directory),
                         'benchmark_input','Public input cannot link to another material directory.')
                result[path.relative_to(directory).as_posix()]=path.stat().st_size
        return result

    def read_input(self,task_id,path):
        _require(isinstance(path,str),'benchmark_input','Input path must be text.')
        if path.startswith('input/'):path=path.removeprefix('input/')
        parsed=PurePosixPath(path)
        _require(bool(path) and not parsed.is_absolute() and str(parsed)==path and '..' not in parsed.parts
                 and '\\' not in path and all(ord(c)>=32 for c in path),
                 'benchmark_input','Only exact paths relative to the current public input directory are allowed.')
        _require(path in self.public_files(task_id),'benchmark_input','This file is not part of the current public input.')
        target=self._task_dir(task_id)/'input'/path
        return target.read_text(encoding='utf-8')

    def business_get(self,path,query=None):
        _require(isinstance(path,str) and path.startswith('/'),'benchmark_endpoint','Use an official relative GET path.')
        parsed=urlsplit(path)
        _require(not parsed.scheme and not parsed.netloc and not parsed.fragment,
                 'benchmark_endpoint','External URLs and fragments are not business endpoints.')
        parts=[unquote(part) for part in parsed.path.split('/') if part]
        route='/'+'/'.join(parts) if parts else '/'
        if route in _COLLECTION_QUERIES:allowed=_COLLECTION_QUERIES[route]
        elif len(parts)==2 and parts[0] in _ITEM_COLLECTIONS and parts[1] not in ('.','..') and '/' not in parts[1]:allowed=set()
        else:raise DomainError('benchmark_endpoint','This endpoint is not an implemented official business GET.')
        embedded=parse_qsl(parsed.query,keep_blank_values=True)
        _require(len({key for key,_ in embedded})==len(embedded),'benchmark_query','Duplicate query fields are ambiguous.')
        supplied={} if query is None else copy.deepcopy(query)
        _require(isinstance(supplied,dict) and not (set(supplied)&{key for key,_ in embedded}),
                 'benchmark_query','Use each query field once, in the path or the query object.')
        supplied.update(embedded)
        _require(set(supplied)<=allowed,'benchmark_query','This official endpoint does not support the requested filter.')
        for value in supplied.values():
            _require(type(value) in (str,int,float) and (type(value) is not float or math.isfinite(value)),
                     'benchmark_query','Query values must be finite numbers or strings.')
        try:return copy.deepcopy(self._handler.route(parts,{key:[str(value)] for key,value in supplied.items()}))
        except (KeyError,ValueError,TypeError,IndexError) as exc:
            raise DomainError('benchmark_query',str(exc)) from exc

    def evaluate(self,request,execution,full_case):
        """Score one original artifact outside the Actor, preserving official output."""
        _require(isinstance(full_case,dict) and isinstance(full_case.get('task'),dict),
                 'benchmark_binding','Scoring needs the bound public task, not a caller-selected evaluator path.')
        task=full_case['task'];task_id=task.get('task_id')
        directory=self._task_dir(task_id)
        _require(task.get('revision')==self.commit,'benchmark_binding','Task revision differs from the pinned source.')
        for field in ('case_ref','case_id'):
            if field in request:
                _require(request[field]==full_case.get('id'),'benchmark_binding','Scoring request belongs to a different case.')
        if 'task_id' in request:
            _require(request['task_id']==task_id,'benchmark_binding','Scoring request belongs to a different benchmark task.')
        script=directory/'eval/eval.sh';scorer=directory/'eval/evaluate.py';gold=directory/'output/answer.json'
        evidence={'kind':'gdpevo_official_evaluator','group_id':self.group_id,'task_id':task_id,
                  'source_commit':self.commit,'returncode':None,'stdout':'','stderr':'','result':None}
        if not all(path.is_file() for path in (script,scorer,gold)):
            evidence['error']='Official scorer or private reference is unavailable.'
            return {'outcome':'unknown','score':None,'source':'executable','evidence':[evidence]}
        evidence['scorer_sha256']=hashlib.sha256(scorer.read_bytes()).hexdigest()
        if not isinstance(execution,dict) or 'artifact' not in execution:
            evidence['error']='No original candidate artifact was returned.'
            return {'outcome':'unknown','score':None,'source':'executable','evidence':[evidence]}
        artifact=execution['artifact']
        try:text=artifact if isinstance(artifact,str) else json.dumps(artifact,ensure_ascii=False,allow_nan=False)
        except (ValueError,TypeError) as exc:
            evidence['error']='Candidate is not finite JSON: '+str(exc)
            return {'outcome':'unknown','score':None,'source':'executable','evidence':[evidence]}
        evidence['candidate_sha256']=hashlib.sha256(text.encode('utf-8')).hexdigest()
        try:
            with tempfile.TemporaryDirectory(prefix='gdpevo-official-score-') as temporary:
                candidate=Path(temporary)/'candidate.json';candidate.write_text(text,encoding='utf-8')
                completed=subprocess.run(['bash',str(script),str(candidate)],cwd=temporary,
                    env={'PATH':os.defpath,'LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'},
                    capture_output=True,text=True,timeout=30,check=False)
                evidence.update(returncode=completed.returncode,stdout=completed.stdout,stderr=completed.stderr)
        except (OSError,subprocess.TimeoutExpired) as exc:
            evidence['error']=type(exc).__name__+': '+str(exc)
            return {'outcome':'unknown','score':None,'source':'executable','evidence':[evidence]}
        try:result=json.loads(completed.stdout)
        except (ValueError,TypeError):result=None
        evidence['result']=result
        score=result.get('score') if isinstance(result,dict) else None
        if type(score) not in (int,float) or not math.isfinite(score) or not 0<=score<=1:
            evidence['error']='Official evaluator did not return a finite normalized score.'
            return {'outcome':'unknown','score':None,'source':'executable','evidence':[evidence]}
        passed=math.isclose(round(score,6),1.0,abs_tol=1e-6)
        return {'outcome':'pass' if passed else 'fail','score':score,'source':'executable','evidence':[evidence],
                'reason':'Official weighted field-group exact match; original score and per-point evidence retained.'}
