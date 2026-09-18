"""Run only during the root-granted exclusive mutation window; save raw evidence."""
from pathlib import Path
import hashlib
import json
import shlex
import subprocess
import sys

ROOT = next(path for path in Path(__file__).resolve().parents if (path / '.trellis').is_dir() and (path / 'src/memory_orchestrator').is_dir())
HERE = Path(__file__).resolve().parent
CASES = [
    ("trace_cold_hash", "trace.py", "test_memory_trace.TraceTests.test_cold_index_rejects_changed_raw_bytes_before_any_record_query"),
    ("trace_batch_cap", "trace.py", "test_memory_trace.TraceTests.test_resume_reopen_and_exact_multibyte_ranges_without_whole_file_text_load"),
    ("trace_byte_range", "trace.py", "test_memory_trace.TraceTests.test_resume_reopen_and_exact_multibyte_ranges_without_whole_file_text_load"),
    ("trace_hot_identity", "trace.py", "test_memory_trace.TraceTests.test_archived_source_tamper_invalidates_existing_reader"),
    ("goal_user_anchor", "goals.py", "test_memory_goals.GoalTests.test_agent_instruction_is_not_a_user_anchor_even_if_its_text_says_switch"),
    ("goal_future_window", "goals.py", "test_memory_goals.GoalTests.test_switch_resume_uses_prior_grounded_catalog_and_never_rewrites_raw"),
    ("maintenance_commit", "maintenance.py", "test_memory_maintenance.MaintenanceTests.test_uncommitted_relation_has_no_retrieval_effect"),
    ("maintenance_conflict", "maintenance.py", "test_memory_maintenance.MaintenanceTests.test_transitive_duplicates_cannot_hide_an_unresolved_contradiction"),
    ("necessity_noop", "learning.py", "test_memory_learning.LearningTests.test_necessity_noop_stops_proposal_and_persists_decision"),
    ("necessity_add", "learning.py", "test_memory_learning.LearningTests.test_add_denied_by_necessity_is_repaired_before_candidate_application"),
    ("failure_ranking", "learning.py", "test_memory_learning.LearningTests.test_failure_signature_beats_unrelated_lexical_match"),
    ("maintenance_consumer", "learning.py", "test_memory_learning.LearningTests.test_semantic_maintenance_runs_in_learn_and_next_retrieval_folds_real_records"),
    ("archive_parent", "learning.py", "test_memory_trace.TraceTests.test_zero_dependency_body_budget_still_indexes_transitive_source_eligibility"),
    ("derived_projection", "evidence.py", "test_memory_learning.LearningTests.test_missing_goals_reach_real_extraction_as_sidecar_not_observed_identity"),
    ("resource_candidate", "evidence.py", "test_memory_trace.TraceTests.test_file_dependency_is_retrieved_as_candidate_not_claimed_causality"),
    ("check_reference", "learning.py", "test_memory_learning.LearningTests.test_invented_check_reference_is_repaired_at_diagnosis_before_proposal"),
    ("fee_amount", "learning.py", "test_memory_learning.LearningTests.test_outer_transport_price_survives_actual_learn_and_call_usage_report"),
    ("fee_currency", "learning.py", "test_memory_learning.LearningTests.test_outer_transport_price_survives_actual_learn_and_call_usage_report"),
    ("fee_price_version", "learning.py", "test_memory_learning.LearningTests.test_outer_transport_price_survives_actual_learn_and_call_usage_report"),
    ("interrupted_wait", "learning.py", "test_memory_learning.LearningTests.test_interrupted_provider_wait_is_not_charged_as_local_maintenance"),
]


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    if sys.argv[1:] != ["--exclusive-window-granted"]:
        raise SystemExit("Root must grant an exclusive Python mutation window first.")
    paths = {name: ROOT / "src/memory_orchestrator" / name for _, name, _ in CASES}
    baseline = {name: sha(path) for name, path in paths.items()}
    directory = HERE / "B-mutation-evidence"; directory.mkdir(exist_ok=True)
    results = []
    for case, name, test in CASES:
        tests = "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest " + shlex.quote(test) + " -v"
        mutate = "python3 " + shlex.quote(str(HERE / "B-mutations.py")) + " " + shlex.quote(case)
        command = ["python3", "/home/kelong/ai-workbench/tools/mutation_license.py", "--tests", tests,
                   "--target", str(paths[name]), "--mutate", mutate]
        finished = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        (directory / (case + ".log")).write_text(finished.stdout)
        result = {"case": case, "target": name, "tests": tests, "mutate": mutate, "command": command,
                  "exit_code": finished.returncode, "restored": sha(paths[name]) == baseline[name]}
        results.append(result)
        (directory / "results.json").write_text(json.dumps({"source_hashes": baseline, "results": results}, indent=2) + "\n")
        print(json.dumps({k: result[k] for k in ("case", "exit_code", "restored")}), flush=True)
        if finished.returncode or not result["restored"]:
            raise SystemExit("Stop after an unsuccessful license; inspect the saved raw log.")
    print(json.dumps({"licenses": len(results), "all_files_restored": all(sha(path) == baseline[name] for name, path in paths.items())}), flush=True)
