"""
Integration tests for the LitIntel pipeline.

These tests call real APIs and require environment variables to be set.
They are skipped by default unless explicitly enabled with:
    pytest tests/test_integration.py --run-integration

Required environment variables:
    - OPENAI_API_KEY
    - NCBI_API_KEY (optional but recommended)
    - NCBI_EMAIL (optional but recommended)
"""

import os
import pytest
import sys

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


@pytest.fixture
def openai_api_key():
    """Fixture that provides OPENAI_API_KEY or skips test."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        pytest.skip("OPENAI_API_KEY not set")
    return key


@pytest.mark.integration
class TestIntegrationPipeline:
    """Integration tests that call real APIs."""

    def test_enrich_single_record_openai(self, openai_api_key):
        """Test enriching a single record with OpenAI API."""
        from src.litintel.enrich.ai_client import enrich_record
        from src.litintel.config import AIConfig, AIProvider
        from src.litintel.enrich.prompt_templates import get_system_prompt

        config = AIConfig(
            provider=AIProvider.OPENAI,
            model_default="gpt-5-nano",
            model_escalate="gpt-5-mini",
            max_chars=10000,
            prompt_template="tier1_pca"
        )

        system_prompt = get_system_prompt(config.prompt_template)
        
        # Sample abstract for prostate cancer paper
        test_text = """
        Title: Single-cell spatial transcriptomics reveals tumor heterogeneity in prostate cancer
        
        Abstract: We performed Visium spatial transcriptomics and single-nucleus RNA-seq 
        on 50 prostate cancer samples to identify tumor microenvironment heterogeneity. 
        Using SCTransform normalization and Harmony integration, we identified 15 distinct 
        cell clusters. Key findings include novel CAF subtypes expressing ACTA2 and FAP,
        and spatial co-localization of exhausted T cells with tumor cells.
        """

        result = enrich_record(
            text=test_text,
            authors="Smith J, Doe A, Johnson B",
            pmid="99999999",  # Fake PMID
            config=config,
            system_prompt=system_prompt,
            json_schema={},
            pydantic_model=None
        )

        # Basic validation
        assert "RelevanceScore" in result
        assert isinstance(result["RelevanceScore"], int)
        assert result["RelevanceScore"] >= 0
        
        assert "WhyRelevant" in result
        assert len(result["WhyRelevant"]) > 10  # Should have some explanation
        
        print(f"RelevanceScore: {result['RelevanceScore']}")
        print(f"WhyRelevant: {result['WhyRelevant']}")
        print(f"WhyYouMightCare: {result.get('WhyYouMightCare', 'N/A')}")

    def test_escalation_heuristics(self, openai_api_key):
        """Test that escalation heuristics work correctly."""
        from src.litintel.enrich.escalation_heuristics import should_escalate
        from src.litintel.config import EscalationTriggersConfig

        config = EscalationTriggersConfig()

        # Test H1: Short rationale should trigger
        result_short = {"WhyRelevant": "Short", "RelevanceScore": 85}
        should_esc, signals = should_escalate(result_short, config)
        assert should_esc, "Short rationale should trigger H1"
        assert "H1" in str(signals)

        # Test H2: Score in range should trigger
        result_ambiguous = {"WhyRelevant": "This is a sufficiently long rationale for testing", "RelevanceScore": 75}
        should_esc, signals = should_escalate(result_ambiguous, config)
        assert should_esc, "Score 75 should trigger H2"
        assert "H2" in str(signals)

        # Test no trigger for high-confidence result
        result_good = {"WhyRelevant": "This is a sufficiently long rationale for testing purposes", "RelevanceScore": 90}
        should_esc, signals = should_escalate(result_good, config)
        assert not should_esc, "Score 90 with good rationale should not trigger"


@pytest.mark.integration  
class TestIntegrationShadowJudge:
    """Test Shadow Judge integration."""

    def test_shadow_judge_pass(self, openai_api_key):
        """Test that Shadow Judge correctly validates a good response."""
        from src.litintel.enrich.ai_client import _shadow_judge, _get_openai_client

        client = _get_openai_client()
        
        nano_output = {
            "RelevanceScore": 85,
            "WhyRelevant": "Prostate cancer with Visium spatial transcriptomics - highly relevant",
            "StudySummary": "This study uses Visium to profile prostate cancer tumor microenvironment."
        }
        
        abstract = "We performed Visium spatial transcriptomics on prostate cancer samples."
        methods = "We used 10x Genomics Visium platform. Samples were processed following standard protocols."
        results = "We identified 15 distinct cell clusters in the tumor microenvironment."

        override, decision, details = _shadow_judge(
            client=client,
            nano_output=nano_output,
            abstract=abstract,
            methods=methods,
            results=results,
            pmid="12345",
            model="gpt-5-mini"
        )

        print(f"Decision: {decision}")
        print(f"Override: {override}")
        print(f"Details: {details}")

        # Good response should pass
        assert decision in ["PASS", "DISAGREE"], f"Expected PASS or DISAGREE, got {decision}"
        assert not override, "Should not override a valid response"
