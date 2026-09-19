"""Task-scoped official mutation recheck; restores each target byte-for-byte."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / 'pyproject.toml').is_file())
OUT = Path(__file__).parent
LEARNING = 'src/memory_orchestrator/learning.py'
TEST_PREFIX = 'test_memory_trajectory_learning.TrajectoryLearningTests.'
CASES = [
    ('exact_quote', LEARNING, 'if offset < 0:', 'if False:', 'test_unread_or_paraphrased_quotes_are_rejected_together'),
    ('provided_source', LEARNING, 'source = supplied.get(excerpt["ref_id"])', 'source = next(iter(supplied.values()))', 'test_quote_cannot_borrow_identical_text_from_an_unprovided_reference'),
    ('observation_limit', LEARNING, 'if len(draft["observations"]) > limits["max_observations"]:', 'if False:', 'test_all_local_count_and_quote_limits_are_enforced_with_field_paths'),
    ('quote_limit', LEARNING, 'or len(quote) > limits["max_quote_chars"]', 'or False', 'test_all_local_count_and_quote_limits_are_enforced_with_field_paths'),
    ('raw_not_summary', LEARNING, '"ref_id": ref, "text": quote,', '"ref_id": ref, "text": observation["text"],', 'test_local_excerpts_are_original_byte_ranges_not_relabelled_summaries'),
    ('utf8_range', LEARNING, 'len(source["text"][:offset].encode("utf-8"))', 'offset', 'test_local_excerpts_are_original_byte_ranges_not_relabelled_summaries'),
    ('assistant_claim', LEARNING, 'observation["kind"] != "intention"', 'False', 'test_visible_assistant_claim_is_not_retyped_as_a_verified_outcome'),
    ('call_pair', LEARNING, 'return list(result.values())', 'return quotes', 'test_long_real_trace_is_summarized_before_extraction'),
    ('direct_catalog', LEARNING, 'if not anchors_only:', 'if False:', 'test_short_projected_trace_keeps_continuation_catalog_without_summary_calls'),
    ('partial_progress', LEARNING, '            error_record(exc, "summarize_trace_v1")', '            error_record(exc, "summarize_trace_v1")\n            raise', 'test_later_local_failure_keeps_prior_summary_and_actual_failed_usage'),
    ('abstain_state', LEARNING, '"trajectory_no_summary") else "error"', '"unreachable_state") else "error"', 'test_all_local_abstentions_are_not_an_error_or_a_skill'),
    ('disabled_path', LEARNING, 'if processing is None:', 'if False:', 'test_null_strategy_cannot_disable_the_unified_input_path'),
    ('preflight_extract', LEARNING, 'if not extraction_preview["fits"]:', 'if False:', 'test_impossible_extraction_budget_does_not_spend_on_local_summaries'),
    ('unified_consumer', LEARNING,
     'packet = _learning_packet(store, index, episodes, related, policy, model, call, result, error_record)',
     'packet = build_packet(index, limits=policy["packet"])', 'test_long_real_trace_is_summarized_before_extraction'),
    ('reported_partial', 'src/memory_orchestrator/report.py', "'trajectory_processing': [", "'trajectory_processing_omitted': [", 'test_project_report_exposes_partial_analysis_without_counting_reserves_as_usage'),
    ('enabled_example', 'examples/gdpevo_pilot/run.py', "'token_budget': {", "'disabled_token_budget': {", 'test_pilot_profile_enables_budgeted_processing_of_its_real_trace'),
    ('dependency_consumer', LEARNING, 'dependency_limits=policy.get("dependency_lookup")',
     'dependency_limits=None', 'test_dependency_lookup_reaches_actual_local_and_extraction_inputs'),
]


def main():
    rows = []
    for label, target, old, new, name in CASES:
        path = ROOT / target
        original = path.read_bytes()
        assert old in original.decode('utf-8'), (label, 'mutation seam missing')
        before = hashlib.sha256(original).hexdigest()
        code = f'from pathlib import Path; p=Path({target!r}); s=p.read_text(); old={old!r}; assert old in s; p.write_text(s.replace(old,{new!r},1))'
        test = 'PYTHONPATH=src:tests .venv/bin/python -m unittest ' + TEST_PREFIX + name + ' -v'
        command = [sys.executable, '/home/kelong/ai-workbench/tools/mutation_license.py',
                   '--tests', test, '--target', target, '--mutate', 'python3 -c ' + shlex.quote(code)]
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        after = hashlib.sha256(path.read_bytes()).hexdigest()
        row = {'label': label, 'target': target, 'test': test, 'command': command,
               'exit_code': completed.returncode, 'before_sha256': before, 'after_sha256': after,
               'stdout': completed.stdout, 'stderr': completed.stderr}
        rows.append(row)
        (OUT / 'learning-mutation-results.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
        print(label, completed.returncode, 'restored=' + str(before == after), flush=True)
        if completed.returncode or before != after:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
