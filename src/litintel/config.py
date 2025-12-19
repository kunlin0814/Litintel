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

class AIConfig(BaseModel):
    provider: AIProvider
    model_default: str
    model_escalate: str
    max_chars: int = 80000
    prompt_template: str
    escalation_triggers: Optional[Dict[str, Any]] = None

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
