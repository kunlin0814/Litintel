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
    def test_enrich_record_normalizes_none_score_to_zero(self, mock_call_openai, mock_get_client):
        """Test that None RelevanceScore is normalized to 0 (no escalation in new flow)."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        
        usage = {"input": 100, "output": 50, "cached": 10}
        # Returns None score - should be normalized to 0
        response = {
            "RelevanceScore": None,
            "WhyRelevant": "Some reason",
        }
        
        mock_call_openai.return_value = (response, usage)
        
        config = AIConfig(
            provider=AIProvider.OPENAI,
            model_default="gpt-5-nano",
            model_escalate="gpt-5-mini",
            max_chars=1000,
            prompt_template="Dummy Prompt"
        )
        
        result = enrich_record(
            text="Test text",
            authors="Test Authors",
            pmid="12345",
            config=config,
            system_prompt="System Prompt",
            json_schema={},
            pydantic_model=None
        )
        
        # New behavior: single call, score normalized to 0
        self.assertEqual(mock_call_openai.call_count, 1)
        self.assertEqual(result["RelevanceScore"], 0)
        self.assertEqual(result["WhyRelevant"], "Some reason")

    @patch('src.litintel.enrich.ai_client._get_openai_client')
    @patch('src.litintel.enrich.ai_client._call_openai')
    def test_enrich_record_returns_valid_score(self, mock_call_openai, mock_get_client):
        """Test that valid scores are returned correctly."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        
        usage = {"input": 100, "output": 50, "cached": 10}
        response = {
            "RelevanceScore": 85,
            "WhyRelevant": "Valid reason",
        }
        
        mock_call_openai.return_value = (response, usage)
        
        config = AIConfig(
            provider=AIProvider.OPENAI,
            model_default="gpt-5-nano",
            model_escalate="gpt-5-mini",
            max_chars=1000,
            prompt_template="Dummy Prompt"
        )
        
        result = enrich_record(
            text="Test text",
            authors="Test Authors",
            pmid="12345",
            config=config,
            system_prompt="System Prompt",
            json_schema={},
            pydantic_model=None
        )
        
        self.assertEqual(mock_call_openai.call_count, 1)
        self.assertEqual(result["RelevanceScore"], 85)
        self.assertEqual(result["WhyRelevant"], "Valid reason")

if __name__ == '__main__':
    unittest.main()
