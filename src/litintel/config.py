from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

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

class AppConfig(BaseModel):
    pipeline_tier: PipelineTier
    pipeline_name: str
    discovery: DiscoveryConfig
    ai: AIConfig
    storage: StorageConfig
    dedup: DedupConfig

def load_config_from_yaml(path: str) -> AppConfig:
    import yaml
    with open(path, "r") as f:
        raw = yaml.safe_load(f)
    return AppConfig(**raw)
