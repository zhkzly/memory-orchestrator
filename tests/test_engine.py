"""Core API behavior with actual temporary files, without native Agents."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory_orchestrator import MemorySystem
from memory_orchestrator.common import DomainError, digest, load_contracts


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.memory = MemorySystem(self.tmp.name)

    def test_record_accepts_unknown_context_and_feedback(self):
        episode = self.memory.record("convert a CSV", "alpha", ["observed id 00123 became 123"])
        self.assertIsNone(episode["task_id"])
        self.assertIsNone(episode["snapshot_id"])
        self.assertEqual(episode["feedback"], [])
        self.assertEqual(self.memory.episode(episode["id"])["events"][0]["text"], "observed id 00123 became 123")

    def test_context_roundtrip_and_delayed_feedback_do_not_rewrite_episode(self):
        context = self.memory.recall("CSV conversion", "alpha")
        episode = self.memory.record("CSV conversion", "alpha", ["conversion completed"],
                                     task_id="csv-1", task_revision="v1", context_id=context["id"])
        before = copy.deepcopy(self.memory.store.get("episodes", episode["id"]))
        self.memory.add_feedback(episode["id"], {"outcome": "fail", "source": "human", "text": "leading zeros lost"}, state_ref="artifact-v1")
        self.assertEqual(before, self.memory.store.get("episodes", episode["id"]))
        updated = self.memory.episode(episode["id"])
        self.assertEqual(updated["snapshot_id"], context["snapshot_id"])
        self.assertEqual(updated["feedback"][0]["value"]["outcome"], "fail")
        self.assertEqual(updated["feedback"][0]["state_ref"], "artifact-v1")
        self.assertEqual(updated["task_revision"], "v1")

    def test_cross_project_context_is_rejected(self):
        context = self.memory.recall("task", "alpha")
        with self.assertRaises(DomainError):
            self.memory.record("task", "beta", ["data"], context_id=context["id"])

    def test_unknown_feedback_is_not_promoted_to_success(self):
        episode = self.memory.record("task", "alpha", [])
        self.memory.add_feedback(episode["id"], {"outcome": "unknown", "source": "external", "text": "checker unavailable"})
        self.assertEqual(self.memory.episode(episode["id"])["feedback"][0]["value"]["outcome"], "unknown")
        with self.assertRaises(DomainError):
            self.memory.add_feedback(episode["id"], {"outcome": "awesome"})

    def test_invalid_observation_does_not_create_partial_record(self):
        with self.assertRaises(DomainError):
            self.memory.record("task", "alpha", [{"kind": "observation"}])
        self.assertEqual(self.memory.store.list("episodes"), [])

    def test_learning_requires_model_and_same_project(self):
        a = self.memory.record("a", "alpha", ["a"])
        with self.assertRaises(DomainError):
            self.memory.learn([a["id"]])
        b = self.memory.record("b", "beta", ["b"])
        self.memory.model = object()
        with self.assertRaises(DomainError):
            self.memory.learn([a["id"], b["id"]])

    def test_learning_persists_noop_and_usage_without_changing_facts(self):
        self.memory.remember("user", "Prefer concise answers", source="explicit instruction")
        ep = self.memory.record("task", "alpha", ["network timed out"])
        before = copy.deepcopy(self.memory.store.facts("alpha"))
        active = copy.deepcopy(self.memory.store.active("alpha"))
        self.memory.model = object()
        reply = {"status": "noop", "experiences": [], "diagnosis": {"route": "external_issue"},
                 "patch": None, "usage": [{"stage": "diagnose", "input_tokens": None, "output_tokens": None}], "errors": []}
        with patch("memory_orchestrator.engine.learn_from_episodes", return_value=reply):
            outcome = self.memory.learn([ep["id"]])
        self.assertEqual(outcome["candidate_ids"], [])
        self.assertEqual(outcome["status"], "noop")
        self.assertEqual(before, self.memory.store.facts("alpha"))
        self.assertEqual(active, self.memory.store.active("alpha"))
        self.assertEqual(len(outcome["usage_ids"]), 1)
        self.assertIsNone(self.memory.store.get("usage", outcome["usage_ids"][0])["input_tokens"])


if __name__ == "__main__":
    unittest.main()
