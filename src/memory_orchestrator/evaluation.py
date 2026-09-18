"""Finite, recorded comparisons. Callback correctness remains the caller's duty."""
from __future__ import annotations

import copy
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .schemas import DomainError, digest, new_id, now_iso, validate, normalize_usage_measurements
from .outcomes import parse_execution, resolve_scoring_policy


BASE_GATES = {"complete_results", "target_gain", "regression_non_decrease",
              "call_budget", "scope_bound", "versions_unchanged"}
OPTIONAL_GATES = {"transfer_gain", "transfer_non_decrease", "cost", "stability"}
ORDER = ["accepted quality gain descending", "evaluation cost ascending", "candidate digest ascending"]


def _require(condition, code, message):
    if not condition:
        raise DomainError(code, message)


def _number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _json(value):
    """Validate JSON without silently coercing keys, tuples or nonfinite numbers."""
    if value is None or type(value) in (str, bool, int):
        return copy.deepcopy(value)
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) is list:
        return [_json(v) for v in value]
    if type(value) is dict and all(type(k) is str for k in value):
        return {k: _json(v) for k, v in value.items()}
    raise DomainError("invalid_json", "Expected finite JSON values")


def _raw(value):
    """Preserve invalid callback values explicitly, instead of losing the return."""
    try:
        return _json(value)
    except (DomainError, ValueError, OverflowError):
        if type(value) is dict:
            return {str(k): _raw(v) for k, v in value.items()}
        if type(value) in (list, tuple):
            return [_raw(v) for v in value]
        return {"non_json_type": type(value).__name__, "representation": repr(value)}


def _error(exc):
    return {"type": type(exc).__name__, "message": str(exc),
            "code": getattr(exc, "code", None), "details": _raw(getattr(exc, "details", None))}


def _check_protocol(protocol, case_set, candidate_count, max_parallel):
    p, cs = _json(protocol), _json(case_set)
    _require(set(p) <= {"id", "comparison_scope", "repeat_count", "required_gates", "criteria",
                       "selection_rule", "executor", "evaluator", "allowed_sources", "material_visibility", "note", "scoring_policy"},
             "unsupported_protocol", "Unsupported protocol fields; no ignored policy switches")
    p["scoring_policy"] = resolve_scoring_policy(p.get("scoring_policy"), default="available_artifact")
    _require(type(max_parallel) is int and max_parallel > 0, "invalid_parallelism", "max_parallel must be positive")
    _require(type(p.get("repeat_count")) is int and p["repeat_count"] > 0,
             "invalid_protocol", "repeat_count must be explicit and positive")
    for key in ("id", "comparison_scope"):
        _require(isinstance(p.get(key), str) and p[key], "invalid_protocol", f"Missing {key}")
    gates = p.get("required_gates", [])
    _require(type(gates) is list and all(type(g) is str for g in gates)
             and len(gates) == len(set(gates)) and BASE_GATES <= set(gates)
             and set(gates) <= BASE_GATES | OPTIONAL_GATES,
             "unsupported_gates", "Declare all six basic gates and only supported optional gates")
    criteria = p.get("criteria", {})
    _require(isinstance(criteria, dict) and set(criteria) <= {
        "target_mean_gain_must_exceed", "maximum_per_case_regression", "maximum_evaluation_calls", "transfer_claim",
        "transfer_mean_gain_must_exceed", "maximum_per_case_transfer_regression", "maximum_score_range",
        "maximum_monetary_cost", "currency"}, "unsupported_protocol", "Unsupported criteria fields")
    thresholds = {"target_gain": "target_mean_gain_must_exceed",
                  "regression_non_decrease": "maximum_per_case_regression",
                  "transfer_gain": "transfer_mean_gain_must_exceed",
                  "transfer_non_decrease": "maximum_per_case_transfer_regression",
                  "stability": "maximum_score_range", "cost": "maximum_monetary_cost"}
    for gate, key in thresholds.items():
        if gate in gates:
            _require(_number(criteria.get(key)) and criteria[key] >= 0,
                     "invalid_threshold", f"{gate} requires explicit nonnegative {key}")
    if "cost" in gates:
        _require(isinstance(criteria.get("currency"), str) and criteria["currency"],
                 "invalid_threshold", "cost requires currency")
    _require(type(criteria.get("transfer_claim")) is bool, "invalid_protocol", "Declare transfer_claim")
    _require(criteria["transfer_claim"] == bool(set(gates) & {"transfer_gain", "transfer_non_decrease"}),
             "scope_mismatch", "Transfer claim must match an explicit transfer gate")
    selection = p.get("selection_rule", {})
    _require(selection.get("order") == ORDER and selection.get("missing_cost") == "last"
             and isinstance(selection.get("id"), str) and bool(selection["id"]),
             "unsupported_selection", "Use the declared quality/cost/digest order and missing_cost=last")
    for key in ("executor", "evaluator"):
        cfg = p.get(key, {})
        _require(isinstance(cfg, dict) and isinstance(cfg.get("id"), str) and bool(cfg["id"])
                 and isinstance(cfg.get("config"), dict), "invalid_protocol", f"Missing {key} identity/config")
    sources = p.get("allowed_sources")
    _require(isinstance(sources, list) and bool(sources) and set(sources) <= {"executable", "human"},
             "unsupported_source", "Published comparisons require declared executable/human evidence, not proxy alone")
    _require(isinstance(cs.get("id"), str) and bool(cs["id"]) and isinstance(cs.get("version"), str),
             "invalid_cases", "Case set needs id and version")
    cases = cs.get("cases", [])
    _require(isinstance(cases, list) and bool(cases), "invalid_cases", "At least target and regression cases required")
    ids = []
    for case in cases:
        _require(isinstance(case, dict) and isinstance(case.get("id"), str) and bool(case["id"])
                 and case.get("split") in {"target", "regression", "transfer"}
                 and "task" in case and "criteria" in case, "invalid_cases", "Case needs id/split/task/criteria")
        ids.append(case["id"])
    _require(len(ids) == len(set(ids)), "duplicate_case", "Case IDs must be unique")
    splits = {c["split"] for c in cases}
    _require({"target", "regression"} <= splits and (not criteria["transfer_claim"] or "transfer" in splits),
             "missing_split", "Missing case split required by the comparison scope")
    planned = candidate_count * len(cases) * 2 * p["repeat_count"]
    limit = criteria.get("maximum_evaluation_calls")
    _require(type(limit) is int and limit >= planned, "call_budget", f"Plan requires {planned} evaluation requests")
    return p, cs


def _usage(store, project, request, stage, supplied, elapsed):
    uid = new_id("usage")
    known = isinstance(supplied, dict)
    measurements = normalize_usage_measurements(supplied)
    currency = measurements["currency"]
    cost = measurements["monetary_cost"] if currency is not None else None
    item = {"usage_id": uid, "project_id": project, "exclusive_stage": stage,
            "purpose": "validation", "request_id": request["request_id"],
            "run_or_proposal_id": request["request_id"], "price_version": None,
            "monetary_cost": cost, "currency": currency,
            "tokens": measurements["tokens"], "diagnostics": _raw(measurements["diagnostics"]),
            "time": elapsed, "status": "reported" if known else "missing", "raw": _raw(supplied)}
    store.put("usage", uid, item)
    return uid


def _invoke(store, project, request, stage, callback, args):
    copied = copy.deepcopy(args)
    before = _json(list(copied))
    start = time.monotonic()
    returned, error = None, None
    try:
        returned = callback(*copied)
        _require(_raw(list(copied)) == before, "callback_mutated_input", "Callback changed the evaluated input")
        _json(returned)
        _require(isinstance(returned, dict), "invalid_return", "Callback must return an object")
        for field in ("request_id", "case_ref", "snapshot_digest"):
            if field in returned:
                _require(returned[field] == request[field], "return_binding_mismatch", f"Wrong returned {field}")
    except Exception as exc:
        error = _error(exc)
    elapsed = time.monotonic() - start
    supplied = returned.get("usage") if isinstance(returned, dict) else None
    usage_id = _usage(store, project, request, stage, supplied, elapsed)
    rid = new_id("callback")
    record = {"id": rid, "project_id": project, "request": copy.deepcopy(request), "stage": stage,
              "inputs": before, "returned": _raw(returned), "error": error,
              "usage_ref": usage_id, "created_at": now_iso()}
    store.put("evaluation_returns", rid, record)
    return record


def _unknown(request, reason, execution_ref=None, usage_refs=None, evidence_refs=None, execution_status="unknown"):
    return {"request_id": request["request_id"], "case_ref": request["case_ref"],
            "snapshot_digest": request["snapshot_digest"], "outcome": "unknown", "score": None,
            "evaluator_status": "error", "source": "executable",
            "evidence_refs": evidence_refs or [], "execution_ref": execution_ref,
            "usage_refs": usage_refs or [], "gaps": [reason], "execution_status": execution_status}


def _one_request(store, project, request, snapshot, case, execute_fn, evaluate_fn, sources, scoring_policy):
    public_case = {k: copy.deepcopy(case[k]) for k in ("id", "split", "task")}
    execution = _invoke(store, project, request, "execute", execute_fn, (request, snapshot, public_case))
    usage = [execution["usage_ref"]]
    terminal = parse_execution(execution["returned"], execution["error"], scoring_policy)
    execution_status = terminal["execution_status"]
    if not terminal["eligible"]:
        return _unknown(request, f"Execution ineligible: {terminal['reason']}", execution["id"], usage,
                        execution_status=execution_status)
    feedback = _invoke(store, project, request, "evaluate", evaluate_fn,
                       (request, execution["returned"], case))
    usage.append(feedback["usage_ref"])
    out = feedback["returned"]
    evidence = [feedback["id"]]
    if feedback["error"]:
        return _unknown(request, f"Evaluator error: {feedback['error']}", execution["id"], usage, evidence, execution_status)
    valid = (out.get("outcome") in {"pass", "fail"} and _number(out.get("score"))
             and 0 <= out["score"] <= 1 and out.get("source") in sources
             and isinstance(out.get("evidence"), list) and bool(out["evidence"]))
    if not valid:
        return _unknown(request, "Unknown, invalid score/source or missing evaluation evidence", execution["id"], usage, evidence, execution_status)
    return {"request_id": request["request_id"], "case_ref": request["case_ref"],
            "snapshot_digest": request["snapshot_digest"], "outcome": out["outcome"], "score": out["score"],
            "evaluator_status": "ok", "source": out["source"], "evidence_refs": evidence,
            "execution_ref": execution["id"], "usage_refs": usage, "gaps": [], "execution_status": execution_status}


def proposal_aliases(candidates):
    """Content identities map to all distinct persisted proposal attempts."""
    aliases, seen = {}, {}
    for candidate in candidates:
        proposal, snapshot = candidate["proposal_id"], candidate["candidate_digest"]
        _require(proposal not in seen or seen[proposal] == snapshot, "proposal_binding", "Proposal names different snapshots")
        seen[proposal] = snapshot
        aliases.setdefault(snapshot, set()).add(proposal)
    return {snapshot: sorted(ids) for snapshot, ids in aliases.items()}


def _summaries(plan, results, case_set):
    rows = []
    by_request = {r["request_id"]: r for r in results}
    for case in case_set["cases"]:
        row = {"case_id": case["id"], "split": case["split"]}
        for arm in ("base", "candidate"):
            scores = [by_request[r["request_id"]]["score"] for r in plan["requests"]
                      if r["case_ref"] == case["id"] and r["arm"] == arm and r["request_id"] in by_request]
            known = len(scores) == plan["repeat_count"] and all(_number(v) for v in scores)
            row[arm] = sum(scores) / len(scores) if known else None
            row[arm + "_range"] = max(scores) - min(scores) if known else None
        row["gain"] = row["candidate"] - row["base"] if row["base"] is not None and row["candidate"] is not None else None
        rows.append(row)
    return rows


def _cost(store, results, currency=None):
    usages = [store.get("usage", uid) for uid in sorted({uid for r in results for uid in r["usage_refs"]})]
    units = {u["currency"] for u in usages if u["monetary_cost"] is not None}
    known = bool(usages) and all(u["monetary_cost"] is not None for u in usages) and len(units) == 1
    if currency is not None:
        known = known and units == {currency}
    return sum(u["monetary_cost"] for u in usages) if known else None


def _gates(store, plan, results, case_set, protocol, planned_total, round_results=None):
    expected = {r["request_id"]: r for r in plan["requests"]}
    complete = len(results) == len(expected) and len({r["request_id"] for r in results}) == len(results)
    complete = complete and all(r["request_id"] in expected and all(r[k] == expected[r["request_id"]][k]
                               for k in ("case_ref", "snapshot_digest")) and r["evaluator_status"] == "ok"
                               and r["outcome"] in {"pass", "fail"} and _number(r["score"])
                               and 0 <= r["score"] <= 1 and bool(r["evidence_refs"]) for r in results)
    rows = _summaries(plan, results, case_set)
    criteria = protocol["criteria"]
    active = store.active(plan["project_id"])
    unchanged = (active["snapshot_id"] == plan["base_digest"] and active["generation"] == plan["expected_generation"])
    for sid in (plan["base_digest"], plan["candidate_digest"]):
        unchanged = unchanged and store.snapshot(sid)["project_id"] == plan["project_id"]
    target = [r["gain"] for r in rows if r["split"] == "target"]
    regression = [r["gain"] for r in rows if r["split"] == "regression"]
    transfer = [r["gain"] for r in rows if r["split"] == "transfer"]
    all_known = complete and all(v is not None for v in target + regression + transfer)
    decisions = {"complete_results": complete,
                 "target_gain": sum(target) / len(target) > criteria["target_mean_gain_must_exceed"] if all_known else None,
                 "regression_non_decrease": all(v >= -criteria["maximum_per_case_regression"] for v in regression) if all_known else None,
                 "call_budget": planned_total <= criteria["maximum_evaluation_calls"],
                 "scope_bound": bool(target) and bool(regression) and (not criteria["transfer_claim"] or bool(transfer)),
                 "versions_unchanged": unchanged}
    for name in protocol["required_gates"]:
        if name == "transfer_gain":
            decisions[name] = sum(transfer) / len(transfer) > criteria["transfer_mean_gain_must_exceed"] if all_known and transfer else None
        elif name == "transfer_non_decrease":
            decisions[name] = all(v >= -criteria["maximum_per_case_transfer_regression"] for v in transfer) if all_known and transfer else None
        elif name == "stability":
            decisions[name] = all(r[arm + "_range"] <= criteria["maximum_score_range"] for r in rows for arm in ("base", "candidate")) if all_known else None
        elif name == "cost":
            cost = _cost(store, round_results if round_results is not None else results, criteria["currency"])
            decisions[name] = cost <= criteria["maximum_monetary_cost"] if cost is not None else None
    gates = [{"gate": name, "passed": decisions[name], "evidence_refs": [plan["plan_id"]],
              "detail": "Computed from the frozen plan and all recorded request results."} for name in protocol["required_gates"]]
    status = "unknown" if not complete or any(g["passed"] is None for g in gates) else (
        "accepted" if all(g["passed"] is True for g in gates) else "rejected")
    return gates, status, rows


def _rank(store, validations, plans, case_set):
    """Never compare numeric costs across different currencies."""
    all_usage = {u for v in validations for u in v["usage_refs"]}
    currencies = {store.get("usage", u)["currency"] for u in all_usage
                  if store.get("usage", u)["monetary_cost"] is not None}
    ranked = []
    for val in validations:
        if val["status"] != "accepted":
            continue
        rows = _summaries(plans[val["plan_id"]], val["results"], case_set)
        gains = [r["gain"] for r in rows if r["split"] == "target"]
        cost = _cost(store, val["results"]) if len(currencies) == 1 else None
        ranked.append((-sum(gains)/len(gains), cost is None, cost or 0.0,
                       val["candidate_digest"], val["validation_id"]))
    return sorted(ranked)


def compare_candidates(store, project_id, candidates, case_set, protocol, execute_fn, evaluate_fn, *, max_parallel):
    """Compare all candidates and select; does not learn or change active state.

    Callers provide request-local/resettable execution environments. Copying inputs
    here is not OS isolation. The cost gate covers all invocations in this comparison
    round; other learning/maintenance costs remain in the project report.
    """
    _require(callable(execute_fn) and callable(evaluate_fn), "missing_callback", "Actual execution and evaluation functions required")
    _require(isinstance(candidates, list) and bool(candidates), "missing_candidates", "Candidates required")
    active = copy.deepcopy(store.active(project_id))
    snapshots = {active["snapshot_id"]: store.snapshot(active["snapshot_id"])}
    candidates = _json(candidates)
    attempts = {}
    for candidate in candidates:
        canonical = store.get("candidates", candidate["proposal_id"])
        _require(canonical == candidate, "candidate_changed", "Use the stored immutable candidate")
        _require(candidate["project_id"] == project_id and candidate["base_digest"] == active["snapshot_id"]
                 and candidate["expected_generation"] == active["generation"], "stale_candidate", "Candidate project/base/generation mismatch")
        attempts[candidate["proposal_id"]] = candidate
        sid = candidate["candidate_digest"]
        snapshot = store.snapshot(sid)
        _require(snapshot["project_id"] == project_id and snapshot["parent"] == active["snapshot_id"],
                 "candidate_parent", "Candidate must belong to this project and base")
        snapshots[sid] = snapshot
    candidates = list(attempts.values())
    aliases = proposal_aliases(candidates)
    protocol, case_set = _check_protocol(protocol, case_set, len(aliases), max_parallel)
    round_id = new_id("comparison")
    protocol_id, cases_id = new_id("protocol"), new_id("cases")
    store.put("protocols", protocol_id, {"id": protocol_id, "project_id": project_id, "value": protocol})
    store.put("case_sets", cases_id, {"id": cases_id, "project_id": project_id, "value": case_set})
    plans = []
    for snapshot_digest, proposal_ids in aliases.items():
        requests = [{"request_id": new_id("request"), "case_ref": case["id"], "arm": arm,
                     "snapshot_digest": active["snapshot_id"] if arm == "base" else snapshot_digest,
                     "repeat_index": i} for case in case_set["cases"] for arm in ("base", "candidate")
                    for i in range(protocol["repeat_count"])]
        plan = {"plan_id": new_id("plan"), "project_id": project_id, "base_digest": active["snapshot_id"],
                "candidate_digest": snapshot_digest, "expected_generation": active["generation"],
                "protocol_ref": protocol_id, "protocol_hash": digest(protocol), "case_set_ref": cases_id,
                "case_set_hash": digest(case_set), "evaluator_ref": protocol["evaluator"]["id"],
                "evaluator_config_hash": digest(protocol["evaluator"]["config"]),
                "repeat_count": protocol["repeat_count"], "acceptance_scope": protocol["comparison_scope"], "requests": requests,
                "proposal_ids": proposal_ids, "scoring_policy": protocol["scoring_policy"],
                "purpose": "validation", "update_mode": "none"}
        validate("EvaluationPlan", plan)
        store.put("evaluation_plans", plan["plan_id"], plan)
        plans.append(plan)
    frozen = {"id": round_id, "project_id": project_id, "base_digest": active["snapshot_id"],
              "expected_generation": active["generation"], "candidates": candidates, "protocol_ref": protocol_id,
              "case_set_ref": cases_id, "plan_ids": [p["plan_id"] for p in plans],
              "selection_rule": protocol["selection_rule"], "max_parallel": max_parallel,
              "proposal_snapshots": [{"proposal_id": c["proposal_id"], "candidate_digest": c["candidate_digest"]} for c in candidates]}
    store.put("evaluation_inputs", round_id, frozen)
    by_case = {c["id"]: c for c in case_set["cases"]}
    requests = [r for p in plans for r in p["requests"]]
    outcomes = {}
    try:
        with ThreadPoolExecutor(max_workers=min(max_parallel, len(requests))) as pool:
            futures = {pool.submit(_one_request, store, project_id, r, snapshots[r["snapshot_digest"]], by_case[r["case_ref"]],
                                   execute_fn, evaluate_fn, protocol["allowed_sources"], protocol["scoring_policy"]): r for r in requests}
            for future in as_completed(futures):
                request = futures[future]
                try:
                    outcomes[request["request_id"]] = future.result()
                except Exception as exc:
                    outcomes[request["request_id"]] = _unknown(request, f"Request exception: {_error(exc)}")
    except Exception as exc:
        for request in requests:
            outcomes.setdefault(request["request_id"], _unknown(request, f"Scheduling exception: {_error(exc)}"))
    # Keep usage written before a later persistence/scheduling failure as well.
    request_ids = {r["request_id"] for r in requests}
    used = [u for u in store.list("usage", project_id=project_id) if u.get("request_id") in request_ids]
    for request in requests:
        row = outcomes.setdefault(request["request_id"], _unknown(request, "Missing scheduled result"))
        row["usage_refs"] = sorted(u["usage_id"] for u in used if u["request_id"] == request["request_id"])
    validations = []
    for plan in plans:
        results = [outcomes.get(r["request_id"], _unknown(r, "Missing scheduled result")) for r in plan["requests"]]
        for result in results:
            validate("EvaluationResult", result)
            store.put("evaluation_results", result["request_id"], result)
        gates, status, rows = _gates(store, plan, results, case_set, protocol, len(requests), list(outcomes.values()))
        validation = {"validation_id": new_id("validation"), "project_id": project_id, "plan_id": plan["plan_id"],
                      "plan_hash": digest(plan), "protocol_hash": plan["protocol_hash"], "base_digest": plan["base_digest"],
                      "candidate_digest": plan["candidate_digest"], "expected_active_generation": plan["expected_generation"],
                      "evaluator_ref": plan["evaluator_ref"], "evaluator_config_hash": plan["evaluator_config_hash"],
                      "case_set_hash": plan["case_set_hash"], "results": results, "all_requests_accounted": True,
                      "status": status, "gate_results": gates,
                      "usage_refs": sorted({u for r in results for u in r["usage_refs"]}),
                      "reasons": [g["gate"] for g in gates if g["passed"] is not True], "evidence_cutoff": now_iso()}
        validate("ValidationRecord", validation)
        store.put("validations", validation["validation_id"], validation)
        validations.append(validation)
    ranked = _rank(store, validations, {p["plan_id"]:p for p in plans}, case_set)
    selection = {"selection_id": new_id("selection"), "project_id": project_id, "base_digest": active["snapshot_id"],
                 "expected_generation": active["generation"], "selection_rule_ref": round_id,
                 "selection_rule_hash": digest(protocol["selection_rule"]),
                 "candidate_validations": [{"candidate_digest": v["candidate_digest"], "validation_ref": v["validation_id"], "status": v["status"],
                                            "proposal_ids": aliases[v["candidate_digest"]]} for v in validations],
                 "decision": "selected" if ranked else "keep_current",
                 "selected_candidate_digest": ranked[0][3] if ranked else None,
                 "selected_validation_ref": ranked[0][4] if ranked else None,
                 "reasons": ["Applied frozen quality/cost/digest order; unknown cost ranked last." if ranked else "No accepted candidate."]}
    validate("SelectionRecord", selection)
    store.put("selections", selection["selection_id"], selection)
    return {"comparison_id": round_id, "plan_ids": [p["plan_id"] for p in plans],
            "validation_ids": [v["validation_id"] for v in validations], "selection_id": selection["selection_id"],
            "usage_ids": sorted({u for v in validations for u in v["usage_refs"]})}


def verify_validation(store, validation):
    """Recheck stored evidence/plan binding, not just the status or JSON shape."""
    validate("ValidationRecord", validation)
    plan = store.get("evaluation_plans", validation["plan_id"])
    validate("EvaluationPlan", plan)
    _require(digest(plan) == validation["plan_hash"], "plan_changed", "Plan hash mismatch")
    protocol_record = store.get("protocols", plan["protocol_ref"])
    cases_record = store.get("case_sets", plan["case_set_ref"])
    _require(protocol_record["project_id"] == plan["project_id"] == cases_record["project_id"],
             "project_mismatch", "Protocol/cases belong to another project")
    protocol, cases = protocol_record["value"], cases_record["value"]
    _require(digest(protocol) == plan["protocol_hash"] and digest(cases) == plan["case_set_hash"],
             "protocol_changed", "Protocol or cases changed")
    for key in ("project_id", "base_digest", "candidate_digest", "protocol_hash", "case_set_hash", "evaluator_ref", "evaluator_config_hash"):
        _require(validation[key] == plan[key], "validation_binding", f"Mismatched {key}")
    _require(validation["expected_active_generation"] == plan["expected_generation"], "validation_binding", "Wrong generation")
    _require(plan["evaluator_ref"] == protocol["evaluator"]["id"] and plan["evaluator_config_hash"] == digest(protocol["evaluator"]["config"]),
             "validation_binding", "Evaluator identity/config changed")
    scoring_policy = resolve_scoring_policy(protocol.get("scoring_policy"), default="available_artifact")
    _require(plan.get("scoring_policy", scoring_policy) == scoring_policy, "scoring_policy_binding", "Plan scoring policy differs from its frozen protocol")
    expected = {r["request_id"]: r for r in plan["requests"]}
    expected_pairs = {(c["id"], arm, i) for c in cases["cases"] for arm in ("base", "candidate")
                      for i in range(protocol["repeat_count"])}
    actual_pairs = {(r["case_ref"], r["arm"], r["repeat_index"]) for r in plan["requests"]}
    _require(actual_pairs == expected_pairs and len(plan["requests"]) == len(expected_pairs)
             and plan["repeat_count"] == protocol["repeat_count"]
             and all(r["snapshot_digest"] == plan["base_digest" if r["arm"] == "base" else "candidate_digest"] for r in plan["requests"]),
             "plan_coverage", "Frozen plan does not cover every case/arm/repeat exactly once")
    results = validation["results"]
    _require(len(expected) == len(plan["requests"]) and len(results) == len(expected)
             and {r["request_id"] for r in results} == set(expected), "incomplete_results", "Requests missing or duplicated")
    for result in results:
        req = expected[result["request_id"]]
        _require(result == store.get("evaluation_results", result["request_id"]), "result_changed", "Stored result changed")
        _require(all(result[k] == req[k] for k in ("case_ref", "snapshot_digest")), "result_binding", "Result belongs to another case/version")
        execution = store.get("evaluation_returns", result["execution_ref"]) if result["execution_ref"] else None
        terminal = parse_execution(execution["returned"], execution["error"], scoring_policy) if execution else {
            "execution_status": "unknown", "eligible": False}
        _require(result.get("execution_status", terminal["execution_status"]) == terminal["execution_status"],
                 "execution_status_binding", "Recorded terminal state differs from execution evidence")
        if result["outcome"] == "unknown":
            continue
        _require(execution is not None and terminal["eligible"], "scoring_policy_binding", "Execution is ineligible under frozen scoring policy")
        _require(execution["project_id"] == plan["project_id"] and execution["request"] == req
                 and execution["stage"] == "execute" and execution["error"] is None,
                 "execution_binding", "Missing/invalid actual execution")
        _require(len(result["evidence_refs"]) == 1, "evidence_binding", "Expected actual evaluator return reference")
        evidence = store.get("evaluation_returns", result["evidence_refs"][0])
        out = evidence["returned"]
        _require(evidence["project_id"] == plan["project_id"] and evidence["request"] == req
                 and evidence["stage"] == "evaluate" and evidence["error"] is None
                 and bool(out.get("evidence")) and out.get("source") in protocol["allowed_sources"]
                 and all(result[k] == out.get(k) for k in ("score", "outcome", "source")),
                 "evidence_binding", "Actual evaluator return does not support result")
        _require(set(result["usage_refs"]) == {execution["usage_ref"], evidence["usage_ref"]}, "usage_binding", "Invocation usage missing or wrong")
    return plan, protocol, cases
