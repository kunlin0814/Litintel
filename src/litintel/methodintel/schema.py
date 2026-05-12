from datetime import date as _date
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


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


class SourceRefKind(str, Enum):
    """Where an EvidenceClaim's source lives."""

    PMID = "pmid"
    DOI = "doi"
    URL = "url"
    DOCS_URL = "docs_url"
    GITHUB_URL = "github_url"
    PERSONAL_OBS = "personal_obs"


class SourceRef(BaseModel):
    """Typed pointer to the evidence supporting a single claim."""

    kind: SourceRefKind
    value: str
    note: Optional[str] = None


class EvidenceClaim(BaseModel):
    """One supported assertion. source_ref is required by design.

    The whole point of this model is to make 'no claim without a source'
    a schema-level invariant, not a string convention.
    """

    statement: str
    source_ref: SourceRef
    verified: Optional[bool] = None


class LifecycleStatus(str, Enum):
    """v1 lifecycle taxonomy. Expanded to 6 tiers in Phase 4.5."""

    CURRENT = "current"
    UNDER_REVIEW = "under_review"
    LEGACY = "legacy"


class MethodOption(BaseModel):
    """One candidate inside a decision dossier.

    Algorithm vs implementation are kept separate fields because the same
    algorithm (e.g. Leiden) is exposed by multiple implementations
    (ArchR, Seurat, Scanpy, SnapATAC2) with materially different
    pipeline-fit consequences.
    """

    name: str
    algorithm: str
    implementation: str
    version: Optional[str] = None
    lifecycle_status: LifecycleStatus = LifecycleStatus.CURRENT
    last_reviewed: Optional[_date] = None
    successor_methods: List[str] = Field(default_factory=list)
    benchmark_evidence: List[EvidenceClaim] = Field(default_factory=list)
    notes: Optional[str] = None


class TradeoffDimension(BaseModel):
    """One axis in the trade-off matrix, with per-option values."""

    name: str
    description: str
    per_option: Dict[str, str] = Field(default_factory=dict)


class ValidationExperiment(BaseModel):
    """The concrete experiment that would resolve the decision."""

    summary: str
    success_criterion: str
    estimated_effort: Optional[str] = None


class MethodGraphEdge(BaseModel):
    """One edge in the v1 JSON-only method graph.

    The graph is stored as JSON for v1; this model exists so the graph is
    queryable before a visual view is added.
    """

    src: str
    dst: str
    edge_type: str
    evidence_ref: Optional[SourceRef] = None

    ALLOWED_EDGE_TYPES: frozenset = frozenset({
        "competes_with",
        "replaces_or_modernizes",
        "implements",
        "requires",
        "feeds_into",
        "validated_by",
        "contradicted_by",
        "deprecated_by",
        "sensitive_to",
    })

    @model_validator(mode="after")
    def _validate_edge_type(self) -> "MethodGraphEdge":
        if self.edge_type not in self.ALLOWED_EDGE_TYPES:
            raise ValueError(
                f"edge_type {self.edge_type!r} not in allowed set "
                f"{sorted(self.ALLOWED_EDGE_TYPES)}"
            )
        return self


class MethodDecisionDossier(BaseModel):
    """Top-level container for one routed decision question."""

    decision_question: str
    stage: str
    options: List[MethodOption]
    tradeoffs: List[TradeoffDimension] = Field(default_factory=list)
    validation_experiment: Optional[ValidationExperiment] = None
    recommendation: Optional[str] = None
    open_questions: List[str] = Field(default_factory=list)
    graph_edges: List[MethodGraphEdge] = Field(default_factory=list)
