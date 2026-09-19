"""Dependency handoff checks, using only the official mutation runner."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).parent
TARGET = Path('src/memory_orchestrator/evidence.py')
CASES = [
    ('source_handoff', 'allowed = required | support(scope, members) | neighbor_refs',
     'allowed = required | support(scope, members)', 'test_selected_span_retrieves_its_resource_producer_under_dependency_budget'),
    ('global_balance', "remaining = dependency_limits['max_events'] - len(dependency_charged)",
     "dependency_charged.clear()\n            remaining = dependency_limits['max_events'] - len(dependency_charged)",
     'test_dependency_new_events_share_one_plan_balance_and_keep_chain_depth'),
    ('depth_ceiling', "_dependencies(index, sorted(required), {'max_hops': dependency_limits['max_hops'],",
     "_dependencies(index, sorted(required), {'max_hops': 999,", 'test_dependency_depth_limit_controls_second_hop_call_context'),
    ('known_ref_reuse', "'max_events': remaining + len(known)", "'max_events': remaining",
     'test_dependency_already_counted_producer_is_reused_without_new_charge'),
    ('observed_scope', "source_scope = {key: source[key] for key in ('episode_id', 'task_id', 'goal_id', 'task_revision')}",
     "source_scope = {key: scope[key] for key in ('episode_id', 'task_id', 'goal_id', 'task_revision')}",
     'test_dependency_other_revision_and_resource_version_remains_candidate_context'),
    ('source_versions', "'resources': copy.deepcopy(source.get('resources', []))", "'resources': []",
     'test_dependency_other_revision_and_resource_version_remains_candidate_context'),
    ('missing_support_gap', "dependency_gaps.append('dependency_packet_budget')", 'pass',
     'test_dependency_that_cannot_fit_has_an_explicit_gap'),
    ('parent_path', 'if record["parent_event_id"]:\n                parent = _parent_base(index, record)',
     'if False:\n                parent = _parent_base(index, record)',
     'test_dependency_declared_parent_is_selected_without_a_resource_match'),
]


def main():
    results = []
    for name, old, new, test in CASES:
        before = hashlib.sha256(TARGET.read_bytes()).hexdigest()
        mutation = (f'from pathlib import Path; p=Path({str(TARGET)!r}); s=p.read_text(); '
                    f'old={old!r}; assert s.count(old)==1,s.count(old); p.write_text(s.replace(old,{new!r},1))')
        command = ['python3', '/home/kelong/ai-workbench/tools/mutation_license.py',
            '--tests', 'PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest '
                       + 'test_memory_trajectory.TrajectoryTests.' + test + ' -v',
            '--target', str(TARGET), '--mutate', 'python3 -c ' + shlex.quote(mutation)]
        result = subprocess.run(command, capture_output=True, text=True)
        after = hashlib.sha256(TARGET.read_bytes()).hexdigest()
        (HERE / f'dependency-mutation-{name}.txt').write_text(result.stdout + result.stderr)
        results.append({'name': name, 'command': command, 'exit_code': result.returncode,
                        'before': before, 'after': after, 'exact_restore': before == after})
        (HERE / 'dependency-mutation-results.json').write_text(json.dumps(results, indent=2) + '\n')
        print(name, result.returncode, 'exact_restore=', before == after, flush=True)
        if result.returncode or before != after: raise SystemExit(result.returncode or 99)


if __name__ == '__main__': main()
