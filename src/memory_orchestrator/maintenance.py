"""Source-bound semantic experience links with a concrete retrieval consumer.

Model judgments change a derived view, never the underlying experiences or user
facts. Only relations anchored by a completed review are visible to retrieval.
"""
from copy import deepcopy
from itertools import combinations
import json
import re

from .lineage import require_learning_source
from .schemas import DomainError, digest, new_id, now_iso, validate


def _size(value):
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def eligible_experience(store, memory):
    try:
        for eid in memory.get("source_episode_ids", []):
            source = require_learning_source(store, store.get("episodes", eid))
            if source.get("trace_index_complete") is False or source.get("unindexed_trace_refs"):
                return False
    except DomainError as exc:
        if exc.code != "learning_not_permitted":
            raise
        return False
    return True


def retained_evidence(records):
    kept = {}
    for record in sorted(records, key=lambda r: (r.get("created_at", ""), r["record_id"])):
        for item in record.get("retained_evidence", []):
            kept.setdefault((item["role"], item["ref_id"]), deepcopy(item))
        for role in ("boundary_refs", "counterevidence_refs"):
            for ref in record["draft"][role]:
                kept.setdefault((role, ref), {"role": role, "ref_id": ref, "packet_id": record["packet_id"],
                    "record_id": record["record_id"], "status": "historical_reference_not_retracted"})
    return list(kept.values())


def latest_experiences(records):
    histories, latest = {}, {}
    for record in records:
        key = record["canonical_key"]
        histories.setdefault(key, []).append(record)
        if key not in latest or (record.get("created_at", ""), record["record_id"]) > (latest[key].get("created_at", ""), latest[key]["record_id"]):
            latest[key] = deepcopy(record)
    for key, record in latest.items():
        record["retained_evidence"] = retained_evidence(histories[key])
    return list(latest.values())


def failure_signature(index, *, episode_ids=None, max_chars=None):
    """Observed criterion/error terms are retrieval features, not new scores."""
    signature = {"criterion_ids": [], "error_codes": [], "operation": None,
        "resource_kinds": [], "symptom_terms": [], "origin": "observed_fields", "evidence_refs": [],
        "coverage": {"complete": True, "omitted_feature_occurrences": 0, "omitted_evidence_occurrences": 0}}
    if max_chars is not None and (type(max_chars) is not int or max_chars < _size(signature) + 120):
        raise DomainError("signature_budget", "Failure signature metadata cannot fit the declared character budget")
    def add(field, value):
        if value in signature[field]: return
        proposed = {**signature, field: sorted([*signature[field], value])}
        if max_chars is None or _size(proposed) <= max_chars - 120:
            signature[field] = proposed[field]
        else:
            signature["coverage"]["complete"] = False
            name = "omitted_evidence_occurrences" if field == "evidence_refs" else "omitted_feature_occurrences"
            signature["coverage"][name] += 1
    for feedback in index["feedback"]:
        if episode_ids is not None and feedback["subject_ref"] not in episode_ids: continue
        if feedback["outcome"] == "fail":
            add("criterion_ids", feedback["criterion_id"])
            add("evidence_refs", "ev:" + digest([index["project_id"], feedback["subject_ref"], "feedback", feedback["check_id"]])[:24])
    records = index["records"].values()
    for record in records:
        if episode_ids is not None and record["episode_id"] not in episode_ids: continue
        for resource in record.get("resources", []):
            add("resource_kinds", resource["kind"])
        # Indexers may supply bounded observed terms without materializing a body.
        terms = record.get("failure_terms")
        if terms is None:
            text = record.get("text", "")
            terms = re.findall(r"\b[A-Z][A-Z0-9_]{2,}(?:ERROR|FAIL|MISMATCH|MISSING)[A-Z0-9_]*\b|\b[A-Z][A-Za-z]+Error\b", text)
        if terms:
            for term in terms: add("error_codes", term)
            add("evidence_refs", record["base_ref"])
            signature["origin"] = "text_pattern"
        if record.get("failure_symptom"):
            add("symptom_terms", record["failure_symptom"])
            signature["origin"] = "text_pattern"
    return validate("FailureSignature", signature)


def signature_score(left, right):
    if not left or not right:
        return 0
    return (4 * len(set(left.get("criterion_ids", [])) & set(right.get("criterion_ids", [])))
            + 3 * len(set(left.get("error_codes", [])) & set(right.get("error_codes", [])))
            + len(set(left.get("symptom_terms", [])) & set(right.get("symptom_terms", [])))
            + int(bool(left.get("operation")) and left.get("operation") == right.get("operation")))


def maintenance_inputs(records, relations, *, max_chars, max_pairs):
    if type(max_chars) is not int or max_chars < 1 or type(max_pairs) is not int or max_pairs < 0:
        raise DomainError("maintenance_budget", "Explicit positive character and nonnegative pair limits required")
    chosen, omitted, seen = [], [], set()
    for record in records:
        identifier = record["record_id"]
        if identifier in seen:
            continue
        seen.add(identifier)
        candidate = deepcopy(record)
        if _size(chosen + [candidate]) <= max_chars // 2:
            chosen.append(candidate)
        else:
            omitted.append(identifier)
    ids = {r["record_id"] for r in chosen}
    existing = [deepcopy(r) for r in relations if set(r.get("record_ids", [])) <= ids]
    known_pairs = {tuple(sorted(r["record_ids"])) for r in existing if r["op"] in ("LINK_DUPLICATE", "MARK_CONFLICT")}
    pairs = [list(pair) for pair in combinations([r["record_id"] for r in chosen], 2)
             if tuple(sorted(pair)) not in known_pairs][:max_pairs]
    result = {"records": chosen, "pairs": pairs, "existing_relations": existing,
              "comparison_refs": ["experience:" + r["record_id"] for r in chosen]
                    + ["relation:" + r["relation_id"] for r in existing],
              "record_hashes": {r["record_id"]: digest(r) for r in chosen},
              "omitted_record_ids": omitted}
    if _size(result) > max_chars:
        raise DomainError("maintenance_budget", "Complete comparison metadata exceeds its declared input budget")
    return result


def check_maintenance(draft, inputs, *, max_actions):
    draft = validate("ExperienceMaintenanceDraft", draft)
    errors, ids = [], set(inputs["record_hashes"])
    refs = set(inputs["comparison_refs"])
    existing = {r["relation_id"] for r in inputs["existing_relations"]}
    pairs = {tuple(sorted(pair)) for pair in inputs["pairs"]}
    seen = set()
    if len(draft["actions"]) > max_actions:
        errors.append({"path": "$.actions", "expected_maximum": max_actions})
    for i, action in enumerate(draft["actions"]):
        path = f"$.actions[{i}]"
        if action["op"] == "NOOP":
            if len(draft["actions"]) != 1:
                errors.append({"path": path, "message": "NOOP must be the sole action"})
            continue
        if not action["evidence_refs"] or set(action["evidence_refs"]) - refs:
            errors.append({"path": path + ".evidence_refs", "allowed_refs": sorted(refs)})
        if action["op"] == "REVOKE":
            if action["relation_id"] not in existing:
                errors.append({"path": path + ".relation_id", "allowed_refs": sorted(existing)})
            key = ("revoke", action["relation_id"])
        else:
            pair = tuple(sorted(action["record_ids"]))
            if len(set(pair)) != 2 or set(pair) - ids or pair not in pairs:
                errors.append({"path": path + ".record_ids", "allowed_pairs": inputs["pairs"]})
            if action["op"] == "LINK_DUPLICATE" and action["preferred_record_id"] not in pair:
                errors.append({"path": path + ".preferred_record_id", "expected": list(pair)})
            key = pair
        if key in seen:
            errors.append({"path": path, "message": "A pair/relation may be changed only once per review"})
        seen.add(key)
    if errors:
        raise DomainError("maintenance_reference", "Maintenance actions exceed their supplied comparison", {"errors": errors})
    return draft


def active_memory_relations(store, project_id):
    records = {r["relation_id"]: validate("MemoryRelation", r) for r in store.list("memory_relations", project_id)}
    active = {}
    reviews = sorted([validate("MaintenanceReview", r) for r in store.list("maintenance_reviews", project_id)],
                     key=lambda r: (r["created_at"], r["review_id"]))
    for review in reviews:
        if review["status"] != "applied":
            continue
        for identifier in review["relation_ids"]:
            relation = records.get(identifier)
            if relation is None or relation["review_ref"] != review["review_id"]:
                raise DomainError("maintenance_binding", "Completed maintenance review lost its exact relation")
            if relation["op"] == "REVOKE":
                active.pop(relation["relation_id_to_revoke"], None)
            else:
                active[identifier] = relation
    # Historical mixed/frozen-source judgments cannot leak back through this view.
    return [r for r in active.values() if all(eligible_experience(store, store.get("experiences", eid))
                                              for eid in r["record_ids"])]


def apply_maintenance(store, project_id, draft, inputs, *, cycle_id, model_report_ref, max_actions=None):
    cap = len(draft.get("actions", [])) if max_actions is None else max_actions
    draft = check_maintenance(draft, inputs, max_actions=cap)
    for identifier, expected in inputs["record_hashes"].items():
        actual = store.get("experiences", identifier)
        if actual["project_id"] != project_id or digest(actual) != expected or not eligible_experience(store, actual):
            raise DomainError("maintenance_binding", "Compared experience/source is no longer eligible", {"record_id": identifier})
    live = {r["relation_id"]: r for r in active_memory_relations(store, project_id)}
    for action in draft["actions"]:
        if action["op"] == "REVOKE" and action["relation_id"] not in live:
            raise DomainError("maintenance_binding", "Relation to revoke is no longer active")
    review_id = new_id("maintenance")
    relation_ids = []
    for index, action in enumerate(draft["actions"]):
        if action["op"] == "NOOP":
            continue
        identifier = "memory_relation_" + digest([review_id, index])
        payload = deepcopy(action)
        if action["op"] == "REVOKE":
            payload["relation_id_to_revoke"] = payload.pop("relation_id")
        relation = {**payload, "relation_id": identifier, "project_id": project_id,
                    "review_ref": review_id, "cycle_id": cycle_id, "origin": "model_proxy"}
        relation = validate("MemoryRelation", relation)
        store.put("memory_relations", identifier, relation)
        relation_ids.append(identifier)
    review = {"review_id": review_id, "project_id": project_id, "cycle_id": cycle_id,
              "model_report_ref": model_report_ref, "input_hash": digest(inputs), "draft": draft,
              "record_ids": list(inputs["record_hashes"]), "relation_ids": relation_ids,
              "status": "applied" if relation_ids else "noop", "origin": "model_proxy", "created_at": now_iso()}
    # This immutable receipt is the visibility point; orphan relations are ignored.
    review = validate("MaintenanceReview", review)
    store.put("maintenance_reviews", review_id, review)
    return review


def fold_related(records, relations):
    """Return duplicate representatives and inseparable unresolved-conflict groups."""
    by_id = {r["record_id"]: deepcopy(r) for r in records}
    parent = {key: key for key in by_id}
    def root(key):
        while parent[key] != key:
            key = parent[key]
        return key
    applicable = [r for r in relations if set(r.get("record_ids", [])) <= set(by_id)]
    for relation in applicable:
        if relation["op"] != "LINK_DUPLICATE":
            continue
        preferred = root(relation["preferred_record_id"])
        proposed = {root(identifier) for identifier in relation["record_ids"]}
        # An unresolved contradiction outranks a duplicate suggestion. Do not
        # hide it indirectly through a third equivalent record.
        if any(r["op"] == "MARK_CONFLICT" and {root(x) for x in r["record_ids"]} <= proposed
               for r in applicable):
            continue
        for identifier in relation["record_ids"]:
            other = root(identifier)
            if other != preferred:
                parent[other] = preferred
    groups = {}
    for identifier in by_id:
        groups.setdefault(root(identifier), []).append(identifier)
    chosen = {}
    for representative, members in groups.items():
        row = by_id[representative]
        row["maintenance_member_ids"] = sorted(members)
        retained = {}
        for member in members:
            for item in by_id[member].get("retained_evidence", []):
                retained[(item["role"], item["ref_id"])] = item
        row["retained_evidence"] = list(retained.values())
        row["source_episode_ids"] = sorted({eid for member in members for eid in by_id[member].get("source_episode_ids", [])})
        row["source_episode_count"] = len(row["source_episode_ids"])
        for key in ("known_task_ids", "known_support_task_ids", "unknown_task_episode_ids"):
            row[key] = sorted({ref for member in members for ref in by_id[member].get(key, [])})
        row["known_task_count"] = len(row["known_task_ids"])
        row["known_support_task_count"] = len(row["known_support_task_ids"])
        chosen[representative] = row
    conflicts = {key: {key} for key in chosen}
    for relation in applicable:
        if relation["op"] == "MARK_CONFLICT":
            left, right = (root(x) for x in relation["record_ids"])
            component = conflicts[left] | conflicts[right]
            for key in component:
                conflicts[key] = component
    for key, row in chosen.items():
        if len(conflicts[key]) > 1:
            row["conflict_record_ids"] = sorted(conflicts[key])
    return list(chosen.values())


def maintenance_summary(store, project_id):
    records = latest_experiences([r for r in store.list("experiences", project_id)
                                  if "canonical_key" in r and eligible_experience(store, r)])
    relations = active_memory_relations(store, project_id)
    view = fold_related(records, relations)
    reviews = store.list("maintenance_reviews", project_id)
    counts = {}
    for review in reviews:
        counts[review["status"]] = counts.get(review["status"], 0) + 1
    committed = {rid for review in reviews if review["status"] == "applied" for rid in review["relation_ids"]}
    revocations = sum(r["relation_id"] in committed and r["op"] == "REVOKE"
                      for r in store.list("memory_relations", project_id))
    return {"review_counts": counts, "origin": "model_proxy", "applied_revocations": revocations,
            "active_duplicate_groups": [{"representative_record_id": r["record_id"], "member_record_ids": r["maintenance_member_ids"]}
                                        for r in view if len(r["maintenance_member_ids"]) > 1],
            "unresolved_conflict_groups": [list(group) for group in sorted({tuple(r["conflict_record_ids"])
                                                 for r in view if r.get("conflict_record_ids")})]}
