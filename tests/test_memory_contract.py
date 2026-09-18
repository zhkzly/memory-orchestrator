"""The same persisted result must have one shape inside and outside a validation."""
import unittest

from memory_orchestrator.schemas import load_contracts


class EmbeddedContractTests(unittest.TestCase):
    def test_validation_embeds_the_same_evaluation_result_contract(self):
        schemas = load_contracts()["schemas"]
        standalone = {key: value for key, value in schemas["EvaluationResult"].items()
                      if key != "$schema"}
        self.assertEqual(standalone, schemas["ValidationRecord"]["properties"]["results"]["items"])


if __name__ == "__main__":
    unittest.main()
