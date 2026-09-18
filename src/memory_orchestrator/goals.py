"""Bounded model suggestions for missing goals; raw identities stay unchanged."""
from copy import deepcopy
import re

from .evidence import _resolve, _pieces, _refresh, build_packet, expand_packet, validate_citations, _matching, _trace_transition
from .schemas import DomainError, digest, new_id, now_iso, validate


def missing_user_goals(index):
    return (r["base_ref"] for r in index["records"].values()
            if r["source_event"] and r["source_role"] == "user" and r["source_kind"] == "instruction"
            and ((r["goal_id"] is None and r["task_id"] is None) or r["task_revision"] is None))


def _catalog(index, annotations, focus, limit):
    rows, seen = [], set()
    first = min((index["records"][ref]["position"] for ref in focus), default=-1)
    episode_ids = {index["records"][ref]["episode_id"] for ref in focus}
    transitions = list(index["goal_transitions"])
    for row in _matching(index, user_goals=True):
        if "_reader" in row and row["episode_id"] in episode_ids and row["position"] < first:
            transitions.append(_trace_transition(index, row))
    for transition in transitions:
        source = index["records"][transition["event_ref"]]
        if source["episode_id"] not in episode_ids or source["position"] >= first: continue
        key = (transition["goal_id"], transition["revision"])
        if None in key or key in seen:
            continue
        seen.add(key)
        rows.append({"goal_id": key[0], "revision": key[1], "origin": "observed", "anchor_ref": transition["event_ref"]})
    for annotation in annotations:
        key = (annotation["goal_id"], annotation["revision"])
        if key not in seen:
            seen.add(key)
            rows.append({"goal_id": key[0], "revision": key[1], "origin": "model_proxy",
                         "anchor_ref": annotation["anchor_user_ref"]})
    rows = rows[-limit:]
    for row in rows:
        row["anchor_excerpt"] = next(_pieces(index["records"][row["anchor_ref"]], 160, 0))
    return rows


def check_goal_draft(draft, index, packet, catalog, limits):
    draft = validate("GoalBindingDraft", draft)
    errors = []
    for field in ("status", "read_requests", "reason"):
        if field not in draft:
            errors.append({"path": "$.'" + field + "'", "message": "New goal responses require this field"})
    if errors:
        raise DomainError("goal_output", "Incomplete goal-association output", {"errors": errors})
    validate_citations({"read_requests": draft["read_requests"]}, packet)
    if len(draft["bindings"]) > limits["max_bindings"] or len(draft["read_requests"]) > limits["max_read_requests"]:
        errors.append({"path": "$", "message": "Goal output exceeds the visible limits"})
    if draft["status"] == "needs_more_evidence" and (not draft["read_requests"] or draft["bindings"]):
        errors.append({"path": "$.status", "message": "Request evidence without committing partial bindings"})
    if draft["status"] != "needs_more_evidence" and draft["read_requests"]:
        errors.append({"path": "$.read_requests", "message": "Only needs_more_evidence can request reading"})
    if draft["status"] == "abstained" and (draft["bindings"] or not draft["reason"].strip()):
        errors.append({"path": "$.status", "message": "Abstention needs a reason and no bindings"})
    provided = {f["ref_id"]: _resolve(index, f["ref_id"], body=False)[0]
                for f in [*packet["fragments"], *[r["anchor_excerpt"] for r in catalog]]}
    known_goals = {row["goal_id"] for row in catalog}
    known_goals.update(r["goal_id"] or r["task_id"] for r in provided.values() if r["goal_id"] or r["task_id"])
    known_revisions = {(row["goal_id"], row["revision"]) for row in catalog}
    local_goals = set()
    for i, binding in enumerate(draft["bindings"]):
        path = f"$.bindings[{i}]"
        anchor = provided.get(binding.get("anchor_user_ref"))
        if anchor is None or anchor["source_role"] != "user" or anchor["source_kind"] != "instruction":
            errors.append({"path": path + ".anchor_user_ref", "message": "Use a provided user instruction as the boundary"})
            continue
        if binding["anchor_user_ref"] not in limits.get("target_user_refs", provided):
            errors.append({"path": path + ".anchor_user_ref", "message": "Anchor is outside this association window"})
        if binding.get("reason") is None or set(binding["event_refs"] + binding["evidence_refs"]) - set(provided):
            errors.append({"path": path, "message": "Give a reason and cite only provided event bodies"})
            continue
        goal, revision = binding["goal_id"], binding["revision"]
        new_goal = re.fullmatch(r"new:[a-z0-9]+(?:-[a-z0-9]+)*", goal) is not None
        new_revision = re.fullmatch(r"new:[a-z0-9]+(?:-[a-z0-9]+)*", revision) is not None
        if not new_goal and goal not in known_goals:
            errors.append({"path": path + ".goal_id", "message": "Reference a catalog goal or declare new:<local_slug>"})
        if not new_revision and (goal, revision) not in known_revisions and anchor["task_revision"] != revision:
            errors.append({"path": path + ".revision", "message": "Reference that goal's revision or declare new:<local_slug>"})
        if binding["relation"] == "resumes" and goal not in known_goals and goal not in local_goals:
            errors.append({"path": path + ".relation", "message": "Cannot resume a goal that has no earlier supplied identity"})
        for ref in binding["event_refs"]:
            event = provided[ref]
            if event["episode_id"] != anchor["episode_id"] or event["position"] < anchor["position"]:
                errors.append({"path": path + ".event_refs", "message": "A later/unrelated anchor cannot govern this event"})
            if any(row["position"] > anchor["position"] and row["position"] <= event["position"]
                   for row in _matching(index, episode_id=event["episode_id"], user_goals=True)):
                errors.append({"path": path + ".anchor_user_ref", "message": "A newer user boundary requires its own explicit association"})
            observed_goal = event["goal_id"] or event["task_id"]
            if observed_goal is not None and observed_goal != goal:
                errors.append({"path": path + ".goal_id", "message": "Do not override an observed goal/task identity"})
            if event["task_revision"] is not None and event["task_revision"] != revision:
                errors.append({"path": path + ".revision", "message": "Do not override an observed revision"})
        local_goals.add(goal)
    if errors:
        raise DomainError("goal_binding", "Goal suggestions exceed their observed anchors", {"errors": errors})
    return draft


def associate_goals(store, index, call, *, limits, cycle_id, model_report_ref):
    missing = missing_user_goals(index)
    for field in ("max_events", "max_bindings", "max_read_requests", "max_expansions", "max_catalog_goals"):
        if type(limits.get(field)) is not int or limits[field] < (0 if field == "max_expansions" else 1):
            raise DomainError("goal_budget", f"Explicit limits.{field} is required")
    if not isinstance(limits.get("packet"), dict):
        raise DomainError("goal_budget", "Explicit packet limits are required")
    annotations, records = [], []
    from itertools import batched
    exhausted = False
    for batch in batched(missing, limits["max_events"]):
        focus = list(batch)
        packet = build_packet(index, limits=limits["packet"], focus_refs=focus)
        # A later user request cannot be supplied as evidence for an earlier
        # association window. Known previous goals have separately cited excerpts.
        ceilings = {}
        for ref in focus:
            row = index["records"][ref]
            ceilings[row["episode_id"]] = max(ceilings.get(row["episode_id"], -1), row["position"])
        for eid, position in list(ceilings.items()):
            later = next((row["position"] for row in _matching(index, episode_id=eid, user_goals=True)
                          if row["position"] > position), None)
            ceilings[eid] = later - 1 if later is not None else float("inf")
        def in_window(item):
            row, _ = _resolve(index, item["ref_id"], body=False)
            return row["episode_id"] in ceilings and row["position"] <= ceilings[row["episode_id"]]
        for key in ("fragments", "readable_ref_catalog"):
            packet[key] = [item for item in packet[key] if in_window(item)]
        _refresh(packet, index)
        catalog = _catalog(index, annotations, focus, limits["max_catalog_goals"])
        for attempt in range(limits["max_expansions"] + 1):
            user_events = [f for f in packet["fragments"]
                           if f["structure"]["source_role"] == "user" and f["structure"]["source_kind"] == "instruction"]
            effective_limits = {**limits, "target_user_refs": [f["ref_id"] for f in user_events
                                 if _resolve(index, f["ref_id"])[0]["base_ref"] in focus]}
            inputs = {"user_events": user_events, "goal_catalog": catalog,
                      "indexed_event_refs": packet["fragments"],
                      "readable_ref_catalog": packet["readable_ref_catalog"], "binding_limits": effective_limits}
            try:
                draft = call("goal_binding_v1", inputs,
                             check=lambda value: check_goal_draft(value, index, packet, catalog, effective_limits))
                draft = check_goal_draft(draft, index, packet, catalog, effective_limits)
            except DomainError as exc:
                exhausted = exc.code == "model_budget_exhausted"
                draft = {"status": "abstained", "bindings": [], "read_requests": [],
                         "reason": "Host retained unresolved association after " + exc.code,
                         "unknowns": [exc.message]}
                break
            if draft["status"] != "needs_more_evidence":
                break
            if attempt == limits["max_expansions"]:
                draft = {"status": "abstained", "bindings": [], "read_requests": [],
                         "reason": "Goal evidence expansion budget exhausted", "unknowns": draft["unknowns"]}
                break
            try:
                packet = expand_packet(index, packet, draft["read_requests"], limits=limits["packet"])
            except DomainError as exc:
                draft = {"status": "abstained", "bindings": [], "read_requests": [],
                         "reason": "Host could not supply requested goal evidence: " + exc.code, "unknowns": [exc.message]}
                break
        record_id = new_id("goal_binding")
        resolved, names = [], {}
        for binding in draft["bindings"]:
            anchor, _ = _resolve(index, binding["anchor_user_ref"])
            goal = binding["goal_id"]
            if goal.startswith("new:"):
                goal = names.setdefault(goal, "derived-goal:" + digest([index["project_id"], anchor["base_ref"], goal])[:24])
            revision = binding["revision"]
            if revision.startswith("new:"):
                key = (goal, revision)
                revision = names.setdefault(key, "derived-revision:" + digest([goal, anchor["base_ref"], revision])[:24])
            evidence = [_resolve(index, ref)[0]["base_ref"] for ref in binding["evidence_refs"]]
            for ref in binding["event_refs"]:
                event, _ = _resolve(index, ref)
                row = {"binding_ref": record_id, "event_ref": event["base_ref"], "goal_id": goal,
                       "revision": revision, "relation": binding["relation"], "anchor_user_ref": anchor["base_ref"],
                       "evidence_refs": evidence, "origin": "model_proxy"}
                resolved.append(row); annotations.append(row)
        record = {"record_id": record_id, "project_id": index["project_id"], "cycle_id": cycle_id,
                  "episode_ids": [ep["episode_id"] for ep in index["episodes"]],
                  "source_hashes": {ep["episode_id"]: digest({"episode": ep,
                       "trace_raw_hash": next((r.manifest["raw_sha256"] for r in index.get("trace_readers", [])
                                               if r.manifest["episode_id"] == ep["episode_id"]), None)}) for ep in index["episodes"]},
                  "model_report_ref": model_report_ref(), "draft": draft, "resolved_bindings": resolved,
                  "status": draft["status"], "unresolved_refs": [ref for ref in focus if ref not in {r["event_ref"] for r in resolved}], "created_at": now_iso()}
        record = validate("GoalBindingRecord", record)
        store.put("goal_bindings", record_id, record); records.append(record_id)
        if record["unresolved_refs"]:
            index["gaps"].append(f"Derived goal association {record_id} left this window unresolved: {draft['reason']}")
        if exhausted:
            index["gaps"].append("Remaining goal windows were not associated because the global model-call budget ended.")
            break
    index["goal_annotations"] = annotations
    return index, records
