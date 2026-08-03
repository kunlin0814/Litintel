import logging
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class PipelineTier(int, Enum):
    TIER1 = 1
    TIER2 = 2

class DiscoveryMode(str, Enum):
    AUTHOR_SEEDED = "AUTHOR_SEEDED"
    KEYWORD = "KEYWORD"
    MIXED = "MIXED"

class AIProvider(str, Enum):
    GEMINI = "gemini"
    OPENAI = "openai"

class DiscoveryConfig(BaseModel):
    mode: DiscoveryMode
    queries: Optional[List[str]] = None
    seed_authors: Optional[List[str]] = None
    keyword_queries: Optional[List[str]] = None
    retmax: int = 30
    reldays: int = 365

class EscalationTriggersConfig(BaseModel):
    """Configuration for heuristic-based escalation to Shadow Judge."""
    # H2: Score range triggering escalation
    score_range: List[int] = [70, 79]
    # H1: Short rationale threshold
    min_rationale_length: int = 50
    # H4: High reuse score threshold
    escalate_on_high_reuse: int = 4
    # H3: Text/score mismatch thresholds
    h3_high_score_thresh: int = 80
    h3_low_score_thresh: int = 70
    # Upfront escalation (complexity-based)
    min_chars: Optional[int] = None
    min_modalities: Optional[int] = None
    modality_keywords: List[str] = []
    # Behavior
    retry_on_error: bool = True

class AIConfig(BaseModel):
    provider: AIProvider
    # Legacy / Default Single-Pass Fields (Optional now)
    model_default: Optional[str] = "gpt-5-nano"
    model_escalate: Optional[str] = "gpt-5-mini"
    
    # Two-Pass Architecture Fields
    pass1_model_fulltext: Optional[str] = None
    pass1_thinking_fulltext: Optional[str] = None
    pass1_model_abstract: Optional[str] = None
    pass1_thinking_abstract: Optional[str] = None
    pass2_model: Optional[str] = None
    pass2_thinking: Optional[str] = None
    pass2_min_score: int = 88
    
    max_chars: int = 80000
    prompt_template: str
    escalation_triggers: Optional[EscalationTriggersConfig] = None

class NotionConfig(BaseModel):
    enabled: bool = False
    database_id_env: str

class DriveConfig(BaseModel):
    enabled: bool = False
    folder_id_env: Optional[str] = None
    markdown_grouping: Optional[str] = None
    papers_jsonl_file_id_env: Optional[str] = None
    notebooklm_folder_id_env: Optional[str] = None
    methods_folder_id_env: Optional[str] = None
    upload_pdfs: bool = False
    pdf_min_score: int = 88
    pdf_folder_name: str = "PDFs"
    pdf_folder_id_env: Optional[str] = None

class MarkdownBundleConfig(BaseModel):
    enabled: bool = False
    output_dir: Optional[str] = None

class CsvConfig(BaseModel):
    enabled: bool = True
    filename: str

class StorageConfig(BaseModel):
    notion: Optional[NotionConfig] = None
    drive: Optional[DriveConfig] = None
    markdown_bundle: Optional[MarkdownBundleConfig] = None
    csv: Optional[CsvConfig] = None

class DedupConfig(BaseModel):
    keys: List[str] = ["DOI", "PMID"]

class TierCConfig(BaseModel):
    """Tier C (figure-grounded multimodal PDF enrichment) settings."""
    enabled: bool = False
    model: str = "gemini-3.1-pro-preview"
    thinking: str = "MEDIUM"
    min_score: int = 90
    inbox_folder_id_env: str = "GOOGLE_DRIVE_TIERC_INBOX_FOLDER_ID"
    output_folder_id_env: str = "GOOGLE_DRIVE_TIERC_OUTPUT_FOLDER_ID"
    process_inbox_in_cron: bool = True
    max_size_mb: float = 18.0
    chunk_pages: int = 25
    max_chunks: int = 4
    identity_model: str = "gemini-3.6-flash"

class RagAgentConfig(BaseModel):
    """Vertex RAG corpus sync + the natural-language query agent (agent/cli.py).

    Resource identifiers (corpus name, GCP project) stay in .env because they are
    deployment credentials; every model and tuning knob lives here.
    """
    model: str = "gemini-3.6-flash"
    thinking: str = "LOW"
    location: str = "us-east5"
    top_k: int = 10
    vector_distance_threshold: float = 0.5
    # Minimum RelevanceScore for a paper to be ingested into the RAG corpus.
    min_score: int = 85


class AppConfig(BaseModel):
    pipeline_tier: PipelineTier
    pipeline_name: str
    discovery: DiscoveryConfig
    ai: AIConfig
    storage: StorageConfig
    dedup: DedupConfig
    tier_c: Optional[TierCConfig] = None
    rag_agent: RagAgentConfig = Field(default_factory=RagAgentConfig)
    # Path to the bioinfo-methods knowledge base (a directory in the dotfiles
    # repo). Litintel WRITES records here and never commits -- the human commits
    # in dotfiles, which is the review gate. None disables the methods feed.
    methods_repo_path: Optional[str] = None

def load_config_from_yaml(path: str) -> AppConfig:
    import yaml
    from dotenv import load_dotenv

    # Still needed: credentials and Drive/Notion IDs come from .env.
    load_dotenv()

    with open(path, "r") as f:
        raw = yaml.safe_load(f)

    # The YAML file is the single source of truth for models and thinking effort.
    # Env vars deliberately do NOT override it -- a silent env override made the
    # committed config unreliable to read. Change models by editing configs/*.yaml.
    cfg = AppConfig(**raw)

    logger.info(
        "Config %s -- pass1: %s/%s (fulltext) %s/%s (abstract) | pass2: %s/%s | escalate: %s",
        path,
        cfg.ai.pass1_model_fulltext, cfg.ai.pass1_thinking_fulltext,
        cfg.ai.pass1_model_abstract, cfg.ai.pass1_thinking_abstract,
        cfg.ai.pass2_model, cfg.ai.pass2_thinking,
        cfg.ai.model_escalate,
    )
    if cfg.tier_c and cfg.tier_c.enabled:
        logger.info(
            "Config %s -- tier_c: %s/%s (identity: %s)",
            path, cfg.tier_c.model, cfg.tier_c.thinking, cfg.tier_c.identity_model,
        )
    logger.info(
        "Config %s -- rag_agent: %s/%s (min_score: %d, top_k: %d)",
        path, cfg.rag_agent.model, cfg.rag_agent.thinking,
        cfg.rag_agent.min_score, cfg.rag_agent.top_k,
    )

    return cfg


