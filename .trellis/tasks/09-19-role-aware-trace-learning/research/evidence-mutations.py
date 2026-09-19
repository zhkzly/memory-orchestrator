"""Run the prepared evidence guards via the official snapshot/restore tool only.

Root must grant an exclusive mutation window before running this script.
"""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

TARGET = Path('src/memory_orchestrator/evidence.py')
HERE = Path(__file__).parent
CASES = [
    ('user_prefix', "preserve_prefix = learning_role(record) == 'user'", 'preserve_prefix = False',
     'test_user_control_prefix_is_not_displaced_by_quoted_error_material'),
    ('empty_allowlist', 'allowed = None if allowed_refs is None else set(allowed_refs)',
     'allowed = None if not allowed_refs else set(allowed_refs)', 'test_allowed_refs_is_a_strict_boundary_including_empty_set'),
    ('allowed_call_members', "members = [item for item in members if item['base_ref'] in allowed_refs]",
     'members = members', 'test_allowed_refs_is_a_strict_boundary_including_empty_set'),
    ('role_caps', "role = learning_role(row)\n    cap = caps[role]", 'return width\n    cap = 0',
     'test_user_paste_and_visible_analysis_have_distinct_source_caps'),
    ('critical_cap', "cap = max(cap, caps['feedback'])", 'cap = cap', 'test_failure_result_uses_protected_diagnostic_cap'),
    ('call_groups', "groups.setdefault(key, []).append(row)", "groups.setdefault((row['base_ref'],), []).append(row)",
     'test_real_trace_is_covered_by_multiple_bounded_call_groups'),
    ('scope_split', "scope != current_scope or scope['binding_status'] == 'ambiguous'", "scope['binding_status'] == 'ambiguous'",
     'test_goal_revision_chunks_do_not_inherit_final_requirement'),
    ('binding_conflict', 'conflict = any(len(v) > 1 for v in values.values())', 'conflict = False',
     'test_cross_revision_call_is_explicitly_ambiguous'),
    ('unknown_binding', "'unknown' if missing else 'derived'", "'unknown' if False else 'derived'",
     'test_missing_binding_does_not_inherit_episode_final_revision'),
    ('derived_conflict', 'values[key].update(inferred)', 'values[key].add(next(iter(inferred)))',
     'test_conflicting_derived_bindings_are_not_last_write_wins'),
    ('scan_limit', "_trajectory_records(index, limits['max_scan_events'])", '_trajectory_records(index, 100000)',
     'test_scan_and_segment_caps_report_unprocessed_events'),
    ('segment_limit', "while pending and len(segments) < limits['max_segments']:", 'while pending:',
     'test_scan_and_segment_caps_report_unprocessed_events'),
    ('group_limit', "or len(current) >= limits['max_groups_per_segment']", 'or False',
     'test_real_trace_is_covered_by_multiple_bounded_call_groups'),
    ('span_priority', 'queued.sort(key=span_priority)', 'pass',
     'test_late_verifier_failure_is_prioritized_before_early_routine_groups'),
    ('source_order', "packet['fragments'].sort(key=lambda f: (f['episode_id'], f['structure']['source_position'], f['range']['start_byte']))",
     'pass', 'test_real_trace_is_covered_by_multiple_bounded_call_groups'),
    ('repeat_error', 'if not critical and identity in result_hashes:', 'if identity in result_hashes:',
     'test_repeated_results_fold_but_failure_remains_source_evidence'),
    ('body_coverage', "'raw_body_complete': len(full) == total", "'raw_body_complete': True",
     'test_user_paste_and_visible_analysis_have_distinct_source_caps'),
    ('control_only', 'if not rows:\n        # Imported material', 'if False:\n        # Imported material',
     'test_missing_execution_events_still_preserves_supplied_feedback_and_requirement'),
]


def main():
    results = []
    for name, old, new, test in CASES:
        before = hashlib.sha256(TARGET.read_bytes()).hexdigest()
        mutation = (f'from pathlib import Path; p=Path({str(TARGET)!r}); s=p.read_text(); '
                    f'old={old!r}; assert s.count(old)==1, s.count(old); p.write_text(s.replace(old,{new!r},1))')
        command = ['python3', '/home/kelong/ai-workbench/tools/mutation_license.py',
            '--tests', 'PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest '
                       + 'test_memory_trajectory.TrajectoryTests.' + test + ' -v',
            '--target', str(TARGET), '--mutate', 'python3 -c ' + shlex.quote(mutation)]
        result = subprocess.run(command, capture_output=True, text=True)
        after = hashlib.sha256(TARGET.read_bytes()).hexdigest()
        (HERE / f'evidence-mutation-{name}.txt').write_text(result.stdout + result.stderr)
        results.append({'name': name, 'command': command, 'exit_code': result.returncode,
                        'before': before, 'after': after, 'exact_restore': before == after})
        (HERE / 'evidence-mutation-results.json').write_text(json.dumps(results, indent=2) + '\n')
        print(name, result.returncode, 'exact_restore=', before == after, flush=True)
        if result.returncode or before != after:
            raise SystemExit(result.returncode or 99)


if __name__ == '__main__': main()
