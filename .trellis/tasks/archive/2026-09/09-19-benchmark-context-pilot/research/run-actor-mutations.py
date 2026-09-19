"""Coordinator-scheduled actor-only official mutation evidence capture."""
from pathlib import Path
import hashlib
import json
import shlex
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
TARGET = ROOT / 'examples/gdpevo_pilot/actor.py'
TESTS = {
    'public_file_scope': 'test_gold_unknown_tool_and_judge_are_rejected_without_dispatch',
    'business_get_scope': 'test_gold_unknown_tool_and_judge_are_rejected_without_dispatch',
    'tool_id_pairing': 'test_real_public_prompt_and_parallel_tool_pairs_reach_the_next_sdk_call',
    'input_budget': 'test_complete_payload_budget_blocks_dispatch_without_removing_context',
    'tool_budget': 'test_tool_batch_over_budget_executes_none_and_keeps_attempts',
    'asset_read_consumption': 'test_only_an_actual_selected_asset_read_records_consumption',
    'selected_asset_scope': 'test_only_an_actual_selected_asset_read_records_consumption',
    'length_termination': 'test_timeout_length_and_malformed_sdk_envelope_keep_terminal_state',
    'stop_raw_artifact': 'test_normal_stop_preserves_non_json_without_host_repair',
    'host_state_visible': 'test_recorded_six_round_pattern_discloses_remaining_budget_without_inventing_answer',
    'remaining_call_count': 'test_recorded_five_round_submission_keeps_one_unused_model_call_visible',
    'no_stale_state_history': 'test_recorded_six_round_pattern_discloses_remaining_budget_without_inventing_answer',
    'host_state_input_budget': 'test_dynamic_host_state_is_included_in_the_complete_input_budget',
    'sdk_id_type_first': 'test_malformed_list_tool_id_keeps_partial_trace_without_dispatch',
}

def sha(): return hashlib.sha256(TARGET.read_bytes()).hexdigest()

if __name__ == '__main__':
    if sys.argv[1:] != ['--exclusive-window-granted']:
        raise SystemExit('Requires an explicit coordinator-granted exclusive Actor window')
    baseline = sha()
    folder = HERE / 'actor-mutation-evidence'; folder.mkdir(exist_ok=True)
    results = []
    for name, test in TESTS.items():
        tests = 'PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:.:tests .venv/bin/python -m unittest test_gdpevo_actor.ActorTests.' + test + ' -v'
        mutate = 'python3 ' + shlex.quote(str(HERE / 'actor-mutations.py')) + ' ' + shlex.quote(name)
        command = ['python3', '/home/kelong/ai-workbench/tools/mutation_license.py',
                   '--target', str(TARGET), '--tests', tests, '--mutate', mutate]
        returned = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        (folder / (name + '.log')).write_text(returned.stdout)
        row = {'case': name, 'tests': tests, 'mutate': mutate, 'command': command,
               'exit_code': returned.returncode, 'restored_sha256': sha(), 'restored': sha() == baseline}
        results.append(row)
        (folder / 'results.json').write_text(json.dumps({'target': str(TARGET), 'baseline_sha256': baseline, 'results': results}, indent=2) + '\n')
        print(json.dumps({k: row[k] for k in ('case', 'exit_code', 'restored')}), flush=True)
        if returned.returncode or not row['restored']:
            raise SystemExit('Stop: license failed or restoration differs; inspect the raw log')
    print(json.dumps({'licenses': len(results), 'all_restored': sha() == baseline, 'sha256': sha()}), flush=True)
