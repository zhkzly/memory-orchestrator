"""Serial official licenses. This runner never restores or mutates targets."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys

directory=Path(__file__).parent
rows=json.loads((directory/'C-mutations.json').read_text())
evidence=[]
for row in rows:
    target=Path(row['target']);before=hashlib.sha256(target.read_bytes()).hexdigest()
    tests=row['tests']+' >> '+shlex.quote(str(directory/('C-mutant-'+row['name']+'-tests.txt')))+' 2>&1'
    command=['python3','/home/kelong/ai-workbench/tools/mutation_license.py','--tests',tests,
             '--target',row['target'],'--mutate',shlex.join(['python3',str(directory/'C-mutate.py'),row['name']])]
    result=subprocess.run(command,capture_output=True,text=True)
    after=hashlib.sha256(target.read_bytes()).hexdigest()
    evidence.append({**row,'command':command,'before_sha256':before,'after_sha256':after,
                     'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
    (directory/'C-mutation-results.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
    print(row['name'],result.returncode,before==after,result.stdout.strip(),flush=True)
    if before!=after or result.returncode:
        sys.exit(1)
