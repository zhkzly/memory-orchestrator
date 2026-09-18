import copy,json,unittest
from pathlib import Path
from memory_orchestrator.schemas import new_id
from memory_orchestrator.evaluation import _summaries
from test_memory_evaluation import MemoryFixture,case_set

class Fixture(MemoryFixture,unittest.TestCase):pass
f=Fixture();f.setUp()
try:
    protected=case_set();protected['cases'][0]['criteria']['codes']=['12','7']
    extra=[]
    for i,codes in enumerate((['0012','0007'],['0018','0005'])):
        row=copy.deepcopy(case_set()['cases'][0]);row['id']='optional-preserve-'+str(i)
        row['task']['csv']='code,amount\n'+codes[0]+',3\n'+codes[1]+',4\n'
        row['criteria']['codes']=codes;extra.append(row)
    checks=[{'check_ref':'check:'+c['id'],'purpose':'target','description':'Check preservation in optional schema',
             'evidence_kind':'task','case_ids':[c['id']],'asset_test_ids':[]} for c in extra]
    candidate={**f.candidate,'proposal_id':new_id('proposal'),'check_plan':[{'purpose':'target','behavior':c['description'],
        'required_evidence':'Independent optional fixture','check_ref':c['check_ref']} for c in checks]}
    f.store.put('candidates',candidate['proposal_id'],candidate);f.candidate=candidate
    result=f.compare(case_set=protected,verification={'id':'trusted-pool','version':'1','checks':checks,'cases':extra})
    val=f.validation(result);plan=f.store.get('evaluation_plans',result['plan_ids'][0])
    actual_cases=f.store.get('case_sets',plan['case_set_ref'])['value']
    output={'status':val['status'],'rows':_summaries(plan,val['results'],actual_cases),
            'required_gates':val['gate_results'],'original_quality_case_ids':[c['id'] for c in protected['cases']],
            'actual_case_ids':[c['id'] for c in actual_cases['cases']]}
    Path('/tmp/memory-c-quality-probe.json').write_text(json.dumps(output,indent=2))
    print(json.dumps(output,indent=2))
finally:f.doCleanups()
