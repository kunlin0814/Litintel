from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class RouterMode(str, Enum):
    """Supported MethodIntel entry modes."""

    LEARN_METHOD = "learn_method"
    COMPARE_METHODS = "compare_methods"
    CHOOSE_FOR_DATASET = "choose_for_dataset"
    STAGE_OVERVIEW = "stage_overview"
    STALENESS_CHECK = "staleness_check"


class ArtifactType(str, Enum):
    """Structured artifact produced by a routed question."""

    METHOD_CARD = "method_card"
    DECISION_DOSSIER = "decision_dossier"
    CONTEXT_RECOMMENDATION = "context_specific_recommendation"
    STAGE_MAP = "stage_map"
    LIFECYCLE_REPORT = "lifecycle_report"


class SourceType(str, Enum):
    """Evidence source categories available to MethodIntel."""

    EXISTING_METHODINTEL = "existing_methodintel"
    NOTION_PAGES = "notion_pages"
    BENCHMARK_PAPERS = "benchmark_papers"
    ORIGINAL_PAPERS = "original_papers"
    OFFICIAL_DOCS = "official_docs"
    GITHUB_REPOS = "github_repos"
    GITHUB_ISSUES = "github_issues"
    RECENT_REVIEWS = "recent_reviews"
    BROAD_WEB_FALLBACK = "broad_web_fallback"


class MethodIntelContext(BaseModel):
    """Extracted scientific and implementation context for a routed question."""

    modality: Optional[str] = None
    platform: Optional[str] = None
    stack: Optional[str] = None
    biological_goal: Optional[str] = None
    compute_context: Optional[str] = None
    design_context: Optional[str] = None


class RouterDecision(BaseModel):
    """Router output used to decide retrieval and artifact generation."""

    query: str
    mode: RouterMode
    artifact: ArtifactType
    stage: Optional[str] = None
    methods: List[str] = Field(default_factory=list)
    implementations: List[str] = Field(default_factory=list)
    context: MethodIntelContext = Field(default_factory=MethodIntelContext)
    missing_constraints: List[str] = Field(default_factory=list)
    source_plan: List[SourceType] = Field(default_factory=list)
    verify_items: List[str] = Field(default_factory=list)
    rationale: str = ""

    def as_cli_dict(self) -> Dict[str, object]:
        """Return a compact dict with enum values for CLI/YAML output."""
        data = self.model_dump(mode="json", exclude_none=True)
        if "context" in data:
            data["context"] = {
                key: value
                for key, value in data["context"].items()
                if value is not None
            }
        return data
