import typer
import yaml
import logging
from rich.logging import RichHandler
from pathlib import Path

from litintel.config import AppConfig
from litintel.pipeline.tier1 import run_tier1_pipeline
from litintel.pipeline.tier2 import run_tier2_pipeline

# Configure Logging
logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)]
)
logger = logging.getLogger("litintel")

app = typer.Typer(help="Literature Intelligence CLI")

def load_config(config_path: str) -> AppConfig:
    with open(config_path, "r") as f:
        raw_config = yaml.safe_load(f)
    try:
        return AppConfig(**raw_config)
    except Exception as e:
        logger.error(f"Config validation error: {e}")
        raise typer.Exit(1)

@app.command()
def tier1(config: str = "configs/tier1_pca.yaml"):
    """Run Tier-1 (PCa) Pipeline"""
    cfg = load_config(config)
    run_tier1_pipeline(cfg)

@app.command()
def tier2(config: str = "configs/tier2_methods.yaml"):
    """Run Tier-2 (Methods) Pipeline"""
    cfg = load_config(config)
    run_tier2_pipeline(cfg)

@app.command()
def validate(config: str):
    """Validate a configuration file"""
    try:
        cfg = load_config(config)
        logger.info(f"✅ Config '{config}' is valid.")
        logger.info(f"Pipeline: {cfg.pipeline_name} (Tier {cfg.pipeline_tier})")
    except Exception:
        logger.error(f"❌ Config '{config}' is invalid.")

if __name__ == "__main__":
    app()
