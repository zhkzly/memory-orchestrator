"""N06–N08: evidence-backed learning into candidates, never into active memory."""
from __future__ import annotations

import copy
import json
import re
import time

from .candidates import apply_candidate, skill_view
from .context import terms as _terms
from .evidence import build_packet, expand_packet, feedback_view, index_episodes, validate_citations
from .evidence import _refresh, _fits, validate_packet
from .lineage import require_learning_source
from .goals import associate_goals, missing_user_goals
from .maintenance import (eligible_experience as _eligible_experience, retained_evidence as _retained_evidence,
    latest_experiences, failure_signature, signature_score, fold_related,
    active_memory_relations, maintenance_inputs, check_maintenance, apply_maintenance)
from .schemas import DomainError, digest, load_contracts, new_id, now_iso, validate
from .telemetry import measure_stage


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _unique(items):
    return list(dict.fromkeys(items))


def _policy(policy):
    integer_fields = ("max_expansions", "max_experiences", "max_read_requests", "max_related_experiences",
                      "max_related_episodes", "max_related_chars", "candidate_count", "max_operations", "max_skills", "max_asset_bytes")
    for name in integer_fields:
        if type(policy.get(name)) is not int or policy[name] < (1 if name == "candidate_count" else 0):
            raise DomainError("learning_policy", f"Explicit integer policy.{name} is required.")
    for name in ("packet", "expanded_packet"):
        if not isinstance(policy.get(name), dict):
            raise DomainError("learning_policy", f"Explicit policy.{name} is required.")
        for field in ("max_chars", "max_fragment_chars", "max_catalog_refs", "token_budget"):
            if type(policy[name].get(field)) is not int or policy[name][field] < (0 if field == "max_catalog_refs" else 1):
                raise DomainError("learning_policy", f"Invalid policy.{name}.{field}.")
    if not isinstance(policy.get("evaluation_scope"), str) or not policy["evaluation_scope"].strip():
        raise DomainError("learning_policy", "Describe the evaluation scope before learning.")
    policy = copy.deepcopy(policy)
    if "trajectory_processing" not in policy:
        width = policy["packet"]["max_fragment_chars"]
        policy["trajectory_processing"] = {
            "direct_max_input_tokens": policy["packet"]["token_budget"],
            "plan": {"max_scan_events": 4096, "max_segments": 32, "max_groups_per_segment": 8,
                     "packet": copy.deepcopy(policy["packet"]),
                     "role_max_chars": {"user": width, "action": width, "feedback": width,
                                        "note": min(width, 400), "result": min(width, 800), "unknown": min(width, 400)}},
            "summary_limits": {"max_observations": 3, "max_quote_chars": 240},
        }
    processing = policy["trajectory_processing"]
    if processing is None:
        raise DomainError("learning_policy", "Trajectory processing is the learning input path; null does not disable it.")
    if processing is not None:
        if (not isinstance(processing, dict) or type(processing.get("direct_max_input_tokens")) is not int
                or processing["direct_max_input_tokens"] < 0 or not isinstance(processing.get("plan"), dict)):
            raise DomainError("learning_policy", "Trajectory processing needs a plan and a nonnegative direct input threshold.")
        summary = processing.get("summary_limits", {})
        if any(type(summary.get(key)) is not int or summary[key] < 1
               for key in ("max_observations", "max_quote_chars")):
            raise DomainError("learning_policy", "Declare positive local observation and exact-quote limits.")
    return copy.deepcopy(policy)


def _extraction_inputs(episodes, index, packet, related, policy, expansions=0):
    return {
        "task_requirements": [{"episode_id": ep["episode_id"], "task_id": ep["task"]["task_id"],
            "revision": ep["task"]["revision"], "provided_requirement_refs": [f["ref_id"] for f in packet["fragments"]
                if f["episode_id"] == ep["episode_id"] and f["kind"] == "task"]} for ep in episodes],
        "evidence_packet": packet, "available_feedback": feedback_view(index, packet),
        "related_experiences": _visible_related(related, packet),
        "extraction_limits": {"max_experiences": policy["max_experiences"],
            "max_read_requests": policy["max_read_requests"], "max_evidence_expansions": policy["max_expansions"],
            "remaining_evidence_expansions": policy["max_expansions"] - expansions},
    }


def _summary_excerpts(draft, packet, limits):
    """Pure validation plus exact subrange derivation; prose is never raw evidence."""
    draft = validate("LocalSummaryDraft", draft)
    errors, observations, fragments = [], [], {}
    supplied = {f["ref_id"]: f for f in packet["fragments"]}
    if len(draft["observations"]) > limits["max_observations"]:
        errors.append({"path": "$.observations", "maximum": limits["max_observations"],
                       "actual_count": len(draft["observations"])})
    for position, observation in enumerate(draft["observations"]):
        refs = []
        sources = []
        for number, excerpt in enumerate(observation["excerpts"]):
            source = supplied.get(excerpt["ref_id"])
            quote = excerpt["quote"]
            path = f"$.observations[{position}].excerpts[{number}]"
            if source is None or not quote or len(quote) > limits["max_quote_chars"]:
                errors.append({"path": path, "ref_id": excerpt["ref_id"],
                    "expected": "A provided original fragment and a nonempty exact substring within max_quote_chars",
                    "max_quote_chars": limits["max_quote_chars"]})
                continue
            offset = source["text"].find(quote)
            if offset < 0:
                errors.append({"path": path + ".quote", "ref_id": excerpt["ref_id"],
                               "expected": "Copy an exact substring from this provided fragment; do not paraphrase the quote"})
                continue
            start = source["range"]["start_byte"] + len(source["text"][:offset].encode("utf-8"))
            end = start + len(quote.encode("utf-8"))
            ref = source["ref_id"].rsplit(":", 2)[0] + f":{start}:{end}"
            fragments[ref] = {**copy.deepcopy(source), "ref_id": ref, "text": quote,
                "range": {"start_byte": start, "end_byte_exclusive": end}}
            refs.append(ref)
            sources.append(source)
        if (sources and observation["kind"] != "intention" and all(
                f.get("structure", {}).get("source_role") in ("assistant", "agent")
                and f.get("structure", {}).get("source_kind") in ("note", "analysis", "thought", "message")
                for f in sources)):
            errors.append({"path": f"$.observations[{position}].kind", "actual": observation["kind"],
                           "expected": "intention: assistant analysis alone is a reported belief, not an observed environment outcome"})
        observations.append({"kind": observation["kind"], "text": observation["text"], "quote_refs": _unique(refs)})
    if errors:
        raise DomainError("summary_evidence", "Local records need exact excerpts from their own provided packet.", {"errors": errors})
    return observations, list(fragments.values())


def _packet_union(index, packets, limits, *, anchors_only=False):
    """One projected source view; never substitute a summary for an original range."""
    combined = copy.deepcopy(packets[0])
    combined["packet_id"] = new_id("packet")
    combined["token_budget"] = limits["token_budget"]
    bodies = {}
    for packet in packets:
        for fragment in packet["fragments"]:
            if not anchors_only or fragment["kind"] in ("task", "feedback"):
                bodies.setdefault(fragment["ref_id"], fragment)
    combined["fragments"] = list(bodies.values())
    combined["readable_ref_catalog"] = []
    combined["gaps"] = _unique(gap for packet in packets for gap in packet["gaps"])[:24]
    _refresh(combined, index)
    if not anchors_only:
        for packet in packets:
            for locator in packet["readable_ref_catalog"]:
                if len(combined["readable_ref_catalog"]) >= limits["max_catalog_refs"]:
                    break
                if locator["ref_id"] in bodies or locator["ref_id"] in {r["ref_id"] for r in combined["readable_ref_catalog"]}:
                    continue
                trial = copy.deepcopy(combined)
                trial["readable_ref_catalog"].append(locator)
                _refresh(trial, index)
                if _fits(trial, limits):
                    combined = trial
    return combined


def _paired_summary_context(quotes, packet, width):
    """Keep a short matching action/result context without asking the model to copy it."""
    result = {f["ref_id"]: f for f in quotes}
    for source in quotes:
        structure = source.get("structure", {})
        call_id = structure.get("call_id")
        kind = structure.get("source_kind")
        wanted = ("result", "observation") if kind == "action" else ("action",) if kind in ("result", "observation") else ()
        if call_id is None:
            continue
        for other in packet["fragments"]:
            meta = other.get("structure", {})
            if (other["episode_id"] != source["episode_id"] or meta.get("call_id") != call_id
                    or meta.get("source_kind") not in wanted):
                continue
            if any(left is not None and right is not None and left != right for left, right in (
                (source["task_revision"], other["task_revision"]),
                (structure.get("task_id"), meta.get("task_id")), (structure.get("goal_id"), meta.get("goal_id")))):
                continue
            text = other["text"][:width]
            start = other["range"]["start_byte"]
            end = start + len(text.encode("utf-8"))
            ref = other["ref_id"].rsplit(":", 2)[0] + f":{start}:{end}"
            result.setdefault(ref, {**copy.deepcopy(other), "ref_id": ref, "text": text,
                                   "range": {"start_byte": start, "end_byte_exclusive": end}})
    return list(result.values())


def _learning_packet(store, index, episodes, related, policy, model, call, result, error_record):
    """The single N06 input path: role-aware plan, direct or bounded local analysis."""
    from .evidence import build_trajectory_plan
    processing = policy["trajectory_processing"]
    if not callable(getattr(model, "preview", None)):
        raise DomainError("model_boundary", "Learning requires full-request preview from the same structured model boundary.")
    with measure_stage(store, index["project_id"], "index", subject_ref=result["cycle_id"]):
        plan = build_trajectory_plan(index, limits=processing["plan"], dependency_limits=policy.get("dependency_lookup"))
    state = {"mode": "planned", "planned_coverage": copy.deepcopy(plan["coverage"]),
             "analyzed_event_count": 0, "analyzed_packet_count": 0, "segments": [], "summary_count": 0,
             "limitations": ["Local model records are unverified interpretations; quoted text alone is original evidence."]}
    result["trajectory_processing"] = state
    if not plan["segments"]:
        state["mode"] = "abstained"
        raise DomainError("trajectory_no_summary", "No trajectory group fits the declared source projection budget.")
    raw = _packet_union(index, plan["segments"], policy["packet"])
    if (plan["coverage"]["scan_complete"] and plan["coverage"]["omitted_events"] == 0
            and _fits(raw, policy["packet"])):
        direct = model.preview("extract_v1", _extraction_inputs(episodes, index, raw, related, policy))
        if direct["fits"] and direct["estimated_input_tokens"] <= processing["direct_max_input_tokens"]:
            state.update(mode="direct", direct_packet_id=raw["packet_id"])
            return validate_packet(raw, index)
    if not model.limits.get("token_budget"):
        state["mode"] = "abstained"
        raise DomainError("trajectory_no_summary", "Long-trajectory analysis requires explicit cumulative token and stage budgets.")
    anchors = _packet_union(index, plan["segments"], policy["packet"], anchors_only=True)
    minimum = anchors
    if not minimum["fragments"]:
        minimum = copy.deepcopy(raw)
        minimum["fragments"] = raw["fragments"][:1]
        minimum["readable_ref_catalog"] = []
        _refresh(minimum, index)
    extraction_preview = model.preview("extract_v1", _extraction_inputs(episodes, index, minimum, related, policy))
    if not extraction_preview["fits"]:
        state.update(mode="abstained", blocking_reason=extraction_preview["blocking_reason"])
        raise DomainError("trajectory_no_summary", "The extraction prompt and task anchors already exceed the declared budget; local calls were not started.")
    state["segments"] = [{"source_packet_id": packet["packet_id"], "scope": copy.deepcopy(scope), "status": "not_started"}
                         for packet, scope in zip(plan["segments"], plan["segment_scopes"])]
    summaries, seen_events = [], set()
    for segment, scope, row in zip(plan["segments"], plan["segment_scopes"], state["segments"]):
        caps = {**processing["summary_limits"], "source_scope": scope}
        inputs = {"evidence_packet": segment, "summary_limits": caps}
        preview = model.preview("summarize_trace_v1", inputs)
        # Shrink only this segment's original source set; a focus ranking would
        # silently import unrelated events and therefore is not a chunk boundary.
        smaller = copy.deepcopy(processing["plan"]["packet"])
        for _ in range(4):
            if preview["fits"]:
                break
            smaller["max_chars"] = max(1, smaller["max_chars"] * 2 // 3)
            smaller["max_fragment_chars"] = max(1, smaller["max_fragment_chars"] * 2 // 3)
            smaller["max_catalog_refs"] = min(smaller["max_catalog_refs"], 2)
            allowed = {f["ref_id"].rsplit(":", 2)[0] for f in segment["fragments"] + segment["readable_ref_catalog"]}
            try:
                segment = build_packet(index, limits=smaller, allowed_refs=allowed,
                    role_max_chars=processing["plan"]["role_max_chars"])
            except DomainError as exc:
                if exc.code != "evidence_budget_exhausted":
                    raise
                break
            caps["source_scope"] = {**scope, "packet_id": segment["packet_id"]}
            inputs = {"evidence_packet": segment, "summary_limits": caps}
            preview = model.preview("summarize_trace_v1", inputs)
        row["source_packet_id"] = segment["packet_id"]
        row["scope"] = copy.deepcopy(caps["source_scope"])
        if not preview["fits"]:
            row.update(status="not_analyzed_budget", reason=preview["blocking_reason"])
            continue
        store.put("evidence_packets", segment["packet_id"], segment)
        try:
            draft = call("summarize_trace_v1", inputs,
                         check=lambda value: _summary_excerpts(value, segment, processing["summary_limits"]))
        except DomainError as exc:
            row.update(status="failed", error_code=exc.code,
                       report_ref=result["report_ids"][-1] if result["report_ids"] else None)
            error_record(exc, "summarize_trace_v1")
            state["limitations"].append("Local analysis stopped after a failed attempt; previous valid records remain available.")
            break
        row["report_ref"] = result["report_ids"][-1]
        row["status"] = draft["status"]
        state["analyzed_packet_count"] += 1
        seen_events.update((f["episode_id"], f["event_id"]) for f in segment["fragments"]
                           if f.get("structure", {}).get("namespace") == "event")
        state["analyzed_event_count"] = len(seen_events)
        if draft["status"] == "abstained" or not draft["observations"]:
            continue
        observations, quotes = _summary_excerpts(draft, segment, processing["summary_limits"])
        quotes = _paired_summary_context(quotes, segment, processing["summary_limits"]["max_quote_chars"])
        summary = {"summary_id": new_id("summary"), "source_packet_id": segment["packet_id"],
                   "report_ref": row["report_ref"], "observations": observations, "unknowns": draft["unknowns"]}
        summaries.append((summary, quotes, segment))
    for row in state["segments"]:
        if row["status"] == "not_started":
            row["status"] = "not_analyzed_after_stop"
    if not summaries:
        state["mode"] = "abstained"
        raise DomainError("trajectory_no_summary", "No grounded local records fit the declared learning budget.")
    combined = anchors
    combined["trajectory_summaries"] = []
    combined["gaps"].append("Only budget-selected local records and exact excerpts were analyzed; omitted results and unselected segments remain unknown.")
    for summary, quotes, segment in summaries:
        trial = copy.deepcopy(combined)
        bodies = {f["ref_id"]: f for f in trial["fragments"]}
        bodies.update((f["ref_id"], f) for f in quotes)
        trial["fragments"] = list(bodies.values())
        trial["trajectory_summaries"].append(summary)
        _refresh(trial, index)
        if (_fits(trial, policy["packet"]) and
                model.preview("extract_v1", _extraction_inputs(episodes, index, trial, related, policy))["fits"]):
            combined = trial
        else:
            state["limitations"].append("A completed local record was not included in the extractor input budget: " + summary["summary_id"])
    if not combined["trajectory_summaries"]:
        state["mode"] = "abstained"
        raise DomainError("trajectory_no_summary", "Local records cannot fit together with the actual extraction prompt and task anchors.")
    # Original ranges remain available for bounded follow-up reads. A locator is
    # not promoted to evidence merely because a local model saw its body.
    offered = []
    from .evidence import _catalog
    # Include selected original ranges even if their local summary failed or did
    # not use them. Availability is bounded; it never changes the analyzed count.
    for segment in plan["segments"]:
        offered.extend(_catalog(f) for f in segment["fragments"])
        offered.extend(segment["readable_ref_catalog"])
    visible = {f["ref_id"] for f in combined["fragments"]}
    for locator in offered:
        if len(combined["readable_ref_catalog"]) >= policy["packet"]["max_catalog_refs"]:
            break
        if locator["ref_id"] in visible or locator["ref_id"] in {r["ref_id"] for r in combined["readable_ref_catalog"]}:
            continue
        trial = copy.deepcopy(combined)
        trial["readable_ref_catalog"].append(locator)
        _refresh(trial, index)
        if (_fits(trial, policy["packet"]) and
                model.preview("extract_v1", _extraction_inputs(episodes, index, trial, related, policy))["fits"]):
            combined = trial
    _refresh(combined, index)
    state.update(mode="partial", summary_count=len(combined["trajectory_summaries"]))
    return validate_packet(combined, index)


def _visible_related(records, packet):
    provided = {fragment["ref_id"] for fragment in packet["fragments"]}
    result = copy.deepcopy(records)
    for record in result:
        for item in record.get("retained_evidence", []):
            item["body_provided_in_current_packet"] = item["ref_id"] in provided
        record["evidence_rule"] = "Historical references do not count as new original evidence unless their body is in the current packet."
    return result


def _source_provenance(store, episode, contexts):
    context = contexts.get(episode['context_ref']) if episode['context_ref'] is not None else None
    run = require_learning_source(store, episode)['run']
    return {'episode_id': episode['episode_id'], 'source': episode['source'],
            'source_snapshot_ref': episode['source_snapshot_ref'], 'context_ref': episode['context_ref'],
            'provided_context': None if context is None else {key: context.get(key) for key in
                ('manifest_id', 'snapshot_digest', 'selected_skills', 'supplied_hash')},
            'observed_consumption': 'unknown' if run is None else run['consumption_observability'],
            'consumption_event_refs': [] if run is None else run['consumption_events'],
            'consumption_evidence_level': None if run is None else 'reported_by_execution_function'}


def find_related(experiences, task, project_id, *, limit, max_chars, failure_signature=None, relations=()):
    """Rank scoped terms and failures; contradictions enter together or not at all."""
    latest = latest_experiences([r for r in experiences if r.get("project_id") == project_id
                                and "draft" in r and "canonical_key" in r])
    folded = fold_related(latest, relations) if relations else latest
    by_id = {r["record_id"]: r for r in folded}
    query = _terms(task)
    ranked = []
    for record in folded:
        draft = record["draft"]
        terms = _terms(_json([draft["title"], draft["scope"], draft["conditions"], draft["guidance"]]))
        lexical = len(query & terms)
        failure = signature_score(failure_signature, record.get("failure_signature"))
        score = lexical + failure
        record["retrieval_score"] = {"lexical": lexical, "failure_signature": failure, "total": score}
        if score:
            ranked.append((score, bool(record["retained_evidence"]), record))
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]["record_id"]))
    chosen = []
    selected = set()
    for _, _, record in ranked:
        group = [by_id[rid] for rid in record.get("conflict_record_ids", [record["record_id"]]) if rid not in selected]
        if len(chosen) + len(group) <= limit and len(_json(chosen + group)) <= max_chars:
            chosen.extend(copy.deepcopy(group)); selected.update(r["record_id"] for r in group)
    return chosen


def _save_experience(store, draft, packet, index, cycle_id):
    canonical = digest({key: draft[key] for key in ("kind", "scope", "guidance")})
    previous = [x for x in store.list("experiences", index["project_id"])
                if x.get("canonical_key") == canonical and _eligible_experience(store, x)]
    newest = max(previous, key=lambda r: (r["created_at"], r["record_id"])) if previous else None
    references = set(draft["supporting_refs"] + draft["counterevidence_refs"] + draft["boundary_refs"])
    for fact in draft["observed_facts"]:
        references.update(fact["evidence_refs"])
    fragments = {f["ref_id"]: f for f in packet["fragments"]}
    sources = {fragments[ref]["episode_id"] for ref in references}
    signature = failure_signature(index, episode_ids=sources, max_chars=index.get("signature_max_chars"))
    tasks, unknown_episodes, support_tasks = set(), set(), set()
    for ref in references:
        base = ref.rsplit(":", 2)[0]
        source = index["records"][base]
        if source["task_id"] is None:
            unknown_episodes.add(source["episode_id"])
        else:
            tasks.add(source["task_id"])
            if ref in draft["supporting_refs"]:
                support_tasks.add(source["task_id"])
    if (newest and newest["draft"] == draft and sources.issubset(newest["source_episode_ids"])
            and signature == newest.get("failure_signature") and _retained_evidence(previous) == newest.get("retained_evidence", [])):
        return newest["record_id"]
    for record in previous:
        sources.update(record["source_episode_ids"])
        tasks.update(record.get("known_task_ids", []))
        unknown_episodes.update(record.get("unknown_task_episode_ids", []))
        support_tasks.update(record.get("known_support_task_ids", []))
    record_id = new_id("experience")
    record = {"record_id": record_id, "experience_id": "experience_" + canonical[:24],
              "canonical_key": canonical, "project_id": index["project_id"], "cycle_id": cycle_id,
              "draft": copy.deepcopy(draft), "packet_id": packet["packet_id"],
              "source_episode_ids": sorted(sources), "source_episode_count": len(sources),
              "known_task_ids": sorted(tasks), "known_task_count": len(tasks),
              "known_support_task_ids": sorted(support_tasks), "known_support_task_count": len(support_tasks),
              "unknown_task_episode_ids": sorted(unknown_episodes),
              "supersedes": newest["record_id"] if newest else None,
              "status": "unverified_experience", "created_at": now_iso()}
    record["retained_evidence"] = _retained_evidence([*previous, record])
    record["failure_signature"] = signature
    store.put("experiences", record_id, record)
    return record_id


def _diagnosis_targets(diagnosis, view):
    targets, errors = [], []
    stale = False
    allowed = [{"skill_id": sid, "revision": skill["revision"], "rule_ids": [r["rule_id"] for r in skill["rules"]]}
               for sid, skill in view.items()]
    for index, target in enumerate(diagnosis["targets"]):
        skill = view.get(target["skill_id"])
        if skill is None or skill["revision"] != target["revision"]:
            stale = True
            errors.append({"path": f"$.targets[{index}]", "actual": copy.deepcopy(target),
                           "expected": "An existing Skill ID and its exact base revision; ADD has no existing target."})
        elif target["rule_id"] is not None and target["rule_id"] not in {r["rule_id"] for r in skill["rules"]}:
            errors.append({"path": f"$.targets[{index}].rule_id", "actual": target["rule_id"],
                           "expected": [r["rule_id"] for r in skill["rules"]]})
        targets.append(target["skill_id"])
    if errors:
        raise DomainError("stale_diagnosis_target" if stale else "invalid_diagnosis_rule",
            "Diagnosis targets must refer to existing rules in the supplied base.",
            {"errors": errors, "actual_targets": copy.deepcopy(diagnosis["targets"]), "allowed_targets": allowed,
             "correction": "For a new Skill ADD, use targets=[]; keep route=skill_patch and describe the new capability in expected_behavior. Do not invent a Skill ID or a revision such as 'new'. For existing edits, use only allowed_targets with the exact revision/rule ID."})
    return _unique(targets)


def _check_necessity(diagnosis, view, packet, limits):
    decision = diagnosis.get("necessity")
    if decision is None:
        raise DomainError("necessity_missing", "New diagnoses require an explicit necessity decision.")
    compared = decision["compared_skill_refs"]
    expected = {(sid, row["revision"]) for sid, row in view.items()}
    actual = {(row["skill_id"], row["revision"]) for row in compared}
    errors = []
    if len(compared) != len(actual) or actual - expected or len(actual) > limits["max_compared_skills"]:
        errors.append({"path": "$.necessity.compared_skill_refs", "allowed": sorted(expected)})
    targets = {(t["skill_id"], t["revision"]) for t in diagnosis["targets"]}
    if targets - actual:
        errors.append({"path": "$.necessity.compared_skill_refs", "message": "Every proposed existing target must be compared", "required": sorted(targets)})
    if decision["verdict"] == "proceed":
        if decision["repeatable"] is not True or not decision["behavior_delta"].strip() or not decision["evidence_refs"]:
            errors.append({"path": "$.necessity", "message": "Proceed needs grounded reusable behavior difference; it is still a hypothesis."})
        if decision["allow_add"] and (not decision["capability_gap"].strip() or actual != expected):
            errors.append({"path": "$.necessity.allow_add", "message": "ADD requires a stated gap and comparison of every provided existing capability."})
    for i, check in enumerate(diagnosis["check_plan"]):
        if "check_ref" not in check:
            errors.append({"path": f"$.check_plan[{i}].check_ref", "message": "Use a supplied public check reference or explicit null."})
    validate_citations(decision, packet)
    if errors:
        raise DomainError("necessity_invalid", "Necessity judgment exceeds the supplied comparison.", {"errors": errors})


def _check_verification_refs(value, catalog):
    available = {row["check_ref"]: row for row in catalog}
    errors = []
    for i, item in enumerate(value["check_plan"]):
        ref = item.get("check_ref")
        if "check_ref" not in item or ref is not None and (ref not in available or available[ref]["purpose"] != item["purpose"]):
            errors.append({"path": f"$.check_plan[{i}].check_ref", "actual": ref,
                "allowed_refs": [key for key, row in available.items() if row["purpose"] == item["purpose"]],
                "correction": "Use a supplied check with the same purpose, or null when required material is unavailable."})
    if errors:
        raise DomainError("verification_reference", "Check obligations must bind to the public supplied directory.", {"errors": errors})


def _learning_index(store, episodes, policy, contexts=None):
    """Resolve declared archived parents before any body can reach a model."""
    # Admission follows all known ancestors independently of the optional body
    # neighborhood budget. An unindexed ancestor cannot masquerade as harmless
    # merely because this packet is configured not to read dependency bodies.
    while True:
        unresolved = _unique(ref for ep in episodes for ref in
                             require_learning_source(store, ep).get("unindexed_trace_refs", []))
        if not unresolved: break
        from .trace import ensure_trace_index
        for ref in unresolved:
            _, checkpoint = ensure_trace_index(store, ref, policy.get("trace_index") or {})
            if not checkpoint["index_complete"]:
                raise DomainError("needs_index", "Source ancestry needs another bounded indexing step before learning",
                                  {"trace_ref": ref, "checkpoint": checkpoint})
    caps = policy.get("dependency_lookup")
    if caps is not None and any(type(caps.get(k)) is not int or caps[k] < 0 for k in ("max_hops", "max_events")):
        raise DomainError("dependency_budget", "Explicit nonnegative dependency limits are required")
    contexts = {} if contexts is None else contexts
    loaded, extras, depth = {ep["episode_id"] for ep in episodes}, 0, 0
    while True:
        for ep in episodes:
            if ep["context_ref"] and ep["context_ref"] not in contexts:
                contexts[ep["context_ref"]] = store.get("contexts", ep["context_ref"])
        index = index_episodes(episodes, feedback=[f for ep in episodes for f in store.feedback_for(ep["episode_id"])],
                               contexts=contexts, store=store, trace_limits=policy.get("trace_index"))
        refs = _unique([ref for checkpoint in index["trace_progress"] for ref in checkpoint["parent_episode_refs"]]
            + [event["parent_episode_id"] for ep in episodes for event in ep["events"] if event.get("parent_episode_id")])
        pending = []
        for identifier in refs:
            if identifier in loaded: continue
            try: parent = store.get("episodes", identifier)
            except DomainError as exc:
                if exc.code != "NOT_FOUND": raise
                index["gaps"].append(f"Parent episode {identifier} is unavailable; no identity or body inferred")
                continue
            if parent["project_id"] != index["project_id"]:
                raise DomainError("project_mismatch", "Parent belongs to a different project")
            require_learning_source(store, parent)
            if caps and depth < caps["max_hops"] and extras < caps["max_events"]:
                pending.append(parent); loaded.add(identifier); extras += 1
            else:
                index["gaps"].append(f"Parent episode {identifier} admitted but not read under this dependency budget")
        if not pending: return index
        episodes.extend(pending); depth += 1


def learn(store, episode_ids, model, *, policy, verification_catalog=None):
    """Extract, diagnose and attempt each candidate against one fixed base.

    Model and task feedback remain explicitly reported evidence. This function
    checks source availability and identities, not truth of natural-language claims.
    """
    policy = _policy(policy)
    public_checks = [] if verification_catalog is None else copy.deepcopy(verification_catalog)
    if (not isinstance(public_checks, list) or any(not isinstance(row, dict)
            or set(row) - {"check_ref", "purpose", "description", "evidence_kind", "case_ids", "asset_test_ids"}
            or not isinstance(row.get("check_ref"), str) or not isinstance(row.get("purpose"), str)
            for row in public_checks)
            or len({row["check_ref"] for row in public_checks}) != len(public_checks)):
        raise DomainError("verification_catalog", "Supply a unique public check directory without private grading material.")
    requested_ids = _unique(episode_ids)
    if not requested_ids:
        raise DomainError("empty_evidence", "At least one episode identity is required.")
    episodes = [store.get("episodes", identifier) for identifier in requested_ids]
    project = episodes[0]["project_id"]
    if any(ep["project_id"] != project for ep in episodes):
        raise DomainError("project_mismatch", "Learning cannot mix projects.")
    for episode in episodes:
        require_learning_source(store, episode)
    if not callable(getattr(model, "generate", None)) or not isinstance(getattr(model, "limits", None), dict):
        raise DomainError("model_boundary", "Use a structured model boundary with explicit limits.")
    active = store.ensure_project(project)
    base = store.snapshot(active["snapshot_id"])
    view = skill_view(base)
    cycle_id = new_id("learning")
    result = {"cycle_id": cycle_id, "project_id": project, "base_digest": base["snapshot_id"],
              "contract_source": load_contracts()["source"], "model_limits": copy.deepcopy(model.limits),
              "expected_generation": active["generation"], "requested_episode_ids": requested_ids,
              "source_episode_ids": requested_ids[:], "experience_ids": [], "candidate_ids": [],
              "diagnosis_id": None, "usage_ids": [], "report_ids": [], "errors": [],
              "goal_binding_ids": [], "maintenance_review_ids": [],
              "candidate_slots": [{"slot": i, "status": "not_started", "candidate_id": None}
                                  for i in range(policy["candidate_count"])],
              "status": "planned", "policy": policy, "created_at": now_iso()}
    store.put("learning_cycles", cycle_id + ":plan", result)

    def error_record(exc, stage):
        error = {"error_id": new_id("error"), "project_id": project, "cycle_id": cycle_id,
                 "stage": stage, "code": exc.code, "message": exc.message, "details": copy.deepcopy(exc.details)}
        store.put("errors", error["error_id"], error)
        result["errors"].append(error)

    def persist_call(prompt_id, inputs, response=None, exc=None):
        report_id = new_id("modelreport")
        detail = response if exc is None else exc.details
        detail = copy.deepcopy(detail)
        usage = detail.get("usage", [])
        if not isinstance(usage, list):
            raise DomainError("invalid_model_usage", "Model boundary must return one usage list per call.")
        for entry in usage:
            usage_id = entry.get("usage_id")
            if not usage_id or usage_id in result["usage_ids"]:
                raise DomainError("duplicate_model_usage", "Each attempted call needs a unique usage identity.")
            stored = {"usage_id": usage_id, "project_id": project,
                      "exclusive_stage": {"summarize_trace_v1": "extract", "extract_v1": "extract", "diagnose_v1": "diagnose", "propose_v1": "propose",
                                          "goal_binding_v1": "index", "maintain_experience_v1": "extract"}[prompt_id],
                      "purpose": "learning", "run_or_proposal_id": cycle_id,
                      "tokens": {key: entry.get(key) for key in ("input_tokens", "output_tokens", "total_tokens")},
                      "time": entry.get("elapsed_seconds"), "monetary_cost": entry.get("monetary_cost"),
                      "currency": entry.get("currency"),
                      "status": "reported" if entry.get("measurement") == "provider_reported" else "missing",
                      "price_version": entry.get("price_version"), "raw": copy.deepcopy(entry)}
            store.put("usage", usage_id, stored)
            result["usage_ids"].append(usage_id)
        report = {"report_id": report_id, "project_id": project, "cycle_id": cycle_id,
                  "prompt_digest": digest(load_contracts()["prompts"][prompt_id]),
                  "prompt_id": prompt_id, "inputs": copy.deepcopy(inputs),
                  "status": "returned" if exc is None else "error", "result": detail,
                  "error_code": None if exc is None else exc.code, "created_at": now_iso()}
        store.put("reports", report_id, report)
        result["report_ids"].append(report_id)

    def call(prompt_id, inputs, *, check=None):
        stage_name = {"summarize_trace_v1": "extract", "extract_v1": "extract", "diagnose_v1": "diagnose", "propose_v1": "propose",
                      "goal_binding_v1": "index", "maintain_experience_v1": "extract"}[prompt_id]
        with measure_stage(store, project, stage_name, subject_ref=cycle_id) as meter:
            call_started = time.monotonic()
            try:
                response = model.generate(prompt_id, inputs, check=check)
            except DomainError as exc:
                for entry in exc.details.get("usage", []):
                    if isinstance(entry.get("elapsed_seconds"), (float, int)):
                        meter.exclude(entry["elapsed_seconds"])
                persist_call(prompt_id, inputs, exc=exc)
                raise
            except BaseException:
                # No returned usage exists for this interrupted operation. Keep
                # its billing unknown, and do not rename provider wait as local work.
                meter.exclude(time.monotonic() - call_started)
                raise
            for entry in response.get("usage", []):
                if isinstance(entry.get("elapsed_seconds"), (float, int)):
                    meter.exclude(entry["elapsed_seconds"])
            persist_call(prompt_id, inputs, response=response)
        schema_id = load_contracts()["prompts"][prompt_id]["output_schema"]
        return validate(schema_id, response["value"])

    def finish(status, reason=None):
        result["status"] = status
        result["reason"] = reason
        result["completed_at"] = now_iso()
        if "index" in work:
            result["read_stats"] = {key: sum(r.stats[key] for r in work["index"].get("trace_readers", []))
                                    for key in ("body_bytes", "range_reads", "metadata_rows")}
        store.put("learning_cycles", cycle_id, result)
        return copy.deepcopy(result)

    stage = "evidence"
    work = {}
    try:
        task_text = "\n".join(ep["task"]["description"] + "\n" + "\n".join(e["text"][:1000] for e in ep["events"][:3]) for ep in episodes)
        with measure_stage(store, project, "index", subject_ref=cycle_id):
            source_index = _learning_index(store, episodes, policy)
            signature = failure_signature(source_index, max_chars=policy["packet"]["max_chars"])
        eligible_memories, excluded_memories = [], []
        for memory in store.list("experiences", project):
            if not _eligible_experience(store, memory):
                excluded_memories.append(memory["record_id"])
            else:
                eligible_memories.append(memory)
        with measure_stage(store, project, "select", subject_ref=cycle_id):
            related = find_related(eligible_memories, task_text, project,
                                   limit=policy["max_related_experiences"], max_chars=policy["max_related_chars"],
                                   failure_signature=signature, relations=active_memory_relations(store, project))
        result["retrieval"] = {"failure_signature": signature, "selected_record_ids": [r["record_id"] for r in related],
                               "signature_hits": sum(r["retrieval_score"]["failure_signature"] > 0 for r in related)}
        known_episode_ids = {ep["episode_id"] for ep in episodes}
        related_ids = _unique(eid for record in related for eid in record["source_episode_ids"] if eid not in known_episode_ids)
        for eid in related_ids[:policy["max_related_episodes"]]:
            ep = store.get("episodes", eid)
            if ep["project_id"] != project:
                raise DomainError("project_mismatch", "Related experience references a different project.")
            require_learning_source(store, ep)
            episodes.append(ep)
        result["source_episode_ids"] = [ep["episode_id"] for ep in episodes]
        contexts = {ep["context_ref"]: store.get("contexts", ep["context_ref"]) for ep in episodes if ep["context_ref"]}
        feedback = [fb for ep in episodes for fb in store.feedback_for(ep["episode_id"])]
        with measure_stage(store, project, "index", subject_ref=cycle_id):
            index = _learning_index(store, episodes, policy, contexts)
        result["source_episode_ids"] = [ep["episode_id"] for ep in episodes]
        work["index"] = index
        index["signature_max_chars"] = policy["packet"]["max_chars"]
        result["trace_checkpoint_ids"] = [row["checkpoint_id"] for row in index["trace_progress"]]
        if any(missing_user_goals(index)):
            stage = "goal_binding_v1"
            index, result["goal_binding_ids"] = associate_goals(store, index, call,
                limits=policy.get("goal_binding", {}), cycle_id=cycle_id, model_report_ref=lambda: result["report_ids"][-1])
        if not related:
            index["gaps"].insert(0, "Related-memory lookup found no in-budget matches; this does not establish absence of counterexamples.")
        if excluded_memories:
            index["gaps"].insert(0, "Prior memories with frozen or learning-disabled execution sources were excluded from this learning input.")
        if len(related_ids) > policy["max_related_episodes"]:
            index["gaps"].insert(0, "Additional related source episodes omitted by explicit retrieval budget.")
        stage = "summarize_trace_v1"
        packet = _learning_packet(store, index, episodes, related, policy, model, call, result, error_record)
        expansions = 0
        while True:
            store.put("evidence_packets", packet["packet_id"], packet)
            stage = "extract_v1"
            extraction = call(stage, _extraction_inputs(episodes, index, packet, related, policy, expansions),
                              check=lambda value: validate_citations(value, packet))
            processing_state = result["trajectory_processing"]
            if processing_state["mode"] == "direct":
                processing_state["analyzed_event_count"] = packet["coverage"]["selected_event_count"]
                processing_state["analyzed_packet_count"] += 1
            validate_citations(extraction, packet)
            if len(extraction["experiences"]) > policy["max_experiences"] or len(extraction["read_requests"]) > policy["max_read_requests"]:
                raise DomainError("extraction_limit_exceeded", "Extraction exceeds its visible cycle limits.")
            if extraction["status"] == "abstained":
                return finish("abstained", extraction["reason"])
            if extraction["status"] != "needs_more_evidence":
                break
            if expansions >= policy["max_expansions"]:
                return finish("abstained", "Explicit evidence-expansion budget exhausted.")
            try:
                with measure_stage(store, project, "index", subject_ref=cycle_id):
                    packet = expand_packet(index, packet, extraction["read_requests"], limits=policy["expanded_packet"])
            except DomainError as exc:
                if exc.code == "evidence_budget_exhausted":
                    error_record(exc, "expand_evidence")
                    return finish("abstained", "Requested evidence cannot fit the declared budget.")
                raise
            expansions += 1
        if not extraction["experiences"]:
            return finish("noop", "No reusable experience was extracted.")
        with measure_stage(store, project, "extract", subject_ref=cycle_id):
            for draft in extraction["experiences"]:
                result["experience_ids"].append(_save_experience(store, draft, packet, index, cycle_id))
        result["experience_ids"] = _unique(result["experience_ids"])
        new_records = [store.get("experiences", ref) for ref in result["experience_ids"]]
        # Exact canonical revisions already have a host consolidation rule; the
        # semantic model compares different experiences, not an item with itself.
        comparison_records = [store.get("experiences", r["record_id"]) for r in
                              latest_experiences([*related, *new_records])]
        live_relations = active_memory_relations(store, project)
        if len(comparison_records) > 1 or live_relations:
            stage = "maintain_experience_v1"
            caps = policy.get("maintenance", {})
            if any(type(caps.get(k)) is not int or caps[k] < 1 for k in ("max_chars", "max_pairs", "max_actions")):
                raise DomainError("maintenance_budget", "Explicit positive maintenance limits are required.")
            with measure_stage(store, project, "extract", subject_ref=cycle_id):
                comparison = maintenance_inputs(comparison_records, live_relations,
                                                max_chars=caps["max_chars"], max_pairs=caps["max_pairs"])
            if comparison["pairs"] or comparison["existing_relations"]:
                ids = set(result["experience_ids"])
                try:
                    maintenance = call(stage, {"new_experiences": [r for r in comparison["records"] if r["record_id"] in ids],
                        "related_experiences": [r for r in comparison["records"] if r["record_id"] not in ids],
                        "comparison_evidence": {k: v for k, v in comparison.items() if k != "records"},
                        "existing_relations": comparison["existing_relations"], "maintenance_limits": caps},
                        check=lambda draft: check_maintenance(draft, comparison, max_actions=caps["max_actions"]))
                    with measure_stage(store, project, "extract", subject_ref=cycle_id):
                        review = apply_maintenance(store, project, maintenance, comparison, cycle_id=cycle_id,
                            model_report_ref=result["report_ids"][-1], max_actions=caps["max_actions"])
                except DomainError as exc:
                    review = {"review_id": new_id("maintenance"), "project_id": project, "cycle_id": cycle_id,
                        "model_report_ref": result["report_ids"][-1] if result["report_ids"] else None,
                        "status": "error", "origin": "model_proxy", "record_ids": list(comparison["record_hashes"]),
                        "relation_ids": [], "error_code": exc.code, "created_at": now_iso()}
                    review = validate("MaintenanceReview", review)
                    store.put("maintenance_reviews", review["review_id"], review)
                    result["maintenance_review_ids"].append(review["review_id"])
                    raise
                result["maintenance_review_ids"].append(review["review_id"])
                live_relations = active_memory_relations(store, project)
                related = find_related([*eligible_memories, *new_records], task_text, project,
                    limit=policy["max_related_experiences"], max_chars=policy["max_related_chars"],
                    failure_signature=signature, relations=live_relations)
        stage = "diagnose_v1"
        necessity_limits = policy.get("necessity", {})
        if type(necessity_limits.get("max_compared_skills")) is not int or necessity_limits["max_compared_skills"] < 0:
            raise DomainError("necessity_budget", "Explicit max_compared_skills is required.")
        if len(view) > necessity_limits["max_compared_skills"]:
            return finish("abstained", "Existing capability comparison exceeds its declared budget; no unexamined ADD.")
        def check_diagnosis(value):
            validate_citations(value, packet)
            _diagnosis_targets(value, view)
            _check_necessity(value, view, packet, necessity_limits)
            _check_verification_refs(value, public_checks)

        diagnosis = call(stage, {
            "evaluation_scope": policy["evaluation_scope"],
            "experiences": extraction["experiences"], "evidence_packets": [packet],
            "source_provenance": [_source_provenance(store, ep, contexts) for ep in episodes],
            "target_snapshot": {"snapshot_id": base["snapshot_id"], "project_id": project, "skills": view},
            "related_skills_and_relations": {"skills": view, "relations": store.list("relations", project),
                "related_experiences": _visible_related(related, packet), "relation_warning": "Observed co-use is not causal influence."},
            "available_feedback": feedback_view(index, packet), "learning_limits": model.limits,
            "verification_catalog": public_checks,
            "existing_capability_catalog": {"skills": view, "all_bodies_provided": True,
                "memory_relations": live_relations, "judgment_origin": "model_proxy"},
            "necessity_limits": necessity_limits,
        }, check=check_diagnosis)
        validate_citations(diagnosis, packet)
        allowed_targets = _diagnosis_targets(diagnosis, view)
        _check_necessity(diagnosis, view, packet, necessity_limits)
        _check_verification_refs(diagnosis, public_checks)
        diagnosis_id = new_id("diagnosis")
        diagnosis_record = {"diagnosis_id": diagnosis_id, "project_id": project,
            "cycle_id": cycle_id, "base_digest": base["snapshot_id"], "packet_id": packet["packet_id"],
            "draft": diagnosis, "decision_origin": "model_proxy", "allowed_skill_ids": allowed_targets, "created_at": now_iso()}
        store.put("diagnoses", diagnosis_id, diagnosis_record)
        result["diagnosis_id"] = diagnosis_id
        if diagnosis["necessity"]["verdict"] != "proceed":
            for slot in result["candidate_slots"]: slot["status"] = "noop"
            return finish("noop" if diagnosis["necessity"]["verdict"] == "noop" else "abstained",
                          "Necessity judgment: " + diagnosis["necessity"]["verdict"])
        if diagnosis["route"] != "skill_patch":
            for slot in result["candidate_slots"]:
                slot["status"] = "noop"
            return finish("abstained" if diagnosis["route"] == "abstain" else "noop", diagnosis["abstain_reason"] or diagnosis["route"])
        allowed_refs = [f["ref_id"] for f in packet["fragments"]]
        operations = ["ADD", "PATCH", "RETIRE", "NOOP"] if diagnosis["necessity"]["allow_add"] else ["PATCH", "RETIRE", "NOOP"]
        def check_patch(value):
            validate_citations(value, packet)
            _check_verification_refs(value, public_checks)
            if any(op["op"] not in operations for op in value["operations"]):
                raise DomainError("necessity_operation", "necessity.allow_add=false excludes ADD from this proposal.")
            if any("check_ref" not in c for c in value["check_plan"]):
                raise DomainError("verification_reference", "Each generated check needs check_ref or explicit null.")
        for slot in result["candidate_slots"]:
            stage = f"propose_v1:{slot['slot']}"
            try:
                patch = call("propose_v1", {
                    "change_intent": diagnosis, "base_snapshot_digest": base["snapshot_id"],
                    "allowed_skill_contents": {key: view[key] for key in allowed_targets},
                    "editable_fields_and_asset_paths": {"skill_ids": allowed_targets,
                        "rule_ids": {key: [rule["rule_id"] for rule in view[key]["rules"]] for key in allowed_targets},
                        "asset_roots": ["scripts", "references", "templates"],
                        "current_assets": {path: body for path, body in base["assets"].items() if path.split("/", 1)[0] in allowed_targets}},
                    "operation_constraints": {"allowed_operations": operations,
                        "allowed_evidence_refs": allowed_refs, "known_readonly_skill_ids": list(view),
                        "max_operations": policy["max_operations"], "max_skills": policy["max_skills"],
                        "max_asset_bytes": policy["max_asset_bytes"], "project_id": project,
                        "atomic_operation_count": "Each PATCH edit, ADD, RETIRE and asset edit counts once.",
                        "rule_anchors": "Rule IDs refer to the original expected_revision; newly added rules cannot be targeted in this patch."},
                    "evaluation_scope": policy["evaluation_scope"], "learning_limits": model.limits,
                    "verification_catalog": public_checks,
                }, check=check_patch)
                check_patch(patch)
                candidate = apply_candidate(store, project, patch, base_digest=base["snapshot_id"],
                    expected_generation=active["generation"], allowed_evidence_refs=allowed_refs,
                    allowed_skill_ids=allowed_targets, max_operations=policy["max_operations"],
                    max_skills=policy["max_skills"], max_asset_bytes=policy["max_asset_bytes"],
                    diagnosis_ref=diagnosis_id, diagnosis_hash=digest(diagnosis_record))
                if candidate is None:
                    slot["status"] = "noop"
                else:
                    slot.update(status="candidate", candidate_id=candidate["proposal_id"])
                    result["candidate_ids"].append(candidate["proposal_id"])
            except DomainError as exc:
                error_record(exc, stage)
                slot.update(status="error", error_code=exc.code)
        if result["candidate_ids"]:
            return finish("partial" if result["errors"] else "proposed")
        return finish("error" if result["errors"] else "noop")
    except DomainError as exc:
        error_record(exc, stage)
        if exc.code == "needs_index": return finish("needs_index", exc.message)
        return finish("abstained" if exc.code in ("evidence_budget_exhausted", "model_budget_exhausted",
                                                 "trajectory_no_summary") else "error", exc.message)
