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
tierc_app = typer.Typer(help="Tier C: figure-grounded multimodal PDF enrichment")

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


@tierc_app.command("inbox")
def tierc_inbox(
    config: str = "configs/tier1_pca.yaml",
    model: str = "gemini-3.1-pro-preview",
    dry_run: bool = False,
):
    """Process the Drive inbox: any new PDF whose PMID is not yet in Notion."""
    import os

    inbox_id = os.environ.get("GOOGLE_DRIVE_TIERC_INBOX_FOLDER_ID")
    output_id = os.environ.get("GOOGLE_DRIVE_TIERC_OUTPUT_FOLDER_ID")
    if not inbox_id or not output_id:
        logger.error(
            "Tier C inbox: required env vars not set. "
            "GOOGLE_DRIVE_TIERC_INBOX_FOLDER_ID=%s GOOGLE_DRIVE_TIERC_OUTPUT_FOLDER_ID=%s",
            bool(inbox_id), bool(output_id),
        )
        raise typer.Exit(code=2)

    notion_db_id = os.environ.get("NOTION_DB_ID")
    notion_index = {}
    if notion_db_id:
        from litintel.storage.notion import build_notion_index
        try:
            notion_index = build_notion_index(notion_db_id)
            logger.info("Tier C inbox: Notion index has %d PMIDs", len(notion_index))
        except Exception:
            logger.exception("Tier C inbox: failed to build Notion index (continuing without dedup)")
    else:
        logger.warning("Tier C inbox: NOTION_DB_ID not set; running without dedup")

    from litintel.storage.drive import get_drive_service
    from litintel.tierc.inbox import list_inbox_pdfs, process_inbox

    service = get_drive_service()

    if dry_run:
        files = list_inbox_pdfs(service, inbox_id)
        logger.info("Tier C inbox dry-run: %d PDF(s)", len(files))
        for f in files:
            logger.info("  - %s (%s, %d bytes)", f["name"], f["id"], f["size"])
        return

    records = process_inbox(
        drive_service=service,
        inbox_folder_id=inbox_id,
        notion_index=notion_index,
        output_folder_id=output_id,
        engine_model=model,
    )
    logger.info("Tier C inbox: processed %d file(s)", len(records))
    for r in records:
        logger.info(
            "  PMID=%s status=%s figs=%d verify=%s",
            r.PMID, r.TierC_Status, r.TierC_FigureCount, r.TierC_VerificationStatus,
        )


@tierc_app.command("pmid")
def tierc_pmid(
    pmid: str,
    config: str = "configs/tier1_pca.yaml",
    model: str = "gemini-3.1-pro-preview",
):
    """Run Tier C for a single PMID (must have PMC OA PDF).

    Writes JSON artifact locally to /tmp/<PMID>_tierC.json.
    Drive/Notion upload is wired in Step 4.
    """
    import json
    from litintel.pubmed.client import fetch_details, fetch_pmc_pdf
    import xml.etree.ElementTree as ET

    # Resolve PMCID from the PMID
    pmcid = None
    try:
        xml = fetch_details([pmid])
        if xml:
            root = ET.fromstring(xml)
            for art_id in root.iter("ArticleId"):
                if art_id.attrib.get("IdType") == "pmc":
                    pmcid = art_id.text.strip()
                    break
    except Exception:
        logger.exception("Failed to resolve PMCID for PMID %s", pmid)

    if not pmcid:
        logger.error("No PMCID found for PMID %s; cannot fetch PMC OA PDF", pmid)
        raise typer.Exit(code=2)

    logger.info("Tier C pmid: PMID=%s -> PMCID=%s", pmid, pmcid)
    pdf_bytes = fetch_pmc_pdf(pmcid)
    if not pdf_bytes:
        logger.error("Failed to fetch PMC OA PDF for %s", pmcid)
        raise typer.Exit(code=3)
    logger.info("Tier C pmid: fetched %d bytes of PDF", len(pdf_bytes))

    from litintel.tierc.engine import run_all_stages

    artifact, usage, warnings = run_all_stages(pdf_bytes, model=model)
    artifact = artifact.model_copy(update={"pmid": pmid, "source": "PMC_OA"})

    out_path = f"/tmp/{pmid}_tierC.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(artifact.model_dump(), fh, indent=2, ensure_ascii=True)
    logger.info("Tier C pmid: wrote %s", out_path)
    logger.info(
        "Tier C pmid: figs=%d anchors=%d methods=%d findings=%d warnings=%d",
        len(artifact.evidence_map.figures),
        len(artifact.evidence_map.anchors),
        len(artifact.evidence_map.methods.BioinfoMethods),
        len(artifact.synthesis.TopFindings),
        len(warnings),
    )
    logger.info(
        "Tier C pmid: usage In=%s Out=%s Cached=%s Thinking=%s",
        usage.get("input"), usage.get("output"),
        usage.get("cached"), usage.get("thinking"),
    )


app.add_typer(tierc_app, name="tier-c")

if __name__ == "__main__":
    app()
