"""Read-only repo audit; all mutable Stores live in auto-cleaned temp dirs."""
import json
import subprocess
import tempfile
from unittest.mock import patch

from test_memory_evaluation import MemoryEvaluationTests, execute_csv
from memory_orchestrator.release import publish
from memory_orchestrator.report import report
from memory_orchestrator.sampling import sample_tasks
from memory_orchestrator.store import Store
from memory_orchestrator.schemas import DomainError


results = {"head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
           "evidence_kind": "constructed temporary-Store probes, not benchmark results"}


def fixture():
    obj = MemoryEvaluationTests()
    obj.setUp()
    return obj


f = fixture()
try:
    def cancelled_candidate(request, snapshot, case):
        output = execute_csv(request, snapshot, case)
        if request["arm"] == "candidate":
            output["execution_status"] = "cancelled"
        return output
    compared = f.compare(execute_fn=cancelled_candidate)
    validation = f.validation(compared)
    released = publish(f.store, f.project, f.candidate["proposal_id"], validation["validation_id"],
                       compared["selection_id"], expected_active_digest=f.active["snapshot_id"],
                       expected_generation=0)
    results["noncompleted_candidate_is_published"] = {
        "validation_status": validation["status"],
        "reported_candidate_execution_statuses": [x["returned"]["execution_status"]
            for x in f.store.list("evaluation_returns", project_id=f.project)
            if x["stage"] == "execute" and x["request"]["arm"] == "candidate"],
        "candidate_outcomes": [x["outcome"] for x in validation["results"]
            if x["snapshot_digest"] == f.candidate["candidate_digest"]],
        "new_generation": released["new_generation"],
    }
finally:
    f.doCleanups()

f = fixture()
try:
    original_put = f.store.put
    def stop_before_validation(kind, *args, **kwargs):
        if kind == "validations":
            raise DomainError("audit_interruption", "Stop after results persist, before validation persists")
        return original_put(kind, *args, **kwargs)
    caught = None
    with patch.object(f.store, "put", side_effect=stop_before_validation):
        try:
            f.compare()
        except DomainError as exc:
            caught = exc.code
    stored = f.store.list("evaluation_results")  # Project is joined through plan/request IDs.
    output = report(f.store, f.project)
    results["persisted_results_ignored_without_validation"] = {
        "interruption": caught, "stored_result_count": len(stored),
        "stored_outcomes": {k: sum(r["outcome"] == k for r in stored) for k in ("pass", "fail", "unknown")},
        "report_outcomes": output["outcomes"],
        "reported_unaccounted_requests": output["usage"]["unaccounted_evaluation_requests"],
        "reported_comparison_results": output["comparisons"][0]["recorded_results"],
    }
finally:
    f.doCleanups()

with tempfile.TemporaryDirectory() as directory:
    store = Store(directory)
    tasks = [{"project_id": "p", "task_id": "task", "revision": "1", "description": "local task"}]
    policy = {"repeat_count": 3, "max_parallel": 1, "purpose": "learning", "update_mode": "task_barrier",
              "protocol_id": "audit/v1", "executor": {"id": "audit-executor", "config": {}}}
    def execute(*args):
        return {"artifact": "output"}
    def evaluate(request, *args):
        score = int(request["repeat_index"] != 1)
        return {"outcome": "pass" if score else "fail", "score": score,
                "source": "executable", "evidence": [{"checked": True}]}
    sample_tasks(store, tasks, execute, evaluate, policy=policy,
                 context_policy={"max_roots": 0, "max_context_chars": 0, "relation_weight": 0})
    feedback = store.list("feedback", "p")
    output = report(store, "p")
    results["sampling_quality_missing_from_report"] = {
        "stored_feedback_outcomes": {k: sum(r["outcome"] == k for r in feedback) for k in ("pass", "fail", "unknown")},
        "sampling_slots": output["sampling_slots"], "report_outcomes": output["outcomes"],
        "observed_success_rate": output["observed_success_rate"],
        "comparisons": len(output["comparisons"]),
    }

f = fixture()
try:
    f.compare()
    f.compare()
    output = report(f.store, f.project)
    results["validation_attempts_labelled_candidate_count"] = {
        "unique_stored_candidates": len(f.store.list("candidates", f.project)),
        "validation_attempts": len(f.store.list("validations", f.project)),
        "reported_candidate_counts": output["candidate_counts"],
    }
finally:
    f.doCleanups()

print(json.dumps(results, ensure_ascii=False, indent=2))
