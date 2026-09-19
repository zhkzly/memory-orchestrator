"""Official mutation entrypoints for pilot budget recording and scope disclosure."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'src/memory_orchestrator').is_dir())
HERE = Path(__file__).resolve().parent
CASES = {
    'physical_call_budget': ('examples/gdpevo_pilot/sdk.py',
        "len(previous) >= self.config['max_calls'] or", 'False or',
        'test_gdpevo_sdk.LedgerTests.test_actual_call_envelope_is_saved_and_budget_is_shared_after_reopen'),
    'complete_input_budget': ('examples/gdpevo_pilot/sdk.py',
        "len(serialized) + sum(row['input_chars'] for row in previous)", '0',
        'test_gdpevo_sdk.LedgerTests.test_full_real_messages_and_tools_count_before_dispatch'),
    'unknown_usage': ('examples/gdpevo_pilot/sdk.py',
        "if complete else None", 'if True else None',
        'test_gdpevo_sdk.LedgerTests.test_interrupted_and_failed_transports_remain_unknown_attempts'),
    'hidden_reasoning': ('examples/gdpevo_pilot/sdk.py',
        "('role', 'content', 'tool_calls', 'refusal')", "('role', 'content', 'tool_calls', 'refusal', 'reasoning_content')",
        'test_gdpevo_sdk.LedgerTests.test_actual_call_envelope_is_saved_and_budget_is_shared_after_reopen'),
    'diagnosis_scope': ('src/memory_orchestrator/learning.py',
        'diagnosis = call(stage, {\n            "evaluation_scope": policy["evaluation_scope"],', 'diagnosis = call(stage, {',
        'test_gdpevo_prompt_scope.PromptScopeTests.test_diagnosis_gets_scope_before_it_commits_verification_obligations'),
    'obligation_disclosure': ('src/memory_orchestrator/prompts.json', None, None,
        'test_gdpevo_prompt_scope.PromptScopeTests.test_diagnosis_gets_scope_before_it_commits_verification_obligations'),
}


if sys.argv[1] == 'mutate':
    identifier = sys.argv[2]
    name, before, after, test = CASES[identifier]
    target = ROOT / name
    source = target.read_text()
    if identifier == 'obligation_disclosure':
        content = json.loads(source)
        original = content['prompts']['diagnose_v1']['system']
        assert '发布必需' in original
        content['prompts']['diagnose_v1']['system'] = original.replace('发布必需', '未来可选')
        target.write_text(json.dumps(content, ensure_ascii=False, indent=2) + '\n')
    else:
        assert source.count(before) == 1, (identifier, source.count(before))
        target.write_text(source.replace(before, after, 1))
elif sys.argv[1:] == ['--exclusive-window-granted']:
    results = []
    output = HERE / 'root-mutation-evidence'
    output.mkdir(exist_ok=True)
    for identifier, (name, before, after, test) in CASES.items():
        target = ROOT / name
        original_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        tests = 'PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest ' + shlex.quote(test) + ' -v'
        mutate = shlex.join(['python3', str(Path(__file__)), 'mutate', identifier])
        command = ['python3', '/home/kelong/ai-workbench/tools/mutation_license.py', '--tests', tests,
                   '--target', str(target), '--mutate', mutate]
        run = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        restored = hashlib.sha256(target.read_bytes()).hexdigest()
        (output / (identifier + '.log')).write_text(run.stdout)
        result = {'id': identifier, 'command': command, 'before_sha256': original_hash,
                  'after_sha256': restored, 'exit_code': run.returncode, 'restored': restored == original_hash}
        results.append(result)
        (output / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({k: result[k] for k in ('id', 'exit_code', 'restored')}), flush=True)
        if run.returncode or restored != original_hash:
            raise SystemExit('Official license failed; stop and inspect the original output.')
else:
    raise SystemExit('Use only during a root-granted exclusive mutation window.')
