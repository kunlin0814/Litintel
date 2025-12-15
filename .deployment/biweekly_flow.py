"""
Tier 1 Pipeline Deployment Flow (Prefect).

Wraps the new 'litintel' Tier 1 Gold Standard pipeline.
"""

import sys
import os
from prefect import flow, get_run_logger

# Ensure src is in path for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(script_dir)
if os.path.join(root_dir, "src") not in sys.path:
    sys.path.insert(0, os.path.join(root_dir, "src"))

from litintel.pipeline.tier1 import run_tier1_pipeline
from litintel.config import load_config_from_yaml

@flow(name="PCa-Tier1-GoldStandard-Pipeline")
def tier1_literature_flow():
    """
    Runs the Tier 1 Prostate Cancer Spatial Omics Pipeline.
    
    Configuration is loaded from 'configs/tier1_pca.yaml' in the repo.
    """
    logger = get_run_logger()
    logger.info("🚀 Starting Tier 1 Pipeline Deployment")
    
    # Path to config relative to repo root
    config_path = os.path.join(root_dir, "configs", "tier1_pca.yaml")
    
    if not os.path.exists(config_path):
        logger.error(f"Config file not found at {config_path}")
        raise FileNotFoundError(f"Config not found: {config_path}")
        
    try:
        config = load_config_from_yaml(config_path)
        
        # Override storage settings for Cloud execution if needed?
        # For now, we trust the env vars (NOTION_TOKEN, etc.) are set in Prefect Block or Environment.
        
        run_tier1_pipeline(config)
        
        logger.info("✅ Pipeline execution completed")
        
    except Exception as e:
        logger.error(f"Pipeline Failed: {e}")
        raise e

if __name__ == "__main__":
    tier1_literature_flow()

