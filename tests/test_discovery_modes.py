import unittest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from litintel.config import AppConfig, DiscoveryMode, DiscoveryConfig, AIConfig, AIProvider, StorageConfig, DedupConfig, NotionConfig, CsvConfig
from litintel.pipeline.tier2 import run_tier2_pipeline

# Create partial config helper
def create_mock_config(mode: DiscoveryMode, seed_authors=None, keyword_queries=None):
    # Dummy objects to satisfy Pydantic
    # We construct raw dict and load via Pydantic or just mock object structure
    # Since we imported AppConfig class:
    
    return AppConfig(
        pipeline_tier=2,
        pipeline_name="Test",
        discovery=DiscoveryConfig(
            mode=mode,
            seed_authors=seed_authors if seed_authors else [],
            keyword_queries=keyword_queries if keyword_queries else [],
            retmax=10,
            reldays=10
        ),
        ai=AIConfig(
            provider=AIProvider.OPENAI,
            model_default="gpt-4",
            model_escalate="gpt-4",
            prompt_template="tier2_methods"
        ),
        storage=StorageConfig(
            csv=CsvConfig(enabled=False, filename="test.csv"),
            notion=NotionConfig(enabled=False, database_id_env="TEST_DB")
        ), 
        dedup=DedupConfig()
    )

# Actually simplest is to mock the config object passed to run_tier2_pipeline
class MockConfig:
    def __init__(self, mode, seeds=None, keywords=None):
        self.pipeline_name = "Test"
        self.discovery = MagicMock()
        self.discovery.mode = mode
        self.discovery.seed_authors = seeds or []
        self.discovery.keyword_queries = keywords or []
        self.discovery.retmax = 10
        self.discovery.reldays = 10
        self.dedup = MagicMock()
        self.dedup.keys = ["PMID"]
        self.ai = MagicMock()
        self.ai.prompt_template = "tier2_methods"
        self.storage = MagicMock()
        self.storage.csv.enabled = False
        self.storage.notion.enabled = False

class TestDiscoveryModes(unittest.TestCase):
    
    @patch('litintel.pipeline.tier2.search_pubmed')
    @patch('litintel.pipeline.tier2.fetch_details')
    @patch('litintel.pipeline.tier2.parse_pubmed_xml_stream')
    def test_author_seeded_mode(self, mock_parse, mock_fetch, mock_search):
        # Setup
        # Return empty to stop pipeline early
        mock_search.return_value = []
        
        cfg = MockConfig(DiscoveryMode.AUTHOR_SEEDED, seeds=["Author A", "Author B"])
        
        # execution
        run_tier2_pipeline(cfg)
        
        # check calls
        # Should call search for each author
        self.assertEqual(mock_search.call_count, 2)
        # Check arguments contain author names
        args, _ = mock_search.call_args_list[0]
        self.assertTrue("Author A" in args[0])
        
    @patch('litintel.pipeline.tier2.search_pubmed')
    @patch('litintel.pipeline.tier2.fetch_details')
    @patch('litintel.pipeline.tier2.parse_pubmed_xml_stream')
    def test_keyword_mode(self, mock_parse, mock_fetch, mock_search):
        mock_search.return_value = []
        cfg = MockConfig(DiscoveryMode.KEYWORD, keywords=["Query 1"])
        
        run_tier2_pipeline(cfg)
        
        self.assertEqual(mock_search.call_count, 1)
        self.assertTrue("Query 1" in mock_search.call_args[0][0])
        
    @patch('litintel.pipeline.tier2.search_pubmed')
    @patch('litintel.pipeline.tier2.fetch_details')
    @patch('litintel.pipeline.tier2.parse_pubmed_xml_stream')
    def test_mixed_mode(self, mock_parse, mock_fetch, mock_search):
        mock_search.return_value = []
        cfg = MockConfig(DiscoveryMode.MIXED, seeds=["Author A"], keywords=["Query 1"])
        
        run_tier2_pipeline(cfg)
        
        # 1 seed + 1 keyword = 2 calls
        self.assertEqual(mock_search.call_count, 2)

if __name__ == "__main__":
    unittest.main()
