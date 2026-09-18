"""Observed counts and unique recorded costs; no inferred learning gain."""
from __future__ import annotations

import math
import re
from collections import Counter

from .schemas import DomainError, digest, new_id, now_iso, validate
from .evaluation import _summaries
from .outcomes import parse_execution
from .lineage import check_feedback_binding, resolve_episode_source
from .feedback import verify_assessment, aggregate, check_planned_feedback
from .telemetry import summarize_stages, measure_stage


def aggregate_usage(records):
    unique = {}
    for record in records:
        uid = record["usage_id"]
        if uid in unique and digest(unique[uid]) != digest(record):
            raise DomainError("conflicting_usage", f"Usage ID {uid} has different contents")
        unique[uid] = record
    by_currency, by_stage = {}, {}
    missing = 0
    for record in unique.values():
        amount, currency = record.get("monetary_cost"), record.get("currency")
        stage = record["exclusive_stage"]
        by_stage[stage] = by_stage.get(stage, 0) + 1
        if amount is None or currency is None:
            missing += 1
        else:
            if type(amount) not in (float, int) or not math.isfinite(amount) or amount < 0 or not isinstance(currency, str):
                raise DomainError("invalid_usage", "Cost must be a nonnegative finite value with a currency")
            by_currency[currency] = by_currency.get(currency, 0) + amount
    token_fields = ("input_tokens", "output_tokens", "total_tokens")
    token_values = {field: [] for field in token_fields}
    for record in unique.values():
        tokens = record.get("tokens")
        if tokens is not None and not isinstance(tokens, dict):
            raise DomainError("invalid_usage", "tokens must be an object or null")
        for field in token_fields:
            value = tokens.get(field) if tokens is not None else None
            if value is not None:
                if type(value) is not int or value < 0:
                    raise DomainError("invalid_usage", f"{field} must be a nonnegative integer or null")
                token_values[field].append(value)
    token_summary = {
        "known_subtotals": {f: sum(v) if v else None for f, v in token_values.items()},
        "known_calls": {f: len(v) for f, v in token_values.items()},
        "missing_calls": {f: len(unique) - len(v) for f, v in token_values.items()},
        "complete_totals": {f: sum(v) if v and len(v) == len(unique) else None for f, v in token_values.items()},
    }
    times = [r.get("time") for r in unique.values()]
    known_times = [t for t in times if type(t) in (int, float) and math.isfinite(t) and t >= 0]
    return {"unique_calls": len(unique), "by_stage": by_stage,
            "known_cost_subtotals": by_currency, "missing_cost_calls": missing,
            "complete_cost_totals": by_currency if not missing else None,
            "sum_run_time": sum(known_times) if len(known_times) == len(times) else None,
            "known_run_time_subtotal": sum(known_times), "missing_time_calls": len(times) - len(known_times),
            "tokens": token_summary,
            "usage_ids": sorted(unique)}


def _optional(store, kind, identifier):
    if identifier is None:
        return None
    try:
        return store.get(kind, identifier)
    except DomainError as exc:
        if exc.code != "NOT_FOUND":
            raise
        return None


def _unknown(reason):
    return {"outcome": "unknown", "score": None, "execution_status": "unknown", "reason": reason}


def _quality(rows):
    """Outcomes and execution terminal states have separate denominators."""
    counts = {state: sum(r["outcome"] == state for r in rows) for state in ("pass", "fail", "unknown")}
    terminal = {state: sum(r.get("execution_status", "unknown") == state for r in rows)
                for state in ("completed", "cancelled", "timeout", "budget_exhausted", "adapter_error", "unknown")}
    planned, known = len(rows), counts["pass"] + counts["fail"]
    return {"outcomes": counts, "execution_status_counts": terminal,
            "observed_success_rate": counts["pass"] / known if known else None,
            "coverage": known / planned if planned else None,
            "identification_bounds": [counts["pass"] / planned, (counts["pass"] + counts["unknown"]) / planned] if planned else None,
            "any_success": True if counts["pass"] else None if counts["unknown"] else False,
            "all_success": False if counts["fail"] else None if counts["unknown"] or not planned else True}


def _mode_groups(entries, group_unit):
    buckets = {}
    for purpose, mode, policy, rows in entries:
        buckets.setdefault((purpose, mode, policy), []).append(rows)
    result = []
    for (purpose, mode, policy), groups in sorted(buckets.items()):
        rows = [row for group in groups for row in group]
        per_group = [_quality(group) for group in groups]
        result.append({"purpose": purpose, "update_mode": mode, "scoring_policy": policy, "group_unit": group_unit,
                       "group_count": len(groups), "planned_requests": len(rows), **_quality(rows),
                       "any_success_groups": {label: sum(g["any_success"] is value for g in per_group)
                                              for label, value in (("true", True), ("false", False), ("unknown", None))},
                       "all_success_groups": {label: sum(g["all_success"] is value for g in per_group)
                                              for label, value in (("true", True), ("false", False), ("unknown", None))}})
    return result


def _read_comparison(store, plan):
    """Read normalized observation records even if admission never completed."""
    observed, missing, mismatched = {}, [], []
    for request in plan["requests"]:
        rid = request["request_id"]
        result = _optional(store, "evaluation_results", rid)
        if result is None:
            missing.append(rid)
            continue
        if result["request_id"] != rid or any(result[k] != request[k] for k in ("case_ref", "snapshot_digest")):
            mismatched.append(rid)
            continue
        row = dict(result)
        if "execution_status" not in row:
            execution = _optional(store, "evaluation_returns", row.get("execution_ref"))
            proven = (execution is not None and execution.get("project_id") == plan["project_id"]
                      and execution.get("stage") == "execute" and execution.get("request") == request)
            row["execution_status"] = parse_execution(execution["returned"], execution["error"], "available_artifact")["execution_status"] if proven else "unknown"
        if row.get("evaluator_status") != "ok" or row["score"] is None:
            row["outcome"], row["score"] = "unknown", None
        observed[rid] = row
    return {"observed": observed, "missing": missing, "mismatched": mismatched}


def _comparisons(store, plans, validations, observations):
    comparisons, modes = [], []
    for plan in plans:
        case_record = store.get("case_sets", plan["case_set_ref"])
        case_set = case_record["value"]
        if case_record["project_id"] != plan["project_id"] or digest(case_set) != plan["case_set_hash"]:
            raise DomainError("comparison_binding", "Frozen comparison case set differs")
        facts = observations[plan["plan_id"]]
        observed = facts["observed"]
        decisions = []
        for val in sorted((v for v in validations if v["plan_id"] == plan["plan_id"]), key=lambda v: v["validation_id"]):
            errors = [key for key in ("project_id", "base_digest", "candidate_digest", "protocol_hash", "case_set_hash") if val[key] != plan[key]]
            if val["plan_hash"] != digest(plan):
                errors.append("plan_hash")
            decisions.append({"validation_id": val["validation_id"], "status": val["status"], "binding_errors": errors})
        grouped = {"target": [], "regression": [], "transfer": []}
        purpose, mode = plan.get("purpose", "unknown"), plan.get("update_mode", "unknown")
        for row in _summaries(plan, list(observed.values()), case_set):
            for arm in ("base", "candidate"):
                slots = [r for r in plan["requests"] if r["case_ref"] == row["case_id"] and r["arm"] == arm]
                values = [observed.get(r["request_id"], _unknown("No bound result record")) for r in slots]
                quality = _quality(values)
                row[arm + "_known_repeats"] = sum(v["score"] is not None for v in values)
                for key in ("outcomes", "any_success", "all_success", "execution_status_counts"):
                    row[arm + "_" + key] = quality[key]
                modes.append((purpose, mode, plan.get("scoring_policy", "unknown"), values))
            gain = row["gain"]
            row["observed_change"] = "unknown" if gain is None else "improved" if gain > 0 else "regressed" if gain < 0 else "unchanged"
            grouped[row["split"]].append(row)
        comparisons.append({"plan_id": plan["plan_id"], "project_id": plan["project_id"],
            "validation_id": decisions[0]["validation_id"] if len(decisions) == 1 else None,
            "validation_status": decisions[0]["status"] if len(decisions) == 1 else "multiple" if decisions else "missing",
            "validations": decisions, "base_digest": plan["base_digest"], "candidate_digest": plan["candidate_digest"],
            "case_set_ref": plan["case_set_ref"], "case_set_hash": plan["case_set_hash"],
            "protocol_ref": plan["protocol_ref"], "protocol_hash": plan["protocol_hash"],
            "purpose": purpose, "update_mode": mode, "scoring_policy": plan.get("scoring_policy", "unknown"),
            "proposal_ids": plan.get("proposal_ids", []), "acceptance_scope": plan["acceptance_scope"],
            "quality_case_refs": plan.get('quality_case_refs', [c['id'] for c in case_set['cases']]),
            "repeat_count": plan["repeat_count"], "planned_requests": len(plan["requests"]),
            "recorded_results": len(observed), "missing_request_ids": facts["missing"],
            "mismatched_request_ids": facts["mismatched"], "by_split": grouped})
    return comparisons, _mode_groups(modes, "case_and_arm")


def _feedback_fact(store, feedback, run_id, group, run=None):
    feedback = validate("Feedback", feedback)
    episode = store.get("episodes", feedback["subject_ref"])
    if (feedback.get("run_id") not in (None, run_id) or feedback["criterion_id"] != "task_outcome"
            or feedback["project_id"] != group["project_id"] or feedback["task_revision"] != group["task_revision"]
            or episode["source"]["reference"] != run_id):
        raise DomainError("assessment_binding", "Feedback does not describe this task_outcome")
    source = check_feedback_binding(store, feedback, episode)
    if (not source.get("known") or source.get("run_id") != run_id or source.get("group") is None
            or source["group"]["group_id"] != group["group_id"]
            or source["task_revision"] != group["task_revision"] or source["snapshot_digest"] != group["snapshot_digest"]):
        raise DomainError("assessment_binding", "Original execution does not prove this frozen slot's identity")
    if feedback["outcome"] != "unknown" and (feedback["binding_status"] != "bound"
            or feedback["evaluated_state_digest"] is None or feedback["evaluated_state_digest"] != source["artifact_digest"]
            or feedback["evaluator_status"] != "ok" or feedback["score"] is None):
        raise DomainError("assessment_binding", "Known outcome lacks a proven checked state")
    execution = source.get("execution")
    terminal = parse_execution(execution["output"], source.get("binding_error"),
                               group.get("scoring_policy", "completed_only")) if execution else None
    return {"outcome": feedback["outcome"], "score": feedback["score"], "feedback_ref": feedback["check_id"],
            "execution_status": run["execution_status"] if run is not None else terminal["execution_status"] if terminal else "unknown"}


def _sampling_outcome(store, run_id, run, group, feedback_records):
    try:
        slot = next(item for item in group['slots'] if item['run_id'] == run_id)
        plan_ref = slot.get('feedback_plan_id')
        linked = _optional(store, 'assessments', run.get('assessment_ref')) if run else None
        if linked is not None and linked.get('feedback_plan_ref'):
            plan_ref = linked['feedback_plan_ref']
        if plan_ref:
            plan = _optional(store, 'feedback_plans', plan_ref)
            if plan is None:
                return {**_unknown('Frozen feedback has not been prepared'), 'assessment_source': 'planned_pending'}
            if (plan['project_id'] != group['project_id'] or plan['run_id'] != run_id
                    or plan['protocol_id'] != group['protocol_id'] or plan['subject']['kind'] != 'episode'
                    or plan['task_revision'] != group['task_revision']):
                raise DomainError('assessment_binding', 'Feedback plan does not bind the frozen sampling slot.')
            episode = store.get('episodes', plan['subject']['ref'])
            source = resolve_episode_source(store, episode)
            if (not source['known'] or source['run_id'] != run_id or source['group'] is None
                    or source['group']['group_id'] != group['group_id']
                    or source['snapshot_digest'] != group['snapshot_digest']):
                raise DomainError('assessment_binding', 'Saved source does not belong to the sampling group.')
            assessment = linked or _optional(store, 'assessments', plan['assessment_id'])
            if assessment is not None:
                verified = verify_assessment(store, assessment, expected_subject=plan['subject'],
                                             expected_protocol=group['protocol_id'])
                values, feedbacks = verified['aggregate'], verified['feedbacks']
                origin = 'referenced' if linked is not None else 'recovered_assessment'
            else:
                feedbacks = [item for request in plan['requests']
                             if (item := _optional(store, 'feedback', request['feedback_id'])) is not None]
                for item in feedbacks:
                    check_planned_feedback(store, plan, item)
                values, origin = aggregate(plan, feedbacks), 'partial_planned_feedback'
            raw = source.get('execution')
            terminal = parse_execution(raw['output'], source.get('binding_error'), plan['scoring_policy']) if raw else None
            return {'outcome': values['outcome'], 'score': values['score'],
                    'assessment_ref': assessment['assessment_id'] if assessment else None,
                    'feedback_plan_ref': plan_ref, 'assessment_source': origin,
                    'criterion_ids': values['expected_criterion_ids'], 'missing_criterion_ids': values['missing_criterion_ids'],
                    'criterion_coverage': values['criterion_coverage'], 'score_bounds': values['score_bounds'],
                    'feedback_sources': values['feedback_sources'], 'feedback_refs': [f['check_id'] for f in feedbacks],
                    'execution_status': run['execution_status'] if run else terminal['execution_status'] if terminal else 'unknown'}
        episodes = {e["episode_id"] for e in store.list("episodes", project_id=group["project_id"])
                    if e["source"]["reference"] == run_id}
        matches = [f for f in feedback_records if f["criterion_id"] == "task_outcome"
                   and (f.get("run_id") == run_id or f["subject_ref"] in episodes)]
        assessment_id = run.get("assessment_ref") if run else None
        recovered = False
        if run is None:
            available = [a for a in store.list("assessments", project_id=group["project_id"])
                         if a.get("run_id") == run_id or a.get("subject_ref") in episodes]
            if len(available) > 1 or len(matches) != 1:
                raise DomainError("ambiguous_assessment", "Early assessment or feedback is missing or non-unique")
            if available:
                assessment_id = available[0].get("assessment_id")
                if not assessment_id:
                    raise DomainError("assessment_binding", "Early assessment has no stored identity")
                recovered = True
        if assessment_id:
            assessment = validate("TaskAssessment", store.get("assessments", assessment_id))
            if (assessment.get("assessment_id") != assessment_id or assessment.get("project_id") != group["project_id"]
                    or assessment.get("run_id") != run_id or assessment["protocol_id"] != group["protocol_id"]
                    or assessment["aggregation_rule"] != "single_task_outcome"
                    or len(assessment["criterion_feedback_ids"]) != 1):
                raise DomainError("assessment_binding", "Assessment does not bind this planned run")
            feedback = store.get("feedback", assessment["criterion_feedback_ids"][0])
            value = _feedback_fact(store, feedback, run_id, group, run)
            if any(assessment[k] != feedback[k] for k in ("subject_ref", "outcome", "score")):
                raise DomainError("assessment_binding", "Assessment differs from its original feedback")
            return {**value, "assessment_ref": assessment_id,
                    "assessment_source": "recovered_assessment" if recovered else "referenced"}
        # Legacy records may recover only one provably related task_outcome.
        if len(matches) != 1:
            raise DomainError("ambiguous_assessment", "Legacy task_outcome is missing or non-unique")
        return {**_feedback_fact(store, matches[0], run_id, group, run), "assessment_ref": None, "assessment_source": "unique_original_feedback"}
    except DomainError as exc:
        return {**_unknown(exc.code + ": " + str(exc)), "assessment_ref": run.get("assessment_ref") if run else None, "assessment_source": "unknown",
                "assessment_error": {"code": exc.code, "message": str(exc), "details": exc.details}}


def _sampling(store, groups, runs, feedback_records):
    details, mode_rows, seen_runs = [], [], set()
    missing = incomplete = 0
    for group in groups:
        rows, missing_ids = [], []
        for slot in group["slots"]:
            if slot["run_id"] in seen_runs:
                raise DomainError("duplicate_run", "Run ID occurs in multiple planned sampling slots")
            seen_runs.add(slot["run_id"])
            run = runs.get(slot["run_id"])
            bound = (run is not None and run["group_id"] == group["group_id"] and run["slot_id"] == slot["slot_id"]
                     and run["project_id"] == group["project_id"]
                     and all(run[k] == group[k] for k in ("snapshot_digest", "context_digest", "task_revision")))
            if run is not None and not bound:
                row = _unknown("Contradictory RunBundle does not bind this planned slot")
            else:
                row = _sampling_outcome(store, slot["run_id"], run, group, feedback_records)
            if not bound:
                missing_ids.append(slot["run_id"])
                missing += 1
            if bound:
                row["execution_status"] = run["execution_status"]
            incomplete += row["execution_status"] != "completed"
            rows.append({"run_id": slot["run_id"], **row})
        receipts = [receipt for receipt in store.list("group_receipts", project_id=group["project_id"])
                    if receipt.get("group_id") == group["group_id"]]
        details.append({"group_id": group["group_id"], "purpose": group["purpose"], "update_mode": group["update_mode"],
                        "scoring_policy": group.get("scoring_policy", "unknown"), "snapshot_digest": group["snapshot_digest"],
                        "task_revision": group["task_revision"], "planned_slots": len(group["slots"]),
                        "recorded_runs": len(group["slots"]) - len(missing_ids), "missing_run_ids": missing_ids,
                        "recorded_receipts": len(receipts), "receipt_refs": [r["receipt_id"] for r in receipts],
                        "results": rows, **_quality(rows)})
        mode_rows.append((group["purpose"], group["update_mode"], group.get("scoring_policy", "unknown"), rows))
    return {"groups": details, "by_mode": _mode_groups(mode_rows, "same_task_run_group")}, missing, incomplete


def _learning_cycles(store, project_id):
    cycles = {}
    for record in store.list("learning_cycles", project_id=project_id):
        key = record["cycle_id"]
        if key not in cycles or record["status"] != "planned":
            cycles[key] = record
    return list(cycles.values())


def _proposal_attempts(store, project_id):
    slots = [slot for cycle in _learning_cycles(store, project_id) for slot in cycle["candidate_slots"]]
    return {"planned_slots": len(slots), "slot_status_counts": dict(Counter(s["status"] for s in slots)),
            "finished_slots": sum(s["status"] in ("candidate", "error", "noop") for s in slots),
            "note": "Proposal slots are not unique snapshots or model repair calls; usage records count physical calls."}


def sampling_quality(store, project_id, plan_ids):
    """Read just these frozen groups; experiment scoring does not write a full project report."""
    groups = [store.get('run_groups', identifier) for identifier in plan_ids]
    if any(group['project_id'] != project_id for group in groups):
        raise DomainError('project_mismatch', 'Sampling report belongs to another project.')
    runs = {slot['run_id']: row for group in groups for slot in group['slots']
            if (row := _optional(store, 'runs', slot['run_id'])) is not None}
    legacy = any(not slot.get('feedback_plan_id') for group in groups for slot in group['slots'])
    return _sampling(store, groups, runs, store.list('feedback', project_id=project_id) if legacy else [])[0]


def _wall_segments(store, project_id, kind, group_key):
    groups = {}
    for row in store.list(kind, project_id=project_id):
        segments = groups.setdefault(row[group_key], {})
        current = segments.get(row['segment_id'])
        if current is None or row.get('finished_at') is not None:
            segments[row['segment_id']] = row
    results = []
    for identifier, segments in sorted(groups.items()):
        rows = list(segments.values())
        known = [r['elapsed_seconds'] for r in rows if r.get('finished_at') is not None
                 and type(r.get('elapsed_seconds')) in (int, float) and math.isfinite(r['elapsed_seconds'])]
        results.append({group_key: identifier, 'segment_ids': sorted(segments),
                        'known_active_wall_seconds': sum(known), 'missing_segments': len(rows) - len(known),
                        'complete_active_wall_seconds': sum(known) if len(known) == len(rows) else None,
                        'statuses': dict(Counter(r['status'] for r in rows))})
    return results


def _library_history(store, project_id):
    active = store.active(project_id)
    releases = [r for r in store.release_history(project_id) if r['new_generation'] <= active['generation']]
    baseline = releases[0]['expected_active_digest'] if releases else active['snapshot_id']
    points = [(0, baseline, 'baseline', None)] + [(r['new_generation'], r['new_digest'], r['kind'], r['release_id']) for r in releases]
    rows, previous = [], set()
    for generation, sid, kind, release_ref in points:
        snapshot = store.snapshot(sid)
        current = set(snapshot['skills'])
        rows.append({'generation': generation, 'snapshot_digest': sid, 'kind': kind, 'release_ref': release_ref,
                     'skill_count': len(current), 'rule_count': sum(len(s['content']['steps']) for s in snapshot['skills'].values()),
                     'asset_bytes': sum(len(text.encode('utf-8')) for text in snapshot['assets'].values()),
                     'added_skill_ids': sorted(current - previous), 'removed_skill_ids': sorted(previous - current)})
        previous = current
    return rows


def _consumption_layers(store, project_id, runs):
    provided, observed = {}, []
    for context in store.list('contexts', project_id=project_id):
        for skill in context['selected_skills']:
            key = skill['skill_id'] + '@' + skill['revision']
            provided.setdefault(key, set()).add(context['manifest_id'])
    for run in runs.values():
        raw = _optional(store, 'executions', run['raw_events_ref'])
        output = raw.get('output') if raw else None
        declarations = output.get('consumption_events', []) if isinstance(output, dict) else []
        for ref in run['consumption_events']:
            match = re.fullmatch(re.escape(run['run_id']) + r'#/output/consumption_events/(\d+)', ref)
            if match is None or not isinstance(declarations, list) or int(match[1]) >= len(declarations):
                continue
            item = declarations[int(match[1])]
            level = item.get('level', item.get('evidence_kind', 'unclassified'))
            level = level if level in ('read', 'behavior') else 'unclassified'
            observed.append({'run_id': run['run_id'], 'skill_id': item['skill_id'], 'level': level,
                             'source_ref': ref, 'authority': 'execution_provider_report'})
    effects = store.list('contrast_results', project_id=project_id)
    return {'provided_manifest_counts': {key: len(values) for key, values in provided.items()},
            'observed_events': observed, 'observed_level_counts': dict(Counter(r['level'] for r in observed)),
            'effect_records': [{'contrast_result_id': r['contrast_result_id'], 'status': r['status'],
                                'value': r['value'], 'relation_ref': r['relation_ref']} for r in effects],
            'note': 'Provided, reported read, reported behavior and measured conditional effects are distinct; absent level is unclassified, not inferred use.'}


def _memory_progress(store, project_id):
    from .maintenance import maintenance_summary
    cycles = _learning_cycles(store, project_id)
    bindings = store.list('goal_bindings', project_id=project_id)
    manifests = store.list('trace_manifests', project_id=project_id)
    checkpoints = {}
    for row in store.list('trace_index_checkpoints', project_id=project_id):
        prior = checkpoints.get(row['trace_id'])
        if prior is None or (row['next_raw_byte'], row['created_at']) > (prior['next_raw_byte'], prior['created_at']):
            checkpoints[row['trace_id']] = row
    return {'maintenance': maintenance_summary(store, project_id),
            'goal_binding_statuses': dict(Counter(row['status'] for row in bindings)),
            'derived_goal_bindings': sum(len(row['resolved_bindings']) for row in bindings),
            'trace_count': len(manifests), 'archived_trace_bytes': sum(row['byte_length'] for row in manifests),
            'indexed_events': sum(row['event_count'] for row in checkpoints.values()),
            'incomplete_traces': [row['trace_id'] for row in manifests if not checkpoints.get(row['trace_id'], {}).get('index_complete')],
            'signature_retrieval_hits': sum(row.get('retrieval', {}).get('signature_hits', 0) for row in cycles),
            'range_reads': sum(row.get('read_stats', {}).get('range_reads', 0) for row in cycles),
            'decoded_body_bytes_read': sum(row.get('read_stats', {}).get('body_bytes', 0) for row in cycles),
            'necessity_verdicts': dict(Counter(row['draft'].get('necessity', {}).get('verdict', 'legacy_unrecorded')
                                                for row in store.list('diagnoses', project_id=project_id))),
            'judgment_origin': 'Model judgments are not semantic accuracy measurements; unlabeled accuracy remains unknown.'}


def report(store, project_id):
    with measure_stage(store, project_id, 'report', purpose='maintenance') as meter:
        return _report(store, project_id, meter.measurement_id)


def _report(store, project_id, report_measurement_ref):
    plans = sorted(store.list("evaluation_plans", project_id=project_id), key=lambda p: p["plan_id"])
    validations = store.list("validations", project_id=project_id)
    observations = {p["plan_id"]: _read_comparison(store, p) for p in plans}
    result_records = {rid: row for observed in observations.values() for rid, row in observed["observed"].items()}
    requests = {}
    for plan in plans:
        for request in plan["requests"]:
            rid = request["request_id"]
            if rid in requests:
                raise DomainError("duplicate_request", "Request appears in multiple plans")
            requests[rid] = request
    rows = [result_records.get(rid, _unknown("Missing or mismatched result")) for rid in requests]
    quality = _quality(rows)
    planned = len(requests)
    episodes = store.list("episodes", project_id=project_id)
    task_ids = {e["task"]["task_id"] for e in episodes if e["task"].get("task_id") is not None}
    unknown_tasks = sum(e["task"].get("task_id") is None for e in episodes)
    usages = store.list("usage", project_id=project_id)
    usage_summary = aggregate_usage(usages)
    maintenance = summarize_stages(store.list('stage_measurements', project_id=project_id))
    attempts = store.list('callback_attempts', project_id=project_id)
    returned_attempts = {row['attempt_id'] for row in store.list('callback_returns', project_id=project_id)}
    unreturned_attempts = [row['attempt_id'] for row in attempts if row['attempt_id'] not in returned_attempts]
    usage_summary['callback_attempts'] = len(attempts)
    usage_summary['unreturned_attempt_ids'] = unreturned_attempts
    unfinished_learning = [row['cycle_id'] for row in _learning_cycles(store, project_id) if row['status'] == 'planned']
    usage_summary['unfinished_learning_cycle_ids'] = unfinished_learning
    unfinished = sum(rid not in result_records or result_records[rid].get("execution_ref") is None for rid in requests)
    usage_summary["unaccounted_evaluation_requests"] = unfinished
    groups = store.list("run_groups", project_id=project_id)
    runs = {r["run_id"]: r for r in store.list("runs", project_id=project_id)}
    sampling, missing_slots, incomplete_slots = _sampling(store, groups, runs, store.list("feedback", project_id=project_id))
    sampling_slots = sum(len(group["slots"]) for group in groups)
    usage_summary["unaccounted_sampling_slots"] = missing_slots
    usage_summary["incomplete_sampling_slots"] = incomplete_slots
    if unfinished or missing_slots or unreturned_attempts or unfinished_learning:
        usage_summary["complete_cost_totals"] = None
        usage_summary["tokens"]["complete_totals"] = {field: None for field in usage_summary["tokens"]["complete_totals"]}
    comparisons, comparison_modes = _comparisons(store, plans, validations, observations)
    proposals = store.list("candidates", project_id=project_id)
    snapshot_states = {}
    for validation in validations:
        snapshot_states.setdefault(validation["candidate_digest"], set()).add(validation["status"])
    payload = {"report_id": new_id("report"), "project_id": project_id, "created_at": now_iso(),
               "evidence_kind": "caller execution/evaluation records; not automatic independent truth",
               "evaluation_requests": planned, **quality,
               "comparisons": comparisons,
               "comparison_summary": {"planned_requests": planned, "by_mode": comparison_modes, **quality},
               "pooled_rate_note": "Overall success rate mixes base and candidate requests; it is not an improvement estimate.",
               "sampling_slots": sampling_slots, "sampling": sampling,
               "maintenance": maintenance,
               "report_measurement_ref": report_measurement_ref,
               "measurement_scope": "Cost totals cover listed completed records; this report's own timing is appended on return and addressed by report_measurement_ref.",
               "batch_wall_time": {'sampling': _wall_segments(store, project_id, 'sampling_segments', 'batch_id'),
                                   'comparison': _wall_segments(store, project_id, 'comparison_segments', 'comparison_id'),
                                   'sampling_receipts': store.list('sampling_batch_receipts', project_id=project_id)},
               "library_history": _library_history(store, project_id),
               "memory_progress": _memory_progress(store, project_id),
               "consumption_layers": _consumption_layers(store, project_id, runs),
               "unique_case_identity_count": len({(p["case_set_hash"], r["case_ref"]) for p in plans for r in p["requests"]}),
               "known_task_ids": sorted(task_ids), "episodes_with_unknown_task_id": unknown_tasks,
               "distinct_known_task_count": len(task_ids), "episode_count": len(episodes),
               "candidate_counts": {"unique_snapshots": len({p["candidate_digest"] for p in proposals}),
                                    "proposal_records": len(proposals), "compared_snapshots": len({p["candidate_digest"] for p in plans})},
               "proposal_attempts": _proposal_attempts(store, project_id),
               "proposal_snapshots": [{"proposal_id": p["proposal_id"], "candidate_digest": p["candidate_digest"]} for p in proposals],
               "validation_attempt_counts": {status: sum(v["status"] == status for v in validations)
                                             for status in ("accepted", "rejected", "unknown")},
               "snapshot_validation_statuses": {snapshot: sorted(states) for snapshot, states in snapshot_states.items()},
               "usage": usage_summary,
               "committed_release_ids": [r["release_id"] for r in store.release_history(project_id)]}
    store.put("reports", payload["report_id"], payload)
    return payload
