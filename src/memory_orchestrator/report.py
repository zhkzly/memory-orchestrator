"""Observed counts and unique recorded costs; no inferred learning gain."""
from __future__ import annotations

import math
from collections import Counter

from .schemas import DomainError, digest, new_id, now_iso
from .evaluation import _summaries


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


def _comparisons(store, plans, validations):
    """Read historical comparisons; never rerun gates against today's active."""
    comparisons = []
    for plan in sorted(plans, key=lambda p: p["plan_id"]):
        case_record = store.get("case_sets", plan["case_set_ref"])
        case_set = case_record["value"]
        if case_record["project_id"] != plan["project_id"] or digest(case_set) != plan["case_set_hash"]:
            raise DomainError("comparison_binding", "Frozen comparison case set differs")
        expected = {r["request_id"]: r for r in plan["requests"]}
        matches = [v for v in validations if v["plan_id"] == plan["plan_id"]] or [None]
        for validation in sorted(matches, key=lambda v: v["validation_id"] if v else ""):
            results = validation["results"] if validation else []
            counts = Counter(r["request_id"] for r in results)
            duplicates = sorted(rid for rid, count in counts.items() if count > 1)
            extras = sorted(set(counts) - set(expected))
            mismatches = sorted({r["request_id"] for r in results if r["request_id"] in expected
                                 and any(r[k] != expected[r["request_id"]][k] for k in ("case_ref", "snapshot_digest"))})
            usable = [r for r in results if r["request_id"] in expected
                      and r["request_id"] not in duplicates and r["request_id"] not in mismatches]
            binding_errors = []
            if validation:
                for key in ("project_id", "base_digest", "candidate_digest", "protocol_hash", "case_set_hash"):
                    if validation[key] != plan[key]:
                        binding_errors.append(key)
                if validation["plan_hash"] != digest(plan):
                    binding_errors.append("plan_hash")
                if binding_errors:
                    usable = []
            per_case = _summaries(plan, usable, case_set)
            by_request = {r["request_id"]: r for r in usable}
            grouped = {"target": [], "regression": [], "transfer": []}
            for row in per_case:
                for arm in ("base", "candidate"):
                    requested = [r for r in plan["requests"] if r["case_ref"] == row["case_id"] and r["arm"] == arm]
                    row[arm + "_known_repeats"] = sum(r["request_id"] in by_request
                        and by_request[r["request_id"]]["score"] is not None for r in requested)
                gain = row["gain"]
                row["observed_change"] = ("unknown" if gain is None else "improved" if gain > 0
                                          else "regressed" if gain < 0 else "unchanged")
                grouped[row["split"]].append(row)
            comparisons.append({"plan_id": plan["plan_id"], "project_id": plan["project_id"],
                "validation_id": validation["validation_id"] if validation else None,
                "validation_status": validation["status"] if validation else "missing",
                "base_digest": plan["base_digest"], "candidate_digest": plan["candidate_digest"],
                "case_set_ref": plan["case_set_ref"], "case_set_hash": plan["case_set_hash"],
                "protocol_ref": plan["protocol_ref"], "protocol_hash": plan["protocol_hash"],
                "acceptance_scope": plan["acceptance_scope"], "repeat_count": plan["repeat_count"],
                "planned_requests": len(plan["requests"]), "recorded_results": len(results),
                "missing_request_ids": sorted(set(expected) - set(by_request)),
                "duplicate_request_ids": duplicates, "unexpected_request_ids": extras,
                "mismatched_request_ids": mismatches, "binding_errors": binding_errors,
                "by_split": grouped})
    return comparisons


def report(store, project_id):
    plans = store.list("evaluation_plans", project_id=project_id)
    validations = store.list("validations", project_id=project_id)
    result_records = {}
    for validation in validations:
        for result in validation["results"]:
            rid = result["request_id"]
            if rid in result_records and result_records[rid] != result:
                raise DomainError("conflicting_result", f"Conflicting result for {rid}")
            result_records[rid] = result
    counts = {"pass": 0, "fail": 0, "unknown": 0}
    requests = {}
    for plan in plans:
        for request in plan["requests"]:
            rid = request["request_id"]
            if rid in requests:
                raise DomainError("duplicate_request", "Request appears in multiple plans")
            requests[rid] = request
    for rid, request in requests.items():
        result = result_records.get(rid)
        bound = result is not None and all(result[k] == request[k] for k in ("case_ref", "snapshot_digest"))
        outcome = result["outcome"] if bound else "unknown"
        counts[outcome] += 1
    planned = len(requests)
    known = counts["pass"] + counts["fail"]
    episodes = store.list("episodes", project_id=project_id)
    task_ids = {e["task"]["task_id"] for e in episodes if e["task"].get("task_id") is not None}
    unknown_tasks = sum(e["task"].get("task_id") is None for e in episodes)
    usages = store.list("usage", project_id=project_id)
    usage_summary = aggregate_usage(usages)
    unfinished = sum(rid not in result_records or result_records[rid].get("execution_ref") is None for rid in requests)
    usage_summary["unaccounted_evaluation_requests"] = unfinished
    groups = store.list("run_groups", project_id=project_id)
    runs = {r["run_id"]: r for r in store.list("runs", project_id=project_id)}
    sampling_slots, missing_slots, incomplete_slots = 0, 0, 0
    seen_runs = set()
    for group in groups:
        for slot in group["slots"]:
            sampling_slots += 1
            if slot["run_id"] in seen_runs:
                raise DomainError("duplicate_run", "Run ID occurs in multiple planned sampling slots")
            seen_runs.add(slot["run_id"])
            run = runs.get(slot["run_id"])
            bound = (run is not None and run["group_id"] == group["group_id"]
                     and run["slot_id"] == slot["slot_id"] and run["project_id"] == project_id
                     and all(run[k] == group[k] for k in ("snapshot_digest", "context_digest", "task_revision")))
            missing_slots += not bound
            incomplete_slots += not bound or run["execution_status"] != "completed"
    usage_summary["unaccounted_sampling_slots"] = missing_slots
    usage_summary["incomplete_sampling_slots"] = incomplete_slots
    if unfinished or incomplete_slots:
        usage_summary["complete_cost_totals"] = None
        usage_summary["tokens"]["complete_totals"] = {field: None for field in usage_summary["tokens"]["complete_totals"]}
    payload = {"report_id": new_id("report"), "project_id": project_id, "created_at": now_iso(),
               "evidence_kind": "caller execution/evaluation records; not automatic independent truth",
               "evaluation_requests": planned, "outcomes": counts,
               "comparisons": _comparisons(store, plans, validations),
               "pooled_rate_note": "Overall success rate mixes base and candidate requests; it is not an improvement estimate.",
               "sampling_slots": sampling_slots,
               "unique_case_identity_count": len({(p["case_set_hash"], r["case_ref"]) for p in plans for r in p["requests"]}),
               "observed_success_rate": counts["pass"] / known if known else None,
               "coverage": known / planned if planned else None,
               "identification_bounds": [counts["pass"] / planned, (counts["pass"] + counts["unknown"]) / planned] if planned else None,
               "known_task_ids": sorted(task_ids), "episodes_with_unknown_task_id": unknown_tasks,
               "distinct_known_task_count": len(task_ids), "episode_count": len(episodes),
               "candidate_counts": {status: sum(v["status"] == status for v in validations)
                                    for status in ("accepted", "rejected", "unknown")},
               "usage": usage_summary,
               "committed_release_ids": [r["release_id"] for r in store.release_history(project_id)]}
    store.put("reports", payload["report_id"], payload)
    return payload
