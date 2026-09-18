"""Concrete contract violations, applied only by the official snapshot/restore tool."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = next(path for path in Path(__file__).resolve().parents if (path / '.trellis').is_dir() and (path / 'src/memory_orchestrator').is_dir())
HERE = Path(__file__).resolve().parent
CASES = {
    'fact_relevance': ('context.py',
        "return (float(overlap), 'lexical_task_overlap') if overlap else (None, 'task_relevance')",
        "return 1.0, 'incorrect_unconditional_fact'", 2,
        'test_memory_completion.CompletionConsumers.test_current_task_filters_unrelated_project_facts_before_budget'),
    'relation_task_scope': ('context.py', "if scope != task.get('task_id'):", 'if False:', 1,
        'test_memory_completion.CompletionConsumers.test_co_use_from_another_task_or_revision_does_not_change_selection'),
    'local_time_double_charge': ('telemetry.py', 'local = elapsed - meter.delegated', 'local = elapsed', 1,
        'test_memory_telemetry.TelemetryTests.test_local_time_excludes_delegated_calls_and_deduplicates_price'),
    'unreturned_cost': ('report.py', 'if unfinished or missing_slots or unreturned_attempts or unfinished_learning:',
        'if unfinished or missing_slots or unfinished_learning:', 1,
        'test_memory_completion.CompletionConsumers.test_a_later_priced_callback_does_not_erase_an_unreturned_attempt'),
    'unfinished_model_cost': ('report.py', 'if unfinished or missing_slots or unreturned_attempts or unfinished_learning:',
        'if unfinished or missing_slots or unreturned_attempts:', 1,
        'test_memory_completion.CompletionConsumers.test_interrupted_model_learning_keeps_reported_costs_incomplete'),
    'frozen_config_consumer': ('experiments.py',
        'sampling_policy, context_policy, learning_policy, comparison_protocol, verification, seed = deepcopy(',
        'sampling_policy, context_policy, learning_policy, comparison_protocol, verification, seed = (', 1,
        'test_memory_experiments.ExperimentTests.test_retained_caller_config_cannot_change_frozen_arm_execution'),
    'model_reported_fee': ('model.py', 'entry[key] = fee[key]', 'entry[key] = None', 1,
        'test_memory_model.ModelTests.test_transport_fee_metadata_survives_the_structured_call'),
    'sdk_reported_fee': ('model.py',
        '**{key: usage[key] for key in ("monetary_cost", "currency", "price_version") if key in usage}', '**{}', 1,
        'test_memory_model.ModelTests.test_sdk_preserves_explicit_fee_without_pricing_by_guess'),
    'frozen_arm': ('experiments.py', "live = mode != 'frozen'", 'live = True', 1,
        'test_memory_experiments.ExperimentTests.test_real_same_core_runs_all_modes_with_frozen_final_and_equal_budgets'),
    'per_arm_budget': ('experiments.py', 'if arm_cycles >=', 'if cycles >=', 1,
        'test_memory_experiments.ExperimentTests.test_real_same_core_runs_all_modes_with_frozen_final_and_equal_budgets'),
    'final_source_overlap': ('experiments.py', '_require(not any(row[key] for row in overlaps.values() for key in denied),',
        '_require(True or not any(row[key] for row in overlaps.values() for key in denied),', 1,
        'test_memory_experiments.ExperimentTests.test_split_audit_rejects_source_and_content_leakage_without_claiming_unknown_provenance'),
    'history_generation': ('report.py', "(r['new_generation'], r['new_digest'], r['kind'], r['release_id']) for r in releases",
        "(r['new_generation'], r['new_digest'], r['kind'], r['release_id']) for r in []", 1,
        'test_memory_completion.CompletionConsumers.test_two_actual_releases_and_rollback_reach_longitudinal_report'),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == '__main__':
    if sys.argv[1] == 'mutate':
        name, before, after, count, test = CASES[sys.argv[2]]
        path = ROOT / 'src/memory_orchestrator' / name
        source = path.read_text()
        assert source.count(before) == count, (name, before, source.count(before))
        path.write_text(source.replace(before, after))
    elif sys.argv[1:] == ['--exclusive-window-granted']:
        directory = HERE / 'root-mutation-evidence'
        directory.mkdir(exist_ok=True)
        hashes = {name: sha(ROOT / 'src/memory_orchestrator' / name) for name, *_ in CASES.values()}
        results = []
        for identifier, (name, before, after, count, test) in CASES.items():
            target = ROOT / 'src/memory_orchestrator' / name
            tests = 'PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest ' + shlex.quote(test) + ' -v'
            mutate = 'python3 ' + shlex.quote(str(Path(__file__))) + ' mutate ' + shlex.quote(identifier)
            command = ['python3', '/home/kelong/ai-workbench/tools/mutation_license.py',
                       '--tests', tests, '--target', str(target), '--mutate', mutate]
            run = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            (directory / (identifier + '.log')).write_text(run.stdout)
            result = {'id': identifier, 'target': name, 'command': command, 'exit_code': run.returncode,
                      'restored': sha(target) == hashes[name]}
            results.append(result)
            (directory / 'results.json').write_text(json.dumps({'source_hashes': hashes, 'results': results}, indent=2) + '\n')
            print(json.dumps({k: result[k] for k in ('id', 'exit_code', 'restored')}), flush=True)
            if run.returncode != 0 or not result['restored']:
                raise SystemExit('Stopped; inspect the original official tool result before continuing.')
    else:
        raise SystemExit('An exclusive mutation window is required.')
