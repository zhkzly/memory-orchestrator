"""The evaluation scope reaches diagnosis in the actual learning call path.

The CSV task and scope are the same executable scenario used by the saved live
canary; this checks disclosure, not that a model will obey or learn correctly.
"""
from copy import deepcopy
import json
import tempfile
import unittest

from examples.memory_evolution.demo import ScriptedTeacher, LEARNING, run_demo
from memory_orchestrator.model import StructuredModel


class PromptScopeTests(unittest.TestCase):
    def test_diagnosis_gets_scope_before_it_commits_verification_obligations(self):
        observed = {}
        class Teacher(ScriptedTeacher):
            def generate(self, prompt_id, inputs, **kwargs):
                result = super().generate(prompt_id, inputs, **kwargs)
                if prompt_id == 'diagnose_v1':
                    observed.update(inputs=deepcopy(inputs), draft=deepcopy(result['value']))
                return result
        teacher = Teacher()
        with tempfile.TemporaryDirectory() as root:
            run_demo(root, model=teacher, rounds=1)
        self.assertEqual(observed['inputs'].get('evaluation_scope'), LEARNING['evaluation_scope'])
        messages = []
        def invoke(request):
            messages.extend(request['messages'])
            return {'text': json.dumps(observed['draft']), 'finish_reason': 'stop'}
        StructuredModel(invoke, limits=teacher.limits).generate('diagnose_v1', observed['inputs'])
        self.assertIn(LEARNING['evaluation_scope'], messages[1]['content'])
        self.assertIn('发布必需', messages[0]['content'])
        self.assertIn('并集', messages[0]['content'])
        self.assertIn('null', messages[0]['content'])


if __name__ == '__main__':
    unittest.main()
