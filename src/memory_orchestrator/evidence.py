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


_FAILURE = re.compile(r"(?i:\b(?:error|fail(?:ed|ure)?|traceback)\b|\bexception\s*[:(])"
                      r"|\b[A-Za-z][A-Za-z0-9]*(?:Error|Exception)\b|错误|失败|丢失|不通过")
_RECOVERY = re.compile(r"recovery|retry|修复|恢复|重试|另一运行", re.I)
_COUNTER = re.compile(r"counterexample|反例|妨碍", re.I)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _unique(values):
    return list(dict.fromkeys(values))


def _failure_position(text):
    """Locate an error hint without treating business identifiers as failures."""
    for match in _FAILURE.finditer(text):
        # A serialized no-error field is metadata, not an observed failure.
        if re.match(r'["\s]*:\s*(?:null|false|0\b|""|\[\]|\{\})', text[match.end():], re.I):
            continue
        return match.start()
    return None


def _temporal_positions(length, count):
    """Bounded breadth across local source order, not a causal-time inference."""
    if length <= 0 or count <= 0:
        return
    from collections import deque
    yielded = 0
    for position in _unique([0, length - 1]):
        if yielded >= count: return
        yield position; yielded += 1
    intervals = deque([(1, length - 2)])
    while intervals and yielded < count:
        start, end = intervals.popleft()
        if start > end: continue
        middle = (start + end) // 2
        yield middle; yielded += 1
        intervals.extend(((start, middle - 1), (middle + 1, end)))


def _spread(rows):
    """Round-robin episodes and spread positions inside each source."""
    from collections import deque
    groups = defaultdict(list)
    for row in rows:
        groups[row['episode_id']].append(row)
    streams = deque()
    for key in sorted(groups):
        values = sorted(groups[key], key=lambda row: (row['position'], row['base_ref']))
        streams.append(iter([values[i] for i in _temporal_positions(len(values), len(values))]))
    while streams:
        iterator = streams.popleft()
        try: yield next(iterator)
        except StopIteration: continue
        streams.append(iterator)


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


def index_episodes(episodes, *, feedback=(), contexts=None, store=None, trace_limits=None):
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
    readers, progress = [], []
    for ep in episodes:
        if not ep.get("trace_ref"): continue
        if store is None or trace_limits is None or ep["events"]:
            raise DomainError("trace_source", "A trace episode needs its Store, explicit index limits, and one event source")
        from .trace import ensure_trace_index
        reader, checkpoint = ensure_trace_index(store, ep["trace_ref"], trace_limits)
        if reader.manifest["episode_id"] != ep["episode_id"] or reader.manifest["project_id"] != project:
            raise DomainError("trace_mismatch", "Trace manifest does not belong to this episode/project")
        if not checkpoint["index_complete"]:
            raise DomainError("needs_index", "Another bounded indexing step is required before using this source",
                              {"trace_ref": ep["trace_ref"], "checkpoint": checkpoint})
        readers.append(reader); progress.append(checkpoint)

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
            "resources": copy.deepcopy(event.get("resources", [])),
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
        state_resource = None
        if fb['binding_status'] == 'bound' and fb['evaluated_state_digest'] is not None:
            state_resource = {'kind': 'artifact', 'ref': 'evaluated-state:' + fb['evaluated_state_digest'],
                              'access': 'check', 'version_ref': fb['evaluated_state_digest']}
            # Older in-memory Episodes predate Host artifact resources. Derive
            # only after parsing the exact environment result and matching the
            # feedback's evaluated-state digest; raw event text remains intact.
            for record in records.values():
                if (not record['source_event'] or record['episode_id'] != ep['episode_id']
                        or record['source_role'] != 'environment'
                        or record['source_kind'] not in ('result', 'observation')):
                    continue
                try:
                    material = json.loads(record['text'])
                except (TypeError, ValueError):
                    continue
                if (isinstance(material, dict) and 'artifact' in material
                        and digest(material['artifact']) == fb['evaluated_state_digest']
                        and state_resource not in record['resources']):
                    record['resources'].append(copy.deepcopy(state_resource))
        event_count = next((reader.checkpoint['event_count'] for reader in readers
                            if reader.manifest['episode_id'] == ep['episode_id']), len(ep['events']))
        full = add(ep, {"event_id": fb["check_id"], "kind": "feedback", "text": _json(fb),
                 "task_revision": fb["task_revision"], "source_ref": f"feedback:{fb['check_id']}",
                 **({'resources': [state_resource]} if state_resource is not None else {})},
            event_count, namespace="feedback", kind="feedback")
        if fb["reason"]:
            # Keep the original whole-record coordinates. This fixed field view
            # avoids a second JSON-string encoding without parsing its contents.
            base = "ev:" + digest([project, ep["episode_id"], "feedback", fb["check_id"], "reason-text-v1"])[:24]
            records[base] = {**full, "base_ref": base, "text": fb["reason"],
                             "raw_ref": f"feedback:{fb['check_id']}#/reason", "raw_hash": digest(fb["reason"])}
    for ep in episodes:
        if not any(f["subject_ref"] == ep["episode_id"] for f in allowed_feedback):
            gaps.append(f"{ep['episode_id']}: no separately supplied adaptation feedback; outcome unknown")
    if readers:
        from .trace import TraceRecords
        records = TraceRecords(records, readers)
    return {"project_id": project, "episodes": episodes, "records": records,
            "feedback": allowed_feedback, "goal_transitions": transitions,
            "call_pairs": pairs, "gaps": _unique(gaps), "trace_progress": progress,
            "trace_readers": readers, "read_stats": {"body_bytes": 0, "range_reads": 0}}


def _limits(limits):
    for name in ("max_chars", "max_fragment_chars", "max_catalog_refs", "token_budget"):
        value = limits.get(name)
        if type(value) is not int or value < (0 if name == "max_catalog_refs" else 1):
            raise DomainError("invalid_budget", f"Explicit integer {name} is required.")
    return limits


def _byte_length(record):
    return record["text_bytes"] if "_reader" in record else len(record["text"].encode("utf-8"))


def _bytes(record, start, end):
    return record["_reader"].read_range(record, start, end) if "_reader" in record else record["text"].encode("utf-8")[start:end]


def _trace_hint(record):
    if '_verified_hint' in record: return record['_verified_hint']
    failure = record.get('failure_byte')
    record['_verified_hint'] = None
    if failure is None: return None
    start = max(0, failure - 32)
    raw = _bytes(record, start, min(_byte_length(record), failure + 160))
    while raw and raw[0] & 0xC0 == 0x80: start += 1; raw = raw[1:]
    text = raw.decode('utf-8', errors='ignore')
    position = _failure_position(text)
    recovery = _RECOVERY.search(text)
    if position is None and recovery: position = recovery.start()
    if position is not None:
        record['_verified_hint'] = start + len(text[:position].encode('utf-8'))
    return record['_verified_hint']


def _piece(record, start, end, *, body=True):
    item = {"ref_id": f"{record['base_ref']}:{start}:{end}", "episode_id": record["episode_id"],
            "event_id": record["event_id"], "kind": record["kind"], "raw_ref": record["raw_ref"],
            "raw_hash": record["raw_hash"],
            "range": {"start_byte": start, "end_byte_exclusive": end},
            "task_revision": record["task_revision"], "structure": _structure(record)}
    if body: item["text"] = _bytes(record, start, end).decode("utf-8")
    if "source_record" in record: item["source_record"] = copy.deepcopy(record["source_record"])
    return item


def _pieces(record, width, extra):
    preserve_prefix = learning_role(record) == 'user'
    if "_reader" in record:
        length = _byte_length(record)
        # Older indexes carry a broad lexical hint. It is rechecked before use;
        # raw archives and previously saved checkpoints are not rewritten.
        failure = None if preserve_prefix else _trace_hint(record)
        starts = ([max(0, failure - width // 4)] if failure is not None else [])
        starts += [0, max(0, length-width), *[i*width for i in range(1, min(extra+1, math.ceil(length/width)))]]
        for start in _unique(starts):
            raw = _bytes(record, start, min(length, start + width*4 + 4))
            while raw and raw[0] & 0xC0 == 0x80: start += 1; raw = raw[1:]
            text = raw.decode("utf-8", errors="ignore")[:width]
            yield {**_piece(record, start, start + len(text.encode()), body=False), "text": text}
        return
    text = record["text"]
    failure = None if preserve_prefix else _failure_position(text)
    recovery = None if preserve_prefix else _RECOVERY.search(text)
    anchor = failure if failure is not None else recovery.start() if recovery else None
    starts = ([max(0, anchor - width // 4)] if anchor is not None else []) + [0, max(0, len(text) - width)]
    starts += [i * width for i in range(1, min(extra + 1, math.ceil(len(text) / width)))]
    for start in _unique(starts):
        end = min(len(text), start + width)
        yield _piece(record, len(text[:start].encode("utf-8")), len(text[:end].encode("utf-8")))


def _catalog(fragment):
    return {**{k: fragment[k] for k in ("ref_id", "episode_id", "task_revision", "raw_ref", "raw_hash", "range", "structure")},
            **({"source_record": fragment["source_record"]} if "source_record" in fragment else {}),
            "available": True}


def _resolve(index, ref, *, body=True):
    if ref in index["records"]:
        record = index["records"][ref]
        if "_reader" not in record and digest(record["text"]) != record["raw_hash"]:
            raise DomainError("evidence_mismatch", "Indexed original text no longer matches its source hash.")
        return record, _piece(record, 0, _byte_length(record), body=body)
    try:
        base, start, end = ref.rsplit(":", 2)
        record = index["records"][base]
        if "_reader" not in record and digest(record["text"]) != record["raw_hash"]:
            raise DomainError("evidence_mismatch", "Indexed original text no longer matches its source hash.")
        start, end = int(start), int(end)
        if not 0 <= start <= end <= _byte_length(record):
            raise ValueError("out of range")
        return record, _piece(record, start, end, body=body)
    except (KeyError, ValueError, UnicodeError, AttributeError) as exc:
        raise DomainError("unsupported_evidence", "Reference is not a valid original range.", {"ref_id": ref}) from exc


def _bindings(index):
    bindings = []
    for ep in index["episodes"]:
        pairs = [(ep["task"]["task_id"], ep["task"]["revision"])]
        pairs += [(e.get("task_id"), e["task_revision"]) for e in ep["events"]]
        if ep.get("trace_ref"):
            pairs += _unique((r["task_id"], r["task_revision"]) for r in index["records"].matching(episode_id=ep["episode_id"]))
        for task, revision in _unique(pairs):
            bindings.append({"episode_id": ep["episode_id"], "task_ref": task,
                             "task_revision": revision, "relation": "unknown" if task is None or revision is None else "related_task"})
    known = {(b["task_ref"], b["task_revision"]) for b in bindings if b["relation"] != "unknown"}
    if len(known) == 1:
        for binding in bindings:
            if binding["relation"] != "unknown":
                binding["relation"] = "same_task"
    return bindings


def _matching(index, *, episode_id=None, call_id=None, resource=None, user_goals=False):
    records = index["records"]
    if hasattr(records, "matching"):
        yield from records.matching(episode_id=episode_id, call_id=call_id, resource=resource, user_goals=user_goals)
        return
    for row in records.values():
        if (row["source_event"] and (episode_id is None or row["episode_id"] == episode_id)
                and (call_id is None or row["call_id"] == call_id)
                and (not user_goals or row["source_role"] == "user" and row["source_kind"] == "instruction")
                and (resource is None or any(r["ref"] == resource for r in row.get("resources", [])))):
            yield row


def _parent_base(index, record):
    return "ev:" + digest([index["project_id"], record["parent_episode_id"] or record["episode_id"],
                            "event", record["parent_event_id"]])[:24]


def _trace_transition(index, record):
    key = (record["goal_id"] or record["task_id"], record["task_revision"])
    previous, seen = None, None
    for row in _matching(index, episode_id=record["episode_id"], user_goals=True):
        if row["position"] >= record["position"]: break
        identity = (row["goal_id"] or row["task_id"], row["task_revision"])
        if None not in identity:
            previous = row
            if identity == key and seen is None: seen = row["base_ref"]
    old = None if previous is None else (previous["goal_id"] or previous["task_id"], previous["task_revision"])
    relation = ("ambiguous" if None in key else "continues" if old is None or old == key else
                "revises" if old[0] == key[0] else "resumes" if seen else "switches")
    basis = [] if previous is None else [previous["base_ref"]]
    if relation == "resumes": basis.append(seen)
    return {"event_ref": record["base_ref"], "goal_id": key[0], "revision": key[1], "relation": relation, "basis_refs": _unique(basis)}


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
        record, _ = _resolve(index, item["ref_id"], body=False)
        visible.setdefault(record["base_ref"], item["ref_id"])
    calls, goals, parents = [], [], []
    visible_records = [index["records"][ref] for ref in visible]
    for eid, call_id in sorted({(r["episode_id"], r["call_id"]) for r in visible_records if r["call_id"] is not None}):
        action_refs, result_refs, actions, results, complete = [], [], 0, 0, True
        for record in _matching(index, episode_id=eid, call_id=call_id):
            if record["source_kind"] == "action":
                actions += 1
                if record["base_ref"] in visible: action_refs.append(visible[record["base_ref"]])
                else: complete = False
            elif record["source_kind"] in ("observation", "result"):
                results += 1
                if record["base_ref"] in visible: result_refs.append(visible[record["base_ref"]])
                else: complete = False
        calls.append({"episode_id": eid, "call_id": call_id, "action_refs": action_refs, "result_refs": result_refs,
                      "status": "paired" if actions == 1 and results else "ambiguous", "coverage": "complete" if complete else "partial"})
    transitions = [t for t in index["goal_transitions"] if t["event_ref"] in visible]
    transitions += [_trace_transition(index, r) for r in visible_records if "_reader" in r
                    and r["source_role"] == "user" and r["source_kind"] == "instruction"]
    for transition in transitions:
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
        parent_base = _parent_base(index, record)
        if parent_base not in index["records"]: parent_base = None
        parent_ref = visible.get(parent_base)
        status = ("missing" if parent_base is None else "outside_packet" if parent_ref is None
                  else "provided" if parent_ref in provided else "readable")
        parents.append({"child_ref": child_ref, "parent_ref": parent_ref, "status": status})
    return {"calls": calls, "goals": goals, "parents": parents}


def _resource_relations(packet, index):
    visible = {}
    for item in packet["fragments"] + packet["readable_ref_catalog"]:
        record, _ = _resolve(index, item["ref_id"], body=False)
        visible.setdefault(record["base_ref"], (item["ref_id"], record))
    links = []
    rows = list(visible.values())
    for i, (left_ref, left) in enumerate(rows):
        for right_ref, right in rows[i+1:]:
            for a in left.get("resources", []):
                for b in right.get("resources", []):
                    if a["ref"] != b["ref"]: continue
                    version = None if a["version_ref"] is None or b["version_ref"] is None else a["version_ref"] == b["version_ref"]
                    if left["episode_id"] != right["episode_id"] and version is not True: continue
                    parent = (_parent_base(index, left) == right["base_ref"] if left["parent_event_id"] else False)
                    parent |= (_parent_base(index, right) == left["base_ref"] if right["parent_event_id"] else False)
                    links.append({"from_ref": left_ref, "to_ref": right_ref, "resource_ref": a["ref"],
                        "relation": "declared_parent" if parent else "same_resource_candidate", "version_match": version,
                        "coverage": "complete" if left["episode_id"] == right["episode_id"] else "partial"})
    return links


def _dependencies(index, focus, limits, *, ordered=None):
    if limits is None: return set()
    if any(type(limits.get(k)) is not int or limits[k] < 0 for k in ("max_hops", "max_events")):
        raise DomainError("dependency_budget", "Explicit nonnegative hop/event limits required")
    found, frontier = set(), list(focus)
    for _ in range(limits["max_hops"]):
        next_frontier = []
        for ref in frontier:
            record = index["records"][ref]
            neighbors = []
            if record["parent_event_id"]:
                parent = _parent_base(index, record)
                if parent in index["records"]: neighbors.append(index["records"][parent])
            if record["call_id"] is not None:
                from itertools import islice
                neighbors.extend(islice(_matching(index, episode_id=record["episode_id"], call_id=record["call_id"]), limits["max_events"]))
            for resource in record.get("resources", []):
                for candidate in _matching(index, resource=resource["ref"]):
                    if (candidate["episode_id"] == record["episode_id"] or resource["version_ref"] is not None
                            and any(r["ref"] == resource["ref"] and r["version_ref"] == resource["version_ref"] for r in candidate.get("resources", []))):
                        neighbors.append(candidate)
                    if len(neighbors) >= limits["max_events"]: break
            for candidate in neighbors:
                key = candidate["base_ref"]
                if key in found or key in focus: continue
                if len(found) >= limits["max_events"]: return found
                found.add(key); next_frontier.append(key)
                if ordered is not None: ordered.append(key)
        frontier = next_frontier
    return found


def _is_feedback_reason(record):
    return (record["namespace"] == "feedback"
            and record["raw_ref"] == f"feedback:{record['event_id']}#/reason")


def _refresh(packet, index):
    packet.pop("goal_annotations", None)
    packet.pop("resource_relations", None)
    selected = {_resolve(index, f["ref_id"], body=False)[0]["base_ref"] for f in packet["fragments"]}
    # The optional field view neither creates another source obligation nor
    # substitutes for an unread original record. Only inspect in-memory views;
    # disk event metadata must not be materialized to count this fixed field.
    records = index["records"]
    metadata = records.memory if hasattr(records, "memory") else records
    required_count = len(records) - sum(_is_feedback_reason(row) for row in metadata.values())
    selected_required = {ref for ref in selected if not _is_feedback_reason(records[ref])}
    catalog_refs = [c["ref_id"] for c in packet["readable_ref_catalog"]]
    provided = {f["ref_id"] for f in packet["fragments"]}
    packet["omitted_refs"] = [ref for ref in catalog_refs if ref not in provided]
    packet["coverage"] = {
        "selected_event_count": sum(index["records"][ref]["source_event"] for ref in selected),
        "total_event_count": sum(len(ep["events"]) for ep in index["episodes"]) + sum(p["event_count"] for p in index.get("trace_progress", [])),
        "mandatory_roles_present": sorted({f["kind"] for f in packet["fragments"]}),
        "incomplete_reasons": ["Catalog and original ranges are bounded; unlisted material remains in the source index."]
            if len(selected_required) < required_count or any(
                len(f["text"].encode("utf-8")) < _byte_length(_resolve(index, f["ref_id"], body=False)[0])
                for f in packet["fragments"] if f["ref_id"].rsplit(":", 2)[0] in selected_required) else [],
        "omitted_episode_refs": [ep["episode_id"] for ep in index["episodes"]
                                 if ep["episode_id"] not in {f["episode_id"] for f in packet["fragments"]}],
    }
    if packet.get("projection_version") == 2:
        packet["relations"] = _relations(packet, index)
        if "goal_annotations" in index:
            visible = {}
            for item in packet["fragments"] + packet["readable_ref_catalog"]:
                visible.setdefault(_resolve(index, item["ref_id"], body=False)[0]["base_ref"], item["ref_id"])
            packet["goal_annotations"] = [
                {**row, "event_ref": visible[row["event_ref"]], "anchor_user_ref": visible[row["anchor_user_ref"]],
                 "evidence_refs": [visible[ref] for ref in row["evidence_refs"]]}
                for row in index["goal_annotations"]
                if all(ref in visible for ref in [row["event_ref"], row["anchor_user_ref"], *row["evidence_refs"]])]
        if any(index["records"][ref].get("resources") for ref in selected):
            packet["resource_relations"] = _resource_relations(packet, index)
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


def _metadata_candidates(index, focus, cap):
    registry = index['records']
    if hasattr(registry, 'select_metadata'):
        return registry.select_metadata({'focus': focus}, cap)
    selected = {ref: registry[ref] for ref in sorted(focus)}
    important = [row for row in registry.values() if row['kind'] in ('task', 'feedback', 'recovery', 'counterexample')
                 or _failure_position(row.get('text', '')) is not None]
    for pool in (important, list(registry.values())):
        for row in _spread(pool):
            if len(selected) >= cap: break
            selected.setdefault(row['base_ref'], row)
    return list(selected.values())


def _selection_units(index, candidates, focus, cap, allowed_refs=None):
    """Choose calls by identity and local phase, not all requests before results."""
    from itertools import islice
    terminals = {ep['episode_id']: len(ep['events']) - 1 for ep in index['episodes'] if ep['events']}
    terminals.update({reader.manifest['episode_id']: reader.checkpoint['event_count'] - 1
                      for reader in index.get('trace_readers', [])})
    feedback_views = defaultdict(list)
    for row in candidates:
        if row['namespace'] == 'feedback':
            feedback_views[(row['episode_id'], row['event_id'])].append(row)
    seen, units = set(), []
    for row in candidates:
        key = (('feedback', row['episode_id'], row['event_id']) if row['namespace'] == 'feedback' else
               (row['episode_id'], row['call_id']) if row['call_id'] is not None else (row['base_ref'],))
        if key in seen: continue
        seen.add(key)
        members = (sorted(feedback_views[(row['episode_id'], row['event_id'])], key=_is_feedback_reason)
                   if row['namespace'] == 'feedback' else
                   list(islice(_matching(index, episode_id=row['episode_id'], call_id=row['call_id']), cap))
                   if row['call_id'] is not None else [row])
        if allowed_refs is not None:
            members = [item for item in members if item['base_ref'] in allowed_refs]
        if not members: continue
        def priority(item):
            if item['base_ref'] in focus: return -1
            if item['kind'] in ('task', 'feedback'): return 0
            if item['source_event'] and item['position'] == terminals.get(item['episode_id']): return 0
            if item['kind'] in ('recovery', 'counterexample'): return 1
            if (_trace_hint(item) if '_reader' in item else _failure_position(item.get('text', ''))) is not None: return 1
            return 2
        units.append({'base_ref': members[0]['base_ref'] if row['namespace'] == 'feedback' else row['base_ref'],
                      'episode_id': row['episode_id'],
                      'position': min(item['position'] for item in members), 'members': members,
                      'priority': min(map(priority, members))})
    return [unit for priority in sorted({u['priority'] for u in units})
            for unit in _spread([u for u in units if u['priority'] == priority])]


def learning_role(record):
    """A selection role, never a rewrite of the observed source metadata."""
    if record['namespace'] == 'feedback' or record['source_kind'] == 'feedback': return 'feedback'
    if record['namespace'] == 'requirement' or record['source_role'] == 'user': return 'user'
    if record['source_kind'] == 'action': return 'action'
    if record['source_role'] == 'agent' and record['source_kind'] in ('note', 'instruction'): return 'note'
    if record['source_kind'] in ('result', 'observation'): return 'result'
    return 'unknown'


def _role_limits(caps):
    if caps is not None:
        for role in ('user', 'action', 'note', 'result', 'feedback', 'unknown'):
            if type(caps.get(role)) is not int or caps[role] < 1:
                raise DomainError('invalid_budget', f'Explicit positive role_max_chars.{role} required')
    return caps


def _role_width(row, limits, caps):
    width = limits['max_fragment_chars']
    if caps is None: return width
    role = learning_role(row)
    cap = caps[role]
    if role == 'result' and (row['kind'] in ('recovery', 'counterexample') or
            (_trace_hint(row) if '_reader' in row else _failure_position(row.get('text', ''))) is not None):
        cap = max(cap, caps['feedback'])
    return min(width, cap)


def build_packet(index, *, limits, focus_refs=(), dependency_limits=None, allowed_refs=None, role_max_chars=None):
    """Select exact snippets; metadata and the read catalog count toward the budget."""
    _limits(limits)
    _role_limits(role_max_chars)
    allowed = None if allowed_refs is None else set(allowed_refs)
    if allowed is not None:
        for ref in allowed:
            if ref not in index['records']:
                raise DomainError('unsupported_evidence', 'allowed_refs must contain original event base references', {'ref_id': ref})
    for reader in index.get("trace_readers", []): reader.set_read_budget(limits["max_chars"] * 4)
    focus = {_resolve(index, ref, body=False)[0]["base_ref"] for ref in focus_refs}
    if allowed is not None: focus &= allowed
    if dependency_limits and not focus:
        from itertools import islice
        focus = {row["base_ref"] for row in islice((r for r in index["records"].values()
                 if r["parent_event_id"] or r.get("resources") or r.get("failure_terms")), dependency_limits.get("max_events", 0))}
    focus |= _dependencies(index, focus, dependency_limits)
    if allowed is not None: focus &= allowed
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
    metadata_cap = max(1, limits["max_chars"] // 350 + limits["max_catalog_refs"])
    candidates = (_metadata_candidates(index, focus, metadata_cap) if allowed is None else
                  [index['records'][ref] for ref in sorted(allowed)])
    units = _selection_units(index, candidates, focus, metadata_cap, allowed)
    pieces = {}
    for unit in units:
        members = unit['members']
        if len(members) != 2 or any(row['namespace'] != 'feedback' for row in members): continue
        full, reason = sorted(members, key=_is_feedback_reason)
        if _is_feedback_reason(full) or not _is_feedback_reason(reason): continue
        width = _role_width(reason, limits, role_max_chars)
        # One feedback gets one body allowance. Its fixed metadata prefix is
        # useful control evidence, but never consumes more than half of it.
        # The known outer fields are canonical JSON; reason itself is unparsed.
        start, end = 0, full['text'].index(',"reason":')
        if end > width // 2:
            outcome = re.search(r'"outcome":"(?:pass|fail|unknown)"', full['text'])
            start, end = outcome.span()
        if end - start > width // 2:
            pieces[full['base_ref']] = None
            metadata_chars = 0
        else:
            pieces[full['base_ref']] = _piece(full, len(full['text'][:start].encode('utf-8')),
                                             len(full['text'][:end].encode('utf-8')))
            metadata_chars = end - start
        pieces[reason['base_ref']] = next(_pieces(reason, width - metadata_chars, 0))
    def piece(row):
        if row['base_ref'] not in pieces:
            pieces[row['base_ref']] = next(_pieces(row, _role_width(row, limits, role_max_chars), 0))
        return pieces[row['base_ref']]
    reserve = min(limits["max_chars"] // 4, limits["max_catalog_refs"] * 450)
    def place(unit, reserve, *, locator_only=False):
        proposed = copy.deepcopy(packet)
        provided = {f['ref_id'] for f in proposed['fragments']}
        readable = {r['ref_id'] for r in proposed['readable_ref_catalog']}
        members = unit['members']
        actions = [row for row in members if row['source_kind'] == 'action']
        results = [row for row in members if row['source_kind'] in ('result', 'observation')]
        if locator_only and (not actions or not results): return None
        for row in members:
            fragment = piece(row)
            if fragment is None:
                # Tiny allowances favor reason. The whole-record source is
                # still readable if the independently charged catalog fits.
                locator = _catalog(next(_pieces(row, _role_width(row, limits, role_max_chars), 0)))
                if locator['ref_id'] not in readable and len(readable) < limits['max_catalog_refs']:
                    proposed['readable_ref_catalog'].append(locator); readable.add(locator['ref_id'])
                continue
            if fragment['ref_id'] in provided: continue
            if locator_only and row in results:
                if fragment['ref_id'] not in readable:
                    proposed['readable_ref_catalog'].append(_catalog(fragment))
                    readable.add(fragment['ref_id'])
            else:
                proposed['fragments'].append(fragment); provided.add(fragment['ref_id'])
        proposed['readable_ref_catalog'] = [r for r in proposed['readable_ref_catalog'] if r['ref_id'] not in provided]
        if len(proposed['readable_ref_catalog']) > limits['max_catalog_refs']: return None
        _refresh(proposed, index)
        return proposed if _fits(proposed, limits, reserve) else None
    for unit in units:
        proposed = place(unit, reserve)
        if proposed is None:
            proposed = place(unit, reserve, locator_only=True)
        if proposed is not None: packet = proposed
    if not packet["fragments"]:
        for row in candidates:
            if piece(row) is None: continue
            candidate = copy.deepcopy(packet)
            candidate["fragments"] = [piece(row)]
            _refresh(candidate, index)
            if _fits(candidate, limits):
                packet = candidate
                break
    if not packet["fragments"]:
        raise DomainError("evidence_budget_exhausted", "No source fragment fits with its required provenance.")
    # Partial provided bodies are actionable navigation anchors. Give their
    # continuations before offering unrelated opaque request IDs.
    supplied = {f["ref_id"] for f in packet["fragments"]}
    selected_rows = {_resolve(index, fragment['ref_id'], body=False)[0]['base_ref']:
                     _resolve(index, fragment['ref_id'], body=False)[0] for fragment in packet['fragments']}
    def catalog_candidates():
        streams = []
        from collections import deque
        ordered_rows = sorted(selected_rows.values(), key=lambda row:
            (0 if row['kind'] in ('task', 'feedback') else 1 if row['source_kind'] != 'action' else 2, row['position']))
        for row in ordered_rows:
            if not any(f['ref_id'].startswith(row['base_ref'] + ':') and len(f['text'].encode('utf-8')) == _byte_length(row)
                       for f in packet['fragments']):
                streams.append(iter(_pieces(row, _role_width(row, limits, role_max_chars), limits['max_catalog_refs'])))
        pending = deque(streams)
        while pending:
            iterator = pending.popleft()
            try: yield next(iterator)
            except StopIteration: continue
            pending.append(iterator)
    for fragment in catalog_candidates():
        if len(packet["readable_ref_catalog"]) >= limits["max_catalog_refs"]: break
        if fragment['ref_id'] in supplied or fragment['ref_id'] in {r['ref_id'] for r in packet['readable_ref_catalog']}:
            continue
        proposed = copy.deepcopy(packet)
        proposed["readable_ref_catalog"].append(_catalog(fragment))
        _refresh(proposed, index)
        if _fits(proposed, limits):
            packet = proposed
    # Further calls can be advertised only with a visible action/return anchor;
    # request and response locators no longer compete in separate ranked lists.
    for unit in units:
        proposed = place(unit, 0, locator_only=True)
        if proposed is not None: packet = proposed
    packet = validate_packet(packet, index)
    index["read_stats"] = {key: sum(r.stats[key] for r in index.get("trace_readers", []))
                           for key in ("body_bytes", "range_reads")}
    return packet


def _group_binding(index, members):
    values = {key: set() for key in ('task_id', 'goal_id', 'task_revision')}
    derived, missing = False, False
    annotations = defaultdict(list)
    for row in index.get('goal_annotations', []):
        if row['relation'] != 'ambiguous': annotations[row['event_ref']].append(row)
    for member in members:
        effective = {}
        for key in values:
            value = member[key]
            fallback = annotations.get(member['base_ref'], [])
            if value is None and fallback and key in ('goal_id', 'task_revision'):
                inferred = {row['revision' if key == 'task_revision' else key] for row in fallback}
                values[key].update(inferred)
                value = next(iter(inferred)) if len(inferred) == 1 else None
                derived = True
            if value is not None: values[key].add(value)
            effective[key] = value
        missing |= effective['task_revision'] is None or effective['task_id'] is None and effective['goal_id'] is None
    conflict = any(len(v) > 1 for v in values.values())
    binding = {key: next(iter(v)) if len(v) == 1 else None for key, v in values.items()}
    status = 'ambiguous' if conflict else 'unknown' if missing else 'derived' if derived else 'observed'
    return {'episode_id': members[0]['episode_id'], **binding, 'binding_status': status}


def _trajectory_records(index, maximum):
    """Read bounded metadata pages, never materialize all disk event bodies."""
    remaining = maximum
    readers = {r.manifest['episode_id']: r for r in index.get('trace_readers', [])}
    for episode in index['episodes']:
        if remaining <= 0: return
        eid = episode['episode_id']
        if eid in readers:
            rows = readers[eid].rows(limit=remaining)
        else:
            rows = (index['records']['ev:' + digest([index['project_id'], eid, 'event', event['event_id']])[:24]]
                    for event in episode['events'][:remaining])
        for row in rows:
            remaining -= 1
            yield row


def build_trajectory_plan(index, *, limits, dependency_limits=None):
    """Project complete observed call groups into finite, source-backed packets.

    max_scan_events bounds selection scanning, not provenance metadata queries
    or integrity I/O. Actual reader work is returned separately as read_stats.
    Summaries are produced elsewhere and never replace these fragments.
    """
    for key in ('max_scan_events', 'max_segments', 'max_groups_per_segment'):
        if type(limits.get(key)) is not int or limits[key] < 1:
            raise DomainError('invalid_budget', f'Explicit positive trajectory {key} required')
    packet_limits = _limits(limits.get('packet', {}))
    role_caps = _role_limits(limits.get('role_max_chars', {}))
    if dependency_limits is not None and (not isinstance(dependency_limits, dict) or any(
            type(dependency_limits.get(key)) is not int or dependency_limits[key] < 0
            for key in ('max_hops', 'max_events'))):
        raise DomainError('dependency_budget', 'Explicit nonnegative dependency max_hops/max_events required')
    before_reads = {key: sum(r.stats[key] for r in index.get('trace_readers', []))
                    for key in ('body_bytes', 'range_reads', 'metadata_rows')}
    rows = list(_trajectory_records(index, limits['max_scan_events']))
    metadata = index['records'].memory if hasattr(index['records'], 'memory') else index['records']
    groups = {}
    for row in rows:
        # Scan position controls progression. Fetching a late call result never
        # advances past another call's earlier action or creates a second group.
        key = (row['episode_id'], row['call_id']) if row['call_id'] is not None else (row['base_ref'],)
        groups.setdefault(key, []).append(row)
    if not rows:
        # Imported material may contain only a requirement and separately
        # supplied feedback. Keep that evidence without inventing execution.
        for row in metadata.values():
            if not row['source_event']:
                groups.setdefault((row['episode_id'], 'control-only'), []).append(row)
    queued, current, current_scope = [], [], None
    for members in groups.values():
        scope = _group_binding(index, members)
        if current and (scope != current_scope or scope['binding_status'] == 'ambiguous'
                        or len(current) >= limits['max_groups_per_segment']):
            queued.append((current_scope, current)); current = []
        current_scope = scope
        current.append(members)
        if scope['binding_status'] == 'ambiguous':
            queued.append((scope, current)); current = []
    if current: queued.append((current_scope, current))

    terminal_positions = {ep['episode_id']: len(ep['events']) - 1 for ep in index['episodes']}
    terminal_positions.update({r.manifest['episode_id']: r.checkpoint['event_count'] - 1
                               for r in index.get('trace_readers', [])})
    def span_priority(item):
        priorities = []
        for group in item[1]:
            for row in group:
                role = learning_role(row)
                failed = role != 'user' and (_trace_hint(row) if '_reader' in row else _failure_position(row.get('text', ''))) is not None
                if role == 'feedback' or failed: priority = 0
                elif role == 'user' or row['kind'] in ('counterexample', 'recovery'): priority = 1
                elif row['position'] == terminal_positions[row['episode_id']]: priority = 2
                elif role == 'action': priority = 3
                elif role == 'note': priority = 4
                else: priority = 5
                priorities.append(priority)
        return min(priorities)
    # The segment cap is applied AFTER importance selection; it must not make
    # late failures disappear simply because routine calls occurred earlier.
    queued.sort(key=span_priority)

    anchors = [row for row in rows if learning_role(row) == 'user']
    anchors += [row for row in metadata.values() if not row['source_event']]
    def support(scope, members):
        refs, preceding_users = set(), []
        for row in anchors:
            if row['episode_id'] != scope['episode_id']: continue
            if scope['binding_status'] == 'ambiguous': continue
            if row['task_revision'] != scope['task_revision']: continue
            if any(row[key] is not None and scope[key] is not None and row[key] != scope[key]
                   for key in ('task_id', 'goal_id')): continue
            if row['source_event'] and row['position'] > min(r['position'] for r in members): continue
            if row['source_event']: preceding_users.append(row)
            else: refs.add(row['base_ref'])
        if preceding_users:
            refs.add(max(preceding_users, key=lambda row: row['position'])['base_ref'])
        # A derived binding remains a sidecar, with its actual user basis visible.
        member_refs = {row['base_ref'] for row in members}
        for annotation in index.get('goal_annotations', []):
            if annotation['event_ref'] in member_refs:
                refs.update([annotation['anchor_user_ref'], *annotation['evidence_refs']])
        return refs

    from collections import deque
    pending = deque(queued)
    segments, scopes, reasons, folded, result_hashes = [], [], [], set(), set()
    dependency_charged, dependency_all, already_provided = set(), set(), set()
    while pending and len(segments) < limits['max_segments']:
        scope, chunk_groups = pending.popleft()
        members = [row for group in chunk_groups for row in group]
        required = {row['base_ref'] for row in members}
        neighbor_refs, dependency_gaps = set(), []
        if dependency_limits is not None:
            remaining = dependency_limits['max_events'] - len(dependency_charged)
            known = dependency_charged | already_provided
            order = []
            # Existing evidence is free to reuse. The enlarged discovery limit
            # only makes room for these known IDs; novel accepted neighbors are
            # still charged against one plan-wide balance below. Hops remain a
            # per-chain depth ceiling, never a count of span calls.
            _dependencies(index, sorted(required), {'max_hops': dependency_limits['max_hops'],
                'max_events': remaining + len(known)}, ordered=order)
            for ref in order:
                if ref in required: continue
                if ref not in known:
                    if len(dependency_charged) >= dependency_limits['max_events']:
                        dependency_gaps.append('dependency_budget'); continue
                    dependency_charged.add(ref); known.add(ref)
                neighbor_refs.add(ref)
            if (not remaining or not dependency_limits['max_hops']) and any(
                    r['parent_event_id'] or r.get('resources') for r in members):
                dependency_gaps.append('dependency_budget')
        dependency_all.update(neighbor_refs)
        allowed = required | support(scope, members) | neighbor_refs
        try:
            packet = build_packet(index, limits=packet_limits, allowed_refs=allowed,
                                  role_max_chars=role_caps)
            dependency_rows = []
            for ref in sorted(neighbor_refs):
                source = index['records'][ref]
                source_scope = {key: source[key] for key in ('episode_id', 'task_id', 'goal_id', 'task_revision')}
                conflict = any(source_scope[key] is not None and scope[key] is not None
                               and source_scope[key] != scope[key] for key in source_scope)
                relation = ('different_scope' if conflict else 'same_scope' if
                    source_scope == {key: scope[key] for key in source_scope}
                    and source_scope['task_revision'] is not None
                    and (source_scope['task_id'] is not None or source_scope['goal_id'] is not None)
                    else 'unknown_scope')
                dependency_rows.append({'event_ref': ref, 'event_id': source['event_id'],
                    'source_scope': source_scope, 'scope_relation': relation,
                    'resources': copy.deepcopy(source.get('resources', []))})
            if dependency_rows or dependency_gaps:
                # A single bounded notice is also visible in the raw packet.
                # Detailed source scope remains in the segment sidecar passed
                # to the local model; neither changes observed event identity.
                relations = sorted({row['scope_relation'] for row in dependency_rows})
                packet['gaps'].append('Dependency support is candidate context, not current-goal or current-version truth: '
                    + ','.join(relations + _unique(dependency_gaps)) + '. Original scope/resource versions remain unchanged.')
                _refresh(packet, index)
                while not _fits(packet, packet_limits) and packet['readable_ref_catalog']:
                    packet['readable_ref_catalog'].pop(); _refresh(packet, index)
                if not _fits(packet, packet_limits):
                    raise DomainError('evidence_budget_exhausted', 'Dependency notice and source evidence cannot fit this segment')
        except DomainError as exc:
            if exc.code != 'evidence_budget_exhausted': raise
            if len(chunk_groups) > 1:
                half = len(chunk_groups) // 2
                pending.appendleft((scope, chunk_groups[half:])); pending.appendleft((scope, chunk_groups[:half]))
                continue
            reasons.append('packet_budget'); continue
        visible = {item['ref_id'].rsplit(':', 2)[0] for item in packet['fragments'] + packet['readable_ref_catalog']}
        if not required <= visible and len(chunk_groups) > 1:
            half = len(chunk_groups) // 2
            pending.appendleft((scope, chunk_groups[half:])); pending.appendleft((scope, chunk_groups[:half]))
            continue
        if not required <= visible: reasons.append('group_partial')
        if scope['binding_status'] == 'ambiguous': reasons.append('binding_conflict')
        if not neighbor_refs <= visible:
            dependency_gaps.append('dependency_packet_budget')
            reasons.append('dependency_packet_budget')
        reasons.extend(dependency_gaps)
        scope_key = tuple(scope.values())
        # Repeated ordinary tool output keeps its own read locator and call
        # membership. Errors/recovery and environment final results stay bodies.
        for row in members:
            if row['source_role'] != 'tool' or learning_role(row) != 'result': continue
            critical = row['kind'] in ('feedback', 'recovery', 'counterexample') or (
                _trace_hint(row) if '_reader' in row else _failure_position(row.get('text', ''))) is not None
            identity = (scope_key, row['raw_hash'])
            if not critical and identity in result_hashes:
                bodies = [f for f in packet['fragments'] if f['ref_id'].startswith(row['base_ref'] + ':')]
                if bodies and len(packet['readable_ref_catalog']) < packet_limits['max_catalog_refs']:
                    candidate = copy.deepcopy(packet)
                    candidate['fragments'] = [f for f in candidate['fragments'] if f not in bodies]
                    existing = {r['ref_id'] for r in candidate['readable_ref_catalog']}
                    if bodies[0]['ref_id'] not in existing:
                        candidate['readable_ref_catalog'].append(_catalog(bodies[0]))
                    candidate['gaps'].append(f"Repeated ordinary result {row['event_id']} folded to its original read locator; body not supplied.")
                    _refresh(candidate, index)
                    if candidate['fragments'] and _fits(candidate, packet_limits):
                        packet = validate_packet(candidate, index); folded.add(row['base_ref'])
            if any(f['ref_id'].startswith(row['base_ref'] + ':') for f in packet['fragments']):
                result_hashes.add(identity)
        # Importance chooses spans; each selected span still exposes the actual
        # local source order, including interleaved calls and late returns.
        packet['fragments'].sort(key=lambda f: (f['episode_id'], f['structure']['source_position'], f['range']['start_byte']))
        _refresh(packet, index)
        packet = validate_packet(packet, index)
        actual_visible = {f['ref_id'].rsplit(':', 2)[0] for f in packet['fragments'] + packet['readable_ref_catalog']}
        actual_bodies = {f['ref_id'].rsplit(':', 2)[0] for f in packet['fragments']}
        for row in dependency_rows:
            row['availability'] = 'provided' if row['event_ref'] in actual_bodies else 'readable' if row['event_ref'] in actual_visible else 'omitted'
        segments.append(packet); scopes.append({'packet_id': packet['packet_id'], **scope,
            'dependency_support': dependency_rows, 'dependency_gaps': _unique(dependency_gaps)})
        already_provided.update(ref for ref in actual_visible if index['records'][ref]['source_event'])
    if pending: reasons.append('segment_budget')
    total = sum(len(ep['events']) for ep in index['episodes']) + sum(r.checkpoint['event_count'] for r in index.get('trace_readers', []))
    if len(rows) < total: reasons.append('scan_budget')
    ranges, visible = defaultdict(list), set()
    for packet in segments:
        for item in packet['fragments'] + packet['readable_ref_catalog']:
            record, _ = _resolve(index, item['ref_id'], body=False)
            if record['source_event']: visible.add(record['base_ref'])
        for item in packet['fragments']:
            record, _ = _resolve(index, item['ref_id'], body=False)
            if record['source_event']:
                ranges[record['base_ref']].append((item['range']['start_byte'], item['range']['end_byte_exclusive']))
    full = set()
    for ref, intervals in ranges.items():
        end = 0
        for start, finish in sorted(intervals):
            if start > end: break
            end = max(end, finish)
        if end == _byte_length(index['records'][ref]): full.add(ref)
    reads = {key: sum(r.stats[key] for r in index.get('trace_readers', [])) - value for key, value in before_reads.items()}
    return {'segments': segments, 'segment_scopes': scopes, 'read_stats': reads, 'coverage': {
        'total_events': total, 'scanned_events': len(rows), 'projected_events': len(ranges),
        'folded_events': len(folded), 'truncated_events': len(set(ranges) - full),
        'dependency_discovered_events': len(dependency_charged),
        'dependency_provided_events': len(dependency_charged & set(ranges)),
        'dependency_support_events': len(dependency_all & visible),
        'dependency_omitted_events': len(dependency_all - visible),
        'omitted_events': total - len(visible), 'scan_complete': len(rows) == total,
        'scan_limit_scope': 'selection_events', 'raw_body_complete': len(full) == total, 'stop_reasons': _unique(reasons)}}


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
            _, expected = _resolve(index, item["ref_id"], body=field == "fragments")
            for key in ("episode_id", "raw_ref", "raw_hash", "range", "task_revision"):
                if item[key] != expected[key]:
                    raise DomainError("evidence_mismatch", f"Original evidence field changed: {key}", {"ref_id": item["ref_id"]})
            if field == "fragments" and any(item[key] != expected[key] for key in ("text", "event_id", "kind")):
                raise DomainError("evidence_mismatch", "Provided text is not the exact original byte range.")
            if structured and item.get("structure") != expected["structure"]:
                raise DomainError("evidence_mismatch", "Observed event structure changed.", {"ref_id": item["ref_id"]})
            if item.get("source_record") != expected.get("source_record"):
                raise DomainError("evidence_mismatch", "Serialized source locator changed.")
    refreshed = copy.deepcopy(packet)
    _refresh(refreshed, index)
    if packet["coverage"] != refreshed["coverage"] or packet["omitted_refs"] != refreshed["omitted_refs"]:
        raise DomainError("evidence_mismatch", "Packet coverage or unread references changed.")
    if structured and packet.get("relations") != refreshed["relations"]:
        raise DomainError("evidence_mismatch", "Packet relationships differ from the visible source projection.")
    if packet.get("goal_annotations") != refreshed.get("goal_annotations"):
        raise DomainError("evidence_mismatch", "Derived goal annotations changed their source projection.")
    if packet.get("resource_relations") != refreshed.get("resource_relations"):
        raise DomainError("evidence_mismatch", "Resource neighborhood changed its source projection.")
    if math.ceil(len(_json(packet).encode("utf-8")) / 3) > packet["token_budget"]:
        raise DomainError("evidence_budget_exhausted", "Packet exceeds its explicitly estimated token budget.")
    return packet


def expand_packet(index, packet, requests, *, limits):
    """Read only advertised ranges, retaining all previously supplied evidence."""
    _limits(limits)
    for reader in index.get("trace_readers", []): reader.set_read_budget(limits["max_chars"] * 4)
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
    result = validate_packet(result, index)
    index["read_stats"] = {key: sum(r.stats[key] for r in index.get("trace_readers", [])) for key in ("body_bytes", "range_reads")}
    return result


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
            record, _ = _resolve(index, item["ref_id"], body=False)
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
