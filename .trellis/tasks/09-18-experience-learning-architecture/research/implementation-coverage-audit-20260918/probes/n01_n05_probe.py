"""Read-only audit reproduction at HEAD 4a71ccf.

Run with the repository's Python environment, PYTHONDONTWRITEBYTECODE=1,
and PYTHONPATH=<repository>/src. All test Store data is created under /tmp.
No models, benchmarks, source changes or mutation checks are performed.
"""
import copy
import json
import tempfile

from memory_orchestrator.store import Store
from memory_orchestrator.sampling import sample_tasks
from memory_orchestrator.schemas import digest, now_iso
from memory_orchestrator.evidence import index_episodes


def policy(n=1):
    return {
        "repeat_count": n, "max_parallel": 1, "purpose": "learning",
        "update_mode": "task_barrier", "protocol_id": "audit/v1",
        "executor": {"id": "audit", "config": {}},
    }


context = {"max_roots": 2, "max_context_chars": 5000, "relation_weight": 0.0}


def task(**extra):
    return {
        "project_id": "p", "task_id": "t", "revision": "v1",
        "description": "audit task", **extra,
    }


with tempfile.TemporaryDirectory(prefix="memory-audit-feedback-", dir="/tmp") as root:
    store = Store(root)
    sampled = sample_tasks(
        store, [task()],
        lambda request, *args: {"artifact": "result-" + str(request["repeat_index"])},
        None, policy=policy(2), context_policy=context,
    )
    ep0, ep1 = sampled["episodes"]
    run0 = store.get("runs", sampled["run_ids"][0])
    run1 = store.get("runs", sampled["run_ids"][1])
    feedback = copy.deepcopy(store.feedback_for(ep0["episode_id"])[0])
    feedback.update(
        check_id="late-wrong-state", run_id=run1["run_id"],
        evaluated_state_digest=run1["artifact_digest"],
        evaluator_status="ok", outcome="pass", score=1, source="external",
        checked_at=now_iso(), binding_status="bound",
    )
    store.add_feedback(feedback)
    saved = store.get("feedback", "late-wrong-state")
    print(json.dumps({
        "probe": "late_feedback_wrong_known_run_and_state",
        "accepted": True,
        "subject_is_first_episode": saved["subject_ref"] == ep0["episode_id"],
        "stored_run_is_other_episode": saved["run_id"] == ep1["source"]["reference"],
        "state_matches_subject_run": saved["evaluated_state_digest"] == run0["artifact_digest"],
        "binding_status": saved["binding_status"],
    }))

with tempfile.TemporaryDirectory(prefix="memory-audit-partial-", dir="/tmp") as root:
    store = Store(root)

    def execute(*args):
        return {
            "execution_status": "timeout", "artifact": None,
            "events": [{
                "event_id": "partial", "kind": "action",
                "text": "PARTIAL_OPERATION_BEFORE_TIMEOUT", "call_id": "c1",
                "task_revision": "v1", "source_role": "tool",
            }],
        }

    sampled = sample_tasks(
        store, [task()], execute, None, policy=policy(), context_policy=context,
    )
    episode = sampled["episodes"][0]
    raw = store.get("executions", sampled["run_ids"][0])
    index = index_episodes(
        [episode],
        contexts={episode["context_ref"]: store.get("contexts", episode["context_ref"])},
    )
    print(json.dumps({
        "probe": "timeout_partial_trace",
        "raw_contains_partial": any(
            event["text"] == "PARTIAL_OPERATION_BEFORE_TIMEOUT"
            for event in raw["output"]["events"]
        ),
        "episode_contains_partial": any(
            "PARTIAL_OPERATION_BEFORE_TIMEOUT" in event["text"]
            for event in episode["events"]
        ),
        "index_contains_partial": any(
            "PARTIAL_OPERATION_BEFORE_TIMEOUT" in record["text"]
            for record in index["records"].values()
        ),
        "gaps": episode["gaps"],
    }, ensure_ascii=False))

with tempfile.TemporaryDirectory(prefix="memory-audit-state-", dir="/tmp") as root:
    store = Store(root)
    expected = digest("expected initial state")
    actual = digest("different state")
    sampled = sample_tasks(
        store, [task(initial_state_digest=expected)],
        lambda *args: {
            "artifact": "ok", "initial_state_digest": actual,
            "environment_instance_id": "different-env",
        },
        None, policy=policy(), context_policy=context,
    )
    plan = store.get("run_groups", sampled["plan_ids"][0])
    run = store.get("runs", sampled["run_ids"][0])
    print(json.dumps({
        "probe": "reported_initial_state_contradicts_plan",
        "state_matches_plan": run["initial_state_digest"] == plan["initial_state_digest"],
        "execution_status": run["execution_status"],
        "capture_gaps": run["capture_gaps"],
        "comparability": run["comparability"],
    }, ensure_ascii=False))
