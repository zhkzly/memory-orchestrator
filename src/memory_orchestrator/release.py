"""N10 is the only caller of Store's atomic active-pointer commit operation."""
from __future__ import annotations

from .schemas import digest, now_iso, validate
from .evaluation import _require, _check_protocol, _gates, _rank, verify_validation


def _verify_selection(store, selection):
    validate("SelectionRecord", selection)
    frozen = store.get("evaluation_inputs", selection["selection_rule_ref"])
    _require(selection["project_id"] == frozen["project_id"]
             and selection["base_digest"] == frozen["base_digest"]
             and selection["expected_generation"] == frozen["expected_generation"]
             and selection["selection_rule_hash"] == digest(frozen["selection_rule"]),
             "selection_binding", "Selection differs from frozen comparison inputs")
    entries = selection["candidate_validations"]
    candidates = {c["candidate_digest"]: c for c in frozen["candidates"]}
    _require(len(entries) == len(candidates) and {e["candidate_digest"] for e in entries} == set(candidates),
             "selection_coverage", "Selection must account for every frozen candidate")
    validations, plans = [], {}
    protocol = store.get("protocols", frozen["protocol_ref"])["value"]
    cases = store.get("case_sets", frozen["case_set_ref"])["value"]
    _check_protocol(protocol, cases, len(candidates), frozen["max_parallel"])
    _require(protocol["selection_rule"] == frozen["selection_rule"], "selection_binding", "Selection rule changed")
    for entry in entries:
        val = store.get("validations", entry["validation_ref"])
        plan, _, _ = verify_validation(store, val)
        _require(val["validation_id"] == entry["validation_ref"] and val["candidate_digest"] == entry["candidate_digest"]
                 and val["status"] == entry["status"] and val["project_id"] == frozen["project_id"]
                 and val["base_digest"] == frozen["base_digest"]
                 and val["expected_active_generation"] == frozen["expected_generation"]
                 and plan["protocol_ref"] == frozen["protocol_ref"] and plan["case_set_ref"] == frozen["case_set_ref"],
                 "selection_binding", "Candidate validation does not belong to this comparison")
        validations.append(val)
        plans[plan["plan_id"]] = plan
    _require(len(plans) == len(frozen["plan_ids"]) and set(plans) == set(frozen["plan_ids"]),
             "selection_coverage", "Comparison plans missing or repeated")
    all_results = [r for v in validations for r in v["results"]]
    planned = sum(len(p["requests"]) for p in plans.values())
    for val in validations:
        actual = val["gate_results"]
        _require(len(actual) == len(protocol["required_gates"])
                 and {g["gate"] for g in actual} == set(protocol["required_gates"]),
                 "gate_coverage", "Required gates missing or duplicated")
        gates, status, _ = _gates(store, plans[val["plan_id"]], val["results"], cases, protocol, planned, all_results)
        _require(val["status"] == status and {g["gate"]:g["passed"] for g in actual} == {g["gate"]:g["passed"] for g in gates},
                 "gate_result", "Recorded gates do not match stored evidence")
    ranked = _rank(store, validations, plans, cases)
    _require(bool(ranked) and selection["decision"] == "selected"
             and selection["selected_candidate_digest"] == ranked[0][3]
             and selection["selected_validation_ref"] == ranked[0][4],
             "selection_mismatch", "Publication must use the candidate selected by the frozen rule")
    return frozen


def _record(store, identity):
    release_id = "release_" + digest(identity)
    proposed = {"release_id": release_id, **identity, "status": "published",
                "new_generation": identity["expected_generation"] + 1, "timestamp": now_iso()}
    # Stable retry uses the original timestamp; an orphan still needs an active CAS.
    matches = [r for r in store.list("releases", project_id=identity["project_id"]) if r["release_id"] == release_id]
    if matches:
        proposed = matches[0]
        _require(all(proposed[k] == v for k, v in identity.items()), "release_identity", "Release ID content mismatch")
    validate("ReleaseRecord", proposed)
    return proposed


def publish(store, project_id, candidate_id, validation_id, selection_id, *, expected_active_digest, expected_generation):
    candidate = store.get("candidates", candidate_id)
    validation = store.get("validations", validation_id)
    selection = store.get("selections", selection_id)
    _require(candidate["proposal_id"] == candidate_id and validation["validation_id"] == validation_id
             and selection["selection_id"] == selection_id, "record_identity", "Stored identity mismatch")
    _require(candidate["project_id"] == validation["project_id"] == selection["project_id"] == project_id,
             "project_mismatch", "Publication records belong to different projects")
    _require(candidate["base_digest"] == validation["base_digest"] == selection["base_digest"] == expected_active_digest
             and candidate["expected_generation"] == validation["expected_active_generation"] == selection["expected_generation"] == expected_generation,
             "base_mismatch", "Publication base or generation mismatch")
    _require(validation["status"] == "accepted" and validation["candidate_digest"] == candidate["candidate_digest"]
             and selection["selected_candidate_digest"] == candidate["candidate_digest"]
             and selection["selected_validation_ref"] == validation_id,
             "selection_mismatch", "Only the selected accepted candidate can publish")
    identity = {"project_id": project_id, "expected_active_digest": expected_active_digest,
                "expected_generation": expected_generation, "new_digest": candidate["candidate_digest"],
                "validation_ref": validation_id, "selection_ref": selection_id, "rollback_target_release_ref": None,
                "kind": "promote", "reason": "Publish the candidate chosen by the frozen comparison rule."}
    record = _record(store, identity)
    if any(r["release_id"] == record["release_id"] for r in store.release_history(project_id)):
        return record
    active = store.active(project_id)
    _require(active["snapshot_id"] == expected_active_digest and active["generation"] == expected_generation,
             "stale", "Active changed; rebase/re-evaluation required")
    frozen = _verify_selection(store, selection)
    _require(candidate in frozen["candidates"], "candidate_changed", "Candidate differs from frozen comparison")
    snapshot = store.snapshot(candidate["candidate_digest"])
    _require(snapshot["project_id"] == project_id and snapshot["parent"] == expected_active_digest,
             "candidate_parent", "Candidate project or parent differs")
    return store._commit_release(project_id, expected_active_digest, expected_generation, record)


def rollback(store, project_id, target_release_id, *, expected_active_digest, expected_generation, reason):
    _require(isinstance(reason, str) and bool(reason.strip()), "rollback_reason", "Rollback requires a reason")
    history = store.release_history(project_id)
    target = next((r for r in history if r["release_id"] == target_release_id), None)
    _require(target is not None and target["project_id"] == project_id and target["status"] == "published",
             "rollback_history", "Target must be a committed release in this project")
    snapshot = store.snapshot(target["new_digest"])
    _require(snapshot["project_id"] == project_id, "project_mismatch", "Rollback snapshot belongs elsewhere")
    record = _record(store, {"project_id": project_id, "expected_active_digest": expected_active_digest,
                           "expected_generation": expected_generation, "new_digest": target["new_digest"],
                           "validation_ref": None, "selection_ref": None,
                           "rollback_target_release_ref": target_release_id, "kind": "rollback", "reason": reason})
    return store._commit_release(project_id, expected_active_digest, expected_generation, record)
