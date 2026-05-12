import typer
import yaml
import logging
from rich.logging import RichHandler
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()

from litintel.config import AppConfig, load_config_from_yaml
from litintel.pipeline.tier1 import run_tier1_pipeline
from litintel.pipeline.tier2 import run_tier2_pipeline
from litintel.methodintel.router import route_question

# Configure Logging (ONE time)
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)]
)

# Silence verbose HTTP logs (do NOT call basicConfig again)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

logger = logging.getLogger("litintel")

app = typer.Typer(help="Literature Intelligence CLI")
methodintel_app = typer.Typer(help="MethodIntel method-decision tools")

@app.command()
def tier1(config: str = "configs/tier1_pca.yaml", limit: int = None):
    """Run Tier-1 (PCa) Pipeline"""
    cfg = load_config_from_yaml(config)
    run_tier1_pipeline(cfg, limit=limit)

@app.command()
def tier2(config: str = "configs/tier2_methods.yaml"):
    """Run Tier-2 (Methods) Pipeline"""
    cfg = load_config_from_yaml(config)
    run_tier2_pipeline(cfg)

@app.command()
def validate(config: str):
    """Validate a configuration file"""
    try:
        cfg = load_config_from_yaml(config)
        logger.info(f"Config '{config}' is valid.")
        logger.info(f"Pipeline: {cfg.pipeline_name} (Tier {cfg.pipeline_tier})")
    except Exception:
        logger.exception(f"Config '{config}' is invalid.")

@methodintel_app.command("route")
def methodintel_route(question: str):
    """Route a MethodIntel question to mode, artifact, and source plan."""
    decision = route_question(question)
    typer.echo(yaml.safe_dump(decision.as_cli_dict(), sort_keys=False))

app.add_typer(methodintel_app, name="methodintel")

if __name__ == "__main__":
    app()
