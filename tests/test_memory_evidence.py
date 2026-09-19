"""Constructed boundary tests derived from the blueprint's illustrative CSV examples."""
import copy
import json
import unittest
from pathlib import Path

from memory_orchestrator.schemas import DomainError, digest, validate
from memory_orchestrator.evidence import (
    index_episodes, build_packet, expand_packet, validate_packet,
    validate_citations, validate_goal_bindings,
)

C = json.loads((Path(__file__).parents[1] / "docs/blueprint/project-contract.json").read_text())
EXAMPLES = {x["id"]: x["value"] for x in C["examples"]}


def episode():
    return copy.deepcopy(EXAMPLES["imported-episode"])


def event(event_id, text, kind="observation", **extra):
    return dict(event_id=event_id, text=text, kind=kind, source_ref=None,
                call_id=None, task_revision=None, **extra)


def csv_episodes():
    groups = {}
    mapping = {"task": "instruction", "skill": "note", "action": "action",
               "observation": "observation", "feedback": "feedback",
               "recovery": "result", "counterexample": "note"}
    for fragment in EXAMPLES["evidence-packet"]["fragments"]:
        ep = groups.setdefault(fragment["episode_id"], episode())
        if ep["episode_id"] != fragment["episode_id"]:
            ep.update(episode_id=fragment["episode_id"], events=[])
        ep["events"].append(dict(event_id=fragment["event_id"], kind=mapping[fragment["kind"]],
            text=fragment["text"], source_ref=fragment["raw_ref"], call_id=None,
            task_revision=fragment["task_revision"], task_id=fragment["task_revision"].split("@")[0]))
    return list(groups.values())


def limits(max_chars=20000, max_fragment_chars=800, max_catalog_refs=8):
    return {"max_chars": max_chars, "max_fragment_chars": max_fragment_chars,
            "max_catalog_refs": max_catalog_refs, "token_budget": max_chars}


class EvidenceTests(unittest.TestCase):
    def test_unknown_import_preserves_source_and_does_not_modify_original(self):
        ep = episode()
        old = copy.deepcopy(ep)
        index = index_episodes([ep])
        packet = build_packet(index, limits=limits())
        validate("EvidencePacket", packet)
        self.assertEqual(ep, old)
        self.assertEqual(packet["source_snapshot_refs"], [])
        self.assertEqual(packet["context_refs"], [])
        self.assertIsNone(packet["task_revision"])
        self.assertEqual(packet["token_count_source"], "estimated")
        self.assertTrue(any("estimate" in gap.lower() for gap in packet["gaps"]))
        self.assertTrue(any("provided_material" in gap for gap in packet["gaps"]))

    def test_goal_switch_resume_revision_and_old_feedback_stay_bound(self):
        ep = episode()
        ep["task"] = {"description": "final goal A revision 2", "task_id": "A", "revision": "A@2"}
        ep["events"] = []
        for i, (goal, revision) in enumerate([("A", "A@1"), ("B", "B@1"), ("A", "A@1"), ("A", "A@2")]):
            e = event(f"e{i}", f"User instruction {goal} {revision}", "instruction", source_role="user", goal_id=goal, task_id=goal)
            e["task_revision"] = revision
            ep["events"].append(e)
        fb = copy.deepcopy(EXAMPLES["criterion-feedback"])
        fb.update(subject_ref=ep["episode_id"], task_revision="A@1", evidence_refs=["e0"])
        index = index_episodes([ep], feedback=[fb])
        self.assertEqual([t["relation"] for t in index["goal_transitions"]], ["continues", "switches", "resumes", "revises"])
        packet = build_packet(index, limits=limits())
        revs = {f["event_id"]: f["task_revision"] for f in packet["fragments"]}
        self.assertEqual(revs["e0"], "A@1")
        self.assertEqual(revs["e3"], "A@2")
        self.assertIsNone(packet["task_revision"])
        self.assertIn(fb["check_id"], packet["feedback_ids"])

    def test_call_pairing_is_by_identity_not_adjacency(self):
        ep = episode()
        a = event("a", "command", "action"); a["call_id"] = "c1"
        b = event("b", "other command", "action"); b["call_id"] = "c2"
        result = event("r", "first command result", "result"); result["call_id"] = "c1"
        ep["events"] = [a, b, result]
        index = index_episodes([ep])
        pair = next(x for x in index["call_pairs"] if x["call_id"] == "c1")
        self.assertEqual(pair["action_event_ids"], ["a"])
        self.assertEqual(pair["result_event_ids"], ["r"])
        self.assertTrue(any("c2" in g for g in index["gaps"]))

    def test_packet_projects_observed_call_parent_role_and_source_order(self):
        ep = episode()
        action = {**event("launch", "start", "action", source_role="agent", task_id="A", goal_id="G"), "call_id": "c1"}
        result = {**event("returned", "done", "result", source_role="tool", parent_event_id="launch"), "call_id": "c1"}
        ep["events"] = [action, event("between", "unrelated"), result]
        packet = build_packet(index_episodes([ep]), limits=limits())
        self.assertEqual(packet["projection_version"], 2)
        fragments = {f["event_id"]: f for f in packet["fragments"]}
        info = fragments["returned"]["structure"]
        self.assertEqual(info["source_kind"], "result")
        self.assertEqual(info["source_position"], 2)
        self.assertEqual(info["source_role"], "tool")
        self.assertEqual(info["call_id"], "c1")
        self.assertEqual(info["parent_event_id"], "launch")
        self.assertIsNone(info["task_id"])
        self.assertIsNone(info["goal_id"])
        self.assertEqual(fragments["launch"]["structure"]["task_id"], "A")
        self.assertEqual(fragments["launch"]["structure"]["goal_id"], "G")
        self.assertEqual(packet["relations"]["calls"], [{"episode_id": ep["episode_id"], "call_id": "c1",
            "action_refs": [fragments["launch"]["ref_id"]], "result_refs": [fragments["returned"]["ref_id"]],
            "status": "paired", "coverage": "complete"}])
        self.assertEqual(packet["relations"]["parents"], [{"child_ref": fragments["returned"]["ref_id"],
            "parent_ref": fragments["launch"]["ref_id"], "status": "provided"}])

    def test_structure_and_relationships_share_exact_source_validation(self):
        ep = episode()
        ep["events"] = [
            {**event("a", "same text", "action", source_role="agent"), "call_id": "known"},
            {**event("b", "same text", "result", source_role="tool", parent_event_id="a"), "call_id": "known"}]
        index = index_episodes([ep]); packet = build_packet(index, limits=limits())
        for field, wrong in [("call_id", "invented"), ("source_position", 999), ("source_role", "user"),
                             ("goal_id", "invented goal"), ("parent_event_id", "invented parent")]:
            altered = copy.deepcopy(packet)
            altered["fragments"][1]["structure"][field] = wrong
            with self.subTest(field=field), self.assertRaises(DomainError):
                validate_packet(altered, index)
        altered = copy.deepcopy(packet)
        altered["relations"]["calls"][0]["result_refs"] = [packet["fragments"][0]["ref_id"]]
        with self.assertRaises(DomainError): validate_packet(altered, index)

    def test_cross_episode_parent_identity_survives_projection(self):
        parent = episode()
        parent["episode_id"] = "parent-episode"
        parent["events"] = [event("same-id", "parent text", "action", source_role="agent")]
        child = episode()
        child["episode_id"] = "child-episode"
        child["events"] = [event("same-id", "child text", "result", source_role="tool",
                                  parent_episode_id="parent-episode", parent_event_id="same-id")]
        packet = build_packet(index_episodes([parent, child]), limits=limits())
        first = next(f for f in packet["fragments"] if f["text"] == "parent text")
        second = next(f for f in packet["fragments"] if f["text"] == "child text")
        self.assertEqual(second["structure"]["parent_episode_id"], "parent-episode")
        self.assertEqual(packet["relations"]["parents"], [{"child_ref": second["ref_id"],
                         "parent_ref": first["ref_id"], "status": "provided"}])

    def test_relationship_metadata_is_bounded_and_undisclosed_endpoints_are_partial(self):
        ep = episode()
        ep["events"] = [{**event(f"a{i}", "launch task " * 30, "action"), "call_id": f"call-{i}"} for i in range(20)]
        ep["events"] += [{**event(f"r{i}", "task returned " * 30, "result"), "call_id": f"call-{i}"} for i in range(20)]
        index = index_episodes([ep])
        packet = build_packet(index, limits=limits(8000, 100, 2))
        self.assertLessEqual(len(json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"))), 8000)
        available = {x["ref_id"] for x in packet["fragments"] + packet["readable_ref_catalog"]}
        self.assertLess(len(packet["relations"]["calls"]), len(index["call_pairs"]))
        for relation in packet["relations"]["calls"]:
            self.assertTrue(set(relation["action_refs"] + relation["result_refs"]) <= available)
        for locator in packet["readable_ref_catalog"]:
            with self.assertRaises(DomainError): validate_citations({"evidence_refs": [locator["ref_id"]]}, packet)
        # Grouped selection need not strand a return merely to create partial
        # metadata. A narrower consumer projection (as with goal windows) must
        # still describe an actually hidden counterpart as partial.
        from memory_orchestrator.evidence import _refresh
        hidden = next(row for row in packet['relations']['calls'] if row['result_refs'])
        for key in ('fragments', 'readable_ref_catalog'):
            packet[key] = [item for item in packet[key] if not (
                item['structure']['call_id'] == hidden['call_id']
                and item['structure']['source_kind'] in ('result', 'observation'))]
        _refresh(packet, index)
        validate_packet(packet, index)
        self.assertEqual(next(row['coverage'] for row in packet['relations']['calls'] if row['call_id'] == hidden['call_id']), 'partial')

    def test_business_exception_fields_and_null_error_are_not_failure_anchors(self):
        from memory_orchestrator.evidence import _failure_position
        self.assertIsNone(_failure_position('{"customer_exception":"none","error":null}'))
        self.assertIsNone(_failure_position('Customer requests a same-week exception despite account flags.'))
        self.assertIsNotNone(_failure_position('ValueError: invalid amount'))
        self.assertIsNotNone(_failure_position('ERROR: tool invocation failed'))
        self.assertIsNotNone(_failure_position('{"error":"access denied"}'))

    def test_goal_transition_needs_its_visible_basis(self):
        ep = episode()
        ep["events"] = [{**event(f"u{i}", "Continue", "instruction", source_role="user", goal_id="A" if i < 19 else "B"),
                         "task_revision": "r1"} for i in range(20)]
        index = index_episodes([ep])
        focus = next(r["base_ref"] for r in index["records"].values() if r["event_id"] == "u19")
        packet = build_packet(index, limits=limits(5000, 30, 0), focus_refs=[focus])
        shown = next(f for f in packet["fragments"] if f["event_id"] == "u19")
        relation = next(r for r in packet["relations"]["goals"] if r["event_ref"] == shown["ref_id"])
        self.assertEqual(relation["goal_id"], "B")
        self.assertEqual(relation["coverage"], "partial")
        self.assertEqual(relation["relation"], "ambiguous")
        self.assertTrue(any("relationship endpoints" in reason for reason in packet["coverage"]["incomplete_reasons"]))

    def test_legacy_packet_remains_readable_and_expansion_upgrades_structure(self):
        ep = episode()
        ep["events"][0]["call_id"] = "legacy-known-call"
        ep["events"][0]["source_role"] = "tool"
        ep["events"] += [event(f"more{i}", "old details " * 100) for i in range(12)]
        index = index_episodes([ep]); current = build_packet(index, limits=limits(6000, 200, 3))
        legacy = copy.deepcopy(current)
        legacy.pop("projection_version"); legacy.pop("relations")
        for item in legacy["fragments"] + legacy["readable_ref_catalog"]:
            item.pop("structure")
        # This is the actual v1 field shape, derived from the unchanged source index.
        before = copy.deepcopy(legacy)
        self.assertEqual(validate_packet(legacy, index), legacy)
        ref = legacy["omitted_refs"][0]
        expanded = expand_packet(index, legacy, [{"ref_id": ref, "purpose": "Read legacy source"}], limits=limits())
        self.assertEqual(legacy, before)
        self.assertEqual(expanded["projection_version"], 2)
        self.assertTrue(all("structure" in f for f in expanded["fragments"] + expanded["readable_ref_catalog"]))
        self.assertTrue({f["ref_id"] for f in legacy["fragments"]} <= {f["ref_id"] for f in expanded["fragments"]})
        self.assertIn(ref, {f["ref_id"] for f in expanded["fragments"]})
        source = next(f for f in expanded["fragments"] if f["event_id"] == ep["events"][0]["event_id"])
        self.assertEqual(source["structure"]["call_id"], "legacy-known-call")
        self.assertEqual(source["structure"]["source_role"], "tool")

    def test_cross_project_context_and_duplicate_event_rejected(self):
        ep = episode(); other = episode(); other.update(episode_id="other", project_id="foreign")
        with self.assertRaises(DomainError): index_episodes([ep, other])
        ep["context_ref"] = "context-1"
        with self.assertRaises(DomainError):
            index_episodes([ep], contexts={"context-1": {"project_id": "foreign"}})
        ep["context_ref"] = None
        ep["events"].append(copy.deepcopy(ep["events"][0]))
        with self.assertRaises(DomainError): index_episodes([ep])

    def test_selection_only_feedback_is_not_model_evidence(self):
        ep = episode()
        fb = copy.deepcopy(EXAMPLES["criterion-feedback"])
        fb.update(subject_ref=ep["episode_id"], visibility="selection_only", reason="PRIVATE ANSWER")
        index = index_episodes([ep], feedback=[fb])
        packet = build_packet(index, limits=limits())
        self.assertNotIn("PRIVATE ANSWER", json.dumps(packet))
        self.assertEqual(index["feedback"], [])
        self.assertNotIn(fb["check_id"], packet["feedback_ids"])

    def test_long_trace_and_single_long_event_are_bounded_and_verifiable(self):
        ep = episode()
        noise = [event(f"noise{i}", "ordinary output " * 100) for i in range(50)]
        ep["events"] = [event("req", "Preserve CSV identifiers", "instruction")] + noise[:25] + [
            event("bad", "x" * 6000 + " ERROR missing schema " + "中" * 6000, "feedback")
        ] + noise[25:] + [event("recover", "Recovery: schema-based retry succeeds", "result")]
        index = index_episodes([ep])
        packet = build_packet(index, limits=limits(8000, 450, 6))
        encoded = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertLessEqual(len(encoded), 8000)
        self.assertTrue({"req", "bad", "recover"}.issubset({f["event_id"] for f in packet["fragments"]}))
        self.assertIn("ERROR missing schema", " ".join(f["text"] for f in packet["fragments"]))
        validate_packet(packet, index)
        bad = next(f for f in packet["fragments"] if f["event_id"] == "bad")
        raw = next(e["text"] for e in ep["events"] if e["event_id"] == "bad").encode()
        self.assertEqual(raw[bad["range"]["start_byte"]:bad["range"]["end_byte_exclusive"]].decode(), bad["text"])
        self.assertEqual(bad["raw_hash"], digest(raw.decode()))

    def test_expand_only_catalogued_ranges_and_reject_raw_tampering(self):
        ep = episode()
        ep["events"] += [event(f"more{i}", "more details " * 80) for i in range(12)]
        index = index_episodes([ep])
        packet = build_packet(index, limits=limits(5000, 300, 4))
        ref = packet["omitted_refs"][0]
        expanded = expand_packet(index, packet, [{"ref_id": ref, "purpose": "inspect omitted source"}], limits=limits(15000, 300, 4))
        self.assertIn(ref, {f["ref_id"] for f in expanded["fragments"]})
        self.assertNotIn(ref, {f["ref_id"] for f in packet["fragments"]})
        with self.assertRaises(DomainError):
            expand_packet(index, packet, [{"ref_id": "foreign", "purpose": "read"}], limits=limits())
        broken = copy.deepcopy(packet); broken["fragments"][0]["text"] += " fabricated"
        with self.assertRaises(DomainError): validate_packet(broken, index)

    def test_catalog_not_citable_until_read_and_other_project_rejected(self):
        ep = episode(); ep["events"] += [event(f"more{i}", "long " * 1000) for i in range(6)]
        index = index_episodes([ep])
        packet = build_packet(index, limits=limits(4500, 200, 3))
        ref = packet["omitted_refs"][0]
        with self.assertRaises(DomainError): validate_citations({"evidence_refs": [ref]}, packet)
        with self.assertRaises(DomainError): validate_citations({"supporting_refs": ["foreign"]}, packet)
        valid = packet["fragments"][0]["ref_id"]
        validate_citations({"observed_facts": [{"evidence_refs": [valid]}]}, packet)
        changed = copy.deepcopy(packet); changed["project_id"] = "foreign"
        with self.assertRaises(DomainError): validate_packet(changed, index)

    def test_goal_suggestion_cannot_use_agent_plan_as_user_revision(self):
        ep = episode(); ep["events"] = [event("plan", "I will change the goal", "note", source_role="agent")]
        index = index_episodes([ep])
        ref = next(iter(index["records"]))
        draft = {"bindings": [{"event_refs": [ref], "goal_id": "invented", "revision": "r1",
                  "relation": "revises", "evidence_refs": [ref]}], "unknowns": []}
        with self.assertRaises(DomainError): validate_goal_bindings(draft, index)

    def test_budget_must_be_explicit_and_cannot_fit_returns_error(self):
        index = index_episodes([episode()])
        with self.assertRaises(DomainError): build_packet(index, limits={})
        with self.assertRaises(DomainError): build_packet(index, limits=limits(100, 10, 0))

    def test_packet_cannot_relabel_revision_feedback_or_budget(self):
        index = index_episodes([episode()])
        packet = build_packet(index, limits=limits())
        for field, replacement in (("task_revision", "invented@1"), ("feedback_ids", ["invented-check"]),
                                   ("source_snapshot_refs", ["invented-snapshot"]), ("token_budget", 1)):
            with self.subTest(field=field):
                changed = copy.deepcopy(packet); changed[field] = replacement
                with self.assertRaises(DomainError): validate_packet(changed, index)
        changed = copy.deepcopy(packet); changed["fragments"][0]["raw_hash"] = "a" * 64
        with self.assertRaises(DomainError): validate_packet(changed, index)

    def test_later_user_revision_cannot_bind_earlier_event(self):
        ep = episode()
        first = event("first", "Earlier observation with unknown goal", "observation", source_role="tool")
        later = event("later", "Now use B", "instruction", source_role="user", goal_id="B")
        later["task_revision"] = "B@1"
        ep["events"] = [first, later]
        index = index_episodes([ep])
        by_event = {value["event_id"]: ref for ref, value in index["records"].items()}
        draft = {"bindings": [{"event_refs": [by_event["first"]], "goal_id": "B", "revision": "B@1",
                  "relation": "revises", "evidence_refs": [by_event["later"]]}], "unknowns": []}
        with self.assertRaises(DomainError): validate_goal_bindings(draft, index)


if __name__ == "__main__": unittest.main()
