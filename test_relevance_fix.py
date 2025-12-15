#!/usr/bin/env python3
"""
Quick test script to verify RelevanceScore is properly returned by AI.
Tests the fix for the RelevanceScore=0 issue.
"""
import os
import sys
import logging
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

load_dotenv()

# Configure logging to see debug output
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s - %(name)s - %(message)s'
)

from litintel.enrich.ai_client import enrich_record
from litintel.enrich.schema import Tier1Record
from litintel.enrich.prompt_templates import get_system_prompt
from litintel.config import AIConfig, AIProvider

# Test with a known prostate cancer paper
TEST_PMID = "39475794"
TEST_TITLE = "Spatial multi-omics reveals stromal fibroblast heterogeneity and immune escape in prostate cancer"
TEST_ABSTRACT = """This study uses spatial transcriptomics and proteomics to map the tumor microenvironment 
in prostate cancer. We identified heterogeneous cancer-associated fibroblast populations and their role in 
immune evasion. Single-cell RNA-seq and spatial ATAC-seq were integrated to characterize chromatin accessibility 
patterns in the tumor and stroma."""

TEST_AUTHORS = "Smith J, Johnson A, Williams B"

def main():
    print("=" * 80)
    print("Testing RelevanceScore Fix")
    print("=" * 80)
    
    # Create AI config (using OpenAI as specified in tier1_pca.yaml)
    ai_config = AIConfig(
        provider=AIProvider.OPENAI,
        model_default="gpt-4o-mini",  # Use the actual model
        model_escalate="gpt-4o",
        prompt_template="tier1_pca"
    )
    
    system_prompt = get_system_prompt("tier1_pca")
    
    print(f"\n➡️  Testing PMID: {TEST_PMID}")
    print(f"    Title: {TEST_TITLE[:60]}...")
    print(f"\n🤖 Calling AI with fixed prompt template...\n")
    
    try:
        enrichment = enrich_record(
            text=f"Title: {TEST_TITLE}\nAbstract: {TEST_ABSTRACT}",
            authors=TEST_AUTHORS,
            pmid=TEST_PMID,
            config=ai_config,
            system_prompt=system_prompt,
            json_schema=Tier1Record.model_json_schema(),
            pydantic_model=Tier1Record,
            group_fallback="Williams B",
            geo_candidates="",
            sra_candidates=""
        )
        
        print("\n" + "=" * 80)
        print("✅ AI RESPONSE RECEIVED")
        print("=" * 80)
        
        relevance_score = enrichment.get("RelevanceScore", "NOT FOUND")
        
        print(f"\n📊 RelevanceScore: {relevance_score}")
        print(f"📝 WhyRelevant: {enrichment.get('WhyRelevant', 'N/A')[:100]}...")
        print(f"🔬 DataTypes: {enrichment.get('DataTypes', 'N/A')}")
        print(f"👥 Group: {enrichment.get('Group', 'N/A')}")
        
        print("\n" + "=" * 80)
        if isinstance(relevance_score, int) and relevance_score > 0:
            print(f"✅ SUCCESS! RelevanceScore = {relevance_score} (non-zero)")
            print("=" * 80)
            return 0
        else:
            print(f"❌ FAILED! RelevanceScore = {relevance_score} (expected > 0)")
            print("=" * 80)
            print("\nDEBUG: Full enrichment response:")
            import json
            print(json.dumps(enrichment, indent=2))
            return 1
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
