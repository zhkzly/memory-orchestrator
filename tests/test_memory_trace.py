"""Constructed UTF-8 JSONL sources exercise actual disk indexing and learn input."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory_orchestrator.schemas import DomainError
from memory_orchestrator.store import Store
from memory_orchestrator.trace import import_trace, ensure_trace_index
from memory_orchestrator.evidence import index_episodes, build_packet, expand_packet
from test_memory_evidence import episode, event, limits


class TraceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "store")
        self.source = Path(self.tmp.name) / "events.jsonl"
        self.events = [event("e" + str(i), ("失败 Unicode🙂 " if i == 7 else "ordinary ") + "数据 " * 1000,
                             "observation") for i in range(12)]
        self.events[7]["resources"] = [{"kind": "file", "ref": "input.csv", "access": "check", "version_ref": "v1"}]
        self.events[2]["resources"] = [{"kind": "file", "ref": "input.csv", "access": "write", "version_ref": "v1"}]
        self.source.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in self.events))
        self.caps = {"max_events": 5, "max_bytes": 100000, "max_event_bytes": 40000}
        self.ep = episode(); self.ep["events"] = []

    def test_resume_reopen_and_exact_multibyte_ranges_without_whole_file_text_load(self):
        original_read = Path.read_text
        def guarded(path, *args, **kwargs):
            if path.suffix in (".jsonl", ".text"): raise AssertionError("No whole-file source text loading")
            return original_read(path, *args, **kwargs)
        with patch.object(Path, "read_text", guarded):
            imported = import_trace(self.store, self.ep, self.source, limits=self.caps)
            with self.assertRaises(DomainError) as caught:
                index_episodes([imported], store=self.store, trace_limits=self.caps)
            self.assertEqual(caught.exception.code, "needs_index")
            reopened = Store(self.store.root)
            _, progress = ensure_trace_index(reopened, imported["trace_ref"], self.caps)
            self.assertFalse(progress["index_complete"])
            index = index_episodes([imported], store=reopened, trace_limits=self.caps)
            packet = build_packet(index, limits=limits(14000, 120, 4))
        self.assertEqual(packet["coverage"]["total_event_count"], 12)
        self.assertTrue(packet["coverage"]["incomplete_reasons"])
        for fragment in packet["fragments"]:
            if fragment["event_id"] == "task": continue
            original = next(e for e in self.events if e["event_id"] == fragment["event_id"])["text"].encode()
            r = fragment["range"]
            self.assertEqual(fragment["text"].encode(), original[r["start_byte"]:r["end_byte_exclusive"]])
            self.assertEqual(fragment["source_record"]["trace_ref"], imported["trace_ref"])
        read = next(c for c in packet["readable_ref_catalog"] if c["ref_id"] not in {f["ref_id"] for f in packet["fragments"]})
        expanded = expand_packet(index, packet, [{"ref_id": read["ref_id"], "purpose": "inspect evidence"}], limits=limits(30000))
        self.assertIn(read["ref_id"], {f["ref_id"] for f in expanded["fragments"]})
        self.assertLess(index["read_stats"]["body_bytes"], sum(len(e["text"].encode()) for e in self.events))

    def test_archived_source_tamper_invalidates_existing_reader(self):
        imported = import_trace(self.store, self.ep, self.source, limits=self.caps)
        big = {**self.caps, "max_events": 50, "max_bytes": 1000000}
        index = index_episodes([imported], store=self.store, trace_limits=big)
        manifest = self.store.get("trace_manifests", imported["trace_ref"])
        path = self.store.root / manifest["raw_path"]
        with path.open("r+b") as handle: handle.write(b"X")
        with self.assertRaises(DomainError) as caught: build_packet(index, limits=limits())
        self.assertEqual(caught.exception.code, "trace_mismatch")

    def test_cold_index_rejects_changed_raw_bytes_before_any_record_query(self):
        imported = import_trace(self.store, self.ep, self.source, limits=self.caps)
        manifest = self.store.get("trace_manifests", imported["trace_ref"])
        path = self.store.root / manifest["raw_path"]
        with path.open("r+b") as handle: handle.seek(10); handle.write(b"X")
        with self.assertRaises(DomainError) as caught:
            ensure_trace_index(Store(self.store.root), imported["trace_ref"], self.caps)
        self.assertEqual(caught.exception.code, "trace_mismatch")
        self.assertEqual(self.store.list("trace_index_checkpoints"), [])

    def test_byte_budget_can_resume_with_a_larger_declared_budget_and_keeps_failure(self):
        imported = import_trace(self.store, self.ep, self.source, limits=self.caps)
        with self.assertRaises(DomainError):
            ensure_trace_index(self.store, imported["trace_ref"], {**self.caps, "max_bytes": 20})
        checkpoints = self.store.list("trace_index_checkpoints", self.ep["project_id"])
        self.assertEqual(checkpoints[0]["next_raw_byte"], 0)
        self.assertEqual(checkpoints[0]["error"]["code"], "trace_event_budget")
        reader, progress = ensure_trace_index(self.store, imported["trace_ref"], self.caps)
        self.assertEqual(progress["event_count"], 5)
        self.assertIsNone(progress["error"])
        self.assertEqual(len(self.store.list("trace_index_checkpoints", self.ep["project_id"])), 2)

    def test_malformed_record_retains_raw_locator_and_cannot_become_complete(self):
        self.source.write_bytes(b'{"broken": true}\n')
        imported = import_trace(self.store, self.ep, self.source, limits=self.caps)
        with self.assertRaises(DomainError) as caught:
            ensure_trace_index(self.store, imported["trace_ref"], self.caps)
        self.assertEqual(caught.exception.code, "trace_index_invalid")
        self.assertEqual(caught.exception.details["error"]["raw_range"], [0, 17])
        self.assertFalse(caught.exception.details["index_complete"])
        with self.assertRaises(DomainError): ensure_trace_index(self.store, imported["trace_ref"], self.caps)

    def test_symlinked_archive_does_not_become_a_new_source(self):
        imported = import_trace(self.store, self.ep, self.source, limits=self.caps)
        manifest = self.store.get("trace_manifests", imported["trace_ref"])
        path = self.store.root / manifest["raw_path"]
        path.unlink(); path.symlink_to(self.source)
        with self.assertRaises(DomainError) as caught: ensure_trace_index(self.store, imported["trace_ref"], self.caps)
        self.assertEqual(caught.exception.code, "UNSAFE_PATH")

    def test_file_dependency_is_retrieved_as_candidate_not_claimed_causality(self):
        imported = import_trace(self.store, self.ep, self.source, limits=self.caps)
        index = index_episodes([imported], store=self.store, trace_limits={**self.caps, "max_events": 50})
        focus = next(r["base_ref"] for r in index["records"].values() if r["event_id"] == "e7")
        packet = build_packet(index, limits=limits(19000, 100, 4), focus_refs=[focus],
                              dependency_limits={"max_hops": 2, "max_events": 4})
        relations = packet["resource_relations"]
        self.assertTrue(any(r["resource_ref"] == "input.csv" and r["relation"] == "same_resource_candidate" for r in relations))
        self.assertTrue(any(f["event_id"] == "e2" for f in packet["fragments"]))

    def test_actual_learn_waits_for_index_then_supplies_source_backed_fragments(self):
        from memory_orchestrator.learning import learn
        from memory_orchestrator.model import StructuredModel
        from test_memory_learning import policy
        from test_memory_model import FakeCall, response, limits as model_limits
        from test_memory_evidence import EXAMPLES
        imported = import_trace(self.store, self.ep, self.source, limits=self.caps)
        caps = policy(trace_index=self.caps, dependency_lookup={"max_hops": 2, "max_events": 4})
        transport = FakeCall([response(EXAMPLES["abstain"])])
        model = StructuredModel(transport, limits=model_limits())
        first = learn(self.store, [imported["episode_id"]], model, policy=caps)
        self.assertEqual(first["status"], "needs_index")
        self.assertEqual(transport.calls, [])
        second = learn(self.store, [imported["episode_id"]], model, policy=caps)
        self.assertEqual(second["status"], "needs_index")
        result = learn(self.store, [imported["episode_id"]], model, policy=caps)
        self.assertEqual(result["status"], "abstained")
        text = transport.calls[0]["messages"][1]["content"]
        packet, _ = json.JSONDecoder().raw_decode(text.split("证据包及缺口：", 1)[1].lstrip())
        self.assertEqual(packet["coverage"]["total_event_count"], 12)
        self.assertIn(imported["trace_ref"], json.dumps(packet))
        self.assertTrue(result["trace_checkpoint_ids"])

    def test_archived_frozen_parent_cannot_reenter_learning_via_empty_header(self):
        from memory_orchestrator.learning import learn
        from memory_orchestrator.sampling import sample_tasks
        from test_memory_learning import policy
        from test_memory_model import FakeCall, limits as model_limits
        from memory_orchestrator.model import StructuredModel
        frozen = sample_tasks(self.store,
            [{"project_id": self.ep["project_id"], "task_id": "private", "revision": "v1", "description": "held out"}],
            lambda *args: {"artifact": "private result"}, None,
            policy={"purpose": "final", "update_mode": "none", "repeat_count": 1, "max_parallel": 1,
                    "protocol_id": "test", "executor": {"id": "fixture", "config": {}}},
            context_policy={"max_roots": 1, "max_context_chars": 5000, "relation_weight": 0})["episodes"][0]
        self.events[0].update(parent_episode_id=frozen["episode_id"], parent_event_id="instruction")
        self.source.write_text("".join(json.dumps(e) + "\n" for e in self.events))
        imported = import_trace(self.store, self.ep, self.source, limits=self.caps)
        transport = FakeCall([])
        result = learn(self.store, [imported["episode_id"]], StructuredModel(transport, limits=model_limits()),
                       policy=policy(trace_index={**self.caps, "max_events": 50, "max_bytes": 1000000}))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["errors"][0]["code"], "learning_not_permitted")
        self.assertEqual(transport.calls, [])

    def test_zero_dependency_body_budget_still_indexes_transitive_source_eligibility(self):
        from memory_orchestrator.learning import learn
        from memory_orchestrator.sampling import sample_tasks
        from test_memory_learning import policy
        from test_memory_model import FakeCall, response, limits as model_limits
        from test_memory_evidence import EXAMPLES
        from memory_orchestrator.model import StructuredModel
        frozen = sample_tasks(self.store,
            [{"project_id": self.ep["project_id"], "task_id": "private-ancestor", "revision": "v1", "description": "held out"}],
            lambda *args: {"artifact": "private result"}, None,
            policy={"purpose": "final", "update_mode": "none", "repeat_count": 1, "max_parallel": 1,
                    "protocol_id": "test", "executor": {"id": "fixture", "config": {}}},
            context_policy={"max_roots": 1, "max_context_chars": 5000, "relation_weight": 0})["episodes"][0]
        parent_event = event("bridge", "derived from another execution", parent_episode_id=frozen["episode_id"], parent_event_id="instruction")
        self.source.write_text(json.dumps(parent_event) + "\n")
        imported = import_trace(self.store, self.ep, self.source, limits=self.caps)
        child = copy.deepcopy(self.ep); child["episode_id"] = "inline-child"
        child["events"] = [event("child", "apparently ordinary result", parent_episode_id=imported["episode_id"], parent_event_id="bridge")]
        self.store.add_episode(child)
        transport = FakeCall([response(EXAMPLES["abstain"])])
        result = learn(self.store, [child["episode_id"]], StructuredModel(transport, limits=model_limits()),
            policy=policy(trace_index=self.caps, dependency_lookup={"max_hops": 0, "max_events": 0}))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["errors"][0]["code"], "learning_not_permitted")
        self.assertEqual(transport.calls, [])


if __name__ == "__main__": unittest.main()
