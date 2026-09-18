"""N10 is the only caller of Store's atomic active-pointer commit operation."""
from __future__ import annotations

from .schemas import digest, now_iso, validate
from .evaluation import _require, _check_protocol, _gates, _rank, verify_validation, proposal_aliases, criterion_count, comparison_call_budget
from .telemetry import measure_stage


def _frozen_aliases(store, selection):
    frozen = store.get("evaluation_inputs", selection["selection_rule_ref"])
    aliases = proposal_aliases(frozen["candidates"])
    mapping = [{"proposal_id": c["proposal_id"], "candidate_digest": c["candidate_digest"]} for c in frozen["candidates"]]
    _require(frozen.get("proposal_snapshots", mapping) == mapping, "proposal_binding", "Frozen proposal/snapshot mapping changed")
    for candidate in frozen["candidates"]:
        _require(store.get("candidates", candidate["proposal_id"]) == candidate,
                 "candidate_changed", "A frozen proposal no longer matches its stored attempt")
    for entry in selection["candidate_validations"]:
        expected = aliases.get(entry["candidate_digest"])
        actual = entry.get("proposal_ids") if "proposal_snapshots" in frozen else entry.get("proposal_ids", expected)
        _require(expected is not None and actual == expected, "selection_aliases", "Selected snapshot aliases differ from frozen proposal attempts")
    return frozen, aliases


def _verify_selection(store, selection):
    validate("SelectionRecord", selection)
    frozen, aliases = _frozen_aliases(store, selection)
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
    _require(bool(frozen.get('quality_case_set_ref')),'quality_scope','Comparison requires its original frozen quality cases')
    quality_record=store.get('case_sets',frozen['quality_case_set_ref']);quality_cases=quality_record['value']
    _require(quality_record['project_id']==frozen['project_id'] and digest(quality_cases)==frozen['quality_case_set_hash'],
             'quality_scope','Original quality case set changed')
    quality_refs=[c['id'] for c in quality_cases['cases']]
    by_case={c['id']:c for c in cases['cases']}
    _require(all(ref in by_case for ref in quality_refs) and [by_case[ref] for ref in quality_refs]==quality_cases['cases'],
             'quality_scope','Supplemental checks cannot replace original quality cases')
    _check_protocol(protocol,quality_cases,len(candidates),frozen['max_parallel'])
    _check_protocol(protocol, cases, len(candidates), frozen["max_parallel"])
    _require(protocol["selection_rule"] == frozen["selection_rule"], "selection_binding", "Selection rule changed")
    for entry in entries:
        val = store.get("validations", entry["validation_ref"])
        plan, _, _ = verify_validation(store, val)
        _require(plan.get('quality_case_refs')==quality_refs,'quality_scope','Candidate changed the frozen admission objective')
        expected_aliases = aliases[entry["candidate_digest"]]
        actual_aliases = plan.get("proposal_ids") if "proposal_snapshots" in frozen else plan.get("proposal_ids", expected_aliases)
        _require(actual_aliases == expected_aliases, "plan_aliases", "Comparison plan lost or changed proposal aliases")
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
    verification_records={v['plan_id']:store.get('verification_records',v['verification_record_ref']) for v in validations}
    auxiliary_usage=sorted({uid for v in verification_records.values() for uid in v['usage_refs']})
    planned = sum(len(p["requests"]) for p in plans.values())
    for plan in plans.values():
        vp=store.get('verification_plans',plan['verification_plan_ref'])
        _require(vp['materials_ref']==frozen['verification_materials_ref'] and vp['materials_hash']==frozen['verification_materials_hash'],
                 'verification_binding','Comparison changed its trusted material catalog')
        planned += sum(len(store.get('contrast_plans',ref)['requests']) for ref in vp['contrast_plan_refs'])
    planned *= criterion_count(protocol)
    _require(planned==frozen['planned_evaluation_calls'],'call_budget','Frozen evaluation call count changed')
    planned=comparison_call_budget(store,frozen)
    for val in validations:
        actual = val["gate_results"]
        required=set(protocol['required_gates']) | {'verification_complete'}
        _require(len(actual) == len(required)
                 and {g["gate"] for g in actual} == required,
                 "gate_coverage", "Required gates missing or duplicated")
        gates, status, _ = _gates(store, plans[val["plan_id"]], val["results"], cases, protocol, planned, all_results,
                                   verification_records[val['plan_id']],auxiliary_usage)
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
    with measure_stage(store,project_id,'publish',purpose='maintenance',subject_ref=selection_id):
        return _publish(store,project_id,candidate_id,validation_id,selection_id,
                        expected_active_digest=expected_active_digest,expected_generation=expected_generation)


def _publish(store, project_id, candidate_id, validation_id, selection_id, *, expected_active_digest, expected_generation):
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
    frozen, aliases = _frozen_aliases(store, selection)
    _require(candidate in frozen["candidates"] and candidate_id in aliases[candidate["candidate_digest"]],
             "candidate_changed", "Proposal was not one of the frozen attempts for the selected snapshot")
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
    _verify_selection(store, selection)
    snapshot = store.snapshot(candidate["candidate_digest"])
    _require(snapshot["project_id"] == project_id and snapshot["parent"] == expected_active_digest,
             "candidate_parent", "Candidate project or parent differs")
    return store._commit_release(project_id, expected_active_digest, expected_generation, record)


def rollback(store, project_id, target_release_id, *, expected_active_digest, expected_generation, reason):
    with measure_stage(store,project_id,'recover',purpose='maintenance',subject_ref=target_release_id):
        return _rollback(store,project_id,target_release_id,expected_active_digest=expected_active_digest,
                         expected_generation=expected_generation,reason=reason)


def _rollback(store, project_id, target_release_id, *, expected_active_digest, expected_generation, reason):
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
