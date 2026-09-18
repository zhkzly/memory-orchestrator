"""N06–N08: evidence-backed learning into candidates, never into active memory."""
from __future__ import annotations

import copy
import json
import re

from .candidates import apply_candidate, skill_view
from .context import terms as _terms
from .evidence import build_packet, expand_packet, feedback_view, index_episodes, validate_citations
from .schemas import DomainError, digest, load_contracts, new_id, now_iso, validate


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
    return copy.deepcopy(policy)


def _check_learning_source(store, episode, visited=None):
    """Respect known execution purpose before any trajectory enters model inputs.

    Imported material without a local run remains allowed with unknown provenance.
    A known frozen run (including an explicit parent) is never relabelled training.
    """
    visited = set() if visited is None else visited
    eid = episode["episode_id"]
    if eid in visited:
        return
    visited.add(eid)
    reference = episode["source"]["reference"]
    if reference is not None:
        try:
            run = store.get("runs", reference)
        except DomainError as exc:
            if exc.code != "NOT_FOUND":
                raise
            try:
                store.get("executions", reference)
            except DomainError as missing:
                if missing.code != "NOT_FOUND":
                    raise
            else:
                raise DomainError("learning_not_permitted", "Local execution has no completed, purpose-bound run record.", {"episode_id": eid})
        else:
            group = store.get("run_groups", run["group_id"])
            if run["project_id"] != episode["project_id"] or group["project_id"] != episode["project_id"]:
                raise DomainError("project_mismatch", "Execution provenance belongs to another project.")
            if group["purpose"] != "learning" or group["learning_enabled"] is not True or group["update_mode"] == "none":
                raise DomainError("learning_not_permitted", "Frozen validation/final or learning-disabled execution cannot train memory.",
                                  {"episode_id": eid, "run_id": reference, "group_id": group["group_id"], "purpose": group["purpose"]})
    for parent_id in _unique(e.get("parent_episode_id") for e in episode["events"] if e.get("parent_episode_id") and e["parent_episode_id"] != eid):
        parent = store.get("episodes", parent_id)
        if parent["project_id"] != episode["project_id"]:
            raise DomainError("project_mismatch", "Parent episode belongs to another project.")
        _check_learning_source(store, parent, visited)


def _retained_evidence(records):
    """Keep adverse references with their original packet/revision, not as new facts."""
    retained = {}
    for record in sorted(records, key=lambda r: (r.get("created_at", ""), r["record_id"])):
        for item in record.get("retained_evidence", []):
            retained.setdefault((item["role"], item["ref_id"]), copy.deepcopy(item))
        for role in ("boundary_refs", "counterevidence_refs"):
            for ref in record["draft"][role]:
                retained.setdefault((role, ref), {"role": role, "ref_id": ref,
                    "packet_id": record["packet_id"], "record_id": record["record_id"],
                    "status": "historical_reference_not_retracted"})
    return list(retained.values())


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
    run = None
    if episode['source']['reference'] is not None:
        try:
            run = store.get('runs', episode['source']['reference'])
        except DomainError as exc:
            if exc.code != 'NOT_FOUND':
                raise
    return {'episode_id': episode['episode_id'], 'source': episode['source'],
            'source_snapshot_ref': episode['source_snapshot_ref'], 'context_ref': episode['context_ref'],
            'provided_context': None if context is None else {key: context.get(key) for key in
                ('manifest_id', 'snapshot_digest', 'selected_skills', 'supplied_hash')},
            'observed_consumption': 'unknown' if run is None else run['consumption_observability'],
            'consumption_event_refs': [] if run is None else run['consumption_events'],
            'consumption_evidence_level': None if run is None else 'reported_by_execution_function'}


def find_related(experiences, task, project_id, *, limit, max_chars):
    """Simple deterministic lookup, retaining distinct boundary/contrary examples."""
    latest, histories = {}, {}
    for record in experiences:
        if record.get("project_id") != project_id or "draft" not in record or "canonical_key" not in record:
            continue
        key = record["canonical_key"]
        histories.setdefault(key, []).append(record)
        if key not in latest or (record.get("created_at", ""), record["record_id"]) > (latest[key].get("created_at", ""), latest[key]["record_id"]):
            latest[key] = copy.deepcopy(record)
    for key, record in latest.items():
        record["retained_evidence"] = _retained_evidence(histories[key])
    query = _terms(task)
    ranked = []
    for record in latest.values():
        draft = record["draft"]
        terms = _terms(_json([draft["title"], draft["scope"], draft["conditions"], draft["guidance"]]))
        score = len(query & terms)
        if score:
            ranked.append((score, bool(record["retained_evidence"]), record))
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]["record_id"]))
    chosen = []
    for _, _, record in ranked:
        if len(chosen) >= limit:
            break
        if len(_json(chosen + [record])) <= max_chars:
            chosen.append(copy.deepcopy(record))
    return chosen


def _save_experience(store, draft, packet, index, cycle_id):
    canonical = digest({key: draft[key] for key in ("kind", "scope", "guidance")})
    previous = [x for x in store.list("experiences", index["project_id"]) if x.get("canonical_key") == canonical]
    newest = max(previous, key=lambda r: (r["created_at"], r["record_id"])) if previous else None
    references = set(draft["supporting_refs"] + draft["counterevidence_refs"] + draft["boundary_refs"])
    for fact in draft["observed_facts"]:
        references.update(fact["evidence_refs"])
    fragments = {f["ref_id"]: f for f in packet["fragments"]}
    sources = {fragments[ref]["episode_id"] for ref in references}
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
    if newest and newest["draft"] == draft and sources.issubset(newest["source_episode_ids"]) and _retained_evidence(previous) == newest.get("retained_evidence", []):
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


def learn(store, episode_ids, model, *, policy):
    """Extract, diagnose and attempt each candidate against one fixed base.

    Model and task feedback remain explicitly reported evidence. This function
    checks source availability and identities, not truth of natural-language claims.
    """
    policy = _policy(policy)
    requested_ids = _unique(episode_ids)
    if not requested_ids:
        raise DomainError("empty_evidence", "At least one episode identity is required.")
    episodes = [store.get("episodes", identifier) for identifier in requested_ids]
    project = episodes[0]["project_id"]
    if any(ep["project_id"] != project for ep in episodes):
        raise DomainError("project_mismatch", "Learning cannot mix projects.")
    for episode in episodes:
        _check_learning_source(store, episode)
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
                      "exclusive_stage": {"extract_v1": "extract", "diagnose_v1": "diagnose", "propose_v1": "propose"}[prompt_id],
                      "purpose": "learning", "run_or_proposal_id": cycle_id,
                      "tokens": {key: entry.get(key) for key in ("input_tokens", "output_tokens", "total_tokens")},
                      "time": entry.get("elapsed_seconds"), "monetary_cost": None, "currency": None,
                      "status": "reported" if entry.get("measurement") == "provider_reported" else "missing",
                      "price_version": None, "raw": copy.deepcopy(entry)}
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
        try:
            response = model.generate(prompt_id, inputs, check=check)
        except DomainError as exc:
            persist_call(prompt_id, inputs, exc=exc)
            raise
        persist_call(prompt_id, inputs, response=response)
        schema_id = load_contracts()["prompts"][prompt_id]["output_schema"]
        return validate(schema_id, response["value"])

    def finish(status, reason=None):
        result["status"] = status
        result["reason"] = reason
        result["completed_at"] = now_iso()
        store.put("learning_cycles", cycle_id, result)
        return copy.deepcopy(result)

    stage = "evidence"
    try:
        task_text = "\n".join(ep["task"]["description"] + "\n" + "\n".join(e["text"][:1000] for e in ep["events"][:3]) for ep in episodes)
        eligible_memories, excluded_memories = [], []
        for memory in store.list("experiences", project):
            try:
                for eid in memory.get("source_episode_ids", []):
                    _check_learning_source(store, store.get("episodes", eid))
            except DomainError as exc:
                if exc.code != "learning_not_permitted":
                    raise
                excluded_memories.append(memory["record_id"])
            else:
                eligible_memories.append(memory)
        related = find_related(eligible_memories, task_text, project,
                               limit=policy["max_related_experiences"], max_chars=policy["max_related_chars"])
        related_ids = _unique(eid for record in related for eid in record["source_episode_ids"] if eid not in requested_ids)
        for eid in related_ids[:policy["max_related_episodes"]]:
            ep = store.get("episodes", eid)
            if ep["project_id"] != project:
                raise DomainError("project_mismatch", "Related experience references a different project.")
            episodes.append(ep)
        result["source_episode_ids"] = [ep["episode_id"] for ep in episodes]
        contexts = {ep["context_ref"]: store.get("contexts", ep["context_ref"]) for ep in episodes if ep["context_ref"]}
        feedback = [fb for ep in episodes for fb in store.feedback_for(ep["episode_id"])]
        index = index_episodes(episodes, feedback=feedback, contexts=contexts)
        if not related:
            index["gaps"].insert(0, "Related-memory lookup found no in-budget matches; this does not establish absence of counterexamples.")
        if excluded_memories:
            index["gaps"].insert(0, "Prior memories with frozen or learning-disabled execution sources were excluded from this learning input.")
        if len(related_ids) > policy["max_related_episodes"]:
            index["gaps"].insert(0, "Additional related source episodes omitted by explicit retrieval budget.")
        packet = build_packet(index, limits=policy["packet"])
        expansions = 0
        while True:
            store.put("evidence_packets", packet["packet_id"], packet)
            stage = "extract_v1"
            extraction = call(stage, {
                "task_requirements": [{"episode_id": ep["episode_id"], "task_id": ep["task"]["task_id"],
                    "revision": ep["task"]["revision"], "provided_requirement_refs": [f["ref_id"] for f in packet["fragments"]
                        if f["episode_id"] == ep["episode_id"] and f["kind"] == "task"]} for ep in episodes],
                "evidence_packet": packet, "available_feedback": feedback_view(index, packet),
                "related_experiences": _visible_related(related, packet), "readable_ref_catalog": packet["readable_ref_catalog"],
                "extraction_limits": {"max_experiences": policy["max_experiences"],
                    "max_read_requests": policy["max_read_requests"], "max_evidence_expansions": policy["max_expansions"],
                    "remaining_evidence_expansions": policy["max_expansions"] - expansions},
            }, check=lambda value: validate_citations(value, packet))
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
                packet = expand_packet(index, packet, extraction["read_requests"], limits=policy["expanded_packet"])
            except DomainError as exc:
                if exc.code == "evidence_budget_exhausted":
                    error_record(exc, "expand_evidence")
                    return finish("abstained", "Requested evidence cannot fit the declared budget.")
                raise
            expansions += 1
        if not extraction["experiences"]:
            return finish("noop", "No reusable experience was extracted.")
        for draft in extraction["experiences"]:
            result["experience_ids"].append(_save_experience(store, draft, packet, index, cycle_id))
        result["experience_ids"] = _unique(result["experience_ids"])
        stage = "diagnose_v1"
        def check_diagnosis(value):
            validate_citations(value, packet)
            _diagnosis_targets(value, view)

        diagnosis = call(stage, {
            "experiences": extraction["experiences"], "evidence_packets": [packet],
            "source_provenance": [_source_provenance(store, ep, contexts) for ep in episodes],
            "target_snapshot": {"snapshot_id": base["snapshot_id"], "project_id": project, "skills": view},
            "related_skills_and_relations": {"skills": view, "relations": store.list("relations", project),
                "related_experiences": _visible_related(related, packet), "relation_warning": "Observed co-use is not causal influence."},
            "available_feedback": feedback_view(index, packet), "learning_limits": model.limits,
        }, check=check_diagnosis)
        validate_citations(diagnosis, packet)
        allowed_targets = _diagnosis_targets(diagnosis, view)
        diagnosis_id = new_id("diagnosis")
        store.put("diagnoses", diagnosis_id, {"diagnosis_id": diagnosis_id, "project_id": project,
            "cycle_id": cycle_id, "base_digest": base["snapshot_id"], "packet_id": packet["packet_id"],
            "draft": diagnosis, "allowed_skill_ids": allowed_targets, "created_at": now_iso()})
        result["diagnosis_id"] = diagnosis_id
        if diagnosis["route"] != "skill_patch":
            for slot in result["candidate_slots"]:
                slot["status"] = "noop"
            return finish("abstained" if diagnosis["route"] == "abstain" else "noop", diagnosis["abstain_reason"] or diagnosis["route"])
        allowed_refs = [f["ref_id"] for f in packet["fragments"]]
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
                    "operation_constraints": {"allowed_operations": ["ADD", "PATCH", "RETIRE", "NOOP"],
                        "allowed_evidence_refs": allowed_refs, "known_readonly_skill_ids": list(view),
                        "max_operations": policy["max_operations"], "max_skills": policy["max_skills"],
                        "max_asset_bytes": policy["max_asset_bytes"], "project_id": project,
                        "atomic_operation_count": "Each PATCH edit, ADD, RETIRE and asset edit counts once.",
                        "rule_anchors": "Rule IDs refer to the original expected_revision; newly added rules cannot be targeted in this patch."},
                    "evaluation_scope": policy["evaluation_scope"], "learning_limits": model.limits,
                }, check=lambda value: validate_citations(value, packet))
                validate_citations(patch, packet)
                candidate = apply_candidate(store, project, patch, base_digest=base["snapshot_id"],
                    expected_generation=active["generation"], allowed_evidence_refs=allowed_refs,
                    allowed_skill_ids=allowed_targets, max_operations=policy["max_operations"],
                    max_skills=policy["max_skills"], max_asset_bytes=policy["max_asset_bytes"])
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
        return finish("abstained" if exc.code in ("evidence_budget_exhausted", "model_budget_exhausted") else "error", exc.message)
