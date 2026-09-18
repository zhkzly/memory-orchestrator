"""Bounded concurrency audit; no model/network calls, only scripted JSON."""
import copy
import json
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from memory_orchestrator.evidence import index_episodes, build_packet
from memory_orchestrator.learning import learn
from memory_orchestrator.model import StructuredModel
from memory_orchestrator.sampling import sample_tasks
from memory_orchestrator.schemas import DomainError
from memory_orchestrator.store import Store
from test_memory_evidence import EXAMPLES
from test_memory_learning import policy
from test_memory_model import FakeCall, response, limits as model_limits


with tempfile.TemporaryDirectory(prefix="memory-open-group-", dir="/tmp") as directory:
    store = Store(directory)
    blocked, unblock = threading.Event(), threading.Event()
    project = "demo-project"
    tasks = [{"project_id": project, "task_id": "csv", "revision": "csv@1",
              "description": "Preserve a CSV identifier", "input": "001", "criteria": {"expected": "001"}}]

    def execute(request, snapshot, case):
        if request["repeat_index"] == 1:
            blocked.set()
            if not unblock.wait(timeout=10):
                raise TimeoutError("Audit barrier timed out; released by bounded execution")
        return {"artifact": case["task"]["input"]}

    def evaluate(request, execution, case):
        passed = execution["artifact"] == case["criteria"]["expected"]
        return {"outcome": "pass" if passed else "fail", "score": int(passed), "source": "executable",
                "evidence": [{"actual": execution["artifact"], "expected": case["criteria"]["expected"]}]}

    sampling_policy = {"repeat_count": 2, "max_parallel": 2, "purpose": "learning",
                       "update_mode": "frozen_microbatch", "protocol_id": "audit-group/v1",
                       "executor": {"id": "local-csv/v1", "config": {}}}
    context_policy = {"max_roots": 2, "max_context_chars": 5000, "relation_weight": 0.0}
    with ThreadPoolExecutor(max_workers=1) as outer:
        future = outer.submit(sample_tasks, store, tasks, execute, evaluate,
                              policy=sampling_policy, context_policy=context_policy)
        try:
            assert blocked.wait(timeout=5), "second attempt never reached the barrier"
            deadline = time.monotonic() + 5
            while not store.list("runs", project_id=project) and time.monotonic() < deadline:
                time.sleep(0.01)
            runs = store.list("runs", project_id=project)
            assert len(runs) == 1, f"expected one finished run, got {len(runs)}"
            episode = next(ep for ep in store.list("episodes", project_id=project)
                           if ep["source"]["reference"] == runs[0]["run_id"])
            group = store.get("run_groups", runs[0]["group_id"])
            before = {"planned_slots": len(group["slots"]), "stored_runs": len(runs),
                      "receipt_count": len(store.list("group_receipts", project_id=project)),
                      "experience_count": len(store.list("experiences", project_id=project)),
                      "sampling_finished": future.done()}
            contexts = {episode["context_ref"]: store.get("contexts", episode["context_ref"])}
            packet = build_packet(index_episodes([episode], feedback=store.feedback_for(episode["episode_id"]),
                                                  contexts=contexts), limits=policy()["packet"])
            ref = next(f["ref_id"] for f in packet["fragments"] if f["event_id"] == "result")
            experience = copy.deepcopy(EXAMPLES["experience"])
            experience.update(title="Preserve the observed identifier", conditions=["CSV identifier task"],
                observed_facts=[{"claim": "The first run returned identifier 001", "evidence_refs": [ref]}],
                supporting_refs=[ref], counterevidence_refs=[], boundary_refs=[],
                alternatives=["The second scheduled run is unfinished"], unknowns=["Repeat stability unknown"])
            extraction = {"status": "completed", "experiences": [experience], "read_requests": [],
                          "missing_evidence": [], "reason": "Constructed timing probe"}
            diagnosis = copy.deepcopy(EXAMPLES["diagnosis"])
            diagnosis.update(route="external_issue", targets=[], hypotheses=[], evidence_refs=[ref])
            scripted = FakeCall([response(extraction), response(diagnosis)])
            model = StructuredModel(scripted, limits=model_limits(max_calls=8))
            try:
                result = learn(store, [episode["episode_id"]], model, policy=policy())
                learning_status, error = result["status"], None
            except DomainError as exc:
                learning_status, error = "rejected", exc.code
            during = {"actual_model_calls": 0, "scripted_generate_calls": len(scripted.calls),
                      "learning_status": learning_status, "learning_error": error,
                      "experience_count": len(store.list("experiences", project_id=project)),
                      "receipt_count": len(store.list("group_receipts", project_id=project)),
                      "sampling_finished": future.done()}
        finally:
            unblock.set()
        completed = future.result(timeout=15)
    after = {"stored_runs": len(store.list("runs", project_id=project)),
             "receipt_count": len(store.list("group_receipts", project_id=project)),
             "sampling_finished": future.done()}
    print(json.dumps({"before_learning": before, "during_open_group": during,
                      "after_cleanup": after,
                      "reproduced": during["experience_count"] > before["experience_count"]
                        and during["receipt_count"] == 0 and not during["sampling_finished"]}, indent=2))
