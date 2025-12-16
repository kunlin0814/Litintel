
import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add the project root to the path
sys.path.append(os.getcwd())

from src.litintel.enrich.ai_client import enrich_record
from src.litintel.config import AIConfig, AIProvider

class TestLitIntelAIClient(unittest.TestCase):
    @patch('src.litintel.enrich.ai_client._get_openai_client')
    @patch('src.litintel.enrich.ai_client._call_openai')
    def test_enrich_record_escalates_on_none_score(self, mock_call_openai, mock_get_client):
        # Setup
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        
        # Mock responses
        # First call (nano) returns None score
        response_nano = {
            "RelevanceScore": None,
            "WhyRelevant": "Failed parsing",
        }
        # Second call (escalation) returns valid score
        response_escalated = {
            "RelevanceScore": 85,
            "WhyRelevant": "Escalated Success",
            "PipelineConfidence": "Medium"
        }
        
        # side_effect allows returning different values for consecutive calls
        mock_call_openai.side_effect = [
            (response_nano, 100),       # 1st call: Nano -> None
            (response_escalated, 200)   # 2nd call: Escalated -> 85
        ]
        
        config = AIConfig(
            provider=AIProvider.OPENAI,
            model_default="gpt-5-nano",
            model_escalate="gpt-5-mini",
            max_chars=1000,
            prompt_template="Dummy Prompt"
        )
        
        # Execute
        result = enrich_record(
            text="Test text",
            authors="Test Authors",
            pmid="12345",
            config=config,
            system_prompt="System Prompt",
            json_schema={},
            pydantic_model=None
        )
        
        # Verify
        self.assertEqual(mock_call_openai.call_count, 2)
        # Check that the second call was made with the escalation model
        args_call_2 = mock_call_openai.call_args_list[1]
        self.assertEqual(args_call_2[0][1], "gpt-5-mini") # model arg is 2nd pos
        
        self.assertEqual(result["RelevanceScore"], 85)
        self.assertEqual(result["WhyRelevant"], "Escalated Success")
        print("Test passed: LitIntel AI Client Escalates on None Score")

if __name__ == '__main__':
    unittest.main()
