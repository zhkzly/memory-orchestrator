"""Observed-event indexing and bounded, source-verifiable learning packets.

Nothing here reads native-agent state or executes tools. A packet contains exact
UTF-8 ranges from caller material; classification helps selection, not truth.
"""
from __future__ import annotations

import copy
import json
import math
import re
from collections import defaultdict

from .schemas import DomainError, digest, new_id, validate


_FAILURE = re.compile(r"error|fail(?:ed|ure)?|exception|错误|失败|丢失|不通过", re.I)
_RECOVERY = re.compile(r"recovery|retry|修复|恢复|重试|另一运行", re.I)
_COUNTER = re.compile(r"counterexample|反例|妨碍", re.I)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _unique(values):
    return list(dict.fromkeys(values))


def _kind(event):
    if event["kind"] == "instruction":
        return "task"
    if event["kind"] == "feedback":
        return "feedback"
    if _COUNTER.search(event["text"]):
        return "counterexample"
    if _RECOVERY.search(event["text"]):
        return "recovery"
    if event["kind"] == "action":
        return "action"
    return "observation"


def _structure(record):
    """One projection for declared event metadata, including its source order."""
    return {"source_kind": record["source_kind"], "namespace": record["namespace"],
            "source_position": record["position"],
            **{key: record[key] for key in ("task_id", "goal_id", "source_role", "call_id",
                                            "parent_event_id", "parent_episode_id")}}


def index_episodes(episodes, *, feedback=(), contexts=None):
    """Index explicit identities; do not inherit the final goal onto old events.

    ``records`` is an internal read registry. Its text is never itself a model
    input. Adaptation-ineligible feedback is not copied into the registry.
    """
    episodes = [validate("EpisodeRecord", ep) for ep in episodes]
    if not episodes:
        raise DomainError("empty_evidence", "At least one episode is required.")
    project = episodes[0]["project_id"]
    if any(ep["project_id"] != project for ep in episodes):
        raise DomainError("project_mismatch", "An evidence index cannot mix projects.")
    ids = [ep["episode_id"] for ep in episodes]
    if len(ids) != len(set(ids)):
        raise DomainError("duplicate_episode", "Repeated episode identities must be resolved before indexing.")
    records, transitions, pairs, gaps, allowed_feedback = {}, [], [], [], []
    episode_map = {ep["episode_id"]: ep for ep in episodes}

    def add(ep, event, position, *, namespace="event", kind=None):
        base = "ev:" + digest([project, ep["episode_id"], namespace, event["event_id"]])[:24]
        if base in records:
            raise DomainError("duplicate_event", "Event identities must be unique within an episode.")
        records[base] = {
            "base_ref": base, "episode_id": ep["episode_id"], "event_id": event["event_id"],
            "kind": kind or _kind(event), "text": event["text"],
            "source_kind": event["kind"], "namespace": namespace,
            "raw_ref": event.get("source_ref") or f"episode:{ep['episode_id']}/{namespace}:{event['event_id']}",
            "raw_hash": digest(event["text"]), "task_revision": event.get("task_revision"),
            "task_id": event.get("task_id"), "goal_id": event.get("goal_id"),
            "source_role": event.get("source_role"), "source": copy.deepcopy(ep["source"]),
            "position": position, "source_event": namespace == "event",
            "call_id": event.get("call_id"), "parent_event_id": event.get("parent_event_id"),
            "parent_episode_id": event.get("parent_episode_id"),
        }
        return records[base]

    for ep in episodes:
        eid = ep["episode_id"]
        gaps.extend(f"{eid}: {gap}" for gap in ep["gaps"])
        gaps.append(f"{eid}: source={ep['source']['kind']}; reported material is not independent verification.")
        for field in ("source_snapshot_ref", "context_ref"):
            if ep[field] is None:
                gaps.append(f"{eid}: {field}=unknown")
        if ep["context_ref"] is not None:
            if contexts is None:
                gaps.append(f"{eid}: context content not supplied; consumption unknown")
            elif ep["context_ref"] not in contexts or contexts[ep["context_ref"]].get("project_id") != project:
                raise DomainError("context_mismatch", "Known context must belong to the source project.")
        add(ep, {"event_id": "task", "kind": "instruction", "text": ep["task"]["description"],
                 "task_id": ep["task"]["task_id"], "task_revision": ep["task"]["revision"]},
            -1, namespace="requirement", kind="task")
        seen_goals, previous, previous_ref = {}, None, None
        calls = defaultdict(lambda: {"actions": [], "results": []})
        event_ids = {event["event_id"] for event in ep["events"]}
        for position, event in enumerate(ep["events"]):
            item = add(ep, event, position)
            if item["task_revision"] is None:
                gaps.append(f"{eid}/{event['event_id']}: task revision unknown; final requirements not inherited")
            if event.get("source_role") == "user" and event["kind"] == "instruction":
                key = (event.get("goal_id") or event.get("task_id"), event["task_revision"])
                if None in key:
                    relation = "ambiguous"
                elif previous is None or previous == key:
                    relation = "continues"
                elif previous[0] == key[0]:
                    relation = "revises"
                elif key in seen_goals:
                    relation = "resumes"
                else:
                    relation = "switches"
                basis = [previous_ref] if previous_ref is not None else []
                if relation == "resumes":
                    basis.append(seen_goals[key])
                transitions.append({"event_ref": item["base_ref"], "episode_id": eid,
                                    "goal_id": key[0], "revision": key[1], "relation": relation,
                                    "basis_refs": _unique(basis)})
                if None not in key:
                    previous = key
                    previous_ref = item["base_ref"]
                    seen_goals.setdefault(key, item["base_ref"])
            if event["call_id"] is not None:
                bucket = calls[event["call_id"]]
                if event["kind"] == "action":
                    bucket["actions"].append(event["event_id"])
                elif event["kind"] in ("observation", "result"):
                    bucket["results"].append(event["event_id"])
            parent_episode = event.get("parent_episode_id") or eid
            parent = event.get("parent_event_id")
            if parent and (parent_episode not in episode_map or parent not in {
                e["event_id"] for e in episode_map[parent_episode]["events"]
            }):
                gaps.append(f"{eid}/{event['event_id']}: parent event not provided")
        if len(event_ids) != len(ep["events"]):
            raise DomainError("duplicate_event", "Event identities must be unique within an episode.")
        for call_id, pair in calls.items():
            paired = len(pair["actions"]) == 1 and bool(pair["results"])
            pairs.append({"episode_id": eid, "call_id": call_id, "action_event_ids": pair["actions"],
                          "result_event_ids": pair["results"], "status": "paired" if paired else "ambiguous"})
            if not paired:
                gaps.append(f"{eid}: call {call_id} unmatched or ambiguous; not paired by adjacency")

    for raw_feedback in feedback:
        fb = validate("Feedback", raw_feedback)
        if fb["project_id"] != project:
            raise DomainError("project_mismatch", "Feedback belongs to a different project.")
        if fb["visibility"] != "adaptation":
            gaps.append(f"Feedback {fb['check_id']} withheld: visibility={fb['visibility']}")
            continue
        if fb["subject_ref"] not in episode_map:
            gaps.append(f"Feedback {fb['check_id']} unbound: source episode not provided")
            continue
        ep = episode_map[fb["subject_ref"]]
        known_revisions = {event["task_revision"] for event in ep["events"]} | {ep["task"]["revision"]}
        if fb["task_revision"] is None or fb["task_revision"] not in known_revisions:
            gaps.append(f"Feedback {fb['check_id']}: task revision binding unknown; do not apply to other revisions")
        if fb["binding_status"] != "bound" or fb["evaluated_state_digest"] is None:
            gaps.append(f"Feedback {fb['check_id']}: checked-state binding incomplete")
        allowed_feedback.append(fb)
        add(ep, {"event_id": fb["check_id"], "kind": "feedback", "text": _json(fb),
                 "task_revision": fb["task_revision"], "source_ref": f"feedback:{fb['check_id']}"},
            len(ep["events"]), namespace="feedback", kind="feedback")
    for ep in episodes:
        if not any(f["subject_ref"] == ep["episode_id"] for f in allowed_feedback):
            gaps.append(f"{ep['episode_id']}: no separately supplied adaptation feedback; outcome unknown")
    return {"project_id": project, "episodes": episodes, "records": records,
            "feedback": allowed_feedback, "goal_transitions": transitions,
            "call_pairs": pairs, "gaps": _unique(gaps)}


def _limits(limits):
    for name in ("max_chars", "max_fragment_chars", "max_catalog_refs", "token_budget"):
        value = limits.get(name)
        if type(value) is not int or value < (0 if name == "max_catalog_refs" else 1):
            raise DomainError("invalid_budget", f"Explicit integer {name} is required.")
    return limits


def _piece(record, start, end):
    raw = record["text"].encode("utf-8")
    return {"ref_id": f"{record['base_ref']}:{start}:{end}", "episode_id": record["episode_id"],
            "event_id": record["event_id"], "kind": record["kind"], "raw_ref": record["raw_ref"],
            "raw_hash": record["raw_hash"], "text": raw[start:end].decode("utf-8"),
            "range": {"start_byte": start, "end_byte_exclusive": end},
            "task_revision": record["task_revision"], "structure": _structure(record)}


def _pieces(record, width, extra):
    text = record["text"]
    match = _FAILURE.search(text) or _RECOVERY.search(text)
    starts = ([max(0, match.start() - width // 4)] if match else []) + [0, max(0, len(text) - width)]
    starts += [i * width for i in range(1, min(extra + 1, math.ceil(len(text) / width)))]
    for start in _unique(starts):
        end = min(len(text), start + width)
        yield _piece(record, len(text[:start].encode("utf-8")), len(text[:end].encode("utf-8")))


def _catalog(fragment):
    return {**{k: fragment[k] for k in ("ref_id", "episode_id", "task_revision", "raw_ref", "raw_hash", "range", "structure")},
            "available": True}


def _resolve(index, ref):
    if ref in index["records"]:
        record = index["records"][ref]
        if digest(record["text"]) != record["raw_hash"]:
            raise DomainError("evidence_mismatch", "Indexed original text no longer matches its source hash.")
        return record, _piece(record, 0, len(record["text"].encode("utf-8")))
    try:
        base, start, end = ref.rsplit(":", 2)
        record = index["records"][base]
        if digest(record["text"]) != record["raw_hash"]:
            raise DomainError("evidence_mismatch", "Indexed original text no longer matches its source hash.")
        start, end = int(start), int(end)
        if not 0 <= start <= end <= len(record["text"].encode("utf-8")):
            raise ValueError("out of range")
        return record, _piece(record, start, end)
    except (KeyError, ValueError, UnicodeError, AttributeError) as exc:
        raise DomainError("unsupported_evidence", "Reference is not a valid original range.", {"ref_id": ref}) from exc


def _bindings(index):
    bindings = []
    for ep in index["episodes"]:
        pairs = [(ep["task"]["task_id"], ep["task"]["revision"])]
        pairs += [(e.get("task_id"), e["task_revision"]) for e in ep["events"]]
        for task, revision in _unique(pairs):
            bindings.append({"episode_id": ep["episode_id"], "task_ref": task,
                             "task_revision": revision, "relation": "unknown" if task is None or revision is None else "related_task"})
    known = {(b["task_ref"], b["task_revision"]) for b in bindings if b["relation"] != "unknown"}
    if len(known) == 1:
        for binding in bindings:
            if binding["relation"] != "unknown":
                binding["relation"] = "same_task"
    return bindings


def _relations(packet, index):
    """Disclose relationships only between currently provided/readable events.

    Metadata in a read locator is not permission to cite the unread event body.
    Coverage is explicit when an indexed counterpart is outside this packet.
    """
    visible, provided = {}, {f["ref_id"] for f in packet["fragments"]}
    # A supplied range takes precedence over a locator for the same event.
    for item, available in [(item, True) for item in packet["fragments"]] + [
            (item, item["available"]) for item in packet["readable_ref_catalog"]]:
        if not available:
            continue
        record, _ = _resolve(index, item["ref_id"])
        visible.setdefault(record["base_ref"], item["ref_id"])
    event_bases = {(r["episode_id"], r["event_id"]): ref for ref, r in index["records"].items() if r["source_event"]}
    calls, goals, parents = [], [], []
    for pair in index["call_pairs"]:
        action_bases = [event_bases[(pair["episode_id"], eid)] for eid in pair["action_event_ids"]]
        result_bases = [event_bases[(pair["episode_id"], eid)] for eid in pair["result_event_ids"]]
        action_refs = [visible[ref] for ref in action_bases if ref in visible]
        result_refs = [visible[ref] for ref in result_bases if ref in visible]
        if action_refs or result_refs:
            calls.append({"episode_id": pair["episode_id"], "call_id": pair["call_id"],
                          "action_refs": action_refs, "result_refs": result_refs, "status": pair["status"],
                          "coverage": "complete" if all(ref in visible for ref in action_bases + result_bases) else "partial"})
    for transition in index["goal_transitions"]:
        if transition["event_ref"] not in visible:
            continue
        complete = all(ref in visible for ref in transition["basis_refs"])
        goals.append({"event_ref": visible[transition["event_ref"]], "goal_id": transition["goal_id"],
                      "revision": transition["revision"], "relation": transition["relation"] if complete else "ambiguous",
                      "basis_refs": [visible[ref] for ref in transition["basis_refs"] if ref in visible],
                      "coverage": "complete" if complete else "partial"})
    for base, child_ref in visible.items():
        record = index["records"][base]
        if record["parent_event_id"] is None:
            continue
        identity = (record["parent_episode_id"] or record["episode_id"], record["parent_event_id"])
        parent_base = event_bases.get(identity)
        parent_ref = visible.get(parent_base)
        status = ("missing" if parent_base is None else "outside_packet" if parent_ref is None
                  else "provided" if parent_ref in provided else "readable")
        parents.append({"child_ref": child_ref, "parent_ref": parent_ref, "status": status})
    return {"calls": calls, "goals": goals, "parents": parents}


def _refresh(packet, index):
    selected = {_resolve(index, f["ref_id"])[0]["base_ref"] for f in packet["fragments"]}
    catalog_refs = [c["ref_id"] for c in packet["readable_ref_catalog"]]
    provided = {f["ref_id"] for f in packet["fragments"]}
    packet["omitted_refs"] = [ref for ref in catalog_refs if ref not in provided]
    packet["coverage"] = {
        "selected_event_count": sum(index["records"][ref]["source_event"] for ref in selected),
        "total_event_count": sum(len(ep["events"]) for ep in index["episodes"]),
        "mandatory_roles_present": sorted({f["kind"] for f in packet["fragments"]}),
        "incomplete_reasons": ["Catalog and original ranges are bounded; unlisted material remains in the source index."]
            if len(selected) < len(index["records"]) or any(len(f["text"].encode("utf-8")) < len(_resolve(index, f["ref_id"])[0]["text"].encode("utf-8")) for f in packet["fragments"]) else [],
        "omitted_episode_refs": [ep["episode_id"] for ep in index["episodes"]
                                 if ep["episode_id"] not in {f["episode_id"] for f in packet["fragments"]}],
    }
    if packet.get("projection_version") == 2:
        packet["relations"] = _relations(packet, index)
        relations = packet["relations"]
        if (any(row["coverage"] == "partial" for row in relations["calls"] + relations["goals"])
                or any(row["status"] in ("missing", "outside_packet") for row in relations["parents"])):
            packet["coverage"]["incomplete_reasons"].append(
                "Some relationship endpoints are outside the provided/readable packet; do not infer their bodies or goal transitions.")


def _fits(packet, limits, reserve=0):
    serialized = _json(packet)
    # A declared heuristic, not the model tokenizer. Actual usage is separately reported.
    estimate = math.ceil(len(serialized.encode("utf-8")) / 3)
    return len(serialized) <= limits["max_chars"] - reserve and estimate <= limits["token_budget"]


def build_packet(index, *, limits, focus_refs=()):
    """Select exact snippets; metadata and the read catalog count toward the budget."""
    _limits(limits)
    focus = {_resolve(index, ref)[0]["base_ref"] for ref in focus_refs}
    bindings = _bindings(index)
    revisions = {b["task_revision"] for b in bindings}
    gaps = index["gaps"][:16]
    if len(index["gaps"]) > len(gaps):
        gaps += [f"{len(index['gaps']) - len(gaps)} additional gap annotations remain in the source index."]
    gaps += ["Token estimate = ceil(UTF-8 JSON bytes / 3); not a tokenizer measurement."]
    packet = {
        "projection_version": 2,
        "packet_id": new_id("packet"), "project_id": index["project_id"],
        "episode_refs": [ep["episode_id"] for ep in index["episodes"]], "episode_bindings": bindings,
        "task_revision": next(iter(revisions)) if len(revisions) == 1 else None,
        "source_snapshot_refs": _unique(ep["source_snapshot_ref"] for ep in index["episodes"] if ep["source_snapshot_ref"]),
        "context_refs": _unique(ep["context_ref"] for ep in index["episodes"] if ep["context_ref"]),
        "feedback_ids": [fb["check_id"] for fb in index["feedback"]],
        "fragments": [], "readable_ref_catalog": [], "omitted_refs": [], "gaps": gaps,
        "coverage": {}, "token_budget": limits["token_budget"], "token_count_source": "estimated",
    }
    def rank(record):
        if record["base_ref"] in focus:
            return -1
        if record["kind"] in ("task", "feedback", "recovery", "counterexample") or _FAILURE.search(record["text"]):
            return 0
        if record["kind"] == "action":
            return 1
        return 2
    ordered = sorted(index["records"].values(), key=lambda r: (rank(r), r["position"], r["base_ref"]))
    pieces = {r["base_ref"]: list(_pieces(r, limits["max_fragment_chars"], limits["max_catalog_refs"])) for r in ordered}
    reserve = min(limits["max_chars"] // 4, limits["max_catalog_refs"] * 450)
    for record in ordered:
        fragment = pieces[record["base_ref"]][0]
        proposed = copy.deepcopy(packet)
        proposed["fragments"].append(fragment)
        _refresh(proposed, index)
        if _fits(proposed, limits, reserve):
            packet = proposed
    if not packet["fragments"]:
        for record in ordered:
            candidate = copy.deepcopy(packet)
            candidate["fragments"] = [pieces[record["base_ref"]][0]]
            _refresh(candidate, index)
            if _fits(candidate, limits):
                packet = candidate
                break
    if not packet["fragments"]:
        raise DomainError("evidence_budget_exhausted", "No source fragment fits with its required provenance.")
    # First expose omitted events, then additional ranges of already-read events.
    supplied = {f["ref_id"] for f in packet["fragments"]}
    candidates = [parts[0] for parts in pieces.values()] + [f for parts in pieces.values() for f in parts[1:]]
    for fragment in candidates:
        if fragment["ref_id"] in supplied or len(packet["readable_ref_catalog"]) >= limits["max_catalog_refs"]:
            continue
        proposed = copy.deepcopy(packet)
        proposed["readable_ref_catalog"].append(_catalog(fragment))
        _refresh(proposed, index)
        if _fits(proposed, limits):
            packet = proposed
    return validate_packet(packet, index)


def validate_packet(packet, index):
    packet = validate("EvidencePacket", packet)
    structured = packet.get("projection_version") == 2
    if not structured and ("relations" in packet or any("structure" in item
            for item in packet["fragments"] + packet["readable_ref_catalog"])):
        raise DomainError("evidence_mismatch", "Structural evidence must declare projection_version=2.")
    if packet["project_id"] != index["project_id"] or packet["episode_refs"] != [ep["episode_id"] for ep in index["episodes"]]:
        raise DomainError("project_mismatch", "Packet source identities differ from the original index.")
    if packet["episode_bindings"] != _bindings(index):
        raise DomainError("goal_binding_mismatch", "Packet changed the observed task/revision bindings.")
    revisions = {b["task_revision"] for b in packet["episode_bindings"]}
    expected_metadata = {
        "task_revision": next(iter(revisions)) if len(revisions) == 1 else None,
        "source_snapshot_refs": _unique(ep["source_snapshot_ref"] for ep in index["episodes"] if ep["source_snapshot_ref"]),
        "context_refs": _unique(ep["context_ref"] for ep in index["episodes"] if ep["context_ref"]),
        "feedback_ids": [f["check_id"] for f in index["feedback"]],
        "token_count_source": "estimated",
    }
    for field, expected in expected_metadata.items():
        if packet[field] != expected:
            raise DomainError("evidence_mismatch", f"Packet source metadata changed: {field}")
    for field in ("fragments", "readable_ref_catalog"):
        refs = [item["ref_id"] for item in packet[field]]
        if len(refs) != len(set(refs)):
            raise DomainError("duplicate_reference", "Repeated fragment or catalog references.")
        for item in packet[field]:
            _, expected = _resolve(index, item["ref_id"])
            for key in ("episode_id", "raw_ref", "raw_hash", "range", "task_revision"):
                if item[key] != expected[key]:
                    raise DomainError("evidence_mismatch", f"Original evidence field changed: {key}", {"ref_id": item["ref_id"]})
            if field == "fragments" and any(item[key] != expected[key] for key in ("text", "event_id", "kind")):
                raise DomainError("evidence_mismatch", "Provided text is not the exact original byte range.")
            if structured and item.get("structure") != expected["structure"]:
                raise DomainError("evidence_mismatch", "Observed event structure changed.", {"ref_id": item["ref_id"]})
    refreshed = copy.deepcopy(packet)
    _refresh(refreshed, index)
    if packet["coverage"] != refreshed["coverage"] or packet["omitted_refs"] != refreshed["omitted_refs"]:
        raise DomainError("evidence_mismatch", "Packet coverage or unread references changed.")
    if structured and packet.get("relations") != refreshed["relations"]:
        raise DomainError("evidence_mismatch", "Packet relationships differ from the visible source projection.")
    if math.ceil(len(_json(packet).encode("utf-8")) / 3) > packet["token_budget"]:
        raise DomainError("evidence_budget_exhausted", "Packet exceeds its explicitly estimated token budget.")
    return packet


def expand_packet(index, packet, requests, *, limits):
    """Read only advertised ranges, retaining all previously supplied evidence."""
    _limits(limits)
    result = validate_packet(packet, index)
    catalog = {entry["ref_id"]: entry for entry in result["readable_ref_catalog"]}
    refs = [request.get("ref_id") for request in requests]
    if not refs or len(refs) != len(set(refs)):
        raise DomainError("invalid_read_request", "A non-empty, non-repeated read request is required.")
    supplied = {f["ref_id"] for f in result["fragments"]}
    for ref in refs:
        if ref not in catalog or not catalog[ref]["available"] or ref in supplied:
            raise DomainError("unsupported_evidence", "Only unread, available catalog references can be expanded.", {"ref_id": ref})
        result["fragments"].append(_resolve(index, ref)[1])
    # Legacy archives stay readable. Re-reading their sources upgrades a new
    # packet, without changing the archived packet or dropping prior body ranges.
    result["projection_version"] = 2
    result["fragments"] = [_resolve(index, item["ref_id"])[1] for item in result["fragments"]]
    result["readable_ref_catalog"] = [{**_catalog(_resolve(index, item["ref_id"])[1]), "available": item["available"]}
                                     for item in result["readable_ref_catalog"]]
    result["packet_id"] = new_id("packet")
    result["token_budget"] = limits["token_budget"]
    result["readable_ref_catalog"] = [item for item in result["readable_ref_catalog"] if item["ref_id"] not in refs]
    _refresh(result, index)
    if not _fits(result, limits):
        raise DomainError("evidence_budget_exhausted", "Requested original ranges exceed the declared packet budget.")
    return validate_packet(result, index)


def validate_citations(draft, packet):
    """Check reference availability, not semantic truth or causal attribution."""
    packet = validate("EvidencePacket", packet)
    provided = {f["ref_id"] for f in packet["fragments"]}
    readable = {r["ref_id"] for r in packet["readable_ref_catalog"] if r["available"]}
    errors = []
    citation_fields = {"evidence_refs", "supporting_refs", "counterevidence_refs", "boundary_refs"}
    def walk(value, path):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in citation_fields and isinstance(child, list):
                    errors.extend({"path": f"{path}.{key}[{i}]", "ref_id": ref, "reason": "original body not provided"}
                                  for i, ref in enumerate(child) if ref not in provided)
                elif key == "read_requests" and isinstance(child, list):
                    errors.extend({"path": f"{path}.read_requests[{i}]", "ref_id": req.get("ref_id"), "reason": "not an available unread catalog entry"}
                                  for i, req in enumerate(child) if req.get("ref_id") not in readable or req.get("ref_id") in provided)
                else:
                    walk(child, f"{path}.{key}")
        elif isinstance(value, list):
            for i, child in enumerate(value):
                walk(child, f"{path}[{i}]")
    walk(draft, "$")
    if errors:
        raise DomainError("unsupported_evidence", "Draft cites unavailable original evidence.", {"errors": errors})
    return copy.deepcopy(draft)


def feedback_view(index, packet):
    """Project feedback identity/state metadata; its long text stays in the packet.

    Catalog-only items are read locators, not scored evidence. No ``reason`` or
    arbitrary checker log bypasses the packet's exact-byte/character budget.
    """
    packet = validate_packet(packet, index)
    fields = ("check_id", "subject_ref", "project_id", "criterion_id", "task_revision",
              "evaluated_state_digest", "binding_status", "source", "visibility",
              "evaluator_status", "outcome", "score", "checked_at", "received_at")
    visible = []
    for feedback in index["feedback"]:
        def belongs(item):
            record, _ = _resolve(index, item["ref_id"])
            return (not record["source_event"] and record["kind"] == "feedback"
                    and record["event_id"] == feedback["check_id"]
                    and record["episode_id"] == feedback["subject_ref"])
        provided = [f["ref_id"] for f in packet["fragments"] if belongs(f)]
        readable = [f["ref_id"] for f in packet["readable_ref_catalog"] if belongs(f)]
        if provided:
            visible.append({**{key: feedback[key] for key in fields}, "provided_refs": provided,
                            "readable_refs": readable, "read_status": "provided_ranges_only"})
        elif readable:
            visible.append({"check_id": feedback["check_id"], "provided_refs": [],
                            "readable_refs": readable, "read_status": "catalog_only"})
    return visible


def validate_goal_bindings(draft, index):
    """Validate sidecar suggestions; never rewrite raw events or imply outcomes."""
    draft = validate("GoalBindingDraft", draft)
    for binding in draft["bindings"]:
        evidence = [_resolve(index, ref)[0] for ref in binding["evidence_refs"]]
        events = [_resolve(index, ref)[0] for ref in binding["event_refs"]]
        user_sources = [r for r in evidence if r["source_role"] == "user" and r["kind"] == "task"]
        if not user_sources:
            raise DomainError("invalid_goal_binding", "A goal change requires a provided user instruction, not an agent plan.")
        if binding["relation"] != "ambiguous" and not any((r["goal_id"] or r["task_id"]) == binding["goal_id"] and r["task_revision"] == binding["revision"] for r in user_sources):
            raise DomainError("invalid_goal_binding", "Suggested goal/revision has no explicit source identity.")
        for event in events:
            if not any(r["episode_id"] == event["episode_id"] and r["position"] <= event["position"] for r in user_sources):
                raise DomainError("invalid_goal_binding", "Later or unrelated user requirements cannot govern earlier events.")
            if event["task_revision"] is not None and event["task_revision"] != binding["revision"]:
                raise DomainError("invalid_goal_binding", "Suggestion contradicts an observed event revision.")
    return draft
