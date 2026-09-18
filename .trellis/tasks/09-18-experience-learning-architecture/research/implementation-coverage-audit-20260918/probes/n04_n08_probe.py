"""Read-only HEAD 4a71ccf audit. Writes only stdout and disposable /tmp stores.

Run from the repository root:
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python /tmp/memory-core-audit-n04-n08/probe.py
No SDK/client/network/model calls. The evolution probe uses preconstructed JSON
responses via the existing FakeCall test callable and reports that separately.
"""
import copy
import json
import subprocess
import tempfile

from memory_orchestrator.candidates import apply_candidate
from memory_orchestrator.engine import evolve
from memory_orchestrator.evidence import build_packet, index_episodes
from memory_orchestrator.model import StructuredModel
from memory_orchestrator.store import Store
from test_memory_evidence import episode, csv_episodes, limits
from test_memory_learning import drafts, policy as learning_policy
from test_memory_model import FakeCall, response, limits as model_limits
from test_memory_evaluation import case_set, protocol


def event(identifier, kind, text, call_id):
    return {"event_id": identifier, "kind": kind, "text": text,
            "source_ref": None, "call_id": call_id, "task_revision": None}


def packet_without_random_id(index):
    packet = build_packet(index, limits=limits())
    del packet["packet_id"]
    return packet


output = {"source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
          "actual_model_calls": 0, "network_calls": 0}

first = episode()
first["events"] = [event("a1", "action", "launch process", "c1"),
                   event("a2", "action", "launch process", "c2"),
                   event("r1", "result", "result success", "c1"),
                   event("r2", "result", "result failure", "c2")]
second = copy.deepcopy(first)
second["events"][2]["call_id"] = "c2"
second["events"][3]["call_id"] = "c1"
ia, ib = index_episodes([first]), index_episodes([second])
pa, pb = packet_without_random_id(ia), packet_without_random_id(ib)
assert ia["call_pairs"] != ib["call_pairs"]
assert pa == pb
output["call_metadata_loss"] = {"first_pairs": ia["call_pairs"], "second_pairs": ib["call_pairs"],
    "packets_equal_except_packet_id": pa == pb, "packet_fragment_fields": sorted(pa["fragments"][0])}

first = episode()
first["events"] = [{**event("u1", "instruction", "Continue task", None),
                    "task_revision": "r1", "goal_id": "A", "source_role": "user"},
                   {**event("u2", "instruction", "Continue task", None),
                    "task_revision": "r1", "goal_id": "B", "source_role": "user"}]
second = copy.deepcopy(first)
second["events"][1]["goal_id"] = "A"
ia, ib = index_episodes([first]), index_episodes([second])
pa, pb = packet_without_random_id(ia), packet_without_random_id(ib)
assert ia["goal_transitions"] != ib["goal_transitions"]
assert pa == pb
output["goal_metadata_loss"] = {"first_relations": [x["relation"] for x in ia["goal_transitions"]],
    "second_relations": [x["relation"] for x in ib["goal_transitions"]],
    "packets_equal_except_packet_id": pa == pb}

with tempfile.TemporaryDirectory(prefix="memory-audit-", dir="/tmp") as root:
    store = Store(root)
    episodes = csv_episodes()
    for item in episodes:
        store.add_episode(item)
    extraction, diagnosis, patch = drafts(episodes)
    fake = FakeCall([response(extraction), response(diagnosis), response(patch), response(patch)])
    model = StructuredModel(fake, limits=model_limits(max_calls=8))
    calls = {"execute": 0, "evaluate": 0}

    def execute(*_):
        calls["execute"] += 1
        return {"artifact": None}

    def evaluate(*_):
        calls["evaluate"] += 1
        return {"outcome": "unknown", "score": None, "source": "executable", "evidence": []}

    result = evolve(store, [e["episode_id"] for e in episodes], model,
                    learning_policy=learning_policy(candidate_count=2),
                    case_set=case_set(), protocol=protocol(), execute=execute,
                    evaluate=evaluate, max_parallel=1)
    candidates = [store.get("candidates", cid) for cid in result["learning"]["candidate_ids"]]
    error = store.get("errors", result["error_id"])
    assert len(candidates) == 2
    assert candidates[0]["proposal_id"] != candidates[1]["proposal_id"]
    assert candidates[0]["candidate_digest"] == candidates[1]["candidate_digest"]
    assert result["status"] == "error" and error["code"] == "duplicate_candidate"
    assert calls == {"execute": 0, "evaluate": 0}
    output["duplicate_candidate_evolution"] = {
        "learning_status": result["learning"]["status"],
        "candidate_slots": [s["status"] for s in result["learning"]["candidate_slots"]],
        "proposal_ids_differ": True, "same_candidate_digest": True,
        "engine_status": result["status"], "engine_error_code": error["code"],
        "actual_model_calls": 0, "scripted_generate_calls": len(fake.calls),
        "execute_calls": calls["execute"], "evaluate_calls": calls["evaluate"],
        "active_generation": store.active(episodes[0]["project_id"])["generation"],
    }

print(json.dumps(output, ensure_ascii=False, indent=2))
