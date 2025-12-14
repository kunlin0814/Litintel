import unittest
import sys
import os
from pydantic import ValidationError

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from litintel.enrich.schema import Tier2Record

class TestSchemaValidation(unittest.TestCase):
    def test_valid_tier2_record(self):
        data = {
            "PMID": "12345678",
            "Title": "Test Paper",
            "Abstract": "Abstract here.",
            "RelevanceScore": 90,
            "WhyRelevant": "Relevant because...",
            "StudySummary": "Summary.",
            "PI_Group": "Lab X",
            "ProblemArea": "integration",
            "MethodName": "ToolY",
            "MethodRole": "Role Z",
            "InputsRequired": "Data A",
            "KeyParameters": "Param B",
            "AssumptionsFailureModes": "None",
            "EvidenceContext": "Simulated",
            "DataTypes": "scRNA-seq"
        }
        # Should raise no error
        rec = Tier2Record(**data)
        self.assertEqual(rec.PMID, "12345678")

    def test_invalid_relevance_score_type(self):
        # RelevanceScore must be int
        data = {
            "PMID": "123",
            "Title": "T",
            "Abstract": "A",
            "RelevanceScore": "High", # Invalid
        }
        with self.assertRaises(ValidationError):
            Tier2Record(**data)

    def test_missing_required_field_defaults(self):
        # BaseRecord requires PMID, Title, Abstract. Others have defaults.
        data = {
            "PMID": "123",
            "Title": "T",
            "Abstract": "A",
            # Missing RelevanceScore, etc.
        }
        # Should pass because Pydantic models define defaults (0, "")
        rec = Tier2Record(**data)
        self.assertEqual(rec.RelevanceScore, 0)
        
    def test_extra_fields_ignored_or_allowed(self):
        # Pydantic BaseConfig default is 'ignore' extra arguments usually, let's verify behavior
        data = {
            "PMID": "123",
            "Title": "T",
            "Abstract": "A",
            "ExtraField": "Should be ignored"
        }
        rec = Tier2Record(**data)
        # Verify ExtraField is not on object if strict? 
        # By default pydantic ignores.
        self.assertFalse(hasattr(rec, "ExtraField"))

if __name__ == "__main__":
    unittest.main()
